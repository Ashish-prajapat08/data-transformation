# AI Data Migration & Transformation Agent
## Product + Engineering Source of Truth
### V0 Build Specification

> **Purpose:** This document is the canonical context for Codex while evolving the existing `data-cleaning-preprocessing-ai-agent` repository.
>
> **Important:** Do NOT treat the current implementation as the final architecture. The existing codebase is the starting point. Refactor it incrementally into the product defined below.

---

# 1. Product Identity

## Product Name

**AI Data Migration & Transformation Agent**

Working short name:

**Data Migration Agent**

## One-line Product

> An Agentic AI system that takes messy business data and autonomously profiles, maps, transforms, validates, and prepares it for migration into a target system.

## Core Problem

Businesses frequently move data between:

- Excel/CSV files
- legacy systems
- databases
- APIs
- CRMs
- business tools

The source and target schemas rarely match.

Typical problems:

- different column names
- inconsistent data types
- duplicate records
- missing values
- inconsistent dates
- inconsistent phone numbers
- malformed emails
- different naming conventions
- duplicate/near-duplicate entities
- target-schema incompatibility

The product should automate this preparation work while keeping the user in control of risky or ambiguous decisions.

---

# 2. The Product Is NOT

Do NOT turn this into:

- a generic "Chat with CSV" application
- a generic ChatGPT wrapper
- a simple LLM prompt that returns cleaned CSV text
- a generic PDF/RAG application
- a fully autonomous system that silently changes business data
- an unnecessarily complex multi-agent demo
- a huge ETL/data warehouse platform in V0

The core product is:

> **Agentic data migration preparation and transformation.**

---

# 3. Target User

V0 should primarily serve:

- small businesses
- startup operations teams
- data/operations analysts
- CRM implementation teams
- consultants handling client data migration
- people moving data from spreadsheets/legacy systems into a new system

Initial use case:

> **Prepare messy CSV/Excel data for migration into a target schema.**

V0 should not attempt to support every CRM or business system.

---

# 4. Primary User Journey

Example:

A user has:

`customers.xlsx`

They want:

> "Prepare this data for HubSpot."

The system should:

```text
Upload Source Data
       ↓
Profile Dataset
       ↓
Understand Schema
       ↓
Understand Target Schema
       ↓
Create Migration Plan
       ↓
User Reviews / Approves Plan
       ↓
Execute Transformations
       ↓
Resolve Duplicates / Entities
       ↓
Validate Output
       ↓
If failure → Re-plan / Retry
       ↓
Human Review for Ambiguous Cases
       ↓
Migration Readiness Score
       ↓
Export Target-Ready Dataset
```

---

# 5. Core Product Architecture

```text
                    USER
                      |
                      v
              Streamlit UI
                      |
                      v
                 FastAPI
                      |
                      v
              Migration Service
                      |
                      v
             LangGraph Agent
                      |
       +--------------+--------------+
       |              |              |
       v              v              v
 Data Profiling   Schema Mapping   Entity Matching
     Tool             Tool             Tool
       |              |              |
       +--------------+--------------+
                      |
                      v
              Transformation Tools
                      |
                      v
                 Validator
                      |
             +--------+--------+
             |                 |
            PASS              FAIL
             |                 |
             v                 v
          Export            Re-plan
             |
             v
       Human Approval
             |
             v
          Final Data
             |
             v
       Agent Evaluation
             |
             v
      Evaluation Results
```

---

# 6. Agentic AI Definition for This Product

This project must demonstrate real Agentic AI behavior.

A simple:

```text
CSV → LLM → cleaned CSV
```

is NOT sufficient.

The agent must be able to:

1. inspect the dataset
2. understand the migration objective
3. create a plan
4. decide which tools are needed
5. execute tools
6. inspect intermediate results
7. validate the output
8. react to validation failures
9. retry/re-plan when appropriate
10. request human review when confidence is low
11. produce a final migration-ready artifact

The LLM provides intelligence/reasoning.

Deterministic Python tools perform actual data operations.

Do NOT ask the LLM to directly rewrite entire datasets as free-form text.

---

# 7. Recommended Agent Design

## Single Orchestrator Agent for V0

Do NOT create multiple agents just for the sake of calling it multi-agent.

V0 should use:

```text
LangGraph
   |
   v
Migration Orchestrator Agent
   |
   +-- profile_data
   +-- inspect_schema
   +-- map_schema
   +-- normalize_data
   +-- detect_duplicates
   +-- resolve_entities
   +-- validate_data
   +-- request_human_review
   +-- export_data
```

A multi-agent architecture may be introduced later only if actual complexity justifies it.

---

# 8. LangGraph State

Use a typed state model.

Conceptually:

```python
MigrationState:
    run_id
    source_metadata
    target_system
    source_schema
    target_schema
    dataset_profile
    migration_plan
    tool_results
    transformations
    validation_results
    review_items
    evaluation_results
    status
    errors
```

The exact implementation can differ, but state must remain explicit and inspectable.

---

# 9. Agent Workflow

## Node 1 — Intake

Inputs:

- uploaded file
- target system/schema
- optional natural-language instructions

Example:

> "Prepare this customer file for HubSpot."

---

## Node 2 — Data Profiling

The system should inspect:

- row count
- column count
- data types
- null percentages
- unique values
- duplicate counts
- likely identifiers
- date patterns
- email patterns
- phone patterns
- categorical fields
- suspicious values

Output:

```text
42,381 rows
17 columns

Issues detected:
- 1,923 inconsistent dates
- 621 invalid emails
- 2,481 duplicate records
- 812 possible entity matches
```

---

# 10. Schema Mapping

Source:

```text
customer_name
mobile
dob
city
```

Target:

```text
name
phone_number
date_of_birth
location
```

Agent should produce structured mappings:

```json
{
  "customer_name": "name",
  "mobile": "phone_number",
  "dob": "date_of_birth",
  "city": "location"
}
```

Mappings must include confidence where appropriate.

Example:

```json
{
  "source": "mobile",
  "target": "phone_number",
  "confidence": 0.99
}
```

Ambiguous mappings should be sent to human review instead of silently guessing.

---

# 11. Data Transformation Tools

Implement deterministic Python functions/tools for operations such as:

```text
normalize_email()
normalize_phone()
normalize_date()
normalize_text()
handle_missing_values()
remove_exact_duplicates()
standardize_categories()
convert_data_type()
```

The agent decides when to use them.

The actual transformation should be deterministic whenever possible.

---

# 12. Entity Resolution

This is a key differentiator.

Example:

```text
ABC Pvt Ltd
ABC Private Limited
ABC PVT. LTD.
A.B.C Private Ltd
```

The system should identify possible same-entity records.

Each match should have:

- confidence
- reason/evidence
- recommendation
- review status

Example:

```text
Possible duplicate

ABC Pvt Ltd
ABC Private Limited

Confidence: 0.94

[Merge]
[Keep Separate]
[Review]
```

Do not automatically merge low-confidence entities.

---

# 13. Validation

After transformations, the system must validate the resulting dataset against the target schema/rules.

Examples:

- required columns present
- required values not null
- correct data types
- valid email format
- valid phone format
- valid date format
- unique identifiers
- no unexpected columns
- allowed categorical values
- target-specific constraints

Validation must return structured results.

Example:

```json
{
  "status": "failed",
  "issues": [
    {
      "type": "invalid_phone",
      "count": 1241
    }
  ]
}
```

---

# 14. Replanning / Retry

If validation fails:

```text
Agent
  ↓
Validator
  ↓
FAIL
  ↓
Analyze failure
  ↓
Choose corrective tool
  ↓
Run correction
  ↓
Validate again
```

Put a configurable retry limit in place.

Do not create infinite agent loops.

Example:

```text
MAX_RETRIES = 2 or 3
```

---

# 15. Human-in-the-Loop

Human review is required for:

- low-confidence schema mappings
- ambiguous entity matches
- destructive transformations
- uncertain data interpretation
- target-required fields with no safe mapping

The system should show the user:

```text
Issue
AI recommendation
Confidence
Reason
Available actions
```

The user must be able to approve/reject where required.

---

# 16. Evaluation System

Evaluation is a first-class component, not an afterthought.

Directory suggestion:

```text
evaluation/
    datasets/
    generators/
    evaluators/
    metrics/
    runner.py
```

## Evaluation goals

Measure:

### Agent behavior

- task completion
- plan quality
- tool selection
- unnecessary tool calls
- retry behavior
- failure recovery

### Data quality

- schema mapping accuracy
- transformation accuracy
- duplicate detection
- entity matching
- validation accuracy

### End-to-end

- migration success rate
- target schema compliance
- human-review rate
- error rate

---

# 17. Evaluation Dataset / Problem Injection

Create clean datasets and intentionally inject problems.

Example:

```text
Clean Dataset
     ↓
Problem Injector
     ↓
Messy Dataset
     ↓
Agent
     ↓
Actual Output
     ↓
Expected Output
     ↓
Metrics
```

Problem types:

- missing values
- duplicate rows
- near duplicates
- inconsistent casing
- whitespace
- malformed emails
- inconsistent phone formats
- inconsistent dates
- type mismatches
- renamed columns
- entity-name variations
- invalid categorical values

This allows repeatable evaluation.

---

# 18. Metrics

At minimum:

```text
Task Success Rate
Schema Mapping Accuracy
Transformation Accuracy
Duplicate Detection Precision/Recall
Entity Matching Precision/Recall
Validation Accuracy
Human Review Rate
Retry Rate
```

Optional:

```text
Tool Selection Accuracy
Tool Call Count
Latency
Token Usage
Estimated Cost per Run
```

Do not invent metrics or percentages.

Only report measured values.

---

# 19. LLM-as-a-Judge

LLM-as-a-Judge can be used for qualitative evaluation where deterministic metrics are insufficient.

Examples:

- quality of migration plan
- quality of explanations
- reasoning consistency
- appropriateness of tool selection

However:

> LLM-as-a-Judge must NOT be the only evaluation method for deterministic data transformations.

Prefer exact comparison / deterministic metrics wherever possible.

---

# 20. Audit Trail

Every migration run should record:

```text
run_id
user request
input dataset metadata
agent plan
tool calls
tool inputs/outputs metadata
transformations
validation results
retries
human approvals
final result
evaluation results
```

Do not store sensitive raw data unnecessarily.

---

# 21. Observability

The UI should expose an understandable execution trace.

Example:

```text
Migration Run #1023

✓ Dataset profiled
✓ Schema mapped
✓ Phone numbers normalized
✓ Duplicate detection completed
⚠ 36 low-confidence matches found
✓ Validation completed
✓ Export generated
```

For development/debugging, retain structured logs.

---

# 22. Technology Stack

## Python

Primary language.

Used for:

- backend
- data processing
- tools
- agent logic
- evaluation

---

## FastAPI

Backend/API layer.

Responsibilities:

- file upload
- migration job creation
- migration status
- approvals
- execution
- evaluation results
- export/download endpoints

---

## LangGraph

Agent orchestration/state machine.

Responsibilities:

- explicit agent state
- planning
- tool execution
- conditional routing
- validation loop
- retry/replanning
- human-in-the-loop state

---

## LangChain

Use where useful for:

- model integration
- tool abstractions
- structured outputs
- prompt management

Do not use LangChain abstractions unnecessarily if plain Python is clearer.

---

## LLM

Use an LLM for:

- understanding natural-language instructions
- schema semantic interpretation
- migration planning
- ambiguous mappings
- entity reasoning
- explanations

Do NOT use the LLM for simple deterministic operations such as:

- dropping exact duplicate rows
- parsing dates when deterministic parsing works
- validating regex-based emails
- numeric conversion

---

## Pandas

Primary data manipulation engine.

Used for:

- CSV/Excel processing
- transformations
- filtering
- joining
- validation
- deterministic cleaning

---

## Pydantic

Used for:

- structured agent outputs
- API request/response models
- state validation
- tool input/output schemas

---

## PostgreSQL

Used for application persistence:

```text
users
datasets
migration_runs
agent_runs
tool_calls
validation_results
evaluation_results
audit_logs
```

V0 may also retain PostgreSQL as a data source, but application persistence is the more important role.

---

## Streamlit

V0 frontend.

Use it for:

- upload
- target selection
- migration configuration
- plan review
- execution progress
- human review
- results
- evaluation dashboard
- download

Do not over-engineer frontend infrastructure in V0.

---

# 23. V0 Scope

V0 must support:

### Input

- CSV
- Excel

### Target

Start with:

- Generic target schema
- One concrete CRM-style target schema for demonstration

Do not build five CRM integrations immediately.

### Core capabilities

- dataset profiling
- schema mapping
- deterministic transformations
- duplicate detection
- basic entity resolution
- validation
- agent planning
- tool calling
- retry/replanning
- human review
- export
- evaluation
- audit trail

---

# 24. V0 Explicitly Out of Scope

Do NOT build yet:

- Salesforce direct integration
- HubSpot direct API integration
- Zoho integration
- Google Sheets integration
- data warehouse integrations
- billing
- multi-tenant production auth
- complex RBAC
- massive distributed processing
- Kubernetes
- complicated microservices
- multi-agent architecture without need
- autonomous destructive imports

These can be future roadmap items.

---

# 25. Suggested Repository Structure

Refactor toward:

```text
project/
│
├── app/
│   └── streamlit_app.py
│
├── backend/
│   ├── main.py
│   ├── routes/
│   │   ├── migrations.py
│   │   ├── datasets.py
│   │   └── evaluations.py
│   └── services/
│
├── agent/
│   ├── graph.py
│   ├── state.py
│   ├── nodes/
│   │   ├── intake.py
│   │   ├── planning.py
│   │   ├── execution.py
│   │   ├── validation.py
│   │   └── human_review.py
│   └── prompts/
│
├── tools/
│   ├── profiling.py
│   ├── schema_mapping.py
│   ├── transformations.py
│   ├── duplicates.py
│   ├── entity_resolution.py
│   ├── validation.py
│   └── export.py
│
├── evaluation/
│   ├── datasets/
│   ├── generators/
│   ├── evaluators/
│   ├── metrics.py
│   └── runner.py
│
├── data/
│
├── models/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evaluation/
│
├── docs/
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

The exact folder structure can differ if there is a strong reason, but responsibilities must remain separated.

---

# 26. Current Codebase Migration Strategy

The existing project already contains:

- Streamlit UI
- FastAPI backend
- CSV/Excel ingestion
- PostgreSQL ingestion
- API ingestion
- rule-based cleaning
- LangGraph-based AI component

Do NOT delete everything and rewrite blindly.

Refactor incrementally.

## Existing → New

```text
Current data_ingestion.py
        ↓
Input / ingestion layer

Current data_cleaning.py
        ↓
Deterministic transformation tools

Current ai_agent.py
        ↓
Real LangGraph migration orchestrator

Current backend.py
        ↓
Migration API/service layer

Current app/app.py
        ↓
Migration dashboard

PostgreSQL
        ↓
Persistence + optional source

Current README
        ↓
Replace with product documentation
```

---

# 27. Important Current-Code Problems to Fix

The existing implementation has several issues that must not be carried into the new architecture.

Examples:

1. The current LangGraph graph is effectively a single LLM node.
2. The LLM currently receives batches of dataframe text and returns free-form text.
3. Data should not depend on parsing arbitrary LLM-generated CSV/text.
4. Agent state needs to become structured and explicit.
5. Tools need typed inputs/outputs.
6. Validation needs to be a first-class stage.
7. Retry/replanning needs explicit graph routing.
8. API/UI endpoint naming should be made consistent.
9. Error handling should be structured.
10. Secrets must not be hard-coded.
11. `.env` should not be committed.
12. `__pycache__` should not be committed.
13. Tests need to be added.
14. Evaluation needs repeatable datasets and metrics.

---

# 28. Security Requirements

Never:

- hard-code API keys
- hard-code database passwords
- commit `.env`
- expose credentials in logs
- execute arbitrary SQL supplied by untrusted users without controls
- execute arbitrary Python generated by an LLM without sandboxing

Use:

```text
.env
.env.example
environment variables
```

For any future code execution capability, use a controlled/sandboxed execution environment.

---

# 29. Testing Strategy

## Unit tests

Test deterministic tools:

```text
test_normalize_email
test_normalize_phone
test_date_normalization
test_duplicate_detection
test_schema_validation
```

## Integration tests

Test:

```text
upload
→ profile
→ plan
→ tools
→ validation
→ export
```

## Agent evaluation

Run the evaluation dataset repeatedly and track metrics.

---

# 30. Product UX Principle

The user should always understand:

1. What the agent found.
2. What the agent plans to do.
3. What the agent actually changed.
4. What failed.
5. What needs human review.
6. Whether the final dataset is safe to import.

Do not hide all agent activity behind a single spinner.

---

# 31. Product Differentiator

The project is NOT trying to win by saying:

> "We use an LLM to clean CSVs."

The product differentiator is:

> **Agentic migration workflow + schema understanding + entity resolution + validation + human approval + measurable evaluation.**

---

# 32. Future Roadmap

## V0

CSV/Excel → target schema → migration-ready export.

## V1

Add:

- Google Sheets
- more target schemas
- better entity resolution
- richer evaluation
- migration history

## V2

Direct integrations:

- HubSpot
- Salesforce
- Zoho
- Pipedrive

## V3

Business SaaS:

- authentication
- teams
- workspaces
- usage limits
- billing
- audit/compliance controls
- production monitoring

---

# 33. Resume Positioning

Final project title:

**Agentic AI Data Migration & Transformation Platform**

Resume positioning:

> Built a LangGraph-based Agentic AI system that autonomously profiles, maps, transforms, validates, and prepares heterogeneous business datasets for migration into target schemas.

Possible second bullet:

> Implemented tool-calling workflows for schema mapping, deterministic data transformation, duplicate detection, entity resolution, validation, and retry/replanning.

Possible evaluation bullet:

> Built an automated evaluation framework with synthetic problem injection to measure schema mapping, transformation, entity matching, validation, and end-to-end task success.

Only add numerical performance claims after actually measuring them.

---

# 34. Codex Operating Rules

When working on this repository:

### Rule 1
Treat this document as the product source of truth.

### Rule 2
Inspect the current code before modifying it.

### Rule 3
Preserve working functionality unless it conflicts with the new architecture.

### Rule 4
Prefer incremental refactoring over blind rewrites.

### Rule 5
Do not introduce unnecessary technologies.

### Rule 6
Do not create multi-agent architecture unless a concrete requirement justifies it.

### Rule 7
Keep deterministic data operations in Python tools.

### Rule 8
Use the LLM for semantic reasoning and planning, not for blindly rewriting complete datasets.

### Rule 9
All agent outputs should be structured and validated with Pydantic where appropriate.

### Rule 10
Every important agent decision should be observable.

### Rule 11
Evaluation is part of the product architecture.

### Rule 12
Never invent performance metrics.

### Rule 13
Do not hard-code credentials or secrets.

### Rule 14
Write tests alongside important new components.

### Rule 15
Before declaring a feature complete, verify it end-to-end.

### Rule 16
Keep V0 small enough to finish.

---

# 35. Definition of Done for V0

V0 is considered complete only when a user can:

```text
1. Upload CSV/Excel
2. Select a target schema
3. See an automatically generated data profile
4. Ask the migration agent to prepare the dataset
5. See the agent's migration plan
6. Approve/reject the plan where required
7. Watch tool execution
8. See transformations
9. Review ambiguous records
10. Run validation
11. See validation failures
12. Allow the agent to retry/replan
13. Receive a final migration readiness score
14. Download target-ready CSV
15. Inspect an audit trail
16. Run the same scenario through the evaluation suite
17. See measurable evaluation results
```

---

# 36. Final Product Mental Model

Always remember:

```text
                MESSY BUSINESS DATA
                        |
                        v
                ┌──────────────┐
                │ AI MIGRATION  │
                │    AGENT      │
                └──────┬───────┘
                       |
        Understand → Plan → Act → Validate
                       |
              ┌────────┴────────┐
              |                 |
          deterministic       LLM
             tools          reasoning
              |                 |
              └────────┬────────┘
                       |
                 Human Review
                       |
                       v
              MIGRATION-READY DATA
                       |
                       v
                  EVALUATION
                       |
                       v
              MEASURABLE QUALITY
```

The goal is not to make the most complicated AI system.

The goal is to build a **credible, useful, measurable Agentic AI product** that solves a real data migration problem and demonstrates strong Generative AI + Agentic AI engineering.

---

# 37. Canonical Build Statement

> **We are evolving the existing AI Data Cleaning project into an Agentic AI Data Migration & Transformation Platform. The system will use LangGraph to orchestrate an agent that profiles messy business data, plans a migration, selects deterministic tools for transformation, performs schema mapping and entity resolution, validates the result, retries/replans when validation fails, requests human approval for ambiguous cases, produces a migration-ready dataset, and evaluates its own performance using repeatable evaluation datasets and metrics.**
