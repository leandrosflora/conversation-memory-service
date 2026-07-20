# Conversation Memory Service

Serviço de memória conversacional da plataforma de IA conversacional: sessão ativa de conversa e histórico de mensagens, persistidos e integrados pelo `conversation-orchestrator` e pelo `agent-runtime-renegotiation`. Memória de longo prazo por usuário (`/users/{id}/memory`) está implementada mas ainda sem chamador real — ver "Integrações".

Este serviço expõe uma API HTTP/JSON autenticada com JWT interno. Persiste sessão ativa no Redis com TTL (chave escopada por tenant) e histórico de mensagens / fatos de memória no MongoDB, nas coleções já provisionadas em `database/conversational-ai-mongodb-init.js`.

## Visão geral

```mermaid
flowchart LR
    Orchestrator[Conversation Orchestrator] -->|GET/PUT /sessions\nvia outbox assíncrono| Memory[Conversation Memory Service]
    Orchestrator -->|POST /conversations/id/messages\nvia outbox assíncrono| Memory
    AgentRuntime[Agent Runtime Renegotiation] -->|GET /conversations/id/messages| Memory
    Memory -->|sessão ativa, TTL, chave por tenant| Redis[(Redis)]
    Memory -->|conversation_messages, agent_memory| Mongo[(MongoDB)]
```

## Stack

- Python 3.12
- FastAPI
- Uvicorn
- Motor (MongoDB async)
- redis-py (`redis.asyncio`)
- Pydantic Settings
- OpenTelemetry
- Pytest

## Responsabilidades

- Guardar e devolver o estado ativo de uma conversa (`data` livre) no Redis, com TTL configurável.
- Persistir mensagens de uma conversa no MongoDB (`conversation_messages`), de forma idempotente por `externalMessageId`.
- Listar o histórico de uma conversa em ordem cronológica, com limite opcional.
- Persistir e devolver fatos de memória de longo prazo por usuário no MongoDB (`agent_memory`), com TTL opcional.
- Responder `503` (não travar) quando Redis ou MongoDB estiverem inacessíveis.

## Endpoints

Todos exigem `Authorization: Bearer <jwt-interno>` e `X-Tenant-Id: <tenant>` (validado contra a claim assinada). Nos endpoints de `POST`/`PUT` que recebem `tenantId` no corpo, esse valor precisa bater com o `X-Tenant-Id` (`400` se não bater).

### Sessão (Redis)

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/sessions/{conversation_id}` | Retorna `data`/`updated_at` da sessão ativa, ou `404` se não existir/expirou. |
| `PUT` | `/sessions/{conversation_id}` | Cria/atualiza a sessão (`{"data": {...}, "ttl_seconds": opcional}`), reiniciando o TTL. |
| `DELETE` | `/sessions/{conversation_id}` | Remove a sessão (idempotente — `204` mesmo se já não existir). |

A chave no Redis é `tenant:{tenant_id}:session:{conversation_id}` — escopada por tenant, não só por conversa.

### Histórico de mensagens (MongoDB)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/conversations/{conversation_id}/messages` | Anexa uma mensagem (`tenantId`, `role`, `content`, ... — mesmos campos de `conversation_messages`). Retorna `201` (nova) ou `200` (retry idempotente pelo mesmo `externalMessageId`). |
| `GET` | `/conversations/{conversation_id}/messages?tenant_id=...&limit=...` | Lista o histórico em ordem cronológica, com `limit` opcional. |

### Memória de longo prazo (MongoDB)

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/users/{user_id}/memory?tenant_id=...&memory_type=...` | Retorna os `facts` armazenados (lista vazia se não houver, inclusive se expirados). |
| `PUT` | `/users/{user_id}/memory` | Substitui os `facts` do par `(tenantId, userId, memoryType)`; `ttl_seconds` opcional define `expiresAt`. |

### `GET /health/live`, `GET /health/ready`

Endpoints públicos (não exigem JWT). `/health/ready` verifica a chave de assinatura JWT interna, o Redis e o MongoDB.

## Configuração

O serviço usa `pydantic-settings`, com suporte a variáveis de ambiente.

| Variável | Default | Descrição |
|---|---:|---|
| `REDIS_URL` | `redis://localhost:6379/0` | String de conexão do Redis. |
| `SESSION_TTL_SECONDS` | `1800` | TTL padrão da sessão ativa (mesmo valor do `Session:TtlMinutes=30` do Orchestrator). |
| `MONGODB_URI` | `mongodb://conversational_ai_app:conversational_ai_app@localhost:27018/conversational_ai` | String de conexão do MongoDB (usuário de app com `readWrite`, não root). Porta `27018`, não a `27017` padrão — ver nota no `docker-compose.yml`/runbook sobre conflito com um `mongod.exe` nativo do Windows nesta máquina. |
| `MONGODB_DATABASE` | `conversational_ai` | Nome do banco. |
| `OTEL_OTLP_ENDPOINT` | `http://localhost:4317` | Endpoint OTLP para tracing (Jaeger). |
| `INTERNAL_AUTH_ENABLED` | `true` | Se `false`, os endpoints não exigem JWT (uso local/teste); `X-Tenant-Id` continua obrigatório. |
| `INTERNAL_AUTH_SIGNING_KEY` | (vazio) | Chave HS256 usada para validar o JWT recebido. Obrigatória com auth habilitada. |

## Como executar localmente

### Pré-requisitos

- Python 3.12
- Redis e MongoDB acessíveis (localmente ou via `docker compose up redis mongodb` no `conversational-ai-demo-arch`)
- `INTERNAL_AUTH_SIGNING_KEY` com pelo menos 32 bytes, igual ao configurado no `conversation-orchestrator` e no `agent-runtime-renegotiation`

### Criar ambiente virtual

```bash
python -m venv .venv
```

Ativar no Windows: `.venv\Scripts\activate` — Linux/macOS: `source .venv/bin/activate`.

### Instalar dependências

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # para desenvolvimento e testes
```

### Subir a API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8600 --reload
```

Swagger: `http://localhost:8600/docs`

## Testes

```bash
python -m pytest
```

> Use `python -m pytest`, não o script `pytest` isolado — sem o `python -m`, o diretório do projeto não entra no `sys.path` e a suíte inteira falha com `ModuleNotFoundError: No module named 'app'` (é exatamente por isso que o workflow de CI usa `python -m pytest`).

Os testes usam `fakeredis` e `mongomock-motor`, então rodam sem depender de Redis/MongoDB reais. `PlatformMiddleware` é contornado com um fixture `autouse` em `tests/conftest.py` que muta o singleton `app.main.settings` (`internal_auth_enabled=False`) em vez de assinar um JWT de verdade, já que a instância é fixada na app na inicialização e não é resolvida via `Depends` a cada request; cada request de teste ainda passa um `X-Tenant-Id` válido.

## CI

`.github/workflows/ci.yml` roda `pip install`/`python -m pytest` a cada push/PR para `master`.

## Estrutura

```text
.
├── app
│   ├── api
│   │   ├── sessions.py
│   │   ├── messages.py
│   │   └── memory.py
│   ├── repositories
│   │   ├── session_store.py
│   │   ├── message_history.py
│   │   └── memory_facts.py
│   ├── config.py
│   ├── db.py
│   ├── errors.py
│   ├── logging_setup.py
│   ├── main.py
│   ├── models.py
│   └── platform.py
├── tests
│   └── conftest.py
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── Dockerfile
├── .github/workflows/ci.yml
└── conversation-memory-service.pyproj
```

## Integrações

### Conversation Orchestrator

Integrado de fato: `ConversationMemoryClient.cs` chama `GET`/`PUT /sessions/{conversationId}` e `POST /conversations/{conversationId}/messages` — mas não de forma síncrona durante o request, e sim como efeitos do outbox transacional (`MemorySaveSession`/`MemoryAppendMessage`), despachados de forma assíncrona pelo `OutboxDispatcherService` depois que `POST /messages` já retornou `202`.

### Agent Runtime Renegotiation

Integrado de fato: `app/context/history.py` chama `GET /conversations/{conversationId}/messages` de forma síncrona antes de montar o prompt do agente, para dar contexto de histórico recente. Indisponibilidade degrada para histórico vazio (não derruba a requisição).

### O que ainda não está integrado

`GET`/`PUT /users/{user_id}/memory` (memória de longo prazo por usuário) está implementado e testado, mas nenhum chamador real o invoca ainda — nem o Orchestrator nem o Agent Runtime persistem fatos de longo prazo hoje. Wireá-lo é um change futuro.

### Redis / MongoDB

Único consumidor de MongoDB do workspace; `whatsapp-bff` também usa Redis (para idempotência de envio outbound), com chaves em um namespace diferente do usado aqui.

## Observações técnicas

- Campos persistidos no MongoDB usam os mesmos nomes em camelCase do schema já provisionado (`tenantId`, `conversationId`, ...), não snake_case — é esse schema, não um contrato de chamador, que é a fonte de verdade aqui.
- Indisponibilidade de Redis/MongoDB responde `503` de forma limitada no tempo (timeouts de conexão de 3s configurados em `app/db.py`/`app/main.py`), nunca trava a requisição.
- Índices de `conversation_messages`/`agent_memory` são recriados de forma idempotente no startup (`app/db.py`), cobrindo o caso de um volume Mongo anterior a este serviço que nunca rodou o script de init.

## Próximos passos sugeridos

- Integrar `conversation-orchestrator` ou `agent-runtime-renegotiation` com `/users/{id}/memory` (memória de longo prazo), hoje implementado mas sem chamador.
- Resumo/compactação de histórico ("histórico resumido", per o C4) — hoje o histórico é devolvido bruto.
- Endpoint de merge/patch de fatos de memória por chave, em vez de substituição total do array.
