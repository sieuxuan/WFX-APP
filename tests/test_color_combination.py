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


def test_file_stem_joins_style_reference_and_code():
    stem = color_combination.safe_file_stem("GWSD15176", "SWV0003935")

    assert stem == "GWSD15176 - SWV0003935"


def test_file_stem_replaces_characters_windows_forbids():
    stem = color_combination.safe_file_stem("GW/SD:15176", "SWV*3935")

    assert stem == "GW_SD_15176 - SWV_3935"


def test_file_stem_drops_the_code_part_when_there_is_no_code():
    assert color_combination.safe_file_stem("GWSD15176", "") == "GWSD15176"


def test_file_stem_never_ends_with_a_dot_or_space():
    """Windows từ chối tên file kết thúc bằng dấu chấm hoặc khoảng trắng."""
    assert color_combination.safe_file_stem("GWSD15176.", "") == "GWSD15176"


def test_unique_target_adds_a_counter_when_the_name_is_taken(tmp_path):
    (tmp_path / "GWSD15176.xlsx").write_text("x", encoding="utf-8")
    (tmp_path / "GWSD15176 (2).xlsx").write_text("x", encoding="utf-8")

    target = color_combination.unique_target(tmp_path, "GWSD15176")

    assert target == tmp_path / "GWSD15176 (3).xlsx"


def test_unique_target_uses_the_plain_name_when_it_is_free(tmp_path):
    target = color_combination.unique_target(tmp_path, "GWSD15176")

    assert target == tmp_path / "GWSD15176.xlsx"
