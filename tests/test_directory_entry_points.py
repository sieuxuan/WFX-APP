"""Buyer/Supplier: đúng PartyType, và tìm qua nhiều Category không bỏ sót.

`directory.py` ở mức 34%. Hai ràng buộc CLAUDE.md nằm ở phần chưa được test:

* "Buyer/Supplier chỉ được resolve lại frame **cùng PartyType** với flow ban
  đầu." Hai màn dùng chung `#txtCompanyName`, nên nhận nhầm frame là tìm Buyer
  trên màn Supplier.
* "Search tất cả Supplier Category phải **tiếp tục** khi một Category lỗi, báo
  rõ kết quả một phần và **đếm tổng trước khi giới hạn** danh sách hiển thị."
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import directory

MODULE_XPATH = '//*[@id="0002_1000"]/a'
CATEGORIES = {"Fabric": "01", "Trims": "02", "Service": "03"}


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, directory)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _quiet():
    return lambda _line: None


# --- PartyType: không nhận nhầm màn Buyer/Supplier ---------------------


@pytest.mark.parametrize(
    "marker",
    [
        "wfxcompany.aspx?partytype=2 supplier list",
        "SUPPLIER MASTER",
        "…PartyType=2…",
    ],
)
def test_a_supplier_screen_is_accepted_for_supplier(marker):
    assert directory._company_marker_matches(marker, "supplier") is True
    assert directory._company_marker_matches(marker, "buyer") is False


@pytest.mark.parametrize(
    "marker",
    ["wfxcompany.aspx?partytype=1 buyer list", "BUYER MASTER"],
)
def test_a_buyer_screen_is_accepted_for_buyer(marker):
    assert directory._company_marker_matches(marker, "buyer") is True
    assert directory._company_marker_matches(marker, "supplier") is False


def test_a_frame_mentioning_both_parties_is_refused_by_both():
    """Menu WFX liệt kê cả hai; frame như vậy không đủ chắc để dùng."""
    marker = "wfx menu: buyer list | supplier list"

    assert directory._company_marker_matches(marker, "buyer") is False
    assert directory._company_marker_matches(marker, "supplier") is False


@pytest.mark.parametrize("marker", ["", "company master", "wfxcompany.aspx"])
def test_a_generic_company_frame_is_never_accepted(marker):
    """`#txtCompanyName` có ở cả hai màn nên frame chung chung phải bị loại."""
    assert directory._company_marker_matches(marker, "buyer") is False
    assert directory._company_marker_matches(marker, "supplier") is False


@pytest.mark.parametrize("kind", ["", "company", "both", None])
def test_an_unknown_expected_kind_matches_nothing(kind):
    assert directory._company_marker_matches("partytype=2", kind) is False


def test_the_buyer_frame_helper_asks_for_the_buyer_party_type(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        directory,
        "_company_search_frame",
        lambda _page, kind, timeout_s=4: seen.setdefault("kind", kind),
    )

    directory._buyer_search_frame(object())

    assert seen["kind"] == "buyer", (
        "Dùng nhầm PartyType sẽ mở Edit của Supplier khi user tìm Buyer"
    )


# --- Tìm Supplier qua nhiều Category -----------------------------------


class _Scan:
    """Giả lập kết quả mỗi Category: danh sách công ty khớp, hoặc lỗi."""

    def __init__(self, by_category):
        self.by_category = by_category
        self.opened: list[str] = []

    def open_category(self, _page, _xpath, category_name, _value, _log):
        self.opened.append(category_name)
        outcome = self.by_category.get(category_name)
        if isinstance(outcome, Exception):
            raise outcome
        return f"frame-{category_name}"

    def filter_rows(self, _page, frame, _query, _log, kind):
        assert kind == "supplier", "Quét Supplier không được dùng PartyType khác"
        category = str(frame).removeprefix("frame-")
        companies = self.by_category.get(category) or []
        return frame, {
            "rows": [{"company": name, "matches": True} for name in companies]
        }


def _wire_scan(monkeypatch, scan: _Scan) -> None:
    monkeypatch.setattr(
        directory, "_open_supplier_category_on_page", scan.open_category
    )
    monkeypatch.setattr(directory, "_filter_company_rows", scan.filter_rows)


def _search(world, query="ABC"):
    return directory.find_supplier_across_categories(
        MODULE_XPATH,
        CATEGORIES,
        query,
        _quiet(),
    )


def test_a_blank_query_never_opens_the_browser(monkeypatch, world):
    wire_automation(monkeypatch, directory, world)

    result = _search(world, "   ")

    assert result["code"] == "QUERY_REQUIRED"
    assert world.driver_starts == 0


def test_every_category_is_checked_even_after_a_match(monkeypatch, world):
    wire_automation(monkeypatch, directory, world)
    scan = _Scan({"Fabric": ["ABC Ltd"], "Trims": [], "Service": ["ABC Co"]})
    _wire_scan(monkeypatch, scan)

    result = _search(world)

    assert result["code"] == "SUPPLIER_FOUND"
    assert result["checked_categories"] == ["Fabric", "Trims", "Service"]
    assert result["categories"] == ["Fabric", "Service"]
    assert result["category"] == "Fabric", "Phải đưa WFX về Category đầu tiên"


def test_a_failing_category_does_not_stop_the_scan(monkeypatch, world):
    """Một Category lỗi vẫn phải kiểm tiếp các Category còn lại."""
    wire_automation(monkeypatch, directory, world)
    scan = _Scan(
        {
            "Fabric": directory.PlaywrightTimeoutError("grid chưa render"),
            "Trims": ["ABC Ltd"],
            "Service": [],
        }
    )
    _wire_scan(monkeypatch, scan)

    result = _search(world)

    assert result["ok"] is True
    assert result["code"] == "SUPPLIER_FOUND_PARTIAL"
    assert [item["category"] for item in result["failed_categories"]] == ["Fabric"]
    assert scan.opened[:3] == ["Fabric", "Trims", "Service"]
    assert "chưa kiểm tra được" in result["message"]


def test_no_match_but_a_failed_category_is_reported_as_partial(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, directory, world)
    scan = _Scan(
        {
            "Fabric": [],
            "Trims": directory.PlaywrightError("frame detach"),
            "Service": [],
        }
    )
    _wire_scan(monkeypatch, scan)

    result = _search(world)

    assert result["ok"] is False
    assert result["code"] == "SUPPLIER_SEARCH_PARTIAL"
    assert result["checked_categories"] == ["Fabric", "Trims", "Service"]


def test_no_match_anywhere_says_how_many_categories_were_checked(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, directory, world)
    _wire_scan(monkeypatch, _Scan({name: [] for name in CATEGORIES}))

    result = _search(world)

    assert result["code"] == "SUPPLIER_NOT_FOUND"
    assert "3 Category" in result["message"]


def test_the_total_is_counted_before_the_display_list_is_capped(
    monkeypatch,
    world,
):
    """CLAUDE.md: đếm tổng TRƯỚC khi giới hạn danh sách hiển thị."""
    wire_automation(monkeypatch, directory, world)
    many = [f"ABC {index:02d}" for index in range(25)]
    _wire_scan(monkeypatch, _Scan({"Fabric": many, "Trims": [], "Service": []}))

    result = _search(world)

    assert "25 kết quả" in result["message"]
    assert len(result["matches"]) == 10, "Danh sách hiển thị vẫn bị giới hạn 10"
    assert result["matches_by_category"][0]["count"] == 25


def test_duplicate_company_names_are_counted_once(monkeypatch, world):
    wire_automation(monkeypatch, directory, world)
    _wire_scan(
        monkeypatch,
        _Scan({"Fabric": ["ABC Ltd", "ABC Ltd", "ABC Co"], "Trims": [], "Service": []}),
    )

    result = _search(world)

    assert result["matches"] == ["ABC Ltd", "ABC Co"]
    assert "2 kết quả" in result["message"]


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_are_reported(
    monkeypatch,
    world,
    ready,
    logged_in,
    expected,
):
    wire_automation(
        monkeypatch,
        directory,
        world,
        chrome_ready=ready,
        logged_in=logged_in,
    )

    result = _search(world)

    assert result["code"] == expected
    assert world.driver_stops == 1


def test_an_unexpected_error_keeps_the_categories_already_checked(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, directory, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi DOM")

    monkeypatch.setattr(directory, "_scan_supplier_categories", boom)

    result = _search(world)

    assert result["code"] == "SUPPLIER_SEARCH_FAILED"
    assert result["checked_categories"] == []
    assert world.driver_stops == 1
