from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


class SimulationPayloadError(RuntimeError):
    pass


ZETRA_PROCESSOR_CODES = frozenset({"zetra", "econsig-zetra"})


@dataclass(frozen=True)
class SimulationClient:
    name: str
    document: str
    phone: str


@dataclass(frozen=True)
class SerproIdentifiers:
    agency_id: str
    agency_sub_id: str = ""
    agency_sub_upag_id: str = ""


@dataclass(frozen=True)
class SimulationPayloadInput:
    agreement_id: str
    product_id: str
    sale_modality_id: str
    withdraw_type_id: str
    processor_code: str
    margin_value: str | int
    client: SimulationClient
    income_value: str | int | None = None
    benefit_number: str = ""
    user_password: str = ""
    sponsor_benefit_number: str = ""
    client_benefit_number: str = ""
    original_ccb_code: str = ""
    original_ccb_origin: str = ""
    serpro_identifiers: SerproIdentifiers | None = None
    cip_agency_id: str = ""



def normalize_processor_code(processor_code: str) -> str:
    return processor_code.strip().lower()



def is_dataprev_processor(processor_code: str) -> bool:
    return normalize_processor_code(processor_code) == "dataprev"



def is_zetra_processor(processor_code: str) -> bool:
    return normalize_processor_code(processor_code) in ZETRA_PROCESSOR_CODES



def is_serpro_processor(processor_code: str) -> bool:
    return normalize_processor_code(processor_code) == "serpro"



def is_cip_processor(processor_code: str) -> bool:
    return normalize_processor_code(processor_code) == "cip"



def build_simulation_payload(data: SimulationPayloadInput) -> dict[str, Any]:
    client_name = data.client.name.strip()
    client_document = sanitize_digits(data.client.document)
    client_phone = sanitize_digits(data.client.phone)
    margin_value_cents = money_to_cents(data.margin_value)
    income_value_cents = None
    if data.income_value not in (None, ""):
        income_value_cents = money_to_cents(data.income_value)

    if not client_name:
        raise SimulationPayloadError("O nome do cliente e obrigatorio para a simulacao.")
    if not client_document:
        raise SimulationPayloadError("O documento do cliente e obrigatorio para a simulacao.")
    if not client_phone:
        raise SimulationPayloadError("O telefone do cliente e obrigatorio para a simulacao.")
    if margin_value_cents <= 0:
        raise SimulationPayloadError("O margin_value da simulacao deve ser maior que zero.")

    agreement_payload: dict[str, Any] = {
        "id": int(data.agreement_id),
    }
    if is_serpro_processor(data.processor_code):
        if data.serpro_identifiers is None or not data.serpro_identifiers.agency_id:
            raise SimulationPayloadError(
                "O serpro_agency_id e obrigatorio para esta simulacao."
            )
        agreement_payload["serpro_agency_id"] = int(data.serpro_identifiers.agency_id)
        if data.serpro_identifiers.agency_sub_id:
            agreement_payload["serpro_agency_sub_id"] = int(data.serpro_identifiers.agency_sub_id)
        if data.serpro_identifiers.agency_sub_upag_id:
            agreement_payload["serpro_agency_sub_upag_id"] = int(data.serpro_identifiers.agency_sub_upag_id)
    if is_cip_processor(data.processor_code) and data.cip_agency_id:
        agreement_payload["cip_agency_id"] = int(data.cip_agency_id)

    sale_modality_payload: dict[str, Any] = {
        "id": int(data.sale_modality_id),
        "original_ccb_code": data.original_ccb_code.strip() or None,
        "original_ccb_origin": data.original_ccb_origin.strip() or None,
    }
    if bool(sale_modality_payload["original_ccb_code"]) != bool(sale_modality_payload["original_ccb_origin"]):
        raise SimulationPayloadError(
            "original_ccb_code e original_ccb_origin devem ser informados juntos."
        )

    payload: dict[str, Any] = {
        "data": {
            "agreement": agreement_payload,
            "product": {
                "id": int(data.product_id),
            },
            "sale_modality": sale_modality_payload,
            "withdraw_type": {
                "id": int(data.withdraw_type_id),
            },
            "client": {
                "name": client_name,
                "document": client_document,
                "phone": client_phone,
            },
            "margin_value": margin_value_cents,
            "income_value": income_value_cents,
            "sponsor_benefit_number": data.sponsor_benefit_number.strip() or None,
            "client_benefit_number": data.client_benefit_number.strip() or None,
        }
    }

    benefit_number = data.benefit_number.strip()
    if benefit_number:
        payload["data"]["benefit_number"] = benefit_number

    user_password = data.user_password.strip()
    if user_password:
        payload["data"]["user_password"] = user_password

    if is_zetra_processor(data.processor_code) and not benefit_number:
        raise SimulationPayloadError(
            "benefit_number e obrigatorio para simulacao com processadora Zetra."
        )

    return payload



def money_to_cents(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        decimal_value = Decimal(str(value))
        return int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    text = str(value).strip()
    if not text:
        raise SimulationPayloadError("Nao foi possivel converter um valor monetario vazio em centavos.")

    normalized = text.replace("R$", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")

    try:
        decimal_value = Decimal(normalized)
    except InvalidOperation as exc:
        raise SimulationPayloadError(
            f"Nao foi possivel converter o valor monetario '{value}' em centavos."
        ) from exc

    return int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))



def sanitize_digits(value: str) -> str:
    return "".join(character for character in str(value) if character.isdigit())



def sale_modality_requires_original_ccb(sale_modality_name: str) -> bool:
    normalized_name = sale_modality_name.strip().lower()
    return "agrega" in normalized_name or "refin" in normalized_name

