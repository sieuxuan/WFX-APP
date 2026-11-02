"""Expense ledger allocations: names in Excel, live WFX dropdowns on import.

Popup Save functions below only update the unsaved invoice's local cache.
Never call CostCentreAllocSaveData (it persists to the server).
"""

from __future__ import annotations

from decimal import Decimal

from wfx_panel.automation.runtime import checkpoint


def _source(frame, row: dict) -> dict:
    return frame.evaluate(
        """row => {
        if (String(row.IsCostCenterAttached) !== '1') return {mode:'none'};
        if (String(window.gHierarchyStructureForCostCenters) === '1') {
            const source=GetDatasourceForCostCentreHierarchyStructure(
                gExpenseInvoiceID, 'ExpenseInvoice', row.LedgerAcCode,
                row.LedgerAmt, row.ExpenseInvoiceLedgerID,
                'xtExpenseInvoiceLedger.ExpenseInvoiceLedgerID');
            return {mode:'hierarchy',source};
        }
        const key='CostCenterAllocation|'+row.LedgerAcCode+'|'+row.ExpenseInvoiceLedgerID;
        const source=window.objHashData?.[key] || GetCostCenterAllocationData(
            row.ExpenseInvoiceLedgerID,row.LedgerAcCode,row.LedgerAmt,row.IsCostCenterAttached);
        return {mode:'flat',source};
    }""",
        row,
    )


def allocations_from_source(payload: dict, amount: str) -> list[dict]:
    """Flatten WFX's inherited hierarchy rows without carrying document IDs."""
    source = payload.get("source") or {}
    if payload.get("mode") == "none":
        return []
    result = []
    if payload["mode"] == "hierarchy":
        categories = sorted(
            source["CostCentreAllocCat"]["JsonData"], key=lambda c: int(c["ColSno"])
        )
        inherited: dict[str, str] = {}
        for row in source["CostCentreAlloc"]["JsonData"]:
            for index, category in enumerate(categories):
                key = str(category["CostCategoryID"])
                name = str(row.get("CostProfitName" + key) or "").strip()
                if name:
                    if inherited.get(key) != name:
                        for later in categories[index + 1 :]:
                            inherited.pop(str(later["CostCategoryID"]), None)
                    inherited[key] = name
            if Decimal(str(row.get("Amount") or "0")) <= 0:
                continue
            centers = [
                {
                    "category": c["CostProfitCatName"],
                    "center": inherited[str(c["CostCategoryID"])],
                }
                for c in categories
                if inherited.get(str(c["CostCategoryID"]))
            ]
            percent = str(
                row.get("Perc") or Decimal(row["Amount"]) * 100 / Decimal(amount)
            )
            result.append(
                {
                    "centers": centers,
                    "percent": percent,
                    "comments": str(row.get("Narration") or ""),
                }
            )
    else:
        for row in source["CostCenterAllocation"]["JsonData"]:
            if Decimal(str(row.get("Amt") or "0")) <= 0:
                continue
            result.append(
                {
                    "centers": [
                        {
                            "category": row["CostProfitCatName"],
                            "center": row["CostProfitName"],
                        }
                    ],
                    "percent": str(Decimal(str(row["Amt"])) * 100 / Decimal(amount)),
                    "comments": str(row.get("Narration") or ""),
                }
            )
    return result


def read_cost_centers(frame, row: dict) -> list[dict]:
    return allocations_from_source(_source(frame, row), str(row["LedgerAmt"]))


def _signature(allocations: list[dict]) -> list:
    return sorted(
        (
            tuple(
                sorted(
                    (c["category"].strip().casefold(), c["center"].strip().casefold())
                    for c in a["centers"]
                )
            ),
            Decimal(a["percent"]),
            a.get("comments", "").strip(),
        )
        for a in allocations
    )


def _metadata(frame, index: int) -> dict:
    return frame.evaluate(
        "index => window.objsectionExpenseInvoiceExpenseDetail?.gridExpenseInvoiceExpenseDetail?.data[index] || {}",
        index,
    )


def _edit(
    frame, grid_name: str, index: int, column: str, value: str, *, select: bool = False
) -> None:
    from wfx_panel.automation.expense_invoice import ExpenseInputError, _select, _settle

    checkpoint()
    row = frame.locator(f"#{grid_name}_tblGridContent tr.trContent").nth(index)
    cell = row.locator(f'[id="{column}"]')
    cell.dblclick(timeout=5000)
    editor = frame.evaluate(
        """args => {
        const grid=GetObjGrid(args.grid)[0];
        const col=grid.definition.Columns.Column.find(c=>c.ID===args.column);
        return col?.EditItem?.Item?.[0]?.ID || '';
    }""",
        {"grid": grid_name.removeprefix("grid"), "column": column},
    )
    if not editor:
        raise ExpenseInputError("Không mở được ô phân bổ Cost Center trên WFX.")
    # WFX reuses lblNarration for a Label in every row and its Input editor.
    # Restrict to editable controls so split allocations never match another row.
    selector = ",".join(
        f'{tag}[id="{editor}"]' for tag in ("select", "input", "textarea")
    )
    if select:
        _select(frame, selector, value, ledger=True)
    else:
        field = frame.locator(selector)
        field.fill(value)
        field.dispatch_event("change")
    frame.locator(f"#{grid_name}_tblGridHeader").click()
    frame.evaluate(
        "name => GetObjGrid(name).SaveGridFocusedCell()", grid_name.removeprefix("grid")
    )
    _settle(frame)


def fill_cost_centers(frame, index: int, allocations: list[dict]) -> None:
    from wfx_panel.automation.expense_invoice import (
        ExpenseInputError,
        _normal,
        _rows,
        _settle,
    )

    meta = _metadata(frame, index)
    mandatory = str(meta.get("IsCostCenterMandatory", "0")) == "1"
    if not allocations:
        if mandatory:
            raise ExpenseInputError(
                f"Ledger dòng {index + 1} yêu cầu Cost Center. Hãy điền sheet Cost Centers rồi chọn lại file."
            )
        return
    if str(meta.get("IsCostCenterAttached", "0")) != "1":
        raise ExpenseInputError(
            f"Ledger dòng {index + 1} không cho phân bổ Cost Center."
        )
    if Decimal(str(meta.get("LedgerAmt") or "0")) <= 0:
        raise ExpenseInputError(
            f"Chi phí {index + 1} phải có số tiền lớn hơn 0 để phân bổ Cost Center."
        )
    hierarchy = (
        str(frame.evaluate("() => window.gHierarchyStructureForCostCenters")) == "1"
    )
    if hierarchy and sum(Decimal(a["percent"]) for a in allocations) != 100:
        raise ExpenseInputError(
            f"Chi phí {index + 1}: tổng tỷ lệ các Allocation phải bằng 100."
        )
    _rows(frame).nth(index).locator('[id="colLedgerCostCenter"] a').evaluate(
        "e => e.click()"
    )
    _settle(frame)
    if hierarchy:
        grid_name = "gridCostCentreAlloc"
        categories = frame.evaluate("() => gHierarchyStructureCategory")
        columns = {_normal(c["CostProfitCatName"]): c for c in categories}
        for a in allocations:
            provided = {_normal(c["category"]) for c in a["centers"]}
            if provided - columns.keys() or any(
                str(c.get("Mandatory")) == "1" and key not in provided
                for key, c in columns.items()
            ):
                raise ExpenseInputError(
                    f"Chi phí {index + 1}: Category thiếu hoặc không khớp yêu cầu Ledger trên WFX."
                )
        # Fresh New only: replace any automatic allocation with the file's exact rows.
        count = frame.locator(f"#{grid_name}_tblGridContent tr.trContent").count()
        if count > len(allocations):
            frame.evaluate(
                "indices => GetObjGrid('CostCentreAlloc').DeleteRows(indices,false,false)",
                ",".join(str(i) for i in range(len(allocations), count)),
            )
        for i, allocation in enumerate(allocations):
            checkpoint()
            if i >= frame.locator(f"#{grid_name}_tblGridContent tr.trContent").count():
                frame.evaluate(
                    "index => imgSplitOnClick(undefined,undefined,'1',index-1)", i
                )
            for category in categories:
                matches = [
                    c
                    for c in allocation["centers"]
                    if _normal(c["category"]) == _normal(category["CostProfitCatName"])
                ]
                _edit(
                    frame,
                    grid_name,
                    i,
                    "colCostProfit" + str(category["CostCategoryID"]),
                    matches[0]["center"] if matches else "",
                    select=True,
                )
            _edit(frame, grid_name, i, "colNarration", allocation.get("comments", ""))
            _edit(frame, grid_name, i, "colPerc", allocation["percent"])
        if not frame.evaluate("() => SaveCostCentreAllocPopup()"):
            raise ExpenseInputError(
                f"WFX chưa nhận đủ phân bổ Cost Center dòng {index + 1}."
            )
    else:
        grid_name = "gridCostCenterAllocation"
        entries = [(a, center) for a in allocations for center in a["centers"]]
        # Resolve columns by the actual WFX field definition, not translated captions.
        cols = frame.evaluate("""() => Object.fromEntries(
            objsectionCostCenterAllocation.gridCostCenterAllocation.definition.Columns.Column
            .flatMap(c=>[c.EditItem?.Item?.[0]?.Value,c.EditItem?.Item?.[0]?.ValueText]
                .filter(Boolean).map(field=>[field,c.ID])))""")
        count = frame.locator(f"#{grid_name}_tblGridContent tr.trContent").count()
        if count > len(entries):
            frame.evaluate(
                "indices => $(objsectionCostCenterAllocation.gridCostCenterAllocation).DeleteRows(indices,false,false)",
                ",".join(str(i) for i in range(len(entries), count)),
            )
        for i, (allocation, center) in enumerate(entries):
            if i >= frame.locator(f"#{grid_name}_tblGridContent tr.trContent").count():
                frame.evaluate(
                    "() => sectionCostCenterAllocation_Add('Add','sectionCostCenterAllocation')"
                )
            _edit(
                frame,
                grid_name,
                i,
                cols["CostProfitCatName"],
                center["category"],
                select=True,
            )
            _edit(
                frame,
                grid_name,
                i,
                cols["CostProfitName"],
                center["center"],
                select=True,
            )
            _edit(
                frame, grid_name, i, cols["Narration"], allocation.get("comments", "")
            )
            _edit(
                frame,
                grid_name,
                i,
                cols["Amt"],
                str(Decimal(meta["LedgerAmt"]) * Decimal(allocation["percent"]) / 100),
            )
        if not frame.evaluate("() => SaveAndCloseCostCenterAllocation()"):
            raise ExpenseInputError(
                f"WFX chưa nhận đủ phân bổ Cost Center dòng {index + 1}."
            )
    verify_cost_centers(frame, index, allocations)


def verify_cost_centers(frame, index: int, allocations: list[dict]) -> None:
    from wfx_panel.automation.expense_invoice import ExpenseInputError

    meta = _metadata(frame, index)
    if not allocations:
        if str(meta.get("IsCostCenterMandatory", "0")) == "1":
            raise ExpenseInputError(
                f"Ledger dòng {index + 1} yêu cầu Cost Center trong sheet Cost Centers."
            )
        return
    expected = allocations
    if str(frame.evaluate("() => window.gHierarchyStructureForCostCenters")) != "1":
        # Flat WFX represents every category in a separate grid row, whereas
        # the workbook can group several categories into the same allocation.
        expected = [
            {**allocation, "centers": [center]}
            for allocation in allocations
            for center in allocation["centers"]
        ]
    if _signature(read_cost_centers(frame, meta)) != _signature(expected):
        raise ExpenseInputError(
            f"Cost Center dòng {index + 1} đã thay đổi hoặc chưa được WFX nhận đủ."
        )
