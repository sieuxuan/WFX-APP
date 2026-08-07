"""Báo cáo Color Combination - Production: cascade tham số và tải hàng loạt."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

from wfx_panel.automation._common import (
    Page,
    Playwright,
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
from wfx_panel.automation.reports import (
    REPORTS,
    _click_view_report,
    _export_excel,
    _open_report,
    _wait_postback_settled,
    _wait_report_ready,
    read_select_options,
    read_select_value,
    resolve_controls,
)
from wfx_panel.automation.runtime import AutomationCancelled, checkpoint
from wfx_panel.automation.session import _session_is_active

REPORT_ID = "color_combination_production"
REPORT_NAME = "Color Combination - Production"
POSTBACK_TIMEOUT_SECONDS = 45.0
LEVEL_LABELS = {
    "division": "OC Division",
    "buyer": "Buyer",
    "season": "Season",
    "style_ref": "BuyerStyleReference",
}
CASCADE_KEYS = ("division", "buyer", "season")
STYLE_CODE_LABEL = "StyleCode"
SIZE_VISIBILITY_LABEL = "SizeVisibility"

_TRAILING_DIGITS = re.compile(r"(\d+)\s*$")
_FORBIDDEN_FILE_CHARS = re.compile(r'[\\/:*?"<>|]')


def _style_code_rank(label: str) -> int | None:
    match = _TRAILING_DIGITS.search(str(label or ""))
    return int(match.group(1)) if match else None


def pick_style_code(
    options: list[Mapping[str, str]],
) -> dict[str, str] | None:
    """Chọn style mới nhất: mã có số đuôi lớn nhất, hòa thì lấy option sau."""
    cleaned = [dict(option) for option in options or () if option]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    ranked = [
        (rank, index, option)
        for index, option in enumerate(cleaned)
        if (rank := _style_code_rank(option.get("label", ""))) is not None
    ]
    if not ranked:
        return cleaned[-1]
    return max(ranked, key=lambda item: (item[0], item[1]))[2]


def safe_file_stem(style_ref: str, style_code: str) -> str:
    """Tên file theo style; ký tự Windows cấm được thay bằng gạch dưới."""
    reference = str(style_ref or "").strip()
    code = str(style_code or "").strip()
    stem = f"{reference} - {code}" if reference and code else (reference or code)
    stem = _FORBIDDEN_FILE_CHARS.sub("_", stem).strip().rstrip(" .")
    return stem or "report"


def unique_target(
    directory: Path, stem: str, suffix: str = ".xlsx"
) -> Path:
    """Không ghi đè file đã có: thêm hậu tố (2), (3)... như Chrome."""
    target = Path(directory) / f"{stem}{suffix}"
    index = 2
    while target.exists():
        target = Path(directory) / f"{stem} ({index}){suffix}"
        index += 1
    return target


def prune_selection(
    values: Mapping[str, str],
    options_by_key: Mapping[str, list[Mapping[str, str]]],
) -> dict[str, str]:
    """Giữ các cấp cascade còn hợp lệ; gặp cấp hỏng thì bỏ luôn cấp dưới."""
    cleaned: dict[str, str] = {}
    for key in CASCADE_KEYS:
        available = {
            str(option.get("value") or "")
            for option in options_by_key.get(key) or ()
        }
        current = str((values or {}).get(key) or "")
        if not current or current not in available:
            break
        cleaned[key] = current
    return cleaned


class StyleFailure(Exception):
    """Lỗi ở mức một style; vòng lặp ghi lại rồi chạy tiếp style kế."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def batch_styles(
    style_refs: list[str],
    run_one: Callable[[str], dict],
    progress: Callable[..., None] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Chạy từng style, bỏ qua style lỗi, và giữ kết quả khi user bấm Stop."""
    references = [
        str(reference).strip()
        for reference in style_refs or ()
        if str(reference).strip()
    ]
    total = len(references)
    saved: list[dict] = []
    failed: list[dict] = []
    for index, reference in enumerate(references, start=1):
        try:
            checkpoint()
            if progress is not None:
                progress(
                    "style", f"Đang tải {reference}… {index}/{total}", index, total
                )
            saved.append(run_one(reference))
        except AutomationCancelled:
            log(f"[COLOR] Đã dừng theo yêu cầu sau {len(saved)}/{total} style.")
            return {"saved": saved, "failed": failed, "cancelled": True}
        except StyleFailure as failure:
            log(f"[COLOR] Bỏ qua {reference}: {failure.message}")
            failed.append(
                {
                    "style_ref": reference,
                    "code": failure.code,
                    "message": failure.message,
                }
            )
        except Exception as error:
            log(f"[COLOR] Bỏ qua {reference}: {type(error).__name__}: {error}")
            failed.append(
                {
                    "style_ref": reference,
                    "code": "COLOR_REPORT_STYLE_FAILED",
                    "message": f"{type(error).__name__}: {error}",
                }
            )
    return {"saved": saved, "failed": failed, "cancelled": False}


def select_and_settle(
    page: Page,
    controls: Mapping[str, str],
    label: str,
    value: str,
) -> dict[str, str]:
    """Đặt một select rồi chờ WFX nạp xong các tham số phía dưới."""
    checkpoint()
    control_id = str(controls.get(label) or "").replace(chr(34), "")
    if not control_id:
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY",
            f"Không tìm thấy tham số {label} trên báo cáo.",
        )
    page.locator(f'[id="{control_id}"]').select_option(str(value))
    _wait_postback_settled(page, POSTBACK_TIMEOUT_SECONDS)
    return resolve_controls(page)


def read_cascade(page: Page, values: Mapping[str, str] | None) -> dict:
    """Áp giá trị đã lưu tới cấp còn hợp lệ rồi đọc option của mọi cấp."""
    controls = resolve_controls(page)
    wanted = dict(values or {})
    # prune_selection duyệt cả chuỗi cascade và dừng ở cấp đầu tiên không hợp
    # lệ, nên phải truyền map option đã tích lũy tới cấp hiện tại. Truyền map
    # chỉ có một cấp sẽ làm nó dừng ngay ở cấp trên và luôn trả rỗng.
    options_by_key: dict[str, list] = {}
    levels: dict[str, dict] = {}
    for key in CASCADE_KEYS:
        label = LEVEL_LABELS[key]
        options = read_select_options(page, controls.get(label, ""))
        options_by_key[key] = options
        levels[key] = {"options": options, "value": ""}
        target = prune_selection(wanted, options_by_key).get(key, "")
        if target and target != read_select_value(page, controls.get(label, "")):
            controls = select_and_settle(page, controls, label, target)
            options = read_select_options(page, controls.get(label, ""))
            options_by_key[key] = options
            levels[key] = {"options": options, "value": target}
        elif target:
            levels[key]["value"] = target
        else:
            # Cấp này không áp được thì các cấp dưới là của lựa chọn khác.
            wanted = {}
        levels[key]["value"] = levels[key]["value"] or read_select_value(
            page, controls.get(label, "")
        )
    style_label = LEVEL_LABELS["style_ref"]
    levels["style_ref"] = {
        "options": read_select_options(page, controls.get(style_label, "")),
        "value": read_select_value(page, controls.get(style_label, "")),
    }
    return {"levels": levels}


def load_color_report_options(
    values: Mapping[str, str] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    report = REPORTS[REPORT_ID]
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        _write_log(log, f"[COLOR] Đang tải tham số {report['name']}...")
        report_page = _open_report(page, report)
        _attach_dialog_handler(report_page, log)
        cascade = read_cascade(report_page, values)
        styles = cascade["levels"]["style_ref"]["options"]
        if cascade["levels"]["season"]["value"] and not styles:
            return _result(
                False,
                "COLOR_REPORT_STYLE_LIST_EMPTY",
                "Mùa đang chọn không có BuyerStyleReference nào.",
            )
        _write_log(log, f"[COLOR] Đã đọc {len(styles)} style.")
        return _result(
            True,
            "COLOR_REPORT_OPTIONS_READY",
            f"Đã tải tham số cho {report['name']}.",
            report_id=REPORT_ID,
            report_name=report["name"],
            **cascade,
        )
    except StyleFailure as failure:
        return _result(False, failure.code, failure.message)
    except PlaywrightTimeoutError as error:
        return _result(False, "COLOR_REPORT_OPTIONS_NOT_READY", str(error))
    except Exception as error:
        return _result(
            False, "REPORT_LOAD_FAILED", f"{type(error).__name__}: {error}"
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _view_and_download(page: Page, log: Callable[[str], None]) -> Path:
    """Chạy report rồi trả về file Chrome vừa tải trong Downloads."""
    from wfx_panel.automation.runtime import _user_downloads_dir

    _click_view_report(page)
    _wait_report_ready(page, log)
    file_name = _export_excel(page)
    return _user_downloads_dir() / file_name


def _run_one_style(
    page: Page,
    controls: Mapping[str, str],
    style_ref: str,
    output_dir: Path,
    log: Callable[[str], None],
) -> dict:
    """Một style: chọn ref, chọn StyleCode mới nhất, chạy report, lưu file."""
    current = select_and_settle(
        page, controls, LEVEL_LABELS["style_ref"], style_ref
    )
    style_options = read_select_options(
        page, current.get(STYLE_CODE_LABEL, "")
    )
    picked = pick_style_code(style_options)
    if picked is None:
        raise StyleFailure(
            "COLOR_REPORT_STYLECODE_MISSING",
            f"Không có StyleCode cho {style_ref}.",
        )
    if len(style_options) > 1:
        current = select_and_settle(
            page, current, STYLE_CODE_LABEL, picked["value"]
        )
    # SizeVisibility luôn phải là Yes; chỉ đặt khi đang khác để tránh
    # một postback thừa cho mỗi style.
    size_id = current.get(SIZE_VISIBILITY_LABEL, "")
    if size_id:
        for option in read_select_options(page, size_id):
            if option["label"].strip().casefold() == "yes":
                if read_select_value(page, size_id) != option["value"]:
                    current = select_and_settle(
                        page, current, SIZE_VISIBILITY_LABEL, option["value"]
                    )
                break
    # OCNum giữ nguyên mặc định WFX: nó được nạp lại theo style và
    # mặc định đã chọn hết PO.
    source = _view_and_download(page, log)
    target = unique_target(
        Path(output_dir), safe_file_stem(style_ref, picked["label"])
    )
    try:
        shutil.copy2(source, target)
    except OSError as error:
        raise StyleFailure(
            "COLOR_REPORT_SAVE_FAILED",
            f"Không lưu được file cho {style_ref}: {type(error).__name__}",
        ) from error
    return {
        "style_ref": style_ref,
        "style_code": picked["label"],
        "file_path": str(target),
        "file_name": target.name,
    }


def run_color_report_batch(
    selection: Mapping[str, str],
    style_refs: list[str],
    output_dir: str,
    log: Callable[[str], None] = print,
    progress: Callable[..., None] | None = None,
) -> dict:
    references = [
        str(item).strip() for item in style_refs or () if str(item).strip()
    ]
    if not references:
        return _result(
            False,
            "COLOR_REPORT_NO_STYLE_SELECTED",
            "Hãy chọn ít nhất một BuyerStyleReference trước khi tải.",
        )
    target_dir = Path(str(output_dir or ""))
    if not str(output_dir or "").strip() or not target_dir.is_dir():
        return _result(
            False,
            "COLOR_REPORT_OUTPUT_DIR_REQUIRED",
            "Hãy chọn thư mục lưu báo cáo trước khi tải.",
        )
    report = REPORTS[REPORT_ID]
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        report_page = _open_report(page, report)
        _attach_dialog_handler(report_page, log)
        read_cascade(report_page, selection)
        controls = resolve_controls(report_page)
        outcome = batch_styles(
            references,
            lambda reference: _run_one_style(
                report_page, controls, reference, target_dir, log
            ),
            progress=progress,
            log=log,
        )
        saved = outcome["saved"]
        failed = outcome["failed"]
        if outcome["cancelled"]:
            return _result(
                False,
                "COLOR_REPORT_CANCELLED",
                f"Đã dừng theo yêu cầu. Đã tải {len(saved)}/{len(references)} style.",
                saved=saved,
                failed=failed,
                output_dir=str(target_dir),
            )
        message = f"Đã tải {len(saved)}/{len(references)} style."
        if failed:
            message += f" {len(failed)} style lỗi."
        return _result(
            True,
            "COLOR_REPORT_BATCH_DONE",
            message,
            saved=saved,
            failed=failed,
            output_dir=str(target_dir),
        )
    except Exception as error:
        return _result(
            False, "REPORT_EXPORT_FAILED", f"{type(error).__name__}: {error}"
        )
    finally:
        if playwright is not None:
            playwright.stop()
