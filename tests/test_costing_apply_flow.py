"""Apply Costing: phase 2 ghi dữ liệu thật lên WFX.

`wfx_panel/automation/costing/apply.py` ở mức 47%. Đây là flow GHI đắt nhất của
app, và CLAUDE.md đặt ra hàng loạt điều kiện nằm đúng trong phần chưa chạy:

* "Import và Apply chỉ được bật khi Costing hiện tại có status chính xác là
  `Open`; nếu status khác `Open` hoặc chưa có Costing, app dừng với
  `COSTING_NOT_OPEN`."
* phase 2 phải "re-scan/chống stale, apply plan server-side, Save trong
  `cancellation_deferred()` và đọc lại field đã đổi để xác nhận".
* "Add Article … 0 kết quả thì skip/báo, nhiều kết quả thì chờ user resolve."
* Khi hỏng, "message tuyệt đối không được nói là đã Save thành công".
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from wfx_panel.automation.costing import apply as costing_apply
from wfx_panel.automation.costing.constants import (
    CostingApplyAbort,
    CostingFieldApplyError,
)


def _quiet():
    return lambda _line: None


def _plan(**overrides) -> dict:
    base = {
        "new_required": False,
        "additions": [],
        "cost_line_additions": [],
        "splits": [],
        "deletes": [],
        "fields_to_set": [],
        "live_signature": "sig",
        "costing_status": "Open",
    }
    base.update(overrides)
    return base


# --- validate trước khi chạm Chrome --------------------------------------


def test_a_costing_that_is_not_open_is_refused_before_anything_else():
    result = costing_apply._validate_costing_apply_request(
        "ABC", _plan(new_required=True), None
    )

    assert result["code"] == "COSTING_NOT_OPEN"
    assert result["article_code"] == "ABC"


@pytest.mark.parametrize(
    "mutation",
    ["additions", "cost_line_additions", "splits", "deletes"],
)
def test_a_plan_that_touches_articles_needs_its_source_document(mutation):
    result = costing_apply._validate_costing_apply_request(
        "ABC", _plan(**{mutation: [{"article_code": "F-001"}]}), None
    )

    assert result["code"] == "COSTING_SOURCE_REQUIRED"


def test_a_plan_with_its_source_document_passes_validation():
    assert (
        costing_apply._validate_costing_apply_request(
            "ABC", _plan(additions=[{"article_code": "F-001"}]), {"fields": []}
        )
        is None
    )


def test_a_field_only_plan_needs_no_source_document():
    assert (
        costing_apply._validate_costing_apply_request(
            "ABC", _plan(fields_to_set=[{"field_key": "colUsage"}]), None
        )
        is None
    )


@pytest.mark.parametrize(
    "key",
    ["additions", "cost_line_additions", "splits", "deletes", "fields_to_set"],
)
def test_any_non_empty_bucket_counts_as_a_change(key):
    assert costing_apply._costing_plan_has_changes(_plan(**{key: [{}]})) is True


def test_an_empty_plan_has_no_change():
    assert costing_apply._costing_plan_has_changes(_plan()) is False


# --- phạm vi tab ----------------------------------------------------------


class _Context:
    def __init__(self, pages=()):
        self.pages = list(pages)


def test_a_plan_that_is_not_tab_scoped_never_reads_the_active_tab(monkeypatch):
    called: list[int] = []
    monkeypatch.setattr(
        costing_apply, "_active_costing_page", lambda _ctx: called.append(1)
    )

    assert costing_apply._costing_apply_scope(_Context(), "ABC", False) is None
    assert called == []


def test_the_active_tab_is_accepted_when_it_holds_the_same_style(monkeypatch):
    page = object()
    monkeypatch.setattr(costing_apply, "_active_costing_page", lambda _ctx: page)
    monkeypatch.setattr(
        costing_apply, "_article_code_from_page", lambda _page: "abc"
    )

    assert costing_apply._costing_apply_scope(_Context(), "ABC", True) == [page]


def test_an_active_tab_holding_another_style_aborts_the_apply(monkeypatch):
    monkeypatch.setattr(costing_apply, "_active_costing_page", lambda _ctx: object())
    monkeypatch.setattr(
        costing_apply, "_article_code_from_page", lambda _page: "XYZ"
    )

    with pytest.raises(CostingApplyAbort) as error:
        costing_apply._costing_apply_scope(_Context(), "ABC", True)

    assert error.value.result["code"] == "COSTING_STYLE_MISMATCH"
    assert error.value.result["file_style"] == "ABC"
    assert error.value.result["live_style"] == "XYZ"


def test_an_active_tab_with_no_readable_style_aborts_the_apply(monkeypatch):
    monkeypatch.setattr(costing_apply, "_active_costing_page", lambda _ctx: object())
    monkeypatch.setattr(costing_apply, "_article_code_from_page", lambda _page: "")

    with pytest.raises(CostingApplyAbort) as error:
        costing_apply._costing_apply_scope(_Context(), "ABC", True)

    assert error.value.result["code"] == "COSTING_STYLE_NOT_DETECTED"


# --- mở phiên apply -------------------------------------------------------


class _Browser:
    def __init__(self, context):
        self.contexts = [context]


def _wire_session(monkeypatch, *, status="Open", signature="sig"):
    page, frame = object(), object()
    monkeypatch.setattr(
        costing_apply, "_costing_frame", lambda *a, **kw: (page, frame)
    )
    monkeypatch.setattr(
        costing_apply, "_selected_costing_title", lambda *a, **kw: "Costing"
    )
    monkeypatch.setattr(
        costing_apply,
        "_inventory_costing_frame",
        lambda *a, **kw: {"cost_sheet_status": status, "fields": []},
    )
    monkeypatch.setattr(costing_apply, "live_signature", lambda _live: signature)
    return page, frame


def test_a_session_opens_when_the_costing_is_open_and_unchanged(monkeypatch):
    page, frame = _wire_session(monkeypatch)

    session = costing_apply._open_costing_apply_session(
        _Browser(_Context()), "ABC", _plan(), None, False, _quiet()
    )

    assert session.article_code == "ABC"
    assert session.costing_page is page
    assert session.frame is frame


@pytest.mark.parametrize("status", ["Approved", "Closed", ""])
def test_a_costing_that_left_open_aborts_the_apply(monkeypatch, status):
    _wire_session(monkeypatch, status=status)

    with pytest.raises(CostingApplyAbort) as error:
        costing_apply._open_costing_apply_session(
            _Browser(_Context()), "ABC", _plan(), None, False, _quiet()
        )

    assert error.value.result["code"] == "COSTING_NOT_OPEN"


def test_a_costing_that_changed_since_the_dry_run_aborts_the_apply(monkeypatch):
    _wire_session(monkeypatch, signature="khac")

    with pytest.raises(CostingApplyAbort) as error:
        costing_apply._open_costing_apply_session(
            _Browser(_Context()), "ABC", _plan(), None, False, _quiet()
        )

    assert error.value.result["code"] == "COSTING_PLAN_STALE"


# --- chuẩn hoá lựa chọn Article của người dùng ---------------------------


def test_article_resolutions_drop_blank_keys_and_values():
    assert costing_apply._normalize_article_resolutions(
        {"item-1": " F-001 ", "  ": "X", "item-2": "  ", "item-3": "T-009"}
    ) == {"item-1": "F-001", "item-3": "T-009"}


def test_article_resolutions_of_none_are_empty():
    assert costing_apply._normalize_article_resolutions(None) == {}


def test_missing_article_codes_fall_back_to_the_name():
    assert costing_apply._missing_article_codes(
        {"missing": [{"article_code": "F-001"}, {"article_name": "Vải"}]}
    ) == {"f-001", "vải"}


# --- chuẩn bị Article -----------------------------------------------------


class _Session:
    def __init__(self, **overrides):
        self.article_code = "ABC"
        self.browser = None
        self.context = _Context()
        self.costing_page = object()
        self.frame = object()
        self.scoped_pages = None
        self.live = {"fields": []}
        self.working_plan = _plan()
        self.source_document = None
        self.log = _quiet()
        for key, value in overrides.items():
            setattr(self, key, value)


def _wire_prepare(monkeypatch, *, preflight=None, refreshes=None):
    # `refreshes or []` sẽ tạo list mới khi truyền vào list rỗng, nên giữ
    # đúng tham chiếu mà test đang quan sát.
    sink = refreshes if refreshes is not None else []
    monkeypatch.setattr(
        costing_apply,
        "_preflight_article_additions",
        lambda *a: dict(
            preflight or {"found": [], "missing": [], "ambiguous": []}
        ),
    )
    monkeypatch.setattr(costing_apply, "_delete_articles", lambda *a: [])
    monkeypatch.setattr(costing_apply, "_add_articles", lambda *a: [])
    monkeypatch.setattr(costing_apply, "_add_special_cost_lines", lambda *a: [])
    monkeypatch.setattr(
        costing_apply,
        "_refresh_apply_inventory",
        lambda *a, **kw: sink.append(kw),
    )


def test_ambiguous_articles_stop_before_anything_is_written(monkeypatch):
    deleted: list[int] = []
    _wire_prepare(
        monkeypatch,
        preflight={
            "found": [],
            "missing": [],
            "ambiguous": [{"article_code": "F-001", "candidates": [1, 2]}],
        },
    )
    monkeypatch.setattr(
        costing_apply, "_delete_articles", lambda *a: deleted.append(1) or []
    )
    progress = costing_apply._CostingApplyProgress()

    with pytest.raises(CostingApplyAbort) as error:
        costing_apply._prepare_costing_articles(_Session(), progress, None)

    assert error.value.result["code"] == "COSTING_ARTICLE_AMBIGUOUS"
    assert error.value.result["ambiguous_articles"]
    assert deleted == []


def test_the_inventory_is_refreshed_after_articles_change(monkeypatch):
    refreshes: list[dict] = []
    _wire_prepare(monkeypatch, refreshes=refreshes)
    monkeypatch.setattr(
        costing_apply, "_add_articles", lambda *a: [{"article_code": "F-001"}]
    )
    progress = costing_apply._CostingApplyProgress()

    costing_apply._prepare_costing_articles(_Session(), progress, None)

    assert refreshes == [{"wait_ms": 500}]
    assert progress.added == [{"article_code": "F-001"}]


def test_the_inventory_is_refreshed_after_cost_lines_change(monkeypatch):
    refreshes: list[dict] = []
    _wire_prepare(monkeypatch, refreshes=refreshes)
    monkeypatch.setattr(
        costing_apply, "_add_special_cost_lines", lambda *a: [{"x": 1}]
    )
    progress = costing_apply._CostingApplyProgress()

    costing_apply._prepare_costing_articles(_Session(), progress, None)

    assert refreshes == [{"wait_ms": 350}]


def test_nothing_changed_means_no_refresh(monkeypatch):
    refreshes: list[dict] = []
    _wire_prepare(monkeypatch, refreshes=refreshes)
    progress = costing_apply._CostingApplyProgress()

    costing_apply._prepare_costing_articles(_Session(), progress, None)

    assert refreshes == []


# --- splitter -------------------------------------------------------------


def test_splits_of_an_article_wfx_never_found_are_skipped(monkeypatch):
    split_calls: list[dict] = []
    monkeypatch.setattr(
        costing_apply,
        "_split_article_row",
        lambda _frame, _live, request: split_calls.append(dict(request)),
    )
    monkeypatch.setattr(costing_apply, "_refresh_apply_inventory", lambda *a, **kw: None)
    progress = costing_apply._CostingApplyProgress()
    progress.preflight = {"missing": [{"article_code": "F-999"}]}
    session = _Session(
        working_plan=_plan(
            splits=[{"article_code": "F-999"}, {"article_code": "F-001"}]
        )
    )

    costing_apply._apply_costing_splits(session, progress)

    assert split_calls == [{"article_code": "F-001"}]
    assert progress.split == [{"article_code": "F-001"}]


def test_the_plan_is_rebuilt_once_after_splitting(monkeypatch):
    monkeypatch.setattr(costing_apply, "_split_article_row", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_refresh_apply_inventory", lambda *a, **kw: None)
    rebuilds: list[int] = []
    monkeypatch.setattr(
        costing_apply,
        "build_costing_plan",
        lambda _source, _live: rebuilds.append(1) or _plan(),
    )
    progress = costing_apply._CostingApplyProgress()
    progress.preflight = {"missing": []}
    session = _Session(
        working_plan=_plan(splits=[{"article_code": "F-001"}]),
        source_document={"fields": []},
    )

    costing_apply._apply_costing_splits(session, progress)

    assert rebuilds == [1]


def test_no_split_means_no_rebuild(monkeypatch):
    rebuilds: list[int] = []
    monkeypatch.setattr(
        costing_apply,
        "build_costing_plan",
        lambda *_a: rebuilds.append(1) or _plan(),
    )
    progress = costing_apply._CostingApplyProgress()
    progress.preflight = {"missing": []}

    costing_apply._apply_costing_splits(_Session(), progress)

    assert rebuilds == []


# --- điền field -----------------------------------------------------------


def _change(**overrides) -> dict:
    base = {
        "scope": "item",
        "section_key": "section-1-fabric",
        "item_key": "item-1",
        "field_key": "colUsage",
        "value": "5",
    }
    base.update(overrides)
    return base


def test_the_change_key_is_case_insensitive_on_every_part():
    assert costing_apply._costing_change_key(
        {
            "scope": "Item",
            "section_key": "S1",
            "item_key": "I1",
            "field_key": "ColUsage",
        }
    ) == ("item", "s1", "i1", "colusage")


def test_a_change_of_an_article_wfx_never_found_is_recognised():
    assert (
        costing_apply._change_belongs_to_missing_article(_change(), {"item-1"})
        is True
    )
    assert (
        costing_apply._change_belongs_to_missing_article(
            _change(scope="section"), {"item-1"}
        )
        is False
    )


def _wire_field(monkeypatch, *, variant=None, dependency="", fails=None):
    monkeypatch.setattr(
        costing_apply, "_material_variant_config", lambda _field: variant
    )
    monkeypatch.setattr(
        costing_apply, "_add_missing_material_variant", lambda *a: True
    )
    monkeypatch.setattr(
        costing_apply, "_dependency_kind", lambda _field, _value: dependency
    )
    applied: list[tuple] = []
    monkeypatch.setattr(
        costing_apply,
        "_set_dependency_mapping",
        lambda _frame, field, value: applied.append(("dependency", value)),
    )

    def set_field(_frame, _field, value):
        if fails is not None:
            raise fails
        applied.append(("field", value))

    monkeypatch.setattr(costing_apply, "_set_live_field", set_field)
    return applied


def _live_index(editable=True):
    return {
        ("item", "section-1-fabric", "item-1", "colusage"): {
            "editable": editable,
            "field_key": "colUsage",
        }
    }


def test_a_plain_field_is_written_and_recorded(monkeypatch):
    applied = _wire_field(monkeypatch)
    progress = costing_apply._CostingApplyProgress()

    costing_apply._apply_single_costing_field(
        _Session(), progress, _live_index(), _change(), 1, 1
    )

    assert applied == [("field", "5")]
    assert progress.applied == [_change()]


def test_a_dependency_field_goes_through_the_popup_instead(monkeypatch):
    applied = _wire_field(monkeypatch, dependency="Color")
    progress = costing_apply._CostingApplyProgress()

    costing_apply._apply_single_costing_field(
        _Session(), progress, _live_index(), _change(), 1, 1
    )

    assert applied == [("dependency", "5")]
    assert progress.dependency_confirmed


def test_a_missing_material_variant_is_added_before_the_field_is_written(
    monkeypatch,
):
    applied = _wire_field(monkeypatch, variant={"kind": "Color"})
    progress = costing_apply._CostingApplyProgress()

    costing_apply._apply_single_costing_field(
        _Session(), progress, _live_index(), _change(), 1, 1
    )

    assert progress.material_variants_added == [_change()]
    assert applied == [("field", "5")]


@pytest.mark.parametrize("editable", [False])
def test_a_read_only_field_is_skipped_with_a_reason(monkeypatch, editable):
    _wire_field(monkeypatch)
    progress = costing_apply._CostingApplyProgress()

    costing_apply._apply_single_costing_field(
        _Session(), progress, _live_index(editable), _change(), 1, 1
    )

    assert progress.skipped[0]["reason"] == "not_found_or_read_only"
    assert progress.applied == []


def test_a_field_that_is_not_on_the_live_costing_is_skipped(monkeypatch):
    _wire_field(monkeypatch)
    progress = costing_apply._CostingApplyProgress()

    costing_apply._apply_single_costing_field(
        _Session(), progress, {}, _change(), 1, 1
    )

    assert progress.skipped[0]["reason"] == "not_found_or_read_only"


def test_a_field_wfx_refuses_stops_the_apply_with_its_context(monkeypatch):
    _wire_field(monkeypatch, fails=PlaywrightError("editor không mở"))
    progress = costing_apply._CostingApplyProgress()
    logs: list[str] = []

    with pytest.raises(CostingFieldApplyError) as error:
        costing_apply._apply_single_costing_field(
            _Session(log=logs.append),
            progress,
            _live_index(),
            _change(),
            3,
            7,
        )

    assert error.value.field_key == "colUsage"
    assert error.value.item_key == "item-1"
    assert any("3/7" in line for line in logs)


def test_every_change_of_a_missing_article_is_skipped_up_front(monkeypatch):
    _wire_field(monkeypatch)
    progress = costing_apply._CostingApplyProgress()
    progress.preflight = {"missing": [{"import_item_key": "item-1"}]}
    monkeypatch.setattr(
        costing_apply, "_live_field_index", lambda _live: _live_index()
    )
    session = _Session(working_plan=_plan(fields_to_set=[_change()]))

    costing_apply._apply_costing_fields(session, progress)

    assert progress.skipped[0]["reason"] == "article_not_found"
    assert progress.applied == []


def test_progress_is_logged_on_the_first_and_every_tenth_field(monkeypatch):
    _wire_field(monkeypatch)
    progress = costing_apply._CostingApplyProgress()
    progress.preflight = {"missing": []}
    monkeypatch.setattr(
        costing_apply, "_live_field_index", lambda _live: _live_index()
    )
    monkeypatch.setattr(costing_apply, "_field_application_priority", lambda _c: 0)
    logs: list[str] = []
    session = _Session(
        working_plan=_plan(fields_to_set=[_change() for _ in range(12)]),
        log=logs.append,
    )

    costing_apply._apply_costing_fields(session, progress)

    counters = [line for line in logs if "Đã điền" in line]
    assert len(counters) == 2
    assert "1/12" in counters[0]
    assert "10/12" in counters[1]


# --- kết quả khi không có gì đổi -----------------------------------------


def test_a_plan_with_no_change_never_saves(monkeypatch):
    saved: list[int] = []
    monkeypatch.setattr(costing_apply, "_save_costing", lambda *a: saved.append(1))

    result = costing_apply._run_costing_apply(_Session(), None)

    assert result["code"] == "COSTING_APPLIED"
    assert result["no_changes"] is True
    assert result["applied_count"] == 0
    assert saved == []


# --- vỏ entry point -------------------------------------------------------


class _Driver:
    def stop(self):
        return None


class _Starter:
    def start(self):
        return _Driver()


def _wire_entry(monkeypatch, *, chrome_ready=True, logged_in=True):
    monkeypatch.setattr(costing_apply, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(costing_apply, "_chrome_is_ready", lambda: chrome_ready)
    monkeypatch.setattr(
        costing_apply,
        "_connect_to_chrome",
        lambda _playwright, **_kw: (_Browser(_Context()), object()),
    )
    monkeypatch.setattr(costing_apply, "_attach_dialog_handler", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_session_is_active", lambda _page: logged_in)


def test_apply_reports_a_closed_browser(monkeypatch):
    _wire_entry(monkeypatch, chrome_ready=False)

    assert costing_apply.apply_costing_plan("ABC", _plan())["code"] == "CHROME_CLOSED"


def test_apply_reports_an_expired_session(monkeypatch):
    _wire_entry(monkeypatch, logged_in=False)

    assert costing_apply.apply_costing_plan("ABC", _plan())["code"] == "NOT_LOGGED_IN"


def test_apply_returns_the_result_of_the_run(monkeypatch):
    _wire_entry(monkeypatch)
    monkeypatch.setattr(
        costing_apply, "_open_costing_apply_session", lambda *a: _Session()
    )
    monkeypatch.setattr(
        costing_apply,
        "_run_costing_apply",
        lambda *a: {"ok": True, "code": "COSTING_APPLIED"},
    )

    assert costing_apply.apply_costing_plan("ABC", _plan())["code"] == "COSTING_APPLIED"


def test_an_abort_keeps_its_own_structured_result(monkeypatch):
    _wire_entry(monkeypatch)
    monkeypatch.setattr(
        costing_apply,
        "_open_costing_apply_session",
        lambda *a: (_ for _ in ()).throw(
            CostingApplyAbort({"ok": False, "code": "COSTING_PLAN_STALE"})
        ),
    )

    assert (
        costing_apply.apply_costing_plan("ABC", _plan())["code"]
        == "COSTING_PLAN_STALE"
    )


def test_a_field_failure_names_the_field_and_never_claims_a_save(monkeypatch):
    _wire_entry(monkeypatch)
    monkeypatch.setattr(
        costing_apply,
        "_open_costing_apply_session",
        lambda *a: (_ for _ in ()).throw(
            CostingFieldApplyError("colUsage", "item-1", "editor không mở")
        ),
    )

    result = costing_apply.apply_costing_plan("ABC", _plan())

    assert result["code"] == "COSTING_FIELD_APPLY_FAILED"
    assert result["failed_field"] == "colUsage"
    assert result["failed_item"] == "item-1"
    assert result["failure_reason"] == "editor không mở"
    assert "thành công" not in result["message"]


def test_a_timeout_that_carries_a_costing_code_keeps_it(monkeypatch):
    _wire_entry(monkeypatch)
    monkeypatch.setattr(
        costing_apply,
        "_open_costing_apply_session",
        lambda *a: (_ for _ in ()).throw(
            PlaywrightTimeoutError("COSTING_GRID_NOT_FOUND")
        ),
    )

    assert (
        costing_apply.apply_costing_plan("ABC", _plan())["code"]
        == "COSTING_GRID_NOT_FOUND"
    )


def test_a_plain_timeout_becomes_the_generic_apply_failure(monkeypatch):
    _wire_entry(monkeypatch)
    monkeypatch.setattr(
        costing_apply,
        "_open_costing_apply_session",
        lambda *a: (_ for _ in ()).throw(PlaywrightTimeoutError("chậm")),
    )

    assert (
        costing_apply.apply_costing_plan("ABC", _plan())["code"]
        == "COSTING_APPLY_FAILED"
    )


def test_an_unexpected_failure_never_claims_the_save_succeeded(monkeypatch):
    _wire_entry(monkeypatch)
    monkeypatch.setattr(
        costing_apply,
        "_open_costing_apply_session",
        lambda *a: (_ for _ in ()).throw(RuntimeError("COSTING_SPLITTER_NOT_FOUND:1")),
    )
    logs: list[str] = []

    result = costing_apply.apply_costing_plan("ABC", _plan(), log=logs.append)

    assert result["code"] == "COSTING_SPLITTER_NOT_FOUND"
    assert "chưa xác nhận Save thành công" in result["message"]
    assert logs


# --- xác nhận sau Save ----------------------------------------------------


def _applied(progress, *changes):
    progress.applied = [dict(change) for change in changes]
    return progress


def test_a_field_wfx_saved_correctly_is_not_a_mismatch(monkeypatch):
    monkeypatch.setattr(
        costing_apply,
        "_live_field_index",
        lambda _verified: {
            ("item", "section-1-fabric", "item-1", "colusage"): {"value": "5"}
        },
    )
    progress = _applied(costing_apply._CostingApplyProgress(), _change())

    assert costing_apply._field_verification_mismatches({}, progress) == []


def test_a_field_wfx_did_not_keep_is_reported_with_both_values(monkeypatch):
    monkeypatch.setattr(
        costing_apply,
        "_live_field_index",
        lambda _verified: {
            ("item", "section-1-fabric", "item-1", "colusage"): {"value": "9"}
        },
    )
    progress = _applied(costing_apply._CostingApplyProgress(), _change())

    assert costing_apply._field_verification_mismatches({}, progress) == [
        {"field_key": "colUsage", "expected": "5", "actual": "9"}
    ]


def test_a_dependency_field_is_never_re_checked_against_the_main_grid(
    monkeypatch,
):
    """Grid chính chỉ hiện [Table]; popup đã được tick exact lúc apply."""
    monkeypatch.setattr(
        costing_apply,
        "_live_field_index",
        lambda _verified: {
            ("item", "section-1-fabric", "item-1", "colusage"): {"value": "[Table]"}
        },
    )
    progress = _applied(costing_apply._CostingApplyProgress(), _change())
    progress.dependency_confirmed.add(
        ("item", "section-1-fabric", "item-1", "colusage")
    )

    assert costing_apply._field_verification_mismatches({}, progress) == []


def test_an_article_that_is_missing_after_save_is_reported():
    progress = costing_apply._CostingApplyProgress()
    progress.added = [{"resolved_code": "F-001"}]

    assert costing_apply._article_verification_mismatches(
        {"items": []}, progress
    ) == [
        {
            "field_key": "Article:F-001",
            "expected": "present",
            "actual": "missing_after_save",
        }
    ]


def test_an_article_that_survived_a_delete_is_reported():
    progress = costing_apply._CostingApplyProgress()
    progress.deleted = [{"article_code": "F-001"}]

    assert costing_apply._article_verification_mismatches(
        {"items": [{"article_code": "f-001"}]}, progress
    ) == [
        {
            "field_key": "Article:F-001",
            "expected": "deleted",
            "actual": "still_present_after_save",
        }
    ]


def test_articles_that_were_added_and_deleted_correctly_are_silent():
    progress = costing_apply._CostingApplyProgress()
    progress.added = [{"resolved_code": "F-001"}]
    progress.deleted = [{"article_code": "T-009"}]

    assert (
        costing_apply._article_verification_mismatches(
            {"items": [{"article_code": "F-001"}]}, progress
        )
        == []
    )


def test_a_cost_line_that_is_missing_after_save_is_reported():
    assert costing_apply._cost_line_verification_mismatches(
        {"items": []},
        [{"section_key": "s1", "article_name": "Nha may A"}],
    ) == [
        {
            "field_key": "Cost line:Nha may A",
            "expected": "present",
            "actual": "missing_after_save",
        }
    ]


def test_a_cost_line_wfx_kept_is_silent():
    verified = {
        "items": [
            {
                "section_key": "S1",
                "article_name": "nha may a",
                "item_type": "cost_line",
            }
        ]
    }

    assert (
        costing_apply._cost_line_verification_mismatches(
            verified, [{"section_key": "s1", "article_name": "Nha may A"}]
        )
        == []
    )


def test_a_row_that_is_not_a_cost_line_never_satisfies_a_cost_line_check():
    verified = {
        "items": [
            {
                "section_key": "s1",
                "article_name": "Nha may A",
                "item_type": "material",
            }
        ]
    }

    assert costing_apply._cost_line_verification_mismatches(
        verified, [{"section_key": "s1", "article_name": "Nha may A"}]
    )


def test_a_split_that_did_not_create_enough_rows_is_reported():
    verified = {"items": [{"section_key": "s1", "article_code": "F-001"}]}

    assert costing_apply._split_verification_mismatches(
        verified, [{"section_key": "s1", "article_code": "F-001"}]
    ) == [{"field_key": "Splitter:F-001", "expected": 2, "actual": 1}]


def test_a_split_that_created_the_rows_is_silent():
    verified = {
        "items": [
            {"section_key": "s1", "article_code": "F-001"},
            {"section_key": "s1", "article_code": "F-001"},
        ]
    }

    assert (
        costing_apply._split_verification_mismatches(
            verified, [{"section_key": "s1", "article_code": "F-001"}]
        )
        == []
    )


def test_a_split_can_ask_for_more_than_two_rows():
    verified = {
        "items": [
            {"section_key": "s1", "article_code": "F-001"},
            {"section_key": "s1", "article_code": "F-001"},
        ]
    }

    assert costing_apply._split_verification_mismatches(
        verified, [{"section_key": "s1", "article_code": "F-001", "occurrence": 3}]
    ) == [{"field_key": "Splitter:F-001", "expected": 3, "actual": 2}]


def test_verification_rereads_the_costing_from_wfx(monkeypatch):
    reads: list[str] = []
    monkeypatch.setattr(costing_apply, "_wait", lambda *a: None)
    monkeypatch.setattr(
        costing_apply,
        "_costing_frame",
        lambda *a, **kw: reads.append("frame") or (object(), object()),
    )
    monkeypatch.setattr(
        costing_apply, "_selected_costing_title", lambda *a, **kw: "Costing"
    )
    monkeypatch.setattr(
        costing_apply,
        "_inventory_costing_frame",
        lambda *a, **kw: reads.append("inventory") or {"items": [], "fields": []},
    )
    monkeypatch.setattr(costing_apply, "_live_field_index", lambda _v: {})

    assert (
        costing_apply._verify_costing_apply(
            _Session(), costing_apply._CostingApplyProgress()
        )
        == []
    )
    assert reads == ["frame", "inventory"]


def test_a_verification_mismatch_never_reports_a_successful_save(monkeypatch):
    monkeypatch.setattr(costing_apply, "_save_costing", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_prepare_costing_articles", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_apply_costing_splits", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_apply_costing_fields", lambda *a: None)
    monkeypatch.setattr(
        costing_apply,
        "_verify_costing_apply",
        lambda *a: [{"field_key": "colUsage", "expected": "5", "actual": "9"}],
    )
    session = _Session(working_plan=_plan(fields_to_set=[_change()]))

    result = costing_apply._run_costing_apply(session, None)

    assert result["ok"] is False
    assert result["code"] == "COSTING_VERIFY_FAILED"
    assert result["mismatches"]


def test_a_clean_apply_reports_every_count(monkeypatch):
    monkeypatch.setattr(costing_apply, "_save_costing", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_apply_costing_splits", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_apply_costing_fields", lambda *a: None)
    monkeypatch.setattr(costing_apply, "_verify_costing_apply", lambda *a: [])

    def prepare(_session, progress, _resolutions):
        progress.preflight = {"missing": [{"article_code": "F-999"}]}
        progress.added = [{"resolved_code": "F-001"}]
        progress.applied = [_change()]

    monkeypatch.setattr(costing_apply, "_prepare_costing_articles", prepare)
    session = _Session(working_plan=_plan(fields_to_set=[_change()]))

    result = costing_apply._run_costing_apply(session, None)

    assert result["code"] == "COSTING_APPLIED"
    assert result["applied_count"] == 1
    assert result["added_count"] == 1
    assert result["missing_articles"] == [{"article_code": "F-999"}]
    assert result["verified"] is True


def test_refreshing_the_inventory_rebuilds_the_plan_from_the_source(monkeypatch):
    monkeypatch.setattr(costing_apply, "_wait", lambda *a: None)
    monkeypatch.setattr(
        costing_apply, "_selected_costing_title", lambda *a, **kw: "Costing"
    )
    monkeypatch.setattr(
        costing_apply,
        "_inventory_costing_frame",
        lambda *a, **kw: {"fields": [], "items": []},
    )
    rebuilt: list[int] = []
    monkeypatch.setattr(
        costing_apply,
        "build_costing_plan",
        lambda _source, _live: rebuilt.append(1) or _plan(),
    )
    session = _Session(source_document={"fields": []})

    costing_apply._refresh_apply_inventory(session, wait_ms=100)

    assert rebuilt == [1]


def test_refreshing_can_keep_the_plan_untouched(monkeypatch):
    monkeypatch.setattr(costing_apply, "_wait", lambda *a: None)
    monkeypatch.setattr(
        costing_apply, "_selected_costing_title", lambda *a, **kw: "Costing"
    )
    monkeypatch.setattr(
        costing_apply,
        "_inventory_costing_frame",
        lambda *a, **kw: {"fields": [], "items": []},
    )
    rebuilt: list[int] = []
    monkeypatch.setattr(
        costing_apply,
        "build_costing_plan",
        lambda *_a: rebuilt.append(1) or _plan(),
    )
    session = _Session(source_document={"fields": []})

    costing_apply._refresh_apply_inventory(session, rebuild_plan=False)

    assert rebuilt == []
