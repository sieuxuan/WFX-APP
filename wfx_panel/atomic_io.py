"""Ghi file nguyên tử dùng chung cho mọi state lưu trên đĩa của app.

Trước đây mỗi module tự viết lại cùng một đoạn write-temp-rồi-replace, với năm
cách đặt tên temp khác nhau (``prefs.json.tmp``, ``jobs.tmp``,
``telemetry-outbox.json.tmp``, ``Preferences.tmp``). Sự phân tán đó chính là lý
do một biến thể dùng tên ``.tmp`` cố định KHÔNG có khoá tồn tại lâu mà không ai
thấy: hai thread cùng ghi thì bên replace() sau gặp FileNotFoundError/
PermissionError vì temp đã bị bên kia move đi.

Ở đây temp luôn mang pid + thread id nên hai người ghi song song không bao giờ
đụng nhau, và ``os.replace`` bảo đảm người đọc chỉ thấy nội dung cũ hoặc mới
nguyên vẹn, không bao giờ thấy file ghi dở.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


def write_text_atomic(path: Path | str, content: str) -> None:
    """Thay thế nội dung ``path`` nguyên tử."""
    target = Path(path)
    temp = target.with_name(
        f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(target)
    finally:
        # replace() thành công thì temp đã biến mất; chỉ dọn khi ghi lỗi giữa
        # đường để không để lại rác .tmp trong thư mục dữ liệu người dùng.
        try:
            temp.unlink()
        except OSError:
            pass


def write_json_atomic(
    path: Path | str,
    payload: Any,
    *,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
) -> None:
    """Như :func:`write_text_atomic` nhưng nhận thẳng payload JSON."""
    write_text_atomic(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
        ),
    )
