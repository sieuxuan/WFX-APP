"use strict";
// Thanh trạng thái, badge phiên/Division/quyền và nhật ký.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function setStatus(tone, label) {
  const status = $(".footer-status");
  status.dataset.tone = tone || "neutral";
  $(".footer-status-text").textContent = label || "";
}
window.wfxSetStatus = setStatus;

function setBrowserStatus(alive, available = true, name = null) {
  const health = $(".health-chrome");
  if (health) {
    health.dataset.state = alive ? "ok" : "bad";
    health.dataset.tooltip = alive
      ? `${name || "Chromium"} · trình duyệt làm việc`
      : "Chưa kết nối trình duyệt";
  }
  const banner = $(".browser-banner");
  if (banner) {
    banner.hidden = alive === true;
    $(".browser-banner-message").textContent = available === false
      ? "Chưa cài Chrome, Edge, Brave hoặc Chromium."
      : `Dùng ${name || "Chrome, Edge, Brave hoặc Chromium"}.`;
    $(".open-chrome-button").textContent = available === false ? "Kiểm tra lại" : "Mở trình duyệt";
  }
}
window.wfxSetChromeStatus = (alive) => setBrowserStatus(alive);
window.wfxSetBrowserStatus = setBrowserStatus;

function setDivisionState(key, label, name) {
  currentDivision = key || null;
  $$(".division-button").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(Boolean(currentDivision) && button.dataset.division === currentDivision)
    );
  });
  syncDivisionHint();
}
window.wfxSetDivisionState = setDivisionState;

// Ba nút Division bị disable khi chưa có phiên WFX. Nếu không nói lý do thì
// người dùng chỉ thấy chúng mờ đi mà không biết phải làm gì. Dòng này chỉ
// hiện khi thật sự có việc cần làm nên không tốn chiều cao lúc bình thường.
function syncDivisionHint() {
  const hint = $(".division-hint");
  if (!hint) return;
  let message = "";
  if (!currentDivision) {
    if (sessionActive === true) message = "Chưa nhận ra Division của tài khoản.";
    else if (sessionActive === false) message = "Đăng nhập để chọn Division.";
  }
  hint.textContent = message;
  hint.hidden = !message;
}

function setSessionStatus(active, lastLoginAt) {
  sessionActive = active == null ? null : Boolean(active);
  if (lastLoginAt !== undefined) {
    lastLoginTime = String(lastLoginAt || "");
  }
  const node = $(".health-session");
  if (node) {
    node.dataset.state = active == null ? "unknown" : (active ? "ok" : "bad");
    node.dataset.tooltip = active === true && lastLoginTime
      ? `Phiên WFX · đăng nhập lúc ${lastLoginTime}`
      : "Phiên WFX";
  }
  $$(".division-button").forEach((button) => {
    button.disabled = active !== true;
  });
  const accountIcon = $(".account-status-icon");
  const accountLabel = $(".account-status-label");
  if (accountIcon) accountIcon.dataset.state = active == null ? "unknown" : (active ? "ok" : "bad");
  if (accountLabel) {
    accountLabel.textContent = active == null
      ? "Chưa kiểm tra"
      : (active
        ? (lastLoginTime ? `Đã đăng nhập lúc ${lastLoginTime}` : "Đã đăng nhập")
        : "Chưa đăng nhập");
  }
  syncAccountView();
  if (active !== true) setDivisionState(null, null, null);
  else syncDivisionHint();
}
window.wfxSetSessionStatus = setSessionStatus;


function setAdminAccess(access, moduleIds, enabled) {
  adminAccess = access === true;
  adminModuleIds = new Set(Array.isArray(moduleIds) ? moduleIds : []);
  adminMode = adminAccess && enabled === true;
  const row = $(".admin-mode-row");
  if (row) row.hidden = !adminAccess;
  const input = $(".admin-mode-input");
  if (input) input.checked = adminMode;
  const syncCard = $(".reference-sync-card");
  if (syncCard) syncCard.hidden = !adminAccess;
  const syncAdmin = $(".reference-sync-admin");
  if (syncAdmin) syncAdmin.hidden = !adminAccess;
  buildModules();
}
window.wfxSetAdminAccess = setAdminAccess;

function setReferenceSyncStatus(state) {
  if (!state || typeof state !== "object") return;
  referenceSyncState = { ...referenceSyncState, ...state };
  const articleCount = Number(referenceSyncState.article_count || 0);
  const optionCount = Number(referenceSyncState.style_option_count || 0);
  const lastSuccess = Number(referenceSyncState.last_success || 0);
  const statusNode = $(".reference-sync-status");
  if ($(".reference-sync-articles")) {
    $(".reference-sync-articles").textContent = articleCount.toLocaleString("vi-VN");
  }
  if ($(".reference-sync-options")) {
    $(".reference-sync-options").textContent = optionCount.toLocaleString("vi-VN");
  }
  if (statusNode) {
    if (!referenceSyncState.configured) {
      statusNode.textContent = "Bản này chưa bật đồng bộ";
    } else if (lastSuccess > 0) {
      const when = new Date(lastSuccess * 1000).toLocaleString("vi-VN", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
      statusNode.textContent = `${referenceSyncState.fresh ? "Đã cập nhật" : "Cần cập nhật"} · ${when}`;
    } else {
      statusNode.textContent = "Chưa đồng bộ lần nào";
    }
  }
  const publishButton = $(".reference-sync-publish");
  if (publishButton) {
    publishButton.textContent = referenceSyncState.admin_configured
      ? "Đẩy lên server"
      : "Lưu key trước đã";
    publishButton.disabled = !referenceSyncState.admin_configured;
  }
}
window.wfxSetReferenceSyncStatus = setReferenceSyncStatus;

// App nằm ở khay hệ thống cả ngày nên <pre> log phải có trần. Ngoài chuyện
// phình DOM, mọi lần đọc pre.textContent đều nối lại toàn bộ text node con:
// đọc nó trên từng dòng làm chi phí ghi log tăng theo bình phương số dòng.
// Vì vậy ở đây chỉ đụng tới childNodes/firstChild, không đọc textContent.
const LOG_PLACEHOLDER = "Chưa có nhật ký hệ thống.";
const LOG_MAX_LINES = 2000;

function pushLog(line) {
  const pre = $(".catalog-log");
  const selection = window.getSelection?.();
  const selectionInLog = Boolean(
    selection
    && !selection.isCollapsed
    && (
      pre.contains(selection.anchorNode)
      || pre.contains(selection.focusNode)
    ),
  );
  const followLatest = (
    pre.scrollHeight - pre.scrollTop - pre.clientHeight <= 28
    && !selectionInLog
  );
  if (
    pre.childNodes.length === 1
    && pre.firstChild.nodeValue === LOG_PLACEHOLDER
  ) {
    pre.textContent = "";
  }
  pre.append(document.createTextNode(
    `${pre.childNodes.length ? "\n" : ""}${line}`,
  ));
  while (pre.childNodes.length > LOG_MAX_LINES) {
    pre.removeChild(pre.firstChild);
  }
  // Mỗi dòng mang sẵn "\n" ở đầu; sau khi cắt bớt phải bỏ ký tự đó của dòng
  // đầu còn lại để log không mở màn bằng một dòng trống.
  const first = pre.firstChild;
  if (first && first.nodeValue.charCodeAt(0) === 10) {
    first.nodeValue = first.nodeValue.slice(1);
  }
  if (followLatest) pre.scrollTop = pre.scrollHeight;
}
window.wfxPushLog = pushLog;
