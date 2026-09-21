"""Tải file đính kèm Article theo từng chunk."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from wfx_panel.automation._common import (
    Any,
    Callable,
    Playwright,
    PlaywrightError,
    _first_line,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.catalog.files import _attachment_url
from wfx_panel.automation.runtime import _user_downloads_dir
from wfx_panel.automation.session import _session_is_active


def _safe_attachment_name(value: str) -> str:
    name = Path(str(value or "").replace("\\", "/")).name
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" .")
    if not name:
        name = "wfx-attachment"
    stem = Path(name).stem[:150].rstrip(" .")
    suffix = Path(name).suffix[:20]
    return (stem or "wfx-attachment") + suffix


def _available_download_path(directory: Path, file_name: str) -> Path:
    """Không ghi đè: file trùng tên được thêm ``(1)``, ``(2)``..."""
    wanted = directory / _safe_attachment_name(file_name)
    if not wanted.exists():
        return wanted
    for index in range(1, 10_000):
        candidate = wanted.with_name(
            f"{wanted.stem} ({index}){wanted.suffix}"
        )
        if not candidate.exists():
            return candidate
    raise OSError("Không tạo được tên file tải xuống không trùng.")


_DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024


_CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$",
    flags=re.IGNORECASE,
)


def _download_attachment_in_chunks(
    request: Any,
    download_url: str,
    target_handle: Any,
    log: Callable[[str], None],
    *,
    chunk_size: int = _DOWNLOAD_CHUNK_SIZE,
) -> int:
    """Tải file WFX theo Range để file lớn không timeout khi buffer một lần."""
    offset = 0
    total: int | None = None
    last_logged_percent = -1

    while total is None or offset < total:
        end = offset + chunk_size - 1
        if total is not None:
            end = min(end, total - 1)
        response = None
        try:
            response = request.get(
                download_url,
                headers={
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",
                    "Range": f"bytes={offset}-{end}",
                },
                timeout=60_000,
                fail_on_status_code=False,
            )
            status = int(response.status)
            body = response.body()

            # Server nhỏ/không hỗ trợ Range: vẫn chấp nhận response đầy đủ.
            if status == 200 and offset == 0:
                if not body:
                    raise RuntimeError("WFX trả về file rỗng.")
                target_handle.write(body)
                return len(body)

            if status != 206:
                raise RuntimeError(
                    f"WFX trả về HTTP {status} khi tải file."
                )
            match = _CONTENT_RANGE_RE.match(
                str(response.headers.get("content-range") or "").strip()
            )
            if match is None or match.group(3) == "*":
                raise RuntimeError(
                    "WFX không trả về Content-Range hợp lệ."
                )
            chunk_start = int(match.group(1))
            chunk_end = int(match.group(2))
            current_total = int(match.group(3))
            expected_size = chunk_end - chunk_start + 1
            if (
                chunk_start != offset
                or current_total <= 0
                or len(body) != expected_size
            ):
                raise RuntimeError(
                    "Dữ liệu file WFX trả về không đầy đủ."
                )
            if total is not None and total != current_total:
                raise RuntimeError(
                    "Kích thước file WFX thay đổi trong lúc tải."
                )
            total = current_total
            target_handle.write(body)
            offset += len(body)

            percent = min(100, int(offset * 100 / total))
            if percent == 100 or percent - last_logged_percent >= 20:
                _write_log(
                    log,
                    f"[ARTICLE FILE] Đã tải {percent}%...",
                )
                last_logged_percent = percent
        finally:
            if response is not None:
                try:
                    response.dispose()
                except PlaywrightError:
                    pass

    return offset


def download_catalog_file(
    file_info: dict[str, Any],
    log: Callable[[str], None] = print,
    download_dir: Path | None = None,
) -> dict[str, Any]:
    """Tải file bằng cookie của BrowserContext và lưu an toàn vào Downloads."""
    file_name = _safe_attachment_name(str(file_info.get("file_name") or ""))
    download_url = _attachment_url(
        {
            "href": str(file_info.get("download_url") or ""),
            "onclick": "",
        }
    )
    if not download_url:
        return _result(
            False,
            "CATALOG_FILE_URL_INVALID",
            "Đường dẫn file không hợp lệ hoặc không thuộc WFX.",
        )
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Trình duyệt làm việc chưa được mở.",
        )

    playwright: Playwright | None = None
    part_path: Path | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        _write_log(log, f"[ARTICLE FILE] Đang tải {file_name}...")
        target_dir = Path(download_dir or _user_downloads_dir())
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _available_download_path(target_dir, file_name)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.stem}-",
            suffix=".wfx-part",
            dir=target_dir,
            delete=False,
        ) as part:
            part_path = Path(part.name)
            file_size = _download_attachment_in_chunks(
                browser.contexts[0].request,
                download_url,
                part,
                log,
            )
        part_path.replace(target)
        part_path = None
        _write_log(log, f"[ARTICLE FILE] Đã lưu {target.name}.")
        return _result(
            True,
            "CATALOG_FILE_DOWNLOADED",
            f"Đã tải {target.name} vào thư mục Downloads.",
            file_name=target.name,
            download_path=str(target),
            file_size=file_size,
        )
    except OSError as exc:
        return _result(
            False,
            "CATALOG_FILE_SAVE_FAILED",
            f"Không lưu được file: {exc}",
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_FILE_DOWNLOAD_FAILED", message)
    finally:
        if part_path is not None:
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
        if playwright is not None:
            playwright.stop()
