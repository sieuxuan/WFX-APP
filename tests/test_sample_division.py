"""Sample No. mang Division trong tiền tố: tìm phải đổi Division trước."""

from __future__ import annotations

import pytest

from wfx_panel.controllers.catalog import CatalogController
from wfx_panel.controllers.modules import ModulesController
from wfx_panel.controllers.sample_division import (
    align_sample_division,
    sample_no_division,
)


@pytest.mark.parametrize(
    ("sample_no", "expected"),
    [
        ("PSG-ONL-26-170", "pssg"),
        ("PSW-JLD-26-6242", "woven"),
        ("PSK-PARAGON-26-3374", "knit"),
        ("  psw-jld-26-6242 ", "woven"),
        ("PSW -JLD-26-6242", "woven"),
        ("6242", None),
        ("JLD-26-6242", None),
        ("PSWX-JLD-26", None),
        ("", None),
    ],
)
def test_tien_to_sample_no_quyet_dinh_division(sample_no, expected):
    assert sample_no_division(sample_no) == expected


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

    def search_sample_list_with_filters(self, xpath, values, log=print):
        self.calls.append(("search", dict(values)))
        return {
            "ok": True,
            "code": "MODULE_SEARCH_APPLIED",
            "message": "Đã lọc Sample List theo Sample Order No..",
        }

    def find_sample_file_results_with_filters(self, xpath, values, log=print):
        self.calls.append(("find", dict(values)))
        return {"ok": False, "code": "NO_RESULTS", "message": "Không có."}


class _Panel:
    def __init__(self, login: _Login) -> None:
        self._login = login
        self._catalog = CatalogController(self)

    def _log(self, _line: str) -> None:
        return None

    def _run(self, method, action, request=None):
        return action()


def test_search_doi_division_roi_moi_tim_va_bao_ro():
    login = _Login()
    panel = _Panel(login)

    result = ModulesController(panel).search_sample(sample_no="PSW-JLD-26-6242")

    assert login.calls == [
        ("switch_division", "woven"),
        (
            "search",
            {
                "sample_no": "PSW-JLD-26-6242",
                "style": "",
                "created_by": "",
                "buyer": "",
            },
        ),
    ]
    assert login.menu_resets == 1
    # Run engine cập nhật Division của panel từ chính các field này.
    assert result["current_division"] == "woven"
    assert result["message"].startswith("Đã tự chuyển sang Division WOVEN.")


def test_dang_dung_division_thi_khong_them_thong_bao():
    login = _Login("DIVISION_ALREADY_ACTIVE")
    panel = _Panel(login)

    result = ModulesController(panel).search_sample(
        sample_no="PSK-PARAGON-26-3374"
    )

    assert [call[0] for call in login.calls] == ["switch_division", "search"]
    assert login.menu_resets == 0
    assert result["message"].startswith("Đã lọc Sample List")


def test_khong_co_tien_to_thi_khong_cham_division():
    login = _Login()
    panel = _Panel(login)

    ModulesController(panel).search_sample(sample_no="6242", buyer="NIKE")

    assert [call[0] for call in login.calls] == ["search"]


def test_doi_division_that_bai_thi_dung_khong_tim_o_division_sai():
    login = _Login("DIVISION_OPTION_NOT_FOUND")
    panel = _Panel(login)

    result = ModulesController(panel).search_sample(sample_no="PSG-ONL-26-170")

    assert [call[0] for call in login.calls] == ["switch_division"]
    assert result["ok"] is False
    assert result["code"] == "DIVISION_OPTION_NOT_FOUND"
    assert "thuộc Division PSSG" in result["message"]


def test_mat_phien_khi_doi_division_giu_nguyen_ma_de_engine_tu_login_lai():
    login = _Login("NOT_LOGGED_IN")

    failed, state = align_sample_division(_Panel(login), "PSG-ONL-26-170")

    assert failed is not None
    assert failed["code"] == "NOT_LOGGED_IN"
    assert failed["message"] == "WFX từ chối."
    assert state == {}


def test_xem_file_dinh_kem_cung_doi_division_truoc():
    login = _Login()
    panel = _Panel(login)

    result = panel._catalog.files_view.check_sample_files_with_filters(
        {"sample_no": "PSK-PARAGON-26-3374"}
    )

    assert [call[0] for call in login.calls] == ["switch_division", "find"]
    assert result["source"] == "sample"
    assert result["current_division"] == "knit"
    assert result["code"] == "NO_RESULTS"
