"""Điều phối kho nguyên phụ liệu: tìm RMPO và làm phiếu nhập kho GRN.

Lựa chọn RMPO chỉ sống tới lần Search kế tiếp; mọi action phải kiểm tra lại
row/status trên WFX trước khi click. Phiên nhập kho giữ RMPO/Supplier đã xác
thực và danh sách Site giữa các checkpoint user tự Confirm trên WFX.

Site nhận kho được nhớ theo User ID + Division (``stores/grn_sites``) để user
chọn ngay trong app: có Site thì một lượt đi thẳng tới New GRN, chưa có thì app
đọc dropdown Site của GRN Pending rồi dừng cho user chọn.

RMPO No. mang Division trong tiền tố (``PSW-JLD-26-6242`` thuộc Woven), mà
RMPO List/GRN chỉ thấy chứng từ của Division đang chọn: tìm và chuẩn bị nhập kho
đổi Division trước, còn bước nối tiếp quay về đúng Division lúc bắt đầu."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants
from wfx_panel.automation.grn.frames import rmpo_receipt_refusal
from wfx_panel.coercion import boolean
from wfx_panel.controllers.document_division import (
    align_division,
    align_document_division,
    document_no_division,
    with_document_division_state,
)
from wfx_panel.stores.grn_sites import GrnSiteStore, clean_sites

_RMPO_LABEL = "RMPO No."
_GRN_MODULE = "(GRN) Nhập kho"
# Mode sai đã bị automation từ chối trước khi chạm Chrome; không đổi Division
# cho một lượt chắc chắn không chạy.
_GRN_MODES = {"foreign", "domestic"}

_NOT_FOUND_CODES = {"RMPO_NO_RESULTS", "GRN_RMPO_NOT_FOUND", "GRN_SEARCH_NO_RESULTS"}


def _hint_other_division(result: dict[str, Any], rmpo_no: str) -> dict[str, Any]:
    """Không thấy RMPO gõ thiếu tiền tố: có thể nó nằm ở Division khác."""
    text = str(rmpo_no or "").strip()
    if (
        result.get("code") not in _NOT_FOUND_CODES
        or not text
        or document_no_division(text) is not None
    ):
        return result
    message = str(result.get("message") or "").strip()
    return {
        **result,
        "message": (
            f"{message} Nếu RMPO thuộc Division khác, hãy nhập đủ số có tiền "
            "tố PSG-/PSW-/PSK- để ứng dụng tự chuyển Division."
        ).strip(),
    }


class InventoryController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        # Token hoá dòng RMPO: WebView chỉ nhận token, không nhận row key WFX.
        self.rmpo_choices: dict[str, dict[str, str]] = {}
        self.grn_sessions: dict[str, dict[str, Any]] = {}
        # Division của lượt tìm sinh ra rmpo_choices: đổi Division thì grid
        # RMPO List cũ đã bị WFX nạp lại, token không còn trỏ vào dòng thật.
        self.rmpo_choices_division: str | None = None

    def _division_after(self, state: dict[str, Any]) -> str | None:
        division = state.get("current_division") or self._panel._current_division
        return str(division) if division else None

    @property
    def site_store(self) -> GrnSiteStore | None:
        # Danh sách Site chỉ là tiện ích: panel không có data dir (panel giả
        # trong test của module khác) thì coi như chưa nhớ Site nào.
        base_dir = getattr(self._panel, "_base_dir", None)
        return GrnSiteStore(base_dir) if base_dir is not None else None

    def _user_id(self) -> str:
        account = getattr(self._panel, "_account", None)
        return str(account().get("user_id") or "") if callable(account) else ""

    def _cached_sites(self, division: str | None) -> list[str]:
        store = self.site_store
        return store.load(self._user_id(), str(division or "")) if store else []

    def _remember_sites(self, division: str | None, sites: list[str]) -> None:
        store = self.site_store
        if store is None:
            return
        try:
            store.remember(self._user_id(), str(division or ""), sites)
        except OSError:
            pass

    def _canonical_site(
        self,
        requested: str,
        division: str | None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Site chọn sẵn phải nằm trong danh sách đã đọc của đúng Division."""
        if not requested:
            return "", None
        canonical = next(
            (
                item
                for item in self._cached_sites(division)
                if item.casefold() == requested.casefold()
            ),
            None,
        )
        if canonical is None:
            return "", {
                "ok": False,
                "code": "GRN_SITE_INVALID",
                "message": (
                    f"Site {requested} không có trong danh sách của Division "
                    "hiện tại. Hãy chọn lại Site, hoặc để trống để app đọc lại "
                    "danh sách Site từ WFX."
                ),
            }
        return canonical, None

    def grn_sites(self) -> dict:
        division = self._panel._current_division
        return {
            "ok": True,
            "code": "GRN_SITES",
            "division": str(division or ""),
            "sites": self._cached_sites(division),
        }

    def _align_grn_session(
        self,
        session: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        return align_division(
            self._panel,
            session.get("division"),
            reason=f"Phiên nhập kho RMPO {session['rmpo_no']}",
            module=_GRN_MODULE,
        )

    def search_rmpo(
        self,
        supplier: str,
        order_no: str,
    ) -> dict:
        panel = self._panel
        rmpo = constants.MODULE_BY_ID["0005_0050_0020"]
        cleaned_order = str(order_no or "").strip()

        def action() -> dict:
            self.rmpo_choices.clear()
            self.rmpo_choices_division = None
            failed, division = align_document_division(
                panel, cleaned_order, label=_RMPO_LABEL, module="RMPO List"
            )
            if failed is not None:
                return failed
            result = _hint_other_division(search(), cleaned_order)
            self.rmpo_choices_division = self._division_after(division)
            return with_document_division_state(
                result, division, label=_RMPO_LABEL
            )

        def search() -> dict:
            result = panel._login.search_rmpo_list(
                rmpo["xpath"],
                str(supplier or "").strip(),
                cleaned_order,
                panel._log,
            )
            if result.get("code") != "RMPO_RESULTS_READY":
                return result
            public_rows: list[dict[str, str]] = []
            for raw in result.get("rmpo_rows") or []:
                if not isinstance(raw, dict):
                    continue
                row = {
                    key: str(raw.get(key) or "").strip()
                    for key in (
                        "row_key",
                        "status",
                        "supplier",
                        "order_no",
                        "last_created",
                        "qty",
                    )
                }
                if not row["row_key"] or not row["order_no"]:
                    continue
                choice_id = secrets.token_urlsafe(18)
                self.rmpo_choices[choice_id] = row
                public_rows.append(
                    {
                        "choice_id": choice_id,
                        "status": row["status"],
                        "supplier": row["supplier"],
                        "order_no": row["order_no"],
                        "last_created": row["last_created"],
                        "qty": row["qty"],
                    }
                )
            if not public_rows:
                return {
                    "ok": False,
                    "code": "RMPO_NO_RESULTS",
                    "message": "Không đọc được dòng RMPO phù hợp để chọn.",
                    "rmpos": [],
                    "result_count": 0,
                }
            return {
                **result,
                "rmpos": public_rows,
                "result_count": max(
                    len(public_rows), int(result.get("result_count") or 0)
                ),
            }

        return panel._run(
            "search_rmpo",
            action,
            {"module_id": "0005_0050_0020"},
        )

    def run_rmpo_action(self, choice_id: str, action_name: str) -> dict:
        panel = self._panel
        token = str(choice_id or "").strip()
        requested_action = str(action_name or "").strip()

        def action() -> dict:
            choice = self.rmpo_choices.get(token)
            if choice is None:
                return {
                    "ok": False,
                    "code": "RMPO_RESULT_EXPIRED",
                    "message": "Lựa chọn RMPO đã hết hiệu lực. Hãy tìm lại.",
                }
            current = panel._current_division
            if (
                self.rmpo_choices_division
                and current
                and str(current) != self.rmpo_choices_division
            ):
                self.rmpo_choices.clear()
                return {
                    "ok": False,
                    "code": "RMPO_RESULT_EXPIRED",
                    "message": (
                        "Division đã đổi sau lượt tìm RMPO nên danh sách cũ "
                        "hết hiệu lực. Hãy tìm lại."
                    ),
                }
            return panel._login.open_rmpo_result_action(
                choice["row_key"],
                choice["order_no"],
                choice["supplier"],
                choice["status"],
                requested_action,
                panel._log,
            )

        return panel._run(
            "run_rmpo_action",
            action,
            {
                "module_id": "0005_0050_0020",
                "action": requested_action,
            },
        )

    def prepare_grn_receipt(
        self,
        rmpo_no: str,
        mode: str,
        rmpo_choice_id: str = "",
        site: str = "",
    ) -> dict:
        panel = self._panel
        cleaned_rmpo = " ".join(str(rmpo_no or "").split())
        cleaned_mode = str(mode or "").strip().casefold()
        choice_token = str(rmpo_choice_id or "").strip()
        requested_site = " ".join(str(site or "").split())

        def action() -> dict:
            supplier = ""
            if choice_token:
                choice = self.rmpo_choices.get(choice_token)
                if (
                    choice is None
                    or choice["order_no"].casefold() != cleaned_rmpo.casefold()
                ):
                    return {
                        "ok": False,
                        "code": "GRN_RMPO_SELECTION_EXPIRED",
                        "message": "Lựa chọn RMPO đã hết hiệu lực. Hãy chọn lại.",
                    }
                refusal = rmpo_receipt_refusal(choice["order_no"], choice["status"])
                if refusal is not None:
                    return refusal
                supplier = choice["supplier"]
            division: dict[str, Any] = {}
            if cleaned_mode in _GRN_MODES:
                failed, division = align_document_division(
                    panel, cleaned_rmpo, label=_RMPO_LABEL, module=_GRN_MODULE
                )
                if failed is not None:
                    return failed
            receipt_division = self._division_after(division)
            # Đối chiếu sau khi đổi Division: RMPO PSW-… dùng Site của Woven.
            chosen_site, invalid = self._canonical_site(
                requested_site, receipt_division
            )
            if invalid is not None:
                return invalid
            result = with_document_division_state(
                _hint_other_division(
                    panel._login.prepare_grn_receipt(
                        constants.MODULE_BY_ID["0005_0050_0020"]["xpath"],
                        cleaned_rmpo,
                        supplier,
                        cleaned_mode,
                        panel._log,
                        # Nước ngoài chỉ dùng Site sau checkpoint Sourcing ASN.
                        site=chosen_site if cleaned_mode == "domestic" else "",
                    ),
                    cleaned_rmpo,
                ),
                division,
                label=_RMPO_LABEL,
            )
            if result.get("code") not in {
                "GRN_SOURCING_ASN_READY",
                "GRN_SITE_SELECTION_REQUIRED",
            }:
                return result
            receipt_token = secrets.token_urlsafe(24)
            sites = clean_sites(result.get("sites") or [])
            if sites:
                self._remember_sites(receipt_division, sites)
            self.grn_sessions.clear()
            self.grn_sessions[receipt_token] = {
                "rmpo_no": str(result.get("rmpo_no") or cleaned_rmpo),
                "supplier": str(result.get("supplier") or supplier),
                "mode": cleaned_mode,
                "stage": (
                    "sourcing"
                    if result.get("code") == "GRN_SOURCING_ASN_READY"
                    else "site"
                ),
                "sites": sites,
                "site": chosen_site,
                # Bước nối tiếp quay về đúng Division này, kể cả khi user đổi
                # Division trong lúc tự Confirm Sourcing ASN trên WFX.
                "division": receipt_division,
            }
            return {**result, "receipt_token": receipt_token, "sites": sites}

        return panel._run(
            "prepare_grn_receipt",
            action,
            {
                "module_id": "grn_receipt",
                "mode": cleaned_mode,
                "from_rmpo_choice": bool(choice_token),
                "site_preselected": bool(requested_site),
            },
        )

    def continue_grn_receipt(
        self,
        receipt_token: str,
        sourcing_confirmed: bool,
        site: str = "",
    ) -> dict:
        panel = self._panel
        token = str(receipt_token or "").strip()
        confirmed = boolean(sourcing_confirmed)
        requested_site = " ".join(str(site or "").split())

        def action() -> dict:
            session = self.grn_sessions.get(token)
            if session is None or session.get("stage") != "sourcing":
                return {
                    "ok": False,
                    "code": "GRN_SESSION_EXPIRED",
                    "message": "Phiên nhập kho đã hết hiệu lực. Hãy bắt đầu lại.",
                }
            if not confirmed:
                return {
                    "ok": False,
                    "code": "GRN_SOURCING_CONFIRM_REQUIRED",
                    "message": "Chỉ tiếp tục sau khi đã Confirm Sourcing ASN trên WFX.",
                }
            # Site chọn ở checkpoint thắng Site chọn lúc bắt đầu.
            chosen_site, invalid = self._canonical_site(
                requested_site or str(session.get("site") or ""),
                session.get("division"),
            )
            if invalid is not None:
                return invalid
            failed, division = self._align_grn_session(session)
            if failed is not None:
                return failed
            result = with_document_division_state(
                panel._login.continue_grn_receipt(
                    session["supplier"],
                    panel._log,
                    rmpo_no=session["rmpo_no"],
                    site=chosen_site,
                ),
                division,
                label=_RMPO_LABEL,
            )
            if result.get("code") == "GRN_NEW_READY":
                self.grn_sessions.pop(token, None)
            if result.get("code") == "GRN_SITE_SELECTION_REQUIRED":
                sites = clean_sites(result.get("sites") or [])
                self._remember_sites(session.get("division"), sites)
                session["stage"] = "site"
                session["sites"] = sites
                result = {
                    **result,
                    "receipt_token": token,
                    "rmpo_no": session["rmpo_no"],
                    "supplier": session["supplier"],
                    "sites": sites,
                }
            return result

        return panel._run(
            "continue_grn_receipt",
            action,
            {"module_id": "grn_receipt"},
        )

    def finalize_grn_receipt(self, receipt_token: str, site: str) -> dict:
        panel = self._panel
        token = str(receipt_token or "").strip()
        requested_site = " ".join(str(site or "").split())

        def action() -> dict:
            session = self.grn_sessions.get(token)
            if session is None or session.get("stage") != "site":
                return {
                    "ok": False,
                    "code": "GRN_SESSION_EXPIRED",
                    "message": "Phiên nhập kho đã hết hiệu lực. Hãy bắt đầu lại.",
                }
            canonical_site = next(
                (
                    item
                    for item in session.get("sites") or []
                    if str(item).casefold() == requested_site.casefold()
                ),
                None,
            )
            if canonical_site is None:
                return {
                    "ok": False,
                    "code": "GRN_SITE_INVALID",
                    "message": "Site không còn trong danh sách GRN hiện tại.",
                }
            failed, division = self._align_grn_session(session)
            if failed is not None:
                return failed
            result = with_document_division_state(
                panel._login.finalize_grn_receipt(
                    session["rmpo_no"],
                    canonical_site,
                    panel._log,
                ),
                division,
                label=_RMPO_LABEL,
            )
            if result.get("ok"):
                self.grn_sessions.pop(token, None)
            return result

        return panel._run(
            "finalize_grn_receipt",
            action,
            {"module_id": "grn_receipt"},
        )

    def search_grn(self, filter_kind: str, query: str) -> dict:
        panel = self._panel
        cleaned_kind = str(filter_kind or "").strip().casefold()
        cleaned_query = " ".join(str(query or "").split())

        def action() -> dict:
            # Chỉ RMPO/Order No. mang tiền tố Division; số Invoice thì tìm ở
            # Division hiện tại.
            division: dict[str, Any] = {}
            if cleaned_kind == "rmpo":
                failed, division = align_document_division(
                    panel, cleaned_query, label=_RMPO_LABEL, module=_GRN_MODULE
                )
                if failed is not None:
                    return failed
            result = panel._login.search_grn_receipt(
                cleaned_kind,
                cleaned_query,
                panel._log,
            )
            if cleaned_kind == "rmpo":
                result = _hint_other_division(result, cleaned_query)
            return with_document_division_state(
                result,
                division,
                label=_RMPO_LABEL,
            )

        return panel._run(
            "search_grn",
            action,
            {
                "module_id": "grn_receipt",
                "filter_kind": cleaned_kind,
            },
        )
