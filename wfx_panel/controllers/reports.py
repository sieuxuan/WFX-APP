"""Điều phối Reports: nhớ tham số đã chọn, xuất Excel và chạy báo cáo màu."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel.stores.report_parameters import ReportParameterStore


class ReportsController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        self._parameter_store = ReportParameterStore(
            panel._base_dir / "report-parameters.json"
        )

    def report_catalog(self) -> dict:
        panel = self._panel
        catalog = getattr(panel._login, "report_catalog", None)
        reports = catalog() if callable(catalog) else []
        return {"ok": True, "code": "REPORT_CATALOG_READY", "reports": reports}

    def _saved_report_parameters(self, report_id: str) -> dict[str, Any]:
        panel = self._panel
        account_key = str(panel._account().get("user_id") or "").strip().casefold()
        return self._parameter_store.load(account_key, str(report_id))

    def load_report_parameters(self, report_id: str) -> dict:
        panel = self._panel
        loader = getattr(panel._login, "load_report_parameters", None)
        if not callable(loader):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Phiên bản tự động hóa chưa hỗ trợ Reports.",
            }
        cleaned_id = str(report_id or "")

        def action() -> dict:
            result = loader(cleaned_id, panel._log)
            if result.get("ok"):
                return {
                    **result,
                    "saved_parameters": self._saved_report_parameters(cleaned_id),
                }
            return result

        return panel._run(
            "load_report_parameters",
            action,
            {"module_id": "reports", "report_id": str(report_id or "")},
        )

    def save_report_parameters(
        self, report_id: str, values: Mapping[str, Any] | None = None
    ) -> dict:
        panel = self._panel
        cleaned_id = str(report_id or "").strip()
        allowed = {
            str(item.get("id") or "")
            for item in (getattr(panel._login, "report_catalog", lambda: [])() or [])
            if isinstance(item, Mapping)
        }
        if not cleaned_id or cleaned_id not in allowed:
            return {
                "ok": False,
                "code": "REPORT_UNKNOWN",
                "message": "Báo cáo không được hỗ trợ.",
            }
        account_key = str(panel._account().get("user_id") or "").strip().casefold()
        if not account_key:
            return {
                "ok": False,
                "code": "REPORT_SAVE_ACCOUNT_REQUIRED",
                "message": "Hãy đăng nhập WFX trước khi lưu tham số báo cáo.",
            }
        if values is not None and not isinstance(values, Mapping):
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Tham số báo cáo phải là một object hợp lệ.",
            }
        try:
            clean_values = self._parameter_store.save(
                account_key,
                cleaned_id,
                dict(values or {}),
            )
        except OSError as error:
            return {
                "ok": False,
                "code": "REPORT_SAVE_FAILED",
                "message": f"Không lưu được tham số báo cáo: {type(error).__name__}",
            }
        return {
            "ok": True,
            "code": "REPORT_PARAMETERS_SAVED",
            "message": "Đã lưu tham số báo cáo để dùng lần sau.",
            "report_id": cleaned_id,
            "saved_parameters": clean_values,
        }

    def export_report_excel(
        self, report_id: str, values: Mapping[str, Any] | None = None
    ) -> dict:
        panel = self._panel
        exporter = getattr(panel._login, "export_report_excel", None)
        if not callable(exporter):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Phiên bản tự động hóa chưa hỗ trợ Reports.",
            }
        if values is not None and not isinstance(values, Mapping):
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Tham số báo cáo phải là một object hợp lệ.",
            }
        safe_values = dict(values or {})
        return panel._run(
            "export_report_excel",
            lambda: exporter(str(report_id or ""), safe_values, panel._log),
            {"module_id": "reports", "report_id": str(report_id or "")},
        )

    def load_color_report_options(
        self, values: Mapping[str, Any] | None = None
    ) -> dict:
        panel = self._panel
        loader = getattr(panel._login, "load_color_report_options", None)
        if not callable(loader):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Phiên bản tự động hóa chưa hỗ trợ báo cáo này.",
            }
        if values is not None and not isinstance(values, Mapping):
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Tham số báo cáo phải là một object hợp lệ.",
            }
        safe_values = {
            str(key): str(value)[:500]
            for key, value in dict(values or {}).items()
            if isinstance(value, (str, int, float))
        }
        if not safe_values:
            saved = self._saved_report_parameters("color_combination_production")
            safe_values = {
                key: str(saved.get(key) or "")
                for key in ("division", "buyer", "season")
                if str(saved.get(key) or "")
            }
        return panel._run(
            "load_color_report_options",
            lambda: loader(safe_values, panel._log),
            {"module_id": "reports", "report_id": "color_combination_production"},
        )

    def run_color_report_batch(
        self,
        selection: Mapping[str, Any] | None = None,
        style_refs: list[str] | None = None,
        output_dir: str = "",
    ) -> dict:
        panel = self._panel
        runner = getattr(panel._login, "run_color_report_batch", None)
        if not callable(runner):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Phiên bản tự động hóa chưa hỗ trợ báo cáo này.",
            }
        if selection is not None and not isinstance(selection, Mapping):
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Lựa chọn báo cáo phải là một object hợp lệ.",
            }
        if style_refs is not None and not isinstance(style_refs, (list, tuple)):
            return {
                "ok": False,
                "code": "REPORT_STYLE_REFS_INVALID",
                "message": "Danh sách Style của báo cáo không hợp lệ.",
            }
        safe_selection = {
            str(key): str(value)[:500]
            for key, value in dict(selection or {}).items()
            if isinstance(value, (str, int, float))
        }
        safe_refs = [
            str(item)[:200]
            for item in list(style_refs or ())[:500]
            if str(item).strip()
        ]
        method = "run_color_report_batch"
        self.save_report_parameters("color_combination_production", safe_selection)
        return panel._run(
            method,
            lambda: runner(
                safe_selection,
                safe_refs,
                str(output_dir or ""),
                panel._log,
                progress=panel._progress_for(method),
            ),
            {"module_id": "reports", "style_count": len(safe_refs)},
        )
