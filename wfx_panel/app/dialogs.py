"""Hộp thoại chọn/lưu file và các mẫu Excel tải từ panel.

Mỗi hộp thoại nhớ thư mục dùng gần nhất qua prefs, và sau khi lưu thành công
thì tự mở thư mục chứa file. ``Tải form Excel`` phải hỏi nơi lưu TRƯỚC khi
lấy dropdown, vì bước lấy dropdown có thể gọi mạng hoặc quét cả một lượt WFX."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import webview

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel import article_library, prefs
from wfx_panel.app.helpers import (
    _dialog_selected_path,
    _is_excel_file,
    _open_downloaded_file,
    _reveal_downloaded_file,
    _safe_costing_file_stem,
)
from wfx_panel.oc_workbook import write_oc_input_template
from wfx_panel.sale_asn_workbook import write_sale_asn_template
from wfx_panel.style_workbook import write_style_template


class FileDialogController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app


    def reveal_download(self, value: object) -> bool:
        """Mở thư mục chứa file vừa tải và chọn đúng file đó."""
        return _reveal_downloaded_file(value)

    def _handle_downloaded_excel(self, value: object) -> bool:
        """Áp dụng tùy chọn mở file chung rồi luôn hiện file trong Explorer."""
        app = self._app
        preferences = prefs.load_prefs(app._base_dir)
        should_open = preferences.get(
            "open_excel_file_after_download",
            preferences.get("open_costing_file_after_export", True),
        )
        if should_open and not _open_downloaded_file(value):
            app.api._log(
                "[DOWNLOAD] File đã tải nhưng Windows không mở được bằng "
                "ứng dụng mặc định."
            )
        revealed = _reveal_downloaded_file(value)
        if not revealed:
            app.api._log(
                "[DOWNLOAD] File đã tải nhưng Explorer không hiện được vị trí file."
            )
        return revealed

    def choose_costing_import_file(self) -> dict:
        """Mở native dialog; chỉ trả file do chính người dùng chọn."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ chọn file chưa sẵn sàng.",
            }
        try:
            selected = app.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ chọn file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy chọn file Costing.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            return {
                "ok": False,
                "code": "COSTING_FILE_TYPE_UNSUPPORTED",
                "message": "Costing chỉ hỗ trợ file .xlsx.",
            }
        return {
            "ok": True,
            "code": "COSTING_FILE_SELECTED",
            "message": f"Đã chọn {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def choose_costing_export_file(
        self,
        style_name: str,
        file_format: str = "xlsx",
    ) -> dict:
        """Chọn đích lưu XLSX; dùng đúng toàn bộ đường dẫn từ native dialog."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        if str(file_format or "xlsx").casefold() != "xlsx":
            return {
                "ok": False,
                "code": "COSTING_FILE_TYPE_UNSUPPORTED",
                "message": "Costing chỉ hỗ trợ file .xlsx.",
            }
        extension = ".xlsx"
        stem = _safe_costing_file_stem(style_name)
        saved_directory = str(
            prefs.load_prefs(app._base_dir).get("costing_export_dir") or ""
        ).strip()
        if not saved_directory or not Path(saved_directory).is_dir():
            saved_directory = ""
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=saved_directory,
                allow_multiple=False,
                save_filename=f"{stem}-Costing{extension}",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy tải Costing.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "COSTING_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != extension:
            target = target.with_suffix(extension)
        try:
            prefs.save_prefs(
                app._base_dir,
                costing_export_dir=str(target.parent),
            )
        except OSError:
            pass
        return {
            "ok": True,
            "code": "COSTING_EXPORT_PATH_SELECTED",
            "message": f"Sẽ lưu thành {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
            "file_format": extension.lstrip("."),
        }

    def choose_report_export_dir(self) -> dict:
        """Chọn thư mục lưu báo cáo hàng loạt và nhớ cho lần sau."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ chọn thư mục chưa sẵn sàng.",
            }
        saved_directory = str(
            prefs.load_prefs(app._base_dir).get("report_export_dir") or ""
        ).strip()
        if not saved_directory or not Path(saved_directory).is_dir():
            saved_directory = ""
        try:
            selected = app.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=saved_directory,
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ chọn thư mục: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_CANCELLED",
                "message": "Đã hủy chọn thư mục lưu báo cáo.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_FAILED",
                "message": str(error),
            }
        try:
            prefs.save_prefs(app._base_dir, report_export_dir=str(target))
        except OSError:
            pass
        return {
            "ok": True,
            "code": "REPORT_DIR_SELECTED",
            "message": f"Sẽ lưu báo cáo vào {target.name}.",
            "output_dir": str(target),
        }

    def open_report_export_dir(self, path: str = "") -> dict:
        """Mở thư mục chứa các file báo cáo vừa tải."""
        directory = Path(str(path or "")).expanduser()
        if not directory.is_dir() or os.name != "nt":
            return {
                "ok": False,
                "code": "REPORT_DIR_MISSING",
                "message": "Thư mục lưu báo cáo không còn tồn tại.",
            }
        try:
            os.startfile(directory)  # type: ignore[attr-defined]
        except (OSError, ValueError) as error:
            return {
                "ok": False,
                "code": "REPORT_DIR_MISSING",
                "message": f"Không mở được thư mục: {type(error).__name__}",
            }
        return {
            "ok": True,
            "code": "REPORT_DIR_OPENED",
            "message": f"Đã mở {directory.name}.",
        }

    def choose_oc_upload_file(self, mode: str) -> dict:
        """Chọn file OC New/Revise mà người dùng chủ động cung cấp."""
        app = self._app
        selected_mode = str(mode or "").strip().casefold()
        if selected_mode not in {"new", "revise"}:
            return {
                "ok": False,
                "code": "OC_MODE_INVALID",
                "message": "Chế độ Upload OC phải là New hoặc Revise.",
            }
        if app.window is None:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ chọn file chưa sẵn sàng.",
            }
        try:
            selected = app.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ chọn file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy chọn file Upload OC.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            return {
                "ok": False,
                "code": "OC_FILE_TYPE_UNSUPPORTED",
                "message": "Upload OC chỉ hỗ trợ file .xlsx.",
            }
        return {
            "ok": True,
            "code": "OC_FILE_SELECTED",
            "message": f"Đã chọn {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
            "mode": selected_mode,
        }

    def choose_oc_upload_export_file(self, source_file: str = "") -> dict:
        """Choose where to save the generated EDI workbook before upload."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        stem = _safe_costing_file_stem(source_file or "OC-EDI-Upload")
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename=f"WFX-Smart-{stem}.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy tải file EDI Upload OC.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            target = target.with_suffix(".xlsx")
        return {
            "ok": True,
            "code": "OC_UPLOAD_EXPORT_PATH_SELECTED",
            "message": f"Sẽ lưu file EDI thành {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def choose_sale_asn_export_file(self, invoice_no: str) -> dict:
        """Chọn đích lưu sau khi đã đọc được Invoice No. thực tế."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        stem = _safe_costing_file_stem(invoice_no or "Invoice")
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename=f"{stem}.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy lưu Documents Sale ASN.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            target = target.with_suffix(".xlsx")
        return {
            "ok": True,
            "code": "SALE_ASN_EXPORT_PATH_SELECTED",
            "message": f"Sẽ lưu thành {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def choose_sale_asn_price_check_export_file(self, invoice_no: str) -> dict:
        """Chọn nơi lưu workbook đối chiếu tự động của Sale ASN."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        stem = _safe_costing_file_stem(invoice_no or "Invoice")
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename=f"WFX-Smart-Sale-ASN-Check-{stem}.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy xuất kết quả Check giá Sale ASN.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            target = target.with_suffix(".xlsx")
        return {
            "ok": True,
            "code": "SALE_ASN_PRICE_EXPORT_PATH_SELECTED",
            "message": f"Sẽ lưu thành {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def export_sale_asn_price_check(
        self,
        price_check: dict,
        file_path: str,
    ) -> dict:
        """Lưu kết quả đối chiếu và áp dụng tùy chọn mở Excel chung."""
        app = self._app
        result = app._export_sale_asn_price_check(price_check, file_path)
        if result.get("ok") and _is_excel_file(result.get("export_path")):
            self._handle_downloaded_excel(result.get("export_path"))
        return result

    def choose_sale_asn_import_file(self) -> dict:
        """Chọn workbook tạo Sale ASN do người dùng chủ động cung cấp."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ chọn file chưa sẵn sàng.",
            }
        saved_directory = str(
            prefs.load_prefs(app._base_dir).get("sale_asn_import_dir") or ""
        ).strip()
        if not saved_directory or not Path(saved_directory).is_dir():
            saved_directory = ""
        try:
            selected = app.window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=saved_directory,
                allow_multiple=False,
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ chọn file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy chọn file Sale ASN.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_TYPE_UNSUPPORTED",
                "message": "Tạo Sale ASN chỉ hỗ trợ file .xlsx.",
            }
        try:
            prefs.save_prefs(
                app._base_dir,
                sale_asn_import_dir=str(target.parent),
            )
        except OSError:
            pass
        return {
            "ok": True,
            "code": "SALE_ASN_FILE_SELECTED",
            "message": f"Đã chọn {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def choose_style_import_file(self) -> dict:
        """Chọn workbook Tạo Style do người dùng chủ động cung cấp."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ chọn file chưa sẵn sàng.",
            }
        try:
            selected = app.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ chọn file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy chọn file Tạo Style.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_FAILED",
                "message": str(error),
            }
        if target.suffix.casefold() != ".xlsx":
            return {
                "ok": False,
                "code": "STYLE_FILE_TYPE_UNSUPPORTED",
                "message": "Tạo Style chỉ hỗ trợ file .xlsx.",
            }
        return {
            "ok": True,
            "code": "STYLE_FILE_SELECTED",
            "message": f"Đã chọn {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def download_style_template(self, group_id: str = "") -> dict:
        """Lấy dropdown tháng rồi sinh form Tạo Style tại nơi user chọn."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        # Hỏi nơi lưu TRƯỚC. ensure_catalog_style_options có thể gọi GitHub
        # (timeout 20 s) hoặc chạy nguyên một lượt quét WFX; đặt nó trước hộp
        # thoại làm người dùng bấm nút xong phải chờ rất lâu mà chưa thấy gì.
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename="WFX-Smart-Tao-Style.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "STYLE_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy tải form Tạo Style.",
            }
        option_result = {"ok": True, "options": {}}
        if str(group_id or "").strip():
            option_result = app.api.ensure_catalog_style_options(
                str(group_id or ""),
                False,
            )
            if not option_result.get("ok"):
                return option_result
        try:
            target = _dialog_selected_path(selected)
            template_options = dict(option_result.get("options") or {})
            fields = dict(template_options.get("fields") or {})
            fields["style_copy"] = self._style_copy_article_names()
            template_options["fields"] = fields
            target = write_style_template(
                target,
                options=template_options,
            )
            self._handle_downloaded_excel(target)
        except Exception as error:
            return {
                "ok": False,
                "code": "STYLE_TEMPLATE_EXPORT_FAILED",
                "message": f"Không tạo được form Tạo Style: {error}",
            }
        return {
            "ok": True,
            "code": "STYLE_TEMPLATE_EXPORTED",
            "message": (
                f"Đã tạo form {target.name} với dropdown cập nhật theo tháng."
            ),
            "file_path": str(target),
            "file_name": target.name,
        }

    def _style_copy_article_names(self) -> list[str]:
        """Trả Article Name duy nhất của đúng Category Apparel cho Style copy."""
        app = self._app
        cached = article_library.load_cached(app._base_dir)
        if not cached:
            return []
        names: list[str] = []
        seen: set[str] = set()
        for section in cached.get("sections") or ():
            for option in section.get("options") or ():
                if str(option.get("article_category") or "").strip().casefold() != "apparel":
                    continue
                name = str(option.get("article_name") or "").strip()
                identity = name.casefold()
                if name and identity not in seen:
                    seen.add(identity)
                    names.append(name)
        return names

    def download_oc_template(self) -> dict:
        """Sinh form OC INPUT một header và lưu vào nơi người dùng chọn."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename="WFX-Smart-Upload-OC.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "OC_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy tải form Upload OC.",
            }
        try:
            target = _dialog_selected_path(selected)
            if target.suffix.casefold() != ".xlsx":
                target = target.with_suffix(".xlsx")
            write_oc_input_template(target)
            self._handle_downloaded_excel(target)
        except Exception as error:
            return {
                "ok": False,
                "code": "OC_TEMPLATE_EXPORT_FAILED",
                "message": f"Không tạo được form Upload OC: {error}",
            }
        return {
            "ok": True,
            "code": "OC_TEMPLATE_EXPORTED",
            "message": f"Đã tạo form {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def download_sale_asn_template(self) -> dict:
        """Tạo form 19 cột cho luồng New Sale ASN."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename="WFX-Smart-Sale-ASN.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy tải form Sale ASN.",
            }
        try:
            target = _dialog_selected_path(selected)
            target = write_sale_asn_template(target)
            self._handle_downloaded_excel(target)
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_TEMPLATE_EXPORT_FAILED",
                "message": f"Không tạo được form Sale ASN: {error}",
            }
        return {
            "ok": True,
            "code": "SALE_ASN_TEMPLATE_EXPORTED",
            "message": f"Đã tạo form {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }

    def save_sale_asn_continue_template(self, rows: list[dict]) -> dict:
        """Xuất form 22 cột có sẵn PO/Order Details của Sale ASN đang mở."""
        app = self._app

        if app.window is None:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ lưu file chưa sẵn sàng.",
            }
        try:
            selected = app.window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                save_filename="WFX-Smart-Sale-ASN-Continue.xlsx",
                file_types=("Excel workbook (*.xlsx)",),
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ lưu file: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_DIALOG_CANCELLED",
                "message": "Đã hủy xuất form tiếp tục Sale ASN.",
            }
        try:
            target = _dialog_selected_path(selected)
            target = write_sale_asn_template(target, rows or [])
            self._handle_downloaded_excel(target)
        except Exception as error:
            return {
                "ok": False,
                "code": "SALE_ASN_TEMPLATE_EXPORT_FAILED",
                "message": f"Không tạo được form tiếp tục Sale ASN: {error}",
            }
        return {
            "ok": True,
            "code": "SALE_ASN_TEMPLATE_EXPORTED",
            "message": f"Đã xuất {len(rows or [])} PO vào form {target.name}.",
            "file_path": str(target),
            "file_name": target.name,
        }
