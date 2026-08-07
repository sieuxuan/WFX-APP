from wfx_panel.automation import color_combination


def _options(*labels):
    return [
        {"value": str(index), "label": label}
        for index, label in enumerate(labels, start=1)
    ]


def test_picks_the_style_code_with_the_largest_trailing_number():
    """Số đuôi lớn hơn là style mới hơn, không phụ thuộc thứ tự WFX trả về."""
    picked = color_combination.pick_style_code(
        _options("SWV0004012", "SWV0003935")
    )

    assert picked["label"] == "SWV0004012"


def test_single_option_is_used_even_without_digits():
    picked = color_combination.pick_style_code(_options("SAMPLE"))

    assert picked["label"] == "SAMPLE"


def test_falls_back_to_the_last_option_when_no_code_has_digits():
    """WFX sắp xếp tăng dần, nên option cuối là phỏng đoán an toàn nhất."""
    picked = color_combination.pick_style_code(_options("ALPHA", "BETA"))

    assert picked["label"] == "BETA"


def test_ties_prefer_the_later_option():
    picked = color_combination.pick_style_code(
        _options("AAA0003935", "BBB0003935")
    )

    assert picked["label"] == "BBB0003935"


def test_empty_option_list_returns_none():
    assert color_combination.pick_style_code([]) is None
