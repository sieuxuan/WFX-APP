"""Áp plan Costing đã dry-run xuống WFX rồi đọc lại để xác nhận."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.costing.articles import (
    _add_articles,
    _add_special_cost_lines,
    _article_identity,
    _delete_articles,
    _preflight_article_additions,
    _split_article_row,
)
from wfx_panel.automation.costing.constants import (
    CostingApplyAbort,
    CostingFieldApplyError,
)
from wfx_panel.automation.costing.context import (
    _active_costing_page,
    _article_code_from_page,
    _costing_frame,
    _selected_costing_title,
)
from wfx_panel.automation.costing.dependencies import (
    _dependency_kind,
    _set_dependency_mapping,
)
from wfx_panel.automation.costing.fields import (
    _field_application_priority,
    _field_value_matches,
    _live_field_index,
    _save_costing,
    _set_live_field,
)
from wfx_panel.automation.costing.inventory import _inventory_costing_frame
from wfx_panel.automation.costing.variants import (
    _add_missing_material_variant,
    _material_variant_config,
)
from wfx_panel.automation.runtime import checkpoint
from wfx_panel.automation.session import _session_is_active
from wfx_panel.workbooks.costing_planner import (
    CostingPlanError,
    build_costing_plan,
    live_signature,
)


@dataclass
class _CostingApplySession:
    article_code: str
    browser: Any
    context: Any
    costing_page: Page
    frame: Frame
    scoped_pages: Sequence[Page] | None
    live: dict[str, Any]
    working_plan: dict[str, Any]
    source_document: Mapping[str, Any] | None
    log: Callable[[str], None]


@dataclass
class _CostingApplyProgress:
    preflight: dict[str, Any] = dataclass_field(default_factory=dict)
    added: list[dict[str, Any]] = dataclass_field(default_factory=list)
    cost_line_added: list[dict[str, Any]] = dataclass_field(default_factory=list)
    deleted: list[dict[str, Any]] = dataclass_field(default_factory=list)
    split: list[dict[str, Any]] = dataclass_field(default_factory=list)
    applied: list[dict[str, Any]] = dataclass_field(default_factory=list)
    material_variants_added: list[dict[str, Any]] = dataclass_field(
        default_factory=list
    )
    skipped: list[dict[str, Any]] = dataclass_field(default_factory=list)
    dependency_confirmed: set[tuple[str, str, str, str]] = dataclass_field(
        default_factory=set
    )


def _validate_costing_apply_request(
    article_code: str,
    plan: Mapping[str, Any],
    source_document: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if plan.get("new_required"):
        return _result(
            False,
            "COSTING_NOT_OPEN",
            "CostSheet phải ở trạng thái Open trước khi import.",
            article_code=article_code,
        )
    article_mutations = (
        plan.get("additions")
        or plan.get("cost_line_additions")
        or plan.get("splits")
        or plan.get("deletes")
    )
    if not article_mutations or source_document is not None:
        return None
    return _result(
        False,
        "COSTING_SOURCE_REQUIRED",
        "Plan thêm/split/xóa Article thiếu dữ liệu nguồn server-side.",
        additions=list(plan.get("additions") or ()),
        cost_line_additions=list(plan.get("cost_line_additions") or ()),
        splits=list(plan.get("splits") or ()),
        deletes=list(plan.get("deletes") or ()),
    )


def _costing_plan_has_changes(plan: Mapping[str, Any]) -> bool:
    return any(
        plan.get(key)
        for key in (
            "additions",
            "cost_line_additions",
            "splits",
            "deletes",
            "fields_to_set",
        )
    )


def _costing_apply_scope(
    context: Any,
    article_code: str,
    active_tab_only: bool,
) -> Sequence[Page] | None:
    if not active_tab_only:
        return None
    active_page = _active_costing_page(context)
    detected_code = _article_code_from_page(active_page)
    if not detected_code:
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_STYLE_NOT_DETECTED",
                "Không đọc được Style Code từ tab Costing đang chọn.",
            )
        )
    if detected_code.casefold() == article_code.casefold():
        return [active_page]
    raise CostingApplyAbort(
        _result(
            False,
            "COSTING_STYLE_MISMATCH",
            (
                "Tab Costing đang chọn không còn khớp file dry-run. "
                "Hãy quay lại đúng style rồi thử lại."
            ),
            file_style=article_code,
            live_style=detected_code,
        )
    )


def _open_costing_apply_session(
    browser: Any,
    article_code: str,
    plan: Mapping[str, Any],
    source_document: Mapping[str, Any] | None,
    active_tab_only: bool,
    log: Callable[[str], None],
) -> _CostingApplySession:
    context = browser.contexts[0]
    scoped_pages = _costing_apply_scope(
        context,
        article_code,
        active_tab_only,
    )
    costing_page, frame = _costing_frame(context, pages=scoped_pages)
    live = _inventory_costing_frame(
        frame,
        article_code,
        costing_status=str(plan.get("costing_status") or ""),
        title=_selected_costing_title(context, pages=scoped_pages),
    )
    if str(live.get("cost_sheet_status") or "").casefold() != "open":
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_NOT_OPEN",
                "CostSheet không còn ở trạng thái Open. Hãy mở/tạo Costing trước.",
                article_code=article_code,
            )
        )
    if str(plan.get("live_signature") or "") != live_signature(live):
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_PLAN_STALE",
                "Costing đã thay đổi sau dry-run. Hãy import và kiểm tra lại.",
            )
        )
    return _CostingApplySession(
        article_code=article_code,
        browser=browser,
        context=context,
        costing_page=costing_page,
        frame=frame,
        scoped_pages=scoped_pages,
        live=live,
        working_plan=dict(plan),
        source_document=source_document,
        log=log,
    )


def _refresh_apply_inventory(
    session: _CostingApplySession,
    *,
    wait_ms: int = 0,
    rebuild_plan: bool = True,
) -> None:
    if wait_ms:
        _wait(session.costing_page, wait_ms)
    session.live = _inventory_costing_frame(
        session.frame,
        session.article_code,
        costing_status="Open",
        title=_selected_costing_title(
            session.context,
            pages=session.scoped_pages,
        ),
    )
    if rebuild_plan and session.source_document is not None:
        session.working_plan = build_costing_plan(
            session.source_document,
            session.live,
        )


def _normalize_article_resolutions(
    article_resolutions: Mapping[str, str] | None,
) -> dict[str, str]:
    return {
        str(key): str(value).strip()
        for key, value in dict(article_resolutions or {}).items()
        if str(key).strip() and str(value).strip()
    }


def _prepare_costing_articles(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
    article_resolutions: Mapping[str, str] | None,
) -> None:
    _write_log(
        session.log,
        "[COSTING] Đang kiểm tra Article trước khi điền field.",
    )
    progress.preflight = _preflight_article_additions(
        session.context,
        session.frame,
        session.working_plan.get("additions") or (),
        _normalize_article_resolutions(article_resolutions),
        session.log,
    )
    if progress.preflight["ambiguous"]:
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_ARTICLE_AMBIGUOUS",
                "Có Article trùng kết quả. Chọn đúng Article Code rồi áp dụng lại.",
                ambiguous_articles=progress.preflight["ambiguous"],
                missing_articles=progress.preflight["missing"],
            )
        )
    progress.deleted = _delete_articles(
        session.costing_page,
        session.frame,
        session.live,
        session.working_plan.get("deletes") or (),
        session.log,
    )
    progress.added = _add_articles(
        session.context,
        session.frame,
        progress.preflight,
        session.log,
    )
    if progress.added or progress.deleted:
        _refresh_apply_inventory(session, wait_ms=500)
    progress.cost_line_added = _add_special_cost_lines(
        session.frame,
        session.working_plan.get("cost_line_additions") or (),
        session.log,
    )
    if progress.cost_line_added:
        _refresh_apply_inventory(session, wait_ms=350)


def _missing_article_codes(preflight: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("article_code") or item.get("article_name") or "").casefold()
        for item in preflight.get("missing") or ()
    }


def _apply_costing_splits(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
) -> None:
    missing_codes = _missing_article_codes(progress.preflight)
    pending_splits = [
        request
        for request in session.working_plan.get("splits") or ()
        if str(
            request.get("article_code") or request.get("article_name") or ""
        ).casefold()
        not in missing_codes
    ]
    if pending_splits:
        _write_log(
            session.log,
            f"[COSTING] Đang Splitter {len(pending_splits)} dòng Article liền nhau.",
        )
    for request in pending_splits:
        checkpoint()
        _split_article_row(session.frame, session.live, request)
        progress.split.append(dict(request))
        _refresh_apply_inventory(
            session,
            wait_ms=250,
            rebuild_plan=False,
        )
    if progress.split and session.source_document is not None:
        session.working_plan = build_costing_plan(
            session.source_document,
            session.live,
        )


def _costing_change_key(
    change: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    return (
        str(change.get("scope") or "").casefold(),
        str(change.get("section_key") or "").casefold(),
        str(change.get("item_key") or "").casefold(),
        str(change.get("field_key") or "").casefold(),
    )


def _change_belongs_to_missing_article(
    change: Mapping[str, Any],
    missing_item_keys: set[str],
) -> bool:
    return (
        str(change.get("scope") or "").casefold() == "item"
        and str(change.get("item_key") or "").casefold() in missing_item_keys
    )


def _apply_single_costing_field(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
    live_fields: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
    change: Mapping[str, Any],
    change_index: int,
    change_count: int,
) -> None:
    key = _costing_change_key(change)
    live_field = live_fields.get(key)
    if live_field is None or not live_field.get("editable"):
        progress.skipped.append({**change, "reason": "not_found_or_read_only"})
        return
    try:
        if (
            _material_variant_config(live_field) is not None
            and _add_missing_material_variant(
                session.context,
                session.frame,
                live_field,
                change.get("value"),
                session.log,
            )
        ):
            progress.material_variants_added.append(dict(change))
        if _dependency_kind(live_field, change.get("value")):
            _set_dependency_mapping(
                session.frame,
                live_field,
                change.get("value"),
            )
            progress.dependency_confirmed.add(key)
        else:
            _set_live_field(session.frame, live_field, change.get("value"))
    except (PlaywrightError, RuntimeError) as error:
        field_key = str(change.get("field_key") or "")
        item_key = str(change.get("item_key") or "")
        reason = _first_line(error)[:160]
        _write_log(
            session.log,
            "[COSTING] Không thể điền field "
            f"{change_index}/{change_count} "
            f"{field_key} ({item_key}): {reason}",
        )
        raise CostingFieldApplyError(field_key, item_key, reason) from error
    progress.applied.append(dict(change))


def _apply_costing_fields(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
) -> None:
    live_fields = _live_field_index(session.live)
    missing_item_keys = {
        str(item.get("import_item_key") or "").casefold()
        for item in progress.preflight.get("missing") or ()
    }
    ordered_changes = sorted(
        session.working_plan.get("fields_to_set") or (),
        key=_field_application_priority,
    )
    change_count = len(ordered_changes)
    if change_count:
        _write_log(
            session.log,
            f"[COSTING] Bắt đầu điền {change_count} field.",
        )
    for change_index, change in enumerate(ordered_changes, 1):
        checkpoint()
        if _change_belongs_to_missing_article(change, missing_item_keys):
            progress.skipped.append({**change, "reason": "article_not_found"})
            continue
        _apply_single_costing_field(
            session,
            progress,
            live_fields,
            change,
            change_index,
            change_count,
        )
        if change_index == 1 or change_index % 10 == 0:
            _write_log(
                session.log,
                f"[COSTING] Đã điền {change_index}/{change_count} field.",
            )


def _field_verification_mismatches(
    verified: Mapping[str, Any],
    progress: _CostingApplyProgress,
) -> list[dict[str, Any]]:
    verified_fields = _live_field_index(verified)
    mismatches: list[dict[str, Any]] = []
    for change in progress.applied:
        key = _costing_change_key(change)
        if key in progress.dependency_confirmed:
            # Main inventory only renders [Table]; the popup was checked exactly.
            continue
        actual = verified_fields.get(key, {}).get("value")
        if _field_value_matches(
            actual,
            change.get("value"),
            str(change.get("data_type") or "text"),
        ):
            continue
        mismatches.append(
            {
                "field_key": change.get("field_key"),
                "expected": change.get("value"),
                "actual": actual,
            }
        )
    return mismatches


def _article_verification_mismatches(
    verified: Mapping[str, Any],
    progress: _CostingApplyProgress,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    verified_codes = {
        str(item.get("article_code") or "").casefold()
        for item in verified.get("items") or ()
        if str(item.get("article_code") or "").strip()
    }
    for addition in progress.added:
        code = str(addition.get("resolved_code") or "").strip()
        if code and code.casefold() not in verified_codes:
            mismatches.append(
                {
                    "field_key": f"Article:{code}",
                    "expected": "present",
                    "actual": "missing_after_save",
                }
            )
    for deletion in progress.deleted:
        code = str(deletion.get("article_code") or "").strip()
        if code and code.casefold() in verified_codes:
            mismatches.append(
                {
                    "field_key": f"Article:{code}",
                    "expected": "deleted",
                    "actual": "still_present_after_save",
                }
            )
    return mismatches


def _cost_line_verification_mismatches(
    verified: Mapping[str, Any],
    additions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    identities = {
        (
            str(item.get("section_key") or "").casefold(),
            str(item.get("article_name") or "").casefold(),
        )
        for item in verified.get("items") or ()
        if str(item.get("item_type") or "").casefold() == "cost_line"
    }
    return [
        {
            "field_key": f"Cost line:{addition.get('article_name', '')}",
            "expected": "present",
            "actual": "missing_after_save",
        }
        for addition in additions
        if (
            str(addition.get("section_key") or "").casefold(),
            str(addition.get("article_name") or "").casefold(),
        )
        not in identities
    ]


def _split_verification_mismatches(
    verified: Mapping[str, Any],
    split_requests: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    identity_counts: dict[tuple[str, str], int] = {}
    for item in verified.get("items") or ():
        identity = _article_identity(item)
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
    mismatches: list[dict[str, Any]] = []
    for split_request in split_requests:
        expected_count = int(split_request.get("occurrence") or 2)
        actual_count = identity_counts.get(_article_identity(split_request), 0)
        if actual_count >= expected_count:
            continue
        article_identity = str(
            split_request.get("article_code") or split_request.get("article_name") or ""
        )
        mismatches.append(
            {
                "field_key": f"Splitter:{article_identity}",
                "expected": expected_count,
                "actual": actual_count,
            }
        )
    return mismatches


def _verify_costing_apply(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
) -> list[dict[str, Any]]:
    _wait(session.costing_page, 500)
    session.costing_page, session.frame = _costing_frame(
        session.context,
        timeout_seconds=10,
        pages=session.scoped_pages,
    )
    verified = _inventory_costing_frame(
        session.frame,
        session.article_code,
        costing_status="Open",
        title=_selected_costing_title(
            session.context,
            pages=session.scoped_pages,
        ),
    )
    return [
        *_field_verification_mismatches(verified, progress),
        *_article_verification_mismatches(verified, progress),
        *_cost_line_verification_mismatches(
            verified,
            progress.cost_line_added,
        ),
        *_split_verification_mismatches(verified, progress.split),
    ]


def _no_change_apply_result(article_code: str) -> dict[str, Any]:
    return _result(
        True,
        "COSTING_APPLIED",
        f"Costing style {article_code} đã khớp file; không cần Save.",
        article_code=article_code,
        applied_count=0,
        added_count=0,
        cost_line_added_count=0,
        split_count=0,
        deleted_count=0,
        material_variant_added_count=0,
        skipped_fields=[],
        verified=True,
        no_changes=True,
    )


def _run_costing_apply(
    session: _CostingApplySession,
    article_resolutions: Mapping[str, str] | None,
) -> dict[str, Any]:
    if not _costing_plan_has_changes(session.working_plan):
        return _no_change_apply_result(session.article_code)
    progress = _CostingApplyProgress()
    _prepare_costing_articles(session, progress, article_resolutions)
    _apply_costing_splits(session, progress)
    _apply_costing_fields(session, progress)
    _save_costing(session.costing_page, session.frame, session.log)
    mismatches = _verify_costing_apply(session, progress)
    if mismatches:
        return _result(
            False,
            "COSTING_VERIFY_FAILED",
            "WFX chưa xác nhận một số field sau Save.",
            applied_count=len(progress.applied),
            skipped_fields=progress.skipped,
            mismatches=mismatches,
        )
    return _result(
        True,
        "COSTING_APPLIED",
        f"Đã cập nhật và Save Costing cho style {session.article_code}.",
        article_code=session.article_code,
        applied_count=len(progress.applied),
        added_count=len(progress.added),
        cost_line_added_count=len(progress.cost_line_added),
        split_count=len(progress.split),
        deleted_count=len(progress.deleted),
        material_variant_added_count=len(progress.material_variants_added),
        missing_articles=progress.preflight["missing"],
        skipped_fields=progress.skipped,
        verified=True,
    )


def apply_costing_plan(
    article_code: str,
    plan: Mapping[str, Any],
    *,
    source_document: Mapping[str, Any] | None = None,
    article_resolutions: Mapping[str, str] | None = None,
    active_tab_only: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Áp dụng plan Open-only: Material Search, field, Delete và Save."""
    article_code = str(article_code or "").strip()
    validation_error = _validate_costing_apply_request(
        article_code,
        plan,
        source_document,
    )
    if validation_error is not None:
        return validation_error
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        session = _open_costing_apply_session(
            browser,
            article_code,
            plan,
            source_document,
            active_tab_only,
            log,
        )
        return _run_costing_apply(session, article_resolutions)
    except CostingApplyAbort as error:
        return error.result
    except CostingFieldApplyError as error:
        return _result(
            False,
            "COSTING_FIELD_APPLY_FAILED",
            (
                f"Không thể điền field {error.field_key or '(không rõ)'}"
                f"{f' của Article {error.item_key}' if error.item_key else ''}."
            ),
            article_code=article_code,
            failed_field=error.field_key,
            failed_item=error.item_key,
            failure_reason=error.reason,
        )
    except PlaywrightTimeoutError as error:
        code = (
            str(error) if str(error).startswith("COSTING_") else "COSTING_APPLY_FAILED"
        )
        return _result(False, code, "WFX chưa sẵn sàng để áp dụng Costing.")
    except CostingPlanError as error:
        return error.as_result()
    except Exception as error:
        raw = _first_line(error)
        code = (
            raw.split(":", 1)[0]
            if raw.startswith("COSTING_")
            else "COSTING_APPLY_FAILED"
        )
        _write_log(log, f"[COSTING] {type(error).__name__}: {raw}")
        return _result(
            False,
            code,
            "Không thể áp dụng Costing; chưa xác nhận Save thành công.",
        )
    finally:
        if playwright is not None:
            playwright.stop()
