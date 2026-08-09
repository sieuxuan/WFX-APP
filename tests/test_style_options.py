import json
import time

from wfx_panel import style_options


def _snapshot(generated_at=None):
    return {
        "schema_version": 1,
        "generated_at": generated_at or time.time(),
        "source": "test",
        "fields": {
            "material_type": ["KNIT", "WOVEN"],
            "buyer": ["Buyer A", "Buyer A"],
            "division": ["Division A"],
            "product_group": ["Top", "Bottom"],
            "color_card": ["Color A"],
            "size_range": ["Size A"],
            "season": ["FW27"],
        },
        "subcategories_by_product_group": {
            "Top": ["Jacket", "Shirt"],
            "Bottom": ["Pants"],
        },
    }


def test_style_options_cache_is_fresh_for_thirty_days(tmp_path):
    saved = style_options.save_snapshot(tmp_path, _snapshot())

    loaded = style_options.load_cached(tmp_path, allow_expired=False)

    assert loaded == saved
    assert style_options.status(tmp_path)["fresh"] is True
    assert loaded["fields"]["buyer"] == ["Buyer A"]
    assert loaded["subcategories_by_product_group"]["Top"] == [
        "Jacket",
        "Shirt",
    ]


def test_expired_style_options_remain_available_as_offline_fallback(tmp_path):
    style_options.save_snapshot(
        tmp_path,
        _snapshot(time.time() - style_options.CACHE_TTL_SECONDS - 1),
    )

    assert style_options.load_cached(tmp_path) is not None
    assert style_options.load_cached(tmp_path, allow_expired=False) is None
    assert style_options.status(tmp_path)["fresh"] is False


def test_style_cache_invalid_timestamp_is_treated_as_expired(tmp_path):
    payload = _snapshot()
    payload["generated_at"] = "invalid"
    payload["saved_at"] = ["invalid"]
    (tmp_path / "style-options.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    loaded = style_options.load_cached(tmp_path)

    assert loaded is not None
    assert loaded["generated_at"] == 0
    assert style_options.status(tmp_path)["fresh"] is False


def test_remote_style_options_replace_older_cache(tmp_path, monkeypatch):
    style_options.save_snapshot(tmp_path, _snapshot(time.time() - 100))
    remote = _snapshot(time.time())

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _maximum):
            return json.dumps(remote).encode()

    monkeypatch.setattr(style_options, "urlopen", lambda *_args, **_kwargs: Response())
    synced = style_options.sync_remote(tmp_path)

    assert synced["source"] == "github"
    assert synced["generated_at"] == remote["generated_at"]


def test_publish_style_options_uses_github_contents_api(monkeypatch):
    requests = []

    class Response:
        status = 200

        def __init__(self, payload=b"{}"):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _maximum=None):
            return self.payload

    def fake_urlopen(request, **_kwargs):
        requests.append(request)
        if request.get_method() == "GET":
            return Response(json.dumps({"sha": "old-sha"}).encode())
        return Response()

    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    monkeypatch.setattr(style_options, "urlopen", fake_urlopen)

    assert style_options.publish_snapshot(_snapshot()) is True
    assert [request.get_method() for request in requests] == ["GET", "PUT"]
    body = json.loads(requests[1].data)
    assert body["branch"] == "main"
    assert body["sha"] == "old-sha"
    assert body["content"]
