# README - Suite Consignado

Este documento descreve o estado atual do projeto e deve ser suficiente para uma pessoa ou outra IA entender, executar e reconstruir a solucao com boa fidelidade.

## 1. Objetivo do projeto

O projeto deixou de ser apenas uma automacao de simulacao em terminal.
Hoje ele cobre dois fluxos principais:

1. simulacao de consignado ponta a ponta
2. geracao de proposta a partir da simulacao

A suite roda com integracoes reais, sem depender de mocks no fluxo principal, e conversa diretamente com:

- API do Consignado
- banco PostgreSQL do ambiente escolhido
- Google Sheets com massa operacional por processadora
- endpoints auxiliares de processadoras como CIP e SERPRO

O projeto possui duas interfaces:

- fluxo terminal em `main.py`
- fluxo web em `webapp.py`

## 2. Capacidades atuais

Hoje a suite consegue:

- carregar configuracao por ambiente via `.env`
- autenticar na API com refresh automatico de token
- consultar lojas do usuario (`my-stores`) e montar query string para consultas de dashboard
- validar conexao com o banco
- listar convenios, produtos, modalidades e tipos de saque
- descobrir a processadora de cada convenio via `/admin/agreement/{id}`
- consultar Google Sheets e selecionar um registro elegivel
- enriquecer dados online com `dataprev/list-benefits`, `cip/list-benefits` e `serpro/list-benefits`
- gerar simulacoes em `/admin/simulation`
- transformar a simulacao em proposta via `/admin/proposal`
- oferecer um frontend web para operar o fluxo de simulacao e proposta
- consultar o dashboard da proposta para extrair dados da esteira (flow, stages)
- armazenar em memoria o contexto completo de cada proposta gerada, incluindo dados de esteira, segregado por ambiente
- limpar historico automaticamente ao recarregar a pagina
- permitir configurar a matriz de avaliacao da esteira de cada proposta via modal interativo
- executar etapas da esteira automaticamente via `finish` ou monitorar via `wait`/`manual`
- acompanhar execucao da esteira em tempo real com polling de status
- expandir linhas do historico para visualizar esteira inline com status por etapa
- executar todas as propostas do historico em lote ("Testar Tudo")

## 3. Estrutura do projeto

Na raiz:

- `main.py`
- `webapp.py`
- `requirements.txt`
- `pyproject.toml`
- `.env`
- `credentials.json`
- `.gitignore`
- `frontend/`
- `src/`
- `tests/`
- `artifacts/`

Arquitetura atual de `src/`:

- `src/core/`: configuracao, bootstrap e historico de propostas em memoria
- `src/infra/`: integracoes externas como API, banco e Google Sheets
- `src/domain/`: regras e montagem de payloads de simulacao e proposta
- `src/services/`: servicos auxiliares, como Faker
- `src/interfaces/terminal/`: fluxo do terminal
- `src/interfaces/web/`: backend local do frontend

Arquivos principais por camada:

- `src/core/config.py`: carrega `.env` e resolve configuracoes por ambiente
- `src/core/proposal_history.py`: historico de propostas em memoria, segregado por ambiente
- `src/infra/database.py`: conexao PostgreSQL com pool e cache
- `src/infra/api_client.py`: autenticacao, refresh de token, chamadas HTTP com reuso de sessao, finish de etapas da esteira
- `src/infra/google_sheets.py`: leitura da planilha e escolha de registro elegivel com cache
- `src/domain/simulation.py`: montagem e validacao do payload de simulacao
- `src/domain/proposal.py`: montagem dos payloads e identificadores da proposta
- `src/services/fake_data.py`: geracao de dados com Faker
- `src/interfaces/terminal/runner.py`: orquestracao do fluxo terminal
- `src/interfaces/web/server.py`: backend HTTP local que atende o frontend, motor de execucao de esteira em background

Pontos de entrada:

- `main.py`: inicia o fluxo terminal
- `webapp.py`: publica o frontend web local

Estrutura reservada para crescimento da suite:

- `tests/e2e`: validacoes ponta a ponta
- `tests/unit`: testes de regras isoladas
- `tests/fixtures`: massas e arquivos auxiliares
- `artifacts/`: saidas e evidencias futuras da suite

Arquivos importantes em `frontend/`:

- `frontend/index.html`
- `frontend/assets/scripts/app.js`
- `frontend/assets/styles/app.css`
- `frontend/assets/logo1.svg`
- `frontend/assets/logo2.svg`
- `frontend/assets/images/senff_logo_inverted.png`

## 4. Dependencias

O `requirements.txt` deve conter pelo menos:

```txt
python-dotenv==1.1.0
requests==2.32.3
psycopg2-binary==2.9.10
gspread==6.2.1
google-auth==2.40.3
Faker
```

## 5. Segredos e versionamento

Arquivos sensiveis:

- `.env`
- `credentials.json`

O `.gitignore` precisa ignorar ao menos:

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

Nunca documentar segredos reais no README.

## 6. Formato do `.env`

O `.env` deve conter configuracoes para:

- `HOMOLOG`
- `DEV`
- `RANCHER`

Variaveis por ambiente:

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
SENFF_LOGO_URL=
SENFF_ICON_URL=
```

Observacoes:

- `DEFAULT_ACCOUNT` e `DEFAULT_STORE_CODE` entram em todos os requests
- `SENFF_ICON_URL` alimenta o favicon do frontend
- a rota `/api/app-config` continua expondo branding do `.env`
- a logo atual da sidebar esta mockada localmente em `frontend/assets/logo.svg`
- `config.py` normaliza URLs quando necessario:
  - `/auth` -> `/auth/v1/auth`
  - `/api` -> `/api/v1`

## 7. Fluxo do terminal

O fluxo principal do terminal segue esta ordem:

1. escolher ambiente
2. autenticar na API
3. consultar lojas do usuario (`my-stores`)
4. validar conexao com o banco
5. escolher convenio
6. descobrir a processadora
7. escolher produto
8. consultar a planilha da processadora
9. preencher nome e telefone
10. escolher modalidade
11. escolher tipo de saque
12. enriquecer dados da processadora quando necessario
13. gerar simulacao
14. gerar proposta
15. consultar dashboard para extrair dados da esteira

### Menus vindos do banco

Ordenar sempre por `id ASC`:

- `agreements`
- `products`
- `sale_modalities`
- `withdraw_types`

## 8. Google Sheets e processadoras

Planilha:

```txt
18gmFibQE9dzbBkyuZFW3_kCvpAZc1arKmA0XFYGE5d4
```

Mapeamento de abas:

- `dataprev` -> `DATAPREV`
- `cip` -> `CIP`
- `serpro` -> `SERPRO`
- `zetra` -> `ZETRA`
- `econsig-zetra` -> `ZETRA`

Regra base:

- carregar apenas linhas com `Cpf` preenchido
- quando houver varios registros elegiveis, usar o primeiro
- se nao houver elegivel, oferecer tentar novamente ou encerrar
- a leitura usa `value_render_option=FORMATTED_VALUE` e `numericise_ignore=['all']` para preservar zeros a esquerda em campos como CPF e Matricula (ex: `04611813126` em vez de `4611813126`)

### DATAPREV

- exigir `Status = Ok`
- RCC -> `Saldo Atualizado RCC > 0`
- RMC -> `Saldo Atualizado RMC > 0`
- capturar `Matricula/Beneficio`, `Cpf`, `Nome`
- chamar `GET /api/v1/admin/dataprev/list-benefits` antes da simulacao (params: `document`, `name`)
- a margem online da DATAPREV substitui a margem da planilha
- em caso de falha, seguir com os dados da planilha

### CIP

- RCC -> `Saldo Atualizado RCC > 0`
- RMC -> `Saldo Atualizado RMC > 0`
- capturar `Matricula/Beneficio`, `Cpf`

### SERPRO

- RCC -> `Saldo Atualizado RCC > 0`
- RMC -> `Saldo Atualizado RMC > 0`
- capturar `Matricula/Beneficio`, `Cpf`, `Orgao`

### ZETRA

- ignorar o produto para selecao do saldo
- usar sempre `Saldo Atualizado RCC > 0`
- capturar `Matricula/Beneficio`, `Cpf`, `Senha`

## 9. Coleta de dados do cliente

Regras atuais:

- nome: sempre perguntar entre manual ou Faker
- telefone: manual ou Faker
- CPF: vem da base e deve ser usado automaticamente quando existir
- matricula, beneficio, senha e dados de processadora nao devem usar Faker se vierem da planilha

## 10. Simulacao

Endpoint principal:

```http
POST /api/v1/admin/simulation
```

Obrigatorios gerais:

- `data.agreement.id`
- `data.product.id`
- `data.sale_modality.id`
- `data.withdraw_type.id`
- `data.client.name`
- `data.client.document`
- `data.client.phone`
- `data.margin_value`

Regras importantes:

- `margin_value` e `income_value` devem ir em centavos
- nao enviar `balance_id`
- nao enviar `simulation_type`
- em caso de `401`, a sessao deve autenticar novamente e repetir a chamada uma vez

### CIP

- em Homolog, usar `cip_agency_id = 1`
- chamar `GET /api/v1/admin/cip/list-benefits` depois da escolha do tipo de saque
- a margem online da CIP substitui a margem da planilha
- em caso de falha (`EncryptionException` / `XmlEncrypto`), seguir com a margem da planilha

### SERPRO

- chamar `GET /api/v1/admin/serpro/list-benefits` antes da simulacao
- campos mais importantes para o payload:
  - `agreement.serpro_agency_id`
  - `sponsor_benefit_number`

### ZETRA

- `benefit_number` obrigatorio
- `user_password` opcional
- `benefit_number` normalmente vem da matricula da planilha

## 11. Geracao de proposta

Depois que a simulacao e criada com sucesso, a suite continua para a proposta.

Fluxo resumido:

1. obter `client_id` a partir da simulacao
2. carregar catalogos obrigatorios para montagem do cliente
3. consultar `GET /admin/client/{id}`
4. localizar os dados base do cliente e do beneficio
5. gerar automaticamente os campos complementares com Faker
6. atualizar o cliente com `PUT /admin/client/{id}`
7. localizar os IDs finais necessarios para a proposta
8. enviar `POST /admin/proposal`

### Regras importantes da proposta

- o CPF usado na simulacao deve continuar sendo o documento principal do cliente
- o documento principal vira `client_main_document_id`
- o documento contratual deve ser gerado separadamente
- o documento contratual nunca pode se misturar com o CPF
- o tipo do documento contratual e escolhido automaticamente entre `RG` e `CNH`
- o documento contratual vira `client_contract_document_id`

### Dados gerados automaticamente para proposta

A etapa de proposta usa Faker para completar dados como:

- nascimento
- nome da mae
- email
- endereco
- banco
- agencia
- conta
- documento contratual
- renda
- demais campos auxiliares exigidos para emissao

Essas regras sao centralizadas em:

- `build_complete_client_payload()`
- `build_proposal_payload()`
- `extract_main_document_id()`
- `extract_related_client_ids()`
- `select_client_benefit_data()`

Arquivo principal dessa etapa:

- `src/domain/proposal.py`

## 12. Historico de propostas em memoria

Cada proposta gerada com sucesso e salva automaticamente em memoria, segregada pelo ambiente em que foi criada (HOMOLOG, DEV, RANCHER). Isso permite que uma unica run do script acumule o contexto de todas as propostas geradas.

O modulo responsavel e `src/core/proposal_history.py`.

Cada registro (`ProposalRecord`) contem:

- identificadores da simulacao: `simulation_id`, `simulation_code`, `client_id`
- identificadores da proposta: `proposal_id`, `proposal_code`, `contract_code`
- contexto de entrada: `agreement_id`, `product_id`, `sale_modality_id`, `withdraw_type_id`, `processor_code`
- dados do cliente: `client_name`, `client_document`, `client_phone`, `benefit_number`
- dados gerados: `contract_document_type`, `contract_document_number`, `email`
- dados de esteira: `flow` (`ProposalFlow` com `proposal_id`, `flow_id` e lista de `FlowStage`)
- responses completas da API: `simulation_response`, `proposal_response`

Cada `FlowStage` contem: `id`, `code`, `name`, `status`.

Funcoes disponiveis:

- `record_proposal(record)`: salva e retorna o indice (1-based)
- `get_history(environment_key)`: retorna todos os registros de um ambiente
- `count(environment_key)`: contagem de propostas de um ambiente
- `get_all_history()`: retorna o mapa completo de todos os ambientes
- `clear_history()`: limpa todo o historico de todos os ambientes
- `extract_proposal_flow(dashboard_response)`: extrai dados de esteira do retorno do dashboard

No frontend web:

- `GET /api/proposal-history?environment=HOMOLOG` expoe o historico com dados de esteira
- `DELETE /api/proposal-history` limpa o historico (chamado automaticamente ao recarregar a pagina)

O historico e os dados de esteira sao a base para a validacao automatizada de propostas.

## 12.1 Motor de execucao da esteira

Apos configurar a matriz de avaliacao de uma proposta, o usuario pode executar a esteira. O motor processa cada etapa sequencialmente em uma thread em background.

### Acoes por etapa

| Acao | Comportamento |
|---|---|
| `wait` | Monitora a etapa ate resolucao natural (aprovada, reprovada ou manual). Timeout: 60s. |
| `manual` | Igual a `wait` — monitora sem intervir. Timeout: 60s. |
| `finish` | Chama `PUT /admin/proposal/{id}/flow/{flowId}/stage/{stageId}/finish` e depois monitora ate resolucao. Timeout: 5s pos-finish. |

### Classificacao de status das etapas

O motor classifica o status retornado pelo dashboard em categorias:

- **Sucesso:** APPROVED, SUCCESS, DONE, COMPLETED, COMPLETE, FINISHED, OK
- **Falha:** FAIL, FAILED, ERROR, REJECTED, DENIED, CANCELED, CANCELLED, INVALID
- **Manual:** MANUAL, MANUAL_ANALYSIS, PENDING_MANUAL, ou qualquer status contendo "MANUAL"
- **Em progresso:** IN_PROGRESS, PROCESSING, RUNNING, STARTED

### Controle de estado

O estado de execucao e gerenciado por `(ambiente, indice_historico)` com acesso thread-safe. Estados possiveis: `idle`, `running`, `completed`, `failed`, `manual_pending`, `waiting`.

Cada etapa processada produz um registro com: `stageId`, `stageCode`, `stageName`, `action`, `status`, `result`, `message`. Se uma etapa falha ou expira, a execucao para naquela etapa.

### Execucao em lote

O botao "Testar Tudo" (visivel quando ha 2+ propostas no historico) executa todas as propostas sequencialmente usando suas configuracoes de esteira.

## 13. Performance

O backend aplica as seguintes otimizacoes:

- sessao API cacheada por ambiente: autenticacao OAuth reutilizada entre requests
- pool HTTP com `requests.Session` e `HTTPAdapter` reutilizado pela sessao cacheada
- pool de conexoes PostgreSQL via `ThreadedConnectionPool`
- cache de queries do banco via `@lru_cache`
- cache de catalogos da API (`list_catalog_options`) por chave de ambiente
- cache de dados do Google Sheets por aba de processadora
- queries do banco no connect rodam em paralelo (`ThreadPoolExecutor`)
- 6 catalogos da proposta buscados em paralelo
- fetch de catalogos e fetch de cliente rodam em paralelo na proposta
- pre-carregamento de todas as abas do Google Sheets em background no connect

## 14. Frontend web

O projeto agora possui um frontend web local para operar o fluxo de simulacao e proposta.

### Como iniciar

```bash
python webapp.py
```

Padrao:

- host: `127.0.0.1`
- porta: `8765`

### Componentes web

- `webapp.py`: inicia o servidor local
- `src/interfaces/web/server.py`: recebe requests do frontend e reaproveita as regras de negocio do backend local
- `frontend/index.html`: shell da interface
- `frontend/assets/scripts/app.js`: estado, eventos e chamadas AJAX
- `frontend/assets/styles/app.css`: layout e visual

### Endpoints internos do frontend

O `server.py` expoe pelo menos:

- `GET /api/app-config`
- `GET /api/environments`
- `GET /api/faker?kind=name`
- `GET /api/faker?kind=phone`
- `GET /api/proposal-history?environment=HOMOLOG`
- `DELETE /api/proposal-history`
- `POST /api/session/connect`
- `POST /api/session/preview`
- `POST /api/session/simulate`
- `POST /api/session/proposal`
- `POST /api/proposal-history/flow`
- `POST /api/proposal-history/execute`
- `POST /api/proposal-history/execution-status`

### O que o frontend faz hoje

- conecta no ambiente escolhido
- carrega acordos, produtos, modalidades e tipos de saque
- consulta a base da processadora
- permite preencher nome e telefone
- gera simulacao
- emite proposta a partir da simulacao
- mostra resumo visual com cards de Contrato (codigo extraido de `data.code` da resposta de proposta) e Proposta (codigo da simulacao)
- exibe tabela de historico com todas as propostas geradas na sessao
- permite configurar a matriz de avaliacao da esteira de cada proposta via modal interativo com pipeline visual e opcoes por etapa (Aguardar/Manual/Finalizar)
- permite expandir linhas do historico para visualizar a esteira inline com status coloridos por etapa
- permite executar a esteira de cada proposta individualmente (botao ▶) com acompanhamento em tempo real
- permite executar todas as propostas do historico em lote ("Testar Tudo") quando ha 2+ propostas
- permite iniciar uma nova proposta sem reiniciar a aplicacao
- possui sidebar colapsavel, header fixo, footer fixo e layout mais clean

### Branding atual do frontend

- favicon vem de `SENFF_ICON_URL`
- a logo da sidebar esta mockada localmente em `frontend/assets/logo1.svg`
- existe tambem o asset alternativo `frontend/assets/images/senff_logo_inverted.png`

## 15. UX do terminal

Regras principais:

- terminal menos verboso
- mensagens curtas e amigaveis
- uso moderado de emojis
- nao mostrar token
- nao despejar JSON bruto em sucesso
- exibir diagnosticos melhores em falhas
- manter logs especificos por etapa quando houver erro

## 16. Tratamento de erros

Erros conhecidos:

- `XmlEncrypto` ou `EncryptionException`: problema interno da integracao CIP/WsSecurity
- `AvailableProductsByClientAdapter.php:43`: falha do backend de seguros

Em caso de erro:

- mostrar mensagem amigavel
- mostrar diagnostico curto
- mostrar resumo tecnico quando necessario
- evitar despejar payload completo sem necessidade

## 17. Execucao local

### Terminal

```bash
python main.py
```

### Frontend web

```bash
python webapp.py
```

## 18. Estado funcional esperado

A implementacao atual deve permitir, no minimo:

- INSS / DATAPREV: simulacao funcionando com `dataprev/list-benefits`
- PREF CURITIBA / ZETRA: simulacao funcionando
- SIAPE / SERPRO: simulacao funcionando com `serpro/list-benefits`
- PREF SP / CIP: simulacao funcionando com `cip/list-benefits`
- geracao de proposta a partir da simulacao
- consulta automatica ao dashboard para extrair esteira da proposta
- acumulo de historico de propostas em memoria por ambiente com dados de esteira
- configuracao da matriz de avaliacao de cada proposta via modal interativo
- execucao automatica de etapas da esteira (finish) com monitoramento em tempo real
- execucao em lote de todas as propostas do historico
- visualizacao inline das etapas da esteira na tabela de historico
- operacao do fluxo completo pelo frontend web

## 19. Checklist de reconstrucao

Se for reconstruir o projeto do zero, seguir esta ordem:

1. criar estrutura base e `.venv`
2. implementar configuracao por ambiente
3. implementar autenticacao com refresh de token
4. implementar consulta `my-stores` pos-autenticacao
5. implementar consultas do banco
6. implementar Google Sheets por processadora
7. implementar simulacao
8. implementar proposta
9. implementar consulta ao dashboard pos-proposta
10. implementar historico de propostas em memoria com dados de esteira
11. implementar UX do terminal
12. implementar backend web local
13. implementar frontend web com modal de matriz de avaliacao
14. implementar motor de execucao de esteira com finish, wait e monitoramento em background
15. implementar polling de status e acompanhamento em tempo real no frontend
16. implementar execucao em lote ("Testar Tudo")
17. validar sintaxe e smoke tests locais

## 20. Regra final de fidelidade

Se outra IA precisar reconstruir o projeto, ela deve preservar estas caracteristicas:

- integracoes reais com API, banco e planilha
- descoberta da processadora via endpoint de agreement
- regras especificas por processadora para margem e campos auxiliares
- nome sempre manual ou Faker
- telefone manual ou Faker
- CPF automatico quando vier da base
- geracao de proposta a partir da simulacao
- consulta ao dashboard e extracao de dados de esteira pos-proposta
- historico de propostas em memoria segregado por ambiente com dados de esteira
- consulta `my-stores` pos-autenticacao para contexto de lojas
- motor de execucao de esteira com acoes configuráveis (finish/wait/manual) por etapa
- execucao em background com polling de status em tempo real
- classificacao de status de etapas (sucesso, falha, manual, em progresso)
- execucao em lote de todas as propostas do historico
- frontend web consumindo um backend local em Python
- experiencia mais amigavel para usuario final, tanto no terminal quanto na web
