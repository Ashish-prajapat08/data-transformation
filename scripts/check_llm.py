"""Run a small synthetic planning request without exposing the API key or response payload."""
import os
from dotenv import load_dotenv
import pandas as pd
from agent.graph import MigrationAgent
from agent.planning import configured_planner
from agent.state import MigrationState
from models.migration import TargetSchema, FieldRule


def main():
    load_dotenv()
    if os.getenv('PLANNER_MODE', 'rules') != 'llm':
        raise SystemExit('Set PLANNER_MODE=llm in .env before testing the live provider.')
    try:
        agent = MigrationAgent(configured_planner())
        state = agent.invoke(MigrationState(frame=pd.DataFrame({'email': ['demo@example.com']}),
            target_schema=TargetSchema(fields=[FieldRule(name='email', kind='email', required=True)])))
        if state.status != 'awaiting_plan' or state.migration_plan is None:
            raise ValueError('Planning failed')
    except Exception:
        raise SystemExit('Live planning check failed. Check provider/key, account access, endpoint availability and JSON support.') from None
    print('Live structured planning succeeded. Provider: ' + os.getenv('LLM_PROVIDER', 'openai'))
    print('Next: start FastAPI and Streamlit, upload a CSV and review the plan.')


if __name__ == '__main__':
    main()
