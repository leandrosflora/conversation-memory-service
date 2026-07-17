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
from app.repositories.memory_facts import MemoryFactsRepository
from app.repositories.message_history import MessageHistoryRepository
from app.repositories.session_store import SessionStore

configure_logging()
logger = logging.getLogger(__name__)

_tracer_provider = TracerProvider(
    resource=Resource.create({"service.name": "conversation-memory-service"})
)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=get_settings().otel_otlp_endpoint))
)
trace.set_tracer_provider(_tracer_provider)
PymongoInstrumentor().instrument()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    # Bounded timeouts so a stalled/unreachable Redis surfaces as a prompt 503 (see
    # app/errors.py) instead of blocking the caller for redis-py's longer default.
    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    mongo_client = build_mongo_client(settings)
    database = mongo_client[settings.mongodb_database]
    await ensure_indexes(database)

    app.state.session_store = SessionStore(redis_client, settings.session_ttl_seconds)
    app.state.message_history = MessageHistoryRepository(database.conversation_messages)
    app.state.memory_facts = MemoryFactsRepository(database.agent_memory)

    yield

    await redis_client.aclose()
    mongo_client.close()


app = FastAPI(title="conversation-memory-service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
FastAPIInstrumentor.instrument_app(app)


@app.exception_handler(RequestValidationError)
async def log_validation_errors(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Rejected %s: errors=%s", request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(DatastoreUnavailableError)
async def handle_datastore_unavailable(request: Request, exc: DatastoreUnavailableError) -> JSONResponse:
    logger.error("Datastore unavailable while handling %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(sessions_router)
app.include_router(messages_router)
app.include_router(memory_router)
