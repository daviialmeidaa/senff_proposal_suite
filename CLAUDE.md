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
src/core/       → EnvironmentConfig (loads .env, normalizes URLs), ProposalHistory (in-memory per-environment, execution results & observability data)
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
| `manual` | Same as wait — monitors the stage but does not intervene. Timeout: 60s. **Exception:** when `stage.code == "payment"`, triggers a two-step payment flow: `PUT .../stage/{id}/payment/assume` → refresh dashboard (stage turns blue) → wait 5s → `PUT .../stage/{id}/payment/finish` (with `payment_date`) → refresh → polls until resolved (timeout: 60s). |
| `finish` | Calls `PUT /admin/proposal/{id}/flow/{flowId}/stage/{stageId}/finish` with `comments: "approved"`, then polls until resolved. Timeout: 5s post-finish. **Exception — `unico-id-check`:** polls `unico_id_cloud_process_proposals` in DB until `unico_id_cloud_process_id` is populated (timeout: 60s, poll: 2s), only then calls finish. **Exception — `ibratan` / `cte`:** waits 10s before calling finish to allow backend processing. |

**Execution runs in a background thread** (`Thread(daemon=True)`). The frontend polls `/api/proposal-history/execution-status` to track progress in real time.

**Stage status classification** determines stage resolution:
- **Success:** APPROVED, SUCCESS, DONE, COMPLETED, COMPLETE, FINISHED, OK, PAID
- **Failure:** FAIL, FAILED, ERROR, REJECTED, DENIED, CANCELED, CANCELLED, INVALID
- **Manual:** MANUAL, MANUAL_ANALYSIS, PENDING_MANUAL, or any status containing "MANUAL"
- **In progress:** IN_PROGRESS, PROCESSING, RUNNING, STARTED

**Execution state** is managed per `(environment, history_index)` in a thread-safe `_EXECUTION_STATE` dict. States: `idle`, `running`, `completed`, `failed`, `manual_pending`, `waiting`, `cancelled`.

Each execution step produces a result record: `stageId`, `stageCode`, `stageName`, `action`, `status`, `result`, `message`. If any stage fails, times out, or is cancelled, execution stops at that stage.

**Cancellation and reset system:** Execution can be cancelled individually or globally via cooperative cancellation using `threading.Event`. The `interruptible_sleep()` helper breaks long waits into 0.5s increments, checking the cancellation flag each iteration. All execution loops (stage iteration, `wait_for_stage_resolution`, unico-id DB poll, payment/credit/cte delays) check `is_cancelled()` before proceeding. Four endpoints control this:
- `POST /api/proposal-history/cancel-execution` — cancels one execution
- `POST /api/proposal-history/cancel-all-executions` — cancels all running executions
- `POST /api/proposal-history/reset-execution` — cancels and clears state for one execution
- `POST /api/proposal-history/reset-all-executions` — cancels and clears all execution states

**Post-stage CCB validation:** After the `contract_integration` stage is approved, the engine polls the `ccbs` table in the database (by `code = contract_code`) to confirm the proposal was actually integrated. Poll interval: 2s, timeout: 30s. If the CCB is found, an extra `ccb_validation` step is appended with status `VALIDATED`. If not found, execution fails with status `NOT_FOUND`.

**Stage-specific pre-finish delays:**
- `ibratan` / `cte`: waits `STAGE_PRE_FINISH_DELAY_SECONDS` (10s) before calling finish
- `avbdataprev` (Averbação): waits `STAGE_PRE_FINISH_DELAY_AVB_SECONDS` (15s) before calling finish — the stage continues processing in the background and advances the pipeline even when it turns red, so the delay ensures the backend has time to settle before finish is sent

## Execution Results & Observability

The execution engine records detailed observability data for every execution run. All HTTP calls and DB checks are instrumented with timing, status, and contextual metadata.

**Data structures** (`src/core/proposal_history.py`):
- `ExecutionHttpCall` — `timestamp`, `label`, `method`, `path`, `status_code`, `duration_ms`, `correlation_id`, `message`
- `ExecutionDbCheck` — `timestamp`, `label`, `query_name`, `duration_ms`, `matched` (bool|None), `message`, `query_sql` (optional — the exact SQL string executed, for display in results)
- `StageExecutionResult` — per-stage metrics: `stage_id`, `stage_code`, `stage_name`, `initial_status`, `final_status`, `result`, `started_at`, `finished_at`, `duration_ms`, `configured_action`, `http_calls[]`, `db_checks[]`, `notes[]`, `message`
- `ProposalExecutionResult` — aggregated per-run: `run_id`, `status`, `message`, `started_at`, `finished_at`, `duration_ms`, `total_http_calls`, `total_db_checks`, `stage_results[]`

Each `ProposalRecord` now has an `executions: list[ProposalExecutionResult]` field that accumulates all execution runs for that proposal.

**Instrumented wrappers** in `server.py`:
- `execute_logged_http_call()` — wraps any API call, records method, path, status code, duration, correlation ID, and error messages into an `ExecutionHttpCall`
- `execute_logged_db_check()` — wraps any DB operation, records query name, matched result, duration, and the exact SQL string (`query_sql`) into an `ExecutionDbCheck`. The `query_sql` parameter is optional; call sites pass the real SQL with interpolated values so it can be displayed verbatim in the results dashboard.

**Result building:**
- `build_stage_result()` — assembles a `StageExecutionResult` with all collected HTTP calls, DB checks, notes, and timing for one stage
- `_build_execution_result()` — creates `ProposalExecutionResult` with calculated totals (`total_http_calls`, `total_db_checks`, `duration_ms`) from all stage results

**Artifact persistence:** After each execution completes, `persist_execution_artifact()` saves a full JSON file to `artifacts/executions/{environment}/`. Filename format: `history-{index:03d}_proposal-{proposal_id}_run-{run_id}.json`. Contains the complete serialized execution with all metrics.

**Observability summary:** `_build_observability_summary()` aggregates metrics across all proposals and executions for a given environment:
- `proposalsWithExecutions` — count of proposals with at least one execution
- `totalExecutions`, `completedExecutions`, `failedExecutions`, `manualExecutions`, `waitingExecutions`, `cancelledExecutions`
- `totalStageResults`, `totalHttpCalls`, `totalDbChecks`
- `averageDurationMs` — average execution duration
- `latestFinishedAt` — timestamp of last completed execution

**History response** (`GET /api/proposal-history`) now returns:
```json
{
  "environment": "HOMOLOG",
  "count": 3,
  "observabilitySummary": { ... },
  "proposals": [
    {
      "index": 1,
      "proposalId": "...",
      "executionCount": 2,
      "latestExecution": { ... },
      "executions": [ ... ]
    }
  ]
}
```

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

Each `ProposalRecord` stores: simulation IDs, proposal IDs, input context (agreement, product, modality, withdraw type, processor), client data, generated data, **pipeline flow** (`ProposalFlow` with stages), **full raw API responses** (`simulation_response`, `proposal_response`) for future validation, and **execution results** (`executions: list[ProposalExecutionResult]`) with full observability data.

**Pipeline data structures:**
- `FlowStage` — `id`, `code`, `name`, `status`
- `ProposalFlow` — `proposal_id`, `flow_id`, `stages: list[FlowStage]`

Both interfaces (terminal and web) call `record_proposal()` after every successful proposal creation.

**Additional functions:**
- `update_record_flow(environment_key, index, flow)` → updates the flow of an existing record (used when flow is fetched/refreshed after initial creation)
- `append_record_execution(environment_key, index, execution)` → appends an execution result to an existing record
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

**`POST /api/proposal-history/cancel-execution`** — cancels a single running execution by setting its cancellation flag.

**`POST /api/proposal-history/cancel-all-executions`** — cancels all running executions.

**`POST /api/proposal-history/reset-execution`** — cancels and clears the execution state for a single proposal.

**`POST /api/proposal-history/reset-all-executions`** — cancels and clears all execution states.

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

**Batch execution ("Testar Tudo"):** When 2+ proposals exist in the history, the "Testar Tudo" button appears. It executes all proposals sequentially using their configured flow rules. Batch execution checks `state.batchCancelled` between proposals and stops early if cancellation was requested.

**Real-time execution feedback:** When a proposal is being executed (▶ button), the history row shows a loading state with a cancel button (red X). The frontend polls `/api/proposal-history/execution-status` to update stage statuses in real time as the backend processes each stage.

**Execution controls:** The history section includes "Cancelar Tudo" (cancel all running executions) and "Resetar Execucoes" (cancel and clear all execution states) buttons alongside "Testar Tudo". Individual proposals can be cancelled via the red X button that appears during execution.

**Proposal cooldown:** After a successful simulation, the "Emitir Proposta" button is disabled for 5 seconds (`state.proposalCooldown`) to prevent accidental double-clicks. During cooldown, the action area shows "Aguardando persistencia..." with a spinner.

**Observability section (block 6 — "Resultados"):** Displays a dashboard with execution metrics after proposals are executed. Composed of:
- **Summary cards grid** (`#observabilitySummaryGrid`) — 8 metric cards: proposals monitored, total executions, completed, pending (manual), failures, total HTTP calls, total DB checks, average duration. Each card has a label, value, helper text, and tone-based color palette.
- **Proposal list** (`#observabilityProposalList`) — expandable cards per proposal showing: proposal info, status, duration, stage timeline visualization, and a list of all executions.
- **Execution panels** — collapsible details per execution run: run ID, status, message, timing, HTTP/DB call counts, and per-stage details.
- **Stage cards** — per-stage breakdown: code, name, configured action, status transition (initial → final), duration, notes as badges, expandable HTTP request list and DB check list with full details (method, path, status code, duration, timestamp, correlation ID). The DB check table includes a **SQL** column showing the exact query executed (when `query_sql` is set).
- **Stage timeline** — visual connected-node timeline showing stage progression with color-coded status dots.

The observability summary is populated from `state.observabilitySummary` which comes from the `observabilitySummary` field in the `GET /api/proposal-history` response. Rendering is handled by `renderObservability()` and its builders: `buildObservabilitySummaryCard()`, `buildObservabilityProposalCard()`, `buildObservabilityExecutionPanel()`, `buildObservabilityStageCard()`, `buildObservabilityHttpCallList()`, `buildObservabilityDbCheckList()`, `buildObservabilityStageTimeline()`.

**Status tone mapping:** `getExecutionStatusTone()` maps execution statuses to UI tones — `danger` (failed/cancelled), `warning` (manual_pending/waiting), `progress` (running), `success` (completed), `neutral` (idle/unknown). Each tone defines Tailwind classes for `softBorder`, `softBackground`, `eyebrow`, and `badge`.

**Duration formatting:** `formatDurationMs()` converts milliseconds to human-readable format (ms/s/m/h). `formatDateTimeLabel()` formats timestamps in pt-BR locale.

**Google Sheets leading-zero preservation:** `GoogleSheetsService` reads data with `value_render_option=FORMATTED_VALUE` and `numericise_ignore=['all']` to prevent gspread from converting text fields like CPF and Matricula to integers (which would strip leading zeros). The `_map_row()` method applies `.lstrip("'")` to CPF and Matricula to remove any literal apostrophe from formatted values. Balance values come as formatted strings (`"R$ 5.414,29"`) and are parsed by `_parse_balance()` and `money_to_cents()`, which already handle this format.

## Protheus Validation

Two-phase validation runs automatically when stages `protheus` or `protheus-issuance` are configured as `wait` in the flow modal. Implemented in `src/services/protheus_validator.py`.

### Phase 1 — Formalization (`protheus`)

Triggered when `stage_code == "protheus"` and `action == "wait"`, after the stage resolves (`approved` or `waiting_timeout`). Up to **6 retries** with **5s interval**.

Shared state passed to Phase 2: `_protheus_correlation_id` (fetched once from `proposals WHERE code = proposal_code`), `_protheus_last_log_id` (cutoff ID), `_protheus_client_code` (code from `protheus_client_codes`).

**Steps:**

1. **`protheus_client_codes` lookup** — `SELECT code FROM protheus_client_codes WHERE document = {cpf}`. If CPF not found → immediate failure. If found → records the `code` value in the results. This `code` is passed to Phase 2.

2. **Read `protheus_logs`** — `SELECT ... FROM protheus_logs WHERE correlation_id = {cid} ORDER BY id ASC`. Audit check records row count.

3. **Determine `cutoff_id`** — scans logs for the first entry where `request_body` contains `ATUALIZAR` and `response_body` contains `<STATUS>true</STATUS>`. Sets `db_atualizar_ok = True`. If not found, cutoff falls back to the last log ID.

4. **Build evidence** — adds one `ProtheusCheckItem` per log up to `cutoff_id`.

5. **Re-derive `db_atualizar_ok`** from evidence logs.

6. **External VALFOR SOAP call (always mandatory)** — `POST` to `SENFFFORNECEDORES.apw`. Success criterion: **`<RETWS>` present in response (true OR false)** — either value confirms the CPF is registered in Protheus. Absent RETWS = connectivity failure or CPF not found. Recorded as `api_valfor_ok`.

7. **Result:** `db_atualizar_ok AND api_valfor_ok`.

Returns `(ProtheusValidationResult, cutoff_id, client_code)`.

> **Note:** VALFOR is no longer checked in `protheus_logs`. It is always called externally.

### Phase 2 — Issuance (`protheus-issuance`)

Triggered when `stage_code == "protheus-issuance"` and `action == "wait"`. Up to **6 retries** with **5s interval**.

**Steps:**

1. **`protheus_client_codes` lookup** — uses `_protheus_client_code` inherited from Phase 1 (shown as "herdado"). If Phase 1 did not run, fetches from DB. If still `None` → immediate failure.

2. **Read `protheus_logs`** — full table read; only logs with `id > last_protheus_id` are added as evidence.

3. **Find INCPAGARSE log** — scans all logs for `INCPAGARSE` in `request_body` + `<STATUS>true</STATUS>` in `response_body` → `db_success`. If not found and `stage_already_approved == True` → **Sem Saque bypass** (`valid=True, bypassed=True`). If not found and not approved → returns `valid=False` (triggers retry).

4. **Proof-of-reality SOAP call** — `POST` to `SENFFTITULOSSE.apw` (INCPAGARSE). Uses `protheus_client_code` in `CLIENTEFORNECEDOOR` field (not CPF digits). Expects duplicate-fault response (`"Je existe titulo"`) → `api_ok`.

5. **Confirm in `protheus_issuance`** — `SELECT WHERE proposal_id = {id} AND number = 'SC{id:07d}'` → `table_ok`.

6. **Result:** `db_success AND api_ok AND table_ok`.

### Database functions (`src/infra/database.py`)

| Function | Query |
|---|---|
| `fetch_proposal_correlation_id(config, code)` | `SELECT correlation_id FROM proposals WHERE code = %s` |
| `fetch_protheus_logs(config, correlation_id)` | `SELECT ... FROM protheus_logs WHERE correlation_id = %s ORDER BY id ASC` |
| `fetch_protheus_client_code(config, cpf)` | `SELECT code FROM protheus_client_codes WHERE document = %s` |
| `check_protheus_issuance_exists(config, proposal_id, number)` | `SELECT id FROM protheus_issuance WHERE proposal_id = %s AND number = %s` |

### AI Commentary

After each Protheus validation, `generate_ai_commentary_for_protheus_stage()` sends a compact check summary to OpenAI (model from `OPENAI_STAGE_MODEL` env var, fallbacks to `gpt-4.1-mini` / `gpt-4o-mini`). Returns a 3-line diagnosis: `BANCO:` / `API:` / `CONSOLIDADO:`. Injected as a `SYSTEM`-type `ProtheusCheckItem` into the validation checks. If `OPENAI_API_KEY` is not set, a fallback message is used.

### Frontend display

Validation results are serialized via `_serialize_protheus_validation()` and included in every `StageExecutionResult`. Rendered in block 6 ("Resultados") by `buildObsProtheusValidation()`: green/red panel header, badge (Validado/Invalido/Bypass), check table with expandable request/response payloads.

### Scenario documentation

`cenarios/validacoes_esteira/protheus/validacao_protheus.md` — full technical spec of validation rules, SQL queries, SOAP payloads, and retry/bypass behaviour.

## Planned Scope (partially implemented)

**Pipeline de validação — PARTIALLY IMPLEMENTED:** The execution engine is in place: flow configuration modal, per-stage actions (wait/manual/finish), background execution with polling, stage status classification, batch execution ("Testar Tudo"), cooperative cancellation/reset system, CCB integration validation, Protheus two-phase validation, proposal cooldown, and full observability with metrics. What remains is defining validation rules for other stages/processors — the user will provide these before further implementation.

**Testes automatizados:** Automated test suite with processor-specific scenarios and rules. The user will teach the specific automation patterns and rules for each scenario before implementation begins. Do not implement or scaffold proactively.

**Observabilidade — IMPLEMENTED:** The observability layer is fully in place. Every execution run is instrumented with HTTP call timing, DB check tracking, per-stage duration and status transitions. Results are persisted as JSON artifacts in `artifacts/executions/` and displayed in a dedicated frontend dashboard (block 6 — "Resultados") with summary metrics, proposal-level drill-down, and per-stage HTTP/DB call details.
