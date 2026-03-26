from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from requests import Response

from src.config import EnvironmentConfig


class ApiAuthenticationError(RuntimeError):
    pass


class ApiRequestError(RuntimeError):
    pass


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


class ApiSession:
    def __init__(self, config: EnvironmentConfig) -> None:
        self.config = config
        self.access_token: str | None = None

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
            response = requests.post(
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
            raise ApiRequestError(
                f"Falha na requisicao da API ({response.status_code}): {response.text}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiRequestError(
                "A API respondeu com um conteudo que nao e JSON."
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
            return requests.request(
                method=method,
                url=f"{self.config.api_url}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ApiRequestError(
                f"Falha de conexao ao chamar a API: {exc}"
            ) from exc


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


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
