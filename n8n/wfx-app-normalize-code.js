// Dán toàn bộ file này vào Code node "Chuẩn hóa thông tin WFX" của n8n.
// Telegram node chỉ cần dùng: {{$json.notification_text}}

const source = ($json.body && typeof $json.body === 'object')
  ? $json.body
  : $json;
const diagnostics = (
  source.diagnostics && typeof source.diagnostics === 'object'
)
  ? source.diagnostics
  : {};
const account = (source.account && typeof source.account === 'object')
  ? source.account
  : {};

const methodLabels = {
  login: 'Đăng nhập WFX',
  check_session: 'Kiểm tra phiên WFX',
  open_chrome: 'Mở trình duyệt automation',
  open_module: 'Mở module',
  prepare_catalog: 'Chuẩn bị Catalog',
  browse_catalog: 'Mở Catalog List',
  catalog_action: 'Tìm trong Catalog',
  find_code: 'Tìm Style Code',
  find_buyer_reference: 'Tìm Buyer Reference',
  open_catalog_destination: 'Mở Costing/BOM',
  download_catalog_file: 'Tải file Catalog',
  open_sale_asn_new: 'Mở Sale ASN mới',
  open_sample_new: 'Mở Sample Order mới',
  search_oc: 'Tìm trong OC List',
  search_sample: 'Tìm trong Sample List',
  search_sale_asn: 'Tìm trong Sale ASN List',
  prepare_sale_asn_documents: 'Tải Documents Sale ASN',
  save_sale_asn_documents: 'Lưu Documents Sale ASN',
  search_rmpo: 'Tìm trong RMPO List',
  search_indent: 'Tìm trong Indent List',
  open_module_new: 'Mở màn New của module',
  open_supplier_category: 'Mở Supplier List',
  find_supplier: 'Tìm Supplier',
  find_supplier_in_category: 'Tìm Supplier theo Category',
  find_buyer: 'Tìm Buyer',
  toggle_company_foc: 'Đổi FOC trong Company Setup',
  switch_division: 'Đổi Division',
};

const methodContexts = {
  search_oc: { module: 'OC List', filter: 'OC No. / Style' },
  search_sample: {
    module: 'Sample List',
    filter: 'Sample Order No. / Style / Created By',
  },
  search_sale_asn: {
    module: 'Sale ASN',
    filter: 'Invoice No. / Style',
  },
  prepare_sale_asn_documents: {
    module: 'Sale ASN',
    filter: 'Invoice No. / Buyer Order Ref/OC No.',
  },
  save_sale_asn_documents: { module: 'Sale ASN', filter: '' },
  search_rmpo: { module: 'RMPO List', filter: 'Supplier / RMPO No.' },
  search_indent: {
    module: 'Indent List / User Indent',
    filter: 'Supplier / Article / Indent No. / Style',
  },
  find_supplier: { module: 'Supplier List', filter: 'Company Name' },
  find_supplier_in_category: {
    module: 'Supplier List',
    filter: 'Company Name',
  },
  find_buyer: { module: 'Buyer List', filter: 'Company Name' },
  toggle_company_foc: { module: 'Company Setup', filter: '' },
};

// Mapping này giúp webhook của các bản app cũ vẫn có thông báo dễ hiểu.
const errorCodes = {
  DIVISION_CHANGE_NOT_CONFIRMED: {
    title: 'WFX chưa xác nhận đổi Division',
    suggestion: 'Kiểm tra menu Division trên WFX rồi thử lại.',
  },
  DIVISION_CHANGE_FAILED: {
    title: 'Không thể đổi Division',
    suggestion: 'Kiểm tra phiên WFX và menu Division rồi thử lại.',
  },
  MODULE_NOT_FOUND: {
    title: 'Không tìm thấy menu module',
    suggestion: 'Kiểm tra quyền tài khoản và menu WFX rồi thử lại.',
  },
  MODULE_FAILED: {
    title: 'Không thể thao tác module WFX',
    suggestion: 'Mở Log kỹ thuật để xem bước và lỗi gốc cuối cùng.',
  },
  MODULE_SEARCH_NOT_READY: {
    title: 'Ô tìm kiếm của module chưa sẵn sàng',
    suggestion: 'Bấm List, chờ danh sách tải xong rồi thử tìm lại.',
  },
  MODULE_SEARCH_NOT_CONFIRMED: {
    title: 'WFX chưa xác nhận kết quả tìm kiếm',
    suggestion: 'Kiểm tra màn List và thử lại sau khi grid tải xong.',
  },
  MODULE_SEARCH_FAILED: {
    title: 'Không thể thao tác ô tìm kiếm',
    suggestion: 'Mở Log kỹ thuật để xem lỗi gốc rồi thử lại.',
  },
  FLOATING_FILTER_NOT_READY: {
    title: 'Floating Filter chưa sẵn sàng',
    suggestion: 'Chờ danh sách tải xong, bật Floating Filter rồi thử lại.',
  },
  SALE_ASN_REPORT_NOT_READY: {
    title: 'Report Sale ASN chưa sẵn sàng',
    suggestion: 'Chờ Documents/Report Viewer load xong rồi thử lại.',
  },
  SALE_ASN_REPORT_DOWNLOAD_FAILED: {
    title: 'Không tải được report Sale ASN',
    suggestion: 'Kiểm tra hai report và quyền export Excel.',
  },
  SALE_ASN_REPORT_MERGE_FAILED: {
    title: 'Không ghép được hai report Sale ASN',
    suggestion: 'Mở Log kỹ thuật và dùng Run ID để kiểm tra.',
  },
  SALE_ASN_DOCUMENTS_SAVE_FAILED: {
    title: 'Không lưu được file Documents Sale ASN',
    suggestion: 'Chọn thư mục có quyền ghi và thử lại.',
  },
  SUPPLIER_SEARCH_PARTIAL: {
    title: 'Chưa kiểm tra được toàn bộ Category Supplier',
    suggestion: 'Thử lại hoặc mở từng Category bị lỗi để kiểm tra riêng.',
  },
  PANEL_ERROR: {
    title: 'Ứng dụng gặp lỗi khi chạy tác vụ',
    suggestion: 'Mở Log kỹ thuật và dùng Run ID để đối chiếu.',
  },
};

const eventType = String(source.event_type || 'unknown');
const eventLabel = eventType === 'user_feedback'
  ? (source.kind === 'bug' ? 'Báo lỗi từ người dùng' : 'Góp ý tính năng')
  : eventType === 'automation_error'
    ? 'Lỗi automation'
    : 'Sự kiện khác';
const method = String(source.method || '');
const methodLabel = String(
  source.method_label || methodLabels[method] || method || 'Tác vụ WFX',
);
const code = String(source.code || '');
const mappedError = errorCodes[code] || {};
const methodContext = methodContexts[method] || {};
const moduleName = String(source.module || methodContext.module || '');
const filterKind = String(source.filter_kind || methodContext.filter || '');
// Giống redact_telemetry_text của app: chỉ giữ tên trang WFX (.aspx…), bỏ
// host, thư mục, query và fragment.
const redactUrl = (url) => {
  const address = url.split(/[?#]/)[0];
  const segments = address.split('://').pop().split('/').slice(1);
  const name = (segments.length ? segments[segments.length - 1] : '')
    .replace(/[.,;:)\]}]+$/, '');
  return /^[\w-]{1,80}\.(aspx|ashx|asmx|axd|html?|svc)$/i.test(name)
    ? `[URL đã ẩn: ${name}]`
    : '[URL đã ẩn]';
};
const redactAutomationText = (value) => String(value || '')
  .replace(/https?:\/\/[^\s<>'"]+/gi, redactUrl)
  .replace(
    /\b(password|passwd|pwd|cookie|session[_\s-]?id|login[_\s-]?id|query|article[_\s-]?code|buyer[_\s-]?reference|style[_\s-]?code)\b\s*[:=]\s*("[^"]*"|'[^']*'|[^\s,;]+)/gi,
    '$1=[đã ẩn]',
  )
  .replace(
    /\bcode\s+(chính\s+xác|cần\s+tìm)\s*:\s*[^\s,;]+/gi,
    'Code [đã ẩn]',
  );
const errorTitle = String(
  source.error_title
    || mappedError.title
    || `${methodLabel} chưa hoàn tất`,
);
const fallbackErrorDetail = (() => {
  if (['MODULE_SEARCH_NOT_READY', 'MODULE_LIST_NOT_OPEN'].includes(code)) {
    const target = filterKind ? `ô ${filterKind}` : 'ô tìm kiếm';
    const location = moduleName ? ` trong ${moduleName}` : '';
    return `Không tìm thấy ${target}${location}; màn List có thể chưa mở hoặc chưa tải xong.`;
  }
  if (code === 'MODULE_SEARCH_NOT_CONFIRMED') {
    const target = filterKind ? ` theo ${filterKind}` : '';
    const location = moduleName ? ` trong ${moduleName}` : '';
    return `WFX chưa xác nhận kết quả tìm kiếm${target}${location}.`;
  }
  if (['open_module', 'open_module_new'].includes(method)) {
    const target = moduleName || 'module được chọn';
    return `Không thể mở ${target}; menu hoặc frame WFX chưa sẵn sàng (mã ${code || 'UNKNOWN'}).`;
  }
  if (method === 'switch_division') {
    return `WFX chưa hoàn tất đổi Division (mã ${code || 'UNKNOWN'}).`;
  }
  return `${methodLabel} trả về mã ${code || 'UNKNOWN'} nhưng không kèm lỗi gốc.`;
})();
const errorDetail = String(
  redactAutomationText(
    source.error_detail
      || source.message
      || fallbackErrorDetail,
  ),
);
// Báo lỗi một chạm của người dùng mang đủ context của lần chạy hỏng (Run ID,
// mã lỗi, log), nên được trình bày như lỗi automation chứ không như góp ý.
const isOneClickReport = eventType === 'user_feedback'
  && source.source === 'one_click';
const hasRunContext = eventType === 'automation_error' || isOneClickReport;
const safeMessage = hasRunContext
  ? errorDetail
  : String(source.message || '');
const logTail = (Array.isArray(source.log_tail) ? source.log_tail : [])
  .map((line) => redactAutomationText(line))
  .filter(Boolean);
const repeatCount = Number(source.repeat_count || 0);
const suggestion = String(
  source.suggestion
    || mappedError.suggestion
    || 'Mở Log kỹ thuật và dùng Run ID để đối chiếu bước bị lỗi.',
);
const failedStage = String(source.failed_stage || '');
const failedStep = Number(source.failed_step || 0);
const progressTotal = Number(source.progress_total || 0);
const stepText = failedStep
  ? ` (bước ${failedStep}${progressTotal ? `/${progressTotal}` : ''})`
  : '';
const stageText = failedStage ? `${failedStage}${stepText}` : '';
const chromeAlive = diagnostics.chrome_alive;
const browserName = String(diagnostics.browser_name || '');
const lastLoginAt = String(diagnostics.last_login_at || '');
const osName = diagnostics.os || source.os || '';
const osRelease = diagnostics.os_release || source.os_release || '';
const pythonVersion = diagnostics.python || source.python || '';
const machine = [
  [osName, osRelease].filter(Boolean).join(' '),
  pythonVersion ? `Python ${pythonVersion}` : '',
].filter(Boolean).join(' · ');
const recentJobs = Array.isArray(diagnostics.recent_jobs)
  ? diagnostics.recent_jobs
  : [];
// Các lần chạy ngay trước lần hỏng: thấy được lỗi dây chuyền (mất phiên rồi
// mọi flow sau cùng hỏng) mà không phải hỏi người dùng đã làm gì trước đó.
const recentText = recentJobs
  .filter((job) => job && typeof job === 'object' && job.run_id !== source.run_id)
  .slice(0, 4)
  .map((job) => `${job.method || '?'} ${job.ok ? '✓' : `✗ ${job.code || ''}`.trim()}`)
  .join(' · ');
const division = [
  account.division_label || diagnostics.division_label,
  account.division_name || diagnostics.division_name,
].filter(Boolean).join(' · ')
  || diagnostics.current_division
  || '';

const notificationLines = [
  `📣 WFX SMART · ${eventLabel}`,
  '',
  `🕒 Thời gian: ${source.timestamp || new Date().toISOString()}`,
  account.user_id ? `👤 Tài khoản: ${account.user_id}` : '',
  account.company_id ? `🏢 Company: ${account.company_id}` : '',
  division ? `🏭 Division: ${division}` : '',
  source.app_version ? `📦 Phiên bản: ${source.app_version}` : '',
];

if (hasRunContext) {
  notificationLines.push(
    `⚙️ Tác vụ: ${methodLabel}`,
    moduleName ? `📂 Module: ${moduleName}` : '',
    filterKind ? `🔍 Trường tìm: ${filterKind}` : '',
    `❌ Lỗi: ${errorTitle}`,
    `📝 Chi tiết: ${errorDetail}`,
    `💡 Xử lý: ${suggestion}`,
    code ? `🔧 Mã kỹ thuật: ${code}` : '',
    source.run_id ? `🔎 Run ID: ${source.run_id}` : '',
    stageText ? `🧭 Bước hỏng: ${stageText}` : '',
    source.elapsed_ms !== undefined && source.elapsed_ms !== ''
      ? `⏱️ Thời gian chạy: ${source.elapsed_ms} ms${source.started_at ? ` (bắt đầu ${source.started_at})` : ''}`
      : '',
    repeatCount > 1
      ? `🔁 Lặp lại: ${repeatCount} lần (Run ID cuối: ${source.last_run_id || '?'})`
      : '',
    chromeAlive !== undefined
      ? `🌐 Trình duyệt: ${chromeAlive ? 'đang chạy' : 'không chạy'}${browserName ? ` (${browserName})` : ''}`
      : '',
    diagnostics.session_active !== undefined
      ? `🔑 Phiên WFX: ${diagnostics.session_active ? 'còn' : 'mất'}${lastLoginAt ? ` (đăng nhập lúc ${lastLoginAt})` : ''}`
      : '',
    machine ? `💻 Máy: ${machine}` : '',
    source.has_screenshot ? '🖼️ Có ảnh lỗi trên máy người dùng' : '',
    recentText ? `🗂️ Tác vụ trước đó: ${recentText}` : '',
  );
} else {
  notificationLines.push(
    `📝 Nội dung: ${source.message || 'Không có mô tả'}`,
  );
}

// Telegram giới hạn 4.096 ký tự. Lỗi gốc nằm ở các dòng log CUỐI, nên phần
// đầu tin giữ nguyên còn log được thêm từ dòng mới nhất ngược lên tới khi hết
// chỗ; cắt cả tin từ đầu như trước làm mất đúng các dòng quan trọng nhất.
// Đủ log_tail vẫn nằm trong trường log_tail của output.
const NOTIFICATION_LIMIT = 4000;
const headText = notificationLines.filter(Boolean).join('\n');
const notificationText = (() => {
  if (!hasRunContext || !logTail.length) {
    return headText.slice(0, NOTIFICATION_LIMIT);
  }
  const header = '\n📜 Log cuối:';
  let budget = NOTIFICATION_LIMIT - headText.length - header.length;
  if (budget <= 1) return headText.slice(0, NOTIFICATION_LIMIT);
  const kept = [];
  for (let index = logTail.length - 1; index >= 0; index -= 1) {
    const line = logTail[index];
    if (line.length + 1 > budget) {
      // Dòng mới nhất dài hơn chỗ còn lại: giữ phần cuối của nó.
      if (!kept.length) kept.unshift(`…${line.slice(line.length - (budget - 2))}`);
      break;
    }
    kept.unshift(line);
    budget -= line.length + 1;
  }
  return `${headText}${header}\n${kept.join('\n')}`;
})();

return [{
  json: {
    received_at: source.timestamp || new Date().toISOString(),
    event_type: eventType,
    event_label: eventLabel,
    kind: source.kind || '',
    message: safeMessage,
    app_version: source.app_version || '',
    method,
    method_label: methodLabel,
    code,
    error_title: hasRunContext ? errorTitle : '',
    error_detail: hasRunContext ? errorDetail : '',
    suggestion: hasRunContext ? suggestion : '',
    report_source: String(source.source || ''),
    repeat_count: repeatCount || 1,
    last_run_id: source.last_run_id || '',
    log_tail: logTail,
    module: moduleName,
    filter_kind: filterKind,
    run_id: source.run_id || '',
    elapsed_ms: source.elapsed_ms ?? '',
    user_id: account.user_id || '',
    company_id: account.company_id || '',
    division,
    started_at: source.started_at || '',
    failed_stage: failedStage,
    failed_step: failedStep || '',
    progress_total: progressTotal || '',
    has_screenshot: Boolean(source.has_screenshot),
    os: osName,
    os_release: osRelease,
    python: pythonVersion,
    chrome_alive: chromeAlive ?? '',
    browser_name: browserName,
    session_active: diagnostics.session_active ?? '',
    last_login_at: lastLoginAt,
    recent_jobs: recentJobs,
    notification_text: notificationText,
  },
}];
