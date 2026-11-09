"""Bridge for exporting and filling the open Blanket GMPO."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from wfx_panel.automation.gmpo import run_gmpo
from wfx_panel.workbooks.gmpo import read_changes, write_workbook

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI


class GMPOController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel

    def export(self, file_path: str) -> dict:
        target = Path(file_path)
        if target.suffix.casefold() != ".xlsx":
            return {
                "ok": False,
                "code": "GMPO_FILE_INVALID",
                "message": "Chọn nơi lưu file GMPO .xlsx.",
            }

        def action() -> dict:
            result = run_gmpo(self._panel._log)
            if not result["ok"]:
                return result
            snapshot = result["snapshot"]
            try:
                write_workbook(target, snapshot)
            except (OSError, ValueError) as error:
                self._panel._log(f"[GMPO EXCEL] {type(error).__name__}: {error}")
                return {
                    "ok": False,
                    "code": "GMPO_EXPORT_FAILED",
                    "message": "Không xuất được Excel GMPO. Hãy đóng file Excel đích và kiểm tra thư mục lưu.",
                }
            return {
                "ok": True,
                "code": "GMPO_EXPORTED",
                "message": f"Đã xuất {len(snapshot['rows'])} dòng GMPO vào {target.name}.",
                "export_path": str(target),
            }

        return self._panel._run("export_gmpo", action, {"module_id": "gmpo"})

    def import_quantities(self, file_path: str) -> dict:
        try:
            scope, changes = read_changes(Path(file_path))
        except ValueError as error:
            return {"ok": False, "code": "GMPO_FILE_INVALID", "message": str(error)}
        if not changes:
            return {
                "ok": True,
                "code": "GMPO_IMPORT_READY",
                "message": "File Excel không có thay đổi Order Qty.",
            }
        return self._panel._run(
            "import_gmpo",
            lambda: run_gmpo(self._panel._log, scope=scope, changes=changes),
            {"module_id": "gmpo"},
        )
