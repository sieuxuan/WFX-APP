"""RMPO No. mang Division trong tiền tố: tìm/nhập kho phải đổi Division trước."""

from __future__ import annotations

from wfx_panel.controllers.catalog import CatalogController
from wfx_panel.controllers.inventory import InventoryController

_ROW = {
    "row_key": "r1",
    "status": "Open",
    "supplier": "YKK",
    "order_no": "PSW-JLD-26-6242",
    "last_created": "",
    "qty": "10",
}


class _Login:
    def __init__(self, switch_code: str = "DIVISION_CHANGED") -> None:
        self.switch_code = switch_code
        self.calls: list[tuple] = []
        self.menu_resets = 0
        self.rows = [dict(_ROW)]

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

    def search_rmpo_list(self, xpath, supplier, order_no, log=print):
        self.calls.append(("search", order_no))
        if not self.rows:
            return {
                "ok": False,
                "code": "RMPO_NO_RESULTS",
                "message": "Không tìm thấy RMPO phù hợp.",
            }
        return {
            "ok": True,
            "code": "RMPO_RESULTS_READY",
            "message": "Có 1 RMPO phù hợp.",
            "rmpo_rows": self.rows,
            "result_count": len(self.rows),
        }

    def open_rmpo_result_action(self, *args, log=print):
        self.calls.append(("action", args[-1] if args else ""))
        return {"ok": True, "code": "RMPO_PO_OPENED", "message": "Đã mở."}

    def prepare_grn_receipt(self, xpath, rmpo_no, supplier, mode, log=print):
        self.calls.append(("prepare", rmpo_no))
        return {
            "ok": True,
            "code": "GRN_SOURCING_ASN_READY",
            "message": "Đã Add RMPO vào Sourcing ASN.",
            "rmpo_no": rmpo_no,
            "supplier": supplier or "YKK",
        }

    def continue_grn_receipt(self, supplier, log=print):
        self.calls.append(("continue", supplier))
        return {
            "ok": True,
            "code": "GRN_SITE_SELECTION_REQUIRED",
            "message": "Chọn Site.",
            "sites": ["HANOI"],
        }

    def search_grn_receipt(self, kind, query, log=print):
        self.calls.append(("search_grn", kind))
        return {
            "ok": False,
            "code": "GRN_SEARCH_NO_RESULTS",
            "message": "Không tìm thấy GRN.",
        }


class _Panel:
    def __init__(self, login: _Login, division: str | None = "pssg") -> None:
        self._login = login
        self._catalog = CatalogController(self)
        self._current_division = division

    def _log(self, _line: str) -> None:
        return None

    def _run(self, method, action, request=None):
        result = action()
        # Giống run engine: Division của panel đi theo kết quả cuối.
        if result.get("current_division") is not None:
            self._current_division = str(result["current_division"])
        return result


def _names(login: _Login) -> list[str]:
    return [call[0] for call in login.calls]


def test_search_rmpo_doi_division_roi_moi_tim():
    login = _Login()
    panel = _Panel(login)

    result = InventoryController(panel).search_rmpo("", "PSW-JLD-26-6242")

    assert login.calls[:2] == [
        ("switch_division", "woven"),
        ("search", "PSW-JLD-26-6242"),
    ]
    assert login.menu_resets == 1
    assert result["current_division"] == "woven"
    assert result["message"].startswith("Đã tự chuyển sang Division WOVEN.")
    assert len(result["rmpos"]) == 1


def test_khong_tim_thay_sau_khi_doi_van_bao_da_doi_division():
    login = _Login()
    login.rows = []
    panel = _Panel(login)

    result = InventoryController(panel).search_rmpo("", "PSK-PARAGON-26-3374")

    assert result["code"] == "RMPO_NO_RESULTS"
    assert result["current_division"] == "knit"
    assert result["message"].startswith("Đã tự chuyển sang Division KNIT.")
    # Có tiền tố rồi thì không gợi ý nhập tiền tố nữa.
    assert "PSG-/PSW-/PSK-" not in result["message"]


def test_rmpo_khong_tien_to_giu_division_va_goi_y_khi_khong_thay():
    login = _Login()
    login.rows = []
    panel = _Panel(login)

    result = InventoryController(panel).search_rmpo("YKK", "6242")

    assert _names(login) == ["search"]
    assert "PSG-/PSW-/PSK-" in result["message"]


def test_chi_tim_supplier_thi_khong_cham_division():
    login = _Login()
    panel = _Panel(login)

    InventoryController(panel).search_rmpo("YKK", "")

    assert _names(login) == ["search"]


def test_doi_division_that_bai_thi_dung_khong_tim_o_division_sai():
    login = _Login("DIVISION_OPTION_NOT_FOUND")
    panel = _Panel(login)

    result = InventoryController(panel).search_rmpo("", "PSG-ONL-26-170")

    assert _names(login) == ["switch_division"]
    assert result["ok"] is False
    assert result["code"] == "DIVISION_OPTION_NOT_FOUND"
    assert "RMPO No. PSG-ONL-26-170 thuộc Division PSSG" in result["message"]


def test_mat_phien_khi_doi_division_giu_nguyen_ma_de_engine_tu_login_lai():
    login = _Login("NOT_LOGGED_IN")
    panel = _Panel(login)

    result = InventoryController(panel).search_rmpo("", "PSW-JLD-26-6242")

    assert result["code"] == "NOT_LOGGED_IN"
    assert result["message"] == "WFX từ chối."


def test_doi_division_sau_luot_tim_thi_lua_chon_rmpo_het_hieu_luc():
    login = _Login()
    panel = _Panel(login)
    inventory = InventoryController(panel)
    found = inventory.search_rmpo("", "PSW-JLD-26-6242")
    choice_id = found["rmpos"][0]["choice_id"]

    panel._current_division = "knit"  # user tự đổi Division trên panel
    result = inventory.run_rmpo_action(choice_id, "check_po")

    assert result["code"] == "RMPO_RESULT_EXPIRED"
    assert "Division đã đổi" in result["message"]
    assert "action" not in _names(login)


def test_cung_division_thi_thao_tac_rmpo_chay_binh_thuong():
    login = _Login()
    panel = _Panel(login)
    inventory = InventoryController(panel)
    found = inventory.search_rmpo("", "PSW-JLD-26-6242")

    result = inventory.run_rmpo_action(found["rmpos"][0]["choice_id"], "check_po")

    assert result["code"] == "RMPO_PO_OPENED"


def test_nhap_kho_truc_tiep_doi_division_truoc_khi_tra_rmpo():
    login = _Login()
    panel = _Panel(login)

    result = InventoryController(panel).prepare_grn_receipt(
        "PSW-JLD-26-6242", "foreign"
    )

    assert login.calls[:2] == [
        ("switch_division", "woven"),
        ("prepare", "PSW-JLD-26-6242"),
    ]
    assert result["code"] == "GRN_SOURCING_ASN_READY"
    assert result["current_division"] == "woven"
    assert result["receipt_token"]


def test_mode_sai_khong_doi_division():
    login = _Login()
    panel = _Panel(login)

    InventoryController(panel).prepare_grn_receipt("PSW-JLD-26-6242", "air")

    assert "switch_division" not in _names(login)


def test_tiep_tuc_grn_quay_ve_division_luc_bat_dau():
    login = _Login()
    panel = _Panel(login)
    inventory = InventoryController(panel)
    token = inventory.prepare_grn_receipt("PSW-JLD-26-6242", "foreign")[
        "receipt_token"
    ]
    login.calls.clear()

    panel._current_division = "knit"  # user đổi Division lúc Confirm Sourcing
    result = inventory.continue_grn_receipt(token, True)

    assert login.calls == [
        ("switch_division", "woven"),
        ("continue", "YKK"),
    ]
    assert result["code"] == "GRN_SITE_SELECTION_REQUIRED"
    assert result["current_division"] == "woven"


def test_tim_grn_theo_rmpo_doi_division_con_invoice_thi_khong():
    login = _Login()
    panel = _Panel(login)
    inventory = InventoryController(panel)

    inventory.search_grn("rmpo", "PSK-PARAGON-26-3374")
    assert login.calls[0] == ("switch_division", "knit")

    login.calls.clear()
    inventory.search_grn("invoice", "PSK-INV-001")
    assert _names(login) == ["search_grn"]
