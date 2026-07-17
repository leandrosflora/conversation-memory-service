from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.errors import DatastoreUnavailableError


class SessionStore:
    def __init__(self, client: redis.Redis, default_ttl_seconds: int) -> None:
        self._client = client
        self._default_ttl_seconds = default_ttl_seconds

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"session:{conversation_id}"

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            raw = await self._client.get(self._key(conversation_id))
        except RedisError as exc:
            raise DatastoreUnavailableError("Redis unavailable") from exc

        if raw is None:
            return None
        return json.loads(raw)

    async def put(
        self, conversation_id: str, data: dict[str, Any], ttl_seconds: int | None = None
    ) -> dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        try:
            await self._client.set(self._key(conversation_id), json.dumps(payload), ex=ttl)
        except RedisError as exc:
            raise DatastoreUnavailableError("Redis unavailable") from exc

        return payload

    async def delete(self, conversation_id: str) -> None:
        try:
            await self._client.delete(self._key(conversation_id))
        except RedisError as exc:
            raise DatastoreUnavailableError("Redis unavailable") from exc
