"""Snapshot dropdown Style: dữ liệu hỏng, tải chung từ GitHub, và quyền ghi.

CLAUDE.md: form Excel lấy dropdown từ snapshot GitHub/cache 30 ngày; app ghi
`data/style-options.json` qua GitHub Contents API khi máy quản trị có token,
còn bản phát hành thường chỉ có quyền đọc GitHub Raw. Mọi URL do cấu hình cung
cấp phải qua kiểm tra HTTPS trước khi gọi `urlopen`.
"""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError

import pytest

from wfx_panel.stores import style_options


def _snapshot(generated_at=None):
    return {
        "schema_version": 1,
        "generated_at": generated_at or time.time(),
        "source": "test",
        "fields": {
            "material_type": ["KNIT", "WOVEN"],
            "buyer": ["Buyer A"],
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


class _Response:
    status = 200

    def __init__(self, payload=b"{}"):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _maximum=None):
        return self.payload


def _answer(monkeypatch, handler):
    monkeypatch.setattr(style_options, "urlopen", handler)


def _never_called(*_args, **_kwargs):
    raise AssertionError("không được gọi mạng trong tình huống này")


# --- dữ liệu không đúng hình dạng mong đợi ------------------------------


@pytest.mark.parametrize("raw", ["Top", None, 7, {"label": "Top"}])
def test_a_field_that_is_not_a_list_becomes_an_empty_dropdown(raw):
    assert style_options._values(raw) == []


def test_a_dropdown_option_is_read_from_its_label_then_its_value():
    raw = [
        {"label": "Jacket", "value": "01"},
        {"value": "02"},
        {"label": "   ", "value": "  "},
        "Shirt",
        "shirt",
    ]

    assert style_options._values(raw) == ["Jacket", "02", "Shirt"]


@pytest.mark.parametrize("raw", [None, "snapshot", [], 7])
def test_anything_that_is_not_a_snapshot_is_rejected(raw):
    assert style_options.normalise_snapshot(raw) is None


def test_a_snapshot_without_a_field_table_is_rejected():
    assert style_options.normalise_snapshot({"fields": ["Top"]}) is None


def test_material_type_falls_back_to_the_two_values_wfx_always_has():
    payload = _snapshot()
    payload["fields"]["material_type"] = []

    normalised = style_options.normalise_snapshot(payload)

    assert normalised["fields"]["material_type"] == ["KNIT", "WOVEN"]


@pytest.mark.parametrize("field", ["buyer", "product_group", "season"])
def test_a_snapshot_missing_a_field_the_form_needs_is_rejected(field):
    payload = _snapshot()
    payload["fields"][field] = []

    assert style_options.normalise_snapshot(payload) is None


def test_a_snapshot_without_sub_category_dependencies_is_rejected():
    payload = _snapshot()
    payload["subcategories_by_product_group"] = {"  ": ["Jacket"], "Top": []}

    assert style_options.normalise_snapshot(payload) is None


def test_a_cache_file_that_is_no_longer_a_valid_snapshot_reads_as_missing(
    tmp_path,
):
    (tmp_path / "style-options.json").write_text(
        json.dumps({"fields": {}}), encoding="utf-8"
    )

    assert style_options.load_cached(tmp_path) is None
    assert style_options.status(tmp_path) == {
        "available": False,
        "fresh": False,
        "generated_at": 0,
    }


def test_a_machine_that_has_never_synced_reads_as_no_cache(tmp_path):
    assert style_options.load_cached(tmp_path) is None


def test_a_cache_file_damaged_on_disk_reads_as_no_cache(tmp_path):
    (tmp_path / "style-options.json").write_text("{khong", encoding="utf-8")

    assert style_options.load_cached(tmp_path) is None


def test_an_invalid_snapshot_is_never_written_to_the_cache(tmp_path):
    with pytest.raises(ValueError, match="không hợp lệ"):
        style_options.save_snapshot(tmp_path, {"fields": {}})

    assert not (tmp_path / "style-options.json").exists()


# --- bundle phẳng từ máy chủ --------------------------------------------


def _server_bundle(tmp_path, **kwargs):
    return style_options.save_server_options(
        tmp_path,
        kwargs.pop(
            "options",
            [
                {"field_name": "buyer", "option_value": "Buyer A"},
                {"field_name": "product_group", "option_value": "Top"},
                {"field_name": "season", "option_label": "FW27"},
            ],
        ),
        kwargs.pop(
            "subcategories",
            [{"product_group": "Top", "sub_category": "Jacket"}],
        ),
        version=kwargs.pop("version", "7"),
        published_at=kwargs.pop("published_at", "2026-01-31T10:00:00Z"),
        company_id=kwargs.pop("company_id", "psh"),
        division_key=kwargs.pop("division_key", "APPAREL"),
    )


def test_a_server_bundle_becomes_the_snapshot_the_style_form_reads(tmp_path):
    snapshot = _server_bundle(tmp_path)

    assert snapshot["source"] == "postgresql"
    assert snapshot["fields"]["buyer"] == ["Buyer A"]
    assert snapshot["fields"]["season"] == ["FW27"]
    assert snapshot["subcategories_by_product_group"] == {"Top": ["Jacket"]}
    assert style_options.load_cached(tmp_path) == snapshot


def test_rows_the_server_sent_in_the_wrong_shape_are_skipped_not_fatal(tmp_path):
    snapshot = _server_bundle(
        tmp_path,
        options=[
            "Buyer A",
            None,
            {"field_name": "buyer", "option_value": "Buyer A"},
            {"field_name": "khong_co_that", "option_value": "X"},
            {"field_name": "product_group", "option_value": "Top"},
            {"field_name": "season", "option_value": "FW27"},
        ],
        subcategories=[
            "Top",
            {"product_group": "Top"},
            {"sub_category": "Jacket"},
            {"product_group": "Top", "sub_category": "Jacket"},
        ],
    )

    assert snapshot["fields"]["buyer"] == ["Buyer A"]
    assert snapshot["subcategories_by_product_group"] == {"Top": ["Jacket"]}


@pytest.mark.parametrize("published_at", ["", None, "hom qua", "2026-13-45"])
def test_a_publish_date_the_server_sent_wrong_falls_back_to_now(
    tmp_path, published_at
):
    before = time.time()

    snapshot = _server_bundle(tmp_path, published_at=published_at)

    assert snapshot["generated_at"] >= before


# --- tải snapshot dùng chung từ GitHub ----------------------------------


def test_a_snapshot_url_that_is_not_https_is_never_fetched(tmp_path, monkeypatch):
    monkeypatch.setenv(style_options.ENV_LIBRARY_URL, "http://wfx.test/style.json")
    _answer(monkeypatch, _never_called)

    assert style_options.sync_remote(tmp_path) is None


def test_a_snapshot_larger_than_the_cap_is_refused(tmp_path, monkeypatch):
    oversized = b"x" * (style_options.MAX_RESPONSE_BYTES + 1)
    _answer(monkeypatch, lambda *_a, **_k: _Response(oversized))

    assert style_options.sync_remote(tmp_path) is None


def test_a_snapshot_github_serves_broken_leaves_the_cache_alone(
    tmp_path, monkeypatch
):
    local = style_options.save_snapshot(tmp_path, _snapshot())
    _answer(monkeypatch, lambda *_a, **_k: _Response(b'{"fields": {}}'))

    assert style_options.sync_remote(tmp_path) is None
    assert style_options.load_cached(tmp_path) == local


def test_a_snapshot_older_than_the_local_cache_does_not_overwrite_it(
    tmp_path, monkeypatch
):
    local = style_options.save_snapshot(tmp_path, _snapshot(time.time()))
    stale = json.dumps(_snapshot(time.time() - 1_000)).encode()
    _answer(monkeypatch, lambda *_a, **_k: _Response(stale))

    assert style_options.sync_remote(tmp_path) == local


def test_a_machine_that_is_offline_keeps_working_from_its_cache(
    tmp_path, monkeypatch
):
    def offline(*_args, **_kwargs):
        raise OSError("không có mạng")

    _answer(monkeypatch, offline)

    assert style_options.sync_remote(tmp_path) is None


# --- ghi snapshot lên GitHub (chỉ máy quản trị) -------------------------


def test_a_release_build_without_a_write_token_never_pushes_to_github(
    monkeypatch,
):
    monkeypatch.delenv(style_options.ENV_GITHUB_TOKEN, raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    _answer(monkeypatch, _never_called)

    assert style_options.publish_snapshot(_snapshot()) is False


def test_a_misconfigured_repository_stops_the_push(monkeypatch):
    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    monkeypatch.setenv(style_options.ENV_GITHUB_REPOSITORY, "khong-co-dau-gach")
    _answer(monkeypatch, _never_called)

    assert style_options.publish_snapshot(_snapshot()) is False


def test_a_blank_branch_setting_falls_back_to_the_release_branch(monkeypatch):
    requests = []

    def handler(request, **_kwargs):
        requests.append(request)
        if request.get_method() == "GET":
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        return _Response()

    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    monkeypatch.setenv(style_options.ENV_GITHUB_BRANCH, "   ")
    _answer(monkeypatch, handler)

    assert style_options.publish_snapshot(_snapshot()) is True
    assert json.loads(requests[1].data)["branch"] == (
        style_options.DEFAULT_GITHUB_BRANCH
    )


def test_an_invalid_snapshot_is_never_pushed_to_github(monkeypatch):
    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    _answer(monkeypatch, _never_called)

    assert style_options.publish_snapshot({"fields": {}}) is False


def test_the_first_ever_snapshot_is_created_without_a_sha(monkeypatch):
    requests = []

    def handler(request, **_kwargs):
        requests.append(request)
        if request.get_method() == "GET":
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        return _Response()

    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    _answer(monkeypatch, handler)

    assert style_options.publish_snapshot(_snapshot()) is True
    assert "sha" not in json.loads(requests[1].data)


def test_a_token_github_rejects_stops_the_push_instead_of_overwriting(
    monkeypatch,
):
    def handler(request, **_kwargs):
        if request.get_method() == "GET":
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        raise AssertionError("không được PUT khi chưa đọc được file hiện tại")

    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    _answer(monkeypatch, handler)

    assert style_options.publish_snapshot(_snapshot()) is False


def test_a_network_error_while_reading_the_current_file_stops_the_push(
    monkeypatch,
):
    def handler(request, **_kwargs):
        if request.get_method() == "GET":
            raise OSError("mất mạng")
        raise AssertionError("không được PUT khi chưa đọc được file hiện tại")

    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    _answer(monkeypatch, handler)

    assert style_options.publish_snapshot(_snapshot()) is False


def test_a_push_that_never_reaches_github_is_reported_as_failed(monkeypatch):
    def handler(request, **_kwargs):
        if request.get_method() == "GET":
            return _Response(json.dumps({"sha": "old-sha"}).encode())
        raise OSError("timeout")

    monkeypatch.setenv(style_options.ENV_GITHUB_TOKEN, "test-token")
    _answer(monkeypatch, handler)

    assert style_options.publish_snapshot(_snapshot()) is False
