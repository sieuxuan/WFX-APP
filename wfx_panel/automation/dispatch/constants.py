"""Selector, ngưỡng thời gian và snippet JS của luồng (GDN) Dispatch."""

from __future__ import annotations

from wfx_panel.automation._common import Callable

REPORT_URL = (
    "https://prosports.worldfashionexchange.com/WFXBase4.0/"
    "WFXBICustomReportView.aspx?"
    "BICustomReportID=966ae3a5-1edb-4f60-8290-2e3e630aa41f&"
    "Path=/WFXPSHLIVE/Production%20Reports/BuyerDispatchOrder_Invoice&"
    "ReportParams="
)


REPORT_DOC_NO_SELECTOR = "#rptCustomReportViewer_ctl04_ctl03_txtValue"


REPORT_VIEW_SELECTOR = "#rptCustomReportViewer_ctl04_ctl00"


REPORT_EXPORT_LINK_SELECTOR = (
    "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink"
)


REPORT_EXPORT_IMAGE_SELECTOR = (
    "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonImg"
)


REPORT_EXPORT_MENU_SELECTOR = "#rptCustomReportViewer_ctl05_ctl04_ctl00_Menu"


REPORT_EXCEL_SELECTOR = (
    f"{REPORT_EXPORT_MENU_SELECTOR} "
    'a[title="Excel"][onclick*="EXCELOPENXML"]'
)


EDI_MENU_XPATH = '//*[@id="0040_0020_0100"]/a'


PACKAGE_TYPE_SELECTOR = "#ddlPackageType"


PACKAGE_TYPE_VALUE = "Import"


PACKAGE_LABEL = "DecisionOne_BuyerOrderDispatch"


PACKAGE_VALUE = "2"


EDI_GRID_SELECTOR = "#gridEDIProductionOrder_tblGridContent"


EDI_UPLOAD_SELECTOR = "#sectionObjectAttachment input[type='file']"


EDI_CREATE_SELECTOR = (
    'table.clsSectionTitleBar[id="sectionEDIProductionOrder"] '
    "a.ToolLink"
)


REPORT_TIMEOUT_SECONDS = 100


PACKAGE_TIMEOUT_SECONDS = 100


TRANSACTION_TIMEOUT_SECONDS = 150


GDN_PROGRESS_TOTAL = 6


def _emit_progress(
    progress: Callable[..., None] | None,
    stage: str,
    message: str,
    step: int,
    *,
    state: str = "active",
) -> None:
    if progress is None:
        return
    try:
        progress(stage, message, step, GDN_PROGRESS_TOTAL, state=state)
    except Exception:
        # Tiến độ là UX phụ trợ; lỗi WebView không được làm hỏng transaction.
        pass


_EDI_ROWS_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const value = (row, selector) => {
    const element = row.querySelector(selector);
    return norm(element?.getAttribute('title') || element?.value ||
      element?.innerText || element?.textContent);
  };
  const table = document.querySelector('#gridEDIProductionOrder_tblGridContent');
  if (!table) return [];
  return [...table.querySelectorAll(':scope > tbody > tr')].map(row => ({
    row_id: row.getAttribute('rowid') || row.id || '',
    package_name: value(row, '#lblPackageName'),
    transaction: value(row, '#lblTransaction'),
    file_name: value(row, '#lblFileName'),
    processed_on: value(row, '#lblProcessedON'),
    status: value(row, '#lblStatus'),
    transaction_detail: value(row, '#lnkTransactionCreatedInWFX'),
    error: value(row, '#lblErrorMsg')
  })).filter(row => row.row_id);
}"""
