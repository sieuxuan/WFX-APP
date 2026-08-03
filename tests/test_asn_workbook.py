from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, Font, PatternFill, Side

from wfx_panel.asn_workbook import merge_sale_asn_reports


def _report(path, title, value):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet["A1"] = value
    sheet["A1"].font = Font(bold=True, color="FFFFFF")
    sheet["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    sheet["B2"] = "=1+1"
    sheet.merge_cells("A3:C3")
    sheet["A3"] = "Merged heading"
    frame = Side(style="thin", color="000000")
    sheet["A3"].border = Border(left=frame, top=frame, bottom=frame)
    sheet["C3"].border = Border(right=frame, top=frame, bottom=frame)
    sheet.column_dimensions["A"].width = 24
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "A2"
    sheet.sheet_view.zoomScale = 85
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.print_area = "A1:C3"
    sheet.oddHeader.center.text = f"{value} header"
    workbook.save(path)
    workbook.close()


def _reports(path, titles, prefix):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for index, title in enumerate(titles, start=1):
        sheet = workbook.create_sheet(title)
        sheet["A1"] = f"{prefix} {index}"
    workbook.save(path)
    workbook.close()


def test_merge_sale_asn_reports_renames_only_colliding_sheet_titles(tmp_path):
    packing = tmp_path / "packing.xlsx"
    buyer = tmp_path / "buyer.xlsx"
    target = tmp_path / "INV-001.xlsx"
    _report(packing, "Report", "Packing data")
    _report(buyer, "Report", "Buyer data")

    output = merge_sale_asn_reports(
        packing,
        buyer,
        target,
        invoice_no="INV-001",
    )

    assert output == target.resolve()
    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == ["INVOICE INV-001", "PKL INV-001"]
    assert workbook["PKL INV-001"]["A1"].value == "Packing data"
    assert workbook["INVOICE INV-001"]["A1"].value == "Buyer data"
    for sheet in workbook.worksheets:
        assert sheet["A1"].font.bold is True
        assert sheet["A1"].fill.fgColor.rgb == "001F4E78"
        assert sheet["B2"].value == "=1+1"
        assert "A3:C3" in {str(item) for item in sheet.merged_cells.ranges}
        assert sheet["A3"].border.left.style == "thin"
        assert sheet["C3"].border.right.style == "thin"
        assert sheet.column_dimensions["A"].width == 24
        assert sheet.row_dimensions[1].height == 30
        assert sheet.freeze_panes == "A2"
        assert sheet.sheet_view.zoomScale == 85
        assert sheet.sheet_view.showGridLines is False
        assert sheet.page_setup.orientation == "landscape"
        assert sheet.page_setup.fitToWidth == 1
        assert str(sheet.print_area).endswith("!$A$1:$C$3")
    assert workbook["PKL INV-001"].oddHeader.center.text == "Packing data header"
    assert workbook["INVOICE INV-001"].oddHeader.center.text == "Buyer data header"
    workbook.close()


def test_merge_sale_asn_reports_preserves_distinct_original_sheet_titles(tmp_path):
    packing = tmp_path / "packing-original.xlsx"
    buyer = tmp_path / "buyer-original.xlsx"
    target = tmp_path / "INV-002.xlsx"
    _report(packing, "WFX Packing Export", "Packing data")
    _report(buyer, "Commercial Invoice", "Buyer data")

    merge_sale_asn_reports(
        packing,
        buyer,
        target,
        invoice_no="INV-002",
    )

    workbook = load_workbook(target, data_only=False)
    assert workbook.sheetnames == ["Commercial Invoice", "WFX Packing Export"]
    assert workbook["WFX Packing Export"]["A1"].value == "Packing data"
    assert workbook["Commercial Invoice"]["A1"].value == "Buyer data"
    workbook.close()


def test_merge_sale_asn_reports_interleaves_multiple_sheets_invoice_first(tmp_path):
    packing = tmp_path / "packing-multi.xlsx"
    buyer = tmp_path / "buyer-multi.xlsx"
    target = tmp_path / "INV-003.xlsx"
    _reports(packing, ["Report 1", "Report 2", "Report 3"], "Packing")
    _reports(buyer, ["Report 1", "Report 2", "Report 3"], "Invoice")

    merge_sale_asn_reports(packing, buyer, target, invoice_no="INV-003")

    workbook = load_workbook(target, data_only=False)
    assert workbook.sheetnames == [
        "INVOICE INV-003",
        "PKL INV-003",
        "INVOICE INV-003 (2)",
        "PKL INV-003 (2)",
        "INVOICE INV-003 (3)",
        "PKL INV-003 (3)",
    ]
    assert [sheet["A1"].value for sheet in workbook.worksheets] == [
        "Invoice 1",
        "Packing 1",
        "Invoice 2",
        "Packing 2",
        "Invoice 3",
        "Packing 3",
    ]
    workbook.close()


def test_merge_sale_asn_reports_keeps_interleaving_when_counts_differ(tmp_path):
    packing = tmp_path / "packing-extra.xlsx"
    buyer = tmp_path / "buyer-short.xlsx"
    target = tmp_path / "INV-004.xlsx"
    _reports(packing, ["Packing 1", "Packing 2", "Packing 3"], "Packing")
    _reports(buyer, ["Invoice 1", "Invoice 2"], "Invoice")

    merge_sale_asn_reports(packing, buyer, target, invoice_no="INV-004")

    workbook = load_workbook(target, data_only=False)
    assert workbook.sheetnames == [
        "Invoice 1",
        "Packing 1",
        "Invoice 2",
        "Packing 2",
        "Packing 3",
    ]
    assert [sheet["A1"].value for sheet in workbook.worksheets] == [
        "Invoice 1",
        "Packing 1",
        "Invoice 2",
        "Packing 2",
        "Packing 3",
    ]
    workbook.close()
