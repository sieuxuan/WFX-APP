import ast
import inspect
from pathlib import Path

from wfx_panel.automation import bulk_style


def test_copy_search_rule_uses_article_code_for_swn_and_skn():
    source = Path(bulk_style.__file__).read_text(encoding="utf-8")
    assert 'r"^(?:SWN|SKN)"' in source
    assert "COPY_CODE_XPATH" in source
    assert "COPY_BUYER_REFERENCE_XPATH" in source


def test_copy_flow_selects_costsheet_then_copy_as_variant():
    source = Path(bulk_style.__file__).read_text(encoding="utf-8")
    assert "COPY_COSTSHEET_XPATH" in source
    assert "COPY_AS_VARIANT_XPATH" in source
    assert source.index("costsheet.check()") < source.index("variant.click()")


def test_style_flow_contains_mandatory_defaults():
    defaults = {
        label: value
        for label, value, _ids, _labels in bulk_style.FIXED_STYLE_FIELDS
    }
    assert defaults == {
        "Purchase UOM": "Pcs",
        "Price Per": "Article",
        "Color Definition": "Single Colors",
    }


def test_style_automation_only_saves_when_auto_save_is_enabled():
    source = inspect.getsource(bulk_style.prepare_catalog_style_row)
    assert "titlebarArticle" not in source
    assert "if saved:" in source
    assert "_save_style(context, log)" in source
    assert "requires_manual_save=not saved" in source
    assert bulk_style.SAVE_STYLE_XPATH.endswith("/span/div[1]/a")


def test_group_class_detection_accepts_actual_lowercase_wfx_class():
    catalog_source = (
        Path(bulk_style.__file__).with_name("catalog.py").read_text(encoding="utf-8")
    )
    assert "[...li.classList, ...span.classList]" in catalog_source
    assert "name.toLocaleLowerCase('en') === 'groupnode'" in catalog_source


def test_style_flow_selects_exact_new_toolbar_action():
    source = Path(bulk_style.__file__).read_text(encoding="utf-8")
    assert "def _new_style_link" in source
    assert 'candidate.inner_text().strip().casefold() == "new"' in source


def test_auto_save_click_is_wrapped_in_cancellation_deferred():
    """Stop bấm đúng lúc Save đang chạy không được trả ACTION_CANCELLED.

    ``_wait()`` gọi checkpoint(); nếu click Save nằm ngoài cancellation_deferred,
    người dùng nhận báo đã hủy trong khi WFX đã tạo Style, chạy lại dòng đó là
    sinh Style trùng.
    """
    tree = ast.parse(Path(bulk_style.__file__).read_text(encoding="utf-8"))
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_save_style"
    )
    guarded = [
        node
        for node in ast.walk(target)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and getattr(item.context_expr.func, "id", None)
            == "cancellation_deferred"
            for item in node.items
        )
    ]
    assert guarded, "_save_style phải bọc click Save trong cancellation_deferred()"
    protected = {
        line
        for block in guarded
        for node in ast.walk(block)
        if (line := getattr(node, "lineno", None)) is not None
    }
    clicks = [
        node.lineno
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "click"
    ]
    waits = [
        node.lineno
        for node in ast.walk(target)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_wait"
    ]
    assert clicks and set(clicks) <= protected
    assert waits and set(waits) <= protected


def test_open_style_choice_does_not_block_on_a_new_page_event():
    """WFX tái dùng cửa sổ CatalogDetail nên page event không phát lại.

    Chờ blocking ở đây làm mỗi dòng Tạo Style mất trọn timeout dù popup đã sẵn
    sàng; frame scan mới là nguồn xác nhận và nhận được cả hai trường hợp.
    """
    source = inspect.getsource(bulk_style._open_style_choice)
    assert "context.expect_page(" not in source
    assert "_article_left_frame(context, timeout_s=timeout_s)" in source


def test_option_scan_closes_only_the_popups_it_opened():
    """Lượt quét chỉ đọc option; form New Style điền dở không được để lại."""
    source = inspect.getsource(bulk_style.scan_catalog_style_options)
    assert "known_pages = set(context.pages)" in source
    assert "_close_pages_opened_since(context, known_pages)" in source
    assert source.index("finally:") < source.index(
        "_close_pages_opened_since(context, known_pages)"
    )
    cleanup = inspect.getsource(bulk_style._close_pages_opened_since)
    assert "if page in known:" in cleanup
    assert "continue" in cleanup


def test_prepare_style_row_keeps_its_popup_for_the_user_to_review():
    """Dòng đang chuẩn bị là kết quả người dùng cần xem và tự Save."""
    source = inspect.getsource(bulk_style.prepare_catalog_style_row)
    assert "_close_pages_opened_since" not in source
