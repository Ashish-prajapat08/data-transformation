"""SQLAlchemy persistence: SQLite locally, PostgreSQL via DATABASE_URL.
Raw working records are retained only to resume jobs; traces contain metadata.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, JSON, select, update, delete
from sqlalchemy.pool import StaticPool
from agent.state import MigrationState


class ConflictError(ValueError):
    pass


class Store:
    def __init__(self, url=None):
        url = url or os.getenv('DATABASE_URL', 'sqlite:///.runtime/migrations.db')
        if url.startswith('sqlite:///') and url != 'sqlite:///:memory:':
            folder = Path(url.removeprefix('sqlite:///')).parent
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        options = {'connect_args': {'check_same_thread': False}} if url.startswith('sqlite:') else {}
        if url == 'sqlite:///:memory:':
            options['poolclass'] = StaticPool
        self.engine = create_engine(url, hide_parameters=True, **options)
        metadata = MetaData()
        self.runs = Table('migration_runs', metadata,
            Column('run_id', String(36), primary_key=True), Column('version', Integer, nullable=False),
            Column('updated_at', String(40), nullable=False), Column('state', JSON, nullable=False),
            Column('working_data', JSON, nullable=False))
        self.evaluations = Table('evaluation_results', metadata,
            Column('evaluation_id', String(36), primary_key=True), Column('result', JSON, nullable=False))
        metadata.create_all(self.engine)
        if url.startswith('sqlite:///') and url != 'sqlite:///:memory:':
            Path(url.removeprefix('sqlite:///')).chmod(0o600)

    def save(self, state: MigrationState, version: int | None = None) -> int:
        # Pandas' JSON serializer handles NaN and numpy scalars safely.
        payload = json.loads(state.frame.to_json(orient='split'))
        values = dict(state=state.model_dump(mode='json'), working_data=payload,
                      version=1 if version is None else version + 1,
                      updated_at=datetime.now(timezone.utc).isoformat())
        with self.engine.begin() as connection:
            if version is None:
                connection.execute(self.runs.insert().values(run_id=state.run_id, **values))
            else:
                result = connection.execute(update(self.runs).where(
                    self.runs.c.run_id == state.run_id, self.runs.c.version == version).values(**values))
                if result.rowcount != 1:
                    raise ConflictError('Run changed concurrently; refresh and try again')
        return values['version']

    def load(self, run_id: str) -> tuple[MigrationState, int]:
        with self.engine.connect() as connection:
            row = connection.execute(select(self.runs).where(self.runs.c.run_id == run_id)).mappings().first()
        if not row:
            raise KeyError(run_id)
        payload = row['working_data']
        frame = pd.DataFrame(payload['data'], columns=payload['columns'], index=payload['index'])
        return MigrationState.model_validate(row['state'] | {'frame': frame}), row['version']

    def list_runs(self):
        with self.engine.connect() as connection:
            rows = connection.execute(select(self.runs.c.run_id, self.runs.c.updated_at, self.runs.c.state)
                                      .order_by(self.runs.c.updated_at.desc()).limit(100)).mappings().all()
        return [{'run_id': row['run_id'], 'updated_at': row['updated_at'], 'status': row['state']['status']}
                for row in rows]

    def delete_run(self, run_id):
        with self.engine.begin() as connection:
            result = connection.execute(delete(self.runs).where(self.runs.c.run_id == run_id))
            if result.rowcount != 1:
                raise KeyError(run_id)

    def save_evaluation(self, evaluation_id, result):
        with self.engine.begin() as connection:
            connection.execute(self.evaluations.insert().values(evaluation_id=evaluation_id, result=result))

    def load_evaluation(self, evaluation_id):
        with self.engine.connect() as connection:
            row = connection.execute(select(self.evaluations.c.result).where(
                self.evaluations.c.evaluation_id == evaluation_id)).first()
        if row is None:
            raise KeyError(evaluation_id)
        return row[0]
