"""Controller Sale ASN: kho Buyer, review tạo mới, và Save As Documents.

Hai ràng buộc CLAUDE.md nằm ngay ở đây: `scan_sale_asn_buyers` là thao tác nặng
chỉ chạy khi user tự bấm, và file Documents tạm chỉ sống tới đúng một lần Save As
nên không được ghi đè file Excel người dùng đang mở.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import wfx_panel.controllers.sale_asn as sale_asn_controller
from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI
from wfx_panel.workbooks.sale_asn import SaleASNWorkbookError


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls: list[tuple] = []

    def check_session(self, log=print):
        return {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"}


@pytest.fixture
def api(tmp_path):
    return PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )


def _source(tmp_path, name="Sale ASN.xlsx"):
    path = tmp_path / name
    path.write_bytes(b"excel")
    return path


def _document(**overrides):
    values = {
        "file_name": "Sale ASN.xlsx",
        "invoice_no": "INV-1",
        "destination": "VIETNAM",
        "factory": "PSHK VIETNAM",
        "po_count": 1,
        "style_count": 1,
        "rows": [{"po_no": "PO-1", "style_no": "M ACEL", "invoice_no": "INV-1"}],
    }
    values.update(overrides)
    return values


def _wire_read(monkeypatch, outcome=None):
    seen: list[list[str]] = []

    def read(_path, *, required_stages):
        seen.append(list(required_stages))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome or _document()

    monkeypatch.setattr(sale_asn_controller, "read_sale_asn_workbook", read)
    return seen


# --- kho Buyer ----------------------------------------------------------


def test_an_automation_build_without_the_buyer_scan_says_so_plainly(api):
    result = api.scan_sale_asn_buyers()

    assert result["code"] == "SALE_ASN_BUYER_SCAN_FAILED"
    assert "chưa hỗ trợ" in result["message"]


def test_a_successful_scan_normalises_and_caches_the_buyer_list(api):
    api._login.scan_sale_asn_buyers = lambda _xpath, log=print: {
        "ok": True,
        "code": "SALE_ASN_BUYERS_SCANNED",
        "message": "ok",
        "buyers": [
            {"label": "  J.LINDEBERG ", "value": "1"},
            {"label": "j.lindeberg", "value": "2"},
        ],
    }

    result = api.scan_sale_asn_buyers()

    assert [item["label"] for item in result["buyers"]] == ["J.LINDEBERG"]
    assert api._sale_asn.buyers == result["buyers"]


def test_a_cache_that_cannot_be_written_still_returns_the_scanned_buyers(
    api, monkeypatch
):
    api._login.scan_sale_asn_buyers = lambda _xpath, log=print: {
        "ok": True,
        "code": "SALE_ASN_BUYERS_SCANNED",
        "message": "ok",
        "buyers": [{"label": "TRUEWERK", "value": "1"}],
    }

    def refuse(_buyers):
        raise PermissionError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(api._sale_asn._buyer_store, "save", refuse)
    lines: list[str] = []
    monkeypatch.setattr(api, "_log", lines.append)

    result = api.scan_sale_asn_buyers()

    assert [item["label"] for item in result["buyers"]] == ["TRUEWERK"]
    assert any("Không lưu được cache Buyer" in line for line in lines)


def test_a_failed_scan_leaves_the_cached_buyers_untouched(api):
    api._sale_asn.buyers = [{"label": "CŨ", "value": "1"}]
    api._login.scan_sale_asn_buyers = lambda _xpath, log=print: {
        "ok": False,
        "code": "SALE_ASN_BUYER_SCAN_FAILED",
        "message": "không mở được form",
    }

    api.scan_sale_asn_buyers()

    assert api._sale_asn.buyers == [{"label": "CŨ", "value": "1"}]


# --- đọc Order Details đang mở -----------------------------------------


def test_an_automation_build_without_the_order_scan_says_so_plainly(api):
    result = api.scan_sale_asn_order_details()

    assert result["code"] == "SALE_ASN_ORDER_SCAN_FAILED"
    assert "chưa hỗ trợ" in result["message"]


def test_the_order_scan_only_reads_the_grid_already_open(api):
    calls: list[str] = []
    api._login.scan_sale_asn_order_details = lambda log=print: (
        calls.append("scan")
        or {
            "ok": True,
            "code": "SALE_ASN_ORDER_DETAILS_SCANNED",
            "message": "ok",
            "rows": [{"po_no": "PO-1"}],
        }
    )

    result = api.scan_sale_asn_order_details()

    assert result["rows"] == [{"po_no": "PO-1"}]
    assert calls == ["scan"]


# --- chuẩn bị review ----------------------------------------------------


def test_a_broken_step_list_is_refused_before_any_file_is_read(api, tmp_path):
    result = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "J.LINDEBERG", "po"
    )

    assert result["code"] == "SALE_ASN_CREATE_STEPS_INVALID"


def test_an_empty_step_list_asks_the_user_to_pick_at_least_one(api, tmp_path):
    result = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "J.LINDEBERG", ["khong-ton-tai"]
    )

    assert result["code"] == "SALE_ASN_CREATE_STEPS_REQUIRED"


def test_the_po_step_cannot_run_without_a_buyer(api, tmp_path):
    result = api.prepare_sale_asn_create(str(_source(tmp_path)), "  ", ["po"])

    assert result["code"] == "SALE_ASN_BUYER_REQUIRED"


def test_skipping_the_po_step_removes_the_buyer_requirement(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)

    result = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "", ["order_details"]
    )

    assert result["ok"] is True
    assert result["selected_stages"] == ["order_details"]
    # Các bước không chọn được ghi vào review để lượt chạy bỏ qua đúng chúng.
    stored = api._sale_asn.create_reviews[result["review_token"]]
    assert set(stored["skipped_stages"]) == {
        "po",
        "style_details",
        "shipping_info",
    }


def test_the_steps_are_always_ordered_the_way_the_flow_runs_them(
    api, tmp_path, monkeypatch
):
    seen = _wire_read(monkeypatch)

    result = api.prepare_sale_asn_create(
        str(_source(tmp_path)),
        "J.LINDEBERG",
        ["shipping_info", "po", "order_details"],
    )

    assert result["selected_stages"] == ["po", "order_details", "shipping_info"]
    assert seen == [["po", "order_details", "shipping_info"]]


def test_a_workbook_with_cell_errors_is_reported_and_leaves_no_temp_folder(
    api, tmp_path, monkeypatch
):
    _wire_read(
        monkeypatch,
        SaleASNWorkbookError(
            "SALE_ASN_FILE_INVALID",
            "File Sale ASN có lỗi.",
            ("Dòng 3: thiếu FTY.",),
        ),
    )

    result = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "J.LINDEBERG", ["po"]
    )

    assert result["code"] == "SALE_ASN_FILE_INVALID"
    assert result["errors"] == ["Dòng 3: thiếu FTY."]
    assert list((tmp_path / "sale-asn-create-cache").iterdir()) == []


def test_a_file_the_user_already_moved_is_reported_as_missing(api, tmp_path):
    result = api.prepare_sale_asn_create(
        str(tmp_path / "khong-ton-tai.xlsx"), "J.LINDEBERG", ["po"]
    )

    assert result["code"] == "SALE_ASN_FILE_NOT_FOUND"
    assert list((tmp_path / "sale-asn-create-cache").iterdir()) == []


def test_choosing_a_second_file_discards_the_first_review(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)
    source = _source(tmp_path)

    first = api.prepare_sale_asn_create(str(source), "J.LINDEBERG", ["po"])
    second = api.prepare_sale_asn_create(str(source), "J.LINDEBERG", ["po"])

    assert first["review_token"] != second["review_token"]
    assert list(api._sale_asn.create_reviews) == [second["review_token"]]


def test_a_temp_folder_windows_still_locks_is_logged_not_raised(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)
    review = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "J.LINDEBERG", ["po"]
    )

    def refuse():
        raise PermissionError("thư mục đang bị khoá")

    api._sale_asn.create_reviews[review["review_token"]]["temporary"] = (
        SimpleNamespace(cleanup=refuse)
    )
    lines: list[str] = []
    monkeypatch.setattr(api, "_log", lines.append)

    assert (
        api._sale_asn._discard_sale_asn_create_review(review["review_token"])
        is True
    )
    assert any("Không dọn được review tạm" in line for line in lines)


def test_discarding_a_token_that_never_existed_reports_nothing_removed(api):
    assert (
        api._sale_asn._discard_sale_asn_create_review("khong-ton-tai") is False
    )


# --- chạy review --------------------------------------------------------


def test_running_an_expired_review_asks_for_the_file_again(api):
    assert (
        api.start_sale_asn_create("het-han")["code"]
        == "SALE_ASN_CREATE_REVIEW_EXPIRED"
    )
    assert (
        api.continue_sale_asn_create("het-han")["code"]
        == "SALE_ASN_CREATE_REVIEW_EXPIRED"
    )
    assert (
        api.skip_sale_asn_create_step("het-han")["code"]
        == "SALE_ASN_CREATE_REVIEW_EXPIRED"
    )


def test_an_automation_build_without_the_create_flow_says_so_plainly(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)
    review = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "J.LINDEBERG", ["po"]
    )

    result = api.start_sale_asn_create(review["review_token"])

    assert result["code"] == "SALE_ASN_CREATE_FAILED"
    assert "chưa hỗ trợ" in result["message"]


@pytest.mark.parametrize("stage", ["po", "price_check"])
def test_the_po_and_price_check_steps_cannot_be_skipped(
    api, tmp_path, monkeypatch, stage
):
    _wire_read(monkeypatch)
    review = api.prepare_sale_asn_create(
        str(_source(tmp_path)), "J.LINDEBERG", ["po", "order_details"]
    )
    api._sale_asn.create_reviews[review["review_token"]]["next_stage"] = stage

    result = api.skip_sale_asn_create_step(review["review_token"])

    assert result["code"] == "SALE_ASN_CREATE_STAGE_NOT_SKIPPABLE"


def test_skipping_a_step_adds_it_to_the_skip_list_and_runs_on(
    api, tmp_path, monkeypatch
):
    _wire_read(monkeypatch)
    review = api.prepare_sale_asn_create(
        str(_source(tmp_path)),
        "J.LINDEBERG",
        ["po", "order_details", "style_details"],
    )
    token = review["review_token"]
    api._sale_asn.create_reviews[token]["next_stage"] = "order_details"
    seen: list[tuple] = []

    def runner(*_args, **kwargs):
        seen.append(tuple(kwargs.get("skip_stages") or ()))
        return {
            "ok": True,
            "code": "SALE_ASN_FORM_COMPLETED",
            "message": "xong",
        }

    api._login.run_sale_asn_create = runner

    api.skip_sale_asn_create_step(token)

    assert "order_details" in seen[0]
    # Bỏ qua lần nữa không được nhân đôi mục trong danh sách.
    api._sale_asn.create_reviews.setdefault(
        token,
        {
            "document": _document(),
            "buyer": "J.LINDEBERG",
            "next_index": 0,
            "next_stage": "order_details",
            "selected_stages": ["po"],
            "skipped_stages": ["order_details"],
            "po_search_fields": ["po"],
            "temporary": None,
        },
    )
    api.skip_sale_asn_create_step(token)
    assert seen[-1].count("order_details") == 1


def test_cancelling_a_create_review_is_always_a_clean_answer(api):
    result = api.cancel_sale_asn_create("khong-ton-tai")

    assert result["code"] == "SALE_ASN_CREATE_CANCELLED"


# --- xuất kết quả Check giá --------------------------------------------


def test_a_price_check_payload_that_is_not_a_dict_is_refused(api, tmp_path):
    result = api.export_sale_asn_price_check(
        "khong phai dict", str(tmp_path / "check.xlsx")
    )

    assert result["code"] == "SALE_ASN_PRICE_EXPORT_FAILED"
    assert "hãy tạo Sale ASN lại" in result["message"]


@pytest.mark.parametrize("raw_path", ["", "   "])
def test_exporting_without_a_destination_is_refused(api, raw_path):
    result = api.export_sale_asn_price_check({"comparisons": []}, raw_path)

    assert result["code"] == "SALE_ASN_PRICE_EXPORT_FAILED"
    assert "Chưa có đường dẫn" in result["message"]


def test_a_price_check_workbook_is_written_where_the_user_asked(
    api, tmp_path, monkeypatch
):
    written: list[tuple] = []

    def write(target, payload):
        written.append((Path(target).name, payload))
        Path(target).write_bytes(b"PK")
        return Path(target)

    monkeypatch.setattr(
        sale_asn_controller, "write_sale_asn_price_check_workbook", write
    )

    result = api.export_sale_asn_price_check(
        {"comparisons": []}, str(tmp_path / "Check.xlsx")
    )

    assert result["code"] == "SALE_ASN_PRICE_EXPORTED"
    assert result["file_name"] == "Check.xlsx"
    assert written[0][0] == "Check.xlsx"


def test_a_price_check_workbook_that_cannot_be_written_names_the_error(
    api, tmp_path, monkeypatch
):
    def refuse(_target, _payload):
        raise PermissionError("file đang mở trong Excel")

    monkeypatch.setattr(
        sale_asn_controller, "write_sale_asn_price_check_workbook", refuse
    )

    result = api.export_sale_asn_price_check(
        {"comparisons": []}, str(tmp_path / "Check.xlsx")
    )

    assert result["code"] == "SALE_ASN_PRICE_EXPORT_FAILED"
    assert "đang mở trong Excel" in result["message"]


# --- Documents ----------------------------------------------------------


def test_an_automation_build_without_documents_says_so_plainly(api):
    result = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    assert result["code"] == "SALE_ASN_DOCUMENTS_UNSUPPORTED"


def _wire_documents(api, *, ok=True, create_file=True, invoice="INV-1"):
    def preparer(_xpath, _filter, _query, prepared_path, log=print):
        if create_file:
            Path(prepared_path).write_bytes(b"PK workbook")
        if not ok:
            return {
                "ok": False,
                "code": "SALE_ASN_REPORT_NOT_READY",
                "message": "Report chưa sẵn sàng.",
            }
        return {
            "ok": True,
            "code": "SALE_ASN_DOCUMENTS_PREPARED",
            "message": "Đã ghép.",
            "invoice_no": invoice,
            "prepared_path": str(prepared_path),
            "sheet_names": ["Invoice 1", "PKL 1"],
        }

    api._login.prepare_sale_asn_documents = preparer


def test_a_prepared_export_hands_back_a_token_and_hides_the_temp_path(api):
    _wire_documents(api)

    result = api.prepare_sale_asn_documents("invoice_no", " INV-1 ")

    assert result["code"] == "SALE_ASN_DOCUMENTS_PREPARED"
    assert result["export_token"]
    assert "prepared_path" not in result
    assert result["sheet_names"] == ["Invoice 1", "PKL 1"]


def test_a_failed_export_cleans_up_and_never_hands_back_a_token(api, tmp_path):
    _wire_documents(api, ok=False)

    result = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    assert result["code"] == "SALE_ASN_REPORT_NOT_READY"
    assert "export_token" not in result
    assert list((tmp_path / "sale-asn-export-cache").iterdir()) == []


def test_a_success_without_a_file_is_turned_into_a_merge_failure(api, tmp_path):
    _wire_documents(api, create_file=False)

    result = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    assert result["code"] == "SALE_ASN_REPORT_MERGE_FAILED"
    assert result["ok"] is False
    assert list((tmp_path / "sale-asn-export-cache").iterdir()) == []


def test_a_second_export_discards_the_first_temporary_workbook(api):
    _wire_documents(api)

    first = api.prepare_sale_asn_documents("invoice_no", "INV-1")
    second = api.prepare_sale_asn_documents("invoice_no", "INV-2")

    assert list(api._sale_asn.document_exports) == [second["export_token"]]
    assert first["export_token"] != second["export_token"]


def test_cancelling_an_export_removes_the_temporary_workbook(api):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    result = api.cancel_sale_asn_documents(export["export_token"])

    assert result["code"] == "SALE_ASN_DOCUMENTS_CANCELLED"
    assert api._sale_asn.document_exports == {}


def test_a_document_temp_folder_that_stays_locked_is_logged_not_raised(
    api, monkeypatch
):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    def refuse():
        raise PermissionError("thư mục đang bị khoá")

    api._sale_asn.document_exports[export["export_token"]]["temporary"] = (
        SimpleNamespace(cleanup=refuse)
    )
    lines: list[str] = []
    monkeypatch.setattr(api, "_log", lines.append)

    api.cancel_sale_asn_documents(export["export_token"])

    assert any("Không dọn được file tạm" in line for line in lines)


@pytest.mark.parametrize("raw_path", ["", "   "])
def test_saving_documents_without_a_destination_is_refused(api, raw_path):
    result = api.save_sale_asn_documents("token", raw_path)

    assert result["code"] == "SALE_ASN_DOCUMENTS_SAVE_FAILED"
    assert "Chưa có đường dẫn" in result["message"]


def test_saving_documents_forces_the_xlsx_extension(api, tmp_path):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    result = api.save_sale_asn_documents(
        export["export_token"], str(tmp_path / "INV-1.xls")
    )

    assert result["code"] == "SALE_ASN_DOCUMENTS_EXPORTED"
    assert result["file_name"] == "INV-1.xlsx"
    assert result["invoice_no"] == "INV-1"
    assert (tmp_path / "INV-1.xlsx").read_bytes() == b"PK workbook"
    # Save As chỉ chạy một lần: token phải bị tiêu thụ.
    assert api._sale_asn.document_exports == {}


def test_saving_an_expired_export_asks_the_user_to_download_again(api, tmp_path):
    result = api.save_sale_asn_documents("het-han", str(tmp_path / "a.xlsx"))

    assert result["code"] == "SALE_ASN_DOCUMENTS_EXPIRED"


def test_a_temporary_workbook_that_vanished_expires_the_export(api, tmp_path):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")
    Path(
        api._sale_asn.document_exports[export["export_token"]]["prepared_path"]
    ).unlink()

    result = api.save_sale_asn_documents(
        export["export_token"], str(tmp_path / "INV-1.xlsx")
    )

    assert result["code"] == "SALE_ASN_DOCUMENTS_EXPIRED"
    assert api._sale_asn.document_exports == {}


def test_a_destination_open_in_excel_is_saved_under_the_next_free_name(
    api, tmp_path, monkeypatch
):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")
    target = tmp_path / "INV-1.xlsx"
    target.write_bytes(b"dang mo")
    real_replace = os.replace

    def refuse(src, dst):
        if Path(dst) == target:
            raise PermissionError("file đang mở trong Excel")
        return real_replace(src, dst)

    monkeypatch.setattr(sale_asn_controller.os, "replace", refuse)

    result = api.save_sale_asn_documents(export["export_token"], str(target))

    assert result["renamed_for_open_file"] is True
    assert result["file_name"] == "INV-1 (2).xlsx"
    assert "đã tự lưu bằng tên mới" in result["message"]
    assert target.read_bytes() == b"dang mo"


def test_a_destination_that_cannot_be_written_at_all_reports_the_error(
    api, tmp_path, monkeypatch
):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    def refuse(_src, _dst):
        raise OSError("hết dung lượng")

    monkeypatch.setattr(sale_asn_controller.shutil, "copyfile", refuse)

    result = api.save_sale_asn_documents(
        export["export_token"], str(tmp_path / "INV-1.xlsx")
    )

    assert result["code"] == "SALE_ASN_DOCUMENTS_SAVE_FAILED"
    assert "hết dung lượng" in result["message"]


def test_a_failed_document_copy_never_leaves_its_staging_file_behind(
    api, tmp_path, monkeypatch
):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")
    real_copyfile = shutil.copyfile

    def half_copy(src, dst):
        real_copyfile(src, dst)
        raise OSError("hết dung lượng")

    monkeypatch.setattr(sale_asn_controller.shutil, "copyfile", half_copy)

    api.save_sale_asn_documents(
        export["export_token"], str(tmp_path / "INV-1.xlsx")
    )

    assert [path for path in tmp_path.iterdir() if path.suffix == ".tmp"] == []


def test_a_staging_file_that_cannot_be_removed_keeps_the_real_error(
    api, tmp_path, monkeypatch
):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    def refuse_copy(_src, _dst):
        raise OSError("hết dung lượng")

    monkeypatch.setattr(sale_asn_controller.shutil, "copyfile", refuse_copy)

    def refuse_unlink(_self, **_kwargs):
        raise PermissionError("không xoá được file tạm")

    monkeypatch.setattr(Path, "unlink", refuse_unlink)

    result = api.save_sale_asn_documents(
        export["export_token"], str(tmp_path / "INV-1.xlsx")
    )

    assert "hết dung lượng" in result["message"]


def test_the_free_name_search_for_documents_gives_up_safely(
    api, tmp_path, monkeypatch
):
    _wire_documents(api)
    export = api.prepare_sale_asn_documents("invoice_no", "INV-1")

    def always_locked(_src, _dst):
        raise PermissionError("file đang mở trong Excel")

    monkeypatch.setattr(sale_asn_controller.os, "replace", always_locked)
    monkeypatch.setattr(Path, "exists", lambda _self: True)

    result = api.save_sale_asn_documents(
        export["export_token"], str(tmp_path / "INV-1.xlsx")
    )

    assert result["code"] == "SALE_ASN_DOCUMENTS_SAVE_FAILED"
    assert "Không tìm được tên file trống" in result["message"]


def test_discarding_a_document_token_that_never_existed_reports_nothing(api):
    assert (
        api._sale_asn._discard_sale_asn_document_export("khong-ton-tai") is False
    )
