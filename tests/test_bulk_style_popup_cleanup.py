"""Quy tắc dọn popup của workspace Tạo Style.

CLAUDE.md: lượt quét dropdown "để lại một form New Style điền dở nên phải đóng
đúng những popup chính nó mở (so với snapshot ``context.pages``), kể cả khi lỗi
hoặc bị Stop; popup của ``prepare_style_row`` thì giữ nguyên vì đó là kết quả
user cần kiểm tra và tự Save."

Hai vế ngược nhau nên rất dễ sửa nhầm một bên: đóng luôn popup người dùng đang
cần xem, hoặc để lại form rác sau mỗi lượt quét.
"""

from __future__ import annotations

import ast
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from wfx_panel.automation import bulk_style


class FakePage:
    def __init__(self, name: str, *, refuses_close: bool = False) -> None:
        self.name = name
        self.refuses_close = refuses_close
        self.close_calls: list[bool] = []

    def close(self, run_before_unload: bool = True) -> None:
        self.close_calls.append(run_before_unload)
        if self.refuses_close:
            raise PlaywrightError("Target closed")

    def __repr__(self) -> str:  # pragma: no cover - chỉ để đọc lỗi test
        return f"<FakePage {self.name}>"


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


def test_only_pages_opened_by_this_run_are_closed():
    user_tab = FakePage("tab người dùng")
    reused = FakePage("cửa sổ CatalogDetail có sẵn")
    opened = FakePage("popup do lượt quét mở")
    known = {user_tab, reused}
    context = FakeContext([user_tab, reused, opened])

    bulk_style._close_pages_opened_since(context, known)

    assert user_tab.close_calls == []
    assert reused.close_calls == [], (
        "WFX tái dùng cửa sổ CatalogDetail; đóng nó là đóng tab của người dùng"
    )
    assert opened.close_calls == [False], (
        "Phải bỏ qua beforeunload, nếu không form điền dở sẽ chặn bằng dialog"
    )


def test_cleanup_continues_when_one_popup_refuses_to_close():
    stubborn = FakePage("popup Chrome còn giữ target", refuses_close=True)
    other = FakePage("popup thứ hai")
    context = FakeContext([stubborn, other])

    bulk_style._close_pages_opened_since(context, set())

    assert other.close_calls == [False], (
        "Một popup lỗi không được làm mất kết quả quét đã đọc xong"
    )


def test_nothing_is_closed_when_the_run_opened_nothing():
    existing = [FakePage("a"), FakePage("b")]
    context = FakeContext(existing)

    bulk_style._close_pages_opened_since(context, set(existing))

    assert all(page.close_calls == [] for page in existing)


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(
        Path(bulk_style.__file__).read_text(encoding="utf-8"),
        filename=bulk_style.__file__,
    )
    found = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == name
        ),
        None,
    )
    assert found is not None, f"Hàm đã đổi tên: {name}"
    return found


def _calls_cleanup(node: ast.AST) -> list[int]:
    return [
        child.lineno
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and (
            getattr(child.func, "id", "") or getattr(child.func, "attr", "")
        )
        == "_close_pages_opened_since"
    ]


def test_option_scan_cleans_up_inside_finally():
    """Bị Stop hoặc lỗi giữa chừng vẫn phải dọn, nên cleanup nằm trong finally."""
    scan = _function("scan_catalog_style_options")
    finallys = [
        node
        for node in ast.walk(scan)
        if isinstance(node, ast.Try) and node.finalbody
    ]
    in_finally = {
        line
        for node in finallys
        for statement in node.finalbody
        for line in _calls_cleanup(statement)
    }
    assert _calls_cleanup(scan), "Lượt quét không còn dọn popup nào"
    assert set(_calls_cleanup(scan)) == in_finally, (
        "Mọi lời gọi dọn popup phải nằm trong finally, nếu không một lần Stop "
        "sẽ để lại form New Style điền dở."
    )


def test_prepare_style_row_never_closes_its_own_popup():
    """Popup của prepare_style_row là kết quả người dùng cần xem và tự Save."""
    prepare = _function("prepare_catalog_style_row")
    assert _calls_cleanup(prepare) == [], (
        "prepare_style_row không được đóng popup vừa mở cho người dùng "
        f"(dòng {_calls_cleanup(prepare)})"
    )
