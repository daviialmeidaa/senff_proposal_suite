from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.simulation import sanitize_digits


class ProposalPayloadError(RuntimeError):
    pass


CONTRACT_DOCUMENT_TYPE_OPTIONS = {
    "1": "rg",
    "2": "cnh",
}


CLIENT_BENEFIT_FIELDS = (
    "client_id",
    "agreement_id",
    "allow_update",
    "document",
    "admission_date",
    "beneficiary_name",
    "benefit_number",
    "situation_code",
    "situation_description",
    "benefit_type_code",
    "benefit_type_description",
    "juridical_authorization",
    "state_payment",
    "credit_type_code",
    "credit_type_description",
    "cbc_if_payment",
    "payment_agency",
    "account",
    "has_legal_representative",
    "has_attorney",
    "has_representation_entity",
    "has_alimony_code",
    "has_alimony_description",
    "blocked_for_loan",
    "margin_value",
    "margin_value_card",
    "limit_value_card",
    "active_suspended_loan",
    "active_loan",
    "suspended_loan",
    "loan_refin",
    "loan_porta",
    "date_consult",
    "eligible_loan",
    "margin_value_rcc",
    "limit_value_rcc",
    "net_value_rcc",
    "net_value",
    "committed_value",
    "max_commitment_value",
    "pep_code",
    "pep_description",
    "available_value_loan_endorsement",
    "block_type_code",
    "block_type_description",
    "dispatch_date",
)

OPTIONAL_BENEFIT_FIELDS = (
    "sponsor_benefit_number",
    "serpro_agency_id",
    "cip_agency_id",
)


@dataclass(frozen=True)
class ProposalCatalogs:
    civil_status_code: str
    education_code: str
    gender_code: str
    state_code: str
    bank_code: str
    bank_account_type_code: str


@dataclass(frozen=True)
class ProposalGeneratedClientData:
    birth_date: str
    mothers_name: str
    fathers_name: str
    city: str
    email: str
    main_phone: str
    postal_code: str
    street: str
    number: str
    complement_address: str
    district: str
    contract_document_type: str
    contract_document_number: str
    contract_document_state_code: str
    contract_document_issuer: str
    contract_document_expedition_date: str
    bank_agency: str
    bank_agency_digit: str
    bank_account: str
    bank_account_digit: str
    income_value: int = 100000


@dataclass(frozen=True)
class ProposalIdentifiers:
    client_main_document_id: str
    client_contract_document_id: str
    client_address_id: str
    client_bank_id: str
    client_benefit_id: str



def normalize_contract_document_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"rg", "cnh"}:
        return normalized

    mapped_value = CONTRACT_DOCUMENT_TYPE_OPTIONS.get(str(value or "").strip())
    if mapped_value:
        return mapped_value

    raise ProposalPayloadError(
        "O tipo de documento contratual precisa ser RG ou CNH."
    )



def build_complete_client_payload(
    *,
    client_data: dict[str, Any],
    client_name: str,
    agreement_id: str,
    main_document_id: str,
    main_document_number: str,
    benefit_data: dict[str, Any],
    catalogs: ProposalCatalogs,
    generated: ProposalGeneratedClientData,
) -> dict[str, Any]:
    client_id = str(client_data.get("id") or "").strip()
    sanitized_main_document = sanitize_digits(main_document_number)
    contract_document_type = normalize_contract_document_type(generated.contract_document_type)
    contract_document_number = sanitize_digits(generated.contract_document_number)

    if not client_id:
        raise ProposalPayloadError("O client_id e obrigatorio para completar o cliente.")
    if not client_name.strip():
        raise ProposalPayloadError("O nome do cliente e obrigatorio para completar o cliente.")
    if not main_document_id:
        raise ProposalPayloadError("O client_main_document_id e obrigatorio.")
    if not sanitized_main_document:
        raise ProposalPayloadError("O CPF principal do cliente e obrigatorio.")
    if not contract_document_number:
        raise ProposalPayloadError("O numero do documento contratual e obrigatorio.")
    if contract_document_number == sanitized_main_document:
        raise ProposalPayloadError(
            "O documento contratual nao pode usar o mesmo numero do CPF principal."
        )

    benefit_payload = extract_benefit_payload(
        benefit_data=benefit_data,
        client_id=client_id,
        agreement_id=agreement_id,
        main_document_number=sanitized_main_document,
        client_name=client_name,
    )

    payload = {
        "data": {
            "id": int(client_id),
            "name": client_name.strip(),
            "birth_date": generated.birth_date,
            "civil_status": catalogs.civil_status_code,
            "mothers_name": generated.mothers_name,
            "fathers_name": generated.fathers_name,
            "politically_exposed": False,
            "nationality": "1",
            "city": generated.city,
            "education": catalogs.education_code,
            "stateId": catalogs.state_code,
            "gender": catalogs.gender_code,
            "main_phone": sanitize_digits(generated.main_phone),
            "main_email": generated.email,
            "benefits": [benefit_payload],
            "documents": [
                {
                    "id": int(main_document_id),
                    "client_id": int(client_id),
                    "type": "CPF",
                    "number": sanitized_main_document,
                    "state_id": None,
                    "issuer": None,
                    "expedition_date": None,
                },
                {
                    "client_id": int(client_id),
                    "type": contract_document_type,
                    "number": contract_document_number,
                    "state_id": generated.contract_document_state_code,
                    "issuer": generated.contract_document_issuer,
                    "expedition_date": generated.contract_document_expedition_date,
                },
            ],
            "addresses": [
                {
                    "client_id": int(client_id),
                    "postal_code": sanitize_digits(generated.postal_code),
                    "street": generated.street,
                    "number": generated.number,
                    "has_number": True,
                    "complement_address": generated.complement_address,
                    "district": generated.district,
                    "city": generated.city,
                    "state_id": catalogs.state_code,
                }
            ],
            "banks": [
                {
                    "client_id": int(client_id),
                    "bank_id": catalogs.bank_code,
                    "account_type": catalogs.bank_account_type_code,
                    "agency": sanitize_digits(generated.bank_agency),
                    "agency_digit": sanitize_digits(generated.bank_agency_digit),
                    "account": sanitize_digits(generated.bank_account),
                    "account_digit": sanitize_digits(generated.bank_account_digit),
                }
            ],
        }
    }
    return payload



def build_proposal_payload(
    *,
    simulation_id: str,
    simulation_code: str,
    identifiers: ProposalIdentifiers,
    income_value: int,
) -> dict[str, Any]:
    if not simulation_id:
        raise ProposalPayloadError("O simulation_id e obrigatorio para criar a proposta.")
    if not simulation_code:
        raise ProposalPayloadError("O simulation_code e obrigatorio para criar a proposta.")

    for label, value in (
        ("client_address_id", identifiers.client_address_id),
        ("client_bank_id", identifiers.client_bank_id),
        ("client_main_document_id", identifiers.client_main_document_id),
        ("client_contract_document_id", identifiers.client_contract_document_id),
        ("client_benefit_id", identifiers.client_benefit_id),
    ):
        if not value:
            raise ProposalPayloadError(f"O campo {label} e obrigatorio para a proposta.")

    if str(identifiers.client_main_document_id) == str(identifiers.client_contract_document_id):
        raise ProposalPayloadError(
            "Os IDs do documento principal e do documento contratual nao podem ser iguais."
        )

    safe_income_value = income_value if income_value > 0 else 100000
    return {
        "data": {
            "simulation_id": str(simulation_id),
            "client_address_id": str(identifiers.client_address_id),
            "client_bank_id": str(identifiers.client_bank_id),
            "client_main_document_id": str(identifiers.client_main_document_id),
            "client_contract_document_id": str(identifiers.client_contract_document_id),
            "client_benefit_id": str(identifiers.client_benefit_id),
            "simulation_code": str(simulation_code),
            "invoice_by_email": True,
            "invoice_by_sms": True,
            "wait_for_attachment": False,
            "income_value": safe_income_value,
        }
    }



def extract_main_document_id(client_data: dict[str, Any], main_document_number: str) -> str:
    sanitized_main_document = sanitize_digits(main_document_number)
    for document in client_data.get("documents") or []:
        if sanitize_digits(document.get("number")) == sanitized_main_document:
            return str(document.get("id") or "")
        if str(document.get("type") or "").upper() == "CPF":
            return str(document.get("id") or "")
    raise ProposalPayloadError(
        "Nao foi possivel localizar o documento principal do cliente para a proposta."
    )



def extract_related_client_ids(
    client_data: dict[str, Any],
    *,
    main_document_number: str,
    contract_document_type: str,
    contract_document_number: str,
) -> ProposalIdentifiers:
    normalized_type = normalize_contract_document_type(contract_document_type)
    sanitized_main_document = sanitize_digits(main_document_number)
    sanitized_contract_document = sanitize_digits(contract_document_number)

    main_document_id = ""
    contract_document_id = ""
    for document in client_data.get("documents") or []:
        document_number = sanitize_digits(document.get("number"))
        document_type = str(document.get("type") or "").strip().lower()
        if not main_document_id and (
            document_number == sanitized_main_document
            or document_type == "cpf"
        ):
            main_document_id = str(document.get("id") or "")
        if (
            not contract_document_id
            and document_type == normalized_type
            and document_number == sanitized_contract_document
        ):
            contract_document_id = str(document.get("id") or "")

    addresses = client_data.get("addresses") or []
    banks = client_data.get("banks") or []
    benefits = client_data.get("benefits") or []

    if not addresses:
        raise ProposalPayloadError("Nenhum endereco foi encontrado apos completar o cliente.")
    if not banks:
        raise ProposalPayloadError("Nenhum banco foi encontrado apos completar o cliente.")
    if not benefits:
        raise ProposalPayloadError("Nenhum beneficio foi encontrado apos completar o cliente.")
    if not main_document_id:
        raise ProposalPayloadError("Nao foi possivel localizar o client_main_document_id.")
    if not contract_document_id:
        raise ProposalPayloadError("Nao foi possivel localizar o client_contract_document_id.")

    return ProposalIdentifiers(
        client_main_document_id=main_document_id,
        client_contract_document_id=contract_document_id,
        client_address_id=str(addresses[0].get("id") or ""),
        client_bank_id=str(banks[0].get("id") or ""),
        client_benefit_id=str(benefits[0].get("id") or ""),
    )



def select_client_benefit_data(
    client_data: dict[str, Any],
    *,
    agreement_id: str,
    benefit_number: str,
    main_document_number: str,
) -> dict[str, Any]:
    benefits = client_data.get("benefits") or []
    if not benefits:
        raise ProposalPayloadError(
            "Nao foi possivel localizar o beneficio do cliente para completar a proposta."
        )

    normalized_agreement_id = str(agreement_id or "").strip()
    normalized_benefit_number = str(benefit_number or "").strip()
    normalized_main_document = sanitize_digits(main_document_number)

    preferred_matches = [
        benefit
        for benefit in benefits
        if str(benefit.get("agreement_id") or "") == normalized_agreement_id
        and str(benefit.get("benefit_number") or "").strip() == normalized_benefit_number
    ]
    if preferred_matches:
        return preferred_matches[0]

    agreement_matches = [
        benefit
        for benefit in benefits
        if str(benefit.get("agreement_id") or "") == normalized_agreement_id
        and sanitize_digits(benefit.get("document") or "") == normalized_main_document
    ]
    if agreement_matches:
        return agreement_matches[0]

    document_matches = [
        benefit
        for benefit in benefits
        if sanitize_digits(benefit.get("document") or "") == normalized_main_document
    ]
    if document_matches:
        return document_matches[0]

    return benefits[0]



def extract_benefit_payload(
    *,
    benefit_data: dict[str, Any],
    client_id: str,
    agreement_id: str,
    main_document_number: str,
    client_name: str,
) -> dict[str, Any]:
    if not benefit_data:
        raise ProposalPayloadError(
            "Nao foi possivel localizar o beneficio do cliente para completar a proposta."
        )

    payload: dict[str, Any] = {
        field: benefit_data.get(field)
        for field in CLIENT_BENEFIT_FIELDS
    }
    payload["client_id"] = int(client_id)
    payload["agreement_id"] = int(str(benefit_data.get("agreement_id") or agreement_id))
    payload["document"] = sanitize_digits(benefit_data.get("document") or main_document_number)
    payload["beneficiary_name"] = str(
        benefit_data.get("beneficiary_name")
        or client_name
    )
    payload["benefit_number"] = str(benefit_data.get("benefit_number") or "")

    for field in OPTIONAL_BENEFIT_FIELDS:
        if benefit_data.get(field) is not None:
            payload[field] = benefit_data.get(field)

    return payload

