import os
import sys

import pytest

from wfx_panel import autostart

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Registry chỉ có trên Windows")

TEST_KEY = r"Software\WFX-Panel-Test\Run"


@pytest.fixture
def scratch_key():
    yield TEST_KEY
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\WFX-Panel-Test")
    except OSError:
        pass


def test_disabled_when_value_absent(scratch_key):
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is False


def test_enable_then_disable_round_trip(scratch_key):
    autostart.enable(
        '"C:\\fake\\WFX-Panel.exe"', key_path=scratch_key, value_name="Probe"
    )
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is True
    autostart.disable(key_path=scratch_key, value_name="Probe")
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is False


def test_sync_returns_actual_state(scratch_key):
    assert autostart.sync(True, key_path=scratch_key, value_name="Probe") is True
    assert autostart.sync(False, key_path=scratch_key, value_name="Probe") is False


def test_disable_is_idempotent(scratch_key):
    autostart.disable(key_path=scratch_key, value_name="Probe")
    autostart.disable(key_path=scratch_key, value_name="Probe")
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is False


def test_launch_command_quotes_and_targets_module_in_dev():
    command = autostart.launch_command()
    assert command.startswith('"')
    assert "-m wfx_panel.panel_app" in command


def test_launch_command_uses_executable_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\app\WFX-Panel.exe")
    assert autostart.launch_command() == r'"C:\app\WFX-Panel.exe"'


def test_real_run_key_constant_is_hkcu_scoped():
    assert autostart.RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert autostart.VALUE_NAME == "WFXPanel"
