"""Bridge PO Wise: tham số độc lập, lọc retry và tiến độ đúng method."""

import pytest

from tests.test_reports_controller import FakeLogin
from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI

PO = "color_combination_po_wise"


class PoLogin(FakeLogin):
    def report_catalog(self):
        return super().report_catalog() + [
            {"id": PO, "name": "ColorCombination PO Wise"}
        ]

    def load_color_po_report_options(self, values, log=print):
        self.calls.append(("po_options", dict(values)))
        return {"ok": True, "code": "COLOR_REPORT_OPTIONS_READY", "report_id": PO}

    def run_color_po_report_batch(
        self, selection, pos, directory, log=print, progress=None
    ):
        self.calls.append(("po_batch", dict(selection), list(pos), directory))
        if progress:
            progress("po", "PO… 1/1", 1, 1)
        return {"ok": True, "code": "COLOR_REPORT_BATCH_DONE", "report_id": PO}


@pytest.fixture
def api(tmp_path):
    prefs.save_account("tester", "", base_dir=tmp_path)
    return PanelAPI(login_module=PoLogin(), prefs_module=prefs, base_dir=tmp_path)


def test_po_parameters_are_remembered_separately_from_style_wise(api, tmp_path):
    api.save_report_parameters("color_combination_production", {"division": "old"})
    api.save_report_parameters(PO, {"division": "new", "buyer": "b", "season": "s"})
    api.run_color_po_report_batch(
        {"division": "other", "buyer": "other", "season": "other"},
        ["p1"],
        str(tmp_path),
    )
    api.load_color_po_report_options({})
    assert api._login.calls[-1] == (
        "po_options",
        {"division": "new", "buyer": "b", "season": "s"},
    )
    assert api._reports._saved_report_parameters("color_combination_production") == {
        "division": "old"
    }


def test_po_retry_and_progress_reach_correct_runner_without_persisting_retry(
    api, tmp_path
):
    seen = []
    api.set_progress_sink(seen.append)
    retry = {"po_value": "p1", "style_ref_value": "r1", "style_code_value": "c2"}
    api.run_color_po_report_batch(
        {"division": "1", "retry_items": [retry]}, ["p1"], str(tmp_path)
    )
    assert api._login.calls[-1][1]["retry_items"] == [retry]
    assert "retry_items" not in api._reports._saved_report_parameters(PO)
    assert seen[-1]["method"] == "run_color_po_report_batch"


def test_explicit_clear_does_not_restore_previous_po_cascade(api):
    api.save_report_parameters(PO, {"division": "1", "buyer": "b1", "season": "s1"})
    api.load_color_po_report_options({"division": "", "buyer": "", "season": ""})
    assert api._login.calls[-1] == ("po_options", {})


def test_po_run_without_manual_save_does_not_create_defaults(api, tmp_path):
    api.run_color_po_report_batch(
        {"division": "1", "buyer": "b1", "season": "s1"}, ["p1"], str(tmp_path)
    )
    api.load_color_po_report_options({})
    assert api._login.calls[-1] == ("po_options", {})
    assert api._reports._saved_report_parameters(PO) == {}


def test_po_ignores_legacy_auto_saved_parameters(api):
    api._reports._parameter_store.save(
        "tester", PO, {"division": "1", "buyer": "auto", "season": "auto"}
    )
    result = api.load_color_po_report_options({})
    assert api._login.calls[-1] == ("po_options", {})
    assert result["saved_parameters"] == {}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"retry_items": "bad"},
        {"retry_items": [{"po_value": "other"}]},
        {"retry_items": [{"po_value": "p1", "style_code_value": "c1"}]},
    ],
)
def test_bad_po_selection_is_refused_before_automation(api, tmp_path, payload):
    result = api.run_color_po_report_batch(payload, ["p1"], str(tmp_path))
    assert result["code"] == "REPORT_PARAMETERS_INVALID"
    assert api._login.calls == []
