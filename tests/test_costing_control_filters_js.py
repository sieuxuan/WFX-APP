"""Chạy thật những script lọc control mà Costing gửi vào Chrome.

`costing.py` thay `is_visible()`/`is_enabled()`/`get_attribute()` của từng phần
tử bằng một `evaluate_all` duy nhất để bớt lượt gọi CDP. Ngữ nghĩa của mấy
đoạn JS đó chính là thứ quyết định app điền vào ô nào và chọn option nào — tức
là nhánh ghi dữ liệu lên WFX.

`tests/test_costing_control_filters.py` khoá phần Python, nhưng fake ở đó không
chạy JavaScript: bỏ hẳn một vị từ trong thân script vẫn xanh. Test này thực thi
chính chuỗi được gửi vào Chrome bằng Node, theo đúng cách
`tests/test_supplier_invoice_row_scan_js.py` đã làm.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from wfx_panel.automation import costing

HARNESS = Path(__file__).parent / "js" / "costing_control_filters.js"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(
    node is None,
    reason="Cần Node để chạy chính script JS được gửi vào Chrome",
)

SCRIPTS = {
    "usable": costing._USABLE_CONTROL_JS,
    "visible": costing._VISIBLE_JS,
    "visible_with_id": costing._VISIBLE_WITH_ID_JS,
    "inline_editor": costing._INLINE_EDITOR_JS,
    "matching_options": costing._MATCHING_OPTION_VALUES_JS,
}


def _run(tmp_path: Path, cases: list[dict]) -> dict:
    payload = tmp_path / "cases.json"
    payload.write_text(
        json.dumps({"scripts": SCRIPTS, "cases": cases}),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [node, str(HARNESS), str(payload)],
        capture_output=True,
        text=True,
        # Harness in tiếng Việt; locale Windows là cp1252 nên phải nói rõ UTF-8.
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    results = json.loads(completed.stdout)
    for item in results:
        assert "error" not in item, f"{item['name']}: {item.get('error')}"
    return {item["name"]: item["value"] for item in results}


# --- Lọc control dùng được ---------------------------------------------


def test_usable_controls_drop_hidden_disabled_and_detached(tmp_path):
    values = _run(
        tmp_path,
        [
            {
                "name": "usable",
                "script": "usable",
                "elements": [
                    {"id": "ok"},
                    {"id": "display-none", "display": "none"},
                    {"id": "visibility-hidden", "visibility": "hidden"},
                    {"id": "zero-box", "width": 0, "height": 0},
                    {"id": "disabled", "disabled": True},
                    {"id": "detached", "connected": False},
                    {"id": "ok-2"},
                ],
            }
        ],
    )

    assert values["usable"] == [0, 6], (
        "Chỉ control vừa hiện vừa dùng được mới là ứng viên để điền"
    )


def test_visible_filter_keeps_a_disabled_but_shown_element(tmp_path):
    """`_VISIBLE_JS` chỉ hỏi 'có hiện không', không hỏi 'có bấm được không'."""
    values = _run(
        tmp_path,
        [
            {
                "name": "visible",
                "script": "visible",
                "elements": [
                    {"id": "grid", "disabled": True},
                    {"id": "hidden-grid", "display": "none"},
                ],
            }
        ],
    )

    assert values["visible"] == [0]


# --- Soát lại id --------------------------------------------------------


def test_only_elements_carrying_that_exact_id_match(tmp_path):
    values = _run(
        tmp_path,
        [
            {
                "name": "by-id",
                "script": "visible_with_id",
                "arg": "lblRate",
                "elements": [
                    {"id": "lblRateExtra"},
                    {"id": "lblRate"},
                    {"id": "lblRate", "display": "none"},
                    {"id": None},
                ],
            }
        ],
    )

    assert values["by-id"] == [1], (
        "WFX lặp id trên nhiều dòng nên selector phải được soát lại bằng id"
    )


# --- Chọn ô nhập inline -------------------------------------------------


_BLOCKED = ["hidden", "checkbox", "radio", "file", "button", "submit"]


@pytest.mark.parametrize("blocked", _BLOCKED)
def test_a_blocked_input_type_is_never_an_inline_editor(tmp_path, blocked):
    values = _run(
        tmp_path,
        [
            {
                "name": "editors",
                "script": "inline_editor",
                "arg": "",
                "elements": [{"id": "x", "type": blocked}, {"id": "txtQty"}],
            }
        ],
    )

    assert [item["index"] for item in values["editors"]] == [1]


def test_an_inline_editor_reports_its_tag_and_suffix_match(tmp_path):
    values = _run(
        tmp_path,
        [
            {
                "name": "editors",
                "script": "inline_editor",
                "arg": "qty",
                "elements": [
                    {"id": "txtRate", "tag": "input"},
                    {"id": "ddlQty", "tag": "select"},
                    {"id": "", "name": "gridQtyValue", "tag": "textarea"},
                ],
            }
        ],
    )

    assert values["editors"] == [
        {"index": 0, "tag": "input", "matches_suffix": False},
        {"index": 1, "tag": "select", "matches_suffix": True},
        {"index": 2, "tag": "textarea", "matches_suffix": True},
    ]


def test_an_empty_suffix_never_marks_everything_as_a_match(tmp_path):
    values = _run(
        tmp_path,
        [
            {
                "name": "editors",
                "script": "inline_editor",
                "arg": "",
                "elements": [{"id": "txtQty"}, {"id": "txtRate"}],
            }
        ],
    )

    assert [item["matches_suffix"] for item in values["editors"]] == [False, False]


def test_an_inline_editor_is_still_filtered_for_visibility(tmp_path):
    values = _run(
        tmp_path,
        [
            {
                "name": "editors",
                "script": "inline_editor",
                "arg": "",
                "elements": [
                    {"id": "txtHidden", "visibility": "hidden"},
                    {"id": "txtLocked", "disabled": True},
                    {"id": "txtQty"},
                ],
            }
        ],
    )

    assert [item["index"] for item in values["editors"]] == [2]


# --- Khớp option --------------------------------------------------------


def _options(tmp_path, wanted: str) -> list[str]:
    return _run(
        tmp_path,
        [
            {
                "name": "options",
                "script": "matching_options",
                "arg": wanted,
                "elements": [
                    {"textContent": "Alpha Ltd", "value": "1"},
                    {"textContent": "Beta Co", "value": "2"},
                    {"textContent": "Alpha Ltd Extra", "value": "3"},
                ],
            }
        ],
    )["options"]


def test_an_option_matches_by_label_or_by_value(tmp_path):
    assert _options(tmp_path, "alpha ltd") == ["1"]
    assert _options(tmp_path, "2") == ["2"]


def test_a_partial_label_matches_nothing(tmp_path):
    """Khớp gần đúng ở đây là chọn nhầm nhà cung cấp rồi Save lên WFX."""
    assert _options(tmp_path, "alpha") == []


def test_option_matching_ignores_surrounding_spaces_and_case(tmp_path):
    values = _run(
        tmp_path,
        [
            {
                "name": "options",
                "script": "matching_options",
                "arg": "beta co",
                "elements": [{"textContent": "  BETA Co  ", "value": " 2 "}],
            }
        ],
    )

    assert values["options"] == ["2"]
