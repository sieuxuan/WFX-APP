"""DOM Costing giả cho các bộ lọc chạy trong trình duyệt.

`costing.py` gom `is_visible()`/`is_enabled()`/`get_attribute()` của từng
control vào một `evaluate_all` duy nhất để bớt lượt gọi CDP. Fake này **không**
chạy JavaScript; nó nhận diện đúng từng script theo hằng số trong `costing.py`
rồi tính lại cùng ngữ nghĩa từ thuộc tính khai báo của mỗi control
(`visible`/`enabled`/`dom_id`/`input_type`/…).

Nhờ đó test khoá được *hợp đồng* của bộ lọc — control ẩn, control disabled,
`type` bị chặn, id trùng, option khớp exact — độc lập với cách viết JS. Giới hạn
phải nói rõ: fake chứng minh phần Python và ngữ nghĩa lọc, **không** chứng minh
đoạn JS chạy đúng trong Chrome thật.

Gặp script chưa khai báo thì raise ``AssertionError``, không im lặng trả rỗng.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from tests.fakes.wfx_dom import FakeLocator, FakeNode
from wfx_panel.automation import costing

BLOCKED_INPUT_TYPES = frozenset(
    {"hidden", "checkbox", "radio", "file", "button", "submit"}
)


class Control(FakeNode):
    """Một control WFX với đúng những thuộc tính mà bộ lọc đọc tới."""

    def __init__(
        self,
        *,
        dom_id: str = "",
        name: str = "",
        tag: str = "input",
        input_type: str = "",
        css_class: str = "",
        visible: bool = True,
        enabled: bool = True,
        connected: bool = True,
        options: Sequence[tuple[str, str]] = (),
        value: str = "",
    ) -> None:
        super().__init__(visible=visible, enabled=enabled, value=value)
        self.dom_id = dom_id
        self.name = name
        self.tag = tag
        self.input_type = input_type
        self.css_class = css_class
        self.connected = connected
        self.options = [(str(label), str(val)) for label, val in options]
        self.selected: list[str] = []
        self.change_events = 0

    # --- bề mặt Playwright dùng sau khi đã resolve ----------------------

    def get_attribute(self, name: str) -> str | None:
        self._guard()
        return {
            "id": self.dom_id or None,
            "name": self.name or None,
            "type": self.input_type or None,
            "class": self.css_class or None,
        }.get(name)

    def select_option(self, value: str | None = None, **_kwargs: Any) -> None:
        self._guard()
        self.selected.append(str(value))

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self._guard()
        if "dispatchEvent(new Event('change'" in script:
            # Backing select 1×1 của Select2: gán value rồi phát change.
            if str(arg) not in {value for _label, value in self.options}:
                return False
            self.value = str(arg)
            self.selected.append(str(arg))
            self.change_events += 1
            return True
        return super().evaluate(script, arg)

    # --- ngữ nghĩa mà đoạn JS tính ra -----------------------------------

    @property
    def usable(self) -> bool:
        """Tương đương `is_visible() and is_enabled()`."""
        return self.connected and self.visible and self.enabled

    @property
    def shown(self) -> bool:
        """Tương đương `is_visible()`."""
        return self.connected and self.visible


class ControlHandle(FakeLocator):
    """Handle của đúng một control; cho phép đi tiếp xuống `option`."""

    def locator(self, selector: str) -> Any:
        if selector == "option":
            return OptionLocator(self._node)
        return super().locator(selector)

    def select_option(self, value: str | None = None, **kwargs: Any) -> None:
        self._node.select_option(value, **kwargs)


class ControlLocator:
    """Locator biết trả lời đúng những `evaluate_all` của `costing.py`."""

    def __init__(self, controls: Sequence[Control], selector: str) -> None:
        self.controls = list(controls)
        self.selector = selector
        self.evaluate_all_calls = 0
        self.detached = False

    def nth(self, index: int) -> ControlHandle:
        return ControlHandle([self.controls[index]], f"{self.selector}[{index}]")

    @property
    def first(self) -> ControlHandle:
        return self.nth(0)

    def count(self) -> int:
        raise AssertionError(
            f"{self.selector}: lọc từng phần tử bằng count()/nth() tốn một lượt "
            "gọi CDP mỗi node — dùng evaluate_all một lượt"
        )

    def evaluate_all(self, script: str, arg: Any = None) -> list[Any]:
        self.evaluate_all_calls += 1
        if self.detached:
            raise PlaywrightError("Execution context was destroyed")
        if script == costing._USABLE_CONTROL_JS:
            return [
                index
                for index, control in enumerate(self.controls)
                if control.usable
            ]
        if script == costing._VISIBLE_JS:
            return [
                index
                for index, control in enumerate(self.controls)
                if control.shown
            ]
        if script == costing._VISIBLE_WITH_ID_JS:
            return [
                index
                for index, control in enumerate(self.controls)
                if control.dom_id == str(arg) and control.shown
            ]
        if script == costing._INLINE_EDITOR_JS:
            return self._inline_editors(str(arg or "").lower())
        if script == costing._MATCHING_OPTION_VALUES_JS:
            return self._matching_options(str(arg or ""))
        raise AssertionError(f"Fake Costing chưa hỗ trợ script: {script[:120]}")

    def _inline_editors(self, suffix: str) -> list[dict[str, Any]]:
        editors: list[dict[str, Any]] = []
        for index, control in enumerate(self.controls):
            if not control.usable:
                continue
            if control.input_type.lower() in BLOCKED_INPUT_TYPES:
                continue
            identity = f"{control.dom_id} {control.name}".lower()
            editors.append(
                {
                    "index": index,
                    "tag": control.tag,
                    "matches_suffix": bool(suffix) and suffix in identity,
                }
            )
        return editors

    def _matching_options(self, wanted: str) -> list[str]:
        raise AssertionError(
            f"{self.selector} không phải danh sách option của một select"
        )


class OptionLocator(ControlLocator):
    """`editor.locator('option')` của đúng một select."""

    def __init__(self, control: Control) -> None:
        super().__init__([], f"{control.dom_id or 'select'} > option")
        self.control = control

    def _matching_options(self, wanted: str) -> list[str]:
        return [
            value
            for label, value in self.control.options
            if wanted in {label.strip().lower(), value.strip().lower()}
        ]


class ControlFrame:
    """Frame chỉ phục vụ các hàm lọc control của `costing.py`."""

    def __init__(
        self,
        clock: Any,
        controls: Sequence[Control] = (),
        *,
        selectors: dict[str, Sequence[Control]] | None = None,
    ) -> None:
        self.clock = clock
        self.selectors: dict[str, list[Control]] = {
            key: list(value) for key, value in (selectors or {}).items()
        }
        if controls:
            self.selectors.setdefault("input,select,textarea", list(controls))
        self.locators: list[ControlLocator] = []

    def locator(self, selector: str) -> ControlLocator:
        if selector in self.selectors:
            controls = self.selectors[selector]
        elif selector.startswith('[id="') and selector.endswith('"]'):
            # WFX lặp cùng id trên nhiều dòng; selector trả về mọi node trùng.
            dom_id = selector[5:-2]
            controls = [
                control
                for pool in self.selectors.values()
                for control in pool
                if control.dom_id == dom_id
            ]
        else:
            raise AssertionError(f"ControlFrame chưa khai báo: {selector}")
        locator = ControlLocator(controls, selector)
        self.locators.append(locator)
        return locator

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)
