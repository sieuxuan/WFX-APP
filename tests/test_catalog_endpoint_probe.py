"""Chẩn đoán chỉ đọc: dò request nạp dữ liệu của Catalog Grid.

Phần thuần Python (che giá trị, tóm tắt hình dạng JSON, chọn ứng viên) quyết
định file kết quả có an toàn để chuyển cho người khác hay không, nên được canh
kỹ ở đây mà không cần Chrome. Flow Playwright được chạy với context giả để
khẳng định listener gắn TRƯỚC khi mở Master và file thật sự được ghi.
"""

from __future__ import annotations

import json

import pytest

from tests.test_panel_api import make_api
from wfx_panel.automation.catalog import endpoint_probe as probe

# --- che giá trị nhạy cảm -------------------------------------------------


def test_url_keeps_host_and_path_but_never_the_raw_query():
    described = probe.describe_url(
        "https://wfx.test/wfx/Catalog/WFXCatalogList.aspx/GetData"
        "?SessionID=abc&LoginID=u1&CategoryID=01&pageSize=100"
    )

    assert described["host"] == "wfx.test"
    assert described["path"] == "/wfx/Catalog/WFXCatalogList.aspx/GetData"
    params = {item["name"]: item["value"] for item in described["query_params"]}
    assert params == {
        "SessionID": probe.HIDDEN,
        "LoginID": probe.HIDDEN,
        "CategoryID": "01",
        "pageSize": "100",
    }
    assert "abc" not in json.dumps(described)


def test_guid_and_cookieless_session_segments_are_hidden_from_the_path():
    path = probe.safe_path(
        "/(S(xyzsessionabc123))/wfx/3f2504e0-4f89-11d3-9a0c-0305e82c3301/list.aspx"
    )

    assert "xyzsession" not in path
    assert "3f2504e0" not in path
    assert path.endswith("/list.aspx")


def test_param_values_that_look_like_session_keys_are_hidden_even_with_a_plain_name():
    params = probe.describe_params(
        [
            ("filter", "3f2504e0-4f89-11d3-9a0c-0305e82c3301"),
            ("blob", "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo="),
            ("note", "x" * 80),
            ("category", "Apparel"),
        ]
    )

    assert [item["value"] for item in params] == [
        probe.HIDDEN,
        probe.HIDDEN,
        probe.HIDDEN,
        "Apparel",
    ]


def test_json_body_lists_parameter_names_with_masked_values():
    body = probe.describe_body(
        json.dumps({"categoryId": "01", "userGuid": "u-1", "filter": {"x": 1}}),
        "application/json; charset=utf-8",
    )

    assert body["format"] == "json"
    assert {item["name"]: item["value"] for item in body["params"]} == {
        "categoryId": "01",
        "userGuid": probe.HIDDEN,
        "filter": "<dict>",
    }


def test_headers_drop_cookies_and_split_json_parameters():
    headers = probe.describe_headers(
        {
            "cookie": "ASP.NET_SessionId=abc",
            "authorization": "Bearer xyz",
            "referer": "https://wfx.test/list?q=1",
            "sec-ch-ua": "Chrome",
            "accept": "application/json",
            "content-type": "application/json",
            "x-session-guid": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
            "parameters": json.dumps(
                {"FunctionName": "CatalogList", "CategoryID": "01", "LoginID": "u"}
            ),
        }
    )

    text = json.dumps(headers)
    assert "abc" not in text and "xyz" not in text and "q=1" not in text
    by_name = {item["name"]: item for item in headers}
    assert set(by_name) == {"content-type", "parameters", "x-session-guid"}
    assert by_name["x-session-guid"]["value"] == probe.HIDDEN
    assert by_name["parameters"]["value"] == "<json>"
    assert {p["name"]: p["value"] for p in by_name["parameters"]["params"]} == {
        "FunctionName": "CatalogList",
        "CategoryID": "01",
        "LoginID": probe.HIDDEN,
    }


def test_url_encoded_json_headers_are_decoded_before_masking():
    from urllib.parse import quote

    headers = probe.describe_headers(
        {
            "apiparams": quote(json.dumps({"ProcName": "CatalogList", "UserID": 7})),
            "searchparams": quote(json.dumps([{"ColName": "Code", "Value": "F1"}])),
        }
    )

    by_name = {item["name"]: item for item in headers}
    assert {p["name"]: p["value"] for p in by_name["apiparams"]["params"]} == {
        "ProcName": "CatalogList",
        "UserID": probe.HIDDEN,
    }
    assert by_name["searchparams"]["value"] == "<json-array>"
    assert by_name["searchparams"]["shape"]["length"] == 1
    assert by_name["searchparams"]["params"] == [
        {"name": "[0].ColName", "value": "Code"},
        {"name": "[0].Value", "value": "F1"},
    ]


def test_wfx_param_name_value_arrays_list_every_parameter():
    from urllib.parse import quote

    pageparams = [
        {"ParamName": "ProductCatCode", "ParamValue": "01"},
        {"ParamName": "UserID", "ParamValue": "12345"},
        {"ParamName": "CompanyCode", "ParamValue": "77400"},
    ]
    [header] = probe.describe_headers({"pageparams": quote(json.dumps(pageparams))})

    assert header["params"] == [
        {"name": "ProductCatCode", "value": "01"},
        {"name": "UserID", "value": probe.HIDDEN},
        {"name": "CompanyCode", "value": "77400"},
    ]


def test_form_body_is_parsed_as_named_parameters():
    body = probe.describe_body(
        "__VIEWSTATE=dDwtMTI3OTMzNDM4NDs7Pg%3D%3D&ddlCategory=01",
        "application/x-www-form-urlencoded",
    )

    assert body["format"] == "form"
    assert body["params"] == [
        {"name": "__VIEWSTATE", "value": probe.HIDDEN},
        {"name": "ddlCategory", "value": "01"},
    ]


def test_sample_values_keep_only_a_short_prefix():
    assert probe.mask_value("F123456789") == "F12…(len=10)"
    assert probe.mask_value("ab") == "ab"
    assert probe.mask_value("") == ""
    assert probe.mask_value("https://wfx.test/a?SessionID=1") != (
        "https://wfx.test/a?SessionID=1"
    )


def test_a_masked_row_hides_sensitive_columns_and_numbers():
    row = probe.mask_row(
        {
            "ArticleCode": "F100200",
            "CreatedByUserID": "u.nguyen",
            "CreatedBy": "u.nguyen",
            "Qty": 12,
            "Active": True,
            "Colors": ["Red"],
        }
    )

    assert row == {
        "ArticleCode": "F10…(len=7)",
        "CreatedByUserID": probe.HIDDEN,
        "CreatedBy": probe.HIDDEN,
        "Qty": "<number>",
        "Active": True,
        "Colors": "<list>",
    }


# --- hình dạng response -----------------------------------------------------


def test_json_shape_counts_arrays_and_names_keys():
    shape = probe.json_shape({"rows": [{"a": 1, "b": "x"}, {"a": 2}], "total": 2})

    assert shape["type"] == "object"
    assert shape["keys"]["total"] == "number"
    rows = shape["keys"]["rows"]
    assert rows["length"] == 2
    assert rows["item"]["keys"] == {"a": "number", "b": "string"}


def test_aspnet_webmethod_string_payload_is_unwrapped():
    rows = [
        {"ArticleCode": "F1", "ArticleName": "Fabric 1", "Category": "Textiles"},
        {"ArticleCode": "F2", "ArticleName": "Fabric 2", "Category": "Textiles"},
    ]
    body = json.dumps({"d": json.dumps({"Data": rows, "Total": 2})}).encode()

    summary = probe.summarize_response_body(body, "application/json")

    assert summary["kind"] == "json"
    assert summary["shape"]["keys"]["d"]["type"] == "json_string"
    [candidate] = summary["row_lists"]
    assert candidate["json_path"] == "$.d<json>.Data"
    assert candidate["row_count"] == 2
    assert candidate["looks_like_article_rows"] is True
    assert candidate["article_fields"] == {
        "article_code": "ArticleCode",
        "article_name": "ArticleName",
        "category": "Category",
    }
    assert len(candidate["sample_rows"]) == 2
    assert candidate["sample_rows"][0]["ArticleName"] == "Fab…(len=8)"


def test_html_document_reports_embedded_article_field_hints():
    body = b'<html><script>var rows=[{"ArticleCode":"F1","BuyerReference":"B"}]</script>'

    summary = probe.summarize_response_body(body, "text/html")

    assert summary == {
        "kind": "html",
        "embedded_field_hints": ["ArticleCode", "BuyerReference"],
    }


def test_unreadable_and_binary_bodies_do_not_raise():
    assert probe.summarize_response_body(None, "")["kind"] == "unavailable"
    assert probe.summarize_response_body(b"\xff\xfe\x00", "")["kind"] == "binary"
    assert probe.summarize_response_body(b"not json", "text/plain")["kind"] == "text"


def test_field_roles_match_wfx_and_generic_column_names():
    fields = probe.match_article_fields(
        ["lnkArticleCode", "Article_Name", "lblBuyerReference", "ArticleCategory"]
    )

    assert fields == {
        "article_code": "lnkArticleCode",
        "article_name": "Article_Name",
        "buyer_reference": "lblBuyerReference",
        "category": "ArticleCategory",
    }


# --- chọn ứng viên ----------------------------------------------------------


def _entry(index, rows, *, from_grid=False, path="/x"):
    return {
        "index": index,
        "method": "POST",
        "host": "wfx.test",
        "path": path,
        "from_catalog_grid": from_grid,
        "response": {"kind": "json", "row_lists": probe.row_list_candidates(rows)},
    }


def test_best_candidate_prefers_rows_that_look_like_articles():
    menu = _entry(0, [{"MenuName": "Catalog", "Url": "a"}] * 50, path="/menu")
    articles = _entry(
        1,
        [{"ArticleCode": "F1", "BuyerReference": "B1"}],
        from_grid=True,
        path="/catalog/data",
    )

    best = probe.best_candidate([menu, articles])

    assert best["path"] == "/catalog/data"
    assert best["looks_like_article_rows"] is True
    assert best["article_fields"] == {
        "article_code": "ArticleCode",
        "buyer_reference": "BuyerReference",
    }


def test_no_candidate_when_nothing_resembles_article_rows():
    assert probe.best_candidate([_entry(0, [{"MenuName": "x"}])]) is None
    message = probe.candidate_message(None, 3)
    assert "3 request" in message


def test_report_carries_score_and_best_candidate():
    entries = [_entry(0, [{"ArticleCode": "F1", "ArticleName": "N"}])]

    report = probe.build_report(
        entries, category="Apparel", app_version="9.9.9", run_note="note"
    )

    assert report["kind"] == "catalog-endpoint-probe"
    assert report["request_count"] == 1
    assert report["requests"][0]["candidate_score"] > 0
    assert report["best_candidate"]["index"] == 0


# --- flow Playwright với context giả ----------------------------------------


class _FakeFrame:
    def __init__(self, url, name=""):
        self.url = url
        self.name = name


class _FakeRequest:
    def __init__(self, url, resource_type="xhr", frame=None, post_data=None):
        self.url = url
        self.resource_type = resource_type
        self.method = "POST"
        self.headers = {"content-type": "application/json", "cookie": "SECRET=1"}
        self.post_data = post_data
        self.frame = frame or _FakeFrame("https://wfx.test/wfx/wfxcataloglist.aspx")


class _FakeResponse:
    def __init__(self, request, body):
        self.request = request
        self.status = 200
        self.headers = {"content-type": "application/json"}
        self._body = body

    def body(self):
        return self._body


class _FakeContext:
    def __init__(self):
        self.handlers: dict[str, list] = {}

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        self.handlers.get(event, []).remove(handler)

    def emit(self, event, value):
        for handler in list(self.handlers.get(event, [])):
            handler(value)


class _FakePage:
    url = "https://wfx.test/wfx/default.aspx"
    frames: list = []


class _FakeBrowser:
    def __init__(self, context):
        self.contexts = [context]


class _FakePlaywright:
    stopped = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True


@pytest.fixture
def wired(monkeypatch):
    context = _FakeContext()
    playwright = _FakePlaywright()
    calls: list = []

    def connect(_playwright, *, bring_to_front=True):
        calls.append(("connect", bring_to_front))
        return _FakeBrowser(context), _FakePage()

    def click_master(_page, _log):
        calls.append(("master", bool(context.handlers.get("request"))))
        data = _FakeRequest(
            "https://wfx.test/wfx/CatalogService.asmx/GetArticles?sid=zz",
            post_data='{"categoryId":"01"}',
        )
        context.emit("request", data)
        context.emit(
            "response",
            _FakeResponse(
                data,
                json.dumps(
                    {"d": [{"ArticleCode": "F1", "ArticleName": "Fabric"}]}
                ).encode(),
            ),
        )
        context.emit(
            "request",
            _FakeRequest("https://wfx.test/img/logo.png", resource_type="image"),
        )
        context.emit(
            "request",
            _FakeRequest("https://mail.example.com/sync/inbox?u=me@example.com"),
        )

    monkeypatch.setattr(probe, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(probe, "sync_playwright", lambda: playwright)
    monkeypatch.setattr(probe, "_connect_to_chrome", connect)
    monkeypatch.setattr(probe, "_attach_dialog_handler", lambda *_a: None)
    monkeypatch.setattr(probe, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(
        probe, "_open_catalog_tree_on_page", lambda *_a: calls.append(("tree",))
    )
    monkeypatch.setattr(probe, "_click_catalog_master", click_master)
    monkeypatch.setattr(probe, "_show_catalog_floating_filter", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_wait", lambda *_a: None)
    return context, playwright, calls


def test_probe_records_grid_requests_and_writes_a_redacted_file(tmp_path, wired):
    context, playwright, calls = wired

    result = probe.probe_catalog_data_source(
        "Apparel", "01", tmp_path / "diagnostics", lambda _line: None
    )

    assert result["code"] == "CATALOG_DATA_SOURCE_PROBED"
    # Grid Catalog chỉ được nhận khi tab đang hiển thị, nên probe đưa tab WFX
    # lên trước giống nút Mở Catalog.
    assert ("connect", True) in calls
    assert ("master", True) in calls, "listener phải gắn trước khi mở Master"
    assert result["request_count"] == 1, "chỉ ghi XHR/fetch của WFX, bỏ ảnh/web khác"
    assert result["best_candidate"]["path"] == "/wfx/CatalogService.asmx/GetArticles"
    text = (tmp_path / "diagnostics").joinpath(
        result["file_path"].split("\\")[-1].split("/")[-1]
    ).read_text(encoding="utf-8")
    assert "SECRET" not in text and "zz" not in text
    assert "example.com" not in text
    report = json.loads(text)
    assert report["requests"][0]["query_params"] == [
        {"name": "sid", "value": probe.HIDDEN}
    ]
    assert report["requests"][0]["from_catalog_grid"] is True
    assert not context.handlers.get("request"), "listener phải được gỡ"
    assert playwright.stopped


def test_probe_stops_when_the_working_browser_is_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "_chrome_is_ready", lambda: False)

    result = probe.probe_catalog_data_source("Apparel", "01", tmp_path)

    assert result["code"] == "CHROME_CLOSED"
    assert not list(tmp_path.iterdir())


def test_probe_timeout_is_reported_as_not_ready(tmp_path, wired, monkeypatch):
    def timeout(*_args):
        raise probe.PlaywrightTimeoutError("Master chưa mở")

    monkeypatch.setattr(probe, "_click_catalog_master", timeout)

    result = probe.probe_catalog_data_source("Apparel", "01", tmp_path, lambda _l: None)

    assert result["code"] == "CATALOG_PROBE_NOT_READY"


def test_requests_seen_before_a_grid_timeout_are_still_saved(
    tmp_path, wired, monkeypatch
):
    def timeout(*_args, **_kwargs):
        raise probe.PlaywrightTimeoutError("grid chưa ổn định")

    monkeypatch.setattr(probe, "_show_catalog_floating_filter", timeout)

    result = probe.probe_catalog_data_source("Apparel", "01", tmp_path, lambda _l: None)

    assert result["code"] == "CATALOG_PROBE_NOT_READY"
    assert result["request_count"] == 1
    with open(result["file_path"], encoding="utf-8") as handle:
        report = json.load(handle)
    assert report["note"].startswith("Một phần")


# --- controller -------------------------------------------------------------


def test_only_an_admin_account_can_run_the_probe(tmp_path):
    api, fake = make_api(tmp_path)
    api._admin_access = False

    result = api.probe_catalog_data_source("Apparel")

    assert result["code"] == "ADMIN_ACCESS_DENIED"
    assert not any(call[0] == "probe_catalog_data_source" for call in fake.calls)


def test_the_probe_writes_into_the_app_data_diagnostics_folder(tmp_path):
    api, fake = make_api(tmp_path)
    api._admin_access = True
    seen = {}

    def fake_probe(category_name, category_value, output_dir, log, *, app_version):
        seen.update(
            category=category_name,
            value=category_value,
            output_dir=output_dir,
            version=app_version,
        )
        return {
            "ok": True,
            "code": "CATALOG_DATA_SOURCE_PROBED",
            "message": "ok",
            "file_path": str(output_dir / "x.json"),
        }

    fake.probe_catalog_data_source = fake_probe

    result = api.probe_catalog_data_source("Apparel")

    assert result["code"] == "CATALOG_DATA_SOURCE_PROBED"
    assert seen["output_dir"] == tmp_path / "diagnostics"
    assert seen["value"] == "01"
    assert seen["version"]
    assert api._catalog.prepared_category == "Apparel"
