"""Ghi tuỳ chọn người dùng xuống prefs và áp ngay xuống lớp hệ điều hành.

Mỗi setter ghi prefs rồi gọi applier tương ứng của panel (hotkey, always on
top, autostart…). Setter phải trả về trạng thái THẬT sau khi áp: nếu áp
thất bại thì prefs không được nói dối là đã bật."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import autostart, constants, reference_sync, updater
from wfx_panel import hotkey as hotkey_spec
from wfx_panel.coercion import boolean

THEME_CHOICES = frozenset({"light", "dark", "system"})


class SettingsController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    def set_theme(self, theme: str) -> dict:
        panel = self._panel
        # load_prefs chuẩn hóa giá trị lạ về "light". Nếu API cũng im lặng
        # chấp nhận thì UI báo "Đã đổi giao diện" trong khi giao diện nhảy về
        # Sáng — người dùng không hiểu vì sao lựa chọn của họ bị bỏ.
        wanted = str(theme or "").strip().casefold()
        if wanted not in THEME_CHOICES:
            return {
                "ok": False,
                "code": "THEME_INVALID",
                "message": "Giao diện chỉ nhận Sáng, Tối hoặc Tự động.",
                "theme": panel._prefs.load_prefs(base_dir=panel._base_dir)["theme"],
            }
        saved = panel._prefs.save_prefs(base_dir=panel._base_dir, theme=wanted)
        return {"ok": True, "code": "THEME_SAVED", "message": "Đã đổi giao diện", "theme": saved["theme"]}

    def set_sale_asn_stages(self, stages: list[str] | None = None) -> dict:
        """Nhớ các bước Sale ASN user đã chọn giữa các phiên chạy."""
        panel = self._panel
        if stages is not None and not isinstance(stages, (list, tuple)):
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_STEPS_INVALID",
                "message": "Danh sách bước Sale ASN không hợp lệ.",
            }
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            sale_asn_stages=[
                str(stage or "").strip()
                for stage in (stages or ())
                if isinstance(stage, str)
            ],
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": "Đã lưu các bước Sale ASN.",
            "sale_asn_stages": saved["sale_asn_stages"],
        }

    def set_sale_asn_po_search_fields(
        self,
        fields: list[str] | None = None,
    ) -> dict:
        """Nhớ các tiêu chí Add PO và luôn trả danh sách đã chuẩn hóa."""
        panel = self._panel

        if fields is not None and not isinstance(fields, (list, tuple)):
            return {
                "ok": False,
                "code": "SALE_ASN_PO_SEARCH_FIELDS_INVALID",
                "message": "Danh sách tiêu chí tìm PO không hợp lệ.",
            }

        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            sale_asn_po_search_fields=[
                str(field or "").strip()
                for field in (fields or ())
                if isinstance(field, str)
            ],
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": "Đã lưu tiêu chí tìm PO cho Sale ASN.",
            "sale_asn_po_search_fields": saved[
                "sale_asn_po_search_fields"
            ],
        }

    def set_excel_file_after_download(self, enabled: bool) -> dict:
        panel = self._panel
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            open_excel_file_after_download=boolean(enabled),
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": "Đã lưu cách mở file Excel sau khi tải.",
            "open_excel_file_after_download": saved[
                "open_excel_file_after_download"
            ],
        }

    def set_module_favorite(self, module_id: str, favorite: bool) -> dict:
        panel = self._panel
        module_id = str(module_id or "").strip()
        if module_id not in constants.MODULE_BY_ID:
            return {
                "ok": False,
                "code": "MODULE_UNKNOWN",
                "message": "Không tìm thấy module để ghim.",
            }
        preferences = panel._prefs.load_prefs(base_dir=panel._base_dir)
        ids = list(preferences["favorite_module_ids"])
        wanted = boolean(favorite)
        if wanted and module_id not in ids:
            ids.append(module_id)
        elif not wanted:
            ids = [value for value in ids if value != module_id]
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            favorite_module_ids=ids,
        )
        module_name = constants.MODULE_BY_ID[module_id]["name"]
        return {
            "ok": True,
            "code": "MODULE_FAVORITE_SAVED",
            "message": (
                f"Đã ghim {module_name} lên đầu."
                if wanted
                else f"Đã bỏ ghim {module_name}."
            ),
            "favorite_module_ids": saved["favorite_module_ids"],
        }

    def set_hotkey(self, spec: str | dict) -> dict:
        panel = self._panel
        try:
            normalized = (
                hotkey_spec.from_event(spec)
                if isinstance(spec, dict)
                else hotkey_spec.normalize(spec)
            )
        except (ValueError, TypeError, AttributeError) as error:
            return {
                "ok": False,
                "code": "HOTKEY_INVALID",
                "message": str(error),
            }

        previous = panel._prefs.load_prefs(base_dir=panel._base_dir)["hotkey"]
        if panel._hotkey_applier is not None:
            failure = panel._hotkey_applier(normalized)
            if failure:
                panel._hotkey_applier(previous)
                return {
                    "ok": False,
                    "code": "HOTKEY_REGISTER_FAILED",
                    "message": failure,
                    "hotkey": previous,
                    "hotkey_label": hotkey_spec.format_label(previous),
                }

        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir, hotkey=normalized
        )
        panel._log(f"[SETTINGS] Đã đổi hotkey sang {saved['hotkey_label']}")
        return {
            "ok": True,
            "code": "HOTKEY_SAVED",
            "message": f"Đã đổi hotkey sang {saved['hotkey_label']}.",
            "hotkey": saved["hotkey"],
            "hotkey_label": saved["hotkey_label"],
        }

    def set_autostart(self, enabled: bool) -> dict:
        panel = self._panel
        wanted = boolean(enabled)
        actual = autostart.sync(wanted)
        panel._prefs.save_prefs(
            base_dir=panel._base_dir, autostart=actual
        )
        if actual != wanted:
            return {
                "ok": False,
                "code": "AUTOSTART_FAILED",
                "message": "Không ghi được thiết lập khởi động cùng Windows.",
                "autostart": actual,
            }
        return {
            "ok": True,
            "code": "AUTOSTART_SAVED",
            "message": (
                "Đã bật khởi động cùng Windows."
                if actual
                else "Đã tắt khởi động cùng Windows."
            ),
            "autostart": actual,
        }

    def set_start_hidden(self, enabled: bool) -> dict:
        panel = self._panel
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir, start_hidden=boolean(enabled)
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Lần mở tới sẽ ẩn trong tray."
                if saved["start_hidden"]
                else "Lần mở tới sẽ hiện panel."
            ),
            "start_hidden": saved["start_hidden"],
        }

    def set_toast_enabled(self, enabled: bool) -> dict:
        panel = self._panel
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir, toast_enabled=boolean(enabled)
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Đã bật thông báo."
                if saved["toast_enabled"]
                else "Đã tắt thông báo."
            ),
            "toast_enabled": saved["toast_enabled"],
        }

    def set_focus_chrome_on_module(self, enabled: bool) -> dict:
        panel = self._panel
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            focus_chrome_on_module=boolean(enabled),
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Chrome sẽ tự hiện khi chạy module."
                if saved["focus_chrome_on_module"]
                else "Đã tắt tự động đưa Chrome lên trước."
            ),
            "focus_chrome_on_module": saved[
                "focus_chrome_on_module"
            ],
        }

    def set_always_on_top(self, enabled: bool) -> dict:
        panel = self._panel
        value = boolean(enabled)
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir, always_on_top=value
        )
        if panel._on_top_applier is not None:
            panel._on_top_applier(saved["always_on_top"])
        return {
            "ok": True,
            "code": "WINDOW_PREF_SAVED",
            "message": (
                "Panel sẽ luôn nằm trên cùng."
                if saved["always_on_top"]
                else "Panel không còn bị ghim trên cùng."
            ),
            "always_on_top": saved["always_on_top"],
        }

    def set_update_channel(self, channel: str) -> dict:
        panel = self._panel
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir, update_channel="stable"
        )
        return {
            "ok": True,
            "code": "UPDATE_CHANNEL_SAVED",
            "message": "Ứng dụng luôn sử dụng kênh Stable.",
            "update_channel": saved["update_channel"],
        }

    def save_sync_admin_key(self, admin_key: str) -> dict:
        panel = self._panel
        if panel._admin_access is not True:
            return {
                "ok": False,
                "code": "ADMIN_ACCESS_DENIED",
                "message": "Tài khoản WFX chưa có quyền quản trị.",
                **reference_sync.status(panel._base_dir),
            }
        try:
            configured = panel._prefs.save_sync_admin_key(
                str(admin_key or ""),
                base_dir=panel._base_dir,
            )
        except (OSError, RuntimeError) as error:
            return {
                "ok": False,
                "code": "REFERENCE_ADMIN_KEY_SAVE_FAILED",
                "message": str(error),
                **reference_sync.status(panel._base_dir),
            }
        return {
            "ok": True,
            "code": "REFERENCE_ADMIN_KEY_SAVED",
            "message": (
                "Đã lưu Admin key an toàn trên máy này."
                if configured
                else "Đã xóa Admin key trên máy này."
            ),
            **reference_sync.status(panel._base_dir),
        }

    def check_for_updates(self) -> dict:
        return updater.check_for_updates(channel="stable")

    def install_update(self) -> dict:
        panel = self._panel
        state = updater.check_for_updates(channel="stable")
        if not state.get("can_update"):
            return state
        if panel._update_applier is None:
            return {
                **state,
                "ok": False,
                "code": "UPDATE_APPLIER_MISSING",
                "message": "Bộ cài cập nhật chưa sẵn sàng.",
                "can_update": False,
            }
        failure = panel._update_applier(state)
        if failure:
            return {
                **state,
                "ok": False,
                "code": "UPDATE_SCHEDULE_FAILED",
                "message": failure,
                "can_update": False,
            }
        return {
            **state,
            "ok": True,
            "code": "UPDATE_SCHEDULED",
            "message": (
                "Đang cài bản mới. Ứng dụng sẽ đóng và tự mở lại khi hoàn tất."
            ),
            "can_update": False,
        }

    def publish_reference_data(self) -> dict:
        panel = self._panel
        if panel._admin_access is not True:
            return {
                "ok": False,
                "code": "ADMIN_ACCESS_DENIED",
                "message": "Tài khoản WFX chưa có quyền quản trị.",
                **reference_sync.status(panel._base_dir),
            }
        return panel._run(
            "publish_reference_data",
            lambda: reference_sync.publish_current(
                panel._base_dir,
                panel._log,
            ),
        )

    def sync_reference_data(self, force: bool = True) -> dict:
        """Tải snapshot tham chiếu; chạy NGOÀI `_run()` như sync_article_library.

        Đây là một lời gọi HTTP thuần, không đụng Playwright/Chrome, nhưng
        `_run()` giữ `_run_lock` và chiếm luôn automation worker suốt cả
        `REQUEST_TIMEOUT_SECONDS`. Hệ quả khi bọc nó vào `_run()`:

        - vòng lặp nền mỗi giờ khóa mọi thao tác của người dùng tới 60 giây và
          UI chỉ trả `ACTION_IN_PROGRESS` dù người dùng không chạy gì;
        - ngược lại lúc khởi động, auto-login đang giữ lock nên chính lượt sync
          bị bỏ qua và không thử lại suốt một tiếng;
        - mỗi lượt còn đẩy một dòng nền vào `job_history`, làm loãng trần 200
          dòng dành cho job thật.

        Không cần khóa riêng: hai lượt sync chồng nhau chỉ tải trùng, vì cache
        được ghi bằng `write_json_atomic` và nội dung là idempotent.
        """
        panel = self._panel
        return reference_sync.sync_latest(
            panel._base_dir,
            panel._log,
            force=boolean(force, True),
        )
