"""Validated contracts shared by tools, graph, API and persistence."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldRule(Contract):
    name: str = Field(min_length=1, max_length=128)
    kind: Literal['text', 'email', 'phone', 'date', 'integer', 'number', 'boolean', 'category'] = 'text'
    required: bool = False
    unique: bool = False
    aliases: list[str] = Field(default_factory=list)
    allowed: list[str] = Field(default_factory=list)
    default: str | None = None
    category_map: dict[str, str] = Field(default_factory=dict)
    date_order: Literal['dayfirst', 'monthfirst'] | None = None

    @model_validator(mode='after')
    def category_contract(self):
        if self.kind == 'category' and not self.allowed:
            raise ValueError('Categorical fields require allowed values')
        if any(value not in self.allowed for value in self.category_map.values()):
            raise ValueError('Category mappings must use allowed target values')
        return self


class TargetSchema(Contract):
    name: str = 'Generic'
    fields: list[FieldRule] = Field(min_length=1, max_length=100)
    entity_field: str | None = None

    @model_validator(mode='after')
    def valid_names(self):
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError('Target field names must be unique')
        if self.entity_field and self.entity_field not in names:
            raise ValueError('Entity field must be a target field')
        return self


class Mapping(Contract):
    source: str | None
    target: str
    confidence: float = Field(ge=0, le=1)
    reason: str


ToolName = Literal['normalize_email', 'normalize_phone', 'normalize_date', 'normalize_text',
                   'convert_data_type', 'standardize_categories', 'handle_missing_values',
                   'detect_duplicates', 'resolve_entities']


class ToolCall(Contract):
    tool: ToolName
    column: str | None = None
    reason: str


class MigrationPlan(Contract):
    explanation: str
    mappings: list[Mapping]
    tools: list[ToolCall]
    planner: Literal['rules', 'llm'] = 'rules'


class ValidationIssue(Contract):
    code: str
    column: str
    rows: list[int] = Field(default_factory=list)
    message: str


class ValidationResult(Contract):
    passed: bool
    issues: list[ValidationIssue]
    readiness: float = Field(ge=0, le=100)


class ReviewItem(Contract):
    id: str
    kind: Literal['mapping', 'entity', 'validation']
    reason: str
    confidence: float = Field(ge=0, le=1)
    recommendation: str
    column: str | None = None
    rows: list[int] = Field(default_factory=list)
    actions: list[str]
    decision: str | None = None


class ReviewDecision(Contract):
    item_id: str
    action: Literal['map', 'keep', 'merge', 'correct']
    source: str | None = None
    # Row labels are strings in JSON and validated against the review item.
    values: dict[str, str | None] = Field(default_factory=dict)


class TraceEvent(Contract):
    sequence: int
    node: str
    action: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def crm_target() -> TargetSchema:
    return TargetSchema(name='CRM contacts (CSV demo)', entity_field='company', fields=[
        FieldRule(name='name', required=True, aliases=['customer_name', 'full_name']),
        FieldRule(name='email', kind='email', required=True, unique=True, aliases=['email_address']),
        FieldRule(name='phone', kind='phone', aliases=['mobile', 'phone_number']),
        FieldRule(name='company', aliases=['organization']),
        FieldRule(name='created_date', kind='date', aliases=['joined', 'signup_date']),
    ])


class EntityReasoning(Contract):
    confidence: float = Field(ge=0, le=1)
    reason: str
    recommendation: Literal['review', 'keep_separate']
