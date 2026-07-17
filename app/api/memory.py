from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.models import MemoryResponse, MemoryUpsertRequest
from app.repositories.memory_facts import MemoryFactsRepository

router = APIRouter(prefix="/users", tags=["memory"])


def get_memory_facts(request: Request) -> MemoryFactsRepository:
    return request.app.state.memory_facts


@router.get("/{user_id}/memory", response_model=MemoryResponse)
async def get_memory(
    user_id: str,
    tenant_id: str = Query(...),
    memory_type: str = Query(...),
    repo: MemoryFactsRepository = Depends(get_memory_facts),
) -> MemoryResponse:
    document = await repo.get(tenant_id, user_id, memory_type)
    if document is None:
        return MemoryResponse(tenantId=tenant_id, userId=user_id, memoryType=memory_type, facts=[])
    return MemoryResponse.model_validate(document)


@router.put("/{user_id}/memory", response_model=MemoryResponse)
async def put_memory(
    user_id: str,
    payload: MemoryUpsertRequest,
    repo: MemoryFactsRepository = Depends(get_memory_facts),
) -> MemoryResponse:
    document = await repo.upsert(
        tenant_id=payload.tenant_id,
        user_id=user_id,
        memory_type=payload.memory_type,
        facts=[fact.model_dump() for fact in payload.facts],
        source_conversation_id=payload.source_conversation_id,
        ttl_seconds=payload.ttl_seconds,
    )
    return MemoryResponse.model_validate(document)
