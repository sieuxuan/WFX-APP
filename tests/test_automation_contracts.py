"""Ràng buộc tĩnh cho các quy tắc "tuyệt đối không" trong CLAUDE.md.

Những quy tắc này không thể phủ bằng test hành vi vì chúng nói về *toàn bộ* lớp
automation chứ không về một lời gọi: "không bao giờ click selector X", "mọi
`connect_over_cdp` phải truyền `no_defaults=True`". Quét AST là cách duy nhất
khẳng định được "không còn chỗ nào", giống ``test_cancellation_contract.py``.

Mỗi test ghi rõ hậu quả thật khi vi phạm, để người sửa sau biết vì sao quy tắc
tồn tại chứ không chỉ thấy một assert đỏ.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from wfx_panel.automation import costing, runtime, session

AUTOMATION_DIR = Path(runtime.__file__).resolve().parent

# CLAUDE.md: "Costing tuyệt đối không click #colBodyType label span,
# #imgDeleteSection, #imgEditSection hoặc #imgCopySection." Click nhầm là xoá
# hoặc nhân bản nguyên một Section của Cost Sheet — mất dữ liệu, không undo.
FORBIDDEN_SECTION_IDS = frozenset(
    {
        "colBodyType",
        "imgDeleteSection",
        "imgEditSection",
        "imgCopySection",
    }
)

FORBIDDEN_SECTION_SELECTORS = frozenset(
    {
        "#colBodyType label span",
        "#imgDeleteSection",
        "#imgEditSection",
        "#imgCopySection",
    }
)

# CLAUDE.md: các probe chỉ đọc session/Division/quyền và ảnh chẩn đoán phải
# dùng `bring_to_front=False` để không kéo người dùng khỏi tab đang làm.
READ_ONLY_PROBES = frozenset(
    {
        "get_division_state",
        "check_session",
        "check_module_access",
        "capture_failure_screenshot",
    }
)


def _automation_sources() -> list[Path]:
    return sorted(
        path
        for path in AUTOMATION_DIR.glob("*.py")
        if path.name != "__init__.py"
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str:
    best = "<module>"
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        end = candidate.end_lineno or candidate.lineno
        if candidate.lineno <= node.lineno <= end:
            best = candidate.name
    return best


def _calls_named(tree: ast.Module, name: str) -> list[ast.Call]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if called == name:
            found.append(node)
    return found


def _keyword_is_true(call: ast.Call, name: str) -> bool:
    return any(
        keyword.arg == name
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _keyword_is_false(call: ast.Call, name: str) -> bool:
    return any(
        keyword.arg == name
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
        for keyword in call.keywords
    )


# --- Costing: không được chạm control Section ---------------------------


def test_forbidden_section_selectors_are_still_declared():
    """Danh sách chặn không được rút gọn âm thầm."""
    assert costing.FORBIDDEN_CONTROL_IDS == FORBIDDEN_SECTION_IDS
    assert costing.FORBIDDEN_ACTION_SELECTORS == FORBIDDEN_SECTION_SELECTORS


def test_no_automation_code_targets_a_forbidden_section_control():
    """Bốn id này chỉ được xuất hiện trong chính bộ lọc loại trừ.

    Bất kỳ literal nào khác chứa chúng nghĩa là có code đang định locate hoặc
    click vào control xoá/sửa/copy Section.
    """
    allowed_owners = {"FORBIDDEN_CONTROL_IDS", "FORBIDDEN_ACTION_SELECTORS"}
    offenders: list[str] = []
    for path in _automation_sources():
        tree = _tree(path)
        allowed_literals = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if not names & allowed_owners:
                continue
            for literal in ast.walk(node.value):
                if isinstance(literal, ast.Constant):
                    allowed_literals.add(id(literal))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str):
                continue
            if not any(item in node.value for item in FORBIDDEN_SECTION_IDS):
                continue
            if id(node) in allowed_literals:
                continue
            # Script quét DOM dùng chính các id này để LOẠI TRỪ control.
            if "forbiddenIds" in node.value:
                continue
            offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, (
        "Có code đang trỏ tới control Section bị cấm (xoá/sửa/copy Section "
        f"của Cost Sheet): {', '.join(offenders)}"
    )


# --- Download: Chrome tự quản lý file -----------------------------------


def test_downloads_never_use_playwright_save_as():
    """`download.save_as()` kéo file về artifact tạm của Playwright.

    Khi đó file thật và Chrome Download history trỏ hai nơi khác nhau, nên
    "Mở file"/"Hiện trong thư mục" của người dùng không chạy.
    """
    offenders = [
        f"{path.name}:{call.lineno}"
        for path in _automation_sources()
        for call in _calls_named(_tree(path), "save_as")
    ]
    assert not offenders, (
        "Phải dùng snapshot_downloads()/save_native_download() thay cho "
        f"save_as(): {', '.join(offenders)}"
    )


def test_download_behavior_is_only_ever_reset_to_default():
    """Chỉ được reset về `default`; `allow`/`deny`/`downloadPath` bị cấm."""
    tree = _tree(Path(runtime.__file__))
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant):
            continue
        if first.value != "Browser.setDownloadBehavior":
            continue
        checked += 1
        payload = node.args[1] if len(node.args) > 1 else None
        assert isinstance(payload, ast.Dict), (
            "setDownloadBehavior phải truyền dict literal để kiểm tra được"
        )
        options = {
            key.value: value
            for key, value in zip(payload.keys, payload.values, strict=True)
            if isinstance(key, ast.Constant)
        }
        assert "downloadPath" not in options, (
            "Không được ép downloadPath: Chrome phải tự lưu vào Known Folder "
            "Downloads theo profile."
        )
        behavior = options.get("behavior")
        assert isinstance(behavior, ast.Constant) and behavior.value == "default"
    assert checked >= 1, "AST scan không còn thấy call site nào — test đã mục"


def test_every_cdp_connection_disables_playwright_defaults():
    """Thiếu `no_defaults=True` thì Playwright ghi đè cấu hình download/context
    của Chrome thật mà người dùng đang dùng."""
    offenders = []
    checked = 0
    for path in _automation_sources():
        tree = _tree(path)
        for call in _calls_named(tree, "connect_over_cdp"):
            checked += 1
            if not _keyword_is_true(call, "no_defaults"):
                owner = _enclosing_function(tree, call)
                offenders.append(f"{path.name}:{call.lineno} ({owner})")
    assert checked >= 1, "AST scan không còn thấy call site nào — test đã mục"
    assert not offenders, (
        f"connect_over_cdp thiếu no_defaults=True: {', '.join(offenders)}"
    )


# --- Không chờ blocking khi WFX tái dùng cửa sổ -------------------------


def test_bulk_style_never_blocks_on_expect_page():
    """WFX đặt tên cửa sổ `CatalogDetail`.

    Từ dòng thứ hai trở đi `window.open` tái dùng cửa sổ đang mở nên Chromium
    không phát page event: `expect_page` sẽ ăn trọn timeout cho MỖI dòng.
    """
    offenders = [
        f"{path.name}:{call.lineno}"
        for path in _automation_sources()
        for call in _calls_named(_tree(path), "expect_page")
    ]
    assert not offenders, (
        "Phải xác nhận cửa sổ mới bằng frame scan, không dùng expect_page: "
        + ", ".join(offenders)
    )


# --- Probe chỉ đọc không được kéo Chrome lên foreground -----------------


@pytest.mark.parametrize("probe_name", sorted(READ_ONLY_PROBES))
def test_read_only_probes_never_activate_the_wfx_tab(probe_name):
    """Thay cho assert chuỗi: kiểm tra đúng ĐỐI SỐ của lời gọi kết nối.

    Chuỗi "bring_to_front=False" có thể nằm trong comment hoặc trong một lời
    gọi khác; chỉ AST mới khẳng định được chính `_connect_to_chrome` của probe
    đó đã tắt activate.
    """
    assert hasattr(session, probe_name), f"Probe đã đổi tên: {probe_name}"
    tree = _tree(Path(session.__file__))
    calls = [
        call
        for call in _calls_named(tree, "_connect_to_chrome")
        if _enclosing_function(tree, call) == probe_name
    ]
    assert calls, f"{probe_name} không còn tự kết nối Chrome — cập nhật test"
    for call in calls:
        assert _keyword_is_false(call, "bring_to_front"), (
            f"{probe_name} sẽ kéo người dùng khỏi tab đang làm "
            f"(dòng {call.lineno})"
        )


def test_real_login_is_still_allowed_to_activate_the_auth_tab():
    """Đăng nhập thật thì PHẢI đưa tab lên trước để người dùng thấy form."""
    tree = _tree(Path(session.__file__))
    calls = [
        call
        for call in _calls_named(tree, "_connect_to_chrome")
        if _enclosing_function(tree, call) == "run"
    ]
    assert calls, "session.run không còn tự kết nối Chrome — cập nhật test"
    assert not any(_keyword_is_false(call, "bring_to_front") for call in calls)


# --- Mã ranh giới trình duyệt không được nguỵ trang --------------------


def _codes_from_str_of_exception(handler: ast.ExceptHandler) -> set[str]:
    """Tên biến được gán từ chính thông điệp của exception."""
    names: set[str] = set()
    for node in ast.walk(handler):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and "str(" in ast.unparse(node.value):
            names.add(target.id)
    return names


def _returns_code_variable(handler: ast.ExceptHandler, names: set[str]) -> bool:
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        called = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if called != "_result":
            continue
        ok_node, code_node = node.args[:2]
        if not (isinstance(ok_node, ast.Constant) and ok_node.value is False):
            continue
        if isinstance(code_node, ast.Name) and code_node.id in names:
            return True
    return False


def _has_whitelist_guard(handler: ast.ExceptHandler, names: set[str]) -> bool:
    """Whitelist hợp lệ: `in {...}`, `== "CODE"`, `messages[code]`, `startswith`."""
    for node in ast.walk(handler):
        compared = (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id in names
        )
        looked_up = (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Name)
            and node.slice.id in names
        )
        prefixed = (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "startswith"
        )
        if compared or looked_up or prefixed:
            return True
    return False


def test_no_handler_turns_an_arbitrary_exception_into_an_error_code():
    """`code = str(exc)` biến mọi exception thành một "mã lỗi" tự do.

    `_active_wfx_page` báo trình duyệt đóng bằng
    ``RuntimeError("CHROME_CLOSED")``, nên nhiều handler từng gán thẳng
    ``code = str(exc)`` rồi trả về. Một exception khác — ví dụ
    "Đã kết nối Chrome nhưng không tìm thấy browser context." — trở thành mã
    lỗi là cả một câu tiếng Việt: không có trong ``ERROR_CODE_INFO`` lẫn
    ``NON_REPORTABLE_FAILURES``, telemetry nhận mã rác còn người dùng đọc sai
    nguyên nhân.

    Cách đúng: `_browser_boundary_result()`, hoặc tự whitelist mã trước khi
    dùng nó làm `code`.
    """
    offenders = []
    for path in _automation_sources():
        tree = _tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = _codes_from_str_of_exception(node)
            if not names:
                continue
            if not _returns_code_variable(node, names):
                continue
            if _has_whitelist_guard(node, names):
                continue
            offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, (
        "Handler trả mã lỗi lấy thẳng từ str(exc) mà không whitelist: "
        + ", ".join(offenders)
    )


def test_the_browser_boundary_helper_is_the_single_whitelist():
    """Whitelist chỉ được sống ở một chỗ, nếu không lại trôi ra như trước."""
    from wfx_panel.automation import _common

    assert {"CHROME_CLOSED", "NOT_LOGGED_IN"} == _common.BROWSER_BOUNDARY_CODES
    for code in _common.BROWSER_BOUNDARY_CODES:
        assert _common._browser_boundary_result(RuntimeError(code))["code"] == code
    assert _common._browser_boundary_result(RuntimeError("WFX đổi DOM")) is None
    assert _common._browser_boundary_result(ValueError("CHROME_CLOSED"))["code"] == (
        "CHROME_CLOSED"
    ), "Helper đọc thông điệp, không phụ thuộc kiểu exception"
