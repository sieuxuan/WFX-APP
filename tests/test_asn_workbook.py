from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

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


def test_merge_sale_asn_reports_keeps_two_named_formatted_sheets(tmp_path):
    packing = tmp_path / "packing.xlsx"
    buyer = tmp_path / "buyer.xlsx"
    target = tmp_path / "INV-001.xlsx"
    _report(packing, "Report", "Packing data")
    _report(buyer, "Report", "Buyer data")

    output = merge_sale_asn_reports(packing, buyer, target)

    assert output == target.resolve()
    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == ["Packing List", "Buyer Invoice"]
    assert workbook["Packing List"]["A1"].value == "Packing data"
    assert workbook["Buyer Invoice"]["A1"].value == "Buyer data"
    for sheet in workbook.worksheets:
        assert sheet["A1"].font.bold is True
        assert sheet["A1"].fill.fgColor.rgb == "001F4E78"
        assert sheet["B2"].value == "=1+1"
        assert "A3:C3" in {str(item) for item in sheet.merged_cells.ranges}
        assert sheet.column_dimensions["A"].width == 24
        assert sheet.row_dimensions[1].height == 30
        assert sheet.freeze_panes == "A2"
        assert sheet.sheet_view.zoomScale == 85
        assert sheet.sheet_view.showGridLines is False
        assert sheet.page_setup.orientation == "landscape"
        assert sheet.page_setup.fitToWidth == 1
        assert str(sheet.print_area).endswith("!$A$1:$C$3")
    assert workbook["Packing List"].oddHeader.center.text == "Packing data header"
    assert workbook["Buyer Invoice"].oddHeader.center.text == "Buyer data header"
    workbook.close()
