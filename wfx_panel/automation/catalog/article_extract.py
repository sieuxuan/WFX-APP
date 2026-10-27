"""Lấy toàn bộ Article từ WFX bằng ``fetch`` trong tab đã đăng nhập — CHỈ ĐỌC.

Gọi thẳng ``GET /WFXERPAPI/api/WFXCommon/GetData`` mà Catalog Grid dùng, thay
vì scrape DOM. Tham số đi trong header JSON thô (``apiparams``, ``pageparams``,
``searchparams``…); phiên đi bằng cookie của chính tab nên không cần đụng tới
cookie hay header xác thực. GUID phiên đọc từ ``sessionStorage`` của tab và
không bao giờ rời khỏi trang.

Server luôn cắt 100 dòng mới nhất nên ``article_partition.PartitionPlanner``
chia không gian Code thành các truy vấn ``contains`` đủ hẹp. Không điều hướng,
không click, không đưa tab lên trước: người dùng có thể tiếp tục làm việc.
"""

from __future__ import annotations

import time as _time
from pathlib import Path

from wfx_panel.atomic_io import write_json_atomic, write_text_atomic
from wfx_panel.automation._common import (
    Any,
    Callable,
    Playwright,
    _first_line,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.browser import _chrome_is_ready, _connect_to_chrome
from wfx_panel.automation.catalog.article_partition import (
    PartitionPlanner,
    articles_csv,
)
from wfx_panel.automation.runtime import checkpoint
from wfx_panel.automation.session import _session_is_active
from wfx_panel.telemetry import redact_telemetry_text

GET_DATA_PATH = "/WFXERPAPI/api/WFXCommon/GetData"
BATCH_SIZE = 12
CONCURRENCY = 4
REQUEST_TIMEOUT_MS = 60_000
MAX_QUERIES_PER_CATEGORY = 4000

# Chạy trong tab WFX: dựng header y như Angular `commonsvc.getList`, gửi theo
# pool song song nhỏ và chỉ trả về các cột cần dùng.
_FETCH_BATCH_JS = r"""async ({path, catCode, queries, concurrency, timeoutMs}) => {
  const guid = sessionStorage.getItem('GUID') || localStorage.getItem('GUID');
  if (!guid) return {error: 'GUID_MISSING'};
  const pageParams = [
    {ParamName: 'ProductCatCode', ParamValue: catCode},
    {ParamName: 'ParentNodeCode', ParamValue: 'Master'},
    {ParamName: 'ViewAsOthers', ParamValue: '0'},
    {ParamName: 'OrderBy', ParamValue: 'CreatedOn'},
    {ParamName: 'orderAscDesc', ParamValue: 'DESC'},
    {ParamName: 'customSearchParams', ParamValue: ''},
    {ParamName: 'catalogID', ParamValue: ''},
    {ParamName: 'GUID', ParamValue: guid},
    {ParamName: 'methodName', ParamValue: 'GetList'},
  ];
  const apiParams = [
    {ParamName: 'objectName', ParamValue: 'CatalogList'},
    {ParamName: 'gridID', ParamValue: 'gridWFXCatalogList'},
  ];
  const searchFor = (q) => q ? [
    {ParamName: 'lnkArticleCode', ParamValue: q},
    {ParamName: 'frameworkSearchParams', ParamValue: 'lnkArticleCode|' + q + '~'},
    {ParamName: 'FilterCriteriaModel', ParamValue: [{
      colKey: 'lnkArticleCode', filterType: 'text', c1Value: q, c1filterTypeOperator: 'contains'
    }]},
  ] : [];
  const one = async (q) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, {
        method: 'GET', credentials: 'include', signal: controller.signal,
        headers: {
          apiparams: JSON.stringify(apiParams),
          pageparams: JSON.stringify(pageParams),
          searchparams: JSON.stringify(searchFor(q)),
          sortparams: '[]',
          pagingparams: JSON.stringify({PageIndex: 0, PageSize: 0}),
          'Content-Type': 'application/json; charset=utf-8',
        },
      });
      let body = null;
      try { body = await response.json(); } catch (e) { body = null; }
      if (!response.ok || !body || body.Status === 'Fail' || !Array.isArray(body.ResponseData)) {
        return {query: q, error: 'HTTP ' + response.status + ' ' +
          String((body && (body.ErrorMsg || body.Status)) || 'không đọc được JSON').slice(0, 160)};
      }
      return {query: q, rows: body.ResponseData.map(r => ({
        code: r.ArticleCode, name: r.ArticleName, buyer_reference: r.BuyerReference,
        article_id: r.ArticleID, created_on: r.CreatedOn,
      }))};
    } catch (e) {
      return {query: q, error: String(e && e.name === 'AbortError' ? 'timeout' : e).slice(0, 160)};
    } finally {
      clearTimeout(timer);
    }
  };
  const results = new Array(queries.length);
  let next = 0;
  const worker = async () => {
    while (next < queries.length) {
      const index = next++;
      results[index] = await one(queries[index]);
    }
  };
  await Promise.all(Array.from({length: Math.min(concurrency, queries.length)}, worker));
  return {results};
}"""


class _ExtractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _run_batch(page: Any, category_value: str, queries: list[str]) -> list[dict]:
    response = page.evaluate(
        _FETCH_BATCH_JS,
        {
            "path": GET_DATA_PATH,
            "catCode": category_value,
            "queries": queries,
            "concurrency": CONCURRENCY,
            "timeoutMs": REQUEST_TIMEOUT_MS,
        },
    )
    if not isinstance(response, dict):
        raise _ExtractError("CATALOG_EXTRACT_FAILED", "WFX trả kết quả không đọc được.")
    if response.get("error") == "GUID_MISSING":
        raise _ExtractError(
            "CATALOG_EXTRACT_SESSION_MISSING",
            "Tab WFX chưa có mã phiên Catalog. Hãy mở Catalog một lần rồi thử lại.",
        )
    results = response.get("results") or []
    failed = [item for item in results if item.get("error")]
    if failed:
        raise _ExtractError(
            "CATALOG_EXTRACT_FAILED",
            "WFX từ chối truy vấn danh sách Article: "
            + redact_telemetry_text(failed[0]["error"]),
        )
    return results


def _extract_category(
    page: Any,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> tuple[PartitionPlanner, float]:
    started = _time.monotonic()
    planner = PartitionPlanner(max_queries=MAX_QUERIES_PER_CATEGORY)
    batches = 0
    while not planner.done:
        checkpoint()
        queries = planner.next_batch(BATCH_SIZE)
        if not queries:
            break
        for item in _run_batch(page, category_value, queries):
            planner.record(item["query"], item.get("rows") or [])
        batches += 1
        if batches % 10 == 0:
            _write_log(
                log,
                f"[ARTICLE EXTRACT] {category_name}: {len(planner.rows)} mã · "
                f"{planner.query_count} truy vấn",
            )
    return planner, _time.monotonic() - started


def extract_catalog_articles(
    categories: dict[str, str],
    output_dir: Path | str,
    log: Callable[[str], None] = print,
    *,
    app_version: str = "",
) -> dict[str, Any]:
    """Lấy đủ Article của từng Category và ghi CSV cùng định dạng Article List."""
    playwright: Playwright | None = None
    try:
        if not categories:
            return _result(False, "CATEGORY_UNKNOWN", "Chưa chọn Category nào.")
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        # Chỉ gọi fetch trong tab sẵn có, không điều hướng: không kéo người
        # dùng khỏi màn đang làm.
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        rows_by_category: dict[str, list[dict]] = {}
        summary: dict[str, dict] = {}
        incomplete: list[str] = []
        for category_name, category_value in categories.items():
            _write_log(log, f"[ARTICLE EXTRACT] Đang lấy Article {category_name}...")
            planner, elapsed = _extract_category(
                page, category_name, category_value, log
            )
            rows_by_category[category_name] = list(planner.rows.values())
            complete = not planner.exhausted
            if not complete:
                incomplete.append(category_name)
            summary[category_name] = {
                "category_code": category_value,
                "article_count": len(planner.rows),
                "query_count": planner.query_count,
                "seconds": round(elapsed, 1),
                "complete": complete,
                "assumed_complete_blocks": planner.assumed_complete_blocks,
                "roots_seen_only_mid_code": planner.unexpanded_roots,
                "ignored_queries": planner.ignored_queries,
            }
            _write_log(
                log,
                f"[ARTICLE EXTRACT] {category_name}: {len(planner.rows)} mã sau "
                f"{planner.query_count} truy vấn ({elapsed:.0f} giây).",
            )

        stamp = _time.strftime("%Y%m%d-%H%M%S")
        target = Path(output_dir) / f"article-list-{stamp}.csv"
        summary_path = Path(output_dir) / f"article-list-{stamp}.json"
        total = sum(len(rows) for rows in rows_by_category.values())
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # BOM giống Article List.csv để Excel mở đúng tiếng Việt.
            write_text_atomic(target, "﻿" + articles_csv(rows_by_category))
            write_json_atomic(
                summary_path,
                {
                    "kind": "catalog-article-extract",
                    "created_at": _time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "app_version": app_version,
                    "source": f"GET {GET_DATA_PATH} (objectName=CatalogList)",
                    "article_count": total,
                    "categories": summary,
                },
                indent=2,
            )
        except OSError as exc:
            message = f"Không ghi được file Article: {_first_line(exc)}"
            _write_log(log, message)
            return _result(False, "CATALOG_EXTRACT_WRITE_FAILED", message)

        counts = ", ".join(
            f"{name} {item['article_count']}" for name, item in summary.items()
        )
        _write_log(log, f"[ARTICLE EXTRACT] Đã lưu: {target}")
        if incomplete:
            return _result(
                False,
                "CATALOG_ARTICLES_PARTIAL",
                f"Đã lấy {total} Article nhưng chưa đủ ở: {', '.join(incomplete)}.",
                file_path=str(target),
                summary_path=str(summary_path),
                article_count=total,
                categories=summary,
            )
        return _result(
            True,
            "CATALOG_ARTICLES_EXTRACTED",
            f"Đã lấy {total} Article từ WFX ({counts}).",
            file_path=str(target),
            summary_path=str(summary_path),
            article_count=total,
            categories=summary,
        )
    except _ExtractError as exc:
        _write_log(log, str(exc))
        return _result(False, exc.code, str(exc))
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_EXTRACT_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
