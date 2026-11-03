"""PO Wise: đủ mọi ref/code, chọn hết OC, bỏ qua thiếu dữ liệu và giữ file."""

from pathlib import Path

import pytest

from wfx_panel.automation import color_combination as color
from wfx_panel.automation import color_combination_po as po
from wfx_panel.automation.reports import REPORTS
from wfx_panel.automation.runtime import AutomationCancelled


@pytest.fixture
def world(monkeypatch, tmp_path):
    class World:
        plan = {
            "PO/A": {"STYLE-A": {"CODE1": ["OC1", "OC2"], "CODE2": []}, "EMPTY": {}},
            "PO-B": {"STYLE-B": {"CODE9": ["OC9"]}},
        }
        selected_po = ""
        ref = ""
        code = ""
        selected_codes = []
        selected_ocs = []

        def select_po(self, _page, label):
            self.selected_po, self.ref, self.code = label, "", ""

        def select_native(self, _page, label, value):
            if label == "BuyerStyleReference":
                self.ref, self.code = value, ""
            else:
                self.code = value
                self.selected_codes.append((self.selected_po, self.ref, value))

        def options(self, _page, label):
            if label == "BuyerStyleReference":
                values = self.plan[self.selected_po]
            else:
                values = self.plan[self.selected_po][self.ref]
            return [{"value": "0", "label": "<Select a Value>"}] + [
                {"value": value, "label": value} for value in values
            ]

        def ocs(self, _page):
            return {
                "options": [
                    {"value": value, "label": value}
                    for value in self.plan[self.selected_po][self.ref][self.code]
                ]
            }

    state = World()
    monkeypatch.setattr(po, "_select_po", state.select_po)
    monkeypatch.setattr(po, "_select_native", state.select_native)
    monkeypatch.setattr(
        po,
        "resolve_controls",
        lambda _p: {
            "BuyerStyleReference": "BuyerStyleReference",
            "StyleCode": "StyleCode",
        },
    )
    monkeypatch.setattr(po, "read_select_options", state.options)
    monkeypatch.setattr(po, "read_po_ocs", state.ocs)
    monkeypatch.setattr(
        po, "_select_ocnums", lambda _p, labels: state.selected_ocs.append(labels)
    )
    source = tmp_path / "native.xlsx"
    source.write_bytes(b"Excel from WFX")
    monkeypatch.setattr(color, "_view_and_download", lambda *_a: source)
    return state


def run_batch(tmp_path, **kwargs):
    return po.batch_po_reports(
        object(),
        [{"value": "p1", "label": "PO/A"}, {"value": "p2", "label": "PO-B"}],
        tmp_path,
        lambda _line: None,
        **kwargs,
    )


def test_po_batch_visits_every_code_and_saves_files_under_each_po(world, tmp_path):
    result = run_batch(tmp_path)
    assert world.selected_codes == [
        ("PO/A", "STYLE-A", "CODE1"),
        ("PO/A", "STYLE-A", "CODE2"),
        ("PO-B", "STYLE-B", "CODE9"),
    ]
    assert world.selected_ocs == [
        None,
        None,
    ]  # Mỗi file gồm hết OC, không xuất từng OC.
    paths = [
        Path(item["file_path"]).relative_to(tmp_path).as_posix()
        for item in result["saved"]
    ]
    assert paths == [
        "PO_A/PO_A - STYLE-A - CODE1.xlsx",
        "PO-B/PO-B - STYLE-B - CODE9.xlsx",
    ]
    assert [item["message"] for item in result["skipped"]] == [
        "Không tìm thấy OC",
        "Không tìm thấy StyleCode",
    ]
    assert result["failed"] == []
    assert all(
        Path(item["file_path"]).read_bytes() == b"Excel from WFX"
        for item in result["saved"]
    )


def test_retry_visits_only_failed_po_ref_code(world, tmp_path):
    world.plan["PO/A"]["STYLE-A"]["CODE2"] = ["OC2"]
    result = run_batch(
        tmp_path,
        retry_items=[
            {
                "po_value": "p1",
                "style_ref_value": "STYLE-A",
                "style_code_value": "CODE2",
            }
        ],
    )
    assert world.selected_codes == [("PO/A", "STYLE-A", "CODE2")]
    assert len(result["saved"]) == 1
    assert result["skipped"] == []


def test_stop_inside_po_keeps_files_downloaded_before_stop(
    world, monkeypatch, tmp_path
):
    original = world.select_native

    def select(_page, label, value):
        if value == "CODE2":
            raise AutomationCancelled()
        original(_page, label, value)

    monkeypatch.setattr(po, "_select_native", select)
    result = run_batch(tmp_path)
    assert result["cancelled"] is True
    assert len(result["saved"]) == 1
    assert Path(result["saved"][0]["file_path"]).exists()


def test_failed_export_does_not_stop_remaining_po(world, monkeypatch, tmp_path):
    def download(*_args):
        if world.selected_po == "PO/A":
            raise color.StyleFailure("COLOR_REPORT_SAVE_FAILED", "File locked")
        return {"file_path": str(tmp_path / "saved.xlsx"), "file_name": "saved.xlsx"}

    monkeypatch.setattr(po, "_download_style_report", download)
    result = run_batch(tmp_path)
    assert result["failed"][0]["po_value"] == "p1"
    assert result["failed"][0]["style_code_value"] == "CODE1"
    assert result["saved"][0]["po_no"] == "PO-B"


def test_repeated_run_preserves_existing_files(world, tmp_path):
    first = run_batch(tmp_path)
    second = run_batch(tmp_path)
    assert first["saved"][0]["file_name"].endswith("CODE1.xlsx")
    assert second["saved"][0]["file_name"].endswith("CODE1 (2).xlsx")


@pytest.mark.parametrize(
    "name,expected", [("../PO/A", ".._PO_A"), ("CON", "_CON"), ("PO:1", "PO_1")]
)
def test_po_folder_name_cannot_escape_output_folder(name, expected):
    assert po.po_folder_name(name) == expected
    assert Path(expected).name == expected


def test_catalog_separates_style_wise_and_po_wise():
    assert (
        REPORTS[po.REPORT_ID]["custom_report_id"]
        == "bb9548d2-1fd3-41a6-9f66-e6a424dd9415"
    )
    assert REPORTS[po.REPORT_ID]["name"] == "ColorCombination PO Wise"
    assert REPORTS[color.REPORT_ID]["name"] == "ColorCombination Style Wise"
    assert (
        REPORTS[po.REPORT_ID]["custom_report_id"]
        != REPORTS[color.REPORT_ID]["custom_report_id"]
    )


def test_empty_batch_is_normal_and_stale_po_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(po, "_with_report", lambda action, *_a, **_k: action(object()))
    monkeypatch.setattr(
        po,
        "read_po_cascade",
        lambda *_a: {
            "levels": {
                **{key: {"value": "1"} for key in po.CASCADE_KEYS},
                "po_no": {"options": [{"value": "p1", "label": "PO1"}]},
            }
        },
    )
    seen = []
    monkeypatch.setattr(
        po,
        "batch_po_reports",
        lambda *_a: (
            seen.append(True)
            or {
                "saved": [],
                "failed": [],
                "skipped": [{"message": "Không tìm thấy StyleCode"}],
                "cancelled": False,
            }
        ),
    )
    result = po.run_color_po_report_batch({}, ["p1"], str(tmp_path))
    assert result["ok"] is True
    assert result["code"] == "COLOR_PO_REPORT_EMPTY"
    assert result["failed"] == []
    result = po.run_color_po_report_batch({}, ["stale"], str(tmp_path))
    assert result["code"] == "REPORT_PARAMETERS_INVALID"
    assert len(seen) == 1
