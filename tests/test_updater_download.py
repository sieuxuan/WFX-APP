"""Hàm tải của updater chạy thật trên PowerShell và một máy chủ HTTP cục bộ.

Đây là phần chờ lâu nhất của cả lượt cập nhật. Trước đây nó dùng
`DownloadFileTaskAsync` + thanh marquee, nên người dùng không biết còn bao lâu;
và không test nào chạy chính đoạn PowerShell đó. File này tải thật qua hàm sinh
ra trong helper, kiểm byte + SHA-256 và khẳng định tiến trình là phần trăm thật.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_updater import update_state
from wfx_panel import updater

pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None,
    reason="Cần Windows PowerShell để chạy đúng shell mà updater dùng",
)


def _helper_content(tmp_path, monkeypatch):
    """Sinh helper thật rồi trả nội dung, không chạy nó."""
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "WFX-Panel.exe").write_bytes(b"old")
    (install_dir / "_internal").mkdir()
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    # Chỉ chặn đúng lúc `schedule_update` khởi chạy helper, rồi trả Popen thật
    # ngay: chính test này dùng `subprocess.run` để chạy PowerShell sau đó.
    real_popen = updater.subprocess.Popen
    updater.subprocess.Popen = lambda *_a, **_k: type("P", (), {})()
    try:
        helper = updater.schedule_update(
            update_state(version="9.9.9"),
            executable=install_dir / "WFX-Panel.exe",
        )
    finally:
        updater.subprocess.Popen = real_popen
    return helper.read_text(encoding="utf-8")


def _download_function(content):
    start = content.index("function Download-WithUi(")
    end = content.index("function Import-CmsAssembly")
    return content[start:end]


@pytest.fixture
def served(tmp_path):
    """Máy chủ HTTP cục bộ phục vụ một gói vài MB như GitHub Release."""
    root = tmp_path / "serve"
    root.mkdir()
    payload = os.urandom(3 * 1024 * 1024)
    (root / "goi.bin").write_bytes(payload)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/goi.bin", payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_download(tmp_path, content, url, target, extra=""):
    harness = tmp_path / "download-harness.ps1"
    harness.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "$script:paints = @()",
                "function Update-UI([string]$text, [int]$percent = -1, "
                "[string]$tone = 'info') {",
                "  $script:paints += \"$percent|$text\"",
                "}",
                _download_function(content),
                extra,
                "Download-WithUi $args[0] $args[1] 'Dang tai:' 10 40",
                "$script:paints | ForEach-Object { Write-Output \"PAINT=$_\" }",
            ]
        ),
        encoding="utf-8-sig",
    )
    process = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
            url,
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return process


def test_the_package_is_downloaded_byte_for_byte(tmp_path, monkeypatch, served):
    url, payload = served
    content = _helper_content(tmp_path, monkeypatch)
    target = tmp_path / "goi-tai-ve.bin"

    process = _run_download(tmp_path, content, url, target)

    assert process.returncode == 0, process.stderr or process.stdout
    assert target.read_bytes() == payload
    assert (
        hashlib.sha256(target.read_bytes()).hexdigest()
        == hashlib.sha256(payload).hexdigest()
    )


def test_the_user_sees_a_real_percentage_and_size_not_a_marquee(
    tmp_path, monkeypatch, served
):
    url, _payload = served
    content = _helper_content(tmp_path, monkeypatch)

    process = _run_download(tmp_path, content, url, tmp_path / "goi.bin")

    paints = [
        line.removeprefix("PAINT=")
        for line in process.stdout.splitlines()
        if line.startswith("PAINT=")
    ]
    assert paints, process.stderr or process.stdout
    percents = [int(line.split("|", 1)[0]) for line in paints]
    # Marquee là -1; tiến trình thật nằm trong đúng khoảng được cấp.
    assert all(10 <= percent <= 40 for percent in percents), paints
    assert percents[-1] == 40
    assert all("MB" in line for line in paints), paints


def test_a_download_that_stops_short_is_refused_not_saved_as_valid(
    tmp_path, monkeypatch, served
):
    """Content-Length nói một đằng, dữ liệu về một nẻo thì phải là lỗi."""
    url, _payload = served
    content = _helper_content(tmp_path, monkeypatch)

    process = _run_download(
        tmp_path,
        # Ép Content-Length lớn hơn thực tế để mô phỏng kết nối đứt giữa chừng.
        content.replace(
            "$total = [int64]$response.ContentLength",
            "$total = [int64]$response.ContentLength + 1024",
        ),
        url,
        tmp_path / "goi.bin",
    )

    assert process.returncode != 0
    # Console PowerShell bóp dấu tiếng Việt, nên khẳng định theo số byte — đó
    # mới là bằng chứng chính hàm này phát hiện thiếu dữ liệu.
    assert re.search(r"\d+/\d+ byte", process.stderr + process.stdout), (
        process.stderr or process.stdout
    )


def test_a_missing_file_on_the_server_fails_loudly(
    tmp_path, monkeypatch, served
):
    url, _payload = served
    content = _helper_content(tmp_path, monkeypatch)

    process = _run_download(
        tmp_path, content, url.replace("goi.bin", "khong-co.bin"), tmp_path / "x.bin"
    )

    assert process.returncode != 0
    assert not (tmp_path / "x.bin").exists()
