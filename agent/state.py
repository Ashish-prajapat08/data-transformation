from typing import Any, Literal
from uuid import uuid4
from pydantic import ConfigDict, Field
import pandas as pd
from models.migration import Contract, TargetSchema, MigrationPlan, ValidationResult, ReviewItem, TraceEvent


class MigrationState(Contract):
    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    source_schema: dict[str, str] = Field(default_factory=dict)
    target_schema: TargetSchema
    instructions: str = ''
    dataset_profile: dict[str, Any] = Field(default_factory=dict)
    migration_plan: MigrationPlan | None = None
    plan_history: list[MigrationPlan] = Field(default_factory=list)
    validation_results: ValidationResult | None = None
    review_items: list[ReviewItem] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    evaluation_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    status: Literal['new', 'awaiting_plan', 'approved', 'executing', 'awaiting_review',
                    'reviewing', 'ready', 'rejected', 'failed'] = 'new'
    retry_count: int = 0
    max_retries: int = Field(default=2, ge=0, le=5)
    frame: pd.DataFrame = Field(exclude=True)

    def record(self, node: str, action: str, **metadata):
        self.trace.append(TraceEvent(sequence=len(self.trace) + 1, node=node, action=action, metadata=metadata))
