"""One orchestrator: profile → plan → approval → tools → validate → retry/review."""
from langgraph.graph import StateGraph, START, END
from agent.state import MigrationState
from agent.planning import configured_planner, guard_plan
from models.migration import ReviewItem
from tools.profiling import profile_data, inspect_schema
from tools.schema_mapping import map_schema
from tools.transformations import TRANSFORMERS, handle_missing_values
from tools.duplicates import detect_duplicates
from tools.entity_resolution import resolve_entities
from tools.validation import validate_data


def request_human_review(state, items):
    state.review_items.extend(items)
    state.record('human_review', 'request_human_review', count=len(items), kinds=sorted({item.kind for item in items}))


class MigrationAgent:
    def __init__(self, planner=None):
        self.planner = planner or configured_planner()
        builder = StateGraph(MigrationState)
        for name, node in [('profile', self.profile), ('plan', self.plan), ('execute', self.execute),
                           ('validate', self.validate), ('replan', self.replan), ('review', self.review),
                           ('complete', self.complete)]:
            def checkpointed(state, config, operation=node):
                result = operation(state, config) if operation == self.execute else operation(state)
                callback = config.get('configurable', {}).get('checkpoint')
                if callback:
                    callback(state)
                return result
            builder.add_node(name, checkpointed)
        builder.add_conditional_edges(START, self.entry, {'profile': 'profile', 'execute': 'execute', 'validate': 'validate'})
        builder.add_edge('profile', 'plan')
        builder.add_edge('plan', END)  # Durable application-level approval checkpoint.
        builder.add_edge('execute', 'validate')
        builder.add_conditional_edges('validate', self.route_validation,
                                      {'replan': 'replan', 'review': 'review', 'complete': 'complete'})
        builder.add_edge('replan', 'execute')
        builder.add_edge('review', END)
        builder.add_edge('complete', END)
        self.graph = builder.compile()

    @staticmethod
    def entry(state):
        return {'new': 'profile', 'approved': 'execute', 'reviewing': 'validate'}[state.status]

    def invoke(self, state, checkpoint=None):
        latest = state

        def track(progress):
            nonlocal latest
            latest = progress.model_copy(deep=True)
            if checkpoint:
                checkpoint(progress)

        try:
            result = self.graph.invoke(state, {'recursion_limit': 40, 'configurable': {'checkpoint': track}})
            return MigrationState.model_validate(result)
        except Exception as error:
            # No exception text: providers and DB drivers may embed credentials/payloads.
            state = latest
            state.status = 'failed'
            category = 'invalid_plan' if isinstance(error, ValueError) and state.migration_plan is None else 'stage_error'
            message = ('AI planning failed: the response did not satisfy the target schema or tool constraints. '
                       'Start a new run after checking planner configuration.' if category == 'invalid_plan' else
                       'Migration stage failed; check configuration or plan constraints')
            state.errors.append(message)
            state.record('error', 'failed', retry_count=state.retry_count, category=category)
            return state

    @staticmethod
    def profile(state):
        state.dataset_profile = profile_data(state.frame)
        state.source_schema = inspect_schema(state.frame)
        state.record('profile', 'profile_data', rows=len(state.frame), columns=len(state.frame.columns))
        state.record('profile', 'inspect_schema', columns=list(state.source_schema))
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}

    def plan(self, state):
        plan = guard_plan(self.planner.plan(state), state)
        state.migration_plan = plan
        state.plan_history.append(plan.model_copy(deep=True))
        state.status = 'awaiting_plan'
        state.record('plan', 'migration_plan', planner=plan.planner, tools=[c.tool for c in plan.tools])
        request_human_review(state, [ReviewItem(id='mapping:' + item.target, kind='mapping',
            column=item.target, confidence=item.confidence, reason=item.reason,
            recommendation='Select the correct source column or explicitly leave unmapped', actions=['map'])
            for item in plan.mappings if item.confidence < .85 or item.source is None])
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}

    def execute(self, state, config=None):
        if state.retry_count == 0:
            # Deduplicate only complete source rows. Distinct records that collapse after mapping
            # must remain visible to uniqueness validation / entity review.
            calls = state.migration_plan.tools
            if any(call.tool == 'detect_duplicates' for call in calls):
                rows = detect_duplicates(state.frame)
                state.frame = state.frame.drop(index=rows).copy()
                state.record('execute', 'detect_duplicates', removed_rows=rows, removed_count=len(rows))
            state.frame = map_schema(state.frame, state.migration_plan.mappings, state.target_schema)
            state.record('execute', 'map_schema', columns=list(state.frame.columns))
        state.status = 'executing'
        fields = {field.name: field for field in state.target_schema.fields}
        for call in state.migration_plan.tools:
            if call.tool == 'detect_duplicates':
                continue
            if call.tool == 'resolve_entities':
                # Delayed until all transformations have finished.
                continue
            before = state.frame[call.column].copy()
            rule = fields[call.column]
            if call.tool == 'handle_missing_values':
                state.frame[call.column] = handle_missing_values(before, rule)
            else:
                state.frame[call.column] = before.map(lambda value: TRANSFORMERS[call.tool](value, rule))
            changed = int((before.fillna('') != state.frame[call.column].fillna('')).sum())
            state.record('execute', call.tool, column=call.column, changed_cells=changed)
            callback = (config or {}).get('configurable', {}).get('checkpoint')
            if callback:
                callback(state)
        if state.retry_count == 0 and state.target_schema.entity_field:
            candidates = resolve_entities(state.frame, state.target_schema.entity_field)
            if hasattr(self.planner, 'reason_entities') and candidates:
                candidates = self.planner.reason_entities(state.frame, candidates)
                state.record('execute', 'entity_reasoning', planner='llm', assessed=min(len(candidates), 50))
            request_human_review(state, candidates)
            state.record('execute', 'resolve_entities', candidates=sum(i.kind == 'entity' for i in state.review_items))
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}

    @staticmethod
    def validate(state):
        state.validation_results = validate_data(state.frame, state.target_schema)
        state.record('validate', 'validate_data', passed=state.validation_results.passed,
                     issue_count=len(state.validation_results.issues), readiness=state.validation_results.readiness)
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}

    @staticmethod
    def route_validation(state):
        if not state.validation_results.passed and state.retry_count < state.max_retries:
            return 'replan'
        if not state.validation_results.passed or any(item.decision is None for item in state.review_items):
            return 'review'
        return 'complete'

    def replan(self, state):
        plan = guard_plan(self.planner.plan(state, retry=True), state, retry=True)
        state.retry_count += 1
        state.migration_plan = plan
        state.plan_history.append(plan.model_copy(deep=True))
        state.record('replan', 'corrective_plan', retry=state.retry_count, tools=[call.tool for call in plan.tools])
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}

    @staticmethod
    def review(state):
        # Replace obsolete validation items after corrections, retain their decisions in the audit.
        state.review_items = [item for item in state.review_items if item.kind != 'validation']
        if not state.validation_results.passed:
            request_human_review(state, [ReviewItem(id=f'validation:{issue.column}:{issue.code}',
                kind='validation', column=issue.column, rows=issue.rows, confidence=0,
                reason=issue.message, recommendation='Provide verified values; unresolved failures block export',
                actions=['correct']) for issue in state.validation_results.issues])
        state.status = 'awaiting_review'
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}

    @staticmethod
    def complete(state):
        state.status = 'ready'
        state.record('complete', 'migration_ready', rows=len(state.frame))
        return state.model_dump(exclude={'frame'}) | {'frame': state.frame}
