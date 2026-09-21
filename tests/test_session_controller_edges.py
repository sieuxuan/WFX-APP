"""Controller phiên: lưu tài khoản, heartbeat, mở lại Chrome, và thoát app.

CLAUDE.md: mật khẩu chỉ nằm trong `.env` đã mã hóa DPAPI — Windows từ chối mã
hóa thì phải báo lỗi chứ không ghi thường; app tự nhớ chủ phiên mỗi lần chính
nó đăng nhập; heartbeat thành công im lặng tuyệt đối; và `Thoát và đóng trình
duyệt` phải đóng Chrome trên chính automation worker để không tạo race CDP.
"""

from __future__ import annotations

import pytest

from tests.test_panel_api import FakeLogin, make_api
from wfx_panel.controllers import session as session_module


@pytest.fixture
def api(tmp_path):
    instance, _fake = make_api(tmp_path)
    return instance


@pytest.fixture
def session(api):
    return api._session


# --- lưu tài khoản ------------------------------------------------------


def test_a_password_windows_refuses_to_encrypt_is_reported_not_stored(
    api, session, monkeypatch
):
    class CredentialProtectionError(RuntimeError):
        pass

    def refuse(*_args, **_kwargs):
        raise CredentialProtectionError("DPAPI từ chối mã hóa")

    monkeypatch.setattr(
        api._prefs, "CredentialProtectionError", CredentialProtectionError,
        raising=False,
    )
    monkeypatch.setattr(api._prefs, "save_account", refuse)

    result = session.save_account("tester", "mat-khau")

    assert result["code"] == "CREDENTIAL_PROTECTION_FAILED"
    assert "DPAPI" in result["message"]


def test_a_new_user_id_without_a_password_is_refused(api, session):
    result = session.save_account("nguoi-khac", "")

    assert result["code"] == "PASSWORD_REQUIRED"


# --- nhớ chủ phiên ------------------------------------------------------


def test_the_session_owner_is_written_to_prefs_when_the_app_logs_in(
    api, session
):
    session._remember_session_user("tester")

    assert api._session_user_id == "tester"
    assert api._prefs.load_prefs(base_dir=api._base_dir)["session_user_id"] == (
        "tester"
    )


def test_remembering_the_same_owner_twice_does_not_rewrite_prefs(
    api, session, monkeypatch
):
    session._remember_session_user("tester")
    writes: list[int] = []
    monkeypatch.setattr(
        api._prefs, "save_prefs", lambda **_kw: writes.append(1)
    )

    session._remember_session_user("tester")

    assert writes == []


def test_an_old_prefs_module_that_does_not_know_the_key_still_protects_the_run(
    api, session, monkeypatch
):
    def old_prefs(**_kwargs):
        raise TypeError("save_prefs() got an unexpected keyword argument")

    monkeypatch.setattr(api._prefs, "save_prefs", old_prefs)

    session._remember_session_user("tester")

    assert api._session_user_id == "tester"


# --- gọi login module ---------------------------------------------------


def test_a_login_module_that_knows_the_session_owner_is_told_who_it_is(
    api, session, monkeypatch
):
    seen: list[dict] = []

    def run(user_id, password, company_id, log, *, session_owner=None):
        seen.append({"user_id": user_id, "session_owner": session_owner})
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    monkeypatch.setattr(api._login, "run", run)
    session._remember_session_user("tester")

    session._login_run("tester", "mat-khau")

    assert seen[0]["session_owner"] == "tester"


def test_an_older_login_module_is_called_without_the_extra_argument(
    api, session, monkeypatch
):
    seen: list[tuple] = []

    def run(user_id, password, company_id, log):
        seen.append((user_id, password))
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    monkeypatch.setattr(api._login, "run", run)

    session._login_run("tester", "mat-khau")

    assert seen == [("tester", "mat-khau")]


def test_a_login_callable_python_cannot_inspect_is_still_called(
    api, session, monkeypatch
):
    class Builtin:
        """Callable không có chữ ký đọc được, như hàm C."""

        def __call__(self, *args, **_kwargs):
            self.args = args
            return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    runner = Builtin()
    monkeypatch.setattr(api._login, "run", len)
    monkeypatch.setattr(
        session_module.inspect,
        "signature",
        lambda _target: (_ for _ in ()).throw(ValueError("không đọc được")),
    )
    monkeypatch.setattr(api._login, "run", runner)

    assert session._login_run("tester", "mat-khau")["ok"] is True
    assert runner.args[0] == "tester"


# --- trạng thái credential ----------------------------------------------


def test_an_old_prefs_module_reports_credentials_from_the_saved_account(
    api, session, monkeypatch
):
    monkeypatch.setattr(api._prefs, "credential_status", None, raising=False)
    api._prefs.save_account("tester", "mat-khau", base_dir=api._base_dir)

    assert session._credential_state() == "ok"


def test_an_account_that_was_never_saved_reads_as_empty(
    api, session, monkeypatch
):
    monkeypatch.setattr(api._prefs, "credential_status", None, raising=False)

    assert session._credential_state() == "empty"


def test_a_prefs_file_that_cannot_be_read_reads_as_empty(
    api, session, monkeypatch
):
    def refuse(**_kwargs):
        raise OSError("ổ đĩa lỗi")

    monkeypatch.setattr(api._prefs, "credential_status", refuse, raising=False)

    assert session._credential_state() == "empty"


# --- mở lại Chrome giữa một flow ----------------------------------------


def test_a_browser_that_will_not_reopen_stops_the_retry(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login,
        "start_chrome",
        lambda _log: {"ok": False, "code": "BROWSER_NOT_FOUND", "message": "x"},
        raising=False,
    )

    result = session._run_action_with_auto_relogin(
        "open_module", lambda: {"ok": False, "code": "CHROME_CLOSED"}
    )

    assert result["code"] in {"BROWSER_NOT_FOUND", "CHROME_CLOSED"}


def test_a_reopened_browser_without_saved_credentials_asks_the_user_to_save(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login,
        "start_chrome",
        lambda _log: {"ok": True, "browser_name": "Chrome"},
        raising=False,
    )
    monkeypatch.setattr(session, "_restore_expired_session", lambda: None)

    result = session._run_action_with_auto_relogin(
        "open_module", lambda: {"ok": False, "code": "CHROME_CLOSED"}
    )

    assert result["code"] == "MISSING_CREDENTIALS"
    assert result["chrome_alive"] is True
    assert result["browser_name"] == "Chrome"


def test_a_reopened_browser_that_cannot_log_in_reports_the_login_failure(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login,
        "start_chrome",
        lambda _log: {"ok": True, "browser_name": "Chrome"},
        raising=False,
    )
    monkeypatch.setattr(
        session,
        "_restore_expired_session",
        lambda: {"ok": False, "code": "LOGIN_FAILED", "message": "sai mật khẩu"},
    )

    result = session._run_action_with_auto_relogin(
        "open_module", lambda: {"ok": False, "code": "CHROME_CLOSED"}
    )

    assert result["code"] == "LOGIN_FAILED"
    assert result["chrome_alive"] is True


def test_a_reopen_result_that_is_not_a_result_dict_is_reported_as_a_failure(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login, "start_chrome", lambda _log: "hỏng", raising=False
    )

    result = session._run_action_with_auto_relogin(
        "open_module", lambda: {"ok": False, "code": "CHROME_CLOSED"}
    )

    assert result["code"] == "CHROME_OPEN_FAILED"
    assert result["chrome_alive"] is False


# --- mở Chrome từ tab Tài khoản ------------------------------------------


def test_a_browser_that_cannot_start_is_reported_before_logging_in(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login,
        "start_chrome",
        lambda _log: {"ok": False, "code": "BROWSER_NOT_FOUND", "message": "x"},
        raising=False,
    )
    monkeypatch.setattr(
        session,
        "_login_run",
        lambda *_a: pytest.fail("chưa mở được Chrome thì không được đăng nhập"),
    )

    assert session.open_chrome()["code"] == "BROWSER_NOT_FOUND"


# --- thoát app -----------------------------------------------------------


def test_quitting_without_closing_the_browser_leaves_chrome_alone(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login,
        "close_chrome",
        lambda _log: pytest.fail("không được đóng Chrome khi user giữ trình duyệt"),
        raising=False,
    )
    monkeypatch.setattr(session_module.automation_runtime, "shutdown", lambda: None)

    session.shutdown(close_browser=False)


def test_quitting_and_closing_the_browser_runs_on_the_automation_worker(
    api, session, monkeypatch
):
    order: list[str] = []
    monkeypatch.setattr(
        api._login, "close_chrome", lambda _log: order.append("close"), raising=False
    )
    monkeypatch.setattr(
        session_module.AUTOMATION_RUNTIME,
        "request_cancel",
        lambda: order.append("cancel"),
    )
    monkeypatch.setattr(
        session_module.AUTOMATION_RUNTIME,
        "execute",
        lambda action: order.append("execute") or action(),
    )
    monkeypatch.setattr(session_module.automation_runtime, "shutdown", lambda: None)

    session.shutdown(close_browser=True)

    assert order == ["cancel", "execute", "close"]


def test_a_browser_that_refuses_to_close_does_not_stop_the_app_from_quitting(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login, "close_chrome", lambda _log: None, raising=False
    )
    monkeypatch.setattr(
        session_module.AUTOMATION_RUNTIME, "request_cancel", lambda: None
    )

    def refuse(_action):
        raise RuntimeError("worker đã dừng")

    monkeypatch.setattr(session_module.AUTOMATION_RUNTIME, "execute", refuse)
    shut: list[int] = []
    monkeypatch.setattr(
        session_module.automation_runtime, "shutdown", lambda: shut.append(1)
    )

    session.shutdown(close_browser=True)

    assert shut == [1]
    assert any("Không đóng được trình duyệt" in line for line in api._logs)


def test_an_automation_build_without_close_chrome_still_quits(
    tmp_path, monkeypatch
):
    from wfx_panel import prefs
    from wfx_panel.panel_api import PanelAPI

    class NoCloser(FakeLogin):
        close_chrome = None

    api = PanelAPI(
        login_module=NoCloser(), prefs_module=prefs, base_dir=tmp_path
    )
    shut: list[int] = []
    monkeypatch.setattr(
        session_module.automation_runtime, "shutdown", lambda: shut.append(1)
    )

    api._session.shutdown(close_browser=True)

    assert shut == [1]


# --- heartbeat ------------------------------------------------------------


def test_a_heartbeat_that_finds_a_live_session_stays_completely_silent(
    api, session, monkeypatch
):
    monkeypatch.setattr(
        api._login,
        "check_session",
        lambda _log: {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"},
        raising=False,
    )
    before = len(api._logs)

    result = session.maintain_session()

    assert result["code"] == "SESSION_ACTIVE"
    assert len(api._logs) == before


def test_a_heartbeat_that_finds_an_expired_session_logs_what_it_saw(
    api, session, monkeypatch
):
    def check(log):
        log("[SESSION] Không còn phiên đăng nhập")
        return {"ok": False, "code": "NOT_LOGGED_IN", "message": "hết hạn"}

    monkeypatch.setattr(api._login, "check_session", check, raising=False)
    monkeypatch.setattr(session, "_restore_expired_session", lambda: None)

    result = session.maintain_session()

    assert result["code"] == "NOT_LOGGED_IN"
    assert any("Không còn phiên đăng nhập" in line for line in api._logs)
