from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from src.core.proposal_history import build_proposal_record, record_proposal
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
    get_client,
    list_catalog_options,
    list_cip_benefits,
    list_dataprev_benefits,
    list_serpro_benefits,
    update_client,
)
from src.core.config import get_environment_config, load_environment_file
from src.infra.database import (
    Agreement,
    Product,
    SaleModality,
    WithdrawType,
    fetch_agreements,
    fetch_products,
    fetch_sale_modalities,
    fetch_withdraw_types,
    test_connection,
)
from src.services.fake_data import FakeDataService
from src.infra.google_sheets import (
    GoogleSheetsError,
    GoogleSheetsService,
    SelectedSheetRecord,
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


ENVIRONMENT_OPTIONS = {
    "1": "HOMOLOG",
    "2": "DEV",
    "3": "RANCHER",
}


def run() -> None:
    configure_console_output()
    load_environment_file()
    selected_key = prompt_environment()
    config = get_environment_config(selected_key)
    api_session = ApiSession(config)
    fake_data_service = FakeDataService()

    try:
        sheets_service = GoogleSheetsService()
    except GoogleSheetsError as exc:
        print("\n❌ Nao foi possivel iniciar a integracao com Google Sheets.")
        return

    print(f"\n🌍 Ambiente: {config.label}")

    print("\n🔌 Conectando aos servicos...")
    try:
        access_token = api_session.authenticate()
    except ApiAuthenticationError as exc:
        print("\n❌ Nao foi possivel autenticar na API.")
        return
    print("✅ API conectada com sucesso.")

    try:
        store_ids = fetch_my_stores(api_session)
        api_session.store_ids = store_ids
        api_session.stores_query_string = build_stores_query_string(store_ids)
    except ApiRequestError:
        print("\n❌ Nao foi possivel consultar as lojas do usuario.")
        return
    print(f"🏪 Lojas carregadas ({len(store_ids)}).")

    print("🗄️  Verificando acesso ao banco...")
    try:
        test_connection(config)
    except Exception as exc:
        print("\n❌ Nao foi possivel acessar o banco de dados.")
        return
    print("✅ Banco conectado com sucesso.")

    print("\n🧭 Vamos montar a simulacao.")
    agreements = fetch_agreements(config)
    if not agreements:
        print("⚠️ Nenhum convenio foi encontrado neste ambiente.")
        return

    selected_agreement = prompt_agreement(agreements)
    selected_agreement_id = selected_agreement.id
    print(f"\n🏛️  Convenio escolhido: {selected_agreement.name}")

    print("🔎 Identificando a processadora do convenio...")
    try:
        selected_processor_code = fetch_agreement_processor_code(
            api_session=api_session,
            agreement_id=selected_agreement_id,
        )
    except ApiRequestError as exc:
        print("\n❌ Nao foi possivel identificar a processadora do convenio.")
        return
    print(f"🏷️  Processadora detectada: {selected_processor_code.upper()}")

    print("📦 Carregando produtos disponiveis...")
    products = fetch_products(config)
    if not products:
        print("⚠️ Nenhum produto foi encontrado para este ambiente.")
        return

    print("📄 Consultando a base da processadora...")
    try:
        selected_processor_sheet = sheets_service.load_processor_data(selected_processor_code)
    except GoogleSheetsError as exc:
        print("\n❌ Nao foi possivel consultar a base da processadora.")
        return
    processor_records = selected_processor_sheet.records
    print(f"🗂️  Base selecionada: {selected_processor_sheet.worksheet_name}")

    while True:
        selected_product = prompt_product(products)
        selected_product_id = selected_product.id
        print(f"\n🛍️  Produto escolhido: {selected_product.name}")

        try:
            sheet_record_action, selected_sheet_record = choose_sheet_record_for_product(
                sheets_service=sheets_service,
                processor_data=selected_processor_sheet,
                product_name=selected_product.name,
            )
        except GoogleSheetsError as exc:
            print(f"\n⚠️ Nao encontrei um registro elegivel para essa combinacao. {exc}")
            if prompt_retry_or_exit():
                print("\n🙂 Tudo bem, vamos tentar outra opcao.")
                continue
            print("\n👋 Execucao encerrada.")
            return

        if sheet_record_action == "retry_product":
            print("\n🔁 Tudo bem, vamos escolher outro produto.")
            continue
        if sheet_record_action == "exit":
            print("\n👋 Execucao encerrada.")
            return
        break

    selected_sheet_balance = selected_sheet_record.balance_value
    selected_sheet_matricula = selected_sheet_record.matricula
    selected_sheet_cpf = selected_sheet_record.cpf
    selected_sheet_nome = selected_sheet_record.nome
    selected_sheet_senha = selected_sheet_record.senha

    if is_dataprev_processor(selected_processor_code) and not selected_sheet_nome:
        print("\n💡 Dica: para DATAPREV, use o nome real do cliente para melhorar a consulta.")
    if is_serpro_processor(selected_processor_code) and not selected_sheet_nome:
        print("\n💡 Dica: para SERPRO, use o nome real do cliente para melhorar a consulta.")
    if is_cip_processor(selected_processor_code) and not selected_sheet_nome:
        print("\n💡 Dica: para CIP, use o nome real do cliente para melhorar a consulta.")

    client_info = prompt_client_info(
        fake_data_service=fake_data_service,
        default_name=selected_sheet_nome,
        default_document=selected_sheet_cpf,
    )

    selected_margin_value: str | int = selected_sheet_balance
    selected_benefit_number = selected_sheet_matricula
    selected_user_password = ""
    selected_sponsor_benefit_number = ""
    selected_cip_agency_id = "1" if is_cip_processor(selected_processor_code) and config.key == "HOMOLOG" else ""
    selected_serpro_identifiers = None

    if selected_cip_agency_id:
        print("\n⚙️ Usando configuracao padrao da CIP para este ambiente.")

    if is_dataprev_processor(selected_processor_code):
        print("\n🔎 Consultando beneficios na DATAPREV...")
        try:
            dataprev_benefits = list_dataprev_benefits(
                api_session=api_session,
                document=client_info.document,
                name=client_info.name,
            )
            selected_dataprev_benefit = select_dataprev_benefit(
                dataprev_benefits,
                selected_product.name,
            )
        except (ApiRequestError, ValueError) as exc:
            print("\n⚠️ Nao consegui concluir a consulta automatica da DATAPREV.")
            print("Vamos seguir com os dados disponiveis na planilha.")
        else:
            selected_margin_value = selected_dataprev_benefit.margin_value_for_product(selected_product.name)
            selected_benefit_number = selected_dataprev_benefit.benefit_number or selected_benefit_number
            print_selected_dataprev_benefit(selected_dataprev_benefit, selected_product.name)

    if is_zetra_processor(selected_processor_code):
        selected_benefit_number = prompt_value_with_fallback(
            fake_data_service=fake_data_service,
            label="matricula do beneficio",
            default_value=selected_sheet_matricula,
            digits_only=True,
            fake_mode="numeric",
            fake_length=10,
        )
        selected_user_password = prompt_optional_value_with_fallback(
            fake_data_service=fake_data_service,
            label="senha do servidor",
            default_value=selected_sheet_senha,
            digits_only=False,
            fake_mode="password",
        )

    if is_serpro_processor(selected_processor_code):
        print("\n🔎 Consultando beneficios na SERPRO...")
        try:
            serpro_benefits = list_serpro_benefits(
                api_session=api_session,
                document=client_info.document,
                name=client_info.name,
                product_id=selected_product_id,
                agreement_id=selected_agreement_id,
            )
            selected_serpro_benefit = select_serpro_benefit(
                serpro_benefits,
                selected_product.name,
            )
        except (ApiRequestError, ValueError) as exc:
            print("\n⚠️ Nao consegui concluir a consulta automatica da SERPRO.")
            print("Vamos seguir com preenchimento assistido.")
            selected_benefit_number = prompt_value_with_fallback(
                fake_data_service=fake_data_service,
                label="matricula do beneficio SERPRO",
                default_value=selected_sheet_matricula,
                digits_only=True,
                fake_mode="numeric",
                fake_length=10,
            )
            selected_sponsor_benefit_number = prompt_optional_value_with_fallback(
                fake_data_service=fake_data_service,
                label="sponsor_benefit_number",
                default_value="",
                digits_only=True,
                fake_mode="numeric",
                fake_length=8,
            )
            selected_serpro_identifiers = SerproIdentifiers(
                agency_id=prompt_value_with_fallback(
                    fake_data_service=fake_data_service,
                    label="serpro_agency_id",
                    default_value="",
                    digits_only=True,
                    fake_mode="numeric",
                    fake_length=3,
                )
            )
        else:
            selected_margin_value = selected_serpro_benefit.margin_value_for_product(selected_product.name)
            selected_benefit_number = selected_serpro_benefit.benefit_number or prompt_value_with_fallback(
                fake_data_service=fake_data_service,
                label="matricula do beneficio SERPRO",
                default_value=selected_sheet_matricula,
                digits_only=True,
                fake_mode="numeric",
                fake_length=10,
            )
            selected_sponsor_benefit_number = (
                selected_serpro_benefit.sponsor_benefit_number
                or prompt_optional_value_with_fallback(
                    fake_data_service=fake_data_service,
                    label="sponsor_benefit_number",
                    default_value="",
                    digits_only=True,
                    fake_mode="numeric",
                    fake_length=8,
                )
            )
            selected_serpro_identifiers = SerproIdentifiers(
                agency_id=selected_serpro_benefit.serpro_agency_id
                or prompt_value_with_fallback(
                    fake_data_service=fake_data_service,
                    label="serpro_agency_id",
                    default_value="",
                    digits_only=True,
                    fake_mode="numeric",
                    fake_length=3,
                )
            )
            print_selected_serpro_benefit(selected_serpro_benefit, selected_product.name)

    print("\n📘 Agora vamos definir a modalidade.")
    sale_modalities = fetch_sale_modalities(config)
    if not sale_modalities:
        print("⚠️ Nenhuma modalidade foi encontrada.")
        return

    selected_sale_modality = prompt_sale_modality(sale_modalities)
    selected_sale_modality_id = selected_sale_modality.id
    print(f"\n📘 Modalidade escolhida: {selected_sale_modality.name}")

    original_ccb_code = ""
    original_ccb_origin = ""
    if sale_modality_requires_original_ccb(selected_sale_modality.name):
        print("\n🧾 Essa modalidade precisa dos dados do contrato original.")
        original_ccb_code = prompt_text("Digite o original_ccb_code")
        original_ccb_origin = prompt_text("Digite o original_ccb_origin")

    print("\n💸 Por fim, escolha o tipo de saque.")
    withdraw_types = fetch_withdraw_types(config)
    if not withdraw_types:
        print("⚠️ Nenhum tipo de saque foi encontrado.")
        return

    selected_withdraw_type = prompt_withdraw_type(withdraw_types)
    selected_withdraw_type_id = selected_withdraw_type.id
    print(f"\n💸 Tipo de saque: {selected_withdraw_type.name}")

    if is_cip_processor(selected_processor_code):
        if not selected_cip_agency_id:
            selected_cip_agency_id = prompt_value_with_fallback(
                fake_data_service=fake_data_service,
                label="cip_agency_id",
                default_value="",
                digits_only=True,
                fake_mode="numeric",
                fake_length=3,
            )

        while True:
            print("\n🔎 Consultando beneficios na CIP...")
            try:
                cip_benefits = list_cip_benefits(
                    api_session=api_session,
                    document=client_info.document,
                    agency_id=selected_cip_agency_id,
                    agreement_id=selected_agreement_id,
                    product_id=selected_product_id,
                    withdraw_type_id=selected_withdraw_type_id,
                    name=client_info.name,
                )
                selected_cip_benefit = select_cip_benefit(
                    cip_benefits,
                    selected_product.name,
                )
            except (ApiRequestError, ValueError) as exc:
                print("\n⚠️ Nao consegui concluir a consulta automatica da CIP.")
                print(describe_api_error(exc))
                cip_fallback_action = prompt_cip_error_action()
                if cip_fallback_action == "retry":
                    continue
                if cip_fallback_action == "exit":
                    print("\n👋 Execucao encerrada.")
                    return
                print("\n🙂 Vamos seguir com os dados disponiveis por enquanto.")
                break
            else:
                selected_margin_value = selected_cip_benefit.margin_value_for_product(selected_product.name)
                selected_benefit_number = (selected_cip_benefit.benefit_number or "").strip()
                selected_cip_agency_id = selected_cip_benefit.cip_agency_id or selected_cip_agency_id
                print_selected_cip_benefit(selected_cip_benefit, selected_product.name)
                break

    simulation_input = SimulationPayloadInput(
        agreement_id=selected_agreement_id,
        product_id=selected_product_id,
        sale_modality_id=selected_sale_modality_id,
        withdraw_type_id=selected_withdraw_type_id,
        processor_code=selected_processor_code,
        margin_value=selected_margin_value,
        client=client_info,
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
        print("\n❌ Nao consegui preparar a simulacao com os dados informados.")
        return

    print("\n✨ Gerando a simulacao...")
    try:
        simulation_response = create_simulation(
            api_session=api_session,
            payload=simulation_payload,
        )
    except ApiRequestError as exc:
        print("\n❌ Nao consegui concluir a simulacao.")
        print(describe_api_error(exc))
        print_simulation_payload_summary(simulation_payload)
        return

    print_simulation_success(simulation_response)

    simulation_data = simulation_response.get("data") or {}
    simulation_id = str(simulation_data.get("id") or "")
    simulation_code = str(simulation_data.get("code") or "")
    client_id = str(simulation_data.get("client_id") or "")
    if not client_id:
        print("\n❌ A simulacao foi criada, mas o client_id nao veio na resposta.")
        return

    print("\n🧾 Vamos transformar essa simulacao em proposta.")
    contract_document_type = fake_data_service.generate_contract_document_type()
    print(f"🪪 Documento contratual definido automaticamente: {contract_document_type.upper()}")

    print("🔎 Buscando os dados necessarios para a proposta...")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_catalogs = executor.submit(fetch_proposal_catalogs, api_session)
            f_client = executor.submit(get_client, api_session, client_id)
        proposal_catalogs = f_catalogs.result()
        proposal_client_data = f_client.result()
    except ApiRequestError as exc:
        report_step_error("carregar os dados da proposta", exc)
        return

    try:
        main_document_id = extract_main_document_id(proposal_client_data, client_info.document)
        proposal_benefit_data = select_client_benefit_data(
            proposal_client_data,
            agreement_id=selected_agreement_id,
            benefit_number=selected_benefit_number,
            main_document_number=client_info.document,
        )
    except ProposalPayloadError as exc:
        report_step_error("identificar os dados base do cliente para a proposta", exc)
        return

    generated_proposal_data = build_generated_proposal_client_data(
        fake_data_service=fake_data_service,
        client_name=client_info.name,
        client_phone=client_info.phone,
        contract_document_type=contract_document_type,
        state_code=proposal_catalogs.state_code,
        main_document_number=client_info.document,
    )
    print_generated_proposal_preview(generated_proposal_data)

    try:
        complete_client_payload = build_complete_client_payload(
            client_data=proposal_client_data,
            client_name=client_info.name,
            agreement_id=selected_agreement_id,
            main_document_id=main_document_id,
            main_document_number=client_info.document,
            benefit_data=proposal_benefit_data,
            fallback_benefit_number=selected_benefit_number,
            catalogs=proposal_catalogs,
            generated=generated_proposal_data,
        )
    except ProposalPayloadError as exc:
        report_step_error("montar o payload de complemento do cliente", exc)
        return

    print("✍️ Complementando o cadastro do cliente...")
    try:
        updated_client_response = update_client(
            api_session=api_session,
            client_id=client_id,
            payload=complete_client_payload,
        )
    except ApiRequestError as exc:
        report_step_error("complementar o cadastro do cliente", exc)
        return

    refreshed_client_data = extract_response_data_dict(updated_client_response)
    if refreshed_client_data is None:
        try:
            refreshed_client_data = get_client(api_session, client_id)
        except ApiRequestError as exc:
            report_step_error("recarregar o cliente apos o complemento", exc)
            return

    try:
        proposal_identifiers = extract_related_client_ids(
            refreshed_client_data,
            main_document_number=client_info.document,
            contract_document_type=contract_document_type,
            contract_document_number=generated_proposal_data.contract_document_number,
        )
        proposal_payload = build_proposal_payload(
            simulation_id=simulation_id,
            simulation_code=simulation_code,
            identifiers=proposal_identifiers,
            income_value=generated_proposal_data.income_value,
        )
    except ProposalPayloadError as exc:
        report_step_error("montar os identificadores finais da proposta", exc)
        return

    print("📨 Emitindo a proposta...")
    try:
        proposal_response = create_proposal(
            api_session=api_session,
            payload=proposal_payload,
        )
    except ApiRequestError as exc:
        report_step_error("emitir a proposta", exc)
        print_proposal_payload_summary(proposal_payload)
        return

    print_proposal_success(proposal_response)

    history_index = record_proposal(build_proposal_record(
        environment_key=config.key,
        agreement_id=selected_agreement_id,
        product_id=selected_product_id,
        sale_modality_id=selected_sale_modality_id,
        withdraw_type_id=selected_withdraw_type_id,
        processor_code=selected_processor_code,
        client_name=client_info.name,
        client_document=client_info.document,
        client_phone=client_info.phone,
        benefit_number=selected_benefit_number,
        simulation_id=simulation_id,
        simulation_code=simulation_code,
        client_id=client_id,
        contract_document_type=contract_document_type,
        contract_document_number=generated_proposal_data.contract_document_number,
        email=generated_proposal_data.email,
        simulation_response=simulation_response,
        proposal_response=proposal_response,
    ))
    print(f"📋 Proposta #{history_index} salva no historico do ambiente {config.key}.")



def configure_console_output() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")



def prompt_environment() -> str:
    print("🌍 Selecione o ambiente desejado:")
    print("1 - Homolog")
    print("2 - Dev")
    print("3 - Rancher")

    while True:
        option = input("\nDigite a opcao desejada (1 a 3): ").strip()
        if option in ENVIRONMENT_OPTIONS:
            return ENVIRONMENT_OPTIONS[option]
        print("Opcao invalida. Escolha 1, 2 ou 3.")



def preview_token(access_token: str) -> str:
    return f"{access_token[:12]}..."



def prompt_agreement(agreements: list[Agreement]) -> Agreement:
    print("🏛️  Selecione o convenio desejado:")
    for index, agreement in enumerate(agreements, start=1):
        print(f"{index} - {agreement.name}")

    while True:
        option = input("\nDigite o numero do convenio: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(agreements):
                return agreements[selected_index]
        print("Opcao invalida. Escolha um numero da lista de convenios.")



def prompt_product(products: list[Product]) -> Product:
    print("🛍️  Selecione o produto desejado:")
    for index, product in enumerate(products, start=1):
        print(f"{index} - {product.name}")

    while True:
        option = input("\nDigite o numero do produto: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(products):
                return products[selected_index]
        print("Opcao invalida. Escolha um numero da lista de produtos.")



def prompt_cip_error_action() -> str:
    print("1 - Tentar novamente a consulta CIP")
    print("2 - Continuar com dados da planilha")
    print("3 - Encerrar")

    while True:
        option = input("\nDigite a opcao desejada (1, 2 ou 3): ").strip()
        if option == "1":
            return "retry"
        if option == "2":
            return "continue"
        if option == "3":
            return "exit"
        print("Opcao invalida. Escolha 1, 2 ou 3.")



def describe_api_error(error: Exception) -> str:
    if isinstance(error, ProposalPayloadError):
        return f"Diagnostico: {error}"

    message = str(error)
    details = getattr(error, "details", None)
    if "XmlEncrypto" in message or "EncryptionException" in message:
        return "Diagnostico: a consulta falhou dentro da integracao CIP/WsSecurity no backend. Isso indica problema de chave/certificado ou configuracao do servico externo, nao dos dados digitados no terminal."
    if "AvailableProductsByClientAdapter.php:43" in message:
        return "Diagnostico: a simulacao chegou ao backend, mas falhou na etapa de seguros. Isso aponta para erro interno do servico de insurance, nao para montagem do payload principal."
    if details and details.status_code == 404:
        return "Diagnostico: a API nao encontrou o recurso esperado para continuar o fluxo."
    if details and details.status_code == 422:
        return "Diagnostico: a API rejeitou os dados enviados por validacao de regra de negocio."
    if details and details.status_code == 401:
        return "Diagnostico: a autenticacao perdeu a validade ou o backend recusou o token nesta etapa."
    if details and details.status_code == 500:
        return "Diagnostico: a API respondeu com erro interno 500. O payload foi enviado, mas o backend falhou durante o processamento."
    if "500" in message:
        return "Diagnostico: a API respondeu com erro interno 500. O payload foi enviado, mas o backend falhou durante o processamento."
    if "Falha de conexao" in message:
        return "Diagnostico: houve falha de conectividade ao chamar a API nesta etapa."
    return "Diagnostico: a API retornou erro durante o processamento da requisicao."



def print_error_details(error: Exception) -> None:
    if isinstance(error, ProposalPayloadError):
        print(f"- Regra identificada: {error}")
        return

    details = getattr(error, "details", None)
    if not details:
        return

    detail_lines: list[str] = []
    if details.method or details.path:
        detail_lines.append(f"Endpoint: {details.method} {details.path}".strip())
    if details.status_code is not None:
        detail_lines.append(f"Status HTTP: {details.status_code}")
    if details.correlation_id:
        detail_lines.append(f"Correlation ID: {details.correlation_id}")
    if details.api_message:
        detail_lines.append(f"Mensagem da API: {details.api_message}")
    if details.trace_excerpt:
        detail_lines.append(f"Trace resumido: {details.trace_excerpt}")
    elif details.raw_body and not details.api_message:
        detail_lines.append(f"Resposta bruta: {details.raw_body[:240]}")

    if not detail_lines:
        return

    print("Detalhes tecnicos:")
    for line in detail_lines:
        print(f"- {line}")



def report_step_error(step_label: str, error: Exception) -> None:
    print(f"\n❌ Nao consegui {step_label}.")
    print(describe_api_error(error))
    print_error_details(error)



def print_simulation_success(simulation_response: dict) -> None:
    data = simulation_response.get("data") or {}
    print("\n🎉 Simulacao pronta.")
    if data.get("id") is not None:
        print(f"- ID da simulacao: {data.get('id')}")
    if data.get("code"):
        print(f"- Codigo: {data.get('code')}")
    if data.get("requested_value") is not None:
        print(f"- Valor liberado: {format_cents(int(data.get('requested_value') or 0))}")
    if data.get("installment_value") is not None:
        print(f"- Parcela: {format_cents(int(data.get('installment_value') or 0))}")
    if data.get("deadline") is not None:
        print(f"- Prazo: {data.get('deadline')} meses")



def print_simulation_payload_summary(simulation_payload: dict) -> None:
    data = simulation_payload.get("data") or {}
    client = data.get("client") or {}
    agreement = data.get("agreement") or {}
    product = data.get("product") or {}
    sale_modality = data.get("sale_modality") or {}
    withdraw_type = data.get("withdraw_type") or {}

    print("Resumo tecnico do envio:")
    print(f"- agreement.id: {agreement.get('id')}")
    if agreement.get("cip_agency_id") is not None:
        print(f"- agreement.cip_agency_id: {agreement.get('cip_agency_id')}")
    if agreement.get("serpro_agency_id") is not None:
        print(f"- agreement.serpro_agency_id: {agreement.get('serpro_agency_id')}")
    print(f"- product.id: {product.get('id')}")
    print(f"- sale_modality.id: {sale_modality.get('id')}")
    print(f"- withdraw_type.id: {withdraw_type.get('id')}")
    print(f"- client.name: {client.get('name')}")
    print(f"- client.document: {mask_document(str(client.get('document') or ''))}")
    print(f"- client.phone: {mask_phone(str(client.get('phone') or ''))}")
    print(f"- margin_value: {data.get('margin_value')}")
    if data.get("benefit_number"):
        print(f"- benefit_number: {data.get('benefit_number')}")




def fetch_proposal_catalogs(api_session: ApiSession) -> ProposalCatalogs:
    with ThreadPoolExecutor(max_workers=6) as executor:
        f_civil = executor.submit(list_catalog_options, api_session, "/admin/civil-status")
        f_education = executor.submit(list_catalog_options, api_session, "/admin/education")
        f_gender = executor.submit(list_catalog_options, api_session, "/admin/gender")
        f_state = executor.submit(list_catalog_options, api_session, "/admin/state")
        f_bank_type = executor.submit(list_catalog_options, api_session, "/admin/bank-account-type")
        f_bank = executor.submit(
            list_catalog_options, api_session, "/admin/bank", params={"limit": 300, "offset": 10},
        )

    civil_status = pick_catalog_option(f_civil.result(), preferred_codes=("1", "2"))
    education = pick_catalog_option(f_education.result(), preferred_codes=("1", "2", "3"))
    gender = pick_catalog_option(f_gender.result(), preferred_codes=("M", "F"))
    state = pick_catalog_option(f_state.result(), preferred_codes=("MG", "SP", "PR"))
    bank_account_type = pick_catalog_option(f_bank_type.result(), preferred_codes=("cc",))
    bank = pick_catalog_option(f_bank.result(), preferred_codes=("001",))

    return ProposalCatalogs(
        civil_status_code=civil_status.code or civil_status.id,
        education_code=education.code or education.id,
        gender_code=gender.code or gender.id,
        state_code=state.code or state.id,
        bank_code=bank.code or bank.id,
        bank_account_type_code=bank_account_type.code or bank_account_type.id,
    )



def pick_catalog_option(
    options: list[CatalogOption],
    *,
    preferred_codes: tuple[str, ...] = (),
    preferred_names: tuple[str, ...] = (),
) -> CatalogOption:
    if not options:
        raise ProposalPayloadError("Um dos catalogos obrigatorios da proposta retornou vazio.")

    normalized_codes = {code.strip().lower() for code in preferred_codes if code}
    normalized_names = {name.strip().lower() for name in preferred_names if name}

    for option in options:
        if option.code.strip().lower() in normalized_codes:
            return option
    for option in options:
        if option.name.strip().lower() in normalized_names:
            return option
    return options[0]



def build_generated_proposal_client_data(
    *,
    fake_data_service: FakeDataService,
    client_name: str,
    client_phone: str,
    contract_document_type: str,
    state_code: str,
    main_document_number: str,
) -> ProposalGeneratedClientData:
    contract_document_number = fake_data_service.generate_contract_document_number(
        contract_document_type,
        exclude=main_document_number,
    )
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
        contract_document_number=contract_document_number,
        contract_document_state_code=state_code,
        contract_document_issuer=("DETRAN" if contract_document_type == "cnh" else "SSP"),
        contract_document_expedition_date=fake_data_service.generate_document_expedition_date(),
        bank_agency=fake_data_service.generate_agency(),
        bank_agency_digit=fake_data_service.generate_agency_digit(),
        bank_account=fake_data_service.generate_account(),
        bank_account_digit=fake_data_service.generate_account_digit(),
    )



def print_generated_proposal_preview(generated: ProposalGeneratedClientData) -> None:
    print("🧪 Completei automaticamente os dados adicionais da proposta:")
    print(
        f"- Documento contratual: {generated.contract_document_type.upper()} "
        f"{mask_document(generated.contract_document_number)}"
    )
    print(f"- Email sugerido: {generated.email}")
    print(f"- Endereco sugerido: {generated.street}, {generated.number}")



def print_proposal_success(proposal_response: dict) -> None:
    data = proposal_response.get("data") or {}
    print("\n🎯 Proposta criada com sucesso.")
    if data.get("id") is not None:
        print(f"- ID da proposta: {data.get('id')}")
    if data.get("code"):
        print(f"- Contrato: {data.get('code')}")
    if data.get("full_name"):
        print(f"- Cliente: {data.get('full_name')}")
    if data.get("requested_value") is not None:
        print(f"- Valor solicitado: {format_cents(int(data.get('requested_value') or 0))}")



def print_proposal_payload_summary(proposal_payload: dict) -> None:
    data = proposal_payload.get("data") or {}
    print("Resumo tecnico da proposta:")
    print(f"- simulation_id: {data.get('simulation_id')}")
    print(f"- simulation_code: {data.get('simulation_code')}")
    print(f"- client_main_document_id: {data.get('client_main_document_id')}")
    print(f"- client_contract_document_id: {data.get('client_contract_document_id')}")
    print(f"- client_address_id: {data.get('client_address_id')}")
    print(f"- client_bank_id: {data.get('client_bank_id')}")
    print(f"- client_benefit_id: {data.get('client_benefit_id')}")
    print(f"- income_value: {data.get('income_value')}")




def mask_document(value: str) -> str:
    digits = sanitize_digits(value)
    if len(digits) <= 4:
        return digits
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"



def mask_phone(value: str) -> str:
    digits = sanitize_digits(value)
    if len(digits) <= 4:
        return digits
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"

def choose_sheet_record_for_product(
    *,
    sheets_service: GoogleSheetsService,
    processor_data,
    product_name: str,
) -> tuple[str, SelectedSheetRecord | None]:
    record_index = 0

    while True:
        selected_record = sheets_service.select_record_from_data(
            processor_data=processor_data,
            product_name=product_name,
            record_index=record_index,
        )
        print_selected_sheet_record(selected_record)

        if selected_record.matching_records_count <= 1:
            return "use", selected_record

        action = prompt_sheet_record_action()
        if action == "use":
            return "use", selected_record
        if action == "retry_product":
            return "retry_product", None
        if action == "exit":
            return "exit", None

        next_index = selected_record.selected_record_index + 1
        if next_index >= selected_record.matching_records_count:
            next_index = 0
            print("\n🔁 Cheguei ao fim da lista e vou voltar para o primeiro registro elegivel.")
        else:
            print("\n🔄 Vou buscar outro registro elegivel para voce.")
        record_index = next_index



def prompt_sheet_record_action() -> str:
    print("\nComo voce quer seguir com esse registro?")
    print("1 - Usar este registro")
    print("2 - Buscar outro registro elegivel")
    print("3 - Escolher outro produto")
    print("4 - Encerrar")

    while True:
        option = input("\nDigite a opcao desejada (1 a 4): ").strip()
        if option == "1":
            return "use"
        if option == "2":
            return "next"
        if option == "3":
            return "retry_product"
        if option == "4":
            return "exit"
        print("Opcao invalida. Escolha 1, 2, 3 ou 4.")



def prompt_retry_or_exit() -> bool:
    print("1 - Tentar novamente")
    print("2 - Encerrar")

    while True:
        option = input("\nDigite a opcao desejada (1 ou 2): ").strip()
        if option == "1":
            return True
        if option == "2":
            return False
        print("Opcao invalida. Escolha 1 ou 2.")



def prompt_client_info(
    fake_data_service: FakeDataService,
    default_name: str,
    default_document: str,
) -> SimulationClient:
    default_document_digits = sanitize_digits(default_document)
    name = prompt_name_field(
        fake_data_service=fake_data_service,
        default_value=default_name,
    )
    if default_document_digits:
        document = default_document_digits
        print("\n🧾 CPF carregado automaticamente da planilha.")
    else:
        document = prompt_client_field(
            label="documento do cliente",
            default_value="",
            fake_value_factory=fake_data_service.generate_document,
            digits_only=True,
            allow_faker=False,
        )
    phone = prompt_client_field(
        label="telefone do cliente",
        default_value="",
        fake_value_factory=fake_data_service.generate_phone,
        digits_only=True,
        allow_faker=True,
    )
    return SimulationClient(
        name=name,
        document=document,
        phone=phone,
    )



def prompt_name_field(
    fake_data_service: FakeDataService,
    default_value: str,
) -> str:
    print("\n🙂 Como voce prefere informar o nome do cliente?")
    if default_value:
        print(f"Sugestao da base: {default_value}")
    print("1 - Inserir manualmente")
    print("2 - Gerar com Faker")

    while True:
        option = input("\nDigite a opcao desejada (1 ou 2): ").strip()
        if option == "1":
            return prompt_text("Digite o nome do cliente", default_value)
        if option == "2":
            generated_value = fake_data_service.generate_name()
            print(f"🤖 Usei um nome ficticio: {generated_value}")
            return generated_value
        print("Opcao invalida. Escolha 1 ou 2.")



def prompt_client_field(
    label: str,
    default_value: str,
    fake_value_factory,
    *,
    digits_only: bool,
    allow_faker: bool = False,
) -> str:
    if default_value:
        if digits_only:
            return prompt_digits(f"Digite o {label}", default_value)
        return prompt_text(f"Digite o {label}", default_value)

    print(f"\n🤝 Nao encontrei {label} nos dados atuais.")
    if not allow_faker:
        if digits_only:
            return prompt_digits(f"Digite o {label}")
        return prompt_text(f"Digite o {label}")

    print("1 - Inserir manualmente")
    print("2 - Gerar com Faker")

    while True:
        option = input("\nDigite a opcao desejada (1 ou 2): ").strip()
        if option == "1":
            if digits_only:
                return prompt_digits(f"Digite o {label}")
            return prompt_text(f"Digite o {label}")
        if option == "2":
            generated_value = fake_value_factory()
            if digits_only:
                generated_value = sanitize_digits(generated_value)
            print(f"🤖 Usei um valor ficticio para {label}: {generated_value}")
            return generated_value
        print("Opcao invalida. Escolha 1 ou 2.")



def prompt_value_with_fallback(
    fake_data_service: FakeDataService,
    label: str,
    default_value: str,
    *,
    digits_only: bool,
    fake_mode: str = "document",
    fake_length: int = 8,
    allow_faker: bool = False,
) -> str:
    if default_value:
        return sanitize_digits(default_value) if digits_only else str(default_value).strip()

    fake_value_factory = build_fake_value_factory(
        fake_data_service=fake_data_service,
        fake_mode=fake_mode,
        fake_length=fake_length,
    )
    return prompt_client_field(
        label=label,
        default_value=default_value,
        fake_value_factory=fake_value_factory,
        digits_only=digits_only,
        allow_faker=allow_faker,
    )



def prompt_optional_value_with_fallback(
    fake_data_service: FakeDataService,
    label: str,
    default_value: str,
    *,
    digits_only: bool,
    fake_mode: str = "document",
    fake_length: int = 8,
    allow_faker: bool = False,
) -> str:
    if default_value:
        return sanitize_digits(default_value) if digits_only else str(default_value).strip()

    print(f"\n🤝 Nao encontrei {label} nos dados atuais.")
    print("1 - Inserir manualmente")
    if allow_faker:
        print("2 - Gerar com Faker")
        print("3 - Continuar sem informar")
    else:
        print("2 - Continuar sem informar")

    fake_value_factory = build_fake_value_factory(
        fake_data_service=fake_data_service,
        fake_mode=fake_mode,
        fake_length=fake_length,
    )

    while True:
        option = input("\nDigite a opcao desejada (1, 2 ou 3): ").strip() if allow_faker else input("\nDigite a opcao desejada (1 ou 2): ").strip()
        if option == "1":
            if digits_only:
                return prompt_digits(f"Digite o {label}")
            return prompt_text(f"Digite o {label}")
        if allow_faker and option == "2":
            generated_value = fake_value_factory()
            if digits_only:
                generated_value = sanitize_digits(generated_value)
            print(f"🤖 Usei um valor ficticio para {label}: {generated_value}")
            return generated_value
        if (allow_faker and option == "3") or ((not allow_faker) and option == "2"):
            return ""
        print("Opcao invalida. Escolha 1, 2 ou 3." if allow_faker else "Opcao invalida. Escolha 1 ou 2.")



def build_fake_value_factory(
    fake_data_service: FakeDataService,
    fake_mode: str,
    fake_length: int,
):
    if fake_mode == "password":
        return fake_data_service.generate_password
    if fake_mode == "numeric":
        return lambda: fake_data_service.generate_numeric_code(fake_length)
    return fake_data_service.generate_document



def prompt_text(label: str, default: str = "") -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"\n{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("Campo obrigatorio. Informe um valor.")



def prompt_digits(label: str, default: str = "") -> str:
    while True:
        raw_value = prompt_text(label, default)
        digits = sanitize_digits(raw_value)
        if digits:
            return digits
        print("Informe um valor que contenha numeros.")



def print_selected_sheet_record(record: SelectedSheetRecord) -> None:
    print("📋 Registro elegivel encontrado na base:")
    if record.matching_records_count > 1:
        print(f"- Registro: {record.selected_record_number} de {record.matching_records_count}")
    print(f"- Base: {record.worksheet_name}")
    print(f"- Saldo considerado: {record.balance_value}")
    print(f"- CPF: {mask_document(record.cpf)}")
    if record.orgao:
        print(f"- Orgao: {record.orgao}")



def prompt_sale_modality(sale_modalities: list[SaleModality]) -> SaleModality:
    print("📘 Selecione a modalidade desejada:")
    for index, sale_modality in enumerate(sale_modalities, start=1):
        print(f"{index} - {sale_modality.name}")

    while True:
        option = input("\nDigite o numero da modalidade: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(sale_modalities):
                return sale_modalities[selected_index]
        print("Opcao invalida. Escolha um numero da lista de modalidades.")



def prompt_withdraw_type(withdraw_types: list[WithdrawType]) -> WithdrawType:
    print("💸 Selecione o tipo de saque desejado:")
    for index, withdraw_type in enumerate(withdraw_types, start=1):
        print(f"{index} - {withdraw_type.name}")

    while True:
        option = input("\nDigite o numero do tipo de saque: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(withdraw_types):
                return withdraw_types[selected_index]
        print("Opcao invalida. Escolha um numero da lista de tipos de saque.")



def select_cip_benefit(
    benefits: list[CipBenefit],
    product_name: str,
) -> CipBenefit:
    if not benefits:
        raise ValueError("A consulta CIP nao retornou beneficios para o cliente informado.")

    candidates = [benefit for benefit in benefits if benefit.is_eligible_for_product(product_name)]
    if not candidates:
        raise ValueError(
            f"Nenhum beneficio CIP elegivel foi encontrado para o produto '{product_name}'."
        )

    preferred_candidates = [
        benefit
        for benefit in candidates
        if not benefit.blocked_for_loan
    ] or candidates

    if len(preferred_candidates) == 1:
        return preferred_candidates[0]

    print("Mais de um beneficio CIP elegivel foi encontrado:")
    for index, benefit in enumerate(preferred_candidates, start=1):
        agency_display = benefit.agency_name or benefit.agency_identification or benefit.cip_agency_id or "-"
        margin_display = format_cents(benefit.margin_value_for_product(product_name))
        print(
            f"{index} - Beneficiario: {benefit.beneficiary_name or '-'} | "
            f"cip_agency_id: {benefit.cip_agency_id or '-'} | "
            f"Agencia: {agency_display} | "
            f"Margem: {margin_display}"
        )

    while True:
        option = input("\nDigite o numero do beneficio CIP: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(preferred_candidates):
                return preferred_candidates[selected_index]
        print("Opcao invalida. Escolha um numero da lista de beneficios CIP.")



def print_selected_cip_benefit(benefit: CipBenefit, product_name: str) -> None:
    print("? Beneficio CIP validado:")
    print(f"- Cliente: {benefit.beneficiary_name or '(vazio)'}")
    print(f"- Agencia: {benefit.cip_agency_id or '(vazio)'}")
    if benefit.agency_name or benefit.agency_identification:
        print(f"- Detalhe da agencia: {benefit.agency_name or benefit.agency_identification}")
    if benefit.situation_description:
        print(f"- Situacao: {benefit.situation_description}")
    print(
        f"- Margem usada para {product_name}: "
        f"{format_cents(benefit.margin_value_for_product(product_name))}"
    )



def select_serpro_benefit(
    benefits: list[SerproBenefit],
    product_name: str,
) -> SerproBenefit:
    if not benefits:
        raise ValueError("A consulta SERPRO nao retornou beneficios para o cliente informado.")

    candidates = [benefit for benefit in benefits if benefit.is_eligible_for_product(product_name)]
    if not candidates:
        raise ValueError(
            f"Nenhum beneficio SERPRO elegivel foi encontrado para o produto '{product_name}'."
        )

    preferred_candidates = [
        benefit
        for benefit in candidates
        if not benefit.blocked_for_loan
    ] or candidates

    if len(preferred_candidates) == 1:
        return preferred_candidates[0]

    print("Mais de um beneficio SERPRO elegivel foi encontrado:")
    for index, benefit in enumerate(preferred_candidates, start=1):
        sponsor_display = benefit.sponsor_benefit_number or "-"
        department_display = benefit.department_name or benefit.department or "-"
        margin_display = format_cents(benefit.margin_value_for_product(product_name))
        print(
            f"{index} - Beneficio: {benefit.benefit_number or '-'} | "
            f"serpro_agency_id: {benefit.serpro_agency_id or '-'} | "
            f"Sponsor: {sponsor_display} | "
            f"Orgao: {department_display} | "
            f"Margem: {margin_display}"
        )

    while True:
        option = input("\nDigite o numero do beneficio SERPRO: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(preferred_candidates):
                return preferred_candidates[selected_index]
        print("Opcao invalida. Escolha um numero da lista de beneficios SERPRO.")



def print_selected_serpro_benefit(benefit: SerproBenefit, product_name: str) -> None:
    print("? Beneficio SERPRO validado:")
    print(f"- Beneficio: {benefit.benefit_number}")
    print(f"- Agencia SERPRO: {benefit.serpro_agency_id}")
    if benefit.sponsor_benefit_number:
        print(f"- Matricula do instituidor: {benefit.sponsor_benefit_number}")
    if benefit.department_name or benefit.department:
        print(f"- Orgao: {benefit.department_name or benefit.department}")
    if benefit.situation_description:
        print(f"- Situacao: {benefit.situation_description}")
    print(
        f"- Margem usada para {product_name}: "
        f"{format_cents(benefit.margin_value_for_product(product_name))}"
    )



def select_dataprev_benefit(
    benefits: list[DataprevBenefit],
    product_name: str,
) -> DataprevBenefit:
    if not benefits:
        raise ValueError("A consulta DATAPREV nao retornou beneficios para o cliente informado.")

    candidates = [benefit for benefit in benefits if benefit.is_eligible_for_product(product_name)]
    if not candidates:
        raise ValueError(
            f"Nenhum beneficio DATAPREV elegivel foi encontrado para o produto '{product_name}'."
        )

    preferred_candidates = [
        benefit
        for benefit in candidates
        if not benefit.blocked_for_loan
    ] or candidates

    if len(preferred_candidates) == 1:
        return preferred_candidates[0]

    print("Mais de um beneficio DATAPREV elegivel foi encontrado:")
    for index, benefit in enumerate(preferred_candidates, start=1):
        margin_display = format_cents(benefit.margin_value_for_product(product_name))
        print(
            f"{index} - Beneficio: {benefit.benefit_number or '-'} | "
            f"Nome: {benefit.beneficiary_name or '-'} | "
            f"Situacao: {benefit.situation_description or '-'} | "
            f"Margem: {margin_display}"
        )

    while True:
        option = input("\nDigite o numero do beneficio DATAPREV: ").strip()
        if option.isdigit():
            selected_index = int(option) - 1
            if 0 <= selected_index < len(preferred_candidates):
                return preferred_candidates[selected_index]
        print("Opcao invalida. Escolha um numero da lista de beneficios DATAPREV.")



def print_selected_dataprev_benefit(benefit: DataprevBenefit, product_name: str) -> None:
    print("? Beneficio DATAPREV validado:")
    print(f"- Nome: {benefit.beneficiary_name or '(vazio)'}")
    print(f"- Beneficio: {benefit.benefit_number or '(vazio)'}")
    if benefit.situation_description:
        print(f"- Situacao: {benefit.situation_description}")
    print(
        f"- Margem usada para {product_name}: "
        f"{format_cents(benefit.margin_value_for_product(product_name))}"
    )



def format_cents(value_in_cents: int) -> str:
    value_in_reais = value_in_cents / 100
    formatted_value = f"{value_in_reais:,.2f}"
    formatted_value = formatted_value.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted_value}"


if __name__ == "__main__":
    run()



