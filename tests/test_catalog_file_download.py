"""Tải file đính kèm Article: tên file an toàn, Range, và không ghi đè.

CLAUDE.md: file phải lưu thẳng vào Windows Known Folder Downloads, và một lượt
tải hỏng không được để lại file nửa vời mang tên thật cho người dùng mở.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import wfx_panel.automation.catalog.downloads as downloads
from tests.fakes.module_reflection import patch_automation
from wfx_panel.automation._common import PlaywrightError

WFX_URL = "https://prosports.worldfashionexchange.com/Company/7/Doc/jacket.pdf"


class Response:
    def __init__(self, status=206, body=b"", content_range="", dispose_error=None):
        self.status = status
        self._body = body
        self.headers = {"content-range": content_range} if content_range else {}
        self.dispose_error = dispose_error
        self.disposed = False

    def body(self):
        return self._body

    def dispose(self):
        self.disposed = True
        if self.dispose_error is not None:
            raise self.dispose_error


class Request:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.ranges: list[str] = []

    def get(self, _url, headers=None, **_kwargs):
        self.ranges.append((headers or {}).get("Range", ""))
        return self.responses.pop(0)


def _chunks(tmp_path, request, **kwargs):
    target = tmp_path / "tai-ve.bin"
    with target.open("wb") as handle:
        size = downloads._download_attachment_in_chunks(
            request, WFX_URL, handle, lambda _line: None, **kwargs
        )
    return size, target


# --- tên file WFX trả về ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("jacket.pdf", "jacket.pdf"),
        (r"C:\Users\Admin\jacket.pdf", "jacket.pdf"),
        ("../../etc/passwd", "passwd"),
        ('bang:gia<2026>.xlsx', "bang_gia_2026_.xlsx"),
        ("", "wfx-attachment"),
        (None, "wfx-attachment"),
        ("   ...  ", "wfx-attachment"),
        ("a" * 200 + ".pdf", "a" * 150 + ".pdf"),
    ],
)
def test_a_file_name_from_wfx_can_never_escape_the_downloads_folder(
    raw, expected
):
    assert downloads._safe_attachment_name(raw) == expected


def test_a_name_that_is_only_an_extension_never_becomes_a_hidden_file():
    # `.pdf` mà giữ nguyên thì Explorer coi là file ẩn không đuôi: người dùng
    # bấm Tải xong lại không thấy gì trong thư mục Downloads.
    assert downloads._safe_attachment_name(".pdf") == "pdf"


# --- không ghi đè file đã có -------------------------------------------


def test_the_first_download_keeps_the_name_wfx_gave_it(tmp_path):
    assert downloads._available_download_path(tmp_path, "jacket.pdf") == (
        tmp_path / "jacket.pdf"
    )


def test_downloading_the_same_file_twice_never_overwrites_the_first(tmp_path):
    (tmp_path / "jacket.pdf").write_bytes(b"cu")
    (tmp_path / "jacket (1).pdf").write_bytes(b"cu")

    assert downloads._available_download_path(tmp_path, "jacket.pdf") == (
        tmp_path / "jacket (2).pdf"
    )


def test_a_folder_already_full_of_copies_reports_a_real_error(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(downloads.Path, "exists", lambda _self: True)

    with pytest.raises(OSError, match="không trùng"):
        downloads._available_download_path(tmp_path, "jacket.pdf")


# --- tải theo Range -----------------------------------------------------


def test_a_server_that_ignores_ranges_still_delivers_the_whole_file(tmp_path):
    request = Request(Response(status=200, body=b"0123456789"))

    size, target = _chunks(tmp_path, request)

    assert size == 10
    assert target.read_bytes() == b"0123456789"


def test_an_empty_file_is_reported_instead_of_being_saved_as_valid(tmp_path):
    request = Request(Response(status=200, body=b""))

    with pytest.raises(RuntimeError, match="file rỗng"):
        _chunks(tmp_path, request)


def test_a_session_that_expired_mid_download_is_reported_by_its_status(tmp_path):
    request = Request(Response(status=302))

    with pytest.raises(RuntimeError, match="HTTP 302"):
        _chunks(tmp_path, request)


@pytest.mark.parametrize(
    "content_range",
    ["", "bytes 0-3/*", "khong phai range"],
)
def test_a_range_header_wfx_did_not_send_properly_is_refused(
    tmp_path, content_range
):
    request = Request(
        Response(status=206, body=b"0123", content_range=content_range)
    )

    with pytest.raises(RuntimeError, match="Content-Range"):
        _chunks(tmp_path, request, chunk_size=4)


@pytest.mark.parametrize(
    ("body", "content_range"),
    [
        (b"012", "bytes 0-3/10"),
        (b"0123", "bytes 4-7/10"),
        (b"0123", "bytes 0-3/0"),
    ],
)
def test_a_chunk_that_does_not_match_its_header_is_refused(
    tmp_path, body, content_range
):
    request = Request(Response(status=206, body=body, content_range=content_range))

    with pytest.raises(RuntimeError, match="không đầy đủ"):
        _chunks(tmp_path, request, chunk_size=4)


def test_a_file_wfx_replaced_halfway_through_the_download_is_refused(tmp_path):
    request = Request(
        Response(status=206, body=b"0123", content_range="bytes 0-3/10"),
        Response(status=206, body=b"4567", content_range="bytes 4-7/99"),
    )

    with pytest.raises(RuntimeError, match="thay đổi trong lúc tải"):
        _chunks(tmp_path, request, chunk_size=4)


def test_progress_is_logged_without_flooding_the_technical_log(tmp_path):
    payload = bytes(range(100))
    request = Request(
        *[
            Response(
                status=206,
                body=payload[start : start + 10],
                content_range=f"bytes {start}-{start + 9}/100",
            )
            for start in range(0, 100, 10)
        ]
    )
    logged: list[str] = []
    target = tmp_path / "tai-ve.bin"
    with target.open("wb") as handle:
        downloads._download_attachment_in_chunks(
            request, WFX_URL, handle, logged.append, chunk_size=10
        )

    assert target.read_bytes() == payload
    assert [line for line in logged if "100%" in line]
    assert len(logged) <= 6


def test_a_response_that_cannot_be_released_does_not_fail_the_download(tmp_path):
    request = Request(
        Response(
            status=200,
            body=b"pdf",
            dispose_error=PlaywrightError("context đã đóng"),
        )
    )

    size, target = _chunks(tmp_path, request)

    assert size == 3
    assert target.read_bytes() == b"pdf"


# --- điểm vào ------------------------------------------------------------


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Nối các biên Playwright, để lại chỗ cho từng test thay đúng một mắt."""
    playwright = type("Playwright", (), {"stop": lambda self: None})()
    context = type("Context", (), {"request": object()})()
    browser = type("Browser", (), {"contexts": [context]})()

    patch_automation(monkeypatch, downloads, "_chrome_is_ready", lambda: True)
    patch_automation(
        monkeypatch,
        downloads,
        "sync_playwright",
        type(
            "Factory",
            (),
            {"__call__": lambda self: self, "start": lambda self: playwright},
        )(),
    )
    patch_automation(
        monkeypatch,
        downloads,
        "_connect_to_chrome",
        lambda _playwright: (browser, object()),
    )
    patch_automation(
        monkeypatch, downloads, "_attach_dialog_handler", lambda *_args: None
    )
    patch_automation(
        monkeypatch, downloads, "_session_is_active", lambda _page: True
    )
    patch_automation(
        monkeypatch, downloads, "_user_downloads_dir", lambda: tmp_path
    )
    return monkeypatch


def _download(tmp_path, **overrides):
    payload = {"file_name": "jacket.pdf", "download_url": WFX_URL}
    payload.update(overrides)
    return downloads.download_catalog_file(
        payload, lambda _line: None, download_dir=tmp_path
    )


@pytest.mark.parametrize(
    "url",
    ["", "https://example.com/jacket.pdf", "javascript:void(0)"],
)
def test_a_link_that_does_not_belong_to_wfx_is_never_fetched(tmp_path, url):
    result = _download(tmp_path, download_url=url)

    assert result["code"] == "CATALOG_FILE_URL_INVALID"


def test_a_closed_browser_is_reported_before_anything_is_written(
    tmp_path, monkeypatch
):
    patch_automation(monkeypatch, downloads, "_chrome_is_ready", lambda: False)

    assert _download(tmp_path)["code"] == "CHROME_CLOSED"


def test_an_expired_session_stops_the_download(tmp_path, wired):
    patch_automation(
        wired, downloads, "_session_is_active", lambda _page: False
    )

    assert _download(tmp_path)["code"] == "NOT_LOGGED_IN"


def test_a_finished_download_lands_in_the_downloads_folder(tmp_path, wired):
    def deliver(_request, _url, stream, _log):
        stream.write(b"pdf")
        return 3

    patch_automation(
        wired, downloads, "_download_attachment_in_chunks", deliver
    )

    result = _download(tmp_path)

    assert result["code"] == "CATALOG_FILE_DOWNLOADED"
    assert Path(result["download_path"]) == tmp_path / "jacket.pdf"
    assert Path(result["download_path"]).read_bytes() == b"pdf"
    assert not list(tmp_path.glob("*.wfx-part"))


def test_a_download_that_fails_leaves_no_half_written_file_behind(
    tmp_path, wired
):
    def fail(_request, _url, stream, _log):
        stream.write(b"mot nua")
        raise RuntimeError("WFX trả về HTTP 500 khi tải file.")

    patch_automation(wired, downloads, "_download_attachment_in_chunks", fail)

    result = _download(tmp_path)

    assert result["code"] == "CATALOG_FILE_DOWNLOAD_FAILED"
    assert "HTTP 500" in result["message"]
    assert list(tmp_path.iterdir()) == []


def test_a_disk_that_refuses_the_write_is_reported_as_a_save_problem(
    tmp_path, wired
):
    def refuse(_request, _url, _stream, _log):
        raise PermissionError("ổ đĩa chỉ đọc")

    patch_automation(wired, downloads, "_download_attachment_in_chunks", refuse)

    result = _download(tmp_path)

    assert result["code"] == "CATALOG_FILE_SAVE_FAILED"
    assert list(tmp_path.iterdir()) == []


def test_a_leftover_part_file_windows_will_not_release_is_not_fatal(
    tmp_path, wired
):
    def fail(_request, _url, _stream, _log):
        raise RuntimeError("mất kết nối")

    def refuse_unlink(self, **_kwargs):
        raise PermissionError("file đang bị khóa")

    patch_automation(wired, downloads, "_download_attachment_in_chunks", fail)
    wired.setattr(downloads.Path, "unlink", refuse_unlink)

    assert _download(tmp_path)["code"] == "CATALOG_FILE_DOWNLOAD_FAILED"
