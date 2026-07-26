from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls = []

    def run(self, user_id, password, company_id="psh", log=print):
        self.calls.append(("run", user_id, password, company_id))
        log("[SESSION] fake login")
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    def check_session(self, log=print):
        self.calls.append(("check_session",))
        return {"ok": False, "code": "NOT_LOGGED_IN", "message": "no"}

    def start_chrome(self, log=print):
        self.calls.append(("start_chrome",))
        return {
            "ok": True,
            "code": "CHROME_OPENED",
            "message": "opened",
            "chrome_alive": True,
        }

    def open_module(self, module_name, xpath, log=print):
        self.calls.append(("open_module", module_name, xpath))
        return {"ok": True, "code": "MODULE_OPENED", "message": module_name}

    def set_catalog_category(self, category_name, category_value, log=print):
        self.calls.append(("set_catalog_category", category_name, category_value))
        return {"ok": True, "code": "CATEGORY_SELECTED", "message": category_name}

    def quick_find_catalog(self, category_name, category_value, filter_kind, query,
                           user_id, password, company_id="psh", log=print, destination=None):
        self.calls.append(("quick_find_catalog", category_name, category_value,
                           filter_kind, query, user_id, password, destination))
        return {"ok": True, "code": "RESULT_OPENED", "message": query, "codes": [query]}


def make_api(tmp_path):
    fake = FakeLogin()
    api = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    return api, fake


def test_find_code_calls_quick_find(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    result = api.find_code("Apparel", "ABC123", destination="bom")
    assert result["code"] == "RESULT_OPENED"
    assert ("quick_find_catalog", "Apparel", "01", "code", "ABC123", "u", "p", "bom") in fake.calls


def test_find_buyer_reference_uses_buyer_kind(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    api.find_buyer_reference("Apparel", "PO-9")
    assert ("quick_find_catalog", "Apparel", "01", "buyer_reference", "PO-9", "u", "p", None) in fake.calls


def test_open_module_builds_xpath(tmp_path):
    api, fake = make_api(tmp_path)
    api.open_module("0004_0050_0020")
    assert ("open_module", "OC List", '//*[@id="0004_0050_0020"]/a') in fake.calls


def test_open_chrome_uses_login_module(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    result = api.open_chrome()
    assert result["code"] == "LOGGED_IN"
    assert result["chrome_alive"] is True
    assert ("start_chrome",) in fake.calls
    assert ("run", "u", "p", "psh") in fake.calls
    assert "đăng nhập WFX" in result["message"]


def test_prepare_catalog_opens_then_selects(tmp_path):
    api, fake = make_api(tmp_path)
    api.prepare_catalog("Apparel")
    names = [c[0] for c in fake.calls]
    assert names == ["open_module", "set_catalog_category"]


def test_log_sink_receives_lines(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    lines = []
    api.set_log_sink(lines.append)
    api.login()
    assert any("fake login" in line for line in lines)
    assert ("run", "u", "p", "psh") in fake.calls


def test_get_initial_state(tmp_path):
    prefs.save_account("bob", "pw", base_dir=tmp_path)
    prefs.save_prefs(base_dir=tmp_path, theme="dark")
    api, _ = make_api(tmp_path)
    state = api.get_initial_state()
    assert state["user_id"] == "bob"
    assert state["theme"] == "dark"
    assert state["hotkey_label"] == "Ctrl + Shift + X"


def test_save_account_persists(tmp_path):
    api, _ = make_api(tmp_path)
    api.save_account("carol", "s3cret")
    assert prefs.load_account(base_dir=tmp_path)["user_id"] == "carol"


def test_save_account_blank_password_keeps_existing(tmp_path):
    # Password input trên UI không bao giờ được điền lại khi mở Settings, nên
    # nếu người dùng chỉ đổi User ID rồi lưu, password gửi lên sẽ luôn rỗng.
    # Không được ghi đè mật khẩu đã lưu bằng chuỗi rỗng.
    api, _ = make_api(tmp_path)
    api.save_account("dave", "s3cret")
    result = api.save_account("dave2", "")
    assert result["ok"] is True
    assert result["code"] == "ACCOUNT_SAVED"
    loaded = prefs.load_account(base_dir=tmp_path)
    assert loaded == {"user_id": "dave2", "password": "s3cret"}


def test_save_account_blank_password_and_no_stored_password_fails(tmp_path):
    api, _ = make_api(tmp_path)
    result = api.save_account("erin", "   ")
    assert result["ok"] is False
    assert result["code"] == "PASSWORD_REQUIRED"
    assert "mật khẩu" in result["message"].lower()
    # Không được ghi bất cứ thứ gì xuống .env khi từ chối lưu.
    assert prefs.load_account(base_dir=tmp_path) == {"user_id": "", "password": ""}


def test_result_sink_receives_method_result_and_elapsed(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, _ = make_api(tmp_path)
    seen = []
    api.set_result_sink(
        lambda method, result, elapsed: seen.append((method, result, elapsed))
    )
    api.find_code("Apparel", "ABC123")
    assert len(seen) == 1
    method, result, elapsed = seen[0]
    assert method == "find_code"
    assert result["code"] == "RESULT_OPENED"
    assert isinstance(elapsed, float) and elapsed >= 0


def test_result_sink_receives_early_validation_result(tmp_path):
    api, _ = make_api(tmp_path)
    seen = []
    api.set_result_sink(
        lambda method, result, elapsed: seen.append((method, result, elapsed))
    )
    result = api.open_module("not-a-module")
    assert result["code"] == "MODULE_UNKNOWN"
    assert len(seen) == 1
    assert seen[0][0] == "open_module"
    assert seen[0][1]["code"] == "MODULE_UNKNOWN"


def test_session_state_tracks_result_codes(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, _ = make_api(tmp_path)
    assert api.get_status()["session_active"] is None

    api.login()
    status_after_login = api.get_status()
    assert status_after_login["session_active"] is True
    assert status_after_login["last_login_at"] is not None

    api.check_session()
    assert api.get_status()["session_active"] is False


def test_unknown_result_code_leaves_session_state_untouched(tmp_path):
    api, _ = make_api(tmp_path)
    api._session_active = True
    api._observe("whatever", {"ok": False, "code": "SOMETHING_NEW"}, 0.1)
    assert api.get_status()["session_active"] is True


def test_set_hotkey_rejects_unsafe_combo(tmp_path):
    api, _ = make_api(tmp_path)
    result = api.set_hotkey("ctrl+backspace")
    assert result["ok"] is False
    assert result["code"] == "HOTKEY_INVALID"
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+shift+x"


def test_set_hotkey_applies_and_persists(tmp_path):
    api, _ = make_api(tmp_path)
    applied = []
    api.set_hotkey_applier(lambda spec: applied.append(spec) or None)
    result = api.set_hotkey("Alt+Shift+K")
    assert result["ok"] is True
    assert result["hotkey"] == "alt+shift+k"
    assert applied == ["alt+shift+k"]
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "alt+shift+k"


def test_set_hotkey_accepts_browser_event_payload(tmp_path):
    api, _ = make_api(tmp_path)
    result = api.set_hotkey(
        {
            "ctrl": True,
            "alt": True,
            "shift": False,
            "meta": False,
            "key": "J",
            "code": "KeyJ",
        }
    )
    assert result["ok"] is True
    assert result["hotkey"] == "ctrl+alt+j"


def test_set_hotkey_rolls_back_when_registration_fails(tmp_path):
    api, _ = make_api(tmp_path)
    attempts = []

    def applier(spec):
        attempts.append(spec)
        return (
            "Phím đang bị ứng dụng khác chiếm."
            if spec == "alt+shift+k"
            else None
        )

    api.set_hotkey_applier(applier)
    result = api.set_hotkey("alt+shift+k")
    assert result["ok"] is False
    assert result["code"] == "HOTKEY_REGISTER_FAILED"
    assert attempts == ["alt+shift+k", "ctrl+shift+x"]
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+shift+x"


def test_toggle_prefs_persist(tmp_path):
    api, _ = make_api(tmp_path)
    assert api.set_start_hidden(True)["start_hidden"] is True
    assert api.set_toast_enabled(False)["toast_enabled"] is False
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["start_hidden"] is True
    assert loaded["toast_enabled"] is False


def test_initial_state_exposes_new_fields(tmp_path):
    api, _ = make_api(tmp_path)
    state = api.get_initial_state()
    for field in (
        "hotkey",
        "hotkey_label",
        "autostart",
        "start_hidden",
        "toast_enabled",
        "chrome_alive",
        "session_active",
        "last_login_at",
    ):
        assert field in state, field


def test_git_update_methods_delegate_and_schedule(tmp_path, monkeypatch):
    api, _ = make_api(tmp_path)
    state = {
        "ok": True,
        "code": "UPDATE_AVAILABLE",
        "message": "Có bản mới.",
        "can_update": True,
        "branch": "main",
        "repo_root": str(tmp_path),
    }
    monkeypatch.setattr(
        "wfx_panel.panel_api.updater.check_for_updates",
        lambda **_kwargs: dict(state),
    )
    applied = []
    api.set_update_applier(lambda payload: applied.append(payload) or None)
    assert api.check_for_updates()["can_update"] is True
    result = api.install_update()
    assert result["code"] == "UPDATE_SCHEDULED"
    assert applied and applied[0]["branch"] == "main"


def test_panel_update_channel_is_always_stable(tmp_path, monkeypatch):
    api, _ = make_api(tmp_path)
    calls = []
    monkeypatch.setattr(
        "wfx_panel.panel_api.updater.check_for_updates",
        lambda **kwargs: calls.append(kwargs) or {
            "ok": True,
            "code": "UP_TO_DATE",
            "can_update": False,
        },
    )
    api.set_update_channel("current")
    assert prefs.load_prefs(base_dir=tmp_path)["update_channel"] == "stable"
    api.check_for_updates()
    api.install_update()
    assert calls == [{"channel": "stable"}, {"channel": "stable"}]


def test_automation_job_has_run_id_and_can_retry(tmp_path):
    api, fake = make_api(tmp_path)
    result = api.open_module("0004_0050_0020")
    assert result["run_id"]
    history = api.get_job_history()["jobs"]
    assert history[0]["run_id"] == result["run_id"]
    retried = api.retry_job(result["run_id"])
    assert retried["ok"] is True
    assert retried["run_id"] != result["run_id"]
    assert [call[0] for call in fake.calls].count("open_module") == 2


def test_job_history_never_stores_credentials(tmp_path):
    prefs.save_account("private-user", "private-password", base_dir=tmp_path)
    api, _ = make_api(tmp_path)
    api.login()
    serialized = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert "private-user" not in serialized
    assert "private-password" not in serialized


def test_initial_state_contains_module_classes_and_jobs(tmp_path):
    api, _ = make_api(tmp_path)
    state = api.get_initial_state()
    catalog = state["module_groups"][0]["modules"][0]
    assert catalog["kind"] == "catalog"
    assert catalog["description"]
    assert state["jobs"] == []


def test_window_preferences_apply_and_persist(tmp_path):
    api, _ = make_api(tmp_path)
    on_top = []
    stick = []
    api.set_window_pref_appliers(on_top.append, stick.append)
    top_result = api.set_always_on_top(False)
    stick_result = api.set_stick_to_browser(True)
    assert top_result["always_on_top"] is False
    assert stick_result["stick_to_browser"] is True
    assert on_top == [False]
    assert stick == [True]
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["always_on_top"] is False
    assert loaded["stick_to_browser"] is True


def test_failed_automation_records_local_screenshot(tmp_path):
    class FailingLogin(FakeLogin):
        def open_module(self, module_name, xpath, log=print):
            return {
                "ok": False,
                "code": "MODULE_FAILED",
                "message": "fake failure",
            }

        def capture_failure_screenshot(self, path, log=print):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png")
            return True

    api = PanelAPI(
        login_module=FailingLogin(),
        prefs_module=prefs,
        base_dir=tmp_path,
    )
    result = api.open_module("0004_0050_0020")
    assert result["ok"] is False
    job = api.get_job_history()["jobs"][0]
    assert job["run_id"] == result["run_id"]
    assert job["has_screenshot"] is True
    assert "password" not in str(job).lower()


class AuthorizedAdminLogin(FakeLogin):
    def check_module_access(self, specs, log=print):
        self.calls.append(("check_module_access", tuple(s["id"] for s in specs)))
        return {
            "ok": True,
            "code": "MODULE_ACCESS_CHECKED",
            "accessible_module_ids": ["0090_0250", "0004_0010_1720"],
        }


def test_admin_mode_requires_real_wfx_access(tmp_path):
    api, fake = make_api(tmp_path)
    denied = api.set_admin_mode(True)
    assert denied["code"] == "ADMIN_ACCESS_DENIED"
    assert denied["admin_access"] is False
    assert prefs.load_prefs(base_dir=tmp_path)["admin_mode"] is False
    opened = api.open_module("0090_0250")
    assert opened["code"] == "ADMIN_ACCESS_DENIED"
    assert not any(
        call[:2] == ("open_module", "System Coding")
        for call in fake.calls
    )


def test_admin_login_exposes_only_authorized_modules(tmp_path):
    fake = AuthorizedAdminLogin()
    api = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    prefs.save_account("admin", "pw", base_dir=tmp_path)
    logged_in = api.login()
    assert logged_in["admin_access"] is True
    assert logged_in["admin_mode"] is False
    assert logged_in["admin_module_ids"] == ["0004_0010_1720", "0090_0250"]

    enabled = api.set_admin_mode(True)
    assert enabled["admin_mode"] is True
    opened = api.open_module("0090_0250")
    assert opened["ok"] is True
    assert ("open_module", "System Coding", '//*[@id="0090_0250"]/a') in fake.calls


def test_feedback_queues_without_exposing_webhook(tmp_path, monkeypatch):
    monkeypatch.delenv("WFX_ERROR_WEBHOOK_URL", raising=False)
    api, _ = make_api(tmp_path)
    result = api.submit_feedback("bug", "Nút Catalog không phản hồi", True)
    assert result["ok"] is True
    assert result["code"] == "FEEDBACK_QUEUED"
    assert result["reporting_configured"] is False
    assert "webhook" not in result
    outbox = (tmp_path / "telemetry-outbox.json").read_text(encoding="utf-8")
    assert "Nút Catalog không phản hồi" in outbox
