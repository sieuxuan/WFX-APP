"""Module Sample Order: chạy thật luồng Search / Check File / chọn kết quả.

Trước đây Sample chỉ được phủ bằng hai kiểu test yếu:

* `tests/test_login_special_workflows.py` grep tên hàm trong source — xanh kể cả
  khi thân hàm sai;
* `tests/test_panel_api.py` stub hẳn lớp automation — không chạm phần quyết định
  thật (đọc grid, đếm dòng, click đúng Style Code).

File này vá đúng ranh giới Playwright (`tests/fakes/automation_boundary.py`) rồi
cho toàn bộ logic Sample trong `wfx_panel/automation/modules.py` chạy thật trên
một AG Grid giả. Các quy tắc CLAUDE.md được giữ ở đây:

* Check File chạy đúng flow Search trước; một dòng thì tự mở Style Code, nhiều
  dòng thì giữ grid cho người dùng chọn — không tự chọn dòng đầu.
* Sau khi user chọn, app tiếp tục từ grid đang mở, KHÔNG tìm lại.
* Floating Filter phải quét ngang vì mỗi tài khoản kéo cột một kiểu.
* Thiếu điều kiện tìm là lỗi người dùng: chặn trước khi chạm Chrome.
* Mọi flow phải nhả driver Playwright ở `finally`.
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.ui_source import panel_js
from tests.fakes.wfx_dom import install_fake_clock
from tests.fakes.wfx_sample_grid import (
    SampleGridFrame,
    SampleRow,
    sample_filters,
)
from wfx_panel.automation import modules
from wfx_panel.automation.search_specs import SAMPLE_SEARCH_SPEC

SAMPLE_XPATH = '//*[@id="0004_0056_4070"]/a'


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, modules)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _world(clock, frame: SampleGridFrame) -> WfxWorld:
    page = FakePage(clock, frames=[frame], empty_selectors=[])
    return WfxWorld(clock, [page])


def _grid(clock, **kwargs) -> SampleGridFrame:
    return SampleGridFrame(clock, **kwargs)


# --- đọc kết quả grid ---------------------------------------------------


def test_mot_dong_duy_nhat_thi_tu_mo_style_code(clock):
    frame = _grid(
        clock,
        rows=[SampleRow("3", style_code="ABC123", sample_no="SMP-001")],
    )
    lines, log = _logs()

    result = modules._sample_file_result(frame, log)

    assert result["code"] == "SAMPLE_STYLE_OPENED"
    assert result["article_code"] == "ABC123"
    assert frame.clicked == [("3", "ABC123")]
    assert any("Đã click Style Code ABC123" in line for line in lines)


def test_nhieu_dong_thi_giu_grid_va_khong_tu_chon_dong_dau(clock):
    frame = _grid(
        clock,
        rows=[
            SampleRow("0", style_code="ABC123", sample_no="SMP-001"),
            SampleRow("1", style_code="XYZ999", sample_no="SMP-002"),
        ],
    )

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["ok"] is True
    assert result["code"] == "SAMPLE_MULTIPLE_RESULTS"
    assert result["result_count"] == 2
    assert [item["style_code"] for item in result["samples"]] == [
        "ABC123",
        "XYZ999",
    ]
    assert frame.clicked == []


def test_danh_sach_tra_ve_gioi_han_20_dong_nhung_van_dem_du(clock):
    frame = _grid(
        clock,
        rows=[SampleRow(str(index), style_code=f"S{index:03d}") for index in range(25)],
    )

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["code"] == "SAMPLE_MULTIPLE_RESULTS"
    assert result["result_count"] == 25
    assert len(result["samples"]) == 20


def test_khong_co_dong_nao_thi_tra_no_results(clock):
    frame = _grid(clock, rows=[], no_rows=True)

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["ok"] is False
    assert result["code"] == "NO_RESULTS"
    assert result["samples"] == []
    assert frame.clicked == []


def test_dong_khong_co_style_code_thi_khong_click(clock):
    frame = _grid(clock, rows=[SampleRow("0", sample_no="SMP-001")])

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["code"] == "SAMPLE_STYLE_NOT_FOUND"
    assert frame.clicked == []


def test_cho_grid_on_dinh_truoc_khi_ket_luan_so_ket_qua(clock):
    """Grid đang bind dở trả 1 dòng rồi mới đủ 3; không được chốt sớm."""

    def grow(frame: SampleGridFrame, poll: int) -> None:
        if poll == 2:
            frame.rows = [
                SampleRow("0", style_code="ABC123"),
                SampleRow("1", style_code="ABC124"),
                SampleRow("2", style_code="ABC125"),
            ]

    frame = _grid(
        clock,
        rows=[SampleRow("0", style_code="ABC123")],
        on_poll=grow,
    )

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["code"] == "SAMPLE_MULTIPLE_RESULTS"
    assert result["result_count"] == 3
    assert frame.clicked == []


def test_click_dung_row_key_va_dung_code(clock):
    frame = _grid(
        clock,
        rows=[
            SampleRow("0", style_code="ABC123"),
            SampleRow("1", style_code="XYZ999"),
        ],
    )

    assert modules._click_sample_style_result(frame, "1", "XYZ999", _logs()[1])
    assert frame.clicked == [("1", "XYZ999")]


def test_khong_click_khi_dong_da_doi_code(clock):
    frame = _grid(clock, rows=[SampleRow("1", style_code="DOI-KHAC")])
    lines, log = _logs()

    assert modules._click_sample_style_result(frame, "1", "XYZ999", log) is False
    assert frame.clicked == []
    assert any("không còn trong kết quả" in line for line in lines)


# --- vỏ entry point -----------------------------------------------------


def test_thieu_dieu_kien_thi_khong_cham_chrome(clock, monkeypatch):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)

    for runner in (
        modules.search_sample_list_with_filters,
        modules.find_sample_file_results_with_filters,
    ):
        result = runner(SAMPLE_XPATH, {"sample_no": "  ", "style": ""}, _logs()[1])
        assert result["ok"] is False
        assert result["code"] == "QUERY_REQUIRED"
        assert "Sample Order No." in result["message"]
    assert world.driver_starts == 0


def test_check_file_chay_flow_search_roi_mo_style(clock, monkeypatch):
    frame = _grid(clock, rows=[SampleRow("4", style_code="ABC123")])
    world = _world(clock, frame)
    wire_automation(monkeypatch, modules, world)

    result = modules.find_sample_file_results_with_filters(
        SAMPLE_XPATH,
        {"sample_no": "SMP-001", "buyer": "NIKE"},
        _logs()[1],
    )

    assert result["code"] == "SAMPLE_STYLE_OPENED"
    assert result["article_code"] == "ABC123"
    # Đúng thứ tự khai báo trong spec, và filter cũ đã được xóa trước khi điền.
    assert frame.fill_log[-2:] == [
        ("Sample Order No.", "SMP-001"),
        ("Buyer", "NIKE"),
    ]
    assert world.driver_starts == world.driver_stops == 1


def test_search_nhieu_dieu_kien_tra_ve_dung_cac_filter_da_dung(clock, monkeypatch):
    frame = _grid(clock, rows=[SampleRow("0", style_code="ABC123")])
    world = _world(clock, frame)
    wire_automation(monkeypatch, modules, world)

    result = modules.search_sample_list_with_filters(
        SAMPLE_XPATH,
        {"style": "JACKET", "created_by": "Alice"},
        _logs()[1],
    )

    assert result["code"] == "MODULE_SEARCH_APPLIED"
    assert result["module"] == "Sample List"
    assert result["filter_kinds"] == ["style", "created_by"]
    assert "Style, Created By" in result["message"]
    assert world.driver_starts == world.driver_stops == 1


def test_search_khong_bao_gio_bao_nguoi_dung_bam_list(clock, monkeypatch):
    """CLAUDE.md: Search tự mở List, cấm trả `*_LIST_NOT_OPEN`."""
    frame = _grid(clock, rows=[], no_rows=True, filter_row_visible=False)
    world = _world(clock, frame)
    wire_automation(monkeypatch, modules, world)
    patch_automation(
        monkeypatch, modules,
        "_click_module_menu_on_page",
        lambda *_args, **_kwargs: None,
    )
    patch_automation(
        monkeypatch, modules,
        "_show_module_floating_filter",
        lambda *_args, **_kwargs: None,
    )
    patch_automation(monkeypatch, modules, "_mark_grid_roots", lambda _page: None)

    result = modules.search_sample_list_with_filters(
        SAMPLE_XPATH,
        {"sample_no": "SMP-001"},
        _logs()[1],
    )

    assert result["ok"] is False
    assert result["code"] == "MODULE_SEARCH_NOT_READY"
    assert "LIST_NOT_OPEN" not in result["code"]
    assert "bấm List" not in result["message"]
    assert world.driver_starts == world.driver_stops == 1


def test_chrome_dong_thi_tra_ma_ranh_gioi(clock, monkeypatch):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world, chrome_ready=False)

    result = modules.find_sample_file_results_with_filters(
        SAMPLE_XPATH,
        {"sample_no": "SMP-001"},
        _logs()[1],
    )

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_starts == world.driver_stops == 1


# --- tiếp tục từ grid đang mở -------------------------------------------


def test_chon_ket_qua_thi_tiep_tuc_tu_grid_dang_mo(clock, monkeypatch):
    frame = _grid(
        clock,
        rows=[
            SampleRow("0", style_code="ABC123"),
            SampleRow("1", style_code="XYZ999"),
        ],
    )
    world = _world(clock, frame)
    wire_automation(monkeypatch, modules, world)

    result = modules.open_sample_file_result("1", "XYZ999", _logs()[1])

    assert result["code"] == "SAMPLE_STYLE_OPENED"
    assert result["article_code"] == "XYZ999"
    assert frame.clicked == [("1", "XYZ999")]
    # Không tìm lại: không ô filter nào bị ghi đè.
    assert frame.fill_log == []
    assert world.driver_starts == world.driver_stops == 1


def test_chon_ket_qua_van_chay_khi_cot_sample_no_bi_cuon_ngang(clock, monkeypatch):
    """Mỗi user kéo cột một kiểu; cột Sample Order No. có thể ngoài viewport.

    Grid vẫn đang mở và dòng vẫn còn, nên app phải quét ngang để nhận lại
    context thay vì bắt người dùng bấm Check File lại từ đầu.
    """
    frame = _grid(
        clock,
        rows=[SampleRow("1", style_code="XYZ999")],
        filters=sample_filters(hidden_beyond={"sample_no": 200}),
        scroll_current=900,
        scroll_maximum=1_200,
    )
    world = _world(clock, frame)
    wire_automation(monkeypatch, modules, world)

    result = modules.open_sample_file_result("1", "XYZ999", _logs()[1])

    assert result["code"] == "SAMPLE_STYLE_OPENED"
    assert frame.clicked == [("1", "XYZ999")]


def test_lua_chon_rong_khong_mo_playwright(clock, monkeypatch):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)

    result = modules.open_sample_file_result("", "", _logs()[1])

    assert result["code"] == "SAMPLE_RESULT_EXPIRED"
    assert world.driver_starts == 0


def test_dong_da_bien_mat_thi_bao_het_hieu_luc(clock, monkeypatch):
    frame = _grid(clock, rows=[SampleRow("0", style_code="ABC123")])
    world = _world(clock, frame)
    wire_automation(monkeypatch, modules, world)

    result = modules.open_sample_file_result("9", "XYZ999", _logs()[1])

    assert result["ok"] is False
    assert result["code"] == "SAMPLE_RESULT_EXPIRED"
    assert frame.clicked == []
    assert world.driver_starts == world.driver_stops == 1


# --- đặc tả filter ------------------------------------------------------


def test_spec_sample_dung_context_rieng_khong_dung_chung_txtarticle():
    """OC/Sample/Sale ASN dùng chung `#txtArticle`; context phải riêng."""
    assert SAMPLE_SEARCH_SPEC.requires_floating_filter is True
    assert "#txtArticle" not in SAMPLE_SEARCH_SPEC.context_field.selectors
    assert set(SAMPLE_SEARCH_SPEC.fields) == {
        "sample_no",
        "style",
        "created_by",
        "buyer",
    }


# --- token hóa lựa chọn Sample ------------------------------------------


class _FakeLogin:
    """Chỉ những hàm mà CatalogController thật sự gọi cho luồng Sample."""

    def __init__(self, *, opened: dict | None = None) -> None:
        self.opened = opened or {
            "ok": True,
            "code": "SAMPLE_STYLE_OPENED",
            "article_code": "ABC123",
        }
        self.open_calls: list[tuple[str, str]] = []

    def open_sample_file_result(self, row_key, style_code, log=print):
        self.open_calls.append((row_key, style_code))
        return dict(self.opened)

    def scan_catalog_files(self, article_code, log=print):
        return {
            "ok": True,
            "code": "CATALOG_FILES_SCANNED",
            "files": [
                {
                    "section": "Style Files",
                    "file_name": "tech-pack.pdf",
                    "download_url": "https://wfx.test/file/1",
                }
            ],
        }


class _FakePanel:
    def __init__(self, login: _FakeLogin) -> None:
        self._login = login
        self.runs: list[str] = []

    def _log(self, line: str) -> None:
        return None

    def _run(self, method, action, request=None):
        self.runs.append(method)
        return action()


def _controller(login: _FakeLogin):
    from wfx_panel.controllers.catalog import CatalogController

    return CatalogController(_FakePanel(login))


def test_row_key_cua_grid_khong_bao_gio_ra_webview():
    controller = _controller(_FakeLogin())

    published = controller.files_view._publish_sample_file_choices(
        {
            "code": "SAMPLE_MULTIPLE_RESULTS",
            "samples": [
                {"row_key": "17", "style_code": "ABC123", "sample_no": "SMP-1"},
                # Dòng không mở được thì không được phát token.
                {"row_key": "18", "style_code": ""},
                {"row_key": "", "style_code": "XYZ999"},
            ],
        }
    )

    assert published["source"] == "sample"
    assert len(published["samples"]) == 1
    assert "row_key" not in published["samples"][0]
    assert published["samples"][0]["style_code"] == "ABC123"
    assert list(controller.files_view.sample_choices.values()) == [
        {"row_key": "17", "style_code": "ABC123"}
    ]


def test_token_la_khong_the_doan_va_khong_dung_lai_sau_khi_mo():
    login = _FakeLogin()
    controller = _controller(login)
    controller.files_view._publish_sample_file_choices(
        {
            "code": "SAMPLE_MULTIPLE_RESULTS",
            "samples": [{"row_key": "17", "style_code": "ABC123"}],
        }
    )
    choice_id = next(iter(controller.files_view.sample_choices))

    opened = controller.files_view.open_sample_file_choice(choice_id)

    assert opened["code"] == "CATALOG_FILES_SCANNED"
    assert opened["source"] == "sample"
    assert opened["article_code"] == "ABC123"
    assert login.open_calls == [("17", "ABC123")]

    again = controller.files_view.open_sample_file_choice(choice_id)

    assert again["code"] == "SAMPLE_RESULT_EXPIRED"
    assert login.open_calls == [("17", "ABC123")]


def test_token_la_khong_cham_automation():
    login = _FakeLogin()
    controller = _controller(login)

    result = controller.files_view.open_sample_file_choice("khong-ton-tai")

    assert result["ok"] is False
    assert result["code"] == "SAMPLE_RESULT_EXPIRED"
    assert login.open_calls == []


def test_dem_ket_qua_theo_so_dong_bam_duoc_khong_phai_so_dong_grid(clock):
    """Dòng không có Style Code không vào danh sách nên không được đếm."""
    frame = _grid(
        clock,
        rows=[
            SampleRow("0", style_code="ABC123", sample_no="SMP-001"),
            SampleRow("1", sample_no="SMP-002"),
            SampleRow("2", sample_no="SMP-003"),
        ],
    )

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["code"] == "SAMPLE_MULTIPLE_RESULTS"
    assert len(result["samples"]) == 1
    assert result["result_count"] == 1
    # Vẫn phải nói rõ grid có 3 dòng, nếu không người dùng tưởng app lọc sai.
    assert "3 kết quả" in result["message"]
    assert "1 dòng mở được Style Code" in result["message"]
    assert frame.clicked == []


def test_moi_dong_deu_bam_duoc_thi_message_khong_them_phan_giai_thich(clock):
    frame = _grid(
        clock,
        rows=[
            SampleRow("0", style_code="ABC123"),
            SampleRow("1", style_code="XYZ999"),
        ],
    )

    result = modules._sample_file_result(frame, _logs()[1])

    assert result["result_count"] == 2
    assert result["message"] == "Có 2 kết quả; chọn Sample cần kiểm tra file."


def test_mo_that_bai_vi_grid_doi_thi_xoa_het_token_cu():
    """Grid đã khác: cả danh sách trỏ vào dòng cũ, không riêng dòng vừa bấm."""
    login = _FakeLogin(
        opened={
            "ok": False,
            "code": "SAMPLE_RESULT_EXPIRED",
            "message": "Kết quả Sample đã thay đổi.",
        }
    )
    controller = _controller(login)
    controller.files_view._publish_sample_file_choices(
        {
            "code": "SAMPLE_MULTIPLE_RESULTS",
            "samples": [
                {"row_key": "17", "style_code": "ABC123"},
                {"row_key": "18", "style_code": "XYZ999"},
            ],
        }
    )
    first, second = list(controller.files_view.sample_choices)

    failed = controller.files_view.open_sample_file_choice(first)

    assert failed["code"] == "SAMPLE_RESULT_EXPIRED"
    assert failed["source"] == "sample"
    assert controller.files_view.sample_choices == {}

    again = controller.files_view.open_sample_file_choice(second)

    assert again["code"] == "SAMPLE_RESULT_EXPIRED"
    assert login.open_calls == [("17", "ABC123")]


def test_loi_khac_khong_xoa_token_de_con_thu_lai():
    """`CHROME_CLOSED` là lỗi tạm; xóa token sẽ chặn cả lần thử lại hợp lệ."""
    login = _FakeLogin(
        opened={
            "ok": False,
            "code": "CHROME_CLOSED",
            "message": "Trình duyệt làm việc đã đóng.",
        }
    )
    controller = _controller(login)
    controller.files_view._publish_sample_file_choices(
        {
            "code": "SAMPLE_MULTIPLE_RESULTS",
            "samples": [{"row_key": "17", "style_code": "ABC123"}],
        }
    )
    choice_id = next(iter(controller.files_view.sample_choices))

    failed = controller.files_view.open_sample_file_choice(choice_id)

    assert failed["code"] == "CHROME_CLOSED"
    assert choice_id in controller.files_view.sample_choices

    controller.files_view.open_sample_file_choice(choice_id)

    assert login.open_calls == [("17", "ABC123"), ("17", "ABC123")]


def test_giao_dien_an_danh_sach_khi_lua_chon_het_hieu_luc():

    source = panel_js()
    start = source.index('} else if (result.code === "SAMPLE_MULTIPLE_RESULTS")')
    block = source[start : start + 600]

    assert 'result.code === "SAMPLE_RESULT_EXPIRED"' in block
    assert "hideSampleFileResults()" in block


def test_khong_con_entry_point_sample_mot_dieu_kien():
    """UI chỉ đi đường `*_with_filters`; bản một filter là code chết."""
    from wfx_panel import automation
    from wfx_panel.controllers.catalog import CatalogController

    assert not hasattr(automation, "search_sample_list")
    assert not hasattr(automation, "find_sample_file_results")
    assert hasattr(automation, "search_sample_list_with_filters")
    assert hasattr(automation, "find_sample_file_results_with_filters")
    assert not hasattr(CatalogController, "check_sample_files")
    from wfx_panel.controllers.catalog_files import ArticleFileController

    assert hasattr(ArticleFileController, "check_sample_files_with_filters")


def test_thong_bao_loi_goi_dung_ten_nut_tren_panel():
    """Không nút nào tên `Check File`; hướng dẫn sai làm người dùng bế tắc."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sources = [root / "wfx_panel/controllers/catalog.py"]
    sources += sorted((root / "wfx_panel/automation/modules").rglob("*.py"))
    for path in sources:
        assert "bấm Check File" not in path.read_text(encoding="utf-8")
    index_html = (root / "wfx_panel/ui/index.html").read_text(encoding="utf-8")
    assert "Xem file đính kèm" in index_html
