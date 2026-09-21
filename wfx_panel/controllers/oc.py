"""Điều phối luồng OC: review workbook, upload EDI, Confirm và Reject All.

``Create Transaction`` là ranh giới không idempotent nên workbook đã chuẩn
hoá chỉ sống từ Review tới Confirm/Cancel, gắn token một lần. Token ngăn
một panel cũ hoặc cú click lặp upload nhầm review khác.

Controller mượn hạ tầng chung của panel (``_run``, ``_log``, ``_login``,
``_prefs``) qua tham chiếu ``panel`` — cùng package nên coupling chặt là
chấp nhận được, đổi lại bridge gọn và luồng OC test được độc lập."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel.workbooks.oc import OCWorkbookError, prepare_oc_workbook


def _snapshot_oc_source(source: Path, target: Path) -> str:
    """Copy the exact current workbook bytes and return their SHA-256.

    A review must never reuse a previous transformation just because Windows
    returns the same selected path.  Snapshotting also prevents Excel saving
    the source halfway through the three validation/read passes.
    """
    for attempt in range(2):
        try:
            before = source.stat()
            digest = hashlib.sha256()
            with source.open("rb") as reader, target.open("wb") as writer:
                while chunk := reader.read(1024 * 1024):
                    writer.write(chunk)
                    digest.update(chunk)
            after = source.stat()
        except OSError as error:
            raise OCWorkbookError(
                "OC_FILE_READ_FAILED",
                "Không đọc được file OC. Hãy lưu và đóng file Excel rồi chọn lại.",
                (f"{type(error).__name__}: {error}",),
            ) from error
        unchanged = (
            before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
            and target.stat().st_size == after.st_size
        )
        if unchanged:
            return digest.hexdigest()
        if attempt == 0:
            continue
    raise OCWorkbookError(
        "OC_FILE_CHANGED_DURING_READ",
        "File OC đang được Excel lưu. Hãy chờ lưu xong rồi chọn lại file.",
    )


class OCController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        # Workbook đã chuẩn hoá chỉ sống từ bước Review đến Confirm/Cancel.
        # Token ngẫu nhiên ngăn UI cũ hoặc click lặp upload nhầm review khác.
        self.reviews: dict[str, dict] = {}

    @staticmethod
    def _oc_review_payload(prepared) -> dict:
        return {
            "buyer": prepared.buyer,
            "seasons": list(prepared.seasons),
            "season": ", ".join(prepared.seasons) or "—",
            "po_count": prepared.po_count,
            "style_count": prepared.style_count,
            "total_units": prepared.total_units,
            "row_count": prepared.row_count,
            "mode": prepared.mode,
            "warnings": list(prepared.warnings),
        }

    def _discard_oc_upload_review(self, review_token: str) -> bool:
        panel = self._panel
        review = self.reviews.pop(review_token, None)
        if review is None:
            return False
        temporary = review.get("temporary")
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError as error:
                panel._log(
                    "[OC] Không dọn được workbook review tạm: "
                    f"{type(error).__name__}"
                )
        return True

    def review_oc_upload(self, mode: str, file_path: str) -> dict:
        """Validate locally and return business totals before touching WFX."""
        panel = self._panel
        selected_mode = str(mode or "").strip().casefold()
        source = Path(str(file_path or "")).expanduser().resolve()

        def action() -> dict:
            # UI chỉ duy trì một review hiện hành; file cũ không được phép vô
            # tình confirm sau khi user đã chọn workbook khác.
            for old_token in tuple(self.reviews):
                self._discard_oc_upload_review(old_token)
            cache_root = panel._base_dir / "oc-upload-cache"
            cache_root.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(
                prefix="review-",
                dir=cache_root,
            )
            try:
                source_snapshot = Path(temporary.name) / "OC-Source.xlsx"
                source_sha256 = _snapshot_oc_source(source, source_snapshot)
                upload_path = Path(temporary.name) / "OC-EDI-Upload.xlsx"
                prepared = prepare_oc_workbook(
                    source_snapshot,
                    selected_mode,
                    upload_path,
                )
            except OCWorkbookError as error:
                temporary.cleanup()
                return {
                    "ok": False,
                    "code": error.code,
                    "message": error.message,
                    "errors": list(error.errors),
                    "source_file": source.name,
                    "mode": selected_mode,
                }
            except Exception:
                temporary.cleanup()
                raise
            review_token = secrets.token_urlsafe(24)
            self.reviews[review_token] = {
                "temporary": temporary,
                "prepared": prepared,
                "source_file": source.name,
                "source_sha256": source_sha256,
            }
            panel._log(
                "[OC] Review sẵn sàng: "
                f"{prepared.row_count} dòng, {prepared.po_count} PO, "
                f"{prepared.style_count} Style, {prepared.total_units} Units"
            )
            return {
                "ok": True,
                "code": "OC_UPLOAD_REVIEW_READY",
                "message": "File hợp lệ. Kiểm tra số liệu trước khi xác nhận Upload.",
                "review_token": review_token,
                "source_file": source.name,
                "source_sha256": source_sha256,
                **self._oc_review_payload(prepared),
            }

        return panel._run(
            "review_oc_upload",
            action,
            {"mode": selected_mode, "file_name": source.name},
        )

    def cancel_oc_upload_review(self, review_token: str) -> dict:
        panel = self._panel
        token = str(review_token or "").strip()

        def action() -> dict:
            self._discard_oc_upload_review(token)
            return {
                "ok": True,
                "code": "OC_UPLOAD_REVIEW_CANCELLED",
                "message": "Đã hủy Upload OC; WFX chưa nhận dữ liệu.",
            }

        return panel._run("cancel_oc_upload_review", action)

    def save_oc_upload_file(
        self,
        review_token: str,
        file_path: str,
    ) -> dict:
        """Save the generated value-only workbook without consuming the review."""
        panel = self._panel
        token = str(review_token or "").strip()
        raw_path = str(file_path or "").strip()
        if not raw_path:
            return {
                "ok": False,
                "code": "OC_UPLOAD_FILE_SAVE_FAILED",
                "message": "Chưa có đường dẫn lưu file EDI Upload OC.",
            }
        target = Path(raw_path).expanduser().resolve()
        if target.suffix.casefold() != ".xlsx":
            target = target.with_suffix(".xlsx")

        def next_available_target(current: Path) -> Path:
            suffix = current.suffix or ".xlsx"
            for index in range(2, 10_000):
                candidate = current.with_name(f"{current.stem} ({index}){suffix}")
                if not candidate.exists():
                    return candidate
            raise OSError("Không tìm được tên file trống để lưu EDI Upload OC.")

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
            review = self.reviews.get(token)
            if review is None:
                return {
                    "ok": False,
                    "code": "OC_UPLOAD_REVIEW_EXPIRED",
                    "message": "Review Upload OC không còn hiệu lực; hãy chọn lại file.",
                }
            source = Path(review["prepared"].upload_path)
            if not source.is_file():
                return {
                    "ok": False,
                    "code": "OC_UPLOAD_FILE_MISSING",
                    "message": (
                        "File EDI Upload OC đã sinh không còn tồn tại; "
                        "hãy chọn lại file nguồn."
                    ),
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
                    "code": "OC_UPLOAD_FILE_SAVE_FAILED",
                    "message": f"Không lưu được file EDI Upload OC: {error}",
                }
            suffix_message = (
                " File cùng tên đang mở nên đã tự lưu bằng tên mới."
                if renamed_for_open_file
                else ""
            )
            return {
                "ok": True,
                "code": "OC_UPLOAD_FILE_SAVED",
                "message": (
                    f"Đã tải form EDI Upload OC xuống {actual_target.name}."
                    f"{suffix_message} Bạn có thể tự Upload lại file này nếu WFX báo lỗi."
                ),
                "file_path": str(actual_target),
                "file_name": actual_target.name,
                "renamed_for_open_file": renamed_for_open_file,
            }

        return panel._run(
            "save_oc_upload_file",
            action,
            {"file_name": target.name},
        )

    def confirm_oc_upload(self, review_token: str) -> dict:
        """Upload exactly the value-only workbook shown in the review."""
        panel = self._panel
        token = str(review_token or "").strip()

        def action() -> dict:
            review = self.reviews.get(token)
            if review is None:
                return {
                    "ok": False,
                    "code": "OC_UPLOAD_REVIEW_EXPIRED",
                    "message": "Review Upload OC không còn hiệu lực; hãy chọn lại file.",
                }
            prepared = review["prepared"]
            try:
                result = panel._login.upload_oc_edi(
                    prepared.upload_path,
                    prepared.buyer,
                    prepared.mode,
                    panel._log,
                )
            except BaseException:
                self._discard_oc_upload_review(token)
                raise
            # Cho auto-relogin gọi lại action đúng một lần khi chưa hề chạm EDI.
            if str(result.get("code") or "") != "NOT_LOGGED_IN":
                self._discard_oc_upload_review(token)
            return {
                **result,
                "source_file": review["source_file"],
                **self._oc_review_payload(prepared),
            }

        return panel._run(
            "confirm_oc_upload",
            action,
            {"review_token": token[:8]},
        )

    def confirm_oc_pending(self, mode: str) -> dict:
        """Confirm tuần tự các Style chờ, không phụ thuộc lịch sử upload app."""
        panel = self._panel
        selected_mode = str(mode or "").strip().casefold()
        return panel._run(
            "confirm_oc_pending",
            lambda: panel._login.confirm_oc_pending(selected_mode, panel._log),
            {"mode": selected_mode},
        )

    def reject_all_oc_pending(self) -> dict:
        """Reject tuần tự PO trong tab New hoặc Revision đang mở trên WFX."""
        panel = self._panel
        return panel._run(
            "reject_all_oc_pending",
            lambda: panel._login.reject_all_oc_pending(panel._log),
        )

    def upload_oc(self, mode: str, file_path: str) -> dict:
        panel = self._panel
        selected_mode = str(mode or "").strip().casefold()
        source = Path(str(file_path or "")).expanduser().resolve()

        def action() -> dict:
            cache_root = panel._base_dir / "oc-upload-cache"
            cache_root.mkdir(parents=True, exist_ok=True)
            try:
                with tempfile.TemporaryDirectory(
                    prefix="run-",
                    dir=cache_root,
                ) as temporary:
                    upload_path = Path(temporary) / "OC-EDI-Upload.xlsx"
                    prepared = prepare_oc_workbook(
                        source,
                        selected_mode,
                        upload_path,
                    )
                    panel._log(
                        "[OC] Workbook hợp lệ: "
                        f"{prepared.row_count} dòng, Buyer {prepared.buyer}"
                    )
                    for warning in prepared.warnings:
                        panel._log(f"[OC] {warning}")
                    result = panel._login.upload_oc_edi(
                        prepared.upload_path,
                        prepared.buyer,
                        prepared.mode,
                        panel._log,
                    )
                    return {
                        **result,
                        "source_file": source.name,
                        "row_count": prepared.row_count,
                        "buyer": prepared.buyer,
                        "mode": prepared.mode,
                        "warnings": list(prepared.warnings),
                    }
            except OCWorkbookError as error:
                return {
                    "ok": False,
                    "code": error.code,
                    "message": error.message,
                    "errors": list(error.errors),
                    "source_file": source.name,
                    "mode": selected_mode,
                }

        return panel._run(
            "upload_oc",
            action,
            {
                "mode": selected_mode,
                "file_name": source.name,
            },
        )

    def open_oc_revision_report(self) -> dict:
        panel = self._panel
        return panel._run(
            "open_oc_revision_report",
            lambda: panel._login.open_oc_revision_report(panel._log),
        )
