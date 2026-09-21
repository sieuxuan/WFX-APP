"""Hộp thoại chọn/lưu file và các mẫu Excel tải từ panel.

`wfx_panel/app/dialogs.py` ở mức 48%: phần Costing đã có test, nhưng OC,
Sale ASN, Tạo Style, thư mục báo cáo và mọi nhánh lỗi thì chưa. Ràng buộc
CLAUDE.md nằm đúng ở phần chưa chạy:

* "`Tải form Excel` phải hỏi nơi lưu TRƯỚC khi lấy dropdown, vì bước lấy
  dropdown có thể gọi GitHub hoặc chạy nguyên một lượt quét WFX."
* "Hộp thoại nhớ thư mục export gần nhất; Settings dùng một tùy chọn chung để
  mở mọi file Excel sau khi tải từ app. Thư mục chứa file luôn tự mở sau mọi
  download/export thành công."
* "Style copy có dropdown lấy Article Name từ Article List, chỉ nhận
  `Article Category = Apparel`."
* "hộp thoại chỉ hỗ trợ `.xlsx`."
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wfx_panel import panel_app, prefs
from wfx_panel.app import dialogs as app_dialogs
from wfx_panel.app import helpers as app_helpers


class Window:
    """Cửa sổ pywebview giả: trả đúng thứ native dialog trả về."""

    def __init__(self, selection=None, *, error=None):
        self.selection = selection
        self.error = error
        self.calls: list[tuple] = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        if self.error is not None:
            raise self.error
        return self.selection


@pytest.fixture
def app(tmp_path, monkeypatch):
    """PanelApp thật, base_dir tạm, không chạm Explorer hay Excel."""
    instance = panel_app.PanelApp()
    instance._base_dir = tmp_path
    instance.window = Window()
    opened: list[str] = []
    revealed: list[str] = []
    monkeypatch.setattr(
        app_dialogs,
        "_open_downloaded_file",
        lambda value: opened.append(str(value)) or True,
    )
    monkeypatch.setattr(
        app_dialogs,
        "_reveal_downloaded_file",
        lambda value: revealed.append(str(value)) or True,
    )
    instance.opened = opened
    instance.revealed = revealed
    return instance


def _controller(app) -> app_dialogs.FileDialogController:
    return app_dialogs.FileDialogController(app)


# --- mở file sau khi tải --------------------------------------------------


def test_a_downloaded_excel_is_opened_and_revealed_by_default(app, tmp_path):
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")

    assert _controller(app)._handle_downloaded_excel(target) is True
    assert app.opened == [str(target)]
    assert app.revealed == [str(target)]


def test_the_shared_setting_can_turn_opening_off_but_never_revealing(
    app, tmp_path, monkeypatch
):
    prefs.save_prefs(tmp_path, open_excel_file_after_download=False)
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")

    _controller(app)._handle_downloaded_excel(target)

    assert app.opened == []
    assert app.revealed == [str(target)]


def test_a_file_windows_cannot_open_is_logged_but_still_revealed(
    app, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_dialogs, "_open_downloaded_file", lambda _value: False)
    logs: list[str] = []
    monkeypatch.setattr(app.api, "_log", logs.append)

    _controller(app)._handle_downloaded_excel(tmp_path / "a.xlsx")

    assert any("không mở được" in line for line in logs)
    assert app.revealed


def test_a_folder_explorer_cannot_show_is_logged(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_dialogs, "_reveal_downloaded_file", lambda _value: False)
    logs: list[str] = []
    monkeypatch.setattr(app.api, "_log", logs.append)

    assert _controller(app)._handle_downloaded_excel(tmp_path / "a.xlsx") is False
    assert any("Explorer không hiện được" in line for line in logs)


def test_reveal_download_is_a_thin_pass_through(app, tmp_path):
    assert _controller(app).reveal_download(tmp_path / "a.xlsx") is True
    assert app.revealed == [str(tmp_path / "a.xlsx")]


# --- không có cửa sổ ------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "args", "code"),
    [
        ("choose_costing_import_file", (), "COSTING_FILE_DIALOG_UNAVAILABLE"),
        ("choose_costing_export_file", ("S",), "COSTING_FILE_DIALOG_UNAVAILABLE"),
        ("choose_report_export_dir", (), "REPORT_DIR_DIALOG_UNAVAILABLE"),
        ("choose_oc_upload_file", ("new",), "OC_FILE_DIALOG_UNAVAILABLE"),
        ("choose_oc_upload_export_file", (), "OC_FILE_DIALOG_UNAVAILABLE"),
        ("choose_sale_asn_export_file", ("INV",), "SALE_ASN_FILE_DIALOG_UNAVAILABLE"),
        (
            "choose_sale_asn_price_check_export_file",
            ("INV",),
            "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
        ),
        ("choose_sale_asn_import_file", (), "SALE_ASN_FILE_DIALOG_UNAVAILABLE"),
        ("choose_style_import_file", (), "STYLE_FILE_DIALOG_UNAVAILABLE"),
        ("download_style_template", (), "STYLE_FILE_DIALOG_UNAVAILABLE"),
        ("download_oc_template", (), "OC_FILE_DIALOG_UNAVAILABLE"),
        ("download_sale_asn_template", (), "SALE_ASN_FILE_DIALOG_UNAVAILABLE"),
        (
            "save_sale_asn_continue_template",
            ([],),
            "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
        ),
    ],
)
def test_every_dialog_reports_a_missing_window_instead_of_crashing(
    app, method, args, code
):
    app.window = None

    assert getattr(_controller(app), method)(*args)["code"] == code


# --- lỗi native dialog ----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "args", "code"),
    [
        ("choose_costing_import_file", (), "COSTING_FILE_DIALOG_FAILED"),
        ("choose_costing_export_file", ("S",), "COSTING_FILE_DIALOG_FAILED"),
        ("choose_report_export_dir", (), "REPORT_DIR_DIALOG_FAILED"),
        ("choose_oc_upload_file", ("new",), "OC_FILE_DIALOG_FAILED"),
        ("choose_oc_upload_export_file", (), "OC_FILE_DIALOG_FAILED"),
        ("choose_sale_asn_export_file", ("INV",), "SALE_ASN_FILE_DIALOG_FAILED"),
        (
            "choose_sale_asn_price_check_export_file",
            ("INV",),
            "SALE_ASN_FILE_DIALOG_FAILED",
        ),
        ("choose_sale_asn_import_file", (), "SALE_ASN_FILE_DIALOG_FAILED"),
        ("choose_style_import_file", (), "STYLE_FILE_DIALOG_FAILED"),
        ("download_style_template", (), "STYLE_FILE_DIALOG_FAILED"),
        ("download_oc_template", (), "OC_FILE_DIALOG_FAILED"),
        ("download_sale_asn_template", (), "SALE_ASN_FILE_DIALOG_FAILED"),
        ("save_sale_asn_continue_template", ([],), "SALE_ASN_FILE_DIALOG_FAILED"),
    ],
)
def test_every_dialog_reports_a_native_failure(app, method, args, code):
    app.window = Window(error=RuntimeError("WinForms lỗi"))

    result = getattr(_controller(app), method)(*args)

    assert result["code"] == code
    assert "WinForms lỗi" in result["message"]


# --- hủy ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "args", "code"),
    [
        ("choose_costing_import_file", (), "COSTING_FILE_DIALOG_CANCELLED"),
        ("choose_costing_export_file", ("S",), "COSTING_FILE_DIALOG_CANCELLED"),
        ("choose_report_export_dir", (), "REPORT_DIR_DIALOG_CANCELLED"),
        ("choose_oc_upload_file", ("new",), "OC_FILE_DIALOG_CANCELLED"),
        ("choose_oc_upload_export_file", (), "OC_FILE_DIALOG_CANCELLED"),
        ("choose_sale_asn_export_file", ("INV",), "SALE_ASN_FILE_DIALOG_CANCELLED"),
        (
            "choose_sale_asn_price_check_export_file",
            ("INV",),
            "SALE_ASN_FILE_DIALOG_CANCELLED",
        ),
        ("choose_sale_asn_import_file", (), "SALE_ASN_FILE_DIALOG_CANCELLED"),
        ("choose_style_import_file", (), "STYLE_FILE_DIALOG_CANCELLED"),
        ("download_style_template", (), "STYLE_FILE_DIALOG_CANCELLED"),
        ("download_oc_template", (), "OC_FILE_DIALOG_CANCELLED"),
        ("download_sale_asn_template", (), "SALE_ASN_FILE_DIALOG_CANCELLED"),
        ("save_sale_asn_continue_template", ([],), "SALE_ASN_FILE_DIALOG_CANCELLED"),
    ],
)
def test_every_dialog_is_clean_when_the_user_cancels(app, method, args, code):
    app.window = Window(selection=None)

    assert getattr(_controller(app), method)(*args)["code"] == code
    assert app.revealed == []


# --- đường dẫn trả về dạng lạ --------------------------------------------


@pytest.mark.parametrize(
    ("method", "args", "code"),
    [
        ("choose_costing_import_file", (), "COSTING_FILE_DIALOG_FAILED"),
        ("choose_report_export_dir", (), "REPORT_DIR_DIALOG_FAILED"),
        ("choose_oc_upload_file", ("new",), "OC_FILE_DIALOG_FAILED"),
        ("choose_sale_asn_import_file", (), "SALE_ASN_FILE_DIALOG_FAILED"),
        ("choose_style_import_file", (), "STYLE_FILE_DIALOG_FAILED"),
    ],
)
def test_a_dialog_result_without_a_path_is_a_failure_not_a_crash(
    app, method, args, code
):
    app.window = Window(selection=object())

    assert getattr(_controller(app), method)(*args)["code"] == code


# --- OC -------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["", "  ", "khac"])
def test_the_oc_upload_mode_must_be_new_or_revise(app, mode):
    assert _controller(app).choose_oc_upload_file(mode)["code"] == "OC_MODE_INVALID"


@pytest.mark.parametrize("mode", ["new", "REVISE", " Revise "])
def test_the_oc_upload_mode_is_normalised(app, tmp_path, mode):
    chosen = tmp_path / "oc.xlsx"
    chosen.write_bytes(b"x")
    app.window = Window(selection=(str(chosen),))

    result = _controller(app).choose_oc_upload_file(mode)

    assert result["code"] == "OC_FILE_SELECTED"
    assert result["mode"] == mode.strip().casefold()


def test_an_oc_file_that_is_not_xlsx_is_refused(app, tmp_path):
    chosen = tmp_path / "oc.xls"
    chosen.write_bytes(b"x")
    app.window = Window(selection=(str(chosen),))

    assert (
        _controller(app).choose_oc_upload_file("new")["code"]
        == "OC_FILE_TYPE_UNSUPPORTED"
    )


def test_the_edi_workbook_name_is_derived_from_the_source_file(app, tmp_path):
    app.window = Window(selection=str(tmp_path / "chon"))

    result = _controller(app).choose_oc_upload_export_file("PO/2026:1")

    assert app.window.calls[-1][1]["save_filename"] == "WFX-Smart-PO 2026 1.xlsx"
    assert result["file_name"].endswith(".xlsx")


def test_the_edi_workbook_falls_back_to_a_default_name(app, tmp_path):
    app.window = Window(selection=str(tmp_path / "chon"))

    _controller(app).choose_oc_upload_export_file("")

    assert app.window.calls[-1][1]["save_filename"] == "WFX-Smart-OC-EDI-Upload.xlsx"


def test_the_oc_template_is_written_then_revealed(app, tmp_path, monkeypatch):
    target = tmp_path / "form.xlsx"
    app.window = Window(selection=str(target))
    written: list[Path] = []
    monkeypatch.setattr(
        app_dialogs, "write_oc_input_template", lambda path: written.append(path)
    )

    result = _controller(app).download_oc_template()

    assert result["code"] == "OC_TEMPLATE_EXPORTED"
    assert written == [target]
    assert app.revealed == [str(target)]


def test_a_failing_oc_template_write_is_reported(app, tmp_path, monkeypatch):
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    monkeypatch.setattr(
        app_dialogs,
        "write_oc_input_template",
        lambda _path: (_ for _ in ()).throw(OSError("ổ đĩa đầy")),
    )

    result = _controller(app).download_oc_template()

    assert result["code"] == "OC_TEMPLATE_EXPORT_FAILED"
    assert "ổ đĩa đầy" in result["message"]


# --- thư mục báo cáo ------------------------------------------------------


def test_the_report_folder_is_remembered_for_next_time(app, tmp_path):
    folder = tmp_path / "bao-cao"
    folder.mkdir()
    app.window = Window(selection=(str(folder),))

    result = _controller(app).choose_report_export_dir()

    assert result["code"] == "REPORT_DIR_SELECTED"
    assert prefs.load_prefs(tmp_path)["report_export_dir"] == str(folder.resolve())

    _controller(app).choose_report_export_dir()
    assert app.window.calls[-1][1]["directory"] == str(folder.resolve())


def test_a_remembered_folder_that_vanished_is_not_reused(app, tmp_path):
    prefs.save_prefs(tmp_path, report_export_dir=str(tmp_path / "khong-con"))
    folder = tmp_path / "moi"
    folder.mkdir()
    app.window = Window(selection=(str(folder),))

    _controller(app).choose_report_export_dir()

    assert app.window.calls[0][1]["directory"] == ""


def test_opening_the_report_folder_needs_it_to_still_exist(app, tmp_path):
    assert (
        _controller(app).open_report_export_dir(str(tmp_path / "khong-co"))["code"]
        == "REPORT_DIR_MISSING"
    )


def test_opening_the_report_folder_uses_the_shell(app, tmp_path, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(app_dialogs.os, "name", "nt")
    monkeypatch.setattr(
        app_dialogs.os, "startfile", lambda path: opened.append(str(path)),
        raising=False,
    )

    result = _controller(app).open_report_export_dir(str(tmp_path))

    assert result["code"] == "REPORT_DIR_OPENED"
    assert opened == [str(tmp_path)]


def test_a_shell_failure_opening_the_report_folder_is_reported(
    app, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_dialogs.os, "name", "nt")
    monkeypatch.setattr(
        app_dialogs.os,
        "startfile",
        lambda _path: (_ for _ in ()).throw(OSError("shell lỗi")),
        raising=False,
    )

    result = _controller(app).open_report_export_dir(str(tmp_path))

    assert result["code"] == "REPORT_DIR_MISSING"
    assert "OSError" in result["message"]


# --- Sale ASN -------------------------------------------------------------


def test_the_sale_asn_export_name_comes_from_the_invoice(app, tmp_path):
    app.window = Window(selection=str(tmp_path / "chon"))

    result = _controller(app).choose_sale_asn_export_file("INV/2026:9")

    assert app.window.calls[-1][1]["save_filename"] == "INV 2026 9.xlsx"
    assert result["code"] == "SALE_ASN_EXPORT_PATH_SELECTED"


def test_an_export_without_an_extension_gets_xlsx(app, tmp_path):
    app.window = Window(selection=str(tmp_path / "chon"))

    result = _controller(app).choose_sale_asn_export_file("INV")

    assert result["file_name"].endswith(".xlsx")


def test_the_price_check_export_name_is_prefixed(app, tmp_path):
    app.window = Window(selection=str(tmp_path / "chon"))

    result = _controller(app).choose_sale_asn_price_check_export_file("INV")

    assert (
        app.window.calls[-1][1]["save_filename"]
        == "WFX-Smart-Sale-ASN-Check-INV.xlsx"
    )
    assert result["code"] == "SALE_ASN_PRICE_EXPORT_PATH_SELECTED"


def test_the_sale_asn_import_folder_is_remembered(app, tmp_path):
    folder = tmp_path / "nhap"
    folder.mkdir()
    chosen = folder / "asn.xlsx"
    chosen.write_bytes(b"x")
    app.window = Window(selection=(str(chosen),))

    result = _controller(app).choose_sale_asn_import_file()

    assert result["code"] == "SALE_ASN_FILE_SELECTED"
    assert prefs.load_prefs(tmp_path)["sale_asn_import_dir"] == str(folder.resolve())

    _controller(app).choose_sale_asn_import_file()
    assert app.window.calls[-1][1]["directory"] == str(folder.resolve())


def test_a_sale_asn_file_that_is_not_xlsx_is_refused(app, tmp_path):
    chosen = tmp_path / "asn.csv"
    chosen.write_bytes(b"x")
    app.window = Window(selection=(str(chosen),))

    assert (
        _controller(app).choose_sale_asn_import_file()["code"]
        == "SALE_ASN_FILE_TYPE_UNSUPPORTED"
    )


def test_the_sale_asn_template_is_written_then_revealed(app, tmp_path, monkeypatch):
    target = tmp_path / "form.xlsx"
    app.window = Window(selection=str(target))
    monkeypatch.setattr(app_dialogs, "write_sale_asn_template", lambda path: path)

    result = _controller(app).download_sale_asn_template()

    assert result["code"] == "SALE_ASN_TEMPLATE_EXPORTED"
    assert app.revealed == [str(target)]


def test_a_failing_sale_asn_template_write_is_reported(app, tmp_path, monkeypatch):
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    monkeypatch.setattr(
        app_dialogs,
        "write_sale_asn_template",
        lambda _path: (_ for _ in ()).throw(OSError("ổ đĩa đầy")),
    )

    assert (
        _controller(app).download_sale_asn_template()["code"]
        == "SALE_ASN_TEMPLATE_EXPORT_FAILED"
    )


def test_the_continue_template_reports_how_many_po_it_wrote(
    app, tmp_path, monkeypatch
):
    target = tmp_path / "tiep-tuc.xlsx"
    app.window = Window(selection=str(target))
    seen: list[list] = []
    monkeypatch.setattr(
        app_dialogs,
        "write_sale_asn_template",
        lambda path, rows=None: seen.append(list(rows or [])) or path,
    )

    result = _controller(app).save_sale_asn_continue_template(
        [{"PO No": "1"}, {"PO No": "2"}]
    )

    assert result["code"] == "SALE_ASN_TEMPLATE_EXPORTED"
    assert "Đã xuất 2 PO" in result["message"]
    assert seen == [[{"PO No": "1"}, {"PO No": "2"}]]


def test_the_continue_template_accepts_an_empty_row_list(app, tmp_path, monkeypatch):
    app.window = Window(selection=str(tmp_path / "t.xlsx"))
    monkeypatch.setattr(
        app_dialogs, "write_sale_asn_template", lambda path, rows=None: path
    )

    assert "Đã xuất 0 PO" in _controller(app).save_sale_asn_continue_template(
        None
    )["message"]


def test_the_price_check_export_applies_the_shared_excel_option(
    app, tmp_path, monkeypatch
):
    target = tmp_path / "check.xlsx"
    target.write_bytes(b"x")
    monkeypatch.setattr(
        app,
        "_export_sale_asn_price_check",
        lambda _payload, _path: {"ok": True, "export_path": str(target)},
    )

    result = _controller(app).export_sale_asn_price_check({}, str(target))

    assert result["ok"] is True
    assert app.revealed == [str(target)]


def test_a_failed_price_check_export_is_never_revealed(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        app,
        "_export_sale_asn_price_check",
        lambda _payload, _path: {"ok": False, "code": "X"},
    )

    _controller(app).export_sale_asn_price_check({}, "x")

    assert app.revealed == []


# --- Tạo Style ------------------------------------------------------------


def test_a_style_file_that_is_not_xlsx_is_refused(app, tmp_path):
    chosen = tmp_path / "style.xls"
    chosen.write_bytes(b"x")
    app.window = Window(selection=(str(chosen),))

    assert (
        _controller(app).choose_style_import_file()["code"]
        == "STYLE_FILE_TYPE_UNSUPPORTED"
    )


def test_the_style_template_asks_where_to_save_before_fetching_dropdowns(
    app, tmp_path, monkeypatch
):
    """CLAUDE.md: hỏi nơi lưu TRƯỚC, vì lấy dropdown có thể quét cả WFX."""
    order: list[str] = []
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    original = app.window.create_file_dialog

    def dialog(*args, **kwargs):
        order.append("dialog")
        return original(*args, **kwargs)

    app.window.create_file_dialog = dialog
    monkeypatch.setattr(
        app.api,
        "ensure_catalog_style_options",
        lambda _group, _force: order.append("options") or {"ok": True, "options": {}},
    )
    monkeypatch.setattr(
        app_dialogs, "write_style_template", lambda path, options=None: path
    )

    result = _controller(app).download_style_template("123")

    assert result["code"] == "STYLE_TEMPLATE_EXPORTED"
    assert order == ["dialog", "options"]


def test_the_style_template_never_fetches_dropdowns_when_cancelled(
    app, monkeypatch
):
    app.window = Window(selection=None)
    calls: list[int] = []
    monkeypatch.setattr(
        app.api,
        "ensure_catalog_style_options",
        lambda *_a: calls.append(1) or {"ok": True},
    )

    _controller(app).download_style_template("123")

    assert calls == []


def test_a_failing_dropdown_scan_is_returned_as_is(app, tmp_path, monkeypatch):
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    monkeypatch.setattr(
        app.api,
        "ensure_catalog_style_options",
        lambda *_a: {"ok": False, "code": "STYLE_OPTIONS_FAILED"},
    )

    assert (
        _controller(app).download_style_template("123")["code"]
        == "STYLE_OPTIONS_FAILED"
    )


def test_the_style_template_without_a_group_skips_the_dropdown_scan(
    app, tmp_path, monkeypatch
):
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    calls: list[int] = []
    monkeypatch.setattr(
        app.api, "ensure_catalog_style_options", lambda *_a: calls.append(1)
    )
    monkeypatch.setattr(
        app_dialogs, "write_style_template", lambda path, options=None: path
    )

    assert _controller(app).download_style_template("  ")["ok"] is True
    assert calls == []


def test_a_failing_style_template_write_is_reported(app, tmp_path, monkeypatch):
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    monkeypatch.setattr(
        app_dialogs,
        "write_style_template",
        lambda _path, options=None: (_ for _ in ()).throw(OSError("ổ đĩa đầy")),
    )

    assert (
        _controller(app).download_style_template("")["code"]
        == "STYLE_TEMPLATE_EXPORT_FAILED"
    )


# --- Style copy dropdown --------------------------------------------------


def test_style_copy_only_offers_apparel_article_names(app, monkeypatch):
    monkeypatch.setattr(
        app_dialogs.article_library,
        "load_cached",
        lambda _base: {
            "sections": [
                {
                    "options": [
                        {"article_name": "Áo khoác", "article_category": "Apparel"},
                        {"article_name": "Vải", "article_category": "Textiles"},
                        {"article_name": "áo khoác", "article_category": "apparel"},
                        {"article_name": "  ", "article_category": "Apparel"},
                    ]
                }
            ]
        },
    )

    assert _controller(app)._style_copy_article_names() == ["Áo khoác"]


def test_style_copy_is_empty_without_a_cached_library(app, monkeypatch):
    monkeypatch.setattr(
        app_dialogs.article_library, "load_cached", lambda _base: None
    )

    assert _controller(app)._style_copy_article_names() == []


def test_style_copy_names_reach_the_template(app, tmp_path, monkeypatch):
    app.window = Window(selection=str(tmp_path / "form.xlsx"))
    monkeypatch.setattr(
        app_dialogs.article_library,
        "load_cached",
        lambda _base: {
            "sections": [
                {"options": [{"article_name": "Áo", "article_category": "Apparel"}]}
            ]
        },
    )
    captured: list[dict] = []
    monkeypatch.setattr(
        app_dialogs,
        "write_style_template",
        lambda path, options=None: captured.append(dict(options or {})) or path,
    )

    _controller(app).download_style_template("")

    assert captured[0]["fields"]["style_copy"] == ["Áo"]


# --- helper dùng chung ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SWN/000:1", "SWN 000 1"),
        ("  a  b  ", "a b"),
        ("...", "Costing"),
        ("", "Costing"),
        ("x" * 200, "x" * 120),
    ],
)
def test_a_file_stem_is_always_safe_for_windows(raw, expected):
    assert app_helpers._safe_costing_file_stem(raw) == expected


@pytest.mark.parametrize(
    ("selected", "expected_name"),
    [
        ("C:/a/b.xlsx", "b.xlsx"),
        (("C:/a/b.xlsx",), "b.xlsx"),
        (["C:/a/b.xlsx"], "b.xlsx"),
    ],
)
def test_a_dialog_result_is_normalised_whatever_shape_windows_returns(
    selected, expected_name
):
    assert app_helpers._dialog_selected_path(selected).name == expected_name


@pytest.mark.parametrize("selected", [(), [], object(), None])
def test_a_dialog_result_without_a_path_raises_a_clear_error(selected):
    with pytest.raises(ValueError, match="không trả về đường dẫn"):
        app_helpers._dialog_selected_path(selected)


@pytest.mark.parametrize(
    ("name", "is_excel"),
    [
        ("a.xlsx", True),
        ("a.XLS", True),
        ("a.xlsm", True),
        ("a.xlsb", True),
        ("a.pdf", False),
        ("", False),
    ],
)
def test_excel_files_are_recognised_by_suffix(name, is_excel):
    assert app_helpers._is_excel_file(name) is is_excel


# --- mở file qua Windows Shell -------------------------------------------


def test_revealing_a_file_selects_it_in_explorer(tmp_path, monkeypatch):
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")
    commands: list[list[str]] = []
    monkeypatch.setattr(app_helpers.os, "name", "nt")
    monkeypatch.setattr(
        app_helpers.subprocess, "Popen", lambda command: commands.append(command)
    )

    assert app_helpers._reveal_downloaded_file(target) is True
    assert commands == [["explorer.exe", "/select,", str(target.resolve())]]


def test_revealing_falls_back_to_opening_the_parent_folder(tmp_path, monkeypatch):
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")
    opened: list[str] = []
    monkeypatch.setattr(app_helpers.os, "name", "nt")
    monkeypatch.setattr(
        app_helpers.subprocess,
        "Popen",
        lambda _command: (_ for _ in ()).throw(OSError("explorer lỗi")),
    )
    monkeypatch.setattr(
        app_helpers.os, "startfile", lambda path: opened.append(str(path)),
        raising=False,
    )

    assert app_helpers._reveal_downloaded_file(target) is True
    assert opened == [str(tmp_path.resolve())]


def test_revealing_is_false_when_both_shell_paths_fail(tmp_path, monkeypatch):
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")
    monkeypatch.setattr(app_helpers.os, "name", "nt")
    monkeypatch.setattr(
        app_helpers.subprocess,
        "Popen",
        lambda _command: (_ for _ in ()).throw(OSError("explorer lỗi")),
    )
    monkeypatch.setattr(
        app_helpers.os,
        "startfile",
        lambda _path: (_ for _ in ()).throw(OSError("shell lỗi")),
        raising=False,
    )

    assert app_helpers._reveal_downloaded_file(target) is False


def test_revealing_a_file_that_does_not_exist_is_false(tmp_path, monkeypatch):
    monkeypatch.setattr(app_helpers.os, "name", "nt")

    assert app_helpers._reveal_downloaded_file(tmp_path / "khong-co.xlsx") is False


def test_opening_a_file_uses_the_default_application(tmp_path, monkeypatch):
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")
    opened: list[str] = []
    monkeypatch.setattr(app_helpers.os, "name", "nt")
    monkeypatch.setattr(
        app_helpers.os, "startfile", lambda path: opened.append(str(path)),
        raising=False,
    )

    assert app_helpers._open_downloaded_file(target) is True
    assert opened == [str(target.resolve())]


def test_opening_a_missing_file_is_false(tmp_path, monkeypatch):
    monkeypatch.setattr(app_helpers.os, "name", "nt")

    assert app_helpers._open_downloaded_file(tmp_path / "khong-co.xlsx") is False


def test_opening_reports_false_when_the_shell_fails(tmp_path, monkeypatch):
    target = tmp_path / "a.xlsx"
    target.write_bytes(b"x")
    monkeypatch.setattr(app_helpers.os, "name", "nt")
    monkeypatch.setattr(
        app_helpers.os,
        "startfile",
        lambda _path: (_ for _ in ()).throw(OSError("shell lỗi")),
        raising=False,
    )

    assert app_helpers._open_downloaded_file(target) is False


# --- vị trí mở panel ------------------------------------------------------


def test_the_panel_opens_near_the_top_right_of_the_main_screen(monkeypatch):
    monkeypatch.setattr(
        app_helpers.webview,
        "screens",
        [type("Screen", (), {"width": 2560})()],
        raising=False,
    )

    x, y = app_helpers._top_right_position()

    assert x == 2560 - app_helpers.WINDOW_WIDTH - app_helpers.WINDOW_MARGIN
    assert y == app_helpers.WINDOW_MARGIN


def test_a_screen_narrower_than_the_panel_still_yields_a_visible_margin(
    monkeypatch,
):
    monkeypatch.setattr(
        app_helpers.webview,
        "screens",
        [type("Screen", (), {"width": 100})()],
        raising=False,
    )

    x, _y = app_helpers._top_right_position()

    assert x == app_helpers.WINDOW_MARGIN


def test_the_position_falls_back_to_1920_when_screens_are_unavailable(monkeypatch):
    monkeypatch.setattr(app_helpers.webview, "screens", [], raising=False)

    x, _y = app_helpers._top_right_position()

    assert x == 1920 - app_helpers.WINDOW_WIDTH - app_helpers.WINDOW_MARGIN


# --- in qua WebView2 ------------------------------------------------------


def test_the_print_dialog_runs_on_the_webview_ui_thread(monkeypatch):
    invoked: list[str] = []

    class Core:
        def ShowPrintUI(self, _kind):
            invoked.append("print")

    class Browser:
        class webview:
            CoreWebView2 = Core()

    class Native:
        browser = Browser()

        def Invoke(self, action):
            action()

    monkeypatch.setattr(
        app_helpers,
        "_webview2_print_bindings",
        lambda: (lambda function: function, "system"),
    )
    window = type("Window", (), {"native": Native()})()

    assert app_helpers._show_webview2_print_dialog(window) is True
    assert invoked == ["print"]


def test_the_print_dialog_is_false_without_a_core_webview(monkeypatch):
    class Browser:
        class webview:
            CoreWebView2 = None

    class Native:
        browser = Browser()

        def Invoke(self, action):
            action()

    monkeypatch.setattr(
        app_helpers,
        "_webview2_print_bindings",
        lambda: (lambda function: function, "system"),
    )
    window = type("Window", (), {"native": Native()})()

    assert app_helpers._show_webview2_print_dialog(window) is False


def test_the_print_dialog_never_raises_when_the_bindings_are_missing():
    assert app_helpers._show_webview2_print_dialog(object()) is False
