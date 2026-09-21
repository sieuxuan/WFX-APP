"""Điểm vào: quét dropdown Style và chuẩn bị từng dòng.

Lượt quét để lại một form New Style điền dở nên phải đóng đúng những popup do
chính nó mở — kể cả khi lỗi hoặc bị Stop. Popup của prepare_catalog_style_row
thì giữ nguyên vì đó là kết quả user cần kiểm tra và tự Save."""

from __future__ import annotations

from typing import Any

from wfx_panel.automation._common import (
    Callable,
    Frame,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.bulk_style.constants import (
    _CLICK_COPY_RESULT_JS,
    _COPY_RESULTS_JS,
    COPY_ARTICLE_CODE_NAME_XPATH,
    COPY_AS_VARIANT_XPATH,
    COPY_COSTSHEET_XPATH,
    COPY_SEARCH_XPATH,
    NEW_STYLE_XPATH,
    STYLE_FIELDS,
)
from wfx_panel.automation.bulk_style.editor import (
    _field_options_with_wait,
    _fill_style_editor,
    _read_style_options,
    _save_style,
    _set_field,
)
from wfx_panel.automation.bulk_style.frames import (
    _close_pages_opened_since,
    _copy_result_frame,
    _new_style_link,
    _open_style_choice,
    _style_editor_frame,
)
from wfx_panel.automation.catalog import open_catalog_folder
from wfx_panel.automation.modules import _active_wfx_page


def scan_catalog_style_options(
    category_value: str,
    group_id: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét dropdown Style và quan hệ Product Group → Sub-category, không Save."""
    opened = open_catalog_folder("Apparel", category_value, str(group_id), log)
    if not opened.get("ok"):
        return opened
    if str((opened.get("folder") or {}).get("kind") or "") != "group":
        return _result(False, "STYLE_GROUP_REQUIRED", "Vị trí đã chọn không phải Group.")
    playwright: Playwright | None = None
    context: Any = None
    known_pages: set = set()
    try:
        playwright = sync_playwright().start()
        browser, _page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        known_pages = set(context.pages)
        _owner, _frame, new_link = _new_style_link(context, 12)
        # Anchor href="#" dùng chung class với toolbar khác; click chính TD có
        # onclick="New()" mới ổn định trên WFX cũ.
        choice_frame = _open_style_choice(context, new_link)
        choice_frame.locator(f"xpath={NEW_STYLE_XPATH}").first.evaluate(
            "element => element.click()"
        )
        editor = _style_editor_frame(context)
        fields: dict[str, list[dict[str, str]]] = {}
        specs = {key: (label, ids, labels) for key, label, ids, labels in STYLE_FIELDS}
        fields["material_type"] = _read_style_options(
            editor, specs["material_type"][1]
        )
        if not fields.get("material_type"):
            fields["material_type"] = [
                {"label": "KNIT", "value": "KNIT"},
                {"label": "WOVEN", "value": "WOVEN"},
            ]
        folder_label = str((opened.get("folder") or {}).get("path_label") or "")
        material = next(
            (
                option
                for option in fields["material_type"]
                if option["label"].casefold() in folder_label.casefold()
            ),
            fields["material_type"][0],
        )
        _set_field(
            context,
            specs["material_type"][0],
            material.get("value") or material["label"],
            specs["material_type"][1],
            specs["material_type"][2],
            lambda _message: None,
        )
        for key in ("buyer", "division"):
            label, ids, labels = specs[key]
            options = _field_options_with_wait(context, ids)
            fields[key] = options
            if options:
                first = options[0]
                _set_field(
                    context,
                    label,
                    first.get("value") or first["label"],
                    ids,
                    labels,
                    lambda _message: None,
                )

        product_spec = ("product_group", *specs["product_group"])
        subcategory_spec = ("sub_category", *specs["sub_category"])
        fields["product_group"] = _field_options_with_wait(
            context, product_spec[2]
        )
        dependencies: dict[str, list[dict[str, str]]] = {}
        for option in fields.get("product_group", [])[:500]:
            label = option["label"]
            try:
                _set_field(
                    context,
                    product_spec[1],
                    option.get("value") or label,
                    product_spec[2],
                    product_spec[3],
                    lambda _message: None,
                )
                editor = _style_editor_frame(context)
                values = _field_options_with_wait(context, subcategory_spec[2])
                if values:
                    dependencies[label] = values
            except (RuntimeError, PlaywrightError, PlaywrightTimeoutError):
                continue
        if fields["product_group"]:
            first_product = fields["product_group"][0]
            _set_field(
                context,
                product_spec[1],
                first_product.get("value") or first_product["label"],
                product_spec[2],
                product_spec[3],
                lambda _message: None,
            )
            first_subcategories = dependencies.get(first_product["label"], [])
            if first_subcategories:
                first_subcategory = first_subcategories[0]
                _set_field(
                    context,
                    subcategory_spec[1],
                    first_subcategory.get("value") or first_subcategory["label"],
                    subcategory_spec[2],
                    subcategory_spec[3],
                    lambda _message: None,
                )
        for key in ("color_card", "size_range", "season"):
            fields[key] = _field_options_with_wait(context, specs[key][1])
        missing = [
            label
            for key, label in (
                ("buyer", "Buyer"),
                ("product_group", "Product Group"),
                ("season", "Season"),
            )
            if not fields.get(key)
        ]
        if missing:
            raise RuntimeError(
                "STYLE_OPTIONS_INCOMPLETE:" + ", ".join(missing)
            )
        _write_log(
            log,
            "[STYLE OPTIONS] Đã quét "
            f"{sum(len(values) for values in fields.values())} lựa chọn và "
            f"{len(dependencies)} nhóm Sub-category; không Save.",
        )
        return _result(
            True,
            "STYLE_OPTIONS_SCANNED",
            "Đã cập nhật danh sách dropdown Style từ WFX.",
            fields=fields,
            subcategories_by_product_group=dependencies,
            group_id=str(group_id),
        )
    except RuntimeError as exc:
        code = str(exc).partition(":")[0]
        if code in {"CHROME_CLOSED", "NOT_LOGGED_IN"}:
            message = (
                "Trình duyệt làm việc chưa được mở."
                if code == "CHROME_CLOSED"
                else "Phiên chưa đăng nhập hoặc đã hết hạn."
            )
            return _result(False, code, message)
        message = f"Không quét được dropdown Style: RuntimeError: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_OPTIONS_SCAN_FAILED", message)
    except Exception as exc:
        message = f"Không quét được dropdown Style: {type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_OPTIONS_SCAN_FAILED", message)
    finally:
        # Lượt quét chỉ đọc option; form New Style bị điền dở trong quá trình
        # quét không phải kết quả người dùng cần, phải dọn kể cả khi lỗi/Stop.
        if context is not None:
            _close_pages_opened_since(context, known_pages)
        if playwright is not None:
            playwright.stop()


def _prepare_copy(
    context: Any,
    frame: Frame,
    row: dict[str, Any],
    copy_choice: int | None,
    log: Callable[[str], None],
) -> dict[str, Any] | None:
    source = str(row.get("style_copy") or "").strip()
    search_input = frame.locator(
        f"xpath={COPY_ARTICLE_CODE_NAME_XPATH}"
    ).first
    search_input.wait_for(state="visible", timeout=5_000)
    search_input.fill(source)
    search = frame.locator(f"xpath={COPY_SEARCH_XPATH}").first
    search.wait_for(state="visible", timeout=5_000)
    search.click()
    _write_log(log, "[STYLE COPY] Đang tìm bằng ArticleCode/Name.")
    result_frame = _copy_result_frame(context)
    choices = list(result_frame.evaluate(_COPY_RESULTS_JS) or [])
    if not choices:
        raise RuntimeError("STYLE_COPY_NOT_FOUND")
    if len(choices) > 1 and copy_choice is None:
        return _result(
            True,
            "STYLE_COPY_MULTIPLE_RESULTS",
            f"Có {len(choices)} Style nguồn. Hãy chọn đúng một Style trong app.",
            choices=choices,
            source_row=int(row.get("source_row") or 0),
        )
    # Lựa chọn rõ ràng của người dùng luôn phải được xác thực lại với tập kết
    # quả HIỆN TẠI. Trước đây nhánh `len(choices) == 1` bỏ qua `copy_choice`,
    # nên khi dữ liệu WFX đổi giữa lượt chọn và lượt xác nhận và tập kết quả co
    # lại còn một Style KHÁC, flow vẫn Copy Style đó mà không báo gì.
    if copy_choice is not None:
        selected_index = int(copy_choice)
    elif len(choices) == 1:
        selected_index = int(choices[0]["choice_index"])
    else:
        selected_index = -1
    allowed = {int(choice["choice_index"]) for choice in choices}
    if selected_index not in allowed:
        raise RuntimeError("STYLE_COPY_CHOICE_INVALID")
    if not result_frame.evaluate(_CLICK_COPY_RESULT_JS, selected_index):
        raise RuntimeError("STYLE_COPY_RESULT_DETACHED")

    costsheet = result_frame.locator(f"xpath={COPY_COSTSHEET_XPATH}").first
    costsheet.wait_for(state="attached", timeout=5_000)
    if not costsheet.is_checked():
        costsheet.check()
    variant = result_frame.locator(f"xpath={COPY_AS_VARIANT_XPATH}").first
    variant.wait_for(state="visible", timeout=5_000)
    variant.click()
    _write_log(log, "[STYLE COPY] Đã chọn CostSheet và Copy as Variant.")
    return None


def prepare_catalog_style_row(
    category_value: str,
    group_id: str,
    row: dict[str, Any],
    copy_choice: int | None = None,
    auto_save: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chuẩn bị đúng một Style; chỉ Save khi ``auto_save`` được bật rõ ràng."""
    kind = str(row.get("type") or "").strip().casefold()
    if kind not in {"new", "copy"}:
        return _result(False, "STYLE_TYPE_INVALID", "Type phải là New hoặc Copy.")
    group_id = str(group_id or "").strip()
    if not group_id.isdigit():
        return _result(
            False,
            "STYLE_GROUP_REQUIRED",
            "Hãy chọn đúng một Group Apparel trước khi chuẩn bị Style.",
        )

    opened = open_catalog_folder("Apparel", category_value, group_id, log)
    if not opened.get("ok"):
        return opened
    if str((opened.get("folder") or {}).get("kind") or "") != "group":
        return _result(
            False,
            "STYLE_GROUP_REQUIRED",
            "Vị trí đã chọn không phải Group. Hãy chọn một Group Apparel.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        _owner, _frame, new_link = _new_style_link(context, 12)
        choice_frame = _open_style_choice(context, new_link)
        _write_log(log, "[STYLE] Đã mở New trong Group đã chọn.")

        if kind == "new":
            new_button = choice_frame.locator(f"xpath={NEW_STYLE_XPATH}").first
            new_button.evaluate("element => element.click()")
        else:
            pending = _prepare_copy(
                context,
                choice_frame,
                row,
                copy_choice,
                log,
            )
            if pending is not None:
                return pending

        _style_editor_frame(context)
        filled = _fill_style_editor(context, row, log)
        saved = bool(auto_save)
        if saved:
            _save_style(context, log)
        page.bring_to_front()
        source_row = int(row.get("source_row") or 0)
        return _result(
            True,
            "STYLE_FORM_READY",
            (
                f"Đã chuẩn bị dòng {source_row} trên WFX"
                + (" và Save tự động." if saved else " và dừng trước Save. ")
                + ("" if saved else "Hãy kiểm tra rồi tự bấm Save.")
            ),
            source_row=source_row,
            style_type="New" if kind == "new" else "Copy",
            filled_fields=filled,
            requires_manual_save=not saved,
            saved=saved,
        )
    except RuntimeError as exc:
        raw = str(exc)
        code, _, detail = raw.partition(":")
        messages = {
            # PanelAPI khớp đúng hai mã này để tự mở lại trình duyệt và đăng
            # nhập lại. Gộp chúng vào STYLE_PREPARE_FAILED là mất hẳn cơ chế
            # khôi phục, lại còn gửi telemetry cho một tình huống bình thường.
            "CHROME_CLOSED": "Trình duyệt làm việc chưa được mở.",
            "NOT_LOGGED_IN": "Phiên chưa đăng nhập hoặc đã hết hạn.",
            "STYLE_COPY_NOT_FOUND": "Không tìm thấy Style nguồn để Copy.",
            "STYLE_COPY_CHOICE_INVALID": "Lựa chọn Style nguồn không còn hợp lệ.",
            "STYLE_COPY_RESULT_DETACHED": "Dòng Style nguồn đã đổi trước khi chọn.",
            "STYLE_REQUIRED_FIELD_MISSING": (
                f"Dòng New còn thiếu trường bắt buộc: {detail}."
            ),
            "STYLE_FIELD_NOT_AVAILABLE": (
                f"Không điền được trường {detail.split(':', 1)[0] or 'Style'} "
                "trên form WFX."
            ),
        }
        if code in messages:
            return _result(False, code, messages[code])
        message = f"Không chuẩn bị được Style: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_PREPARE_FAILED", message)
    except PlaywrightTimeoutError as exc:
        message = f"Màn hình Tạo Style chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_FORM_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_PREPARE_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
