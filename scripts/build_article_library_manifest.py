"""Tạo manifest server cho file Article Library CSV/XLSX bốn cột.

Ví dụ:
  python scripts/build_article_library_manifest.py "Article List.csv"

Sau đó publish file dữ liệu và ``data/article-library-manifest.json`` lên server.
Ứng dụng người dùng tự kiểm tra manifest mỗi giờ và chỉ tải khi version đổi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--data-url",
        default="",
        help="URL HTTPS tuyệt đối hoặc tương đối so với manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/article-library-manifest.json"),
    )
    parser.add_argument(
        "--version",
        default="",
        help="Version dữ liệu; mặc định là timestamp UTC.",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    data_format = source.suffix.casefold().removeprefix(".")
    if data_format not in {"csv", "xlsx"} or not source.is_file():
        parser.error("File nguồn phải là CSV hoặc XLSX đang tồn tại.")
    payload = source.read_bytes()
    version = args.version.strip() or datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    manifest = {
        "schema_version": 1,
        "version": version,
        "format": data_format,
        "data_url": args.data_url.strip() or source.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output} for {source.name} ({version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
