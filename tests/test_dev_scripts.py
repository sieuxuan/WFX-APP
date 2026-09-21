"""Hai script phát hành/kiểm thử trong `scripts/`.

Chúng chưa từng chạy trong test (0%), nhưng cả hai đều là hợp đồng thật:

* `build_article_library_manifest.py` sinh đúng manifest mà
  `wfx_panel/stores/article_library.py` đọc — sai schema/định dạng là app
  không tải được dữ liệu Article.
* `visual_regression_panel.py` là chốt chặn giao diện: nó so ảnh và *validate*
  các luật CLAUDE.md không thể kiểm bằng unit test giao diện (DPR đúng theo
  DPI, không còn `title` native, không tràn ngang, không có nút nhỏ hơn 22px).
  Phần chụp ảnh cần màn hình thật nên không test được; phần so sánh và validate
  thì test được và chính nó quyết định build đỏ hay xanh.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from scripts import build_article_library_manifest as manifest_script
from scripts import visual_regression_panel as visual
from wfx_panel.stores import article_library


def _run_manifest(monkeypatch, argv) -> int:
    monkeypatch.setattr(sys, "argv", ["build_article_library_manifest.py", *argv])
    return manifest_script.main()


# --- manifest Article Library --------------------------------------------


def test_the_manifest_matches_what_the_app_expects_to_read(
    tmp_path, monkeypatch
):
    source = tmp_path / "Article List.csv"
    source.write_text("Article Code,Article Name\nA,B\n", encoding="utf-8")
    output = tmp_path / "data" / "article-library-manifest.json"

    assert (
        _run_manifest(
            monkeypatch,
            [str(source), "--output", str(output), "--version", "v1"],
        )
        == 0
    )

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == article_library.SCHEMA_VERSION
    assert manifest["version"] == "v1"
    assert manifest["format"] == "csv"
    assert manifest["data_url"] == "Article List.csv"
    assert manifest["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_an_absolute_data_url_is_kept_as_given(tmp_path, monkeypatch):
    source = tmp_path / "a.xlsx"
    source.write_bytes(b"x")
    output = tmp_path / "m.json"

    _run_manifest(
        monkeypatch,
        [
            str(source),
            "--output",
            str(output),
            "--data-url",
            "https://cdn.test/a.xlsx",
        ],
    )

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["data_url"] == "https://cdn.test/a.xlsx"
    assert manifest["format"] == "xlsx"


def test_an_omitted_version_becomes_a_utc_timestamp(tmp_path, monkeypatch):
    source = tmp_path / "a.csv"
    source.write_text("x", encoding="utf-8")
    output = tmp_path / "m.json"

    _run_manifest(monkeypatch, [str(source), "--output", str(output)])

    version = json.loads(output.read_text(encoding="utf-8"))["version"]
    assert version.endswith("Z")
    assert len(version) == len("20260921T101500Z")


@pytest.mark.parametrize("name", ["a.txt", "a.json", "a"])
def test_only_csv_and_xlsx_are_accepted(tmp_path, monkeypatch, name):
    source = tmp_path / name
    source.write_bytes(b"x")

    with pytest.raises(SystemExit):
        _run_manifest(
            monkeypatch, [str(source), "--output", str(tmp_path / "m.json")]
        )


def test_a_source_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _run_manifest(
            monkeypatch,
            [str(tmp_path / "khong-co.csv"), "--output", str(tmp_path / "m.json")],
        )


# --- so ảnh visual regression --------------------------------------------


def _image(path: Path, size=(4, 4), colour=(255, 255, 255)) -> Path:
    Image.new("RGB", size, colour).save(path, format="PNG")
    return path


def test_two_identical_captures_have_no_difference(tmp_path):
    first = Image.open(_image(tmp_path / "a.png"))
    second = Image.open(_image(tmp_path / "b.png"))

    assert visual._significant_difference(first, second) == 0.0


def test_a_capture_of_another_size_is_a_total_difference(tmp_path):
    first = Image.open(_image(tmp_path / "a.png", size=(4, 4)))
    second = Image.open(_image(tmp_path / "b.png", size=(8, 8)))

    assert visual._significant_difference(first, second) == 1.0


def test_only_pixels_that_moved_more_than_the_noise_floor_count(tmp_path):
    first = Image.open(_image(tmp_path / "a.png", colour=(100, 100, 100)))
    quiet = Image.open(_image(tmp_path / "b.png", colour=(105, 105, 105)))
    loud = Image.open(_image(tmp_path / "c.png", colour=(200, 200, 200)))

    assert visual._significant_difference(first, quiet) == 0.0
    assert visual._significant_difference(first, loud) == 1.0


# --- validate manifest giao diện -----------------------------------------


def _metrics(**overrides) -> dict:
    base = {
        "dpr": 1.5,
        "theme": "light",
        "nativeTitles": 0,
        "scrollWidth": 440,
        "innerWidth": 440,
        "tinyButtons": [],
    }
    base.update(overrides)
    return base


def _manifest(**overrides) -> dict:
    base = {"theme": "light", "dpi": 150, "expectedDpr": 1.5, "metrics": _metrics()}
    base.update(overrides)
    return base


def test_a_clean_capture_has_no_errors():
    assert visual._validate_manifest(_manifest()) == []


def test_a_wrong_device_pixel_ratio_is_an_error():
    errors = visual._validate_manifest(
        _manifest(metrics=_metrics(dpr=1.0))
    )

    assert any("DPR" in error for error in errors)


def test_a_device_pixel_ratio_within_tolerance_is_accepted():
    assert visual._validate_manifest(_manifest(metrics=_metrics(dpr=1.55))) == []


def test_a_theme_mismatch_is_an_error():
    errors = visual._validate_manifest(_manifest(metrics=_metrics(theme="dark")))

    assert any("theme" in error for error in errors)


def test_a_leftover_native_title_is_an_error():
    """CLAUDE.md: tooltip là `data-tooltip`, không được còn `title` native."""
    errors = visual._validate_manifest(
        _manifest(metrics=_metrics(nativeTitles=3))
    )

    assert any("title native" in error for error in errors)


def test_horizontal_overflow_is_an_error():
    errors = visual._validate_manifest(
        _manifest(metrics=_metrics(scrollWidth=520, innerWidth=440))
    )

    assert any("tràn ngang" in error for error in errors)


def test_a_button_smaller_than_the_touch_target_is_an_error():
    errors = visual._validate_manifest(
        _manifest(metrics=_metrics(tinyButtons=["icon-button"]))
    )

    assert any("nhỏ hơn 22px" in error for error in errors)


def test_a_capture_without_metrics_still_reports_every_rule():
    errors = visual._validate_manifest(
        {"theme": "light", "dpi": 150, "expectedDpr": 1.5}
    )

    assert any("DPR" in error for error in errors)
    assert any("theme" in error for error in errors)


# --- báo cáo so sánh ------------------------------------------------------


def _suite(output: Path, *, difference=False) -> None:
    for theme in visual.THEMES:
        for dpi, factor in visual.DPI_FACTORS.items():
            manifest = {
                "theme": theme,
                "dpi": dpi,
                "expectedDpr": factor,
                "metrics": _metrics(dpr=factor, theme=theme),
            }
            (output / "current").mkdir(parents=True, exist_ok=True)
            (output / "baseline").mkdir(parents=True, exist_ok=True)
            (output / "current" / f"{theme}-{dpi}.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            for state in visual.STATES:
                name = f"panel-{theme}-{dpi}-{state}.png"
                _image(output / "baseline" / name)
                _image(
                    output / "current" / name,
                    colour=(0, 0, 0) if difference else (255, 255, 255),
                )


def test_an_identical_suite_reports_ok_and_writes_the_report(tmp_path):
    _suite(tmp_path)

    report = visual._compare(tmp_path, 0.002)

    assert report["ok"] is True
    assert report["errors"] == []
    assert len(report["comparisons"]) == len(visual.THEMES) * len(
        visual.DPI_FACTORS
    ) * len(visual.STATES)
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["ok"]


def test_a_changed_capture_fails_the_comparison(tmp_path):
    _suite(tmp_path, difference=True)

    report = visual._compare(tmp_path, 0.002)

    assert report["ok"] is False
    assert all("sai khác" in error for error in report["errors"])


def test_a_generous_tolerance_accepts_the_same_change(tmp_path):
    _suite(tmp_path, difference=True)

    assert visual._compare(tmp_path, 1.0)["ok"] is True


# --- CLI ------------------------------------------------------------------


def _run_visual(monkeypatch, argv) -> int:
    monkeypatch.setattr(sys, "argv", ["visual_regression_panel.py", *argv])
    return visual.main()


def test_the_visual_cli_needs_a_suite_or_compare(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_visual(monkeypatch, ["--output", str(tmp_path)])


def test_capture_one_needs_theme_dpi_and_suite(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_visual(
            monkeypatch, ["--capture-one", "--output", str(tmp_path)]
        )


def test_the_visual_cli_returns_zero_for_a_clean_comparison(
    monkeypatch, tmp_path, capsys
):
    _suite(tmp_path)

    assert _run_visual(monkeypatch, ["--compare", "--output", str(tmp_path)]) == 0
    assert '"ok": true' in capsys.readouterr().out


def test_the_visual_cli_returns_one_when_something_changed(
    monkeypatch, tmp_path
):
    _suite(tmp_path, difference=True)

    assert _run_visual(monkeypatch, ["--compare", "--output", str(tmp_path)]) == 1


def test_running_a_suite_spawns_one_child_per_theme_and_dpi(
    monkeypatch, tmp_path
):
    commands: list[list[str]] = []
    monkeypatch.setattr(
        visual.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(list(command)),
    )

    assert _run_visual(monkeypatch, ["--suite", "baseline", "--output", str(tmp_path)]) == 0
    assert len(commands) == len(visual.THEMES) * len(visual.DPI_FACTORS)
    assert all("--capture-one" in command for command in commands)


# --- trạng thái panel dùng khi chụp --------------------------------------


@pytest.mark.parametrize("theme", visual.THEMES)
def test_the_visual_state_declares_the_theme_it_captures(theme):
    state = visual._visual_state(theme)

    assert state["theme"] == theme
    assert state["version"] == "visual-test"
    assert state["user_id"] == "VISUAL.TEST"


def test_the_visual_api_answers_every_bridge_call_the_panel_makes():
    state = visual._visual_state("light")
    api = visual._VisualAPI(state)

    assert api.get_initial_state() is state
    assert api.set_panel_pointer_inside(True) == {"ok": True}
    assert api.request_panel_hide() == {"ok": True}
    assert api.set_theme("dark") == {"ok": True}
