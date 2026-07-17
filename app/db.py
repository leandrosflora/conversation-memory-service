from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import Settings


def build_mongo_client(settings: Settings) -> AsyncIOMotorClient:
    # tz_aware=True keeps every datetime this service reads back from Mongo timezone-aware
    # (UTC), so it can be compared directly against datetime.now(timezone.utc) without a
    # separate naive/aware normalization step (see repositories/memory_facts.py).
    #
    # PyMongo's serverSelectionTimeoutMS defaults to 30s - far past what a caller waiting
    # on a 503 should ever block for. Bounding it here is what makes the "503, not a hang"
    # behavior (see app/errors.py) actually true rather than just documented.
    return AsyncIOMotorClient(
        settings.mongodb_uri,
        tz_aware=True,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
    )


async def ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    """Idempotently (re)creates the indexes `database/conversational-ai-mongodb-init.js`
    already defines for the collections this service uses.

    docs/runbook.md notes that the Postgres/Mongo init scripts only run against an empty
    volume - a Mongo volume created before this service existed would otherwise never get
    these indexes. create_index is a no-op when an identical index already exists, so this
    is safe to run on every startup.
    """
    messages = database.conversation_messages
    await messages.create_index([("tenantId", 1), ("conversationId", 1), ("createdAt", 1)])
    await messages.create_index([("tenantId", 1), ("userId", 1), ("createdAt", -1)])
    await messages.create_index("externalMessageId", unique=True, sparse=True)
    await messages.create_index("correlationId", sparse=True)
    await messages.create_index("traceId", sparse=True)

    memory = database.agent_memory
    await memory.create_index([("tenantId", 1), ("userId", 1), ("memoryType", 1)])
    await memory.create_index("expiresAt", expireAfterSeconds=0, sparse=True)
