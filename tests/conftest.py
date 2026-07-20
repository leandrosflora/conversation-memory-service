import pytest

import app.main as main_module

TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _disable_internal_auth():
    # PlatformMiddleware is added with the module-level `settings` singleton at app-construction
    # time (see app/main.py), not resolved per-request via FastAPI DI, so per-test dependency
    # overrides can't reach it. Mutating that same singleton in place (rather than signing a
    # real JWT) mirrors how conversation-orchestrator's WebApplicationFactory tests bypass
    # internal auth; PlatformMiddleware still requires and validates the X-Tenant-Id header
    # either way (each test's client fixture sets it), so tenant scoping is still exercised.
    original = main_module.settings.internal_auth_enabled
    main_module.settings.internal_auth_enabled = False
    yield
    main_module.settings.internal_auth_enabled = original
