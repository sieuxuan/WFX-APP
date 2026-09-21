"""Tiêu chí nghiệm thu của workspace `Tạo Style` (Apparel).

Mỗi test chạy thật `bulk_style.prepare_catalog_style_row` trên form WFX giả
(`tests/fakes/wfx_style.py`). Đây là flow ghi dữ liệu thật lên WFX và
``Create``/``Save`` không idempotent, nên các ràng buộc dưới đây đều có hậu quả
trực tiếp: Save nhầm sinh Style trùng, tự chọn Style nguồn sai sinh Copy sai.
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import wire_automation
from tests.fakes.wfx_dom import install_fake_clock
from tests.fakes.wfx_style import StyleWorld, build_style_fields
from wfx_panel.automation import bulk_style, runtime

VALID_NEW_ROW = {
    "type": "New",
    "material_type": "Apparel",
    "buyer": "J.LINDEBERG",
    "division": "PSHK",
    "product_group": "Jacket",
    "sub_category": "Padded",
    "color_card": "Main",
    "size_range": "XS-XXL",
    "season": "SS27",
    "buyer_style_ref": "JL-1001",
    "internal_style_ref": "INT-1001",
    "source_row": 4,
}

COPY_ROW = {
    "type": "Copy",
    "style_copy": "SWN0000001",
    "buyer": "J.LINDEBERG",
    "season": "FW26",
    "source_row": 7,
}


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, bulk_style)


@pytest.fixture
def world(clock):
    return StyleWorld(clock)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _wire(
    monkeypatch,
    world: StyleWorld,
    *,
    folder_kind: str = "group",
    **boundary,
) -> None:
    """Chỉ giả lập ranh giới ngoài module: folder + Playwright/trang WFX."""
    monkeypatch.setattr(
        bulk_style,
        "open_catalog_folder",
        lambda *_args, **_kwargs: {
            "ok": True,
            "code": "CATALOG_FOLDER_OPENED",
            "folder": {"kind": folder_kind, "id": "42"},
        },
    )
    wire_automation(monkeypatch, bulk_style, world, **boundary)


def _prepare(world: StyleWorld, row: dict, **kwargs) -> dict:
    _lines, log = _logs()
    return bulk_style.prepare_catalog_style_row(
        "01",
        kwargs.pop("group_id", "42"),
        row,
        log=log,
        **kwargs,
    )


# --- Toggle Tự động Save ------------------------------------------------


def test_auto_save_off_stops_before_save(monkeypatch, world):
    """Mặc định phải dừng trước Save để người dùng tự kiểm tra."""
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["code"] == "STYLE_FORM_READY"
    assert result["saved"] is False
    assert result["requires_manual_save"] is True
    assert world.save_clicks == 0, "Save khi user chưa bật toggle là tạo Style ngoài ý muốn"
    assert "tự bấm Save" in result["message"]


def test_auto_save_on_clicks_save_exactly_once(monkeypatch, world):
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW), auto_save=True)

    assert result["code"] == "STYLE_FORM_READY"
    assert result["saved"] is True
    assert result["requires_manual_save"] is False
    assert world.save_clicks == 1, "Save hai lần có thể sinh Style trùng"


def test_save_is_never_interrupted_by_a_stop_request(monkeypatch, world):
    """Stop đúng lúc đang Save: WFX đã ghi nhưng user tưởng là chưa.

    `_save_style` bọc click + chờ trong `cancellation_deferred()` nên checkpoint
    không được ném ACTION_CANCELLED giữa chừng.
    """
    _wire(monkeypatch, world)
    _lines, log = _logs()
    # Mở sẵn form Article rồi mới bật cờ huỷ, đúng thời điểm nguy hiểm.
    world.open_style_form()
    runtime.RUNTIME._cancel.set()
    try:
        bulk_style._save_style(world.context, log)
    finally:
        runtime.RUNTIME._cancel.clear()

    assert world.save_clicks == 1


def test_stop_outside_the_save_window_still_cancels(monkeypatch, world):
    """Đối chứng: ngoài vùng deferred, Stop vẫn phải dừng được flow."""
    _wire(monkeypatch, world)
    runtime.RUNTIME._cancel.set()
    try:
        with pytest.raises(runtime.AutomationCancelled):
            runtime.checkpoint()
    finally:
        runtime.RUNTIME._cancel.clear()


# --- Ba field cố định ---------------------------------------------------


def test_fixed_fields_are_always_applied(monkeypatch, world):
    """Purchase UOM=Pcs, Price Per=Article, Color Definition=Single Colors."""
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert world.applied_value("ddlStorageUOM") == "Pcs"
    assert world.applied_value("ddlPricePer") == "Article"
    assert world.applied_value("ddlColorDefinition") == "Single Colors"
    for label in ("Purchase UOM", "Price Per", "Color Definition"):
        assert label in result["filled_fields"]


def test_row_values_reach_the_matching_wfx_controls(monkeypatch, world):
    _wire(monkeypatch, world)

    _prepare(world, dict(VALID_NEW_ROW))

    assert world.applied_value("ddlBuyer") == "J.LINDEBERG"
    assert world.applied_value("ddlSeason") == "SS27"
    assert world.applied_value("txtBuyerStyleRef") == "JL-1001"
    assert world.applied_value("txtInternalStyleRef") == "INT-1001"


def test_missing_option_names_the_field_instead_of_failing_at_save(
    monkeypatch,
    clock,
):
    world = StyleWorld(clock, fields=build_style_fields({"ddlSeason": ["FW26"]}))
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_FIELD_NOT_AVAILABLE"
    assert "Season" in result["message"]
    assert world.save_clicks == 0


# --- Dòng New thiếu dữ liệu --------------------------------------------


def test_new_row_missing_a_required_field_is_rejected(monkeypatch, world):
    _wire(monkeypatch, world)
    row = dict(VALID_NEW_ROW)
    row["division"] = ""

    result = _prepare(world, row)

    assert result["ok"] is False
    assert result["code"] == "STYLE_REQUIRED_FIELD_MISSING"
    assert "Division" in result["message"]
    assert world.save_clicks == 0


def test_copy_row_may_leave_fields_empty(monkeypatch, world):
    """Copy kế thừa từ Style nguồn nên không bắt buộc đủ field như New."""
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "SWN0000001"}
    ]

    result = _prepare(world, dict(COPY_ROW))

    assert result["code"] == "STYLE_FORM_READY"
    assert result["style_type"] == "Copy"
    assert world.applied_value("ddlBuyer") == "J.LINDEBERG"


# --- Chọn Style nguồn ---------------------------------------------------


def test_copy_searches_by_article_code_or_name_not_buyer_reference(
    monkeypatch,
    world,
):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "SWN0000001"}
    ]

    _prepare(world, dict(COPY_ROW))

    assert world.choice.copy_search_field.fills == ["SWN0000001"]
    assert world.choice.copy_search_button.clicks == 1


def test_a_single_source_style_is_selected_automatically(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 3, "article_code": "SWN0000001", "label": "SWN0000001"}
    ]

    result = _prepare(world, dict(COPY_ROW))

    assert result["code"] == "STYLE_FORM_READY"
    assert world.choice.clicked_copy_index == 3


def test_multiple_source_styles_stop_for_the_user_to_choose(monkeypatch, world):
    """Không được tự chọn dòng đầu: Copy sai Style là tạo nhầm dữ liệu."""
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"},
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"},
    ]

    result = _prepare(world, dict(COPY_ROW))

    assert result["ok"] is True
    assert result["code"] == "STYLE_COPY_MULTIPLE_RESULTS"
    assert len(result["choices"]) == 2
    assert result["source_row"] == 7
    assert world.choice.clicked_copy_index is None
    assert world.save_clicks == 0


def test_user_choice_is_honoured_and_validated(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"},
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"},
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=1)

    assert result["code"] == "STYLE_FORM_READY"
    assert world.choice.clicked_copy_index == 1


def test_a_choice_outside_the_current_result_set_is_refused(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"},
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"},
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=9)

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_CHOICE_INVALID"
    assert world.choice.clicked_copy_index is None


def test_a_single_result_currently_overrides_an_explicit_user_choice(
    monkeypatch,
    world,
):
    """Ghi lại hành vi HIỆN TẠI, kèm rủi ro đã biết.

    `_prepare_copy` bỏ qua `copy_choice` khi chỉ còn đúng một kết quả. Nếu giữa
    lượt `STYLE_COPY_MULTIPLE_RESULTS` và lượt xác nhận, dữ liệu WFX đổi khiến
    tập kết quả co lại còn một dòng KHÁC dòng người dùng đã chọn, flow vẫn Copy
    dòng đó mà không báo `STYLE_COPY_CHOICE_INVALID`.

    Test này cố tình khẳng định hiện trạng để thay đổi hành vi phải là một
    quyết định có ý thức, không phải hồi quy âm thầm.
    """
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 5, "article_code": "SWN0000009", "label": "Style khác"}
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=1)

    assert result["code"] == "STYLE_FORM_READY"
    assert world.choice.clicked_copy_index == 5


def test_no_source_style_found_is_reported(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = []

    result = _prepare(world, dict(COPY_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_NOT_FOUND"


def test_source_row_detached_before_the_click_is_reported(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"}
    ]
    world.choice.copy_click_succeeds = False

    result = _prepare(world, dict(COPY_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_RESULT_DETACHED"


# --- CostSheet + Copy as Variant ---------------------------------------


def test_copy_always_selects_costsheet_and_copy_as_variant(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"}
    ]

    _prepare(world, dict(COPY_ROW))

    assert world.choice.costsheet.is_checked() is True
    assert world.choice.copy_as_variant.clicks == 1


def test_costsheet_already_ticked_is_not_toggled_off(monkeypatch, clock):
    world = StyleWorld(clock, costsheet_checked=True)
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"}
    ]

    _prepare(world, dict(COPY_ROW))

    assert world.choice.costsheet.is_checked() is True
    assert world.choice.costsheet.check_calls == 0, (
        "Tick lại checkbox đang bật sẽ bỏ chọn CostSheet"
    )


# --- Điều kiện vào flow -------------------------------------------------


def test_a_folder_that_is_not_a_group_never_touches_chrome(monkeypatch, world):
    _wire(monkeypatch, world, folder_kind="folder")

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_GROUP_REQUIRED"
    assert world.group.opened_popup == 0
    assert world.save_clicks == 0


def test_a_non_numeric_group_id_is_rejected_before_opening_the_folder(
    monkeypatch,
    world,
):
    opened: list[str] = []
    monkeypatch.setattr(
        bulk_style,
        "open_catalog_folder",
        lambda *args, **_kwargs: opened.append(str(args)) or {"ok": True},
    )

    result = _prepare(world, dict(VALID_NEW_ROW), group_id="chưa chọn")

    assert result["code"] == "STYLE_GROUP_REQUIRED"
    assert opened == []


@pytest.mark.parametrize("kind", ["", "revise", "NEW STYLE"])
def test_only_new_or_copy_are_accepted(monkeypatch, world, kind):
    _wire(monkeypatch, world)
    row = dict(VALID_NEW_ROW)
    row["type"] = kind

    result = _prepare(world, row)

    assert result["ok"] is False
    assert result["code"] == "STYLE_TYPE_INVALID"


def test_a_failing_folder_open_is_returned_unchanged(monkeypatch, world):
    monkeypatch.setattr(
        bulk_style,
        "open_catalog_folder",
        lambda *_args, **_kwargs: {
            "ok": False,
            "code": "CATALOG_FOLDER_STALE",
            "message": "Cây thư mục đã đổi.",
        },
    )

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["code"] == "CATALOG_FOLDER_STALE"


# --- Một lượt chỉ chuẩn bị một dòng -------------------------------------


def test_one_call_prepares_exactly_one_row_and_returns_to_the_user(
    monkeypatch,
    world,
):
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["source_row"] == 4
    assert world.group.opened_popup == 1, "Mỗi lượt chỉ được mở New đúng một lần"
    assert world.group_page.bring_to_front_calls == 1, (
        "Phải đưa WFX lên trước để người dùng kiểm tra dòng vừa chuẩn bị"
    )


# --- Lượt quét dropdown -------------------------------------------------


def _scan(world: StyleWorld, group_id: str = "42") -> dict:
    _lines, log = _logs()
    return bulk_style.scan_catalog_style_options("01", group_id, log=log)


def test_option_scan_never_saves_and_cleans_up_its_own_popup(monkeypatch, world):
    """Lượt quét chỉ đọc option; form New Style điền dở không được để lại."""
    _wire(monkeypatch, world)

    result = _scan(world)

    assert result["code"] == "STYLE_OPTIONS_SCANNED"
    assert world.save_clicks == 0, "Lượt quét tuyệt đối không được Save"
    assert world.popup_page.closed is True, (
        "Form New Style điền dở là rác do chính lượt quét tạo ra"
    )
    assert world.group_page.closed is False, "Không được đụng tab của người dùng"


def test_option_scan_returns_options_for_every_required_field(monkeypatch, world):
    _wire(monkeypatch, world)

    result = _scan(world)

    fields = result["fields"]
    assert [item["label"] for item in fields["buyer"]] == [
        "J.LINDEBERG",
        "TRUEWERK",
    ]
    assert [item["label"] for item in fields["season"]] == ["SS27", "FW26"]
    assert result["subcategories_by_product_group"], (
        "Sub-Category phụ thuộc Product Group nên phải quét theo từng nhóm"
    )


def test_option_scan_still_cleans_up_when_the_scan_fails(monkeypatch, clock):
    """Kể cả khi lỗi hoặc bị Stop, popup của lượt quét vẫn phải bị đóng."""
    world = StyleWorld(clock, fields=build_style_fields({"ddlSeason": []}))
    _wire(monkeypatch, world)

    result = _scan(world)

    assert result["ok"] is False
    assert result["code"] == "STYLE_OPTIONS_SCAN_FAILED"
    assert "Season" in result["message"]
    assert world.popup_page.closed is True


def test_option_scan_refuses_a_node_that_is_not_a_group(monkeypatch, world):
    _wire(monkeypatch, world, folder_kind="folder")

    result = _scan(world)

    assert result["ok"] is False
    assert result["code"] == "STYLE_GROUP_REQUIRED"
    assert world.group.opened_popup == 0


# --- Ranh giới trình duyệt / phiên đăng nhập ----------------------------


def test_playwright_driver_is_always_released(monkeypatch, world):
    _wire(monkeypatch, world)

    _prepare(world, dict(VALID_NEW_ROW))

    assert world.driver_stops == 1, "Giữ driver sau flow là rò rỉ Playwright"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: bulk_style nuốt CHROME_CLOSED thành STYLE_PREPARE_FAILED nên "
        "PanelAPI._run_action_with_auto_relogin không tự mở lại trình duyệt, "
        "và vì STYLE_PREPARE_FAILED là mã reportable nên telemetry còn gửi "
        "webhook cho một tình huống chỉ là 'Chrome đã đóng'. oc/grn/dispatch/"
        "directory/sale_asn_create đều đã map đúng."
    ),
)
def test_chrome_closed_is_reported_so_the_app_can_reopen_the_browser(
    monkeypatch,
    world,
):
    _wire(monkeypatch, world, chrome_ready=False)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["code"] == "CHROME_CLOSED"


@pytest.mark.xfail(
    strict=True,
    reason="BUG: cùng nguyên nhân — NOT_LOGGED_IN bị nuốt, app không tự đăng nhập lại.",
)
def test_expired_session_is_reported_so_the_app_can_log_in_again(
    monkeypatch,
    world,
):
    _wire(monkeypatch, world, logged_in=False)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["code"] == "NOT_LOGGED_IN"


def test_option_scan_also_swallows_the_browser_boundary_codes(
    monkeypatch,
    world,
):
    """Ghi lại hiện trạng của lượt quét: cùng một lỗi map mã."""
    _wire(monkeypatch, world, chrome_ready=False)

    result = _scan(world)

    assert result["code"] == "STYLE_OPTIONS_SCAN_FAILED"
    assert world.driver_stops == 1
