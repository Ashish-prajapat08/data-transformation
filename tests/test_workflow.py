from io import BytesIO
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from agent.graph import MigrationAgent
from agent.planning import RulesPlanner, LLMPlanner
from backend.persistence import Store, ConflictError
from backend.service import MigrationService
from backend.main import create_app
from evaluation.generators.problems import scenarios
from evaluation.runner import run_evaluation
from models.migration import FieldRule, TargetSchema, ReviewDecision, MigrationPlan, ToolCall


@pytest.fixture
def service():
    store = Store('sqlite:///:memory:')
    yield MigrationService(store, MigrationAgent(RulesPlanner()))
    store.engine.dispose()


def test_api_upload_plan_execute_export(service):
    fixture = scenarios()[1]
    with TestClient(create_app(service)) as client:
        response = client.post('/migrations', files={'file': ('source.csv', fixture.source.to_csv(index=False))},
                               data={'target_schema': fixture.target.model_dump_json()})
        assert response.status_code == 201, response.text
        state = response.json()
        assert state['status'] == 'awaiting_plan'
        assert 'frame' not in state
        run = state['run_id']
        assert client.get(f'/migrations/{run}/export').status_code == 400
        result = client.post(f'/migrations/{run}/approval', json={'approved': True})
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'approved'
        assert client.get(f'/migrations/{run}').json()['status'] == 'ready'
        exported = client.get(f'/migrations/{run}/export')
        assert exported.status_code == 200
        actual = pd.read_csv(BytesIO(exported.content), dtype=str)
        pd.testing.assert_frame_equal(actual, fixture.expected)
        assert client.get(f'/migrations/{run}/audit').json()[-1]['action'] == 'export_data'
        assert client.post(f'/migrations/{run}/approval', json={'approved': True}).status_code == 400
        assert client.get('/migrations/missing').status_code == 404


def test_ambiguous_mapping_requires_explicit_review(service):
    target = TargetSchema(fields=[FieldRule(name='email', kind='email', required=True)])
    state = service.create(b'unknown\na@b.com\n', 'source.csv', target)
    with pytest.raises(ValueError, match='ambiguous'):
        service.approve(state.run_id, True)
    state = service.review(state.run_id, [ReviewDecision(item_id='mapping:email', action='map', source='unknown')])
    assert state.status == 'awaiting_plan'
    assert service.approve(state.run_id, True).status == 'ready'


def test_failed_validation_retry_human_correction(service):
    target = TargetSchema(fields=[FieldRule(name='email', kind='email', required=True)])
    state = service.create(b'email\nbad\n', 'bad.csv', target)
    state = service.approve(state.run_id, True)
    assert state.status == 'awaiting_review'
    assert state.retry_count == state.max_retries == 2
    with pytest.raises(ValueError):
        service.export(state.run_id)
    item = state.review_items[0]
    state = service.review(state.run_id, [ReviewDecision(item_id=item.id, action='correct', values={'0': 'fixed@example.com'})])
    assert state.status == 'ready'
    assert state.validation_results.passed


def test_review_is_atomic_and_revalidated(service):
    state = service.create(b'email\nbad\n', 'source.csv', TargetSchema(fields=[FieldRule(name='email', kind='email')]))
    state = service.approve(state.run_id, True)
    item = state.review_items[0]
    with pytest.raises(ValueError):
        service.review(state.run_id, [ReviewDecision(item_id=item.id, action='correct', values={'999': 'x@y.com'})])
    persisted, _ = service.store.load(state.run_id)
    assert persisted.frame.iloc[0, 0] == 'bad'
    state = service.review(state.run_id, [ReviewDecision(item_id=item.id, action='correct', values={'0': 'stillbad'})])
    assert state.status == 'awaiting_review'
    assert state.review_items[0].decision is None


def test_entities_keep_or_merge_and_restart(tmp_path):
    url = 'sqlite:///' + str(tmp_path / 'runs.db')
    store = Store(url)
    service = MigrationService(store, MigrationAgent(RulesPlanner()))
    fixture = scenarios()[3]
    state = service.create(fixture.source.to_csv(index=False).encode(), 'entities.csv', fixture.target)
    state = service.approve(state.run_id, True)
    assert state.status == 'awaiting_review'
    store.engine.dispose()
    store = Store(url)
    service = MigrationService(store, MigrationAgent(RulesPlanner()))
    state = service.review(state.run_id, [ReviewDecision(item_id='entity:0:3', action='keep')])
    assert state.status == 'ready'
    assert len(state.frame) == 4
    _, stale_version = store.load(state.run_id)
    store.save(state, stale_version)
    with pytest.raises(ConflictError):
        store.save(state, stale_version)
    store.delete_run(state.run_id)
    with pytest.raises(KeyError):
        store.load(state.run_id)
    store.engine.dispose()


def test_excel_api_and_invalid_uploads(service):
    fixture = scenarios()[0]
    file = BytesIO()
    fixture.source.to_excel(file, index=False)
    with TestClient(create_app(service)) as client:
        result = client.post('/migrations', files={'file': ('source.xlsx', file.getvalue())},
                             data={'target_schema': fixture.target.model_dump_json()})
        assert result.status_code == 201, result.text
        assert result.json()['dataset_profile']['row_count'] == 3
        result = client.post('/migrations', files={'file': ('bad.exe', b'nonsense')},
                             data={'target_schema': fixture.target.model_dump_json()})
        assert result.status_code == 400
        result = client.post('/migrations', files={'file': ('bad.csv', b'a\n1\n')}, data={'target_schema': '{}'})
        assert result.status_code == 422


def test_structured_llm_plans_and_reacts_to_validation(service):
    class StubModel:
        def __init__(self):
            self.messages = []
        def with_structured_output(self, schema):
            assert schema is MigrationPlan
            return self
        def invoke(self, messages):
            import json
            context = json.loads(messages[1][1])
            self.messages.append(context)
            if context['retry']:
                assert context['validation']['passed'] is False
                return MigrationPlan(explanation='Validation found whitespace; call email tool',
                    mappings=[{'source': 'email', 'target': 'email', 'confidence': 1, 'reason': 'same name'}],
                    tools=[ToolCall(tool='normalize_email', column='email', reason='Correct invalid email')])
            return MigrationPlan(explanation='Inspect email field',
                mappings=[{'source': 'email', 'target': 'email', 'confidence': 1, 'reason': 'same name'}], tools=[])
    model = StubModel()
    service.agent = MigrationAgent(LLMPlanner(model))
    state = service.create(b'email\n A@B.COM \n', 'source.csv', TargetSchema(fields=[FieldRule(name='email', kind='email')]))
    state = service.approve(state.run_id, True)
    assert state.status == 'ready'
    assert state.retry_count == 1
    assert state.frame.iloc[0, 0] == 'a@b.com'
    assert len(model.messages) == 2
    assert 'A@B.COM' not in str(model.messages)
    assert state.migration_plan.planner == 'llm'


def test_evaluation_measured_and_reproducible():
    first = run_evaluation()
    second = run_evaluation()
    assert first['metrics'] == second['metrics']
    assert first['fixture_count'] == 4
    assert first['metrics']['task_success_rate'] == .75
    assert first['metrics']['safety_outcome_accuracy'] == 1
    assert first['metrics']['duplicate_detection']['recall'] == 1
    assert first['metrics']['entity_matching']['recall'] == 1


def test_entity_merge_requires_explicit_decision(service):
    fixture = scenarios()[3]
    state = service.create(fixture.source.to_csv(index=False).encode(), 'entities.csv', fixture.target)
    state = service.approve(state.run_id, True)
    with pytest.raises(ValueError):
        service.export(state.run_id)
    state = service.review(state.run_id, [ReviewDecision(item_id='entity:0:3', action='merge')])
    assert state.status == 'ready'
    assert list(state.frame.index) == [0, 1, 2]
    assert any(event.action == 'entity_merge' for event in state.trace)


def test_reject_plan_does_not_transform(service):
    state = service.create(b'email\n A@B.COM \n', 'source.csv', TargetSchema(fields=[FieldRule(name='email', kind='email')]))
    state = service.approve(state.run_id, False)
    assert state.status == 'rejected'
    assert state.frame.iloc[0, 0] == ' A@B.COM '
    assert not any(event.node == 'execute' for event in state.trace)


def test_llm_unknown_tool_and_source_fail_closed(service):
    class BadPlanner:
        def plan(self, state, retry=False):
            return MigrationPlan(explanation='Invalid source', mappings=[
                {'source': 'unknown', 'target': 'email', 'confidence': 1, 'reason': 'untrusted'}], tools=[])
    service.agent = MigrationAgent(BadPlanner())
    state = service.create(b'email\na@b.com\n', 'source.csv', TargetSchema(fields=[FieldRule(name='email')]))
    assert state.status == 'failed'
    assert state.trace[0].action == 'profile_data'
    assert 'unknown' not in str(state.errors)
    with pytest.raises(ValueError):
        ToolCall(tool='execute_python', column='email', reason='malicious')


def test_evaluation_api_persists_report(service):
    with TestClient(create_app(service)) as client:
        response = client.post('/evaluations')
        assert response.status_code == 200
        result = response.json()
        persisted = client.get('/evaluations/' + result['evaluation_id']).json()
        assert persisted['metrics'] == result['metrics']


def test_progress_checkpoints_are_persisted(service):
    fixture = scenarios()[1]
    state = service.create(fixture.source.to_csv(index=False).encode(), 'source.csv', fixture.target)
    state = service.approve(state.run_id, True, execute=False)
    assert service.store.load(state.run_id)[0].status == 'approved'
    saved = []
    original = service.store.save
    def capture(progress, version=None):
        saved.append((progress.status, len(progress.trace)))
        return original(progress, version)
    service.store.save = capture
    state = service.resume(state.run_id)
    assert state.status == 'ready'
    assert sum(status == 'executing' for status, _ in saved) >= len(fixture.target.fields)


def test_export_columns_do_not_collapse_distinct_source_records(service):
    target = TargetSchema(fields=[FieldRule(name='email', kind='email', unique=True)])
    state = service.create(b'email,other\na@b.com,one\na@b.com,two\n', 'source.csv', target)
    state = service.approve(state.run_id, True)
    assert len(state.frame) == 2
    assert state.status == 'awaiting_review'
    assert state.validation_results.issues[0].code == 'unique'


def test_structured_entity_semantics_never_authorize_automatic_merge(service):
    from models.migration import EntityReasoning
    class Model:
        def with_structured_output(self, schema):
            if schema is MigrationPlan:
                class PlanResponse:
                    def invoke(self, messages):
                        import json
                        context = json.loads(messages[1][1])
                        return MigrationPlan(explanation='Normalize and inspect entities',
                            mappings=[{'source': name, 'target': name, 'confidence': 1, 'reason': 'matching name'}
                                      for name in context['source_schema']],
                            tools=[ToolCall(tool='normalize_text', column=name, reason='Normalize')
                                   for name in context['source_schema']])
                return PlanResponse()
            assert schema is EntityReasoning
            class EntityResponse:
                def invoke(self, messages):
                    import json
                    context = json.loads(messages[1][1])
                    assert set(context) == {'organization_names'}
                    return EntityReasoning(confidence=.6, reason='Could be legal-name variants', recommendation='review')
            return EntityResponse()
    service.agent = MigrationAgent(LLMPlanner(Model()))
    target = TargetSchema(fields=[FieldRule(name='company'), FieldRule(name='contact')], entity_field='company')
    state = service.create(b'company,contact\nABC Pvt Ltd,Ada\nABC Private Limited,Ben\n', 'entities.csv', target)
    state = service.approve(state.run_id, True)
    assert state.status == 'awaiting_review'
    assert len(state.frame) == 2
    assert state.review_items[0].confidence == .6
    assert 'legal-name' in state.review_items[0].reason
    assert any(event.action == 'entity_reasoning' for event in state.trace)
