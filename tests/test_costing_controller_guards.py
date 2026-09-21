"""Controller Costing: những gì nó từ chối làm trước khi chạm WFX.

CLAUDE.md: Costing file chỉ áp dụng cho Apparel; hộp thoại chỉ hỗ trợ `.xlsx`;
Export được phép ở mọi status còn Import/Apply chỉ khi Costing đang `Open`; và
bản automation cũ không có hàm tương ứng thì phải trả mã riêng chứ không nổ.
"""

from __future__ import annotations

import pytest

from tests.test_panel_api import FakeLogin, make_api
from wfx_panel.workbooks.costing import CostingWorkbookError


@pytest.fixture
def api(tmp_path):
    instance, _fake = make_api(tmp_path)
    return instance


@pytest.fixture
def costing(api):
    return api._catalog.costing


def _target(tmp_path, name="SWN0000001-Costing.xlsx"):
    return str(tmp_path / name)


# --- chỉ Apparel --------------------------------------------------------


def test_exporting_costing_for_another_category_is_refused(api, tmp_path):
    result = api.export_catalog_costing(
        "Trims", "code", "T0001", _target(tmp_path)
    )

    assert result["code"] == "APPAREL_ONLY"


def test_importing_costing_for_another_category_is_refused(api, tmp_path):
    result = api.prepare_catalog_costing_import(
        "Trims", "code", "T0001", _target(tmp_path)
    )

    assert result["code"] == "APPAREL_ONLY"


def test_inspecting_the_costing_card_for_another_category_is_refused(api):
    assert api.inspect_active_catalog_costing("Trims")["code"] == "APPAREL_ONLY"


def test_opening_a_style_for_a_file_action_outside_apparel_is_refused(costing):
    result = costing._open_for_file_action("Trims", "code", "T0001")

    assert result["code"] == "APPAREL_ONLY"


# --- chỉ .xlsx ----------------------------------------------------------


@pytest.mark.parametrize("name", ["costing.xls", "costing.csv", "costing"])
def test_a_file_that_is_not_an_xlsx_is_refused_before_wfx_is_touched(
    api, tmp_path, name
):
    result = api.export_catalog_costing(
        "Apparel", "code", "SWN0000001", _target(tmp_path, name)
    )

    assert result["code"] == "COSTING_FILE_TYPE_UNSUPPORTED"


def test_an_import_file_that_is_not_an_xlsx_is_refused_too(api, tmp_path):
    result = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", _target(tmp_path, "plan.csv")
    )

    assert result["code"] == "COSTING_FILE_TYPE_UNSUPPORTED"


def test_a_standalone_file_check_reports_its_own_error_code(api, tmp_path):
    result = api.validate_catalog_costing_file(_target(tmp_path, "plan.csv"))

    assert result["ok"] is False
    assert result["code"] == "COSTING_FILE_TYPE_UNSUPPORTED"


# --- style không mở được ------------------------------------------------


def _refuse_to_open(monkeypatch, costing, code="NO_RESULTS"):
    monkeypatch.setattr(
        costing,
        "_open_for_file_action",
        lambda *_args: {"ok": False, "code": code, "message": "Không tìm thấy."},
    )


def test_a_style_that_cannot_be_opened_stops_the_export(
    api, costing, monkeypatch, tmp_path
):
    _refuse_to_open(monkeypatch, costing)

    result = api.export_catalog_costing(
        "Apparel", "code", "SWN0000001", _target(tmp_path)
    )

    assert result["code"] == "NO_RESULTS"


def test_a_style_that_cannot_be_opened_stops_the_import(
    api, costing, monkeypatch, tmp_path
):
    exported = _target(tmp_path)
    assert api.export_catalog_costing(
        "Apparel", "code", "SWN0000001", exported
    )["ok"]
    _refuse_to_open(monkeypatch, costing)

    result = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", exported
    )

    assert result["code"] == "NO_RESULTS"


# --- bản automation cũ --------------------------------------------------


class _OldAutomation(FakeLogin):
    """Bản automation chưa có các hàm Costing mới."""

    def __init__(self, *missing):
        super().__init__()
        for name in missing:
            setattr(self, name, None)


@pytest.mark.parametrize(
    ("missing", "call", "expected"),
    [
        (
            ("scan_open_costing",),
            lambda api, path: api.export_catalog_costing(
                "Apparel", "code", "SWN0000001", path
            ),
            "COSTING_EXPORT_UNSUPPORTED",
        ),
        (
            ("scan_active_open_costing",),
            lambda api, path: api.export_catalog_costing(
                "Apparel", "code", "", path
            ),
            "COSTING_EXPORT_UNSUPPORTED",
        ),
        (
            ("inspect_active_costing",),
            lambda api, _path: api.inspect_active_catalog_costing("Apparel"),
            "COSTING_EXPORT_UNSUPPORTED",
        ),
        (
            ("clear_active_costing_dependencies",),
            lambda api, _path: api.clear_catalog_costing_dependencies(),
            "COSTING_CLEAR_UNSUPPORTED",
        ),
    ],
)
def test_an_automation_build_without_the_feature_says_so_plainly(
    tmp_path, missing, call, expected
):
    from wfx_panel import prefs
    from wfx_panel.panel_api import PanelAPI

    api = PanelAPI(
        login_module=_OldAutomation(*missing),
        prefs_module=prefs,
        base_dir=tmp_path,
    )

    assert call(api, _target(tmp_path))["code"] == expected


# --- WFX từ chối đọc/ghi ------------------------------------------------


def test_a_scan_that_failed_is_passed_straight_back_to_the_user(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)

    def refuse(*_args, **_kwargs):
        return {
            "ok": False,
            "code": "COSTING_NOT_OPEN",
            "message": "Costing chưa ở trạng thái Open.",
        }

    monkeypatch.setattr(fake, "scan_open_costing", refuse, raising=False)

    result = api.export_catalog_costing(
        "Apparel", "code", "SWN0000001", _target(tmp_path)
    )

    assert result["code"] == "COSTING_NOT_OPEN"


def test_a_workbook_that_cannot_be_written_is_a_file_error_not_a_crash(
    api, monkeypatch, tmp_path
):
    import wfx_panel.controllers.costing as controller

    def refuse(_document, _target):
        raise CostingWorkbookError(
            "COSTING_VALIDATION_FAILED", "Không ghi được workbook."
        )

    monkeypatch.setattr(controller, "write_costing_file", refuse)

    result = api.export_catalog_costing(
        "Apparel", "code", "SWN0000001", _target(tmp_path)
    )

    assert result["code"] == "COSTING_VALIDATION_FAILED"
    assert result["ok"] is False


def test_scanning_article_dropdowns_is_opt_in_for_a_named_style(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)
    api._account = lambda: {"user_id": "alice"}
    seen: list[dict] = []
    real_scan = fake.scan_open_costing

    def record(article_code, **kwargs):
        seen.append(dict(kwargs))
        return real_scan(article_code, **kwargs)

    monkeypatch.setattr(fake, "scan_open_costing", record, raising=False)

    api.export_catalog_costing(
        "Apparel", "code", "SWN0000001", _target(tmp_path), True
    )

    assert seen[0]["scan_article_options"] is True


# --- Import và Apply ----------------------------------------------------


def _exported(api, tmp_path, name="SWN0000001-Costing.xlsx"):
    target = _target(tmp_path, name)
    assert api.export_catalog_costing("Apparel", "code", "SWN0000001", target)["ok"]
    return target


def test_an_automation_build_that_cannot_read_costing_stops_the_import(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)
    source = _exported(api, tmp_path)
    monkeypatch.setattr(fake, "scan_open_costing", None, raising=False)

    result = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", source
    )

    assert result["code"] == "COSTING_IMPORT_UNSUPPORTED"


def test_a_costing_that_is_not_open_stops_the_import(tmp_path, monkeypatch):
    api, fake = make_api(tmp_path)
    source = _exported(api, tmp_path)

    def refuse(*_args, **_kwargs):
        return {
            "ok": False,
            "code": "COSTING_NOT_OPEN",
            "message": "Costing chưa ở trạng thái Open.",
        }

    monkeypatch.setattr(fake, "scan_open_costing", refuse, raising=False)

    result = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", source
    )

    assert result["code"] == "COSTING_NOT_OPEN"


def test_a_file_for_another_style_is_never_applied_to_the_open_one(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)
    source = _exported(api, tmp_path)
    real_scan = fake.scan_open_costing

    def other_style(article_code, **kwargs):
        scanned = real_scan(article_code, **kwargs)
        scanned = {**scanned, "article_code": "SWN0009999"}
        scanned["costing"] = {**scanned["costing"], "style_code": "SWN0009999"}
        return scanned

    monkeypatch.setattr(fake, "scan_open_costing", other_style, raising=False)

    result = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", source
    )

    assert result["code"] == "COSTING_STYLE_MISMATCH"
    assert result["file_style"] == "SWN0000001"
    assert result["live_style"] == "SWN0009999"


def test_a_plan_the_engine_refuses_to_build_is_a_file_error(
    tmp_path, monkeypatch
):
    import wfx_panel.controllers.costing as controller

    api, _fake = make_api(tmp_path)
    source = _exported(api, tmp_path)

    def refuse(_imported, _live):
        raise controller.CostingPlanError(
            "COSTING_PLAN_INVALID", "Không dựng được kế hoạch."
        )

    monkeypatch.setattr(controller, "build_costing_plan", refuse)

    result = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", source
    )

    assert result["code"] == "COSTING_PLAN_INVALID"


def _prepared(api, tmp_path):
    source = _exported(api, tmp_path)
    prepared = api.prepare_catalog_costing_import(
        "Apparel", "code", "SWN0000001", source
    )
    assert prepared["ok"], prepared
    return prepared["plan_token"]


def test_a_style_that_closed_between_dry_run_and_apply_stops_the_write(
    tmp_path, monkeypatch
):
    api, _fake = make_api(tmp_path)
    token = _prepared(api, tmp_path)
    _refuse_to_open(monkeypatch, api._catalog.costing, "CATALOG_RESULT_EXPIRED")

    result = api.apply_catalog_costing(token)

    assert result["code"] == "CATALOG_RESULT_EXPIRED"


def test_a_different_style_reopening_before_apply_stops_the_write(
    tmp_path, monkeypatch
):
    api, _fake = make_api(tmp_path)
    token = _prepared(api, tmp_path)
    monkeypatch.setattr(
        api._catalog.costing,
        "_open_for_file_action",
        lambda *_args: {"ok": True, "article_code": "SWN0009999"},
    )

    result = api.apply_catalog_costing(token)

    assert result["code"] == "COSTING_STYLE_MISMATCH"
    assert result["live_style"] == "SWN0009999"


def test_an_automation_build_that_cannot_write_costing_says_so(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)
    token = _prepared(api, tmp_path)
    monkeypatch.setattr(fake, "apply_costing_plan", None, raising=False)

    result = api.apply_catalog_costing(token)

    assert result["code"] == "COSTING_IMPORT_UNSUPPORTED"


def test_an_ambiguous_article_keeps_the_plan_so_the_user_can_choose(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)
    token = _prepared(api, tmp_path)

    def ambiguous(*_args, **_kwargs):
        return {
            "ok": False,
            "code": "COSTING_ARTICLE_AMBIGUOUS",
            "message": "Nhiều Article khớp; hãy chọn đúng mã.",
            "candidates": [{"key": "f1", "options": ["F0001", "F0002"]}],
        }

    monkeypatch.setattr(fake, "apply_costing_plan", ambiguous, raising=False)

    result = api.apply_catalog_costing(token)

    assert result["code"] == "COSTING_ARTICLE_AMBIGUOUS"
    # Plan phải còn sống để lượt chọn Article của người dùng dùng lại được.
    assert result["plan_token"] == token
    assert token in api._catalog.costing.plans
