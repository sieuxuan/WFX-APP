"""Đưa kết quả "Lấy Article từ WFX" vào Article Library rồi publish lên n8n.

Trước đây Admin phải tự xuất ``Article List.csv`` từ WFX, chép vào cache rồi bấm
publish. Giờ extractor đọc thẳng WFX ra CSV cùng định dạng; module này thay cache
Article Library bằng file đó và gọi đúng luồng publish sẵn có của
``reference_sync`` (cùng admin key, cùng schema PostgreSQL, kèm Category).

Python thuần, không chạm Playwright: chạy NGOÀI ``_run()`` vì chỉ là IO + HTTP.

Hai chốt an toàn trước khi thay dữ liệu dùng chung của mọi máy:

* chỉ nhận lượt lấy đủ mọi Category — lượt lấy một phần sẽ xóa sạch Category
  còn lại khỏi thư viện;
* số Article mới không được tụt quá ``MIN_KEEP_RATIO`` so với thư viện đang có.
  Tài khoản/Division nhìn được ít Catalog hơn sẽ trả ít Article hơn hẳn, và
  publish kết quả đó là xóa Article của người khác trên mọi máy.
"""

from __future__ import annotations

import csv
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from wfx_panel.stores import article_library, reference_sync

MIN_KEEP_RATIO = 0.9


def read_articles_csv(path: Path | str) -> list[dict[str, str]]:
    """CSV do extractor ghi (header giống ``Article List.csv``)."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return [
            {
                "article_code": str(row.get("Article_Code") or "").strip(),
                "article_name": str(row.get("Article_Name") or "").strip(),
                "buyer_reference": str(row.get("Buyer_Reference") or "").strip(),
                "article_category": str(row.get("Article_Category") or "").strip(),
            }
            for row in csv.DictReader(handle)
            if str(row.get("Article_Code") or "").strip()
        ]


def shrink_guard(new_count: int, current_count: int) -> str | None:
    """Thông điệp chặn khi thư viện mới tụt quá ngưỡng; ``None`` là an toàn."""
    if current_count <= 0 or new_count >= current_count * MIN_KEEP_RATIO:
        return None
    return (
        f"WFX chỉ trả {new_count} Article, ít hơn nhiều so với {current_count} "
        "Article đang có. Kiểm tra lại tài khoản/Division rồi lấy lại; thư viện "
        "chưa bị thay."
    )


def install_and_publish(
    base_dir: Path,
    csv_path: Path | str,
    *,
    extracted_categories: Iterable[str],
    all_categories: Iterable[str],
    publish: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    missing = sorted(set(all_categories) - set(extracted_categories))
    if missing:
        return {
            "ok": False,
            "code": "ARTICLE_LIBRARY_PARTIAL_EXTRACT",
            "message": (
                "Chỉ thay thư viện Article khi lấy đủ mọi Category; còn thiếu: "
                + ", ".join(missing)
                + "."
            ),
        }
    try:
        articles = read_articles_csv(csv_path)
    except (OSError, UnicodeError, csv.Error) as error:
        return {
            "ok": False,
            "code": "ARTICLE_LIBRARY_INSTALL_FAILED",
            "message": f"Không đọc được file Article vừa lấy ({type(error).__name__}).",
        }
    current = int(article_library.status(base_dir).get("article_count") or 0)
    blocked = shrink_guard(len(articles), current)
    if blocked:
        log(f"[ARTICLE LIBRARY] {blocked}")
        return {"ok": False, "code": "ARTICLE_LIBRARY_SHRINK_BLOCKED", "message": blocked}

    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        library = article_library.save_server_articles(
            base_dir,
            articles,
            version=f"wfx-extract-{time.strftime('%Y%m%d-%H%M%S')}",
            generated_at=stamp,
        )
    except (OSError, ValueError) as error:
        return {
            "ok": False,
            "code": "ARTICLE_LIBRARY_INSTALL_FAILED",
            "message": f"Không ghi được thư viện Article ({type(error).__name__}).",
        }
    log(
        f"[ARTICLE LIBRARY] Đã thay thư viện trên máy: {current} → "
        f"{library.get('article_count')} Article."
    )
    installed = {
        "library_article_count": int(library.get("article_count") or 0),
        "previous_article_count": current,
    }
    if not publish:
        return {
            "ok": True,
            "code": "ARTICLE_LIBRARY_UPDATED",
            "message": f"Đã cập nhật thư viện Article trên máy ({len(articles)} Article).",
            **installed,
        }

    published = reference_sync.publish_current(base_dir, log)
    if published.get("ok"):
        return {
            **published,
            **installed,
            "message": (
                f"Đã lấy {len(articles)} Article từ WFX và publish lên server."
            ),
        }
    reason = str(published.get("message") or "Publish thất bại.")
    return {
        **published,
        **installed,
        "ok": False,
        "message": f"Đã cập nhật thư viện trên máy nhưng chưa publish: {reason}",
    }
