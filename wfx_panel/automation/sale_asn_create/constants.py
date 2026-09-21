"""Selector, nhãn và bảng tra cố định của form Sale ASN New."""

from __future__ import annotations

ADD_ORDER_XPATH = '//*[@id="sectionOrderDetails"]/tbody/tr/td[2]/span/div[3]'


PO_POPUP_SELECTOR = "#wfx_GMPOAsnSearch"


PO_RESULTS_TABLE_XPATH = '//*[@id="wfx_GMPOAsnSearch"]/div[3]/table'


PO_RESULTS_TABLE_SELECTOR = f"xpath={PO_RESULTS_TABLE_XPATH}"


PO_OK_XPATH = '//*[@id="wfx_GMPOAsnSearch"]/table[1]/tbody/tr/td[3]/table/tbody/tr/td[3]'


PO_OK_SELECTOR = f"xpath={PO_OK_XPATH}"


ORDER_GRID_SELECTOR = "#gridOrderDetails_tblGridContent"


PO_SEARCH_SELECTOR = (
    '#wfx_GMPOAsnSearch input[value="Search" i], '
    '#wfx_GMPOAsnSearch input[type="button"][onclick*="Search" i]'
)


PO_CONTINUE_SELECTOR = "#lnkAddnContinue"


STYLE_INPUT_SELECTORS = (
    "#txtStyle",
    "#txtStyleNo",
    "#txtArticle",
    "#txtBuyerStyleRef",
)


SALE_ASN_PO_SEARCH_FIELDS = ("po", "style", "destination")


SALE_ASN_PO_SEARCH_LABELS = {
    "po": "PO",
    "style": "Style",
    "destination": "Destination",
}


CONSIGNEE_ADDRESS_SELECTOR = (
    "#ddlConsigneeAddress, #Cell_ConsigneeAddress, #Cell_Consignee"
)


SHIP_TO_SELECTOR = "#ddlShipTo, #Cell_ShipTo"


PORT_OF_LOADING_SELECTORS = (
    "#Cell_AWBLoadingPort",
    "#Cell_BLMotherLoadingPort",
)


PORT_OF_LOADING_SELECTOR = ", ".join(PORT_OF_LOADING_SELECTORS)


SHIPMENT_MODE_SELECTOR = "#ddlShipmentMode"


# WFX đôi khi cần thêm vài giây để Ajax ghi Order Details sau Add & Continue.
# Chờ đủ ở đây giúp tránh mở/submit popup chồng lên request cũ nhưng vẫn không
# kéo dài các thao tác ngoài Add PO.
ORDER_GRID_SYNC_TIMEOUT_SECONDS = 40


PO_POPUP_RECOVERY_TIMEOUT_SECONDS = 40


SHIPMENT_DETAILS_TAB_SELECTOR = "#tabShipmentDetails"


SHIPMENT_DETAILS_GRID_SELECTOR = "#gridShipmentDetails_tblGridContent"


SUMMARY_TOTAL_GRID_SELECTOR = "#gridASNSummaryTotal_tblGridContent"


SHIPPING_MODE_VALUES = {
    "AIR": {
        "port_of_loading": "HAN - Hanoi",
        "delivery_terms": "FCA HANOI, VIET NAM",
    },
    "SEA": {
        "port_of_loading": "HPH - Haiphong",
        "delivery_terms": "FOB HAIPHONG, VIETNAM",
    },
    "COURIER": {
        "port_of_loading": "HAN - Hanoi",
        "delivery_terms": "EXW",
    },
}


_WFX_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


_WFX_MONTH_NUMBERS = {month.casefold(): index for index, month in enumerate(_WFX_MONTHS, 1)}


ORDER_FIELD_COLUMNS = {
    "carton": "colTotalNoOfCartons",
    "gw": "colTotalGrossWeight",
    "nw": "colTotalNetWeight",
    "cbm": "colTotalVolume",
    "fob_price": "colFFTextField1",
    "service_price": "colFFTextField2",
    "cargo_ready_date": "colFFDate1",
}


SHIPPING_FIELDS = (
    ("#Cell_InvoiceNo", "invoice_no", "value"),
    ("#Cell_InvoiceDate", "invoice_date", "value"),
    ("#Cell_ShippingBillNo", "shipping_bill_no", "value"),
    ("#Cell_ShippingBillDate", "shipping_bill_date", "value"),
    ("#Cell_ShipDate", "shipping_bill_date", "value"),
    ("#Cell_DestinationCountry", "destination", "exact"),
    ("#Cell_FinalDestination", "destination", "exact"),
    ("#ddlConsignorAddress", "__BILL-ADD - PSHK", "exact"),
    (CONSIGNEE_ADDRESS_SELECTOR, "consignee_address", "closest"),
    (SHIP_TO_SELECTOR, "ship_to", "closest"),
    (SHIPMENT_MODE_SELECTOR, "shipping_mode", "exact"),
    (PORT_OF_LOADING_SELECTOR, "port_of_loading", "exact"),
    ("#ddlDeliveryTerms", "delivery_terms", "exact"),
    ("#ddlFactory", "factory", "factory_first"),
)


SHIPPING_FIELD_LABELS = {
    "#Cell_InvoiceNo": "Invoice No.",
    "#Cell_InvoiceDate": "Invoice Date",
    "#Cell_ShippingBillNo": "Shipping Bill No.",
    "#Cell_ShippingBillDate": "Shipping Bill Date",
    "#Cell_ShipDate": "Ship Date",
    "#Cell_DestinationCountry": "Destination Country",
    "#Cell_FinalDestination": "Final Destination",
    "#ddlConsignorAddress": "Consignor Address",
    CONSIGNEE_ADDRESS_SELECTOR: "Consignee Address",
    SHIP_TO_SELECTOR: "Ship To",
    SHIPMENT_MODE_SELECTOR: "Shipment Mode",
    PORT_OF_LOADING_SELECTOR: "Port of Loading",
    "#ddlDeliveryTerms": "Delivery Terms",
    "#ddlFactory": "Factory",
}


SALE_ASN_STAGE_FRAME_SELECTORS = {
    "order_details": "#sectionOrderDetails",
    "style_details": "#tabStyleDetails",
    "shipping_info": "#tabShippingInfo",
}
