from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from prometheus_client import Counter

from app.models import MemoryResponse, MemoryUpsertRequest
from app.platform import current_tenant_id
from app.repositories.memory_facts import MemoryFactsRepository

router = APIRouter(prefix="/users", tags=["memory"])
MEMORY_OPERATIONS = Counter(
    "memory_fact_operations_total",
    "Tenant-scoped long-term memory operations.",
    ["operation", "outcome"],
)


def get_memory_facts(request: Request) -> MemoryFactsRepository:
    return request.app.state.memory_facts


@router.get("/{user_id}/memory", response_model=MemoryResponse)
async def get_memory(
    user_id: str,
    memory_type: str = Query(...),
    repo: MemoryFactsRepository = Depends(get_memory_facts),
) -> MemoryResponse:
    tenant_id = current_tenant_id()
    document = await repo.get(tenant_id, user_id, memory_type)
    if document is None:
        MEMORY_OPERATIONS.labels("get", "empty").inc()
        return MemoryResponse(
            tenantId=tenant_id,
            userId=user_id,
            memoryType=memory_type,
            facts=[],
        )
    MEMORY_OPERATIONS.labels("get", "success").inc()
    return MemoryResponse.model_validate(document)


@router.put("/{user_id}/memory", response_model=MemoryResponse)
async def put_memory(
    user_id: str,
    payload: MemoryUpsertRequest,
    repo: MemoryFactsRepository = Depends(get_memory_facts),
) -> MemoryResponse:
    tenant_id = current_tenant_id()
    if payload.tenant_id != tenant_id:
        MEMORY_OPERATIONS.labels("put", "tenant_mismatch").inc()
        raise HTTPException(status_code=400, detail="Tenant header and payload do not match.")

    document = await repo.upsert(
        tenant_id=tenant_id,
        user_id=user_id,
        memory_type=payload.memory_type,
        facts=[fact.model_dump() for fact in payload.facts],
        source_conversation_id=payload.source_conversation_id,
        ttl_seconds=payload.ttl_seconds,
    )
    MEMORY_OPERATIONS.labels("put", "success").inc()
    return MemoryResponse.model_validate(document)
