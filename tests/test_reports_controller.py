"""Controller Reports: nhớ tham số theo tài khoản và lọc mọi payload từ UI.

Tham số báo cáo đến từ JavaScript nên controller phải coi chúng là dữ liệu
không tin được: sai kiểu thì trả mã lỗi, giá trị lạ thì cắt bớt, và chỉ lưu cho
đúng tài khoản đang đăng nhập.
"""

from __future__ import annotations

import pytest

from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI

COLOR = "color_combination_production"


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls: list[tuple] = []

    def check_session(self, log=print):
        return {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"}

    def report_catalog(self):
        return [
            {"id": "shipment_summary", "name": "Shipment Summary"},
            {"id": COLOR, "name": "Color Combination - Production"},
            "khong phai mapping",
        ]

    def load_report_parameters(self, report_id, log=print):
        self.calls.append(("load", report_id))
        return {
            "ok": True,
            "code": "REPORT_PARAMETERS_READY",
            "message": "ok",
            "parameters": [],
        }

    def export_report_excel(self, report_id, values, log=print):
        self.calls.append(("export", report_id, dict(values)))
        return {"ok": True, "code": "REPORT_EXPORTED", "message": "ok"}

    def load_color_report_options(self, values, log=print):
        self.calls.append(("color_options", dict(values)))
        return {"ok": True, "code": "COLOR_REPORT_OPTIONS_READY", "message": "ok"}

    def run_color_report_batch(
        self, selection, style_refs, output_dir, log=print, progress=None
    ):
        self.calls.append(
            ("color_batch", dict(selection), list(style_refs), output_dir)
        )
        return {"ok": True, "code": "COLOR_REPORT_BATCH_DONE", "message": "ok"}


@pytest.fixture
def api(tmp_path):
    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )
    prefs.save_account("tester", "", base_dir=tmp_path)
    return api


class BareLogin(FakeLogin):
    """Bản automation cũ chưa có Reports."""

    def __init__(self):
        super().__init__()
        for name in (
            "report_catalog",
            "load_report_parameters",
            "export_report_excel",
            "load_color_report_options",
            "run_color_report_batch",
        ):
            setattr(self, name, None)


@pytest.fixture
def bare_api(tmp_path):
    return PanelAPI(
        login_module=BareLogin(), prefs_module=prefs, base_dir=tmp_path
    )


# --- danh mục báo cáo ---------------------------------------------------


def test_the_catalog_is_taken_from_the_automation_layer(api):
    result = api.report_catalog()

    assert result["code"] == "REPORT_CATALOG_READY"
    assert {item["id"] for item in result["reports"] if isinstance(item, dict)} == {
        "shipment_summary",
        COLOR,
    }


def test_an_automation_build_without_reports_returns_an_empty_catalog(bare_api):
    assert bare_api.report_catalog()["reports"] == []


# --- tham số đã lưu -----------------------------------------------------


def test_loading_parameters_adds_whatever_was_saved_for_this_account(api):
    api.save_report_parameters(COLOR, {"division": "d1", "buyer": "b1"})

    result = api.load_report_parameters(COLOR)

    assert result["saved_parameters"]["division"] == "d1"
    assert api._login.calls[0] == ("load", COLOR)


def test_a_failed_load_is_handed_back_without_the_saved_parameters(api):
    api._login.load_report_parameters = lambda report_id, log=print: {
        "ok": False,
        "code": "REPORT_NOT_FOUND",
        "message": "Không thấy report.",
    }

    result = api.load_report_parameters(COLOR)

    assert result["code"] == "REPORT_NOT_FOUND"
    assert "saved_parameters" not in result


def test_an_automation_build_without_reports_says_so_when_loading(bare_api):
    result = bare_api.load_report_parameters(COLOR)

    assert result["code"] == "REPORT_UNAVAILABLE"


def test_parameters_are_only_saved_for_a_report_the_catalog_knows(api):
    result = api.save_report_parameters("khong-ton-tai", {"a": "b"})

    assert result["code"] == "REPORT_UNKNOWN"


def test_an_empty_report_id_is_refused(api):
    assert api.save_report_parameters("  ", {})["code"] == "REPORT_UNKNOWN"


def test_parameters_cannot_be_saved_before_the_user_logs_in(tmp_path):
    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )

    result = api.save_report_parameters(COLOR, {"division": "d1"})

    assert result["code"] == "REPORT_SAVE_ACCOUNT_REQUIRED"


def test_a_payload_that_is_not_an_object_is_refused(api):
    result = api.save_report_parameters(COLOR, ["khong", "phai", "object"])

    assert result["code"] == "REPORT_PARAMETERS_INVALID"


def test_saving_returns_the_cleaned_values_the_store_kept(api):
    result = api.save_report_parameters(COLOR, {"division": "d1"})

    assert result["code"] == "REPORT_PARAMETERS_SAVED"
    assert result["report_id"] == COLOR
    assert result["saved_parameters"]["division"] == "d1"


def test_a_store_that_cannot_be_written_is_reported_not_raised(api, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise PermissionError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(api._reports._parameter_store, "save", refuse)

    result = api.save_report_parameters(COLOR, {"division": "d1"})

    assert result["code"] == "REPORT_SAVE_FAILED"
    assert "PermissionError" in result["message"]


def test_parameters_are_kept_apart_per_account(api, tmp_path):
    api.save_report_parameters(COLOR, {"division": "cua-tester"})
    prefs.save_account("nguoi-khac", "", base_dir=tmp_path)

    assert api._reports._saved_report_parameters(COLOR) == {}


# --- xuất Excel ---------------------------------------------------------


def test_an_automation_build_without_export_says_so(bare_api):
    assert bare_api.export_report_excel(COLOR, {})["code"] == "REPORT_UNAVAILABLE"


def test_an_export_payload_that_is_not_an_object_is_refused(api):
    result = api.export_report_excel(COLOR, "khong phai object")

    assert result["code"] == "REPORT_PARAMETERS_INVALID"
    assert api._login.calls == []


def test_exporting_passes_a_copy_of_the_values_through(api):
    values = {"division": "d1"}

    result = api.export_report_excel(COLOR, values)

    assert result["code"] == "REPORT_EXPORTED"
    assert api._login.calls == [("export", COLOR, {"division": "d1"})]
    values["division"] = "doi-sau"
    assert api._login.calls[0][2] == {"division": "d1"}


def test_exporting_without_any_value_still_works(api):
    assert api.export_report_excel(COLOR)["code"] == "REPORT_EXPORTED"


# --- tham số Color Combination -----------------------------------------


def test_an_automation_build_without_the_colour_report_says_so(bare_api):
    result = bare_api.load_color_report_options({})

    assert result["code"] == "REPORT_UNAVAILABLE"


def test_a_colour_payload_that_is_not_an_object_is_refused(api):
    result = api.load_color_report_options(["a"])

    assert result["code"] == "REPORT_PARAMETERS_INVALID"


def test_colour_values_are_coerced_to_short_strings(api):
    api.load_color_report_options(
        {
            "division": "d1",
            "season": 2026,
            "buyer": "x" * 600,
            "bo_qua": {"khong": "phai chuoi"},
        }
    )

    sent = api._login.calls[0][1]
    assert sent["season"] == "2026"
    assert len(sent["buyer"]) == 500
    assert "bo_qua" not in sent


def test_an_empty_colour_payload_falls_back_to_the_saved_cascade(api):
    api.save_report_parameters(
        COLOR, {"division": "d1", "buyer": "b1", "season": "", "khac": "x"}
    )

    api.load_color_report_options({})

    assert api._login.calls[-1][1] == {"division": "d1", "buyer": "b1"}


def test_an_empty_payload_with_nothing_saved_sends_nothing(api):
    api.load_color_report_options(None)

    assert api._login.calls[-1][1] == {}


# --- chạy hàng loạt -----------------------------------------------------


def test_an_automation_build_without_the_batch_says_so(bare_api):
    result = bare_api.run_color_report_batch({}, [], "")

    assert result["code"] == "REPORT_UNAVAILABLE"


def test_a_batch_selection_that_is_not_an_object_is_refused(api):
    result = api.run_color_report_batch("khong phai object", [], "")

    assert result["code"] == "REPORT_PARAMETERS_INVALID"
    assert api._login.calls == []


def test_a_style_list_that_is_not_a_list_is_refused(api):
    result = api.run_color_report_batch({}, "r1", "")

    assert result["code"] == "REPORT_STYLE_REFS_INVALID"
    assert api._login.calls == []


def test_a_batch_saves_the_selection_before_it_runs(api, tmp_path):
    api.run_color_report_batch(
        {"division": "d1", "buyer": "b1"}, ["r1"], str(tmp_path)
    )

    assert api._reports._saved_report_parameters(COLOR)["division"] == "d1"


def test_a_batch_trims_the_style_list_and_drops_blank_entries(api, tmp_path):
    api.run_color_report_batch(
        {}, ["r1", "   ", "", "r2"] + [f"r{index}" for index in range(600)],
        str(tmp_path),
    )

    _label, _selection, refs, output_dir = api._login.calls[-1]
    assert refs[:2] == ["r1", "r2"]
    assert "" not in refs
    assert len(refs) <= 500
    assert output_dir == str(tmp_path)


def test_a_batch_is_recorded_in_the_job_history_under_its_own_method(
    api, tmp_path
):
    result = api.run_color_report_batch({}, ["r1", "r2"], str(tmp_path))

    assert result["code"] == "COLOR_REPORT_BATCH_DONE"
    methods = [job["method"] for job in api.get_job_history()["jobs"]]
    assert "run_color_report_batch" in methods
