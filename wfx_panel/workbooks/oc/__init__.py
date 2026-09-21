"""Workbook OC: sinh form nhập, validate và dựng Sheet1 EDI 51 cột.

Trước đây là một file 1594 dòng. Nay tách theo tầng: ``schema`` → ``values`` →
``template``/``rows`` → ``upload``. Package re-export nguyên bề mặt cũ nên
caller và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
from collections import defaultdict  # noqa: F401
from collections.abc import Iterable  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from datetime import date, datetime  # noqa: F401
from decimal import Decimal, InvalidOperation  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401
from zipfile import BadZipFile, ZipFile  # noqa: F401

from openpyxl import Workbook, load_workbook  # noqa: F401
from openpyxl.comments import Comment  # noqa: F401
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: F401
from openpyxl.utils.datetime import from_excel  # noqa: F401
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: F401

from wfx_panel.workbooks.oc.rows import (  # noqa: F401
    _new_rows,
    _revise_rows,
    _simple_new_rows,
)
from wfx_panel.workbooks.oc.schema import (  # noqa: F401
    BUYER_OPTIONS,
    DATE_HEADERS,
    DESTINATION_COUNTRY_MARKET,
    EDI_HEADERS,
    FACTORY_OPTIONS,
    FORM_HEADERS,
    INPUT_COMMENTS,
    INPUT_HEADERS,
    INPUT_SHEET_NAME,
    MAX_ARCHIVE_ENTRIES,
    MAX_OC_ROWS,
    MAX_UNCOMPRESSED_BYTES,
    MAX_XLSX_BYTES,
    NEW_REQUIRED_FORM_COLUMNS,
    ORDER_TYPE_OPTIONS,
    PAYMENT_TERM_OPTIONS,
    PO_TYPE_OPTIONS,
    REFERENCE_SHEET_NAME,
    REVISE_REQUIRED_HEADERS,
    SIMPLE_NEW_COMMON_COLUMNS,
    SIMPLE_NEW_OPTIONAL_COLUMNS,
    OCWorkbookError,
    PreparedOCUpload,
)
from wfx_panel.workbooks.oc.template import (  # noqa: F401
    _nonempty_rows,
    write_oc_input_template,
)
from wfx_panel.workbooks.oc.upload import (  # noqa: F401
    _excel_value,
    _verify_static_output,
    _write_static_workbook,
    prepare_oc_workbook,
)
from wfx_panel.workbooks.oc.values import (  # noqa: F401
    _add_date_sequence_validation,
    _add_list_validation,
    _canonical_option,
    _date_value,
    _decimal,
    _ensure_headers,
    _ensure_input_values_only,
    _is_zero_quantity,
    _lookup_lists,
    _normalise_header,
    _normalise_text,
    _safe_text,
    _validate_delivery_dates,
    _validate_xlsx_archive,
)

__all__ = [
    "BUYER_OPTIONS",
    "DATE_HEADERS",
    "DESTINATION_COUNTRY_MARKET",
    "EDI_HEADERS",
    "FACTORY_OPTIONS",
    "FORM_HEADERS",
    "INPUT_COMMENTS",
    "INPUT_HEADERS",
    "INPUT_SHEET_NAME",
    "MAX_ARCHIVE_ENTRIES",
    "MAX_OC_ROWS",
    "MAX_UNCOMPRESSED_BYTES",
    "MAX_XLSX_BYTES",
    "NEW_REQUIRED_FORM_COLUMNS",
    "OCWorkbookError",
    "ORDER_TYPE_OPTIONS",
    "PAYMENT_TERM_OPTIONS",
    "PO_TYPE_OPTIONS",
    "PreparedOCUpload",
    "REFERENCE_SHEET_NAME",
    "REVISE_REQUIRED_HEADERS",
    "SIMPLE_NEW_COMMON_COLUMNS",
    "SIMPLE_NEW_OPTIONAL_COLUMNS",
    "prepare_oc_workbook",
    "write_oc_input_template",
]
