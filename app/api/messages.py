from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.models import MessageAppendRequest, MessageResponse
from app.repositories.message_history import MessageHistoryRepository

router = APIRouter(tags=["messages"])


def get_message_history(request: Request) -> MessageHistoryRepository:
    return request.app.state.message_history


def _to_response(document: dict[str, Any]) -> MessageResponse:
    return MessageResponse.model_validate({**document, "_id": str(document["_id"])})


@router.post("/conversations/{conversation_id}/messages")
async def append_message(
    conversation_id: str,
    payload: MessageAppendRequest,
    repo: MessageHistoryRepository = Depends(get_message_history),
) -> JSONResponse:
    message = payload.model_dump(by_alias=True, exclude_none=True)
    document, created = await repo.append(conversation_id, message)
    body = _to_response(document).model_dump(mode="json", by_alias=True)
    status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return JSONResponse(status_code=status_code, content=body)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    tenant_id: str = Query(...),
    limit: int | None = Query(default=None, ge=1),
    repo: MessageHistoryRepository = Depends(get_message_history),
) -> list[MessageResponse]:
    documents = await repo.list_by_conversation(conversation_id, tenant_id, limit)
    return [_to_response(document) for document in documents]
