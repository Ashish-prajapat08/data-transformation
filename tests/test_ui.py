"""Render the actual Streamlit app against the actual API using a transport adapter."""
from pathlib import Path
import requests
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from backend.main import create_app
from backend.service import MigrationService
from backend.persistence import Store
from agent.graph import MigrationAgent
from agent.planning import RulesPlanner
from evaluation.generators.problems import scenarios


def test_dashboard_plan_approval_and_results(monkeypatch):
    store = Store('sqlite:///:memory:')
    service = MigrationService(store, MigrationAgent(RulesPlanner()))
    scenario = scenarios()[1]
    state = service.create(scenario.source.to_csv(index=False).encode(), 'source.csv', scenario.target)
    with TestClient(create_app(service)) as client:
        class Adapter:
            def __init__(self, response):
                self.response = response
                self.ok = response.is_success
                self.content = response.content
            def json(self):
                return self.response.json()
        def transport(method, url, **kwargs):
            kwargs.pop('timeout', None)
            return Adapter(client.request(method, url.replace('http://127.0.0.1:8000', ''), **kwargs))
        monkeypatch.setattr(requests, 'request', transport)
        app = AppTest.from_file(str(Path('app/app.py').resolve()))
        app.session_state['run_id'] = state.run_id
        app.run(timeout=10)
        assert not app.exception
        assert any('Migration plan' in header.value for header in app.subheader)
        button = next(button for button in app.button if button.label == 'Approve plan and execute')
        button.click().run(timeout=10)
        assert not app.exception
        assert service.store.load(state.run_id)[0].status == 'ready'
        assert any('validation passed' in item.value for item in app.success)
    store.engine.dispose()



def test_hosted_demo_password_blocks_api_calls(monkeypatch):
    monkeypatch.setenv('APP_PASSWORD', 'synthetic-demo-password')
    def blocked(*args, **kwargs):
        raise AssertionError('Unauthenticated visitor reached the backend')
    monkeypatch.setattr(requests, 'request', blocked)
    app = AppTest.from_file(str(Path('app/app.py').resolve()))
    app.run(timeout=10)
    assert not app.exception
    assert not app.get('file_uploader')
    app.text_input[0].set_value('wrong')
    app.button[0].click().run(timeout=10)
    assert not app.exception
    assert app.error[0].value == 'Incorrect demo password.'
    assert 'demo_access' not in app.session_state
