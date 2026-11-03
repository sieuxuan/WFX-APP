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
    _wait,
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
REPORT_NAME = "ColorCombination Style Wise"
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
OC_NUM_LABEL = "OCNum"

# ReportViewer không tạo Select All khi chỉ có một OC. Nhận diện theo nhãn/
# handler thay vì bỏ checkbox đầu tiên (đó có thể là OC duy nhất).
_OC_ROWS_JS = r"""root => [...root.querySelectorAll('input[type="checkbox"], input[type="radio"]')]
  .map(element => {
    const label = ([...(element.labels || [])].map(label => label.textContent).join(' ')
      || element.parentElement?.textContent || '').replace(/\s+/g, ' ').trim();
    return {
      value: element.id, label, selected: element.checked,
      select_all: /^\(?select all\)?$/i.test(label)
        || /OnSelectAllClick/.test(element.getAttribute('onclick') || ''),
    };
  }).filter(option => option.value && option.label)"""

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


def clean_style_ref_options(
    options: list[Mapping[str, str]] | None,
) -> list[dict[str, str]]:
    """Bỏ placeholder nhưng giữ mọi record, kể cả label bị lặp."""
    cleaned: list[dict[str, str]] = []
    for raw in options or ():
        option = dict(raw or {})
        value = str(option.get("value") or "").strip()
        label = str(option.get("label") or "").replace("\xa0", " ").strip()
        normalized = " ".join(label.split()).casefold()
        if not value or normalized.startswith("<select"):
            continue
        cleaned.append({"value": value, "label": label})
    return cleaned


def unique_target(directory: Path, stem: str, suffix: str = ".xlsx") -> Path:
    """Không ghi đè file đã có: thêm hậu tố (2), (3)..."""
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
            str(option.get("value") or "") for option in options_by_key.get(key) or ()
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
    skipped: list[dict] = []
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
            return {
                "saved": saved,
                "failed": failed,
                "skipped": skipped,
                "cancelled": True,
            }
        except StyleFailure as failure:
            log(f"[COLOR] Bỏ qua {reference}: {failure.message}")
            (skipped if failure.code == "COLOR_REPORT_OC_NOT_FOUND" else failed).append(
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
    return {"saved": saved, "failed": failed, "skipped": skipped, "cancelled": False}


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
        # Chỉ phản hồi lựa chọn mà app thực sự gửi lên. ReportViewer đôi khi
        # tự chọn option đầu tiên sau postback; nếu trả giá trị đó về UI thì
        # app hiểu nhầm user đã chọn Season và kiểm tra style quá sớm.
        levels[key]["value"] = target
    style_label = LEVEL_LABELS["style_ref"]
    levels["style_ref"] = {
        "options": clean_style_ref_options(
            read_select_options(page, controls.get(style_label, ""))
        ),
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
                report_id=REPORT_ID,
                report_name=report["name"],
                **cascade,
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
        return _result(False, "REPORT_LOAD_FAILED", f"{type(error).__name__}: {error}")
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


def _prepare_style(
    page: Page,
    controls: Mapping[str, str],
    style_ref: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Chọn ref, StyleCode mới nhất và SizeVisibility trước khi xuất."""
    current = select_and_settle(page, controls, LEVEL_LABELS["style_ref"], style_ref)
    style_options = read_select_options(page, current.get(STYLE_CODE_LABEL, ""))
    picked = pick_style_code(style_options)
    if picked is None:
        raise StyleFailure(
            "COLOR_REPORT_STYLECODE_MISSING",
            f"Không có StyleCode cho {style_ref}.",
        )
    if len(style_options) > 1:
        current = select_and_settle(page, current, STYLE_CODE_LABEL, picked["value"])
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
    return current, picked


def read_parameter_choices(page: Page, label: str) -> dict:
    """Đọc select/popup ReportViewer; đối chiếu nhãn OCNum và OC Num như nhau."""
    normalized = re.sub(r"[\s_]", "", label).casefold()
    controls = resolve_controls(page)
    key = next(
        (
            value
            for name, value in controls.items()
            if re.sub(r"[\s_]", "", name).casefold() == normalized
        ),
        "",
    )
    if key and page.locator(f'[id="{key}"]').evaluate(
        "element => element.tagName === 'SELECT'"
    ):
        options = clean_style_ref_options(read_select_options(page, key))
        values = page.locator(f'[id="{key}"]').evaluate(
            "element => [...element.selectedOptions].map(option => option.value)"
        )
        return {"key": key, "options": options, "value": values, "native": True}
    button_id = key.removesuffix("_txtValue") + "_ddDropDownButton"
    button = page.locator(f'[id="{button_id}"]')
    if not key or not button.count() or not button.is_enabled():
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY",
            f"Danh sách {label} chưa sẵn sàng. Hãy tải lại tham số báo cáo.",
        )
    root_id = key.removesuffix("_txtValue") + "_divDropDown"
    root = page.locator(f'[id="{root_id}"]')
    # Khi Chrome bị cửa sổ khác che, click chờ animation frame có thể treo.
    # Gọi đúng handler popup; vẫn phát click event và đối chiếu sau postback.
    if not root.evaluate("element => getComputedStyle(element).display !== 'none'"):
        button.evaluate("element => element.click()")
    try:
        _wait(page, 100)
        rows = [row for row in root.evaluate(_OC_ROWS_JS) if not row["select_all"]]
    finally:
        if root.evaluate("element => getComputedStyle(element).display !== 'none'"):
            button.evaluate("element => element.click()")
        _wait_postback_settled(page, POSTBACK_TIMEOUT_SECONDS)
    return {
        "key": key,
        "options": [{"value": row["value"], "label": row["label"]} for row in rows],
        "value": [row["value"] for row in rows if row["selected"]],
    }


def _read_oc_parameter(page: Page) -> dict:
    return read_parameter_choices(page, OC_NUM_LABEL)


def _set_oc_parameter(page: Page, parameter: dict, values: list[str]) -> None:
    if parameter.get("native"):
        page.locator(f'[id="{parameter["key"]}"]').select_option(values)
        _wait_postback_settled(page, POSTBACK_TIMEOUT_SECONDS)
        return
    stem = parameter["key"].removesuffix("_txtValue")
    button = page.locator(f'[id="{stem}_ddDropDownButton"]')
    root = page.locator(f'[id="{stem}_divDropDown"]')
    if not root.evaluate("element => getComputedStyle(element).display !== 'none'"):
        button.evaluate("element => element.click()")
    try:
        _wait(page, 100)
        root.evaluate(
            """(root, values) => {
              const rows = ("""
            + _OC_ROWS_JS
            + """)(root);
              const wanted = new Set(values);
              const all = rows.find(row => row.select_all);
              if (all?.selected) root.ownerDocument.getElementById(all.value).click();
              for (const row of rows.filter(row => !row.select_all)) {
                const box = root.ownerDocument.getElementById(row.value);
                if (box.type === 'radio') {
                  if (wanted.has(box.id) && !box.checked) box.click();
                } else if (box.checked !== wanted.has(box.id)) box.click();
              }
            }""",
            values,
        )
    finally:
        if root.evaluate("element => getComputedStyle(element).display !== 'none'"):
            button.evaluate("element => element.click()")
        _wait_postback_settled(page, POSTBACK_TIMEOUT_SECONDS)


def _select_ocnums(page: Page, labels: list[str] | None) -> None:
    """Resolve lại ID sau postback; None chọn tất cả OC để xuất theo style."""
    parameter = _read_oc_parameter(page)
    options = parameter["options"]
    if not options:
        raise StyleFailure("COLOR_REPORT_OC_NOT_FOUND", "Không tìm thấy OC.")
    wanted = (
        options
        if labels is None
        else [option for option in options if option["label"] in labels]
    )
    if not wanted or (labels is not None and len(wanted) != len(labels)):
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY",
            "OCNum cần tải không còn trong danh sách của style. Hãy tải lại tham số.",
        )
    values = [option["value"] for option in wanted]
    if set(parameter.get("value") or []) != set(values):
        _set_oc_parameter(page, parameter, values)
    confirmed = _read_oc_parameter(page)
    selected = set(confirmed.get("value") or [])
    actual = [
        option["label"]
        for option in confirmed["options"]
        if option["value"] in selected
    ]
    if sorted(actual) != sorted(option["label"] for option in wanted):
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY",
            "WFX chưa nhận đúng lựa chọn OCNum. Hãy thử tải lại báo cáo.",
        )


def _download_style_report(
    page: Page,
    output_dir: Path,
    log: Callable[[str], None],
    display_ref: str,
    style_code: str,
    oc_num: str = "",
) -> dict:
    source = _view_and_download(page, log)
    stem = safe_file_stem(display_ref, style_code)
    if oc_num:
        stem = safe_file_stem(stem, oc_num)
    target = unique_target(Path(output_dir), stem)
    try:
        shutil.copy2(source, target)
    except OSError as error:
        raise StyleFailure(
            "COLOR_REPORT_SAVE_FAILED",
            f"Không lưu được file cho {display_ref}: {type(error).__name__}",
        ) from error
    return {
        "style_ref": display_ref,
        "style_code": style_code,
        "file_path": str(target),
        "file_name": target.name,
        **({"oc_num": oc_num} if oc_num else {}),
    }


def _run_one_style(
    page: Page,
    controls: Mapping[str, str],
    style_ref: str,
    output_dir: Path,
    log: Callable[[str], None],
    style_ref_label: str | None = None,
) -> dict:
    current, picked = _prepare_style(page, controls, style_ref)
    # Lượt trước có thể đã tải một OC trên cùng tab report. Chọn lại toàn bộ
    # để chế độ theo style luôn gộp đủ OC, kể cả WFX giữ lựa chọn cũ.
    if current.get(OC_NUM_LABEL):
        _select_ocnums(page, None)
    display_ref = str(style_ref_label or style_ref).strip() or str(style_ref)
    return _download_style_report(page, output_dir, log, display_ref, picked["label"])


def _batch_ocnums(
    page: Page,
    references: list[str],
    style_labels: Mapping[str, str],
    output_dir: Path,
    log: Callable[[str], None],
    progress: Callable[..., None] | None,
    retry_ocnums: Mapping[str, list[str]],
) -> dict:
    """Giữ kết quả từng OC ngay khi tải xong, kể cả lỗi hoặc Stop giữa style."""
    saved: list[dict] = []
    failed: list[dict] = []
    skipped: list[dict] = []

    def record_failure(item: dict, error: Exception) -> None:
        if (
            isinstance(error, StyleFailure)
            and error.code == "COLOR_REPORT_OC_NOT_FOUND"
        ):
            _write_log(log, f"[COLOR] {item['style_ref']}: Không tìm thấy OC, bỏ qua.")
            skipped.append({**item, "code": error.code, "message": error.message})
        else:
            failed.append({**item, **_oc_failure(error, log)})

    try:
        for index, reference in enumerate(references, start=1):
            checkpoint()
            display_ref = style_labels.get(reference) or reference
            item = {"style_ref": display_ref, "style_ref_value": reference}
            try:
                if progress:
                    progress(
                        "style",
                        f"Đang đọc OCNum {display_ref}… {index}/{len(references)}",
                        index,
                        len(references),
                    )
                _current, picked = _prepare_style(
                    page, resolve_controls(page), reference
                )
                options = _read_oc_parameter(page)["options"]
                if not options:
                    raise StyleFailure(
                        "COLOR_REPORT_OC_NOT_FOUND", "Không tìm thấy OC."
                    )
                labels = list(dict.fromkeys(option["label"] for option in options))
                if reference in retry_ocnums:
                    labels = list(dict.fromkeys(retry_ocnums[reference]))
            except AutomationCancelled:
                raise
            except Exception as error:
                record_failure(item, error)
                continue
            for oc_index, label in enumerate(labels, start=1):
                checkpoint()
                oc_item = {**item, "oc_num": label}
                try:
                    if progress:
                        progress(
                            "oc_num",
                            f"Đang tải {display_ref} · {label} ({oc_index}/{len(labels)} OC)… {index}/{len(references)}",
                            index,
                            len(references),
                        )
                    _select_ocnums(page, [label])
                    saved.append(
                        {
                            **_download_style_report(
                                page,
                                output_dir,
                                log,
                                display_ref,
                                picked["label"],
                                label,
                            ),
                            "style_ref_value": reference,
                        }
                    )
                except AutomationCancelled:
                    raise
                except Exception as error:
                    record_failure(oc_item, error)
    except AutomationCancelled:
        return {"saved": saved, "failed": failed, "skipped": skipped, "cancelled": True}
    return {"saved": saved, "failed": failed, "skipped": skipped, "cancelled": False}


def _oc_failure(error: Exception, log: Callable[[str], None]) -> dict:
    _write_log(log, f"[COLOR] OCNum: {type(error).__name__}: {error}")
    return {
        "code": error.code
        if isinstance(error, StyleFailure)
        else "COLOR_REPORT_STYLE_FAILED",
        "message": error.message
        if isinstance(error, StyleFailure)
        else f"{type(error).__name__}: {error}",
    }


def run_color_report_batch(
    selection: Mapping[str, str],
    style_refs: list[str],
    output_dir: str,
    log: Callable[[str], None] = print,
    progress: Callable[..., None] | None = None,
) -> dict:
    export_mode = str(selection.get("export_mode") or "style")
    if export_mode not in {"style", "oc_num"}:
        return _result(
            False, "REPORT_PARAMETERS_INVALID", "Hãy chọn xuất theo Style hoặc OCNum."
        )
    references = [str(item).strip() for item in style_refs or () if str(item).strip()]
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
        cascade = read_cascade(report_page, selection)
        style_labels = {
            str(option.get("value")): str(option.get("label") or "")
            for option in cascade["levels"]["style_ref"]["options"]
        }
        controls = resolve_controls(report_page)
        outcome = (
            _batch_ocnums(
                report_page,
                references,
                style_labels,
                target_dir,
                log,
                progress,
                selection.get("retry_ocnums") or {},
            )
            if export_mode == "oc_num"
            else batch_styles(
                references,
                lambda reference: _run_one_style(
                    report_page,
                    controls,
                    reference,
                    target_dir,
                    log,
                    style_labels.get(reference),
                ),
                progress=progress,
                log=log,
            )
        )
        saved = outcome["saved"]
        failed = outcome["failed"]
        skipped = outcome.get("skipped", [])
        for item in skipped:
            if not item.get("style_ref_value"):
                item["style_ref_value"] = item["style_ref"]
                item["style_ref"] = style_labels.get(
                    item["style_ref"], item["style_ref"]
                )
        if export_mode == "oc_num":
            message = f"Đã tải {len(saved)} báo cáo theo OCNum."
            if failed:
                message += f" {len(failed)} mục lỗi."
        else:
            message = f"Đã tải {len(saved)}/{len(references)} style."
            if failed:
                message += f" {len(failed)} style lỗi."
        if skipped:
            message += f" Không tìm thấy OC ở {len(skipped)} style; đã bỏ qua."
        if outcome["cancelled"]:
            return _result(
                False,
                "COLOR_REPORT_CANCELLED",
                f"Đã dừng theo yêu cầu. {message}",
                saved=saved,
                failed=failed,
                skipped=skipped,
                output_dir=str(target_dir),
                export_mode=export_mode,
            )
        if not saved and not failed and skipped:
            return _result(
                True,
                "COLOR_REPORT_OC_NOT_FOUND",
                f"Không tìm thấy OC cho {len(skipped)} style đã chọn.",
                saved=saved,
                failed=failed,
                skipped=skipped,
                output_dir=str(target_dir),
                export_mode=export_mode,
            )
        return _result(
            bool(saved),
            "COLOR_REPORT_BATCH_DONE"
            if saved
            else (failed[0]["code"] if failed else "REPORT_EXPORT_FAILED"),
            message if saved else f"Không tải được báo cáo nào. {message}",
            saved=saved,
            failed=failed,
            skipped=skipped,
            output_dir=str(target_dir),
            export_mode=export_mode,
        )
    except StyleFailure as failure:
        return _result(False, failure.code, failure.message)
    except PlaywrightTimeoutError as error:
        return _result(False, "COLOR_REPORT_OPTIONS_NOT_READY", str(error))
    except Exception as error:
        return _result(
            False, "REPORT_EXPORT_FAILED", f"{type(error).__name__}: {error}"
        )
    finally:
        if playwright is not None:
            playwright.stop()
