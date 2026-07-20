import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.api.memory import router as memory_router
from app.api.messages import router as messages_router
from app.api.sessions import router as sessions_router
from app.config import get_settings
from app.db import build_mongo_client, ensure_indexes
from app.errors import DatastoreUnavailableError
from app.logging_setup import CorrelationIdMiddleware, configure_logging
from app.platform import PlatformMiddleware, metrics_response
from app.repositories.memory_facts import MemoryFactsRepository
from app.repositories.message_history import MessageHistoryRepository
from app.repositories.session_store import SessionStore

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

_tracer_provider = TracerProvider(
    resource=Resource.create({"service.name": settings.internal_auth_service_name})
)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_otlp_endpoint))
)
trace.set_tracer_provider(_tracer_provider)
PymongoInstrumentor().instrument()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    app.state.mongo_client = build_mongo_client(settings)
    database = app.state.mongo_client[settings.mongodb_database]
    await ensure_indexes(database)

    app.state.session_store = SessionStore(
        app.state.redis_client,
        settings.session_ttl_seconds,
    )
    app.state.message_history = MessageHistoryRepository(database.conversation_messages)
    app.state.memory_facts = MemoryFactsRepository(database.agent_memory)

    yield
    await app.state.redis_client.aclose()
    app.state.mongo_client.close()


app = FastAPI(title="conversation-memory-service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    PlatformMiddleware,
    settings=settings,
    public_paths=("/health/live", "/health/ready", "/metrics", "/docs", "/openapi.json", "/redoc"),
    tenant_required_paths=("/sessions", "/conversations", "/users"),
)
FastAPIInstrumentor.instrument_app(app)


@app.exception_handler(RequestValidationError)
async def log_validation_errors(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Rejected %s: errors=%s", request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(DatastoreUnavailableError)
async def handle_datastore_unavailable(request: Request, exc: DatastoreUnavailableError) -> JSONResponse:
    logger.error("Datastore unavailable while handling %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health/live", include_in_schema=False)
async def health_live() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready", include_in_schema=False)
async def health_ready(request: Request) -> JSONResponse:
    failures: list[str] = []
    if settings.internal_auth_enabled:
        for caller in ("conversation-orchestrator", "agent-runtime-renegotiation"):
            secret = settings.internal_auth_inbound_secrets.get(caller)
            if not secret or len(secret.encode("utf-8")) < 32:
                failures.append(f"internal_auth_inbound_secret_missing:{caller}")
    try:
        await request.app.state.redis_client.ping()
    except Exception:
        failures.append("redis_unavailable")
    try:
        await request.app.state.mongo_client.admin.command("ping")
    except Exception:
        failures.append("mongodb_unavailable")

    return JSONResponse(
        {"status": "not_ready" if failures else "ready", "failures": failures},
        status_code=503 if failures else 200,
    )


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_response()


app.include_router(sessions_router)
app.include_router(messages_router)
app.include_router(memory_router)
