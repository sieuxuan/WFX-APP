from __future__ import annotations

import pytest

from wfx_panel import telemetry


@pytest.fixture(autouse=True)
def disable_production_telemetry_for_tests(monkeypatch):
    """Mọi test mặc định phải tuyệt đối im lặng với webhook production."""
    monkeypatch.delenv(telemetry.ENV_NAME, raising=False)
    monkeypatch.setattr(telemetry, "DEFAULT_WEBHOOK_URL", "")
