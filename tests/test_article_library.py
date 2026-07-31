import hashlib
import json
from io import BytesIO

from openpyxl import Workbook

from wfx_panel import article_library


def _xlsx_payload():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Article Code", "Article Name"])
    sheet.append(["FAB001", "Cotton Jersey"])
    sheet.append(["TRM002", "Metal Zipper"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _csv_payload():
    return (
        "Article_Code,Article_Name,Buyer_Reference,Article_Category\r\n"
        'S0001,"Dress, Navy",BUY-01,Apparel\r\n'
        "F0001,Cotton Jersey,,Textiles/Fabric\r\n"
    ).encode("utf-8-sig")


def test_two_column_xlsx_remains_backward_compatible():
    sections, generated_at = article_library._sections_from_payload(
        _xlsx_payload(),
        data_format="xlsx",
    )

    assert generated_at == ""
    assert sections == [
        {
            "section_key": "*",
            "section_name": "All Categories",
            "options": [
                {
                    "article_code": "FAB001",
                    "article_name": "Cotton Jersey",
                    "buyer_reference": "",
                    "article_category": "",
                },
                {
                    "article_code": "TRM002",
                    "article_name": "Metal Zipper",
                    "buyer_reference": "",
                    "article_category": "",
                },
            ],
        }
    ]


def test_four_column_csv_preserves_category_and_buyer_reference():
    sections, generated_at = article_library._sections_from_payload(
        _csv_payload(),
        data_format="csv",
    )

    assert generated_at == ""
    assert sections[0]["options"] == [
        {
            "article_code": "S0001",
            "article_name": "Dress, Navy",
            "buyer_reference": "BUY-01",
            "article_category": "Apparel",
        },
        {
            "article_code": "F0001",
            "article_name": "Cotton Jersey",
            "buyer_reference": "",
            "article_category": "Textiles/Fabric",
        },
    ]


def test_bundled_csv_seeds_only_an_empty_cache(tmp_path):
    source = tmp_path / "Article List.csv"
    source.write_bytes(_csv_payload())
    cache_dir = tmp_path / "cache"

    first = article_library.seed_bundled(cache_dir, source)
    second = article_library.seed_bundled(cache_dir, source)

    assert first is True
    assert second is False
    assert article_library.status(cache_dir)["article_count"] == 2


def test_server_sync_checks_checksum_and_keeps_versioned_cache(
    tmp_path,
    monkeypatch,
):
    data = _xlsx_payload()
    manifest = json.dumps(
        {
            "schema_version": 1,
            "version": "2026-07-31-01",
            "format": "xlsx",
            "data_url": "article-library.xlsx",
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    ).encode()
    calls = []

    def download(url, *, maximum):
        calls.append((url, maximum))
        return manifest if url.endswith("manifest.json") else data

    monkeypatch.setattr(article_library, "_download_bytes", download)
    first = article_library.sync(
        tmp_path,
        manifest_url="https://data.example.test/manifest.json",
    )
    second = article_library.sync(
        tmp_path,
        manifest_url="https://data.example.test/manifest.json",
    )

    assert first["code"] == "ARTICLE_LIBRARY_UPDATED"
    assert first["article_count"] == 2
    assert second["code"] == "ARTICLE_LIBRARY_CURRENT"
    assert [url for url, _maximum in calls].count(
        "https://data.example.test/article-library.xlsx"
    ) == 1


def test_sync_failure_keeps_last_server_cache(tmp_path, monkeypatch):
    data = _xlsx_payload()
    manifest = json.dumps(
        {
            "schema_version": 1,
            "version": "v1",
            "format": "xlsx",
            "data_url": "library.xlsx",
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    ).encode()
    monkeypatch.setattr(
        article_library,
        "_download_bytes",
        lambda url, *, maximum: manifest if url.endswith("manifest.json") else data,
    )
    article_library.sync(
        tmp_path,
        manifest_url="https://data.example.test/manifest.json",
    )
    monkeypatch.setattr(
        article_library,
        "_download_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )

    result = article_library.sync(
        tmp_path,
        manifest_url="https://data.example.test/manifest.json",
    )

    assert result["code"] == "ARTICLE_LIBRARY_SYNC_FAILED"
    assert result["available"] is True
    assert result["article_count"] == 2
