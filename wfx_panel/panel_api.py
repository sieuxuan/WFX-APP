from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from wfx_panel import (
    constants,
    job_history,
    log_bridge,
    module_controllers,
    status,
    telemetry,
)
from wfx_panel import prefs as prefs_default
from wfx_panel.automation.runtime import RUNTIME as AUTOMATION_RUNTIME
from wfx_panel.coercion import boolean
from wfx_panel.controllers import (
    AccessController,
    CatalogController,
    DirectoryController,
    FinanceController,
    InventoryController,
    JobsController,
    ModulesController,
    OCController,
    ReportsController,
    SaleASNController,
    SessionController,
    SettingsController,
)
from wfx_panel.run_engine import AutomationRunEngine
from wfx_panel.run_policy import (  # noqa: F401
    AUTO_RELOGIN_EXCLUDED_METHODS,
    CATALOG_CONTEXT_INVALIDATING_METHODS,
    DIAGNOSTIC_FAILURES,
    LOGIN_CODES,
    NON_REPORTABLE_FAILURES,
    SCREENSHOT_METHODS,
    SESSION_LOST,
    SESSION_OK,
)
from wfx_panel.stores import reference_sync
from wfx_panel.version import APP_VERSION, DISPLAY_VERSION


class PanelAPI:
    def __init__(self, login_module=None, prefs_module=None, base_dir: Path | None = None):
        if login_module is None:
            import login as login_module  # imported lazily so tests can inject a fake
        self._login = login_module
        self._prefs = prefs_module or prefs_default
        self._base_dir = base_dir or self._prefs.DATA_DIR
        self._logs: list[str] = []
        self._sink: Callable[[str], None] | None = None
        self._result_sink: Callable[[str, dict, float], None] | None = None
        self._progress_sink: Callable[[dict], None] | None = None
        self._hotkey_applier: Callable[[str], str | None] | None = None
        self._update_applier: Callable[[dict], str | None] | None = None
        self._on_top_applier: Callable[[bool], None] | None = None
        self._session_active: bool | None = None
        self._last_login_at: str | None = None
        # User ID mà app tin rằng đang sở hữu phiên Chrome hiện tại. Đọc trễ:
        # __init__ chạy trước khi UI kịp hiện, không được chạm đĩa ở đây.
        self._session_user_id_loaded = False
        self._session_user_id_value: str | None = None
        # Chặn vòng lặp tự đăng nhập lại bằng đúng bộ credential vừa bị WFX
        # từ chối: mỗi cú bấm của người dùng là một lần nhập sai nữa, đủ nhiều
        # là WFX khóa tài khoản.
        self._rejected_credential: str | None = None
        self._current_run_id: str | None = None
        self._admin_access: bool | None = None
        self._admin_module_ids: set[str] = set()
        self._current_division: str | None = None
        self._division_label: str | None = None
        self._division_name: str | None = None
        # Playwright/CDP không được chạy hai workflow song song trên cùng WFX
        # session. Trả về ngay thay vì xếp hàng khiến WebView trông bị treo.
        # RLock chứ không phải Lock: các thao tác Costing là composite gồm NHIỀU
        # _run liên tiếp (mở Costing rồi export/dry-run/apply). Với Lock thường,
        # cách duy nhất để chúng chạy được là nhả khóa giữa các bước — và đúng
        # khe hở đó cho phép flow khác đổi module/Division khiến bước sau thao
        # tác nhầm màn hình. run_composite() giữ khóa xuyên suốt, các _run lồng
        # bên trong tái nhập trên cùng thread.
        self._run_lock = threading.RLock()
        # Không dùng RLock.locked() cho is_action_running(): API đó chỉ có từ
        # Python 3.13 mà project khai báo requires-python >=3.11.
        self._run_depth = 0
        self._run_depth_lock = threading.Lock()
        # Toàn bộ state + logic Catalog (kết quả tìm, category đã chuẩn bị, cache
        # cây folder) sống trong controller riêng để bridge không phình to.
        self._catalog = CatalogController(self)
        # Toàn bộ state + logic OC (review workbook, token upload) nằm trong
        # controller riêng, giống Catalog.
        self._oc = OCController(self)
        self._sale_asn = SaleASNController(self)
        self._inventory = InventoryController(self)
        self._reports = ReportsController(self)
        self._finance = FinanceController(self)
        self._directory = DirectoryController(self)
        self._settings = SettingsController(self)
        self._jobs = JobsController(self)
        self._modules = ModulesController(self)
        self._access = AccessController(self)
        self._session = SessionController(self)
        # Engine chạy flow: khóa, hủy, lịch sử, telemetry.
        self._engine = AutomationRunEngine(self)

    # -- logging -----------------------------------------------------------
    def set_log_sink(self, sink: Callable[[str], None]) -> None:
        self._sink = sink
        # Runtime cứu file người dùng tự tải trong lúc flow chạy; họ phải thấy
        # được nó đã lưu vào đâu.
        AUTOMATION_RUNTIME.log_sink = self._log

    def set_result_sink(
        self, sink: Callable[[str, dict, float], None]
    ) -> None:
        self._result_sink = sink

    def set_progress_sink(self, sink: Callable[[dict], None]) -> None:
        self._progress_sink = sink

    def _progress(self, method: str, stage: str, message: str, step: int, total: int, *, state: str='active') -> None:
        return self._engine._progress(method, stage, message, step, total, state=state)

    def _progress_for(self, method: str) -> Callable[..., None]:
        return self._engine._progress_for(method)

    def set_hotkey_applier(
        self, applier: Callable[[str], str | None]
    ) -> None:
        self._hotkey_applier = applier

    def set_update_applier(
        self, applier: Callable[[dict], str | None]
    ) -> None:
        self._update_applier = applier

    def set_window_pref_appliers(
        self,
        on_top: Callable[[bool], None],
    ) -> None:
        self._on_top_applier = on_top

    def _log(self, message: str) -> None:
        if self._current_run_id:
            message = f"[{self._current_run_id}] {message}"
        line = log_bridge.format_log_line(message)
        self._logs.append(line)
        if len(self._logs) > 300:
            self._logs = self._logs[-300:]
        if self._sink is not None:
            try:
                self._sink(line)
            except Exception:
                pass

    def _account(self) -> dict:
        return self._session._account()

    @property
    def _session_user_id(self) -> str | None:
        """Chủ phiên Chrome hiện tại, nhớ xuyên lần chạy qua prefs."""
        if not self._session_user_id_loaded:
            self._session_user_id_loaded = True
            try:
                stored = self._prefs.load_prefs(
                    base_dir=self._base_dir
                ).get("session_user_id")
            except OSError:
                stored = ""
            self._session_user_id_value = str(stored or "").strip() or None
        return self._session_user_id_value

    @_session_user_id.setter
    def _session_user_id(self, value: str | None) -> None:
        self._session_user_id_loaded = True
        self._session_user_id_value = str(value or "").strip() or None

    def _login_run(self, user_id: str, password: str) -> dict:
        return self._session._login_run(user_id, password)

    def _remember_session_user(self, user_id: str | None) -> None:
        return self._session._remember_session_user(user_id)

    def _credential_state(self) -> str:
        return self._session._credential_state()

    def _telemetry_account_context(self) -> dict:
        return self._session._telemetry_account_context()

    def _admin_state(self, preferences: Mapping | None=None) -> dict:
        return self._access._admin_state(preferences)

    def _division_state(self) -> dict:
        return self._access._division_state()

    def _refresh_admin_access(self) -> dict:
        return self._access._refresh_admin_access()

    def _with_admin_access(self, result: dict) -> dict:
        return self._access._with_admin_access(result)

    # -- state -------------------------------------------------------------
    def get_initial_state(self) -> dict:
        account = self._account()
        preferences = self._prefs.load_prefs(base_dir=self._base_dir)
        return {
            "app_version": APP_VERSION,
            "app_version_label": DISPLAY_VERSION,
            "version": DISPLAY_VERSION,
            "user_id": account["user_id"],
            "has_credentials": bool(
                account["user_id"].strip() and account["password"].strip()
            ),
            "credential_state": self._credential_state(),
            "theme": preferences["theme"],
            "favorite_module_ids": preferences["favorite_module_ids"],
            "hotkey": preferences["hotkey"],
            "hotkey_label": preferences["hotkey_label"],
            "autostart": preferences["autostart"],
            "start_hidden": preferences["start_hidden"],
            "toast_enabled": preferences["toast_enabled"],
            "focus_chrome_on_module": preferences[
                "focus_chrome_on_module"
            ],
            "always_on_top": preferences["always_on_top"],
            "open_excel_file_after_download": preferences[
                "open_excel_file_after_download"
            ],
            "open_costing_folder_after_export": preferences[
                "open_costing_folder_after_export"
            ],
            "report_export_dir": preferences["report_export_dir"],
            "catalog_default_folder": (
                self._catalog.default_folder_for_account(preferences)
            ),
            "article_library": self._catalog.article_library_status(),
            "reference_sync": reference_sync.status(self._base_dir),
            "costing_special_options": (
                self._catalog.costing.special_options_state(preferences)
            ),
            **self._admin_state(preferences),
            "reporting_configured": telemetry.is_configured(self._base_dir),
            "pending_reports": telemetry.outbox_count(self._base_dir),
            "update_channel": "stable",
            "module_groups": module_controllers.manifest_groups(),
            "divisions": list(constants.DIVISIONS.values()),
            "jobs": job_history.list_jobs(self._base_dir, 20),
            "sale_asn_buyers": list(self._sale_asn.buyers),
            "sale_asn_stages": preferences["sale_asn_stages"],
            "sale_asn_po_search_fields": preferences[
                "sale_asn_po_search_fields"
            ],
            "logs": list(self._logs),
            **self.get_status(),
        }

    def get_status(self) -> dict:
        browser_state = (
            self._login.browser_status()
            if hasattr(self._login, "browser_status")
            else {"chrome_alive": status.chrome_alive()}
        )
        return {
            **browser_state,
            **self._session_status(),
            **self._division_state(),
        }

    def _session_status(self) -> dict:
        return self._session._session_status()

    def refresh_status(self) -> dict:
        return self.get_status()

    def _observe(self, method_name: str, result: dict, elapsed: float, *, emit_result: bool=True) -> None:
        return self._engine._observe(
            method_name,
            result,
            elapsed,
            emit_result=emit_result,
        )

    def _action_in_progress(self) -> dict:
        return self._engine._action_in_progress()

    def _enter_run(self) -> None:
        return self._engine._enter_run()

    def _exit_run(self) -> None:
        return self._engine._exit_run()

    def run_composite(self, steps: Callable[[], dict]) -> dict:
        return self._engine.run_composite(steps)

    def _run(self, method_name: str, action: Callable[[], dict], request: dict | None=None, *, record_job: bool=True, record_job_on_failure: bool=False, announce: bool=True, emit_result: bool=True) -> dict:
        return self._engine._run(
            method_name,
            action,
            request,
            record_job=record_job,
            record_job_on_failure=record_job_on_failure,
            announce=announce,
            emit_result=emit_result,
        )

    def _normalised_result(self, method_name: str, action: Callable[[], dict]) -> dict:
        return self._engine._normalised_result(method_name, action)

    def _wants_failure_screenshot(self, method_name: str, code: str) -> bool:
        return self._engine._wants_failure_screenshot(method_name, code)

    def _capture_failure_screenshot(self, run_id: str) -> str | None:
        return self._engine._capture_failure_screenshot(run_id)

    def _append_job_history(self, run_id: str, method_name: str, request: dict | None, result: dict, started_at: str, elapsed: float, screenshot: str | None) -> None:
        return self._engine._append_job_history(
            run_id,
            method_name,
            request,
            result,
            started_at,
            elapsed,
            screenshot,
        )

    def _announce_finish(self, method_name: str, result: dict, elapsed: float, announce: bool) -> None:
        return self._engine._announce_finish(method_name, result, elapsed, announce)

    def _run_unlocked(self, method_name: str, action: Callable[[], dict], request: dict | None=None, *, record_job: bool=True, record_job_on_failure: bool=False, announce: bool=True, emit_result: bool=True) -> dict:
        return self._engine._run_unlocked(
            method_name,
            action,
            request,
            record_job=record_job,
            record_job_on_failure=record_job_on_failure,
            announce=announce,
            emit_result=emit_result,
        )

    def _restore_expired_session(self) -> dict | None:
        return self._session._restore_expired_session()

    def _run_action_with_auto_relogin(self, method_name: str, action: Callable[[], dict]) -> dict:
        return self._session._run_action_with_auto_relogin(method_name, action)

    def _report_automation_error(self, method_name: str, result: dict, request: dict | None, code: str, run_id: str, elapsed: float) -> None:
        return self._engine._report_automation_error(
            method_name,
            result,
            request,
            code,
            run_id,
            elapsed,
        )

    def cancel_current_action(self) -> dict:
        return self._engine.cancel_current_action()

    def is_action_running(self) -> bool:
        return self._engine.is_action_running()

    def shutdown(self, close_browser: bool=False) -> None:
        return self._session.shutdown(close_browser)

    def login(self) -> dict:
        return self._session.login()

    def check_session(self) -> dict:
        return self._session.check_session()

    def should_maintain_session(self) -> bool:
        return self._session.should_maintain_session()

    def maintain_session(self) -> dict:
        return self._session.maintain_session()

    def open_chrome(self) -> dict:
        return self._session.open_chrome()

    def open_module(self, module_id: str) -> dict:
        return self._modules.open_module(module_id)

    def report_catalog(self) -> dict:
        return self._reports.report_catalog()

    def _saved_report_parameters(self, report_id: str) -> dict[str, Any]:
        return self._reports._saved_report_parameters(report_id)

    def load_report_parameters(self, report_id: str) -> dict:
        return self._reports.load_report_parameters(report_id)

    def save_report_parameters(self, report_id: str, values: Mapping[str, Any] | None=None) -> dict:
        return self._reports.save_report_parameters(report_id, values)

    def export_report_excel(self, report_id: str, values: Mapping[str, Any] | None=None) -> dict:
        return self._reports.export_report_excel(report_id, values)

    def load_color_report_options(self, values: Mapping[str, Any] | None=None) -> dict:
        return self._reports.load_color_report_options(values)

    def run_color_report_batch(self, selection: Mapping[str, Any] | None=None, style_refs: list[str] | None=None, output_dir: str='') -> dict:
        return self._reports.run_color_report_batch(selection, style_refs, output_dir)

    def _admin_module_access_error(self, module_id: str) -> dict | None:
        return self._access._admin_module_access_error(module_id)

    def open_sale_asn_new(self) -> dict:
        return self._sale_asn.open_sale_asn_new()

    def scan_sale_asn_buyers(self) -> dict:
        return self._sale_asn.scan_sale_asn_buyers()

    def scan_sale_asn_order_details(self) -> dict:
        return self._sale_asn.scan_sale_asn_order_details()

    def _discard_sale_asn_create_review(self, review_token: str) -> bool:
        return self._sale_asn._discard_sale_asn_create_review(review_token)

    def prepare_sale_asn_create(self, file_path: str, buyer: str, selected_stages: list[str] | tuple[str, ...] | None=None) -> dict:
        return self._sale_asn.prepare_sale_asn_create(file_path, buyer, selected_stages)

    def _run_sale_asn_create_review(self, review_token: str, *, continue_existing: bool, selected_candidate_ids: list[str] | None=None) -> dict:
        return self._sale_asn._run_sale_asn_create_review(
            review_token,
            continue_existing=continue_existing,
            selected_candidate_ids=selected_candidate_ids,
        )

    def start_sale_asn_create(self, review_token: str) -> dict:
        return self._sale_asn.start_sale_asn_create(review_token)

    def continue_sale_asn_create(self, review_token: str, selected_candidate_ids: list[str] | None=None) -> dict:
        return self._sale_asn.continue_sale_asn_create(
            review_token,
            selected_candidate_ids,
        )

    def skip_sale_asn_create_step(self, review_token: str) -> dict:
        return self._sale_asn.skip_sale_asn_create_step(review_token)

    def cancel_sale_asn_create(self, review_token: str) -> dict:
        return self._sale_asn.cancel_sale_asn_create(review_token)

    def search_oc(self, filter_kind: str, query: str) -> dict:
        return self._modules.search_oc(filter_kind, query)

    def search_sample(self, sample_no: str='', style: str='', created_by: str='', buyer: str='') -> dict:
        return self._modules.search_sample(sample_no, style, created_by, buyer)

    def open_sample_new(self) -> dict:
        return self._modules.open_sample_new()

    def search_sale_asn(self, filter_kind: str, query: str) -> dict:
        return self._sale_asn.search_sale_asn(filter_kind, query)

    def export_sale_asn_price_check(self, price_check: dict, file_path: str) -> dict:
        return self._sale_asn.export_sale_asn_price_check(price_check, file_path)

    def _discard_sale_asn_document_export(self, export_token: str) -> bool:
        return self._sale_asn._discard_sale_asn_document_export(export_token)

    def prepare_sale_asn_documents(self, filter_kind: str, query: str) -> dict:
        return self._sale_asn.prepare_sale_asn_documents(filter_kind, query)

    def cancel_sale_asn_documents(self, export_token: str) -> dict:
        return self._sale_asn.cancel_sale_asn_documents(export_token)

    def save_sale_asn_documents(self, export_token: str, file_path: str) -> dict:
        return self._sale_asn.save_sale_asn_documents(export_token, file_path)

    def search_rmpo(self, supplier: str, order_no: str) -> dict:
        return self._inventory.search_rmpo(supplier, order_no)

    def run_rmpo_action(self, choice_id: str, action_name: str) -> dict:
        return self._inventory.run_rmpo_action(choice_id, action_name)

    def prepare_grn_receipt(self, rmpo_no: str, mode: str, rmpo_choice_id: str='') -> dict:
        return self._inventory.prepare_grn_receipt(rmpo_no, mode, rmpo_choice_id)

    def continue_grn_receipt(self, receipt_token: str, sourcing_confirmed: bool) -> dict:
        return self._inventory.continue_grn_receipt(receipt_token, sourcing_confirmed)

    def finalize_grn_receipt(self, receipt_token: str, site: str) -> dict:
        return self._inventory.finalize_grn_receipt(receipt_token, site)

    def search_grn(self, filter_kind: str, query: str) -> dict:
        return self._inventory.search_grn(filter_kind, query)

    def search_indent(self, module_id: str, supplier: str, article: str, indent_no: str, style: str) -> dict:
        return self._modules.search_indent(
            module_id,
            supplier,
            article,
            indent_no,
            style,
        )

    def search_supplier_invoice(self, supplier: str='', invoice_no: str='', po_no: str='', asn_grn_no: str='') -> dict:
        return self._modules.search_supplier_invoice(
            supplier,
            invoice_no,
            po_no,
            asn_grn_no,
        )

    def search_advance_pr(self, buyer: str='', supplier: str='', invoice_no: str='', order_no: str='') -> dict:
        return self._finance.search_advance_pr(buyer, supplier, invoice_no, order_no)

    def search_expense_invoice(self, supplier: str='', invoice_no: str='', created_by: str='', status: str='') -> dict:
        return self._modules.search_expense_invoice(
            supplier,
            invoice_no,
            created_by,
            status,
        )

    def cancel_supplier_invoice(self, invoice_no: str) -> dict:
        return self._finance.cancel_supplier_invoice(invoice_no)

    def cancel_supplier_invoice_choice(self, choice_id: str) -> dict:
        return self._finance.cancel_supplier_invoice_choice(choice_id)

    def open_module_new(self, module_id: str) -> dict:
        return self._modules.open_module_new(module_id)

    def toggle_company_foc(self) -> dict:
        return self._directory.toggle_company_foc()

    def open_supplier_category(self, category_name: str) -> dict:
        return self._directory.open_supplier_category(category_name)

    def find_supplier(self, query: str) -> dict:
        return self._directory.find_supplier(query)

    def find_supplier_in_category(self, category_name: str, query: str) -> dict:
        return self._directory.find_supplier_in_category(category_name, query)

    def find_buyer(self, query: str) -> dict:
        return self._directory.find_buyer(query)

    def switch_division(self, division_key: str) -> dict:
        return self._access.switch_division(division_key)

    # -- catalog (uỷ quyền cho CatalogController) --------------------------
    def scan_catalog_folders(
        self, category_name: str, force: bool = False
    ) -> dict:
        return self._catalog.scan_folders(category_name, boolean(force))

    def set_catalog_default_folder(
        self, category_name: str, node_id: str
    ) -> dict:
        return self._catalog.set_default_folder(category_name, node_id)

    def browse_catalog(self, category_name: str) -> dict:
        return self._catalog.browse(category_name)

    def prepare_catalog(self, category_name: str) -> dict:
        return self._catalog.prepare(category_name)

    def review_catalog_style_import(
        self,
        file_path: str,
        group_id: str,
    ) -> dict:
        return self._catalog.style.review_style_import(file_path, group_id)

    def clear_catalog_style_import(self, review_token: str) -> dict:
        return self._catalog.style.clear_style_import(review_token)

    def ensure_catalog_style_options(
        self,
        group_id: str,
        force: bool = False,
    ) -> dict:
        return self._catalog.style.ensure_style_options(group_id, boolean(force))

    def prepare_catalog_style_row(
        self,
        review_token: str,
        source_row: int,
        copy_choice: int | None = None,
        auto_save: bool = False,
    ) -> dict:
        return self._catalog.style.prepare_style_row(
            review_token,
            source_row,
            copy_choice,
            boolean(auto_save),
        )

    def find_code(
        self, category_name: str, code: str, destination: str | None = None
    ) -> dict:
        return self._catalog.action(
            category_name,
            "code",
            code,
            destination,
            method_name="find_code",
        )

    def find_buyer_reference(
        self, category_name: str, query: str, destination: str | None = None
    ) -> dict:
        return self._catalog.action(
            category_name,
            "buyer_reference",
            query,
            destination,
            method_name="find_buyer_reference",
        )

    def catalog_action(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        destination: str | None = None,
    ) -> dict:
        return self._catalog.action(
            category_name, filter_kind, query, destination
        )

    def open_catalog_destination(
        self, destination: str, article_code: str
    ) -> dict:
        return self._catalog.open_destination(destination, article_code)

    def download_catalog_file(self, file_id: str) -> dict:
        return self._catalog.files_view.download_file(file_id)

    def export_catalog_costing(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
        scan_article_options: bool = False,
    ) -> dict:
        return self._catalog.costing.export(
            category_name,
            filter_kind,
            query,
            file_path,
            boolean(scan_article_options),
        )

    def check_sample_files(
        self,
        sample_no: str = "",
        style: str = "",
        created_by: str = "",
        buyer: str = "",
    ) -> dict:
        return self._catalog.files_view.check_sample_files_with_filters(
            {
                "sample_no": str(sample_no or "").strip(),
                "style": str(style or "").strip(),
                "created_by": str(created_by or "").strip(),
                "buyer": str(buyer or "").strip(),
            }
        )

    def open_sample_file_choice(self, choice_id: str) -> dict:
        return self._catalog.files_view.open_sample_file_choice(choice_id)

    def open_oc_revision_report(self) -> dict:
        return self._oc.open_oc_revision_report()

    def run_gdn_dispatch(self, invoice: str, grn_wait_confirmed: bool=False) -> dict:
        return self._modules.run_gdn_dispatch(invoice, grn_wait_confirmed)

    def open_gdn_status(self) -> dict:
        return self._modules.open_gdn_status()

    def _discard_oc_upload_review(self, review_token: str) -> bool:
        return self._oc._discard_oc_upload_review(review_token)

    def review_oc_upload(self, mode: str, file_path: str) -> dict:
        return self._oc.review_oc_upload(mode, file_path)

    def cancel_oc_upload_review(self, review_token: str) -> dict:
        return self._oc.cancel_oc_upload_review(review_token)

    def save_oc_upload_file(self, review_token: str, file_path: str) -> dict:
        return self._oc.save_oc_upload_file(review_token, file_path)

    def confirm_oc_upload(self, review_token: str) -> dict:
        return self._oc.confirm_oc_upload(review_token)

    def confirm_oc_pending(self, mode: str) -> dict:
        return self._oc.confirm_oc_pending(mode)

    def reject_all_oc_pending(self) -> dict:
        return self._oc.reject_all_oc_pending()

    def upload_oc(self, mode: str, file_path: str) -> dict:
        return self._oc.upload_oc(mode, file_path)

    def inspect_active_catalog_costing(self, category_name: str) -> dict:
        return self._catalog.costing.inspect_active(category_name)

    def clear_catalog_costing_dependencies(self) -> dict:
        return self._catalog.costing.clear_active_dependencies()

    def sync_article_library(self) -> dict:
        return self._catalog.sync_article_library()

    def sync_reference_data(self, force: bool=True) -> dict:
        return self._settings.sync_reference_data(force)

    def save_sync_admin_key(self, admin_key: str) -> dict:
        return self._settings.save_sync_admin_key(admin_key)

    def publish_reference_data(self) -> dict:
        return self._settings.publish_reference_data()

    def set_costing_special_options_rescan(self, value: bool) -> dict:
        return self._catalog.costing.set_special_options_rescan(value)

    def suggest_articles(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        limit: int = 20,
    ) -> dict:
        return self._catalog.suggest_articles(
            category_name,
            filter_kind,
            query,
            limit,
        )

    def validate_catalog_costing_file(self, file_path: str) -> dict:
        return self._catalog.costing.validate_file(file_path)

    def prepare_catalog_costing_import(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        return self._catalog.costing.prepare_import(
            category_name,
            filter_kind,
            query,
            file_path,
        )

    def clear_catalog_costing_plan(self, plan_token: str) -> dict:
        return self._catalog.costing.clear_plan(plan_token)

    def apply_catalog_costing(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        return self._catalog.costing.apply(plan_token, article_resolutions)

    def save_account(self, user_id: str, password: str) -> dict:
        return self._session.save_account(user_id, password)

    def set_theme(self, theme: str) -> dict:
        return self._settings.set_theme(theme)

    def set_sale_asn_stages(self, stages: list[str] | None=None) -> dict:
        return self._settings.set_sale_asn_stages(stages)

    def set_sale_asn_po_search_fields(self, fields: list[str] | None=None) -> dict:
        return self._settings.set_sale_asn_po_search_fields(fields)

    def set_excel_file_after_download(self, enabled: bool) -> dict:
        return self._settings.set_excel_file_after_download(enabled)

    def set_module_favorite(self, module_id: str, favorite: bool) -> dict:
        return self._settings.set_module_favorite(module_id, favorite)

    def set_hotkey(self, spec: str | dict) -> dict:
        return self._settings.set_hotkey(spec)

    def set_autostart(self, enabled: bool) -> dict:
        return self._settings.set_autostart(enabled)

    def set_start_hidden(self, enabled: bool) -> dict:
        return self._settings.set_start_hidden(enabled)

    def set_toast_enabled(self, enabled: bool) -> dict:
        return self._settings.set_toast_enabled(enabled)

    def set_focus_chrome_on_module(self, enabled: bool) -> dict:
        return self._settings.set_focus_chrome_on_module(enabled)

    def set_always_on_top(self, enabled: bool) -> dict:
        return self._settings.set_always_on_top(enabled)

    def set_admin_mode(self, enabled: bool) -> dict:
        return self._access.set_admin_mode(enabled)

    def submit_feedback(self, kind: str, message: str, include_diagnostics: bool=True) -> dict:
        return self._jobs.submit_feedback(kind, message, include_diagnostics)

    def flush_error_reports(self) -> dict:
        return self._jobs.flush_error_reports()

    def set_update_channel(self, channel: str) -> dict:
        return self._settings.set_update_channel(channel)

    def check_for_updates(self) -> dict:
        return self._settings.check_for_updates()

    def install_update(self) -> dict:
        return self._settings.install_update()

    def get_job_history(self, limit: int=30) -> dict:
        return self._jobs.get_job_history(limit)

    def acknowledge_job(self, run_id: str) -> dict:
        return self._jobs.acknowledge_job(run_id)

    def retry_job(self, run_id: str) -> dict:
        return self._jobs.retry_job(run_id)

    def open_job_screenshot(self, run_id: str) -> dict:
        return self._jobs.open_job_screenshot(run_id)

    def clear_job_history(self) -> dict:
        return self._jobs.clear_job_history()

    def clear_log(self) -> dict:
        return self._jobs.clear_log()
