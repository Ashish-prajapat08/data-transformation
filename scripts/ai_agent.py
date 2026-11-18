"""Legacy name now exposes the typed migration orchestrator.
process_data no longer returns free-form model-generated dataframe text.
"""
from agent.graph import MigrationAgent
from agent.state import MigrationState


class AIAgent(MigrationAgent):
    def process_data(self, df, target_schema, instructions=''):
        return self.invoke(MigrationState(frame=df.copy(), target_schema=target_schema, instructions=instructions))
