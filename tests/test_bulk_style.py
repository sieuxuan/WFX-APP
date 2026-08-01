import inspect
from pathlib import Path

from wfx_panel.automation import bulk_style


def test_copy_search_rule_uses_article_code_for_swn_and_skn():
    source = Path(bulk_style.__file__).read_text(encoding="utf-8")
    assert 'r"^(?:SWN|SKN)"' in source
    assert "COPY_CODE_XPATH" in source
    assert "COPY_BUYER_REFERENCE_XPATH" in source


def test_copy_flow_selects_costsheet_then_copy_as_variant():
    source = Path(bulk_style.__file__).read_text(encoding="utf-8")
    assert "COPY_COSTSHEET_XPATH" in source
    assert "COPY_AS_VARIANT_XPATH" in source
    assert source.index("costsheet.check()") < source.index("variant.click()")


def test_style_flow_contains_mandatory_defaults():
    defaults = {
        label: value
        for label, value, _ids, _labels in bulk_style.FIXED_STYLE_FIELDS
    }
    assert defaults == {
        "Purchase UOM": "Pcs",
        "Price Per": "Article",
        "Color Definition": "Single Colors",
    }


def test_style_automation_never_uses_save_selector():
    source = inspect.getsource(bulk_style.prepare_catalog_style_row)
    assert "titlebarArticle" not in source
    assert "requires_manual_save=True" in source


def test_group_class_detection_accepts_actual_lowercase_wfx_class():
    catalog_source = (
        Path(bulk_style.__file__).with_name("catalog.py").read_text(encoding="utf-8")
    )
    assert "[...li.classList, ...span.classList]" in catalog_source
    assert "name.toLocaleLowerCase('en') === 'groupnode'" in catalog_source
