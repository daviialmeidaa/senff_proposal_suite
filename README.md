# Documentação e Reconstrução

Este documento existe para permitir que outra IA reconstrua este projeto com alta fidelidade, mesmo sem acesso ao historico da conversa.

## 1. Objetivo do projeto

Criar uma automacao em Python, com boas praticas de estrutura, `.venv`, `requirements.txt`, `main.py` na raiz e modulos em `src/`, capaz de:

1. carregar configuracoes por ambiente via `.env`
2. autenticar na API
3. conectar no banco de dados do ambiente escolhido
4. listar menus interativos no terminal
5. consultar Google Sheets para obter dados operacionais
6. enriquecer dados via endpoints auxiliares da API
7. montar e enviar uma requisicao para `/api/v1/admin/simulation`
8. ser amigavel para usuario final no terminal

O usuario final escolhe:

1. ambiente
2. convenio
3. produto
4. modalidade de venda
5. tipo de saque

O sistema descobre automaticamente:

1. processadora do convenio
2. aba correta da planilha
3. registro elegivel da planilha
4. margem e dados complementares por processadora

## 2. Estrutura esperada do projeto

Na raiz devem existir:

- `main.py`
- `requirements.txt`
- `.env`
- `credentials.json`
- `.gitignore`
- `src/`

Arquivos esperados dentro de `src/`:

- `__init__.py`
- `config.py`
- `database.py`
- `api_client.py`
- `google_sheets.py`
- `simulation.py`
- `fake_data.py`
- `runner.py`

Responsabilidade de cada arquivo:

- `main.py`: ponto de entrada, apenas chama `run()`
- `config.py`: carrega e valida `.env`, monta configuracao por ambiente
- `database.py`: conexao PostgreSQL e consultas de menus
- `api_client.py`: autenticacao, reautenticacao automatica e chamadas HTTP
- `google_sheets.py`: leitura da planilha e selecao de registros elegiveis
- `simulation.py`: montagem e validacao do payload de simulacao
- `fake_data.py`: geracao de dados ficticios com Faker
- `runner.py`: orquestrador de toda a jornada do terminal

## 3. Dependencias

O `requirements.txt` precisa conter:

```txt
python-dotenv==1.1.0
requests==2.32.3
psycopg2-binary==2.9.10
gspread==6.2.1
google-auth==2.40.3
Faker
```

## 4. Segredos e versionamento

### Arquivos sensiveis

- `.env`
- `credentials.json`

### Gitignore

O `.gitignore` precisa ignorar pelo menos:

```gitignore
.venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.mypy_cache/
.ruff_cache/
credentials.json
```

Nunca escrever valores reais de segredo em documentacao ou commits.

## 5. Formato do `.env`

O `.env` precisa ter uma secao por ambiente:

- `HOMOLOG`
- `DEV`
- `RANCHER`

Cada ambiente usa estas variaveis:

```env
HOMOLOG_AUTH_URL=
HOMOLOG_API_URL=
HOMOLOG_TENANT_ID=
HOMOLOG_USER=
HOMOLOG_PASS=
HOMOLOG_DB_HOST=
HOMOLOG_DB_PORT=
HOMOLOG_DB_DATABASE=
HOMOLOG_DB_USERNAME=
HOMOLOG_DB_PASSWORD=

DEV_AUTH_URL=
DEV_API_URL=
DEV_TENANT_ID=
DEV_USER=
DEV_PASS=
DEV_DB_HOST=
DEV_DB_PORT=
DEV_DB_DATABASE=
DEV_DB_USERNAME=
DEV_DB_PASSWORD=

RANCHER_AUTH_URL=
RANCHER_API_URL=
RANCHER_TENANT_ID=
RANCHER_USER=
RANCHER_PASS=
RANCHER_DB_HOST=
RANCHER_DB_PORT=
RANCHER_DB_DATABASE=
RANCHER_DB_USERNAME=
RANCHER_DB_PASSWORD=

DEFAULT_ACCOUNT=
DEFAULT_STORE_CODE=
```

Observacoes:

- `DEFAULT_ACCOUNT` e `DEFAULT_STORE_CODE` sao globais e entram em todos os requests.
- `config.py` deve normalizar URLs:
  - se auth terminar em `/auth`, transformar em `/auth/v1/auth`
  - se api terminar em `/api`, transformar em `/api/v1`

## 6. Fluxo geral do terminal

O `runner.py` deve conduzir a jornada nesta ordem:

1. configurar console para UTF-8
2. carregar `.env`
3. mostrar menu de ambiente
4. autenticar na API
5. validar conexao com o banco
6. buscar convenios no banco e mostrar menu
7. consultar `/admin/agreement/{agreement_id}` para descobrir a processadora
8. buscar produtos no banco e mostrar menu
9. consultar a aba correta da planilha
10. selecionar um registro elegivel da planilha
11. coletar dados do cliente
12. se necessario, enriquecer dados via SERPRO ou CIP
13. buscar modalidades no banco e mostrar menu
14. se modalidade exigir, pedir `original_ccb_code` e `original_ccb_origin`
15. buscar tipos de saque no banco e mostrar menu
16. se processadora for CIP, consultar `cip/list-benefits` apos o `withdraw_type`
17. montar payload de simulacao
18. enviar `/admin/simulation`
19. mostrar resumo amigavel do resultado

## 7. Menus do banco

Todos os menus vindos do banco devem ser ordenados por `id ASC`.

### Tabelas e campos usados

- `agreements`: usar `id`, `name`
- `products`: usar `id`, `name`
- `sale_modalities`: usar `id`, `name`
- `withdraw_types`: usar `id`, `name`

Queries esperadas:

```sql
SELECT id, name FROM agreements WHERE name IS NOT NULL ORDER BY id ASC;
SELECT id, name FROM products WHERE name IS NOT NULL ORDER BY id ASC;
SELECT id, name FROM sale_modalities WHERE name IS NOT NULL ORDER BY id ASC;
SELECT id, name FROM withdraw_types WHERE name IS NOT NULL ORDER BY id ASC;
```

## 8. Autenticacao da API

Autenticacao feita com `POST` em `auth_url`.

Headers obrigatorios:

- `account`
- `tenant-id`
- `x-store-code`
- `Content-Type: application/json`

Body:

```json
{
  "username": "<ENV_USER>",
  "password": "<ENV_PASS>"
}
```

Exemplo de `curl`:

```bash
curl --location '{{AUTH_URL}}' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "username": "{{ENV_USER}}",
    "password": "{{ENV_PASS}}"
  }'
```

Regras importantes:

- o token precisa ficar em memoria
- em caso de `401`, a classe de sessao deve autenticar novamente e repetir a requisicao uma unica vez
- todos os requests autenticados devem enviar:
  - `account`
  - `tenant-id`
  - `x-store-code`
  - `Authorization: Bearer <token>`

## 9. Descoberta da processadora

Assim que o convenio for escolhido, chamar:

```http
GET /api/v1/admin/agreement/{agreement_id}
```

Exemplo de `curl`:

```bash
curl --location '{{API_URL}}/admin/agreement/{{AGREEMENT_ID}}' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}'
```

Extrair:

- `data.processors[0].code`

Armazenar em memoria como `processor_code`.

Valores relevantes:

- `dataprev`
- `cip`
- `serpro`
- `zetra`
- `econsig-zetra`

## 10. Google Sheets

### Credenciais

O arquivo `credentials.json` fica na raiz do projeto.

### Planilha

ID da planilha:

```txt
18gmFibQE9dzbBkyuZFW3_kCvpAZc1arKmA0XFYGE5d4
```

### Abas por processadora

Mapeamento:

- `dataprev` -> `DATAPREV`
- `cip` -> `CIP`
- `serpro` -> `SERPRO`
- `zetra` -> `ZETRA`
- `econsig-zetra` -> `ZETRA`

### Colunas relevantes

As abas usam estes nomes de coluna:

- `Matricula/Beneficio`
- `Cpf`
- `Nome`
- `Orgao`
- `Senha`
- `Saldo Atualizado RCC`
- `Saldo Atualizado RMC`
- `Status`

### Regra base de carregamento

Carregar apenas linhas com `Cpf` preenchido.

### Regras de elegibilidade por aba

#### DATAPREV

- considerar apenas `Status = Ok`
- se produto for RCC, usar `Saldo Atualizado RCC > 0`
- se produto for RMC, usar `Saldo Atualizado RMC > 0`
- capturar:
  - `Matricula/Beneficio`
  - `Cpf`
  - `Nome`

#### CIP

- se produto for RCC, usar `Saldo Atualizado RCC > 0`
- se produto for RMC, usar `Saldo Atualizado RMC > 0`
- capturar:
  - `Matricula/Beneficio`
  - `Cpf`
  - opcionalmente `Orgao`

#### SERPRO

- se produto for RCC, usar `Saldo Atualizado RCC > 0`
- se produto for RMC, usar `Saldo Atualizado RMC > 0`
- capturar:
  - `Matricula/Beneficio`
  - `Cpf`
  - `Orgao`

#### ZETRA

- ignorar o produto para a escolha do saldo
- usar sempre `Saldo Atualizado RCC > 0`
- capturar:
  - `Matricula/Beneficio`
  - `Cpf`
  - `Senha`

### Regra de escolha

- quando houver varios registros elegiveis, usar o primeiro
- se nao houver registro elegivel, informar ao usuario e oferecer:
  - tentar novamente
  - encerrar

## 11. Coleta de dados do cliente

### Nome

Mesmo se a base trouxer um nome, sempre perguntar:

- `Inserir manualmente`
- `Gerar com Faker`

Se houver nome na base, mostrar como sugestao.

### Documento

- se vier da planilha, usar automaticamente
- nao pedir digitacao
- apenas informar que o CPF foi carregado automaticamente

### Telefone

- se nao existir, perguntar:
  - `Inserir manualmente`
  - `Gerar com Faker`

### Campos opcionais com fallback

Para campos como senha, sponsor benefit number etc., usar:

- manual
- Faker
- continuar sem informar

## 12. UX do terminal

O terminal precisa ser amigavel e menos verboso.

### Regras

- usar mensagens curtas e acolhedoras
- nao despejar JSON bruto em sucesso
- nao mostrar token
- nao mostrar URL base nem host do banco em execucoes normais
- usar emojis contextualizados, mas sem exagero
- usar resumo curto no final da simulacao

### Compatibilidade Windows

Como o terminal pode estar em `cp1252`, o `runner.py` deve chamar logo no inicio:

- `sys.stdout.reconfigure(encoding="utf-8")`
- `sys.stderr.reconfigure(encoding="utf-8")`

Sem isso, emojis podem quebrar a execucao.

### Mensagens finais de sucesso

Em caso de simulacao bem-sucedida, mostrar somente algo como:

- codigo da simulacao
- valor liberado
- parcela
- prazo

## 13. Faker

O `fake_data.py` deve oferecer:

- `generate_name()`
- `generate_document()`
- `generate_phone()`
- `generate_numeric_code(length)`
- `generate_password()`

Usar `Faker("pt_BR")`.

## 14. Processadora DATAPREV

Para DATAPREV, a simulacao usa principalmente:

- dados da planilha
- `processor_code` vindo do endpoint de agreement

Nao existe consulta auxiliar especifica extra antes do `/simulation`.

## 15. Processadora ZETRA / ECONSIG-ZETRA

### Regras

- a aba da planilha e sempre `ZETRA`
- `benefit_number` e obrigatorio no `/simulation`
- `user_password` e opcional

### Origem dos dados

- `benefit_number`: normalmente vem da matricula da planilha
- `user_password`: normalmente vem da coluna `Senha`
- se faltar:
  - pedir manualmente
  - ou gerar com Faker

### Payload

Para ZETRA, o payload precisa mandar:

- `data.benefit_number`
- `data.user_password` se houver

## 16. Processadora SERPRO

### Endpoint auxiliar obrigatorio

Antes da simulacao, chamar:

```http
GET /api/v1/admin/serpro/list-benefits
```

Parametros:

- `document`
- `name`
- `product_id`
- `agreement_id`

Exemplo de `curl`:

```bash
curl --location '{{API_URL}}/admin/serpro/list-benefits?document={{CLIENT_DOCUMENT}}&name={{CLIENT_NAME_URLENCODED}}&product_id={{PRODUCT_ID}}&agreement_id={{AGREEMENT_ID}}' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}'
```

### Campos importantes da resposta

- `benefit_number`
- `sponsor_benefit_number`
- `serpro_agency_id`
- `beneficiary_name`
- `margin_value`
- `margin_value_card`
- `margin_value_rcc`
- `blocked_for_loan`
- `eligible_loan`
- `serpro_benefit.department`
- `serpro_benefit.department_name`

### Regra de selecao do beneficio

- para RCC: escolher beneficio com `margin_value_rcc > 0`
- para RMC: escolher beneficio com `margin_value_card > 0`
- para emprestimo: escolher beneficio com `eligible_loan = true` e `margin_value > 0`
- preferir beneficios que nao estejam bloqueados
- se houver mais de um, mostrar menu para o usuario escolher

### Campos de simulacao que realmente importam

- `agreement.serpro_agency_id`
- `sponsor_benefit_number`

### Observacoes

- `benefit_number` pode ser enviado para espelhar a tela
- backend aceita `serpro_agency_sub_id` e `serpro_agency_sub_upag_id`, mas a tela atual nao depende deles

### Fallback se a consulta falhar

Se `list-benefits` falhar:

- avisar o usuario
- seguir com preenchimento assistido
- pedir manual/Faker para:
  - matricula
  - sponsor benefit number
  - serpro agency id

## 17. Processadora CIP

### Regra especial em Homolog

Para CIP em Homolog, usar `cip_agency_id = 1`.

### Endpoint auxiliar obrigatorio

A consulta CIP deve acontecer somente depois que o usuario escolhe o `withdraw_type`.

Chamar:

```http
GET /api/v1/admin/cip/list-benefits
```

Parametros:

- `document`
- `agency_id`
- `agreement_id`
- `product_id`
- `withdraw_type_id`
- `name`

Exemplo de `curl`:

```bash
curl --location '{{API_URL}}/admin/cip/list-benefits?document={{CLIENT_DOCUMENT}}&agency_id={{CIP_AGENCY_ID}}&agreement_id={{AGREEMENT_ID}}&product_id={{PRODUCT_ID}}&withdraw_type_id={{WITHDRAW_TYPE_ID}}&name={{CLIENT_NAME_URLENCODED}}' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}'
```

### Campos importantes da resposta

- `beneficiary_name`
- `benefit_number`
- `margin_value`
- `margin_value_card`
- `margin_value_rcc`
- `cip_agency_id`
- `cip_benefit.consult_margin.agency_identification`
- `cip_benefit.consult_margin.agency_name`

### Regra de uso

- para RCC, usar margem de `margin_value_rcc`
- para RMC, usar margem de `margin_value_card`
- se essas margens vierem zeradas, usar `margin_value` como fallback no model
- a margem retornada pela CIP deve substituir a margem da planilha

### Importante

Para CIP, a simulacao correta depende da margem do endpoint online. Nao confiar apenas na planilha.

### Fallback em caso de erro

Se `cip/list-benefits` falhar, oferecer:

1. tentar novamente
2. continuar com os dados da planilha
3. encerrar

Quando o backend da CIP falhar com `EncryptionException` ou `XmlEncrypto`, diagnosticar isso como problema do backend/integrador externo.

## 18. Modalidade de venda

Modalidades vem da tabela `sale_modalities`.

Se o nome da modalidade contiver:

- `agrega`
- `refin`

entao pedir:

- `original_ccb_code`
- `original_ccb_origin`

Os dois devem ser enviados juntos. Se apenas um for preenchido, considerar erro de validacao local.

## 19. Tipo de saque

Tipos vem da tabela `withdraw_types`.

IDs conhecidos:

- `1`: com saque
- `2`: sem saque

## 20. Endpoint de simulacao

### Endpoint

```http
POST /api/v1/admin/simulation
```

### Headers

- `account`
- `tenant-id`
- `x-store-code`
- `Authorization: Bearer <token>`
- `Content-Type: application/json`

### Campos obrigatorios gerais

- `data.agreement.id`
- `data.product.id`
- `data.sale_modality.id`
- `data.withdraw_type.id`
- `data.client.name`
- `data.client.document`
- `data.client.phone`
- `data.margin_value`

### Campos que nao devem ser enviados

- `balance_id`
- `simulation_type`

### Regras monetarias

- `margin_value` e `income_value` devem ir em centavos
- se o valor ja vier como `int`, tratar como centavos
- se vier como string no formato brasileiro, converter corretamente

### Estrutura base do payload

```json
{
  "data": {
    "agreement": {
      "id": 12
    },
    "product": {
      "id": 1
    },
    "sale_modality": {
      "id": 1,
      "original_ccb_code": null,
      "original_ccb_origin": null
    },
    "withdraw_type": {
      "id": 1
    },
    "client": {
      "name": "Nome do Cliente",
      "document": "00000000000",
      "phone": "00000000000"
    },
    "margin_value": 332300,
    "income_value": null,
    "sponsor_benefit_number": null,
    "client_benefit_number": null,
    "benefit_number": "123456",
    "user_password": null
  }
}
```

Exemplo de `curl` base:

```bash
curl --location '{{API_URL}}/admin/simulation' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "data": {
      "agreement": {
        "id": {{AGREEMENT_ID}}
      },
      "product": {
        "id": {{PRODUCT_ID}}
      },
      "sale_modality": {
        "id": {{SALE_MODALITY_ID}},
        "original_ccb_code": null,
        "original_ccb_origin": null
      },
      "withdraw_type": {
        "id": {{WITHDRAW_TYPE_ID}}
      },
      "client": {
        "name": "{{CLIENT_NAME}}",
        "document": "{{CLIENT_DOCUMENT}}",
        "phone": "{{CLIENT_PHONE}}"
      },
      "margin_value": {{MARGIN_VALUE_IN_CENTS}},
      "income_value": null,
      "sponsor_benefit_number": null,
      "client_benefit_number": null
    }
  }'
```

### Regras por processadora no payload

#### CIP

Adicionar:

```json
"agreement": {
  "id": 12,
  "cip_agency_id": 1
}
```

Exemplo de `curl` para CIP:

```bash
curl --location '{{API_URL}}/admin/simulation' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "data": {
      "agreement": {
        "id": {{AGREEMENT_ID}},
        "cip_agency_id": {{CIP_AGENCY_ID}}
      },
      "product": {
        "id": {{PRODUCT_ID}}
      },
      "sale_modality": {
        "id": {{SALE_MODALITY_ID}},
        "original_ccb_code": null,
        "original_ccb_origin": null
      },
      "withdraw_type": {
        "id": {{WITHDRAW_TYPE_ID}}
      },
      "client": {
        "name": "{{CLIENT_NAME}}",
        "document": "{{CLIENT_DOCUMENT}}",
        "phone": "{{CLIENT_PHONE}}"
      },
      "margin_value": {{MARGIN_VALUE_IN_CENTS}},
      "income_value": null,
      "client_benefit_number": null
    }
  }'
```

#### SERPRO

Adicionar:

```json
"agreement": {
  "id": 9,
  "serpro_agency_id": 242
}
```

Opcionalmente:

- `serpro_agency_sub_id`
- `serpro_agency_sub_upag_id`

Exemplo de `curl` para SERPRO:

```bash
curl --location '{{API_URL}}/admin/simulation' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "data": {
      "agreement": {
        "id": {{AGREEMENT_ID}},
        "serpro_agency_id": {{SERPRO_AGENCY_ID}}
      },
      "product": {
        "id": {{PRODUCT_ID}}
      },
      "sale_modality": {
        "id": {{SALE_MODALITY_ID}},
        "original_ccb_code": null,
        "original_ccb_origin": null
      },
      "withdraw_type": {
        "id": {{WITHDRAW_TYPE_ID}}
      },
      "client": {
        "name": "{{CLIENT_NAME}}",
        "document": "{{CLIENT_DOCUMENT}}",
        "phone": "{{CLIENT_PHONE}}"
      },
      "margin_value": {{MARGIN_VALUE_IN_CENTS}},
      "income_value": null,
      "sponsor_benefit_number": "{{SPONSOR_BENEFIT_NUMBER}}",
      "client_benefit_number": null,
      "benefit_number": "{{BENEFIT_NUMBER}}",
      "user_password": null
    }
  }'
```

#### ZETRA

Adicionar:

- `benefit_number`
- `user_password` se houver

Exemplo de `curl` para ZETRA:

```bash
curl --location '{{API_URL}}/admin/simulation' \
  --header 'account: {{DEFAULT_ACCOUNT}}' \
  --header 'tenant-id: {{TENANT_ID}}' \
  --header 'x-store-code: {{DEFAULT_STORE_CODE}}' \
  --header 'Authorization: Bearer {{ACCESS_TOKEN}}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "data": {
      "agreement": {
        "id": {{AGREEMENT_ID}}
      },
      "product": {
        "id": {{PRODUCT_ID}}
      },
      "sale_modality": {
        "id": {{SALE_MODALITY_ID}},
        "original_ccb_code": null,
        "original_ccb_origin": null
      },
      "withdraw_type": {
        "id": {{WITHDRAW_TYPE_ID}}
      },
      "client": {
        "name": "{{CLIENT_NAME}}",
        "document": "{{CLIENT_DOCUMENT}}",
        "phone": "{{CLIENT_PHONE}}"
      },
      "margin_value": {{MARGIN_VALUE_IN_CENTS}},
      "income_value": null,
      "sponsor_benefit_number": null,
      "client_benefit_number": null,
      "benefit_number": "{{BENEFIT_NUMBER}}",
      "user_password": "{{USER_PASSWORD_OR_NULL}}"
    }
  }'
```

## 21. Tratamento de erros

### Reautenticacao

Em caso de `401`, autenticar novamente e repetir a chamada.

### Erros conhecidos de backend

Se a mensagem contiver:

- `XmlEncrypto`
- `EncryptionException`

diagnosticar como falha interna da integracao CIP/WsSecurity.

Se a mensagem contiver:

- `AvailableProductsByClientAdapter.php:43`

diagnosticar como falha do backend de seguros.

### Em erro de simulacao

Mostrar:

- mensagem amigavel
- diagnostico curto
- resumo tecnico mascarado do payload enviado

Mas nao despejar JSON completo no terminal.

## 22. Funcoes importantes que devem existir

No estado final, a solucao deve ter pelo menos equivalentes a estas responsabilidades:

- `load_environment_file()`
- `get_environment_config()`
- `connect()`
- `test_connection()`
- `fetch_agreements()`
- `fetch_products()`
- `fetch_sale_modalities()`
- `fetch_withdraw_types()`
- `ApiSession.authenticate()`
- `ApiSession.request()`
- `fetch_agreement_processor_code()`
- `list_serpro_benefits()`
- `list_cip_benefits()`
- `create_simulation()`
- `GoogleSheetsService.load_processor_data()`
- `GoogleSheetsService.select_record_from_data()`
- `build_simulation_payload()`
- `money_to_cents()`
- `prompt_client_info()`
- `prompt_name_field()`
- `print_simulation_success()`

## 23. Estado funcional esperado

A implementacao final deve permitir, no minimo:

- INSS / DATAPREV: simulacao com sucesso
- PREF CURITIBA / ZETRA: simulacao com sucesso
- SIAPE / SERPRO: simulacao com sucesso usando `serpro/list-benefits`
- PREF SP / CIP: simulacao com sucesso usando `cip/list-benefits`

Historicamente:

- PREF SP falhava quando usava apenas a margem da planilha
- passou a funcionar depois que a margem do `cip/list-benefits` passou a substituir a da planilha

## 24. Checklist de reconstrucao

Se precisar reconstruir o projeto do zero, siga esta ordem:

1. criar estrutura da pasta e `main.py`
2. criar `.venv`
3. criar `requirements.txt`
4. implementar `config.py`
5. implementar `database.py`
6. implementar `api_client.py` com refresh de token
7. implementar `google_sheets.py`
8. implementar `simulation.py`
9. implementar `fake_data.py`
10. implementar `runner.py`
11. ignorar `credentials.json` no `.gitignore`
12. validar sintaxe com `python -m compileall`
13. validar fluxos em Homolog

## 25. Regra final de fidelidade

Se for reconstruir esse projeto, ela deve preservar estas caracteristicas:

- menus por banco ordenados por `id ASC`
- descoberta da processadora via endpoint de agreement
- selecao da aba da planilha por processadora
- regras especificas por processadora para margem e campos auxiliares
- nome sempre com escolha manual ou Faker
- CPF automatico se vier da base
- fallbacks amigaveis para erros operacionais
- terminal enxuto, amigavel, com emojis moderados e mensagens em portugues
- `credentials.json` fora do versionamento
