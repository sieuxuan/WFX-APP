"""Sinh nội dung GitHub Release từ chính `wfx_panel/manual/whats_new.json`.

Trước đây phần `body` nằm cứng trong `.github/workflows/release.yml`, nên mọi
bản phát hành sau đều mang ghi chú của bản cũ cho tới khi có người nhớ sửa
workflow. Nguồn sự thật duy nhất phải là mục "Có gì mới" mà chính ứng dụng hiển
thị sau khi tự cập nhật — nếu hai nơi lệch nhau thì người dùng đọc được hai
danh sách tính năng khác nhau cho cùng một phiên bản.

Chạy: python scripts/release_notes.py > notes.md
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wfx_panel import manual_book  # noqa: E402
from wfx_panel.version import APP_VERSION  # noqa: E402

LEGACY_NOTES = (
    "**Nếu đang dùng 1.0.8 trở xuống:** hãy cài thủ công một lần theo ba bước "
    "trên. Gói mới cố ý không kích hoạt updater cũ để tránh nguy cơ updater đó "
    "xóa nhầm thư mục chứa ứng dụng.\n"
    "\n"
    "**Nếu bản 1.0.9–1.0.11 báo lỗi CMS hoặc hash:** hãy cài thủ công một lần. "
    "Từ 1.0.12 trở đi, updater tương thích cả Windows PowerShell 5.1 và "
    "PowerShell 7, đồng thời vẫn xác minh chữ ký, giới hạn file được thay và có "
    "rollback."
)


def release_highlights(version: str, releases: list[dict]) -> list[dict]:
    """Các mục "Có gì mới" của đúng phiên bản sắp phát hành."""
    for release in releases:
        if str(release.get("version") or "") == version:
            return list(release.get("highlights") or [])
    raise SystemExit(
        f"whats_new.json chưa có mục cho phiên bản {version}. "
        "Thêm mục đó trước khi phát hành."
    )


def build_release_notes(
    version: str,
    releases: list[dict],
    *,
    setup_name: str,
    zip_name: str,
) -> str:
    highlights = release_highlights(version, releases)
    if not highlights:
        raise SystemExit(f"Mục {version} trong whats_new.json không có nội dung.")

    lines = [f"## Có gì mới trong {version}", ""]
    for item in highlights:
        title = str(item.get("title") or "").strip()
        body = " ".join(str(item.get("body") or "").split())
        lines.append(f"- **{title}** — {body}" if body else f"- **{title}**")
    lines.extend(
        [
            "",
            "## Cách cài",
            "",
            f"1. Tải **{setup_name}** và mở file.",
            "2. Bộ cài tự đóng đúng WFX Smart đang chạy, nâng cấp tại chỗ và",
            "   tạo shortcut ngoài Desktop.",
            "3. Tài khoản, Settings và dữ liệu làm việc được giữ nguyên.",
            "",
            f"Bản portable: tải **{zip_name}**, giải nén vào một thư mục riêng",
            "rồi mở **WFX-Panel.exe**.",
            "",
            LEGACY_NOTES,
            "",
            "File `.sha256` và chữ ký `.p7s` xác minh gói tải về đúng từ nhà "
            "phát hành.",
        ]
    )
    return "\n".join(lines) + "\n"


def _use_utf8_console() -> None:
    """Runner Windows chạy Python 3.12 với locale cp1252.

    Ghi chú phát hành và mọi thông điệp lỗi ở đây đều là tiếng Việt; in thẳng
    ra stdout/stderr đã bị chuyển hướng sẽ ném UnicodeEncodeError và làm hỏng
    cả bước phát hành vì một lý do không liên quan tới nội dung.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _use_utf8_console()
    version = APP_VERSION
    notes = build_release_notes(
        version,
        manual_book.load_whats_new(),
        setup_name=f"WFX-Smart-Setup-v{version}.exe",
        zip_name=f"WFX-Smart-v{version}-win64.zip",
    )
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if target is None:
        sys.stdout.write(notes)
    else:
        target.write_text(notes, encoding="utf-8")
        print(f"Đã ghi ghi chú phát hành {version} vào {target}")


if __name__ == "__main__":
    main()
