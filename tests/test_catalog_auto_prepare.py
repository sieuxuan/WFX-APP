"""Tự mở Catalog khi vào module không được làm mất màn WFX đang nhập dở."""

from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError

from wfx_panel.automation.catalog import flows


class FakeFrame:
    def __init__(self, unsaved=False, broken=False):
        self.unsaved = unsaved
        self.broken = broken

    def evaluate(self, _script):
        if self.broken:
            raise PlaywrightError("frame detached")
        return self.unsaved


class FakePage:
    def __init__(self, *frames):
        self.main_frame = FakeFrame(unsaved=True)
        self.frames = [self.main_frame, *frames]


def test_an_open_catalog_is_always_safe(monkeypatch):
    monkeypatch.setattr(flows, "_catalog_tree_frame_now", lambda page: object())

    assert flows._catalog_auto_open_blocker(FakePage(FakeFrame(unsaved=True))) is None


def test_a_page_with_typed_data_blocks_the_auto_open(monkeypatch):
    monkeypatch.setattr(flows, "_catalog_tree_frame_now", lambda page: None)

    blocker = flows._catalog_auto_open_blocker(
        FakePage(FakeFrame(), FakeFrame(unsaved=True))
    )

    assert blocker == "màn WFX đang mở còn dữ liệu nhập"


def test_an_unreadable_frame_counts_as_unsafe(monkeypatch):
    monkeypatch.setattr(flows, "_catalog_tree_frame_now", lambda page: None)

    assert flows._catalog_auto_open_blocker(FakePage(FakeFrame(broken=True)))


def test_the_menu_frame_alone_does_not_block(monkeypatch):
    # Frame chính chỉ là menu/top bar của WFX; ô của nó không phải việc dở.
    monkeypatch.setattr(flows, "_catalog_tree_frame_now", lambda page: None)

    assert flows._catalog_auto_open_blocker(FakePage(FakeFrame())) is None
