"""Ghi chú phát hành phải sinh từ đúng mục "Có gì mới" của phiên bản.

Trước đây `body` nằm cứng trong `.github/workflows/release.yml`, nên bản 1.0.37
vẫn phát hành kèm mô tả của một bản cũ hơn. Người dùng đọc GitHub Release và
đọc mục Có gì mới trong app phải thấy đúng một danh sách.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_notes  # noqa: E402

from wfx_panel import manual_book  # noqa: E402
from wfx_panel.version import APP_VERSION  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _notes(version=APP_VERSION, releases=None):
    return release_notes.build_release_notes(
        version,
        releases if releases is not None else manual_book.load_whats_new(),
        setup_name=f"WFX-Smart-Setup-v{version}.exe",
        zip_name=f"WFX-Smart-v{version}-win64.zip",
    )


def test_the_notes_list_every_highlight_of_this_release():
    highlights = release_notes.release_highlights(
        APP_VERSION, manual_book.load_whats_new()
    )
    notes = _notes()

    assert highlights, "Bản phát hành phải có ít nhất một mục Có gì mới."
    for item in highlights:
        assert item["title"] in notes


def test_the_notes_name_the_files_the_user_has_to_download():
    notes = _notes()

    assert f"WFX-Smart-Setup-v{APP_VERSION}.exe" in notes
    assert f"WFX-Smart-v{APP_VERSION}-win64.zip" in notes
    assert "`.sha256`" in notes


def test_a_version_without_a_whats_new_entry_stops_the_release():
    with pytest.raises(SystemExit, match="whats_new.json"):
        _notes("9.9.9")


def test_a_release_entry_with_no_content_stops_the_release():
    with pytest.raises(SystemExit, match="không có nội dung"):
        _notes("1.1.1", [{"version": "1.1.1", "highlights": []}])


def test_a_highlight_without_a_body_still_appears():
    notes = _notes(
        "1.1.1", [{"version": "1.1.1", "highlights": [{"title": "Chỉ có tiêu đề"}]}]
    )

    assert "**Chỉ có tiêu đề**" in notes


def test_the_notes_are_written_to_the_file_the_workflow_asks_for(tmp_path):
    target = tmp_path / "release-notes.md"

    release_notes.main.__globals__["sys"].argv = ["release_notes.py", str(target)]
    release_notes.main()

    assert APP_VERSION in target.read_text(encoding="utf-8")


def test_the_release_workflow_reads_the_generated_file_instead_of_fixed_text():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python scripts/release_notes.py release-notes.md" in workflow
    assert "body_path: release-notes.md" in workflow
    # `body:` cứng là đúng cái đã khiến ghi chú phát hành bị cũ.
    assert "\n          body: |" not in workflow


def test_the_script_runs_on_a_windows_console_that_is_not_utf8(tmp_path):
    """Runner Windows dùng locale cp1252; thông điệp tiếng Việt không được nổ."""
    import subprocess

    target = tmp_path / "release-notes.md"
    environment = {
        **os.environ,
        "PYTHONIOENCODING": "cp1252",
        "PYTHONUTF8": "0",
    }

    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "release_notes.py"), str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        cwd=ROOT,
        timeout=120,
    )

    assert process.returncode == 0, process.stderr or process.stdout
    assert APP_VERSION in target.read_text(encoding="utf-8")


def test_a_missing_whats_new_entry_fails_the_script_not_the_encoding(tmp_path):
    import subprocess

    environment = {
        **os.environ,
        "PYTHONIOENCODING": "cp1252",
        "PYTHONUTF8": "0",
    }
    script = (
        "import sys; sys.path.insert(0, 'scripts');"
        " import release_notes;"
        " release_notes._use_utf8_console();"
        " release_notes.release_highlights('9.9.9', [])"
    )

    process = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        cwd=ROOT,
        timeout=120,
    )

    assert process.returncode != 0
    assert "whats_new.json" in process.stderr
