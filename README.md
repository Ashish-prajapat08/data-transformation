# Agentic AI Data Migration & Transformation Platform

This project evolves the original Pandas/FastAPI/Streamlit cleaning app into a single LangGraph migration orchestrator. The canonical specification is [AI_DATA_MIGRATION_AGENT_SOURCE_OF_TRUTH.md](AI_DATA_MIGRATION_AGENT_SOURCE_OF_TRUTH.md).

Upload CSV/XLSX → profile → review mappings and migration plan → approve tools → transform → validate → bounded corrective replanning → human review → target-ready CSV.

## Run locally

Use Python 3.11–3.13. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, activate the environment and run:

```bash
streamlit run app/app.py
```

The existing `uvicorn scripts.backend:app` entry point still works. `scripts.ai_agent.AIAgent` now consumes a typed target schema and returns migration state, rather than free-form model-generated CSV. File ingestion and deterministic cleaning compatibility facades remain under `scripts/`.

## Enable semantic AI planning

For NVIDIA's hosted endpoint, add/update these values in your existing local `.env`:

```dotenv
PLANNER_MODE=llm
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=your-local-nvidia-key
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

Keep the key out of source files. The NVIDIA transport uses the existing OpenAI-compatible SDK against `https://integrate.api.nvidia.com/v1`; it sends requests to NVIDIA, not OpenAI. It requests JSON with thinking disabled, embeds the Pydantic schema in the system instructions, and validates the response locally before any tool execution. Both migration planning and entity reasoning use this adapter. Invalid, empty or truncated outputs fail closed; JSON mode alone is not a schema guarantee. See [NVIDIA structured-generation documentation](https://docs.nvidia.com/nim/large-language-models/1.14.0/structured-generation.html).

After saving `.env`, test one small synthetic live planning request:

```bash
python -m scripts.check_llm
```

Restart the backend after changing provider settings. Upload `data/demo_contacts.csv` with the CRM demo target to try normalization and duplicate handling. No live NVIDIA request was made during implementation; provider access/JSON-mode compatibility must be verified with your own key using the command above.


`.env.example` starts in `PLANNER_MODE=rules`, an explicitly labelled offline baseline. To use the real LLM orchestrator, set locally:

```dotenv
PLANNER_MODE=llm
LLM_PROVIDER=openai
OPENAI_API_KEY=your-local-key
OPENAI_MODEL=gpt-4.1-mini
```

The model returns a Pydantic `MigrationPlan`, chooses allowlisted typed tools, explains schema mappings and reads structured validation feedback when replanning. For entity candidates, a separate structured call by the same orchestrator assesses organization-name semantics. It never writes dataframe text, Python or SQL. Initial plans, destructive deduplication and entity merges require human decisions; low confidence cannot bypass review.

LLM calls to the selected provider transmit schema names, profile statistics, target constraints, supplied instructions and validation row IDs. Entity reasoning additionally transmits only the two organization names in each candidate, capped at 50 semantic assessments per run. Other raw records and entire dataframes stay local. Do not place credentials in instructions or column names. Provider failures are surfaced as a failed run with a sanitized error; there is no silent switch from AI to rules.

## Target schemas

The UI provides one CRM contacts CSV demo (no direct CRM integration) and a generic JSON schema editor. See [the evaluation target schema](evaluation/datasets/target_schema.json) for a full example.

```json
{
  "name": "Customers",
  "fields": [
    {"name": "name", "required": true, "aliases": ["customer_name"]},
    {"name": "email", "kind": "email", "required": true, "unique": true},
    {"name": "phone", "kind": "phone", "aliases": ["mobile"]},
    {"name": "joined", "kind": "date", "date_order": "dayfirst"},
    {"name": "status", "kind": "category", "allowed": ["active", "inactive"],
     "category_map": {"enabled": "active"}}
  ]
}
```

Kinds: `text`, `email`, `phone`, `date`, `integer`, `number`, `boolean`, `category`. Fields also support `default`, `unique`, `required`, and `aliases`. `entity_field` optionally names the organization/name field to compare.

Dates such as `02/03/2024` remain unresolved unless `date_order` is declared. Invalid emails, phones, types and categories remain visible for validation/review. Missing values use only schema-declared defaults included in the approved plan. There is no automatic mean/mode imputation of business facts.

Exact duplicate removal compares complete source rows before mapping. Different records that become identical after mapping are retained for uniqueness validation or entity review. Entity merges are explicit, destructive **keep-first-record** decisions: they delete the second complete row, without inventing a field-wise merge. The UI shows the affected records and alternatives before submission.

Readiness is the percentage of valid target cells; it is a data quality signal. A score alone never authorizes export. Export requires validation to pass and every review to be resolved. Spreadsheet formula cells are escaped in the exported CSV.

## API

Interactive API documentation: `http://127.0.0.1:8000/docs`.

| Endpoint | Behavior |
|---|---|
| `GET /targets` | CRM demo target schema |
| `POST /migrations` | Multipart `file`, JSON-string `target_schema`, optional `instructions`; profile and plan |
| `GET /migrations` | Latest 100 run summaries |
| `GET /migrations/{id}` | Explicit migration state, excluding records |
| `GET /migrations/{id}/preview` | Paginated records with stable row IDs |
| `POST /migrations/{id}/approval` | `{"approved": true/false}`; approving starts background execution |
| `POST /migrations/{id}/reviews` | Checked mapping/entity/value-correction decisions |
| `GET /migrations/{id}/reviews/{item_id}/preview` | Records affected by review, capped at 200 |
| `GET /migrations/{id}/audit` | Metadata-only ordered execution trace |
| `POST /migrations/{id}/resume` | Resume an approved run that has not started execution |
| `GET /migrations/{id}/export` | Validated CSV download, recorded in audit |
| `DELETE /migrations/{id}` | Delete run and retained working records |
| `POST /evaluations` | Execute and persist measured evaluation with configured planner |
| `GET /evaluations/{id}` | Retrieve persisted evaluation report |

Approval returns `approved` while a local background task runs. Poll migration state to see tool checkpoints; Streamlit does this every two seconds. No external task queue or distributed worker is involved.

Mapping review example:

```json
{"decisions": [{"item_id": "mapping:email", "action": "map", "source": "mail"}]}
```

Validation correction example (the row must belong to the pending issue):

```json
{"decisions": [{"item_id": "validation:email:invalid_email", "action": "correct",
                "values": {"0": "verified@example.com"}}]}
```

The API validates the corrected dataset again. An invalid correction creates another unresolved review instead of permitting export.

## Persistence and security

`DATABASE_URL` selects SQLAlchemy persistence. Default: `.runtime/migrations.db` (SQLite). PostgreSQL example, using environment-owned credentials:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB
```

Runs retain typed state, plan versions, tool traces, validations, retries, review decisions and working records required to resume review. Evaluation reports have a separate table. Raw records are not copied into audit events. Local runtime directories/database files use restrictive permissions. Storage is not encrypted; delete runs when their retained data is no longer needed. PostgreSQL backups and filesystem backups have their own retention settings. Updates use optimistic version checks to reject concurrent writes.

V0 limits: CSV/XLSX, first Excel sheet, 10 MiB compressed upload, 100 MiB expanded workbook, 100,000 rows, 100 columns, at most five configured retries. Entity comparison uses blocked candidates and bounded work; high-density entity groups may require splitting the input. CSV must be UTF-8. Duplicate/empty source headers are rejected.

Public arbitrary SQL and user-supplied external-URL ingestion endpoints were retired. No multi-agent system, billing, external CRM imports or production authentication is included. Bind locally; multiuser hosting requires a later authentication/authorization design. In-process execution is not a durable job queue. If a server exits mid-tool execution, retained checkpoints show progress but the safe recovery is to create a new run from the original upload. Review states and not-yet-started approved runs can resume after restart.

Hard-coded database credentials were removed from the old scripts. Rotate any previously exposed credentials. `.env`, bytecode and runtime data are ignored. This supplied folder has no Git metadata; prior repository history/secret removal cannot be verified here.

## Tests and evaluation

```bash
python3 -m pytest -q
python3 -m evaluation.runner --output evaluation/results/baseline.json
# Uses .env / configured AI planner; provider charges may apply:
python3 -m evaluation.runner --planner configured --output evaluation/results/agent.json
```

Fixtures inject missing values, exact/near duplicates, whitespace/casing, malformed emails, phone/date variations, renamed columns, numeric mismatches, entity-name variations and invalid categories. Expected values are declared independently of the transformation tools.

Metrics include task success, schema mapping accuracy, cell transformation accuracy, duplicate/entity precision and recall, validation-outcome accuracy, safety outcome, retry rate, human-review rate and tool-call counts. Undefined precision/recall denominators are `null`. The simulated human policy approves unambiguous plans, keeps entity candidates separate, and never repairs invalid facts from expected output. A safely blocked invalid dataset counts as task failure and safety success.

The four V0 scenarios are small regression fixtures, not a production benchmark. Transformation accuracy excludes the irreparable fixture, whose correct output facts are unknown. Duplicate/entity matching each currently have one positive pair; do not generalize those scores. Live LLM behavior (OpenAI or NVIDIA) and PostgreSQL connectivity require configured credentials/services. Unit/integration tests use the offline baseline and a structured model stub; they do not claim measured live-model quality.

See [architecture and verification notes](docs/IMPLEMENTATION.md) for component boundaries and limitations.

## Deploy on Render

See [GitHub and Render setup](docs/DEPLOYMENT.md). The repository includes Dockerfile, render.yaml and CI tests. Supply NVIDIA_API_KEY and APP_PASSWORD through Render environment settings. Free-plan SQLite storage is ephemeral; no paid storage is provisioned.
