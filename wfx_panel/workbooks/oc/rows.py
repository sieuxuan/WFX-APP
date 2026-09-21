"""Đọc từng dòng file thành bản ghi EDI đã kiểm tra.

Mỗi file chỉ được chứa MỘT Buyer. Với OC New, Buyer/Season/Order Type/Currency
chỉ bắt buộc ở dòng dữ liệu đầu tiên; dòng sau để trống thì kế thừa."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from wfx_panel.workbooks.oc.schema import (
    BUYER_OPTIONS,
    DATE_HEADERS,
    DESTINATION_COUNTRY_MARKET,
    EDI_HEADERS,
    FACTORY_OPTIONS,
    FORM_HEADERS,
    INPUT_HEADERS,
    INPUT_SHEET_NAME,
    NEW_REQUIRED_FORM_COLUMNS,
    ORDER_TYPE_OPTIONS,
    PO_TYPE_OPTIONS,
    REVISE_REQUIRED_HEADERS,
    SIMPLE_NEW_COMMON_COLUMNS,
    SIMPLE_NEW_OPTIONAL_COLUMNS,
    OCWorkbookError,
)
from wfx_panel.workbooks.oc.template import _nonempty_rows
from wfx_panel.workbooks.oc.values import (
    _canonical_option,
    _date_value,
    _decimal,
    _ensure_headers,
    _is_zero_quantity,
    _lookup_lists,
    _normalise_text,
    _safe_text,
    _validate_delivery_dates,
)


def _simple_new_rows(workbook: Any) -> tuple[str, list[list[Any]], tuple[str, ...]]:
    sheet = workbook[INPUT_SHEET_NAME]
    _ensure_headers(
        [sheet.cell(1, column).value for column in range(1, len(INPUT_HEADERS) + 1)],
        INPUT_HEADERS,
        INPUT_SHEET_NAME,
    )
    source_rows = _nonempty_rows(sheet, 2, len(INPUT_HEADERS))
    if not source_rows:
        raise OCWorkbookError(
            "OC_FILE_EMPTY",
            f"{INPUT_SHEET_NAME} chưa có dòng đơn hàng nào từ dòng 2.",
        )
    errors: list[str] = []
    warnings: list[str] = []
    prepared: list[dict[str, Any]] = []
    buyers: dict[str, str] = {}
    seen_keys: set[tuple[str, ...]] = set()
    known_buyers = {item.casefold() for item in BUYER_OPTIONS}
    known_factories = {item.casefold() for item in FACTORY_OPTIONS}
    skipped_zero_units = 0
    common_values = {
        index: source_rows[0][1][index] for index in SIMPLE_NEW_COMMON_COLUMNS
    }
    countries = {
        reference.casefold(): country_market
        for reference, country_market in DESTINATION_COUNTRY_MARKET.items()
    }
    for row_number, values in source_rows:
        values = list(values)
        for index, common_value in common_values.items():
            if values[index] in (None, ""):
                values[index] = common_value
        if _is_zero_quantity(values[19]):
            skipped_zero_units += 1
            continue
        missing = [
            INPUT_HEADERS[index]
            for index in range(len(INPUT_HEADERS))
            if index not in SIMPLE_NEW_OPTIONAL_COLUMNS
            if values[index] in (None, "")
        ]
        if missing:
            errors.append(
                f"Dòng {row_number}: thiếu {', '.join(missing[:5])}"
                + ("…" if len(missing) > 5 else ".")
            )
            continue
        try:
            text = [
                _safe_text(value, INPUT_HEADERS[index], row_number)
                for index, value in enumerate(values)
            ]
            buyer = text[0]
            factory = text[4]
            order_type = _canonical_option(
                values[2], "Order Type", row_number, ORDER_TYPE_OPTIONS
            )
            payment_terms = text[13]
            zone = _canonical_option(
                values[21],
                "PO Type (Zone)",
                row_number,
                PO_TYPE_OPTIONS,
                default="FOB",
            )
            buyers.setdefault(buyer.casefold(), buyer)
            if buyer.casefold() not in known_buyers:
                warning = (
                    f"Buyer '{buyer}' chưa có trong danh sách gợi ý; "
                    "app sẽ yêu cầu khớp chính xác trên WFX."
                )
                if warning not in warnings:
                    warnings.append(warning)
            if factory.casefold() not in known_factories:
                warning = (
                    f"Factory '{factory}' chưa có trong danh sách gợi ý; "
                    "WFX sẽ kiểm tra khi Process Package."
                )
                if warning not in warnings:
                    warnings.append(warning)
            country_key = text[14].casefold()
            if country_key not in countries:
                errors.append(
                    f"Dòng {row_number}: Country '{text[14]}' chưa có mapping Market."
                )
                destination, market = text[14], ""
            else:
                destination, market = countries[country_key]
            buyer_order_date = _date_value(values[10], INPUT_HEADERS[10], row_number)
            delivery_date = _date_value(values[11], INPUT_HEADERS[11], row_number)
            raw_material_eta = _date_value(values[12], INPUT_HEADERS[12], row_number)
            price = _decimal(values[18], INPUT_HEADERS[18], row_number)
            units = _decimal(values[19], INPUT_HEADERS[19], row_number)
            extra = (
                Decimal(0)
                if values[22] in (None, "")
                else _decimal(values[22], INPUT_HEADERS[22], row_number)
            )
            errors.extend(
                _validate_delivery_dates(
                    buyer_order_date,
                    raw_material_eta,
                    delivery_date,
                    row_number,
                )
            )
            if price <= 0:
                errors.append(f"Dòng {row_number}: Selling Price phải lớn hơn 0.")
            if units <= 0 or units != units.to_integral_value():
                errors.append(f"Dòng {row_number}: Units phải là số nguyên lớn hơn 0.")
            if extra < 0:
                errors.append(f"Dòng {row_number}: Extra Production % không được âm.")
            duplicate_key = tuple(
                item.casefold()
                for item in (text[5], text[7], text[8], text[15], text[17])
            )
            if duplicate_key in seen_keys:
                errors.append(
                    f"Dòng {row_number}: trùng PO/Style/Color/Size với dòng trước."
                )
            seen_keys.add(duplicate_key)
            prepared.append(
                {
                    "buyer": buyer,
                    "season": text[1],
                    "order_type": order_type,
                    "currency": text[3],
                    "factory": factory,
                    "ship_ref": text[5],
                    "article": text[6],
                    "buyer_style": text[7],
                    "buyer_po": text[8],
                    "summary_ref": text[9],
                    "buyer_order_date": buyer_order_date,
                    "delivery_date": delivery_date,
                    "raw_material_eta": raw_material_eta,
                    "payment_terms": payment_terms,
                    "destination": destination,
                    "market": market,
                    "color": f"{text[15]}^{text[16]}",
                    "size": text[17],
                    "price": price,
                    "units": units,
                    "internal_lot": text[20],
                    "zone": zone,
                    "extra": extra,
                    "buyer_lot": text[23],
                }
            )
        except OCWorkbookError as error:
            errors.extend(error.errors or (f"Dòng {row_number}: {error.message}",))
    if len(buyers) > 1:
        errors.append(
            "File có nhiều Buyer: " + ", ".join(sorted(buyers.values()))
            + ". Mỗi lần EDI chỉ upload một Buyer."
        )
    if errors:
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            f"Workbook có {len(errors)} lỗi cần sửa trước khi upload.",
            errors[:100],
        )
    if not prepared:
        raise OCWorkbookError(
            "OC_FILE_EMPTY",
            "Không còn dòng Upload OC nào sau khi bỏ các dòng có Units = 0.",
        )
    if skipped_zero_units:
        warnings.append(
            f"App đã bỏ qua {skipped_zero_units} dòng có Units = 0."
        )

    totals: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for item in prepared:
        totals[
            (
                item["ship_ref"].casefold(),
                item["summary_ref"].casefold(),
                item["buyer_style"].casefold(),
            )
        ] += item["units"]
    output_rows: list[list[Any]] = []
    for item in prepared:
        key = (
            item["ship_ref"].casefold(),
            item["summary_ref"].casefold(),
            item["buyer_style"].casefold(),
        )
        row = [None] * len(EDI_HEADERS)
        output_values = {
            "Factory": item["factory"],
            "Ship Under PO Ref": item["ship_ref"],
            "Article": item["article"],
            "Buyer": item["buyer"],
            "Currency": item["currency"],
            "Season": item["season"],
            "Country of Origin": "Vietnam",
            "Payment Terms": item["payment_terms"],
            "Buyer PO Num": item["buyer_po"],
            "Summary Buyer Order Ref": item["summary_ref"],
            "Market Buyer Order Ref": item["summary_ref"],
            "Destination Buyer Order Ref": item["summary_ref"],
            "Delivery Buyer Order Ref": item["summary_ref"],
            "Buyer Order Date": item["buyer_order_date"],
            "Order Type": item["order_type"],
            "Mode of Shipment": "AIR/SEA",
            "Buyer Delivery Date": item["delivery_date"],
            "OC Delivery Date": item["delivery_date"],
            "Raw Matetrial ETA": item["raw_material_eta"],
            "Country of Final Destination": item["destination"],
            "Final Destination": item["destination"],
            "Market": item["market"],
            "Buyer Style Ref.": item["buyer_style"],
            "Color": item["color"],
            "Size": item["size"],
            "Total Qty": totals[key],
            "Price": item["price"],
            "Units": item["units"],
            "Zone": item["zone"],
            "Internal Lot No.": item["internal_lot"],
            "Buyer Lot No.": item["buyer_lot"] or None,
            "Fulfillment Type": "Back Order",
            "FirstBuyerDeliveryDate": item["delivery_date"],
            "Extra Production %": item["extra"],
        }
        for header, value in output_values.items():
            row[EDI_HEADERS.index(header)] = value
        output_rows.append(row)
    return next(iter(buyers.values())), output_rows, tuple(warnings)


def _new_rows(workbook: Any) -> tuple[str, list[list[Any]], tuple[str, ...]]:
    if INPUT_SHEET_NAME in workbook.sheetnames:
        return _simple_new_rows(workbook)
    if "FORM" not in workbook.sheetnames:
        raise OCWorkbookError(
            "OC_TEMPLATE_SHEET_MISSING",
            f"Thiếu sheet {INPUT_SHEET_NAME} hoặc FORM trong workbook Upload OC.",
        )
    sheet = workbook["FORM"]
    _ensure_headers(
        [sheet.cell(5, column).value for column in range(1, 21)],
        FORM_HEADERS,
        "FORM",
    )
    buyer = _safe_text(sheet["B1"].value, "Buyer", 1)
    season = _safe_text(sheet["B2"].value, "Season", 2)
    order_type = _safe_text(sheet["B3"].value, "Order Type", 3)
    currency = _safe_text(sheet["B4"].value, "Currency", 4)
    metadata_errors = [
        f"{label} (ô {cell}) không được để trống."
        for label, cell, value in (
            ("Buyer", "B1", buyer),
            ("Season", "B2", season),
            ("Order Type", "B3", order_type),
            ("Currency", "B4", currency),
        )
        if not value
    ]
    if metadata_errors:
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            "Thông tin chung trong FORM chưa đầy đủ.",
            metadata_errors,
        )
    order_type = _canonical_option(
        order_type, "Order Type", 3, ORDER_TYPE_OPTIONS
    )
    factories, buyers, countries = _lookup_lists(workbook)
    if buyer.casefold() not in buyers:
        metadata_errors.append(f"Buyer '{buyer}' không có trong THONG TIN.")

    source_rows = _nonempty_rows(sheet, 6, 20)
    if not source_rows:
        raise OCWorkbookError(
            "OC_FILE_EMPTY",
            "FORM chưa có dòng đơn hàng nào từ dòng 6.",
        )

    errors = list(metadata_errors)
    prepared: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, ...]] = set()
    skipped_zero_units = 0
    for row_number, values in source_rows:
        if _is_zero_quantity(values[15]):
            skipped_zero_units += 1
            continue
        missing = [
            FORM_HEADERS[index]
            for index in NEW_REQUIRED_FORM_COLUMNS
            if values[index] in (None, "")
        ]
        if missing:
            errors.append(
                f"Dòng {row_number}: thiếu {', '.join(missing[:5])}"
                + ("…" if len(missing) > 5 else ".")
            )
            continue
        try:
            text = [
                _safe_text(value, FORM_HEADERS[index], row_number)
                for index, value in enumerate(values)
            ]
            factory = text[0]
            country_key = text[10].casefold()
            if factory.casefold() not in factories:
                errors.append(
                    f"Dòng {row_number}: Factory '{factory}' không có trong THONG TIN."
                )
            if country_key not in countries:
                errors.append(
                    f"Dòng {row_number}: Country '{text[10]}' không có mapping Market."
                )
                destination, market = text[10], ""
            else:
                destination, market = countries[country_key]
            buyer_order_date = _date_value(values[6], FORM_HEADERS[6], row_number)
            delivery_date = _date_value(values[7], FORM_HEADERS[7], row_number)
            raw_material_eta = _date_value(values[8], FORM_HEADERS[8], row_number)
            price = _decimal(values[14], FORM_HEADERS[14], row_number)
            units = _decimal(values[15], FORM_HEADERS[15], row_number)
            extra = (
                Decimal(0)
                if values[18] in (None, "")
                else _decimal(values[18], FORM_HEADERS[18], row_number)
            )
            payment_terms = text[9]
            zone = _canonical_option(
                values[17],
                "PO Type",
                row_number,
                PO_TYPE_OPTIONS,
                default="FOB",
            )
            errors.extend(
                _validate_delivery_dates(
                    buyer_order_date,
                    raw_material_eta,
                    delivery_date,
                    row_number,
                )
            )
            if price <= 0:
                errors.append(f"Dòng {row_number}: Selling Price phải lớn hơn 0.")
            if units <= 0 or units != units.to_integral_value():
                errors.append(f"Dòng {row_number}: Units phải là số nguyên lớn hơn 0.")
            if extra < 0:
                errors.append(f"Dòng {row_number}: Extra Production không được âm.")
            duplicate_key = tuple(
                item.casefold()
                for item in (text[1], text[3], text[4], text[11], text[13])
            )
            if duplicate_key in seen_keys:
                errors.append(
                    f"Dòng {row_number}: trùng PO/Style/Color/Size với dòng trước."
                )
            seen_keys.add(duplicate_key)
            prepared.append(
                {
                    "source_row": row_number,
                    "factory": factory,
                    "ship_ref": text[1],
                    "article": text[2],
                    "buyer_style": text[3],
                    "buyer_po": text[4],
                    "summary_ref": text[5],
                    "buyer_order_date": buyer_order_date,
                    "delivery_date": delivery_date,
                    "raw_material_eta": raw_material_eta,
                    "payment_terms": payment_terms,
                    "destination": destination,
                    "market": market,
                    "color": f"{text[11]}^{text[12]}",
                    "size": text[13],
                    "price": price,
                    "units": units,
                    "internal_lot": text[16],
                    "zone": zone,
                    "extra": extra,
                    "buyer_lot": text[19],
                }
            )
        except OCWorkbookError as error:
            errors.extend(error.errors or (f"Dòng {row_number}: {error.message}",))

    if errors:
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            f"Workbook có {len(errors)} lỗi cần sửa trước khi upload.",
            errors[:100],
        )
    if not prepared:
        raise OCWorkbookError(
            "OC_FILE_EMPTY",
            "Không còn dòng Upload OC nào sau khi bỏ các dòng có Units = 0.",
        )

    totals: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for item in prepared:
        totals[
            (
                item["ship_ref"].casefold(),
                item["summary_ref"].casefold(),
                item["buyer_style"].casefold(),
            )
        ] += item["units"]

    output_rows: list[list[Any]] = []
    for item in prepared:
        key = (
            item["ship_ref"].casefold(),
            item["summary_ref"].casefold(),
            item["buyer_style"].casefold(),
        )
        row = [None] * len(EDI_HEADERS)
        values = {
            "Factory": item["factory"],
            "Ship Under PO Ref": item["ship_ref"],
            "Article": item["article"],
            "Buyer": buyer,
            "Currency": currency,
            "Season": season,
            "Country of Origin": "Vietnam",
            "Payment Terms": item["payment_terms"],
            "Buyer PO Num": item["buyer_po"],
            "Summary Buyer Order Ref": item["summary_ref"],
            "Market Buyer Order Ref": item["summary_ref"],
            "Destination Buyer Order Ref": item["summary_ref"],
            "Delivery Buyer Order Ref": item["summary_ref"],
            "Buyer Order Date": item["buyer_order_date"],
            "Order Type": order_type,
            "Mode of Shipment": "AIR/SEA",
            "Buyer Delivery Date": item["delivery_date"],
            "OC Delivery Date": item["delivery_date"],
            "Raw Matetrial ETA": item["raw_material_eta"],
            "Country of Final Destination": item["destination"],
            "Final Destination": item["destination"],
            "Market": item["market"],
            "Buyer Style Ref.": item["buyer_style"],
            "Color": item["color"],
            "Size": item["size"],
            "Total Qty": totals[key],
            "Price": item["price"],
            "Units": item["units"],
            "Zone": item["zone"],
            "Internal Lot No.": item["internal_lot"],
            "Buyer Lot No.": item["buyer_lot"] or None,
            "Fulfillment Type": "Back Order",
            "FirstBuyerDeliveryDate": item["delivery_date"],
            "Extra Production %": item["extra"],
        }
        for header, value in values.items():
            row[EDI_HEADERS.index(header)] = value
        output_rows.append(row)
    warnings = (
        (f"App đã bỏ qua {skipped_zero_units} dòng có Units = 0.",)
        if skipped_zero_units
        else ()
    )
    return buyer, output_rows, warnings


def _revise_rows(workbook: Any) -> tuple[str, list[list[Any]], tuple[str, ...]]:
    if "Sheet1" not in workbook.sheetnames:
        raise OCWorkbookError(
            "OC_TEMPLATE_SHEET_MISSING",
            "File Revise OC phải có sheet Sheet1.",
        )
    sheet = workbook["Sheet1"]
    _ensure_headers(
        [sheet.cell(1, column).value for column in range(1, len(EDI_HEADERS) + 1)],
        EDI_HEADERS,
        "Sheet1",
    )
    source_rows = _nonempty_rows(sheet, 2, len(EDI_HEADERS))
    if not source_rows:
        raise OCWorkbookError("OC_FILE_EMPTY", "Sheet1 chưa có dữ liệu Revise OC.")

    indexes = {header: index for index, header in enumerate(EDI_HEADERS)}
    errors: list[str] = []
    buyers: dict[str, str] = {}
    prepared: list[list[Any]] = []
    seen_keys: set[tuple[str, ...]] = set()
    skipped_zero_units = 0
    for row_number, values in source_rows:
        if _is_zero_quantity(values[indexes["Units"]]):
            skipped_zero_units += 1
            continue
        text_values: dict[str, str] = {}
        try:
            for header in EDI_HEADERS:
                value = values[indexes[header]]
                if header not in DATE_HEADERS and not isinstance(value, (int, float, Decimal)):
                    text_values[header] = _safe_text(value, header, row_number)
            missing = [
                header
                for header in REVISE_REQUIRED_HEADERS
                if values[indexes[header]] in (None, "")
            ]
            if missing:
                errors.append(
                    f"Dòng {row_number}: thiếu {', '.join(sorted(missing)[:5])}"
                    + ("…" if len(missing) > 5 else ".")
                )
                continue
            buyer = _safe_text(values[indexes["Buyer"]], "Buyer", row_number)
            buyers.setdefault(buyer.casefold(), buyer)
            for header in DATE_HEADERS:
                value = values[indexes[header]]
                if value not in (None, ""):
                    values[indexes[header]] = _date_value(value, header, row_number)
            values[indexes["Order Type"]] = _canonical_option(
                values[indexes["Order Type"]],
                "Order Type",
                row_number,
                ORDER_TYPE_OPTIONS,
            )
            values[indexes["Zone"]] = _canonical_option(
                values[indexes["Zone"]],
                "Zone",
                row_number,
                PO_TYPE_OPTIONS,
                default="FOB",
            )
            errors.extend(
                _validate_delivery_dates(
                    values[indexes["Buyer Order Date"]],
                    values[indexes["Raw Matetrial ETA"]],
                    values[indexes["Buyer Delivery Date"]],
                    row_number,
                    oc_delivery_date=values[indexes["OC Delivery Date"]],
                )
            )
            units = _decimal(values[indexes["Units"]], "Units", row_number)
            price = _decimal(values[indexes["Price"]], "Price", row_number)
            extra = (
                Decimal(0)
                if values[indexes["Extra Production %"]] in (None, "")
                else _decimal(
                    values[indexes["Extra Production %"]],
                    "Extra Production %",
                    row_number,
                )
            )
            if units <= 0 or units != units.to_integral_value():
                errors.append(f"Dòng {row_number}: Units phải là số nguyên lớn hơn 0.")
            if price <= 0:
                errors.append(f"Dòng {row_number}: Price phải lớn hơn 0.")
            if extra < 0:
                errors.append(f"Dòng {row_number}: Extra Production % không được âm.")
            values[indexes["Units"]] = units
            values[indexes["Price"]] = price
            values[indexes["Extra Production %"]] = extra
            duplicate_key = tuple(
                _normalise_text(values[indexes[header]]).casefold()
                for header in (
                    "Ship Under PO Ref",
                    "Delivery Buyer Order Ref",
                    "Buyer Style Ref.",
                    "Color",
                    "Size",
                )
            )
            if duplicate_key in seen_keys:
                errors.append(f"Dòng {row_number}: trùng Delivery/Style/Color/Size.")
            seen_keys.add(duplicate_key)
            prepared.append(values)
        except OCWorkbookError as error:
            errors.extend(error.errors or (f"Dòng {row_number}: {error.message}",))

    if len(buyers) > 1:
        errors.append(
            "File có nhiều Buyer: " + ", ".join(sorted(buyers.values()))
            + ". EDI chỉ cho chọn một Buyer mỗi lần upload."
        )
    if errors:
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            f"Workbook Revise OC có {len(errors)} lỗi cần sửa.",
            errors[:100],
        )
    if not prepared:
        raise OCWorkbookError(
            "OC_FILE_EMPTY",
            "Không còn dòng Revise OC nào sau khi bỏ các dòng có Units = 0.",
        )

    totals: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for row in prepared:
        key = tuple(
            _normalise_text(row[indexes[header]]).casefold()
            for header in (
                "Ship Under PO Ref",
                "Delivery Buyer Order Ref",
                "Buyer Style Ref.",
            )
        )
        totals[key] += row[indexes["Units"]]
    corrected = 0
    for row in prepared:
        key = tuple(
            _normalise_text(row[indexes[header]]).casefold()
            for header in (
                "Ship Under PO Ref",
                "Delivery Buyer Order Ref",
                "Buyer Style Ref.",
            )
        )
        expected = totals[key]
        current = row[indexes["Total Qty"]]
        try:
            current_number = Decimal(str(current).replace(",", ""))
        except (InvalidOperation, AttributeError, ValueError):
            current_number = Decimal("NaN")
        if current_number != expected:
            corrected += 1
        row[indexes["Total Qty"]] = expected
    warnings: list[str] = []
    if skipped_zero_units:
        warnings.append(
            f"App đã bỏ qua {skipped_zero_units} dòng có Units = 0."
        )
    if corrected:
        warnings.append(
            f"App đã tính lại Total Qty cho {corrected} dòng từ cột Units."
        )
    buyer = next(iter(buyers.values()))
    return buyer, prepared, tuple(warnings)
