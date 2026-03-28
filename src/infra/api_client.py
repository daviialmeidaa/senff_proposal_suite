from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

import requests
from requests import Response
from requests.adapters import HTTPAdapter

from src.core.config import EnvironmentConfig


class ApiAuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiErrorDetails:
    status_code: int | None = None
    method: str = ""
    path: str = ""
    correlation_id: str = ""
    api_message: str = ""
    trace_excerpt: str = ""
    raw_body: str = ""


class ApiRequestError(RuntimeError):
    def __init__(self, message: str, *, details: ApiErrorDetails | None = None) -> None:
        super().__init__(message)
        self.details = details


@dataclass(frozen=True)
class CatalogOption:
    id: str
    code: str
    name: str


@dataclass(frozen=True)
class SerproBenefit:
    benefit_number: str
    sponsor_benefit_number: str
    serpro_agency_id: str
    beneficiary_name: str
    margin_value: int
    margin_value_card: int
    margin_value_rcc: int
    blocked_for_loan: bool
    eligible_loan: bool
    department: str = ""
    department_name: str = ""
    situation_description: str = ""

    def margin_value_for_product(self, product_name: str) -> int:
        normalized_product = product_name.upper()
        if "RCC" in normalized_product:
            return self.margin_value_rcc
        if "RMC" in normalized_product:
            return self.margin_value_card
        return self.margin_value

    def is_eligible_for_product(self, product_name: str) -> bool:
        margin_value = self.margin_value_for_product(product_name)
        normalized_product = product_name.upper()
        if "RCC" in normalized_product or "RMC" in normalized_product:
            return margin_value > 0
        return self.eligible_loan and margin_value > 0


@dataclass(frozen=True)
class CipBenefit:
    benefit_number: str
    cip_agency_id: str
    beneficiary_name: str
    margin_value: int
    margin_value_card: int
    margin_value_rcc: int
    blocked_for_loan: bool
    eligible_loan: bool
    agency_identification: str = ""
    agency_name: str = ""
    situation_description: str = ""

    def margin_value_for_product(self, product_name: str) -> int:
        normalized_product = product_name.upper()
        if "RCC" in normalized_product:
            return self.margin_value_rcc or self.margin_value
        if "RMC" in normalized_product:
            return self.margin_value_card or self.margin_value
        return self.margin_value

    def is_eligible_for_product(self, product_name: str) -> bool:
        margin_value = self.margin_value_for_product(product_name)
        normalized_product = product_name.upper()
        if "RCC" in normalized_product or "RMC" in normalized_product:
            return margin_value > 0
        return self.eligible_loan and margin_value > 0



_CATALOG_CACHE_LOCK = Lock()
_CATALOG_CACHE: dict[tuple[str, str, tuple[tuple[str, str], ...]], tuple[CatalogOption, ...]] = {}

class ApiSession:
    def __init__(self, config: EnvironmentConfig) -> None:
        self.config = config
        self.access_token: str | None = None
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def authenticate(self) -> str:
        headers = {
            "account": self.config.default_account,
            "tenant-id": self.config.tenant_id,
            "x-store-code": self.config.default_store_code,
            "Content-Type": "application/json",
        }
        payload = {
            "username": self.config.username,
            "password": self.config.password,
        }

        try:
            response = self.session.post(
                self.config.auth_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ApiAuthenticationError(
                f"Falha de conexao ao autenticar na API: {exc}"
            ) from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise ApiAuthenticationError(
                f"Falha na autenticacao da API ({response.status_code}): {response.text}"
            ) from exc

        try:
            auth_payload = response.json()
        except ValueError as exc:
            raise ApiAuthenticationError(
                "A autenticacao respondeu com um conteudo que nao e JSON."
            ) from exc

        self.access_token = extract_access_token(auth_payload)
        return self.access_token

    def ensure_authenticated(self) -> str:
        if self.access_token:
            return self.access_token
        return self.authenticate()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._send_request(
            method=method,
            path=path,
            params=params,
            json=json,
        )

        if response.status_code == 401:
            self.authenticate()
            response = self._send_request(
                method=method,
                path=path,
                params=params,
                json=json,
            )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise build_api_request_error(
                response=response,
                method=method,
                path=path,
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiRequestError(
                "A API respondeu com um conteudo que nao e JSON.",
                details=ApiErrorDetails(
                    status_code=response.status_code,
                    method=method.upper(),
                    path=path,
                    raw_body=response.text,
                ),
            ) from exc

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Response:
        access_token = self.ensure_authenticated()
        headers = {
            "account": self.config.default_account,
            "tenant-id": self.config.tenant_id,
            "x-store-code": self.config.default_store_code,
            "Authorization": f"Bearer {access_token}",
        }

        try:
            return self.session.request(
                method=method,
                url=f"{self.config.api_url}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ApiRequestError(
                f"Falha de conexao ao chamar a API: {exc}",
                details=ApiErrorDetails(
                    method=method.upper(),
                    path=path,
                    raw_body=str(exc),
                ),
            ) from exc



def build_api_request_error(
    *,
    response: Response,
    method: str,
    path: str,
) -> ApiRequestError:
    details = extract_api_error_details(
        response=response,
        method=method,
        path=path,
    )

    message_parts = [f"Falha na requisicao da API ({details.status_code or response.status_code})"]
    if details.method or details.path:
        message_parts.append(f"[{details.method} {details.path}]")
    if details.correlation_id:
        message_parts.append(f"correlation_id={details.correlation_id}")
    if details.api_message:
        message_parts.append(f"message={details.api_message}")
    if details.trace_excerpt:
        message_parts.append(f"trace={details.trace_excerpt}")
    elif details.raw_body:
        message_parts.append(f"body={details.raw_body[:240]}")

    return ApiRequestError(
        ": ".join(message_parts[:2]) + (" | " + " | ".join(message_parts[2:]) if len(message_parts) > 2 else ""),
        details=details,
    )



def extract_api_error_details(
    *,
    response: Response,
    method: str,
    path: str,
) -> ApiErrorDetails:
    raw_body = response.text or ""
    correlation_id = ""
    api_message = ""
    trace_excerpt = ""

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        correlation_id = str(payload.get("correlation_id") or "")
        api_message = str(payload.get("message") or "")
        trace_excerpt = summarize_trace(payload.get("trace"))
        if not api_message and trace_excerpt:
            api_message = "Internal Server Error"

    return ApiErrorDetails(
        status_code=response.status_code,
        method=method.upper(),
        path=path,
        correlation_id=correlation_id,
        api_message=api_message,
        trace_excerpt=trace_excerpt,
        raw_body=raw_body,
    )



def summarize_trace(trace: Any) -> str:
    text = str(trace or "").strip()
    if not text:
        return ""

    first_line = text.splitlines()[0].strip()
    return first_line[:240]



def extract_access_token(auth_response: dict[str, Any]) -> str:
    possible_keys = ("access_token", "token", "id_token", "jwt")
    for key in possible_keys:
        value = auth_response.get(key)
        if isinstance(value, str) and value:
            return value

    raise ApiAuthenticationError(
        "A autenticacao foi concluida, mas o token nao foi encontrado na resposta."
    )



def fetch_agreement_processor_code(
    api_session: ApiSession,
    agreement_id: str,
) -> str:
    payload = api_session.request(
        method="GET",
        path=f"/admin/agreement/{agreement_id}",
    )

    data = payload.get("data") or {}
    processors = data.get("processors") or []
    if not processors:
        raise ApiRequestError(
            "Nenhuma processadora foi encontrada em data.processors para o convenio informado."
        )

    processor_code = processors[0].get("code")
    if not processor_code:
        raise ApiRequestError(
            "A processadora retornada nao possui o campo code preenchido."
        )

    return str(processor_code)



def _build_catalog_cache_key(
    api_session: ApiSession,
    path: str,
    params: dict[str, Any] | None,
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    normalized_params = tuple(
        sorted((str(key), str(value)) for key, value in (params or {}).items())
    )
    return (api_session.config.key, path, normalized_params)



def list_catalog_options(
    api_session: ApiSession,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> list[CatalogOption]:
    cache_key = _build_catalog_cache_key(api_session, path, params)
    with _CATALOG_CACHE_LOCK:
        cached_options = _CATALOG_CACHE.get(cache_key)
    if cached_options is not None:
        return list(cached_options)

    payload = api_session.request(
        method="GET",
        path=path,
        params=params,
    )

    rows = payload.get("rows") or []
    options = tuple(
        CatalogOption(
            id=str(row.get("id") or ""),
            code=str(row.get("code") or ""),
            name=str(row.get("name") or row.get("description") or ""),
        )
        for row in rows
    )

    with _CATALOG_CACHE_LOCK:
        _CATALOG_CACHE[cache_key] = options
    return list(options)



def extract_response_data_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return None


def get_client(api_session: ApiSession, client_id: str | int) -> dict[str, Any]:
    payload = api_session.request(
        method="GET",
        path=f"/admin/client/{client_id}",
    )
    data = extract_response_data_dict(payload)
    if data is None:
        raise ApiRequestError("A consulta do cliente nao retornou data valido.")
    return data



def update_client(
    api_session: ApiSession,
    client_id: str | int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return api_session.request(
        method="PUT",
        path=f"/admin/client/{client_id}",
        json=payload,
    )



def list_serpro_benefits(
    api_session: ApiSession,
    *,
    document: str,
    name: str,
    product_id: str,
    agreement_id: str,
) -> list[SerproBenefit]:
    payload = api_session.request(
        method="GET",
        path="/admin/serpro/list-benefits",
        params={
            "document": document,
            "name": name,
            "product_id": product_id,
            "agreement_id": agreement_id,
        },
    )

    rows = payload.get("rows") or []
    benefits: list[SerproBenefit] = []
    for row in rows:
        serpro_benefit = row.get("serpro_benefit") or {}
        benefits.append(
            SerproBenefit(
                benefit_number=str(row.get("benefit_number") or ""),
                sponsor_benefit_number=str(row.get("sponsor_benefit_number") or ""),
                serpro_agency_id=str(row.get("serpro_agency_id") or ""),
                beneficiary_name=str(row.get("beneficiary_name") or ""),
                margin_value=_to_int(row.get("margin_value")),
                margin_value_card=_to_int(row.get("margin_value_card")),
                margin_value_rcc=_to_int(row.get("margin_value_rcc")),
                blocked_for_loan=bool(row.get("blocked_for_loan")),
                eligible_loan=bool(row.get("eligible_loan")),
                department=str(serpro_benefit.get("department") or ""),
                department_name=str(serpro_benefit.get("department_name") or ""),
                situation_description=str(row.get("situation_description") or ""),
            )
        )
    return benefits



def list_cip_benefits(
    api_session: ApiSession,
    *,
    document: str,
    agency_id: str,
    agreement_id: str,
    product_id: str,
    withdraw_type_id: str,
    name: str,
) -> list[CipBenefit]:
    payload = api_session.request(
        method="GET",
        path="/admin/cip/list-benefits",
        params={
            "document": document,
            "agency_id": agency_id,
            "agreement_id": agreement_id,
            "product_id": product_id,
            "withdraw_type_id": withdraw_type_id,
            "name": name,
        },
    )

    rows = payload.get("rows") or []
    benefits: list[CipBenefit] = []
    for row in rows:
        cip_benefit = row.get("cip_benefit") or {}
        consult_margin = cip_benefit.get("consult_margin") or {}
        benefits.append(
            CipBenefit(
                benefit_number=str(row.get("benefit_number") or ""),
                cip_agency_id=str(
                    row.get("cip_agency_id")
                    or consult_margin.get("agency_identification")
                    or ""
                ),
                beneficiary_name=str(row.get("beneficiary_name") or ""),
                margin_value=_to_int(row.get("margin_value")),
                margin_value_card=_to_int(row.get("margin_value_card")),
                margin_value_rcc=_to_int(row.get("margin_value_rcc")),
                blocked_for_loan=bool(row.get("blocked_for_loan")),
                eligible_loan=bool(row.get("eligible_loan")),
                agency_identification=str(consult_margin.get("agency_identification") or ""),
                agency_name=str(consult_margin.get("agency_name") or ""),
                situation_description=str(row.get("situation_description") or ""),
            )
        )
    return benefits



def create_simulation(
    api_session: ApiSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return api_session.request(
        method="POST",
        path="/admin/simulation",
        json=payload,
    )



def create_proposal(
    api_session: ApiSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return api_session.request(
        method="POST",
        path="/admin/proposal",
        json=payload,
    )



def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0









