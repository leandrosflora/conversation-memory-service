from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.models import SessionPutRequest, SessionResponse
from app.repositories.session_store import SessionStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


@router.get("/{conversation_id}", response_model=SessionResponse)
async def get_session(
    conversation_id: str, store: SessionStore = Depends(get_session_store)
) -> SessionResponse:
    session = await store.get(conversation_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionResponse(**session)


@router.put("/{conversation_id}", response_model=SessionResponse)
async def put_session(
    conversation_id: str,
    payload: SessionPutRequest,
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    session = await store.put(conversation_id, payload.data, payload.ttl_seconds)
    return SessionResponse(**session)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    conversation_id: str, store: SessionStore = Depends(get_session_store)
) -> Response:
    await store.delete(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
