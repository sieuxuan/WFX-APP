"""Điều phối Reports: nhớ tham số đã chọn, xuất Excel và chạy báo cáo màu."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel.stores.report_parameters import ReportParameterStore

_COLOR_REPORT_IDS = frozenset(
    {"color_combination_production", "color_combination_po_wise"}
)
_USER_SAVED_MARKER = "__user_saved_parameters__"


class ReportsController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        self._parameter_store = ReportParameterStore(
            panel._base_dir / "report-parameters.json"
        )

    def load_color_po_report_options(
        self, values: Mapping[str, Any] | None = None
    ) -> dict:
        panel = self._panel
        loader = getattr(panel._login, "load_color_po_report_options", None)
        if not callable(loader):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Chưa hỗ trợ ColorCombination PO Wise.",
            }
        if values is not None and not isinstance(values, Mapping):
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Tham số PO Wise không hợp lệ.",
            }
        selected = {
            key: str(value)[:500]
            for key, value in dict(values or {}).items()
            if key in {"division", "buyer", "season"}
            and isinstance(value, (str, int, float))
            and str(value)
        }
        if not values:
            saved = self._saved_report_parameters("color_combination_po_wise")
            selected = {
                key: str(saved[key])
                for key in ("division", "buyer", "season")
                if saved.get(key)
            }
        saved_parameters = (
            self._saved_report_parameters("color_combination_po_wise")
            if not values
            else None
        )

        def action():
            result = loader(selected, panel._log)
            return (
                {**result, "saved_parameters": saved_parameters}
                if saved_parameters is not None and result.get("ok")
                else result
            )

        return panel._run(
            "load_color_po_report_options",
            action,
            {"module_id": "reports", "report_id": "color_combination_po_wise"},
        )

    def run_color_po_report_batch(
        self,
        selection: Mapping[str, Any] | None = None,
        po_values: list[str] | None = None,
        output_dir: str = "",
    ) -> dict:
        panel = self._panel
        runner = getattr(panel._login, "run_color_po_report_batch", None)
        if not callable(runner):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Chưa hỗ trợ ColorCombination PO Wise.",
            }
        if (selection is not None and not isinstance(selection, Mapping)) or (
            po_values is not None and not isinstance(po_values, (list, tuple))
        ):
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Lựa chọn PO Wise không hợp lệ.",
            }
        values = dict(selection or {})
        selected = {
            key: str(value)[:500]
            for key, value in values.items()
            if key in {"division", "buyer", "season"}
            and isinstance(value, (str, int, float))
        }
        pos = list(
            dict.fromkeys(
                str(value).strip()[:200]
                for value in (po_values or [])[:500]
                if str(value).strip()
            )
        )
        retries = values.get("retry_items")
        if retries is not None:
            if (
                not isinstance(retries, list)
                or len(retries) > 5000
                or any(
                    not isinstance(item, Mapping)
                    or item.get("po_value") not in pos
                    or any(not isinstance(value, str) for value in item.values())
                    or (
                        item.get("style_code_value") and not item.get("style_ref_value")
                    )
                    for item in retries
                )
            ):
                return {
                    "ok": False,
                    "code": "REPORT_PARAMETERS_INVALID",
                    "message": "Danh sách mục PO cần chạy lại không hợp lệ.",
                }
            selected["retry_items"] = [
                {
                    key: str(item.get(key) or "")[:200]
                    for key in ("po_value", "style_ref_value", "style_code_value")
                }
                for item in retries
            ]
        method = "run_color_po_report_batch"
        return panel._run(
            method,
            lambda: runner(
                selected,
                pos,
                str(output_dir or ""),
                panel._log,
                progress=panel._progress_for(method),
            ),
            {
                "module_id": "reports",
                "report_id": "color_combination_po_wise",
                "po_count": len(pos),
            },
        )

    def report_catalog(self) -> dict:
        panel = self._panel
        catalog = getattr(panel._login, "report_catalog", None)
        reports = catalog() if callable(catalog) else []
        return {"ok": True, "code": "REPORT_CATALOG_READY", "reports": reports}

    def _saved_report_parameters(self, report_id: str) -> dict[str, Any]:
        panel = self._panel
        account_key = str(panel._account().get("user_id") or "").strip().casefold()
        saved = self._parameter_store.load(account_key, str(report_id))
        # Các bản cũ tự lưu sau mỗi lượt chạy. Chỉ khôi phục giá trị mà user
        # chủ động lưu; không dùng lựa chọn chạy thử làm mặc định.
        if (
            report_id in _COLOR_REPORT_IDS
            and saved.pop(_USER_SAVED_MARKER, False) is not True
        ):
            return {}
        return saved

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
            stored_values = dict(values or {})
            if cleaned_id in _COLOR_REPORT_IDS:
                stored_values[_USER_SAVED_MARKER] = True
            clean_values = self._parameter_store.save(
                account_key,
                cleaned_id,
                stored_values,
            )
            if cleaned_id in _COLOR_REPORT_IDS:
                clean_values.pop(_USER_SAVED_MARKER, None)
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
        saved_parameters = (
            self._saved_report_parameters("color_combination_production")
            if not values
            else None
        )

        def action():
            result = loader(safe_values, panel._log)
            return (
                {**result, "saved_parameters": saved_parameters}
                if saved_parameters is not None and result.get("ok")
                else result
            )

        return panel._run(
            "load_color_report_options",
            action,
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
        if safe_selection.get("export_mode", "style") not in {"style", "oc_num"}:
            return {
                "ok": False,
                "code": "REPORT_PARAMETERS_INVALID",
                "message": "Hãy chọn xuất theo Style hoặc OCNum.",
            }
        retry_ocnums = dict(selection or {}).get("retry_ocnums")
        if retry_ocnums is not None:
            if not isinstance(retry_ocnums, Mapping) or any(
                not isinstance(labels, list)
                or not labels
                or any(
                    not isinstance(label, str) or not label.strip() for label in labels
                )
                for labels in retry_ocnums.values()
            ):
                return {
                    "ok": False,
                    "code": "REPORT_PARAMETERS_INVALID",
                    "message": "Danh sách OCNum cần chạy lại không hợp lệ.",
                }
            safe_selection["retry_ocnums"] = {
                str(key)[:200]: [label[:200] for label in labels[:500]]
                for key, labels in list(retry_ocnums.items())[:500]
                if str(key) in safe_refs
            }
        method = "run_color_report_batch"
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
