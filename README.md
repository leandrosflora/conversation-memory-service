# Conversation Memory Service

Serviço de memória conversacional da plataforma de IA conversacional: sessão ativa de conversa e histórico/memória de longo prazo, hoje ainda não persistidos por nenhum outro serviço (que mantêm estado apenas em memória de processo).

Este serviço expõe uma API HTTP/JSON usada (no papel, per o diagrama C4 — ver "Integrações") pelo `conversation-orchestrator` (sessão) e pelo `agent-runtime-renegotiation` (memória de longo prazo). Persiste sessão ativa no Redis com TTL e histórico de mensagens / fatos de memória no MongoDB, nas coleções já provisionadas em `database/conversational-ai-mongodb-init.js`.

## Visão geral

```mermaid
flowchart LR
    Orchestrator[Conversation Orchestrator] -.->|GET/PUT/DELETE /sessions| Memory[Conversation Memory Service]
    AgentRuntime[Agent Runtime Renegotiation] -.->|GET/PUT /users/id/memory| Memory
    Memory -->|sessão ativa, TTL| Redis[(Redis)]
    Memory -->|conversation_messages, agent_memory| Mongo[(MongoDB)]
```

> As setas tracejadas (Orchestrator/Agent Runtime → Memory Service) representam o contrato desenhado a partir do C4, não uma integração já implementada — ver "Integrações" abaixo.

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

### Sessão (Redis)

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/sessions/{conversation_id}` | Retorna `data`/`updated_at` da sessão ativa, ou `404` se não existir/expirou. |
| `PUT` | `/sessions/{conversation_id}` | Cria/atualiza a sessão (`{"data": {...}, "ttl_seconds": opcional}`), reiniciando o TTL. |
| `DELETE` | `/sessions/{conversation_id}` | Remove a sessão (idempotente — `204` mesmo se já não existir). |

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

## Configuração

O serviço usa `pydantic-settings`, com suporte a variáveis de ambiente.

| Variável | Default | Descrição |
|---|---:|---|
| `REDIS_URL` | `redis://localhost:6379/0` | String de conexão do Redis. |
| `SESSION_TTL_SECONDS` | `1800` | TTL padrão da sessão ativa (mesmo valor do `Session:TtlMinutes=30` do Orchestrator). |
| `MONGODB_URI` | `mongodb://conversational_ai_app:conversational_ai_app@localhost:27018/conversational_ai` | String de conexão do MongoDB (usuário de app com `readWrite`, não root). Porta `27018`, não a `27017` padrão — ver nota no `docker-compose.yml`/runbook sobre conflito com um `mongod.exe` nativo do Windows nesta máquina. |
| `MONGODB_DATABASE` | `conversational_ai` | Nome do banco. |
| `OTEL_OTLP_ENDPOINT` | `http://localhost:4317` | Endpoint OTLP para tracing (Jaeger). |

## Como executar localmente

### Pré-requisitos

- Python 3.12
- Redis e MongoDB acessíveis (localmente ou via `docker compose up redis mongodb` no `conversational-ai-demo-arch`)

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
pytest
```

Os testes usam `fakeredis` e `mongomock-motor`, então rodam sem depender de Redis/MongoDB reais.

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
│   └── models.py
├── tests
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── conversation-memory-service.pyproj
```

## Integrações

### Conversation Orchestrator / Agent Runtime Renegotiation

Nenhum dos dois chama este serviço ainda — ambos continuam com sessão/memória em processo (`ConcurrentDictionary`/`IMemoryCache`), perdida a cada restart. O contrato HTTP acima foi definido a partir do C4 (`docs/architecture/C4/c4-container.puml`), não de um client já existente; wireá-los para consumir este serviço é um change futuro.

### Redis / MongoDB

Primeiro serviço deste workspace a se conectar de fato a eles — ambos já estavam provisionados em `docker-compose.yml` (com schema Mongo pronto em `database/conversational-ai-mongodb-init.js`), mas sem nenhum consumidor até este serviço existir.

## Observações técnicas

- Campos persistidos no MongoDB usam os mesmos nomes em camelCase do schema já provisionado (`tenantId`, `conversationId`, ...), não snake_case — é esse schema, não um contrato de chamador, que é a fonte de verdade aqui.
- Indisponibilidade de Redis/MongoDB responde `503` de forma limitada no tempo (timeouts de conexão de 3s configurados em `app/db.py`/`app/main.py`), nunca trava a requisição.
- Índices de `conversation_messages`/`agent_memory` são recriados de forma idempotente no startup (`app/db.py`), cobrindo o caso de um volume Mongo anterior a este serviço que nunca rodou o script de init.

## Próximos passos sugeridos

- Integrar `conversation-orchestrator` e `agent-runtime-renegotiation` para de fato chamar este serviço.
- Resumo/compactação de histórico ("histórico resumido", per o C4) — hoje o histórico é devolvido bruto.
- Endpoint de merge/patch de fatos de memória por chave, em vez de substituição total do array.
