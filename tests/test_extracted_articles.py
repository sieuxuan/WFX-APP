"""Kết quả "Lấy Article từ WFX" thay thư viện Article rồi publish lên n8n.

Đây là dữ liệu dùng chung của mọi máy: một lượt lấy thiếu Category hoặc lấy
bằng tài khoản nhìn được ít Catalog mà vẫn publish là xóa Article của người
khác. Test canh hai chốt chặn đó cùng đường publish thật của reference_sync.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from tests.test_panel_api import make_api
from wfx_panel import constants
from wfx_panel.automation.catalog.article_partition import articles_csv
from wfx_panel.stores import (
    article_library,
    extracted_articles,
    reference_sync,
    style_options,
)

ALL = tuple(constants.CATEGORIES)


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _maximum):
        return self.payload


def _configure(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "sync-config.json"
    config.write_text(
        json.dumps(
            {
                "read_key": "read-key",
                "read_url": "https://example.test/latest",
                "publish_url": "https://example.test/publish",
                "company_id": "77400",
                "division_key": "01",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(reference_sync, "_private_config_paths", lambda _b: (config,))


def _seed(tmp_path: Path, article_count: int) -> None:
    article_library.save_server_articles(
        tmp_path,
        [
            {
                "article_code": f"OLD{n:05d}",
                "article_name": f"Old {n}",
                "buyer_reference": "",
                "article_category": "Apparel",
            }
            for n in range(article_count)
        ],
        version="old",
    )
    style_options.save_snapshot(
        tmp_path,
        {
            "generated_at": time.time() - 100,
            "source": "test",
            "company_id": "77400",
            "division_key": "01",
            "fields": {
                "material_type": ["KNIT"],
                "buyer": ["Buyer A"],
                "division": ["Division A"],
                "product_group": ["TEE"],
                "color_card": ["Card A"],
                "size_range": ["S-XL"],
                "season": ["SS26"],
            },
            "subcategories_by_product_group": {"TEE": ["T-SHIRT"]},
        },
    )


def _extracted_csv(tmp_path: Path, apparel: int = 9, trims: int = 3) -> Path:
    path = tmp_path / "exports" / "article-list.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "﻿"
        + articles_csv(
            {
                "Apparel": [
                    {"code": f"SWV{n:07d}", "name": f"Style {n}", "buyer_reference": "JL"}
                    for n in range(apparel)
                ],
                "Trims": [{"code": f"T{n:07d}", "name": "Zip"} for n in range(trims)],
            }
        ),
        encoding="utf-8",
    )
    return path


def _capture_publish(monkeypatch) -> dict:
    captured: dict = {}

    def open_request(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response({"ok": True, "version": "v-new", "counts": {"articles": 12}})

    monkeypatch.setattr(reference_sync, "urlopen", open_request)
    return captured


def test_the_extract_replaces_the_library_and_is_published_with_categories(
    tmp_path, monkeypatch
):
    _configure(tmp_path, monkeypatch)
    _seed(tmp_path, 10)
    monkeypatch.setenv("WFX_SYNC_ADMIN_KEY", "admin-key")
    captured = _capture_publish(monkeypatch)

    result = extracted_articles.install_and_publish(
        tmp_path,
        _extracted_csv(tmp_path),
        extracted_categories=ALL,
        all_categories=ALL,
        log=lambda _line: None,
    )

    assert result["ok"] is True
    assert result["code"] == "REFERENCE_SYNC_PUBLISHED"
    assert result["previous_article_count"] == 10
    assert result["library_article_count"] == 12
    sent = captured["body"]["articles"]
    assert len(sent) == 12
    assert {row["article_category"] for row in sent} == {"Apparel", "Trims"}
    assert not any(row["article_code"].startswith("OLD") for row in sent)


def test_a_partial_extract_never_touches_the_library(tmp_path, monkeypatch):
    _seed(tmp_path, 10)
    monkeypatch.setattr(reference_sync, "urlopen", lambda *_a, **_k: 1 / 0)

    result = extracted_articles.install_and_publish(
        tmp_path,
        _extracted_csv(tmp_path),
        extracted_categories=("Apparel", "Trims"),
        all_categories=ALL,
    )

    assert result["code"] == "ARTICLE_LIBRARY_PARTIAL_EXTRACT"
    assert article_library.status(tmp_path)["article_count"] == 10


def test_a_much_smaller_extract_is_blocked_before_publishing(tmp_path, monkeypatch):
    _seed(tmp_path, 100)
    monkeypatch.setattr(reference_sync, "urlopen", lambda *_a, **_k: 1 / 0)

    result = extracted_articles.install_and_publish(
        tmp_path,
        _extracted_csv(tmp_path, apparel=50, trims=10),
        extracted_categories=ALL,
        all_categories=ALL,
        log=lambda _line: None,
    )

    assert result["code"] == "ARTICLE_LIBRARY_SHRINK_BLOCKED"
    assert article_library.status(tmp_path)["article_count"] == 100


def test_the_shrink_guard_allows_normal_churn():
    assert extracted_articles.shrink_guard(15_590, 15_829) is None
    assert extracted_articles.shrink_guard(5, 0) is None
    assert extracted_articles.shrink_guard(80, 100)


def test_without_an_admin_key_the_library_is_updated_but_not_published(
    tmp_path, monkeypatch
):
    _configure(tmp_path, monkeypatch)
    _seed(tmp_path, 10)
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    monkeypatch.setattr(reference_sync.prefs, "load_sync_admin_key", lambda **_k: "")

    result = extracted_articles.install_and_publish(
        tmp_path,
        _extracted_csv(tmp_path),
        extracted_categories=ALL,
        all_categories=ALL,
        log=lambda _line: None,
    )

    assert result["ok"] is False
    assert result["code"] == "REFERENCE_ADMIN_KEY_REQUIRED"
    assert "chưa publish" in result["message"]
    assert article_library.status(tmp_path)["article_count"] == 12


def test_publish_can_be_skipped(tmp_path, monkeypatch):
    _seed(tmp_path, 10)
    monkeypatch.setattr(reference_sync, "urlopen", lambda *_a, **_k: 1 / 0)

    result = extracted_articles.install_and_publish(
        tmp_path,
        _extracted_csv(tmp_path),
        extracted_categories=ALL,
        all_categories=ALL,
        publish=False,
        log=lambda _line: None,
    )

    assert result["code"] == "ARTICLE_LIBRARY_UPDATED"


def test_reading_the_extract_csv_keeps_every_column(tmp_path):
    rows = extracted_articles.read_articles_csv(_extracted_csv(tmp_path, 1, 1))

    assert rows == [
        {
            "article_code": "SWV0000000",
            "article_name": "Style 0",
            "buyer_reference": "JL",
            "article_category": "Apparel",
        },
        {
            "article_code": "T0000000",
            "article_name": "Zip",
            "buyer_reference": "",
            "article_category": "Trims",
        },
    ]
    with open(_extracted_csv(tmp_path, 1, 1), encoding="utf-8-sig") as handle:
        assert next(csv.reader(handle))[0] == "Article_Code"


# --- controller -------------------------------------------------------------


def test_the_controller_installs_and_publishes_after_a_full_extract(
    tmp_path, monkeypatch
):
    api, fake = make_api(tmp_path)
    api._admin_access = True
    csv_path = _extracted_csv(tmp_path)
    fake.extract_catalog_articles = lambda categories, output_dir, log, *, app_version: {
        "ok": True,
        "code": "CATALOG_ARTICLES_EXTRACTED",
        "message": "Đã lấy 12 Article",
        "file_path": str(csv_path),
        "categories": {name: {} for name in categories},
    }
    seen = {}

    def install(base_dir, path, **kwargs):
        seen.update(path=path, **kwargs)
        return {"ok": True, "code": "REFERENCE_SYNC_PUBLISHED", "message": "đã publish"}

    monkeypatch.setattr(extracted_articles, "install_and_publish", install)

    result = api.extract_catalog_articles([], True)

    assert result["code"] == "REFERENCE_SYNC_PUBLISHED"
    assert result["file_path"] == str(csv_path)
    assert result["extract_message"] == "Đã lấy 12 Article"
    assert seen["publish"] is True
    assert set(seen["extracted_categories"]) == set(ALL)


def test_a_failed_extract_is_returned_without_installing(tmp_path, monkeypatch):
    api, fake = make_api(tmp_path)
    api._admin_access = True
    fake.extract_catalog_articles = lambda *_a, **_k: {
        "ok": False,
        "code": "CATALOG_ARTICLES_PARTIAL",
        "message": "thiếu",
    }
    monkeypatch.setattr(
        extracted_articles, "install_and_publish", lambda *_a, **_k: 1 / 0
    )

    assert api.extract_catalog_articles([])["code"] == "CATALOG_ARTICLES_PARTIAL"
