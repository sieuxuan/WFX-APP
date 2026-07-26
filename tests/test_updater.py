from wfx_panel import updater


def release_payload(version: str = "1.1.0") -> dict:
    package = f"WFX-Panel-v{version}-win64.zip"
    base = f"https://github.com/sieuxuan/WFX-APP/releases/download/v{version}"
    return {
        "id": 110,
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/sieuxuan/WFX-APP/releases/tag/v{version}",
        "assets": [
            {
                "name": package,
                "browser_download_url": f"{base}/{package}",
            },
            {
                "name": package + ".sha256",
                "browser_download_url": f"{base}/{package}.sha256",
            },
        ],
    }


def test_check_for_updates_reports_release_in_plain_language(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_load_latest_release",
        lambda: release_payload("1.1.0"),
    )

    result = updater.check_for_updates()

    assert result["code"] == "UPDATE_AVAILABLE"
    assert result["can_update"] is True
    assert result["version"] == "1.1.0"
    assert result["notice_id"] == "110"
    assert "Phiên bản 1.1.0" in result["message"]
    assert "commit" not in result["message"].lower()
    assert result["package_url"].endswith("WFX-Panel-v1.1.0-win64.zip")
    assert result["checksum_url"].endswith(".zip.sha256")


def test_current_release_is_up_to_date(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_load_latest_release",
        lambda: release_payload("1.0.0"),
    )

    result = updater.check_for_updates()

    assert result["code"] == "UP_TO_DATE"
    assert result["can_update"] is False
    assert result["version"] == "1.0.0"
    assert result["message"] == "Bạn đang dùng phiên bản mới nhất."


def test_release_without_checksum_is_not_offered(monkeypatch):
    payload = release_payload("1.1.0")
    payload["assets"].pop()
    monkeypatch.setattr(updater, "_load_latest_release", lambda: payload)

    result = updater.check_for_updates()

    assert result["code"] == "UPDATE_CHECK_FAILED"
    assert result["can_update"] is False
    assert "tự thử lại" in result["message"]


def test_schedule_update_downloads_verifies_and_rolls_back(
    monkeypatch, tmp_path
):
    local_data = tmp_path / "local"
    install_dir = tmp_path / "WFX-Panel"
    install_dir.mkdir()
    executable = install_dir / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    launched = []
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda args, **kwargs: launched.append((args, kwargs)),
    )
    state = {
        "can_update": True,
        "version": "1.1.0",
        "package_url": (
            "https://github.com/sieuxuan/WFX-APP/releases/download/"
            "v1.1.0/WFX-Panel-v1.1.0-win64.zip"
        ),
        "checksum_url": (
            "https://github.com/sieuxuan/WFX-APP/releases/download/"
            "v1.1.0/WFX-Panel-v1.1.0-win64.zip.sha256"
        ),
    }

    helper = updater.schedule_update(
        state,
        current_pid=123,
        executable=executable,
    )
    content = helper.read_text(encoding="utf-8-sig")

    assert "DownloadFile" in content
    assert "Get-FileHash" in content
    assert "Expand-Archive" in content
    assert "UPDATE_INSTALLED" in content
    assert "UPDATE_ROLLED_BACK" in content
    assert "Start-Process -FilePath $targetExe" in content
    assert "git " not in content.lower()
    assert launched


def test_consume_update_result_is_one_shot(tmp_path):
    path = tmp_path / "update-result.json"
    path.write_text(
        '{"ok": true, "code": "UPDATE_INSTALLED"}',
        encoding="utf-8",
    )
    result = updater.consume_update_result(tmp_path)
    assert result["code"] == "UPDATE_INSTALLED"
    assert updater.consume_update_result(tmp_path) is None


def test_version_comparison_accepts_display_and_release_forms():
    assert updater._version_tuple("v1.2.3") == (1, 2, 3)
    assert updater._version_tuple("1.2") == (1, 2, 0)
