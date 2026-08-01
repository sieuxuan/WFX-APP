import json
import time
from pathlib import Path

from wfx_panel import article_library, reference_sync, style_options


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
                "read_key": "read-only-test-key",
                "read_url": "https://example.test/latest",
                "publish_url": "https://example.test/publish",
                "company_id": "77400",
                "division_key": "01",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        reference_sync,
        "_private_config_paths",
        lambda _base_dir: (config,),
    )


def _seed_caches(tmp_path: Path) -> None:
    article_library.save_server_articles(
        tmp_path,
        [
            {
                "article_code": "SWN-1",
                "article_name": "Old",
                "buyer_reference": "BUY-1",
                "article_category": "Apparel",
            }
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
                "material_type": ["KNIT", "WOVEN"],
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


def test_user_sync_saves_article_and_style_caches(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _seed_caches(tmp_path)
    calls = []

    def open_request(request, timeout):
        calls.append((request.full_url, timeout, request.get_header("X-wfx-read-key")))
        return _Response(
            {
                "ok": True,
                "version": "v2",
                "published_at": "2026-08-02T00:00:00Z",
                "not_modified": False,
                "articles": [
                    {
                        "article_code": "SWN-1",
                        "article_name": "Updated",
                        "buyer_reference": "BUY-1",
                    },
                    {
                        "article_code": "SWN-2",
                        "article_name": "New",
                        "buyer_reference": "BUY-2",
                    },
                ],
                "style_options": [
                    {"field_name": "material_type", "option_value": "KNIT"},
                    {"field_name": "buyer", "option_value": "Buyer A"},
                    {"field_name": "division", "option_value": "Division A"},
                    {"field_name": "product_group", "option_value": "TEE"},
                    {"field_name": "color_card", "option_value": "Card A"},
                    {"field_name": "size_range", "option_value": "S-XL"},
                    {"field_name": "season", "option_value": "SS26"},
                ],
                "style_subcategories": [
                    {"product_group": "TEE", "sub_category": "T-SHIRT"}
                ],
            }
        )

    monkeypatch.setattr(reference_sync, "urlopen", open_request)
    result = reference_sync.sync_latest(tmp_path, lambda _line: None, force=True)

    assert result["ok"] is True
    assert result["article_count"] == 2
    assert result["style_option_count"] == 7
    assert result["version"] == "v2"
    assert calls[0][2] == "read-only-test-key"
    cached = article_library.load_cached(tmp_path)
    assert cached["sections"][0]["options"][0]["article_category"] == "Apparel"
    assert style_options.load_cached(tmp_path)["source"] == "postgresql"


def test_monthly_cache_skips_network_when_fresh(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _seed_caches(tmp_path)
    reference_sync._save_state(tmp_path, last_success=time.time(), version="v1")
    monkeypatch.setattr(
        reference_sync,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no network")),
    )
    result = reference_sync.sync_latest(tmp_path, lambda _line: None)
    assert result["code"] == "REFERENCE_SYNC_CURRENT"


def test_admin_publish_uses_current_cache(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _seed_caches(tmp_path)
    monkeypatch.setenv("WFX_SYNC_ADMIN_KEY", "admin-test-key")
    captured = {}

    def open_request(request, timeout):
        captured["key"] = request.get_header("X-wfx-admin-key")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "ok": True,
                "version": "published-v2",
                "counts": {
                    "articles": 1,
                    "style_options": 8,
                    "style_subcategories": 1,
                },
            }
        )

    monkeypatch.setattr(reference_sync, "urlopen", open_request)
    result = reference_sync.publish_current(tmp_path, lambda _line: None)

    assert result["ok"] is True
    assert result["version"] == "published-v2"
    assert captured["key"] == "admin-test-key"
    assert len(captured["body"]["articles"]) == 1
    assert captured["body"]["company_id"] == "77400"
