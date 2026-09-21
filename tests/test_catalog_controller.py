"""Controller Catalog: chuẩn bị Category, tìm Style, và tái dùng popup đang mở.

CLAUDE.md cấm chạy lại cả luồng Catalog khi popup Article vừa mở còn dùng được,
và bắt mọi mã "context lost" phải xoá sạch state để lượt sau mở lại từ đầu thay
vì thao tác trên grid cũ.
"""

from __future__ import annotations

import pytest

from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI

APPAREL = "Apparel"
TRIMS = "Trims"


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls: list[tuple] = []
        self.find_result = {
            "ok": True,
            "code": "RESULT_OPENED",
            "message": "Đã mở style.",
            "article_code": "F0001",
            "style_status": "Open",
        }
        self.destination_result = {
            "ok": True,
            "code": "CATALOG_DESTINATION_OPENED",
            "message": "Đã mở Costsheet.",
        }
        self.prepare_result = {
            "ok": True,
            "code": "CATEGORY_SELECTED",
            "message": "Đã chọn Apparel.",
        }

        # Gắn theo instance để test gỡ được từng khả năng, mô phỏng đúng cách
        # controller dùng `hasattr` dò xem bản automation có hỗ trợ hay không.
        self.prepare_catalog_master = self._prepare_catalog_master
        self.find_in_open_catalog = self._find_in_open_catalog
        self.open_catalog_destination = self._open_catalog_destination

    def check_session(self, log=print):
        return {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"}

    def _prepare_catalog_master(self, category_name, value, log=print):
        self.calls.append(("prepare_catalog_master", category_name, value))
        return self.prepare_result

    def _find_in_open_catalog(self, category_name, filter_kind, query, log=print):
        self.calls.append(("find", category_name, filter_kind, query))
        return self.find_result

    def _open_catalog_destination(self, article_code, destination, log=print):
        self.calls.append(("destination", article_code, destination))
        return self.destination_result


class LegacyLogin(FakeLogin):
    """Bản automation cũ: chỉ có open_module + set_catalog_category."""

    def __init__(self):
        super().__init__()
        self.module_result = {
            "ok": True,
            "code": "MODULE_OPENED",
            "message": "Catalog",
        }
        del self.prepare_catalog_master

    def open_module(self, module_name, xpath, log=print):
        self.calls.append(("open_module", module_name))
        return self.module_result

    def set_catalog_category(self, category_name, value, log=print):
        self.calls.append(("set_category", category_name, value))
        return self.prepare_result


def _api(tmp_path, login=None):
    return PanelAPI(
        login_module=login or FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )


@pytest.fixture
def api(tmp_path):
    return _api(tmp_path)


def _prepared(api, category=APPAREL):
    result = api._catalog.prepare(category)
    assert result["code"] == "CATEGORY_SELECTED"
    return api


# --- chuẩn bị Category --------------------------------------------------


def test_an_unknown_category_never_reaches_wfx(api):
    result = api._catalog.prepare("Khong Ton Tai")

    assert result["code"] == "CATEGORY_UNKNOWN"
    assert api._login.calls == []


def test_preparing_remembers_the_category_for_the_next_search(api):
    api._catalog.prepare(APPAREL)

    assert api._catalog.prepared_category == APPAREL
    assert api._login.calls == [("prepare_catalog_master", APPAREL, "01")]


def test_a_failed_preparation_leaves_no_category_remembered(api):
    api._login.prepare_result = {
        "ok": False,
        "code": "CATALOG_DATA_NOT_READY",
        "message": "Grid chưa ổn định.",
    }

    api._catalog.prepare(APPAREL)

    assert api._catalog.prepared_category is None


def test_preparing_clears_whatever_result_was_open_before(api):
    api._catalog.result = {"article_code": "F0001", "category_name": APPAREL}
    api._catalog.active_article_destination = ("f0001", "costsheet")

    api._catalog.prepare(APPAREL)

    assert api._catalog.result is None
    assert api._catalog.active_article_destination is None


def test_an_older_automation_build_opens_the_module_then_sets_the_category(
    tmp_path,
):
    api = _api(tmp_path, LegacyLogin())

    result = api._catalog.prepare(APPAREL)

    assert result["code"] == "CATEGORY_SELECTED"
    assert api._login.calls == [
        ("open_module", "Catalog"),
        ("set_category", APPAREL, "01"),
    ]


def test_an_older_build_that_cannot_open_the_module_stops_there(tmp_path):
    login = LegacyLogin()
    login.module_result = {
        "ok": False,
        "code": "CATALOG_MENU_NOT_FOUND",
        "message": "Không thấy menu.",
    }
    api = _api(tmp_path, login)

    result = api._catalog.prepare(APPAREL)

    assert result["code"] == "CATALOG_MENU_NOT_FOUND"
    assert [call[0] for call in login.calls] == ["open_module"]


# --- duyệt Category -----------------------------------------------------


def test_browsing_an_unknown_category_never_reaches_wfx(api):
    result = api._catalog.browse("Khong Ton Tai")

    assert result["code"] == "CATEGORY_UNKNOWN"
    assert api._login.calls == []


def test_an_automation_build_without_folder_support_says_so_plainly(api):
    result = api._catalog.browse(APPAREL)

    assert result["code"] == "CATALOG_FOLDER_OPEN_UNSUPPORTED"


# --- tìm theo từng bước -------------------------------------------------


def test_finding_before_opening_the_catalog_asks_the_user_to_open_it(api):
    result = api._catalog.find("find_code", APPAREL, "code", "F0001", None)

    assert result["code"] == "CATALOG_PREPARE_REQUIRED"
    assert "Mở Catalog" in result["message"]


def test_finding_in_an_unknown_category_is_refused(api):
    result = api._catalog.find("find_code", "La Lam", "code", "F0001", None)

    assert result["code"] == "CATEGORY_UNKNOWN"


def test_an_automation_build_without_step_search_says_so_plainly(api):
    _prepared(api)
    del api._login.find_in_open_catalog

    result = api._catalog.find("find_code", APPAREL, "code", "F0001", None)

    assert result["code"] == "CATALOG_SEARCH_UNSUPPORTED"


def test_a_found_style_is_remembered_so_costing_can_reuse_the_popup(api):
    _prepared(api)

    result = api._catalog.find("find_code", APPAREL, "code", " F0001 ", None)

    assert result["code"] == "RESULT_OPENED"
    assert api._catalog.result == {
        "article_code": "F0001",
        "category_name": APPAREL,
        "filter_kind": "code",
        "query": "F0001",
        "style_status": "Open",
    }
    assert api._catalog.active_article_destination is None


def test_several_results_leave_no_remembered_style(api):
    _prepared(api)
    api._login.find_result = {
        "ok": True,
        "code": "MULTIPLE_RESULTS",
        "message": "Có 3 kết quả.",
        "codes": ["F0001", "F0002", "F0003"],
    }

    api._catalog.find("find_code", APPAREL, "code", "F000", None)

    assert api._catalog.result is None


def test_losing_the_search_context_forces_the_catalog_to_be_opened_again(api):
    _prepared(api)
    api._login.find_result = {
        "ok": False,
        "code": "CATALOG_SEARCH_CONTEXT_LOST",
        "message": "Grid đã đổi.",
    }

    api._catalog.find("find_code", APPAREL, "code", "F0001", None)

    assert api._catalog.prepared_category is None
    assert api._catalog.result is None


# --- một nút cho Tìm/Costing/BOM/File -----------------------------------


def test_an_unknown_category_stops_the_combined_action(api):
    result = api._catalog.action("La Lam", "code", "F0001", "costsheet")

    assert result["code"] == "CATEGORY_UNKNOWN"
    assert api._login.calls == []


def test_an_unknown_filter_kind_stops_the_combined_action(api):
    result = api._catalog.action(APPAREL, "mau_sac", "F0001", None)

    assert result["ok"] is False
    assert api._login.calls == []


def test_the_combined_action_opens_the_catalog_then_searches(api):
    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["code"] == "RESULT_OPENED"
    assert [call[0] for call in api._login.calls] == [
        "prepare_catalog_master",
        "find",
    ]
    assert api._catalog.prepared_category == APPAREL


def test_a_second_action_reuses_the_master_already_open(api):
    api._catalog.action(APPAREL, "code", "F0001", None)
    api._login.calls.clear()

    api._catalog.action(APPAREL, "code", "F0002", None)

    assert [call[0] for call in api._login.calls] == ["find"]


def test_a_master_that_lost_its_context_is_opened_again_before_searching(api):
    api._catalog.action(APPAREL, "code", "F0001", None)
    api._login.calls.clear()
    lost = {
        "ok": False,
        "code": "CATALOG_SEARCH_CONTEXT_LOST",
        "message": "Grid đã đổi.",
    }
    good = dict(api._login.find_result)
    outcomes = [lost, good]
    api._login.find_in_open_catalog = (
        lambda *_args, **_kwargs: outcomes.pop(0) if outcomes else good
    )

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["code"] == "RESULT_OPENED"
    assert [call[0] for call in api._login.calls] == ["prepare_catalog_master"]


def test_a_catalog_that_cannot_be_prepared_stops_before_searching(api):
    api._login.prepare_result = {
        "ok": False,
        "code": "CATALOG_DATA_NOT_READY",
        "message": "Grid chưa ổn định.",
    }

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["code"] == "CATALOG_DATA_NOT_READY"
    assert [call[0] for call in api._login.calls] == ["prepare_catalog_master"]


def test_opening_costing_after_a_search_remembers_which_screen_is_open(api):
    result = api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert api._catalog.active_article_destination == ("f0001", "costsheet")


def test_the_same_article_and_destination_reuses_the_popup_without_searching(
    api,
):
    api._catalog.action(APPAREL, "code", "F0001", "costsheet")
    api._login.calls.clear()

    result = api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert result["article_code"] == "F0001"
    # Không tìm lại Catalog: chỉ mở lại đúng destination trên popup đang mở.
    assert [call[0] for call in api._login.calls] == ["destination"]


def test_an_expired_popup_falls_back_to_a_full_search(api):
    api._catalog.action(APPAREL, "code", "F0001", "costsheet")
    api._login.calls.clear()
    expired = {
        "ok": False,
        "code": "CATALOG_RESULT_EXPIRED",
        "message": "Popup đã đóng.",
    }
    good = dict(api._login.destination_result)
    outcomes = [expired, good]
    api._login.open_catalog_destination = (
        lambda *_args, **_kwargs: outcomes.pop(0) if outcomes else good
    )

    result = api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    # Master vẫn còn dùng được nên chỉ tìm lại, không mở lại Catalog từ đầu.
    assert [call[0] for call in api._login.calls] == ["find"]
    assert outcomes == [], "phải thử mở destination lần thứ hai sau khi tìm lại"


def test_a_destination_that_fails_after_the_search_is_returned_as_is(api):
    api._login.destination_result = {
        "ok": False,
        "code": "ARTICLE_DESTINATION_NOT_FOUND",
        "message": "Không thấy Costsheet.",
    }

    result = api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    assert result["code"] == "ARTICLE_DESTINATION_NOT_FOUND"
    assert api._catalog.active_article_destination is None


def test_a_search_that_found_nothing_never_tries_to_open_a_destination(api):
    api._login.find_result = {
        "ok": False,
        "code": "NO_RESULTS",
        "message": "Không tìm thấy.",
    }

    result = api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    assert result["code"] == "NO_RESULTS"
    assert "destination" not in [call[0] for call in api._login.calls]


def test_a_context_lost_answer_wipes_every_piece_of_catalog_state(api):
    api._catalog.action(APPAREL, "code", "F0001", "costsheet")
    api._login.find_in_open_catalog = lambda *_a, **_k: {
        "ok": False,
        "code": "CATALOG_SEARCH_CONTEXT_LOST",
        "message": "Grid đã đổi.",
    }
    api._login.prepare_result = {
        "ok": False,
        "code": "CATALOG_SEARCH_CONTEXT_LOST",
        "message": "Grid đã đổi.",
    }

    api._catalog.action(APPAREL, "code", "F0002", None)

    assert api._catalog.prepared_category is None
    assert api._catalog.result is None
    assert api._catalog.active_article_destination is None


def test_searching_without_a_destination_forgets_the_screen_that_was_open(api):
    api._catalog.action(APPAREL, "code", "F0001", "costsheet")

    api._catalog.action(APPAREL, "code", "F0002", None)

    assert api._catalog.active_article_destination is None


# --- mở Costing/BOM từ kết quả hiện tại ---------------------------------


def test_opening_a_destination_without_a_current_result_is_refused(api):
    result = api._catalog.open_destination("costsheet", "F0001")

    assert result["code"] == "CATALOG_RESULT_REQUIRED"


def test_opening_a_destination_for_another_article_invalidates_the_result(api):
    api._catalog.action(APPAREL, "code", "F0001", None)

    result = api._catalog.open_destination("costsheet", "F9999")

    assert result["code"] == "CATALOG_RESULT_CHANGED"
    assert api._catalog.result is None


def test_costing_and_bom_stay_apparel_only(api):
    _prepared(api, TRIMS)
    api._catalog.find("find_code", TRIMS, "code", "T0001", None)
    api._catalog.result = {
        "article_code": "T0001",
        "category_name": TRIMS,
        "filter_kind": "code",
        "query": "T0001",
        "style_status": None,
    }

    result = api._catalog.open_destination("costsheet", "T0001")

    assert result["code"] == "APPAREL_ONLY"


def test_an_automation_build_without_destinations_says_so_plainly(api):
    api._catalog.action(APPAREL, "code", "F0001", None)
    del api._login.open_catalog_destination

    result = api._catalog.open_destination("costsheet", "F0001")

    assert result["code"] == "CATALOG_DESTINATION_UNSUPPORTED"


def test_opening_a_destination_uses_the_article_already_found(api):
    api._catalog.action(APPAREL, "code", "F0001", None)
    api._login.calls.clear()

    result = api._catalog.open_destination("COSTSHEET", "f0001")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert api._login.calls == [("destination", "f0001", "costsheet")]


# --- gợi ý Article ------------------------------------------------------


def _library(api, rows):
    """Ghi thẳng file cache Article Library như một lượt sync đã thành công."""
    import json

    from wfx_panel.stores import article_library

    path = article_library._cache_path(api._base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": article_library.SCHEMA_VERSION,
                "remote_version": "test",
                "generated_at": "2026-01-01",
                "synced_at": 1.0,
                "sha256": "0" * 64,
                "sections": [
                    {"section_key": "*", "section_name": "All", "options": rows}
                ],
            }
        ),
        encoding="utf-8",
    )


def _row(code, name, reference, category=APPAREL):
    return {
        "article_code": code,
        "article_name": name,
        "buyer_reference": reference,
        "article_category": category,
    }


def test_a_query_shorter_than_two_characters_returns_nothing(api):
    result = api._catalog.suggest_articles(APPAREL, "code", "F")

    assert result["suggestions"] == []
    assert result["code"] == "ARTICLE_SUGGESTIONS"


def test_suggestions_are_empty_while_the_library_has_never_synced(api):
    result = api._catalog.suggest_articles(APPAREL, "code", "F00")

    assert result["suggestions"] == []


def test_an_unknown_filter_kind_yields_no_suggestion(api):
    _library(api, [_row("F0001", "JACKET", "PO-1")])

    assert (
        api._catalog.suggest_articles(APPAREL, "mau_sac", "F00")["suggestions"]
        == []
    )


def test_buyer_reference_suggestions_are_apparel_only(api):
    _library(api, [_row("T0001", "BUTTON", "PO-1", TRIMS)])

    assert (
        api._catalog.suggest_articles(TRIMS, "buyer_reference", "PO")[
            "suggestions"
        ]
        == []
    )


def test_suggestions_prefer_a_prefix_match_over_a_substring_match(api):
    _library(
        api,
        [
            _row("XF0012", "JACKET A", "PO-1"),
            _row("F0012", "JACKET B", "PO-2"),
        ],
    )

    suggestions = api._catalog.suggest_articles(APPAREL, "code", "F00")[
        "suggestions"
    ]

    assert [item["article_code"] for item in suggestions] == ["F0012", "XF0012"]


def test_suggestions_stay_inside_the_category_the_user_picked(api):
    _library(
        api,
        [
            _row("F0001", "JACKET", "PO-1"),
            _row("T0001", "JACKET TRIM", "PO-2", TRIMS),
        ],
    )

    suggestions = api._catalog.suggest_articles(APPAREL, "article_name", "JACK")[
        "suggestions"
    ]

    assert [item["article_code"] for item in suggestions] == ["F0001"]


def test_the_suggestion_limit_is_clamped_to_something_sane(api):
    _library(api, [_row(f"F{index:04d}", "JACKET", "PO") for index in range(60)])

    result = api._catalog.suggest_articles(APPAREL, "code", "F0", limit=9_999)

    assert len(result["suggestions"]) == 50


# --- validate trước khi chạm WFX ---------------------------------------


@pytest.mark.parametrize(
    ("category", "filter_kind", "query", "destination", "code"),
    [
        (APPAREL, "article_name", "JACKET", None, "INVALID_FILTER"),
        (TRIMS, "buyer_reference", "PO-1", None, "INVALID_FILTER"),
        (APPAREL, "code", "   ", None, "QUERY_REQUIRED"),
        (APPAREL, "code", "F0001", "ho_so", "ARTICLE_DESTINATION_UNKNOWN"),
        (TRIMS, "code", "T0001", "costsheet", "APPAREL_ONLY"),
        (TRIMS, "code", "T0001", "bom", "APPAREL_ONLY"),
    ],
)
def test_every_invalid_combination_is_named_before_chrome_is_touched(
    api, category, filter_kind, query, destination, code
):
    result = api._catalog.action(category, filter_kind, query, destination)

    assert result["code"] == code
    assert api._login.calls == []


def test_apparel_searches_by_buyer_reference_and_others_by_article_name(api):
    assert api._catalog.action(APPAREL, "buyer_reference", "PO-1", None)["ok"]
    api._login.calls.clear()
    api._catalog.prepared_category = None
    assert api._catalog.action(TRIMS, "article_name", "BUTTON", None)["ok"]


# --- duyệt folder mặc định ---------------------------------------------


def _save_default_folder(api, node_id):
    """Folder mặc định chỉ dùng lại được khi đúng User ID đang đăng nhập."""
    user_id = "tester"
    api._prefs.save_account(user_id, "", base_dir=api._base_dir)
    api._prefs.save_prefs(
        base_dir=api._base_dir,
        catalog_default_folder={
            "category_name": APPAREL,
            "category_value": "01",
            "user_id": user_id,
            "node_id": node_id,
            "node_code": "Folder",
            "name": "Folder",
            "path": ["Master", "Folder"],
            "path_label": "Master / Folder",
        },
    )


def _wire_folder_opener(api, outcomes):
    calls: list[str] = []

    def opener(category_name, value, node_id, log=print):
        calls.append(node_id)
        return outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]

    api._login.open_catalog_folder = opener
    return calls


def test_browsing_opens_the_saved_default_folder_for_apparel(api):
    calls = _wire_folder_opener(
        api,
        [{"ok": True, "code": "CATALOG_FOLDER_OPENED", "message": "Đã mở."}],
    )
    _save_default_folder(api, "7")

    result = api._catalog.browse(APPAREL)

    assert result["code"] == "CATALOG_FOLDER_OPENED"
    assert calls == ["7"]


def test_a_default_folder_that_disappeared_falls_back_to_master(api):
    calls = _wire_folder_opener(
        api,
        [
            {"ok": False, "code": "CATALOG_FOLDER_STALE", "message": "Mất folder."},
            {"ok": True, "code": "CATALOG_FOLDER_OPENED", "message": "Đã mở."},
        ],
    )
    _save_default_folder(api, "99")

    result = api._catalog.browse(APPAREL)

    assert result["code"] == "CATALOG_FOLDER_FALLBACK"
    assert "Đã chuyển về Master" in result["message"]
    assert calls == ["99", ""]
    # Prefs phải được ghi lại về Master, nếu không lần sau vẫn thử folder chết.
    saved = api._prefs.load_prefs(base_dir=api._base_dir)["catalog_default_folder"]
    assert saved["category_name"] == APPAREL


def test_a_fallback_that_also_fails_returns_the_original_stale_answer(api):
    _wire_folder_opener(
        api,
        [
            {"ok": False, "code": "CATALOG_FOLDER_STALE", "message": "Mất folder."},
            {"ok": False, "code": "CATALOG_MENU_NOT_FOUND", "message": "Hỏng."},
        ],
    )

    result = api._catalog.browse(APPAREL)

    assert result["code"] == "CATALOG_FOLDER_STALE"


def test_a_non_apparel_category_never_reads_the_saved_apparel_folder(api):
    calls = _wire_folder_opener(
        api,
        [{"ok": True, "code": "CATALOG_FOLDER_OPENED", "message": "Đã mở."}],
    )
    _save_default_folder(api, "7")

    api._catalog.browse(TRIMS)

    assert calls == [""]


# --- các delegator mỏng -------------------------------------------------


def test_the_library_helpers_go_straight_to_the_store(api, monkeypatch):
    from wfx_panel.stores import article_library

    seen: list[str] = []
    monkeypatch.setattr(
        article_library,
        "sync",
        lambda base_dir, log: seen.append("sync") or {"ok": True},
    )

    assert api._catalog.sync_article_library() == {"ok": True}
    assert seen == ["sync"]


def test_the_cached_folder_helper_delegates_to_the_folder_controller(
    api, monkeypatch
):
    monkeypatch.setattr(
        api._catalog.folders,
        "_cached_folders",
        lambda category_name: [{"node_id": category_name}],
    )

    assert api._catalog._cached_folders(APPAREL) == [{"node_id": APPAREL}]


def test_a_result_cleared_between_two_checks_falls_back_to_a_full_search(api):
    """Một flow khác vừa reset Catalog ngay giữa lúc lượt này đang tái dùng."""
    api._catalog.action(APPAREL, "code", "F0001", "costsheet")
    from wfx_panel.controllers.catalog import CatalogActionRequest

    def cleared(_request):
        api._catalog.result = None
        return True

    api._catalog._matches_current_result = cleared
    request = CatalogActionRequest(APPAREL, "code", "F0001", "costsheet")

    assert api._catalog._reuse_current_catalog_result(request) is None


def test_an_older_build_prepares_the_catalog_inside_the_combined_action(
    tmp_path,
):
    api = _api(tmp_path, LegacyLogin())

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["code"] == "RESULT_OPENED"
    assert [call[0] for call in api._login.calls] == [
        "open_module",
        "set_category",
        "find",
    ]


def test_an_older_build_that_cannot_open_the_catalog_stops_the_action(tmp_path):
    login = LegacyLogin()
    login.module_result = {
        "ok": False,
        "code": "CATALOG_MENU_NOT_FOUND",
        "message": "Không thấy menu.",
    }
    api = _api(tmp_path, login)

    result = api._catalog.action(APPAREL, "code", "F0001", None)

    assert result["code"] == "CATALOG_MENU_NOT_FOUND"
    assert "find" not in [call[0] for call in login.calls]


def test_articles_that_do_not_contain_the_query_are_left_out(api):
    _library(
        api,
        [
            _row("F0012", "JACKET", "PO-1"),
            _row("T9999", "TRIM", "PO-2"),
        ],
    )

    suggestions = api._catalog.suggest_articles(APPAREL, "code", "F00")[
        "suggestions"
    ]

    assert [item["article_code"] for item in suggestions] == ["F0012"]
