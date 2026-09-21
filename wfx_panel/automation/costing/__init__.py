"""Khảo sát và thao tác Costing trong popup Article của WFX.

Module chỉ tin metadata vừa quét từ DOM hiện tại. Workbook không được truyền
selector/DOM index vào các hàm ghi dữ liệu.

Trước đây đây là một file 4684 dòng. Nay tách theo tầng: constants →
keys/dom/context → fields/articles/variants →
dependencies → inventory → apply/scan. Package re-export nguyên
bề mặt cũ nên caller và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của costing.py: các tên này từng nằm ở module level nên test và
# caller vẫn gắn/đọc qua ``costing.<tên>``. Giữ nguyên để tách file không đổi
# hợp đồng import.
from wfx_panel.automation._common import (  # noqa: F401
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _sleep,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (  # noqa: F401
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.costing.apply import (  # noqa: F401
    _apply_costing_fields,
    _apply_costing_splits,
    _apply_single_costing_field,
    _article_verification_mismatches,
    _change_belongs_to_missing_article,
    _cost_line_verification_mismatches,
    _costing_apply_scope,
    _costing_change_key,
    _costing_plan_has_changes,
    _CostingApplyProgress,
    _CostingApplySession,
    _field_verification_mismatches,
    _missing_article_codes,
    _no_change_apply_result,
    _normalize_article_resolutions,
    _open_costing_apply_session,
    _prepare_costing_articles,
    _refresh_apply_inventory,
    _run_costing_apply,
    _split_verification_mismatches,
    _validate_costing_apply_request,
    _verify_costing_apply,
    apply_costing_plan,
)
from wfx_panel.automation.costing.articles import (  # noqa: F401
    _add_articles,
    _add_special_cost_lines,
    _article_identity,
    _close_material_search,
    _delete_articles,
    _delete_row_index,
    _material_option_rows,
    _material_rows,
    _material_search_frame,
    _new_special_cost_row,
    _preflight_article_additions,
    _resolved_search,
    _scan_costing_article_dropdowns,
    _scan_material_option_rows,
    _search_material,
    _section_action,
    _section_row_index,
    _select_material_match,
    _select_special_cost_article,
    _special_cost_config,
    _split_article_row,
)
from wfx_panel.automation.costing.constants import (  # noqa: F401
    _ARTICLE_LEFT_STYLE_RE,
    _ARTICLE_NAME_CODE_RE,
    _ARTICLE_NAME_VALUE_RE,
    _COSTING_INVENTORY_JS,
    _COSTING_NO_OPEN_RE,
    _COSTING_STATUS_RE,
    _DEPENDENCY_OPTIONS_JS,
    _INLINE_EDITOR_JS,
    _KEY_CLEAN_RE,
    _MATCHING_OPTION_VALUES_JS,
    _MATERIAL_VARIANT_CARD_XPATH,
    _MATERIAL_VARIANT_CLOSE_XPATH,
    _MATERIAL_VARIANT_FIELDS,
    _MATERIAL_VARIANT_SAVE_XPATH,
    _MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH,
    _MATERIAL_VARIANT_SEARCH_XPATH,
    _SPECIAL_COST_SECTION_EDITORS,
    _STYLE_CODE_CONTROL_SELECTORS,
    _STYLE_CODE_RE,
    _USABLE_CONTROL_JS,
    _VISIBLE_JS,
    _VISIBLE_WITH_ID_JS,
    COSTING_DETAIL_SELECTOR,
    COSTING_GRID_SELECTOR,
    COSTING_NEW_SELECTOR,
    COSTING_SAVE_SELECTOR,
    COSTING_TREE_SELECTOR,
    DEPENDENCY_TABLE_ATTEMPTS,
    FIELD_CONTROL_SELECTOR,
    FORBIDDEN_ACTION_SELECTORS,
    FORBIDDEN_CONTROL_IDS,
    CostingApplyAbort,
    CostingFieldApplyError,
)
from wfx_panel.automation.costing.context import (  # noqa: F401
    _active_costing_page,
    _article_code_from_page,
    _costing_frame,
    _page_activity,
    _page_has_costing_context,
    _selected_costing_title,
    _status_from_tree,
    _style_codes_from_text,
    _style_name_from_page,
)
from wfx_panel.automation.costing.dependencies import (  # noqa: F401
    _apply_dependency_rules,
    _cancel_dependency_popup,
    _dependency_kind,
    _dependency_mapping_rules,
    _dependency_match_tokens,
    _dependency_option_indexes,
    _dependency_scan_incomplete,
    _dependency_source_label,
    _dependency_values,
    _ensure_table_dependency_mode,
    _matching_dependency_rule,
    _open_dependency_popup,
    _scan_costing_dependency_tables,
    _scan_dependency_table,
    _scan_dependency_tables_from_page_data,
    _set_dependency_mapping,
    _set_dependency_row_options,
    _split_dependency_display_values,
)
from wfx_panel.automation.costing.dom import (  # noqa: F401
    _apply_inline_select_option,
    _close_inline_editor,
    _edit_wfx_label,
    _evaluate_all,
    _filtered_indexes,
    _option_value,
    _select_options,
    _unique_visible_by_id,
    _visible_controls,
    _visible_costing_grid,
    _visible_unique,
)
from wfx_panel.automation.costing.fields import (  # noqa: F401
    _field_application_priority,
    _field_value_matches,
    _live_field_index,
    _resolve_live_field,
    _save_costing,
    _set_live_field,
)
from wfx_panel.automation.costing.inventory import (  # noqa: F401
    _add_production_value_fields,
    _ensure_dependency_mapping_fields,
    _inventory_costing_frame,
    _inventory_to_document,
    _scan_costing_item_options,
    _scan_special_cost_options,
    _special_section_options,
)
from wfx_panel.automation.costing.keys import (  # noqa: F401
    _base_costing_field_key,
    _clean_key,
    _costing_semantic_token,
)
from wfx_panel.automation.costing.scan import (  # noqa: F401
    _costing_scan_error,
    _scan_open_costing_context,
    clear_active_costing_dependencies,
    costing_forbidden_selectors,
    inspect_active_costing,
    scan_active_open_costing,
    scan_open_costing,
)
from wfx_panel.automation.costing.variants import (  # noqa: F401
    _add_material_variant_to_card,
    _add_missing_material_variant,
    _choose_and_add_material_variant,
    _close_material_variant_list,
    _costing_row_for_field,
    _material_variant_candidate_select,
    _material_variant_card_select,
    _material_variant_config,
    _material_variant_is_available,
    _material_variant_list_frame,
    _material_variant_option_matches,
    _material_variant_search_input,
    _material_variant_tokens,
    _open_material_variant_editor,
    _save_material_variant_list,
    _search_material_variant,
    _select_material_variant_card,
)
from wfx_panel.automation.runtime import (  # noqa: F401
    cancellation_deferred,
    checkpoint,
)
from wfx_panel.automation.session import _session_is_active  # noqa: F401
from wfx_panel.workbooks.costing import (  # noqa: F401
    FORMAT_VERSION,
    normalize_document,
)
from wfx_panel.workbooks.costing_planner import (  # noqa: F401
    CostingPlanError,
    build_costing_plan,
    live_signature,
)

__all__ = [
    "COSTING_DETAIL_SELECTOR",
    "COSTING_GRID_SELECTOR",
    "COSTING_NEW_SELECTOR",
    "COSTING_SAVE_SELECTOR",
    "COSTING_TREE_SELECTOR",
    "CostingApplyAbort",
    "CostingFieldApplyError",
    "DEPENDENCY_TABLE_ATTEMPTS",
    "FIELD_CONTROL_SELECTOR",
    "FORBIDDEN_ACTION_SELECTORS",
    "FORBIDDEN_CONTROL_IDS",
    "apply_costing_plan",
    "clear_active_costing_dependencies",
    "costing_forbidden_selectors",
    "inspect_active_costing",
    "scan_active_open_costing",
    "scan_open_costing",
]
