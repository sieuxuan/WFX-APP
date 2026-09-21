"""Cột, giới hạn và danh sách tuỳ chọn của workbook OC.

EDI_HEADERS là hợp đồng 51 cột với WFX: Sheet1 sinh ra chỉ chứa giá trị, không
công thức, không macro và không phụ thuộc phiên bản Excel."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_XLSX_BYTES = 100 * 1024 * 1024


MAX_ARCHIVE_ENTRIES = 2_000


MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024


MAX_OC_ROWS = 10_000


FORM_HEADERS = (
    "Factory",
    "Ship Under PO Ref",
    "Article Code",
    "Buyer Style Ref",
    "Buyer PO Num",
    "Summary Buyer Order Ref",
    "Buyer Order Date",
    "Order/Buyer Delivery Date",
    "Raw Matetrial ETA Date",
    "Payment Terms",
    "Country of Final Destination",
    "Color code",
    "Color name",
    "Size code",
    "Selling Price",
    "Units",
    "Internal Lot No.",
    "PO Type",
    "Extra Production",
    "Buyer Lot No.",
)


INPUT_SHEET_NAME = "OC INPUT"


REFERENCE_SHEET_NAME = "REFERENCES"


INPUT_HEADERS = (
    "Buyer",
    "Season",
    "Order Type",
    "Currency",
    "Factory",
    "Ship Under PO Ref",
    "Article Code",
    "Buyer Style Ref",
    "Buyer PO Num",
    "Summary Buyer Order Ref",
    "Buyer Order Date",
    "Buyer Delivery Date",
    "Raw Material ETA Date",
    "Payment Terms",
    "Country of Final Destination",
    "Color Code",
    "Color Name",
    "Size Code",
    "Selling Price",
    "Units",
    "Internal Lot No.",
    "PO Type (Zone)",
    "Extra Production %",
    "Buyer Lot No.",
)


FACTORY_OPTIONS = (
    "888 COMPANY LTD",
    "CELEBRITY FASHION VINA COMPANY LIMITED",
    "GARMENT 10 CORPORATION-JOINT STOCK COMPANY",
    "PRO SPORTS GIAO YEN GARMENT JOINT STOCK COMPANY",
    "HABAC EXPORT GARMENT JOINT STOCK COMPANY",
    "HANSOL VINA LTD COMPANY",
    "HUNG BINH GARMENT JOINT STOCK COMPANY",
    "PHU THO GARMENT JOINT STOCK COMPANY",
    "PROSPORTS GIAO THUY JOINT STOCK COMPANY",
    "PRO SPORTS HA NOI JSC",
    "SON HA GARMENT JOINT STOCK COMPANY",
    "TNG PHU BINH 1 BRANCH",
    "X20 JOINT STOCK COMPANY (HEAD OFFICE)",
    "FACTORY GARMENT BIM SON",
    "S&D THANH HOA CO.LTD",
    "X20 NGHE AN ONE MEMBER COMPANY LTD",
    "THANH TRI JOINT STOCK COMPANY",
    "THAGACO INTERNATIONAL INVESTMENT JSC",
    "HANA KOVI INC.",
    "THIEN AN PHU TEXTILE GARMENT JOINT STOCK COMPANY",
    "VIET THAI GARMENT EXPORT JOINT STOCK COMPANY",
    "S-LIFE JOINT STOCK COMPANY",
)


BUYER_OPTIONS = (
    "BIRDDOGS",
    "CORPORATE OFFICE - TRUEWERK",
    "DOITE",
    "FAM BRANDS",
    "FORTUNE SWIMWEAR LLC",
    "J.LINDEBERG",
    "JOCKEY",
    "ONEILL",
    "PARAGON FITWEAR, LLC",
    "PREMIER EXIM (HK) LTD.,",
    "REVOLUTIONRACE",
    "SWIM RX",
    "UFPRO",
)


ORDER_TYPE_OPTIONS = (
    "Confirmed",
    "Forecast",
    "SMS",
)


PAYMENT_TERM_OPTIONS = (
    "15% Deposit After Contract - 85% TT Before Shipment",
    "20% Deposit, Balance TT at Sight",
    "30 Days At Month End",
    "30% Advanced Before Shipment - 70% TT After Shipment",
    "30% Deposit + ROG + 30 Days",
    "30% Once Order Committed - 70% LC Irrevocable 30 Days",
    "40% Advanced Before Shipment - 60% TT After Shipment",
    "50% Deposit / 50% TT After 30 Days",
    "After Finished 30-45 Days",
    "By Bank Draft or TT Before Shipment",
    "Cash Before Delivery First 3 Shipments And Then 30 Days",
    "Credit of T/T 30 days",
    "Deposit 30% - 70% TT Against Shipment",
    "LC 45 Days",
    "LC 60 Days",
    "LC At Sight",
    "LC At Sight 30 Days",
    "OA 15 Days",
    "Payment 60 Days After Ex Works Date",
    "Payment Within 90 Days",
    "ROG 30 Days",
    "TT 30% Deposit - 70% Before Shipping",
    "TT After Shipment",
    "TT After Shipment 10 Days",
    "TT After Shipment 15 Days",
    "TT After Shipment 20 Days",
    "TT After Shipment 30 Days",
    "TT After Shipment 40 Days",
    "TT After Shipment 45 Days",
    "TT After Shipment 60 Days",
    "TT After Shipment 90 Days",
    "TT Against Documents",
    "TT Before ETA",
    "TT Before Shipment",
    "TT Before Shipment 30 Days",
    "TT In Advance For First Order / TT After 30 Days For Next Order",
    "TT Payment",
    "Wire Payment 90 Days",
)


PO_TYPE_OPTIONS = ("CM", "CMT", "FOB", "DDP")


DESTINATION_COUNTRY_MARKET = {
    "TEXPORT": ("Sweden", "Europe"),
    "CA": ("Canada", "America"),
    "DO": ("Dominican Republic", "America"),
    "JP": ("Japan", "Asia"),
    "US": ("United States", "America"),
    "KR": ("South Korea", "Asia"),
    "SG": ("Singapore", "Asia"),
    "TH": ("Thailand", "Asia"),
    "JLHQ": ("Sweden", "Europe"),
    "TW": ("Taiwan", "Asia"),
    "JLCN": ("China", "Asia"),
    "AU": ("Australia", "Australia"),
    "HK": ("Hong Kong", "Asia"),
    "AE": ("United Arab Emirates-AE", "Asia"),
    "GE": ("Germany", "Europe"),
    "JLHQ STUDI": ("Sweden", "Europe"),
    "SW": ("Switzerland", "Europe"),
    "AUT": ("Austria", "Europe"),
    "SP": ("Spain", "Europe"),
    "NW": ("Norway", "Europe"),
    "UK": ("United Kingdom", "Europe"),
    "IT": ("Italy", "Europe"),
    "FR": ("France", "Europe"),
    "JLUS": ("United States", "America"),
    "United States-US-Hanger": ("United States-US-Hanger", "America"),
    "United States-US-Flat": ("United States-US-Flat", "America"),
    "Chile": ("Chile", "America"),
    "Vietnam": ("Vietnam", "Asia"),
    "New Zealand": ("New Zealand", "Australia"),
    "Sweden": ("Sweden", "Europe"),
    "Canada": ("Canada", "America"),
    "Dominican Republic": ("Dominican Republic", "America"),
    "Japan": ("Japan", "Asia"),
    "United States": ("United States", "America"),
    "South Korea": ("South Korea", "Asia"),
    "Singapore": ("Singapore", "Asia"),
    "Thailand": ("Thailand", "Asia"),
    "Taiwan": ("Taiwan", "Asia"),
    "China": ("China", "Asia"),
    "Australia": ("Australia", "Australia"),
    "Hong Kong": ("Hong Kong", "Asia"),
    "United Arab Emirates": ("United Arab Emirates-AE", "Asia"),
    "United Arab Emirates-AE": ("United Arab Emirates-AE", "Asia"),
    "Germany": ("Germany", "Europe"),
    "Switzerland": ("Switzerland", "Europe"),
    "Austria": ("Austria", "Europe"),
    "Spain": ("Spain", "Europe"),
    "Norway": ("Norway", "Europe"),
    "United Kingdom": ("United Kingdom", "Europe"),
    "Italy": ("Italy", "Europe"),
    "France": ("France", "Europe"),
    "ZALANDOPHO": ("Germany", "Europe"),
    "ES": ("Spain", "Europe"),
    "ID": ("Indonesia", "Asia"),
    "Republic of Slovenia": ("Republic of Slovenia", "Europe"),
}


INPUT_COMMENTS = {
    "Buyer": (
        "Chọn Buyer đúng với Buyer sẽ chọn tại EDI Buyer PO. Chỉ cần nhập ở "
        "dòng dữ liệu đầu tiên."
    ),
    "Season": (
        "Season phải giống Season trong Techpack Style. Chỉ cần nhập ở dòng "
        "dữ liệu đầu tiên."
    ),
    "Order Type": (
        "Chọn Confirmed, Forecast hoặc SMS. Chỉ cần nhập ở dòng dữ liệu đầu tiên."
    ),
    "Currency": "Chỉ cần nhập Currency ở dòng dữ liệu đầu tiên.",
    "Ship Under PO Ref": "Mã PO dùng để gom các dòng Color/Size cùng đơn hàng.",
    "Article Code": "Article Code lấy trên WFX.",
    "Buyer Style Ref": "Buyer Style Ref phải giống Techpack Style.",
    "Buyer PO Num": "Thường giống Summary Buyer Order Ref.",
    "Buyer Order Date": "Nhập ngày theo dd-mm-yyyy; phải trước Raw Material ETA.",
    "Buyer Delivery Date": "Nhập ngày theo dd-mm-yyyy; phải sau Raw Material ETA.",
    "Raw Material ETA Date": (
        "Nhập ngày theo dd-mm-yyyy; phải sau Buyer Order Date và trước "
        "Buyer Delivery Date."
    ),
    "Payment Terms": (
        "Có thể chọn điều khoản trong danh sách gợi ý hoặc nhập giá trị đang có "
        "trên WFX."
    ),
    "Country of Final Destination": (
        "Có thể nhập tên quốc gia hoặc mã Destination ref trong danh sách. App "
        "tự chuẩn hóa Final Destination và Market."
    ),
    "Color Code": "Color Code lấy trên WFX.",
    "Color Name": "Tên màu lấy trên WFX.",
    "Size Code": "Size Code lấy trên WFX.",
    "Selling Price": "Phải lớn hơn 0 và không nhỏ hơn Costing.",
    "Units": "Số nguyên; dòng có Units = 0 sẽ được app tự bỏ qua.",
    "Internal Lot No.": "Chia theo Buy hoặc số nội bộ.",
    "PO Type (Zone)": "Để trống nếu dùng FOB; hoặc chọn CM/CMT/FOB/DDP.",
    "Extra Production %": "Có thể để trống; app tự xuất 0.",
    "Buyer Lot No.": "Tuỳ chọn; dùng theo quy định Buyer.",
}


EDI_HEADERS = (
    "Factory",
    "Ship Under PO Ref",
    "Article",
    "Buyer",
    "Buyer Division/Dept",
    "Currency",
    "Season",
    "Country of Origin",
    "Place of Receipt by Pre-Carrier",
    "Prod. Capacity Booking No",
    "Order Initiation Date",
    "Payment Terms",
    "Buyer PO Num",
    "Summary Buyer Order Ref",
    "Market Buyer Order Ref",
    "Destination Buyer Order Ref",
    "Delivery Buyer Order Ref",
    "Buyer Order Date",
    "Order Type",
    "Mode of Shipment",
    "Buyer Delivery Date",
    "OC Delivery Date",
    "PCD Date",
    "Original GAC Date",
    "GAC Date",
    "Raw Matetrial ETA",
    "Country of Final Destination",
    "Final Destination",
    "Market",
    "Buyer Style Ref.",
    "Packing Type",
    "Packing Option/Flat Pack)",
    "Color",
    "Size",
    "Total Qty",
    "Price",
    "Units",
    "Delivery Terms",
    "Zone",
    "Internal Lot No.",
    "Buyer Lot No.",
    "DeliveryOCID",
    "Fulfillment Type",
    "Initial PCD Date",
    "FirstBuyerDeliveryDate",
    "Packing Code(SKU)",
    "Make to Stock",
    "Split",
    "Other Instruction",
    "Extra Production %",
    "Upcharge",
)


DATE_HEADERS = frozenset(
    {
        "Buyer Order Date",
        "Buyer Delivery Date",
        "OC Delivery Date",
        "PCD Date",
        "Original GAC Date",
        "GAC Date",
        "Raw Matetrial ETA",
        "Initial PCD Date",
        "FirstBuyerDeliveryDate",
    }
)


NEW_REQUIRED_FORM_COLUMNS = frozenset(range(17))


SIMPLE_NEW_OPTIONAL_COLUMNS = frozenset({21, 22, 23})


SIMPLE_NEW_COMMON_COLUMNS = frozenset({0, 1, 2, 3})


REVISE_REQUIRED_HEADERS = frozenset(
    {
        "Factory",
        "Ship Under PO Ref",
        "Article",
        "Buyer",
        "Currency",
        "Season",
        "Payment Terms",
        "Buyer PO Num",
        "Summary Buyer Order Ref",
        "Market Buyer Order Ref",
        "Destination Buyer Order Ref",
        "Delivery Buyer Order Ref",
        "Buyer Order Date",
        "Order Type",
        "Mode of Shipment",
        "Buyer Delivery Date",
        "OC Delivery Date",
        "Raw Matetrial ETA",
        "Country of Final Destination",
        "Final Destination",
        "Market",
        "Buyer Style Ref.",
        "Color",
        "Size",
        "Price",
        "Units",
        "Internal Lot No.",
        "DeliveryOCID",
        "Fulfillment Type",
    }
)


class OCWorkbookError(ValueError):
    def __init__(self, code: str, message: str, errors: Iterable[str] = ()):
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = tuple(errors)


@dataclass(frozen=True)
class PreparedOCUpload:
    mode: str
    buyer: str
    row_count: int
    upload_path: Path
    seasons: tuple[str, ...] = ()
    po_count: int = 0
    style_count: int = 0
    total_units: int | float = 0
    warnings: tuple[str, ...] = ()
