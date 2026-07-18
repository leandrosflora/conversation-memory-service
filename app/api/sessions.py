from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from prometheus_client import Counter

from app.models import SessionPutRequest, SessionResponse
from app.platform import current_tenant_id
from app.repositories.session_store import SessionStore

router = APIRouter(prefix="/sessions", tags=["sessions"])
SESSION_OPERATIONS = Counter(
    "memory_session_operations_total",
    "Tenant-scoped Redis session operations.",
    ["operation", "outcome"],
)


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


@router.get("/{conversation_id}", response_model=SessionResponse)
async def get_session(
    conversation_id: str,
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    session = await store.get(current_tenant_id(), conversation_id)
    if session is None:
        SESSION_OPERATIONS.labels("get", "not_found").inc()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    SESSION_OPERATIONS.labels("get", "success").inc()
    return SessionResponse(**session)


@router.put("/{conversation_id}", response_model=SessionResponse)
async def put_session(
    conversation_id: str,
    payload: SessionPutRequest,
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    session = await store.put(
        current_tenant_id(),
        conversation_id,
        payload.data,
        payload.ttl_seconds,
    )
    SESSION_OPERATIONS.labels("put", "success").inc()
    return SessionResponse(**session)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    conversation_id: str,
    store: SessionStore = Depends(get_session_store),
) -> Response:
    await store.delete(current_tenant_id(), conversation_id)
    SESSION_OPERATIONS.labels("delete", "success").inc()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
