"""Vòng tải hai report của `prepare_sale_asn_documents`.

Đây là phần WFX hay đổi hành vi nhất: đôi khi Docs mở cửa sổ mới, đôi khi tái
dùng chính tab Documents. Cả hai đường phải kết thúc bằng một workbook ghép và
mọi lỗi phải rơi vào đúng mã để UI hiển thị hướng xử lý.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import sale_asn_documents as docs
from wfx_panel.automation.sale_asn_documents.constants import (
    BUYER_INVOICE_SELECTOR,
    PACKING_LIST_SELECTOR,
)
from wfx_panel.workbooks.asn import ASNWorkbookError


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, docs)


def _quiet():
    return lambda _line: None


def _row(invoice_no="INV-1", buyer="J.LINDEBERG"):
    return {
        "invoice_no": invoice_no,
        "buyer": buyer,
        "selected": False,
        "row_key": "row-1",
    }


class DocsLink:
    def __init__(self, sink, selector):
        self._sink = sink
        self._selector = selector

    @property
    def first(self):
        return self

    def evaluate(self, _script):
        self._sink.append(self._selector)


class DocsFrame:
    """Frame Documents: chỉ cần hai link report và một URL để quay lại."""

    def __init__(self, url="https://wfx.test/SaleASNDocuments.aspx"):
        self.url = url
        self.clicked: list[str] = []

    def locator(self, selector):
        return DocsLink(self.clicked, selector)


def _wire_until_docs(monkeypatch, world, docs_frame, docs_page):
    patch_automation(
        monkeypatch, docs, "_open_list_search_context", lambda *_a, **_k: "frame"
    )
    patch_automation(
        monkeypatch, docs, "_clear_list_search_fields", lambda *_a, **_k: None
    )
    patch_automation(
        monkeypatch, docs, "_search_input_in_frame", lambda *_a, **_k: "field"
    )
    patch_automation(
        monkeypatch, docs, "_apply_module_search", lambda *_a, **_k: None
    )
    patch_automation(
        monkeypatch,
        docs,
        "_sale_asn_result_grid",
        lambda *_a, **_k: ("root", {"rows": [_row()]}),
    )
    patch_automation(
        monkeypatch, docs, "_click_sale_asn_docs", lambda *_a, **_k: True
    )
    patch_automation(
        monkeypatch,
        docs,
        "_documents_frame",
        lambda *_a, **_k: (docs_page, docs_frame),
    )
    patch_automation(
        monkeypatch, docs, "_mark_report_frames", lambda _context: []
    )


def _record_merge(monkeypatch, calls, *, error=None):
    def merge(packing, buyer, target, **kwargs):
        calls.append((Path(packing).name, Path(buyer).name, kwargs))
        if error is not None:
            raise error
        Path(target).write_bytes(b"ghep")

    patch_automation(monkeypatch, docs, "merge_sale_asn_reports", merge)
    patch_automation(
        monkeypatch,
        docs,
        "sale_asn_sheet_names",
        lambda _target: ["Invoice 1", "PKL 1"],
    )


def _prepare(tmp_path, *, filter_kind="invoice_no", query="INV-1"):
    return docs.prepare_sale_asn_documents(
        '//*[@id="0003_1000"]/a',
        filter_kind,
        query,
        tmp_path / "invoice.xlsx",
        _quiet(),
    )


def test_both_reports_are_downloaded_in_order_and_merged_invoice_first(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    docs_frame = DocsFrame()
    _wire_until_docs(monkeypatch, world, docs_frame, docs_page)

    report_frame = object()
    patch_automation(
        monkeypatch,
        docs,
        "_wait_report_ready",
        lambda *_a, **_k: (docs_page, report_frame),
    )
    downloaded: list[tuple[str, str]] = []

    def download(_context, frame, target, label, _log):
        assert frame is report_frame
        downloaded.append((label, Path(target).name))
        Path(target).write_bytes(b"PK")

    patch_automation(monkeypatch, docs, "_download_report_excel", download)
    restored: list[str] = []

    def restore(_context, _page, _frame, docs_url):
        restored.append(docs_url)
        return docs_page, docs_frame

    patch_automation(monkeypatch, docs, "_restore_documents_screen", restore)
    merges: list[tuple] = []
    _record_merge(monkeypatch, merges)

    result = _prepare(tmp_path)

    assert docs_frame.clicked == [PACKING_LIST_SELECTOR, BUYER_INVOICE_SELECTOR]
    assert downloaded == [
        ("Packing List", "packing-list-source.xlsx"),
        ("Buyer Invoice", "buyer-invoice-source.xlsx"),
    ]
    # Chỉ report đầu mới phải quay lại màn Documents; report cuối thì không.
    assert restored == ["https://wfx.test/SaleASNDocuments.aspx"]
    assert merges[0][0] == "packing-list-source.xlsx"
    assert merges[0][2] == {"invoice_no": "INV-1", "buyer_name": "J.LINDEBERG"}
    assert result["code"] == "SALE_ASN_DOCUMENTS_PREPARED"
    assert result["invoice_no"] == "INV-1"
    assert result["sheet_names"] == ["Invoice 1", "PKL 1"]
    assert Path(result["prepared_path"]).name == "invoice.xlsx"


def test_a_report_that_opened_its_own_window_is_closed_before_the_next_one(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    docs_frame = DocsFrame()
    _wire_until_docs(monkeypatch, world, docs_frame, docs_page)

    popups: list[FakePage] = []

    def wait_ready(_context, _snapshots):
        popup = world.add_page(FakePage(clock, url="https://wfx.test/report"))
        popups.append(popup)
        return popup, object()

    patch_automation(monkeypatch, docs, "_wait_report_ready", wait_ready)
    patch_automation(
        monkeypatch,
        docs,
        "_download_report_excel",
        lambda _c, _f, target, _l, _log: Path(target).write_bytes(b"PK"),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_restore_documents_screen",
        lambda *_a, **_k: pytest.fail(
            "Cửa sổ report riêng phải được đóng, không phải history.back()"
        ),
    )
    _record_merge(monkeypatch, [])

    result = _prepare(tmp_path)

    assert result["code"] == "SALE_ASN_DOCUMENTS_PREPARED"
    assert popups[0].closed is True
    assert docs_page.closed is False


def test_a_report_window_that_refuses_to_close_does_not_abort_the_run(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    docs_frame = DocsFrame()
    _wire_until_docs(monkeypatch, world, docs_frame, docs_page)

    def wait_ready(_context, _snapshots):
        popup = world.add_page(FakePage(clock, url="https://wfx.test/report"))

        def explode(*_args, **_kwargs):
            raise docs.PlaywrightError("target đã đóng")

        popup.close = explode
        return popup, object()

    patch_automation(monkeypatch, docs, "_wait_report_ready", wait_ready)
    patch_automation(
        monkeypatch,
        docs,
        "_download_report_excel",
        lambda _c, _f, target, _l, _log: Path(target).write_bytes(b"PK"),
    )
    _record_merge(monkeypatch, [])

    result = _prepare(tmp_path)

    assert result["code"] == "SALE_ASN_DOCUMENTS_PREPARED"


def test_an_invoice_no_is_taken_from_the_query_when_the_grid_hides_the_column(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    docs_frame = DocsFrame()
    _wire_until_docs(monkeypatch, world, docs_frame, docs_page)
    patch_automation(
        monkeypatch,
        docs,
        "_sale_asn_result_grid",
        lambda *_a, **_k: (
            "root",
            {"rows": [{"row_key": "1", "selected": True}]},
        ),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_wait_report_ready",
        lambda *_a, **_k: (docs_page, object()),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_download_report_excel",
        lambda _c, _f, target, _l, _log: Path(target).write_bytes(b"PK"),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_restore_documents_screen",
        lambda *_a, **_k: (docs_page, docs_frame),
    )
    merges: list[tuple] = []
    _record_merge(monkeypatch, merges)

    result = _prepare(tmp_path, filter_kind="buyer_order_ref", query="PO-77")

    assert result["invoice_no"] == "PO-77"
    assert merges[0][2] == {"invoice_no": "PO-77", "buyer_name": ""}


def test_a_download_failure_is_reported_as_a_download_failure(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    _wire_until_docs(monkeypatch, world, DocsFrame(), docs_page)
    patch_automation(
        monkeypatch,
        docs,
        "_wait_report_ready",
        lambda *_a, **_k: (docs_page, object()),
    )

    def explode(*_args, **_kwargs):
        raise RuntimeError("WFX trả file Packing List không hợp lệ (HTTP 500).")

    patch_automation(monkeypatch, docs, "_download_report_excel", explode)
    lines: list[str] = []

    result = docs.prepare_sale_asn_documents(
        '//*[@id="0003_1000"]/a',
        "invoice_no",
        "INV-1",
        tmp_path / "invoice.xlsx",
        lines.append,
    )

    assert result["code"] == "SALE_ASN_REPORT_DOWNLOAD_FAILED"
    assert "HTTP 500" in result["message"]
    assert any("HTTP 500" in line for line in lines)


def test_a_merge_failure_is_reported_separately_from_a_download_failure(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    docs_frame = DocsFrame()
    _wire_until_docs(monkeypatch, world, docs_frame, docs_page)
    patch_automation(
        monkeypatch,
        docs,
        "_wait_report_ready",
        lambda *_a, **_k: (docs_page, object()),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_download_report_excel",
        lambda _c, _f, target, _l, _log: Path(target).write_bytes(b"PK"),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_restore_documents_screen",
        lambda *_a, **_k: (docs_page, docs_frame),
    )
    lines: list[str] = []
    _record_merge(
        monkeypatch,
        [],
        error=ASNWorkbookError("Sheet Packing List không có cột JL PO#."),
    )

    result = docs.prepare_sale_asn_documents(
        '//*[@id="0003_1000"]/a',
        "invoice_no",
        "INV-1",
        tmp_path / "invoice.xlsx",
        lines.append,
    )

    assert result["code"] == "SALE_ASN_REPORT_MERGE_FAILED"
    assert "JL PO#" in result["message"]
    assert lines and "JL PO#" in lines[-1]


def test_an_unexpected_error_still_names_its_type_for_the_log(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    _wire_until_docs(monkeypatch, world, DocsFrame(), docs_page)
    patch_automation(
        monkeypatch,
        docs,
        "_wait_report_ready",
        lambda *_a, **_k: (docs_page, object()),
    )

    def explode(*_args, **_kwargs):
        raise PermissionError("Thư mục đích đang bị khóa")

    patch_automation(monkeypatch, docs, "_download_report_excel", explode)
    lines: list[str] = []

    result = docs.prepare_sale_asn_documents(
        '//*[@id="0003_1000"]/a',
        "invoice_no",
        "INV-1",
        tmp_path / "invoice.xlsx",
        lines.append,
    )

    assert result["code"] == "SALE_ASN_REPORT_DOWNLOAD_FAILED"
    assert result["message"].startswith("PermissionError: ")
    assert lines[-1].startswith("PermissionError: ")


def test_a_search_without_a_query_skips_the_filter_and_uses_the_open_grid(
    monkeypatch, clock, tmp_path
):
    docs_page = FakePage(clock, url="https://wfx.test/SaleASNDocuments.aspx")
    world = WfxWorld(clock, [docs_page])
    wire_automation(monkeypatch, docs, world)
    docs_frame = DocsFrame()
    _wire_until_docs(monkeypatch, world, docs_frame, docs_page)
    patch_automation(
        monkeypatch,
        docs,
        "_sale_asn_result_grid",
        lambda *_a, **_k: (
            "root",
            {"rows": [dict(_row(), selected=True)]},
        ),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_apply_module_search",
        lambda *_a, **_k: pytest.fail("Không có query thì không được lọc lại"),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_wait_report_ready",
        lambda *_a, **_k: (docs_page, object()),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_download_report_excel",
        lambda _c, _f, target, _l, _log: Path(target).write_bytes(b"PK"),
    )
    patch_automation(
        monkeypatch,
        docs,
        "_restore_documents_screen",
        lambda *_a, **_k: (docs_page, docs_frame),
    )
    _record_merge(monkeypatch, [])

    result = _prepare(tmp_path, filter_kind="invoice_no", query="   ")

    assert result["code"] == "SALE_ASN_DOCUMENTS_PREPARED"
    assert result["invoice_no"] == "INV-1"
