"""Dropdown Article của form Costing: item quét live + thư viện server.

Thư viện server chỉ mới bằng lần publish gần nhất. Article vừa tạo trên WFX
chỉ có trong lần quét live, nên có thư viện không được làm mất kết quả quét.
"""

from wfx_panel import prefs
from wfx_panel.atomic_io import write_json_atomic
from wfx_panel.controllers.costing_options import CostingOptionController
from wfx_panel.panel_api import PanelAPI
from wfx_panel.stores import article_library, panel_cache


class _NoAutomation:
    pass


def _write_library(base_dir, options):
    write_json_atomic(
        base_dir / "article-library.json",
        {
            "schema_version": article_library.SCHEMA_VERSION,
            "remote_version": "20260731",
            "generated_at": "2026-07-31T08:00:00Z",
            "synced_at": 100.0,
            "sha256": "a" * 64,
            "sections": [
                {
                    "section_key": "*",
                    "section_name": "All Categories",
                    "options": options,
                }
            ],
        },
    )


def _library_article(code, name, category):
    return {
        "article_code": code,
        "article_name": name,
        "buyer_reference": "",
        "article_category": category,
    }


def _options_controller(tmp_path, user_id="alice"):
    api = PanelAPI(login_module=_NoAutomation(), prefs_module=prefs, base_dir=tmp_path)
    api._account = lambda: {"user_id": user_id}
    return api._catalog.costing.options


def _fabric_document(**section_options):
    return {
        "sections": [
            {"section_key": "fabric", "name": "Fabric", **section_options},
        ]
    }


def _lookup(document):
    return document["sections"][0]["article_lookup_options"]


def test_live_scan_adds_new_articles_on_top_of_the_server_library(tmp_path):
    _write_library(
        tmp_path,
        [
            _library_article("F0001", "Cotton Jersey (library)", "Textiles/Fabric"),
            _library_article("F0002", "Rib", "Textiles/Fabric"),
            _library_article("T0001", "Zipper", "Trims"),
        ],
    )
    options = _options_controller(tmp_path)
    document = _fabric_document(
        article_lookup_options=[
            {"article_code": "F0001", "article_name": "Cotton Jersey"},
            {"article_code": "F9999", "article_name": "Brand New Fleece"},
        ]
    )

    count, source = options._merge_cached_article_options(document, scanned=True)

    assert source == "server_scan"
    assert count == 3
    assert _lookup(document) == [
        # Live là WFX hiện tại nên thắng khi trùng Code với thư viện.
        {"article_code": "F0001", "article_name": "Cotton Jersey"},
        {"article_code": "F9999", "article_name": "Brand New Fleece"},
        {"article_code": "F0002", "article_name": "Rib"},
    ]
    assert document["sections"][0]["article_code_options"] == [
        "F0001",
        "F9999",
        "F0002",
    ]
    saved = panel_cache.load_costing_article_cache("alice", base_dir=tmp_path)
    assert [option["article_code"] for option in saved[0]["options"]] == [
        "F0001",
        "F9999",
    ]


def test_previous_scan_cache_still_feeds_export_without_a_new_scan(tmp_path):
    _write_library(
        tmp_path,
        [_library_article("F0001", "Cotton Jersey", "Textiles/Fabric")],
    )
    panel_cache.save_costing_article_cache(
        "alice",
        [
            {
                "section_key": "fabric",
                "section_name": "Fabric",
                "options": [{"article_code": "F9999", "article_name": "Fleece"}],
            }
        ],
        base_dir=tmp_path,
    )
    options = _options_controller(tmp_path)
    document = _fabric_document()

    count, source = options._merge_cached_article_options(document, scanned=False)

    assert (count, source) == (2, "server_scan")
    assert [option["article_code"] for option in _lookup(document)] == [
        "F9999",
        "F0001",
    ]


def test_scan_with_nothing_new_still_reports_the_server_library(tmp_path):
    _write_library(
        tmp_path,
        [_library_article("F0001", "Cotton Jersey", "Textiles/Fabric")],
    )
    options = _options_controller(tmp_path)
    document = _fabric_document(
        article_lookup_options=[
            {"article_code": "f0001", "article_name": "Cotton Jersey"},
        ]
    )

    assert options._merge_cached_article_options(document, scanned=True) == (
        1,
        "server",
    )


def test_scan_without_a_library_keeps_the_scan_source(tmp_path):
    options = _options_controller(tmp_path)
    document = _fabric_document(
        article_lookup_options=[
            {"article_code": "F9999", "article_name": "Fleece"},
        ]
    )

    assert options._merge_cached_article_options(document, scanned=True) == (
        1,
        "scan",
    )


def test_paired_scan_rows_beat_independently_deduplicated_lists():
    # Hai Article khác mã cùng tên: list name khử trùng còn 1 phần tử nên ghép
    # theo index sẽ gán sai tên cho F0002.
    document = _fabric_document(
        article_code_options=["F0001", "F0002", "F0003"],
        article_name_options=["Jersey", "Rib"],
        article_lookup_options=[
            {"article_code": "F0001", "article_name": "Jersey"},
            {"article_code": "F0002", "article_name": "Jersey"},
            {"article_code": "F0003", "article_name": "Rib"},
        ],
    )

    cached = CostingOptionController._article_cache_sections(document)

    assert cached[0]["options"] == [
        {"article_code": "F0001", "article_name": "Jersey"},
        {"article_code": "F0002", "article_name": "Jersey"},
        {"article_code": "F0003", "article_name": "Rib"},
    ]
