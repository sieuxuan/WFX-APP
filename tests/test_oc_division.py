"""OC No. mang Division trong tiền tố: tìm theo OC No. phải đổi Division trước."""

from __future__ import annotations

import pytest

from wfx_panel.controllers.catalog import CatalogController
from wfx_panel.controllers.modules import ModulesController
from wfx_panel.controllers.oc_division import oc_no_division


@pytest.mark.parametrize(
    ("oc_no", "expected"),
    [
        ("PSG-ONL-26-170.1", "pssg"),
        ("PSW-JLD-26-6242.1", "woven"),
        ("PSK-PARAGON-26-3374.2", "knit"),
        ("  psk-paragon-26-3374.2 ", "knit"),
        ("170.1", None),
        ("JLD-26-6242.1", None),
        ("PSWX-JLD-26", None),
        ("", None),
    ],
)
def test_tien_to_oc_no_quyet_dinh_division(oc_no, expected):
    assert oc_no_division(oc_no) == expected


class _Login:
    def __init__(self, switch_code: str = "DIVISION_CHANGED") -> None:
        self.switch_code = switch_code
        self.calls: list[tuple] = []
        self.menu_resets = 0

    def switch_division(self, key, log=print):
        self.calls.append(("switch_division", key))
        ok = self.switch_code in {"DIVISION_CHANGED", "DIVISION_ALREADY_ACTIVE"}
        return {
            "ok": ok,
            "code": self.switch_code,
            "message": "ok" if ok else "WFX từ chối.",
            "current_division": key if ok else "pssg",
            "division_label": key.upper() if ok else "PSSG",
            "division_name": "Pro Sports",
        }

    def reset_menu_route_cache(self):
        self.menu_resets += 1

    def search_oc_list(self, xpath, filter_kind, query, log=print):
        self.calls.append(("search", filter_kind, query))
        return {
            "ok": True,
            "code": "MODULE_SEARCH_APPLIED",
            "message": "Đã lọc OC List.",
        }


class _Panel:
    def __init__(self, login):
        self._login = login
        self._catalog = CatalogController(self)
        self.catalog_resets = 0
        self._catalog.reset_context = self._count_catalog_reset

    def _count_catalog_reset(self):
        self.catalog_resets += 1

    def _log(self, message):
        pass

    def _run(self, method, action, meta=None):
        return action()


def _search(login, kind, query):
    panel = _Panel(login)
    return panel, ModulesController(panel).search_oc(kind, query)


def test_oc_no_cua_division_khac_doi_division_roi_moi_tim():
    login = _Login()
    panel, result = _search(login, "oc_no", "PSK-PARAGON-26-3374.2")

    assert login.calls == [
        ("switch_division", "knit"),
        ("search", "oc_no", "PSK-PARAGON-26-3374.2"),
    ]
    assert result["ok"] is True
    assert result["current_division"] == "knit"
    assert result["message"].startswith("Đã tự chuyển sang Division KNIT.")
    # WFX vừa nạp lại trang: route menu và context Catalog cũ không còn dùng được.
    assert login.menu_resets == 1
    assert panel.catalog_resets == 1


def test_dang_dung_division_thi_khong_bao_da_doi():
    login = _Login("DIVISION_ALREADY_ACTIVE")
    _panel, result = _search(login, "oc_no", "PSW-JLD-26-6242.1")

    assert login.calls[-1] == ("search", "oc_no", "PSW-JLD-26-6242.1")
    assert result["message"] == "Đã lọc OC List."
    assert result["current_division"] == "woven"
    assert login.menu_resets == 0


def test_doi_division_that_bai_thi_khong_tim_o_division_sai():
    login = _Login("DIVISION_CHANGE_NOT_CONFIRMED")
    _panel, result = _search(login, "oc_no", "PSG-ONL-26-170.1")

    assert login.calls == [("switch_division", "pssg")]
    assert result["ok"] is False
    assert result["code"] == "DIVISION_CHANGE_NOT_CONFIRMED"
    assert "PSSG" in result["message"]
    assert result["module"] == "OC List"


def test_mat_phien_khi_doi_division_giu_nguyen_ma_de_tu_dang_nhap_lai():
    login = _Login("NOT_LOGGED_IN")
    _panel, result = _search(login, "oc_no", "PSG-ONL-26-170.1")

    assert result["code"] == "NOT_LOGGED_IN"
    assert login.calls == [("switch_division", "pssg")]


@pytest.mark.parametrize(
    ("kind", "query"),
    [("style", "PSK-PARAGON-26"), ("oc_no", "3374.2")],
)
def test_tim_theo_style_hoac_oc_no_khong_tien_to_giu_division(kind, query):
    login = _Login()
    _panel, result = _search(login, kind, query)

    assert login.calls == [("search", kind, query)]
    assert "current_division" not in result
