"""Chọn đúng dòng Sale ASN, chống nhầm report, và dọn popup của lượt Docs.

`sale_asn_documents.py` ở mức 42%: phần tải/ghép workbook đã có test, nhưng
`prepare_sale_asn_documents` (76 dòng vỏ, 1%) và khâu chọn dòng thì chưa.

Ba ràng buộc CLAUDE.md nằm đúng ở phần chưa được kiểm:

* Xác nhận invoice **độc lập** với cột Docs; nhiều dòng phù hợp thì dừng cho
  người dùng chọn, không tự lấy dòng đầu.
* Nhận diện nội dung workbook để chặn Packing List bị dùng nhầm làm Buyer
  Invoice và ngược lại.
* Luôn tự đóng mọi popup Docs/report sinh từ lượt này — **kể cả khi lỗi** —
  nhưng giữ nguyên các Page đã có từ trước.
"""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import sale_asn_documents as docs


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, docs)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _quiet():
    return lambda _line: None


def _row(invoice_no: str, *, selected: bool = False, buyer: str = "") -> dict:
    return {
        "invoice_no": invoice_no,
        "selected": selected,
        "buyer": buyer,
        "row_key": f"row-{invoice_no}",
    }


def _pick(rows, filter_kind="invoice_no", query="INV-1"):
    return docs._select_sale_asn_row({"rows": rows}, filter_kind, query)


# --- Chọn dòng Sale ASN -------------------------------------------------


def test_an_exact_invoice_match_is_selected(monkeypatch):
    row = _pick([_row("INV-1"), _row("INV-10")])

    assert row["invoice_no"] == "INV-1", "INV-10 không được nhận là INV-1"


def test_the_invoice_match_ignores_letter_case():
    row = _pick([_row("inv-1")], query="INV-1")

    assert row["invoice_no"] == "inv-1"


def test_no_matching_invoice_is_reported(monkeypatch):
    with pytest.raises(RuntimeError, match="SALE_ASN_INVOICE_NOT_FOUND"):
        _pick([_row("INV-9")])


def test_an_empty_grid_is_reported_as_not_found():
    with pytest.raises(RuntimeError, match="SALE_ASN_INVOICE_NOT_FOUND"):
        _pick([])


def test_several_rows_with_the_same_invoice_stop_for_the_user():
    with pytest.raises(RuntimeError, match="SALE_ASN_MULTIPLE_RESULTS"):
        _pick([_row("INV-1"), _row("INV-1")])


def test_a_tie_is_broken_by_the_row_the_user_already_selected():
    row = _pick([_row("INV-1"), _row("INV-1", selected=True, buyer="J.LINDEBERG")])

    assert row["buyer"] == "J.LINDEBERG"


def test_without_an_invoice_the_single_selected_row_is_used():
    row = _pick(
        [_row("INV-1"), _row("INV-2", selected=True)],
        filter_kind="oc_no",
        query="OC-9",
    )

    assert row["invoice_no"] == "INV-2"


def test_two_selected_rows_stop_for_the_user():
    with pytest.raises(RuntimeError, match="SALE_ASN_MULTIPLE_RESULTS"):
        _pick(
            [_row("INV-1", selected=True), _row("INV-2", selected=True)],
            filter_kind="oc_no",
            query="OC-9",
        )


def test_nothing_selected_and_several_rows_asks_the_user_to_choose():
    with pytest.raises(RuntimeError, match="SALE_ASN_SELECTION_REQUIRED"):
        _pick(
            [_row("INV-1"), _row("INV-2")],
            filter_kind="oc_no",
            query="OC-9",
        )


def test_a_lone_row_from_a_narrowed_search_is_accepted():
    row = _pick([_row("INV-7")], filter_kind="oc_no", query="OC-9")

    assert row["invoice_no"] == "INV-7"


# --- Chống nhầm Packing List với Buyer Invoice -------------------------


def _report(tmp_path, name: str, heading: str):
    path = tmp_path / name
    book = Workbook()
    sheet = book.active
    sheet["A1"] = heading
    book.save(path)
    book.close()
    return path


def test_a_packing_list_served_as_buyer_invoice_is_refused(tmp_path):
    path = _report(tmp_path, "swapped.xlsx", "PACKING LIST")

    with pytest.raises(RuntimeError, match="Packing List"):
        docs._validate_report_kind(path, "Buyer Invoice")


def test_an_invoice_served_as_packing_list_is_refused(tmp_path):
    path = _report(tmp_path, "swapped.xlsx", "COMMERCIAL INVOICE")

    with pytest.raises(RuntimeError, match="Buyer Invoice"):
        docs._validate_report_kind(path, "Packing List")


@pytest.mark.parametrize(
    ("heading", "label"),
    [
        ("Packing List", "Packing List"),
        ("Commercial Invoice", "Buyer Invoice"),
        ("Buyer Invoice", "Buyer Invoice"),
    ],
)
def test_a_matching_report_passes(tmp_path, heading, label):
    docs._validate_report_kind(_report(tmp_path, "ok.xlsx", heading), label)


def test_an_unrecognised_template_is_allowed_through(tmp_path):
    """WFX đổi template thì không được chặn oan; chỉ chặn khi biết chắc là nhầm."""
    docs._validate_report_kind(_report(tmp_path, "x.xlsx", "Bảng kê"), "Packing List")


# --- Dọn popup của lượt Docs -------------------------------------------


def test_only_popups_opened_by_this_run_are_closed(clock):
    before = FakePage(clock, url="https://wfx.test/wfx/list.aspx")
    reused = FakePage(clock, url="https://wfx.test/wfx/docs.aspx")
    world = WfxWorld(clock, [before, reused])
    opened = world.add_page(FakePage(clock, url="https://wfx.test/report.aspx"))

    docs._close_sale_asn_document_popups(
        world.context,
        {id(before), id(reused)},
        _quiet(),
    )

    assert opened.closed is True
    assert before.closed is False
    assert reused.closed is False, "Tab WFX người dùng đã mở sẵn phải được giữ"


def test_cleanup_reports_how_many_windows_it_closed(clock):
    world = WfxWorld(clock, [FakePage(clock)])
    world.add_page(FakePage(clock))
    world.add_page(FakePage(clock))
    lines: list[str] = []

    docs._close_sale_asn_document_popups(
        world.context,
        {id(world.pages[0])},
        lines.append,
    )

    assert any("2" in line for line in lines)


# --- Vỏ entry point ----------------------------------------------------


def _prepare(world, tmp_path, *, filter_kind="invoice_no", query="INV-1"):
    return docs.prepare_sale_asn_documents(
        '//*[@id="0003_1000"]/a',
        filter_kind,
        query,
        tmp_path / "invoice.xlsx",
        _quiet(),
    )


def test_an_unknown_filter_kind_never_opens_the_browser(
    monkeypatch,
    world,
    tmp_path,
):
    wire_automation(monkeypatch, docs, world)

    result = _prepare(world, tmp_path, filter_kind="khong_ton_tai")

    assert result["code"] == "INVALID_FILTER"
    assert world.driver_starts == 0


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_are_reported(
    monkeypatch,
    world,
    tmp_path,
    ready,
    logged_in,
    expected,
):
    wire_automation(
        monkeypatch,
        docs,
        world,
        chrome_ready=ready,
        logged_in=logged_in,
    )

    result = _prepare(world, tmp_path)

    assert result["code"] == expected
    assert result["module"] == "Sale ASN"
    assert world.driver_stops == 1


def _reach_grid(monkeypatch, rows):
    patch_automation(monkeypatch, docs, "_open_list_search_context", lambda *_a, **_k: "frame")
    patch_automation(monkeypatch, docs, "_clear_list_search_fields", lambda *_a, **_k: None)
    patch_automation(monkeypatch, docs, "_search_input_in_frame", lambda *_a, **_k: "field")
    patch_automation(monkeypatch, docs, "_apply_module_search", lambda *_a, **_k: None)
    patch_automation(
        monkeypatch, docs,
        "_sale_asn_result_grid",
        lambda *_a, **_k: ("root", {"rows": rows}),
    )


def test_a_row_without_a_docs_button_is_reported_with_the_invoice(
    monkeypatch,
    world,
    tmp_path,
):
    wire_automation(monkeypatch, docs, world)
    _reach_grid(monkeypatch, [_row("INV-1")])
    patch_automation(monkeypatch, docs, "_click_sale_asn_docs", lambda *_a, **_k: False)

    result = _prepare(world, tmp_path)

    assert result["code"] == "SALE_ASN_DOCS_NOT_AVAILABLE"
    assert result["invoice_no"] == "INV-1"
    assert result["module"] == "Sale ASN"


def test_several_matching_rows_are_reported_to_the_user(
    monkeypatch,
    world,
    tmp_path,
):
    wire_automation(monkeypatch, docs, world)
    _reach_grid(monkeypatch, [_row("INV-1"), _row("INV-1")])
    patch_automation(
        monkeypatch, docs,
        "_click_sale_asn_docs",
        lambda *_a, **_k: pytest.fail("Chưa chọn được dòng thì không được bấm Docs"),
    )

    result = _prepare(world, tmp_path)

    assert result["code"] == "SALE_ASN_MULTIPLE_RESULTS"
    assert result["module"] == "Sale ASN"


def test_popups_are_closed_even_when_the_run_fails(
    monkeypatch,
    clock,
    tmp_path,
):
    """`finally` phải dọn popup kể cả khi tải/ghép report hỏng giữa chừng."""
    before = FakePage(clock)
    world = WfxWorld(clock, [before])
    wire_automation(monkeypatch, docs, world)
    _reach_grid(monkeypatch, [_row("INV-1")])

    opened: list[FakePage] = []

    def click_docs(*_args, **_kwargs):
        opened.append(world.add_page(FakePage(clock)))
        return True

    patch_automation(monkeypatch, docs, "_click_sale_asn_docs", click_docs)

    def boom(*_args, **_kwargs):
        raise docs.PlaywrightTimeoutError("Documents chưa mở")

    patch_automation(monkeypatch, docs, "_documents_frame", boom)

    result = _prepare(world, tmp_path)

    assert result["code"] == "SALE_ASN_REPORT_NOT_READY"
    assert opened and opened[0].closed is True
    assert before.closed is False
    assert world.driver_stops == 1
