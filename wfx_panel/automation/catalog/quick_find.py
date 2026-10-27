"""Đường nhanh tìm theo Article Code: hỏi thẳng datasource của Catalog Grid.

Nút Code trên grid chỉ làm đúng một việc::

    window.open('/wfx/wfx_ArticleDetail.aspx?ID=<ArticleID>&GroupID=<CGID>'
                '&ArticleSelection=&CatalogType=<..>&CatalogCompany=<..>'
                '&ComboCode=<Category>&StyleSheet=wfx_Style', 'ArticleDetail')

và grid lấy dữ liệu từ ``GET /WFXERPAPI/api/WFXCommon/GetData``, server lọc
``contains`` theo ``lnkArticleCode``. Gọi endpoint đó bằng ``fetch`` trong chính
frame grid (cookie + GUID của tab) cho kết quả trong khoảng 1 giây, thay vì
quét ngang Floating Filter, gõ, chờ debounce/render và ổn định grid (~3 giây).

Popup được mở bằng ``window.open`` TỪ frame grid để ``window.opener`` y hệt khi
người dùng tự click. Mọi tình huống không chắc chắn trả ``None`` để caller quay
về state machine DOM: thiếu frame grid/GUID/CompanyCode, fetch lỗi, server bỏ
qua điều kiện lọc, Style bị khóa link, ID không hợp lệ hoặc trình duyệt chặn
popup. Đường nhanh chỉ đọc; không có bước ghi dữ liệu WFX nào.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlencode

from wfx_panel.automation._common import (
    Any,
    Callable,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _result,
    _style_status_suffix,
    _write_log,
)
from wfx_panel.automation.catalog.grid import _catalog_grid_frame

GET_DATA_PATH = "/WFXERPAPI/api/WFXCommon/GetData"
ARTICLE_DETAIL_PATH = "/wfx/wfx_ArticleDetail.aspx"
ARTICLE_WINDOW_NAME = "ArticleDetail"
FETCH_TIMEOUT_MS = 10_000
MAX_STYLES = 20
SERVER_ROW_LIMIT = 100

_DIGITS = re.compile(r"^\d+$")
_COMPANY = re.compile(r"^[A-Za-z0-9_-]+$")

# Header dựng y như Angular `commonsvc.getList` của grid Catalog.
_FIND_CODE_JS = r"""async ({path, catCode, query, timeoutMs}) => {
  const read = key => sessionStorage.getItem(key) || localStorage.getItem(key) || '';
  const guid = read('GUID');
  const company = read('CompanyCode');
  if (!guid || !company) return {error: 'SESSION_MISSING'};
  const pageParams = [
    ['ProductCatCode', catCode], ['ParentNodeCode', 'Master'], ['ViewAsOthers', '0'],
    ['OrderBy', 'CreatedOn'], ['orderAscDesc', 'DESC'], ['customSearchParams', ''],
    ['catalogID', ''], ['GUID', guid], ['methodName', 'GetList'],
  ].map(([name, value]) => ({ParamName: name, ParamValue: value}));
  const searchParams = [
    {ParamName: 'lnkArticleCode', ParamValue: query},
    {ParamName: 'frameworkSearchParams', ParamValue: 'lnkArticleCode|' + query + '~'},
    {ParamName: 'FilterCriteriaModel', ParamValue: [{
      colKey: 'lnkArticleCode', filterType: 'text', c1Value: query,
      c1filterTypeOperator: 'contains'
    }]},
  ];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      method: 'GET', credentials: 'include', signal: controller.signal,
      headers: {
        apiparams: JSON.stringify([
          {ParamName: 'objectName', ParamValue: 'CatalogList'},
          {ParamName: 'gridID', ParamValue: 'gridWFXCatalogList'},
        ]),
        pageparams: JSON.stringify(pageParams),
        searchparams: JSON.stringify(searchParams),
        sortparams: '[]',
        pagingparams: JSON.stringify({PageIndex: 0, PageSize: 0}),
        'Content-Type': 'application/json; charset=utf-8',
      },
    });
    let body = null;
    try { body = await response.json(); } catch (error) { body = null; }
    if (!response.ok || !body || body.Status === 'Fail' || !Array.isArray(body.ResponseData)) {
      return {error: 'HTTP ' + response.status};
    }
    return {
      company,
      catalogType: new URLSearchParams(location.search).get('CatalogType') || '',
      rows: body.ResponseData.map(row => ({
        code: String(row.ArticleCode || '').trim(),
        article_name: String(row.ArticleName || '').trim(),
        buyer_reference: String(row.BuyerReference || '').trim(),
        article_id: String(row.ArticleID ?? ''),
        group_id: String(row.CGID ?? ''),
        season: String(row.Season || '').trim(),
        costsheet_status: String(row.CostsheetStatus || '').trim(),
        link_disabled: Boolean(Number(row.DisableCatalogLink || 0)),
      })),
    };
  } catch (error) {
    return {error: error && error.name === 'AbortError' ? 'timeout' : 'fetch'};
  } finally {
    clearTimeout(timer);
  }
}"""

_OPEN_ARTICLE_JS = """({url, name}) => Boolean(window.open(url, name))"""


def _article_detail_url(
    row: Mapping[str, Any],
    *,
    catalog_type: str,
    company: str,
    category_value: str,
) -> str | None:
    """URL popup đúng như nút Code của grid mở; ``None`` khi thiếu dữ kiện."""
    article_id = str(row.get("article_id") or "")
    group_id = str(row.get("group_id") or "")
    if not (
        _DIGITS.match(article_id)
        and _DIGITS.match(group_id)
        and _DIGITS.match(catalog_type)
        and _COMPANY.match(company)
        and _COMPANY.match(category_value)
    ):
        return None
    query = urlencode(
        [
            ("ID", article_id),
            ("GroupID", group_id),
            ("ArticleSelection", ""),
            ("CatalogType", catalog_type),
            ("CatalogCompany", company),
            ("ComboCode", category_value),
            ("StyleSheet", "wfx_Style"),
        ]
    )
    return f"{ARTICLE_DETAIL_PATH}?{query}"


def _styles_from_api_rows(
    rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Gộp theo Code không phân biệt hoa/thường, giữ thứ tự server trả về."""
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "").strip()
        if code:
            unique.setdefault(code.casefold(), dict(row, code=code))
    return list(unique.values())


def _quick_find_catalog_code(
    page: Page,
    category_value: str,
    query: str,
    log: Callable[[str], None],
) -> dict[str, Any] | None:
    """Tìm Code qua GetData; ``None`` nghĩa là phải dùng state machine DOM."""
    if not category_value:
        return None
    try:
        grid = _catalog_grid_frame(page, timeout_seconds=0.3)
    except PlaywrightTimeoutError:
        return None
    try:
        response = grid.evaluate(
            _FIND_CODE_JS,
            {
                "path": GET_DATA_PATH,
                "catCode": category_value,
                "query": query,
                "timeoutMs": FETCH_TIMEOUT_MS,
            },
        )
    except PlaywrightError as exc:
        _write_log(log, f"[CODE] Không gọi được dữ liệu Catalog ({type(exc).__name__}); dùng grid.")
        return None
    if not isinstance(response, dict) or response.get("error"):
        reason = response.get("error") if isinstance(response, dict) else "?"
        _write_log(log, f"[CODE] Dữ liệu Catalog chưa dùng được ({reason}); dùng grid.")
        return None

    rows = [row for row in response.get("rows") or [] if isinstance(row, dict)]
    folded = query.casefold()
    matching = [row for row in rows if folded in str(row.get("code") or "").casefold()]
    if rows and not matching:
        # Server trả dữ liệu nhưng không dòng nào chứa query: điều kiện lọc bị
        # bỏ qua. Không được kết luận NO_RESULTS từ danh sách "mới nhất".
        _write_log(log, "[CODE] Server không áp điều kiện lọc; dùng grid.")
        return None
    styles = _styles_from_api_rows(matching)
    codes = [style["code"] for style in styles]
    shown = [
        {
            "code": style["code"],
            "season": style.get("season") or "",
            "internal_costsheet_status": style.get("costsheet_status") or "",
            "article_name": style.get("article_name") or "",
            "buyer_reference": style.get("buyer_reference") or "",
        }
        for style in styles[:MAX_STYLES]
    ]
    _write_log(
        log,
        f"[CODE] GetData: unique Code={len(codes)}; codes={codes[:MAX_STYLES]}",
    )
    if not styles:
        return _result(
            False,
            "NO_RESULTS",
            f"Không tìm thấy kết quả cho Code: {query}.",
            codes=[],
            styles=[],
        )
    exact = [style for style in styles if style["code"].casefold() == folded]
    if len(exact) != 1 and len(styles) >= 2:
        return _result(
            True,
            "MULTIPLE_RESULTS",
            f"Có {len(styles)} Code; giữ danh sách để bạn tự chọn.",
            codes=[style["code"] for style in shown],
            matches=[style["code"] for style in shown],
            styles=shown,
            # Server cắt ở 100 dòng: 100 nghĩa là "ít nhất 100".
            total_codes=len(styles),
            total_capped=len(rows) >= SERVER_ROW_LIMIT,
        )

    target = exact[0] if exact else styles[0]
    if target.get("link_disabled"):
        _write_log(log, f"[CODE] Style {target['code']} bị khóa link Catalog; dùng grid.")
        return None
    url = _article_detail_url(
        target,
        catalog_type=str(response.get("catalogType") or ""),
        company=str(response.get("company") or ""),
        category_value=category_value,
    )
    if url is None:
        _write_log(log, "[CODE] Thiếu dữ kiện dựng link Style; dùng grid.")
        return None
    _write_log(log, f"[CODE] Một kết quả, đang mở {target['code']}...")
    try:
        opened = grid.evaluate(
            _OPEN_ARTICLE_JS,
            {"url": url, "name": ARTICLE_WINDOW_NAME},
        )
    except PlaywrightError:
        opened = False
    if not opened:
        _write_log(log, "[CODE] Trình duyệt không mở được popup Style; dùng grid.")
        return None
    style_status = {
        "code": target["code"],
        "season": target.get("season") or "",
        "internal_costsheet_status": target.get("costsheet_status") or "",
    }
    return _result(
        True,
        "RESULT_OPENED",
        f"Đã tìm và mở style {target['code']}.{_style_status_suffix(style_status)}",
        article_code=target["code"],
        codes=codes[:MAX_STYLES],
        matches=codes[:MAX_STYLES],
        styles=shown,
        style_status=style_status,
        season=style_status["season"],
        internal_costsheet_status=style_status["internal_costsheet_status"],
    )
