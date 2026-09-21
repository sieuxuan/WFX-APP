"""Tạo Style hàng loạt: token một lần, chọn đúng Group, và Save vẫn do user.

CLAUDE.md: user phải quét/chọn đúng một node loại Group rồi mới Import; mỗi lần
chỉ chuẩn bị MỘT dòng; `Tự động Save` mặc định off nên app dừng trước Save.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import wfx_panel.controllers.catalog_style as catalog_style
from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI
from wfx_panel.stores import style_options
from wfx_panel.workbooks.style import StyleWorkbookError


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls: list[tuple] = []

    def check_session(self, log=print):
        return {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"}


@pytest.fixture
def api(tmp_path):
    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )
    api._catalog.folders.cache["Apparel"] = [
        {"node_id": "7", "kind": "group", "name": "SS26", "path_label": "Master / SS26"},
        {"node_id": "8", "kind": "folder", "name": "Khong phai group"},
    ]
    return api


def _row(source_row=2, style_type="New"):
    return SimpleNamespace(
        source_row=source_row,
        type=style_type,
        style_copy="",
        buyer_style_ref="PO-1",
        internal_style_ref="ACEL",
        automation_payload=lambda: {
            "source_row": source_row,
            "type": style_type,
            "buyer_style_ref": "PO-1",
        },
    )


def _wire_read(monkeypatch, outcome=None):
    def read(_path):
        if isinstance(outcome, BaseException):
            raise outcome
        return list(outcome if outcome is not None else [_row()])

    monkeypatch.setattr(catalog_style, "read_style_workbook", read)


def _source(tmp_path):
    path = tmp_path / "Style.xlsx"
    path.write_bytes(b"excel")
    return path


# --- chọn Group ---------------------------------------------------------


def test_a_node_that_is_not_a_group_cannot_be_used_for_the_import(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)

    result = api.review_catalog_style_import(str(_source(tmp_path)), "8")

    assert result["code"] == "STYLE_GROUP_REQUIRED"


def test_a_group_the_tree_scan_never_saw_is_refused(api, tmp_path, monkeypatch):
    _wire_read(monkeypatch)

    result = api.review_catalog_style_import(str(_source(tmp_path)), "999")

    assert result["code"] == "STYLE_GROUP_REQUIRED"


# --- review file --------------------------------------------------------


def test_a_valid_file_returns_a_token_and_the_rows_the_user_will_see(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch, [_row(2), _row(3, "Copy")])

    result = api.review_catalog_style_import(str(_source(tmp_path)), "7")

    assert result["code"] == "STYLE_IMPORT_REVIEW_READY"
    assert result["row_count"] == 2
    assert result["requires_manual_save"] is True
    assert result["group"]["path_label"] == "Master / SS26"
    assert [row["source_row"] for row in result["rows"]] == [2, 3]
    assert result["review_token"] in api._catalog.style.imports


def test_a_workbook_with_cell_errors_is_reported_with_every_line(
    api, tmp_path, monkeypatch
):
    _wire_read(
        monkeypatch,
        StyleWorkbookError(
            "STYLE_FILE_INVALID",
            "File Style có lỗi.",
            ("Dòng 3: thiếu Buyer Style Ref.",),
        ),
    )

    result = api.review_catalog_style_import(str(_source(tmp_path)), "7")

    assert result["code"] == "STYLE_FILE_INVALID"
    assert result["errors"] == ["Dòng 3: thiếu Buyer Style Ref."]
    assert result["file_name"] == "Style.xlsx"
    assert api._catalog.style.imports == {}


def test_choosing_a_second_file_replaces_the_first_queue(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)

    first = api.review_catalog_style_import(str(_source(tmp_path)), "7")
    second = api.review_catalog_style_import(str(_source(tmp_path)), "7")

    assert list(api._catalog.style.imports) == [second["review_token"]]
    assert first["review_token"] != second["review_token"]


def test_cancelling_drops_the_queue_without_touching_wfx(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)
    review = api.review_catalog_style_import(str(_source(tmp_path)), "7")

    result = api.clear_catalog_style_import(review["review_token"])

    assert result["code"] == "STYLE_IMPORT_CANCELLED"
    assert api._catalog.style.imports == {}
    assert api._login.calls == []


def test_cancelling_an_unknown_token_is_still_a_clean_answer(api):
    assert (
        api.clear_catalog_style_import("khong-ton-tai")["code"]
        == "STYLE_IMPORT_CANCELLED"
    )


def test_a_queue_older_than_its_ttl_is_dropped(api, tmp_path, monkeypatch):
    _wire_read(monkeypatch)
    review = api.review_catalog_style_import(str(_source(tmp_path)), "7")
    stored = api._catalog.style.imports[review["review_token"]]
    stored["created_at"] -= catalog_style.STYLE_IMPORT_TTL_SECONDS + 1

    assert api._catalog.style._active_style_import(review["review_token"]) is None
    assert api._catalog.style.imports == {}


# --- chuẩn bị một dòng --------------------------------------------------


def _prepared(api, tmp_path, monkeypatch):
    _wire_read(monkeypatch, [_row(2), _row(3)])
    return api.review_catalog_style_import(str(_source(tmp_path)), "7")[
        "review_token"
    ]


def test_preparing_with_an_expired_token_asks_for_the_file_again(api):
    result = api.prepare_catalog_style_row("het-han", 2)

    assert result["code"] == "STYLE_IMPORT_EXPIRED"


def test_a_group_that_disappeared_between_review_and_run_is_refused(
    api, tmp_path, monkeypatch
):
    token = _prepared(api, tmp_path, monkeypatch)
    api._catalog.folders.cache["Apparel"] = []

    result = api.prepare_catalog_style_row(token, 2)

    assert result["code"] == "STYLE_GROUP_STALE"


@pytest.mark.parametrize("source_row", [99, "khong phai so", None])
def test_a_row_that_is_not_in_the_file_is_refused(
    api, tmp_path, monkeypatch, source_row
):
    token = _prepared(api, tmp_path, monkeypatch)

    result = api.prepare_catalog_style_row(token, source_row)

    assert result["code"] == "STYLE_ROW_INVALID"


def test_a_copy_choice_that_is_not_a_number_is_refused(
    api, tmp_path, monkeypatch
):
    token = _prepared(api, tmp_path, monkeypatch)

    result = api.prepare_catalog_style_row(token, 2, "khong phai so")

    assert result["code"] == "STYLE_COPY_CHOICE_INVALID"


def test_an_automation_build_without_style_creation_says_so(
    api, tmp_path, monkeypatch
):
    token = _prepared(api, tmp_path, monkeypatch)

    result = api.prepare_catalog_style_row(token, 2)

    assert result["code"] == "STYLE_PREPARE_UNSUPPORTED"


def test_preparing_a_row_stops_before_save_by_default(
    api, tmp_path, monkeypatch
):
    token = _prepared(api, tmp_path, monkeypatch)
    seen: list[tuple] = []
    api._login.prepare_catalog_style_row = (
        lambda category, node_id, row, copy_choice, auto_save, log=print: (
            seen.append((category, node_id, dict(row), copy_choice, auto_save))
            or {"ok": True, "code": "STYLE_ROW_PREPARED", "message": "ok"}
        )
    )

    result = api.prepare_catalog_style_row(token, 2)

    assert result["code"] == "STYLE_ROW_PREPARED"
    assert seen[0][0] == "01"
    assert seen[0][1] == "7"
    assert seen[0][2]["source_row"] == 2
    assert seen[0][3] is None
    assert seen[0][4] is False, "Tự động Save mặc định phải tắt"


def test_turning_auto_save_on_is_passed_through(api, tmp_path, monkeypatch):
    token = _prepared(api, tmp_path, monkeypatch)
    seen: list[bool] = []
    api._login.prepare_catalog_style_row = (
        lambda _c, _n, _r, _choice, auto_save, log=print: (
            seen.append(auto_save)
            or {"ok": True, "code": "STYLE_ROW_PREPARED", "message": "ok"}
        )
    )

    api.prepare_catalog_style_row(token, 3, 1, True)

    assert seen == [True]


# --- dropdown Style -----------------------------------------------------


def _snapshot(**overrides):
    values = {
        "generated_at": 1.0,
        "source": "test",
        "fields": {"Buyer": ["J.LINDEBERG"]},
        "subcategories_by_product_group": {},
    }
    values.update(overrides)
    return values


def test_options_cannot_be_fetched_without_a_group(api):
    assert (
        api.ensure_catalog_style_options("999")["code"] == "STYLE_GROUP_REQUIRED"
    )


def test_a_fresh_cache_is_used_without_touching_the_network_or_wfx(
    api, monkeypatch
):
    monkeypatch.setattr(
        style_options, "load_cached", lambda _base: _snapshot()
    )
    monkeypatch.setattr(
        style_options, "status", lambda _base: {"fresh": True, "age_days": 1}
    )
    monkeypatch.setattr(
        style_options,
        "sync_remote",
        lambda _base: pytest.fail("Cache còn hạn thì không được gọi GitHub"),
    )

    result = api.ensure_catalog_style_options("7")

    assert result["code"] == "STYLE_OPTIONS_CACHED"
    assert result["options"]["fields"]["Buyer"] == ["J.LINDEBERG"]


def test_a_stale_cache_is_refreshed_from_github_before_scanning_wfx(
    api, monkeypatch
):
    states = [{"fresh": False}, {"fresh": True}]
    monkeypatch.setattr(style_options, "load_cached", lambda _base: _snapshot())
    monkeypatch.setattr(
        style_options,
        "status",
        lambda _base: states[0] if len(states) > 1 else states[0],
    )
    monkeypatch.setattr(
        style_options,
        "sync_remote",
        lambda _base: states.pop(0) and _snapshot(source="github"),
    )

    result = api.ensure_catalog_style_options("7")

    assert result["code"] == "STYLE_OPTIONS_SERVER"
    assert result["options"]["source"] == "github"


def test_an_automation_build_without_the_scan_says_so(api, monkeypatch):
    monkeypatch.setattr(style_options, "load_cached", lambda _base: None)
    monkeypatch.setattr(style_options, "status", lambda _base: {"fresh": False})
    monkeypatch.setattr(style_options, "sync_remote", lambda _base: None)

    result = api.ensure_catalog_style_options("7")

    assert result["code"] == "STYLE_OPTIONS_SCAN_UNSUPPORTED"


def test_a_successful_scan_is_saved_and_published(api, monkeypatch):
    monkeypatch.setattr(style_options, "load_cached", lambda _base: None)
    monkeypatch.setattr(style_options, "status", lambda _base: {"fresh": False})
    monkeypatch.setattr(style_options, "sync_remote", lambda _base: None)
    saved: list[dict] = []
    monkeypatch.setattr(
        style_options,
        "save_snapshot",
        lambda _base, payload: saved.append(payload) or _snapshot(**payload),
    )
    monkeypatch.setattr(style_options, "publish_snapshot", lambda _snap: True)
    api._login.scan_catalog_style_options = lambda category, node_id, log=print: {
        "ok": True,
        "fields": {"Buyer": ["J.LINDEBERG"]},
        "subcategories_by_product_group": {"Woven": ["Jacket"]},
    }

    result = api.ensure_catalog_style_options("7", force=True)

    assert result["code"] == "STYLE_OPTIONS_SCANNED"
    assert result["uploaded"] is True
    assert "cập nhật snapshot trên GitHub" in result["message"]
    assert saved[0]["group_id"] == "7"


def test_a_scan_that_could_not_be_published_only_says_it_saved_locally(
    api, monkeypatch
):
    monkeypatch.setattr(style_options, "load_cached", lambda _base: None)
    monkeypatch.setattr(style_options, "status", lambda _base: {"fresh": False})
    monkeypatch.setattr(style_options, "sync_remote", lambda _base: None)
    monkeypatch.setattr(
        style_options, "save_snapshot", lambda _base, payload: _snapshot()
    )
    monkeypatch.setattr(style_options, "publish_snapshot", lambda _snap: False)
    api._login.scan_catalog_style_options = lambda *_a, **_k: {"ok": True}

    result = api.ensure_catalog_style_options("7", force=True)

    assert result["uploaded"] is False
    assert "lưu cache tháng trên máy" in result["message"]


def test_a_failed_scan_is_handed_back_when_there_is_no_cache_to_fall_back_on(
    api, monkeypatch
):
    monkeypatch.setattr(style_options, "load_cached", lambda _base: None)
    monkeypatch.setattr(style_options, "status", lambda _base: {"fresh": False})
    monkeypatch.setattr(style_options, "sync_remote", lambda _base: None)
    api._login.scan_catalog_style_options = lambda *_a, **_k: {
        "ok": False,
        "code": "STYLE_OPTIONS_SCAN_FAILED",
        "message": "Không mở được form New Style.",
    }

    result = api.ensure_catalog_style_options("7", force=True)

    assert result["code"] == "STYLE_OPTIONS_SCAN_FAILED"


def test_a_failed_scan_falls_back_to_the_last_cache_the_machine_has(
    api, monkeypatch
):
    monkeypatch.setattr(
        style_options, "load_cached", lambda _base: _snapshot(source="cu")
    )
    monkeypatch.setattr(style_options, "status", lambda _base: {"fresh": False})
    monkeypatch.setattr(style_options, "sync_remote", lambda _base: None)
    api._login.scan_catalog_style_options = lambda *_a, **_k: {
        "ok": False,
        "code": "STYLE_OPTIONS_SCAN_FAILED",
        "message": "Không mở được form New Style.",
    }

    result = api.ensure_catalog_style_options("7", force=True)

    assert result["code"] == "STYLE_OPTIONS_STALE_CACHE"
    assert result["options"]["source"] == "cu"
    assert result["warning"] == "Không mở được form New Style."
