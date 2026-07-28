from wfx_panel.automation import directory


class _Field:
    def __init__(self):
        self.value = ""

    def wait_for(self, **_kwargs):
        return None

    def fill(self, value):
        self.value = value

    def type(self, value, **_kwargs):
        self.value += value

    def input_value(self, **_kwargs):
        return self.value

    def press(self, *_args, **_kwargs):
        return None


class _Locator:
    def __init__(self, field=None, count=0):
        self._field = field
        self._count = count

    def count(self):
        return self._count

    def wait_for(self, **kwargs):
        return self._field.wait_for(**kwargs)

    def fill(self, value):
        return self._field.fill(value)

    def type(self, value, **kwargs):
        return self._field.type(value, **kwargs)

    def input_value(self, **kwargs):
        return self._field.input_value(**kwargs)

    def press(self, *args, **kwargs):
        return self._field.press(*args, **kwargs)


class _CompanyFrame:
    def __init__(self, marker, rows):
        self.marker = marker
        self.rows = rows
        self.field = _Field()
        self.row_reads = 0

    def locator(self, selector):
        if selector == "#txtCompanyName":
            return _Locator(self.field, count=1)
        return _Locator(count=0)

    def evaluate(self, script, _argument=None):
        if "partyType" in script:
            return self.marker
        self.row_reads += 1
        return {
            "rows": self.rows,
            "noRows": not self.rows,
            "loading": False,
        }


class _Page:
    def __init__(self, frames, clock):
        self.frames = frames
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        self.clock[0] += milliseconds / 1000


def test_company_marker_requires_the_expected_party_type():
    supplier = "wfxPartyGroup PartyType=2 Supplier List"
    buyer = "wfxPartyGroup PartyType=1 Buyer List"

    assert directory._company_marker_matches(supplier, "supplier")
    assert not directory._company_marker_matches(supplier, "buyer")
    assert directory._company_marker_matches(buyer, "buyer")
    assert not directory._company_marker_matches(buyer, "supplier")


def test_company_filter_keeps_the_original_buyer_context(monkeypatch):
    clock = [0.0]
    supplier = _CompanyFrame(
        "wfxPartyGroup PartyType=2 Supplier List",
        [{"company": "Wrong Supplier", "hasEdit": True, "matches": True}],
    )
    buyer = _CompanyFrame(
        "wfxPartyGroup PartyType=1 Buyer List",
        [{"company": "Right Buyer", "hasEdit": True, "matches": True}],
    )
    page = _Page([supplier, buyer], clock)
    monkeypatch.setattr(directory.time, "monotonic", lambda: clock[0])

    resolved, state = directory._filter_company_rows(
        page,
        buyer,
        "Right",
        lambda _message: None,
        "buyer",
    )

    assert resolved is buyer
    assert state["rows"][0]["company"] == "Right Buyer"
    assert buyer.row_reads > 0
    assert supplier.row_reads == 0


def test_supplier_search_continues_after_one_category_fails(monkeypatch):
    class _Playwright:
        def stop(self):
            return None

    class _Starter:
        def start(self):
            return _Playwright()

    rows = {
        "Apparel": [
            {
                "company": f"Apparel Supplier {index}",
                "hasEdit": True,
                "matches": True,
            }
            for index in range(12)
        ],
        "Trims": [
            {
                "company": f"Trim Supplier {index}",
                "hasEdit": True,
                "matches": True,
            }
            for index in range(2)
        ],
    }

    def open_category(_page, _xpath, name, _value, _log):
        if name == "Broken":
            raise directory.PlaywrightTimeoutError("Category timeout")
        return name

    def filter_rows(_page, frame, _query, _log, expected_kind):
        assert expected_kind == "supplier"
        return frame, {"rows": rows[frame], "noRows": False, "loading": False}

    monkeypatch.setattr(directory, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(
        directory,
        "_active_wfx_page",
        lambda _playwright, _log: (object(), object()),
    )
    monkeypatch.setattr(
        directory,
        "_open_supplier_category_on_page",
        open_category,
    )
    monkeypatch.setattr(directory, "_filter_company_rows", filter_rows)

    result = directory.find_supplier_across_categories(
        "//supplier",
        {"Apparel": "01", "Trims": "05", "Broken": "99"},
        "Supplier",
        lambda _message: None,
    )

    assert result["ok"] is True
    assert result["code"] == "SUPPLIER_FOUND_PARTIAL"
    assert "14 kết quả" in result["message"]
    assert result["matches_by_category"][0]["count"] == 12
    assert len(result["matches_by_category"][0]["matches"]) == 10
    assert result["failed_categories"][0]["category"] == "Broken"
