from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter

from app.models import MessageAppendRequest, MessageResponse
from app.platform import current_tenant_id
from app.repositories.message_history import MessageHistoryRepository

router = APIRouter(tags=["messages"])
MESSAGE_OPERATIONS = Counter(
    "memory_message_operations_total",
    "Tenant-scoped message history operations.",
    ["operation", "outcome"],
)


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
    tenant_id = current_tenant_id()
    if payload.tenant_id != tenant_id:
        MESSAGE_OPERATIONS.labels("append", "tenant_mismatch").inc()
        raise HTTPException(status_code=400, detail="Tenant header and payload do not match.")

    message = payload.model_dump(by_alias=True, exclude_none=True)
    message["tenantId"] = tenant_id
    document, created = await repo.append(conversation_id, message)
    body = _to_response(document).model_dump(mode="json", by_alias=True)
    MESSAGE_OPERATIONS.labels("append", "created" if created else "duplicate").inc()
    return JSONResponse(
        status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        content=body,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    limit: int | None = Query(default=None, ge=1),
    repo: MessageHistoryRepository = Depends(get_message_history),
) -> list[MessageResponse]:
    documents = await repo.list_by_conversation(
        conversation_id,
        current_tenant_id(),
        limit,
    )
    MESSAGE_OPERATIONS.labels("list", "success").inc()
    return [_to_response(document) for document in documents]
