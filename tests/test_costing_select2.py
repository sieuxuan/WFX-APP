"""Quy tắc Select2 của WFX trong Costing.

CLAUDE.md: "Field Supplier và các editor WFX dùng Select2 có backing
``select2-hidden-accessible`` 1×1: không dùng Playwright ``select_option()`` vì
actionability có thể timeout; gán exact option value trên backing select và phát
native ``change`` để chạy nguyên onchange/xOnBlur của WFX."

Đây là ràng buộc hành vi chứ không phải ràng buộc cú pháp — `select_option()`
vẫn hợp lệ cho `<select>` thường — nên test chạy thật hàm phân nhánh thay vì
quét source.
"""

from __future__ import annotations

import pytest

from wfx_panel.automation import costing

SELECT2_CLASSES = "form-control select2-hidden-accessible custom"


class FakeEditor:
    """`<select>` của WFX; ghi lại mọi cách automation cố gán giá trị."""

    def __init__(self, classes: str, *, accepts_value: bool = True) -> None:
        self.classes = classes
        self.accepts_value = accepts_value
        self.value = ""
        self.select_option_calls: list[str] = []
        self.scripts: list[str] = []

    def get_attribute(self, name: str) -> str | None:
        return self.classes if name == "class" else None

    def select_option(self, value: str | None = None, **_kwargs) -> None:
        self.select_option_calls.append(str(value))
        self.value = str(value)

    def evaluate(self, script: str, arg=None):
        self.scripts.append(script)
        if not self.accepts_value:
            return False
        self.value = str(arg)
        return True


def test_select2_backing_select_is_driven_by_value_plus_native_change():
    editor = FakeEditor(SELECT2_CLASSES)

    costing._apply_inline_select_option(editor, "SUP-001")

    assert editor.select_option_calls == [], (
        "Select2 giấu <select> thật ở 1×1 nên actionability của Playwright sẽ "
        "timeout; phải gán value trực tiếp."
    )
    assert editor.value == "SUP-001"
    assert len(editor.scripts) == 1
    script = editor.scripts[0]
    assert "element.value = String(value)" in script
    assert "new Event('change'" in script
    assert "bubbles: true" in script, (
        "Không bubble thì onchange/xOnBlur của WFX không chạy, giá trị nhìn "
        "thấy trên UI nhưng không được ghi."
    )


def test_select2_reports_a_clear_error_when_the_option_does_not_stick():
    editor = FakeEditor(SELECT2_CLASSES, accepts_value=False)

    with pytest.raises(RuntimeError, match="COSTING_INLINE_OPTION_NOT_APPLIED"):
        costing._apply_inline_select_option(editor, "SUP-404")


def test_plain_select_still_uses_playwright_select_option():
    editor = FakeEditor("form-control")

    costing._apply_inline_select_option(editor, "USD")

    assert editor.select_option_calls == ["USD"]
    assert editor.scripts == []


def test_select2_detection_requires_the_exact_class_not_a_prefix():
    """`select2-hidden-accessible-legacy` không phải backing select."""
    editor = FakeEditor("select2-hidden-accessible-legacy")

    costing._apply_inline_select_option(editor, "USD")

    assert editor.select_option_calls == ["USD"]
