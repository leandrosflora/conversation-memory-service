from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError, PyMongoError

from app.errors import DatastoreUnavailableError


class MessageHistoryRepository:
    def __init__(self, collection) -> None:
        self._collection = collection

    async def append(self, conversation_id: str, message: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Inserts a message, returning (document, created).

        `created` is False when a document with the same (tenantId, externalMessageId)
        already existed - the append is treated as a no-op retry rather than an error,
        since `externalMessageId` is a unique-sparse index on the collection.
        """
        tenant_id = message["tenantId"]
        external_message_id = message.get("externalMessageId")

        if external_message_id:
            existing = await self._find_by_external_id(tenant_id, external_message_id)
            if existing is not None:
                return existing, False

        document = {
            **message,
            "conversationId": conversation_id,
            "createdAt": datetime.now(timezone.utc),
        }
        try:
            result = await self._collection.insert_one(document)
        except DuplicateKeyError:
            # Lost a race against a concurrent append with the same externalMessageId.
            existing = await self._find_by_external_id(tenant_id, external_message_id)
            if existing is not None:
                return existing, False
            raise
        except PyMongoError as exc:
            raise DatastoreUnavailableError("MongoDB unavailable") from exc

        document["_id"] = result.inserted_id
        return document, True

    async def _find_by_external_id(self, tenant_id: str, external_message_id: str) -> dict[str, Any] | None:
        try:
            return await self._collection.find_one(
                {"tenantId": tenant_id, "externalMessageId": external_message_id}
            )
        except PyMongoError as exc:
            raise DatastoreUnavailableError("MongoDB unavailable") from exc

    async def list_by_conversation(
        self, conversation_id: str, tenant_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        query = {"tenantId": tenant_id, "conversationId": conversation_id}
        try:
            if limit is not None:
                # Take the most recent `limit` messages, then restore chronological order.
                cursor = self._collection.find(query).sort("createdAt", -1).limit(limit)
                documents = await cursor.to_list(length=limit)
                documents.reverse()
                return documents

            cursor = self._collection.find(query).sort("createdAt", 1)
            return await cursor.to_list(length=None)
        except PyMongoError as exc:
            raise DatastoreUnavailableError("MongoDB unavailable") from exc
