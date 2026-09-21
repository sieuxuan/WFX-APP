"""Điều phối Sale ASN: quét Buyer, tạo chứng từ 5 bước và xuất Invoice + PKL.

Review tạo Sale ASN giữ snapshot workbook và vị trí PO kế tiếp, nên khi WFX
trả nhiều dòng thì user chọn thủ công rồi flow tiếp đúng dòng kế — không đọc
lại file và không đảo thứ tự. Hai report được ghép trong file tạm trước khi
UI mở Save As; token ngăn một panel cũ lưu nhầm workbook khác.

Controller mượn hạ tầng chung của panel qua tham chiếu ``panel``, giống
``CatalogController`` và ``OCController``."""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants
from wfx_panel.sale_asn_buyers import SaleASNBuyerStore, normalise_buyers
from wfx_panel.sale_asn_workbook import (
    SaleASNWorkbookError,
    read_sale_asn_workbook,
    write_sale_asn_price_check_workbook,
)


class SaleASNController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        self._buyer_store = SaleASNBuyerStore(
            panel._base_dir / "sale-asn-buyers.json"
        )
        self.buyers = self._buyer_store.load()
        # Review tạo Sale ASN giữ snapshot workbook và vị trí PO kế tiếp.
        self.create_reviews: dict[str, dict] = {}
        # Hai report Sale ASN được ghép trong file tạm trước khi UI mở Save As.
        self.document_exports: dict[str, dict] = {}

    def open_sale_asn_new(self) -> dict:
        panel = self._panel
        def action() -> dict:
            return panel._login.open_sale_asn_new(
                constants.SALE_ASN_NEW_XPATH,
                panel._log,
            )

        return panel._run("open_sale_asn_new", action)

    def scan_sale_asn_buyers(self) -> dict:
        panel = self._panel
        scanner = getattr(panel._login, "scan_sale_asn_buyers", None)
        if not callable(scanner):
            return {
                "ok": False,
                "code": "SALE_ASN_BUYER_SCAN_FAILED",
                "message": "Phiên bản tự động hóa chưa hỗ trợ quét Buyer Sale ASN.",
            }
        result = panel._run(
            "scan_sale_asn_buyers",
            lambda: scanner(constants.SALE_ASN_NEW_XPATH, panel._log),
        )
        if result.get("ok") and isinstance(result.get("buyers"), list):
            self.buyers = normalise_buyers(result["buyers"])
            try:
                self.buyers = self._buyer_store.save(
                    self.buyers
                )
            except OSError as error:
                panel._log(
                    "[SALE ASN] Không lưu được cache Buyer: "
                    f"{type(error).__name__}."
                )
            result["buyers"] = list(self.buyers)
        return result

    def scan_sale_asn_order_details(self) -> dict:
        """Đọc PO/Order Details đang mở để xuất sẵn vào form 22 cột."""
        panel = self._panel

        scanner = getattr(panel._login, "scan_sale_asn_order_details", None)
        if not callable(scanner):
            return {
                "ok": False,
                "code": "SALE_ASN_ORDER_SCAN_FAILED",
                "message": "Phiên bản tự động hóa chưa hỗ trợ đọc Order Details.",
            }
        return panel._run(
            "scan_sale_asn_order_details",
            lambda: scanner(panel._log),
        )

    def _discard_sale_asn_create_review(self, review_token: str) -> bool:
        panel = self._panel
        review = self.create_reviews.pop(review_token, None)
        if review is None:
            return False
        temporary = review.get("temporary")
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError as error:
                panel._log(
                    "[SALE ASN] Không dọn được review tạm: "
                    f"{type(error).__name__}."
                )
        return True

    def prepare_sale_asn_create(
        self,
        file_path: str,
        buyer: str,
        selected_stages: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        panel = self._panel
        stage_order = (
            "po",
            "order_details",
            "style_details",
            "shipping_info",
        )
        if selected_stages is not None and not isinstance(
            selected_stages,
            (list, tuple),
        ):
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_STEPS_INVALID",
                "message": "Danh sách bước Sale ASN không hợp lệ.",
            }
        requested = {
            str(stage or "").strip()
            for stage in (selected_stages or stage_order)
            if isinstance(stage, str)
        }
        stages = tuple(stage for stage in stage_order if stage in requested)
        if not stages:
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_STEPS_REQUIRED",
                "message": "Hãy chọn ít nhất một bước Sale ASN cần thực hiện.",
            }
        selected_buyer = str(buyer or "").strip()
        if "po" in stages and not selected_buyer:
            return {
                "ok": False,
                "code": "SALE_ASN_BUYER_REQUIRED",
                "message": "Hãy chọn Buyer trước khi kiểm tra file.",
            }
        source = Path(str(file_path or "")).expanduser()
        po_search_fields = list(
            panel._prefs.load_prefs(base_dir=panel._base_dir)[
                "sale_asn_po_search_fields"
            ]
        )
        cache_root = panel._base_dir / "sale-asn-create-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="review-", dir=str(cache_root)
        )
        snapshot = Path(temporary.name) / "Sale-ASN-Input.xlsx"
        try:
            shutil.copy2(source, snapshot)
            document = read_sale_asn_workbook(
                snapshot,
                required_stages=list(stages),
            )
        except SaleASNWorkbookError as error:
            temporary.cleanup()
            return {
                "ok": False,
                "code": error.code,
                "message": error.message,
                "errors": list(error.errors),
            }
        except OSError as error:
            temporary.cleanup()
            return {
                "ok": False,
                "code": "SALE_ASN_FILE_NOT_FOUND",
                "message": f"Không đọc được file Sale ASN: {error}",
            }

        for old_token in tuple(self.create_reviews):
            self._discard_sale_asn_create_review(old_token)
        review_token = secrets.token_urlsafe(24)
        self.create_reviews[review_token] = {
            "temporary": temporary,
            "document": document,
            "buyer": selected_buyer,
            "next_index": 0,
            "next_stage": stages[0],
            "selected_stages": list(stages),
            "skipped_stages": [
                stage for stage in stage_order if stage not in stages
            ],
            "po_search_fields": po_search_fields,
        }
        stage_labels = {
            "po": "Thêm PO",
            "order_details": "Order Details",
            "style_details": "Style Details",
            "shipping_info": "Shipping Info",
        }
        return {
            "ok": True,
            "code": "SALE_ASN_CREATE_REVIEW_READY",
            "message": (
                f"File hợp lệ: {document['po_count']} PO, "
                f"{document['style_count']} Style. Sẽ làm: "
                f"{', '.join(stage_labels[stage] for stage in stages)}."
            ),
            "review_token": review_token,
            "buyer": selected_buyer,
            "selected_stages": list(stages),
            **{
                key: document[key]
                for key in (
                    "file_name",
                    "invoice_no",
                    "destination",
                    "factory",
                    "po_count",
                    "style_count",
                )
            },
        }

    def _run_sale_asn_create_review(
        self,
        review_token: str,
        *,
        continue_existing: bool,
        selected_candidate_ids: list[str] | None = None,
    ) -> dict:
        panel = self._panel
        token = str(review_token or "").strip()
        review = self.create_reviews.get(token)
        if review is None:
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_REVIEW_EXPIRED",
                "message": "Phiên kiểm tra Sale ASN không còn hiệu lực; hãy chọn file lại.",
            }
        runner = getattr(panel._login, "run_sale_asn_create", None)
        if not callable(runner):
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_FAILED",
                "message": "Phiên bản tự động hóa chưa hỗ trợ tạo Sale ASN.",
            }
        document = review["document"]
        start_index = int(review.get("next_index") or 0) if continue_existing else 0
        stage = str(review.get("next_stage") or "po")
        skipped_stages = tuple(review.get("skipped_stages") or ())
        po_search_fields = tuple(
            review.get("po_search_fields")
            or ("po", "style", "destination")
        )
        method = (
            "continue_sale_asn_create" if continue_existing else "start_sale_asn_create"
        )
        pending_candidates = list(review.get("pending_po_candidates") or ())
        selected_candidates: list[dict] = []
        if pending_candidates:
            requested = {
                str(item).strip() for item in (selected_candidate_ids or ()) if str(item).strip()
            }
            by_id = {
                str(candidate.get("candidate_id") or ""): candidate
                for candidate in pending_candidates
            }
            if not requested or not requested.issubset(by_id):
                return {
                    "ok": False,
                    "code": "SALE_ASN_PO_SELECTION_REQUIRED",
                    "message": "Hãy chọn ít nhất một dòng PO trong ứng dụng.",
                    "review_token": token,
                    "candidates": pending_candidates,
                }
            selected_candidates = [
                dict(candidate)
                for candidate in pending_candidates
                if str(candidate.get("candidate_id") or "") in requested
            ]
        runner_kwargs: dict[str, Any] = {
            "stage": stage,
            "skip_stages": skipped_stages,
            "search_fields": po_search_fields,
            "progress": panel._progress_for(method),
        }
        if selected_candidates:
            runner_kwargs.update(
                selected_po_row=dict(review.get("pending_po_row") or {}),
                selected_po_candidates=selected_candidates,
                selected_po_final=bool(review.get("pending_po_final")),
            )
        result = panel._run(
            method,
            lambda: runner(
                constants.SALE_ASN_NEW_XPATH,
                str(review["buyer"]),
                list(document["rows"]),
                start_index,
                panel._log,
                **runner_kwargs,
            ),
            {
                "invoice_no": document["invoice_no"],
                "po_count": document["po_count"],
                "start_index": start_index,
                "stage": stage,
            },
        )
        if result.get("code") == "SALE_ASN_PO_SELECTION_REQUIRED":
            review["next_index"] = int(result.get("pending_index") or start_index)
            review["next_stage"] = "po"
            review["pending_po_candidates"] = list(result.get("candidates") or ())
            review["pending_po_row"] = {
                "source_row": result.get("source_row"),
                "po_no": result.get("po_no"),
                "style_no": result.get("style_no"),
            }
            review["pending_po_final"] = bool(result.get("final"))
            result["review_token"] = token
        elif result.get("resumable"):
            review.pop("pending_po_candidates", None)
            review.pop("pending_po_row", None)
            review.pop("pending_po_final", None)
            review["next_stage"] = str(result.get("resume_stage") or stage)
            result["review_token"] = token
        elif result.get("code") == "SALE_ASN_FORM_COMPLETED":
            self._discard_sale_asn_create_review(token)
        return result

    def start_sale_asn_create(self, review_token: str) -> dict:
        return self._run_sale_asn_create_review(
            review_token,
            continue_existing=False,
        )

    def continue_sale_asn_create(
        self,
        review_token: str,
        selected_candidate_ids: list[str] | None = None,
    ) -> dict:
        return self._run_sale_asn_create_review(
            review_token,
            continue_existing=True,
            selected_candidate_ids=selected_candidate_ids,
        )

    def skip_sale_asn_create_step(self, review_token: str) -> dict:
        token = str(review_token or "").strip()
        review = self.create_reviews.get(token)
        if review is None:
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_REVIEW_EXPIRED",
                "message": "Phiên kiểm tra Sale ASN không còn hiệu lực; hãy chọn file lại.",
            }
        stage = str(review.get("next_stage") or "po")
        if stage not in {"order_details", "style_details", "shipping_info"}:
            return {
                "ok": False,
                "code": "SALE_ASN_CREATE_STAGE_NOT_SKIPPABLE",
                "message": "Bước hiện tại không thể bỏ qua.",
            }
        skipped = list(review.get("skipped_stages") or ())
        if stage not in skipped:
            skipped.append(stage)
        review["skipped_stages"] = skipped
        return self._run_sale_asn_create_review(token, continue_existing=True)

    def cancel_sale_asn_create(self, review_token: str) -> dict:
        self._discard_sale_asn_create_review(str(review_token or "").strip())
        return {
            "ok": True,
            "code": "SALE_ASN_CREATE_CANCELLED",
            "message": "Đã hủy phiên tạo Sale ASN.",
        }

    def search_sale_asn(
        self,
        filter_kind: str,
        query: str,
    ) -> dict:
        panel = self._panel
        sale_asn = constants.MODULE_BY_ID["0004_0070_0020"]
        return panel._run(
            "search_sale_asn",
            lambda: panel._login.search_sale_asn_list(
                sale_asn["xpath"],
                str(filter_kind or ""),
                str(query or "").strip(),
                panel._log,
            ),
            {
                "filter_kind": str(filter_kind or ""),
                "query": str(query or "").strip(),
            },
        )

    def export_sale_asn_price_check(
        self,
        price_check: dict,
        file_path: str,
    ) -> dict:
        """Lưu bản đối chiếu đã chạy trong task tạo Sale ASN vừa hoàn tất."""

        if not isinstance(price_check, dict):
            return {
                "ok": False,
                "code": "SALE_ASN_PRICE_EXPORT_FAILED",
                "message": "Kết quả Check giá không hợp lệ; hãy tạo Sale ASN lại.",
            }
        raw_path = str(file_path or "").strip()
        if not raw_path:
            return {
                "ok": False,
                "code": "SALE_ASN_PRICE_EXPORT_FAILED",
                "message": "Chưa có đường dẫn lưu kết quả Check giá.",
            }
        target = Path(raw_path).expanduser().resolve()
        try:
            actual = write_sale_asn_price_check_workbook(target, price_check)
        except (OSError, ValueError, TypeError) as error:
            return {
                "ok": False,
                "code": "SALE_ASN_PRICE_EXPORT_FAILED",
                "message": f"Không lưu được file Check giá: {error}",
            }
        return {
            "ok": True,
            "code": "SALE_ASN_PRICE_EXPORTED",
            "message": f"Đã lưu kết quả Check giá thành {actual.name}.",
            "export_path": str(actual),
            "file_name": actual.name,
        }

    def _discard_sale_asn_document_export(self, export_token: str) -> bool:
        panel = self._panel
        prepared = self.document_exports.pop(export_token, None)
        if prepared is None:
            return False
        temporary = prepared.get("temporary")
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError as error:
                panel._log(
                    "[SALE ASN DOCS] Không dọn được file tạm: "
                    f"{type(error).__name__}"
                )
        return True

    def prepare_sale_asn_documents(
        self,
        filter_kind: str,
        query: str,
    ) -> dict:
        """Tải/ghép hai report và giữ file tạm đến bước Save As."""
        panel = self._panel
        selected_filter = str(filter_kind or "").strip()
        selected_query = str(query or "").strip()
        sale_asn = constants.MODULE_BY_ID["0004_0070_0020"]
        cache_root = panel._base_dir / "sale-asn-export-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="documents-",
            dir=cache_root,
        )
        prepared_path = Path(temporary.name) / "Sale-ASN-Documents.xlsx"

        def action() -> dict:
            preparer = getattr(
                panel._login,
                "prepare_sale_asn_documents",
                None,
            )
            if not callable(preparer):
                return {
                    "ok": False,
                    "code": "SALE_ASN_DOCUMENTS_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ tải Documents Sale ASN.",
                }
            return preparer(
                sale_asn["xpath"],
                selected_filter,
                selected_query,
                prepared_path,
                panel._log,
            )

        result = panel._run(
            "prepare_sale_asn_documents",
            action,
            {
                "filter_kind": selected_filter,
                "query": selected_query,
            },
        )
        internal_path = Path(str(result.get("prepared_path") or prepared_path))
        public_result = {
            key: value
            for key, value in result.items()
            if key != "prepared_path"
        }
        if not result.get("ok") or not internal_path.is_file():
            temporary.cleanup()
            if result.get("ok"):
                return {
                    **public_result,
                    "ok": False,
                    "code": "SALE_ASN_REPORT_MERGE_FAILED",
                    "message": "Workbook Sale ASN tạm không được tạo.",
                }
            return public_result

        for old_token in tuple(self.document_exports):
            self._discard_sale_asn_document_export(old_token)
        export_token = secrets.token_urlsafe(24)
        self.document_exports[export_token] = {
            "temporary": temporary,
            "prepared_path": internal_path,
            "invoice_no": str(result.get("invoice_no") or "Invoice").strip(),
            "sheet_names": list(result.get("sheet_names") or []),
        }
        return {
            **public_result,
            "export_token": export_token,
        }

    def cancel_sale_asn_documents(self, export_token: str) -> dict:
        token = str(export_token or "").strip()
        self._discard_sale_asn_document_export(token)
        return {
            "ok": True,
            "code": "SALE_ASN_DOCUMENTS_CANCELLED",
            "message": "Đã hủy lưu Documents Sale ASN.",
        }

    def save_sale_asn_documents(
        self,
        export_token: str,
        file_path: str,
    ) -> dict:
        panel = self._panel
        token = str(export_token or "").strip()
        raw_path = str(file_path or "").strip()
        if not raw_path:
            return {
                "ok": False,
                "code": "SALE_ASN_DOCUMENTS_SAVE_FAILED",
                "message": "Chưa có đường dẫn lưu file Sale ASN.",
            }
        target = Path(raw_path).expanduser().resolve()
        if target.suffix.casefold() != ".xlsx":
            target = target.with_suffix(".xlsx")

        def next_available_target(current: Path) -> Path:
            """Tránh ghi đè file đang mở bằng một tên sibling chưa tồn tại."""
            suffix = current.suffix or ".xlsx"
            for index in range(2, 10_000):
                candidate = current.with_name(f"{current.stem} ({index}){suffix}")
                if not candidate.exists():
                    return candidate
            raise OSError("Không tìm được tên file trống để lưu Documents Sale ASN.")

        def copy_to_target(source: Path, destination: Path) -> None:
            staging = destination.with_name(
                f".{destination.name}.{secrets.token_hex(4)}.tmp"
            )
            try:
                shutil.copyfile(source, staging)
                os.replace(staging, destination)
            except OSError:
                try:
                    staging.unlink(missing_ok=True)
                except OSError:
                    pass
                raise

        def action() -> dict:
            prepared = self.document_exports.get(token)
            if prepared is None:
                return {
                    "ok": False,
                    "code": "SALE_ASN_DOCUMENTS_EXPIRED",
                    "message": (
                        "File Sale ASN tạm không còn hiệu lực; hãy tải lại."
                    ),
                }
            source = Path(prepared["prepared_path"])
            if not source.is_file():
                self._discard_sale_asn_document_export(token)
                return {
                    "ok": False,
                    "code": "SALE_ASN_DOCUMENTS_EXPIRED",
                    "message": "File Sale ASN tạm đã bị xóa; hãy tải lại.",
                }
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                actual_target = target
                renamed_for_open_file = False
                try:
                    copy_to_target(source, actual_target)
                except PermissionError:
                    actual_target = next_available_target(target)
                    copy_to_target(source, actual_target)
                    renamed_for_open_file = True
            except OSError as error:
                return {
                    "ok": False,
                    "code": "SALE_ASN_DOCUMENTS_SAVE_FAILED",
                    "message": f"Không lưu được file Excel: {error}",
                }
            invoice_no = str(prepared.get("invoice_no") or "Invoice")
            self._discard_sale_asn_document_export(token)
            suffix_message = (
                " File cùng tên đang mở nên đã tự lưu bằng tên mới."
                if renamed_for_open_file
                else ""
            )
            return {
                "ok": True,
                "code": "SALE_ASN_DOCUMENTS_EXPORTED",
                "message": (
                    f"Đã lưu Packing List + Buyer Invoice của "
                    f"{invoice_no} thành {actual_target.name}.{suffix_message}"
                ),
                "invoice_no": invoice_no,
                "export_path": str(actual_target),
                "file_name": actual_target.name,
                "renamed_for_open_file": renamed_for_open_file,
                "sheet_names": list(prepared.get("sheet_names") or []),
            }

        return panel._run(
            "save_sale_asn_documents",
            action,
            {"file_name": target.name},
        )
