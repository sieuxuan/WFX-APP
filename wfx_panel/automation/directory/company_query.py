"""Điền ô tìm kiếm Company và chờ bảng kết quả ổn định."""

from __future__ import annotations

from collections.abc import Mapping

from wfx_panel.automation._common import (
    _COMPANY_ROWS_JS,
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.directory.frames import (
    _company_frame_marker,
    _company_marker_matches,
    _company_search_frame,
)


def _fill_company_query(
    page: Page,
    frame: Frame,
    query: str,
    log: Callable[[str], None],
    expected_kind: str,
) -> Frame:
    current = frame
    # WFX có thể thay frame Company ngay sau khi Master vừa báo ready. Resolve
    # lại đúng PartyType một lần thay vì trả lỗi ngẫu nhiên ở field đầu tiên.
    for attempt in range(2):
        try:
            field = current.locator("#txtCompanyName")
            field.wait_for(state="visible", timeout=5_000)
            field.fill("")
            field.type(query, delay=25)
            if field.input_value(timeout=1_000) != query:
                raise PlaywrightTimeoutError(
                    "WFX không xác nhận Company Name query."
                )
            try:
                field.press("Enter", timeout=2_000)
            except PlaywrightError:
                pass
            break
        except (PlaywrightError, PlaywrightTimeoutError):
            if attempt:
                raise
            replacement = _company_search_frame(
                page,
                expected_kind,
                timeout_s=3,
            )
            if replacement is None:
                raise PlaywrightTimeoutError(
                    "Frame Company Name đã đổi và chưa sẵn sàng."
                ) from None
            current = replacement
            _write_log(log, "[COMPANY SEARCH] Đã đồng bộ lại frame Company.")
    _write_log(log, f"[COMPANY SEARCH] Đã nhập query={query!r}")
    return current


def _company_result_state_key(state: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        state["noRows"],
        tuple((row["company"], row["hasEdit"]) for row in state["rows"]),
    )


def _wait_company_results(
    page: Page,
    frame: Frame,
    query: str,
    expected_kind: str,
) -> tuple[Frame, dict[str, Any]]:
    current = frame
    deadline = time.monotonic() + 18
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    last: dict[str, Any] = {"rows": [], "noRows": False, "loading": False}
    while time.monotonic() < deadline:
        try:
            if not _company_marker_matches(
                _company_frame_marker(current),
                expected_kind,
            ):
                replacement = _company_search_frame(
                    page,
                    expected_kind,
                    timeout_s=2,
                )
                if replacement is None:
                    _wait(page, 200)
                    continue
                current = replacement
            last = current.evaluate(_COMPANY_ROWS_JS, {"query": query})
            rows = last["rows"]
            matching = [row for row in rows if row["matches"]]
            # Đọc sớm chỉ nguy hiểm ở nhánh 0 kết quả: lọc server-side của WFX
            # chỉ BỎ BỚT dòng không khớp, nên một dòng đã khớp thì tập khớp
            # không đổi dù grid lọc xong hay chưa. Ngược lại, đòi "mọi dòng
            # đang render đều khớp" là sai với DOM thật: WFX giữ lại dòng phụ
            # (tổng/phân trang) không chứa query, và đúng một dòng như vậy đủ
            # để nuốt trọn deadline 18 giây rồi trả lỗi kỹ thuật cho một lượt
            # tìm đã thành công.
            filtered = bool(matching) or not rows
            state_key = _company_result_state_key(last)
            if not last.get("loading") and filtered and state_key == stable_key:
                required = 2.5 if not rows else 0.8
                if time.monotonic() - stable_since >= required:
                    return current, last
            else:
                stable_key = state_key
                stable_since = time.monotonic()
        except PlaywrightError:
            replacement = _company_search_frame(
                page,
                expected_kind,
                timeout_s=2,
            )
            if replacement is not None:
                current = replacement
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Kết quả Company Name chưa ổn định: {last}"
    )


def _filter_company_rows(
    page: Page,
    frame: Frame,
    query: str,
    log: Callable[[str], None],
    expected_kind: str,
) -> tuple[Frame, dict[str, Any]]:
    current = _fill_company_query(page, frame, query, log, expected_kind)
    return _wait_company_results(page, current, query, expected_kind)
