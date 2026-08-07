import pytest

from wfx_panel.automation import color_combination, reports
from wfx_panel.automation.runtime import AutomationCancelled


def _options(*labels):
    return [
        {"value": str(index), "label": label}
        for index, label in enumerate(labels, start=1)
    ]


def test_picks_the_style_code_with_the_largest_trailing_number():
    """Số đuôi lớn hơn là style mới hơn, không phụ thuộc thứ tự WFX trả về."""
    picked = color_combination.pick_style_code(
        _options("SWV0004012", "SWV0003935")
    )

    assert picked["label"] == "SWV0004012"


def test_single_option_is_used_even_without_digits():
    picked = color_combination.pick_style_code(_options("SAMPLE"))

    assert picked["label"] == "SAMPLE"


def test_falls_back_to_the_last_option_when_no_code_has_digits():
    """WFX sắp xếp tăng dần, nên option cuối là phỏng đoán an toàn nhất."""
    picked = color_combination.pick_style_code(_options("ALPHA", "BETA"))

    assert picked["label"] == "BETA"


def test_ties_prefer_the_later_option():
    picked = color_combination.pick_style_code(
        _options("AAA0003935", "BBB0003935")
    )

    assert picked["label"] == "BBB0003935"


def test_empty_option_list_returns_none():
    assert color_combination.pick_style_code([]) is None


def test_file_stem_joins_style_reference_and_code():
    stem = color_combination.safe_file_stem("GWSD15176", "SWV0003935")

    assert stem == "GWSD15176 - SWV0003935"


def test_file_stem_replaces_characters_windows_forbids():
    stem = color_combination.safe_file_stem("GW/SD:15176", "SWV*3935")

    assert stem == "GW_SD_15176 - SWV_3935"


def test_file_stem_drops_the_code_part_when_there_is_no_code():
    assert color_combination.safe_file_stem("GWSD15176", "") == "GWSD15176"


def test_file_stem_never_ends_with_a_dot_or_space():
    """Windows từ chối tên file kết thúc bằng dấu chấm hoặc khoảng trắng."""
    assert color_combination.safe_file_stem("GWSD15176.", "") == "GWSD15176"


def test_unique_target_adds_a_counter_when_the_name_is_taken(tmp_path):
    (tmp_path / "GWSD15176.xlsx").write_text("x", encoding="utf-8")
    (tmp_path / "GWSD15176 (2).xlsx").write_text("x", encoding="utf-8")

    target = color_combination.unique_target(tmp_path, "GWSD15176")

    assert target == tmp_path / "GWSD15176 (3).xlsx"


def test_unique_target_uses_the_plain_name_when_it_is_free(tmp_path):
    target = color_combination.unique_target(tmp_path, "GWSD15176")

    assert target == tmp_path / "GWSD15176.xlsx"


def test_prune_keeps_every_level_that_still_exists():
    values = {"division": "d1", "buyer": "b1", "season": "s1"}
    options = {
        "division": _options("d1"),
        "buyer": _options("b1"),
        "season": _options("s1"),
    }
    options["division"][0]["value"] = "d1"
    options["buyer"][0]["value"] = "b1"
    options["season"][0]["value"] = "s1"

    assert color_combination.prune_selection(values, options) == values


def test_prune_drops_lower_levels_once_one_is_stale():
    """Buyer đổi thì Season của buyer cũ không còn ý nghĩa."""
    values = {"division": "d1", "buyer": "gone", "season": "s1"}
    options = {
        "division": [{"value": "d1", "label": "D1"}],
        "buyer": [{"value": "b1", "label": "B1"}],
        "season": [{"value": "s1", "label": "S1"}],
    }

    assert color_combination.prune_selection(values, options) == {
        "division": "d1"
    }


def test_prune_returns_nothing_when_the_first_level_is_missing():
    assert color_combination.prune_selection({}, {}) == {}


def _saved(style_ref):
    return {
        "style_ref": style_ref,
        "style_code": "SWV0000001",
        "file_path": f"D:/out/{style_ref}.xlsx",
        "file_name": f"{style_ref}.xlsx",
    }


def test_batch_continues_after_a_style_fails():
    """50 style một lượt: một style hỏng không được giết cả lượt chạy."""

    def run_one(style_ref):
        if style_ref == "B":
            raise color_combination.StyleFailure(
                "COLOR_REPORT_STYLECODE_MISSING", "Không có StyleCode."
            )
        return _saved(style_ref)

    result = color_combination.batch_styles(
        ["A", "B", "C"], run_one, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A", "C"]
    assert result["failed"] == [
        {
            "style_ref": "B",
            "code": "COLOR_REPORT_STYLECODE_MISSING",
            "message": "Không có StyleCode.",
        }
    ]
    assert result["cancelled"] is False


def test_batch_labels_unexpected_errors_with_a_generic_code():
    def run_one(_style_ref):
        raise ValueError("frame detached")

    result = color_combination.batch_styles(
        ["A"], run_one, log=lambda _line: None
    )

    assert result["failed"][0]["code"] == "COLOR_REPORT_STYLE_FAILED"
    assert "frame detached" in result["failed"][0]["message"]


def test_batch_keeps_saved_files_when_the_user_presses_stop():
    """Stop giữa lượt vẫn phải trả về file đã tải, không mất trắng."""

    def run_one(style_ref):
        if style_ref == "C":
            raise AutomationCancelled("ACTION_CANCELLED")
        return _saved(style_ref)

    result = color_combination.batch_styles(
        ["A", "B", "C", "D"], run_one, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A", "B"]
    assert result["cancelled"] is True


def test_batch_progress_messages_end_with_the_counter_suffix():
    """UI đọc hậu tố n/m để hiện bộ đếm; đổi định dạng là hỏng thẻ tiến độ."""
    seen = []

    color_combination.batch_styles(
        ["A", "B"],
        _saved,
        progress=lambda stage, message, step, total: seen.append(
            (stage, message, step, total)
        ),
        log=lambda _line: None,
    )

    assert [
        item[1].endswith(suffix)
        for item, suffix in zip(seen, ("1/2", "2/2"), strict=True)
    ] == [
        True,
        True,
    ]
    assert seen[0][0] == "style"
    assert seen[1][2:] == (2, 2)


def test_batch_ignores_blank_style_references():
    result = color_combination.batch_styles(
        ["A", "  ", ""], _saved, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A"]


def test_catalog_exposes_the_kind_so_the_ui_picks_the_right_form():
    """Shipment Summary dùng form tham số một lượt; báo cáo mới dùng cascade."""
    catalog = {item["id"]: item for item in reports.report_catalog()}

    assert catalog["shipment_summary"]["kind"] == "simple"
    assert catalog[color_combination.REPORT_ID]["kind"] == "cascade_batch"
    assert catalog[color_combination.REPORT_ID]["name"] == (
        color_combination.REPORT_NAME
    )


def test_color_combination_report_points_at_the_wfx_custom_report():
    entry = reports.REPORTS[color_combination.REPORT_ID]

    assert entry["custom_report_id"] == "0864e93b-ee5d-4dbc-840e-c83a1b44d728"
    assert entry["custom_report_id"] in entry["url"]
    assert entry["url"].startswith("https://")


class _FakeLocator:
    def __init__(self, payload):
        self._payload = payload

    def evaluate(self, _script, *_args):
        return self._payload


class _FakePage:
    def __init__(self, payload):
        self._payload = payload
        self.selectors = []

    def locator(self, selector):
        self.selectors.append(selector)
        return _FakeLocator(self._payload)


def test_resolve_controls_maps_parameter_labels_to_element_ids():
    page = _FakePage(
        {
            "OC Division": "ctl04_ctl03_ddValue",
            "BuyerStyleReference": "ctl04_ctl09_ddValue",
        }
    )

    controls = reports.resolve_controls(page)

    assert controls["BuyerStyleReference"] == "ctl04_ctl09_ddValue"
    assert reports.PARAMETER_TABLE in page.selectors[0]


def test_read_select_options_returns_value_and_label_pairs():
    page = _FakePage([{"value": "1", "label": "GWSD15176"}])

    options = reports.read_select_options(page, "ctl04_ctl09_ddValue")

    assert options == [{"value": "1", "label": "GWSD15176"}]


class _CascadePage:
    """Giả lập ReportViewer: đổi một cấp thì cấp dưới đổi theo."""

    OPTIONS = {
        "OC Division": [{"value": "d1", "label": "PRO SPORTS - WOVEN HANOI"}],
        "Buyer": [{"value": "b1", "label": "J.LINDEBERG"}],
        "Season": [{"value": "s1", "label": "WH25"}],
        "BuyerStyleReference": [
            {"value": "r1", "label": "GWSD15176"},
            {"value": "r2", "label": "GWSD15177"},
        ],
    }

    def __init__(self):
        self.selected = {}
        self.settled = 0


def _install_cascade_fakes(monkeypatch, page):
    monkeypatch.setattr(
        color_combination, "resolve_controls", lambda _page: {
            label: f"id::{label}" for label in _CascadePage.OPTIONS
        }
    )
    monkeypatch.setattr(
        color_combination,
        "read_select_options",
        lambda _page, control_id: _CascadePage.OPTIONS[control_id.split("::")[1]],
    )
    monkeypatch.setattr(
        color_combination,
        "read_select_value",
        lambda _page, control_id: page.selected.get(control_id.split("::")[1], ""),
    )

    def fake_select(_page, controls, label, value):
        page.selected[label] = value
        page.settled += 1
        return controls

    monkeypatch.setattr(color_combination, "select_and_settle", fake_select)


def test_read_cascade_applies_saved_values_and_returns_every_level(monkeypatch):
    page = _CascadePage()
    _install_cascade_fakes(monkeypatch, page)

    levels = color_combination.read_cascade(
        page, {"division": "d1", "buyer": "b1", "season": "s1"}
    )["levels"]

    assert page.selected["Season"] == "s1"
    assert levels["style_ref"]["options"] == _CascadePage.OPTIONS[
        "BuyerStyleReference"
    ]
    assert levels["division"]["value"] == "d1"


def test_read_cascade_stops_applying_at_the_first_stale_value(monkeypatch):
    """Division cũ không còn thì không được áp Buyer/Season của lần trước."""
    page = _CascadePage()
    _install_cascade_fakes(monkeypatch, page)

    color_combination.read_cascade(
        page, {"division": "gone", "buyer": "b1", "season": "s1"}
    )

    assert page.selected == {}


def test_run_one_style_saves_the_native_download_under_the_style_name(
    monkeypatch, tmp_path
):
    """File native của Chrome được sao chép sang thư mục user chọn."""
    source = tmp_path / "downloaded.xlsx"
    source.write_text("excel", encoding="utf-8")
    controls = {"BuyerStyleReference": "id::ref", "StyleCode": "id::code"}

    monkeypatch.setattr(
        color_combination, "select_and_settle", lambda *_a, **_k: controls
    )
    monkeypatch.setattr(
        color_combination,
        "read_select_options",
        lambda _page, _id: [{"value": "c1", "label": "SWV0003935"}],
    )
    monkeypatch.setattr(color_combination, "read_select_value", lambda *_a: "")
    monkeypatch.setattr(color_combination, "_view_and_download", lambda *_a: source)

    saved = color_combination._run_one_style(
        object(), controls, "GWSD15176", tmp_path, lambda _line: None
    )

    assert saved["style_code"] == "SWV0003935"
    assert saved["file_name"] == "GWSD15176 - SWV0003935.xlsx"
    assert (tmp_path / "GWSD15176 - SWV0003935.xlsx").read_text(
        encoding="utf-8"
    ) == "excel"


def test_run_one_style_reports_a_missing_style_code(monkeypatch, tmp_path):
    controls = {"BuyerStyleReference": "id::ref", "StyleCode": "id::code"}
    monkeypatch.setattr(
        color_combination, "select_and_settle", lambda *_a, **_k: controls
    )
    monkeypatch.setattr(color_combination, "read_select_options", lambda *_a: [])

    with pytest.raises(color_combination.StyleFailure) as error:
        color_combination._run_one_style(
            object(), controls, "GWSD15176", tmp_path, lambda _line: None
        )

    assert error.value.code == "COLOR_REPORT_STYLECODE_MISSING"


def test_batch_requires_a_style_selection(tmp_path):
    result = color_combination.run_color_report_batch(
        {"division": "d1"}, [], str(tmp_path), log=lambda _line: None
    )

    assert result["code"] == "COLOR_REPORT_NO_STYLE_SELECTED"
    assert result["ok"] is False


def test_batch_requires_an_existing_output_directory(tmp_path):
    result = color_combination.run_color_report_batch(
        {"division": "d1"},
        ["GWSD15176"],
        str(tmp_path / "khong-ton-tai"),
        log=lambda _line: None,
    )

    assert result["code"] == "COLOR_REPORT_OUTPUT_DIR_REQUIRED"
