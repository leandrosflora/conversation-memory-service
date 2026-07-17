import asyncio

import httpx
import pytest
from httpx import ASGITransport
from mongomock_motor import AsyncMongoMockClient

from app.api.memory import get_memory_facts
from app.db import ensure_indexes
from app.errors import DatastoreUnavailableError
from app.main import app
from app.repositories.memory_facts import MemoryFactsRepository


@pytest.fixture
async def memory_facts() -> MemoryFactsRepository:
    client = AsyncMongoMockClient()
    database = client["conversational_ai"]
    await ensure_indexes(database)
    return MemoryFactsRepository(database.agent_memory)


@pytest.fixture
async def client(memory_facts: MemoryFactsRepository):
    app.dependency_overrides[get_memory_facts] = lambda: memory_facts
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class BrokenMemoryFacts:
    async def get(self, tenant_id: str, user_id: str, memory_type: str):
        raise DatastoreUnavailableError("MongoDB unavailable")

    async def upsert(self, **kwargs):
        raise DatastoreUnavailableError("MongoDB unavailable")


async def test_get_with_no_matching_document_returns_empty_facts(client: httpx.AsyncClient):
    response = await client.get(
        "/users/u1/memory", params={"tenant_id": "t1", "memory_type": "session"}
    )

    assert response.status_code == 200
    assert response.json()["facts"] == []


async def test_put_creates_new_memory_document(client: httpx.AsyncClient):
    response = await client.put(
        "/users/u1/memory",
        json={
            "tenantId": "t1",
            "memoryType": "session",
            "facts": [{"key": "preferred_language", "value": "pt-BR", "confidence": 1.0}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["facts"] == [{"key": "preferred_language", "value": "pt-BR", "confidence": 1.0}]
    assert body["expiresAt"] is None


async def test_get_returns_existing_facts(client: httpx.AsyncClient):
    await client.put(
        "/users/u1/memory",
        json={
            "tenantId": "t1",
            "memoryType": "session",
            "facts": [{"key": "preferred_channel", "value": "whatsapp"}],
        },
    )

    response = await client.get(
        "/users/u1/memory", params={"tenant_id": "t1", "memory_type": "session"}
    )

    assert response.status_code == 200
    assert response.json()["facts"][0]["key"] == "preferred_channel"


async def test_put_replaces_existing_facts(client: httpx.AsyncClient):
    await client.put(
        "/users/u1/memory",
        json={"tenantId": "t1", "memoryType": "session", "facts": [{"key": "a", "value": 1}]},
    )
    response = await client.put(
        "/users/u1/memory",
        json={"tenantId": "t1", "memoryType": "session", "facts": [{"key": "b", "value": 2}]},
    )

    assert response.status_code == 200
    facts = response.json()["facts"]
    assert len(facts) == 1
    assert facts[0]["key"] == "b"


async def test_ttl_seconds_produces_computed_expiry(client: httpx.AsyncClient):
    response = await client.put(
        "/users/u1/memory",
        json={
            "tenantId": "t1",
            "memoryType": "session",
            "facts": [{"key": "a", "value": 1}],
            "ttl_seconds": 3600,
        },
    )

    assert response.status_code == 200
    assert response.json()["expiresAt"] is not None


async def test_expired_facts_behave_as_not_found(client: httpx.AsyncClient):
    await client.put(
        "/users/u1/memory",
        json={
            "tenantId": "t1",
            "memoryType": "session",
            "facts": [{"key": "a", "value": 1}],
            "ttl_seconds": 1,
        },
    )

    await asyncio.sleep(1.2)

    response = await client.get(
        "/users/u1/memory", params={"tenant_id": "t1", "memory_type": "session"}
    )

    assert response.status_code == 200
    assert response.json()["facts"] == []


async def test_mongodb_unavailable_returns_503():
    app.dependency_overrides[get_memory_facts] = lambda: BrokenMemoryFacts()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                "/users/u1/memory",
                json={"tenantId": "t1", "memoryType": "session", "facts": []},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
