from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import Settings


def build_mongo_client(settings: Settings) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.mongodb_uri,
        tz_aware=True,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
    )


async def ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    messages = database.conversation_messages
    await messages.create_index([("tenantId", 1), ("conversationId", 1), ("createdAt", 1)])
    await messages.create_index([("tenantId", 1), ("userId", 1), ("createdAt", -1)])

    index_information = await messages.index_information()
    legacy_index = index_information.get("externalMessageId_1")
    if legacy_index and legacy_index.get("key") == [("externalMessageId", 1)]:
        await messages.drop_index("externalMessageId_1")
    await messages.create_index(
        [("tenantId", 1), ("externalMessageId", 1)],
        name="ux_conversation_messages_tenant_external_message",
        unique=True,
        partialFilterExpression={"externalMessageId": {"$type": "string"}},
    )

    await messages.create_index("correlationId", sparse=True)
    await messages.create_index("traceId", sparse=True)

    memory = database.agent_memory
    await memory.create_index([("tenantId", 1), ("userId", 1), ("memoryType", 1)])
    await memory.create_index("expiresAt", expireAfterSeconds=0, sparse=True)
