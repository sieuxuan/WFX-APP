"""Đăng nhập, giữ phiên WFX và lưu tài khoản.

Hai ràng buộc an toàn quan trọng nhất của app nằm ở đây:

1. WFX đã từ chối đúng bộ User ID + mật khẩu đang lưu (``LOGIN_FAILED``) thì
   KHÔNG được tự đăng nhập lại bằng đúng bộ đó nữa cho tới khi người dùng
   lưu credential mới hoặc chủ động bấm đăng nhập — mỗi lần thử là một lần
   nhập sai trên WFX, đủ nhiều thì tài khoản bị khóa.
2. App tự nhớ chủ phiên mỗi lần chính nó đăng nhập. Trùng User ID mới được
   trả ``SESSION_REUSED``; WFX không nhả phiên cũ thì trả
   ``SESSION_USER_MISMATCH`` và dừng, tuyệt đối không chạy automation bằng
   tài khoản người khác.

State phiên ở lại ``PanelAPI`` vì mọi kết quả flow đều mang nó về UI."""

from __future__ import annotations

import hashlib
import inspect
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel.automation import runtime as automation_runtime
from wfx_panel.automation.runtime import RUNTIME as AUTOMATION_RUNTIME
from wfx_panel.run_policy import AUTO_RELOGIN_EXCLUDED_METHODS


class SessionController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    # -- settings ----------------------------------------------------------
    def save_account(self, user_id: str, password: str) -> dict:
        panel = self._panel
        # Password field trên UI không bao giờ được điền lại (get_initial_state
        # chỉ trả user_id) nên luôn trống khi sheet mở lại. Nếu người dùng chỉ
        # sửa User ID hoặc bấm CTA mà không gõ lại mật khẩu, KHÔNG được ghi đè
        # mật khẩu đã lưu bằng chuỗi rỗng — giữ nguyên mật khẩu cũ.
        user_id = str(user_id or "").strip()
        previous_user_id = str(
            self._account().get("user_id") or ""
        ).strip()
        password = password or ""
        if not user_id:
            return {
                "ok": False,
                "code": "USER_ID_REQUIRED",
                "message": "Vui lòng nhập User ID trước khi kết nối.",
            }
        account_changed = previous_user_id.casefold() != user_id.casefold()
        if not password.strip():
            # Kế thừa mật khẩu cũ CHỈ đúng khi vẫn là tài khoản cũ. Ghép User
            # ID mới với mật khẩu của người khác thì lần đăng nhập nào cũng
            # sai, và mỗi lần sai là một bước tới khóa tài khoản trên WFX.
            if account_changed and previous_user_id:
                return {
                    "ok": False,
                    "code": "PASSWORD_REQUIRED",
                    "message": (
                        "Đổi sang User ID khác thì phải nhập mật khẩu của "
                        "chính tài khoản đó."
                    ),
                }
            existing_password = self._account().get("password", "")
            if not existing_password.strip():
                return {
                    "ok": False,
                    "code": "PASSWORD_REQUIRED",
                    "message": "Vui lòng nhập mật khẩu trước khi lưu.",
                }
            password = existing_password
        try:
            panel._prefs.save_account(user_id, password, base_dir=panel._base_dir)
        except getattr(
            panel._prefs,
            "CredentialProtectionError",
            RuntimeError,
        ) as error:
            return {
                "ok": False,
                "code": "CREDENTIAL_PROTECTION_FAILED",
                "message": str(error),
            }
        panel._rejected_credential = None
        if account_changed:
            # Chrome vẫn đang giữ phiên của tài khoản CŨ. Giữ nguyên cờ "đã
            # đăng nhập" ở đây là nói dối: mọi automation chạy sau đó vẫn là
            # người cũ. Hạ toàn bộ trạng thái dẫn xuất và để lần login kế
            # tiếp tự đổi phiên (_session_user_id vẫn là chủ phiên cũ).
            panel._session_active = None
            panel._last_login_at = None
            panel._current_division = None
            panel._division_label = None
            panel._division_name = None
            panel._admin_access = None
            panel._admin_module_ids.clear()
            panel._catalog.reset_for_account_change()
        panel._log("[SETTINGS] Đã lưu tài khoản")
        return {
            "ok": True,
            "code": "ACCOUNT_SAVED",
            "message": "Đã lưu tài khoản.",
            "user_id": user_id,
            "has_credentials": True,
            "credential_state": self._credential_state(),
            **self._session_status(),
            **panel._division_state(),
            **panel._admin_state(),
        }

    # -- automation --------------------------------------------------------
    def login(self) -> dict:
        panel = self._panel
        def action() -> dict:
            account = self._account()
            # Người dùng vừa chủ động bấm đăng nhập: cho phép thử lại đúng bộ
            # credential mà lần trước WFX từ chối (họ có thể đã sửa mật khẩu).
            panel._rejected_credential = None
            result = self._login_run(
                account["user_id"],
                account["password"],
            )
            return panel._with_admin_access(result)

        return panel._run("login", action)

    def check_session(self) -> dict:
        panel = self._panel
        return panel._run(
            "check_session",
            lambda: panel._with_admin_access(
                panel._login.check_session(panel._log)
            ),
        )

    def should_maintain_session(self) -> bool:
        """Chỉ keepalive sau khi app đã xác nhận từng có phiên đăng nhập."""
        panel = self._panel
        if panel._session_active is not True:
            return False
        account = self._account()
        return bool(
            str(account.get("user_id") or "").strip()
            and str(account.get("password") or "")
        )

    def maintain_session(self) -> dict:
        """Kiểm tra nền; hết phiên thì tự login lại bằng credential đã lưu."""
        panel = self._panel

        def action() -> dict:
            buffered_logs: list[str] = []
            checked = panel._login.check_session(buffered_logs.append)
            if str(checked.get("code") or "") != "NOT_LOGGED_IN":
                return checked
            for line in buffered_logs:
                panel._log(line)
            restored = self._restore_expired_session()
            return restored or checked

        # Heartbeat thành công không phải tác vụ người dùng: không ghi jobs.json,
        # không thêm hai dòng RUN và không thay footer. Khi session thật sự lỗi,
        # _run_unlocked vẫn ghi một dòng cô đọng và _observe vẫn cập nhật state.
        return panel._run(
            "maintain_session",
            action,
            record_job=False,
            record_job_on_failure=True,
            announce=False,
        )

    def open_chrome(self) -> dict:
        panel = self._panel
        def action() -> dict:
            browser = panel._login.start_chrome(panel._log)
            if not browser.get("ok"):
                return browser
            account = self._account()
            panel._rejected_credential = None
            logged_in = self._login_run(
                account["user_id"],
                account["password"],
            )
            result = {
                **logged_in,
                "chrome_alive": True,
                "browser_available": True,
                "browser_name": browser.get("browser_name"),
                "message": (
                    "Đã mở trình duyệt và đăng nhập WFX."
                    if logged_in.get("ok")
                    else logged_in.get("message")
                ),
            }
            return panel._with_admin_access(result)

        return panel._run("open_chrome", action)

    def _login_run(self, user_id: str, password: str) -> dict:
        """Gọi login module kèm chủ phiên hiện tại nếu module hỗ trợ.

        Các login module cũ/giả lập trong test không có tham số
        ``session_owner``; kiểm tra chữ ký thay vì bắt TypeError để không
        nuốt nhầm lỗi thật phát sinh bên trong flow đăng nhập.
        """
        panel = self._panel
        kwargs: dict[str, Any] = {}
        try:
            parameters = inspect.signature(panel._login.run).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "session_owner" in parameters:
            kwargs["session_owner"] = panel._session_user_id
        return panel._login.run(
            user_id,
            password,
            panel._login.COMPANY_ID,
            panel._log,
            **kwargs,
        )

    def _remember_session_user(self, user_id: str | None) -> None:
        panel = self._panel
        value = str(user_id or "").strip() or None
        if value == panel._session_user_id:
            return
        panel._session_user_id = value
        try:
            panel._prefs.save_prefs(
                base_dir=panel._base_dir,
                session_user_id=value or "",
            )
        except TypeError:
            # prefs module cũ chưa biết khóa này; trạng thái trong bộ nhớ vẫn
            # đủ để bảo vệ trong phiên chạy hiện tại.
            pass

    @staticmethod
    def _credential_fingerprint(user_id: str, password: str) -> str:
        return hashlib.sha256(
            f"{user_id.strip().casefold()}\x00{password}".encode()
        ).hexdigest()

    def _credential_state(self) -> str:
        panel = self._panel
        reader = getattr(panel._prefs, "credential_status", None)
        if not callable(reader):
            return "ok" if self._account()["password"].strip() else "empty"
        try:
            return str(reader(base_dir=panel._base_dir))
        except OSError:
            return "empty"

    def _restore_expired_session(self) -> dict | None:
        """Đăng nhập lại bằng credential đã lưu; ``None`` nếu chưa cấu hình."""
        panel = self._panel
        account = self._account()
        user_id = str(account.get("user_id") or "").strip()
        password = str(account.get("password") or "")
        if not user_id or not password:
            return None
        # WFX khóa tài khoản sau vài lần sai liên tiếp. Một bộ credential đã
        # bị từ chối thì mọi cú bấm tiếp theo của người dùng không được biến
        # thành một lần nhập sai nữa — chờ tới khi họ lưu credential khác.
        fingerprint = self._credential_fingerprint(user_id, password)
        if panel._rejected_credential == fingerprint:
            panel._log(
                "[SESSION] Bỏ qua tự đăng nhập lại: WFX đã từ chối đúng tài "
                "khoản/mật khẩu này. Hãy cập nhật lại trong Cài đặt."
            )
            return {
                "ok": False,
                "code": "LOGIN_FAILED",
                "message": (
                    "WFX đã từ chối tài khoản đang lưu. Mở Cài đặt và nhập "
                    "lại mật khẩu WFX trước khi chạy tiếp."
                ),
            }
        panel._log("[SESSION] Phiên WFX đã hết hạn; đang tự đăng nhập lại...")
        restored = self._login_run(user_id, password)
        if not isinstance(restored, dict) or not restored.get("ok"):
            if (
                isinstance(restored, dict)
                and str(restored.get("code") or "") == "LOGIN_FAILED"
            ):
                panel._rejected_credential = fingerprint
            return restored if isinstance(restored, dict) else {
                "ok": False,
                "code": "LOGIN_FAILED",
                "message": "Kết quả tự đăng nhập lại không hợp lệ.",
            }

        panel._rejected_credential = None
        panel._session_active = True
        panel._last_login_at = time.strftime("%H:%M:%S")
        panel._admin_access = None
        panel._admin_module_ids.clear()
        self._remember_session_user(restored.get("session_user_id") or user_id)
        panel._catalog.reset_context()
        if restored.get("current_division") is not None:
            panel._current_division = str(restored["current_division"])
            panel._division_label = str(restored.get("division_label") or "")
            panel._division_name = str(restored.get("division_name") or "")
        panel._log("[SESSION] Đã tự đăng nhập lại; tiếp tục tác vụ hiện tại.")
        return {
            **restored,
            "code": "SESSION_RESTORED",
            "message": "Đã tự đăng nhập lại WFX.",
        }

    def _run_action_with_auto_relogin(
        self,
        method_name: str,
        action: Callable[[], dict],
    ) -> dict:
        """Khôi phục Chrome/phiên rồi retry toàn bộ action đúng một lần."""
        panel = self._panel
        result = action()
        if (
            method_name in AUTO_RELOGIN_EXCLUDED_METHODS
            or not isinstance(result, dict)
        ):
            return result
        code = str(result.get("code") or "")
        if code == "CHROME_CLOSED":
            panel._log(
                "[BROWSER] Trình duyệt làm việc đã đóng; đang tự mở lại..."
            )
            opened = panel._login.start_chrome(panel._log)
            if not isinstance(opened, dict) or not opened.get("ok"):
                return opened if isinstance(opened, dict) else {
                    "ok": False,
                    "code": "CHROME_OPEN_FAILED",
                    "message": "Kết quả mở lại trình duyệt không hợp lệ.",
                    "chrome_alive": False,
                }
            restored = self._restore_expired_session()
            if restored is None:
                return {
                    "ok": False,
                    "code": "MISSING_CREDENTIALS",
                    "message": (
                        "Đã mở lại trình duyệt. Hãy lưu tài khoản WFX để ứng dụng "
                        "có thể tự đăng nhập và tiếp tục tác vụ."
                    ),
                    "chrome_alive": True,
                    "browser_available": True,
                    "browser_name": opened.get("browser_name"),
                }
            if not restored.get("ok"):
                return {
                    **restored,
                    "chrome_alive": True,
                    "browser_available": True,
                    "browser_name": opened.get("browser_name"),
                }
            panel._log(
                "[BROWSER] Đã mở lại trình duyệt và khôi phục phiên; "
                "tiếp tục tác vụ hiện tại."
            )
            return action()
        if code != "NOT_LOGGED_IN":
            return result
        restored = self._restore_expired_session()
        if restored is None:
            return result
        if not restored.get("ok"):
            return restored
        return action()

    def _session_status(self) -> dict:
        """Trạng thái phiên đã quan sát, không thực hiện thêm I/O tới Chrome."""
        panel = self._panel
        return {
            "session_active": panel._session_active,
            "last_login_at": panel._last_login_at,
        }

    def _telemetry_account_context(self) -> dict:
        panel = self._panel
        account = self._account()
        return {
            "user_id": str(account.get("user_id") or "").strip(),
            "company_id": str(
                getattr(panel._login, "COMPANY_ID", "") or ""
            ).strip(),
            "division_key": panel._current_division or "",
            "division_label": panel._division_label or "",
            "division_name": panel._division_name or "",
        }

    def _account(self) -> dict:
        panel = self._panel
        return panel._prefs.load_account(base_dir=panel._base_dir)

    def shutdown(self, close_browser: bool = False) -> None:
        panel = self._panel
        if close_browser:
            closer = getattr(panel._login, "close_chrome", None)
            if callable(closer):
                # Nếu user thoát giữa flow, dừng ở checkpoint rồi đóng Chrome
                # trên chính automation worker để không tạo race CDP.
                AUTOMATION_RUNTIME.request_cancel()
                try:
                    AUTOMATION_RUNTIME.execute(lambda: closer(panel._log))
                except Exception as exc:
                    panel._log(
                        "Không đóng được trình duyệt làm việc khi thoát: "
                        f"{type(exc).__name__}: {exc}"
                    )
        automation_runtime.shutdown()
