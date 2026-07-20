import asyncio

import httpx
import pytest
from httpx import ASGITransport
from mongomock_motor import AsyncMongoMockClient

from app.api.messages import get_message_history
from app.db import ensure_indexes
from app.errors import DatastoreUnavailableError
from app.main import app
from app.repositories.message_history import MessageHistoryRepository
from tests.conftest import TENANT_ID


@pytest.fixture
async def message_history() -> MessageHistoryRepository:
    client = AsyncMongoMockClient()
    database = client["conversational_ai"]
    await ensure_indexes(database)
    return MessageHistoryRepository(database.conversation_messages)


@pytest.fixture
async def client(message_history: MessageHistoryRepository):
    app.dependency_overrides[get_message_history] = lambda: message_history
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Tenant-Id": TENANT_ID}
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


class BrokenMessageHistory:
    async def append(self, conversation_id: str, message: dict):
        raise DatastoreUnavailableError("MongoDB unavailable")

    async def list_by_conversation(self, conversation_id: str, tenant_id: str, limit=None):
        raise DatastoreUnavailableError("MongoDB unavailable")


async def test_append_creates_message_with_server_timestamp(client: httpx.AsyncClient):
    response = await client.post(
        "/conversations/conv-1/messages",
        json={"tenantId": TENANT_ID, "userId": "u1", "role": "user", "content": {"text": "oi"}},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["tenantId"] == TENANT_ID
    assert body["conversationId"] == "conv-1"
    assert body["role"] == "user"
    assert "createdAt" in body


async def test_append_missing_required_field_rejected(client: httpx.AsyncClient):
    response = await client.post(
        "/conversations/conv-1/messages",
        json={"role": "user", "content": {"text": "oi"}},
    )

    assert response.status_code == 422


async def test_append_with_new_external_message_id_creates(client: httpx.AsyncClient):
    response = await client.post(
        "/conversations/conv-1/messages",
        json={
            "tenantId": TENANT_ID,
            "role": "user",
            "content": {"text": "oi"},
            "externalMessageId": "wamid.001",
        },
    )

    assert response.status_code == 201


async def test_repeated_append_with_same_external_message_id_is_idempotent(client: httpx.AsyncClient):
    payload = {
        "tenantId": TENANT_ID,
        "role": "user",
        "content": {"text": "oi"},
        "externalMessageId": "wamid.001",
    }

    first = await client.post("/conversations/conv-1/messages", json=payload)
    second = await client.post("/conversations/conv-1/messages", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["_id"] == second.json()["_id"]


async def test_list_returns_chronological_order(client: httpx.AsyncClient):
    await client.post(
        "/conversations/conv-1/messages",
        json={"tenantId": TENANT_ID, "role": "user", "content": {"text": "first"}},
    )
    await asyncio.sleep(0.01)
    await client.post(
        "/conversations/conv-1/messages",
        json={"tenantId": TENANT_ID, "role": "assistant", "content": {"text": "second"}},
    )

    response = await client.get("/conversations/conv-1/messages", params={"tenant_id": TENANT_ID})

    assert response.status_code == 200
    texts = [message["content"]["text"] for message in response.json()]
    assert texts == ["first", "second"]


async def test_list_limit_bounds_result_set(client: httpx.AsyncClient):
    for text in ["first", "second", "third"]:
        await client.post(
            "/conversations/conv-1/messages",
            json={"tenantId": TENANT_ID, "role": "user", "content": {"text": text}},
        )
        await asyncio.sleep(0.01)

    response = await client.get(
        "/conversations/conv-1/messages", params={"tenant_id": TENANT_ID, "limit": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["content"]["text"] == "third"


async def test_list_no_messages_returns_empty_list(client: httpx.AsyncClient):
    response = await client.get("/conversations/conv-empty/messages", params={"tenant_id": TENANT_ID})

    assert response.status_code == 200
    assert response.json() == []


async def test_mongodb_unavailable_returns_503():
    app.dependency_overrides[get_message_history] = lambda: BrokenMessageHistory()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"X-Tenant-Id": TENANT_ID}
        ) as ac:
            response = await ac.post(
                "/conversations/conv-1/messages",
                json={"tenantId": TENANT_ID, "role": "user", "content": {"text": "oi"}},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
