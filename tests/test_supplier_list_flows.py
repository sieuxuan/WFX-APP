"""Supplier List: từng flow một, chạy qua vỏ entry point thật.

`tests/test_directory_entry_points.py` đã phủ `find_supplier_across_categories`
ở mức *điều phối* (mọi Category đều được quét, lỗi một Category không dừng
scan) bằng cách monkeypatch cả hai helper bên dưới. Phần chưa ai chạy là toàn
bộ đường đi thật xuống DOM — và đó đúng là nơi đặc tả đặt ràng buộc:

* "Cả hai thao tác đều **tự mở** Supplier List khi WFX chưa mở, nên UI không
  được đánh số bước hay bắt người dùng bấm List trước."
* WFX chỉ bind đủ option Category **sau `mousedown`**; `select_option` thẳng
  trên DOM ban đầu chỉ thấy `[Select]` + `Apparel`.
* Master đang đúng Category thì phải **dùng lại grid**, không click lại.
* `_supplier_category_frame` không được nhận nhầm `#ddlCategory` của Catalog.
* Buyer/Supplier chỉ được resolve lại frame **cùng PartyType**.

File này chạy `directory.py` thật trên DOM giả, chỉ vá đúng ranh giới
Playwright và lời gọi menu WFX.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.ui_source import panel_js
from tests.fakes.wfx_dom import install_fake_clock
from tests.fakes.wfx_supplier import (
    BUYER_URL,
    CatalogTreeFrame,
    Node,
    SupplierFrame,
    default_tree,
)
from wfx_panel.automation import directory

MODULE_XPATH = '//*[@id="0005_0010_1290"]/a'
APPAREL = ("Apparel", "01")
TRIMS = ("Trims", "05")
# Thứ tự quét giống `constants.CATEGORIES`: Apparel trước, Trims sau cùng.
CATEGORIES = {"Apparel": "01", "Textiles/Fabric": "03", "Trims": "05"}


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, directory)


@pytest.fixture
def world(clock):
    return WfxWorld(clock, pages=[FakePage(clock)])


def _quiet():
    return lambda _line: None


def _menu(monkeypatch, page, frame=None):
    """Thay đúng lời gọi menu WFX; trả về số lần app tự mở Supplier List."""
    opened: list[str] = []

    def click_menu(_page, module_name, _xpath, _log):
        opened.append(module_name)
        if frame is not None and frame not in page.frames:
            page.frames.append(frame)
        return True

    monkeypatch.setattr(directory, "_click_module_menu_on_page", click_menu)
    return opened


def _open(category=TRIMS):
    name, value = category
    return directory.open_supplier_category(MODULE_XPATH, name, value, _quiet())


def _find_in(category, query="Acme"):
    name, value = category
    return directory.find_supplier_in_category(
        MODULE_XPATH, name, value, query, _quiet()
    )


def _find_all(query="Acme", categories=None):
    return directory.find_supplier_across_categories(
        MODULE_XPATH, dict(categories or CATEGORIES), query, _quiet()
    )


_UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def _panel_js_action(action: str) -> str:
    """Thân handler của một `data-module-action` trong bảng action panel.js."""
    js = panel_js()
    start = js.index(f'"{action}": ')
    return js[start : js.index("\n\"", start + 10)]


def _supplier_workspace_html() -> str:
    html = (_UI / "index.html").read_text(encoding="utf-8")
    start = html.index('data-module-view="supplier"')
    return html[start : html.index('data-module-view="buyer"', start)]


# === Flow 1 — "Mở Master": mở/đổi Category rồi dựng grid Company ==========


def test_mo_master_tu_mo_supplier_list_khi_wfx_chua_mo(monkeypatch, world):
    """Đặc tả: nút List chỉ là lối tắt, flow phải tự mở khi cần."""
    frame = SupplierFrame(world.clock, category="")
    opened = _menu(monkeypatch, world.page, frame)
    wire_automation(monkeypatch, directory, world)

    result = _open(TRIMS)

    assert result["code"] == "SUPPLIER_CATEGORY_READY"
    assert result["category"] == "Trims"
    assert opened == ["Supplier List"], "Phải tự mở đúng một lần"
    assert frame.category.value == "05"


def test_supplier_list_dang_mo_thi_khong_click_lai_menu(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="01")
    world.page.frames.append(frame)
    opened = _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert opened == [], "List đã mở; mở lại menu là kéo user khỏi màn đang xem"


def test_khong_nham_cay_catalog_lam_cay_supplier(monkeypatch, world):
    """Catalog cũng có `#ddlCategory`; nhận nhầm là đổi Category sai màn."""
    catalog = CatalogTreeFrame(world.clock)
    supplier = SupplierFrame(world.clock, category="01")
    world.page.frames.extend([catalog, supplier])
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert supplier.category.value == "05"
    assert catalog.category.value == "01", "Không được chạm Category của Catalog"


def test_wfx_chi_nap_du_option_sau_mousedown(monkeypatch, world):
    """Bỏ `mousedown` thì DOM chỉ có [Select] + Apparel và Trims sẽ trượt."""
    frame = SupplierFrame(world.clock, category="01")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert frame.category.mousedowns == 1
    assert frame.category.value == "05"


def test_category_dang_dung_thi_khong_dispatch_lai(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="05")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert frame.category.mousedowns == 0


def test_option_chua_bind_tra_ve_master_not_ready(monkeypatch, world):
    """WFX không nạp được option: dừng bằng mã nghiệp vụ, không văng stack."""
    frame = SupplierFrame(world.clock, category="01", options=("01", "03"))
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _open(TRIMS)

    assert result["code"] == "SUPPLIER_MASTER_NOT_READY"
    assert result["ok"] is False


def test_master_dung_category_thi_dung_lai_grid(monkeypatch, world):
    """Đặc tả: đúng Category + Company search sẵn sàng thì không click lại."""
    frame = SupplierFrame(world.clock, category="05", master_opens_after=0)
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert frame.master_clicks == 0


def test_doi_category_thi_luon_click_lai_master(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="01", master_opens_after=1)
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert frame.master_clicks == 1


def test_chi_click_node_master_dung_nghia(monkeypatch, world):
    """`Master Data`, `Group Master`, nút `Search` đều khớp selector."""
    frame = SupplierFrame(world.clock, category="01", master_opens_after=1)
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True

    noise = [node for node in frame.tree if node is not frame.master]
    assert [node.clicks for node in noise] == [0, 0, 0]
    assert frame.master.clicks == 1


def test_master_khong_dung_grid_thi_bao_master_not_ready(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="01", master_opens_after=99)
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _open(TRIMS)

    assert result["code"] == "SUPPLIER_MASTER_NOT_READY"
    assert world.driver_stops == 1, "Flow lỗi vẫn phải nhả Playwright driver"


def test_grid_con_loading_thi_chua_duoc_bao_san_sang(monkeypatch, world):
    """Overlay loading còn hiện = datasource chưa bind; không báo ready."""
    frame = SupplierFrame(world.clock, category="01", busy=True)
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["code"] == "SUPPLIER_MASTER_NOT_READY"


def test_supplier_list_khong_hien_ra_thi_bao_master_not_ready(monkeypatch, world):
    """App tự mở List nhưng WFX không dựng frame: vẫn là lỗi có mã."""
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["code"] == "SUPPLIER_MASTER_NOT_READY"


def test_mo_master_luon_nha_driver(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="05")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    _open(TRIMS)

    assert (world.driver_starts, world.driver_stops) == (1, 1)


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"chrome_ready": False}, "CHROME_CLOSED"),
        ({"logged_in": False}, "NOT_LOGGED_IN"),
    ],
)
def test_mo_master_tra_dung_ma_ranh_gioi_trinh_duyet(
    monkeypatch, world, kwargs, code
):
    wire_automation(monkeypatch, directory, world, **kwargs)

    result = _open(TRIMS)

    assert result["code"] == code
    assert world.driver_stops == 1


def test_loi_la_khong_bien_thanh_ma_ranh_gioi(monkeypatch, world):
    """`_browser_boundary_result` chỉ được nhận đúng hai mã whitelist."""
    frame = SupplierFrame(world.clock, category="05")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)
    monkeypatch.setattr(
        directory,
        "_open_supplier_category_on_page",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("ổ đĩa đầy")),
    )

    result = _open(TRIMS)

    assert result["code"] == "SUPPLIER_OPEN_FAILED"
    assert "RuntimeError" in result["message"]


# === Flow 2 — Tìm trong đúng một Category ================================


def test_query_rong_khong_mo_trinh_duyet(monkeypatch, world):
    wire_automation(monkeypatch, directory, world)

    result = _find_in(TRIMS, "   ")

    assert result["code"] == "QUERY_REQUIRED"
    assert world.driver_starts == 0


def test_tim_trong_category_tra_ve_dung_cong_ty(monkeypatch, world):
    frame = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": ["ACME TRIMS LTD", "BETA BUTTON CO"]},
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_in(TRIMS, "acme")

    assert result["code"] == "SUPPLIER_FOUND"
    assert result["matches"] == ["ACME TRIMS LTD"]
    assert result["category"] == "Trims"
    assert frame.company.value == "acme"
    assert frame.company.presses == ["Enter"]


def test_tim_trong_category_tu_mo_list_khi_chua_mo(monkeypatch, world):
    """Đặc tả cấm trả `*_LIST_NOT_OPEN` cho thao tác Search."""
    frame = SupplierFrame(
        world.clock,
        category="",
        rows_by_category={"05": ["ACME TRIMS LTD"]},
    )
    opened = _menu(monkeypatch, world.page, frame)
    wire_automation(monkeypatch, directory, world)

    result = _find_in(TRIMS, "acme")

    assert result["code"] == "SUPPLIER_FOUND"
    assert opened == ["Supplier List"]


def test_khong_co_ket_qua_tra_supplier_not_found(monkeypatch, world):
    frame = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": ["BETA BUTTON CO"]},
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_in(TRIMS, "acme")

    assert result["code"] == "SUPPLIER_NOT_FOUND"
    assert result["category"] == "Trims"


def test_danh_sach_hien_thi_bi_cat_o_10_dong(monkeypatch, world):
    frame = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": [f"ACME {index:02d}" for index in range(14)]},
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_in(TRIMS, "acme")

    assert len(result["matches"]) == 10
    assert result["total_matches"] == 14, (
        "Cắt danh sách hiển thị mà không kèm tổng thì user tưởng chỉ có 10 "
        "nhà cung cấp — `find_supplier_across_categories` đã đếm tổng trước "
        "khi cắt, nhánh một Category phải nhất quán."
    )


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"chrome_ready": False}, "CHROME_CLOSED"),
        ({"logged_in": False}, "NOT_LOGGED_IN"),
    ],
)
def test_tim_trong_category_tra_dung_ma_ranh_gioi(monkeypatch, world, kwargs, code):
    wire_automation(monkeypatch, directory, world, **kwargs)

    assert _find_in(TRIMS, "acme")["code"] == code
    assert world.driver_stops == 1


# === Flow 3 — Tìm tất cả Category ========================================


def test_quet_moi_category_va_bao_cao_tung_noi_co_ket_qua(monkeypatch, world):
    frame = SupplierFrame(
        world.clock,
        category="",
        rows_by_category={
            "01": ["ACME APPAREL"],
            "03": ["BETA FABRIC"],
            "05": ["ACME TRIMS", "ACME ZIP"],
        },
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_all("acme")

    assert result["code"] == "SUPPLIER_FOUND"
    assert result["checked_categories"] == list(CATEGORIES)
    assert result["categories"] == ["Apparel", "Trims"]
    assert [item["count"] for item in result["matches_by_category"]] == [1, 2]


def test_wfx_duoc_dua_ve_category_dau_tien_co_ket_qua(monkeypatch, world):
    """Thông điệp hứa "Đang hiển thị kết quả ở X" nên WFX phải thật sự ở X."""
    frame = SupplierFrame(
        world.clock,
        category="",
        rows_by_category={"01": ["ACME APPAREL"]},
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_all("acme")

    assert result["category"] == "Apparel"
    assert frame.category.value == "01", "Quét xong đang đứng ở Trims"
    assert frame.applied_query == "acme", "Phải lọc lại để user thấy kết quả"


def test_ket_qua_o_category_cuoi_thi_khong_quet_lai(monkeypatch, world):
    frame = SupplierFrame(
        world.clock,
        category="",
        rows_by_category={"05": ["ACME TRIMS"]},
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    before = frame.row_reads
    result = _find_all("acme")

    assert result["category"] == "Trims"
    assert frame.category.value == "05"
    assert frame.row_reads > before


def test_mot_category_loi_van_bao_ket_qua_mot_phan(monkeypatch, world):
    frame = SupplierFrame(
        world.clock,
        category="",
        rows_by_category={"01": ["ACME APPAREL"]},
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    real = directory._filter_company_rows

    def flaky(page, current, query, log, kind):
        if frame.category.value == "03":
            raise PlaywrightError("Frame Textiles/Fabric đã detach")
        return real(page, current, query, log, kind)

    monkeypatch.setattr(directory, "_filter_company_rows", flaky)

    result = _find_all("acme")

    assert result["code"] == "SUPPLIER_FOUND_PARTIAL"
    assert result["ok"] is True
    assert [item["category"] for item in result["failed_categories"]] == [
        "Textiles/Fabric"
    ]


def test_moi_category_deu_loi_thi_khong_duoc_noi_la_khong_tim_thay(
    monkeypatch, world
):
    """Không Category nào chạy được thì "không tìm thấy kết quả" là sai sự thật.

    Chrome rớt giữa chừng làm cả 3 Category cùng lỗi. Người dùng đọc thông điệp
    hiện tại sẽ kết luận nhà cung cấp không tồn tại rồi đi tạo mới trùng, trong
    khi thực tế app chưa kiểm tra được gì.
    """
    frame = SupplierFrame(world.clock, category="")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)
    monkeypatch.setattr(
        directory,
        "_filter_company_rows",
        lambda *_a, **_k: (_ for _ in ()).throw(PlaywrightError("frame detached")),
    )

    result = _find_all("acme")

    assert result["code"] == "SUPPLIER_SEARCH_PARTIAL"
    assert len(result["failed_categories"]) == 3
    assert "không tìm thấy kết quả" not in result["message"].casefold()


def test_khong_co_ket_qua_o_dau_thi_noi_ro_da_quet_bao_nhieu(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_all("acme")

    assert result["code"] == "SUPPLIER_NOT_FOUND"
    assert result["checked_categories"] == list(CATEGORIES)


# === Flow 4 — Lọc Company Name (dùng chung Buyer/Supplier) ===============


def test_khong_nham_frame_buyer_khi_dang_tim_supplier(monkeypatch, world):
    """Hai màn dùng chung `#txtCompanyName`; nhận nhầm là tìm sai PartyType."""
    buyer = SupplierFrame(
        world.clock,
        url=BUYER_URL,
        title="Buyer List",
        category="05",
        rows_by_category={"05": ["ACME BUYER"]},
    )
    supplier = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": ["ACME SUPPLIER"]},
    )
    world.page.frames.extend([buyer, supplier])
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    result = _find_in(TRIMS, "acme")

    assert result["matches"] == ["ACME SUPPLIER"]
    assert buyer.company.value == "", "Không được gõ vào ô của màn Buyer"


def test_dong_phu_khong_khop_query_khong_duoc_treo_18_giay(monkeypatch, world):
    """Dòng tổng/phân trang của WFX không chứa query nhưng vẫn là `tr` hợp lệ.

    `_wait_company_results` chỉ chấp nhận khi MỌI dòng đang render đều khớp,
    nên một dòng phụ như vậy đủ để nuốt trọn deadline 18 giây rồi trả lỗi kỹ
    thuật — dù kết quả thật đã hiển thị đúng trên WFX.
    """
    frame = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": ["ACME TRIMS LTD"]},
        extra_rows=["Total records: 1"],
    )
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    started = world.clock.monotonic()
    result = _find_in(TRIMS, "acme")
    elapsed = world.clock.monotonic() - started

    assert result["code"] == "SUPPLIER_FOUND"
    assert result["matches"] == ["ACME TRIMS LTD"]
    assert elapsed < 18, f"Chờ hết deadline rồi mới trả lỗi ({elapsed:.1f}s)"


def test_frame_doi_giua_chung_thi_dong_bo_lai_dung_mot_lan(monkeypatch, world):
    """WFX thay frame Company ngay sau khi Master vừa báo ready."""
    stale = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": ["ACME TRIMS LTD"]},
    )
    fresh = SupplierFrame(
        world.clock,
        category="05",
        rows_by_category={"05": ["ACME TRIMS LTD"]},
    )
    world.page.frames.append(stale)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    real_fill = directory._fill_company_query

    def swap(page, current, query, log, kind):
        if current is stale:
            stale.detached = True
            stale.company.detached = True
            page.frames.remove(stale)
            page.frames.append(fresh)
        return real_fill(page, current, query, log, kind)

    monkeypatch.setattr(directory, "_fill_company_query", swap)

    result = _find_in(TRIMS, "acme")

    assert result["code"] == "SUPPLIER_FOUND"
    assert fresh.company.value == "acme"


def test_master_detach_ngay_sau_click_van_la_navigation_thanh_cong(
    monkeypatch, world
):
    """ASP.NET postback: frame detach ngay sau click KHÔNG phải lỗi."""

    def detaching_click() -> None:
        frame.master_clicks += 1
        raise PlaywrightError("Frame was detached")

    master = Node(tag="SPAN", text="Master", on_click=detaching_click)
    frame = SupplierFrame(world.clock, category="01", master_opens_after=1)
    frame.tree = default_tree(master)
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    assert _open(TRIMS)["ok"] is True
    assert frame.master_clicks == 1


def test_select_option_detach_khong_lam_hong_luot_doi_category(monkeypatch, world):
    """WFX reload ngay khi đổi Category; detach ở đây là bình thường."""
    frame = SupplierFrame(world.clock, category="01")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    real_select = frame.category.select_option

    def detaching_select(value=None, timeout=None):
        real_select(value, timeout)
        raise PlaywrightError("Execution context was destroyed")

    frame.category.select_option = detaching_select

    assert _open(TRIMS)["ok"] is True
    assert frame.category.value == "05"


def test_loi_select_option_that_su_van_noi_len(monkeypatch, world):
    """Chỉ hai marker detach mới được nuốt; lỗi khác phải báo."""
    frame = SupplierFrame(world.clock, category="01")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    def broken_select(value=None, timeout=None):
        raise PlaywrightError("Element is not a <select> element")

    frame.category.select_option = broken_select

    result = _open(TRIMS)

    assert result["ok"] is False
    assert result["code"] == "SUPPLIER_OPEN_FAILED"


def test_khong_xac_nhan_duoc_category_thi_dung_lai(monkeypatch, world):
    """Chọn xong mà WFX không đổi giá trị: không được đi tiếp sang Master."""
    frame = SupplierFrame(world.clock, category="01")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)

    frame.category.select_option = lambda value=None, timeout=None: None

    result = _open(TRIMS)

    assert result["code"] == "SUPPLIER_MASTER_NOT_READY"
    assert frame.master_clicks == 0


# === Flow 5 — Hợp đồng với UI và bảng mã ================================


def test_ma_thanh_cong_cua_supplier_deu_duoc_coi_la_phien_con_song():
    """Mọi kết quả `ok` của Supplier đều chứng minh phiên WFX còn sống."""
    from wfx_panel.panel_api import SESSION_OK

    missing = {
        "SUPPLIER_CATEGORY_READY",
        "SUPPLIER_FOUND",
        "SUPPLIER_FOUND_PARTIAL",
    } - SESSION_OK

    assert not missing, (
        f"{sorted(missing)} trả ok=True nhưng không nâng lại badge phiên WFX"
    )


def test_tim_theo_category_co_loi_ra_tren_giao_dien():
    """`find_supplier_in_category` phải có nút gọi, không chỉ có backend.

    Flow này từng có đủ `panel_api`, whitelist bridge, nhãn telemetry và nhãn
    JS nhưng không nút nào gọi — user tìm thấy Supplier ở Category khác vẫn
    phải quét lại cả 6 Category.
    """
    body = _panel_js_action("supplier-find-category")

    assert '"find_supplier_in_category"' in body
    assert '$(".supplier-category").value' in body, "Phải gửi Category đang chọn"
    assert '$(".supplier-query").value.trim()' in body


def test_hai_nut_tim_supplier_khong_trung_nhan_va_chi_mot_nut_chinh():
    """Đặc tả: một màn module chỉ có một nút chính và không trùng nhãn."""
    import re

    workspace = _supplier_workspace_html()
    labels = re.findall(r"<button[^>]*>(.*?)</button>", workspace, re.S)
    stripped = [re.sub(r"<[^>]+>", " ", label).split() for label in labels]
    names = [" ".join(parts) for parts in stripped if parts]

    assert len(names) == len(set(names)), f"Nút trùng nhãn: {names}"
    assert workspace.count("special-primary-button") == 1


def test_nut_tim_theo_category_khoa_cung_nhom_voi_nut_tim_tat_ca():
    """Ô query trống thì cả hai nút Tìm đều phải disable."""
    workspace = _supplier_workspace_html()
    start = workspace.index('data-module-action="supplier-find-category"')
    button = workspace[workspace.rindex("<button", 0, start) : start + 200]

    assert 'data-validation-group="supplier"' in button
    assert "disabled" in button


def test_timeout_cua_supplier_khong_bien_thanh_stack_trace(monkeypatch, world):
    frame = SupplierFrame(world.clock, category="05")
    world.page.frames.append(frame)
    _menu(monkeypatch, world.page)
    wire_automation(monkeypatch, directory, world)
    monkeypatch.setattr(
        directory,
        "_filter_company_rows",
        lambda *_a, **_k: (_ for _ in ()).throw(
            PlaywrightTimeoutError("Kết quả Company Name chưa ổn định")
        ),
    )

    result = _find_in(TRIMS, "acme")

    assert result["code"] == "SUPPLIER_SEARCH_NOT_READY"
    assert "\n" not in result["message"]
