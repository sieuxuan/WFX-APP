import json
import threading
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


def test_reference_state_invalid_timestamp_does_not_break_status(
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, monkeypatch)
    _seed_caches(tmp_path)
    (tmp_path / "reference-sync.json").write_text(
        json.dumps({"last_success": "invalid", "version": "v1"}),
        encoding="utf-8",
    )

    current = reference_sync.status(tmp_path)

    assert current["last_success"] == 0
    assert current["fresh"] is False


def test_manual_and_background_sync_cannot_write_bundle_concurrently(
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, monkeypatch)
    _seed_caches(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    first_result = []

    def request_json(_request):
        entered.set()
        assert release.wait(timeout=2)
        return {
            "ok": True,
            "version": "v2",
            "published_at": "2026-08-09T00:00:00Z",
            "articles": [
                {
                    "article_code": "SWN-2",
                    "article_name": "New",
                    "buyer_reference": "BUY-2",
                }
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

    monkeypatch.setattr(reference_sync, "_request_json", request_json)
    worker = threading.Thread(
        target=lambda: first_result.append(
            reference_sync.sync_latest(
                tmp_path,
                lambda _line: None,
                force=True,
            )
        )
    )
    worker.start()
    assert entered.wait(timeout=1)

    overlapping = reference_sync.sync_latest(
        tmp_path,
        lambda _line: None,
        force=True,
    )

    assert overlapping["code"] == "REFERENCE_SYNC_IN_PROGRESS"
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert first_result[0]["code"] == "REFERENCE_SYNC_UPDATED"
    assert reference_sync.status(tmp_path)["version"] == "v2"


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


def _plain_http_config(tmp_path: Path, monkeypatch, url: str) -> None:
    config = tmp_path / "sync-config.json"
    config.write_text(
        json.dumps(
            {
                "read_key": "read-only-test-key",
                "read_url": url,
                "publish_url": url,
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


def test_sync_refuses_a_non_https_server_before_sending_the_read_key(
    tmp_path,
    monkeypatch,
):
    """Read key nằm trong header nên không được rời máy qua kênh không mã hóa."""
    _plain_http_config(tmp_path, monkeypatch, "http://example.test/latest")
    _seed_caches(tmp_path)

    def refuse(*_args, **_kwargs):
        raise AssertionError("không được gọi mạng với URL không phải HTTPS")

    monkeypatch.setattr(reference_sync, "urlopen", refuse)

    result = reference_sync.sync_latest(tmp_path, lambda _line: None, force=True)

    assert result["ok"] is False
    assert result["code"] == "REFERENCE_SYNC_FAILED"
    assert result["error_type"] == "ValueError"


def test_sync_refuses_a_file_url_so_it_cannot_read_local_files(
    tmp_path,
    monkeypatch,
):
    """urlopen nhận file://; nếu không chặn thì _request_json đọc file trên máy."""
    _plain_http_config(tmp_path, monkeypatch, "file:///C:/Windows/win.ini")
    _seed_caches(tmp_path)

    def refuse(*_args, **_kwargs):
        raise AssertionError("không được mở file:// qua urlopen")

    monkeypatch.setattr(reference_sync, "urlopen", refuse)

    result = reference_sync.sync_latest(tmp_path, lambda _line: None, force=True)

    assert result["ok"] is False
    assert result["code"] == "REFERENCE_SYNC_FAILED"


def test_publish_refuses_a_non_https_server_before_sending_the_admin_key(
    tmp_path,
    monkeypatch,
):
    _plain_http_config(tmp_path, monkeypatch, "http://example.test/publish")
    _seed_caches(tmp_path)
    monkeypatch.setenv("WFX_SYNC_ADMIN_KEY", "admin-test-key")

    def refuse(*_args, **_kwargs):
        raise AssertionError("không được gửi admin key qua HTTP")

    monkeypatch.setattr(reference_sync, "urlopen", refuse)

    result = reference_sync.publish_current(tmp_path, lambda _line: None)

    assert result["ok"] is False
    assert result["code"] == "REFERENCE_SYNC_PUBLISH_FAILED"


def test_https_url_validator_matches_the_sibling_sync_modules():
    for accepted in ("https://n8n.itx.io.vn/webhook/x", "https://example.test/a"):
        assert reference_sync._safe_https_url(accepted) == accepted
    for rejected in (
        "http://example.test/a",
        "file:///etc/passwd",
        "ftp://example.test/a",
        "https:///no-host",
        "",
    ):
        try:
            reference_sync._safe_https_url(rejected)
        except ValueError:
            continue
        raise AssertionError(f"phải từ chối {rejected!r}")
