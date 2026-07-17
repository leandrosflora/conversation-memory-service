from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.errors import PyMongoError

from app.errors import DatastoreUnavailableError


class MemoryFactsRepository:
    def __init__(self, collection) -> None:
        self._collection = collection

    async def get(self, tenant_id: str, user_id: str, memory_type: str) -> dict[str, Any] | None:
        query = {"tenantId": tenant_id, "userId": user_id, "memoryType": memory_type}
        try:
            document = await self._collection.find_one(query)
        except PyMongoError as exc:
            raise DatastoreUnavailableError("MongoDB unavailable") from exc

        if document is None:
            return None

        expires_at = document.get("expiresAt")
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            # Mongo's TTL index only sweeps expired documents periodically (not
            # instantaneously), so a document can be logically expired before it's
            # physically deleted - treat it as absent either way.
            return None

        return document

    async def upsert(
        self,
        tenant_id: str,
        user_id: str,
        memory_type: str,
        facts: list[dict[str, Any]],
        source_conversation_id: str | None,
        ttl_seconds: int | None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {
            "$set": {
                "facts": facts,
                "sourceConversationId": source_conversation_id,
                "updatedAt": now,
            },
            "$setOnInsert": {
                "tenantId": tenant_id,
                "userId": user_id,
                "memoryType": memory_type,
                "createdAt": now,
            },
        }
        if ttl_seconds is not None:
            update["$set"]["expiresAt"] = now + timedelta(seconds=ttl_seconds)
        else:
            update["$unset"] = {"expiresAt": ""}

        query = {"tenantId": tenant_id, "userId": user_id, "memoryType": memory_type}
        try:
            await self._collection.update_one(query, update, upsert=True)
            document = await self._collection.find_one(query)
        except PyMongoError as exc:
            raise DatastoreUnavailableError("MongoDB unavailable") from exc

        return document
