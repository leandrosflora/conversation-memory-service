import fakeredis
import httpx
import pytest
from httpx import ASGITransport

from app.api.sessions import get_session_store
from app.errors import DatastoreUnavailableError
from app.main import app
from app.repositories.session_store import SessionStore
from tests.conftest import TENANT_ID


@pytest.fixture
def session_store() -> SessionStore:
    return SessionStore(fakeredis.FakeAsyncRedis(), default_ttl_seconds=1800)


@pytest.fixture
async def client(session_store: SessionStore):
    app.dependency_overrides[get_session_store] = lambda: session_store
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Tenant-Id": TENANT_ID}
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


class BrokenSessionStore:
    async def get(self, tenant_id: str, conversation_id: str):
        raise DatastoreUnavailableError("Redis unavailable")

    async def put(self, tenant_id: str, conversation_id: str, data, ttl_seconds=None):
        raise DatastoreUnavailableError("Redis unavailable")

    async def delete(self, tenant_id: str, conversation_id: str):
        raise DatastoreUnavailableError("Redis unavailable")


async def test_get_missing_session_returns_404(client: httpx.AsyncClient):
    response = await client.get("/sessions/conv-missing")

    assert response.status_code == 404


async def test_put_creates_session_with_default_ttl(
    client: httpx.AsyncClient, session_store: SessionStore
):
    response = await client.put("/sessions/conv-1", json={"data": {"stage": "greeting"}})

    assert response.status_code == 200
    assert response.json()["data"] == {"stage": "greeting"}

    ttl = await session_store._client.ttl(f"tenant:{TENANT_ID}:session:conv-1")
    assert 0 < ttl <= 1800


async def test_get_existing_session_returns_data(client: httpx.AsyncClient):
    await client.put("/sessions/conv-1", json={"data": {"stage": "greeting"}})

    response = await client.get("/sessions/conv-1")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"stage": "greeting"}
    assert body["conversation_id"] == "conv-1"
    assert "updated_at" in body


async def test_put_refreshes_existing_session(client: httpx.AsyncClient):
    await client.put("/sessions/conv-1", json={"data": {"stage": "greeting"}})
    response = await client.put("/sessions/conv-1", json={"data": {"stage": "eligibility"}})

    assert response.status_code == 200
    assert response.json()["data"] == {"stage": "eligibility"}


async def test_put_honors_explicit_ttl(client: httpx.AsyncClient, session_store: SessionStore):
    await client.put("/sessions/conv-1", json={"data": {"stage": "greeting"}, "ttl_seconds": 5})

    ttl = await session_store._client.ttl(f"tenant:{TENANT_ID}:session:conv-1")
    assert 0 < ttl <= 5


async def test_delete_existing_session(client: httpx.AsyncClient):
    await client.put("/sessions/conv-1", json={"data": {"stage": "greeting"}})

    response = await client.delete("/sessions/conv-1")
    assert response.status_code == 204

    response = await client.get("/sessions/conv-1")
    assert response.status_code == 404


async def test_delete_missing_session_is_idempotent(client: httpx.AsyncClient):
    response = await client.delete("/sessions/conv-missing")

    assert response.status_code == 204


async def test_redis_unavailable_returns_503():
    app.dependency_overrides[get_session_store] = lambda: BrokenSessionStore()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"X-Tenant-Id": TENANT_ID}
        ) as ac:
            response = await ac.get("/sessions/conv-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
