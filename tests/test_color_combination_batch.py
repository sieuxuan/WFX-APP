"""Hai entry point của Color Combination: tải tham số và tải hàng loạt.

`tests/test_color_combination.py` đã phủ luật chọn StyleCode và cascade. File
này phủ phần vỏ: mở report, chuyển lỗi thành mã cho UI, và bảo đảm probe chỉ
đọc tham số không kéo Chrome lên foreground.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import FakeClock
from wfx_panel.automation import color_combination
from wfx_panel.automation._common import PlaywrightTimeoutError
from wfx_panel.automation.color_combination import StyleFailure


@pytest.fixture
def clock():
    return FakeClock()


CONTROLS = {
    "OC Division": "id::OC Division",
    "Buyer": "id::Buyer",
    "Season": "id::Season",
    "BuyerStyleReference": "id::BuyerStyleReference",
    "StyleCode": "id::StyleCode",
    "SizeVisibility": "id::SizeVisibility",
}


def _cascade(style_options, *, season_value="s1"):
    return {
        "levels": {
            "division": {"options": [], "value": "d1"},
            "buyer": {"options": [], "value": "b1"},
            "season": {"options": [], "value": season_value},
            "style_ref": {"options": style_options, "value": ""},
        }
    }


def _wire(monkeypatch, clock, *, cascade=None, **overrides):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world)
    defaults = {
        "_open_report": lambda _page, _report: "report-page",
        "read_cascade": lambda *_a, **_k: (
            cascade if cascade is not None else _cascade([])
        ),
        "resolve_controls": lambda _page: dict(CONTROLS),
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        patch_automation(monkeypatch, color_combination, name, value)
    return world


# --- tải tham số --------------------------------------------------------


def test_loading_options_never_brings_chrome_to_the_front(monkeypatch, clock):
    """Probe chỉ đọc tham số: kéo Chrome lên sẽ cướp tab người dùng đang làm."""
    fronted: list[bool] = []
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world)
    original = color_combination._connect_to_chrome

    def connect(playwright, **kwargs):
        fronted.append(kwargs.get("bring_to_front", True))
        return original(playwright, **kwargs)

    patch_automation(monkeypatch, color_combination, "_connect_to_chrome", connect)
    patch_automation(
        monkeypatch, color_combination, "_open_report", lambda *_a: "page"
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "read_cascade",
        lambda *_a, **_k: _cascade([{"value": "r1", "label": "GWSD15176"}]),
    )

    color_combination.load_color_report_options({}, lambda _line: None)

    assert fronted == [False]


def test_loading_options_returns_every_level_and_counts_the_styles(
    monkeypatch, clock
):
    styles = [
        {"value": "r1", "label": "GWSD15176"},
        {"value": "r2", "label": "GWSD15177"},
    ]
    world = _wire(monkeypatch, clock, cascade=_cascade(styles))
    lines: list[str] = []

    result = color_combination.load_color_report_options({}, lines.append)

    assert result["code"] == "COLOR_REPORT_OPTIONS_READY"
    assert result["report_id"] == "color_combination_production"
    assert result["levels"]["style_ref"]["options"] == styles
    assert any("Đã đọc 2 style" in line for line in lines)
    assert world.driver_stops == 1


def test_a_season_with_no_style_at_all_is_reported_as_a_business_state(
    monkeypatch, clock
):
    _wire(monkeypatch, clock, cascade=_cascade([], season_value="s1"))

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "COLOR_REPORT_STYLE_LIST_EMPTY"
    # Vẫn phải trả cascade để UI giữ nguyên lựa chọn Division/Buyer/Season.
    assert result["levels"]["division"]["value"] == "d1"


def test_no_season_chosen_yet_is_not_an_empty_style_list_error(
    monkeypatch, clock
):
    _wire(monkeypatch, clock, cascade=_cascade([], season_value=""))

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "COLOR_REPORT_OPTIONS_READY"


def test_a_closed_browser_is_reported_before_anything_is_started(
    monkeypatch, clock
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world, chrome_ready=False)

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0


def test_an_expired_session_is_reported_without_reading_the_report(
    monkeypatch, clock
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world, logged_in=False)
    patch_automation(
        monkeypatch,
        color_combination,
        "_open_report",
        lambda *_a: pytest.fail("Chưa đăng nhập thì không được mở report"),
    )

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "NOT_LOGGED_IN"
    assert world.driver_stops == 1


def test_a_missing_parameter_control_keeps_its_own_error_code(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY", "Không tìm thấy tham số Season."
        )

    _wire(monkeypatch, clock, read_cascade=explode)

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "COLOR_REPORT_OPTIONS_NOT_READY"
    assert "Season" in result["message"]


def test_a_report_that_never_loads_is_reported_as_options_not_ready(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Report Viewer chưa load xong.")

    _wire(monkeypatch, clock, _open_report=explode)

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "COLOR_REPORT_OPTIONS_NOT_READY"
    assert "chưa load xong" in result["message"]


def test_an_unexpected_error_while_loading_names_its_type(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise KeyError("ddlSeason")

    _wire(monkeypatch, clock, read_cascade=explode)

    result = color_combination.load_color_report_options({}, lambda _line: None)

    assert result["code"] == "REPORT_LOAD_FAILED"
    assert result["message"].startswith("KeyError: ")


# --- chạy hàng loạt -----------------------------------------------------


def _batch(tmp_path, **kwargs):
    arguments = {
        "selection": {"division": "d1", "buyer": "b1", "season": "s1"},
        "style_refs": ["r1"],
        "output_dir": str(tmp_path),
        "log": lambda _line: None,
    }
    arguments.update(kwargs)
    return color_combination.run_color_report_batch(**arguments)


def test_a_batch_saves_one_file_per_style_using_the_reference_label(
    monkeypatch, clock, tmp_path
):
    styles = [
        {"value": "r1", "label": "GWSD15176"},
        {"value": "r2", "label": "GWSD15177"},
    ]
    world = _wire(monkeypatch, clock, cascade=_cascade(styles))
    source = tmp_path / "chrome-download.xlsx"
    source.write_text("excel", encoding="utf-8")
    patch_automation(
        monkeypatch,
        color_combination,
        "select_and_settle",
        lambda _page, controls, _label, _value: controls,
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "read_select_options",
        lambda _page, _control: [{"value": "c1", "label": "SWV0003935"}],
    )
    patch_automation(
        monkeypatch, color_combination, "read_select_value", lambda *_a: ""
    )
    patch_automation(
        monkeypatch, color_combination, "_view_and_download", lambda *_a: source
    )
    output = tmp_path / "out"
    output.mkdir()

    result = _batch(
        tmp_path, style_refs=["r1", "r2"], output_dir=str(output)
    )

    assert result["code"] == "COLOR_REPORT_BATCH_DONE"
    assert result["message"] == "Đã tải 2/2 style."
    assert [item["file_name"] for item in result["saved"]] == [
        "GWSD15176 - SWV0003935.xlsx",
        "GWSD15177 - SWV0003935.xlsx",
    ]
    assert result["failed"] == []
    assert world.driver_stops == 1


def test_a_style_that_fails_is_counted_but_does_not_stop_the_batch(
    monkeypatch, clock, tmp_path
):
    styles = [
        {"value": "r1", "label": "GWSD15176"},
        {"value": "r2", "label": "GWSD15177"},
    ]
    _wire(monkeypatch, clock, cascade=_cascade(styles))
    source = tmp_path / "chrome-download.xlsx"
    source.write_text("excel", encoding="utf-8")

    def one_style(_page, _controls, reference, *_args, **_kwargs):
        if reference == "r1":
            raise StyleFailure(
                "COLOR_REPORT_STYLECODE_MISSING", "Không có StyleCode cho r1."
            )
        return {
            "style_ref": "GWSD15177",
            "style_code": "SWV0003935",
            "file_path": str(source),
            "file_name": source.name,
        }

    patch_automation(monkeypatch, color_combination, "_run_one_style", one_style)

    result = _batch(tmp_path, style_refs=["r1", "r2"])

    assert result["code"] == "COLOR_REPORT_BATCH_DONE"
    assert result["message"] == "Đã tải 1/2 style. 1 style lỗi."
    assert result["failed"][0]["code"] == "COLOR_REPORT_STYLECODE_MISSING"


def test_pressing_stop_keeps_the_files_already_downloaded(
    monkeypatch, clock, tmp_path
):
    from wfx_panel.automation.runtime import AutomationCancelled

    _wire(
        monkeypatch,
        clock,
        cascade=_cascade([{"value": "r1", "label": "GWSD15176"}]),
    )

    def one_style(*_args, **_kwargs):
        raise AutomationCancelled()

    patch_automation(monkeypatch, color_combination, "_run_one_style", one_style)

    result = _batch(tmp_path, style_refs=["r1", "r2"])

    assert result["code"] == "COLOR_REPORT_CANCELLED"
    assert "0/2 style" in result["message"]
    assert result["output_dir"] == str(tmp_path)


def test_a_batch_without_any_style_never_opens_the_browser(
    monkeypatch, clock, tmp_path
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world)

    result = _batch(tmp_path, style_refs=["  ", ""])

    assert result["code"] == "COLOR_REPORT_NO_STYLE_SELECTED"
    assert world.driver_starts == 0


@pytest.mark.parametrize("output_dir", ["", "   "])
def test_a_batch_without_an_output_folder_is_refused(
    monkeypatch, clock, tmp_path, output_dir
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world)

    result = _batch(tmp_path, output_dir=output_dir)

    assert result["code"] == "COLOR_REPORT_OUTPUT_DIR_REQUIRED"
    assert world.driver_starts == 0


def test_a_folder_the_user_deleted_meanwhile_is_refused(
    monkeypatch, clock, tmp_path
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world)

    result = _batch(tmp_path, output_dir=str(tmp_path / "khong-ton-tai"))

    assert result["code"] == "COLOR_REPORT_OUTPUT_DIR_REQUIRED"
    assert world.driver_starts == 0


def test_a_closed_browser_stops_the_batch_before_it_starts(
    monkeypatch, clock, tmp_path
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world, chrome_ready=False)

    result = _batch(tmp_path)

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0


def test_an_expired_session_stops_the_batch_without_downloading(
    monkeypatch, clock, tmp_path
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, color_combination, world, logged_in=False)
    patch_automation(
        monkeypatch,
        color_combination,
        "_open_report",
        lambda *_a: pytest.fail("Chưa đăng nhập thì không được mở report"),
    )

    result = _batch(tmp_path)

    assert result["code"] == "NOT_LOGGED_IN"
    assert world.driver_stops == 1


def test_a_batch_that_cannot_read_the_cascade_keeps_the_style_failure_code(
    monkeypatch, clock, tmp_path
):
    def explode(*_args, **_kwargs):
        raise StyleFailure("COLOR_REPORT_OPTIONS_NOT_READY", "Mất tham số.")

    _wire(monkeypatch, clock, read_cascade=explode)

    assert _batch(tmp_path)["code"] == "COLOR_REPORT_OPTIONS_NOT_READY"


def test_a_batch_timeout_is_reported_as_options_not_ready(
    monkeypatch, clock, tmp_path
):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Report Viewer chưa load xong.")

    _wire(monkeypatch, clock, _open_report=explode)

    assert _batch(tmp_path)["code"] == "COLOR_REPORT_OPTIONS_NOT_READY"


def test_an_unexpected_batch_error_is_an_export_failure(
    monkeypatch, clock, tmp_path
):
    def explode(*_args, **_kwargs):
        raise ValueError("control id rỗng")

    _wire(monkeypatch, clock, resolve_controls=explode)

    result = _batch(tmp_path)

    assert result["code"] == "REPORT_EXPORT_FAILED"
    assert result["message"].startswith("ValueError: ")


# --- một style ----------------------------------------------------------


def test_size_visibility_is_only_set_when_it_is_not_already_yes(
    monkeypatch, tmp_path
):
    source = tmp_path / "chrome-download.xlsx"
    source.write_text("excel", encoding="utf-8")
    settled: list[tuple[str, str]] = []

    patch_automation(
        monkeypatch,
        color_combination,
        "select_and_settle",
        lambda _page, controls, label, value: (
            settled.append((label, value)) or controls
        ),
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "read_select_options",
        lambda _page, control: (
            [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
            if "SizeVisibility" in control
            else [{"value": "c1", "label": "SWV0003935"}]
        ),
    )
    patch_automation(
        monkeypatch, color_combination, "read_select_value", lambda *_a: "yes"
    )
    patch_automation(
        monkeypatch, color_combination, "_view_and_download", lambda *_a: source
    )

    color_combination._run_one_style(
        object(), dict(CONTROLS), "r1", tmp_path, lambda _line: None
    )

    # Chỉ một postback cho BuyerStyleReference; StyleCode một option và
    # SizeVisibility đã Yes nên không được đặt lại.
    assert settled == [("BuyerStyleReference", "r1")]


def test_size_visibility_is_switched_to_yes_when_wfx_defaults_to_no(
    monkeypatch, tmp_path
):
    source = tmp_path / "chrome-download.xlsx"
    source.write_text("excel", encoding="utf-8")
    settled: list[tuple[str, str]] = []

    patch_automation(
        monkeypatch,
        color_combination,
        "select_and_settle",
        lambda _page, controls, label, value: (
            settled.append((label, value)) or controls
        ),
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "read_select_options",
        lambda _page, control: (
            [{"value": "no", "label": "No"}, {"value": "yes", "label": " yes "}]
            if "SizeVisibility" in control
            else [
                {"value": "c1", "label": "SWV0003935"},
                {"value": "c2", "label": "SWV0004012"},
            ]
        ),
    )
    patch_automation(
        monkeypatch, color_combination, "read_select_value", lambda *_a: "no"
    )
    patch_automation(
        monkeypatch, color_combination, "_view_and_download", lambda *_a: source
    )

    color_combination._run_one_style(
        object(), dict(CONTROLS), "r1", tmp_path, lambda _line: None
    )

    assert settled == [
        ("BuyerStyleReference", "r1"),
        # Nhiều StyleCode thì phải chọn bản mới nhất.
        ("StyleCode", "c2"),
        ("SizeVisibility", "yes"),
    ]


def test_a_file_that_cannot_be_copied_is_reported_with_its_style(
    monkeypatch, tmp_path
):
    source = tmp_path / "chrome-download.xlsx"
    source.write_text("excel", encoding="utf-8")
    patch_automation(
        monkeypatch,
        color_combination,
        "select_and_settle",
        lambda _page, controls, *_a: controls,
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "read_select_options",
        lambda _page, _control: [{"value": "c1", "label": "SWV0003935"}],
    )
    patch_automation(
        monkeypatch, color_combination, "read_select_value", lambda *_a: ""
    )
    patch_automation(
        monkeypatch, color_combination, "_view_and_download", lambda *_a: source
    )

    def refuse(*_args, **_kwargs):
        raise PermissionError("thư mục chỉ đọc")

    monkeypatch.setattr(shutil, "copy2", refuse)

    with pytest.raises(StyleFailure) as error:
        color_combination._run_one_style(
            object(),
            dict(CONTROLS),
            "r1",
            tmp_path,
            lambda _line: None,
            "GWSD15176",
        )

    assert error.value.code == "COLOR_REPORT_SAVE_FAILED"
    assert "GWSD15176" in error.value.message
    assert "PermissionError" in error.value.message


# --- chọn tham số và chờ postback ---------------------------------------


class SelectNode:
    def __init__(self):
        self.selected: list[str] = []

    def select_option(self, value):
        self.selected.append(value)


class ParamPage:
    def __init__(self):
        self.nodes: dict[str, SelectNode] = {}

    def locator(self, selector):
        return self.nodes.setdefault(selector, SelectNode())


def test_setting_a_parameter_waits_for_the_postback_then_rereads_the_controls(
    monkeypatch,
):
    page = ParamPage()
    waited: list[float] = []
    patch_automation(
        monkeypatch,
        color_combination,
        "_wait_postback_settled",
        lambda _page, timeout: waited.append(timeout),
    )
    patch_automation(
        monkeypatch, color_combination, "resolve_controls", lambda _page: {"a": "b"}
    )

    assert color_combination.select_and_settle(
        page, {"Season": 'ddl"Season"'}, "Season", "s1"
    ) == {"a": "b"}
    # Dấu nháy kép trong id phải bị loại, nếu không selector `[id="..."]` vỡ.
    assert page.nodes['[id="ddlSeason"]'].selected == ["s1"]
    assert waited == [color_combination.POSTBACK_TIMEOUT_SECONDS]


def test_a_parameter_wfx_does_not_render_is_named_not_clicked_blindly():
    with pytest.raises(StyleFailure) as error:
        color_combination.select_and_settle(
            ParamPage(), {}, "Season", "s1"
        )

    assert error.value.code == "COLOR_REPORT_OPTIONS_NOT_READY"
    assert "Season" in error.value.message


# --- tải file report ----------------------------------------------------


def test_the_downloaded_file_is_looked_up_in_the_users_downloads_folder(
    monkeypatch, tmp_path
):
    from wfx_panel.automation import runtime

    order: list[str] = []
    patch_automation(
        monkeypatch,
        color_combination,
        "_click_view_report",
        lambda _page: order.append("view"),
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "_wait_report_ready",
        lambda _page, _log: order.append("ready"),
    )
    patch_automation(
        monkeypatch,
        color_combination,
        "_export_excel",
        lambda _page: order.append("export") or "Color Combination.xlsx",
    )
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)

    path = color_combination._view_and_download(object(), lambda _line: None)

    assert order == ["view", "ready", "export"]
    assert path == tmp_path / "Color Combination.xlsx"
    assert isinstance(path, Path)
