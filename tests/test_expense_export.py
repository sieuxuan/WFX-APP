from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.test_expense_invoice import controller, input_file
from tests.test_expense_invoice import expense_page as expense_page
from wfx_panel.automation import expense_cost_centers as costs
from wfx_panel.automation import expense_export as export
from wfx_panel.automation.expense_invoice import ExpenseInputError
from wfx_panel.controllers import finance
from wfx_panel.workbooks.expense_invoice import (
    COST_COLUMNS,
    COST_SHEET,
    SHEET,
    ExpenseWorkbookError,
    read_expense_workbook,
    save_expense_workbook,
)


def allocations():
    return [
        {
            "percent": "100.00",
            "comments": "Ghi chú",
            "centers": [
                {"category": "DIVISION", "center": "WOVEN HANOI"},
                {"category": "DEPARTMENT", "center": "IT & WFX"},
            ],
        }
    ]


def test_export_round_trip_keeps_names_allocation_and_literal_text(tmp_path):
    data = read_expense_workbook(input_file(tmp_path, second=True))
    data["header"]["invoice_no"] = "000001"
    data["header"]["comments"] = "=literal text, not a formula"
    data["cost_centers"] = {1: allocations()}
    target = tmp_path / "export.xlsx"
    save_expense_workbook(target, data)
    parsed = read_expense_workbook(target)
    assert parsed["header"] == data["header"]
    assert parsed["lines"] == data["lines"]
    assert costs._signature(parsed["cost_centers"][1]) == costs._signature(
        allocations()
    )
    # Editing the exported workbook is sufficient to reuse it for another invoice.
    wb = load_workbook(target)
    wb[SHEET]["B2"] = "000002"
    wb[SHEET]["B3"] = "000002"
    wb[SHEET]["J2"] = 5
    wb[COST_SHEET]["D3"] = "NEW DEPARTMENT"
    wb.save(target)
    wb.close()
    changed = read_expense_workbook(target)
    assert changed["header"]["invoice_no"] == "000002"
    assert changed["lines"][0]["rate"] == "5"
    assert changed["cost_centers"][1][0]["centers"][1]["center"] == "NEW DEPARTMENT"


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: setattr(s["A2"], "value", 3),
        lambda s: setattr(s["E2"], "value", 50),
        lambda s: setattr(s["E2"], "value", "=100"),
        lambda s: setattr(s["D2"], "value", None),
        lambda s: setattr(s["C3"], "value", "DIVISION"),
    ],
)
def test_invalid_cost_allocation_is_rejected_before_browser(tmp_path, edit):
    data = read_expense_workbook(input_file(tmp_path))
    data["cost_centers"] = {1: allocations()}
    target = tmp_path / "export.xlsx"
    save_expense_workbook(target, data)
    wb = load_workbook(target)
    edit(wb[COST_SHEET])
    wb.save(target)
    wb.close()
    with pytest.raises(ExpenseWorkbookError, match="Cost Centers"):
        read_expense_workbook(target)


def test_old_file_without_cost_sheet_is_still_supported(tmp_path):
    assert read_expense_workbook(input_file(tmp_path))["cost_centers"] == {}


def test_hierarchy_export_inherits_parent_names_and_omits_internal_ids():
    payload = {
        "mode": "hierarchy",
        "source": {
            "CostCentreAllocCat": {
                "JsonData": [
                    {
                        "CostCategoryID": "68",
                        "CostProfitCatName": "DIVISION",
                        "ColSno": "1",
                    },
                    {
                        "CostCategoryID": "69",
                        "CostProfitCatName": "DEPARTMENT",
                        "ColSno": "2",
                    },
                ]
            },
            "CostCentreAlloc": {
                "JsonData": [
                    {
                        "CostProfitName68": "WOVEN HANOI",
                        "CostProfitName69": "IT",
                        "Perc": "60",
                        "Amount": "60",
                        "CostCentreAllocID": "secret-id",
                    },
                    {
                        "CostProfitName68": "",
                        "CostProfitName69": "HR",
                        "Perc": "40",
                        "Amount": "40",
                    },
                ]
            },
        },
    }
    parsed = costs.allocations_from_source(payload, "100")
    assert parsed[1]["centers"][0]["center"] == "WOVEN HANOI"
    assert parsed[1]["centers"][1]["center"] == "HR"
    assert "secret-id" not in str(parsed)


def test_export_controller_validates_before_replacing_existing_file(
    tmp_path, monkeypatch
):
    ctrl = controller(tmp_path)
    data = read_expense_workbook(input_file(tmp_path))
    data["cost_centers"] = {1: allocations()}
    monkeypatch.setattr(
        finance,
        "export_selected_expense_invoice",
        lambda log: {"ok": True, "data": deepcopy(data)},
    )
    target = tmp_path / "existing.xlsx"
    target.write_bytes(b"original")
    result = ctrl.export_expense_invoice(str(target))
    assert result["code"] == "EXPENSE_EXPORTED"
    assert "data" not in result and "options" not in result
    assert read_expense_workbook(target)["cost_centers"]
    before = target.read_bytes()
    data["header"]["supplier"] = ""
    assert not ctrl.export_expense_invoice(str(target))["ok"]
    assert target.read_bytes() == before
    assert not list(tmp_path.glob(".wfx-expense-*"))


def test_export_failure_keeps_existing_file_and_no_data_in_result(
    tmp_path, monkeypatch
):
    ctrl = controller(tmp_path)
    target = tmp_path / "existing.xlsx"
    target.write_bytes(b"original")
    monkeypatch.setattr(
        finance,
        "export_selected_expense_invoice",
        lambda log: {"ok": False, "code": "EXPENSE_EXPORT_FAILED"},
    )
    assert not ctrl.export_expense_invoice(str(target))["ok"]
    assert target.read_bytes() == b"original"


def _make_list(page, selected):
    page.set_content(
        '<div id="titlebarExpenseInvoiceList"></div><table id="gridExpenseInvoiceList_tblGridContent">'
        + "".join(
            f'<tr class="trContent" id="{i}"><td><input type="checkbox" {"checked" if i in selected else ""}></td><td id="ColInvoiceNo">000{i}</td></tr>'
            for i in (1, 2)
        )
        + "</table>"
    )


def test_selection_requires_exactly_one_expense_row_and_rejects_supplier_context(
    expense_page,
):
    page = expense_page
    page.goto("http://wfx.test/WFXExpenseInvoiceList.aspx")
    _make_list(page, [])
    with pytest.raises(ExpenseInputError, match="một Expense Invoice"):
        export._selected_invoice(page.context.browser)
    _make_list(page, [1, 2])
    with pytest.raises(ExpenseInputError):
        export._selected_invoice(page.context.browser)
    _make_list(page, [2])
    _frame, selected = export._selected_invoice(page.context.browser)
    assert selected == {"id": "2", "invoice": "0002"}
    page.evaluate(
        "() => document.body.insertAdjacentHTML('beforeend','<table id=gridAPInvoiceList_tblGridContent></table>')"
    )
    with pytest.raises(ExpenseInputError):
        export._selected_invoice(page.context.browser)


def test_missing_mandatory_cost_center_stops_before_popup(expense_page):
    expense_page.evaluate("""() => {window.objsectionExpenseInvoiceExpenseDetail = {
        gridExpenseInvoiceExpenseDetail:{data:[{IsCostCenterMandatory:'1',IsCostCenterAttached:'1'}]}};
    }""")
    with pytest.raises(ExpenseInputError, match="yêu cầu Cost Center"):
        costs.fill_cost_centers(expense_page, 0, [])
    assert not expense_page.evaluate("Boolean(window.saved || window.confirmed)")


def test_export_cancel_does_not_start_automation(tmp_path):
    from types import SimpleNamespace

    from wfx_panel.app.dialogs import FileDialogController

    app = SimpleNamespace(
        window=SimpleNamespace(create_file_dialog=lambda *a, **k: None),
        api=SimpleNamespace(
            export_expense_invoice=lambda *a: pytest.fail("cancel must not crawl")
        ),
    )
    assert (
        FileDialogController(app).expense_file_dialog(save=True, export=True)["code"]
        == "EXPENSE_FILE_DIALOG_CANCELLED"
    )


def test_template_includes_blank_editable_cost_sheet(tmp_path):
    from wfx_panel.workbooks.expense_invoice import save_template

    target = tmp_path / "template.xlsx"
    save_template(target)
    wb = load_workbook(target)
    assert tuple(c.value for c in wb[COST_SHEET][1]) == COST_COLUMNS
    assert wb[COST_SHEET].max_row == 1
    wb.close()


def test_split_cost_centers_commit_each_row_and_do_not_match_duplicate_labels(
    expense_page,
):
    expense_page.evaluate("""() => {
        window.gHierarchyStructureForCostCenters='1';
        const meta={IsCostCenterMandatory:'1',IsCostCenterAttached:'1',LedgerAmt:'240',LedgerAcCode:'code',ExpenseInvoiceLedgerID:-1};
        window.objsectionExpenseInvoiceExpenseDetail={gridExpenseInvoiceExpenseDetail:{data:[meta]}};
        window.gHierarchyStructureCategory=[
            {CostCategoryID:'68',CostProfitCatName:'DIVISION',ColSno:'1',Mandatory:'1'},
            {CostCategoryID:'69',CostProfitCatName:'DEPARTMENT',ColSno:'2',Mandatory:'1'}];
        const source={CostCentreAllocCat:{JsonData:gHierarchyStructureCategory},CostCentreAlloc:{JsonData:[]}};
        window.gExpenseInvoiceID=-1;
        window.GetDatasourceForCostCentreHierarchyStructure=()=>source;
        const fields=[['colCostProfit68','ddlCCACostProfit68','CostProfitName68'],
            ['colCostProfit69','ddlCCACostProfit69','CostProfitName69'],
            ['colNarration','lblNarration','Narration'],['colPerc','txtPerc','Perc']];
        const rows=[{}];
        let active=null;
        const commit=()=>{
            if(!active)return;
            const {field,row,key,cell}=active;
            rows[row][key]=field.tagName==='SELECT'?field.selectedOptions[0].textContent:field.value;
            cell.textContent=rows[row][key];
            if(key==='Narration')cell.innerHTML='<span id="lblNarration"></span>';
            active=null;
        };
        const grid={0:{definition:{Columns:{Column:fields.map(([ID,editor])=>({ID,EditItem:{Item:[{ID:editor}]}}))}}},SaveGridFocusedCell:commit};
        window.GetObjGrid=()=>grid;
        const render=()=>{
            const table=document.querySelector('#gridCostCentreAlloc_tblGridContent');
            table.innerHTML='';
            rows.forEach((data,row)=>{
                const tr=table.insertRow();tr.className='trContent';
                fields.forEach(([column,editor,key])=>{
                    const cell=tr.insertCell();cell.id=column;cell.textContent=data[key]||'';
                    if(key==='Narration')cell.innerHTML='<span id="lblNarration"></span>';
                    cell.ondblclick=()=>{
                        commit();cell.textContent='';
                        const isSelect=key.startsWith('CostProfitName');
                        const field=document.createElement(isSelect?'select':'input');field.id=editor;
                        if(isSelect){
                            const choices=key.endsWith('68')?['WOVEN HANOI']:['IT & WFX','HR'];
                            field.innerHTML='<option value="">[Select]</option>'+choices.map((s,i)=>`<option value="${i+1}">${s}</option>`).join('');
                        }else field.value=data[key]||'';
                        cell.append(field);active={field,row,key,cell};
                    };
                });
            });
        };
        window.imgSplitOnClick=()=>{rows.push({});render();};
        window.SaveCostCentreAllocPopup=()=>{
            commit();source.CostCentreAlloc.JsonData=rows.map(r=>({...r,Amount:String(240*Number(r.Perc)/100)}));return true;
        };
        const td=document.querySelector('#gridExpenseInvoiceExpenseDetail_tblGridContent tr').insertCell();
        td.id='colLedgerCostCenter';td.innerHTML='<a href="#">>></a>';
        td.firstChild.onclick=e=>{
            e.preventDefault();
            document.body.insertAdjacentHTML('beforeend','<div id="sectionCostCentreAlloc"><table id="gridCostCentreAlloc_tblGridHeader"><tr><td>Cost Centers</td></tr></table><table id="gridCostCentreAlloc_tblGridContent"></table></div>');
            render();
        };
    }""")
    entries = allocations()
    entries[0]["percent"] = "60"
    entries.append(deepcopy(entries[0]))
    entries[1]["percent"] = "40"
    entries[1]["centers"][1]["center"] = "HR"
    costs.fill_cost_centers(expense_page, 0, entries)
    costs.verify_cost_centers(expense_page, 0, entries)
    assert not expense_page.evaluate("Boolean(window.saved || window.confirmed)")
    # Later WFX callbacks must not silently change the finished allocation.
    expense_page.evaluate(
        "() => GetDatasourceForCostCentreHierarchyStructure().CostCentreAlloc.JsonData[1].CostProfitName69='IT & WFX'"
    )
    with pytest.raises(ExpenseInputError, match="Cost Center dòng 1"):
        costs.verify_cost_centers(expense_page, 0, entries)


def test_committed_ledger_value_ignores_retained_select_options(expense_page):
    from wfx_panel.automation.expense_invoice import _line_value

    expense_page.locator('[id="ColLedgerAcName"]').dblclick()
    expense_page.evaluate("""() => {
        window.objsectionExpenseInvoiceExpenseDetail={gridExpenseInvoiceExpenseDetail:{data:[{LedgerAcName:'Committed ledger'}]}};
    }""")
    assert (
        "HR SUBSCRIPTION" in expense_page.locator('[id="ColLedgerAcName"]').inner_text()
    )
    assert _line_value(expense_page, 0, "ledger") == "Committed ledger"


def test_flat_wfx_categories_match_grouped_excel_allocation(monkeypatch):
    from types import SimpleNamespace

    entries = allocations()
    flat = [{**entries[0], "centers": [center]} for center in entries[0]["centers"]]
    monkeypatch.setattr(
        costs, "_metadata", lambda *args: {"IsCostCenterMandatory": "1"}
    )
    monkeypatch.setattr(costs, "read_cost_centers", lambda *args: flat)
    frame = SimpleNamespace(evaluate=lambda *args: "0")
    costs.verify_cost_centers(frame, 0, entries)
    flat[0]["centers"] = [{"category": "DIVISION", "center": "WRONG DIVISION"}]
    with pytest.raises(ExpenseInputError):
        costs.verify_cost_centers(frame, 0, entries)
