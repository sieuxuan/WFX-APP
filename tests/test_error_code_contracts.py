"""Đồng bộ ba nguồn sự thật về mã lỗi: CLAUDE.md ↔ source ↔ telemetry.

`tests/test_telemetry.py::test_every_reportable_failure_code_has_a_human_description`
đã phủ chiều "code trả về → phải có mô tả". Hai chiều còn lại chưa ai giữ:

1. Đặc tả trong CLAUDE.md liệt kê các trạng thái lỗi bắt buộc của Catalog. Nếu
   một trạng thái không còn mã nào biểu diễn, người dùng mất hẳn chẩn đoán cho
   tình huống đó mà không ai biết.
2. Bảng mã lỗi có thể phình ra vì entry chết: flow bị gỡ nhưng mã vẫn nằm lại
   trong `NON_REPORTABLE_FAILURES`/`ERROR_CODE_INFO` và trong Hướng dẫn sử
   dụng, khiến người dùng đọc phải mục không bao giờ xảy ra.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from wfx_panel import automation, run_policy, telemetry, telemetry_labels
from wfx_panel.panel_api import NON_REPORTABLE_FAILURES

ROOT = Path(__file__).resolve().parent.parent
WFX_PANEL = ROOT / "wfx_panel"

# Đặc tả giữ tên trạng thái của state machine; code gom chúng thành mã nghiệp vụ
# thô hơn và đưa chi tiết vào `message`. Bảng này ghi lại phép gom đó, KÈM module
# sở hữu mã, để việc đổi tên hoặc dời mã không âm thầm làm mất một trạng thái.
_SPEC_STATE_CODES = {
    "CATALOG_MENU_NOT_FOUND": ("CATALOG_NOT_OPEN", "catalog"),
    "CATALOG_LEFT_NOT_FOUND": ("CATALOG_NOT_OPEN", "catalog"),
    "CATALOG_GRID_NOT_FOUND": ("CATALOG_NOT_OPEN", "catalog"),
    "CATALOG_DATA_NOT_READY": ("CATALOG_NOT_OPEN", "catalog"),
    "CATEGORY_OPTION_NOT_FOUND": ("CATEGORY_FAILED", "catalog"),
    "CATEGORY_NOT_CONFIRMED": ("CATEGORY_FAILED", "catalog"),
    "MASTER_NOT_FOUND": ("MASTER_NOT_FOUND", "catalog"),
    "MASTER_CLICK_NO_NAVIGATION": ("MASTER_FAILED", "catalog"),
    # Floating Filter dùng chung cho mọi grid WFX nên mã nằm ở modules.py.
    "FLOATING_FILTER_NOT_READY": ("FLOATING_FILTER_NOT_READY", "modules"),
    "FILTER_VALUE_NOT_CONFIRMED": ("FILTER_VALUE_NOT_CONFIRMED", "catalog"),
    "FILTER_RESULTS_NOT_READY": ("FILTER_RESULTS_NOT_READY", "catalog"),
    "RESULT_DETACHED": ("RESULT_DETACHED", "catalog"),
    "ARTICLE_OPEN_NOT_CONFIRMED": ("CATALOG_DESTINATION_FAILED", "catalog"),
    "ARTICLE_DESTINATION_NOT_FOUND": (
        "CATALOG_DESTINATION_FAILED",
        "catalog",
    ),
}

# Nợ kỹ thuật đã biết: entry còn trong bảng nhưng không flow nào trả về nữa.
# Danh sách này là RATCHET — chỉ được rút ngắn, không được dài thêm.
# Nhóm SALE_ASN_ORDER_* là tàn dư của luồng "Chỉ điền Order Details 8 cột" mà
# CLAUDE.md ghi rõ đã bị gỡ.
_KNOWN_STALE_NON_REPORTABLE = frozenset(
    {
        "BUYER_LIST_NOT_OPEN",
        "CATALOG_FOLDER_SCAN_IN_PROGRESS",
        "COMPANY_LIST_NOT_OPEN",
        "COSTING_ARTICLE_FLOW_PENDING",
        "COSTING_ARTICLE_NOT_FOUND",
        "GRN_SUPPLIER_AMBIGUOUS",
        "RMPO_ACTION_NOT_CONFIRMED",
        "SALE_ASN_ORDER_FILE_EMPTY",
        "SALE_ASN_ORDER_FILE_HEADERS_INVALID",
        "SALE_ASN_ORDER_FILE_VALIDATION_FAILED",
        "SALE_ASN_ORDER_REVIEW_EXPIRED",
    }
)
_KNOWN_STALE_ERROR_INFO = frozenset(
    {
        "COSTING_NEW_DIALOG_NOT_FOUND",
        "COSTING_NEW_FAILED",
        "SALE_ASN_ORDER_FILE_EMPTY",
        "SALE_ASN_ORDER_FILE_HEADERS_INVALID",
        "SALE_ASN_ORDER_FILE_VALIDATION_FAILED",
        "SALE_ASN_ORDER_FILL_FAILED",
        "SALE_ASN_ORDER_REVIEW_EXPIRED",
        "SALE_ASN_ORDER_TEMPLATE_EXPORT_FAILED",
        "SALE_ASN_PO_POPUP_NOT_CLOSED",
        "SALE_ASN_PRICE_CHECK_FAILED",
        "SALE_ASN_SHIPPING_FIELD_FAILED",
    }
)


def _spec_error_codes() -> list[str]:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    block = re.search(
        r"Các error code tối thiểu:\s*```text\n(.*?)```",
        text,
        re.S,
    )
    assert block is not None, "CLAUDE.md không còn khối 'Các error code tối thiểu'"
    return [line.strip() for line in block.group(1).splitlines() if line.strip()]


def _literals_by_module() -> dict[str, set[str]]:
    """Literal chuỗi của từng module automation, tra theo tên module.

    Module lớn đã tách thành package (``costing/``, ``modules/``…) nên một tên
    module gom literal của mọi file con. Bảng ánh xạ vì thế nói "mã này thuộc
    module nào", không phải "nằm ở file nào".
    """
    automation_dir = Path(automation.__file__).parent
    values: dict[str, set[str]] = {}
    for path in automation_dir.rglob("*.py"):
        relative = path.relative_to(automation_dir)
        module = relative.parts[0].removesuffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values.setdefault(module, set()).update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    return values


def test_spec_and_code_cover_exactly_the_same_error_states():
    """Khối đặc tả và bảng ánh xạ phải khớp nhau từng mã."""
    spec_codes = set(_spec_error_codes())
    assert len(spec_codes) >= 14, "Danh sách đặc tả bị cắt ngắn"
    assert spec_codes == set(_SPEC_STATE_CODES), (
        "CLAUDE.md và _SPEC_STATE_CODES đã lệch nhau: "
        f"chỉ có trong đặc tả={sorted(spec_codes - set(_SPEC_STATE_CODES))}, "
        f"chỉ có trong test={sorted(set(_SPEC_STATE_CODES) - spec_codes)}"
    )


def test_every_spec_error_state_still_has_a_real_code():
    literals = _literals_by_module()
    missing = []
    for spec_code, (actual, module) in _SPEC_STATE_CODES.items():
        if actual not in literals.get(module, set()):
            missing.append(f"{spec_code} -> {actual} ({module})")

    assert not missing, (
        "Trạng thái lỗi trong CLAUDE.md không còn mã nào biểu diễn "
        f"đúng chỗ: {', '.join(missing)}"
    )


def _table_line_ranges(path: Path, name: str) -> list[tuple[int, int]]:
    """Vùng dòng của chính bảng khai báo, để không tự đếm mình là một lần dùng."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    ranges = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign | ast.Expr):
            continue
        head = ast.unparse(node)[:120]
        if head.startswith(f"{name} =") or head.startswith(f"{name}.update"):
            ranges.append((node.lineno, node.end_lineno or node.lineno))
    assert ranges, f"Không tìm thấy bảng {name} trong {path.name}"
    return ranges


def _unused_entries(table: frozenset[str] | dict, skip: dict[Path, list]) -> set[str]:
    sources = {
        path: path.read_text(encoding="utf-8").splitlines()
        for path in WFX_PANEL.rglob("*.py")
    }
    unused = set()
    for code in table:
        # Cho phép cả `"CODE"` lẫn `"CODE: chi tiết"` của raise RuntimeError.
        pattern = re.compile(rf'["\']{re.escape(code)}[:"\']')
        used = False
        for path, lines in sources.items():
            ranges = skip.get(path, [])
            for number, line in enumerate(lines, 1):
                if any(lo <= number <= hi for lo, hi in ranges):
                    continue
                if pattern.search(line):
                    used = True
                    break
            if used:
                break
        if not used:
            unused.add(code)
    return unused


def _skip_ranges() -> dict[Path, list[tuple[int, int]]]:
    """Vùng dòng của chính hai bảng khai báo, để không tự đếm mình là một lần dùng.

    ``ERROR_CODE_INFO`` sống ở ``telemetry_labels`` chứ không phải ``telemetry``:
    nó là dữ liệu, còn ``telemetry.py`` chỉ giữ logic gửi.
    """
    run_policy_path = Path(run_policy.__file__)
    labels_path = Path(telemetry_labels.__file__)
    return {
        run_policy_path: _table_line_ranges(
            run_policy_path, "NON_REPORTABLE_FAILURES"
        ),
        labels_path: _table_line_ranges(labels_path, "ERROR_CODE_INFO"),
    }


def test_non_reportable_failures_gains_no_new_dead_entry():
    unused = _unused_entries(NON_REPORTABLE_FAILURES, _skip_ranges())
    new_dead = unused - _KNOWN_STALE_NON_REPORTABLE
    assert not new_dead, (
        "Mã mới trong NON_REPORTABLE_FAILURES nhưng không flow nào trả về: "
        + ", ".join(sorted(new_dead))
    )


def test_error_code_info_gains_no_new_dead_entry():
    unused = _unused_entries(telemetry.ERROR_CODE_INFO, _skip_ranges())
    new_dead = unused - _KNOWN_STALE_ERROR_INFO
    assert not new_dead, (
        "Mã mới có mô tả trong ERROR_CODE_INFO nhưng không flow nào trả về: "
        + ", ".join(sorted(new_dead))
    )


def test_known_stale_lists_shrink_when_the_tables_are_cleaned_up():
    """Ratchet: dọn xong mã nào thì phải xoá mã đó khỏi danh sách nợ."""
    leftover_non_reportable = sorted(
        code
        for code in _KNOWN_STALE_NON_REPORTABLE
        if code not in NON_REPORTABLE_FAILURES
    )
    leftover_info = sorted(
        code
        for code in _KNOWN_STALE_ERROR_INFO
        if code not in telemetry.ERROR_CODE_INFO
    )
    assert not leftover_non_reportable, (
        "Đã dọn khỏi NON_REPORTABLE_FAILURES, hãy xoá khỏi "
        f"_KNOWN_STALE_NON_REPORTABLE: {', '.join(leftover_non_reportable)}"
    )
    assert not leftover_info, (
        "Đã dọn khỏi ERROR_CODE_INFO, hãy xoá khỏi _KNOWN_STALE_ERROR_INFO: "
        + ", ".join(leftover_info)
    )
