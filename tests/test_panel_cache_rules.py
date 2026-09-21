"""Cache cạnh panel: khóa theo tài khoản, chịu được file hỏng, hết hạn 7 ngày.

CLAUDE.md: khi User ID đổi, app phải hạ ngay session, Division, quyền Admin và
cache Catalog theo tài khoản; ba danh sách chi phí chỉ scan một lần trong 7
ngày và cache theo User ID + Division.
"""

from __future__ import annotations

import json
import time

import pytest

from wfx_panel.paths import (
    _catalog_cache_path,
    _costing_article_cache_path,
    _costing_special_options_cache_path,
)
from wfx_panel.stores import panel_cache

SPECIAL_KEYS = ("cmcosts", "productioncosts", "indirectcosts")


def _folder(node_id="12", **overrides):
    folder = {
        "node_id": node_id,
        "node_code": f"G{node_id}",
        "name": "Jacket",
        "path": ["Master", "Jacket"],
        "kind": "folder",
    }
    folder.update(overrides)
    return folder


def _section(key="fabricshell", **overrides):
    section = {
        "section_key": key,
        "section_name": "FABRIC- SHELL",
        "options": [{"article_code": "F0001", "article_name": "Cotton"}],
    }
    section.update(overrides)
    return section


def _special_sections():
    return [
        {"section_key": key, "options": [f"{key}-A", f"{key}-B"]}
        for key in SPECIAL_KEYS
    ]


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# --- cây folder Catalog -------------------------------------------------


def test_the_scanned_tree_comes_back_for_the_account_that_scanned_it(tmp_path):
    saved = panel_cache.save_catalog_folder_cache("tester", [_folder()], base_dir=tmp_path)

    assert saved[0]["path_label"] == "Master / Jacket"
    assert panel_cache.load_catalog_folder_cache("tester", base_dir=tmp_path) == saved


def test_the_tree_of_another_account_is_never_served(tmp_path):
    panel_cache.save_catalog_folder_cache("tester", [_folder()], base_dir=tmp_path)

    assert panel_cache.load_catalog_folder_cache("nguoi-khac", base_dir=tmp_path) is None
    assert panel_cache.load_catalog_folder_cache("", base_dir=tmp_path) is None


def test_a_tree_is_only_kept_for_apparel(tmp_path):
    assert panel_cache.save_catalog_folder_cache(
        "tester", [_folder()], "Trims", base_dir=tmp_path
    ) == []
    panel_cache.save_catalog_folder_cache("tester", [_folder()], base_dir=tmp_path)

    assert panel_cache.load_catalog_folder_cache(
        "tester", "Trims", base_dir=tmp_path
    ) is None


def test_an_account_with_no_id_never_writes_a_tree(tmp_path):
    assert panel_cache.save_catalog_folder_cache("  ", [_folder()], base_dir=tmp_path) == []
    assert not _catalog_cache_path(tmp_path).exists()


def test_a_tree_with_nothing_usable_is_not_written(tmp_path):
    assert panel_cache.save_catalog_folder_cache(
        "tester", ["hong", {"node_id": "abc"}], base_dir=tmp_path
    ) == []
    assert not _catalog_cache_path(tmp_path).exists()


def test_the_same_node_appearing_twice_is_only_kept_once(tmp_path):
    saved = panel_cache.save_catalog_folder_cache(
        "tester", [_folder(), _folder()], base_dir=tmp_path
    )

    assert len(saved) == 1


def test_a_node_without_a_numeric_id_is_dropped(tmp_path):
    assert panel_cache._normalise_catalog_tree_node(_folder(node_id="abc")) is None
    assert panel_cache._normalise_catalog_tree_node("hong") is None


def test_a_node_without_a_name_or_path_is_dropped():
    assert panel_cache._normalise_catalog_tree_node(
        {"node_id": "12", "path": []}
    ) is None
    assert panel_cache._normalise_catalog_tree_node(
        {"node_id": "12", "name": "", "path": "khong phai list"}
    ) is None


def test_a_node_takes_its_name_from_the_last_part_of_its_path():
    node = panel_cache._normalise_catalog_tree_node(
        {"node_id": "12", "path": ["Master", "Jacket"]}
    )

    assert node["name"] == "Jacket"
    assert node["depth"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        "khong phai json",
        json.dumps(["khong phai dict"]),
        json.dumps({"user_id": "tester", "category_name": "Apparel"}),
        json.dumps(
            {
                "user_id": "tester",
                "category_name": "Apparel",
                "folders": "khong phai list",
            }
        ),
    ],
)
def test_a_damaged_tree_cache_reads_as_no_cache(tmp_path, payload):
    path = _catalog_cache_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")

    assert panel_cache.load_catalog_folder_cache("tester", base_dir=tmp_path) is None


def test_a_tree_cache_that_was_never_written_reads_as_no_cache(tmp_path):
    assert panel_cache.load_catalog_folder_cache("tester", base_dir=tmp_path) is None


def test_broken_and_duplicate_nodes_in_a_saved_tree_are_skipped_on_read(tmp_path):
    _write(
        _catalog_cache_path(tmp_path),
        {
            "user_id": "tester",
            "category_name": "Apparel",
            "folders": ["hong", _folder(), _folder(), _folder("13")],
        },
    )

    folders = panel_cache.load_catalog_folder_cache("tester", base_dir=tmp_path)

    assert [folder["node_id"] for folder in folders] == ["12", "13"]


# --- vị trí Apparel mặc định --------------------------------------------


def test_the_default_position_falls_back_to_master_when_no_node_is_pinned():
    folder = panel_cache._normalise_catalog_folder(
        {"category_name": "Apparel", "category_value": "01", "user_id": "tester"}
    )

    assert folder["kind"] == "master"
    assert folder["path_label"] == "Master"


def test_a_default_position_saved_for_another_category_is_discarded():
    assert panel_cache._normalise_catalog_folder(
        {"category_name": "Trims", "category_value": "02", "node_id": "12"}
    ) is None


@pytest.mark.parametrize(
    "value",
    [
        "hong",
        {"category_name": "Apparel", "category_value": "01", "node_id": "abc"},
        {"category_name": "Apparel", "category_value": "01", "node_id": "12"},
    ],
)
def test_a_default_position_that_cannot_be_trusted_is_discarded(value):
    assert panel_cache._normalise_catalog_folder(value) is None


def test_a_pinned_group_keeps_its_kind_and_full_path():
    folder = panel_cache._normalise_catalog_folder(
        {
            "category_name": "Apparel",
            "category_value": "01",
            "node_id": "12",
            "path": ["Master", "Jacket"],
            "kind": "group",
        }
    )

    assert folder["kind"] == "group"
    assert folder["path_label"] == "Master / Jacket"


# --- dropdown Article của Costing ---------------------------------------


def test_the_article_dropdown_comes_back_for_the_same_account(tmp_path):
    saved = panel_cache.save_costing_article_cache(
        "tester", [_section()], base_dir=tmp_path
    )

    assert panel_cache.load_costing_article_cache("tester", base_dir=tmp_path) == saved


def test_the_article_dropdown_of_another_account_is_never_served(tmp_path):
    panel_cache.save_costing_article_cache("tester", [_section()], base_dir=tmp_path)

    assert panel_cache.load_costing_article_cache(
        "nguoi-khac", base_dir=tmp_path
    ) is None


def test_an_article_dropdown_older_than_the_window_is_rescanned(tmp_path):
    panel_cache.save_costing_article_cache("tester", [_section()], base_dir=tmp_path)

    assert panel_cache.load_costing_article_cache(
        "tester", base_dir=tmp_path, max_age_seconds=0
    ) is None


def test_an_article_dropdown_without_a_timestamp_is_rescanned(tmp_path):
    _write(
        _costing_article_cache_path(tmp_path),
        {"user_id": "tester", "sections": [_section()]},
    )

    assert panel_cache.load_costing_article_cache("tester", base_dir=tmp_path) is None


def test_an_account_with_no_id_never_writes_an_article_dropdown(tmp_path):
    assert panel_cache.save_costing_article_cache("  ", [_section()], base_dir=tmp_path) == []
    assert not _costing_article_cache_path(tmp_path).exists()


def test_an_article_dropdown_with_nothing_usable_is_not_written(tmp_path):
    assert panel_cache.save_costing_article_cache(
        "tester", ["hong", _section(options=[])], base_dir=tmp_path
    ) == []
    assert not _costing_article_cache_path(tmp_path).exists()


@pytest.mark.parametrize(
    "value",
    [
        "hong",
        {"section_key": "", "section_name": "A", "options": []},
        {"section_key": "a", "section_name": "", "options": []},
        {"section_key": "a", "section_name": "A", "options": "khong phai list"},
        {"section_key": "a", "section_name": "A", "options": ["hong"]},
        {
            "section_key": "a",
            "section_name": "A",
            "options": [{"article_code": "", "article_name": ""}],
        },
    ],
)
def test_an_article_section_that_cannot_be_trusted_is_dropped(value):
    assert panel_cache._normalise_costing_article_section(value) is None


def test_the_same_article_listed_twice_is_only_offered_once():
    section = panel_cache._normalise_costing_article_section(
        _section(
            options=[
                {"article_code": "F0001", "article_name": "Cotton"},
                {"article_code": "f0001", "article_name": "cotton"},
            ]
        )
    )

    assert len(section["options"]) == 1


@pytest.mark.parametrize(
    "payload",
    [
        "khong phai json",
        json.dumps(["khong phai dict"]),
        json.dumps(
            {"user_id": "tester", "saved_at": time.time(), "sections": "hong"}
        ),
    ],
)
def test_a_damaged_article_cache_reads_as_no_cache(tmp_path, payload):
    path = _costing_article_cache_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")

    assert panel_cache.load_costing_article_cache("tester", base_dir=tmp_path) is None


# --- ba dropdown chi phí ------------------------------------------------


def test_the_cost_dropdowns_come_back_for_the_same_account_and_division(tmp_path):
    saved = panel_cache.save_costing_special_options_cache(
        "tester", "APPAREL", _special_sections(), base_dir=tmp_path
    )

    loaded = panel_cache.load_costing_special_options_cache(
        "tester", "APPAREL", base_dir=tmp_path
    )

    assert loaded["sections"] == saved["sections"]
    assert loaded["expires_at"] > loaded["saved_at"]


def test_switching_division_forces_a_fresh_scan(tmp_path):
    panel_cache.save_costing_special_options_cache(
        "tester", "APPAREL", _special_sections(), base_dir=tmp_path
    )

    assert panel_cache.load_costing_special_options_cache(
        "tester", "TRIMS", base_dir=tmp_path
    ) is None


def test_switching_account_forces_a_fresh_scan(tmp_path):
    panel_cache.save_costing_special_options_cache(
        "tester", "APPAREL", _special_sections(), base_dir=tmp_path
    )

    assert panel_cache.load_costing_special_options_cache(
        "nguoi-khac", "APPAREL", base_dir=tmp_path
    ) is None


def test_cost_dropdowns_older_than_seven_days_are_rescanned(tmp_path):
    panel_cache.save_costing_special_options_cache(
        "tester", "APPAREL", _special_sections(), base_dir=tmp_path
    )

    assert panel_cache.load_costing_special_options_cache(
        "tester", "APPAREL", base_dir=tmp_path, max_age_seconds=0
    ) is None


@pytest.mark.parametrize(
    ("user_id", "division"),
    [("", "APPAREL"), ("tester", "  ")],
)
def test_cost_dropdowns_are_not_written_without_an_account_and_division(
    tmp_path, user_id, division
):
    assert panel_cache.save_costing_special_options_cache(
        user_id, division, _special_sections(), base_dir=tmp_path
    ) is None
    assert not _costing_special_options_cache_path(tmp_path).exists()


def test_a_partial_scan_of_the_three_cost_lists_is_never_saved(tmp_path):
    assert panel_cache.save_costing_special_options_cache(
        "tester",
        "APPAREL",
        _special_sections()[:2],
        base_dir=tmp_path,
    ) is None


def test_a_cache_missing_one_of_the_three_cost_lists_is_rescanned(tmp_path):
    _write(
        _costing_special_options_cache_path(tmp_path),
        {
            "user_id": "tester",
            "division_key": "APPAREL",
            "saved_at": time.time(),
            "sections": _special_sections()[:2],
        },
    )

    assert panel_cache.load_costing_special_options_cache(
        "tester", "APPAREL", base_dir=tmp_path
    ) is None


@pytest.mark.parametrize(
    "value",
    [
        "hong",
        {"section_key": "fabricshell", "options": []},
        {"section_key": "cmcosts", "options": "khong phai list"},
    ],
)
def test_a_cost_list_that_is_not_one_of_the_three_is_dropped(value):
    assert panel_cache._normalise_costing_special_section(value) is None


def test_a_cost_option_listed_twice_is_only_offered_once():
    section = panel_cache._normalise_costing_special_section(
        {"section_key": "cmcosts", "options": ["Sewing", "sewing", "", None]}
    )

    assert section["options"] == ["Sewing"]


@pytest.mark.parametrize(
    "payload",
    [
        "khong phai json",
        json.dumps(["khong phai dict"]),
        json.dumps(
            {
                "user_id": "tester",
                "division_key": "APPAREL",
                "saved_at": time.time(),
                "sections": "hong",
            }
        ),
    ],
)
def test_a_damaged_cost_dropdown_cache_reads_as_no_cache(tmp_path, payload):
    path = _costing_special_options_cache_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")

    assert panel_cache.load_costing_special_options_cache(
        "tester", "APPAREL", base_dir=tmp_path
    ) is None
