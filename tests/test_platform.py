from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from starlette.responses import JSONResponse

from app.platform import PlatformMiddleware, normalize_tenant_id

ISSUER = "conversational-ai-platform"
AUDIENCE = "conversation-memory-service"
TENANT_ID = "00000000-0000-0000-0000-000000000001"

ORCHESTRATOR_SECRET = "orchestrator-secret-value-0123456789ab"
AGENT_RUNTIME_SECRET = "agent-runtime-secret-value-0123456789"


def _settings(**inbound_secrets: str) -> SimpleNamespace:
    return SimpleNamespace(
        internal_auth_enabled=True,
        internal_auth_service_name=AUDIENCE,
        internal_auth_issuer=ISSUER,
        internal_auth_inbound_secrets=inbound_secrets,
    )


def _middleware(settings: SimpleNamespace) -> PlatformMiddleware:
    return PlatformMiddleware(app=None, settings=settings)


def _mint_token(*, kid: str, sub: str, secret: str, aud: str = AUDIENCE, iss: str = ISSUER) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "tenant_id": TENANT_ID,
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(claims, secret, algorithm="HS256", headers={"kid": kid})


def test_normalize_tenant_returns_canonical_uuid() -> None:
    assert normalize_tenant_id("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE") == (
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )


def test_normalize_tenant_rejects_arbitrary_identifier() -> None:
    with pytest.raises(ValueError, match="UUID"):
        normalize_tenant_id("tenant:a")


def test_normalize_tenant_rejects_empty_uuid() -> None:
    with pytest.raises(ValueError, match="empty UUID"):
        normalize_tenant_id("00000000-0000-0000-0000-000000000000")


def test_accepts_token_from_conversation_orchestrator() -> None:
    settings = _settings(**{
        "conversation-orchestrator": ORCHESTRATOR_SECRET,
        "agent-runtime-renegotiation": AGENT_RUNTIME_SECRET,
    })
    middleware = _middleware(settings)
    token = _mint_token(
        kid="conversation-orchestrator",
        sub="conversation-orchestrator",
        secret=ORCHESTRATOR_SECRET,
    )

    result = middleware._authenticate(f"Bearer {token}")

    assert isinstance(result, dict)
    assert result["sub"] == "conversation-orchestrator"


def test_accepts_token_from_agent_runtime_renegotiation() -> None:
    settings = _settings(**{
        "conversation-orchestrator": ORCHESTRATOR_SECRET,
        "agent-runtime-renegotiation": AGENT_RUNTIME_SECRET,
    })
    middleware = _middleware(settings)
    token = _mint_token(
        kid="agent-runtime-renegotiation",
        sub="agent-runtime-renegotiation",
        secret=AGENT_RUNTIME_SECRET,
    )

    result = middleware._authenticate(f"Bearer {token}")

    assert isinstance(result, dict)
    assert result["sub"] == "agent-runtime-renegotiation"


def test_rejects_token_with_kid_outside_allow_list() -> None:
    settings = _settings(**{"conversation-orchestrator": ORCHESTRATOR_SECRET})
    middleware = _middleware(settings)
    # Signed with a secret this service never configured for any caller.
    token = _mint_token(kid="whatsapp-bff", sub="whatsapp-bff", secret="a" * 32)

    result = middleware._authenticate(f"Bearer {token}")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 401


def test_rejects_valid_kid_but_wrong_signature() -> None:
    settings = _settings(**{"conversation-orchestrator": ORCHESTRATOR_SECRET})
    middleware = _middleware(settings)
    # kid is allow-listed, but the token was signed with a different secret.
    token = _mint_token(
        kid="conversation-orchestrator",
        sub="conversation-orchestrator",
        secret="wrong-secret-that-is-not-configured",
    )

    result = middleware._authenticate(f"Bearer {token}")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 401


def test_rejects_kid_sub_mismatch() -> None:
    settings = _settings(**{
        "conversation-orchestrator": ORCHESTRATOR_SECRET,
        "agent-runtime-renegotiation": AGENT_RUNTIME_SECRET,
    })
    middleware = _middleware(settings)
    token = _mint_token(
        kid="agent-runtime-renegotiation",
        sub="conversation-orchestrator",
        secret=AGENT_RUNTIME_SECRET,
    )

    result = middleware._authenticate(f"Bearer {token}")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 401


def test_rejects_when_no_inbound_secrets_configured() -> None:
    settings = _settings()
    middleware = _middleware(settings)
    token = _mint_token(
        kid="conversation-orchestrator",
        sub="conversation-orchestrator",
        secret=ORCHESTRATOR_SECRET,
    )

    result = middleware._authenticate(f"Bearer {token}")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 401
