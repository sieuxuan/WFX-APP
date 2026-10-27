"""Lấy toàn bộ Article qua WFXCommon/GetData bằng các truy vấn ``contains``.

Server WFX cắt mọi kết quả ở 100 dòng mới nhất và bỏ qua phân trang, nên tính
đúng của extractor nằm trọn trong planner: với một server giả cùng luật cắt,
planner phải thu ĐỦ mọi mã, kể cả mã lệch khuôn, mà không nổ số truy vấn.
"""

from __future__ import annotations

import csv
import io

import pytest

from tests.test_panel_api import make_api
from wfx_panel.automation.catalog import article_extract as extract
from wfx_panel.automation.catalog import article_partition as partition


def _serve(codes):
    newest_first = sorted(codes, reverse=True)

    def answer(query):
        return [
            {"code": code, "name": f"Name {code}"}
            for code in newest_first
            if query.upper() in code.upper()
        ][: partition.SERVER_ROW_CAP]

    return answer


def _drain(codes, **kwargs):
    planner = partition.PartitionPlanner(**kwargs)
    answer = _serve(codes)
    while not planner.done:
        for query in planner.next_batch(8):
            planner.record(query, answer(query))
    return planner


def test_a_small_category_is_finished_by_the_unfiltered_query():
    planner = _drain([f"SV{n:03d}" for n in range(40)])

    assert planner.query_count == 1
    assert len(planner.rows) == 40


def test_every_code_of_large_sequential_families_is_found():
    codes = [f"SWV{n:07d}" for n in range(1, 2600)] + [
        f"SKN{n:07d}" for n in range(1, 900)
    ]

    planner = _drain(codes)

    assert set(planner.rows) == set(codes)
    # Không duyệt lại họ mã dưới gốc giữa mã như W/V/K/N.
    assert planner.query_count < 600
    assert planner.assumed_complete_blocks > 0


def test_codes_that_break_the_pattern_are_not_lost():
    codes = (
        [f"T{n:07d}" for n in range(1, 1500)]
        + ["T0000123A", "T0000123-B", "T00001/7", "9ABC001", "XYZ"]
        + [f"0{n:05d}" for n in range(1, 300)]
    )

    planner = _drain(codes)

    assert set(planner.rows) == {c.upper() for c in codes}


def test_a_filter_the_server_ignores_is_not_expanded():
    codes = [f"SWV{n:07d}" for n in range(1, 400)]
    answer = _serve(codes)

    def server(query):
        # WFX cắt khoảng trắng và coi "_" là ký tự đại diện: trả 100 mã mới nhất.
        return answer("" if query.strip(" _") == "" else query)

    planner = partition.PartitionPlanner()
    while not planner.done:
        for query in planner.next_batch(8):
            planner.record(query, server(query))

    assert set(planner.rows) == set(codes)
    assert {" ", "_"} <= set(planner.ignored_queries)
    assert not any(q.startswith((" ", "_")) and len(q) > 1 for q in planner.queried)


def test_query_budget_stops_the_planner():
    planner = _drain([f"SWV{n:07d}" for n in range(1, 3000)], max_queries=20)

    assert planner.exhausted
    assert planner.query_count == 20


def test_full_digit_block_needs_all_hundred_two_digit_suffixes():
    block = [f"SKN00012{n:02d}" for n in range(100)]

    assert partition.is_full_digit_block("SKN00012", block)
    assert not partition.is_full_digit_block("SKN00012", block[:-1] + ["SKN0001299X"])
    assert not partition.is_full_digit_block("SKN0001", block)


def test_csv_matches_the_article_list_layout():
    text = partition.articles_csv(
        {
            "Trims": [{"code": "T2", "name": "Zip  #5", "buyer_reference": ""}],
            "Apparel": [
                {"code": "SKN2", "name": "Polo", "buyer_reference": "JL-1"},
                {"code": "SKN1", "name": "Tee, men", "buyer_reference": None},
            ],
        }
    )

    rows = list(csv.reader(io.StringIO(text)))
    assert rows == [
        ["Article_Code", "Article_Name", "Buyer_Reference", "Article_Category"],
        ["SKN1", "Tee, men", "", "Apparel"],
        ["SKN2", "Polo", "JL-1", "Apparel"],
        ["T2", "Zip #5", "", "Trims"],
    ]


# --- flow với page giả ------------------------------------------------------


class _FakePage:
    def __init__(self, codes_by_category, *, guid=True, fail=None):
        self.answers = {cat: _serve(codes) for cat, codes in codes_by_category.items()}
        self.guid = guid
        self.fail = fail
        self.calls = 0

    def evaluate(self, script, args):
        assert "WFXCommon" not in script or args["path"] == extract.GET_DATA_PATH
        self.calls += 1
        if not self.guid:
            return {"error": "GUID_MISSING"}
        results = []
        for query in args["queries"]:
            if self.fail:
                results.append({"query": query, "error": self.fail})
                continue
            rows = self.answers[args["catCode"]](query)
            results.append({"query": query, "rows": rows})
        return {"results": results}


class _FakePlaywright:
    stopped = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True


@pytest.fixture
def wire(monkeypatch):
    playwright = _FakePlaywright()
    state = {}

    def connect(_playwright, *, bring_to_front=True):
        state["bring_to_front"] = bring_to_front
        return object(), state["page"]

    monkeypatch.setattr(extract, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(extract, "sync_playwright", lambda: playwright)
    monkeypatch.setattr(extract, "_connect_to_chrome", connect)
    monkeypatch.setattr(extract, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(extract, "checkpoint", lambda: None)

    def install(page):
        state["page"] = page
        return state

    return install, playwright


def test_extract_writes_one_csv_for_every_category(tmp_path, wire):
    install, playwright = wire
    state = install(
        _FakePage(
            {
                "01": [f"SWV{n:07d}" for n in range(1, 400)],
                "05": ["T0000001", "T0000002"],
            }
        )
    )

    result = extract.extract_catalog_articles(
        {"Apparel": "01", "Trims": "05"}, tmp_path, lambda _line: None
    )

    assert result["code"] == "CATALOG_ARTICLES_EXTRACTED"
    assert state["bring_to_front"] is False, "không được kéo người dùng khỏi tab đang làm"
    assert result["categories"]["Apparel"]["article_count"] == 399
    assert result["categories"]["Trims"]["query_count"] == 1
    with open(result["file_path"], encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 401
    assert {row["Article_Category"] for row in rows} == {"Apparel", "Trims"}
    assert playwright.stopped


def test_missing_session_guid_is_reported_without_writing(tmp_path, wire):
    install, _ = wire
    install(_FakePage({"01": ["S1"]}, guid=False))

    result = extract.extract_catalog_articles({"Apparel": "01"}, tmp_path, lambda _l: None)

    assert result["code"] == "CATALOG_EXTRACT_SESSION_MISSING"
    assert not list(tmp_path.iterdir())


def test_a_rejected_query_stops_with_a_redacted_message(tmp_path, wire):
    install, _ = wire
    install(_FakePage({"01": ["S1"]}, fail="HTTP 500 password=hunter2"))

    result = extract.extract_catalog_articles({"Apparel": "01"}, tmp_path, lambda _l: None)

    assert result["code"] == "CATALOG_EXTRACT_FAILED"
    assert "hunter2" not in result["message"]


def test_a_category_over_budget_is_saved_as_partial(tmp_path, wire, monkeypatch):
    install, _ = wire
    install(_FakePage({"01": [f"SWV{n:07d}" for n in range(1, 3000)]}))
    monkeypatch.setattr(extract, "MAX_QUERIES_PER_CATEGORY", 10)

    result = extract.extract_catalog_articles({"Apparel": "01"}, tmp_path, lambda _l: None)

    assert result["code"] == "CATALOG_ARTICLES_PARTIAL"
    assert result["file_path"]
    assert result["categories"]["Apparel"]["complete"] is False


def test_the_browser_must_be_open(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "_chrome_is_ready", lambda: False)

    result = extract.extract_catalog_articles({"Apparel": "01"}, tmp_path)

    assert result["code"] == "CHROME_CLOSED"


# --- controller -------------------------------------------------------------


def test_only_an_admin_can_extract_articles(tmp_path):
    api, _fake = make_api(tmp_path)
    api._admin_access = False

    assert api.extract_catalog_articles([])["code"] == "ADMIN_ACCESS_DENIED"


def test_an_unknown_category_is_rejected_before_touching_chrome(tmp_path):
    api, fake = make_api(tmp_path)
    api._admin_access = True

    result = api.extract_catalog_articles(["Shoes"])

    assert result["code"] == "CATEGORY_UNKNOWN"
    assert not any(call[0] == "extract_catalog_articles" for call in fake.calls)


def test_an_empty_selection_extracts_every_category_into_exports(tmp_path):
    api, fake = make_api(tmp_path)
    api._admin_access = True
    seen = {}

    def fake_extract(categories, output_dir, log, *, app_version):
        seen.update(categories=categories, output_dir=output_dir)
        return {"ok": True, "code": "CATALOG_ARTICLES_EXTRACTED", "message": "ok"}

    fake.extract_catalog_articles = fake_extract

    result = api.extract_catalog_articles([])

    assert result["code"] == "CATALOG_ARTICLES_EXTRACTED"
    assert seen["output_dir"] == tmp_path / "exports"
    assert seen["categories"]["Apparel"] == "01"
    assert len(seen["categories"]) == 6
