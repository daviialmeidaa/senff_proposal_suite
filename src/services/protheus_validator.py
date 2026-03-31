"""
Protheus pipeline validation service.

Implements the two-phase validation described in:
  cenarios/validacoes_esteira/protheus/validacao_protheus.md

Phase 1 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Formalization  (stage_code = "protheus")
Phase 2 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Issuance       (stage_code = "protheus-issuance")

Both are called from the execution engine in server.py when the stage is
configured as action = "wait".
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from time import monotonic
from typing import Any

import requests

from src.core.config import EnvironmentConfig
from src.core.proposal_history import (
    ProtheusCheckItem,
    ProtheusLogEntry,
    ProtheusValidationResult,
)
from src.infra.database import (
    check_protheus_issuance_exists,
    fetch_protheus_client_code,
    fetch_protheus_logs,
)

# ---------------------------------------------------------------------------
# SOAP endpoints
# ---------------------------------------------------------------------------
_VALFOR_ENDPOINT = (
    "https://senffnet148708.protheus.cloudtotvs.com.br:1505"
    "/ws9901/SENFFFORNECEDORES.apw"
)
_INCPAGARSE_ENDPOINT = (
    "https://senffnet148708.protheus.cloudtotvs.com.br:1505"
    "/ws9901/SENFFTITULOSSE.apw"
)

_PROTHEUS_SOAP_ACTION_BASE = "https://senffnet148708.protheus.cloudtotvs.com.br:1505"
_PROTHEUS_CONTENT_TYPE = "text/xml; charset=utf-8"
_PROTHEUS_AUTHORIZATION = "Basic c3ZjLm9wZXI6b01mQEswZVI5Rg=="
_SOAP_TIMEOUT_SECONDS = 20
_PROTHEUS_LOGS_QUERY_SQL = "SELECT id, http_verb, url, request_headers, request_body, response_body, http_status_code FROM protheus_logs WHERE correlation_id = %s ORDER BY id ASC"
_PROTHEUS_ISSUANCE_QUERY_SQL = "SELECT 1 FROM protheus_issuance WHERE proposal_id = %s AND number = %s LIMIT 1"
_PROTHEUS_CLIENT_CODE_QUERY_SQL = "SELECT code FROM protheus_client_codes WHERE document = %s LIMIT 1"


def _basic_auth_header() -> str:
    return _PROTHEUS_AUTHORIZATION


def _elapsed_ms(start: float) -> int:
    return max(0, int((monotonic() - start) * 1000))


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"

    text = str(value)
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text or "") and not (text.startswith("0") and len(text) > 1):
        return text

    return "'" + text.replace("'", "''") + "'"


def _render_sql_query(query_sql: str, *params: Any) -> str:
    rendered = query_sql
    for value in params:
        rendered = rendered.replace("%s", _sql_literal(value), 1)
    return rendered


# ---------------------------------------------------------------------------
# Internal helpers ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â log parsing
# ---------------------------------------------------------------------------
def _contains(text: str, fragment: str) -> bool:
    normalized_fragment = (fragment or "").lower()
    if not normalized_fragment:
        return False
    return normalized_fragment in _normalize_log_text(text).lower()


def _flatten_text_chunks(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        chunks: list[str] = []
        for item in value.values():
            chunks.extend(_flatten_text_chunks(item))
        return chunks
    if isinstance(value, (list, tuple, set)):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_flatten_text_chunks(item))
        return chunks
    return [str(value)]


def _normalize_log_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    chunks = [raw]
    for parser in (json.loads,):
        try:
            parsed = parser(raw)
        except Exception:  # noqa: BLE001
            continue
        chunks.extend(_flatten_text_chunks(parsed))

    deduped_chunks = list(dict.fromkeys(chunk for chunk in chunks if chunk))
    normalized = " ".join(deduped_chunks)

    return (
        normalized
        .replace("\\/", "/")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )


def _extract_xml_bool_tag(text: str, tag_name: str) -> bool | None:
    if not text or not tag_name:
        return None
    normalized = _normalize_log_text(text)
    pattern = (
        rf"<\s*{re.escape(tag_name)}[^>]*>\s*(true|false)\s*"
        rf"<\s*(?:\\)?/\s*{re.escape(tag_name)}\s*>"
    )
    match = re.search(pattern, normalized, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _extract_retws_flag(text: str) -> bool | None:
    return _extract_xml_bool_tag(text, "RETWS")


def _extract_status_flag(text: str) -> bool | None:
    return _extract_xml_bool_tag(text, "STATUS")


def _has_status_true(text: str) -> bool:
    return _extract_status_flag(text) is True

def _request_contains(log: ProtheusLogEntry, fragment: str) -> bool:
    return _contains(log.request_headers, fragment) or _contains(log.request_body, fragment)


def _build_evidence(
    log: ProtheusLogEntry,
    label: str,
    query_sql: str,
    result: bool | None = None,
    message: str = "",
) -> ProtheusCheckItem:
    return ProtheusCheckItem(
        label=label,
        source_type="DATABASE",
        origin="DATABASE - protheus_logs",
        result=result,
        message=message,
        query_sql=query_sql,
        http_verb=log.http_verb,
        url=log.url,
        request_headers=log.request_headers,
        request_body=log.request_body,
        response_body=log.response_body,
        http_status_code=log.http_status_code,
    )


# ---------------------------------------------------------------------------
# SOAP helpers
# ---------------------------------------------------------------------------
def _call_valfor_soap(cpf: str) -> tuple[bool, str, str, str, int]:
    """
    Calls SENFFFORNECEDORES VALFOR with the client CPF.
    Returns (api_valfor_ok, request_body, response_body, status_code_str, duration_ms).
    api_valfor_ok = True when response contains <RETWS>false</RETWS>.
    """
    payload = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        '<ns:VALFOR xmlns:ns="https://senffnet148708.protheus.cloudtotvs.com.br:1505/">'
        f"<ns:CPFCNPJ>{cpf}</ns:CPFCNPJ>"
        "</ns:VALFOR>"
        "</soap:Body>"
        "</soap:Envelope>"
    )
    headers = {
        "Content-Type": _PROTHEUS_CONTENT_TYPE,
        "SOAPAction": f"{_PROTHEUS_SOAP_ACTION_BASE}/VALFOR",
        "Authorization": _basic_auth_header(),
    }
    start = monotonic()
    try:
        resp = requests.post(
            _VALFOR_ENDPOINT,
            data=payload.encode("utf-8"),
            headers=headers,
            timeout=_SOAP_TIMEOUT_SECONDS,
        )
        status = str(resp.status_code)
        body = resp.text or ""
        # RETWS present (true or false) means CPF is registered in Protheus
        ok = _extract_retws_flag(body) is not None
        return ok, payload, body, status, _elapsed_ms(start)
    except Exception as exc:  # noqa: BLE001
        return False, payload, f"Erro de rede: {exc}", "ERROR", _elapsed_ms(start)


def _call_incpagarse_soap(
    *,
    client_code: str,
    proposal_id: str | int,
    codigo_criacao: str,
) -> tuple[bool, str, str, str, int]:
    """
    Calls SENFFTITULOSSE INCPAGARSE to confirm the title exists (expects duplicate fault).
    client_code is the value from protheus_client_codes.code for the proposal CPF.
    Returns (api_success, request_body, response_body, status_code_str, duration_ms).
    api_success = True when response contains the duplicate-fault fragment.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    num = f"SC{str(proposal_id).zfill(7)}"

    payload = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        '<s0:INCPAGARSE xmlns="https://senffnet148708.protheus.cloudtotvs.com.br:1505/">'
        "<s0:TITULOSSE>"
        f"<s0:CLIENTEFORNECEDOOR>{client_code}</s0:CLIENTEFORNECEDOOR>"
        f"<s0:EMISSAO>{today}</s0:EMISSAO>"
        "<s0:FILIAL>030101</s0:FILIAL>"
        "<s0:LOJA>0001</s0:LOJA>"
        "<s0:NATUREZ>2010396</s0:NATUREZ>"
        f"<s0:NUM>{num}</s0:NUM>"
        "<s0:NUPORT></s0:NUPORT>"
        f"<s0:ORIGEM>{codigo_criacao}</s0:ORIGEM>"
        "<s0:PREFIXO>SQI</s0:PREFIXO>"
        "<s0:TIPO>OP</s0:TIPO>"
        "<s0:VALOR>50.00</s0:VALOR>"
        f"<s0:VENCTO>{today}</s0:VENCTO>"
        "</s0:TITULOSSE>"
        "</s0:INCPAGARSE>"
        "</soap:Body>"
        "</soap:Envelope>"
    )
    headers = {
        "Content-Type": _PROTHEUS_CONTENT_TYPE,
        "SOAPAction": f"{_PROTHEUS_SOAP_ACTION_BASE}/INCPAGARSE",
        "Authorization": _basic_auth_header(),
    }
    start = monotonic()
    try:
        resp = requests.post(
            _INCPAGARSE_ENDPOINT,
            data=payload.encode("utf-8"),
            headers=headers,
            timeout=_SOAP_TIMEOUT_SECONDS,
        )
        status = str(resp.status_code)
        body = resp.text or ""
        normalized_body = (
            body.lower()
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡", "a")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ", "a")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢", "a")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â£", "a")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©", "e")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Âª", "e")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â­", "i")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â³", "o")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â´", "o")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Âµ", "o")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Âº", "u")
            .replace("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â§", "c")
        )
        # Duplicate fault = title exists = success
        ok = "fault" in normalized_body and "existe titulo" in normalized_body
        return ok, payload, body, status, _elapsed_ms(start)
    except Exception as exc:  # noqa: BLE001
        return False, payload, f"Erro de rede: {exc}", "ERROR", _elapsed_ms(start)


# ---------------------------------------------------------------------------
# Phase 1 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Formalization
# ---------------------------------------------------------------------------
def validate_protheus_formalization(
    *,
    config: EnvironmentConfig,
    correlation_id: str,
    cpf: str,
) -> tuple[ProtheusValidationResult, int, str | None]:
    """
    Validates that the Protheus executed VALFOR + ATUALIZAR for the proposal.
    Also checks protheus_client_codes for the CPF and includes the client code.

    Returns (result, last_log_id, client_code).
    last_log_id is the cutoff log id so Phase 2 can skip already-seen logs.
    client_code is the value from protheus_client_codes.code (None if not found).
    """
    checks: list[ProtheusCheckItem] = []
    logs_query_sql = _render_sql_query(_PROTHEUS_LOGS_QUERY_SQL, correlation_id)
    client_code_query_sql = _render_sql_query(_PROTHEUS_CLIENT_CODE_QUERY_SQL, cpf)

    # --- 0. Lookup protheus_client_codes ---------------------------------
    start = monotonic()
    client_code = fetch_protheus_client_code(config, cpf)
    client_code_ms = _elapsed_ms(start)

    checks.append(ProtheusCheckItem(
        label="Codigo de cliente Protheus",
        source_type="DATABASE",
        origin="DATABASE - protheus_client_codes",
        result=client_code is not None,
        message=(
            f"Codigo de cliente encontrado: '{client_code}'."
            if client_code is not None
            else "CPF nao encontrado na tabela protheus_client_codes. Codigo de cliente indisponivel."
        ),
        query_sql=client_code_query_sql,
        http_verb="SELECT",
        url="protheus_client_codes",
        duration_ms=client_code_ms,
    ))

    if client_code is None:
        return ProtheusValidationResult(
            stage_code="protheus",
            valid=False,
            bypassed=False,
            message="Formalizacao Protheus invalida: CPF nao encontrado na tabela protheus_client_codes.",
            checks=checks,
        ), 0, None

    # --- 1. Read protheus_logs -------------------------------------------
    start = monotonic()
    logs = fetch_protheus_logs(config, correlation_id)
    read_ms = _elapsed_ms(start)

    checks.append(ProtheusCheckItem(
        label="Leitura de logs Protheus",
        source_type="DATABASE",
        origin="AUDITORIA - Leitura de logs Protheus",
        result=len(logs) > 0,
        message=f"{len(logs)} linha(s) retornada(s) da tabela protheus_logs.",
        query_sql=logs_query_sql,
        http_verb="SELECT",
        url="protheus_logs",
        duration_ms=read_ms,
    ))

    if not logs:
        return ProtheusValidationResult(
            stage_code="protheus",
            valid=False,
            bypassed=False,
            message="Nenhum log Protheus encontrado para o correlation_id da proposta.",
            checks=checks,
        ), 0, client_code
    # --- 2. Determine cutoff_id (ATUALIZAR only) --------------------------
    cutoff_id: int = 0
    db_atualizar_ok = False

    for log in logs:
        if (
            _request_contains(log, "ATUALIZAR")
            and _has_status_true(log.response_body)
        ):
            cutoff_id = log.log_id
            db_atualizar_ok = True
            break

    if not cutoff_id:
        cutoff_id = logs[-1].log_id  # fallback: use all logs as evidence

    # --- 3. Build evidence from logs up to cutoff -------------------------
    for log in logs:
        if log.log_id > cutoff_id:
            break
        checks.append(_build_evidence(log, "Evidencia Formalizacao", logs_query_sql))

    # --- 4. Re-derive ATUALIZAR from evidence logs ------------------------
    for log in logs:
        if log.log_id > cutoff_id:
            break
        if (
            _request_contains(log, "ATUALIZAR")
            and _has_status_true(log.response_body)
        ):
            db_atualizar_ok = True

    # --- 5. VALFOR externo (obrigatorio) ----------------------------------
    # RETWS presente na resposta (true ou false) confirma que o CPF consta no Protheus.
    api_valfor_ok = False
    ok, req_body, resp_body, status, ms = _call_valfor_soap(cpf)
    api_valfor_ok = ok
    retws_value = _extract_retws_flag(resp_body)
    retws_label = "true" if retws_value is True else ("false" if retws_value is False else "ausente")
    checks.append(ProtheusCheckItem(
        label="VALFOR externo",
        source_type="API",
        origin="AUDITORIA - VALFOR externo",
        result=ok,
        message=(
            f"SOAP VALFOR retornou HTTP {status}. RETWS={retws_label}. "
            + ("CPF consta no Protheus." if ok else "CPF nao confirmado pelo VALFOR (RETWS ausente ou erro de rede).")
        ),
        http_verb="POST",
        url=_VALFOR_ENDPOINT,
        request_body=req_body,
        response_body=resp_body,
        http_status_code=status,
        duration_ms=ms,
    ))

    # --- 6. Result --------------------------------------------------------
    valid = db_atualizar_ok and api_valfor_ok

    if valid:
        msg = "Formalizacao Protheus validada: ATUALIZAR confirmado e CPF presente no Protheus (VALFOR)."
    elif not api_valfor_ok:
        msg = "Formalizacao Protheus invalida: VALFOR externo nao confirmou o CPF no Protheus (RETWS ausente)."
    else:
        msg = "Formalizacao Protheus invalida: ATUALIZAR nao confirmado nos logs."

    return ProtheusValidationResult(
        stage_code="protheus",
        valid=valid,
        bypassed=False,
        message=msg,
        checks=checks,
    ), cutoff_id, client_code


# ---------------------------------------------------------------------------
# Phase 2 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Issuance
# ---------------------------------------------------------------------------
def validate_protheus_issuance(
    *,
    config: EnvironmentConfig,
    correlation_id: str,
    proposal_id: str | int,
    codigo_criacao: str,
    cpf: str,
    last_protheus_id: int = 0,
    stage_already_approved: bool = False,
    protheus_client_code: str | None = None,
) -> ProtheusValidationResult:
    """
    Validates that the Protheus generated the INCPAGARSE title for the proposal.
    Uses protheus_client_code (from protheus_client_codes.code) in the INCPAGARSE SOAP call.
    If protheus_client_code is not provided, fetches it from the DB using cpf.

    If after exhausting retries the stage is already APPROVED but db_success is
    still False, applies the "Sem Saque" bypass.
    """
    checks: list[ProtheusCheckItem] = []
    num = f"SC{str(proposal_id).zfill(7)}"
    logs_query_sql = _render_sql_query(_PROTHEUS_LOGS_QUERY_SQL, correlation_id)
    incpagarse_log_query_sql = _render_sql_query(
        "SELECT * FROM protheus_logs WHERE correlation_id = %s AND request_body ILIKE '%INCPAGARSE%' AND response_body ILIKE '%<STATUS>true</STATUS>%' ORDER BY id ASC",
        correlation_id,
    )
    issuance_query_sql = _render_sql_query(_PROTHEUS_ISSUANCE_QUERY_SQL, proposal_id, num)
    client_code_query_sql = _render_sql_query(_PROTHEUS_CLIENT_CODE_QUERY_SQL, cpf)

    # --- 0. Resolve protheus_client_code ---------------------------------
    if protheus_client_code is None:
        start = monotonic()
        protheus_client_code = fetch_protheus_client_code(config, cpf)
        client_code_ms = _elapsed_ms(start)
        checks.append(ProtheusCheckItem(
            label="Codigo de cliente Protheus",
            source_type="DATABASE",
            origin="DATABASE - protheus_client_codes",
            result=protheus_client_code is not None,
            message=(
                f"Codigo de cliente encontrado: '{protheus_client_code}'."
                if protheus_client_code is not None
                else "CPF nao encontrado na tabela protheus_client_codes. Codigo de cliente indisponivel."
            ),
            query_sql=client_code_query_sql,
            http_verb="SELECT",
            url="protheus_client_codes",
            duration_ms=client_code_ms,
        ))
    else:
        checks.append(ProtheusCheckItem(
            label="Codigo de cliente Protheus",
            source_type="DATABASE",
            origin="DATABASE - protheus_client_codes",
            result=True,
            message=f"Codigo de cliente disponivel (herdado da etapa protheus): '{protheus_client_code}'.",
            query_sql=client_code_query_sql,
            http_verb="SELECT",
            url="protheus_client_codes",
        ))

    if protheus_client_code is None:
        return ProtheusValidationResult(
            stage_code="protheus-issuance",
            valid=False,
            bypassed=False,
            message="Emissao Protheus invalida: CPF nao encontrado na tabela protheus_client_codes. Codigo indisponivel para INCPAGARSE.",
            checks=checks,
        )

    # --- 1. Read protheus_logs -------------------------------------------
    start = monotonic()
    logs = fetch_protheus_logs(config, correlation_id)
    read_ms = _elapsed_ms(start)

    checks.append(ProtheusCheckItem(
        label="Leitura de logs Emissao",
        source_type="DATABASE",
        origin="AUDITORIA - Leitura de logs Emissao",
        result=len(logs) > 0,
        message=f"{len(logs)} linha(s) retornada(s) da tabela protheus_logs.",
        query_sql=logs_query_sql,
        http_verb="SELECT",
        url="protheus_logs",
        duration_ms=read_ms,
    ))

    # Add evidence for new logs only (id > last_protheus_id)
    for log in logs:
        if log.log_id > last_protheus_id:
            checks.append(_build_evidence(log, "Evidencia Emissao", logs_query_sql))

    # --- 2. Find INCPAGARSE + <STATUS>true</STATUS> ----------------------
    db_success = False
    for log in logs:
        if (
            _request_contains(log, "INCPAGARSE")
            and _has_status_true(log.response_body)
        ):
            db_success = True
            break

    checks.append(ProtheusCheckItem(
        label="Log INCPAGARSE no banco",
        source_type="DATABASE",
        origin="DATABASE - protheus_logs",
        result=db_success,
        message=(
            "Log INCPAGARSE com <STATUS>true</STATUS> encontrado."
            if db_success
            else "Log INCPAGARSE com <STATUS>true</STATUS> nao encontrado."
        ),
        query_sql=incpagarse_log_query_sql,
        http_verb="SELECT",
        url="protheus_logs",
    ))

    if not db_success:
        # Apply sem-saque bypass if stage was already approved externally
        if stage_already_approved:
            checks.append(ProtheusCheckItem(
                label="Bypass Sem Saque",
                source_type="SYSTEM",
                origin="SYSTEM",
                result=True,
                message="Bypass aplicado: proposta do tipo Sem Saque nao gera titulo INCPAGARSE.",
                http_verb="INFO",
                url="Bypass",
                request_body="Bypass aplicado.",
                response_body="Proposta Sem Saque.",
                http_status_code="200",
            ))
            return ProtheusValidationResult(
                stage_code="protheus-issuance",
                valid=True,
                bypassed=True,
                message="Emissao Protheus: bypass Sem Saque aplicado. Proposta aprovada sem titulo INCPAGARSE.",
                checks=checks,
            )

        return ProtheusValidationResult(
            stage_code="protheus-issuance",
            valid=False,
            bypassed=False,
            message="Emissao Protheus invalida: log INCPAGARSE nao encontrado nos logs.",
            checks=checks,
        )

    # --- 3. Proof-of-reality SOAP call -----------------------------------
    api_ok, req_body, resp_body, status, ms = _call_incpagarse_soap(
        client_code=protheus_client_code,
        proposal_id=proposal_id,
        codigo_criacao=codigo_criacao,
    )
    checks.append(ProtheusCheckItem(
        label="Prova real de duplicidade",
        source_type="API",
        origin="AUDITORIA - Prova de Conflito",
        result=api_ok,
        message=(
            f"SOAP INCPAGARSE retornou HTTP {status}. "
            + ("Conflito confirmado: titulo existe." if api_ok else "Conflito nao detectado: titulo pode nao existir.")
        ),
        http_verb="POST",
        url=_INCPAGARSE_ENDPOINT,
        request_body=req_body,
        response_body=resp_body,
        http_status_code=status,
        duration_ms=ms,
    ))

    if not api_ok:
        return ProtheusValidationResult(
            stage_code="protheus-issuance",
            valid=False,
            bypassed=False,
            message="Emissao Protheus invalida: prova de realidade INCPAGARSE nao confirmou o titulo.",
            checks=checks,
        )

    # --- 4. Confirm in protheus_issuance table ---------------------------
    start = monotonic()
    table_ok = check_protheus_issuance_exists(config, proposal_id, num)
    table_ms = _elapsed_ms(start)

    checks.append(ProtheusCheckItem(
        label="Confirmacao em protheus_issuance",
        source_type="DATABASE",
        origin="AUDITORIA - Confirmacao em protheus_issuance",
        result=table_ok,
        message=(
            f"Registro '{num}' encontrado na tabela protheus_issuance."
            if table_ok
            else f"Registro '{num}' nao encontrado na tabela protheus_issuance."
        ),
        query_sql=issuance_query_sql,
        http_verb="SELECT",
        url="protheus_issuance",
        http_status_code="200" if table_ok else "404",
        duration_ms=table_ms,
    ))

    valid = table_ok
    if valid:
        msg = f"Emissao Protheus validada: titulo '{num}' confirmado no banco e na API."
    else:
        msg = f"Emissao Protheus invalida: titulo '{num}' nao encontrado na tabela protheus_issuance."

    return ProtheusValidationResult(
        stage_code="protheus-issuance",
        valid=valid,
        bypassed=False,
        message=msg,
        checks=checks,
    )




