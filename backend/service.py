import os
from agent.graph import MigrationAgent
from agent.state import MigrationState
from backend.persistence import Store
from models.migration import ReviewDecision
from tools.ingestion import load_file
from tools.export import export_data


class MigrationService:
    def __init__(self, store=None, agent=None):
        self.store = store or Store()
        self.agent = agent or MigrationAgent()

    def create(self, content, filename, target, instructions=''):
        frame = load_file(content, filename)
        state = MigrationState(frame=frame, target_schema=target, instructions=instructions,
            source_metadata={'filename': os.path.basename(filename), 'bytes': len(content), 'rows': len(frame)},
            max_retries=int(os.getenv('MAX_RETRIES', '2')))
        state = self.agent.invoke(state)
        self.store.save(state)
        return state

    def approve(self, run_id, approved, execute=True):
        state, version = self.store.load(run_id)
        if state.status != 'awaiting_plan':
            raise ValueError('Run is not awaiting plan approval')
        if approved and any(item.kind == 'mapping' and item.decision is None for item in state.review_items):
            raise ValueError('Resolve all ambiguous mappings before approving the plan')
        state.record('approval', 'plan_approved' if approved else 'plan_rejected',
                     destructive_operations=[call.tool for call in state.migration_plan.tools
                                             if call.tool == 'detect_duplicates'])
        state.status = 'approved' if approved else 'rejected'
        # Persist approved state before execution so failed/restarted workers can resume explicitly.
        version = self.store.save(state, version)
        if approved and execute:
            state = self._execute(state, version)
        return state

    def review(self, run_id, decisions: list[ReviewDecision]):
        state, version = self.store.load(run_id)
        if state.status not in ('awaiting_plan', 'awaiting_review'):
            raise ValueError('Run is not awaiting human review')
        if not decisions or len({decision.item_id for decision in decisions}) != len(decisions):
            raise ValueError('Provide distinct review decisions')
        for decision in decisions:
            item = next((item for item in state.review_items if item.id == decision.item_id), None)
            if item is None or item.decision is not None or decision.action not in item.actions:
                raise ValueError('Unknown, already resolved, or incompatible review decision')
            if item.kind == 'mapping':
                if decision.source is not None and decision.source not in state.source_schema:
                    raise ValueError('Unknown source column')
                mapping = next(mapping for mapping in state.migration_plan.mappings if mapping.target == item.column)
                mapping.source = decision.source
                mapping.confidence = 1
                mapping.reason = 'Explicit human mapping decision'
            elif item.kind == 'entity' and decision.action == 'merge':
                keep, drop = item.rows
                if keep not in state.frame.index or drop not in state.frame.index:
                    raise ValueError('Entity rows changed; refresh review')
                # Merge is an explicit destructive keep-first decision, never an automatic guess.
                state.frame = state.frame.drop(index=drop)
                for related in state.review_items:
                    if related.kind == 'entity' and drop in related.rows and related.id != item.id:
                        related.decision = 'obsolete_after_merge'
                state.record('review', 'entity_merge', kept_row=keep, removed_row=drop)
            elif item.kind == 'validation':
                if not decision.values:
                    raise ValueError('Corrections require row values')
                for row_text, value in decision.values.items():
                    try:
                        row = int(row_text)
                    except ValueError:
                        raise ValueError('Correction row must be an integer') from None
                    if row not in item.rows or row not in state.frame.index:
                        raise ValueError('Correction row is outside this review item')
                    state.frame.at[row, item.column] = value
            item.decision = decision.action
            state.record('review', 'human_decision', item_id=item.id, decision=decision.action,
                         corrected_rows=list(decision.values))
        if state.status == 'awaiting_plan':
            state.plan_history.append(state.migration_plan.model_copy(deep=True))
        elif not any(item.decision is None for item in state.review_items):
            state.status = 'reviewing'
            state = self.agent.invoke(state)
        self.store.save(state, version)
        return state

    def _execute(self, state, version):
        current_version = version

        def checkpoint(progress):
            nonlocal current_version
            current_version = self.store.save(progress, current_version)

        state = self.agent.invoke(state, checkpoint=checkpoint)
        self.store.save(state, current_version)
        return state

    def resume(self, run_id):
        state, version = self.store.load(run_id)
        if state.status not in ('approved', 'executing'):
            raise ValueError('Only interrupted execution runs can be resumed')
        # Working data checkpoints during execution are observable, but not safe to replay.
        # An executing run must be retried from its retained source dataset.
        if state.status == 'executing':
            raise ValueError('Execution was interrupted mid-stage; create a new run from the source file')
        return self._execute(state, version)

    def export(self, run_id):
        state, version = self.store.load(run_id)
        if state.status != 'ready':
            raise ValueError('Migration is not ready for export')
        content = export_data(state.frame, state.target_schema,
                              any(item.decision is None for item in state.review_items))
        state.record('export', 'export_data', rows=len(state.frame), bytes=len(content))
        self.store.save(state, version)
        return content
