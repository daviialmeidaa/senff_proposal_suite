# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run terminal flow
python main.py

# Run web server (default: 127.0.0.1:8765)
python webapp.py
python webapp.py --host 0.0.0.0 --port 9000

# Lint
ruff check src/

# Run tests
pytest
pytest tests/unit/test_something.py::test_name   # single test
```

## Architecture

**Two entry points, one shared backend:**
- `main.py` → `src/interfaces/terminal/runner.py` (interactive CLI)
- `webapp.py` → `src/interfaces/web/server.py` (HTTP server serving `frontend/`)

Both interfaces call the same domain and infra layers — no logic duplication.

**Layer structure:**
```
src/core/       → EnvironmentConfig (loads .env, normalizes URLs), ProposalHistory (in-memory per-environment)
src/infra/      → ApiSession (OAuth + 401 retry), database (psycopg2), GoogleSheetsService (FORMATTED_VALUE + numericise_ignore to preserve leading zeros)
src/domain/     → build_simulation_payload(), build_complete_client_payload(), build_proposal_payload()
src/services/   → FakeDataService (Faker pt_BR)
src/interfaces/ → terminal/runner.py, web/server.py
frontend/       → SPA (HTML + CSS + JS vanilla, no frameworks)
```

**Required files (not committed):**
- `.env` — credentials per environment (see README §6 for format)
- `credentials.json` — Google Service Account for Sheets access

## Key Behaviours

**Processor discovery is always dynamic.** The processor code (`dataprev`, `serpro`, `cip`, `zetra`, `econsig-zetra`) comes from `GET /admin/agreement/{id}` at runtime — never hardcoded by agreement name.

**All monetary values go to the API in centavos (integers).** `money_to_cents()` in `src/domain/simulation.py` handles conversion; the `formatCents()` helper in `app.js` reverses it for display.

**The API requires three mandatory headers on every request:**
```
account: {DEFAULT_ACCOUNT}
tenant-id: {TENANT_ID}
x-store-code: {DEFAULT_STORE_CODE}
```
These come from `EnvironmentConfig` and are set in `ApiSession._headers()`.

**401 responses trigger one automatic re-authentication and retry** inside `ApiSession.request()`. Do not add retry logic elsewhere.

**After authentication, `my-stores` is fetched automatically.** `fetch_my_stores()` calls `GET /admin/store/my-stores` and extracts the `id` from each row. Both `store_ids` (list) and `stores_query_string` (format: `stores[]=1&stores[]=2`) are stored on `ApiSession` for use in subsequent requests that require store context (e.g., dashboard queries).

**URL normalization in `src/core/config.py`:**
- Auth URL ending in `/auth` → appends `/v1/auth`
- API URL ending in `/api` → appends `/v1`

## Processor-Specific Rules

| Processor | Sheet tab | Balance rule | Extra fields captured |
|---|---|---|---|
| DATAPREV | DATAPREV | RCC or RMC > 0, Status = "Ok" | Nome |
| CIP | CIP | RCC or RMC > 0 | — |
| SERPRO | SERPRO | RCC or RMC > 0 | Orgao |
| ZETRA / econsig-zetra | ZETRA | Always RCC > 0 (ignores product) | Senha |

**DATAPREV:** Calls `GET /admin/dataprev/list-benefits` before simulation (params: `document`, `name`). The online margin **replaces** the sheet margin. On failure, falls back to sheet data.

**CIP:** Calls `GET /admin/cip/list-benefits` after withdraw type selection. The online margin **replaces** the sheet margin. On HOMOLOG, `cip_agency_id` is always `"1"`. `EncryptionException` / `XmlEncrypto` errors → fallback to sheet margin.

**SERPRO:** Calls `GET /admin/serpro/list-benefits` before simulation. Requires `agreement.serpro_agency_id` and `sponsor_benefit_number` in the simulation payload. Agency hierarchy (agency → sub → upag) is queried from the database.

**ZETRA:** Requires `benefit_number` (= matricula from sheet). The `user_password` (= Senha) is optional.

## Dashboard & Pipeline Flow

After each proposal is created, the server queries `GET /admin/proposal/dashboard?search={simulationCode}&limit=10&stores[]=...` to retrieve the proposal's pipeline data. From the response, `extract_proposal_flow()` extracts:

- `proposal_id` — `rows[0].id`
- `flow_id` — `rows[0].flow.id`
- `stages[]` — for each stage: `id`, `code`, `name`, `status`

This `ProposalFlow` is stored inside the `ProposalRecord` and returned via the history endpoint. If the dashboard call fails, the proposal is still recorded (with `flow: null`).

**Flow fetch uses retry logic:** Up to 5 attempts with 0.8s delay between each, since the dashboard may not return stages immediately after proposal creation.

## Pipeline Execution Engine

The server includes a full execution engine that processes pipeline stages according to user-defined rules. Each stage can be configured with one of three actions:

| Action | Behaviour |
|---|---|
| `wait` | Polls the dashboard until the stage resolves naturally (approved, failed, or manual). Timeout: 60s. |
| `manual` | Same as wait — monitors the stage but does not intervene. Timeout: 60s. |
| `finish` | Calls `PUT /admin/proposal/{id}/flow/{flowId}/stage/{stageId}/finish` with `comments: "approved"`, then polls until resolved. Timeout: 5s post-finish. |

**Execution runs in a background thread** (`Thread(daemon=True)`). The frontend polls `/api/proposal-history/execution-status` to track progress in real time.

**Stage status classification** determines stage resolution:
- **Success:** APPROVED, SUCCESS, DONE, COMPLETED, COMPLETE, FINISHED, OK
- **Failure:** FAIL, FAILED, ERROR, REJECTED, DENIED, CANCELED, CANCELLED, INVALID
- **Manual:** MANUAL, MANUAL_ANALYSIS, PENDING_MANUAL, or any status containing "MANUAL"
- **In progress:** IN_PROGRESS, PROCESSING, RUNNING, STARTED

**Execution state** is managed per `(environment, history_index)` in a thread-safe `_EXECUTION_STATE` dict. States: `idle`, `running`, `completed`, `failed`, `manual_pending`, `waiting`.

Each execution step produces a result record: `stageId`, `stageCode`, `stageName`, `action`, `status`, `result`, `message`. If any stage fails or times out, execution stops at that stage.

## Proposal Flow

The proposal step requires completing the client record before submitting. Order matters:

1. `get_client(client_id)` — retrieves partial client created by simulation
2. `build_complete_client_payload()` — fills addresses, documents, bank, Faker data
3. `update_client(client_id, payload)` — PUT with completed data
4. `extract_related_client_ids()` — finds the 5 IDs needed: main document, contract document, address, bank, benefit
5. `build_proposal_payload()` — assembles final POST body
6. `create_proposal()`
7. `fetch_proposal_dashboard()` — retrieves pipeline/flow data for the created proposal

**Critical constraint:** The contract document (RG or CNH generated by Faker) must be a different number from the CPF. `build_proposal_payload()` validates this. The CPF from the simulation always becomes `client_main_document_id`.

**Benefit selection priority** in `select_client_benefit_data()`: `(agreement_id + benefit_number)` > `(agreement_id + document)` > `document` alone.

## Proposal History

Every successful proposal is stored in-memory via `src/core/proposal_history.py`, segregated by environment key (HOMOLOG, DEV, RANCHER). This allows the suite to accumulate context across multiple proposals in a single run — essential for future pipeline validation tests. **History is cleared on every page refresh** via `DELETE /api/proposal-history`.

**Key functions:**
- `record_proposal(record)` → saves and returns the index (1-based)
- `get_history(environment_key)` → returns all `ProposalRecord` for that environment
- `count(environment_key)` → number of proposals stored
- `clear_history()` → wipes all history across all environments
- `build_proposal_record(...)` → factory that extracts proposal/simulation IDs from raw responses
- `extract_proposal_flow(dashboard_response)` → extracts `ProposalFlow` from dashboard API response

Each `ProposalRecord` stores: simulation IDs, proposal IDs, input context (agreement, product, modality, withdraw type, processor), client data, generated data, **pipeline flow** (`ProposalFlow` with stages), and **full raw API responses** (`simulation_response`, `proposal_response`) for future validation.

**Pipeline data structures:**
- `FlowStage` — `id`, `code`, `name`, `status`
- `ProposalFlow` — `proposal_id`, `flow_id`, `stages: list[FlowStage]`

Both interfaces (terminal and web) call `record_proposal()` after every successful proposal creation.

**Additional functions:**
- `update_record_flow(environment_key, index, flow)` → updates the flow of an existing record (used when flow is fetched/refreshed after initial creation)
- `get_history_record(environment_key, index)` → retrieves a single record by index
- `get_all_history()` → returns the complete history map across all environments

## Web Server

`src/interfaces/web/server.py` uses `SimpleHTTPRequestHandler` with a **cached `ApiSession` per environment** (`get_cached_api_session()`). The session is reused across requests to the same environment, avoiding re-authentication on every call. The session cache is invalidated on connect (environment switch). The frontend (`app.js`) owns all UI state.

**Performance optimizations:**
- DB queries in connect run in parallel (`ThreadPoolExecutor`)
- Catalog fetches in proposal run in parallel (6 concurrent API calls)
- Catalog + client fetch in proposal run in parallel
- Google Sheets data is pre-warmed in a background thread on connect

**`/api/faker` kinds:** `name`, `phone`, `document`, `numeric` (default length 8), `password`

**`GET /api/proposal-history?environment=HOMOLOG`** — returns the in-memory proposal history for the given environment. Each record includes a `flow` object with pipeline stages when available.

**`DELETE /api/proposal-history`** — clears all in-memory history. Called automatically by the frontend on page load.

**`POST /api/proposal-history/flow`** — fetches (or refreshes) the pipeline flow for a specific proposal in the history. Uses retry logic (5 attempts, 0.8s delay). Returns cached flow if available (unless `forceRefresh: true`).

**`POST /api/proposal-history/execute`** — starts background execution of the pipeline stages for a proposal, using the flow configuration (actions per stage). Returns immediately; the execution runs in a daemon thread. If already running, returns current state without restarting.

**`POST /api/proposal-history/execution-status`** — polls the current execution state for a proposal. The frontend calls this periodically to update the UI in real time.

**Error response shape:**
```json
{ "error": { "message": "...", "detail": "...", "code": "snake_case_code" } }
```

## Frontend

The JS state object (`state` in `app.js`) is the single source of truth. All DOM updates go through render functions (`renderAll()`, `renderPreview()`, etc.) — never mutate DOM directly outside of them.

Processor-specific panels (`#cipPanel`, `#zetraPanel`, `#serproPanel`, `#ccbPanel`) are controlled exclusively by `renderAdvancedPanels()` via `is-hidden` toggling. Do not show/hide them elsewhere.

Theme (light/dark) persists in `localStorage` under key `suite-consignado-theme`. Sidebar collapsed state persists under `suite-consignado-sidebar-collapsed`.

**Sidebar meta cards:** Processadora, Proposta (`simulation.code`), Contrato (`proposal.contractCode`).

**Results section (block 4) has two cards:**
- **Contrato** (`#contractCard`) — shows `proposal.contractCode` (= `data.code` from proposal API response) after proposal is emitted; financial metrics (value, installment, deadline, margin) from simulation data.
- **Proposta** (`#proposalCard`) — shows `proposal.simulationCode` (= simulation code), proposal ID, contract document type/number, email.

**Proposal preparation (block 3):** Shows simulation ID (`proposalSimulationId`), CPF, benefit number, contract document preview, and email. The simulation code is not displayed here — it appears in the sidebar and proposal card instead.

**History section (block 5):** Table listing all proposals generated in the session. Each row has edit (✎) and execute (▶) action buttons. "Testar Tudo" button appears when 2+ proposals exist.

**Flow evaluation modal (`#flowModal`):** Opened via the edit button in the history table. Displays a vertical pipeline stepper (left) with each stage's name and code, alongside a 3-column evaluation matrix (right) where the user selects one action per stage: "Aguardar" (wait), "Manual" (manual), or "Finalizar" (finish). Selections are stored in `state.flowConfigs` keyed by flow ID. The stepper dots change color to match the selected action.

**Expandable flow rows in history table:** Each proposal row can be expanded (click) to show an inline pipeline stepper with all stages and their current status. Stages are color-coded by status. Flow data is lazy-loaded from the server on first expand.

**Batch execution ("Testar Tudo"):** When 2+ proposals exist in the history, the "Testar Tudo" button appears. It executes all proposals sequentially using their configured flow rules.

**Real-time execution feedback:** When a proposal is being executed (▶ button), the history row shows a loading state. The frontend polls `/api/proposal-history/execution-status` to update stage statuses in real time as the backend processes each stage.

**Google Sheets leading-zero preservation:** `GoogleSheetsService` reads data with `value_render_option=FORMATTED_VALUE` and `numericise_ignore=['all']` to prevent gspread from converting text fields like CPF and Matricula to integers (which would strip leading zeros). The `_map_row()` method applies `.lstrip("'")` to CPF and Matricula to remove any literal apostrophe from formatted values. Balance values come as formatted strings (`"R$ 5.414,29"`) and are parsed by `_parse_balance()` and `money_to_cents()`, which already handle this format.

## Planned Scope (partially implemented)

**Pipeline de validação — PARTIALLY IMPLEMENTED:** The execution engine is in place: flow configuration modal, per-stage actions (wait/manual/finish), background execution with polling, stage status classification, and batch execution ("Testar Tudo"). What remains is defining the specific validation rules and expected outcomes per processor/scenario — the user will provide these before further implementation.

**Testes automatizados:** Automated test suite with processor-specific scenarios and rules. The user will teach the specific automation patterns and rules for each scenario before implementation begins. Do not implement or scaffold proactively.

**Observabilidade:** Structured logging, metrics and reporting for execution runs. The user will define the observability strategy before implementation. Do not implement or scaffold proactively.
