from __future__ import annotations

import html
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import Any

import requests
from urllib.parse import parse_qs, urlparse

from src.infra.api_client import (
    ApiAuthenticationError,
    ApiRequestError,
    ApiSession,
    CatalogOption,
    CipBenefit,
    DataprevBenefit,
    SerproBenefit,
    build_stores_query_string,
    create_proposal,
    create_simulation,
    extract_response_data_dict,
    fetch_agreement_processor_code,
    fetch_my_stores,
    fetch_proposal_dashboard,
    assume_payment_stage,
    finish_payment_stage,
    finish_proposal_stage,
    get_client,
    list_catalog_options,
    list_cip_benefits,
    list_dataprev_benefits,
    list_serpro_benefits,
    update_client,
)
from src.core.config import EnvironmentConfig, get_environment_config, load_environment_file
from src.infra.database import (
    Product,
    check_ccb_exists,
    check_unico_id_ready,
    fetch_agreements,
    fetch_products,
    fetch_proposal_correlation_id,
    fetch_sale_modalities,
    fetch_withdraw_types,
    test_connection,
)
from src.services.protheus_validator import (
    validate_protheus_formalization,
    validate_protheus_issuance,
)
from src.services.fake_data import FakeDataService
from src.infra.google_sheets import (
    GoogleSheetsError,
    GoogleSheetsService,
    PROCESSOR_SHEET_MAP,
    SelectedSheetRecord,
)
from src.core.proposal_history import (
    ExecutionDbCheck,
    ExecutionHttpCall,
    ProtheusCheckItem,
    ProposalExecutionResult,
    StageExecutionResult,
    append_record_execution,
    build_proposal_record,
    clear_history,
    extract_proposal_flow,
    get_history,
    get_history_record,
    record_proposal,
    update_record_flow,
)
from src.domain.proposal import (
    ProposalCatalogs,
    ProposalGeneratedClientData,
    ProposalPayloadError,
    build_complete_client_payload,
    build_proposal_payload,
    extract_main_document_id,
    extract_related_client_ids,
    select_client_benefit_data,
)
from src.domain.simulation import (
    SerproIdentifiers,
    SimulationClient,
    SimulationPayloadError,
    SimulationPayloadInput,
    build_simulation_payload,
    is_cip_processor,
    is_dataprev_processor,
    is_serpro_processor,
    is_zetra_processor,
    sale_modality_requires_original_ccb,
    sanitize_digits,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PROPOSAL_FLOW_FETCH_ATTEMPTS = 5
PROPOSAL_FLOW_FETCH_DELAY_SECONDS = 0.8
OPENAI_REPORT_TIMEOUT_SECONDS = 25
OPENAI_STAGE_COMMENT_TIMEOUT_SECONDS = 18
OPENAI_REPORT_MAX_PROPOSALS_CONTEXT = 20
FLOW_EXECUTION_POLL_INTERVAL_SECONDS = 1.0
FLOW_EXECUTION_WAIT_TIMEOUT_SECONDS = 60.0
FLOW_FINISH_APPROVAL_TIMEOUT_SECONDS = 5.0
PAYMENT_ASSUME_SETTLE_SECONDS = 5.0
STAGE_PRE_FINISH_DELAY_SECONDS = 10.0
STAGE_PRE_FINISH_DELAY_AVB_SECONDS = 15.0
UNICO_ID_DB_POLL_INTERVAL_SECONDS = 2.0
UNICO_ID_DB_POLL_TIMEOUT_SECONDS = 60.0
CCB_VALIDATION_POLL_INTERVAL_SECONDS = 2.0
CCB_VALIDATION_POLL_TIMEOUT_SECONDS = 30.0
PROTHEUS_VALIDATION_RETRIES = 6
PROTHEUS_VALIDATION_RETRY_INTERVAL_SECONDS = 5.0
ENVIRONMENT_OPTIONS = {
    "HOMOLOG": "Homolog",
    "DEV": "Dev",
    "RANCHER": "Rancher",
}

_SESSION_CACHE_LOCK = Lock()
_SESSION_CACHE: dict[str, ApiSession] = {}
_EXECUTION_STATE_LOCK = Lock()
_EXECUTION_STATE: dict[str, dict[str, Any]] = {}
_EXECUTION_CANCEL_LOCK = Lock()
_EXECUTION_CANCEL_FLAGS: dict[str, Event] = {}


def get_cached_api_session(config: EnvironmentConfig) -> ApiSession:
    with _SESSION_CACHE_LOCK:
        session = _SESSION_CACHE.get(config.key)
        if session is not None:
            session.ensure_authenticated()
            return session

    session = ApiSession(config)
    session.authenticate()

    with _SESSION_CACHE_LOCK:
        _SESSION_CACHE[config.key] = session
    return session


def invalidate_cached_session(config_key: str) -> None:
    with _SESSION_CACHE_LOCK:
        _SESSION_CACHE.pop(config_key, None)



def build_execution_state_key(environment_key: str, history_index: int) -> str:
    return f"{environment_key}:{history_index}"



def get_execution_state(environment_key: str, history_index: int) -> dict[str, Any] | None:
    key = build_execution_state_key(environment_key, history_index)
    with _EXECUTION_STATE_LOCK:
        value = _EXECUTION_STATE.get(key)
        return dict(value) if value is not None else None



def set_execution_state(environment_key: str, history_index: int, payload: dict[str, Any]) -> dict[str, Any]:
    key = build_execution_state_key(environment_key, history_index)
    next_payload = dict(payload)
    with _EXECUTION_STATE_LOCK:
        _EXECUTION_STATE[key] = next_payload
    return next_payload



def clear_execution_state(environment_key: str, history_index: int) -> None:
    key = build_execution_state_key(environment_key, history_index)
    with _EXECUTION_STATE_LOCK:
        _EXECUTION_STATE.pop(key, None)



def clear_all_execution_states() -> None:
    with _EXECUTION_STATE_LOCK:
        _EXECUTION_STATE.clear()


def get_cancel_flag(environment_key: str, history_index: int) -> Event:
    key = build_execution_state_key(environment_key, history_index)
    with _EXECUTION_CANCEL_LOCK:
        flag = _EXECUTION_CANCEL_FLAGS.get(key)
        if flag is None:
            flag = Event()
            _EXECUTION_CANCEL_FLAGS[key] = flag
        return flag


def request_cancel(environment_key: str, history_index: int) -> None:
    flag = get_cancel_flag(environment_key, history_index)
    flag.set()


def reset_cancel_flag(environment_key: str, history_index: int) -> None:
    key = build_execution_state_key(environment_key, history_index)
    with _EXECUTION_CANCEL_LOCK:
        _EXECUTION_CANCEL_FLAGS.pop(key, None)


def cancel_all_executions() -> None:
    with _EXECUTION_CANCEL_LOCK:
        for flag in _EXECUTION_CANCEL_FLAGS.values():
            flag.set()


def is_cancelled(environment_key: str, history_index: int) -> bool:
    key = build_execution_state_key(environment_key, history_index)
    with _EXECUTION_CANCEL_LOCK:
        flag = _EXECUTION_CANCEL_FLAGS.get(key)
        return flag is not None and flag.is_set()


def build_execution_state_payload(
    *,
    status: str,
    message: str,
    flow_config: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    started_at: str = "",
    finished_at: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "flowConfig": flow_config or {},
        "steps": steps or [],
        "startedAt": started_at,
        "finishedAt": finished_at,
    }

class WebApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = HTTPStatus.BAD_REQUEST,
        detail: str = "",
        code: str = "web_api_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = int(status_code)
        self.detail = detail
        self.code = code


class AutomationRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/environments":
            return self._write_json({"items": list_environment_options()})

        if path == "/api/app-config":
            return self._write_json(build_app_config_response())

        if path == "/api/faker":
            query = parse_qs(parsed.query)
            kind = (query.get("kind") or [""])[0]
            length = int((query.get("length") or ["8"])[0] or "8")
            return self._handle_api_call(lambda: build_faker_response(kind, length))

        if path == "/api/proposal-history":
            query = parse_qs(parsed.query)
            env_key = (query.get("environment") or [""])[0].upper()
            return self._handle_api_call(lambda: build_proposal_history_response(env_key))

        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        handlers = {
            "/api/session/connect": handle_connect_request,
            "/api/session/preview": handle_preview_request,
            "/api/session/simulate": handle_simulate_request,
            "/api/session/proposal": handle_proposal_request,
            "/api/proposal-history/flow": handle_proposal_flow_request,
            "/api/proposal-history/execute": handle_proposal_execute_request,
            "/api/proposal-history/execution-status": handle_proposal_execution_status_request,
            "/api/proposal-history/cancel-execution": handle_cancel_execution_request,
            "/api/proposal-history/cancel-all-executions": handle_cancel_all_executions_request,
            "/api/proposal-history/reset-execution": handle_reset_execution_request,
            "/api/proposal-history/reset-all-executions": handle_reset_all_executions_request,
            "/api/report/generate": handle_generate_report_request,
        }

        handler = handlers.get(parsed.path)
        if handler is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Rota nao encontrada.")
            return

        try:
            payload = self._read_json_body()
        except WebApiError as exc:
            self._write_json_error(exc)
            return

        return self._handle_api_call(lambda: handler(payload))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/proposal-history":
            clear_history()
            clear_all_execution_states()
            return self._write_json({"ok": True})
        self.send_error(HTTPStatus.NOT_FOUND, "Rota nao encontrada.")

    def _handle_api_call(self, action) -> None:
        try:
            payload = action()
        except WebApiError as exc:
            self._write_json_error(exc)
            return
        except Exception as exc:  # noqa: BLE001
            self._write_json_error(
                WebApiError(
                    "Erro interno ao processar a solicitacao.",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=str(exc),
                    code="internal_error",
                )
            )
            return

        self._write_json(payload)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            decoded = raw_body.decode("utf-8")
            payload = json.loads(decoded or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebApiError(
                "Corpo JSON invalido.",
                status_code=HTTPStatus.BAD_REQUEST,
                detail=str(exc),
                code="invalid_json",
            ) from exc

        if not isinstance(payload, dict):
            raise WebApiError(
                "O corpo da requisicao precisa ser um objeto JSON.",
                status_code=HTTPStatus.BAD_REQUEST,
                code="invalid_payload",
            )
        return payload

    def _write_json(self, payload: dict[str, Any], status_code: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_json_error(self, error: WebApiError) -> None:
        self._write_json(
            {
                "error": {
                    "message": error.message,
                    "detail": error.detail,
                    "code": error.code,
                }
            },
            status_code=error.status_code,
        )



def configure_console_output() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")



def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    configure_console_output()
    load_environment_file()
    server = ThreadingHTTPServer((host, port), AutomationRequestHandler)
    print(f"Frontend disponivel em http://{host}:{port}")
    server.serve_forever()



def list_environment_options() -> list[dict[str, str]]:
    return [
        {"key": key, "label": label}
        for key, label in ENVIRONMENT_OPTIONS.items()
    ]


def build_app_config_response() -> dict[str, Any]:
    return {
        "branding": {
            "logoUrl": sanitize_text(os.getenv("SENFF_LOGO_URL")),
            "iconUrl": sanitize_text(os.getenv("SENFF_ICON_URL")),
            "title": "Suite Consignado",
            "subtitle": "Simulacoes e propostas",
        }
    }



def build_faker_response(kind: str, length: int) -> dict[str, str]:
    fake_data_service = FakeDataService()
    if kind == "name":
        return {"value": fake_data_service.generate_name()}
    if kind == "document":
        return {"value": fake_data_service.generate_document()}
    if kind == "phone":
        return {"value": fake_data_service.generate_phone()}
    if kind == "numeric":
        return {"value": fake_data_service.generate_numeric_code(length)}
    if kind == "password":
        return {"value": fake_data_service.generate_password()}
    raise WebApiError(
        "Tipo de dado ficticio nao suportado.",
        status_code=HTTPStatus.BAD_REQUEST,
        code="invalid_faker_kind",
    )



def _serialize_http_call(call: ExecutionHttpCall) -> dict[str, Any]:
    return asdict(call)



def _serialize_db_check(check: ExecutionDbCheck) -> dict[str, Any]:
    return asdict(check)



def _serialize_protheus_validation(pv) -> dict[str, Any] | None:
    if pv is None:
        return None
    return {
        "stageCode": pv.stage_code,
        "valid": pv.valid,
        "bypassed": pv.bypassed,
        "message": pv.message,
        "checks": [
            {
                "label": c.label,
                "sourceType": c.source_type,
                "origin": c.origin,
                "result": c.result,
                "message": c.message,
                "querySql": c.query_sql,
                "httpVerb": c.http_verb,
                "url": c.url,
                "requestHeaders": c.request_headers,
                "requestBody": c.request_body,
                "responseBody": c.response_body,
                "httpStatusCode": c.http_status_code,
                "durationMs": c.duration_ms,
            }
            for c in (pv.checks or [])
        ],
    }


def _serialize_stage_execution(stage: StageExecutionResult) -> dict[str, Any]:
    return {
        "stageId": stage.stage_id,
        "stageCode": stage.stage_code,
        "stageName": stage.stage_name,
        "configuredAction": stage.configured_action,
        "initialStatus": stage.initial_status,
        "finalStatus": stage.final_status,
        "result": stage.result,
        "message": stage.message,
        "startedAt": stage.started_at,
        "finishedAt": stage.finished_at,
        "durationMs": stage.duration_ms,
        "notes": list(stage.notes),
        "httpCalls": [_serialize_http_call(call) for call in stage.http_calls],
        "dbChecks": [_serialize_db_check(check) for check in stage.db_checks],
        "protheusValidation": _serialize_protheus_validation(stage.protheus_validation),
    }



def _serialize_execution_result(execution: ProposalExecutionResult | None) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "runId": execution.run_id,
        "status": execution.status,
        "message": execution.message,
        "startedAt": execution.started_at,
        "finishedAt": execution.finished_at,
        "durationMs": execution.duration_ms,
        "totalHttpCalls": execution.total_http_calls,
        "totalDbChecks": execution.total_db_checks,
        "stageResults": [_serialize_stage_execution(stage) for stage in execution.stage_results],
    }



def _build_observability_summary(records: list[Any]) -> dict[str, Any]:
    executions = [execution for record in records for execution in (record.executions or [])]
    duration_values = [execution.duration_ms for execution in executions if execution.duration_ms > 0]
    latest_finished_at = ""
    if executions:
        latest_finished_at = max((execution.finished_at or "") for execution in executions)

    return {
        "proposalsWithExecutions": sum(1 for record in records if record.executions),
        "totalExecutions": len(executions),
        "completedExecutions": sum(1 for execution in executions if execution.status == "completed"),
        "failedExecutions": sum(1 for execution in executions if execution.status == "failed"),
        "manualExecutions": sum(1 for execution in executions if execution.status == "manual_pending"),
        "waitingExecutions": sum(1 for execution in executions if execution.status == "waiting"),
        "cancelledExecutions": sum(1 for execution in executions if execution.status == "cancelled"),
        "totalStageResults": sum(len(execution.stage_results) for execution in executions),
        "totalHttpCalls": sum(execution.total_http_calls for execution in executions),
        "totalDbChecks": sum(execution.total_db_checks for execution in executions),
        "averageDurationMs": int(sum(duration_values) / len(duration_values)) if duration_values else 0,
        "latestFinishedAt": latest_finished_at,
    }



def persist_execution_artifact(
    environment_key: str,
    history_index: int,
    record,
    execution: ProposalExecutionResult,
) -> None:
    artifacts_dir = PROJECT_ROOT / "artifacts" / "executions" / environment_key.lower()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / (
        f"history-{history_index:03d}_proposal-{sanitize_text(record.proposal_id) or 'unknown'}_run-{execution.run_id}.json"
    )
    artifact_payload = {
        "environment": environment_key,
        "historyIndex": history_index,
        "proposalId": record.proposal_id,
        "proposalCode": record.proposal_code,
        "contractCode": record.contract_code,
        "simulationCode": record.simulation_code,
        "execution": _serialize_execution_result(execution),
    }
    artifact_path.write_text(
        json.dumps(artifact_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



def build_proposal_history_response(environment_key: str) -> dict[str, Any]:
    records = get_history(environment_key) if environment_key else []
    return {
        "environment": environment_key,
        "count": len(records),
        "observabilitySummary": _build_observability_summary(records),
        "proposals": [
            {
                "index": idx + 1,
                "createdAt": r.created_at,
                "proposalId": r.proposal_id,
                "proposalCode": r.proposal_code,
                "contractCode": r.contract_code,
                "simulationId": r.simulation_id,
                "simulationCode": r.simulation_code,
                "clientId": r.client_id,
                "clientName": r.client_name,
                "clientDocument": r.client_document,
                "agreementId": r.agreement_id,
                "productId": r.product_id,
                "saleModalityId": r.sale_modality_id,
                "withdrawTypeId": r.withdraw_type_id,
                "processorCode": r.processor_code,
                "flow": _serialize_flow(r.flow),
                "executionCount": len(r.executions or []),
                "latestExecution": _serialize_execution_result(r.executions[-1] if r.executions else None),
                "executions": [_serialize_execution_result(execution) for execution in (r.executions or [])],
            }
            for idx, r in enumerate(records)
        ],
    }


def handle_proposal_flow_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    history_index = parse_history_index(payload.get("historyIndex"))
    force_refresh = parse_bool(payload.get("forceRefresh"))
    record = get_history_record(config.key, history_index)
    if record is None:
        raise WebApiError(
            "Nao foi possivel localizar a proposta selecionada no historico.",
            status_code=HTTPStatus.NOT_FOUND,
            code="proposal_history_not_found",
        )

    if not force_refresh and record.flow and record.flow.stages:
        return {
            "historyIndex": history_index,
            "flow": _serialize_flow(record.flow),
        }

    try:
        api_session = get_cached_api_session(config)
        ensure_api_session_store_context(api_session)
        proposal_flow = fetch_proposal_flow_with_retry(
            api_session=api_session,
            simulation_code=record.simulation_code,
        )
    except (ApiAuthenticationError, ApiRequestError) as exc:
        raise WebApiError(
            "Nao foi possivel carregar as etapas desta proposta no dashboard.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=format_web_error_detail(exc),
            code="proposal_flow_fetch_failed",
        ) from exc

    if proposal_flow is None or not proposal_flow.stages:
        raise WebApiError(
            "O dashboard ainda nao retornou etapas para esta proposta.",
            status_code=HTTPStatus.NOT_FOUND,
            detail="A proposta foi criada, mas a esteira ainda nao ficou disponivel no dashboard. Tente novamente em alguns instantes.",
            code="proposal_flow_not_available",
        )

    update_record_flow(config.key, history_index, proposal_flow)
    return {
        "historyIndex": history_index,
        "flow": _serialize_flow(proposal_flow),
    }


def handle_proposal_execute_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    history_index = parse_history_index(payload.get("historyIndex"))
    record = get_history_record(config.key, history_index)
    if record is None:
        raise WebApiError(
            "Nao foi possivel localizar a proposta selecionada no historico.",
            status_code=HTTPStatus.NOT_FOUND,
            code="proposal_history_not_found",
        )

    current_state = get_execution_state(config.key, history_index)
    if current_state and current_state.get("status") == "running":
        return {
            "historyIndex": history_index,
            "flow": _serialize_flow(record.flow),
            "flowConfig": current_state.get("flowConfig") or {},
            "execution": current_state,
            "started": False,
        }

    try:
        api_session = get_cached_api_session(config)
        ensure_api_session_store_context(api_session)
        current_flow = refresh_proposal_flow_record(
            api_session=api_session,
            config_key=config.key,
            history_index=history_index,
            record=record,
            use_retry=True,
        )
    except (ApiAuthenticationError, ApiRequestError) as exc:
        raise WebApiError(
            "Nao foi possivel consultar a esteira atual da proposta.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=format_web_error_detail(exc),
            code="proposal_flow_fetch_failed",
        ) from exc

    if current_flow is None or not current_flow.stages:
        raise WebApiError(
            "O dashboard ainda nao retornou etapas para esta proposta.",
            status_code=HTTPStatus.NOT_FOUND,
            detail="A proposta foi criada, mas a esteira ainda nao ficou disponivel no dashboard. Tente novamente em alguns instantes.",
            code="proposal_flow_not_available",
        )

    execution_plan = build_flow_execution_plan(
        record=record,
        flow=current_flow,
        flow_config_payload=payload.get("flowConfig"),
    )

    execution_state = build_execution_state_payload(
        status="running",
        message="Execucao iniciada. Acompanhando a esteira da proposta...",
        flow_config=execution_plan,
    )
    set_execution_state(config.key, history_index, execution_state)

    worker = Thread(
        target=run_proposal_execution_in_background,
        args=(config.key, history_index, execution_plan),
        daemon=True,
    )
    worker.start()

    return {
        "historyIndex": history_index,
        "flow": _serialize_flow(current_flow),
        "flowConfig": execution_plan,
        "execution": execution_state,
        "started": True,
    }



def handle_proposal_execution_status_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    history_index = parse_history_index(payload.get("historyIndex"))
    record = get_history_record(config.key, history_index)
    if record is None:
        raise WebApiError(
            "Nao foi possivel localizar a proposta selecionada no historico.",
            status_code=HTTPStatus.NOT_FOUND,
            code="proposal_history_not_found",
        )

    execution_state = get_execution_state(config.key, history_index)
    if execution_state is None:
        execution_state = build_execution_state_payload(
            status="idle",
            message="Nenhuma execucao em andamento para esta proposta.",
        )

    return {
        "historyIndex": history_index,
        "flow": _serialize_flow(record.flow),
        "flowConfig": execution_state.get("flowConfig") or {},
        "execution": execution_state,
    }



def handle_cancel_execution_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    history_index = parse_history_index(payload.get("historyIndex"))
    request_cancel(config.key, history_index)
    return {"historyIndex": history_index, "cancelled": True}


def handle_cancel_all_executions_request(_payload: dict[str, Any]) -> dict[str, Any]:
    cancel_all_executions()
    return {"cancelled": True}


def handle_reset_execution_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    history_index = parse_history_index(payload.get("historyIndex"))
    current_state = get_execution_state(config.key, history_index)
    if current_state and current_state.get("status") == "running":
        request_cancel(config.key, history_index)
    clear_execution_state(config.key, history_index)
    reset_cancel_flag(config.key, history_index)
    return {"historyIndex": history_index, "reset": True}


def handle_reset_all_executions_request(_payload: dict[str, Any]) -> dict[str, Any]:
    cancel_all_executions()
    clear_all_execution_states()
    with _EXECUTION_CANCEL_LOCK:
        _EXECUTION_CANCEL_FLAGS.clear()
    return {"reset": True}


def run_proposal_execution_in_background(
    environment_key: str,
    history_index: int,
    execution_plan: dict[str, Any],
) -> None:
    reset_cancel_flag(environment_key, history_index)
    execution_state = get_execution_state(environment_key, history_index) or build_execution_state_payload(
        status="running",
        message="Execucao iniciada. Acompanhando a esteira da proposta...",
        flow_config=execution_plan,
    )
    run_started_at = sanitize_text(execution_state.get("startedAt")) or _utc_now_iso()
    run_started_clock = monotonic()
    fallback_run_id = _next_execution_run_id()

    def build_fallback_execution_result(status: str, message: str) -> ProposalExecutionResult:
        return ProposalExecutionResult(
            run_id=fallback_run_id,
            status=status,
            message=message,
            started_at=run_started_at,
            finished_at=_utc_now_iso(),
            duration_ms=_elapsed_ms(run_started_clock),
            total_http_calls=0,
            total_db_checks=0,
            stage_results=[],
        )

    set_execution_state(
        environment_key,
        history_index,
        build_execution_state_payload(
            status="running",
            message=execution_state.get("message") or "Execucao iniciada. Acompanhando a esteira da proposta...",
            flow_config=execution_plan,
            steps=(execution_state.get("steps") or []),
            started_at=run_started_at,
        ),
    )

    try:
        config = get_environment_config(environment_key)
        record = get_history_record(environment_key, history_index)
        if record is None:
            raise WebApiError(
                "Nao foi possivel localizar a proposta selecionada no historico.",
                status_code=HTTPStatus.NOT_FOUND,
                code="proposal_history_not_found",
            )

        api_session = get_cached_api_session(config)
        ensure_api_session_store_context(api_session)
        current_flow = refresh_proposal_flow_record(
            api_session=api_session,
            config_key=config.key,
            history_index=history_index,
            record=record,
            use_retry=True,
        )
        if current_flow is None or not current_flow.stages:
            raise WebApiError(
                "O dashboard ainda nao retornou etapas para esta proposta.",
                status_code=HTTPStatus.NOT_FOUND,
                detail="A proposta foi criada, mas a esteira ainda nao ficou disponivel no dashboard. Tente novamente em alguns instantes.",
                code="proposal_flow_not_available",
            )

        latest_flow, execution = execute_proposal_flow_plan(
            api_session=api_session,
            config_key=config.key,
            environment_key=environment_key,
            history_index=history_index,
            record=record,
            initial_flow=current_flow,
            execution_plan=execution_plan,
        )

        execution_result = execution.get("executionResult")
        if execution_result is None:
            execution_result = build_fallback_execution_result(
                execution.get("status") or "completed",
                execution.get("message") or "Execucao concluida.",
            )

        update_record_flow(config.key, history_index, latest_flow)
        updated_record = append_record_execution(environment_key, history_index, execution_result)
        if updated_record is not None:
            persist_execution_artifact(environment_key, history_index, updated_record, execution_result)

        set_execution_state(
            environment_key,
            history_index,
            build_execution_state_payload(
                status=execution_result.status or execution.get("status") or "completed",
                message=execution_result.message or execution.get("message") or "Execucao concluida.",
                flow_config=execution_plan,
                steps=execution.get("steps") or [],
                started_at=execution_result.started_at,
                finished_at=execution_result.finished_at,
            ),
        )
    except WebApiError as exc:
        execution_result = build_fallback_execution_result("failed", exc.message)
        record = get_history_record(environment_key, history_index)
        if record is not None:
            updated_record = append_record_execution(environment_key, history_index, execution_result)
            if updated_record is not None:
                persist_execution_artifact(environment_key, history_index, updated_record, execution_result)
        set_execution_state(
            environment_key,
            history_index,
            build_execution_state_payload(
                status="failed",
                message=exc.message,
                flow_config=execution_plan,
                steps=(execution_state.get("steps") or []),
                started_at=execution_result.started_at,
                finished_at=execution_result.finished_at,
            ),
        )
    except (ApiAuthenticationError, ApiRequestError) as exc:
        execution_result = build_fallback_execution_result("failed", "Nao foi possivel executar a esteira da proposta.")
        record = get_history_record(environment_key, history_index)
        if record is not None:
            updated_record = append_record_execution(environment_key, history_index, execution_result)
            if updated_record is not None:
                persist_execution_artifact(environment_key, history_index, updated_record, execution_result)
        set_execution_state(
            environment_key,
            history_index,
            build_execution_state_payload(
                status="failed",
                message="Nao foi possivel executar a esteira da proposta.",
                flow_config=execution_plan,
                steps=(execution_state.get("steps") or []),
                started_at=execution_result.started_at,
                finished_at=execution_result.finished_at,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        failure_message = str(exc) or "Falha inesperada ao executar a esteira da proposta."
        execution_result = build_fallback_execution_result("failed", failure_message)
        record = get_history_record(environment_key, history_index)
        if record is not None:
            updated_record = append_record_execution(environment_key, history_index, execution_result)
            if updated_record is not None:
                persist_execution_artifact(environment_key, history_index, updated_record, execution_result)
        set_execution_state(
            environment_key,
            history_index,
            build_execution_state_payload(
                status="failed",
                message=failure_message,
                flow_config=execution_plan,
                steps=(execution_state.get("steps") or []),
                started_at=execution_result.started_at,
                finished_at=execution_result.finished_at,
            ),
        )
    finally:
        reset_cancel_flag(environment_key, history_index)

def ensure_api_session_store_context(api_session: ApiSession) -> None:
    if api_session.store_ids:
        return
    store_ids = fetch_my_stores(api_session)
    api_session.store_ids = store_ids
    api_session.stores_query_string = build_stores_query_string(store_ids)



def fetch_proposal_flow_once(
    *,
    api_session: ApiSession,
    simulation_code: str,
):
    dashboard_response = fetch_proposal_dashboard(
        api_session,
        search=simulation_code,
        store_ids=api_session.store_ids,
    )
    return extract_proposal_flow(dashboard_response)



def refresh_proposal_flow_record(
    *,
    api_session: ApiSession,
    config_key: str,
    history_index: int,
    record,
    use_retry: bool = False,
):
    proposal_flow = (
        fetch_proposal_flow_with_retry(
            api_session=api_session,
            simulation_code=record.simulation_code,
        )
        if use_retry
        else fetch_proposal_flow_once(
            api_session=api_session,
            simulation_code=record.simulation_code,
        )
    )
    update_record_flow(config_key, history_index, proposal_flow)
    return proposal_flow



def fetch_proposal_flow_with_retry(
    *,
    api_session: ApiSession,
    simulation_code: str,
):
    proposal_flow = None
    for attempt in range(PROPOSAL_FLOW_FETCH_ATTEMPTS):
        proposal_flow = fetch_proposal_flow_once(
            api_session=api_session,
            simulation_code=simulation_code,
        )
        if proposal_flow is not None and proposal_flow.stages:
            return proposal_flow
        if attempt < PROPOSAL_FLOW_FETCH_ATTEMPTS - 1:
            sleep(PROPOSAL_FLOW_FETCH_DELAY_SECONDS)
    return proposal_flow



def normalize_execution_action(value: Any) -> str:
    normalized = sanitize_text(value).lower()
    if normalized in {"wait", "manual", "finish"}:
        return normalized
    return "wait"



def normalize_stage_status(value: Any) -> str:
    return sanitize_text(value).upper().replace(" ", "_")



def is_stage_status_success(status: Any) -> bool:
    normalized = normalize_stage_status(status)
    return normalized in {"APPROVED", "SUCCESS", "DONE", "COMPLETED", "COMPLETE", "FINISHED", "OK", "PAID"}



def is_stage_status_failure(status: Any) -> bool:
    normalized = normalize_stage_status(status)
    return normalized in {"FAIL", "FAILED", "ERROR", "REJECTED", "DENIED", "CANCELED", "CANCELLED", "INVALID"}



def is_stage_status_manual(status: Any) -> bool:
    normalized = normalize_stage_status(status)
    return normalized in {"MANUAL", "MANUAL_ANALYSIS", "PENDING_MANUAL"} or "MANUAL" in normalized



def is_stage_status_in_progress(status: Any) -> bool:
    normalized = normalize_stage_status(status)
    return normalized in {"IN_PROGRESS", "PROCESSING", "RUNNING", "STARTED"}



def find_flow_stage(flow, stage_id: str):
    if flow is None:
        return None
    for stage in flow.stages:
        if str(stage.id) == str(stage_id):
            return stage
    return None



def build_flow_execution_plan(
    *,
    record,
    flow,
    flow_config_payload: Any,
) -> dict[str, Any]:
    config_payload = flow_config_payload if isinstance(flow_config_payload, dict) else {}
    payload_proposal_id = sanitize_text(config_payload.get("proposalId"))
    payload_flow_id = sanitize_text(config_payload.get("flowId"))

    proposal_id = payload_proposal_id or sanitize_text(record.proposal_id) or sanitize_text(flow.proposal_id)
    flow_id = payload_flow_id or sanitize_text(flow.flow_id)

    if sanitize_text(record.proposal_id) and proposal_id and proposal_id != sanitize_text(record.proposal_id):
        raise WebApiError(
            "A configuracao enviada nao pertence a proposta selecionada.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="proposal_flow_config_mismatch",
        )
    if sanitize_text(flow.flow_id) and flow_id and flow_id != sanitize_text(flow.flow_id):
        raise WebApiError(
            "A configuracao enviada nao pertence ao fluxo atual da proposta.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="proposal_flow_config_mismatch",
        )

    actions_by_stage_id: dict[str, str] = {}
    stages_payload = config_payload.get("stages") if isinstance(config_payload.get("stages"), list) else []
    for stage_payload in stages_payload:
        if not isinstance(stage_payload, dict):
            continue
        stage_id = sanitize_text(stage_payload.get("stageId") or stage_payload.get("id"))
        if not stage_id:
            continue
        actions_by_stage_id[stage_id] = normalize_execution_action(stage_payload.get("action"))

    return {
        "environment": record.environment_key,
        "historyIndex": config_payload.get("historyIndex") or None,
        "proposalId": proposal_id,
        "proposalCode": sanitize_text(record.proposal_code),
        "contractCode": sanitize_text(record.contract_code),
        "flowId": flow_id,
        "stages": [
            {
                "order": index + 1,
                "stageId": str(stage.id),
                "stageCode": str(stage.code),
                "stageName": str(stage.name),
                "stageStatus": str(stage.status),
                "action": actions_by_stage_id.get(str(stage.id), "wait"),
            }
            for index, stage in enumerate(flow.stages)
        ],
    }



def wait_for_stage_resolution(
    *,
    api_session: ApiSession,
    config_key: str,
    environment_key: str,
    history_index: int,
    record,
    stage_id: str,
    action: str,
    timeout_seconds: float,
    current_flow,
):
    deadline = monotonic() + timeout_seconds
    latest_flow = current_flow
    latest_stage = find_flow_stage(latest_flow, stage_id)

    while True:
        if is_cancelled(environment_key, history_index):
            return latest_flow, latest_stage, "cancelled", "Execucao cancelada pelo usuario."

        if latest_stage is None:
            raise WebApiError(
                "Nao foi possivel localizar a etapa selecionada no dashboard da proposta.",
                status_code=HTTPStatus.NOT_FOUND,
                code="proposal_stage_not_found",
            )

        status = latest_stage.status
        if is_stage_status_success(status):
            return latest_flow, latest_stage, "approved", f"Etapa '{latest_stage.name}' aprovada."
        if is_stage_status_failure(status):
            return latest_flow, latest_stage, "failed", f"Etapa '{latest_stage.name}' retornou status {status}."
        if is_stage_status_manual(status):
            return latest_flow, latest_stage, "manual_pending", f"Etapa '{latest_stage.name}' requer tratamento manual."
        if monotonic() >= deadline:
            if action == "finish":
                message = f"A etapa '{latest_stage.name}' ainda nao ficou APPROVED apos o finish."
                return latest_flow, latest_stage, "finish_timeout", message
            if action == "manual":
                message = f"A etapa '{latest_stage.name}' ainda aguarda andamento manual no sistema."
                return latest_flow, latest_stage, "manual_timeout", message
            message = f"A etapa '{latest_stage.name}' ainda nao foi concluida pelo sistema no tempo esperado."
            return latest_flow, latest_stage, "waiting_timeout", message

        sleep(FLOW_EXECUTION_POLL_INTERVAL_SECONDS)
        latest_flow = refresh_proposal_flow_record(
            api_session=api_session,
            config_key=config_key,
            history_index=history_index,
            record=record,
            use_retry=False,
        )
        latest_stage = find_flow_stage(latest_flow, stage_id)



def map_execution_outcome(outcome: str) -> str:
    if outcome == "approved":
        return "completed"
    if outcome == "cancelled":
        return "cancelled"
    if outcome in {"manual_pending", "manual_timeout"}:
        return "manual_pending"
    if outcome in {"waiting_timeout", "finish_timeout"}:
        return "waiting"
    if outcome == "failed":
        return "failed"
    return "waiting"


def interruptible_sleep(seconds: float, environment_key: str, history_index: int) -> bool:
    """Sleep in small increments, checking for cancellation. Returns True if cancelled."""
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        if is_cancelled(environment_key, history_index):
            return True
        sleep(min(0.5, deadline - monotonic()))
    return False



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _elapsed_ms(start_time: float) -> int:
    return int((monotonic() - start_time) * 1000)



def _next_execution_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")



def _build_stage_step_payload(stage_result: StageExecutionResult) -> dict[str, Any]:
    return {
        "stageId": stage_result.stage_id,
        "stageCode": stage_result.stage_code,
        "stageName": stage_result.stage_name,
        "action": stage_result.configured_action,
        "status": stage_result.final_status,
        "result": stage_result.result,
        "message": stage_result.message,
    }



def _build_execution_result(
    *,
    run_id: str,
    status: str,
    message: str,
    started_at: str,
    started_clock: float,
    stage_results: list[StageExecutionResult],
) -> ProposalExecutionResult:
    total_http_calls = sum(len(stage.http_calls) for stage in stage_results)
    total_db_checks = sum(len(stage.db_checks) for stage in stage_results)
    return ProposalExecutionResult(
        run_id=run_id,
        status=status,
        message=message,
        started_at=started_at,
        finished_at=_utc_now_iso(),
        duration_ms=_elapsed_ms(started_clock),
        total_http_calls=total_http_calls,
        total_db_checks=total_db_checks,
        stage_results=list(stage_results),
    )



def execute_proposal_flow_plan(
    *,
    api_session: ApiSession,
    config_key: str,
    environment_key: str,
    history_index: int,
    record,
    initial_flow,
    execution_plan: dict[str, Any],
):
    latest_flow = initial_flow
    stage_results: list[StageExecutionResult] = []
    proposal_id = sanitize_text(execution_plan.get("proposalId")) or sanitize_text(record.proposal_id)
    flow_id = sanitize_text(execution_plan.get("flowId")) or sanitize_text(latest_flow.flow_id)
    run_started_at = _utc_now_iso()
    run_started_clock = monotonic()
    run_id = _next_execution_run_id()

    # Shared state across stages for Protheus cross-phase validation
    _protheus_correlation_id: str | None = None
    _protheus_last_log_id: int = 0
    _protheus_client_code: str | None = None

    def build_stage_result(
        *,
        stage_id: str,
        stage_code: str,
        stage_name: str,
        configured_action: str,
        initial_status: str,
        final_status: str,
        result: str,
        message: str,
        started_at: str,
        started_clock: float,
        http_calls: list[ExecutionHttpCall],
        db_checks: list[ExecutionDbCheck],
        notes: list[str],
        protheus_validation=None,
    ) -> StageExecutionResult:
        return StageExecutionResult(
            stage_id=stage_id,
            stage_code=stage_code,
            stage_name=stage_name,
            configured_action=configured_action,
            initial_status=initial_status,
            final_status=final_status,
            result=result,
            message=message,
            started_at=started_at,
            finished_at=_utc_now_iso(),
            duration_ms=_elapsed_ms(started_clock),
            http_calls=list(http_calls),
            db_checks=list(db_checks),
            notes=list(notes),
            protheus_validation=protheus_validation,
        )

    def build_terminal_execution(status: str, message: str):
        execution_result = _build_execution_result(
            run_id=run_id,
            status=status,
            message=message,
            started_at=run_started_at,
            started_clock=run_started_clock,
            stage_results=stage_results,
        )
        return {
            "status": status,
            "message": message,
            "steps": [_build_stage_step_payload(stage) for stage in stage_results],
            "executionResult": execution_result,
        }

    def execute_logged_http_call(
        *,
        request_logs: list[ExecutionHttpCall],
        label: str,
        method: str,
        path: str,
        message: str,
        callback,
    ):
        started_at = _utc_now_iso()
        started_clock = monotonic()
        try:
            payload = callback()
            request_logs.append(
                ExecutionHttpCall(
                    timestamp=started_at,
                    label=label,
                    method=method,
                    path=path,
                    status_code=200,
                    duration_ms=_elapsed_ms(started_clock),
                    correlation_id=sanitize_text((payload or {}).get("correlation_id")) if isinstance(payload, dict) else "",
                    message=message,
                )
            )
            return payload
        except ApiRequestError as exc:
            details = getattr(exc, "details", None)
            request_logs.append(
                ExecutionHttpCall(
                    timestamp=started_at,
                    label=label,
                    method=method,
                    path=path,
                    status_code=(details.status_code if details else None),
                    duration_ms=_elapsed_ms(started_clock),
                    correlation_id=(details.correlation_id if details else ""),
                    message=(details.api_message if details and details.api_message else str(exc)),
                )
            )
            raise

    def execute_logged_db_check(
        *,
        db_logs: list[ExecutionDbCheck],
        label: str,
        query_name: str,
        query_sql: str = "",
        callback,
        matched_message: str,
        not_matched_message: str,
    ) -> bool:
        started_at = _utc_now_iso()
        started_clock = monotonic()
        try:
            matched = bool(callback())
            db_logs.append(
                ExecutionDbCheck(
                    timestamp=started_at,
                    label=label,
                    query_name=query_name,
                    duration_ms=_elapsed_ms(started_clock),
                    matched=matched,
                    message=matched_message if matched else not_matched_message,
                    query_sql=query_sql,
                )
            )
            return matched
        except Exception as exc:  # noqa: BLE001
            db_logs.append(
                ExecutionDbCheck(
                    timestamp=started_at,
                    label=label,
                    query_name=query_name,
                    duration_ms=_elapsed_ms(started_clock),
                    matched=None,
                    message=str(exc),
                    query_sql=query_sql,
                )
            )
            raise

    def collect_wait_external_validation_failures(
        *,
        stage_name: str,
        action: str,
        db_logs: list[ExecutionDbCheck],
        protheus_validation,
    ) -> list[str]:
        if action != "wait":
            return []

        failures: list[str] = []

        # Consider only the latest result by query/check name to avoid false negatives
        # from intermediate polling attempts.
        latest_db_results: dict[str, ExecutionDbCheck] = {}
        for check in db_logs:
            key = sanitize_text(check.query_name or check.label or "db_check")
            latest_db_results[key] = check

        for key, check in latest_db_results.items():
            if check.matched is True:
                continue
            reason = sanitize_text(check.message) or "Validacao de banco sem retorno positivo."
            failures.append(f"DB {key}: {reason}")

        if (
            protheus_validation is not None
            and not protheus_validation.valid
            and not protheus_validation.bypassed
        ):
            failures.append(f"Protheus: {sanitize_text(protheus_validation.message)}")

        return failures

    def refresh_flow_with_log(
        *,
        request_logs: list[ExecutionHttpCall],
        label: str,
        message: str,
    ):
        dashboard_response = execute_logged_http_call(
            request_logs=request_logs,
            label=label,
            method="GET",
            path="/admin/proposal/dashboard",
            message=message,
            callback=lambda: fetch_proposal_dashboard(
                api_session,
                search=record.simulation_code,
                store_ids=api_session.store_ids,
            ),
        )
        proposal_flow = extract_proposal_flow(dashboard_response)
        update_record_flow(config_key, history_index, proposal_flow)
        return proposal_flow

    def wait_for_stage_resolution_logged(
        *,
        stage_id: str,
        stage_name: str,
        action: str,
        timeout_seconds: float,
        current_flow,
        request_logs: list[ExecutionHttpCall],
    ):
        deadline = monotonic() + timeout_seconds
        polled_flow = current_flow
        polled_stage = find_flow_stage(polled_flow, stage_id)

        while True:
            if is_cancelled(environment_key, history_index):
                return polled_flow, polled_stage, "cancelled", "Execucao cancelada pelo usuario."

            if polled_stage is None:
                raise WebApiError(
                    "Nao foi possivel localizar a etapa selecionada no dashboard da proposta.",
                    status_code=HTTPStatus.NOT_FOUND,
                    code="proposal_stage_not_found",
                )

            status = polled_stage.status
            if is_stage_status_success(status):
                return polled_flow, polled_stage, "approved", f"Etapa '{stage_name}' aprovada."
            if is_stage_status_failure(status):
                return polled_flow, polled_stage, "failed", f"Etapa '{stage_name}' retornou status {status}."
            if is_stage_status_manual(status):
                return polled_flow, polled_stage, "manual_pending", f"Etapa '{stage_name}' requer tratamento manual."
            if monotonic() >= deadline:
                if action == "finish":
                    return polled_flow, polled_stage, "finish_timeout", f"A etapa '{stage_name}' ainda nao ficou APPROVED apos o finish."
                if action == "manual":
                    return polled_flow, polled_stage, "manual_timeout", f"A etapa '{stage_name}' ainda aguarda andamento manual no sistema."
                return polled_flow, polled_stage, "waiting_timeout", f"A etapa '{stage_name}' ainda nao foi concluida pelo sistema no tempo esperado."

            if interruptible_sleep(FLOW_EXECUTION_POLL_INTERVAL_SECONDS, environment_key, history_index):
                return polled_flow, polled_stage, "cancelled", "Execucao cancelada pelo usuario."

            polled_flow = refresh_flow_with_log(
                request_logs=request_logs,
                label="dashboard_poll",
                message=f"Dashboard consultado para acompanhar a etapa '{stage_name}'.",
            )
            polled_stage = find_flow_stage(polled_flow, stage_id)

    for stage_plan in execution_plan.get("stages") or []:
        if is_cancelled(environment_key, history_index):
            return latest_flow, build_terminal_execution("cancelled", "Execucao cancelada pelo usuario.")

        stage_id = sanitize_text(stage_plan.get("stageId"))
        action = normalize_execution_action(stage_plan.get("action"))
        latest_stage = find_flow_stage(latest_flow, stage_id)
        if latest_stage is None:
            raise WebApiError(
                "Nao foi possivel localizar uma das etapas configuradas na esteira atual.",
                status_code=HTTPStatus.NOT_FOUND,
                code="proposal_stage_not_found",
            )

        stage_code = sanitize_text(stage_plan.get("stageCode")).lower()
        stage_name = sanitize_text(stage_plan.get("stageName")) or latest_stage.name
        initial_status = str(latest_stage.status)
        stage_started_at = _utc_now_iso()
        stage_started_clock = monotonic()
        stage_http_calls: list[ExecutionHttpCall] = []
        stage_db_checks: list[ExecutionDbCheck] = []
        stage_notes: list[str] = []

        if is_stage_status_success(latest_stage.status):
            stage_result = build_stage_result(
                stage_id=stage_id,
                stage_code=stage_code,
                stage_name=stage_name,
                configured_action=action,
                initial_status=initial_status,
                final_status=str(latest_stage.status),
                result="already_approved",
                message=f"Etapa '{stage_name}' ja estava aprovada.",
                started_at=stage_started_at,
                started_clock=stage_started_clock,
                http_calls=stage_http_calls,
                db_checks=stage_db_checks,
                notes=stage_notes,
            )
            stage_results.append(stage_result)
            continue

        outcome = ""
        message = ""

        try:
            is_payment_manual = stage_code == "payment" and action == "manual"
            is_credit_finish = stage_code == "ibratan" and action == "finish"
            is_unico_id_finish = stage_code == "unico-id-check" and action == "finish"
            is_cte_finish = stage_code == "cte" and action == "finish"
            is_avb_finish = stage_code == "avbdataprev" and action == "finish"

            if is_payment_manual:
                stage_notes.append("Fluxo especial de pagamento manual iniciado.")
                execute_logged_http_call(
                    request_logs=stage_http_calls,
                    label="payment_assume",
                    method="PUT",
                    path=f"/admin/proposal/{proposal_id}/flow/{flow_id}/stage/{stage_id}/payment/assume",
                    message=f"Etapa '{stage_name}' assumida para processamento manual de pagamento.",
                    callback=lambda: assume_payment_stage(
                        api_session,
                        proposal_id=proposal_id,
                        flow_id=flow_id,
                        stage_id=stage_id,
                    ),
                )
                latest_flow = refresh_flow_with_log(
                    request_logs=stage_http_calls,
                    label="dashboard_after_assume",
                    message=f"Dashboard atualizado apos assumir a etapa '{stage_name}'.",
                )
                if interruptible_sleep(PAYMENT_ASSUME_SETTLE_SECONDS, environment_key, history_index):
                    outcome = "cancelled"
                    message = "Execucao cancelada pelo usuario."
                else:
                    stage_notes.append(f"Aguardou {int(PAYMENT_ASSUME_SETTLE_SECONDS)}s antes de finalizar o pagamento.")
                    execute_logged_http_call(
                        request_logs=stage_http_calls,
                        label="payment_finish",
                        method="PUT",
                        path=f"/admin/proposal/{proposal_id}/flow/{flow_id}/stage/{stage_id}/payment/finish",
                        message=f"Etapa '{stage_name}' finalizada pelo endpoint de pagamento.",
                        callback=lambda: finish_payment_stage(
                            api_session,
                            proposal_id=proposal_id,
                            flow_id=flow_id,
                            stage_id=stage_id,
                        ),
                    )
                    latest_flow = refresh_flow_with_log(
                        request_logs=stage_http_calls,
                        label="dashboard_after_payment_finish",
                        message=f"Dashboard atualizado apos finalizar a etapa '{stage_name}'.",
                    )
                    latest_flow, latest_stage, outcome, message = wait_for_stage_resolution_logged(
                        stage_id=stage_id,
                        stage_name=stage_name,
                        action="finish",
                        timeout_seconds=FLOW_EXECUTION_WAIT_TIMEOUT_SECONDS,
                        current_flow=latest_flow,
                        request_logs=stage_http_calls,
                    )

            elif is_unico_id_finish:
                stage_notes.append("Aguardando identificador do processo Unico no banco antes do finish.")
                config = get_environment_config(config_key)
                deadline = monotonic() + UNICO_ID_DB_POLL_TIMEOUT_SECONDS
                unico_ready = False
                while monotonic() < deadline:
                    if is_cancelled(environment_key, history_index):
                        outcome = "cancelled"
                        message = "Execucao cancelada pelo usuario."
                        break
                    unico_ready = execute_logged_db_check(
                        db_logs=stage_db_checks,
                        label="unico_id_ready",
                        query_name="unico_id_cloud_process_proposals",
                        query_sql=(
                            "SELECT unico_id_cloud_process_id"
                            " FROM unico_id_cloud_process_proposals"
                            f" WHERE proposal_id = '{proposal_id}'"
                            " LIMIT 1"
                        ),
                        callback=lambda: check_unico_id_ready(config, proposal_id),
                        matched_message="Registro do processo Unico localizado no banco.",
                        not_matched_message="Processo Unico ainda nao disponivel no banco.",
                    )
                    if unico_ready:
                        break
                    if interruptible_sleep(UNICO_ID_DB_POLL_INTERVAL_SECONDS, environment_key, history_index):
                        outcome = "cancelled"
                        message = "Execucao cancelada pelo usuario."
                        break

                if not outcome:
                    if not unico_ready:
                        outcome = "waiting_timeout"
                        message = f"A etapa '{stage_name}' nao foi iniciada pelo sistema no tempo esperado (unico_id_cloud_process_id nao encontrado)."
                    else:
                        execute_logged_http_call(
                            request_logs=stage_http_calls,
                            label="stage_finish",
                            method="PUT",
                            path=f"/admin/proposal/{proposal_id}/flow/{flow_id}/stage/{stage_id}/finish",
                            message=f"Etapa '{stage_name}' finalizada automaticamente via finish.",
                            callback=lambda: finish_proposal_stage(
                                api_session,
                                proposal_id=proposal_id,
                                flow_id=flow_id,
                                stage_id=stage_id,
                                comments="approved",
                            ),
                        )
                        latest_flow = refresh_flow_with_log(
                            request_logs=stage_http_calls,
                            label="dashboard_after_finish",
                            message=f"Dashboard atualizado apos o finish da etapa '{stage_name}'.",
                        )
                        latest_flow, latest_stage, outcome, message = wait_for_stage_resolution_logged(
                            stage_id=stage_id,
                            stage_name=stage_name,
                            action="finish",
                            timeout_seconds=FLOW_FINISH_APPROVAL_TIMEOUT_SECONDS,
                            current_flow=latest_flow,
                            request_logs=stage_http_calls,
                        )

            elif action == "finish":
                if is_credit_finish or is_cte_finish:
                    stage_notes.append(f"Aguardou {int(STAGE_PRE_FINISH_DELAY_SECONDS)}s antes do finish para respeitar o processamento do backend.")
                    if interruptible_sleep(STAGE_PRE_FINISH_DELAY_SECONDS, environment_key, history_index):
                        outcome = "cancelled"
                        message = "Execucao cancelada pelo usuario."
                elif is_avb_finish:
                    stage_notes.append(f"Aguardou {int(STAGE_PRE_FINISH_DELAY_AVB_SECONDS)}s antes do finish para aguardar processamento da averbacao.")
                    if interruptible_sleep(STAGE_PRE_FINISH_DELAY_AVB_SECONDS, environment_key, history_index):
                        outcome = "cancelled"
                        message = "Execucao cancelada pelo usuario."
                if not outcome:
                    execute_logged_http_call(
                        request_logs=stage_http_calls,
                        label="stage_finish",
                        method="PUT",
                        path=f"/admin/proposal/{proposal_id}/flow/{flow_id}/stage/{stage_id}/finish",
                        message=f"Etapa '{stage_name}' finalizada automaticamente via finish.",
                        callback=lambda: finish_proposal_stage(
                            api_session,
                            proposal_id=proposal_id,
                            flow_id=flow_id,
                            stage_id=stage_id,
                            comments="approved",
                        ),
                    )
                    latest_flow = refresh_flow_with_log(
                        request_logs=stage_http_calls,
                        label="dashboard_after_finish",
                        message=f"Dashboard atualizado apos o finish da etapa '{stage_name}'.",
                    )
                    latest_flow, latest_stage, outcome, message = wait_for_stage_resolution_logged(
                        stage_id=stage_id,
                        stage_name=stage_name,
                        action="finish",
                        timeout_seconds=FLOW_FINISH_APPROVAL_TIMEOUT_SECONDS,
                        current_flow=latest_flow,
                        request_logs=stage_http_calls,
                    )

            else:
                latest_flow, latest_stage, outcome, message = wait_for_stage_resolution_logged(
                    stage_id=stage_id,
                    stage_name=stage_name,
                    action=action,
                    timeout_seconds=FLOW_EXECUTION_WAIT_TIMEOUT_SECONDS,
                    current_flow=latest_flow,
                    request_logs=stage_http_calls,
                )

        except WebApiError as exc:
            failed_stage = build_stage_result(
                stage_id=stage_id,
                stage_code=stage_code,
                stage_name=stage_name,
                configured_action=action,
                initial_status=initial_status,
                final_status=str(latest_stage.status if latest_stage else initial_status),
                result="error",
                message=exc.message,
                started_at=stage_started_at,
                started_clock=stage_started_clock,
                http_calls=stage_http_calls,
                db_checks=stage_db_checks,
                notes=stage_notes,
            )
            stage_results.append(failed_stage)
            return latest_flow, build_terminal_execution("failed", exc.message)

        final_status = str(latest_stage.status if latest_stage else initial_status)

        # ------------------------------------------------------------------
        # CCB integration validation (contract_integration stage)
        # ------------------------------------------------------------------
        if stage_code == "contract_integration" and outcome == "approved":
            contract_code = sanitize_text(record.contract_code)
            if contract_code:
                stage_notes.append("Validacao de integracao CCB iniciada apos aprovacao da etapa contract_integration.")
                config = get_environment_config(config_key)
                deadline = monotonic() + CCB_VALIDATION_POLL_TIMEOUT_SECONDS
                ccb_found = False
                while monotonic() < deadline:
                    ccb_found = execute_logged_db_check(
                        db_logs=stage_db_checks,
                        label="ccb_validation",
                        query_name="ccbs",
                        query_sql=f"SELECT 1 FROM ccbs WHERE code = '{contract_code}' LIMIT 1",
                        callback=lambda: check_ccb_exists(config, contract_code),
                        matched_message=f"CCB '{contract_code}' encontrada na tabela ccbs.",
                        not_matched_message=f"CCB '{contract_code}' ainda nao encontrada na tabela ccbs.",
                    )
                    if ccb_found:
                        break
                    if interruptible_sleep(CCB_VALIDATION_POLL_INTERVAL_SECONDS, environment_key, history_index):
                        outcome = "cancelled"
                        final_status = "CANCELLED"
                        message = "Execucao cancelada pelo usuario durante a validacao CCB."
                        break

                if outcome == "approved":
                    if ccb_found:
                        stage_notes.append(f"CCB '{contract_code}' encontrada na tabela ccbs.")
                        message = f"{message} CCB '{contract_code}' encontrada na tabela ccbs."
                    else:
                        outcome = "failed"
                        final_status = "CCB_NOT_FOUND"
                        message = f"A proposta foi aprovada na esteira, mas a CCB '{contract_code}' nao foi encontrada no banco."

        # ------------------------------------------------------------------
        # Protheus validation (protheus / protheus-issuance stages, action=wait)
        # ------------------------------------------------------------------
        protheus_validation_result = None

        is_protheus_wait = stage_code in ("protheus", "protheus-issuance") and action == "wait"
        if is_protheus_wait and outcome in ("approved", "waiting_timeout"):
            config = get_environment_config(config_key)
            client_cpf = sanitize_digits(record.client_document)
            proposal_code = sanitize_text(record.proposal_code) or sanitize_text(record.simulation_code)

            # Fetch correlation_id once (shared between both protheus stages)
            if _protheus_correlation_id is None:
                _protheus_correlation_id = fetch_proposal_correlation_id(config, proposal_code) or ""

            if not _protheus_correlation_id:
                stage_notes.append("Validacao Protheus ignorada: correlation_id nao encontrado para a proposta.")
            else:
                stage_notes.append(f"Iniciando validacao Protheus ({stage_code}) com {PROTHEUS_VALIDATION_RETRIES} tentativas.")
                for attempt in range(1, PROTHEUS_VALIDATION_RETRIES + 1):
                    if is_cancelled(environment_key, history_index):
                        break

                    if stage_code == "protheus":
                        pv_result, last_id, client_code = validate_protheus_formalization(
                            config=config,
                            correlation_id=_protheus_correlation_id,
                            cpf=client_cpf,
                        )
                        if pv_result.valid or attempt == PROTHEUS_VALIDATION_RETRIES:
                            _protheus_last_log_id = last_id
                            _protheus_client_code = client_code
                            protheus_validation_result = pv_result
                            break
                    else:
                        stage_approved = is_stage_status_success(final_status)
                        pv_result = validate_protheus_issuance(
                            config=config,
                            correlation_id=_protheus_correlation_id,
                            proposal_id=proposal_id,
                            codigo_criacao=proposal_code,
                            cpf=client_cpf,
                            last_protheus_id=_protheus_last_log_id,
                            stage_already_approved=stage_approved,
                            protheus_client_code=_protheus_client_code,
                        )
                        if pv_result.valid or pv_result.bypassed or attempt == PROTHEUS_VALIDATION_RETRIES:
                            protheus_validation_result = pv_result
                            break

                    if attempt < PROTHEUS_VALIDATION_RETRIES:
                        if interruptible_sleep(PROTHEUS_VALIDATION_RETRY_INTERVAL_SECONDS, environment_key, history_index):
                            break

                if protheus_validation_result is not None:
                    stage_notes.append(
                        f"CPF principal (main document) usado na validacao Protheus: {mask_value(client_cpf)}."
                    )
                    if not protheus_validation_result.valid and not protheus_validation_result.bypassed:
                        stage_notes.append(f"Validacao Protheus FALHOU: {protheus_validation_result.message}")
                    else:
                        stage_notes.append(f"Validacao Protheus OK: {protheus_validation_result.message}")

                    ai_commentary = generate_ai_commentary_for_protheus_stage(
                        environment_label=ENVIRONMENT_OPTIONS.get(config.key, config.key),
                        proposal_code=sanitize_text(record.proposal_code),
                        stage_code=stage_code,
                        stage_name=stage_name,
                        main_document=client_cpf,
                        validation_message=protheus_validation_result.message,
                        checks=protheus_validation_result.checks,
                    )
                    if ai_commentary:
                        protheus_validation_result.checks.append(
                            ProtheusCheckItem(
                                label="Comentario IA da etapa",
                                source_type="SYSTEM",
                                origin="AI - Comentario da etapa",
                                result=None,
                                message=ai_commentary,
                                http_verb="AI",
                                url="openai://chat/completions",
                            )
                        )

        wait_external_failures = collect_wait_external_validation_failures(
            stage_name=stage_name,
            action=action,
            db_logs=stage_db_checks,
            protheus_validation=protheus_validation_result,
        )
        if wait_external_failures:
            failure_summary = " | ".join(wait_external_failures)
            stage_notes.append(
                f"Falha de validacao externa detectada para etapa configurada como AGUARDAR: {failure_summary}"
            )
            message = (
                f"{message} Falha de validacao externa: {failure_summary}"
                if sanitize_text(message)
                else f"Falha de validacao externa: {failure_summary}"
            )
            if outcome != "failed" and outcome != "cancelled":
                outcome = "failed"
                final_status = "EXTERNAL_VALIDATION_FAILED"

        stage_result = build_stage_result(
            stage_id=stage_id,
            stage_code=stage_code,
            stage_name=stage_name,
            configured_action=action,
            initial_status=initial_status,
            final_status=final_status,
            result=outcome,
            message=message,
            started_at=stage_started_at,
            started_clock=stage_started_clock,
            http_calls=stage_http_calls,
            db_checks=stage_db_checks,
            notes=stage_notes,
            protheus_validation=protheus_validation_result,
        )
        stage_results.append(stage_result)

        if outcome != "approved":
            return latest_flow, build_terminal_execution(map_execution_outcome(outcome), message)

    return latest_flow, build_terminal_execution(
        "completed",
        "As etapas configuradas para esta proposta foram processadas. Revise os detalhes para analisar os resultados.",
    )


def _serialize_flow(flow) -> dict[str, Any] | None:
    if flow is None:
        return None
    return {
        "proposalId": flow.proposal_id,
        "flowId": flow.flow_id,
        "stages": [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "status": s.status,
            }
            for s in flow.stages
        ],
    }


def handle_connect_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))

    try:
        invalidate_cached_session(config.key)
        api_session = get_cached_api_session(config)
        test_connection(config)
    except ApiAuthenticationError as exc:
        invalidate_cached_session(config.key)
        raise WebApiError(
            "Nao foi possivel autenticar na API do ambiente selecionado.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="auth_failed",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise WebApiError(
            "Nao foi possivel acessar o banco de dados do ambiente selecionado.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="database_unavailable",
        ) from exc

    try:
        store_ids = fetch_my_stores(api_session)
        api_session.store_ids = store_ids
        api_session.stores_query_string = build_stores_query_string(store_ids)
    except ApiRequestError as exc:
        raise WebApiError(
            "Nao foi possivel consultar as lojas do usuario autenticado.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="stores_fetch_failed",
        ) from exc

    with ThreadPoolExecutor(max_workers=4) as executor:
        f_agreements = executor.submit(fetch_agreements, config)
        f_products = executor.submit(fetch_products, config)
        f_modalities = executor.submit(fetch_sale_modalities, config)
        f_withdraw_types = executor.submit(fetch_withdraw_types, config)

    Thread(target=_prewarm_sheets, daemon=True).start()

    return {
        "environment": {"key": config.key, "label": config.label},
        "agreements": [asdict(item) for item in f_agreements.result()],
        "products": [asdict(item) for item in f_products.result()],
        "saleModalities": [asdict(item) for item in f_modalities.result()],
        "withdrawTypes": [asdict(item) for item in f_withdraw_types.result()],
    }



def handle_preview_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    agreement_id = require_text(payload, "agreementId")
    product_id = require_text(payload, "productId")
    sheet_record_index = parse_sheet_record_index(payload.get("sheetRecordIndex"))

    try:
        api_session = get_cached_api_session(config)
        processor_code = fetch_agreement_processor_code(api_session, agreement_id)
        product = find_item_by_id(fetch_products(config), product_id, "produto")
        sheet_record = load_sheet_record_for_product(processor_code, product.name, record_index=sheet_record_index)
    except ApiAuthenticationError as exc:
        raise WebApiError(
            "Nao foi possivel autenticar na API para carregar o contexto do convenio.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="auth_failed",
        ) from exc
    except (ApiRequestError, GoogleSheetsError, WebApiError) as exc:
        if isinstance(exc, WebApiError):
            raise
        raise WebApiError(
            "Nao foi possivel montar a previa do convenio selecionado.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="preview_failed",
        ) from exc

    return {
        "processorCode": processor_code,
        "record": serialize_sheet_record(sheet_record),
    }



def handle_simulate_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    agreement_id = require_text(payload, "agreementId")
    product_id = require_text(payload, "productId")
    sale_modality_id = require_text(payload, "saleModalityId")
    withdraw_type_id = require_text(payload, "withdrawTypeId")
    sheet_record_index = parse_sheet_record_index(payload.get("sheetRecordIndex"))

    warnings: list[str] = []

    try:
        api_session = get_cached_api_session(config)
        processor_code = fetch_agreement_processor_code(api_session, agreement_id)
    except (ApiAuthenticationError, ApiRequestError) as exc:
        raise WebApiError(
            "Nao foi possivel preparar a simulacao para o convenio informado.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="context_load_failed",
        ) from exc

    product = find_item_by_id(fetch_products(config), product_id, "produto")
    sale_modality = find_item_by_id(fetch_sale_modalities(config), sale_modality_id, "modalidade")
    sheet_record = load_sheet_record_for_product(processor_code, product.name, record_index=sheet_record_index)

    client_name = sanitize_text(payload.get("clientName"))
    client_document = sanitize_digits(payload.get("clientDocument") or sheet_record.cpf)
    client_phone = sanitize_digits(payload.get("clientPhone"))

    if not client_name:
        raise WebApiError(
            "Informe o nome do cliente antes de gerar a simulacao.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="missing_client_name",
        )
    if not client_document:
        raise WebApiError(
            "Nao foi possivel identificar o documento do cliente.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="missing_client_document",
        )
    if not client_phone:
        raise WebApiError(
            "Informe ou gere um telefone para o cliente antes de continuar.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="missing_client_phone",
        )

    selected_margin_value: str | int = sheet_record.balance_value
    selected_benefit_number = sanitize_text(payload.get("benefitNumber")) or sheet_record.matricula
    selected_user_password = sanitize_text(payload.get("userPassword"))
    if is_zetra_processor(processor_code) and not selected_user_password:
        selected_user_password = sheet_record.senha
    selected_sponsor_benefit_number = sanitize_text(payload.get("sponsorBenefitNumber"))
    selected_cip_agency_id = (
        "1" if is_cip_processor(processor_code) and config.key == "HOMOLOG"
        else sanitize_text(payload.get("cipAgencyId"))
    )
    selected_serpro_identifiers = None

    if is_dataprev_processor(processor_code):
        (
            selected_margin_value,
            selected_benefit_number,
            dataprev_warning,
        ) = resolve_dataprev_context(
            api_session=api_session,
            product=product,
            client_name=client_name,
            client_document=client_document,
            fallback_margin_value=selected_margin_value,
            fallback_benefit_number=selected_benefit_number,
        )
        if dataprev_warning:
            warnings.append(dataprev_warning)

    if is_zetra_processor(processor_code) and not selected_benefit_number:
        raise WebApiError(
            "A processadora Zetra exige a matricula/beneficio para a simulacao.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="missing_benefit_number",
        )

    if is_serpro_processor(processor_code):
        (
            selected_serpro_identifiers,
            serpro_margin_value,
            selected_benefit_number,
            selected_sponsor_benefit_number,
            serpro_warning,
        ) = resolve_serpro_context(
            api_session=api_session,
            agreement_id=agreement_id,
            product=product,
            client_name=client_name,
            client_document=client_document,
            fallback_benefit_number=selected_benefit_number,
            fallback_sponsor_benefit_number=selected_sponsor_benefit_number,
            manual_agency_id=sanitize_text(payload.get("serproAgencyId")),
            manual_agency_sub_id=sanitize_text(payload.get("serproAgencySubId")),
            manual_agency_sub_upag_id=sanitize_text(payload.get("serproAgencySubUpagId")),
        )
        if serpro_margin_value:
            selected_margin_value = serpro_margin_value
        if serpro_warning:
            warnings.append(serpro_warning)

    if is_cip_processor(processor_code):
        (
            selected_margin_value,
            selected_benefit_number,
            selected_cip_agency_id,
            cip_warning,
        ) = resolve_cip_context(
            api_session=api_session,
            agreement_id=agreement_id,
            product=product,
            withdraw_type_id=withdraw_type_id,
            client_name=client_name,
            client_document=client_document,
            fallback_margin_value=selected_margin_value,
            fallback_benefit_number=selected_benefit_number,
            fallback_cip_agency_id=selected_cip_agency_id,
            allow_cip_fallback=bool(payload.get("allowCipFallback", True)),
        )
        if cip_warning:
            warnings.append(cip_warning)

    original_ccb_code = sanitize_text(payload.get("originalCcbCode"))
    original_ccb_origin = sanitize_text(payload.get("originalCcbOrigin"))
    if sale_modality_requires_original_ccb(sale_modality.name):
        if not original_ccb_code or not original_ccb_origin:
            raise WebApiError(
                "Essa modalidade exige original_ccb_code e original_ccb_origin.",
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="missing_original_ccb",
            )

    simulation_input = SimulationPayloadInput(
        agreement_id=agreement_id,
        product_id=product_id,
        sale_modality_id=sale_modality_id,
        withdraw_type_id=withdraw_type_id,
        processor_code=processor_code,
        margin_value=selected_margin_value,
        client=SimulationClient(
            name=client_name,
            document=client_document,
            phone=client_phone,
        ),
        benefit_number=selected_benefit_number,
        user_password=selected_user_password,
        sponsor_benefit_number=selected_sponsor_benefit_number,
        original_ccb_code=original_ccb_code,
        original_ccb_origin=original_ccb_origin,
        serpro_identifiers=selected_serpro_identifiers,
        cip_agency_id=selected_cip_agency_id,
    )

    try:
        simulation_payload = build_simulation_payload(simulation_input)
    except SimulationPayloadError as exc:
        raise WebApiError(
            "Nao foi possivel montar o payload da simulacao.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
            code="payload_invalid",
        ) from exc

    try:
        simulation_response = create_simulation(api_session, simulation_payload)
    except ApiRequestError as exc:
        raise WebApiError(
            "A API nao conseguiu concluir a simulacao.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=f"{describe_api_error(exc)}\n{exc}",
            code="simulation_failed",
        ) from exc

    data = simulation_response.get("data") or {}
    return {
        "processorCode": processor_code,
        "warnings": warnings,
        "record": serialize_sheet_record(sheet_record),
        "summary": {
            "id": data.get("id"),
            "code": data.get("code"),
            "requestedValue": data.get("requested_value"),
            "installmentValue": data.get("installment_value"),
            "deadline": data.get("deadline"),
            "marginValue": data.get("margin_value"),
            "agreementId": data.get("agreement_id"),
            "productId": data.get("product_id"),
        },
        "raw": simulation_response,
    }



def handle_proposal_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    simulation_data = payload.get("simulationData")
    if not isinstance(simulation_data, dict):
        raise WebApiError(
            "A proposta precisa da simulacao concluida para continuar.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="missing_simulation_context",
        )

    agreement_id = require_text(payload, "agreementId")
    client_name = require_text(payload, "clientName")
    client_document = sanitize_digits(payload.get("clientDocument"))
    client_phone = sanitize_digits(payload.get("clientPhone"))
    benefit_number = sanitize_text(payload.get("benefitNumber"))

    simulation_id = sanitize_text(simulation_data.get("id"))
    simulation_code = sanitize_text(simulation_data.get("code"))
    client_id = sanitize_text(simulation_data.get("client_id"))

    if not simulation_id or not simulation_code or not client_id:
        raise WebApiError(
            "A simulacao atual nao trouxe os identificadores minimos para gerar a proposta.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_simulation_context",
        )
    if not client_document:
        raise WebApiError(
            "Nao foi possivel identificar o CPF principal do cliente para a proposta.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="missing_client_document",
        )
    if not client_phone:
        raise WebApiError(
            "Informe ou gere um telefone antes de emitir a proposta.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="missing_client_phone",
        )

    fake_data_service = FakeDataService()

    try:
        api_session = get_cached_api_session(config)
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_catalogs = executor.submit(fetch_proposal_catalogs_for_web, api_session)
            f_client = executor.submit(get_client, api_session, client_id)
        proposal_catalogs = f_catalogs.result()
        proposal_client_data = f_client.result()
        main_document_id = extract_main_document_id(proposal_client_data, client_document)
        proposal_benefit_data = select_client_benefit_data(
            proposal_client_data,
            agreement_id=agreement_id,
            benefit_number=benefit_number,
            main_document_number=client_document,
        )
    except ApiAuthenticationError as exc:
        raise WebApiError(
            "Nao foi possivel autenticar na API para emitir a proposta.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="auth_failed",
        ) from exc
    except ApiRequestError as exc:
        raise WebApiError(
            "Nao foi possivel buscar os dados necessarios da proposta.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=format_web_error_detail(exc),
            code="proposal_context_failed",
        ) from exc
    except ProposalPayloadError as exc:
        raise WebApiError(
            "Nao foi possivel identificar os dados base do cliente para a proposta.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
            code="proposal_payload_base_invalid",
        ) from exc

    generated = build_generated_proposal_client_data_for_web(
        fake_data_service=fake_data_service,
        client_name=client_name,
        client_phone=client_phone,
        main_document_number=client_document,
        state_code=proposal_catalogs.state_code,
    )

    try:
        complete_client_payload = build_complete_client_payload(
            client_data=proposal_client_data,
            client_name=client_name,
            agreement_id=agreement_id,
            main_document_id=main_document_id,
            main_document_number=client_document,
            benefit_data=proposal_benefit_data,
            fallback_benefit_number=benefit_number,
            catalogs=proposal_catalogs,
            generated=generated,
        )
        updated_client_response = update_client(
            api_session=api_session,
            client_id=client_id,
            payload=complete_client_payload,
        )
        refreshed_client_data = extract_response_data_dict(updated_client_response)
        if refreshed_client_data is None:
            refreshed_client_data = get_client(api_session, client_id)
        proposal_identifiers = extract_related_client_ids(
            refreshed_client_data,
            main_document_number=client_document,
            contract_document_type=generated.contract_document_type,
            contract_document_number=generated.contract_document_number,
        )
        proposal_payload = build_proposal_payload(
            simulation_id=simulation_id,
            simulation_code=simulation_code,
            identifiers=proposal_identifiers,
            income_value=generated.income_value,
        )
        proposal_response = create_proposal(api_session, proposal_payload)
    except ApiRequestError as exc:
        raise WebApiError(
            "A API nao conseguiu concluir a emissao da proposta.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=format_web_error_detail(exc),
            code="proposal_failed",
        ) from exc
    except ProposalPayloadError as exc:
        raise WebApiError(
            "Nao foi possivel montar os identificadores finais da proposta.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
            code="proposal_payload_invalid",
        ) from exc

    proposal_data = proposal_response.get("data") or {}

    proposal_flow = None
    try:
        dashboard_response = fetch_proposal_dashboard(
            api_session,
            search=simulation_code,
            store_ids=api_session.store_ids,
        )
        proposal_flow = extract_proposal_flow(dashboard_response)
    except Exception:  # noqa: BLE001
        pass

    history_index = record_proposal(build_proposal_record(
        environment_key=config.key,
        agreement_id=agreement_id,
        product_id=sanitize_text(simulation_data.get("product_id")),
        sale_modality_id=sanitize_text(simulation_data.get("sale_modality_id")),
        withdraw_type_id=sanitize_text(simulation_data.get("withdraw_type_id")),
        processor_code=sanitize_text(payload.get("processorCode")),
        client_name=client_name,
        client_document=client_document,
        client_phone=client_phone,
        benefit_number=benefit_number,
        simulation_id=simulation_id,
        simulation_code=simulation_code,
        client_id=client_id,
        contract_document_type=generated.contract_document_type,
        contract_document_number=generated.contract_document_number,
        email=generated.email,
        simulation_response=simulation_data,
        proposal_response=proposal_response,
        flow=proposal_flow,
    ))

    return {
        "summary": {
            "id": proposal_data.get("id"),
            "code": proposal_data.get("simulation_code") or simulation_code,
            "contractCode": proposal_data.get("code"),
            "requestedValue": proposal_data.get("requested_value"),
            "clientName": proposal_data.get("full_name"),
            "simulationCode": proposal_data.get("simulation_code") or simulation_code,
        },
        "generated": {
            "contractDocumentType": generated.contract_document_type.upper(),
            "contractDocumentMasked": generated.contract_document_number,
            "email": generated.email,
        },
        "historyIndex": history_index,
        "raw": proposal_response,
    }



def fetch_proposal_catalogs_for_web(api_session: ApiSession) -> ProposalCatalogs:
    with ThreadPoolExecutor(max_workers=6) as executor:
        f_civil = executor.submit(list_catalog_options, api_session, "/admin/civil-status")
        f_education = executor.submit(list_catalog_options, api_session, "/admin/education")
        f_gender = executor.submit(list_catalog_options, api_session, "/admin/gender")
        f_state = executor.submit(list_catalog_options, api_session, "/admin/state")
        f_bank_type = executor.submit(list_catalog_options, api_session, "/admin/bank-account-type")
        f_bank = executor.submit(
            list_catalog_options, api_session, "/admin/bank", params={"limit": 300, "offset": 10},
        )

    civil_status = pick_catalog_option_for_web(f_civil.result(), preferred_codes=("1", "2"))
    education = pick_catalog_option_for_web(f_education.result(), preferred_codes=("1", "2", "3"))
    gender = pick_catalog_option_for_web(f_gender.result(), preferred_codes=("M", "F"))
    state = pick_catalog_option_for_web(f_state.result(), preferred_codes=("MG", "SP", "PR"))
    bank_account_type = pick_catalog_option_for_web(f_bank_type.result(), preferred_codes=("cc",))
    bank = pick_catalog_option_for_web(f_bank.result(), preferred_codes=("001",))

    return ProposalCatalogs(
        civil_status_code=civil_status.code or civil_status.id,
        education_code=education.code or education.id,
        gender_code=gender.code or gender.id,
        state_code=state.code or state.id,
        bank_code=bank.code or bank.id,
        bank_account_type_code=bank_account_type.code or bank_account_type.id,
    )



def pick_catalog_option_for_web(
    options: list[CatalogOption],
    *,
    preferred_codes: tuple[str, ...] = (),
    preferred_names: tuple[str, ...] = (),
) -> CatalogOption:
    if not options:
        raise WebApiError(
            "Um dos catalogos obrigatorios da proposta retornou vazio.",
            status_code=HTTPStatus.BAD_GATEWAY,
            code="proposal_catalog_empty",
        )

    normalized_codes = {code.strip().lower() for code in preferred_codes if code}
    normalized_names = {name.strip().lower() for name in preferred_names if name}

    for option in options:
        if option.code.strip().lower() in normalized_codes:
            return option
    for option in options:
        if option.name.strip().lower() in normalized_names:
            return option
    return options[0]



def build_generated_proposal_client_data_for_web(
    *,
    fake_data_service: FakeDataService,
    client_name: str,
    client_phone: str,
    main_document_number: str,
    state_code: str,
) -> ProposalGeneratedClientData:
    contract_document_type = fake_data_service.generate_contract_document_type()
    return ProposalGeneratedClientData(
        birth_date=fake_data_service.generate_birth_date(),
        mothers_name=fake_data_service.generate_parent_name(),
        fathers_name=fake_data_service.generate_parent_name(),
        city=fake_data_service.generate_city(),
        email=fake_data_service.generate_email(client_name),
        main_phone=client_phone,
        postal_code=fake_data_service.generate_postal_code(),
        street=fake_data_service.generate_street(),
        number=fake_data_service.generate_address_number(),
        complement_address=fake_data_service.generate_address_complement(),
        district=fake_data_service.generate_district(),
        contract_document_type=contract_document_type,
        contract_document_number=fake_data_service.generate_contract_document_number(
            contract_document_type,
            exclude=main_document_number,
        ),
        contract_document_state_code=state_code,
        contract_document_issuer=("DETRAN" if contract_document_type == "cnh" else "SSP"),
        contract_document_expedition_date=fake_data_service.generate_document_expedition_date(),
        bank_agency=fake_data_service.generate_agency(),
        bank_agency_digit=fake_data_service.generate_agency_digit(),
        bank_account=fake_data_service.generate_account(),
        bank_account_digit=fake_data_service.generate_account_digit(),
    )


def resolve_dataprev_context(
    *,
    api_session: ApiSession,
    product: Product,
    client_name: str,
    client_document: str,
    fallback_margin_value: str | int,
    fallback_benefit_number: str,
) -> tuple[str | int, str, str]:
    try:
        benefits = list_dataprev_benefits(
            api_session=api_session,
            document=client_document,
            name=client_name,
        )
        selected = select_dataprev_benefit_for_web(benefits, product.name)
        return (
            selected.margin_value_for_product(product.name),
            selected.benefit_number or fallback_benefit_number,
            "",
        )
    except (ApiRequestError, ValueError) as exc:
        warning = "A consulta online da DATAPREV nao concluiu. A simulacao seguiu com os dados disponiveis na planilha."
        return fallback_margin_value, fallback_benefit_number, warning



def select_dataprev_benefit_for_web(benefits: list[DataprevBenefit], product_name: str) -> DataprevBenefit:
    if not benefits:
        raise ValueError("A consulta DATAPREV nao retornou beneficios para o cliente informado.")
    candidates = [benefit for benefit in benefits if benefit.is_eligible_for_product(product_name)]
    if not candidates:
        raise ValueError("Nenhum beneficio DATAPREV elegivel foi encontrado para o produto selecionado.")
    preferred = [benefit for benefit in candidates if not benefit.blocked_for_loan] or candidates
    return preferred[0]



def resolve_serpro_context(
    *,
    api_session: ApiSession,
    agreement_id: str,
    product: Product,
    client_name: str,
    client_document: str,
    fallback_benefit_number: str,
    fallback_sponsor_benefit_number: str,
    manual_agency_id: str,
    manual_agency_sub_id: str,
    manual_agency_sub_upag_id: str,
) -> tuple[SerproIdentifiers, int | str, str, str, str]:
    warning = ""
    try:
        benefits = list_serpro_benefits(
            api_session=api_session,
            document=client_document,
            name=client_name,
            product_id=product.id,
            agreement_id=agreement_id,
        )
        selected = select_serpro_benefit_for_web(benefits, product.name)
        serpro_agency_id = manual_agency_id or selected.serpro_agency_id
        if not serpro_agency_id:
            raise WebApiError(
                "A consulta SERPRO nao retornou serpro_agency_id e nenhum valor manual foi informado.",
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="missing_serpro_agency_id",
            )
        return (
            SerproIdentifiers(
                agency_id=serpro_agency_id,
                agency_sub_id=manual_agency_sub_id,
                agency_sub_upag_id=manual_agency_sub_upag_id,
            ),
            selected.margin_value_for_product(product.name),
            selected.benefit_number or fallback_benefit_number,
            fallback_sponsor_benefit_number or selected.sponsor_benefit_number,
            warning,
        )
    except (ApiRequestError, ValueError) as exc:
        if not manual_agency_id:
            raise WebApiError(
                "A consulta SERPRO falhou e nenhum serpro_agency_id manual foi informado.",
                status_code=HTTPStatus.BAD_GATEWAY,
                detail=str(exc),
                code="serpro_lookup_failed",
            ) from exc
        warning = "A simulacao seguiu com preenchimento manual de SERPRO porque a consulta automatica nao concluiu."
        return (
            SerproIdentifiers(
                agency_id=manual_agency_id,
                agency_sub_id=manual_agency_sub_id,
                agency_sub_upag_id=manual_agency_sub_upag_id,
            ),
            "",
            fallback_benefit_number,
            fallback_sponsor_benefit_number,
            warning,
        )



def resolve_cip_context(
    *,
    api_session: ApiSession,
    agreement_id: str,
    product: Product,
    withdraw_type_id: str,
    client_name: str,
    client_document: str,
    fallback_margin_value: str | int,
    fallback_benefit_number: str,
    fallback_cip_agency_id: str,
    allow_cip_fallback: bool,
) -> tuple[str | int, str, str, str]:
    try:
        benefits = list_cip_benefits(
            api_session=api_session,
            document=client_document,
            agency_id=fallback_cip_agency_id,
            agreement_id=agreement_id,
            product_id=product.id,
            withdraw_type_id=withdraw_type_id,
            name=client_name,
        )
        selected = select_cip_benefit_for_web(benefits, product.name)
        return (
            selected.margin_value_for_product(product.name),
            sanitize_text(selected.benefit_number),
            selected.cip_agency_id or fallback_cip_agency_id,
            "",
        )
    except (ApiRequestError, ValueError) as exc:
        if not allow_cip_fallback:
            raise WebApiError(
                "A consulta CIP falhou e o fallback com dados da planilha foi desabilitado.",
                status_code=HTTPStatus.BAD_GATEWAY,
                detail=str(exc),
                code="cip_lookup_failed",
            ) from exc
        warning = "A consulta online da CIP nao concluiu. A simulacao seguiu com os dados disponiveis na planilha."
        return fallback_margin_value, fallback_benefit_number, fallback_cip_agency_id, warning



def select_serpro_benefit_for_web(benefits: list[SerproBenefit], product_name: str) -> SerproBenefit:
    if not benefits:
        raise ValueError("A consulta SERPRO nao retornou beneficios para o cliente informado.")
    candidates = [benefit for benefit in benefits if benefit.is_eligible_for_product(product_name)]
    if not candidates:
        raise ValueError("Nenhum beneficio SERPRO elegivel foi encontrado para o produto selecionado.")
    preferred = [benefit for benefit in candidates if not benefit.blocked_for_loan] or candidates
    return preferred[0]



def select_cip_benefit_for_web(benefits: list[CipBenefit], product_name: str) -> CipBenefit:
    if not benefits:
        raise ValueError("A consulta CIP nao retornou beneficios para o cliente informado.")
    candidates = [benefit for benefit in benefits if benefit.is_eligible_for_product(product_name)]
    if not candidates:
        raise ValueError("Nenhum beneficio CIP elegivel foi encontrado para o produto selecionado.")
    preferred = [benefit for benefit in candidates if not benefit.blocked_for_loan] or candidates
    return preferred[0]



def resolve_environment_config(environment_value: Any) -> EnvironmentConfig:
    environment_key = sanitize_text(environment_value).upper()
    if environment_key not in ENVIRONMENT_OPTIONS:
        raise WebApiError(
            "Ambiente invalido.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="invalid_environment",
        )
    try:
        return get_environment_config(environment_key)
    except Exception as exc:  # noqa: BLE001
        raise WebApiError(
            "Nao foi possivel carregar as configuracoes do ambiente selecionado.",
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(exc),
            code="environment_config_error",
        ) from exc



def find_item_by_id(items: list[Any], item_id: str, label: str) -> Any:
    for item in items:
        if getattr(item, "id", "") == item_id:
            return item
    raise WebApiError(
        f"Nao foi possivel localizar o {label} selecionado.",
        status_code=HTTPStatus.BAD_REQUEST,
        code="item_not_found",
    )



def _prewarm_sheets() -> None:
    try:
        sheets_service = GoogleSheetsService()
        for processor_code in PROCESSOR_SHEET_MAP:
            sheets_service.load_processor_data(processor_code)
    except Exception:  # noqa: BLE001
        pass


def load_sheet_record_for_product(processor_code: str, product_name: str, *, record_index: int = 0) -> SelectedSheetRecord:
    try:
        sheets_service = GoogleSheetsService()
        processor_sheet = sheets_service.load_processor_data(processor_code)
        return sheets_service.select_record_from_data(processor_sheet, product_name, record_index=record_index)
    except GoogleSheetsError as exc:
        raise WebApiError(
            "Nao foi possivel obter um registro elegivel na planilha para o produto selecionado.",
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=str(exc),
            code="sheet_record_unavailable",
        ) from exc



def serialize_sheet_record(record: SelectedSheetRecord) -> dict[str, Any]:
    return {
        "processorCode": record.processor_code,
        "worksheetName": record.worksheet_name,
        "balanceField": record.balance_field,
        "balanceValue": record.balance_value,
        "matricula": record.matricula,
        "cpf": record.cpf,
        "maskedCpf": record.cpf,
        "nome": record.nome,
        "orgao": record.orgao,
        "senha": record.senha,
        "matchingRecordsCount": record.matching_records_count,
        "selectedRecordIndex": record.selected_record_index,
        "selectedRecordNumber": record.selected_record_number,
    }




def parse_history_index(value: Any) -> int:
    text = str(value or "").strip()
    if not text.isdigit() or int(text) <= 0:
        raise WebApiError(
            "O indice da proposta no historico e obrigatorio.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="invalid_history_index",
        )
    return int(text)

def parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def parse_sheet_record_index(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return max(int(text), 0)
    except ValueError:
        return 0


def require_text(payload: dict[str, Any], key: str) -> str:
    value = sanitize_text(payload.get(key))
    if not value:
        raise WebApiError(
            f"O campo '{key}' e obrigatorio.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="missing_field",
        )
    return value



def sanitize_text(value: Any) -> str:
    return str(value or "").strip()



def mask_value(value: str) -> str:
    digits = sanitize_digits(value)
    if len(digits) <= 4:
        return digits
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"



def format_web_error_detail(error: Exception) -> str:
    details = getattr(error, "details", None)
    if not details:
        return str(error)

    lines: list[str] = [str(error)]
    if details.method or details.path:
        lines.append(f"Endpoint: {details.method} {details.path}".strip())
    if details.status_code is not None:
        lines.append(f"Status HTTP: {details.status_code}")
    if details.correlation_id:
        lines.append(f"Correlation ID: {details.correlation_id}")
    if details.api_message:
        lines.append(f"Mensagem da API: {details.api_message}")
    if details.trace_excerpt:
        lines.append(f"Trace resumido: {details.trace_excerpt}")
    elif details.raw_body:
        lines.append(f"Resposta bruta: {details.raw_body[:320]}")
    return "\n".join(lines)



def describe_api_error(error: Exception) -> str:
    message = str(error)
    details = getattr(error, "details", None)
    if "XmlEncrypto" in message or "EncryptionException" in message:
        return "Diagnostico: a consulta falhou na integracao CIP/WsSecurity do backend."
    if "AvailableProductsByClientAdapter.php:43" in message:
        return "Diagnostico: a simulacao chegou ao backend, mas falhou na etapa de seguros."
    if details and details.status_code == 422:
        return "Diagnostico: a API rejeitou os dados enviados por validacao de regra de negocio."
    if details and details.status_code == 404:
        return "Diagnostico: a API nao encontrou o recurso esperado nesta etapa."
    if details and details.status_code == 500:
        return "Diagnostico: a API respondeu com erro interno 500."
    if "500" in message:
        return "Diagnostico: a API respondeu com erro interno 500."
    return "Diagnostico: a API retornou erro durante o processamento."























def generate_ai_commentary_for_protheus_stage(
    *,
    environment_label: str,
    proposal_code: str,
    stage_code: str,
    stage_name: str,
    main_document: str,
    validation_message: str,
    checks: list[ProtheusCheckItem],
) -> str:
    fallback = "BANCO: Comentario IA indisponivel.\nAPI: Comentario IA indisponivel.\nCONSOLIDADO: Comentario IA indisponivel para esta etapa."
    api_key = sanitize_text(os.getenv("OPENAI_API_KEY"))
    if not api_key:
        return f"{fallback} OPENAI_API_KEY nao configurada."

    compact_checks = [
        {
            "label": c.label,
            "source": c.source_type,
            "origin": c.origin,
            "result": c.result,
            "message": _truncate_text(c.message, 180),
            "querySql": _truncate_text(c.query_sql, 220),
            "httpStatus": c.http_status_code,
        }
        for c in (checks or [])[:10]
    ]

    context_payload = {
        "environment": environment_label,
        "proposalCode": proposal_code,
        "stageCode": stage_code,
        "stageName": stage_name,
        "mainDocument": sanitize_digits(main_document),
        "validationMessage": validation_message,
        "checks": compact_checks,
    }

    system_prompt = (
        "Voce e um analista tecnico de QA para automacao de propostas. "
        "Analise validacoes de banco e APIs externas de maneira objetiva, sem suposicoes, e respeitando rigorosamente a regra de negocio ja aplicada pelo backend. "
        "O campo validationMessage representa o resultado final deterministicamente calculado e nao deve ser contradito."
    )
    user_prompt = (
        "Interprete os dados da etapa do Protheus e responda EXATAMENTE em 3 linhas: \n"
        "BANCO: <diagnostico curto sobre query/logs de banco>\n"
        "API: <diagnostico curto sobre APIs externas/soap>\n"
        "CONSOLIDADO: <resumo curto com risco/proximo passo>\n"
        "Regras: maximo 180 caracteres por linha; nao afirmar sucesso sem evidencia; nao contradizer validationMessage.\n"
        "Regras de negocio obrigatorias:\n"
        "- Se validationMessage indicar validacao bem-sucedida, o CONSOLIDADO deve refletir sucesso, sem sugerir investigacao adicional como conclusao principal.\n"
        "- Etapa protheus: a primeira verificacao obrigatoria e o lookup na tabela protheus_client_codes pelo CPF do cliente. Se o CPF nao estiver cadastrado, a etapa falha imediatamente.\n"
        "- Etapa protheus: o campo 'code' retornado de protheus_client_codes e o identificador do cliente no Protheus e deve estar presente para prosseguir.\n"
        "- Etapa protheus: nao existe mais validacao de VALFOR nos logs do banco (protheus_logs). O VALFOR e chamado SEMPRE externamente via SOAP.\n"
        "- Etapa protheus: o VALFOR externo e obrigatorio. A presenca de RETWS na resposta (true OU false) indica que o CPF esta cadastrado no Protheus — ambos os valores sao validos.\n"
        "- Etapa protheus: se RETWS estiver ausente na resposta do VALFOR, significa falha de conectividade ou CPF nao localizado.\n"
        "- Etapa protheus: STATUS=true em ATUALIZAR nos logs do banco confirma a atualizacao no Protheus.\n"
        "- Etapa protheus: a formalizacao e valida somente se ATUALIZAR confirmado E VALFOR externo retornou RETWS (true ou false).\n"
        "- Etapa protheus-issuance: o campo CLIENTEFORNECEDOOR do payload SOAP INCPAGARSE deve usar o 'code' da tabela protheus_client_codes (nao os primeiros 6 digitos do CPF).\n"
        "- Etapa protheus-issuance: se o codigo de cliente nao estiver disponivel em protheus_client_codes, a emissao falha mesmo que o log INCPAGARSE exista.\n"
        "- Etapa protheus-issuance: a prova de realidade (SOAP duplicidade) confirma que o titulo foi gerado usando o codigo correto do cliente.\n\n"
        f"Dados: {json.dumps(context_payload, ensure_ascii=False)}"
    )

    candidate_models: list[str] = []
    for model in [
        sanitize_text(os.getenv("OPENAI_STAGE_MODEL")),
        sanitize_text(os.getenv("OPENAI_REPORT_MODEL")),
        "gpt-5-mini",
        "gpt-4.1-mini",
        "gpt-4o-mini",
    ]:
        if model and model not in candidate_models:
            candidate_models.append(model)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = ""
    for model in candidate_models:
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "temperature": 0.2,
                    "max_tokens": 180,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=OPENAI_STAGE_COMMENT_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"Falha de rede: {_truncate_text(str(exc), 120)}"
            continue

        if response.status_code >= 400:
            last_error = f"HTTP {response.status_code}: {_truncate_text(response.text, 120)}"
            continue

        try:
            payload = response.json()
        except ValueError:
            last_error = "Resposta da IA sem JSON valido."
            continue

        commentary = _extract_chat_completion_content(payload)
        if commentary:
            return commentary

        last_error = "Resposta da IA sem conteudo textual."

    if last_error:
        return f"{fallback} {last_error}"
    return fallback


def handle_generate_report_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    history_payload = build_proposal_history_response(config.key)
    proposals = [
        proposal
        for proposal in (history_payload.get("proposals") or [])
        if isinstance(proposal.get("executions"), list) and proposal.get("executions")
    ]

    if not proposals:
        raise WebApiError(
            "Nao ha execucoes registradas para gerar o relatorio.",
            status_code=HTTPStatus.BAD_REQUEST,
            code="report_without_executions",
        )

    summary = history_payload.get("observabilitySummary") or {}
    environment_label = ENVIRONMENT_OPTIONS.get(config.key, config.key)
    generated_at = _utc_now_iso()
    ai_commentary = generate_ai_commentary_for_report(
        environment_label=environment_label,
        summary=summary,
        proposals=proposals,
    )

    report_data = {
        "environment": config.key,
        "environmentLabel": environment_label,
        "generatedAt": generated_at,
        "summary": summary,
        "aiCommentary": ai_commentary,
        "proposals": proposals,
        "iconUrl": sanitize_text(os.getenv("SENFF_ICON_URL")),
    }

    report_html = _build_execution_report_html(report_data)
    artifact_path = persist_report_html_artifact(config.key, report_html)

    return {
        "environment": config.key,
        "generatedAt": generated_at,
        "fileName": artifact_path.name,
        "artifactPath": str(artifact_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "aiCommentary": ai_commentary,
        "html": report_html,
    }


def persist_report_html_artifact(environment_key: str, report_html: str) -> Path:
    reports_dir = PROJECT_ROOT / "artifacts" / "reports" / environment_key.lower()
    reports_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.html"
    report_path = reports_dir / file_name
    report_path.write_text(report_html, encoding="utf-8")
    return report_path


def generate_ai_commentary_for_report(
    *,
    environment_label: str,
    summary: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> str:
    fallback = "Comentario de IA indisponivel no momento. Use os graficos e os detalhes por proposta para revisar a rodada."
    api_key = sanitize_text(os.getenv("OPENAI_API_KEY"))
    if not api_key:
        return f"{fallback} OPENAI_API_KEY nao configurada."

    context_payload = _build_ai_report_context(summary=summary, proposals=proposals)
    user_prompt = (
        "Analise os dados de execucao da suite de consignado e escreva um comentario objetivo em portugues brasileiro, "
        "com no maximo 8 linhas, cobrindo: panorama da rodada, riscos observados, pontos de atencao e proximos focos. "
        "Nao afirme sucesso geral do teste sem evidencias claras.\n\n"
        f"Ambiente: {environment_label}\n"
        f"Dados: {json.dumps(context_payload, ensure_ascii=False)}"
    )

    system_prompt = (
        "Voce e um analista tecnico de QA para automacao de propostas. "
        "Analise validacoes de banco e APIs externas de maneira objetiva, sem suposicoes, e respeitando rigorosamente a regra de negocio ja aplicada pelo backend. "
        "O campo validationMessage representa o resultado final deterministicamente calculado e nao deve ser contradito."
    )

    candidate_models: list[str] = []
    for model in [
        sanitize_text(os.getenv("OPENAI_REPORT_MODEL")),
        "gpt-5-mini",
        "gpt-4.1-mini",
        "gpt-4o-mini",
    ]:
        if model and model not in candidate_models:
            candidate_models.append(model)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = ""
    for model in candidate_models:
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "temperature": 0.2,
                    "max_tokens": 380,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=OPENAI_REPORT_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"Falha de rede ao consultar IA: {_truncate_text(str(exc), 180)}"
            continue

        if response.status_code >= 400:
            last_error = f"HTTP {response.status_code}: {_truncate_text(response.text, 180)}"
            continue

        try:
            payload = response.json()
        except ValueError:
            last_error = "A resposta da IA nao retornou JSON valido."
            continue

        commentary = _extract_chat_completion_content(payload)
        if commentary:
            return commentary

        last_error = "A resposta da IA veio sem conteudo textual util."

    if last_error:
        return f"{fallback} Detalhe: {last_error}"
    return fallback


def _build_ai_report_context(*, summary: dict[str, Any], proposals: list[dict[str, Any]]) -> dict[str, Any]:
    compact_proposals: list[dict[str, Any]] = []
    for proposal in proposals[:OPENAI_REPORT_MAX_PROPOSALS_CONTEXT]:
        executions = proposal.get("executions") or []
        latest_execution = executions[-1] if executions else {}
        stage_results = latest_execution.get("stageResults") or []

        compact_proposals.append(
            {
                "index": proposal.get("index"),
                "proposalCode": proposal.get("proposalCode"),
                "contractCode": proposal.get("contractCode"),
                "processorCode": proposal.get("processorCode"),
                "executionCount": proposal.get("executionCount", len(executions)),
                "latestExecution": {
                    "runId": latest_execution.get("runId"),
                    "status": latest_execution.get("status"),
                    "durationMs": latest_execution.get("durationMs"),
                    "httpCalls": latest_execution.get("totalHttpCalls"),
                    "dbChecks": latest_execution.get("totalDbChecks"),
                    "stages": [
                        {
                            "code": stage.get("stageCode"),
                            "result": stage.get("result"),
                            "finalStatus": stage.get("finalStatus"),
                            "action": stage.get("configuredAction"),
                        }
                        for stage in stage_results
                    ],
                },
            }
        )

    return {
        "summary": summary,
        "proposals": compact_proposals,
    }


def _extract_chat_completion_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    content = message.get("content")

    if isinstance(content, str):
        return sanitize_text(content)

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return sanitize_text("\n".join(chunks))

    return ""


def _truncate_text(value: Any, max_length: int) -> str:
    text = sanitize_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}..."


def _build_execution_report_html(report_data: dict[str, Any]) -> str:
    report_json = json.dumps(report_data, ensure_ascii=False).replace("</", "<\\/")
    template = """<!doctype html>
<html lang=\"pt-BR\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Relatorio de Execucao - Suite Consignado</title>
    <link rel="icon" href="__REPORT_FAVICON_URL__" />
    <script src=\"https://cdn.tailwindcss.com\"></script>
    <style>
      body { background: #f1f5f9; }
      .report-shell { max-width: 1180px; margin: 0 auto; }
      .chart-bar-track { height: 10px; border-radius: 999px; background: #e2e8f0; overflow: hidden; }
      .chart-bar-fill { height: 100%; border-radius: 999px; }
      summary::-webkit-details-marker { display: none; }
      details[open] > summary .chevron { transform: rotate(90deg); }
      .chevron { transition: transform 0.15s ease; }
      .mono { font-variant-numeric: tabular-nums; }
      @media print {
        header, footer { position: static !important; }
        body { background: white; }
        details { break-inside: avoid; }
      }
    </style>
  </head>
  <body class=\"text-slate-800\">
    <div class=\"min-h-screen flex flex-col\">
      <header class=\"sticky top-0 z-30 border-b border-slate-200 bg-slate-900 text-white\">
        <div class=\"report-shell px-6 py-5 flex items-center justify-between gap-4\">
          <div>
            <p class=\"text-[0.65rem] uppercase tracking-widest font-bold text-blue-300\">Suite Consignado</p>
            <h1 class=\"text-xl font-bold\">Relatorio de Execucao da Rodada</h1>
            <p id=\"reportHeaderMeta\" class=\"text-xs text-slate-300 mt-1\"></p>
          </div>
          <div class=\"text-right text-xs text-slate-300\">
            <p>Gerado automaticamente</p>
            <p class=\"mono\" id=\"reportHeaderGeneratedAt\"></p>
          </div>
        </div>
      </header>

      <main class=\"report-shell w-full px-6 py-7 space-y-6 flex-1\">
        <section class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5\">
          <h2 class=\"text-sm font-bold text-slate-900\">Resumo da rodada</h2>
          <p class=\"text-xs text-slate-500 mt-1\">Metricas agregadas das execucoes observadas nesta sessao.</p>
          <div id=\"summaryCards\" class=\"mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4\"></div>
        </section>

        <section class=\"grid gap-4 xl:grid-cols-3\">
          <article class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5\">
            <h3 class=\"text-xs uppercase tracking-widest font-bold text-slate-400\">Status das execucoes</h3>
            <div id=\"statusChart\" class=\"mt-4 space-y-2\"></div>
          </article>
          <article class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5\">
            <h3 class=\"text-xs uppercase tracking-widest font-bold text-slate-400\">Duracao por proposta</h3>
            <div id=\"durationChart\" class=\"mt-4 space-y-2\"></div>
          </article>
          <article class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5\">
            <h3 class=\"text-xs uppercase tracking-widest font-bold text-slate-400\">Volume de logs (HTTP/DB)</h3>
            <div id=\"trafficChart\" class=\"mt-4 space-y-3\"></div>
          </article>
        </section>

        <section class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5\">
          <h2 class=\"text-sm font-bold text-slate-900\">Comentario de IA</h2>
          <p class=\"text-xs text-slate-500 mt-1\">Resumo analitico com foco em diagnostico. Pode conter incertezas quando o contexto estiver incompleto.</p>
          <div class=\"mt-3 rounded-lg bg-slate-50 border border-slate-200 px-4 py-3\">
            <p id=\"aiCommentaryText\" class=\"text-sm leading-relaxed text-slate-700 whitespace-pre-line\"></p>
          </div>
        </section>

        <section class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5\">
          <h2 class=\"text-sm font-bold text-slate-900\">Propostas executadas e validacoes</h2>
          <p class=\"text-xs text-slate-500 mt-1\">Expanda uma proposta para ver execucoes, etapas, requests e validacoes de banco.</p>
          <div id=\"proposalList\" class=\"mt-4 space-y-3\"></div>
        </section>
      </main>

      <footer class=\"sticky bottom-0 z-30 border-t border-slate-200 bg-white\">
        <div class=\"report-shell px-6 py-3 text-[0.7rem] text-slate-400 flex items-center justify-between gap-3\">
          <span>Suite Consignado - Relatorio dinamico em HTML</span>
          <span id=\"reportFooterMeta\" class=\"mono\"></span>
        </div>
      </footer>
    </div>

    <script>
      const reportData = __REPORT_DATA__;

      const toneMap = {
        neutral: { badge: "bg-slate-100 text-slate-700", bar: "bg-slate-500" },
        progress: { badge: "bg-blue-100 text-blue-700", bar: "bg-blue-500" },
        warning: { badge: "bg-amber-100 text-amber-700", bar: "bg-amber-500" },
        success: { badge: "bg-emerald-100 text-emerald-700", bar: "bg-emerald-500" },
        danger: { badge: "bg-rose-100 text-rose-700", bar: "bg-rose-500" },
      };

      function esc(value) {
        return String(value ?? "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/\"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      function toneFromStatus(raw) {
        const normalized = String(raw || "").trim().toUpperCase();
        if (!normalized) return "neutral";
        if (["FAILED", "FAIL", "ERROR", "CANCELLED", "CANCELED", "REJECTED", "DENIED", "INVALID"].includes(normalized)) return "danger";
        if (["RUNNING", "IN_PROGRESS", "PROCESSING", "STARTED"].includes(normalized)) return "progress";
        if (["MANUAL_PENDING", "WAITING", "MANUAL", "MANUAL_ANALYSIS", "PENDING_MANUAL"].includes(normalized)) return "warning";
        if (["COMPLETED", "APPROVED", "SUCCESS", "DONE", "OK", "FINISHED", "PAID"].includes(normalized)) return "success";
        return "neutral";
      }

      function statusLabel(raw) {
        const normalized = String(raw || "").trim().toUpperCase();
        const labels = {
          COMPLETED: "Concluida",
          FAILED: "Falhou",
          RUNNING: "Em execucao",
          MANUAL_PENDING: "Manual pendente",
          WAITING: "Aguardando",
          CANCELLED: "Cancelada",
          CANCELED: "Cancelada",
          APPROVED: "Aprovada",
          FAIL: "Falha",
          IN_PROGRESS: "Em progresso",
          MANUAL_ANALYSIS: "Analise manual",
          PENDING: "Pendente",
        };
        return labels[normalized] || (normalized || "Sem status");
      }

      function formatDateTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return new Intl.DateTimeFormat("pt-BR", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }).format(date);
      }

      function formatDuration(ms) {
        const value = Number(ms || 0);
        if (!Number.isFinite(value) || value <= 0) return "0 ms";
        if (value < 1000) return `${Math.round(value)} ms`;
        if (value < 60000) return `${(value / 1000).toFixed(2)} s`;
        const minutes = Math.floor(value / 60000);
        const seconds = Math.round((value % 60000) / 1000);
        if (minutes < 60) return `${minutes} min ${seconds}s`;
        const hours = Math.floor(minutes / 60);
        const remMin = minutes % 60;
        return `${hours}h ${remMin}m ${seconds}s`;
      }

      function renderSummaryCards() {
        const summary = reportData.summary || {};
        const cards = [
          ["Propostas monitoradas", summary.proposalsWithExecutions || 0, "neutral"],
          ["Execucoes", summary.totalExecutions || 0, "progress"],
          ["Concluidas", summary.completedExecutions || 0, "success"],
          ["Falhas", summary.failedExecutions || 0, "danger"],
          ["Manuais", summary.manualExecutions || 0, "warning"],
          ["Aguardando", summary.waitingExecutions || 0, "warning"],
          ["HTTP total", summary.totalHttpCalls || 0, "neutral"],
          ["DB total", summary.totalDbChecks || 0, "neutral"],
        ];

        document.getElementById("summaryCards").innerHTML = cards.map(([label, value, tone]) => {
          const palette = toneMap[tone] || toneMap.neutral;
          return `<article class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <span class="text-[0.65rem] uppercase tracking-widest font-bold text-slate-400">${esc(label)}</span>
            <p class="mt-2 text-xl font-extrabold text-slate-900 mono">${esc(value)}</p>
            <span class="inline-flex mt-2 px-2 py-0.5 rounded text-[0.65rem] font-bold ${palette.badge}">Indicador</span>
          </article>`;
        }).join("");
      }

      function renderStatusChart() {
        const summary = reportData.summary || {};
        const stats = [
          ["Concluidas", Number(summary.completedExecutions || 0), "success"],
          ["Falhas", Number(summary.failedExecutions || 0), "danger"],
          ["Manual", Number(summary.manualExecutions || 0), "warning"],
          ["Aguardando", Number(summary.waitingExecutions || 0), "warning"],
          ["Canceladas", Number(summary.cancelledExecutions || 0), "neutral"],
        ];

        const total = stats.reduce((acc, item) => acc + item[1], 0) || 1;
        document.getElementById("statusChart").innerHTML = stats.map(([label, value, tone]) => {
          const pct = Math.round((value / total) * 100);
          const palette = toneMap[tone] || toneMap.neutral;
          return `<div class="space-y-1">
            <div class="flex items-center justify-between text-[0.7rem] text-slate-500">
              <span>${esc(label)}</span><span class="mono">${esc(value)} (${pct}%)</span>
            </div>
            <div class="chart-bar-track"><div class="chart-bar-fill ${palette.bar}" style="width:${pct}%"></div></div>
          </div>`;
        }).join("");
      }

      function latestExecution(record) {
        const executions = Array.isArray(record.executions) ? record.executions : [];
        return executions.length ? executions[executions.length - 1] : null;
      }

      function renderDurationChart() {
        const proposals = Array.isArray(reportData.proposals) ? reportData.proposals : [];
        const items = proposals
          .map((p) => ({ code: p.proposalCode || `#${p.index || "-"}`, duration: Number(latestExecution(p)?.durationMs || 0) }))
          .sort((a, b) => b.duration - a.duration)
          .slice(0, 8);

        const maxDuration = Math.max(...items.map((item) => item.duration), 1);
        document.getElementById("durationChart").innerHTML = items.length
          ? items.map((item) => {
              const pct = Math.max(6, Math.round((item.duration / maxDuration) * 100));
              return `<div class="space-y-1">
                <div class="flex items-center justify-between text-[0.7rem] text-slate-500 gap-2">
                  <span class="truncate" title="${esc(item.code)}">${esc(item.code)}</span>
                  <span class="mono">${esc(formatDuration(item.duration))}</span>
                </div>
                <div class="chart-bar-track"><div class="chart-bar-fill bg-blue-500" style="width:${pct}%"></div></div>
              </div>`;
            }).join("")
          : '<p class="text-xs text-slate-400">Sem dados de duracao.</p>';
      }

      function renderTrafficChart() {
        const proposals = Array.isArray(reportData.proposals) ? reportData.proposals : [];
        const items = proposals
          .map((p) => {
            const latest = latestExecution(p) || {};
            return {
              code: p.proposalCode || `#${p.index || "-"}`,
              http: Number(latest.totalHttpCalls || 0),
              db: Number(latest.totalDbChecks || 0),
            };
          })
          .slice(0, 8);

        const maxValue = Math.max(...items.map((item) => Math.max(item.http, item.db)), 1);
        document.getElementById("trafficChart").innerHTML = items.length
          ? items.map((item) => {
              const httpPct = Math.round((item.http / maxValue) * 100);
              const dbPct = Math.round((item.db / maxValue) * 100);
              return `<div class="space-y-1">
                <div class="text-[0.7rem] text-slate-500 truncate" title="${esc(item.code)}">${esc(item.code)}</div>
                <div class="flex items-center gap-2 text-[0.65rem] text-slate-400">
                  <span class="w-8">HTTP</span>
                  <div class="flex-1 chart-bar-track"><div class="chart-bar-fill bg-blue-500" style="width:${httpPct}%"></div></div>
                  <span class="mono w-7 text-right">${item.http}</span>
                </div>
                <div class="flex items-center gap-2 text-[0.65rem] text-slate-400">
                  <span class="w-8">DB</span>
                  <div class="flex-1 chart-bar-track"><div class="chart-bar-fill bg-emerald-500" style="width:${dbPct}%"></div></div>
                  <span class="mono w-7 text-right">${item.db}</span>
                </div>
              </div>`;
            }).join("")
          : '<p class="text-xs text-slate-400">Sem dados de HTTP/DB.</p>';
      }

      function renderProtheusValidation(pv) {
        if (!pv) return "";
        const valid = pv.valid === true;
        const bypassed = pv.bypassed === true;
        const checks = Array.isArray(pv.checks) ? pv.checks : [];
        const aiCommentChecks = checks.filter((item) => {
          const label = String(item?.label || "").toUpperCase();
          const origin = String(item?.origin || "").toUpperCase();
          return label.includes("COMENTARIO IA") || origin.includes("AI - COMENTARIO");
        });
        const aiCommentaryItems = aiCommentChecks
          .map((item) => ({
            label: String(item?.label || "Comentario IA"),
            message: String(item?.message || "").trim(),
          }))
          .filter((item) => item.message);
        const visibleChecks = aiCommentChecks.length ? checks.filter((item) => !aiCommentChecks.includes(item)) : checks;
        const color = valid ? "emerald" : "rose";
        const badgeClass = bypassed
          ? "bg-slate-100 text-slate-600"
          : valid
            ? "bg-emerald-100 text-emerald-700"
            : "bg-rose-100 text-rose-700";
        const badgeLabel = bypassed ? "Bypass" : valid ? "Validado" : "Invalido";
        const icon = valid
          ? `<svg class="w-3.5 h-3.5 inline text-${color}-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>`
          : `<svg class="w-3.5 h-3.5 inline text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>`;

        const checkRows = visibleChecks.map((c) => {
          const icon = c.result === true ? "&#10003;" : c.result === false ? "&#10007;" : "&mdash;";
          const iconCls = c.result === true ? "text-emerald-600 font-bold" : c.result === false ? "text-rose-600 font-bold" : "text-slate-400";
          const srcCls = c.sourceType === "API" ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-600";
          const querySql = c.querySql || c.query_sql || "";
          const requestHeaders = c.requestHeaders || c.request_headers || "";
          const hasBody = Boolean(querySql || requestHeaders || c.requestBody || c.responseBody);
          const bodyRows = hasBody ? `<tr><td colspan="4" class="pb-2 px-1">
            <details><summary class="cursor-pointer text-slate-400 text-[0.6rem]">Ver payload</summary>
            <div class="mt-1 space-y-1">
              ${querySql ? `<div><b>Query:</b><pre class="whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded p-1 text-[0.55rem] font-mono mt-0.5 overflow-x-auto">${esc(querySql)}</pre></div>` : ""}
              ${requestHeaders ? `<div><b>Req Headers:</b><pre class="whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded p-1 text-[0.55rem] font-mono mt-0.5 overflow-x-auto">${esc(requestHeaders)}</pre></div>` : ""}
              ${c.requestBody ? `<div><b>Req:</b><pre class="whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded p-1 text-[0.55rem] font-mono mt-0.5 overflow-x-auto">${esc(c.requestBody)}</pre></div>` : ""}
              ${c.responseBody ? `<div><b>Resp:</b><pre class="whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded p-1 text-[0.55rem] font-mono mt-0.5 overflow-x-auto">${esc(c.responseBody)}</pre></div>` : ""}
            </div></details></td></tr>` : "";
          return `<tr class="border-t border-slate-100">
            <td class="py-1 pr-2 w-5 text-center text-[0.7rem] ${iconCls}">${icon}</td>
            <td class="py-1 pr-2"><span class="inline-flex px-1 py-px rounded text-[0.55rem] font-bold ${srcCls}">${esc(c.sourceType || "DB")}</span></td>
            <td class="py-1 pr-2 font-medium">${esc(c.label || "-")}</td>
            <td class="py-1 text-slate-400 text-[0.62rem]">${esc(c.message || "")}</td>
          </tr>${bodyRows}`;
        }).join("");

        return `<div class="mt-2 rounded-lg border border-${color}-200 overflow-hidden text-[0.7rem]">
          <div class="flex items-center gap-2 px-3 py-2 bg-${color}-50 border-b border-${color}-100">
            ${icon}
            <span class="font-bold text-${color}-800 uppercase tracking-wide text-[0.65rem]">Validacao Protheus - ${esc(pv.stageCode || "")}</span>
            <span class="inline-flex px-1.5 py-0.5 rounded text-[0.6rem] font-bold ${badgeClass}">${badgeLabel}</span>
            <span class="ml-auto text-slate-400 text-[0.62rem]">${esc(pv.message || "")}</span>
          </div>
          ${aiCommentaryItems.length ? `<div class="px-3 py-2 bg-blue-50 border-b border-blue-100">
            <span class="text-[0.6rem] font-bold uppercase tracking-wide text-blue-700">Comentarios IA</span>
            <div class="mt-1 space-y-1">
              ${aiCommentaryItems.map((entry) => {
                const lines = String(entry.message || "").split(/\\r?\\n/).map((line) => line.trim()).filter(Boolean);
                return `<div class="text-[0.65rem] text-slate-600"><span class="font-bold text-blue-700">${esc(entry.label || "Comentario IA")}:</span> ${lines.map((line) => esc(line)).join(" | ")}</div>`;
              }).join("")}
            </div>
          </div>` : ""}
          ${visibleChecks.length ? `<div class="overflow-x-auto"><table class="w-full text-[0.65rem]"><thead><tr class="text-slate-400">
            <th class="text-left py-1 w-5"></th><th class="text-left py-1">Origem</th><th class="text-left py-1">Verificacao</th><th class="text-left py-1">Mensagem</th>
          </tr></thead><tbody>${checkRows}</tbody></table></div>` : ""}
        </div>`;
      }

      function renderStage(stage) {
        const tone = toneFromStatus(stage.result || stage.finalStatus || stage.initialStatus || "");
        const palette = toneMap[tone] || toneMap.neutral;
        const httpCalls = Array.isArray(stage.httpCalls) ? stage.httpCalls : [];
        const dbChecks = Array.isArray(stage.dbChecks) ? stage.dbChecks : [];
        const notes = Array.isArray(stage.notes) ? stage.notes : [];
        const pv = stage.protheusValidation || null;

        return `<details class="border border-slate-200 rounded-lg overflow-hidden">
          <summary class="px-3 py-2 cursor-pointer flex items-center gap-2 bg-slate-50">
            <svg class="chevron h-3.5 w-3.5 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M9 5l7 7-7 7"></path></svg>
            <span class="inline-flex px-1.5 py-0.5 rounded text-[0.6rem] font-bold uppercase tracking-wide ${palette.badge}">${esc(statusLabel(stage.result || stage.finalStatus || ""))}</span>
            <span class="text-[0.65rem] font-mono text-slate-500 uppercase">${esc(stage.stageCode || "-")}</span>
            <span class="text-xs font-medium text-slate-700">${esc(stage.stageName || "Etapa")}</span>
            ${pv ? (pv.valid ? `<span class="inline-flex px-1 py-0.5 rounded text-[0.55rem] font-bold bg-emerald-100 text-emerald-700">&#10003; Protheus</span>` : `<span class="inline-flex px-1 py-0.5 rounded text-[0.55rem] font-bold bg-rose-100 text-rose-700">&#10007; Protheus</span>`) : ""}
            <span class="ml-auto text-[0.65rem] text-slate-400 mono">${esc(formatDuration(stage.durationMs || 0))}</span>
          </summary>
          <div class="px-3 py-3 space-y-2 text-[0.72rem] text-slate-600">
            <div class="grid sm:grid-cols-4 gap-2">
              <div><span class="text-slate-400">Acao:</span> <strong>${esc(stage.configuredAction || "-")}</strong></div>
              <div><span class="text-slate-400">Inicial:</span> <strong>${esc(stage.initialStatus || "-")}</strong></div>
              <div><span class="text-slate-400">Final:</span> <strong>${esc(stage.finalStatus || "-")}</strong></div>
              <div><span class="text-slate-400">Resultado:</span> <strong>${esc(stage.result || "-")}</strong></div>
            </div>
            ${stage.message ? `<p class="text-slate-500">${esc(stage.message)}</p>` : ""}
            ${notes.length ? `<div class="flex flex-wrap gap-1">${notes.map((note) => `<span class="inline-flex px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 text-[0.65rem]">${esc(note)}</span>`).join("")}</div>` : ""}
            ${httpCalls.length ? `<div class="overflow-x-auto"><table class="w-full text-[0.65rem]"><thead><tr class="text-slate-400"><th class="text-left py-1">HTTP</th><th class="text-left py-1">Path</th><th class="text-right py-1">Status</th><th class="text-right py-1">Duracao</th></tr></thead><tbody>${httpCalls.map((call) => `<tr class="border-t border-slate-100"><td class="py-1 pr-2">${esc(call.method || "GET")}</td><td class="py-1 pr-2 break-all">${esc(call.path || "-")}</td><td class="py-1 text-right mono">${esc(call.statusCode ?? "-")}</td><td class="py-1 text-right mono">${esc(formatDuration(call.durationMs || 0))}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${dbChecks.length ? `<div class="overflow-x-auto"><table class="w-full text-[0.65rem]"><thead><tr class="text-slate-400"><th class="text-left py-1">DB</th><th class="text-left py-1">Query</th><th class="text-center py-1">Match</th><th class="text-right py-1">Duracao</th></tr></thead><tbody>${dbChecks.map((check) => `<tr class="border-t border-slate-100"><td class="py-1 pr-2">${esc(check.label || check.queryName || "-")}</td><td class="py-1 pr-2 break-all font-mono">${esc(check.queryName || check.query_name || "-")}</td><td class="py-1 text-center">${check.matched === true ? "Sim" : check.matched === false ? "Nao" : "-"}</td><td class="py-1 text-right mono">${esc(formatDuration(check.durationMs || check.duration_ms || 0))}</td></tr>${(check.query_sql || check.querySql) ? `<tr><td></td><td colspan="3" class="py-1"><code class="block break-all bg-slate-100 rounded px-1.5 py-1 text-[0.6rem]">${esc(check.query_sql || check.querySql)}</code></td></tr>` : ""}`).join("")}</tbody></table></div>` : ""}
            ${renderProtheusValidation(pv)}
          </div>
        </details>`;
      }

      function renderExecution(execution) {
        const tone = toneFromStatus(execution.status || "");
        const palette = toneMap[tone] || toneMap.neutral;
        const stages = Array.isArray(execution.stageResults) ? execution.stageResults : [];

        return `<details class="border border-slate-200 rounded-lg overflow-hidden bg-white">
          <summary class="px-3 py-2 cursor-pointer flex items-center gap-2 bg-slate-50">
            <svg class="chevron h-3.5 w-3.5 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M9 5l7 7-7 7"></path></svg>
            <span class="text-[0.65rem] font-mono text-slate-400">Run ${esc(execution.runId || "-")}</span>
            <span class="inline-flex px-1.5 py-0.5 rounded text-[0.6rem] font-bold uppercase tracking-wide ${palette.badge}">${esc(statusLabel(execution.status || ""))}</span>
            <span class="text-[0.65rem] text-slate-500 truncate">${esc(execution.message || "")}</span>
            <span class="ml-auto text-[0.65rem] text-slate-400 mono">${esc(formatDuration(execution.durationMs || 0))}</span>
          </summary>
          <div class="px-3 py-3 space-y-2 border-t border-slate-100">
            <div class="grid sm:grid-cols-5 gap-2 text-[0.7rem] text-slate-500">
              <div><span class="text-slate-400">Inicio:</span> <strong>${esc(formatDateTime(execution.startedAt || ""))}</strong></div>
              <div><span class="text-slate-400">Fim:</span> <strong>${esc(formatDateTime(execution.finishedAt || ""))}</strong></div>
              <div><span class="text-slate-400">HTTP:</span> <strong>${esc(execution.totalHttpCalls || 0)}</strong></div>
              <div><span class="text-slate-400">DB:</span> <strong>${esc(execution.totalDbChecks || 0)}</strong></div>
              <div><span class="text-slate-400">Etapas:</span> <strong>${esc(stages.length)}</strong></div>
            </div>
            <div class="space-y-2">${stages.map((stage) => renderStage(stage)).join("")}</div>
          </div>
        </details>`;
      }

      function renderProposals() {
        const proposals = Array.isArray(reportData.proposals) ? reportData.proposals : [];
        const htmlRows = proposals.map((proposal) => {
          const executions = Array.isArray(proposal.executions) ? proposal.executions : [];
          const latest = executions.length ? executions[executions.length - 1] : null;
          const tone = toneFromStatus(latest?.status || "");
          const palette = toneMap[tone] || toneMap.neutral;
          const agreement = proposal.agreementId || "-";
          const product = proposal.productId || "-";

          return `<details class="border border-slate-200 rounded-xl overflow-hidden bg-white">
            <summary class="px-4 py-3 cursor-pointer flex items-center gap-2">
              <svg class="chevron h-4 w-4 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M9 5l7 7-7 7"></path></svg>
              <span class="text-[0.65rem] font-mono text-slate-400">#${esc(proposal.index || "-")}</span>
              <span class="text-xs font-bold text-slate-900 mono">${esc(proposal.proposalCode || "-")}</span>
              <span class="inline-flex px-1.5 py-0.5 rounded text-[0.6rem] font-bold uppercase tracking-wide ${palette.badge}">${esc(statusLabel(latest?.status || ""))}</span>
              <span class="text-[0.7rem] text-slate-500 truncate hidden md:inline">Contrato ${esc(proposal.contractCode || "-")} | ${esc(String(agreement))} | ${esc(String(product))}</span>
              <span class="ml-auto text-[0.65rem] text-slate-400">${esc((proposal.processorCode || "-").toUpperCase())} | ${esc(executions.length)} execucao(oes)</span>
            </summary>
            <div class="px-4 py-3 border-t border-slate-100 bg-slate-50/50 space-y-2">
              ${executions.length ? executions.slice().reverse().map((execution) => renderExecution(execution)).join("") : '<p class="text-xs text-slate-400">Sem execucoes registradas.</p>'}
            </div>
          </details>`;
        });

        document.getElementById("proposalList").innerHTML = htmlRows.length
          ? htmlRows.join("")
          : '<p class="text-xs text-slate-400">Sem propostas executadas nesta rodada.</p>';
      }

      function bootstrapReport() {
        const generatedAt = reportData.generatedAt || "";
        const envLabel = reportData.environmentLabel || reportData.environment || "Ambiente";
        document.getElementById("reportHeaderMeta").textContent = `${envLabel} | ${reportData.proposals?.length || 0} proposta(s) monitorada(s)`;
        document.getElementById("reportHeaderGeneratedAt").textContent = formatDateTime(generatedAt);
        document.getElementById("reportFooterMeta").textContent = `Gerado em ${formatDateTime(generatedAt)}`;
        document.getElementById("aiCommentaryText").textContent = reportData.aiCommentary || "Comentario de IA indisponivel.";

        renderSummaryCards();
        renderStatusChart();
        renderDurationChart();
        renderTrafficChart();
        renderProposals();
      }

      bootstrapReport();
    </script>
  </body>
</html>
"""
    report_favicon_url = html.escape(sanitize_text(report_data.get("iconUrl")), quote=True)
    return (
        template
        .replace("__REPORT_DATA__", report_json)
        .replace("__REPORT_FAVICON_URL__", report_favicon_url)
    )


