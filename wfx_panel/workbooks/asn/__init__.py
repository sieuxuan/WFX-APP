"""Ghép Buyer Invoice và Packing List thành một workbook giữ nguyên format.

Trước đây là một file 1315 dòng. Nay tách theo tầng: ``ooxml`` (gói zip) →
``cells`` → ``layout``/``packing`` → ``merge``. Package re-export nguyên bề mặt
cũ nên caller và test không đổi.

Invoice luôn đứng trước PKL; nhiều sheet thì xếp xen kẽ Invoice 1, PKL 1,
Invoice 2, PKL 2 cho đến hết.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import math  # noqa: F401
import re  # noqa: F401
import xml.etree.ElementTree as ET  # noqa: F401
from copy import deepcopy  # noqa: F401
from pathlib import Path, PurePosixPath  # noqa: F401
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile  # noqa: F401

from openpyxl import load_workbook  # noqa: F401

from wfx_panel.workbooks.asn.cells import (  # noqa: F401
    _cell_map,
    _cell_row,
    _cell_text,
    _clear_merged_cell_value,
    _column_index,
    _copy_cell_value,
    _existing_merge_ranges,
    _header_text,
    _merge_range_is_free,
    _merged_cell_ends,
    _report_header_text,
)
from wfx_panel.workbooks.asn.layout import (  # noqa: F401
    _PACKING_COLUMN_MINIMUM_WIDTHS,
    _column_width,
    _display_units,
    _fit_packing_measurement_columns,
    _fit_reports_to_a4,
    _fit_wrapped_report_rows,
    _needed_row_lines,
    _set_a4_page_setup,
    _set_column_minimum_width,
    _sheet_column_widths,
    _wrapped_style_ids,
)
from wfx_panel.workbooks.asn.merge import (  # noqa: F401
    merge_sale_asn_reports,
    sale_asn_sheet_names,
)
from wfx_panel.workbooks.asn.ooxml import (  # noqa: F401
    _STYLE_SECTION_ORDER,
    CONTENT_TYPE_NS,
    DOC_REL_NS,
    MAIN_NS,
    PACKAGE_REL_NS,
    WORKSHEET_CONTENT_TYPE,
    WORKSHEET_REL_TYPE,
    ASNWorkbookError,
    _append_components,
    _merge_number_formats,
    _merge_packages,
    _merge_styles,
    _next_relationship_id,
    _relationship_member,
    _remap_sheet_styles,
    _remap_xf,
    _safe_sheet_title,
    _set_count,
    _shared_strings,
    _sheet_records,
    _style_section,
    _tag,
    _update_defined_names,
    _xml,
    _xml_bytes,
)
from wfx_panel.workbooks.asn.packing import (  # noqa: F401
    _JL_BUYER,
    _JL_PACKING_HEADERS,
    _JL_PACKING_MEASUREMENTS,
    _TRUEWERK_BUYER,
    _TRUEWERK_PACKING_DETAIL_HEADERS,
    _TRUEWERK_PACKING_HEADERS,
    _TRUEWERK_PACKING_MEASUREMENTS,
    _is_zero_measurement,
    _merge_jl_packing_measurements,
    _merge_jl_packing_sheet,
    _merge_truewerk_packing_measurements,
    _merge_truewerk_packing_sheet,
    _truewerk_po_base,
)

__all__ = [
    "ASNWorkbookError",
    "CONTENT_TYPE_NS",
    "DOC_REL_NS",
    "MAIN_NS",
    "PACKAGE_REL_NS",
    "WORKSHEET_CONTENT_TYPE",
    "WORKSHEET_REL_TYPE",
    "merge_sale_asn_reports",
    "sale_asn_sheet_names",
]
