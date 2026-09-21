"""Tạo Style hàng loạt khi WFX hoặc cây folder không hợp tác.

CLAUDE.md: user phải quét/chọn một node đúng loại Group rồi mới Import form
XLSX; lượt quét để lại một form New Style điền dở nên phải đóng đúng những
popup chính nó mở, kể cả khi lỗi hoặc bị Stop.
"""

from __future__ import annotations

from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_style import StyleWorld, build_style_fields
from tests.test_bulk_style import (  # noqa: F401
    VALID_NEW_ROW,
    _logs,
    _wire,
    clock,
    world,
)
from wfx_panel.automation import bulk_style
from wfx_panel.automation._common import PlaywrightTimeoutError


def _scan(world, group_id="42"):  # noqa: F811
    _lines, log = _logs()
    return bulk_style.scan_catalog_style_options("01", group_id, log=log)


def _prepare(world, **kwargs):  # noqa: F811
    _lines, log = _logs()
    return bulk_style.prepare_catalog_style_row(
        "01", "42", dict(VALID_NEW_ROW), log=log, **kwargs
    )


# --- cây folder ----------------------------------------------------------


def test_a_folder_that_cannot_be_opened_stops_the_scan(monkeypatch, world):  # noqa: F811
    patch_automation(
        monkeypatch,
        bulk_style,
        "open_catalog_folder",
        lambda *_args, **_kwargs: {
            "ok": False,
            "code": "CATALOG_FOLDER_STALE",
            "message": "Folder không còn tồn tại.",
        },
    )

    assert _scan(world)["code"] == "CATALOG_FOLDER_STALE"


def test_a_node_that_is_not_a_group_is_refused(monkeypatch, world):  # noqa: F811
    _wire(monkeypatch, world, folder_kind="folder")

    assert _scan(world)["code"] == "STYLE_GROUP_REQUIRED"


# --- WFX trả về form thiếu dữ liệu ---------------------------------------


def test_material_type_falls_back_to_the_two_values_wfx_always_has(
    monkeypatch, clock  # noqa: F811
):
    # Select vẫn nhận KNIT/WOVEN, chỉ là WFX chưa bind option lúc form mở.
    scanned = StyleWorld(
        clock, fields=build_style_fields({"ddlMaterialType": ["KNIT", "WOVEN"]})
    )
    _wire(monkeypatch, scanned)
    real_read = bulk_style._read_style_options

    def blank_material(editor, ids):
        # WFX đôi khi chưa bind option Material Type lúc form vừa mở.
        return [] if "ddlMaterialType" in ids else real_read(editor, ids)

    patch_automation(
        monkeypatch, bulk_style, "_read_style_options", blank_material
    )

    result = _scan(scanned)

    assert result["code"] == "STYLE_OPTIONS_SCANNED"
    assert [
        option["label"] for option in result["fields"]["material_type"]
    ] == ["KNIT", "WOVEN"]


def test_a_product_group_whose_sub_categories_will_not_load_is_skipped(
    monkeypatch, world  # noqa: F811
):
    _wire(monkeypatch, world)
    real_options = bulk_style._field_options_with_wait

    def refuse(context, ids, *args, **kwargs):
        if "ddlProductSubCat" in ids:
            raise PlaywrightTimeoutError("Sub-Category chưa nạp")
        return real_options(context, ids, *args, **kwargs)

    patch_automation(
        monkeypatch, bulk_style, "_field_options_with_wait", refuse
    )

    result = _scan(world)

    assert result["code"] == "STYLE_OPTIONS_SCANNED"
    assert result["subcategories_by_product_group"] == {}


def test_an_unexpected_failure_during_the_scan_is_a_technical_error(
    monkeypatch, world  # noqa: F811
):
    _wire(monkeypatch, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX trả về HTML lạ")

    patch_automation(monkeypatch, bulk_style, "_style_editor_frame", boom)

    result = _scan(world)

    assert result["code"] == "STYLE_OPTIONS_SCAN_FAILED"
    assert "ValueError" in result["message"]


# --- chuẩn bị một dòng ---------------------------------------------------


def test_a_form_that_never_becomes_ready_is_reported_as_such(
    monkeypatch, world  # noqa: F811
):
    _wire(monkeypatch, world)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Form New Style chưa mở")

    patch_automation(monkeypatch, bulk_style, "_style_editor_frame", slow)

    result = _prepare(world)

    assert result["code"] == "STYLE_FORM_NOT_READY"
    assert "chưa sẵn sàng" in result["message"]


def test_an_unexpected_failure_while_preparing_a_row_is_a_technical_error(
    monkeypatch, world  # noqa: F811
):
    _wire(monkeypatch, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX trả về HTML lạ")

    patch_automation(monkeypatch, bulk_style, "_style_editor_frame", boom)

    result = _prepare(world)

    assert result["code"] == "STYLE_PREPARE_FAILED"
    assert "ValueError" in result["message"]


def test_a_runtime_failure_without_a_known_code_still_names_the_cause(
    monkeypatch, world  # noqa: F811
):
    _wire(monkeypatch, world)

    def boom(*_args, **_kwargs):
        raise RuntimeError("WFX_KHONG_CO_MA_NAY")

    patch_automation(monkeypatch, bulk_style, "_style_editor_frame", boom)

    result = _prepare(world)

    assert result["code"] == "STYLE_PREPARE_FAILED"
    assert "WFX_KHONG_CO_MA_NAY" in result["message"]
