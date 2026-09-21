from openpyxl import load_workbook

from wfx_panel.workbooks.style import (
    GUIDE_SHEET,
    LIST_SHEET,
    STYLE_COLUMNS,
    STYLE_SHEET,
    StyleWorkbookError,
    read_style_workbook,
    write_style_template,
)


def test_style_template_has_two_user_facing_sheets_and_hidden_lists(tmp_path):
    target = write_style_template(tmp_path / "styles.xlsx")

    workbook = load_workbook(target)
    assert workbook.sheetnames == [GUIDE_SHEET, STYLE_SHEET, LIST_SHEET]
    assert workbook[LIST_SHEET].sheet_state == "veryHidden"
    sheet = workbook[STYLE_SHEET]
    assert tuple(cell.value for cell in sheet[1]) == STYLE_COLUMNS
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref is None
    validations = list(sheet.data_validations.dataValidation)
    assert any(item.formula1 == '"New,Copy"' for item in validations)
    assert any(item.formula1 == "=StyleMaterialType" for item in validations)
    workbook.close()


def test_style_template_has_server_dropdowns_and_dependent_subcategory(tmp_path):
    target = write_style_template(
        tmp_path / "styles.xlsx",
        options={
            "fields": {
                "style_copy": ["Style Apparel A", "Style Apparel B"],
                "material_type": ["KNIT", "WOVEN"],
                "buyer": ["Buyer A"],
                "division": ["Division A"],
                "product_group": ["Top", "Bottom"],
                "color_card": ["Color A"],
                "size_range": ["Size A"],
                "season": ["FW27"],
            },
            "subcategories_by_product_group": {
                "Top": ["Jacket", "Shirt"],
                "Bottom": ["Pants"],
            },
        },
    )
    workbook = load_workbook(target)
    validations = list(workbook[STYLE_SHEET].data_validations.dataValidation)
    formulas = {item.formula1 for item in validations}
    assert "=StyleCopy" in formulas
    assert "=StyleBuyer" in formulas
    assert "=StyleProductGroup" in formulas
    assert any("VLOOKUP($F2" in formula for formula in formulas)
    workbook.close()


def test_style_workbook_reads_new_and_copy_rows(tmp_path):
    target = write_style_template(tmp_path / "styles.xlsx")
    workbook = load_workbook(target)
    sheet = workbook[STYLE_SHEET]
    sheet.append(
        [
            "New", "", "KNIT", "Buyer A", "Knit", "Top", "Polo",
            "Color A", "Size A", "SS27", "BUY-1", "INT-1",
        ]
    )
    sheet.append(
        [
            "Copy", "SWN001", "", "", "", "", "", "", "", "",
            "BUY-2", "INT-2",
        ]
    )
    workbook.save(target)
    workbook.close()

    rows = read_style_workbook(target)

    assert [row.type for row in rows] == ["New", "Copy"]
    assert rows[0].material_type == "KNIT"
    assert rows[1].style_copy == "SWN001"
    assert rows[1].buyer_style_ref == "BUY-2"


def test_new_style_requires_all_business_fields(tmp_path):
    target = write_style_template(tmp_path / "styles.xlsx")
    workbook = load_workbook(target)
    sheet = workbook[STYLE_SHEET]
    sheet.append(["New", "", "KNIT"])
    workbook.save(target)
    workbook.close()

    try:
        read_style_workbook(target)
    except StyleWorkbookError as error:
        assert error.code == "STYLE_FILE_VALIDATION_FAILED"
        assert "Buyer" in error.errors[0]
    else:
        raise AssertionError("Workbook thiếu trường phải bị từ chối")


def test_copy_style_requires_source_reference(tmp_path):
    target = write_style_template(tmp_path / "styles.xlsx")
    workbook = load_workbook(target)
    workbook[STYLE_SHEET].append(["Copy"])
    workbook.save(target)
    workbook.close()

    try:
        read_style_workbook(target)
    except StyleWorkbookError as error:
        assert error.code == "STYLE_FILE_VALIDATION_FAILED"
        assert "Style copy" in error.errors[0]
    else:
        raise AssertionError("Copy thiếu Style nguồn phải bị từ chối")


# --- file người dùng chọn không dùng được -------------------------------


def _template(tmp_path, rows=()):
    target = write_style_template(tmp_path / "styles.xlsx")
    if rows:
        workbook = load_workbook(target)
        for row in rows:
            workbook[STYLE_SHEET].append(list(row))
        workbook.save(target)
        workbook.close()
    return target


def _error(target):
    try:
        read_style_workbook(target)
    except StyleWorkbookError as error:
        return error
    raise AssertionError("Workbook sai phải bị từ chối")


def test_a_file_that_is_not_an_xlsx_is_refused(tmp_path):
    other = tmp_path / "styles.xls"
    other.write_bytes(b"old excel")

    assert _error(other).code == "STYLE_FILE_TYPE_UNSUPPORTED"


def test_a_file_the_user_moved_away_is_refused(tmp_path):
    assert _error(tmp_path / "khong-co.xlsx").code == "STYLE_FILE_NOT_FOUND"


def test_a_file_larger_than_the_limit_is_refused(tmp_path):
    from wfx_panel.workbooks.style import MAX_STYLE_FILE_BYTES

    big = tmp_path / "to.xlsx"
    big.write_bytes(b"0" * (MAX_STYLE_FILE_BYTES + 1))

    assert _error(big).code == "STYLE_FILE_TOO_LARGE"


def test_a_file_that_is_not_a_workbook_at_all_is_refused(tmp_path):
    broken = tmp_path / "hong.xlsx"
    broken.write_text("khong phai xlsx", encoding="utf-8")

    assert _error(broken).code == "STYLE_FILE_INVALID"


def test_a_workbook_with_macros_is_refused(tmp_path):
    import zipfile

    target = _template(tmp_path)
    with zipfile.ZipFile(target, "a") as archive:
        archive.writestr("xl/vbaProject.bin", b"macro")

    assert _error(target).code == "STYLE_FILE_UNSAFE"


def test_a_workbook_without_the_style_sheet_is_refused(tmp_path):
    target = _template(tmp_path)
    workbook = load_workbook(target)
    del workbook[STYLE_SHEET]
    workbook.save(target)
    workbook.close()

    assert _error(target).code == "STYLE_TEMPLATE_SHEET_MISSING"


def test_a_workbook_whose_headers_were_edited_is_refused(tmp_path):
    target = _template(tmp_path)
    workbook = load_workbook(target)
    workbook[STYLE_SHEET]["A1"] = "Loai"
    workbook.save(target)
    workbook.close()

    error = _error(target)

    assert error.code == "STYLE_FILE_HEADERS_INVALID"
    assert STYLE_COLUMNS[0] in error.errors[0]


def test_a_workbook_with_no_data_row_is_refused(tmp_path):
    assert _error(_template(tmp_path)).code == "STYLE_FILE_EMPTY"


# --- từng dòng sai ------------------------------------------------------


def _new_row(**overrides):
    row = {
        "type": "New",
        "style_copy": "",
        "material_type": "KNIT",
        "buyer": "Buyer A",
        "division": "Knit",
        "product_group": "Top",
        "sub_category": "Polo",
        "color_card": "Color A",
        "size_range": "Size A",
        "season": "SS27",
        "buyer_style_ref": "BUY-1",
        "internal_style_ref": "INT-1",
    }
    row.update(overrides)
    return list(row.values())


def test_a_row_carrying_a_formula_is_refused(tmp_path):
    target = _template(tmp_path, [_new_row(buyer_style_ref="=1+1")])

    error = _error(target)

    assert "không được dùng công thức" in error.errors[0]


def test_a_type_that_is_neither_new_nor_copy_is_refused(tmp_path):
    target = _template(tmp_path, [_new_row(type="Sua")])

    assert "New hoặc Copy" in _error(target).errors[0]


def test_a_material_type_wfx_does_not_offer_is_refused(tmp_path):
    target = _template(tmp_path, [_new_row(material_type="DENIM")])

    assert "KNIT hoặc WOVEN" in _error(target).errors[0]


def test_blank_rows_between_data_are_simply_skipped(tmp_path):
    target = _template(tmp_path, [_new_row(), [""] * 12, _new_row()])

    assert len(read_style_workbook(target)) == 2


def test_more_rows_than_the_limit_is_refused(tmp_path):
    from wfx_panel.workbooks.style import MAX_STYLE_ROWS

    target = _template(tmp_path, [_new_row() for _ in range(MAX_STYLE_ROWS + 1)])

    assert f"{MAX_STYLE_ROWS}" in _error(target).errors[0]


def test_a_row_carries_its_own_line_number_into_automation(tmp_path):
    target = _template(tmp_path, [_new_row()])
    workbook = load_workbook(target)
    appended_row = workbook[STYLE_SHEET].max_row
    workbook.close()

    payload = read_style_workbook(target)[0].automation_payload()

    # Số dòng phải là số người dùng nhìn thấy trong Excel, để thông báo lỗi
    # của automation trỏ đúng dòng họ cần sửa.
    assert payload["source_row"] == appended_row
    assert payload["buyer"] == "Buyer A"


def test_a_target_without_the_xlsx_suffix_is_written_as_xlsx(tmp_path):
    target = write_style_template(tmp_path / "styles")

    assert target.suffix == ".xlsx"
    assert target.is_file()


def test_a_product_group_with_no_sub_category_gets_no_dependent_list(tmp_path):
    target = write_style_template(
        tmp_path / "styles.xlsx",
        {
            "fields": {
                "buyer": ["Buyer A"],
                "product_group": ["Top", "Bottom"],
                "season": ["SS27"],
            },
            "subcategories_by_product_group": {"Top": ["Polo"], "Bottom": []},
        },
    )
    workbook = load_workbook(target)

    names = {
        name
        for name in workbook.defined_names
        if name.startswith("StyleSub") and name != "StyleSubcategoryAll"
    }
    workbook.close()

    # Chỉ Product Group thật sự có Sub-Category mới có danh sách phụ thuộc.
    assert len(names) == 1


def test_a_zip_openpyxl_cannot_read_is_reported_as_an_invalid_workbook(tmp_path):
    import zipfile

    target = tmp_path / "gia.xlsx"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("readme.txt", b"khong phai workbook")

    assert _error(target).code == "STYLE_FILE_INVALID"
