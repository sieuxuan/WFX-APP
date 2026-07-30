"""Hợp đồng: yêu cầu Stop phải xuyên qua mọi workflow automation.

``AutomationCancelled`` kế thừa ``BaseException`` chứ không phải ``Exception``,
vì mọi workflow đều kết thúc bằng ``except Exception as exc`` để đổi lỗi kỹ
thuật thành mã nghiệp vụ. Nếu ai đó viết ``except BaseException`` (hoặc
``except:`` trần) mà không re-raise, yêu cầu Stop lại bị nuốt y như bug cũ:
người dùng nhận LOGIN_FAILED/CATALOG_SEARCH_FAILED thay vì ACTION_CANCELLED, và
vì các mã đó nằm ngoài NON_REPORTABLE_FAILURES nên telemetry gửi một lỗi không
tồn tại ra webhook production.

Test quét source thay vì chạy từng flow: đây là ràng buộc tĩnh trên toàn bộ lớp
automation, không thể phủ hết bằng test hành vi.
"""

from __future__ import annotations

import ast
from pathlib import Path

from wfx_panel.automation import runtime

AUTOMATION_DIR = Path(runtime.__file__).resolve().parent
# Chỉ runtime.AutomationRuntime._worker được phép bắt BaseException: nó là nơi
# chuyển exception của task về cho caller, và nó KHÔNG nuốt (gán vào task.error
# rồi execute() raise lại).
ALLOWED_BASE_HANDLERS = {("runtime.py", "_worker")}


def _automation_sources() -> list[Path]:
    return sorted(
        path
        for path in AUTOMATION_DIR.glob("*.py")
        if path.name != "__init__.py"
    )


def _enclosing_function(tree: ast.Module, node: ast.ExceptHandler) -> str:
    best = "<module>"
    for candidate in ast.walk(tree):
        if not isinstance(
            candidate, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        end = candidate.end_lineno or candidate.lineno
        if candidate.lineno <= node.lineno <= end:
            best = candidate.name
    return best


def _handler_reraises(handler: ast.ExceptHandler) -> bool:
    return any(
        isinstance(node, ast.Raise) for node in ast.walk(handler)
    )


def _catches_base_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:  # except: trần
        return True
    caught = (
        handler.type.elts
        if isinstance(handler.type, ast.Tuple)
        else [handler.type]
    )
    return any(
        isinstance(node, ast.Name) and node.id == "BaseException"
        for node in caught
    )


def test_automation_never_swallows_base_exception():
    offenders: list[str] = []
    for path in _automation_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not _catches_base_exception(node):
                continue
            function = _enclosing_function(tree, node)
            if (path.name, function) in ALLOWED_BASE_HANDLERS:
                continue
            if _handler_reraises(node):
                continue
            offenders.append(f"{path.name}:{node.lineno} trong {function}()")

    assert not offenders, (
        "Handler bắt BaseException mà không re-raise sẽ nuốt yêu cầu Stop và "
        "làm telemetry gửi lỗi giả: " + ", ".join(offenders)
    )


def test_cancellation_is_not_an_exception_subclass():
    # Nếu ai đó đổi lại thành Exception/RuntimeError, 40 handler `except
    # Exception` trong lớp automation lập tức nuốt Stop trở lại.
    assert issubclass(runtime.AutomationCancelled, BaseException)
    assert not issubclass(runtime.AutomationCancelled, Exception)


def test_panel_api_handles_cancellation_before_generic_exception():
    """Thứ tự handler trong _run_unlocked quyết định mã trả về: nếu `except
    Exception` đứng trước, cancel sẽ thành PANEL_ERROR và bị gửi telemetry."""
    from wfx_panel import panel_api

    tree = ast.parse(Path(panel_api.__file__).read_text(encoding="utf-8"))
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_run_unlocked"
    )
    handler_names = [
        getattr(handler.type, "id", None)
        for block in ast.walk(target)
        if isinstance(block, ast.Try)
        for handler in block.handlers
    ]
    assert "AutomationCancelled" in handler_names
    assert handler_names.index("AutomationCancelled") < handler_names.index(
        "Exception"
    )
