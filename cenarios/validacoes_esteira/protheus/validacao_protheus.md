# Validação Protheus — Documentação Técnica

> **Projeto:** PJT257 - Automação da Esteira Senff
> **Módulo:** `app/services/validator.py` · `DatabaseValidator`
> **Suíte:** Test Suite 1 (Protheus — Formalização e Emissão)

---

## Visão Geral

A validação do Protheus é executada em **duas etapas sequenciais** durante o percurso da proposta na esteira:

| Ordem | Etapa | Step Code | Método |
|---|---|---|---|
| 1 | Formalização | `protheus` | `validate_protheus_logs()` |
| 2 | Emissão | `protheus-issuance` | `validate_protheus_issuance_logs()` |

Ambas as etapas combinam **consultas ao banco de dados** com **chamadas a APIs SOAP externas** do Protheus (CloudTOTVS), e todo o resultado é registrado em logs de evidência e auditoria que alimentam o relatório HTML final.

---

## Contexto de Execução

Antes das validações serem disparadas, o orquestrador (`main.py → run_workflow_rules()`) realiza uma consulta auxiliar para enriquecer cada proposta com seu identificador de rastreamento:

### Consulta auxiliar — `correlation_id`

**Tabela:** `proposals`

```sql
SELECT correlation_id FROM proposals WHERE code = :code
```

- **Parâmetro:** `code` = `codigo_criacao` da proposta (ex.: `SC0000123`)
- **Retorno:** UUID que será usado como chave em todas as consultas subsequentes ao Protheus

---

## Etapa 1 — Formalização (`protheus`)

**Disparada quando:** a etapa `protheus` aparece no dashboard da proposta.

**Objetivo:** confirmar que o Protheus executou corretamente a validação do fornecedor (VALFOR) e a atualização de dados (ATUALIZAR) para a proposta.

**Resultado esperado:** `(db_valfor_ok OR api_valfor_ok) AND db_atualizar_ok`

---

### 1.1 — Consulta em banco: leitura dos logs Protheus

**Tabela:** `protheus_logs`

```sql
SELECT id, http_verb, url, request_headers, request_body, response_body, http_status_code
FROM protheus_logs
WHERE correlation_id = :cid
ORDER BY id ASC
```

- **Parâmetro:** `cid` = `correlation_id` da proposta
- **Retorno:** lista de todos os logs registrados pelo Protheus para a proposta, em ordem cronológica

**Log de auditoria gerado:**
- Origem: `AUDITORIA - Leitura de logs Protheus`
- Registra a quantidade de linhas retornadas

---

### 1.2 — Análise dos logs: definição do ponto de corte (`cutoff_id`)

Após a leitura, os logs são varridos para identificar o **ponto de corte** — o último log relevante para a formalização. Logs com `id > cutoff_id` são descartados.

**Regra 1 (prioritária):** localiza o primeiro log onde:
- `request_body` contém `ATUALIZAR`
- `response_body` contém `<STATUS>true</STATUS>`

→ esse log define o `cutoff_id` e seta `db_atualizar_ok = True`

**Regra 2 (fallback do corte):** se a Regra 1 não encontrar nada, localiza o primeiro log onde:
- `request_headers` contém `VALFOR`
- `response_body` contém `<RETWS>false</RETWS>`

→ esse log define o `cutoff_id` alternativo e seta `db_valfor_ok = True`

---

### 1.3 — Montagem das evidências de formalização

Para cada log dentro do intervalo válido (`id <= cutoff_id`), é gerado um **log de evidência**:

| Campo | Valor |
|---|---|
| `kind` | `evidence` |
| `label` | `Evidencia Formalizacao` |
| `source_type` | `DATABASE` |
| `origin` | `DATABASE - protheus_logs` |
| `http_verb` | valor da coluna `http_verb` |
| `url` | valor da coluna `url` |
| `request_headers` | valor da coluna `request_headers` |
| `request_body` | valor da coluna `request_body` |
| `response_body` | valor da coluna `response_body` |
| `http_status_code` | valor da coluna `http_status_code` |

---

### 1.4 — Verificação final no banco

Após montar os logs, duas flags são derivadas da lista de evidências:

- **`db_valfor_ok`:** `True` se algum log tem `VALFOR` em `request_headers` e `<RETWS>false</RETWS>` em `response_body`
- **`db_atualizar_ok`:** `True` se algum log tem `ATUALIZAR` em `request_headers` e `<STATUS>true</STATUS>` em `response_body`

---

### 1.5 — Fallback: chamada à API SOAP externa (VALFOR)

**Acionado apenas se:** `db_valfor_ok == False` e o `cpf` do cliente estiver disponível.

**Endpoint:** `https://senffnet148708.protheus.cloudtotvs.com.br:1505/ws9901/SENFFFORNECEDORES.apw`

**Método:** `POST`

**Headers:**
```
Content-Type: text/xml; charset=utf-8
SOAPAction: https://senffnet148708.protheus.cloudtotvs.com.br:1505/VALFOR
Authorization: Basic <token>
```

**Payload:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ns:VALFOR xmlns:ns="https://senffnet148708.protheus.cloudtotvs.com.br:1505/">
      <ns:CPFCNPJ>{cpf}</ns:CPFCNPJ>
    </ns:VALFOR>
  </soap:Body>
</soap:Envelope>
```

**Retorno esperado de sucesso:**
```xml
<RETWS>false</RETWS>
```
> `false` indica que o CPF **não é** fornecedor novo — ou seja, já está cadastrado/validado no Protheus.

**Se bem-sucedido:** `api_valfor_ok = True`

**Logs gerados:**
- Log de evidência: `Fallback VALFOR externo` com a resposta completa da API
- Log de auditoria: `AUDITORIA - Fallback VALFOR` com resumo do status HTTP

---

### 1.6 — Resultado da Etapa 1

```
APROVADO se: (db_valfor_ok OU api_valfor_ok) E db_atualizar_ok
```

O `last_log_id` (ID do último log relevante) é retornado e armazenado para ser usado como ponto de partida na Etapa 2, evitando reprocessar logs já analisados.

---

## Etapa 2 — Emissão (`protheus-issuance`)

**Disparada quando:** a etapa `protheus-issuance` aparece no dashboard da proposta (após a formalização).

**Objetivo:** confirmar que o Protheus gerou o título financeiro (INCPAGARSE) da proposta e que ele foi devidamente registrado.

**Resultado esperado:** `db_success AND api_success AND table_success`

---

### 2.1 — Consulta em banco: leitura dos logs de emissão

**Tabela:** `protheus_logs`

```sql
SELECT id, http_verb, url, request_headers, request_body, response_body, http_status_code
FROM protheus_logs
WHERE correlation_id = :cid
ORDER BY id ASC
```

- **Parâmetro:** `cid` = `correlation_id` da proposta
- Retorna todos os logs; porém, apenas os com `id > last_protheus_id` (herdado da Etapa 1) são adicionados às evidências — os demais são ignorados mas ainda são varridos para análise

**O que é analisado:**
- Busca log onde `request_body` contém `INCPAGARSE` **e** `response_body` contém `<STATUS>true</STATUS>`
- **Flag:** `db_success = True`
- Se não encontrar → retorna `False` imediatamente (emissão ainda não foi processada; o orquestrador aguarda e retenta)

**Log de auditoria gerado:**
- Origem: `AUDITORIA - Leitura de logs Emissao`
- Registra a quantidade de linhas retornadas

---

### 2.2 — Prova de Realidade: chamada à API SOAP externa (INCPAGARSE)

**Acionado apenas se:** `db_success == True`

**Objetivo:** confirmar que o título foi criado no Protheus tentando criá-lo novamente. O Protheus deve **rejeitar** a tentativa com erro de duplicidade — essa rejeição é a prova de que o título original existe.

**Endpoint:** `https://senffnet148708.protheus.cloudtotvs.com.br:1505/ws9901/SENFFTITULOSSE.apw`

**Método:** `POST`

**Headers:**
```
Content-Type: text/xml; charset=utf-8
SOAPAction: https://senffnet148708.protheus.cloudtotvs.com.br:1505/INCPAGARSE
Authorization: Basic <token>
```

**Montagem do payload:**

| Campo XML | Valor | Origem |
|---|---|---|
| `CLIENTEFORNECEDOOR` | primeiros 6 dígitos do CPF | `cpf[:6]` (apenas dígitos) |
| `EMISSAO` | data atual | `datetime.now()` → `YYYY-MM-DD` |
| `FILIAL` | `030101` | fixo |
| `LOJA` | `0001` | fixo |
| `NATUREZ` | `2010396` | fixo |
| `NUM` | `SC` + `proposal_id` com zero-fill de 7 dígitos | ex.: `SC0000042` |
| `NUPORT` | _(vazio)_ | fixo |
| `ORIGEM` | código de criação da proposta | `codigo_criacao` |
| `PREFIXO` | `SQI` | fixo |
| `TIPO` | `OP` | fixo |
| `VALOR` | `50.00` | fixo (valor simbólico) |
| `VENCTO` | data atual | mesmo que `EMISSAO` |

**Payload completo:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <s0:INCPAGARSE xmlns="https://senffnet148708.protheus.cloudtotvs.com.br:1505/">
            <s0:TITULOSSE>
                <s0:CLIENTEFORNECEDOOR>{cpf[:6]}</s0:CLIENTEFORNECEDOOR>
                <s0:EMISSAO>{hoje}</s0:EMISSAO>
                <s0:FILIAL>030101</s0:FILIAL>
                <s0:LOJA>0001</s0:LOJA>
                <s0:NATUREZ>2010396</s0:NATUREZ>
                <s0:NUM>SC{proposal_id_zfill_7}</s0:NUM>
                <s0:NUPORT></s0:NUPORT>
                <s0:ORIGEM>{codigo_criacao}</s0:ORIGEM>
                <s0:PREFIXO>SQI</s0:PREFIXO>
                <s0:TIPO>OP</s0:TIPO>
                <s0:VALOR>50.00</s0:VALOR>
                <s0:VENCTO>{hoje}</s0:VENCTO>
            </s0:TITULOSSE>
        </s0:INCPAGARSE>
    </soap:Body>
</soap:Envelope>
```

**Retorno esperado de sucesso (conflito confirmado):**
```xml
<SOAP-ENV:Fault>Je existe titulo com esta...</SOAP-ENV:Fault>
```

**Se o erro de duplicidade estiver presente:** `api_success = True`

**Se a API não retornar o erro de duplicidade:** `api_success = False` — indica que o título pode não ter sido criado corretamente.

**Logs gerados:**
- Log de evidência: `Prova real de duplicidade` com a resposta completa da API
- Log de auditoria: `AUDITORIA - Prova de Conflito` com resumo do status HTTP

---

### 2.3 — Consulta em banco: confirmação na tabela `protheus_issuance`

**Acionado apenas se:** `api_success == True`

**Tabela:** `protheus_issuance`

```sql
SELECT id FROM protheus_issuance
WHERE proposal_id = :prop_id AND number = :num
```

- **Parâmetros:**
  - `prop_id` = ID interno da proposta
  - `num` = `'SC' + str(proposal_id).zfill(7)` (ex.: `SC0000042`)
- **Retorno esperado:** 1 registro encontrado
- **Flag:** `table_success = True` se registro existir

**Logs gerados:**
- Log de evidência: `Confirmacao em protheus_issuance`
  - `status_code: "200"` se encontrado, `"404"` se não encontrado
- Log de auditoria: `AUDITORIA - Confirmacao em protheus_issuance`

---

### 2.4 — Resultado da Etapa 2

```
APROVADO se: db_success E api_success E table_success
```

---

## Mecanismo de Retry e Bypass

### Retry (ambas as etapas)

O orquestrador (`main.py`) implementa até **6 tentativas** com intervalo de **5 segundos** entre cada uma. A cada tentativa:
1. Consulta o dashboard para verificar o status atual da etapa
2. Reexecuta a validação correspondente
3. Se a validação passar ou se atingir 6 tentativas, avança

### Bypass (somente `protheus-issuance`)

Se após 6 tentativas a emissão não for validada **mas o dashboard já marcou a etapa como `APPROVED`**, o orquestrador assume que a proposta é do tipo **"Sem Saque"** (não gera título) e injeta um log sintético de bypass:

```json
{
  "origin": "SYSTEM",
  "http_verb": "INFO",
  "url": "Bypass",
  "request_body": "Bypass aplicado.",
  "response_body": "Proposta Sem Saque.",
  "http_status_code": "200",
  "kind": "evidence",
  "source_type": "SYSTEM"
}
```

A validação é marcada como `valid: true` e o fluxo prossegue normalmente.

---

## Fluxo Completo de Execução

```
[main.py] Captura correlation_id
    └── SELECT correlation_id FROM proposals WHERE code = :code

[Etapa: protheus]
    └── validate_protheus_logs(correlation_id, cpf)
        │
        ├── 1. SELECT protheus_logs WHERE correlation_id ORDER BY id ASC
        │       └── Varre logs para definir cutoff_id
        │           ├── Achou ATUALIZAR + <STATUS>true>  → db_atualizar_ok ✓, cutoff_id definido
        │           └── Achou VALFOR + <RETWS>false>     → db_valfor_ok ✓ (cutoff alternativo)
        │
        ├── 2. Monta evidências (logs até cutoff_id)
        │
        ├── 3. db_valfor_ok == False?
        │       └── POST SOAP SENFFFORNECEDORES (VALFOR com CPF)
        │               └── <RETWS>false> na resposta → api_valfor_ok ✓
        │
        └── Retorna: (db_valfor_ok OU api_valfor_ok) E db_atualizar_ok
                     + logs de evidência
                     + logs de auditoria
                     + last_log_id

[Etapa: protheus-issuance]
    └── validate_protheus_issuance_logs(correlation_id, proposal_id, codigo_criacao, cpf, last_protheus_id)
        │
        ├── 1. SELECT protheus_logs WHERE correlation_id ORDER BY id ASC
        │       └── Filtra logs com id > last_protheus_id para evidências
        │       └── Varre todos para achar INCPAGARSE + <STATUS>true>
        │               └── Encontrado → db_success ✓
        │               └── Não encontrado → retorna False (retry)
        │
        ├── 2. db_success == True?
        │       └── POST SOAP SENFFTITULOSSE (INCPAGARSE com título duplicado)
        │               ├── CLIENTEFORNECEDOOR = primeiros 6 dígitos do CPF
        │               ├── NUM = SC + proposal_id (zfill 7)
        │               └── Resposta com Fault "Je existe titulo" → api_success ✓
        │
        ├── 3. api_success == True?
        │       └── SELECT protheus_issuance WHERE proposal_id AND number
        │               └── Registro encontrado → table_success ✓
        │
        └── Retorna: db_success E api_success E table_success
                     + logs de evidência
                     + logs de auditoria
```

---

## Tabelas Consultadas

| Tabela | Etapa | Operação | Filtro |
|---|---|---|---|
| `proposals` | pré-validação | `SELECT correlation_id` | `code = :code` |
| `protheus_logs` | Formalização | `SELECT *` | `correlation_id = :cid` |
| `protheus_logs` | Emissão | `SELECT *` | `correlation_id = :cid` |
| `protheus_issuance` | Emissão | `SELECT id` | `proposal_id = :prop_id AND number = :num` |

---

## APIs Externas Consultadas

| Etapa | Serviço | Endpoint | Condição de Disparo |
|---|---|---|---|
| Formalização (fallback) | `SENFFFORNECEDORES` (VALFOR) | `.../ws9901/SENFFFORNECEDORES.apw` | `db_valfor_ok == False` |
| Emissão (prova real) | `SENFFTITULOSSE` (INCPAGARSE) | `.../ws9901/SENFFTITULOSSE.apw` | `db_success == True` |

---

## Estrutura dos Logs Gerados

Cada operação gera dois tipos de log:

| Tipo | `kind` | Conteúdo |
|---|---|---|
| Evidência | `evidence` | Dados completos da operação (request + response completos) — usado no relatório HTML |
| Auditoria | `audit` | Resumo da operação (status, contagem de registros) — trilha de auditoria |

**Campos presentes em todos os logs:**

```json
{
  "origin": "identificador da origem",
  "http_verb": "SELECT | POST",
  "url": "tabela ou endpoint",
  "request_headers": "...",
  "request_body": "...",
  "response_body": "...",
  "http_status_code": "200 | 404 | ERROR",
  "source_type": "DATABASE | API | SYSTEM",
  "duration_ms": 42.5,
  "kind": "evidence | audit",
  "label": "rótulo legível"
}
```
