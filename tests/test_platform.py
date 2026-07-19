from __future__ import annotations

import pytest

from app.platform import normalize_tenant_id


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
