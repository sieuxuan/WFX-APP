"""Cây thư mục Catalog: đọc node, tra node theo id, và chờ WFX chọn xong.

CLAUDE.md: workspace `Tạo Style` bắt user quét/chọn một node đúng loại Group
rồi mới Import form XLSX, nên danh sách folder phải phản ánh đúng cây WFX và
việc "đã click" không được coi là "đã chọn" khi WFX chưa gắn
`clsTreeSelectedNode`.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.catalog.folders as folders
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import FakeLocator, FakeNode, install_fake_clock
from wfx_panel.automation._common import PlaywrightError


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, folders)


class TreeFrame:
    """Frame cây; `evaluate` trả đúng thứ WFX sẽ trả cho script quét node."""

    def __init__(self, nodes, *, selected=(), error=None):
        self.nodes = nodes
        self.selected = set(selected)
        self.error = error
        self.selector_calls: list[str] = []

    def evaluate(self, _script, *_args):
        if self.error is not None:
            raise self.error
        return self.nodes

    def locator(self, selector):
        self.selector_calls.append(selector)
        if self.error is not None:
            raise self.error
        matched = [
            FakeNode()
            for node_id in self.selected
            if f'nodeid="{node_id}"' in selector
        ]
        return FakeLocator(matched, selector)


class TreePage:
    def __init__(self, clock):
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


def _folder(node_id, name, kind="folder"):
    return {
        "node_id": node_id,
        "node_code": f"G{node_id}",
        "name": name,
        "path": ["Master", name],
        "path_label": f"Master / {name}",
        "kind": kind,
        "depth": 2,
    }


# --- đọc cây ------------------------------------------------------------


def test_the_folder_tree_is_read_straight_from_the_dom_wfx_rendered():
    frame = TreeFrame([_folder("12", "Jacket"), _folder("13", "Pant", "group")])

    result = folders._catalog_folder_nodes(frame)

    assert [item["node_id"] for item in result] == ["12", "13"]
    assert result[1]["kind"] == "group"


def test_a_tree_wfx_has_not_rendered_yet_reads_as_no_folders():
    assert folders._catalog_folder_nodes(TreeFrame([])) == []


@pytest.mark.parametrize("payload", [None, "", {"node_id": "12"}, 0])
def test_anything_that_is_not_a_list_of_nodes_reads_as_no_folders(payload):
    assert folders._catalog_folder_nodes(TreeFrame(payload)) == []


# --- tra một node -------------------------------------------------------


def test_a_node_id_resolves_to_the_folder_the_user_picked():
    frame = TreeFrame([_folder("12", "Jacket"), _folder("13", "Pant")])

    assert folders._catalog_folder_for_node(frame, "13")["name"] == "Pant"


def test_a_node_the_user_can_no_longer_see_resolves_to_nothing():
    frame = TreeFrame([_folder("12", "Jacket")])

    assert folders._catalog_folder_for_node(frame, "99") is None


def test_a_node_id_is_compared_as_text_not_as_a_number():
    frame = TreeFrame([{"node_id": 12, "path_label": "Master / Jacket"}])

    assert folders._catalog_folder_for_node(frame, "12") is not None


def test_a_node_without_an_id_never_matches():
    frame = TreeFrame([{"name": "Jacket"}])

    assert folders._catalog_folder_for_node(frame, "12") is None


# --- chờ WFX xác nhận đã chọn -------------------------------------------


def test_a_folder_wfx_has_marked_as_selected_is_confirmed(clock, monkeypatch):
    frame = TreeFrame([], selected={"13"})
    patch_automation(
        monkeypatch, folders, "_catalog_tree_frame_now", lambda _page: frame
    )

    assert folders._wait_catalog_folder_selected(TreePage(clock), "13") is True


def test_a_click_that_wfx_never_confirms_is_not_a_selection(clock, monkeypatch):
    frame = TreeFrame([], selected={"12"})
    patch_automation(
        monkeypatch, folders, "_catalog_tree_frame_now", lambda _page: frame
    )

    assert folders._wait_catalog_folder_selected(TreePage(clock), "13", 1) is False


def test_waiting_survives_wfx_swapping_the_tree_document(clock, monkeypatch):
    frames = [None, TreeFrame([], error=PlaywrightError("frame detached"))]
    ready = TreeFrame([], selected={"13"})

    def tree(_page):
        return frames.pop(0) if frames else ready

    patch_automation(monkeypatch, folders, "_catalog_tree_frame_now", tree)

    assert folders._wait_catalog_folder_selected(TreePage(clock), "13", 5) is True


def test_a_tree_that_never_comes_back_times_out_instead_of_hanging(
    clock, monkeypatch
):
    patch_automation(
        monkeypatch, folders, "_catalog_tree_frame_now", lambda _page: None
    )

    assert folders._wait_catalog_folder_selected(TreePage(clock), "13", 2) is False
