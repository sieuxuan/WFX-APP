"""Hộp thoại file khi pywebview hoặc ổ đĩa không trả về thứ mong đợi.

CLAUDE.md: hộp thoại nhớ thư mục export gần nhất và chỉ hỗ trợ `.xlsx`. Một
lượt lưu prefs hỏng không được làm hỏng chính lượt chọn file, và một đường dẫn
pywebview trả về sai kiểu phải thành lỗi có mã chứ không nổ ra ngoài.
"""

from __future__ import annotations

import pytest

from tests.test_file_dialogs import Window, _controller, app  # noqa: F401
from wfx_panel import prefs
from wfx_panel.app import dialogs as app_dialogs


class _BadSelection:
    """Kết quả dialog không phải str/list — pywebview đôi khi trả None/object."""

    def __getitem__(self, _index):
        raise TypeError("không phải dãy đường dẫn")


def _refuse_prefs(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(app_dialogs.prefs, "save_prefs", refuse)


# --- pywebview trả về thứ không đọc được ---------------------------------


@pytest.mark.parametrize(
    ("method", "args", "expected_code"),
    [
        ("choose_costing_import_file", (), "COSTING_FILE_DIALOG_FAILED"),
        (
            "choose_costing_export_file",
            ("SWN0000001",),
            "COSTING_FILE_DIALOG_FAILED",
        ),
        ("choose_report_export_dir", (), "REPORT_DIR_DIALOG_FAILED"),
        ("choose_oc_upload_export_file", (), "OC_FILE_DIALOG_FAILED"),
        (
            "choose_sale_asn_export_file",
            ("INV-1",),
            "SALE_ASN_FILE_DIALOG_FAILED",
        ),
        (
            "choose_sale_asn_price_check_export_file",
            ("INV-1",),
            "SALE_ASN_FILE_DIALOG_FAILED",
        ),
    ],
)
def test_a_dialog_result_that_is_not_a_path_is_a_clear_error(
    app, method, args, expected_code  # noqa: F811
):
    app.window = Window(selection=_BadSelection())

    result = getattr(_controller(app), method)(*args)

    assert result["ok"] is False
    assert result["code"] == expected_code
    assert "đường dẫn" in result["message"]


# --- prefs không ghi được -------------------------------------------------


def test_an_export_folder_that_cannot_be_remembered_still_returns_the_file(
    app, tmp_path, monkeypatch  # noqa: F811
):
    app.window = Window(selection=str(tmp_path / "Costing.xlsx"))
    _refuse_prefs(monkeypatch)

    result = _controller(app).choose_costing_export_file("SWN0000001")

    assert result["code"] == "COSTING_EXPORT_PATH_SELECTED"
    assert result["file_name"] == "Costing.xlsx"


def test_a_report_folder_that_cannot_be_remembered_is_still_used(
    app, tmp_path, monkeypatch  # noqa: F811
):
    app.window = Window(selection=str(tmp_path))
    _refuse_prefs(monkeypatch)

    result = _controller(app).choose_report_export_dir()

    assert result["code"] == "REPORT_DIR_SELECTED"


def test_a_sale_asn_import_folder_that_cannot_be_remembered_is_not_fatal(
    app, tmp_path, monkeypatch  # noqa: F811
):
    source = tmp_path / "SaleASN.xlsx"
    source.write_bytes(b"x")
    app.window = Window(selection=str(source))
    _refuse_prefs(monkeypatch)

    result = _controller(app).choose_sale_asn_import_file()

    assert result["code"] == "SALE_ASN_FILE_SELECTED"
    assert result["file_name"] == "SaleASN.xlsx"


def test_the_export_folder_is_remembered_for_the_next_time(
    app, tmp_path  # noqa: F811
):
    app.window = Window(selection=str(tmp_path / "Costing.xlsx"))

    _controller(app).choose_costing_export_file("SWN0000001")

    assert prefs.load_prefs(tmp_path)["costing_export_dir"] == str(tmp_path)


# --- chỉ .xlsx ------------------------------------------------------------


def test_an_import_file_that_is_not_an_xlsx_is_refused(
    app, tmp_path  # noqa: F811
):
    source = tmp_path / "Costing.xls"
    source.write_bytes(b"x")
    app.window = Window(selection=str(source))

    result = _controller(app).choose_costing_import_file()

    assert result["code"] == "COSTING_FILE_TYPE_UNSUPPORTED"


def test_an_export_target_without_the_suffix_gets_it(app, tmp_path):  # noqa: F811
    app.window = Window(selection=str(tmp_path / "Costing"))

    result = _controller(app).choose_costing_export_file("SWN0000001")

    assert result["file_name"] == "Costing.xlsx"


# --- form tiếp tục Sale ASN ----------------------------------------------


def test_a_continue_template_that_cannot_be_written_is_reported(
    app, tmp_path, monkeypatch  # noqa: F811
):
    app.window = Window(selection=str(tmp_path / "TiepTuc.xlsx"))

    def refuse(_target, _rows):
        raise OSError("ổ đĩa đầy")

    monkeypatch.setattr(app_dialogs, "write_sale_asn_template", refuse)

    result = _controller(app).save_sale_asn_continue_template([])

    assert result["ok"] is False
    assert result["code"] == "SALE_ASN_TEMPLATE_EXPORT_FAILED"
    assert "ổ đĩa đầy" in result["message"]
