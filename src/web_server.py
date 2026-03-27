from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.api_client import (
    ApiAuthenticationError,
    ApiRequestError,
    ApiSession,
    CatalogOption,
    CipBenefit,
    SerproBenefit,
    create_proposal,
    create_simulation,
    fetch_agreement_processor_code,
    get_client,
    list_catalog_options,
    list_cip_benefits,
    list_serpro_benefits,
    update_client,
)
from src.config import EnvironmentConfig, get_environment_config, load_environment_file
from src.database import (
    Product,
    fetch_agreements,
    fetch_products,
    fetch_sale_modalities,
    fetch_withdraw_types,
    test_connection,
)
from src.fake_data import FakeDataService
from src.google_sheets import GoogleSheetsError, GoogleSheetsService, SelectedSheetRecord
from src.proposal import (
    ProposalCatalogs,
    ProposalGeneratedClientData,
    ProposalPayloadError,
    build_complete_client_payload,
    build_proposal_payload,
    extract_main_document_id,
    extract_related_client_ids,
    select_client_benefit_data,
)
from src.simulation import (
    SerproIdentifiers,
    SimulationClient,
    SimulationPayloadError,
    SimulationPayloadInput,
    build_simulation_payload,
    is_cip_processor,
    is_serpro_processor,
    is_zetra_processor,
    sale_modality_requires_original_ccb,
    sanitize_digits,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ENVIRONMENT_OPTIONS = {
    "HOMOLOG": "Homolog",
    "DEV": "Dev",
    "RANCHER": "Rancher",
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



def handle_connect_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    api_session = ApiSession(config)

    try:
        api_session.authenticate()
        test_connection(config)
    except ApiAuthenticationError as exc:
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

    agreements = fetch_agreements(config)
    products = fetch_products(config)
    sale_modalities = fetch_sale_modalities(config)
    withdraw_types = fetch_withdraw_types(config)

    return {
        "environment": {"key": config.key, "label": config.label},
        "agreements": [asdict(item) for item in agreements],
        "products": [asdict(item) for item in products],
        "saleModalities": [asdict(item) for item in sale_modalities],
        "withdrawTypes": [asdict(item) for item in withdraw_types],
    }



def handle_preview_request(payload: dict[str, Any]) -> dict[str, Any]:
    config = resolve_environment_config(payload.get("environment"))
    agreement_id = require_text(payload, "agreementId")
    product_id = require_text(payload, "productId")
    api_session = ApiSession(config)

    try:
        api_session.authenticate()
        processor_code = fetch_agreement_processor_code(api_session, agreement_id)
        product = find_item_by_id(fetch_products(config), product_id, "produto")
        sheet_record = load_sheet_record_for_product(processor_code, product.name)
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

    api_session = ApiSession(config)
    warnings: list[str] = []

    try:
        api_session.authenticate()
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
    sheet_record = load_sheet_record_for_product(processor_code, product.name)

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
    selected_user_password = sanitize_text(payload.get("userPassword")) or sheet_record.senha
    selected_sponsor_benefit_number = sanitize_text(payload.get("sponsorBenefitNumber"))
    selected_cip_agency_id = (
        "1" if is_cip_processor(processor_code) and config.key == "HOMOLOG"
        else sanitize_text(payload.get("cipAgencyId"))
    )
    selected_serpro_identifiers = None

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

    api_session = ApiSession(config)
    fake_data_service = FakeDataService()

    try:
        api_session.authenticate()
        proposal_catalogs = fetch_proposal_catalogs_for_web(api_session)
        proposal_client_data = get_client(api_session, client_id)
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
            catalogs=proposal_catalogs,
            generated=generated,
        )
        update_client(
            api_session=api_session,
            client_id=client_id,
            payload=complete_client_payload,
        )
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

    data = proposal_response.get("data") or {}
    return {
        "summary": {
            "id": data.get("id"),
            "code": data.get("code"),
            "requestedValue": data.get("requested_value"),
            "clientName": data.get("full_name"),
            "simulationCode": data.get("simulation_code") or simulation_code,
        },
        "generated": {
            "contractDocumentType": generated.contract_document_type.upper(),
            "contractDocumentMasked": mask_value(generated.contract_document_number),
            "email": generated.email,
        },
        "raw": proposal_response,
    }



def fetch_proposal_catalogs_for_web(api_session: ApiSession) -> ProposalCatalogs:
    civil_status = pick_catalog_option_for_web(
        list_catalog_options(api_session, "/admin/civil-status"),
        preferred_codes=("1", "2"),
    )
    education = pick_catalog_option_for_web(
        list_catalog_options(api_session, "/admin/education"),
        preferred_codes=("1", "2", "3"),
    )
    gender = pick_catalog_option_for_web(
        list_catalog_options(api_session, "/admin/gender"),
        preferred_codes=("M", "F"),
    )
    state = pick_catalog_option_for_web(
        list_catalog_options(api_session, "/admin/state"),
        preferred_codes=("MG", "SP", "PR"),
    )
    bank_account_type = pick_catalog_option_for_web(
        list_catalog_options(api_session, "/admin/bank-account-type"),
        preferred_codes=("cc",),
    )
    bank = pick_catalog_option_for_web(
        list_catalog_options(
            api_session,
            "/admin/bank",
            params={"limit": 300, "offset": 10},
        ),
        preferred_codes=("001",),
    )

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
            selected.benefit_number or fallback_benefit_number,
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



def load_sheet_record_for_product(processor_code: str, product_name: str) -> SelectedSheetRecord:
    try:
        sheets_service = GoogleSheetsService()
        processor_sheet = sheets_service.load_processor_data(processor_code)
        return sheets_service.select_record_from_data(processor_sheet, product_name)
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
        "maskedCpf": mask_value(record.cpf),
        "nome": record.nome,
        "orgao": record.orgao,
        "senha": record.senha,
        "matchingRecordsCount": record.matching_records_count,
    }



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







