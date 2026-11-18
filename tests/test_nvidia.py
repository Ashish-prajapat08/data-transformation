import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from agent.nvidia import NVIDIAChatModel, DEFAULT_MODEL
from agent.planning import LLMPlanner, configured_planner
from agent.graph import MigrationAgent
from agent.state import MigrationState
from models.migration import MigrationPlan, EntityReasoning, TargetSchema, FieldRule
import pandas as pd


def fake_client(content, finish_reason='stop'):
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[
        SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))])
    return client


def plan_json():
    return json.dumps({'explanation': 'Normalize email', 'mappings': [
        {'source': 'email', 'target': 'email', 'confidence': 1, 'reason': 'same column'}],
        'tools': [{'tool': 'normalize_email', 'column': 'email', 'reason': 'Normalize'}]})


def test_nvidia_transport_and_graph():
    client = fake_client(plan_json())
    planner = LLMPlanner(NVIDIAChatModel(client))
    agent = MigrationAgent(planner)
    state = agent.invoke(MigrationState(frame=pd.DataFrame({'email': [' A@B.COM ']}),
        target_schema=TargetSchema(fields=[FieldRule(name='email', kind='email')])))
    assert state.status == 'awaiting_plan'
    assert state.migration_plan.planner == 'llm'
    state.status = 'approved'
    state = agent.invoke(state)
    assert state.status == 'ready'
    assert state.frame.iloc[0, 0] == 'a@b.com'
    args = client.chat.completions.create.call_args.kwargs
    assert args['model'] == DEFAULT_MODEL
    assert args['response_format'] == {'type': 'json_object'}
    assert args['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    assert args['messages'][1]['role'] == 'user'
    assert 'A@B.COM' not in str(args['messages'])
    assert 'JSON schema' in args['messages'][0]['content']


@pytest.mark.parametrize('content,finish', [('{}', 'stop'), ('not JSON', 'stop'), (None, 'stop'), (plan_json(), 'length')])
def test_invalid_nvidia_responses_fail_closed(content, finish):
    output = NVIDIAChatModel(fake_client(content, finish)).with_structured_output(MigrationPlan)
    with pytest.raises((ValueError, ValidationError)):
        output.invoke([('system', 'Plan a migration'), ('human', '{}')])


def test_nvidia_entity_contract():
    client = fake_client(json.dumps({'confidence': .6, 'reason': 'Similar legal names', 'recommendation': 'review'}))
    result = NVIDIAChatModel(client).with_structured_output(EntityReasoning).invoke([('human', 'ABC Pvt Ltd / ABC Private Ltd')])
    assert result.confidence == .6
    assert client.chat.completions.create.call_args.kwargs['messages'][0]['role'] == 'system'


def test_provider_selection_uses_nvidia_key_only(monkeypatch):
    monkeypatch.setenv('PLANNER_MODE', 'llm')
    monkeypatch.setenv('LLM_PROVIDER', 'nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY', 'test-key-not-real')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    client = Mock()
    monkeypatch.setattr('agent.nvidia.OpenAI', client)
    assert isinstance(configured_planner().base_model, NVIDIAChatModel)
    kwargs = client.call_args.kwargs
    assert kwargs['api_key'] == 'test-key-not-real'
    assert kwargs['base_url'] == 'https://integrate.api.nvidia.com/v1'


def test_missing_key_error_does_not_expose_secret(monkeypatch):
    monkeypatch.setenv('NVIDIA_API_KEY', '$NVIDIA_API_KEY')
    with pytest.raises(ValueError, match='requires NVIDIA_API_KEY'):
        NVIDIAChatModel()



def test_invalid_target_column_gets_one_bounded_repair():
    bad = json.loads(plan_json())
    bad['tools'][0]['column'] = 'source_email_alias'
    responses = [json.dumps(bad), plan_json()]
    client = fake_client(plan_json())
    client.chat.completions.create.side_effect = [SimpleNamespace(choices=[
        SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=value))]) for value in responses]
    state = MigrationState(frame=pd.DataFrame({'email': [' A@B.COM ']}),
        target_schema=TargetSchema(fields=[FieldRule(name='email', kind='email')]))
    agent = MigrationAgent(LLMPlanner(NVIDIAChatModel(client)))
    state = agent.invoke(state)
    assert state.status == 'awaiting_plan'
    assert client.chat.completions.create.call_count == 2
    context = json.loads(client.chat.completions.create.call_args.kwargs['messages'][1]['content'])
    assert context['plan_validation_error'] == 'Unknown tool column'
    assert context['valid_target_columns'] == ['email']
    assert context['tool_contracts'][0] == {'tool': 'normalize_email', 'column': 'email', 'kind': 'email'}
    assert any(event.action == 'repair_invalid_plan' for event in state.trace)
    assert state.retry_count == 0
    state.status = 'approved'
    assert agent.invoke(state).status == 'ready'


def test_repeated_invalid_plan_stops_and_hides_response():
    bad = json.loads(plan_json())
    bad['tools'][0]['column'] = 'never_execute_this'
    client = fake_client(json.dumps(bad))
    state = MigrationState(frame=pd.DataFrame({'email': ['a@b.com']}),
        target_schema=TargetSchema(fields=[FieldRule(name='email', kind='email')]))
    state = MigrationAgent(LLMPlanner(NVIDIAChatModel(client))).invoke(state)
    assert state.status == 'failed'
    assert client.chat.completions.create.call_count == 2
    assert state.trace[-1].metadata['category'] == 'invalid_plan'
    assert 'never_execute_this' not in str(state.errors)
    assert not any(event.node == 'execute' for event in state.trace)



def test_dataset_entity_tool_binds_only_configured_field():
    from agent.planning import guard_plan
    state = MigrationState(frame=pd.DataFrame({'organization': ['ABC']}),
        target_schema=TargetSchema(fields=[FieldRule(name='company')], entity_field='company'))
    state.source_schema = {'organization': 'object'}
    plan = MigrationPlan(explanation='Review entities', mappings=[
        {'source': 'organization', 'target': 'company', 'confidence': 1, 'reason': 'alias'}],
        tools=[{'tool': 'resolve_entities', 'column': None, 'reason': 'Inspect dataset'}])
    assert guard_plan(plan,state).tools[0].column == 'company'
    plan.tools[0].column = 'organization'
    with pytest.raises(ValueError):
        guard_plan(plan,state)
