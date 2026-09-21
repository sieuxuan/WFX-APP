"""Tìm Supplier trong một Category hoặc quét tất cả Category.

Quét tất cả phải TIẾP TỤC khi một Category lỗi, báo rõ đây là kết quả một phần
và đếm tổng trước khi giới hạn danh sách hiển thị."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from wfx_panel.automation._common import (
    Any,
    Callable,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _first_line,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.directory.company_query import _filter_company_rows
from wfx_panel.automation.directory.supplier_open import _open_supplier_category_on_page
from wfx_panel.automation.modules import _active_wfx_page


@dataclass(frozen=True)
class _SupplierSearchRequest:
    page: Page
    module_xpath: str
    categories: Mapping[str, str]
    query: str
    log: Callable[[str], None]


@dataclass
class _SupplierSearchState:
    checked: list[str] = dataclass_field(default_factory=list)
    found_by_category: list[dict[str, Any]] = dataclass_field(
        default_factory=list
    )
    failed_categories: list[dict[str, str]] = dataclass_field(
        default_factory=list
    )


def _scan_supplier_categories(
    request: _SupplierSearchRequest,
) -> _SupplierSearchState:
    state = _SupplierSearchState()
    categories = request.categories
    for category_name, category_value in categories.items():
        state.checked.append(category_name)
        _write_log(
            request.log,
            f"[SUPPLIER FIND] Đang kiểm tra {category_name}...",
        )
        try:
            frame = _open_supplier_category_on_page(
                request.page,
                request.module_xpath,
                category_name,
                category_value,
                request.log,
            )
            _frame, company_state = _filter_company_rows(
                request.page,
                frame,
                request.query,
                request.log,
                "supplier",
            )
        except (PlaywrightError, PlaywrightTimeoutError) as error:
            detail = _first_line(error)
            state.failed_categories.append(
                {"category": category_name, "detail": detail}
            )
            _write_log(
                request.log,
                f"[SUPPLIER FIND] Bỏ qua {category_name}: {detail}",
            )
            continue
        matches = list(
            dict.fromkeys(
                row["company"]
                for row in company_state["rows"]
                if row["matches"]
            )
        )
        if not matches:
            continue
        state.found_by_category.append(
            {
                "category": category_name,
                "count": len(matches),
                "matches": matches[:10],
            }
        )
        _write_log(
            request.log,
            f"[SUPPLIER FIND] {category_name}: {len(matches)} kết quả.",
        )
    return state


def _restore_first_supplier_result(
    request: _SupplierSearchRequest,
    state: _SupplierSearchState,
) -> None:
    if not state.found_by_category:
        return
    first_category = str(state.found_by_category[0]["category"])
    if state.checked[-1] == first_category:
        return
    try:
        first_frame = _open_supplier_category_on_page(
            request.page,
            request.module_xpath,
            first_category,
            request.categories[first_category],
            request.log,
        )
        _filter_company_rows(
            request.page,
            first_frame,
            request.query,
            request.log,
            "supplier",
        )
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        _write_log(
            request.log,
            "[SUPPLIER FIND] Đã tổng hợp đủ kết quả nhưng không "
            f"đưa được WFX về Category đầu tiên: {error}",
        )


def _supplier_search_result(
    query: str,
    state: _SupplierSearchState,
) -> dict[str, Any]:
    if state.found_by_category:
        first = state.found_by_category[0]
        first_category = str(first["category"])
        category_names = [
            str(item["category"]) for item in state.found_by_category
        ]
        total_matches = sum(
            int(item["count"]) for item in state.found_by_category
        )
        partial = bool(state.failed_categories)
        return _result(
            True,
            "SUPPLIER_FOUND_PARTIAL" if partial else "SUPPLIER_FOUND",
            f"Đã tìm thấy {total_matches} kết quả trong "
            f"{len(state.found_by_category)} Category: "
            f"{', '.join(category_names)}. "
            f"Đang hiển thị kết quả ở {first_category}."
            + (
                f" Có {len(state.failed_categories)} Category chưa kiểm tra được."
                if partial
                else ""
            ),
            category=first_category,
            categories=category_names,
            matches=first["matches"],
            total_matches=total_matches,
            matches_by_category=state.found_by_category,
            checked_categories=state.checked,
            failed_categories=state.failed_categories,
        )
    if state.failed_categories:
        # Không Category nào chạy được thì "không tìm thấy kết quả" là sai sự
        # thật: app chưa kiểm tra được gì. Người dùng đọc câu đó sẽ kết luận
        # nhà cung cấp chưa tồn tại rồi đi tạo trùng.
        if len(state.failed_categories) >= len(state.checked):
            return _result(
                False,
                "SUPPLIER_SEARCH_PARTIAL",
                f"Chưa kiểm tra được Category nào trong {len(state.checked)} "
                "Category. Hãy kiểm tra trình duyệt làm việc rồi tìm lại.",
                checked_categories=state.checked,
                failed_categories=state.failed_categories,
            )
        return _result(
            False,
            "SUPPLIER_SEARCH_PARTIAL",
            "Không tìm thấy kết quả trong các Category đã kiểm tra, "
            f"nhưng có {len(state.failed_categories)} Category bị lỗi.",
            checked_categories=state.checked,
            failed_categories=state.failed_categories,
        )
    return _result(
        False,
        "SUPPLIER_NOT_FOUND",
        f"Không tìm thấy Supplier chứa “{query}” trong "
        f"{len(state.checked)} Category.",
        checked_categories=state.checked,
    )


def find_supplier_across_categories(
    module_xpath: str,
    categories: dict[str, str],
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập tên Supplier cần tìm.")
    playwright: Playwright | None = None
    state = _SupplierSearchState()
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        request = _SupplierSearchRequest(
            page=page,
            module_xpath=module_xpath,
            categories=categories,
            query=query,
            log=log,
        )
        state = _scan_supplier_categories(request)
        _restore_first_supplier_result(request, state)
        return _supplier_search_result(query, state)
    except PlaywrightTimeoutError as exc:
        return _result(
            False,
            "SUPPLIER_SEARCH_NOT_READY",
            _first_line(exc),
            checked_categories=state.checked,
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        return _result(
            False,
            "SUPPLIER_SEARCH_FAILED",
            f"{type(exc).__name__}: {_first_line(exc)}",
            checked_categories=state.checked,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def find_supplier_in_category(
    module_xpath: str,
    category_name: str,
    category_value: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở/đổi Category một lần rồi tìm Supplier ngay trong Category đó."""
    query = query.strip()
    if not query:
        return _result(
            False,
            "QUERY_REQUIRED",
            "Vui lòng nhập tên Supplier cần tìm.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_supplier_category_on_page(
            page,
            module_xpath,
            category_name,
            category_value,
            log,
        )
        _frame, state = _filter_company_rows(
            page,
            frame,
            query,
            log,
            "supplier",
        )
        # Khử trùng giống nhánh quét tất cả Category: WFX render lại cùng một
        # công ty ở cột ghim, đếm hai lần là báo sai số kết quả.
        matches = list(
            dict.fromkeys(
                row["company"]
                for row in state["rows"]
                if row["matches"]
            )
        )
        if not matches:
            return _result(
                False,
                "SUPPLIER_NOT_FOUND",
                f"Không tìm thấy Supplier trong {category_name}: {query}.",
                category=category_name,
            )
        # Đếm tổng TRƯỚC khi cắt danh sách hiển thị, giống nhánh quét tất cả
        # Category: cắt ở 10 mà không kèm tổng thì user tưởng chỉ có 10.
        return _result(
            True,
            "SUPPLIER_FOUND",
            f"Đã tìm thấy {len(matches)} Supplier trong Category "
            f"{category_name}.",
            category=category_name,
            matches=matches[:10],
            total_matches=len(matches),
            checked_categories=[category_name],
        )
    except PlaywrightTimeoutError as exc:
        return _result(
            False,
            "SUPPLIER_SEARCH_NOT_READY",
            _first_line(exc),
            category=category_name,
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        return _result(
            False,
            "SUPPLIER_SEARCH_FAILED",
            f"{type(exc).__name__}: {_first_line(exc)}",
            category=category_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()
