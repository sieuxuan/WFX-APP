"""Đồng bộ Article Library: chỉ HTTPS, kiểm checksum, và không xoá cache đang dùng.

CLAUDE.md yêu cầu mọi URL do cấu hình cung cấp phải qua kiểm tra HTTPS + hostname
trước khi gọi `urlopen` — một cấu hình nhầm `http://` đủ để đẩy read key qua mạng
dạng rõ, còn `file://` biến hàm tải thành trình đọc file cục bộ.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from wfx_panel.stores import article_library

SCHEMA = article_library.SCHEMA_VERSION


class FakeResponse:
    def __init__(self, payload: bytes, *, content_length=None):
        self._payload = payload
        self.headers = {
            "Content-Length": str(
                len(payload) if content_length is None else content_length
            )
        }

    def read(self, size=-1):
        return self._payload[:size] if size and size > 0 else self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _wire_urlopen(monkeypatch, responses):
    """Map URL -> bytes (hoặc exception); ghi lại đúng thứ tự URL đã gọi."""
    seen: list[str] = []

    def urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        seen.append(url)
        outcome = responses[url]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome if isinstance(outcome, FakeResponse) else FakeResponse(outcome)

    monkeypatch.setattr(article_library, "urlopen", urlopen)
    return seen


def _manifest(data_url, payload, *, version="v2", **overrides):
    manifest = {
        "schema_version": SCHEMA,
        "version": version,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "data_url": data_url,
    }
    manifest.update(overrides)
    return json.dumps(manifest).encode("utf-8")


def _articles_json(*rows):
    return json.dumps(
        {"schema_version": SCHEMA, "generated_at": "2026-01-01", "articles": list(rows)}
    ).encode("utf-8")


def _row(code="F0001", name="JACKET", reference="PO-1", category="Apparel"):
    return {
        "article_code": code,
        "article_name": name,
        "buyer_reference": reference,
        "article_category": category,
    }


# --- kiểm tra URL -------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/manifest.json",
        "file:///C:/Windows/win.ini",
        "ftp://example.com/a.json",
        "https:///khong-co-host",
        "",
    ],
)
def test_only_https_urls_with_a_hostname_are_accepted(url):
    with pytest.raises(ValueError, match="HTTPS"):
        article_library._safe_https_url(url)


def test_a_relative_data_url_is_resolved_against_the_manifest(monkeypatch):
    assert article_library._safe_https_url(
        "data/articles.json",
        base_url="https://example.com/library/manifest.json",
    ) == "https://example.com/library/data/articles.json"


def test_a_relative_url_cannot_escape_into_another_scheme():
    with pytest.raises(ValueError, match="HTTPS"):
        article_library._safe_https_url(
            "http://evil.example/a.json",
            base_url="https://example.com/manifest.json",
        )


# --- giới hạn dung lượng ------------------------------------------------


def test_a_response_declaring_too_large_a_body_is_refused(monkeypatch):
    _wire_urlopen(
        monkeypatch,
        {
            "https://example.com/a.json": FakeResponse(
                b"{}", content_length=10_000_000
            )
        },
    )

    with pytest.raises(ValueError, match="dung lượng"):
        article_library._download_bytes(
            "https://example.com/a.json", maximum=1_000
        )


def test_a_response_that_lies_about_its_size_is_still_capped(monkeypatch):
    _wire_urlopen(
        monkeypatch,
        {
            "https://example.com/a.json": FakeResponse(
                b"x" * 2_000, content_length=10
            )
        },
    )

    with pytest.raises(ValueError, match="dung lượng"):
        article_library._download_bytes(
            "https://example.com/a.json", maximum=1_000
        )


def test_a_body_inside_the_limit_is_returned_whole(monkeypatch):
    _wire_urlopen(monkeypatch, {"https://example.com/a.json": b"noi dung"})

    assert article_library._download_bytes(
        "https://example.com/a.json", maximum=1_000
    ) == b"noi dung"


# --- chuẩn hoá Article --------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["khong phai mapping", None, 42, {"article_code": "", "article_name": ""}],
)
def test_rows_without_a_code_or_a_name_are_dropped(raw):
    assert article_library._option(raw) is None


def test_the_legacy_short_keys_are_still_understood():
    option = article_library._option(
        {
            "code": "F0001",
            "name": "JACKET",
            "buyer_ref": "PO-1",
            "category": "Apparel",
        }
    )

    assert option == _row()


def test_a_list_that_is_not_a_list_yields_nothing():
    assert article_library._normalise_articles("khong phai list") == []


def test_duplicate_articles_are_collapsed_ignoring_case():
    articles = article_library._normalise_articles(
        [_row(), _row(code="f0001", name="jacket", reference="po-1"), _row("F0002")]
    )

    assert [item["article_code"] for item in articles] == ["F0001", "F0002"]


# --- đọc CSV / XLSX -----------------------------------------------------


def _csv(headers, *rows, delimiter=","):
    buffer = StringIO()
    buffer.write(delimiter.join(headers) + "\n")
    for row in rows:
        buffer.write(delimiter.join(row) + "\n")
    return buffer.getvalue().encode("utf-8")


def test_a_csv_without_the_two_required_columns_yields_nothing():
    payload = _csv(["Buyer Reference", "Category"], ["PO-1", "Apparel"])

    assert article_library._articles_from_csv(payload) == []


def test_an_empty_csv_yields_nothing():
    assert article_library._articles_from_csv(b"") == []


def test_a_semicolon_csv_is_read_the_same_as_a_comma_one():
    payload = _csv(
        ["Article Code", "Article Name", "Buyer Reference", "Article Category"],
        ["F0001", "JACKET", "PO-1", "Apparel"],
        delimiter=";",
    )

    assert article_library._articles_from_csv(payload) == [_row()]


def test_a_csv_with_a_byte_order_mark_is_read_correctly():
    payload = "\ufeffArticle Code,Article Name\nF0001,JACKET\n".encode("utf-8")

    assert article_library._articles_from_csv(payload)[0]["article_code"] == "F0001"


def _xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_a_worksheet_without_a_header_row_is_skipped():
    payload = _xlsx([["chi la ghi chu"], ["khong co cot nao"]])

    assert article_library._articles_from_xlsx(payload) == []


def test_a_header_row_further_down_the_sheet_is_still_found():
    payload = _xlsx(
        [
            ["BÁO CÁO ARTICLE"],
            [],
            ["Article Code", "Article Name", "Buyer Reference"],
            ["F0001", "JACKET", "PO-1"],
        ]
    )

    assert article_library._articles_from_xlsx(payload) == [
        _row(category="")
    ]


# --- section ------------------------------------------------------------


def test_sections_that_are_not_a_list_yield_nothing():
    assert article_library.normalise_sections("khong phai list") == []


@pytest.mark.parametrize(
    "section",
    [
        "khong phai mapping",
        {"section_name": "All"},
        {"section_key": "*"},
        {"section_key": "*", "section_name": "All", "options": "khong phai list"},
        {"section_key": "*", "section_name": "All", "options": []},
        {"section_key": "*", "section_name": "All", "options": [{"code": ""}]},
    ],
)
def test_a_section_without_key_name_or_options_is_dropped(section):
    assert article_library.normalise_sections([section]) == []


def test_two_sections_with_the_same_identity_are_collapsed():
    section = {"section_key": "*", "section_name": "All", "options": [_row()]}

    assert len(article_library.normalise_sections([section, dict(section)])) == 1


def test_duplicate_options_inside_one_section_are_collapsed():
    sections = article_library.normalise_sections(
        [
            {
                "section_key": "*",
                "section_name": "All",
                "options": [_row(), _row(code="f0001", name="jacket", reference="po-1")],
            }
        ]
    )

    assert len(sections[0]["options"]) == 1


# --- đọc payload theo định dạng ----------------------------------------


def test_a_json_payload_that_is_not_an_object_is_refused():
    with pytest.raises(ValueError, match="không hợp lệ"):
        article_library._sections_from_payload(b"[]", data_format="json")


def test_a_json_payload_from_a_newer_schema_is_refused():
    payload = json.dumps({"schema_version": SCHEMA + 1}).encode("utf-8")

    with pytest.raises(ValueError, match="Schema"):
        article_library._sections_from_payload(payload, data_format="json")


def test_a_json_payload_with_sections_keeps_them_as_they_are():
    payload = json.dumps(
        {
            "schema_version": SCHEMA,
            "generated_at": "2026-01-01",
            "sections": [
                {"section_key": "01", "section_name": "Apparel", "options": [_row()]}
            ],
        }
    ).encode("utf-8")

    sections, generated_at = article_library._sections_from_payload(
        payload, data_format="json"
    )

    assert [item["section_key"] for item in sections] == ["01"]
    assert generated_at == "2026-01-01"


def test_a_payload_with_no_usable_article_yields_no_section():
    payload = json.dumps({"schema_version": SCHEMA, "articles": []}).encode(
        "utf-8"
    )

    assert article_library._sections_from_payload(payload, data_format="json") == (
        [],
        "",
    )


# --- đồng bộ ------------------------------------------------------------


MANIFEST_URL = "https://example.com/library/manifest.json"
DATA_URL = "https://example.com/library/articles.json"


def _sync(tmp_path, monkeypatch, responses, **kwargs):
    seen = _wire_urlopen(monkeypatch, responses)
    result = article_library.sync(
        tmp_path, lambda _line: None, manifest_url=MANIFEST_URL, **kwargs
    )
    return result, seen


def test_a_first_sync_writes_the_cache_and_reports_the_counts(
    tmp_path, monkeypatch
):
    payload = _articles_json(_row(), _row("F0002", "COAT"))
    result, seen = _sync(
        tmp_path,
        monkeypatch,
        {
            MANIFEST_URL: _manifest(DATA_URL, payload),
            DATA_URL: payload,
        },
    )

    assert result["code"] == "ARTICLE_LIBRARY_UPDATED"
    assert result["article_count"] == 2
    assert result["version"] == "v2"
    assert seen == [MANIFEST_URL, DATA_URL]
    assert article_library._cache_path(tmp_path).is_file()


def test_a_second_sync_with_the_same_version_never_downloads_the_data(
    tmp_path, monkeypatch
):
    payload = _articles_json(_row())
    manifest = _manifest(DATA_URL, payload)
    _sync(tmp_path, monkeypatch, {MANIFEST_URL: manifest, DATA_URL: payload})

    result, seen = _sync(
        tmp_path, monkeypatch, {MANIFEST_URL: manifest, DATA_URL: payload}
    )

    assert result["code"] == "ARTICLE_LIBRARY_CURRENT"
    assert seen == [MANIFEST_URL]


def test_a_manifest_that_is_not_an_object_is_refused(tmp_path, monkeypatch):
    result, _seen = _sync(tmp_path, monkeypatch, {MANIFEST_URL: b"[]"})

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    assert result["error_type"] == "ValueError"


def test_a_manifest_from_a_newer_schema_is_refused(tmp_path, monkeypatch):
    manifest = json.dumps({"schema_version": SCHEMA + 1}).encode("utf-8")

    result, _seen = _sync(tmp_path, monkeypatch, {MANIFEST_URL: manifest})

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    assert result["error_type"] == "ValueError"


@pytest.mark.parametrize(
    ("version", "sha"),
    [("", "a" * 64), ("v2", "qua-ngan"), ("v2", "")],
)
def test_a_manifest_without_version_or_checksum_is_refused(
    tmp_path, monkeypatch, version, sha
):
    manifest = json.dumps(
        {
            "schema_version": SCHEMA,
            "version": version,
            "sha256": sha,
            "data_url": DATA_URL,
        }
    ).encode("utf-8")

    result, _seen = _sync(tmp_path, monkeypatch, {MANIFEST_URL: manifest})

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    assert result["error_type"] == "ValueError"


def test_an_unsupported_data_format_is_refused(tmp_path, monkeypatch):
    payload = b"noi dung"
    manifest = _manifest(DATA_URL, payload, format="parquet")

    result, seen = _sync(tmp_path, monkeypatch, {MANIFEST_URL: manifest})

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    # Không tải payload khi đã biết định dạng không đọc được.
    assert seen == [MANIFEST_URL]


@pytest.mark.parametrize(
    ("data_url", "expected_format"),
    [
        ("https://example.com/library/articles.csv", "csv"),
        ("https://example.com/library/articles.xlsx", "xlsx"),
        ("https://example.com/library/articles", "json"),
    ],
)
def test_the_format_is_guessed_from_the_url_when_the_manifest_omits_it(
    tmp_path, monkeypatch, data_url, expected_format
):
    payloads = {
        "csv": _csv(["Article Code", "Article Name"], ["F0001", "JACKET"]),
        "xlsx": _xlsx([["Article Code", "Article Name"], ["F0001", "JACKET"]]),
        "json": _articles_json(_row()),
    }
    payload = payloads[expected_format]

    result, _seen = _sync(
        tmp_path,
        monkeypatch,
        {MANIFEST_URL: _manifest(data_url, payload), data_url: payload},
    )

    assert result["code"] == "ARTICLE_LIBRARY_UPDATED"
    assert result["article_count"] == 1


def test_a_payload_whose_checksum_does_not_match_is_thrown_away(
    tmp_path, monkeypatch
):
    payload = _articles_json(_row())
    manifest = _manifest(DATA_URL, b"noi dung khac")

    result, _seen = _sync(
        tmp_path, monkeypatch, {MANIFEST_URL: manifest, DATA_URL: payload}
    )

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    assert not article_library._cache_path(tmp_path).is_file()


def test_a_payload_with_no_valid_article_is_refused(tmp_path, monkeypatch):
    payload = json.dumps({"schema_version": SCHEMA, "articles": []}).encode(
        "utf-8"
    )

    result, _seen = _sync(
        tmp_path,
        monkeypatch,
        {MANIFEST_URL: _manifest(DATA_URL, payload), DATA_URL: payload},
    )

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    assert result["error_type"] == "ValueError"


def test_a_network_failure_keeps_the_cache_the_app_is_already_using(
    tmp_path, monkeypatch
):
    payload = _articles_json(_row())
    _sync(
        tmp_path,
        monkeypatch,
        {MANIFEST_URL: _manifest(DATA_URL, payload), DATA_URL: payload},
    )
    before = article_library._cache_path(tmp_path).read_bytes()

    result, _seen = _sync(
        tmp_path, monkeypatch, {MANIFEST_URL: OSError("mất mạng")}
    )

    assert result["ok"] is False
    assert article_library._cache_path(tmp_path).read_bytes() == before
    assert result["available"] is True


# --- ghi từ server chia sẻ ----------------------------------------------


def test_server_articles_inherit_their_category_from_the_bundled_cache(
    tmp_path, monkeypatch
):
    payload = _articles_json(_row("F0001", "JACKET", "PO-1", "Apparel"))
    _sync(
        tmp_path,
        monkeypatch,
        {MANIFEST_URL: _manifest(DATA_URL, payload), DATA_URL: payload},
    )

    status = article_library.save_server_articles(
        tmp_path,
        [
            {"article_code": "F0001", "article_name": "JACKET", "buyer_reference": "PO-9"},
            {"article_code": "F0002", "article_name": "COAT", "buyer_reference": "PO-8"},
            "khong phai mapping",
        ],
        version="pg-1",
    )

    assert status["article_count"] == 2
    cached = article_library.load_cached(tmp_path)
    by_code = {
        option["article_code"]: option
        for option in cached["sections"][0]["options"]
    }
    assert by_code["F0001"]["article_category"] == "Apparel"
    assert by_code["F0001"]["buyer_reference"] == "PO-9"
    # Article mới chưa có trong cache đóng gói thì để trống, không đoán.
    assert by_code["F0002"]["article_category"] == ""


def test_a_server_response_without_any_usable_article_is_refused(tmp_path):
    with pytest.raises(ValueError, match="không trả Article hợp lệ"):
        article_library.save_server_articles(tmp_path, [], version="pg-1")


def test_saving_server_articles_works_without_any_previous_cache(tmp_path):
    status = article_library.save_server_articles(
        tmp_path, [_row()], version="pg-1", generated_at="2026-02-02"
    )

    assert status["article_count"] == 1
    assert status["version"] == "pg-1"
    assert status["generated_at"] == "2026-02-02"


# --- trạng thái và cache ------------------------------------------------


def test_the_status_of_a_machine_that_never_synced_is_empty(tmp_path):
    assert article_library.status(tmp_path) == {
        "available": False,
        "version": "",
        "generated_at": "",
        "synced_at": 0,
        "section_count": 0,
        "article_count": 0,
    }


def test_a_cache_file_that_is_not_json_is_ignored(tmp_path):
    article_library._cache_path(tmp_path).write_text("{", encoding="utf-8")

    assert article_library.load_cached(tmp_path) is None


def test_a_cache_from_another_schema_is_ignored(tmp_path):
    article_library._cache_path(tmp_path).write_text(
        json.dumps({"schema_version": SCHEMA + 1}), encoding="utf-8"
    )

    assert article_library.load_cached(tmp_path) is None


def test_a_cache_without_any_section_is_ignored(tmp_path):
    article_library._cache_path(tmp_path).write_text(
        json.dumps({"schema_version": SCHEMA, "sections": []}), encoding="utf-8"
    )

    assert article_library.load_cached(tmp_path) is None


def test_seeding_never_overwrites_a_cache_the_user_already_has(tmp_path):
    source = tmp_path / "Article List.csv"
    source.write_bytes(_csv(["Article Code", "Article Name"], ["F0001", "JACKET"]))

    assert article_library.seed_bundled(tmp_path, source) is True
    assert article_library.seed_bundled(tmp_path, source) is False


def test_seeding_from_a_file_that_does_not_exist_is_a_no_op(tmp_path):
    assert (
        article_library.seed_bundled(tmp_path, tmp_path / "khong-ton-tai.csv")
        is False
    )


def test_the_suggestion_index_only_accepts_the_three_searchable_fields(tmp_path):
    article_library.save_server_articles(tmp_path, [_row()], version="v1")
    cached = article_library.load_cached(tmp_path)

    assert not article_library.suggestion_index(cached, "Apparel", "gia_ban")


def test_the_suggestion_index_is_reused_for_the_same_document(tmp_path):
    article_library.save_server_articles(tmp_path, [_row()], version="v1")
    cached = article_library.load_cached(tmp_path)

    first = article_library.suggestion_index(cached, "Apparel", "article_code")
    second = article_library.suggestion_index(cached, "Apparel", "article_code")

    assert first is second, "index phải bám vào chính document trong cache"


def test_the_cached_document_is_reused_while_the_file_is_unchanged(tmp_path):
    article_library.save_server_articles(tmp_path, [_row()], version="v1")

    assert article_library.load_cached(tmp_path) is article_library.load_cached(
        tmp_path
    )


def test_a_cache_file_that_disappears_drops_the_in_memory_copy(tmp_path):
    article_library.save_server_articles(tmp_path, [_row()], version="v1")
    assert article_library.load_cached(tmp_path) is not None
    article_library._cache_path(tmp_path).unlink()

    assert article_library.load_cached(tmp_path) is None


def test_a_bundled_file_that_is_not_readable_csv_never_blocks_startup(tmp_path):
    """`seed_bundled` chạy trong `PanelApp.__init__` của bản đóng gói."""
    source = tmp_path / "Article List.csv"
    # File Excel (hoặc CSV lưu nhầm ANSI) không decode được bằng UTF-8.
    source.write_bytes(
        _xlsx([["Article Code", "Article Name"], ["F0001", "JACKET"]])
    )

    assert article_library.seed_bundled(tmp_path, source) is False
    assert not article_library._cache_path(tmp_path).is_file()


def test_a_bundled_seed_that_has_nothing_usable_writes_no_cache(tmp_path):
    source = tmp_path / "Article List.csv"
    source.write_bytes(b"chi la ghi chu\n")

    assert article_library.seed_bundled(tmp_path, source) is False
    assert not article_library._cache_path(tmp_path).is_file()


def test_the_cache_path_lives_next_to_the_other_app_data(tmp_path):
    assert article_library._cache_path(tmp_path) == Path(
        tmp_path
    ) / "article-library.json"


def test_rows_with_neither_a_code_nor_a_name_are_skipped_inside_a_list():
    articles = article_library._normalise_articles(
        [{"buyer_reference": "PO-1"}, _row()]
    )

    assert [item["article_code"] for item in articles] == ["F0001"]


def test_a_csv_longer_than_the_cap_stops_at_the_cap(monkeypatch):
    monkeypatch.setattr(article_library, "MAX_OPTIONS_PER_SECTION", 2)
    payload = _csv(
        ["Article Code", "Article Name"],
        *[[f"F{index:04d}", "JACKET"] for index in range(5)],
    )

    assert len(article_library._articles_from_csv(payload)) == 2


def test_an_xlsx_longer_than_the_cap_stops_at_the_cap(monkeypatch):
    monkeypatch.setattr(article_library, "MAX_OPTIONS_PER_SECTION", 2)
    payload = _xlsx(
        [["Article Code", "Article Name"]]
        + [[f"F{index:04d}", "JACKET"] for index in range(5)]
    )

    assert len(article_library._articles_from_xlsx(payload)) == 2
