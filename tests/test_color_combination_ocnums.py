"""Xuất từng OC: chọn exact, giữ kết quả khi lỗi/Stop, chạy lại đúng OC."""

from copy import deepcopy

import pytest

from wfx_panel.automation import color_combination as color
from wfx_panel.automation.runtime import AutomationCancelled


def _oc_popup(monkeypatch):
    state = {
        "key": "oc_txtValue",
        "label": "OCNum",
        "type": "multiselect",
        "options": [
            {"value": "old1", "label": "OC/001"},
            {"value": "old2", "label": "OC002"},
        ],
        "value": ["old1", "old2"],
    }
    monkeypatch.setattr(color, "_read_oc_parameter", lambda *_a: deepcopy(state))
    calls = []

    def apply(_page, parameter, values):
        calls.append({parameter["key"]: deepcopy(values)})
        wanted = set(values)
        # ReportViewer thay ID sau khi OCNum postback; phải verify bằng label.
        for option in state["options"]:
            old = option["value"]
            option["value"] = "new_" + old
        state["value"] = [
            option["value"]
            for option in state["options"]
            if option["value"].removeprefix("new_") in wanted
        ]

    monkeypatch.setattr(color, "_set_oc_parameter", apply)
    return state, calls


def test_oc_selection_unchecks_other_ocs_and_resolves_fresh_ids(monkeypatch):
    state, calls = _oc_popup(monkeypatch)
    color._select_ocnums(object(), ["OC002"])
    assert calls == [{"oc_txtValue": ["old2"]}]
    assert state["value"] == ["new_old2"]


def test_style_mode_restores_all_ocs_after_a_single_oc_export(monkeypatch):
    state, calls = _oc_popup(monkeypatch)
    state["value"] = ["old2"]
    color._select_ocnums(object(), None)
    assert calls == [{"oc_txtValue": ["old1", "old2"]}]
    assert len(state["value"]) == 2


def test_oc_selection_never_exports_if_wfx_did_not_accept_it(monkeypatch):
    _oc_popup(monkeypatch)
    monkeypatch.setattr(color, "_set_oc_parameter", lambda *_a: None)
    with pytest.raises(color.StyleFailure, match="chưa nhận đúng"):
        color._select_ocnums(object(), ["OC002"])


@pytest.mark.parametrize("options", [[], [{"value": "1", "label": "Other OC"}]])
def test_missing_oc_is_an_error_instead_of_exporting_another_oc(monkeypatch, options):
    state, calls = _oc_popup(monkeypatch)
    state["options"] = options
    with pytest.raises(color.StyleFailure):
        color._select_ocnums(object(), ["OC002"])
    assert calls == []


def _batch_setup(monkeypatch, tmp_path):
    source = tmp_path / "native.xlsx"
    source.write_bytes(b"native Excel download")
    monkeypatch.setattr(color, "resolve_controls", lambda _p: {})
    monkeypatch.setattr(color, "_prepare_style", lambda *_a: ({}, {"label": "SWV0001"}))
    monkeypatch.setattr(
        color,
        "_read_oc_parameter",
        lambda _p: {
            "options": [
                {"value": "1", "label": "OC/001"},
                {"value": "2", "label": "OC002"},
            ]
        },
    )
    selected = []
    monkeypatch.setattr(
        color, "_select_ocnums", lambda _p, labels: selected.extend(labels)
    )
    monkeypatch.setattr(color, "_view_and_download", lambda *_a: source)
    return selected


def _batch(tmp_path, retries=None):
    return color._batch_ocnums(
        object(),
        ["r1"],
        {"r1": "BUYERSTYLE"},
        tmp_path,
        lambda _line: None,
        None,
        retries or {},
    )


def test_styles_without_oc_are_skipped_and_other_styles_still_download(
    monkeypatch, tmp_path
):
    selected = _batch_setup(monkeypatch, tmp_path)
    current = {"reference": ""}

    def prepare(_page, _controls, ref):
        current["reference"] = ref
        return {}, {"label": "SWV0001"}

    monkeypatch.setattr(color, "_prepare_style", prepare)
    monkeypatch.setattr(
        color,
        "_read_oc_parameter",
        lambda _page: {
            "options": (
                []
                if current["reference"] == "empty"
                else [{"value": "1", "label": "OC001"}]
            )
        },
    )
    result = color._batch_ocnums(
        object(), ["empty", "has-oc"], {}, tmp_path, lambda _line: None, None, {}
    )
    assert result["failed"] == []
    assert selected == ["OC001"]
    assert result["skipped"][0]["style_ref"] == "empty"
    assert result["skipped"][0]["code"] == "COLOR_REPORT_OC_NOT_FOUND"
    assert len(result["saved"]) == 1


def test_each_oc_gets_a_separate_file_with_its_number(monkeypatch, tmp_path):
    selected = _batch_setup(monkeypatch, tmp_path)
    result = _batch(tmp_path)
    assert selected == ["OC/001", "OC002"]
    assert [item["file_name"] for item in result["saved"]] == [
        "BUYERSTYLE - SWV0001 - OC_001.xlsx",
        "BUYERSTYLE - SWV0001 - OC002.xlsx",
    ]
    assert all(item["style_ref_value"] == "r1" for item in result["saved"])
    assert result["failed"] == []
    assert (
        tmp_path / result["saved"][0]["file_name"]
    ).read_bytes() == b"native Excel download"


def test_oc_failure_does_not_stop_other_ocs_and_keeps_retry_identity(
    monkeypatch, tmp_path
):
    _batch_setup(monkeypatch, tmp_path)

    def select(_page, labels):
        if labels == ["OC/001"]:
            raise color.StyleFailure("COLOR_REPORT_OPTIONS_NOT_READY", "OC lỗi")

    monkeypatch.setattr(color, "_select_ocnums", select)
    result = _batch(tmp_path)
    assert [item["oc_num"] for item in result["saved"]] == ["OC002"]
    assert result["failed"][0]["style_ref_value"] == "r1"
    assert result["failed"][0]["oc_num"] == "OC/001"


def test_stop_mid_style_keeps_the_first_oc_file(monkeypatch, tmp_path):
    _batch_setup(monkeypatch, tmp_path)

    def select(_page, labels):
        if labels == ["OC002"]:
            raise AutomationCancelled()

    monkeypatch.setattr(color, "_select_ocnums", select)
    result = _batch(tmp_path)
    assert result["cancelled"] is True
    assert [item["oc_num"] for item in result["saved"]] == ["OC/001"]


def test_retry_downloads_only_failed_oc_and_preserves_existing_file(
    monkeypatch, tmp_path
):
    selected = _batch_setup(monkeypatch, tmp_path)
    existing = tmp_path / "BUYERSTYLE - SWV0001 - OC002.xlsx"
    existing.write_bytes(b"previous report")
    result = _batch(tmp_path, {"r1": ["OC002"]})
    assert selected == ["OC002"]
    assert result["saved"][0]["file_name"] == "BUYERSTYLE - SWV0001 - OC002 (2).xlsx"
    assert existing.read_bytes() == b"previous report"


def test_style_preparation_error_does_not_skip_the_next_style(monkeypatch, tmp_path):
    _batch_setup(monkeypatch, tmp_path)

    def prepare(_page, _controls, ref):
        if ref == "r1":
            raise color.StyleFailure(
                "COLOR_REPORT_STYLECODE_MISSING", "Thiếu StyleCode"
            )
        return {}, {"label": "SWV0002"}

    monkeypatch.setattr(color, "_prepare_style", prepare)
    result = color._batch_ocnums(
        object(), ["r1", "r2"], {}, tmp_path, lambda _line: None, None, {}
    )
    assert result["failed"][0]["style_ref_value"] == "r1"
    assert len(result["saved"]) == 2
    assert all(item["style_ref_value"] == "r2" for item in result["saved"])
