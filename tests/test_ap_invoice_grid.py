"""Đếm kết quả bảng Supplier Inv / Expense Inv (ASP.NET cổ điển).

Hai bảng này không có overlay no-rows như AG Grid nên app tự đếm: pager ghi
`View 1 - 10 of 47`, dòng dữ liệu là `tr.trContent`. Đếm sai theo hướng "0"
là báo nhầm "không có kết quả" cho một PO/invoice có thật.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from wfx_panel.automation._common import PlaywrightError
from wfx_panel.automation.modules import ap_invoice_grid as grid


class _Frame:
    def __init__(self, state=None, error=None):
        self.state = state
        self.error = error
        self.grid_ids: list[str] = []

    def evaluate(self, _script, grid_id):
        self.grid_ids.append(grid_id)
        if self.error is not None:
            raise self.error
        return self.state


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"rows": 10, "total": 47, "signature": "s"}, 47),
        ({"rows": 0, "total": 0, "signature": "s"}, 0),
        # Pager ẩn khi không có dòng: đếm theo dòng đang hiện.
        ({"rows": 0, "total": None, "signature": "s"}, 0),
        ({"rows": 3, "total": None, "signature": "s"}, 3),
        # Pager còn tổng của lượt trước mà bảng đang trống: chưa kết luận.
        ({"rows": 0, "total": 12, "signature": "s"}, None),
    ],
)
def test_the_total_comes_from_the_pager_and_rows_must_agree(state, expected):
    assert grid._ap_invoice_result_count(_Frame(state)) == expected


def test_each_list_reads_its_own_grid():
    """Supplier Inv và Expense Inv là hai trang, hai id grid khác nhau."""
    supplier, expense = _Frame({"rows": 1}), _Frame({"rows": 1})

    grid._ap_invoice_result_count(supplier)
    grid._ap_invoice_grid_signature(supplier)
    grid._expense_invoice_result_count(expense)
    grid._expense_invoice_grid_signature(expense)

    assert set(supplier.grid_ids) == {"gridAPInvoiceList"}
    assert set(expense.grid_ids) == {"gridExpenseInvoiceList"}


def test_an_unreadable_grid_is_never_counted_as_empty():
    assert grid._ap_invoice_result_count(_Frame(error=PlaywrightError("x"))) is None
    assert grid._expense_invoice_result_count(_Frame("lạ")) is None
    assert grid._ap_invoice_grid_signature(_Frame(error=PlaywrightError("x"))) == ""


_NODE_HARNESS = r"""
const script = JSON.parse(process.argv[1]);
const shownBox = { width: 100, height: 20 };
const makeRow = id => ({ id, isConnected: true, getBoundingClientRect: () => shownBox });
const run = (pagerText, rowIds) => {
  const asked = [];
  global.getComputedStyle = () => ({ display: 'block', visibility: 'visible' });
  global.document = {
    querySelectorAll: selector => { asked.push(selector); return rowIds.map(makeRow); },
    querySelector: selector => {
      asked.push(selector);
      return pagerText === null ? null : ({
        innerText: pagerText, isConnected: true, getBoundingClientRect: () => shownBox,
      });
    },
  };
  return { ...eval(`(${script})`)('gridExpenseInvoiceList'), asked };
};
console.log(JSON.stringify([
  run('\tPage  of 5\t\n10\n50\n100\nView 1 - 10 of 47', ['a', 'b']),
  run('Page 1 of 5', ['a']),
  run(null, []),
]));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Cần Node")
def test_the_pager_total_ignores_the_page_count():
    """Pager thật có cả "Page 1 of 5" lẫn "View 1 - 10 of 47"."""
    completed = subprocess.run(
        [
            shutil.which("node"),
            "-e",
            _NODE_HARNESS,
            json.dumps(grid._CLASSIC_GRID_STATE_JS),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    full, page_only, empty = json.loads(completed.stdout)

    assert full["total"] == 47
    assert full["rows"] == 2
    assert full["signature"].endswith("|a,b")
    assert full["asked"] == [
        "#gridExpenseInvoiceList_tblGridContent tr.trContent",
        "#gridExpenseInvoiceList_divGridPager",
    ]
    assert page_only["total"] is None
    assert (empty["signature"], empty["rows"], empty["total"]) == ("|", 0, None)
