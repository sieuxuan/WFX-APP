"""Cây thư mục Catalog: quét, cache và ghi nhớ vị trí mặc định.

Cache khoá theo tài khoản: đổi User ID là quyền đọc cây khác hẳn, nên phải
bỏ cache cũ chứ không dùng lại. Folder mặc định đã biến mất hoặc mất quyền
thì chuyển về Master và nói rõ, không được im lặng thất bại."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.controllers.catalog import CatalogController

from wfx_panel import constants


class CatalogFolderController:
    def __init__(self, catalog: CatalogController) -> None:
        self._catalog = catalog
        self._panel = catalog._panel
        # Cache cây folder theo Category; bỏ khi đổi tài khoản.
        self.cache: dict[str, list[dict]] = {}

    # -- helpers -----------------------------------------------------------
    def default_folder_for_account(
        self,
        preferences: Mapping | None = None,
    ) -> dict | None:
        panel = self._panel
        if preferences is None:
            preferences = panel._prefs.load_prefs(base_dir=panel._base_dir)
        folder = preferences["catalog_default_folder"]
        if not folder:
            return None
        user_id = str(panel._account().get("user_id") or "").strip()
        owner = str(folder.get("user_id") or "").strip()
        if not user_id or owner.casefold() != user_id.casefold():
            return None
        return folder

    def _master_folder(self, category_name: str) -> dict:
        return {
            "category_name": category_name,
            "category_value": constants.CATEGORIES.get(category_name, ""),
            "user_id": str(self._panel._account().get("user_id") or "").strip(),
            "node_id": "",
            "node_code": "Master",
            "name": "Master",
            "path": ["Master"],
            "path_label": "Master",
            "kind": "master",
            "depth": 0,
        }

    def _cached_folders(self, category_name: str) -> list[dict] | None:
        cached = self.cache.get(category_name)
        if cached:
            return cached
        panel = self._panel
        account = panel._account()
        loader = getattr(panel._prefs, "load_catalog_folder_cache", None)
        if not callable(loader):
            return None
        persisted = loader(
            str(account.get("user_id") or ""),
            category_name,
            base_dir=panel._base_dir,
        )
        if persisted:
            self.cache[category_name] = persisted
            return persisted
        return None

    # -- workflows ---------------------------------------------------------
    def scan_folders(self, category_name: str, force: bool = False) -> dict:
        """Quét cây folder user được quyền xem, không mở Master."""
        catalog = self._catalog
        panel = self._panel
        if category_name != "Apparel":
            return {
                "ok": False,
                "code": "CATALOG_DEFAULT_APPAREL_ONLY",
                "message": "Vị trí mặc định chỉ áp dụng cho Apparel.",
            }
        if not force:
            cached = self._cached_folders(category_name)
            if cached:
                return {
                    "ok": True,
                    "code": "CATALOG_FOLDERS_CACHED",
                    "message": "Đã tải cây Catalog đã lưu.",
                    "category": category_name,
                    "value": constants.CATEGORIES[category_name],
                    "folders": cached,
                    "default_folder": self.default_folder_for_account(),
                    **panel._session_status(),
                    **panel._division_state(),
                }
        scan_user_id = str(panel._account().get("user_id") or "").strip()

        def action() -> dict:
            # Reset context CHỈ sau khi đã giành được run lock (bên trong _run).
            # Nếu đặt ở đầu method, một lần gọi bị từ chối ACTION_IN_PROGRESS vẫn
            # xóa mất Catalog đang chuẩn bị của workflow đang chạy.
            catalog.result = None
            catalog.active_article_destination = None
            catalog.prepared_category = None
            catalog.files_view.tokens.clear()
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            scanner = getattr(panel._login, "scan_catalog_folders", None)
            if not callable(scanner):
                return {
                    "ok": False,
                    "code": "CATALOG_FOLDER_SCAN_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ quét thư mục Catalog.",
                }
            return scanner(category_name, value, panel._log)

        result = panel._run(
            "scan_catalog_folders",
            action,
            {
                "category_name": category_name,
                "force": bool(force),
            },
        )
        if result.get("code") == "CATALOG_FOLDERS_SCANNED":
            current_user_id = str(panel._account().get("user_id") or "").strip()
            if scan_user_id.casefold() != current_user_id.casefold():
                return {
                    "ok": False,
                    "code": "CATALOG_SCAN_ACCOUNT_CHANGED",
                    "message": (
                        "Tài khoản đã đổi trong lúc tải Catalog. "
                        "Hãy mở Catalog lại."
                    ),
                    **panel._session_status(),
                    **panel._division_state(),
                }
            folders = [
                folder
                for folder in result.get("folders", [])
                if isinstance(folder, dict)
                and str(folder.get("node_id") or "").isdigit()
            ]
            self.cache[category_name] = folders
            saver = getattr(panel._prefs, "save_catalog_folder_cache", None)
            if callable(saver):
                try:
                    persisted = saver(
                        scan_user_id,
                        folders,
                        category_name,
                        base_dir=panel._base_dir,
                    )
                    if persisted:
                        folders = persisted
                        result["folders"] = folders
                        self.cache[category_name] = folders
                except OSError:
                    # Cache chỉ là tối ưu UX; scan thành công không được biến
                    # thành lỗi chỉ vì ổ đĩa tạm thời không ghi được.
                    pass
            saved = self.default_folder_for_account()
            if (
                saved
                and saved.get("category_name") == category_name
                and saved.get("node_id")
                and not any(
                    folder.get("node_id") == saved.get("node_id")
                    for folder in folders
                )
            ):
                master = self._master_folder(category_name)
                panel._prefs.save_prefs(
                    base_dir=panel._base_dir,
                    catalog_default_folder=master,
                )
                result["default_folder"] = master
                # `+=` trên key có thể vắng: automation chỉ bảo đảm ok/code,
                # còn `message` là tuỳ chọn. KeyError ở đây xảy ra NGOÀI _run
                # nên không có handler nào biến nó thành PANEL_ERROR.
                result["message"] = (
                    f"{str(result.get('message') or '').rstrip()} "
                    "Folder mặc định cũ không còn quyền truy cập; "
                    "đã chuyển về Master."
                ).strip()
            else:
                result["default_folder"] = saved
        return result

    def set_default_folder(self, category_name: str, node_id: str) -> dict:
        panel = self._panel
        if category_name != "Apparel":
            return {
                "ok": False,
                "code": "CATALOG_DEFAULT_APPAREL_ONLY",
                "message": "Vị trí mặc định chỉ áp dụng cho Apparel.",
            }
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {
                "ok": False,
                "code": "CATEGORY_UNKNOWN",
                "message": f"Category lạ: {category_name}",
            }
        node_id = str(node_id or "").strip()
        if not node_id:
            folder = self._master_folder(category_name)
        else:
            folder = next(
                (
                    item
                    for item in self.cache.get(category_name, [])
                    if str(item.get("node_id") or "") == node_id
                ),
                None,
            )
            if folder is None:
                return {
                    "ok": False,
                    "code": "CATALOG_FOLDER_NOT_SCANNED",
                    "message": "Hãy quét lại cây Catalog trước khi chọn folder.",
                }
            folder = {
                **folder,
                "category_name": category_name,
                "category_value": value,
                "user_id": str(panel._account().get("user_id") or "").strip(),
            }
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            catalog_default_folder=folder,
        )["catalog_default_folder"]
        panel._log(
            f"[SETTINGS] Folder Catalog mặc định: "
            f"{saved['path_label'] if saved else 'Master'}"
        )
        return {
            "ok": True,
            "code": "CATALOG_DEFAULT_FOLDER_SAVED",
            "message": (
                f"Đã đặt folder mặc định: {saved['path_label']}."
                if saved
                else "Đã đặt folder mặc định: Master."
            ),
            "default_folder": saved,
        }
