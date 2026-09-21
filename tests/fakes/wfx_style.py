"""Fake form New/Copy Style của WFX cho `wfx_panel/automation/bulk_style.py`.

Cùng nguyên tắc với ``wfx_dom``: model khai báo + router cho đúng những script
JS mà `bulk_style.py` gửi xuống, và raise ``AssertionError`` khi gặp selector
hoặc script chưa biết.

Cấu trúc bám theo WFX thật: popup Catalog Group có hai frame khác nhau —
``choice`` (nút New, form tìm Style nguồn để Copy) và ``editor`` (form Article
với ``#titlebarArticle``). Nhờ vậy vòng quét frame của `bulk_style` được chạy
thật thay vì bị rút gọn thành một frame duy nhất.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from tests.fakes.wfx_dom import FakeClock, FakeLocator, FakeNode
from wfx_panel.automation import bulk_style

NEW_STYLE_SELECTOR = f"xpath={bulk_style.NEW_STYLE_XPATH}"
COPY_SEARCH_FIELD_SELECTOR = f"xpath={bulk_style.COPY_ARTICLE_CODE_NAME_XPATH}"
COPY_SEARCH_BUTTON_SELECTOR = f"xpath={bulk_style.COPY_SEARCH_XPATH}"
COPY_COSTSHEET_SELECTOR = f"xpath={bulk_style.COPY_COSTSHEET_XPATH}"
COPY_AS_VARIANT_SELECTOR = f"xpath={bulk_style.COPY_AS_VARIANT_XPATH}"
SAVE_SELECTOR = f"xpath={bulk_style.SAVE_STYLE_XPATH}"
EDITOR_TITLE_SELECTOR = "#titlebarArticle"
EDITOR_MATERIAL_SELECTOR = "#ddlMaterialType, #select2-ddlMaterialType-container"
NEW_LINK_SELECTOR = "a.clsNavLinkNew"


class SelectField:
    """`<select>` của form Article: khớp option không phân biệt hoa/thường."""

    def __init__(self, control_id: str, options: Iterable[str]) -> None:
        self.control_id = control_id
        self.options = list(options)
        self.value = ""

    def apply(self, wanted: str) -> dict[str, Any]:
        folded = wanted.casefold().strip()
        exact = [item for item in self.options if item.casefold() == folded]
        if len(exact) != 1:
            return {
                "ok": False,
                "reason": "ambiguous-option" if exact else "option-not-found",
                "options": list(self.options[:30]),
            }
        self.value = exact[0]
        return {"ok": True, "id": self.control_id, "tag": "SELECT", "value": exact[0]}


class TextField:
    def __init__(self, control_id: str) -> None:
        self.control_id = control_id
        self.options: list[str] = []
        self.value = ""

    def apply(self, wanted: str) -> dict[str, Any]:
        self.value = wanted
        return {"ok": True, "id": self.control_id, "tag": "INPUT", "value": wanted}


class FakeStyleEditorFrame:
    """Frame form Article: `#titlebarArticle` + các dropdown Style."""

    def __init__(
        self,
        clock: FakeClock,
        fields: Mapping[str, SelectField | TextField],
        *,
        ready: bool = False,
        url: str = "https://wfx.test/wfx/WFX_ArticleEdit.aspx",
    ) -> None:
        self.clock = clock
        self.url = url
        self.ready = ready
        self.fields = dict(fields)
        self.save = FakeNode()
        self.applied: list[tuple[str, str]] = []

    # --- bề mặt Frame ---------------------------------------------------

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def _field_for(self, spec: Mapping[str, Any]):
        for control_id in spec.get("ids") or ():
            field = self.fields.get(str(control_id))
            if field is not None:
                return field
        # WFX đôi khi chỉ có label; fake tra tiếp bằng nhãn đã khai báo.
        for label in spec.get("labels") or ():
            field = self.fields.get(str(label))
            if field is not None:
                return field
        return None

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "spec.ids" in script and "ambiguous-option" in script:
            assert self.ready, "Form Article chưa mở mà đã điền field"
            field = self._field_for(arg or {})
            if field is None:
                return {"ok": False, "reason": "not-found"}
            wanted = str((arg or {}).get("value") or "").strip()
            outcome = field.apply(wanted)
            if outcome.get("ok"):
                self.applied.append((field.control_id, wanted))
            return outcome
        if "option.textContent" in script or "spec.ids" in script:
            # _READ_STYLE_OPTIONS_JS / _HYDRATE_STYLE_OPTIONS_JS
            field = self._field_for(arg or {})
            if field is None:
                return []
            return [{"label": item, "value": item} for item in field.options]
        if "resultTable" in script:
            # Bảng kết quả Copy không nằm ở frame này; Playwright thật trả rỗng
            # chứ không lỗi, nên vòng quét frame phải đi tiếp.
            return [] if "choice_index" in script else False
        raise AssertionError(f"Fake form Article chưa hỗ trợ script: {script[:140]}")

    def locator(self, selector: str) -> FakeLocator:
        if selector == EDITOR_TITLE_SELECTOR:
            return FakeLocator([FakeNode()] if self.ready else [], selector)
        if selector == EDITOR_MATERIAL_SELECTOR:
            return FakeLocator([FakeNode()] if self.ready else [], selector)
        if selector == SAVE_SELECTOR:
            return FakeLocator([self.save] if self.ready else [], selector)
        if selector in {
            NEW_STYLE_SELECTOR,
            COPY_SEARCH_FIELD_SELECTOR,
            COPY_SEARCH_BUTTON_SELECTOR,
            COPY_COSTSHEET_SELECTOR,
            COPY_AS_VARIANT_SELECTOR,
            NEW_LINK_SELECTOR,
        }:
            return FakeLocator([], selector)
        raise AssertionError(f"Fake form Article chưa hỗ trợ selector: {selector}")


class FakeStyleChoiceFrame:
    """Frame chọn New/Copy: nút New và bảng kết quả tìm Style nguồn."""

    def __init__(
        self,
        clock: FakeClock,
        editor: FakeStyleEditorFrame,
        *,
        copy_results: Iterable[Mapping[str, Any]] = (),
        copy_click_succeeds: bool = True,
        costsheet_checked: bool = False,
        url: str = "https://wfx.test/wfx/WFX_CatalogDetail.aspx",
    ) -> None:
        self.clock = clock
        self.editor = editor
        self.url = url
        self.copy_results = [dict(item) for item in copy_results]
        self.copy_click_succeeds = copy_click_succeeds
        self.clicked_copy_index: int | None = None

        self.new_button = _OpensEditor(editor)
        self.copy_search_field = FakeNode()
        self.copy_search_button = FakeNode()
        self.costsheet = FakeNode()
        self.costsheet.checked = costsheet_checked
        self.copy_as_variant = _OpensEditor(editor)

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "resultTable" in script and "choice_index" in script:
            return list(self.copy_results)
        if "resultTable" in script:
            self.clicked_copy_index = int(arg)
            return self.copy_click_succeeds
        if "typeof New !== 'function'" in script:
            return ""
        raise AssertionError(f"Fake frame chọn Style chưa hỗ trợ: {script[:140]}")

    def locator(self, selector: str) -> FakeLocator:
        mapping = {
            NEW_STYLE_SELECTOR: self.new_button,
            COPY_SEARCH_FIELD_SELECTOR: self.copy_search_field,
            COPY_SEARCH_BUTTON_SELECTOR: self.copy_search_button,
            COPY_COSTSHEET_SELECTOR: self.costsheet,
            COPY_AS_VARIANT_SELECTOR: self.copy_as_variant,
        }
        if selector in mapping:
            return FakeLocator([mapping[selector]], selector)
        if selector in {EDITOR_TITLE_SELECTOR, EDITOR_MATERIAL_SELECTOR}:
            return FakeLocator([], selector)
        if selector == NEW_LINK_SELECTOR:
            return FakeLocator([], selector)
        if selector == SAVE_SELECTOR:
            return FakeLocator([], selector)
        raise AssertionError(f"Fake frame chọn Style chưa hỗ trợ selector: {selector}")


class _OpensEditor(FakeNode):
    """Nút mở form Article: click xong thì `#titlebarArticle` mới xuất hiện."""

    def __init__(self, editor: FakeStyleEditorFrame) -> None:
        super().__init__()
        self.editor = editor

    def click(self, timeout: float | None = None) -> None:
        super().click(timeout)
        self.editor.ready = True

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "element.click()" in script:
            self.clicks += 1
            self.editor.ready = True
            return None
        return super().evaluate(script, arg)


class FakeGroupFrame:
    """Frame toolbar của Catalog Group, nơi có nút `New`."""

    def __init__(
        self,
        clock: FakeClock,
        choice: FakeStyleChoiceFrame,
        on_new_click: Callable[[], None] | None = None,
    ) -> None:
        self.clock = clock
        self.url = "https://wfx.test/wfx/WFX_CatalogBottom.aspx"
        self.choice = choice
        self.on_new_click = on_new_click
        self.new_cell = FakeNode()
        self.new_link = FakeNode()
        self.new_link.text = "New"
        self.new_link.parent = self.new_cell
        # WFX gắn onclick vào TD cha; click TD là thứ mở popup.
        self.new_cell.evaluate = self._open_popup  # type: ignore[method-assign]
        self.opened_popup = 0

    def _open_popup(self, script: str, arg: Any = None) -> Any:
        assert "element.click()" in script
        self.opened_popup += 1
        self.new_cell.clicks += 1
        if self.on_new_click is not None:
            self.on_new_click()
        return None

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> FakeLocator:
        if selector == NEW_LINK_SELECTOR:
            return FakeLocator([self.new_link], selector)
        if selector in {
            NEW_STYLE_SELECTOR,
            EDITOR_TITLE_SELECTOR,
            EDITOR_MATERIAL_SELECTOR,
            SAVE_SELECTOR,
            COPY_AS_VARIANT_SELECTOR,
        }:
            return FakeLocator([], selector)
        raise AssertionError(f"Fake frame Group chưa hỗ trợ selector: {selector}")

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "typeof New !== 'function'" in script:
            return ""
        if "resultTable" in script:
            return [] if "choice_index" in script else False
        raise AssertionError(f"Fake frame Group chưa hỗ trợ: {script[:140]}")


class FakeStylePage:
    def __init__(self, clock: FakeClock, frames: list[Any]) -> None:
        self.clock = clock
        self.frames = frames
        self.bring_to_front_calls = 0
        self.closed = False

    def bring_to_front(self) -> None:
        self.bring_to_front_calls += 1

    def close(self, run_before_unload: bool = True) -> None:
        self.closed = True

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)


class FakeStyleContext:
    def __init__(self, pages: list[FakeStylePage]) -> None:
        self.pages = pages
        self.new_pages = 0

    def new_page(self) -> FakeStylePage:  # pragma: no cover - nhánh fallback
        self.new_pages += 1
        raise PlaywrightError("Fake không dựng popup fallback")


DEFAULT_FIELDS: dict[str, list[str]] = {
    "ddlMaterialType": ["Apparel", "Fabric"],
    "ddlBuyer": ["J.LINDEBERG", "TRUEWERK"],
    "ddlDivision": ["PSHK", "PSVN"],
    "ddlProductGroup": ["Jacket", "Trouser"],
    "ddlProductSubCat": ["Padded", "Shell"],
    "ddlColorCard": ["Main", "Sample"],
    "ddlSizeWidthRange": ["XS-XXL", "S-XL"],
    "ddlSeason": ["SS27", "FW26"],
    "ddlStorageUOM": ["Pcs", "Set"],
    "ddlPricePer": ["Article", "Color"],
    "ddlColorDefinition": ["Single Colors", "Multi Colors"],
}
DEFAULT_TEXT_FIELDS = ("txtBuyerStyleRef", "txtInternalStyleRef")


def build_style_fields(
    overrides: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, SelectField | TextField]:
    options = {key: list(value) for key, value in DEFAULT_FIELDS.items()}
    for key, value in (overrides or {}).items():
        options[key] = list(value)
    fields: dict[str, SelectField | TextField] = {
        key: SelectField(key, value) for key, value in options.items()
    }
    for key in DEFAULT_TEXT_FIELDS:
        fields[key] = TextField(key)
    return fields


class StyleWorld:
    """Toàn bộ context giả cho một lượt chuẩn bị Style."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        fields: Mapping[str, SelectField | TextField] | None = None,
        copy_results: Iterable[Mapping[str, Any]] = (),
        copy_click_succeeds: bool = True,
        costsheet_checked: bool = False,
    ) -> None:
        self.clock = clock
        self.editor = FakeStyleEditorFrame(clock, fields or build_style_fields())
        self.choice = FakeStyleChoiceFrame(
            clock,
            self.editor,
            copy_results=copy_results,
            copy_click_succeeds=copy_click_succeeds,
            costsheet_checked=costsheet_checked,
        )
        self.group = FakeGroupFrame(clock, self.choice, self._open_popup_page)
        self.group_page = FakeStylePage(clock, [self.group])
        self.popup_page = FakeStylePage(clock, [self.choice, self.editor])
        # Giống WFX thật: popup Catalog Group chỉ xuất hiện SAU khi click New.
        # Nhờ vậy snapshot `known_pages` của lượt quét mới có ý nghĩa.
        self.context = FakeStyleContext([self.group_page])
        self.browser = _FakeBrowser(self.context)
        # Giao thức chung với `tests/fakes/automation_boundary.WfxWorld`.
        self.driver_starts = 0
        self.driver_stops = 0
        self.dialog_logs: list[Any] = []

    @property
    def page(self) -> FakeStylePage:
        """Tab WFX chính mà entry point nhận được."""
        return self.group_page

    def _open_popup_page(self) -> None:
        if self.popup_page not in self.context.pages:
            self.context.pages.append(self.popup_page)

    def open_style_form(self) -> None:
        """Đưa world về trạng thái form Article đã mở sẵn trên WFX."""
        self._open_popup_page()
        self.editor.ready = True

    @property
    def save_clicks(self) -> int:
        return self.editor.save.clicks

    def applied_value(self, control_id: str) -> str:
        field = self.editor.fields[control_id]
        return field.value


class _FakeBrowser:
    def __init__(self, context: FakeStyleContext) -> None:
        self.contexts = [context]
