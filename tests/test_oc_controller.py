"""Vòng đời review Upload OC: snapshot file, token một lần, và lưu form EDI.

`Create Transaction` không idempotent, nên workbook đã chuẩn hoá chỉ được sống
từ Review tới Confirm/Cancel và gắn đúng một token. Mỗi lần user chọn lại file —
kể cả cùng tên, cùng đường dẫn — phải snapshot lại bytes hiện tại.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import wfx_panel.controllers.oc as oc_controller
from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI
from wfx_panel.workbooks.oc import OCWorkbookError


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self, upload=None):
        self.calls: list[tuple] = []
        self.upload = upload

    def check_session(self, log=print):
        return {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"}

    def upload_oc_edi(self, path, buyer, mode, log=print):
        self.calls.append(("upload_oc_edi", Path(path).name, buyer, mode))
        if callable(self.upload):
            return self.upload()
        return self.upload or {
            "ok": True,
            "code": "OC_TRANSACTION_CREATED",
            "message": "Đã tạo transaction.",
        }


@pytest.fixture
def api(tmp_path):
    return PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )


def _prepared(**overrides):
    values = {
        "buyer": "J.LINDEBERG",
        "seasons": ["WH25"],
        "po_count": 2,
        "style_count": 3,
        "total_units": 120,
        "row_count": 5,
        "mode": "new",
        "warnings": ["Zone trống, mặc định FOB."],
        "upload_path": Path("OC-EDI-Upload.xlsx"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _wire_prepare(monkeypatch, outcome):
    seen: list[tuple] = []

    def prepare(source, mode, upload_path):
        seen.append((Path(source).name, mode, Path(upload_path).name))
        if isinstance(outcome, BaseException):
            raise outcome
        Path(upload_path).write_bytes(b"PK edi")
        return (
            outcome(upload_path)
            if callable(outcome)
            else _prepared(upload_path=upload_path, **(outcome or {}))
        )

    monkeypatch.setattr(oc_controller, "prepare_oc_workbook", prepare)
    return seen


def _source(tmp_path, name="OC New.xlsx", data=b"excel"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# --- snapshot file nguồn ------------------------------------------------


def test_a_source_that_cannot_be_read_names_the_excel_lock(tmp_path):
    missing = tmp_path / "khong-ton-tai.xlsx"

    with pytest.raises(OCWorkbookError) as error:
        oc_controller._snapshot_oc_source(missing, tmp_path / "snap.xlsx")

    assert error.value.code == "OC_FILE_READ_FAILED"
    assert "đóng file Excel" in error.value.message


def test_a_source_excel_is_still_writing_is_refused_after_one_retry(
    tmp_path, monkeypatch
):
    source = _source(tmp_path)
    real_stat = Path.stat
    counter = {"n": 0}

    def growing(self, *args, **kwargs):
        stat = real_stat(self, *args, **kwargs)
        if self == source:
            counter["n"] += 1
            # Mỗi lần đọc lại báo kích thước khác: Excel đang lưu dở.
            return SimpleNamespace(
                st_size=stat.st_size + counter["n"],
                st_mtime_ns=stat.st_mtime_ns + counter["n"],
            )
        return stat

    monkeypatch.setattr(Path, "stat", growing)

    with pytest.raises(OCWorkbookError) as error:
        oc_controller._snapshot_oc_source(source, tmp_path / "snap.xlsx")

    assert error.value.code == "OC_FILE_CHANGED_DURING_READ"
    # Hai lượt thử, mỗi lượt đọc stat trước + sau + stat của bản sao.
    assert counter["n"] >= 4


def test_a_stable_source_is_copied_byte_for_byte_with_its_digest(tmp_path):
    import hashlib

    payload = b"x" * (1024 * 1024 + 7)
    source = _source(tmp_path, data=payload)
    target = tmp_path / "snap.xlsx"

    digest = oc_controller._snapshot_oc_source(source, target)

    assert target.read_bytes() == payload
    assert digest == hashlib.sha256(payload).hexdigest()


# --- review -------------------------------------------------------------


def test_a_review_returns_the_business_totals_without_touching_wfx(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, None)
    source = _source(tmp_path)

    result = api.review_oc_upload("new", str(source))

    assert result["code"] == "OC_UPLOAD_REVIEW_READY"
    assert result["buyer"] == "J.LINDEBERG"
    assert result["season"] == "WH25"
    assert (result["po_count"], result["style_count"]) == (2, 3)
    assert result["total_units"] == 120
    assert result["source_file"] == "OC New.xlsx"
    assert len(result["source_sha256"]) == 64
    assert api._login.calls == [], "Review không được chạm EDI"


def test_a_review_with_no_season_shows_a_dash_instead_of_an_empty_cell(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, {"seasons": []})

    result = api.review_oc_upload("new", str(_source(tmp_path)))

    assert result["season"] == "—"
    assert result["seasons"] == []


def test_choosing_a_file_again_snapshots_the_current_bytes_not_the_old_review(
    api, tmp_path, monkeypatch
):
    seen = _wire_prepare(monkeypatch, None)
    source = _source(tmp_path, data=b"phien ban 1")

    first = api.review_oc_upload("new", str(source))
    source.write_bytes(b"phien ban 2 dai hon")
    second = api.review_oc_upload("new", str(source))

    assert first["source_sha256"] != second["source_sha256"]
    assert len(seen) == 2
    # Review cũ phải bị huỷ, nếu không một cú click lặp sẽ upload nhầm bản cũ.
    assert list(api._oc.reviews) == [second["review_token"]]


def test_a_workbook_the_user_must_fix_is_reported_with_every_cell_error(
    api, tmp_path, monkeypatch
):
    _wire_prepare(
        monkeypatch,
        OCWorkbookError(
            "OC_FILE_INVALID",
            "File OC có lỗi.",
            ("Dòng 3: Units phải là số nguyên dương.",),
        ),
    )

    result = api.review_oc_upload("new", str(_source(tmp_path)))

    assert result["code"] == "OC_FILE_INVALID"
    assert result["errors"] == ["Dòng 3: Units phải là số nguyên dương."]
    assert result["source_file"] == "OC New.xlsx"
    assert api._oc.reviews == {}, "Lỗi file thì không được giữ review nào"


def test_an_unexpected_failure_still_cleans_up_the_temporary_review_folder(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, MemoryError("hết bộ nhớ"))

    result = api.review_oc_upload("new", str(_source(tmp_path)))

    assert result["ok"] is False
    # Lỗi bất ngờ vẫn không được để lại thư mục review tạm trong data dir.
    assert list((tmp_path / "oc-upload-cache").iterdir()) == []
    assert api._oc.reviews == {}


def test_cancelling_a_review_removes_it_and_never_touches_wfx(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, None)
    review = api.review_oc_upload("new", str(_source(tmp_path)))

    result = api.cancel_oc_upload_review(review["review_token"])

    assert result["code"] == "OC_UPLOAD_REVIEW_CANCELLED"
    assert api._oc.reviews == {}
    assert api._login.calls == []


def test_cancelling_a_token_that_is_already_gone_is_still_a_clean_answer(api):
    assert (
        api.cancel_oc_upload_review("khong-ton-tai")["code"]
        == "OC_UPLOAD_REVIEW_CANCELLED"
    )


def test_a_temporary_folder_windows_still_locks_is_logged_not_raised(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, None)
    review = api.review_oc_upload("new", str(_source(tmp_path)))
    stored = api._oc.reviews[review["review_token"]]

    def refuse():
        raise PermissionError("thư mục đang bị khoá")

    stored["temporary"] = SimpleNamespace(cleanup=refuse)
    lines: list[str] = []
    monkeypatch.setattr(api, "_log", lines.append)

    assert api._oc._discard_oc_upload_review(review["review_token"]) is True
    assert any("Không dọn được workbook review tạm" in line for line in lines)


# --- lưu form EDI -------------------------------------------------------


def _review_token(api, tmp_path, monkeypatch):
    _wire_prepare(monkeypatch, None)
    return api.review_oc_upload("new", str(_source(tmp_path)))["review_token"]


@pytest.mark.parametrize("raw_path", ["", "   "])
def test_saving_without_a_destination_is_refused(api, raw_path):
    result = api.save_oc_upload_file("token", raw_path)

    assert result["code"] == "OC_UPLOAD_FILE_SAVE_FAILED"
    assert "Chưa có đường dẫn" in result["message"]


def test_saving_forces_the_xlsx_extension(api, tmp_path, monkeypatch):
    token = _review_token(api, tmp_path, monkeypatch)

    result = api.save_oc_upload_file(token, str(tmp_path / "EDI.xls"))

    assert result["code"] == "OC_UPLOAD_FILE_SAVED"
    assert result["file_name"] == "EDI.xlsx"
    assert (tmp_path / "EDI.xlsx").read_bytes() == b"PK edi"
    # Lưu file không được tiêu thụ review: user vẫn phải bấm Xác nhận Upload.
    assert token in api._oc.reviews


def test_saving_against_an_expired_review_says_so(api, tmp_path):
    result = api.save_oc_upload_file("het-han", str(tmp_path / "EDI.xlsx"))

    assert result["code"] == "OC_UPLOAD_REVIEW_EXPIRED"


def test_a_generated_workbook_that_vanished_is_reported(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)
    Path(api._oc.reviews[token]["prepared"].upload_path).unlink()

    result = api.save_oc_upload_file(token, str(tmp_path / "EDI.xlsx"))

    assert result["code"] == "OC_UPLOAD_FILE_MISSING"


def test_a_destination_open_in_excel_is_saved_under_the_next_free_name(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)
    target = tmp_path / "EDI.xlsx"
    target.write_bytes(b"dang mo")
    real_replace = os.replace

    def refuse(src, dst):
        if Path(dst) == target:
            raise PermissionError("file đang mở trong Excel")
        return real_replace(src, dst)

    monkeypatch.setattr(oc_controller.os, "replace", refuse)

    result = api.save_oc_upload_file(token, str(target))

    assert result["code"] == "OC_UPLOAD_FILE_SAVED"
    assert result["renamed_for_open_file"] is True
    assert result["file_name"] == "EDI (2).xlsx"
    assert "đã tự lưu bằng tên mới" in result["message"]
    assert target.read_bytes() == b"dang mo", "file đang mở phải nguyên vẹn"


def test_a_folder_that_refuses_every_name_reports_a_save_failure(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)

    def refuse(_src, _dst):
        raise PermissionError("thư mục chỉ đọc")

    monkeypatch.setattr(oc_controller.os, "replace", refuse)

    result = api.save_oc_upload_file(token, str(tmp_path / "EDI.xlsx"))

    assert result["code"] == "OC_UPLOAD_FILE_SAVE_FAILED"
    assert "thư mục chỉ đọc" in result["message"]


def test_a_failed_copy_never_leaves_its_staging_file_behind(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)
    real_copyfile = shutil.copyfile

    def half_copy(src, dst):
        real_copyfile(src, dst)
        raise OSError("hết dung lượng")

    monkeypatch.setattr(oc_controller.shutil, "copyfile", half_copy)

    result = api.save_oc_upload_file(token, str(tmp_path / "EDI.xlsx"))

    assert result["code"] == "OC_UPLOAD_FILE_SAVE_FAILED"
    assert [path.name for path in tmp_path.iterdir() if path.suffix == ".tmp"] == []


def test_a_staging_file_that_cannot_be_removed_does_not_mask_the_real_error(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)

    def refuse_copy(_src, _dst):
        raise OSError("hết dung lượng")

    monkeypatch.setattr(oc_controller.shutil, "copyfile", refuse_copy)

    def refuse_unlink(_self, **_kwargs):
        raise PermissionError("không xoá được file tạm")

    monkeypatch.setattr(Path, "unlink", refuse_unlink)

    result = api.save_oc_upload_file(token, str(tmp_path / "EDI.xlsx"))

    assert result["code"] == "OC_UPLOAD_FILE_SAVE_FAILED"
    assert "hết dung lượng" in result["message"]


def test_the_free_name_search_gives_up_instead_of_looping_forever(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)

    def always_locked(_src, _dst):
        raise PermissionError("file đang mở trong Excel")

    monkeypatch.setattr(oc_controller.os, "replace", always_locked)
    # Mọi tên "EDI (n).xlsx" đều đã tồn tại: vòng tìm tên trống phải dừng ở
    # ngưỡng an toàn thay vì chạy mãi.
    monkeypatch.setattr(Path, "exists", lambda _self: True)

    result = api.save_oc_upload_file(token, str(tmp_path / "EDI.xlsx"))

    assert result["code"] == "OC_UPLOAD_FILE_SAVE_FAILED"
    assert "Không tìm được tên file trống" in result["message"]


# --- xác nhận upload ----------------------------------------------------


def test_confirming_uploads_exactly_the_reviewed_workbook_then_drops_it(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)

    result = api.confirm_oc_upload(token)

    assert result["code"] == "OC_TRANSACTION_CREATED"
    assert result["source_file"] == "OC New.xlsx"
    assert result["buyer"] == "J.LINDEBERG"
    assert api._login.calls == [
        ("upload_oc_edi", "OC-EDI-Upload.xlsx", "J.LINDEBERG", "new")
    ]
    assert api._oc.reviews == {}


def test_confirming_an_expired_review_never_reaches_edi(api):
    result = api.confirm_oc_upload("het-han")

    assert result["code"] == "OC_UPLOAD_REVIEW_EXPIRED"
    assert api._login.calls == []


def test_a_lost_session_keeps_the_review_so_the_retry_can_reuse_it(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)
    api._login.upload = {
        "ok": False,
        "code": "NOT_LOGGED_IN",
        "message": "Phiên đã hết hạn.",
    }

    api._oc.confirm_oc_upload(token)

    # Chưa hề chạm EDI nên auto-relogin được phép chạy lại đúng action này.
    assert token in api._oc.reviews


def test_an_upload_that_crashes_drops_the_review_instead_of_replaying_it(
    api, tmp_path, monkeypatch
):
    token = _review_token(api, tmp_path, monkeypatch)

    def explode():
        raise RuntimeError("CDP mất kết nối giữa lúc Process Package")

    api._login.upload = explode

    result = api.confirm_oc_upload(token)

    assert result["ok"] is False
    assert api._oc.reviews == {}, (
        "Không biết EDI đã nhận hay chưa thì tuyệt đối không giữ token để "
        "upload lại"
    )


# --- upload thẳng (không qua review) ------------------------------------


def test_a_direct_upload_validates_then_sends_the_normalised_workbook(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, None)
    lines: list[str] = []
    monkeypatch.setattr(api, "_log", lines.append)

    result = api.upload_oc("new", str(_source(tmp_path)))

    assert result["code"] == "OC_TRANSACTION_CREATED"
    assert result["source_file"] == "OC New.xlsx"
    assert result["row_count"] == 5
    assert result["buyer"] == "J.LINDEBERG"
    assert result["warnings"] == ["Zone trống, mặc định FOB."]
    assert any("Workbook hợp lệ" in line for line in lines)
    assert any("Zone trống" in line for line in lines)


def test_a_direct_upload_of_a_broken_file_never_opens_edi(
    api, tmp_path, monkeypatch
):
    _wire_prepare(
        monkeypatch,
        OCWorkbookError(
            "OC_FILE_INVALID", "File OC có lỗi.", ("Dòng 2: thiếu Buyer.",)
        ),
    )

    result = api.upload_oc("revision", str(_source(tmp_path)))

    assert result["code"] == "OC_FILE_INVALID"
    assert result["errors"] == ["Dòng 2: thiếu Buyer."]
    assert result["mode"] == "revision"
    assert api._login.calls == []


def test_a_direct_upload_cleans_up_its_temporary_folder(
    api, tmp_path, monkeypatch
):
    _wire_prepare(monkeypatch, None)

    api.upload_oc("new", str(_source(tmp_path)))

    assert list((tmp_path / "oc-upload-cache").iterdir()) == []


# --- các flow chỉ delegate ---------------------------------------------


def test_confirm_pending_passes_the_tab_through_untouched(api):
    calls: list[str] = []
    api._login.confirm_oc_pending = lambda mode, log=print: (
        calls.append(mode) or {"ok": True, "code": "OC_CONFIRMED", "message": "ok"}
    )

    assert api.confirm_oc_pending("  Revision ")["code"] == "OC_CONFIRMED"
    assert calls == ["revision"]


def test_reject_all_runs_on_whatever_tab_wfx_currently_shows(api):
    calls: list[str] = []
    api._login.reject_all_oc_pending = lambda log=print: (
        calls.append("reject")
        or {"ok": True, "code": "OC_REJECTED", "message": "ok"}
    )

    assert api.reject_all_oc_pending()["code"] == "OC_REJECTED"
    assert calls == ["reject"]
