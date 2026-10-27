"""Đường nhanh tìm theo Article Code qua GetData của Catalog Grid.

Đường nhanh chỉ được phép rút ngắn, không được đổi kết quả: 0 Code không mở gì,
nhiều Code giữ để user chọn, chỉ mở khi đúng một Code (hoặc đúng một exact
Code). Mọi tình huống không chắc chắn phải trả ``None`` để flow quay về state
machine DOM — test ở đây khóa từng nhánh đó, và khóa luôn URL popup phải y hệt
nút Code của WFX (đo trên WFX thật 27/10/2026).

Phần JS gửi vào Chrome được chạy thật bằng Node ở cuối file.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from wfx_panel.automation.catalog import quick_find

QUERY = "PSG0000002"


def _row(code, article_id="7740011351", group_id="77400636", **extra):
    return {
        "code": code,
        "article_id": article_id,
        "group_id": group_id,
        "season": extra.pop("season", "SS26"),
        "costsheet_status": extra.pop("costsheet_status", ""),
        "link_disabled": extra.pop("link_disabled", False),
        **extra,
    }


class FakeGrid:
    def __init__(self, response=None, *, open_returns=True, error=None):
        self.response = response
        self.open_returns = open_returns
        self.error = error
        self.fetches: list[dict] = []
        self.opened: list[dict] = []

    def evaluate(self, script, arg=None):
        if script is quick_find._FIND_CODE_JS:
            if self.error is not None:
                raise self.error
            self.fetches.append(arg)
            return self.response
        if script is quick_find._OPEN_ARTICLE_JS:
            self.opened.append(arg)
            return self.open_returns
        raise AssertionError(f"script lạ: {script[:60]}")


def _ok(*rows, company="77400", catalog_type="1"):
    return {"company": company, "catalogType": catalog_type, "rows": list(rows)}


@pytest.fixture
def grid_on_page(monkeypatch):
    holder = {"grid": None}

    def frame(_page, timeout_seconds):
        if holder["grid"] is None:
            raise PlaywrightTimeoutError("không có grid")
        return holder["grid"]

    monkeypatch.setattr(quick_find, "_catalog_grid_frame", frame)
    return holder


def _find(holder, grid, query=QUERY, category="01"):
    holder["grid"] = grid
    lines: list[str] = []
    result = quick_find._quick_find_catalog_code(object(), category, query, lines.append)
    return result, lines


# --- mở đúng một Code ------------------------------------------------------


def test_one_exact_code_opens_the_same_url_as_the_wfx_code_button(grid_on_page):
    grid = FakeGrid(_ok(_row(QUERY)))

    result, _ = _find(grid_on_page, grid)

    assert result["code"] == "RESULT_OPENED"
    assert result["article_code"] == QUERY
    assert grid.opened == [
        {
            "url": (
                "/wfx/wfx_ArticleDetail.aspx?ID=7740011351&GroupID=77400636"
                "&ArticleSelection=&CatalogType=1&CatalogCompany=77400"
                "&ComboCode=01&StyleSheet=wfx_Style"
            ),
            "name": "ArticleDetail",
        }
    ]
    assert grid.fetches[0]["catCode"] == "01"
    assert grid.fetches[0]["query"] == QUERY


def test_the_exact_code_wins_over_codes_that_merely_contain_it(grid_on_page):
    grid = FakeGrid(
        _ok(
            _row("PSG0000002A", article_id="1"),
            _row("psg0000002", article_id="2"),
            _row("PSG0000002-B", article_id="3"),
        )
    )

    result, _ = _find(grid_on_page, grid)

    assert result["code"] == "RESULT_OPENED"
    assert result["article_code"] == "psg0000002"
    assert "ID=2&" in grid.opened[0]["url"]


def test_a_single_contained_code_opens_like_the_grid_does(grid_on_page):
    grid = FakeGrid(_ok(_row("PSG0000002")))

    result, _ = _find(grid_on_page, grid, query="PSG000000")

    assert result["code"] == "RESULT_OPENED"
    assert grid.opened


def test_duplicate_rows_of_one_code_count_as_one(grid_on_page):
    grid = FakeGrid(_ok(_row("ABC-1"), _row("abc-1"), _row("ABC-1")))

    result, _ = _find(grid_on_page, grid, query="ABC")

    assert result["code"] == "RESULT_OPENED"
    assert result["codes"] == ["ABC-1"]


def test_the_opened_style_carries_season_and_costsheet_status(grid_on_page):
    grid = FakeGrid(_ok(_row(QUERY, season="FW26", costsheet_status="Approved")))

    result, _ = _find(grid_on_page, grid)

    assert result["style_status"] == {
        "code": QUERY,
        "season": "FW26",
        "internal_costsheet_status": "Approved",
    }
    assert "Season: FW26" in result["message"]


# --- 0 / nhiều Code -----------------------------------------------------------


def test_no_rows_is_no_results_and_nothing_is_opened(grid_on_page):
    grid = FakeGrid(_ok())

    result, _ = _find(grid_on_page, grid)

    assert result["ok"] is False
    assert result["code"] == "NO_RESULTS"
    assert grid.opened == []


def test_several_codes_without_an_exact_match_wait_for_the_user(grid_on_page):
    rows = [_row(f"PSG00000{index:02d}", article_id=str(index)) for index in range(30)]
    grid = FakeGrid(_ok(*rows))

    result, _ = _find(grid_on_page, grid, query="PSG00000")

    assert result["ok"] is True
    assert result["code"] == "MULTIPLE_RESULTS"
    assert grid.opened == []
    assert len(result["styles"]) == quick_find.MAX_STYLES
    assert result["styles"][0] == {
        "code": "PSG0000000",
        "season": "SS26",
        "internal_costsheet_status": "",
    }
    assert result["codes"] == [style["code"] for style in result["styles"]]


# --- mọi tình huống không chắc chắn: nhường cho luồng DOM ---------------------


def test_no_live_catalog_grid_falls_back_to_the_dom_flow(grid_on_page):
    result, _ = _find(grid_on_page, None)

    assert result is None


def test_an_unknown_category_never_touches_the_page(grid_on_page):
    grid = FakeGrid(_ok(_row(QUERY)))

    result, _ = _find(grid_on_page, grid, category="")

    assert result is None
    assert grid.fetches == []


@pytest.mark.parametrize(
    "response",
    [
        {"error": "SESSION_MISSING"},
        {"error": "HTTP 500"},
        {"error": "timeout"},
        None,
        "lạ",
    ],
)
def test_a_failed_or_unreadable_fetch_falls_back(grid_on_page, response):
    grid = FakeGrid(response)

    result, lines = _find(grid_on_page, grid)

    assert result is None
    assert grid.opened == []
    assert any("dùng grid" in line for line in lines)


def test_a_frame_that_dies_during_the_fetch_falls_back(grid_on_page):
    grid = FakeGrid(error=PlaywrightError("Execution context was destroyed"))

    result, _ = _find(grid_on_page, grid)

    assert result is None


def test_rows_that_ignore_the_filter_are_never_read_as_no_results(grid_on_page):
    """Server trả 100 Style mới nhất thay vì lọc: không kết luận NO_RESULTS."""
    grid = FakeGrid(_ok(_row("PSG0000999"), _row("F0000001")))

    result, lines = _find(grid_on_page, grid, query="ZZZ")

    assert result is None
    assert any("không áp điều kiện lọc" in line for line in lines)


def test_a_style_whose_catalog_link_is_disabled_falls_back(grid_on_page):
    grid = FakeGrid(_ok(_row(QUERY, link_disabled=True)))

    result, _ = _find(grid_on_page, grid)

    assert result is None
    assert grid.opened == []


@pytest.mark.parametrize(
    ("row", "company", "catalog_type"),
    [
        (_row(QUERY, article_id=""), "77400", "1"),
        (_row(QUERY, article_id="12a"), "77400", "1"),
        (_row(QUERY, group_id="None"), "77400", "1"),
        (_row(QUERY), "", "1"),
        (_row(QUERY), "77 400", "1"),
        (_row(QUERY), "77400", ""),
    ],
)
def test_missing_link_parts_fall_back_instead_of_guessing(
    grid_on_page, row, company, catalog_type
):
    grid = FakeGrid(_ok(row, company=company, catalog_type=catalog_type))

    result, _ = _find(grid_on_page, grid)

    assert result is None
    assert grid.opened == []


def test_a_blocked_popup_falls_back(grid_on_page):
    grid = FakeGrid(_ok(_row(QUERY)), open_returns=False)

    result, lines = _find(grid_on_page, grid)

    assert result is None
    assert any("không mở được popup" in line for line in lines)


# --- JS gửi vào Chrome, chạy thật bằng Node ------------------------------------

node = shutil.which("node")

HARNESS = r"""
const script = __SCRIPT__;
const run = async (storage, fetchImpl, search) => {
  const calls = [];
  globalThis.sessionStorage = {getItem: key => storage[key] ?? null};
  globalThis.localStorage = {getItem: () => null};
  globalThis.location = {search};
  globalThis.fetch = async (path, init) => { calls.push({path, init}); return fetchImpl(); };
  const fn = eval(script);
  const result = await fn({path: '/api', catCode: '01', query: 'PSG0000002', timeoutMs: 1000});
  return {result, calls};
};
const okBody = {ResponseData: [{
  ArticleCode: ' PSG0000002 ', ArticleID: 7740011351, CGID: 77400636, Season: 'SS26',
  CostsheetStatus: null, DisableCatalogLink: 1,
}]};
(async () => {
  const out = {};
  out.ok = await run({GUID: 'g-1', CompanyCode: '77400'},
    () => ({ok: true, status: 200, json: async () => okBody}), '?CatalogType=1&ComboCode=01');
  out.noGuid = await run({CompanyCode: '77400'}, () => { throw new Error('không được gọi'); }, '');
  out.http = await run({GUID: 'g', CompanyCode: '1'},
    () => ({ok: false, status: 500, json: async () => ({})}), '');
  out.fail = await run({GUID: 'g', CompanyCode: '1'},
    () => ({ok: true, status: 200, json: async () => ({Status: 'Fail'})}), '');
  process.stdout.write(JSON.stringify(out));
})().catch(error => { process.stdout.write(JSON.stringify({error: String(error.stack)})); });
"""


@pytest.fixture(scope="module")
def js_outcomes(tmp_path_factory):
    if node is None:
        pytest.skip("Cần Node để chạy script GetData")
    script = tmp_path_factory.mktemp("quick_find") / "harness.js"
    script.write_text(
        HARNESS.replace("__SCRIPT__", json.dumps("(" + quick_find._FIND_CODE_JS + ")")),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [node, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    outcome = json.loads(completed.stdout)
    assert "error" not in outcome, outcome.get("error")
    return outcome


def test_the_request_carries_the_grid_headers_and_a_contains_code_filter(js_outcomes):
    call = js_outcomes["ok"]["calls"][0]
    headers = call["init"]["headers"]
    assert call["path"] == "/api"
    assert call["init"]["credentials"] == "include"
    page_params = {item["ParamName"]: item["ParamValue"] for item in json.loads(headers["pageparams"])}
    assert page_params["ProductCatCode"] == "01"
    assert page_params["ParentNodeCode"] == "Master"
    assert page_params["GUID"] == "g-1"
    search = json.loads(headers["searchparams"])
    assert search[0] == {"ParamName": "lnkArticleCode", "ParamValue": "PSG0000002"}
    assert search[2]["ParamValue"][0]["c1filterTypeOperator"] == "contains"
    assert json.loads(headers["pagingparams"]) == {"PageIndex": 0, "PageSize": 0}


def test_rows_are_reduced_to_the_fields_the_popup_link_needs(js_outcomes):
    assert js_outcomes["ok"]["result"] == {
        "company": "77400",
        "catalogType": "1",
        "rows": [
            {
                "code": "PSG0000002",
                "article_id": "7740011351",
                "group_id": "77400636",
                "season": "SS26",
                "costsheet_status": "",
                "link_disabled": True,
            }
        ],
    }


def test_a_tab_without_the_catalog_guid_never_calls_the_server(js_outcomes):
    assert js_outcomes["noGuid"] == {"result": {"error": "SESSION_MISSING"}, "calls": []}


@pytest.mark.parametrize("case", ["http", "fail"])
def test_server_failures_are_reported_not_read_as_empty(js_outcomes, case):
    assert js_outcomes[case]["result"]["error"].startswith("HTTP")
