"""ColorCombination PO Wise: PO → BuyerStyleReference → mọi StyleCode."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path

from wfx_panel.automation._common import (
    PlaywrightTimeoutError,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.color_combination import (
    CASCADE_KEYS,
    POSTBACK_TIMEOUT_SECONDS,
    StyleFailure,
    _download_style_report,
    _select_ocnums,
    _set_oc_parameter,
    clean_style_ref_options,
    read_cascade,
    read_parameter_choices,
    safe_file_stem,
    select_and_settle,
)
from wfx_panel.automation.reports import (
    REPORTS,
    _open_report,
    _wait_postback_settled,
    read_select_options,
    read_select_value,
    resolve_controls,
)
from wfx_panel.automation.runtime import AutomationCancelled, checkpoint
from wfx_panel.automation.session import _session_is_active

REPORT_ID = "color_combination_po_wise"
REPORT_NAME = "ColorCombination PO Wise"


def po_folder_name(po_no: str) -> str:
    name = safe_file_stem(po_no, "")[:120].rstrip(" .") or "PO"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", name.split(".")[0], re.I):
        name = "_" + name
    return name


def _reset_search_po(page) -> None:
    key = resolve_controls(page).get("SearchPO", "")
    if not key:
        return
    null = page.locator(f'[id="{key.removesuffix("_txtValue")}_cbNull"]')
    if null.count() and null.is_enabled() and not null.is_checked():
        null.evaluate("element => element.click()")
        _wait_postback_settled(page, POSTBACK_TIMEOUT_SECONDS)


def read_po_cascade(page, values: Mapping | None) -> dict:
    levels = read_cascade(page, values)["levels"]
    levels.pop("style_ref", None)
    options = []
    if all(levels[key]["value"] for key in CASCADE_KEYS):
        _reset_search_po(page)
        options = read_parameter_choices(page, "PO_No")["options"]
    levels["po_no"] = {"options": options, "value": ""}
    return {"levels": levels}


def _select_po(page, label: str) -> None:
    parameter = read_parameter_choices(page, "PO_No")
    wanted = [
        option["value"] for option in parameter["options"] if option["label"] == label
    ]
    if len(wanted) != 1:
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY",
            "PO cần tải không còn trong danh sách. Hãy nạp lại PO.",
        )
    if parameter["value"] != wanted:
        _set_oc_parameter(page, parameter, wanted)
    confirmed = read_parameter_choices(page, "PO_No")
    labels = [
        option["label"]
        for option in confirmed["options"]
        if option["value"] in confirmed["value"]
    ]
    if labels != [label]:
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY", "WFX chưa nhận đúng PO cần tải."
        )


def _select_native(page, label: str, value: str) -> None:
    controls = resolve_controls(page)
    if read_select_value(page, controls.get(label, "")) != value:
        controls = select_and_settle(page, controls, label, value)
    if read_select_value(page, controls.get(label, "")) != value:
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY", f"WFX chưa nhận lựa chọn {label}."
        )


def read_po_ocs(page) -> dict:
    key = resolve_controls(page).get("OC Num", "")
    if key:
        control = page.locator(f'[id="{key}"]')
        if not control.is_enabled() and not read_select_value(page, key).strip():
            return {"key": key, "options": [], "value": []}
    return read_parameter_choices(page, "OC Num")


def _retry_matches(retries: list[dict], item: dict) -> bool:
    if not retries:
        return True
    return any(
        all(
            not retry.get(key) or not item.get(key) or retry[key] == item[key]
            for key in ("po_value", "style_ref_value", "style_code_value")
        )
        for retry in retries
    )


def batch_po_reports(
    page,
    pos: list[dict],
    output_dir: Path,
    log: Callable,
    progress: Callable | None = None,
    retry_items: list[dict] | None = None,
) -> dict:
    saved, failed, skipped = [], [], []
    retries = retry_items or []

    def failure(item, error):
        _write_log(
            log,
            f"[COLOR PO] {item.get('po_no')} / {item.get('style_ref', '')}: {type(error).__name__}: {error}",
        )
        failed.append(
            {
                **item,
                "code": getattr(error, "code", "COLOR_REPORT_STYLE_FAILED"),
                "message": getattr(
                    error, "message", f"{type(error).__name__}: {error}"
                ),
            }
        )

    def skip(item, message):
        _write_log(
            log,
            f"[COLOR PO] {item['po_no']} / {item.get('style_ref', '')}: {message}; bỏ qua.",
        )
        skipped.append({**item, "message": message})

    try:
        for index, po in enumerate(pos, start=1):
            checkpoint()
            base = {"po_no": po["label"], "po_value": po["value"], "style_ref": ""}
            if not _retry_matches(retries, base):
                continue
            if progress:
                progress(
                    "po",
                    f"Đang tải PO {po['label']}… {index}/{len(pos)}",
                    index,
                    len(pos),
                )
            try:
                _select_po(page, po["label"])
                controls = resolve_controls(page)
                refs = clean_style_ref_options(
                    read_select_options(page, controls.get("BuyerStyleReference", ""))
                )
                if not refs:
                    skip(base, "Không tìm thấy BuyerStyleReference")
                    continue
            except AutomationCancelled:
                raise
            except Exception as error:
                failure(base, error)
                continue
            for ref in refs:
                item = {
                    **base,
                    "style_ref": ref["label"],
                    "style_ref_value": ref["value"],
                }
                if not _retry_matches(retries, item):
                    continue
                checkpoint()
                try:
                    _select_native(page, "BuyerStyleReference", ref["value"])
                    codes = clean_style_ref_options(
                        read_select_options(
                            page, resolve_controls(page).get("StyleCode", "")
                        )
                    )
                    if not codes:
                        skip(item, "Không tìm thấy StyleCode")
                        continue
                except AutomationCancelled:
                    raise
                except Exception as error:
                    failure(item, error)
                    continue
                for code in codes:
                    detail = {
                        **item,
                        "style_code": code["label"],
                        "style_code_value": code["value"],
                    }
                    if not _retry_matches(retries, detail):
                        continue
                    checkpoint()
                    try:
                        if progress:
                            progress(
                                "po",
                                f"{po['label']} · {ref['label']} · {code['label']}… {index}/{len(pos)}",
                                index,
                                len(pos),
                            )
                        _select_native(page, "StyleCode", code["value"])
                        if not read_po_ocs(page)["options"]:
                            skip(detail, "Không tìm thấy OC")
                            continue
                        # OC tự nạp theo StyleCode; chọn hết, không lặp từng OC.
                        _select_ocnums(page, None)
                        directory = Path(output_dir) / po_folder_name(po["label"])
                        directory.mkdir(parents=True, exist_ok=True)
                        report = _download_style_report(
                            page,
                            directory,
                            log,
                            safe_file_stem(po["label"], ref["label"]),
                            code["label"],
                        )
                        saved.append({**report, **detail})
                    except AutomationCancelled:
                        raise
                    except StyleFailure as error:
                        if error.code == "COLOR_REPORT_OC_NOT_FOUND":
                            skip(detail, "Không tìm thấy OC")
                        else:
                            failure(detail, error)
                    except Exception as error:
                        failure(detail, error)
    except AutomationCancelled:
        return {"saved": saved, "failed": failed, "skipped": skipped, "cancelled": True}
    return {"saved": saved, "failed": failed, "skipped": skipped, "cancelled": False}


def _with_report(action, log, *, loading: bool) -> dict:
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        report_page = _open_report(page, REPORTS[REPORT_ID])
        _attach_dialog_handler(report_page, log)
        return action(report_page)
    except AutomationCancelled:
        raise
    except StyleFailure as error:
        return _result(False, error.code, error.message)
    except PlaywrightTimeoutError:
        return _result(
            False,
            "COLOR_REPORT_OPTIONS_NOT_READY",
            "WFX chưa nạp xong tham số PO Wise. Hãy thử lại.",
        )
    except Exception as error:
        _write_log(log, f"[COLOR PO] {type(error).__name__}: {error}")
        return _result(
            False,
            "REPORT_LOAD_FAILED" if loading else "REPORT_EXPORT_FAILED",
            "Chưa tải được tham số PO Wise."
            if loading
            else "Chưa xuất được báo cáo PO Wise.",
        )
    finally:
        if playwright is not None:
            playwright.stop()


def load_color_po_report_options(
    values: Mapping | None = None, log: Callable = print
) -> dict:
    def action(page):
        cascade = read_po_cascade(page, values)
        return _result(
            True,
            "COLOR_REPORT_OPTIONS_READY",
            "Đã tải tham số ColorCombination PO Wise.",
            report_id=REPORT_ID,
            report_name=REPORT_NAME,
            **cascade,
        )

    return _with_report(action, log, loading=True)


def run_color_po_report_batch(
    selection: Mapping,
    po_values: list[str],
    output_dir: str,
    log: Callable = print,
    progress: Callable | None = None,
) -> dict:
    if not po_values:
        return _result(
            False,
            "COLOR_PO_REPORT_NO_PO_SELECTED",
            "Hãy chọn ít nhất một PO_No trước khi tải.",
        )
    directory = Path(output_dir or "")
    if not str(output_dir or "").strip() or not directory.is_dir():
        return _result(
            False,
            "COLOR_REPORT_OUTPUT_DIR_REQUIRED",
            "Hãy chọn thư mục lưu báo cáo trước khi tải.",
        )

    def action(page):
        cascade = read_po_cascade(page, selection)
        if not all(cascade["levels"][key]["value"] for key in CASCADE_KEYS):
            return _result(
                False,
                "REPORT_PARAMETERS_INVALID",
                "Hãy chọn lại OC Division, Buyer và Season.",
            )
        choices = {
            option["value"]: option for option in cascade["levels"]["po_no"]["options"]
        }
        if any(value not in choices for value in po_values):
            return _result(
                False,
                "REPORT_PARAMETERS_INVALID",
                "Danh sách PO đã thay đổi. Hãy nạp lại tham số và chọn PO.",
            )
        outcome = batch_po_reports(
            page,
            [choices[value] for value in dict.fromkeys(po_values)],
            directory,
            log,
            progress,
            selection.get("retry_items"),
        )
        saved, failed, skipped = outcome["saved"], outcome["failed"], outcome["skipped"]
        message = f"Đã tải {len(saved)} báo cáo trong {len({item['po_no'] for item in saved})} thư mục PO."
        if skipped:
            message += f" Bỏ qua {len(skipped)} mục thiếu StyleCode hoặc OC/Style."
        if failed:
            message += f" {len(failed)} mục lỗi."
        code = "COLOR_REPORT_BATCH_DONE"
        ok = bool(saved) or not failed
        if outcome["cancelled"]:
            ok, code, message = False, "COLOR_REPORT_CANCELLED", "Đã dừng. " + message
        elif not saved and not failed:
            code, message = (
                "COLOR_PO_REPORT_EMPTY",
                "Không có mục đủ StyleCode và OC để tải. " + message,
            )
        elif not saved:
            code = failed[0]["code"]
        return _result(
            ok,
            code,
            message,
            report_id=REPORT_ID,
            report_name=REPORT_NAME,
            output_dir=str(directory),
            **outcome,
        )

    return _with_report(action, log, loading=False)
