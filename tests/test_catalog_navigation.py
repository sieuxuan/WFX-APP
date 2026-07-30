from __future__ import annotations

import pytest

from wfx_panel.automation import catalog


class _CatalogAnchor:
    def __init__(self, href: str):
        self.href = href

    def get_attribute(self, name: str):
        return self.href if name == "href" else None


class _BodyElement:
    first = None

    def __init__(self):
        self.first = self
        self.waited = False
        self.navigation = None

    def wait_for(self, **_kwargs):
        self.waited = True

    def evaluate(self, _script, value):
        self.navigation = value


class _Page:
    url = "https://example.test/wfx/default.aspx"

    def __init__(self):
        self.body = _BodyElement()

    def locator(self, selector: str):
        assert selector == 'frame[name="body"], iframe[name="body"]'
        return self.body


def test_catalog_direct_url_uses_same_origin_redir_url():
    page = _Page()
    anchor = _CatalogAnchor(
        "wfx_BaseSetting.aspx?MenuName=mnuTechpack"
        "&RedirURL=WFX_CatalogMain.aspx%3FCatalogType=1"
    )

    assert catalog._catalog_direct_url(page, anchor) == (
        "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1"
    )


@pytest.mark.parametrize(
    "href",
    [
        "wfx_BaseSetting.aspx?MenuName=mnuTechpack",
        (
            "wfx_BaseSetting.aspx?RedirURL="
            "https%3A%2F%2Fevil.test%2Fwfx%2FWFX_CatalogMain.aspx"
        ),
        "wfx_BaseSetting.aspx?RedirURL=AnotherModule.aspx",
    ],
)
def test_catalog_direct_url_rejects_missing_or_unsafe_targets(href):
    assert catalog._catalog_direct_url(_Page(), _CatalogAnchor(href)) is None


def test_catalog_menu_falls_back_to_direct_url_when_wrapper_does_not_load(
    monkeypatch,
):
    page = _Page()
    anchor = _CatalogAnchor(
        "wfx_BaseSetting.aspx?MenuName=mnuTechpack"
        "&RedirURL=WFX_CatalogMain.aspx%3FCatalogType=1"
    )
    expected_frame = object()
    waits = []
    clicked = []
    logs = []

    def wait_for_tree(_page, previous_frame=None, timeout_s=10):
        waits.append((previous_frame, timeout_s))
        if len(waits) == 1:
            raise catalog.PlaywrightTimeoutError("wrapper did not load")
        return expected_frame

    monkeypatch.setattr(catalog, "_catalog_left_frame", wait_for_tree)
    monkeypatch.setattr(catalog, "_click", lambda target: clicked.append(target))

    result = catalog._open_catalog_menu_on_page(
        page,
        anchor,
        logs.append,
        previous_frame="old-frame",
    )

    assert result is expected_frame
    assert clicked == [anchor]
    assert waits == [("old-frame", 3), ("old-frame", 30)]
    assert page.body.waited is True
    assert page.body.navigation == (
        "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1"
    )
    assert any("mở trực tiếp" in line for line in logs)


def test_catalog_menu_keeps_normal_navigation_when_wrapper_loads(monkeypatch):
    page = _Page()
    anchor = _CatalogAnchor(
        "wfx_BaseSetting.aspx?RedirURL=WFX_CatalogMain.aspx%3FCatalogType=1"
    )
    expected_frame = object()

    monkeypatch.setattr(catalog, "_click", lambda _target: None)
    monkeypatch.setattr(
        catalog,
        "_catalog_left_frame",
        lambda _page, previous_frame=None, timeout_s=10: expected_frame,
    )

    result = catalog._open_catalog_menu_on_page(page, anchor, lambda _line: None)

    assert result is expected_frame
    assert page.body.navigation is None


def test_catalog_tree_rejects_supplier_category_frame():
    class Locator:
        def count(self):
            return 1

    class Candidate:
        def __init__(self, url):
            self.url = url

        def locator(self, _selector):
            return Locator()

    supplier = Candidate(
        "https://example.test/WFXPartyGroup.aspx?PartyType=2"
    )
    catalog_tree = Candidate(
        "https://example.test/WFXArticleCatalog.aspx?CatalogType=1"
    )

    assert catalog._is_catalog_tree_frame(supplier) is False
    assert catalog._is_catalog_tree_frame(catalog_tree) is True


def test_catalog_left_accepts_same_frame_after_in_place_reload(monkeypatch):
    frame = object()
    monkeypatch.setattr(
        catalog,
        "_catalog_tree_frame_now",
        lambda _page: frame,
    )

    assert catalog._catalog_left_frame(
        object(),
        previous_frame=frame,
        timeout_s=0.1,
    ) is frame


def test_catalog_direct_navigation_prefers_live_body_frame():
    navigations = []

    class BodyFrame:
        def goto(self, url, **options):
            navigations.append((url, options))

    class Page:
        def frame(self, *, name):
            assert name == "body"
            return BodyFrame()

        def locator(self, _selector):
            raise AssertionError("DOM src fallback should not be used")

    catalog._navigate_catalog_body_direct(
        Page(),
        "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1",
    )

    assert navigations == [
        (
            "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1",
            {"wait_until": "domcontentloaded", "timeout": 15_000},
        )
    ]
