from wfx_panel.automation import color_combination
from wfx_panel.automation.runtime import AutomationCancelled


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


def test_prune_keeps_every_level_that_still_exists():
    values = {"division": "d1", "buyer": "b1", "season": "s1"}
    options = {
        "division": _options("d1"),
        "buyer": _options("b1"),
        "season": _options("s1"),
    }
    options["division"][0]["value"] = "d1"
    options["buyer"][0]["value"] = "b1"
    options["season"][0]["value"] = "s1"

    assert color_combination.prune_selection(values, options) == values


def test_prune_drops_lower_levels_once_one_is_stale():
    """Buyer đổi thì Season của buyer cũ không còn ý nghĩa."""
    values = {"division": "d1", "buyer": "gone", "season": "s1"}
    options = {
        "division": [{"value": "d1", "label": "D1"}],
        "buyer": [{"value": "b1", "label": "B1"}],
        "season": [{"value": "s1", "label": "S1"}],
    }

    assert color_combination.prune_selection(values, options) == {
        "division": "d1"
    }


def test_prune_returns_nothing_when_the_first_level_is_missing():
    assert color_combination.prune_selection({}, {}) == {}


def _saved(style_ref):
    return {
        "style_ref": style_ref,
        "style_code": "SWV0000001",
        "file_path": f"D:/out/{style_ref}.xlsx",
        "file_name": f"{style_ref}.xlsx",
    }


def test_batch_continues_after_a_style_fails():
    """50 style một lượt: một style hỏng không được giết cả lượt chạy."""

    def run_one(style_ref):
        if style_ref == "B":
            raise color_combination.StyleFailure(
                "COLOR_REPORT_STYLECODE_MISSING", "Không có StyleCode."
            )
        return _saved(style_ref)

    result = color_combination.batch_styles(
        ["A", "B", "C"], run_one, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A", "C"]
    assert result["failed"] == [
        {
            "style_ref": "B",
            "code": "COLOR_REPORT_STYLECODE_MISSING",
            "message": "Không có StyleCode.",
        }
    ]
    assert result["cancelled"] is False


def test_batch_labels_unexpected_errors_with_a_generic_code():
    def run_one(_style_ref):
        raise ValueError("frame detached")

    result = color_combination.batch_styles(
        ["A"], run_one, log=lambda _line: None
    )

    assert result["failed"][0]["code"] == "COLOR_REPORT_STYLE_FAILED"
    assert "frame detached" in result["failed"][0]["message"]


def test_batch_keeps_saved_files_when_the_user_presses_stop():
    """Stop giữa lượt vẫn phải trả về file đã tải, không mất trắng."""

    def run_one(style_ref):
        if style_ref == "C":
            raise AutomationCancelled("ACTION_CANCELLED")
        return _saved(style_ref)

    result = color_combination.batch_styles(
        ["A", "B", "C", "D"], run_one, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A", "B"]
    assert result["cancelled"] is True


def test_batch_progress_messages_end_with_the_counter_suffix():
    """UI đọc hậu tố n/m để hiện bộ đếm; đổi định dạng là hỏng thẻ tiến độ."""
    seen = []

    color_combination.batch_styles(
        ["A", "B"],
        _saved,
        progress=lambda stage, message, step, total: seen.append(
            (stage, message, step, total)
        ),
        log=lambda _line: None,
    )

    assert [
        item[1].endswith(suffix)
        for item, suffix in zip(seen, ("1/2", "2/2"), strict=True)
    ] == [
        True,
        True,
    ]
    assert seen[0][0] == "style"
    assert seen[1][2:] == (2, 2)


def test_batch_ignores_blank_style_references():
    result = color_combination.batch_styles(
        ["A", "  ", ""], _saved, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A"]
