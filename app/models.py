from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Field names below use the same camelCase spelling as the MongoDB documents in
# database/conversational-ai-mongodb-init.js (tenantId, conversationId, ...), since that
# schema - not a caller contract - is this service's fixed source of truth. `populate_by_name`
# lets the models also be constructed with snake_case kwargs internally.


class SessionPutRequest(BaseModel):
    data: dict[str, Any]
    ttl_seconds: int | None = None


class SessionResponse(BaseModel):
    conversation_id: str
    data: dict[str, Any]
    updated_at: str


class MessageAppendRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    user_id: str | None = Field(default=None, alias="userId")
    channel: str | None = None
    provider: str | None = None
    external_message_id: str | None = Field(default=None, alias="externalMessageId")
    role: str
    content: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, alias="correlationId")
    trace_id: str | None = Field(default=None, alias="traceId")


class MessageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    tenant_id: str = Field(alias="tenantId")
    conversation_id: str = Field(alias="conversationId")
    user_id: str | None = Field(default=None, alias="userId")
    channel: str | None = None
    provider: str | None = None
    external_message_id: str | None = Field(default=None, alias="externalMessageId")
    role: str
    content: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, alias="correlationId")
    trace_id: str | None = Field(default=None, alias="traceId")
    created_at: datetime = Field(alias="createdAt")


class MemoryFact(BaseModel):
    key: str
    value: Any
    confidence: float | None = None


class MemoryUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    memory_type: str = Field(alias="memoryType")
    facts: list[MemoryFact]
    source_conversation_id: str | None = Field(default=None, alias="sourceConversationId")
    ttl_seconds: int | None = None


class MemoryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    user_id: str = Field(alias="userId")
    memory_type: str = Field(alias="memoryType")
    facts: list[MemoryFact]
    source_conversation_id: str | None = Field(default=None, alias="sourceConversationId")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
