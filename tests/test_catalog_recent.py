"""Style mở gần đây trong Catalog: store, controller và hợp đồng với UI.

Người dùng mở lại vài Style quen nhiều lần trong ngày. Danh sách phải theo
đúng tài khoản + Category (máy dùng chung không lộ danh sách của người khác),
mới nhất trước, không trùng, có trần, và chịu được file JSON hỏng.
"""

from __future__ import annotations

import json

import pytest

from tests.test_catalog_controller import APPAREL, TRIMS, _api, _library, _row
from wfx_panel.stores.catalog_recent import FILE_NAME, PER_SCOPE, CatalogRecentStore


@pytest.fixture
def store(tmp_path):
    return CatalogRecentStore(tmp_path)


def test_the_latest_style_comes_first_without_duplicates(store):
    store.remember("u1", APPAREL, "A-1", "Jacket")
    store.remember("u1", APPAREL, "A-2")
    recent = store.remember("U1", APPAREL, "a-1", "Jacket mới")

    assert recent == [
        {"code": "a-1", "label": "Jacket mới"},
        {"code": "A-2", "label": ""},
    ]


def test_each_account_and_category_keeps_its_own_short_list(store):
    for index in range(PER_SCOPE + 3):
        store.remember("u1", APPAREL, f"A-{index}")
    store.remember("u2", APPAREL, "B-1")
    store.remember("u1", TRIMS, "T-1")

    mine = store.load("u1", APPAREL)
    assert len(mine) == PER_SCOPE
    assert mine[0]["code"] == f"A-{PER_SCOPE + 2}"
    assert store.load("u2", APPAREL) == [{"code": "B-1", "label": ""}]
    assert store.load("u1", TRIMS) == [{"code": "T-1", "label": ""}]
    assert store.load("u3", APPAREL) == []


@pytest.mark.parametrize(
    ("user", "category", "code"),
    [("", APPAREL, "A-1"), ("u1", "", "A-1"), ("u1", APPAREL, "  ")],
)
def test_incomplete_entries_are_never_written(tmp_path, store, user, category, code):
    assert store.remember(user, category, code) == []
    assert not (tmp_path / FILE_NAME).exists()


@pytest.mark.parametrize("payload", ["không phải JSON", "[]", '{"styles": "x"}'])
def test_a_damaged_file_reads_as_empty_and_is_repaired(tmp_path, store, payload):
    (tmp_path / FILE_NAME).write_text(payload, encoding="utf-8")

    assert store.load("u1", APPAREL) == []
    store.remember("u1", APPAREL, "A-1")
    assert store.load("u1", APPAREL) == [{"code": "A-1", "label": ""}]


def test_whitespace_and_overlong_values_are_cleaned(store):
    store.remember("u1", APPAREL, "  A-1  ", "  Áo   khoác  " + "x" * 300)

    entry = store.load("u1", APPAREL)[0]
    assert entry["code"] == "A-1"
    assert entry["label"].startswith("Áo khoác ")
    assert len(entry["label"]) == 160


# --- controller ------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    api = _api(tmp_path)
    api._account = lambda: {"user_id": "xuan"}
    return api


def test_an_opened_style_is_remembered_with_its_buyer_reference(api):
    _library(api, [_row("F0001", "JACKET MEN", "BR-77")])

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["code"] == "RESULT_OPENED"
    assert result["recent_styles"] == [{"code": "F0001", "label": "BR-77"}]
    assert api._catalog.recent_styles(APPAREL)["recent_styles"] == [
        {"code": "F0001", "label": "BR-77"}
    ]


def test_other_categories_are_labelled_with_the_article_name(api):
    _library(api, [_row("T0001", "BUTTON 18L", "", category=TRIMS)])
    api._login.find_result = {**api._login.find_result, "article_code": "T0001"}

    result = api._catalog.action(TRIMS, "code", "T0001", None)

    assert result["recent_styles"] == [{"code": "T0001", "label": "BUTTON 18L"}]


def test_a_costing_opened_from_the_search_is_remembered_too(api):
    result = api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert [item["code"] for item in result["recent_styles"]] == ["F0001"]


@pytest.mark.parametrize(
    "answer",
    [
        {"ok": True, "code": "MULTIPLE_RESULTS", "styles": [], "codes": []},
        {"ok": False, "code": "NO_RESULTS", "codes": []},
        {"ok": False, "code": "CATALOG_DESTINATION_FAILED", "article_code": "F0001"},
    ],
)
def test_nothing_is_remembered_unless_a_style_really_opened(api, answer):
    api._login.find_result = answer

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert "recent_styles" not in result
    assert api._catalog.recent_styles(APPAREL)["recent_styles"] == []


def test_without_a_signed_in_account_nothing_is_stored(tmp_path):
    api = _api(tmp_path)
    api._account = lambda: {"user_id": ""}

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["recent_styles"] == []
    assert not (tmp_path / FILE_NAME).exists()


def test_several_codes_get_names_from_the_library_when_the_grid_had_none(api):
    _library(
        api,
        [_row("F0001", "JACKET MEN", "BR-77"), _row("F0002", "PANT", "")],
    )
    api._login.find_result = {
        "ok": True,
        "code": "MULTIPLE_RESULTS",
        "codes": ["F0001", "F0002", "F0003"],
        "styles": [
            {"code": "F0001", "season": "SS26", "internal_costsheet_status": ""},
            {"code": "f0002", "season": "", "internal_costsheet_status": ""},
            # Đường nhanh GetData đã có tên từ server: không ghi đè.
            {"code": "F0003", "article_name": "SERVER NAME", "buyer_reference": "S"},
        ],
    }

    result = api._catalog.action(APPAREL, "code", "F000", None)

    assert [
        (style["code"], style["article_name"], style["buyer_reference"])
        for style in result["styles"]
    ] == [
        ("F0001", "JACKET MEN", "BR-77"),
        ("f0002", "PANT", ""),
        ("F0003", "SERVER NAME", "S"),
    ]
    assert result["styles"][0]["season"] == "SS26"


def test_the_recent_file_never_holds_secrets(api, tmp_path):
    api._catalog.action(APPAREL, "code", "F0001", None)

    stored = json.loads((tmp_path / FILE_NAME).read_text(encoding="utf-8"))
    assert set(stored["styles"][0]) == {"user_id", "category", "code", "label", "opened_at"}


def test_the_bridge_exposes_the_recent_list(api):
    api._catalog.action(APPAREL, "code", "F0001", None)

    answer = api.catalog_recent_styles(APPAREL)

    assert answer["ok"] is True
    assert answer["category"] == APPAREL
    assert [item["code"] for item in answer["recent_styles"]] == ["F0001"]
