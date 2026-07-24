"use strict";

// Generated Chrome MV3 main-world adapter. Source of truth: ../../wfx-tampermonkey.user.js
(() => {
  if (window.__wfxSmartChromeExtensionLoaded) return;
  window.__wfxSmartChromeExtensionLoaded = true;

  const MESSAGE_SOURCE = "wfx-smart-chrome-extension";
  let started = false;
  let applyStorageUpdate = () => {};
  let handleExtensionCommand = () => {};

  const post = (type, payload = {}) => {
    window.postMessage({
      source: MESSAGE_SOURCE,
      type,
      ...payload,
    }, window.location.origin);
  };

  const start = (bridgeToken, initialValues) => {
    if (started) return;
    started = true;
    const extensionCache = { ...(initialValues || {}) };
    const unsafeWindow = window;

    const GM_getValue = (key) => extensionCache[key];
    const GM_setValue = (key, value) => {
      extensionCache[key] = value;
      post("storage-request", {
        token: bridgeToken,
        operation: "set",
        key,
        value,
      });
    };
    const GM_deleteValue = (key) => {
      delete extensionCache[key];
      post("storage-request", {
        token: bridgeToken,
        operation: "remove",
        key,
      });
    };
    const GM_registerMenuCommand = () => {};
    applyStorageUpdate = (token, updates) => {
      if (token !== bridgeToken || !updates) return;
      for (const [key, value] of Object.entries(updates)) {
        if (value === undefined) delete extensionCache[key];
        else extensionCache[key] = value;
      }
    };
    handleExtensionCommand = (token, command) => {
      if (token !== bridgeToken || command !== "toggle-panel") return;
      document.dispatchEvent(new CustomEvent("wfx-smart-extension-toggle-panel"));
    };
// CHANGELOG 1.2.0 (fix CATALOG_CLICK_FAILED / mọi click đều không mở được / kẹt "Đang đăng nhập..."):
// - Chrome Extension chạy script trong "isolated world" riêng biệt với trang WFX thật. Toàn bộ script
//   trước đây dùng `new MouseEvent(...)`, `new Event(...)`, `new KeyboardEvent(...)` của world cô lập
//   này rồi dispatch lên phần tử DOM thật của WFX (hoặc của frame khác) → trình duyệt coi đây là
//   Event "khác thực thể" và có thể ném lỗi ngay ở bước mouseover/mousedown đầu tiên. Vì hàm click
//   dùng chung 1 khối try/catch, lỗi đó chặn luôn cả `element.click()` thật sự phía sau, nên
//   MỌI nút (Catalog, module, Next, Log In...) đều "click" xong mà WFX không phản ứng gì.
// - Sửa: luôn tạo Event bằng đúng constructor của `ownerDocument.defaultView` (cửa sổ thật chứa
//   phần tử đó, có thể là top window, iframe "left"/grid, hoặc popup Article), và tách các bước
//   phụ (scrollIntoView/focus/mouseover/mousedown/mouseup) thành best-effort — lỗi ở bước phụ
//   không còn chặn cú click thật.
// - Thêm watchdog sau khi bấm Next/Log In: nếu trạng thái đăng nhập không đổi sau ~9s (postback lỗi/
//   bị chặn), tự động huỷ trạng thái "Đang đăng nhập..." và báo lỗi rõ ràng thay vì treo vô thời hạn.
// - Thêm console.debug ở các bước click/chờ để dễ soi lỗi trong DevTools nếu còn phát sinh vấn đề khác.
//
// CHANGELOG 1.3.0 (gộp phần đăng nhập vào Settings + sửa lỗi "mọi ô nhập đều không xoá được text"):
// - Bug xoá text: nút "Nhấn tổ hợp mới" (đổi hotkey) đặt cờ hotkeyCapture=true; nghe phím
//   (document, capture phase) khi cờ này bật sẽ preventDefault() MỌI phím ở MỌI nơi trên trang —
//   nếu người dùng bấm nút đó rồi bấm sang ô khác (User ID, Code...) mà không nhấn Esc, cờ vẫn
//   bật mãi và không gõ/xoá được ký tự nào ở bất kỳ ô nào nữa. Sửa: tự huỷ hotkeyCapture ngay khi
//   nút hotkey mất focus (blur), không cần đợi Esc hay đóng panel.
// - Bỏ khối "Kết nối / Login" to ở đầu panel chính; chuyển trạng thái phiên + nút Kết nối vào
//   trong Settings (chỉ nơi cần chỉnh tài khoản mới cần thao tác này). Auto-login khi mở panel
//   vẫn hoạt động như cũ, không cần bấm nút.
// - Nút "Kết nối / Login" tự ẩn khi đã đăng nhập xong, chỉ hiện khi chưa đăng nhập hoặc đang
//   trong lúc đăng nhập (để thấy tiến trình).
//
// CHANGELOG 1.3.1 (sửa TẬN GỐC bug "vẫn không xoá được text" sau bản 1.3.0):
// - Fix blur ở 1.3.0 chỉ vá 1 đường rò, cờ hotkeyCapture vẫn là biến toàn cục dùng chung bởi
//   listener gắn trên `document` — vẫn còn khả năng kẹt. Sửa tận gốc: bỏ hẳn nhánh bắt tổ hợp
//   phím mới ra khỏi listener toàn trang; logic đó (handleHotkeyButtonKeydown) giờ gắn TRỰC TIẾP
//   vào nút hotkey, chỉ chạy được khi chính nút đó đang focus. Listener toàn trang (handleKeydown)
//   giờ chỉ còn một việc: nhận diện đúng tổ hợp đã lưu để mở/đóng panel — không còn nhánh nào
//   preventDefault() một cách vô điều kiện/kẹt được nữa.
// - Thêm bảo vệ ở getHotkey(): nếu hotkey đã lưu (dữ liệu cũ) không có modifier và không phải
//   F2–F12, tự động bỏ qua và dùng lại mặc định — tránh trường hợp nó trùng với phím thường
//   (vd Backspace) khiến phím đó bị nuốt mất trên toàn trang mỗi lần nhấn.
//
// CHANGELOG 1.3.2 (chặn hẳn Backspace/Delete/Enter/Tab/Space khỏi danh sách hotkey hợp lệ):
// - Trước đây một tổ hợp có giữ modifier (vd Alt+Backspace, Ctrl+Backspace — cũng là phím tắt
//   "xoá cả từ" rất hay dùng khi gõ văn bản) vẫn được CHẤP NHẬN làm hotkey mở panel vì có modifier.
//   Nếu người dùng lỡ đặt trùng, mỗi lần bấm tổ hợp đó để xoá chữ, script sẽ nuốt mất phím đó
//   (preventDefault + toggle panel) — matches đúng triệu chứng "bấm Backspace không xoá được".
// - Thêm UNSAFE_HOTKEY_CODES (Backspace, Delete, Enter, Tab, Space, Escape...): không cho lưu các
//   phím này làm hotkey (báo lỗi khi cố đặt), và getHotkey() cũng tự bỏ qua nếu dữ liệu cũ đã lỡ
//   lưu trùng, quay về mặc định Alt+Shift+W.
//
// CHANGELOG 1.4.0 (người dùng xác nhận KHÔNG hề đặt hotkey trùng Backspace — bug 1.3.x không phải
// nguyên nhân; đổi hướng điều tra và sửa nguyên nhân thực sự):
// - Giả thuyết mới: WFX (ASP.NET WebForms cũ) thường tự chặn phím Backspace ở mức document khi
//   KHÔNG đang gõ trong input/textarea (tránh Backspace vô tình gây điều hướng "back", mất dữ liệu
//   form). Guard đó thường dựa vào `document.activeElement.tagName`. Input/textarea của panel này
//   nằm TRONG Shadow DOM — khi người dùng gõ thật bên trong, `document.activeElement` (nhìn từ
//   NGOÀI, tức từ chính script của WFX) không bao giờ thấy được input thật, chỉ thấy phần tử HOST
//   (một <div>) của shadow root. WFX tưởng nhầm "không phải đang gõ chữ" và nuốt mất phím Backspace
//   — dù người dùng đang gõ thật trong Code/Buyer Reference/User ID/Password của panel. Đây là điểm
//   mù cố hữu của Shadow DOM, không phải lỗi input của panel hay hotkey.
// - Sửa: handleKeydown (đã đăng ký capture:true trên document — chạy TRƯỚC listener bubble-phase
//   điển hình của các trang cũ) giờ dùng event.composedPath() để "nhìn xuyên" shadow boundary; nếu
//   phím thật sự xuất phát từ input/textarea của panel, gọi stopPropagation() để chặn event lan tới
//   listener của WFX trước khi nó kịp preventDefault() — không tự preventDefault ở đây nên trình
//   duyệt vẫn xử lý gõ/xoá chữ bình thường.
// - Đổi hotkey mặc định từ Alt+Shift+W sang Ctrl+Alt+X theo yêu cầu.
//
// CHANGELOG 1.5.0 (fix hotkey Ctrl+Alt+X + đếm sai/tự mở sai kết quả Catalog):
// - Khi đang ghi hotkey, listener toàn trang không còn xử lý tổ hợp cũ trước listener của nút.
// - Chỉ đọc các row/button thật sự có layout trong AG Grid và khử trùng Code theo giá trị.
// - Tìm theo Code ưu tiên mã khớp chính xác, kể cả grid còn render thêm kết quả gần đúng.
// - Theo dõi window.open trong cả iframe grid/Article, không chỉ top window.
// - Sau khi click kết quả, chờ xác nhận popup/frame Article đã mở; không còn báo thành công giả.
//
// CHANGELOG 1.5.1 (fix kẹt Catalog → Master / báo TIMEOUT chung chung):
// - Ưu tiên đúng frame `left`, tìm Master bằng cả text/value/title/aria-label và resolve lại node
//   sau mỗi lần WFX thay frame.
// - Click Master có retry và chỉ hoàn tất khi frame/grid Catalog bắt đầu điều hướng.
// - Floating Filter được poll + click khi nó thực sự render, không chỉ kiểm tra đúng một lần.
// - Tách mã lỗi Category/Master/Grid/Filter để thông báo đúng bước đang kẹt.
//
// CHANGELOG 1.6.0 (fix chọn nhầm container có text "Master" + thêm log chẩn đoán):
// - DOM order thường trả div/td cha trước thẻ a/button Master thật; bản 1.5.1 có thể click lặp lại
//   container không có action. Nay ưu tiên node clickable trực tiếp và thử lần lượt mọi candidate.
// - Thêm nhật ký Catalog ngay trên panel: frame URL, candidate Master, node được click và trạng thái
//   Grid/Floating Filter. Có nút sao chép log để gửi chẩn đoán mà không chứa tài khoản/mật khẩu.
//
// CHANGELOG 1.6.1 (fix báo 32 kết quả trong khi UI chỉ có 1):
// - Không query row trên toàn document nữa; khóa đúng AG Grid root chứa ô filter đang nhập.
// - Loại row cache/virtual buffer nằm ngoài viewport thật của grid.
// - Log raw/rendered/unique counts và danh sách Code để chẩn đoán chính xác bộ đếm.
// - Che SessionID/IP/LoginID trong URL log trước khi cho sao chép.
//
// CHANGELOG 1.7.0 (fix chọn nhầm grid/filter rỗng + Chrome shortcut):
// - Chấm điểm mọi Code/Buyer Filter theo grid root, số row/button và trạng thái hiển thị; giữ đúng
//   active grid thay vì mỗi vòng poll lại lấy input đầu tiên trong document.
// - Chờ dữ liệu ban đầu của AG Grid load xong rồi mới fill, tránh filter bị quá trình init ghi đè.
// - Thêm hook toggle panel cho Chrome Extension `chrome.commands` (Ctrl+Alt+X cấp trình duyệt).
//
// CHANGELOG 1.7.1 (fix Chrome từ chối manifest vì Ctrl+Alt+X không hợp lệ trong commands):
// - Chrome commands API không nhận suggested_key Ctrl+Alt+X. Extension chuyển sang bắt tổ hợp
//   ở isolated bridge từ document_start (trước listener WFX) rồi gửi hook toggle vào MAIN world.
//
// CHANGELOG 1.8.0 (viết lại toàn bộ state machine Catalog theo claude.md — không phải "thêm retry"):
// - NGUYÊN NHÂN GỐC #1 (Master chỉ mở ở lần 4, log 1.7.1 23:01:30): getCatalogMasterCandidates()
//   xếp hạng cả node KHÔNG có action thật (rank "clickable-ancestor"/"exact-text-fallback" click
//   thẳng li/div/td chỉ vì chứa chữ "Master") làm candidate dự phòng. Khi click đúng span[onclick]
//   đầu tiên chỉ làm frame `left` reload (chưa mở Catalog Grid), vòng lặp cũ vẫn còn candidate cũ
//   trong document đã chết và rơi xuống thử img/li — đúng như log mô tả. Sửa: xoá toàn bộ ranking/
//   fallback đó; findExactActionableMaster() giờ CHỈ khớp
//   `span[onclick], a, button, [role="button"], input[type="button"]` có text/value chuẩn hoá
//   đúng "Master". clickCatalogMaster() dùng document identity (markDocumentGeneration/
//   isNewDocument, qua WeakMap<Document, number>) để biết `left` vừa reload và tự resolve lại rồi
//   click lại ĐÚNG node đó — không bao giờ rơi sang node khác.
// - NGUYÊN NHÂN GỐC #2 (báo "Code Filter đã sẵn sàng" dù rawRows=0/rawButtons=0): waitForCatalogGrid()
//   cũ coi Code Filter Input "usable" là đủ để kết thúc mode `prepare`, không hề kiểm tra grid đã
//   nạp dữ liệu. Sửa: tách hẳn bước GRID_DATA_SETTLED (waitGridSettled — chờ hết loading overlay
//   và có ít nhất 1 row thật hoặc no-rows overlay ổn định ≥700ms) chạy TRƯỚC ensureFloatingFilterVisible;
//   floating filter chỉ được báo FILTER_VISIBLE khi input visible+enabled VÀ readGridState() tại
//   đúng thời điểm đó xác nhận rows>0 hoặc no-rows overlay — không có ngoại lệ.
// - Xoá findBestGridFilter()/readGridResults() chấm điểm toàn trang (vi phạm "không chọn candidate
//   bằng global score giữa nhiều grid" của claude.md) — mọi selector filter/kết quả giờ chỉ
//   querySelector bên trong đúng `.ag-root-wrapper` đã được clickCatalogMaster xác nhận
//   (readRenderedUniqueResults), khớp yêu cầu "UI có 1 nhưng script đếm 32".
// - Xoá chooseCatalogTargetCode() tự mở Article khi có nhiều Code nhưng một Code khớp chính xác —
//   claude.md yêu cầu >=2 kết quả luôn giữ grid mở, không có ngoại lệ.
// - Thêm runId + elapsedMs vào mọi log Catalog (logRun/createRunContext) và các mã lỗi còn thiếu:
//   FILTER_VALUE_NOT_CONFIRMED, FILTER_RESULTS_NOT_READY, ARTICLE_DESTINATION_NOT_FOUND. Đổi
//   RESULT_DETACHED thành kết quả trả về (outcome: "detached"), không còn là exception.
//
// CHANGELOG 1.8.1 (fix "Uncaught Error: Extension context invalidated" ở bridge.js):
// - CHỈ xảy ra trên bản Chrome Extension: khi extension được reload/cập nhật (vd sau khi cài lại
//   bản build mới) trong lúc tab WFX vẫn đang mở, content script cũ (bridge.js, ISOLATED world)
//   mất quyền truy cập chrome.storage/chrome.runtime vĩnh viễn — không có cách nào tự phục hồi,
//   chỉ có thể tải lại trang. Trước đây bridge.js gọi thẳng chrome.storage.local.set/remove/get
//   và chrome.runtime.onMessage.addListener mà không có guard, nên lỗi này ném ra console dưới
//   dạng uncaught exception và người dùng không biết vì sao panel ngừng lưu thiết lập.
// - Sửa: bridge.js kiểm tra chrome.runtime.id trước mỗi lần gọi + bọc try/catch quanh chính lời
//   gọi (phòng race giữa lúc kiểm tra và lúc gọi thật); lần đầu phát hiện context mất, gửi
//   postMessage "extension-context-lost" (postMessage không phải API của extension nên vẫn hoạt
//   động sau khi bị invalidate) thay vì im lặng nuốt lỗi.
// - Adapter Chrome Extension (build-extension.ps1) chuyển tiếp message đó thành CustomEvent
//   "wfx-smart-extension-context-lost" trên `document`, và panel (core script, chạy chung cho cả
//   Chrome Extension lẫn Chrome Extension) hiện toast yêu cầu người dùng tải lại trang — Chrome Extension
//   không bao giờ dispatch event này nên không bị ảnh hưởng.

(function () {
  "use strict";

  // Trang WFX thật (page world), KHÔNG phải world cô lập của Chrome Extension. Bắt buộc dùng cái này
  // để lấy đúng constructor Event/MouseEvent/KeyboardEvent khi cần fallback (không có ownerDocument).
  const PAGE_WINDOW = typeof unsafeWindow !== "undefined" && unsafeWindow ? unsafeWindow : window;

  const HOME_URL = "https://prosports.worldfashionexchange.com/wfx_Home.aspx";
  const SCRIPT_VERSION = "1.9.1";
  const ROOT_ID = "wfx-smart-automation-root";
  const PENDING_TTL_MS = 2 * 60 * 1000;

  const STORAGE = Object.freeze({
    account: "wfx-smart-account-v1",
    preferences: "wfx-smart-preferences-v1",
    hotkey: "wfx-smart-hotkey-v1",
    pendingLogin: "wfx-smart-pending-login-v1",
    pendingAction: "wfx-smart-pending-action-v1",
    catalog: "wfx-smart-catalog-v1",
  });

  const CATEGORIES = Object.freeze({
    Apparel: "01",
    "Fixed Asset": "04",
    Miscellaneous: "12",
    Services: "06",
    "Textiles/Fabric": "03",
    Trims: "05",
  });

  const DEFAULT_HOTKEY = Object.freeze({
    ctrl: true,
    alt: true,
    shift: false,
    meta: false,
    code: "KeyX",
    key: "X",
  });

  // Những phím này tuyệt đối không được phép làm "code" của hotkey mở panel — dù có giữ kèm
  // modifier (vd Alt+Backspace, Ctrl+Backspace) vẫn là tổ hợp xoá/soạn thảo văn bản rất hay dùng.
  // Nếu lỡ đặt trùng, mỗi lần người dùng bấm tổ hợp đó để xoá chữ, panel sẽ nuốt mất phím đó.
  const UNSAFE_HOTKEY_CODES = Object.freeze([
    "Backspace", "Delete", "Enter", "NumpadEnter", "Tab", "Space", "Escape",
  ]);

  const MODULE_GROUPS = [
    {
      name: "Operation",
      accent: "cyan",
      modules: [
        { name: "Catalog", id: "0003_6200", icon: "CA" },
        { name: "OC List", id: "0004_0050_0020", icon: "OC" },
        { name: "Sample List", id: "0004_0056_4070", icon: "SL" },
        { name: "Sale ASN", id: "0004_0070_0020", icon: "AS" },
        { name: "RMPO List", id: "0005_0050_0020", icon: "RM" },
        { name: "Indent List", id: "0005_0080_0020", icon: "IN" },
        { name: "QA List", id: "0063_0030_0020", icon: "QA" },
      ],
    },
    {
      name: "Finance",
      accent: "violet",
      modules: [
        { name: "Advance PR List", id: "0065_0880_0010_0020", icon: "PR" },
        { name: "Supplier Inv List", id: "0065_0880_0020_0020", icon: "SI" },
        { name: "Expense Inv List", id: "0065_0880_0030_0020", icon: "EI" },
      ],
    },
    {
      name: "Admin",
      accent: "amber",
      modules: [
        { name: "Org Structure", id: "0090_0001", icon: "OR" },
        { name: "System Coding", id: "0090_0250", icon: "SC" },
        { name: "Company Setup", id: "0090_0007", icon: "CO" },
        { name: "Buyer List", id: "0004_0010_1720", icon: "BU" },
        { name: "Supplier List", id: "0005_0010_1290", icon: "SU" },
      ],
    },
  ];

  const ALL_MODULES = MODULE_GROUPS.flatMap((group) =>
    group.modules.map((module) => ({ ...module, group: group.name, accent: group.accent })),
  );

  let ui = null;
  let hotkeyCapture = false;
  let loginInFlight = false;
  let automationInFlight = false;
  let statusTimer = 0;
  let automationLogs = [];
  const popupWindows = new Set();

  function readValue(key, fallback) {
    try {
      const value = GM_getValue(key);
      return value === undefined || value === null ? fallback : value;
    } catch (error) {
      console.warn("[WFX Smart] Không đọc được thiết lập:", error);
      return fallback;
    }
  }

  function writeValue(key, value) {
    try {
      GM_setValue(key, value);
      return true;
    } catch (error) {
      console.error("[WFX Smart] Không lưu được thiết lập:", error);
      return false;
    }
  }

  function deleteValue(key) {
    try {
      GM_deleteValue(key);
    } catch (error) {
      console.warn("[WFX Smart] Không xóa được trạng thái cũ:", error);
    }
  }

  function getAccount() {
    const value = readValue(STORAGE.account, {});
    return {
      userId: String(value?.userId || "").trim(),
      password: String(value?.password || ""),
      companyId: String(value?.companyId || "psh").trim() || "psh",
    };
  }

  function getPreferences() {
    const value = readValue(STORAGE.preferences, {});
    return {
      autoLoginOnOpen: value?.autoLoginOnOpen !== false,
      closeAfterModule: value?.closeAfterModule !== false,
      theme: value?.theme === "dark" ? "dark" : "light",
    };
  }

  function applyTheme(theme) {
    const value = theme === "dark" ? "dark" : "light";
    if (ui?.host) ui.host.dataset.theme = value;
    if (ui?.appearanceButtons) {
      ui.appearanceButtons.forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.themeChoice === value));
      });
    }
  }

  function getSelectedTheme() {
    const pressed = ui?.appearanceButtons?.find((button) => button.getAttribute("aria-pressed") === "true");
    return pressed?.dataset.themeChoice === "dark" ? "dark" : "light";
  }

  // Đổi theme là hành động hiển thị thuần tuý — áp dụng + lưu ngay, không cần điền tài khoản
  // hay bấm "Lưu thiết lập". Giữ nguyên các preference khác khi ghi lại.
  function setTheme(theme) {
    const value = theme === "dark" ? "dark" : "light";
    applyTheme(value);
    const prefs = getPreferences();
    writeValue(STORAGE.preferences, {
      autoLoginOnOpen: prefs.autoLoginOnOpen,
      closeAfterModule: prefs.closeAfterModule,
      theme: value,
    });
  }

  function getHotkey() {
    const value = readValue(STORAGE.hotkey, null);
    if (!value || typeof value.code !== "string") return { ...DEFAULT_HOTKEY };
    const hotkey = {
      ctrl: Boolean(value.ctrl),
      alt: Boolean(value.alt),
      shift: Boolean(value.shift),
      meta: Boolean(value.meta),
      code: value.code,
      key: String(value.key || value.code),
    };
    // Bảo vệ: một hotkey đã lưu mà KHÔNG có modifier nào và cũng không phải phím F2-F12 (dữ
    // liệu cũ/hỏng) có thể trùng với phím thường dùng (vd Backspace) — nếu khớp, mọi lần nhấn
    // phím đó trên toàn trang sẽ bị nuốt mất (preventDefault) để toggle panel. Không tin dữ liệu
    // này, quay lại mặc định.
    const functionKey = /^F(?:[2-9]|1[0-2])$/.test(hotkey.code);
    if (!hotkey.ctrl && !hotkey.alt && !hotkey.shift && !hotkey.meta && !functionKey) {
      return { ...DEFAULT_HOTKEY };
    }
    // Dù có modifier, code vẫn có thể là phím soạn thảo phổ biến (Backspace, Delete...) nếu lỡ
    // đặt trước đó — không tin, quay lại mặc định thay vì để nó nuốt phím xoá của người dùng.
    if (UNSAFE_HOTKEY_CODES.includes(hotkey.code)) {
      return { ...DEFAULT_HOTKEY };
    }
    return hotkey;
  }

  function isVisible(element) {
    if (!element) return false;
    // Dùng defaultView của chính document chứa element (có thể là frame khác top window),
    // vì getComputedStyle của một world khác có thể trả kết quả sai/ném lỗi trên phần tử "lạ".
    const view = element.ownerDocument?.defaultView || PAGE_WINDOW;
    const style = view.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  }

  function findVisible(selector) {
    return [...document.querySelectorAll(selector)].find(isVisible) || null;
  }

  function findModuleAnchor(moduleId) {
    for (const context of getAccessibleContexts()) {
      const container = context.document.getElementById(moduleId);
      if (container) {
        if (container.matches("a")) return container;
        const childAnchor = container.querySelector("a");
        if (childAnchor) return childAnchor;
      }
      try {
        const exact = context.document.evaluate(
          `//*[@id="${moduleId}"]/a`,
          context.document,
          null,
          XPathResult.FIRST_ORDERED_NODE_TYPE,
          null,
        ).singleNodeValue;
        if (exact) return exact;
      } catch (_error) {
        // Một số trang WFX cũ vô hiệu XPath; getElementById phía trên vẫn là đường chính.
      }
    }
    return null;
  }

  function getAuthState() {
    if (
      findModuleAnchor("0003_6200") ||
      findModuleAnchor("0090_0250") ||
      document.querySelector("a[id*='0003_6200']")
    ) {
      return "authenticated";
    }
    if (findVisible("#txtPassword")) return "password";
    if (findVisible("#txtUserID")) return "user";
    return "unknown";
  }

  function authDetails() {
    const account = getAccount();
    const state = getAuthState();
    if (state === "authenticated") {
      return { state, label: "Đã đăng nhập", detail: account.userId || "WFX session", tone: "success" };
    }
    if (!account.userId || !account.password) {
      return { state, label: "Chưa cấu hình", detail: "Thêm tài khoản để tự đăng nhập", tone: "warning" };
    }
    if (state === "user" || state === "password") {
      return { state, label: "Sẵn sàng login", detail: account.userId, tone: "warning" };
    }
    return { state, label: "Chưa xác định", detail: account.userId, tone: "neutral" };
  }

  function setNativeValue(input, value) {
    // input có thể thuộc frame khác (left panel Catalog, popup Article...), nên phải lấy
    // HTMLInputElement/Event đúng "thế giới" (window) sở hữu nó, không dùng constructor của
    // world cô lập Chrome Extension — nếu không instanceof sẽ sai và Event dispatch có thể bị bỏ qua.
    const view = input.ownerDocument?.defaultView || PAGE_WINDOW;
    const isTextArea = typeof view.HTMLTextAreaElement === "function" && input instanceof view.HTMLTextAreaElement;
    const prototype = isTextArea ? view.HTMLTextAreaElement.prototype : view.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    const EventCtor = view.Event || PAGE_WINDOW.Event;
    input.dispatchEvent(new EventCtor("input", { bubbles: true }));
    input.dispatchEvent(new EventCtor("change", { bubbles: true }));
  }

  function bestEffort(action, label) {
    try {
      action();
    } catch (error) {
      // Bước phụ (scroll/focus/hover) lỗi không được phép chặn cú click thật phía sau.
      console.debug(`[WFX Smart] Bỏ qua bước phụ "${label}":`, error);
    }
  }

  function clickElement(element, label = "phần tử") {
    if (!element) {
      console.warn(`[WFX Smart] clickElement: không có phần tử để click (${label}).`);
      return false;
    }
    // QUAN TRỌNG: phải dùng MouseEvent của đúng "thế giới" (window) sở hữu element — tức
    // ownerDocument.defaultView của chính element đó (top page, iframe "left"/grid, hay popup
    // Article đều khác nhau) — KHÔNG dùng MouseEvent của world cô lập Chrome Extension. Trước đây
    // dùng chung 1 MouseEvent "lạ thế giới" rồi dispatch cho mọi frame khiến trình duyệt có thể
    // ném lỗi ngay ở bước mouseover, và vì tất cả nằm chung 1 try/catch nên element.click() thật
    // sự phía sau không bao giờ chạy → mọi nút bấm xong nhưng WFX không phản ứng gì.
    const view = element.ownerDocument?.defaultView || PAGE_WINDOW;
    const MouseEventCtor = view.MouseEvent || PAGE_WINDOW.MouseEvent;

    bestEffort(() => element.scrollIntoView?.({ block: "center", inline: "center" }), "scrollIntoView");
    bestEffort(() => element.focus?.({ preventScroll: true }), "focus");
    bestEffort(() => element.dispatchEvent(new MouseEventCtor("mouseover", { bubbles: true, cancelable: true, view, button: 0 })), "mouseover");
    bestEffort(() => element.dispatchEvent(new MouseEventCtor("mousedown", { bubbles: true, cancelable: true, view, button: 0 })), "mousedown");
    bestEffort(() => element.dispatchEvent(new MouseEventCtor("mouseup", { bubbles: true, cancelable: true, view, button: 0 })), "mouseup");

    try {
      element.click();
      console.debug(`[WFX Smart] Đã click: ${label}`);
      return true;
    } catch (error) {
      console.error(`[WFX Smart] Click thất bại (${label}):`, error);
      return false;
    }
  }

  function installPopupTracker(startWindow = PAGE_WINDOW) {
    // Nút Code nằm trong iframe grid nên lệnh window.open() chạy trên window CỦA IFRAME, không
    // phải top window. Chỉ wrap PAGE_WINDOW sẽ bỏ sót chính popup Article cần tự động hóa.
    for (const context of getAccessibleContexts(startWindow)) {
      try {
        const targetWindow = context.window;
        if (targetWindow.open?.__wfxSmartWrapped) continue;
        const nativeOpen = targetWindow.open.bind(targetWindow);
        const trackedOpen = function (...args) {
          const popup = nativeOpen(...args);
          if (popup) popupWindows.add(popup);
          else console.warn("[WFX Smart] WFX yêu cầu mở popup nhưng trình duyệt đã chặn.", args[0] || "");
          return popup;
        };
        trackedOpen.__wfxSmartWrapped = true;
        trackedOpen.__wfxSmartNative = nativeOpen;
        targetWindow.open = trackedOpen;
      } catch (error) {
        console.debug(`[WFX Smart] Không wrap được window.open của context "${context.name}":`, error);
      }
    }
  }

  function getAccessibleContexts(startWindow = PAGE_WINDOW) {
    const contexts = [];
    const visited = new Set();
    const visit = (candidate) => {
      if (!candidate || visited.has(candidate)) return;
      visited.add(candidate);
      try {
        const candidateDocument = candidate.document;
        contexts.push({
          window: candidate,
          document: candidateDocument,
          name: String(candidate.name || ""),
          url: String(candidate.location?.href || ""),
        });
        for (let index = 0; index < candidate.frames.length; index += 1) {
          visit(candidate.frames[index]);
        }
      } catch (_error) {
        // Bỏ qua frame khác origin. Các frame Catalog WFX là cùng origin.
      }
    };
    visit(startWindow);
    return contexts;
  }

  function elementIsUsable(element) {
    try {
      if (!element || !element.isConnected) return false;
      const view = element.ownerDocument?.defaultView || PAGE_WINDOW;
      const style = view.getComputedStyle(element);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        style.opacity === "0" ||
        element.disabled
      ) {
        return false;
      }
      // AG Grid giữ lại/recycle một số row trong DOM. getComputedStyle() trên button con vẫn có
      // thể trả "display: block" dù cả row cha đã bị ẩn; chỉ node có rect thật mới là kết quả
      // đang render. Đây là nguyên nhân một mã bị đếm thành 2+ kết quả.
      return [...element.getClientRects()].some((rect) => rect.width > 0 && rect.height > 0);
    } catch (_error) {
      return false;
    }
  }

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function serializeLogDetails(details) {
    if (details === undefined || details === null || details === "") return "";
    if (typeof details === "string") return details;
    try {
      return JSON.stringify(details);
    } catch (_error) {
      return String(details);
    }
  }

  function sanitizeUrlForLog(value) {
    const text = String(value || "");
    try {
      const parsed = new URL(text, PAGE_WINDOW.location?.origin || HOME_URL);
      for (const key of [...parsed.searchParams.keys()]) {
        if (/^(sessionid|remoteip|loginid|userid|password|token|auth|access_token)$/i.test(key)) {
          parsed.searchParams.set(key, "REDACTED");
        }
      }
      return parsed.href;
    } catch (_error) {
      return text
        .replace(/([?&](?:sessionid|remoteip|loginid|userid|password|token|auth|access_token)=)[^&]*/gi, "$1REDACTED");
    }
  }

  function renderAutomationLog() {
    if (!ui?.catalogLog) return;
    ui.catalogLog.textContent = automationLogs.join("\n");
    ui.catalogLog.scrollTop = ui.catalogLog.scrollHeight;
    // Log giờ nằm trong overlay riêng mở từ top nav. Khi có ERROR mà overlay đang đóng, đánh dấu
    // chấm cảnh báo trên nút log để người dùng biết cần mở xem — không tự bung overlay gây khó chịu.
    const hasError = automationLogs.some((line) => /\[ERROR\]/.test(line));
    if (ui.logButton) {
      const logOpen = ui.logOverlay?.classList.contains("log-open");
      ui.logButton.classList.toggle("has-alert", hasError && !logOpen);
    }
  }

  function clearAutomationLog() {
    automationLogs = [];
    renderAutomationLog();
  }

  function logAutomation(stage, message, details = null) {
    const timestamp = new Date().toLocaleTimeString("vi-VN", { hour12: false });
    const suffix = serializeLogDetails(details);
    const line = `[${timestamp}] [${stage}] ${message}${suffix ? ` | ${suffix}` : ""}`;
    automationLogs.push(line);
    if (automationLogs.length > 220) automationLogs.splice(0, automationLogs.length - 220);
    renderAutomationLog();
    console.debug(`[WFX Smart][${stage}] ${message}`, details ?? "");
  }

  function snapshotCatalogContexts() {
    return getAccessibleContexts().map((context) => ({
      name: context.name || "(top)",
      url: sanitizeUrlForLog(context.url),
      category: Boolean(context.document.querySelector("#ddlCategory")),
      grid: Boolean(context.document.querySelector(".ag-root-wrapper")),
      codeFilter: Boolean(context.document.querySelector('input[aria-label="Code Filter Input"]')),
    }));
  }

  function describeElement(element) {
    if (!element) return null;
    const rawClass = typeof element.className === "string" ? element.className : "";
    return {
      tag: String(element.tagName || "").toLocaleLowerCase("en"),
      id: String(element.id || ""),
      class: normalizeText(rawClass).slice(0, 120),
      text: normalizeText(element.textContent || element.value).slice(0, 160),
      href: sanitizeUrlForLog(normalizeText(element.getAttribute?.("href"))).slice(0, 300),
      onclick: Boolean(element.getAttribute?.("onclick") || element.onclick),
    };
  }

  async function copyAutomationLog() {
    const text = automationLogs.join("\n") || "Chưa có log Catalog.";
    try {
      await navigator.clipboard.writeText(text);
      showToast("Đã sao chép log Catalog.", "success");
    } catch (_error) {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      const copied = document.execCommand("copy");
      helper.remove();
      showToast(copied ? "Đã sao chép log Catalog." : "Không sao chép được log.", copied ? "success" : "error");
    }
  }

  function waitFor(check, timeoutMs = 15000, intervalMs = 220) {
    const startedAt = Date.now();
    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const result = await check();
          if (result) {
            resolve(result);
            return;
          }
        } catch (_error) {
          // WFX thường thay frame trong lúc load; thử lại cho tới timeout.
        }
        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error("TIMEOUT"));
          return;
        }
        window.setTimeout(poll, intervalMs);
      };
      void poll();
    });
  }

  function dispatchFilledValue(input, value) {
    const view = input.ownerDocument?.defaultView || PAGE_WINDOW;
    const KeyboardEventCtor = view.KeyboardEvent || PAGE_WINDOW.KeyboardEvent;
    const text = String(value ?? "");
    const lastCharacter = text.slice(-1) || "Backspace";
    const keyCode = lastCharacter === "Backspace"
      ? 8
      : lastCharacter.toLocaleUpperCase("en").charCodeAt(0);
    const keyCodeName = /^[a-z]$/i.test(lastCharacter)
      ? `Key${lastCharacter.toLocaleUpperCase("en")}`
      : /^\d$/.test(lastCharacter)
        ? `Digit${lastCharacter}`
        : lastCharacter === "Backspace"
          ? "Backspace"
          : "";
    bestEffort(() => input.focus({ preventScroll: true }), "focus filter");
    bestEffort(() => input.select?.(), "select filter");
    input.dispatchEvent(new KeyboardEventCtor("keydown", {
      bubbles: true,
      cancelable: true,
      key: lastCharacter,
      code: keyCodeName,
      keyCode,
      which: keyCode,
    }));
    const InputEventCtor = view.InputEvent || PAGE_WINDOW.InputEvent;
    if (typeof InputEventCtor === "function") {
      input.dispatchEvent(new InputEventCtor("beforeinput", {
        bubbles: true,
        cancelable: true,
        data: text || null,
        inputType: text ? "insertText" : "deleteContentBackward",
      }));
    }
    setNativeValue(input, text);
    input.dispatchEvent(new KeyboardEventCtor("keyup", {
      bubbles: true,
      cancelable: true,
      key: lastCharacter,
      code: keyCodeName,
      keyCode,
      which: keyCode,
    }));
  }

  function setCatalogProgress(message, tone = "info") {
    if (!ui) return;
    ui.catalogProgress.textContent = message;
    ui.catalogProgress.dataset.tone = tone;
    ui.catalogProgress.hidden = false;
  }

  function setAutomationBusy(isBusy, message = "Đang xử lý...") {
    automationInFlight = isBusy;
    if (!ui) return;
    ui.catalogActionButtons.forEach((button) => { button.disabled = isBusy; });
    ui.moduleButtons.forEach((button) => { button.disabled = isBusy; });
    ui.catalogCard.classList.toggle("catalog-busy", isBusy);
    if (isBusy) setCatalogProgress(message, "info");
    else saveCatalogForm();
  }

  function readCatalogForm() {
    return {
      categoryName: ui.catalogCategory.value,
      categoryValue: CATEGORIES[ui.catalogCategory.value],
      code: ui.catalogCode.value.trim(),
      buyerReference: ui.catalogBuyerReference.value.trim(),
    };
  }

  function saveCatalogForm() {
    if (!ui) return;
    const form = readCatalogForm();
    writeValue(STORAGE.catalog, {
      categoryName: form.categoryName,
      code: form.code,
      buyerReference: form.buyerReference,
    });
    const apparel = form.categoryValue === "01";
    ui.destinationButtons.forEach((button) => {
      button.disabled = automationInFlight || !apparel;
      button.title = apparel ? "" : "Costsheet/BOM chỉ hỗ trợ Category Apparel";
    });
  }

  function restoreCatalogForm() {
    if (!ui) return;
    const saved = readValue(STORAGE.catalog, {});
    const categoryName = Object.hasOwn(CATEGORIES, saved?.categoryName)
      ? saved.categoryName
      : "Apparel";
    ui.catalogCategory.value = categoryName;
    ui.catalogCode.value = String(saved?.code || "");
    ui.catalogBuyerReference.value = String(saved?.buyerReference || "");
    saveCatalogForm();
  }

  function startPendingLogin(source) {
    const pending = {
      source: source || "panel",
      attempts: 0,
      startedAt: Date.now(),
      expiresAt: Date.now() + PENDING_TTL_MS,
    };
    writeValue(STORAGE.pendingLogin, pending);
    return pending;
  }

  function getPending(key) {
    const pending = readValue(key, null);
    if (!pending || Number(pending.expiresAt || 0) < Date.now()) {
      deleteValue(key);
      return null;
    }
    return pending;
  }

  function bumpPendingLogin(pending, step) {
    const next = {
      ...pending,
      attempts: Number(pending.attempts || 0) + 1,
      lastStep: step,
      lastAttemptAt: Date.now(),
    };
    writeValue(STORAGE.pendingLogin, next);
    return next;
  }

  function showToast(message, tone = "info", timeout = 3300) {
    if (!ui) return;
    const item = document.createElement("div");
    item.className = `toast toast-${tone}`;
    item.innerHTML = `<span class="toast-dot"></span><span class="toast-text"></span>`;
    item.querySelector(".toast-text").textContent = message;
    ui.toastStack.appendChild(item);
    requestAnimationFrame(() => item.classList.add("toast-visible"));
    window.setTimeout(() => {
      item.classList.remove("toast-visible");
      window.setTimeout(() => item.remove(), 220);
    }, timeout);
  }

  function setBusy(isBusy, text = "Đang xử lý...") {
    loginInFlight = isBusy;
    if (!ui) return;
    ui.loginButton.disabled = isBusy;
    ui.loginButton.classList.toggle("is-loading", isBusy);
    ui.loginButton.querySelector("span").textContent = isBusy ? text : "Kết nối / Login";
  }

  async function continueLogin({ reset = false, source = "panel" } = {}) {
    if (loginInFlight) return false;
    const account = getAccount();
    if (!account.userId || !account.password) {
      openPanel({ skipAutoLogin: true });
      openSettings();
      showToast("Hãy lưu User ID và Password trước.", "warning", 4500);
      return false;
    }

    let pending = reset ? startPendingLogin(source) : getPending(STORAGE.pendingLogin);
    if (!pending) pending = startPendingLogin(source);
    if (Number(pending.attempts || 0) >= 3) {
      deleteValue(STORAGE.pendingLogin);
      setBusy(false);
      openPanel({ skipAutoLogin: true });
      showToast("Đăng nhập chưa thành công. Hãy kiểm tra lại tài khoản.", "error", 5200);
      return false;
    }

    setBusy(true, "Đang đăng nhập...");
    const state = getAuthState();
    if (state === "authenticated") {
      deleteValue(STORAGE.pendingLogin);
      setBusy(false);
      refreshStatus();
      await processPendingAction();
      return true;
    }

    if (state === "password") {
      const passwordInput = findVisible("#txtPassword");
      const loginButton = findVisible("#btlLogin[value='Log In'], input[name='btlLogin'][value='Log In']");
      if (!passwordInput || !loginButton) {
        setBusy(false);
        showToast("Không tìm thấy nút Log In trên trang.", "error");
        return false;
      }
      bumpPendingLogin(pending, "password");
      setNativeValue(passwordInput, account.password);
      showToast("Đang xác thực tài khoản...", "info");
      window.setTimeout(() => {
        if (!clickElement(loginButton, "Log In button")) {
          setBusy(false);
          showToast("Không click được nút Log In. Xem console để biết chi tiết.", "error", 6000);
          return;
        }
        void watchLoginProgress(state);
      }, 180);
      return true;
    }

    if (state === "user") {
      const userInput = findVisible("#txtUserID");
      const companyInput = findVisible("#txtCompany");
      const nextButton = findVisible("#btlLogin[value='Next'], input[name='btlLogin'][value='Next']");
      if (!userInput || !nextButton) {
        setBusy(false);
        showToast("Không tìm thấy nút Next trên trang.", "error");
        return false;
      }
      bumpPendingLogin(pending, "user");
      setNativeValue(userInput, account.userId);
      if (companyInput) setNativeValue(companyInput, account.companyId);
      showToast("Đã điền User ID, đang chuyển bước...", "info");
      window.setTimeout(() => {
        if (!clickElement(nextButton, "Next button")) {
          setBusy(false);
          showToast("Không click được nút Next. Xem console để biết chi tiết.", "error", 6000);
          return;
        }
        void watchLoginProgress(state);
      }, 180);
      return true;
    }

    bumpPendingLogin(pending, "navigate");
    showToast("Đang mở trang đăng nhập WFX...", "info");
    window.location.assign(HOME_URL);
    return true;
  }

  // Sau khi bấm Next/Log In, WFX thường điều hướng (postback) sang bước kế tiếp trong vài giây.
  // Nếu click không có tác dụng gì (site chặn thao tác tự động, DOM thay đổi bất ngờ...), trạng thái
  // đăng nhập sẽ đứng yên mãi mãi và nút Login sẽ kẹt ở "Đang đăng nhập..." vô thời hạn vì không có
  // gì reset loginInFlight. Watchdog này phát hiện việc "đứng yên" và tự hủy + báo lỗi rõ ràng.
  async function watchLoginProgress(previousState) {
    try {
      await waitFor(() => (getAuthState() !== previousState ? true : null), 9000, 250);
      console.debug(`[WFX Smart] Trạng thái đăng nhập đã chuyển từ "${previousState}".`);
      // Nếu WFX chuyển bước mà KHÔNG reload trang (postback dạng AJAX), module-level
      // loginInFlight sẽ không tự reset qua việc script bị tiêm lại — chủ động dọn ở đây.
      setBusy(false);
      refreshStatus();
      if (getAuthState() === "authenticated") {
        deleteValue(STORAGE.pendingLogin);
        showToast("Đăng nhập WFX thành công.", "success");
        await processPendingAction();
      }
    } catch (_error) {
      console.warn(`[WFX Smart] Trạng thái vẫn là "${previousState}" sau 9s — WFX có thể không nhận cú click tự động.`);
      setBusy(false);
      showToast("WFX không phản hồi sau khi bấm nút. Hãy thử lại hoặc bấm thủ công.", "error", 6200);
    }
  }

  async function waitForModuleAnchor(moduleId, timeoutMs = 6500) {
    const immediate = findModuleAnchor(moduleId);
    if (immediate) return immediate;
    try {
      return await waitFor(() => findModuleAnchor(moduleId), timeoutMs, 180);
    } catch (_error) {
      return null;
    }
  }

  async function openModule(module) {
    if (!module || automationInFlight) return;
    if (getAuthState() !== "authenticated") {
      writeValue(STORAGE.pendingAction, {
        type: "module",
        moduleId: module.id,
        moduleName: module.name,
        expiresAt: Date.now() + PENDING_TTL_MS,
      });
      showToast(`Sẽ mở ${module.name} sau khi đăng nhập.`, "info");
      await continueLogin({ reset: true, source: "module" });
      return;
    }

    setAutomationBusy(true, `Đang mở ${module.name}...`);
    try {
      const anchor = await waitForModuleAnchor(module.id);
      if (!anchor) {
        showToast(`Không tìm thấy menu ${module.name}. Hãy về trang WFX Home rồi thử lại.`, "error", 5200);
        return;
      }
      deleteValue(STORAGE.pendingAction);
      setCatalogProgress(`Đã gửi lệnh mở ${module.name}.`, "success");
      const clicked = clickElement(anchor, module.name);
      if (!clicked) throw new Error("CLICK_FAILED");
      showToast(`Đã click ${module.name}.`, "success");
      if (getPreferences().closeAfterModule) {
        window.setTimeout(closePanel, 280);
      }
    } catch (error) {
      console.error("[WFX Smart] Module error:", error);
      showToast(`Không mở được ${module.name}.`, "error", 5000);
    } finally {
      window.setTimeout(() => setAutomationBusy(false), 450);
    }
  }

  function getCatalogLeftContexts() {
    return getAccessibleContexts()
      .filter((context) => context.document.querySelector("#ddlCategory"))
      .sort((left, right) => {
        const leftScore = left.name.toLocaleLowerCase("en") === "left" ? 0 : 1;
        const rightScore = right.name.toLocaleLowerCase("en") === "left" ? 0 : 1;
        return leftScore - rightScore;
      });
  }

  function findCatalogGridCandidate() {
    for (const context of getAccessibleContexts()) {
      if (!context.url.toLocaleLowerCase("en").includes("wfxcataloglist")) continue;
      if (context.document.querySelector(".ag-root-wrapper")) return context;
    }
    return null;
  }

  // Một document (frame left hay Catalog Grid) chỉ được coi là "mới" khi nó khác chính object
  // document đã snapshot trước đó. Vì script chạy cùng JS realm với trang WFX (không phải proxy
  // từ xa như Playwright), so sánh identity trực tiếp là đủ và đáng tin hơn việc tự chế một
  // marker — không có cách nào một document cũ "giả" trùng identity với document mới.
  let documentGenerationCounter = 0;
  const documentGenerations = new WeakMap();

  function markDocumentGeneration(doc) {
    if (!doc) return 0;
    if (!documentGenerations.has(doc)) {
      documentGenerationCounter += 1;
      documentGenerations.set(doc, documentGenerationCounter);
    }
    return documentGenerations.get(doc);
  }

  function snapshotContext(context) {
    if (!context) return { document: null, generation: 0, name: "", url: "" };
    return {
      document: context.document,
      generation: markDocumentGeneration(context.document),
      name: context.name,
      url: context.url,
    };
  }

  function snapshotLeftDocument() {
    return snapshotContext(getCatalogLeftContexts()[0] || null);
  }

  function snapshotGridDocument() {
    return snapshotContext(findCatalogGridCandidate());
  }

  function isNewDocument(context, snapshot) {
    if (!context) return false;
    if (!snapshot || !snapshot.document) return true;
    return context.document !== snapshot.document;
  }

  function createRunContext(request) {
    const runId = typeof PAGE_WINDOW.crypto?.randomUUID === "function"
      ? PAGE_WINDOW.crypto.randomUUID()
      : `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return { runId, startedAt: Date.now(), mode: request.mode };
  }

  function logRun(runCtx, stage, message, details = null) {
    logAutomation(stage, message, {
      runId: runCtx.runId,
      elapsedMs: Date.now() - runCtx.startedAt,
      ...(details || {}),
    });
  }

  async function resolveNewLeftFrame(runCtx, oldLeftSnapshot, timeoutMs = 22000) {
    let context;
    try {
      context = await waitFor(() => {
        const candidate = getCatalogLeftContexts()[0] || null;
        return candidate && isNewDocument(candidate, oldLeftSnapshot) ? candidate : null;
      }, timeoutMs, 220);
    } catch (_error) {
      logRun(runCtx, "ERROR", "Không tìm thấy frame left mới sau khi click Catalog.", snapshotCatalogContexts());
      throw new Error("CATALOG_LEFT_NOT_FOUND");
    }
    logRun(runCtx, "LEFT_READY", "Đã nhận frame left mới.", {
      frame: context.name,
      url: sanitizeUrlForLog(context.url),
      generation: markDocumentGeneration(context.document),
    });
    return context;
  }

  async function selectCatalogCategory(runCtx, leftContext, categoryName, categoryValue) {
    setCatalogProgress(`Đang chọn Category: ${categoryName}...`);
    let select = leftContext.document.querySelector("#ddlCategory");
    if (String(select.value) === categoryValue) {
      setCatalogProgress(`Category ${categoryName} đã sẵn sàng.`, "success");
      logRun(runCtx, "CATEGORY_CONFIRMED", "Category đã đúng, không cần đổi.", { value: categoryValue });
      return;
    }

    const openView = leftContext.window;
    select.dispatchEvent(new openView.MouseEvent("mousedown", { bubbles: true, cancelable: true, view: openView }));
    try {
      await waitFor(() => {
        const current = getCatalogLeftContexts()[0] || null;
        const currentSelect = current?.document.querySelector("#ddlCategory");
        return currentSelect?.querySelector(`option[value="${categoryValue}"]`) ? currentSelect : null;
      }, 10000, 180);
    } catch (_error) {
      logRun(runCtx, "ERROR", `Không tìm thấy option Category value=${categoryValue}.`);
      throw new Error("CATEGORY_OPTION_NOT_FOUND");
    }

    select = getCatalogLeftContexts()[0]?.document.querySelector("#ddlCategory") || select;
    const changeView = select.ownerDocument?.defaultView || leftContext.window;
    select.value = categoryValue;
    select.dispatchEvent(new changeView.Event("input", { bubbles: true }));
    select.dispatchEvent(new changeView.Event("change", { bubbles: true }));

    try {
      await waitFor(() => {
        for (const current of getCatalogLeftContexts()) {
          const currentSelect = current.document.querySelector("#ddlCategory");
          if (String(currentSelect?.value || "") === categoryValue) return current;
        }
        return null;
      }, 14000, 200);
    } catch (_error) {
      logRun(runCtx, "ERROR", "WFX không xác nhận Category sau change event.", snapshotCatalogContexts());
      throw new Error("CATEGORY_NOT_CONFIRMED");
    }
    setCatalogProgress(`Đã chọn Category: ${categoryName}.`, "success");
    logRun(runCtx, "CATEGORY_CONFIRMED", `Đã chọn ${categoryName}.`, { value: categoryValue });
  }

  // Đúng theo claude.md: chỉ node có action trực tiếp (span[onclick]/a/button/role=button/
  // input[type=button]) và text chuẩn hóa bằng đúng "Master" mới được click. TUYỆT ĐỐI không
  // fallback sang img collapse hay container li/div/td chỉ vì nó chứa chữ "Master" — đó chính là
  // nguyên nhân bug "Master chỉ mở ở lần 4" (script cũ thử img/li sau khi click đúng span nhưng
  // left mới chỉ reload chứ chưa mở grid).
  const MASTER_ACTIONABLE_SELECTOR = 'span[onclick], a, button, [role="button"], input[type="button"]';

  function findExactActionableMaster(leftContext) {
    const nodes = [...leftContext.document.querySelectorAll(MASTER_ACTIONABLE_SELECTOR)];
    for (const node of nodes) {
      if (!elementIsUsable(node)) continue;
      const label = node.tagName === "INPUT" ? node.value : node.textContent;
      if (normalizeText(label).toLocaleLowerCase("en") === "master") return node;
    }
    return null;
  }

  async function waitForNewGrid(oldGridSnapshot, timeoutMs) {
    try {
      return await waitFor(() => {
        const candidate = findCatalogGridCandidate();
        return candidate && isNewDocument(candidate, oldGridSnapshot) ? candidate : null;
      }, timeoutMs, 200);
    } catch (_error) {
      return null;
    }
  }

  async function clickCatalogMaster(runCtx, oldGridSnapshot) {
    const deadline = Date.now() + 50000;
    let attempt = 0;
    let sawLeftFrame = false;
    let sawMaster = false;
    let leftSnapshot = null;

    while (Date.now() < deadline) {
      const leftContext = getCatalogLeftContexts()[0] || null;
      if (!leftContext) {
        await new Promise((resolve) => window.setTimeout(resolve, 200));
        continue;
      }
      sawLeftFrame = true;

      // Nếu document left vừa đổi (vd click Master lần trước chỉ làm nó reload), luôn resolve
      // lại rồi tìm/click lại đúng Master trên document mới — không bao giờ giữ candidate cũ.
      if (isNewDocument(leftContext, leftSnapshot)) {
        leftSnapshot = snapshotContext(leftContext);
        logRun(runCtx, "MASTER_FRAME", "Đã resolve document left.", {
          frame: leftContext.name,
          url: sanitizeUrlForLog(leftContext.url),
          generation: leftSnapshot.generation,
        });
      }

      const master = findExactActionableMaster(leftContext);
      if (!master) {
        await new Promise((resolve) => window.setTimeout(resolve, 250));
        continue;
      }
      sawMaster = true;

      attempt += 1;
      setCatalogProgress(`Đang mở Catalog → Master${attempt > 1 ? ` (thử ${attempt})` : ""}...`);
      logRun(runCtx, "MASTER_CLICK", "Click exact actionable Master.", {
        attempt,
        tag: master.tagName.toLocaleLowerCase("en"),
        onclick: Boolean(master.getAttribute("onclick")),
        leftGeneration: leftSnapshot.generation,
      });
      if (!clickElement(master, `Catalog Master #${attempt}`)) {
        await new Promise((resolve) => window.setTimeout(resolve, 250));
        continue;
      }

      const remaining = Math.max(200, Math.min(4500, deadline - Date.now()));
      const grid = await waitForNewGrid(oldGridSnapshot, remaining);
      if (grid) {
        logRun(runCtx, "MASTER_OPENED", "Master đã tạo Catalog Grid mới.", {
          attempt,
          url: sanitizeUrlForLog(grid.url),
        });
        return grid;
      }
      logRun(runCtx, "MASTER_RETRY", "Click chưa tạo Catalog Grid mới, sẽ resolve lại document.", { attempt });
    }

    if (!sawLeftFrame) {
      logRun(runCtx, "ERROR", "Không có frame left khi tìm Master.", snapshotCatalogContexts());
      throw new Error("CATALOG_LEFT_NOT_FOUND");
    }
    if (!sawMaster) {
      logRun(runCtx, "ERROR", "Không tìm thấy candidate Master.", snapshotCatalogContexts());
      throw new Error("MASTER_NOT_FOUND");
    }
    logRun(runCtx, "ERROR", "Đã click Master nhưng không có Catalog Grid mới trước deadline.", snapshotCatalogContexts());
    throw new Error("MASTER_CLICK_NO_NAVIGATION");
  }

  function getGridRootElement(gridContext) {
    return gridContext?.document.querySelector(".ag-root-wrapper") || null;
  }

  function gridElementIsRendered(element) {
    if (!elementIsUsable(element)) return false;
    const row = element.closest?.('.ag-row, [role="row"]');
    if (!row) return true;
    if (
      row.getAttribute?.("aria-hidden") === "true" ||
      row.classList?.contains("ag-row-loading") ||
      row.classList?.contains("ag-row-ghost")
    ) {
      return false;
    }

    // AG Grid giữ một virtual buffer ở trên/dưới phần người dùng nhìn thấy. Các row này vẫn có
    // getClientRects() và computed style như bình thường, nên elementIsUsable() chưa đủ.
    const viewport = row.closest?.(
      ".ag-center-cols-viewport, .ag-pinned-left-cols-viewport, .ag-pinned-right-cols-viewport, .ag-body-viewport",
    );
    if (
      !viewport ||
      typeof row.getBoundingClientRect !== "function" ||
      typeof viewport.getBoundingClientRect !== "function"
    ) {
      return true;
    }
    const rowRect = row.getBoundingClientRect();
    const viewportRect = viewport.getBoundingClientRect();
    return (
      rowRect.height > 0 &&
      rowRect.bottom > viewportRect.top + 0.5 &&
      rowRect.top < viewportRect.bottom - 0.5
    );
  }

  function readGridState(gridRoot) {
    const loading = [...gridRoot.querySelectorAll(
      ".ag-overlay-loading-wrapper, .ag-overlay-loading-center, .ag-loading, .ag-row-loading",
    )].some((element) => elementIsUsable(element));
    const noRows = [...gridRoot.querySelectorAll(
      ".ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center",
    )].some((element) => elementIsUsable(element));
    const rows = [...gridRoot.querySelectorAll(
      '.ag-center-cols-container .ag-row[row-index], .ag-center-cols-container [role="row"][row-index]',
    )].filter(gridElementIsRendered);
    return { loading, noRows, renderedRows: rows.length };
  }

  async function waitGridSettled(runCtx, gridRoot, timeoutMs = 35000) {
    const deadline = Date.now() + timeoutMs;
    let stableKey = null;
    let stableSince = 0;
    let last = { loading: true, noRows: false, renderedRows: 0 };
    while (Date.now() < deadline) {
      last = readGridState(gridRoot);
      const ready = !last.loading && (last.renderedRows > 0 || last.noRows);
      const key = `${last.loading}|${last.noRows}|${last.renderedRows}`;
      if (ready && key === stableKey) {
        if (Date.now() - stableSince >= 700) {
          logRun(runCtx, "GRID_SETTLED", "Grid đã ổn định.", last);
          return last;
        }
      } else {
        stableKey = key;
        stableSince = Date.now();
      }
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    logRun(runCtx, "GRID_TIMEOUT", "Grid chưa ổn định (còn loading hoặc không có row/no-rows overlay).", last);
    throw new Error("CATALOG_DATA_NOT_READY");
  }

  // KHÔNG quét toàn bộ frame rồi lấy input điểm cao nhất (đó là nguyên nhân bug chọn nhầm grid
  // rỗng/cũ). Chỉ thao tác trong đúng .ag-root-wrapper đã được clickCatalogMaster xác nhận; nếu
  // Angular thay document sau khi bật Floating Filter thì resolve lại đúng Catalog Grid
  // (wfxcataloglist + .ag-root-wrapper) rồi tiếp tục — không rơi về một document/frame khác.
  async function ensureFloatingFilterVisible(runCtx, gridContext) {
    const deadline = Date.now() + 25000;
    let lastClickAt = 0;
    let currentContext = gridContext;

    while (Date.now() < deadline) {
      const gridRoot = getGridRootElement(currentContext);
      if (gridRoot) {
        // Giống login.py `_show_catalog_floating_filter`: nút #showfloatingfilter chỉ HIỂN THỊ khi
        // hàng floating filter đang ẩn. Thấy nó = filter đang ẩn -> click để HIỆN hàng filter lên
        // cho người dùng thấy. Trước đây ta chỉ click khi không dò thấy input "usable", nên khi WFX
        // để hàng filter ẩn nhưng input vẫn còn trong DOM thì filter không tự hiện lên trên UI.
        const showButton = gridRoot.querySelector("#showfloatingfilter");
        if (showButton && elementIsUsable(showButton) && Date.now() - lastClickAt >= 1500) {
          lastClickAt = Date.now();
          logRun(runCtx, "FILTER_CLICK", "Click #showfloatingfilter.", { frame: currentContext.name });
          clickElement(showButton, "Show Floating Filters");
        }
        const codeInput = gridRoot.querySelector('input[aria-label="Code Filter Input"]');
        if (codeInput && elementIsUsable(codeInput) && !codeInput.disabled) {
          const state = readGridState(gridRoot);
          if (!state.loading && (state.renderedRows > 0 || state.noRows)) {
            logRun(runCtx, "FILTER_VISIBLE", "Code Filter hiển thị, enabled và grid đã có dữ liệu.", {
              frame: currentContext.name,
              url: sanitizeUrlForLog(currentContext.url),
              ...state,
            });
            return currentContext;
          }
          // Input đã visible nhưng grid chưa thật sự có dữ liệu (rawRows=0, không noRows overlay):
          // KHÔNG được báo thành công — chờ vòng tiếp theo.
        }
      }
      // Angular có thể thay document sau click; chỉ chấp nhận lại đúng Catalog Grid.
      const candidate = findCatalogGridCandidate();
      if (candidate) currentContext = candidate;
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    logRun(runCtx, "ERROR", "Floating Filter không sẵn sàng trước deadline.", snapshotCatalogContexts());
    throw new Error("FLOATING_FILTER_NOT_READY");
  }

  const FILTER_DEFINITIONS = Object.freeze({
    code: { label: "Code", selector: 'input[aria-label="Code Filter Input"]', valueColumn: "lnkArticleCode" },
    buyer_reference: {
      label: "Buyer Reference",
      selector: 'input[aria-label="Buyer Reference Filter Input"]',
      valueColumn: "lblBuyerReference",
    },
  });

  function readRenderedUniqueResults(gridRoot, filterKind) {
    const { valueColumn } = FILTER_DEFINITIONS[filterKind];
    const rawValueCells = [...gridRoot.querySelectorAll(`[role="gridcell"][col-id="${valueColumn}"]`)];
    const rawCodeButtons = [...gridRoot.querySelectorAll(
      '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]',
    )];
    const valueCells = rawValueCells.filter(gridElementIsRendered);
    const codeButtons = rawCodeButtons.filter(gridElementIsRendered);
    const values = valueCells.map((cell) => (valueColumn === "lnkArticleCode"
      ? normalizeText(cell.querySelector('input[type="button"]')?.value)
      : normalizeText(cell.textContent))).filter(Boolean);

    // Pinned columns/viewport recycling của AG Grid có thể tạo nhiều DOM node cho cùng một row.
    // Đếm/khử trùng theo giá trị Code duy nhất, nhưng vẫn giữ toàn bộ button tương ứng để chọn
    // đúng node còn sống tại thời điểm click.
    const valueMap = new Map();
    for (const value of values) {
      const key = value.toLocaleLowerCase("vi");
      if (!valueMap.has(key)) valueMap.set(key, value);
    }
    const codeMap = new Map();
    for (const button of codeButtons) {
      const code = normalizeText(button.value);
      if (!code) continue;
      const key = code.toLocaleLowerCase("vi");
      if (!codeMap.has(key)) codeMap.set(key, { code, buttons: [] });
      codeMap.get(key).buttons.push(button);
    }
    const codeEntries = [...codeMap.values()];
    return {
      values: [...valueMap.values()],
      codes: codeEntries.map((entry) => entry.code),
      codeEntries,
      diagnostics: {
        rawValueCells: rawValueCells.length,
        renderedValueCells: valueCells.length,
        rawCodeButtons: rawCodeButtons.length,
        renderedCodeButtons: codeButtons.length,
        uniqueValues: valueMap.size,
        uniqueCodes: codeMap.size,
      },
    };
  }

  async function fillAndConfirmFilter(runCtx, gridRoot, filterKind, query) {
    const { label, selector } = FILTER_DEFINITIONS[filterKind];
    for (const clearSelector of [
      'input[aria-label="Code Filter Input"]',
      'input[aria-label="Buyer Reference Filter Input"]',
    ]) {
      const existing = gridRoot.querySelector(clearSelector);
      if (existing && elementIsUsable(existing)) dispatchFilledValue(existing, "");
    }

    let input;
    try {
      input = await waitFor(() => {
        const candidate = gridRoot.querySelector(selector);
        return candidate && elementIsUsable(candidate) ? candidate : null;
      }, 7000, 160);
    } catch (_error) {
      logRun(runCtx, "ERROR", `Không tìm thấy ${label} Filter Input trong grid đã xác nhận.`);
      throw new Error("FLOATING_FILTER_NOT_READY");
    }

    logRun(runCtx, "FILTER_FILLED", `Đang điền ${label}.`, { query });
    dispatchFilledValue(input, query);
    await new Promise((resolve) => window.setTimeout(resolve, 150));
    if (input.value !== query) {
      logRun(runCtx, "ERROR", "Giá trị filter không khớp sau khi điền.", { expected: query, actual: input.value });
      throw new Error("FILTER_VALUE_NOT_CONFIRMED");
    }
    return input;
  }

  async function waitFilterResultsSettled(runCtx, gridRoot, filterKind, query, timeoutMs = 22000) {
    const deadline = Date.now() + timeoutMs;
    const queryFolded = query.toLocaleLowerCase("vi");
    // Bám sát login.py `_filter_grid_and_maybe_open`: chờ 1s cho AG Grid nhận filter, rồi POLL cho
    // tới khi MỌI value đang render đều chứa query (filter đã áp xong).
    //
    // TUYỆT ĐỐI KHÔNG kết luận "hết kết quả" chỉ vì thấy no-rows overlay: WFX áp Code filter qua một
    // vòng gọi server — nó XOÁ sạch row cũ trước (grid trống + no-rows overlay, và KHÔNG có loading
    // overlay để ta nhận biết) rồi mới NẠP row đã lọc. Bản 1.8.2 chốt "no-rows ổn định 800ms" đã rơi
    // đúng khoảng trống này và báo nhầm "không có kết quả" dù thật ra có (bug query "5526"). Vì vậy
    // chỉ chốt khi filter thật sự áp xong (applied), hoặc khi hết deadline.
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    let last = readRenderedUniqueResults(gridRoot, filterKind);
    while (Date.now() < deadline) {
      last = readRenderedUniqueResults(gridRoot, filterKind);
      const applied = last.values.length > 0
        && last.values.every((value) => value.toLocaleLowerCase("vi").includes(queryFolded));
      if (applied) {
        logRun(runCtx, "FILTER_RESULTS", "Đã đọc kết quả đang render.", {
          uniqueCount: last.codes.length,
          codes: last.codes.slice(0, 20),
          ...last.diagnostics,
        });
        return last;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
    // Hết deadline mà không value nào khớp query. KHÔNG trả code stale (row Master cũ chưa lọc) để
    // tránh báo nhầm "nhiều kết quả"; coi như không có — caller sẽ báo "Không tìm thấy".
    logRun(runCtx, "FILTER_RESULTS", "Hết thời gian chờ; không có value nào khớp query.", {
      uniqueCount: 0,
      codes: [],
      ...last.diagnostics,
    });
    return { values: [], codes: [], codeEntries: [], diagnostics: last.diagnostics };
  }

  function getArticleContexts() {
    const contexts = [];
    const roots = [PAGE_WINDOW, ...popupWindows].filter((candidate) => {
      try { return candidate && !candidate.closed; } catch (_error) { return false; }
    });
    for (const rootWindow of roots) {
      for (const context of getAccessibleContexts(rootWindow)) {
        if (
          context.name === "ArticleTop" ||
          context.document.querySelector("#CostSheet, #BOMMaster")
        ) {
          contexts.push(context);
        }
      }
    }
    return contexts;
  }

  async function clickAndConfirmArticle(runCtx, button, articleCode) {
    // Catalog/grid frame chỉ xuất hiện sau khi mở module; wrap lại ngay trước click để bắt đúng
    // window.open() phát ra từ iframe hiện tại.
    installPopupTracker();
    const previousDocuments = new Set(getArticleContexts().map((context) => context.document));
    const previousPopups = new Set([...popupWindows].filter((candidate) => {
      try { return candidate && !candidate.closed; } catch (_error) { return false; }
    }));

    if (!clickElement(button, `Article ${articleCode}`)) throw new Error("ARTICLE_CLICK_FAILED");
    try {
      await waitFor(() => {
        for (const popup of popupWindows) {
          try {
            if (popup && !popup.closed && !previousPopups.has(popup)) return popup;
          } catch (_error) {
            // Popup đang điều hướng; vòng poll sau sẽ kiểm tra lại.
          }
        }
        return getArticleContexts().find((context) => !previousDocuments.has(context.document)) || null;
      }, 12000, 220);
    } catch (_error) {
      logRun(runCtx, "ERROR", "Đã click Code nhưng không xác nhận được Article mở.", { articleCode });
      throw new Error("ARTICLE_OPEN_NOT_CONFIRMED");
    }
  }

  async function filterCatalogGrid(runCtx, gridContext, filterKind, query) {
    const definition = FILTER_DEFINITIONS[filterKind];
    if (!definition) throw new Error("INVALID_FILTER");
    const label = definition.label;
    const gridRoot = getGridRootElement(gridContext);
    if (!gridRoot) throw new Error("CATALOG_GRID_NOT_FOUND");

    await fillAndConfirmFilter(runCtx, gridRoot, filterKind, query);
    const results = await waitFilterResultsSettled(runCtx, gridRoot, filterKind, query);

    if (!results.codes.length) {
      setCatalogProgress(`Không tìm thấy ${label}: ${query}.`, "error");
      showToast(`Không tìm thấy kết quả cho ${label}: ${query}.`, "warning", 5000);
      return { outcome: "none", ...results };
    }

    if (results.codes.length > 1) {
      setCatalogProgress(`Có ${results.codes.length} kết quả: ${results.codes.slice(0, 4).join(", ")}`, "warning");
      showToast(`Có ${results.codes.length} kết quả; giữ danh sách để bạn tự chọn.`, "info", 5000);
      return { outcome: "multiple", ...results };
    }

    const targetCode = results.codes[0];
    // Resolve lại đúng button ngay trước click — AG Grid có thể đã tái sử dụng row.
    const freshResults = readRenderedUniqueResults(gridRoot, filterKind);
    const targetEntry = freshResults.codeEntries.find(
      (entry) => entry.code.toLocaleLowerCase("vi") === targetCode.toLocaleLowerCase("vi"),
    );
    const target = targetEntry?.buttons.find(elementIsUsable) || null;
    if (!target) {
      logRun(runCtx, "ERROR", "Row đổi trước thời điểm click.", { targetCode });
      return { outcome: "detached", ...results };
    }

    setCatalogProgress(`Đã tìm thấy ${targetCode}, đang mở Article...`);
    await clickAndConfirmArticle(runCtx, target, targetCode);
    setCatalogProgress(`Đã mở style ${targetCode}.`, "success");
    showToast(`Đã tìm và mở style ${targetCode}.`, "success");
    return { outcome: "opened", articleCode: targetCode, ...results };
  }

  async function openArticleDestination(runCtx, destination, articleCode) {
    const destinations = {
      costsheet: { label: "Costsheet", selector: "#CostSheet" },
      bom: { label: "BOM", selector: "#BOMMaster" },
    };
    const targetDefinition = destinations[destination];
    if (!targetDefinition) return;
    setCatalogProgress(`Đang chờ Article để mở ${targetDefinition.label}...`);

    let target;
    try {
      target = await waitFor(() => {
        const roots = [PAGE_WINDOW, ...popupWindows].filter((candidate) => {
          try { return candidate && !candidate.closed; } catch (_error) { return false; }
        });
        for (const rootWindow of roots) {
          // Costsheet/BOM cũng có thể gọi window.open() từ frame ArticleTop.
          installPopupTracker(rootWindow);
          for (const context of getAccessibleContexts(rootWindow)) {
            if (context.name === "ArticleTop" || context.document.querySelector(targetDefinition.selector)) {
              const element = context.document.querySelector(targetDefinition.selector);
              if (element) return element;
            }
          }
        }
        return null;
      }, 40000, 280);
    } catch (_error) {
      logRun(runCtx, "ERROR", `Không tìm thấy popup ArticleTop để mở ${targetDefinition.label}.`);
      throw new Error("ARTICLE_DESTINATION_NOT_FOUND");
    }
    if (!clickElement(target, targetDefinition.label)) throw new Error("ARTICLE_DESTINATION_NOT_FOUND");
    setCatalogProgress(`Đã mở ${articleCode} → ${targetDefinition.label}.`, "success");
    showToast(`Đã mở ${targetDefinition.label}.`, "success");
  }

  async function runCatalogRequest(request) {
    if (automationInFlight) return;
    if (getAuthState() !== "authenticated") {
      writeValue(STORAGE.pendingAction, { ...request, expiresAt: Date.now() + PENDING_TTL_MS });
      showToast("Sẽ chạy Catalog sau khi đăng nhập.", "info");
      await continueLogin({ reset: true, source: "catalog" });
      return;
    }

    deleteValue(STORAGE.pendingAction);
    clearAutomationLog();
    const runCtx = createRunContext(request);
    logRun(runCtx, "START", "Bắt đầu Catalog automation.", {
      version: SCRIPT_VERSION,
      mode: request.mode,
      filterKind: request.filterKind,
      category: request.categoryName,
      query: normalizeText(request.query).slice(0, 120),
    });
    setAutomationBusy(true, "Đang mở Catalog...");
    try {
      // Snapshot document left/grid TRƯỚC khi click Catalog — đây là mốc để xác nhận "mới" ở
      // mọi bước sau, giống old_left/old_grid trong tham chiếu Python.
      const leftSnapshot = snapshotLeftDocument();
      const gridSnapshot = snapshotGridDocument();

      const catalogAnchor = await waitForModuleAnchor("0003_6200", 8000);
      if (!catalogAnchor) throw new Error("CATALOG_MENU_NOT_FOUND");
      setCatalogProgress("Đang mở Catalog...");
      logRun(runCtx, "CATALOG", "Click menu Catalog.", describeElement(catalogAnchor));
      if (!clickElement(catalogAnchor, "Catalog menu")) throw new Error("CATALOG_CLICK_FAILED");

      const leftContext = await resolveNewLeftFrame(runCtx, leftSnapshot);
      await selectCatalogCategory(runCtx, leftContext, request.categoryName, request.categoryValue);
      const gridContext = await clickCatalogMaster(runCtx, gridSnapshot);
      const gridRoot = getGridRootElement(gridContext);
      if (!gridRoot) throw new Error("CATALOG_GRID_NOT_FOUND");
      await waitGridSettled(runCtx, gridRoot);
      const filterContext = await ensureFloatingFilterVisible(runCtx, gridContext);

      if (request.mode === "prepare") {
        setCatalogProgress(`Catalog ${request.categoryName} đã sẵn sàng để lọc.`, "success");
        showToast("Đã mở Catalog → Master → Floating Filter.", "success");
        return;
      }

      const result = await filterCatalogGrid(runCtx, filterContext, request.filterKind, request.query);
      if (result.outcome === "detached") {
        setCatalogProgress("Row đổi trước thời điểm click. Hãy thử lại.", "error");
        showToast("Kết quả vừa đổi trước khi click. Hãy thử lại.", "warning", 5000);
        return;
      }
      if (request.destination && result.outcome === "opened") {
        await openArticleDestination(runCtx, request.destination, result.articleCode);
      }
    } catch (error) {
      const messages = {
        CATALOG_MENU_NOT_FOUND: "Không tìm thấy menu Catalog trên WFX Home.",
        CATALOG_CLICK_FAILED: "Không click được menu Catalog.",
        CATALOG_LEFT_NOT_FOUND: "Catalog đã mở nhưng không tìm thấy frame left hoặc Category.",
        CATEGORY_OPTION_NOT_FOUND: `Không tải được Category ${request.categoryName}.`,
        CATEGORY_NOT_CONFIRMED: `WFX không xác nhận Category ${request.categoryName}.`,
        MASTER_NOT_FOUND: "Đã vào Catalog nhưng không tìm thấy mục Master trong frame left.",
        MASTER_CLICK_NO_NAVIGATION: "Đã click Master nhiều lần nhưng WFX không mở Catalog Grid.",
        CATALOG_GRID_NOT_FOUND: "Master đã được click nhưng Catalog Grid không tải xong.",
        CATALOG_DATA_NOT_READY: "Catalog Grid đã mở nhưng dữ liệu row chưa tải xong.",
        FLOATING_FILTER_NOT_READY: "Catalog Grid đã mở nhưng Floating Filter không sẵn sàng.",
        FILTER_VALUE_NOT_CONFIRMED: "Không điền được giá trị lọc vào ô filter.",
        FILTER_RESULTS_NOT_READY: "Đã điền filter nhưng WFX chưa trả kết quả ổn định.",
        ARTICLE_OPEN_NOT_CONFIRMED: "Đã click Code nhưng WFX không mở Article. Hãy cho phép popup cho trang WFX rồi thử lại.",
        ARTICLE_DESTINATION_NOT_FOUND: "Article đã mở nhưng không tìm thấy Costsheet/BOM.",
        TIMEOUT: "WFX tải quá chậm hoặc cấu trúc Catalog đã thay đổi.",
      };
      const message = messages[error?.message] || `Catalog lỗi: ${error?.message || error}`;
      console.error("[WFX Smart] Catalog error:", error);
      logRun(runCtx, "ERROR", message, {
        code: error?.message || String(error),
        contexts: snapshotCatalogContexts(),
      });
      setCatalogProgress(message, "error");
      showToast(message, "error", 6000);
    } finally {
      setAutomationBusy(false);
      saveCatalogForm();
    }
  }

  function startCatalogAction(mode, filterKind = null, destination = null) {
    if (automationInFlight) return;
    const form = readCatalogForm();
    const query = filterKind === "buyer_reference" ? form.buyerReference : form.code;
    if (mode === "search" && !query) {
      const field = filterKind === "buyer_reference" ? ui.catalogBuyerReference : ui.catalogCode;
      field.focus();
      showToast(`Vui lòng nhập ${filterKind === "buyer_reference" ? "Buyer Reference" : "Code"}.`, "warning");
      return;
    }
    if (destination && form.categoryValue !== "01") {
      showToast("Costsheet và BOM chỉ hỗ trợ Category Apparel.", "warning", 4500);
      return;
    }
    saveCatalogForm();
    void runCatalogRequest({
      type: "catalog",
      mode,
      filterKind,
      query,
      destination,
      categoryName: form.categoryName,
      categoryValue: form.categoryValue,
      expiresAt: Date.now() + PENDING_TTL_MS,
    });
  }

  async function processPendingAction() {
    const action = getPending(STORAGE.pendingAction);
    if (!action || getAuthState() !== "authenticated") return;
    if (action.type === "catalog") {
      await runCatalogRequest(action);
      return;
    }
    if (action.type !== "module") return;
    const module = ALL_MODULES.find((item) => item.id === action.moduleId) || {
      id: action.moduleId,
      name: action.moduleName || "module",
    };
    await openModule(module);
  }

  function formatHotkey(hotkey = getHotkey()) {
    const parts = [];
    if (hotkey.ctrl) parts.push("Ctrl");
    if (hotkey.alt) parts.push("Alt");
    if (hotkey.shift) parts.push("Shift");
    if (hotkey.meta) parts.push("Win");
    const key = hotkey.code.startsWith("Key")
      ? hotkey.code.slice(3)
      : hotkey.code.startsWith("Digit")
        ? hotkey.code.slice(5)
        : hotkey.key;
    parts.push(key);
    return parts.join(" + ");
  }

  function eventMatchesHotkey(event, hotkey = getHotkey()) {
    return (
      event.code === hotkey.code &&
      event.ctrlKey === hotkey.ctrl &&
      event.altKey === hotkey.alt &&
      event.shiftKey === hotkey.shift &&
      event.metaKey === hotkey.meta
    );
  }

  function updateHotkeyLabels() {
    if (!ui) return;
    const label = formatHotkey();
    ui.hotkeyLabel.textContent = label;
    ui.hotkeyButton.textContent = hotkeyCapture ? "Nhấn tổ hợp phím..." : label;
    ui.hotkeyButton.classList.toggle("capturing", hotkeyCapture);
  }

  function beginHotkeyCapture() {
    hotkeyCapture = true;
    // Bảo đảm keydown đi tới đúng nút kể cả WFX vừa cưỡng bức focus sang control khác.
    bestEffort(() => ui.hotkeyButton.focus({ preventScroll: true }), "focus hotkey");
    updateHotkeyLabels();
    showToast("Nhấn tổ hợp mới. Esc để hủy.", "info");
  }

  // Logic "ghi nhận tổ hợp phím mới" TRƯỚC ĐÂY nằm trong handleKeydown (gắn trên `document`,
  // capture phase) và chỉ dựa vào cờ hotkeyCapture để bật/tắt. Nếu cờ đó vì lý do gì đó không
  // được tắt đúng lúc (race condition, quên gọi, blur không bắn...), preventDefault() sẽ chặn
  // MỌI phím ở MỌI ô nhập trên toàn trang — đây chính là bug "gõ/xoá chữ ở ô nào cũng không được".
  // Sửa tận gốc: chuyển hẳn logic này thành listener gắn TRỰC TIẾP trên nút hotkey, chỉ có thể
  // chạy khi chính nút đó đang focus — không còn phụ thuộc một cờ toàn cục nào nữa, nên không có
  // cách nào để nó "kẹt" và ảnh hưởng tới ô nhập khác.
  function handleHotkeyButtonKeydown(event) {
    if (!hotkeyCapture) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.code === "Escape") {
      hotkeyCapture = false;
      updateHotkeyLabels();
      return;
    }
    if (["ControlLeft", "ControlRight", "AltLeft", "AltRight", "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight"].includes(event.code)) {
      return;
    }
    const functionKey = /^F(?:[2-9]|1[0-2])$/.test(event.code);
    if (!event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey && !functionKey) {
      showToast("Dùng ít nhất Ctrl, Alt, Shift hoặc phím F2–F12.", "warning", 4200);
      return;
    }
    if (UNSAFE_HOTKEY_CODES.includes(event.code)) {
      showToast("Không dùng Backspace/Delete/Enter/Tab/Space làm hotkey (trùng phím soạn thảo).", "warning", 4600);
      return;
    }
    writeValue(STORAGE.hotkey, {
      ctrl: event.ctrlKey,
      alt: event.altKey,
      shift: event.shiftKey,
      meta: event.metaKey,
      code: event.code,
      key: event.key.length === 1 ? event.key.toUpperCase() : event.key,
    });
    hotkeyCapture = false;
    updateHotkeyLabels();
    showToast(`Đã đặt hotkey: ${formatHotkey()}`, "success");
  }

  function isEditableElement(node) {
    if (!node || !node.tagName) return false;
    return node.tagName === "INPUT" || node.tagName === "TEXTAREA" || node.isContentEditable === true;
  }

  // GIẢ THUYẾT NGUYÊN NHÂN "Backspace không xoá được", sau khi đã loại trừ khả năng hotkey:
  // Nhiều trang ASP.NET WebForms cũ như WFX tự gắn 1 listener keydown trên `document` để CHẶN
  // phím Backspace khi người dùng KHÔNG đang gõ trong ô input/textarea (tránh Backspace vô tình
  // kích hoạt điều hướng "back" của trình duyệt, làm mất dữ liệu form chưa lưu). Guard đó thường
  // kiểm tra `document.activeElement.tagName`.
  // VẤN ĐỀ: input/textarea của panel này nằm TRONG một Shadow DOM (mode "open"). Khi người dùng
  // thật sự đang gõ bên trong đó, `document.activeElement` (nhìn từ NGOÀI shadow root, tức từ
  // chính script của WFX) không bao giờ trả về cái input thật — nó chỉ thấy phần tử HOST của
  // shadow root (một <div>, không phải INPUT). Guard của WFX vì vậy tưởng nhầm "không phải đang
  // gõ chữ" và preventDefault() mất phím Backspace — dù người dùng đang gõ thật trong Code, Buyer
  // Reference, User ID... Đây là điểm mù cố hữu của Shadow DOM, không phải lỗi ở input của panel.
  // KHẮC PHỤC: composedPath() vẫn "nhìn xuyên" được shadow boundary để biết phần tử thật sự nhận
  // phím là gì. Nếu đúng là input/textarea của panel, ta stopPropagation() NGAY Ở PHA CAPTURE trên
  // `document` (listener này đã đăng ký capture:true) — chặn event lan tới listener của WFX (thường
  // đăng ký ở bubble phase, tức chạy SAU) trước khi nó kịp preventDefault(). Ta KHÔNG tự
  // preventDefault() ở đây nên trình duyệt vẫn xử lý xoá/gõ chữ hoàn toàn bình thường.
  function isOwnEditableKeydown(event) {
    if (!ui) return false;
    const realTarget = typeof event.composedPath === "function" ? event.composedPath()[0] : event.target;
    return Boolean(realTarget) && ui.shadow.contains(realTarget) && isEditableElement(realTarget);
  }

  // Listener toàn trang này giờ có hai việc: (1) bảo vệ các ô nhập của panel khỏi bị trang WFX
  // "nuốt" phím soạn thảo do điểm mù Shadow DOM nói trên, và (2) nhận diện hotkey đã lưu để
  // mở/đóng panel. Không còn nhánh nào preventDefault() một cách "kẹt" nữa.
  function handleKeydown(event) {
    // document listener chạy ở capture phase, tức chạy TRƯỚC listener keydown của nút trong
    // Shadow DOM. Nếu xử lý Ctrl+Alt+X tại đây trong lúc đang ghi hotkey, panel sẽ toggle và
    // listener của nút không bao giờ nhận được tổ hợp để lưu.
    if (hotkeyCapture) return;

    if (isOwnEditableKeydown(event)) {
      event.stopPropagation();
      return;
    }

    if (eventMatchesHotkey(event)) {
      event.preventDefault();
      event.stopPropagation();
      togglePanel();
    }
  }

  function refreshStatus() {
    if (!ui) return;
    const details = authDetails();
    ui.statusCard.dataset.tone = details.tone;
    ui.statusTitle.textContent = details.label;
    ui.statusDetail.textContent = details.detail;
    ui.accountChip.textContent = getAccount().userId || "Chưa có account";
    ui.loginButton.querySelector("span").textContent = loginInFlight ? "Đang đăng nhập..." : "Kết nối / Login";
    // Đã đăng nhập rồi thì không cần hiện nút Kết nối/Login nữa (chỉ hiện khi chưa đăng nhập
    // hoặc đang trong lúc đăng nhập để người dùng thấy tiến trình).
    ui.loginButton.hidden = details.state === "authenticated" && !loginInFlight;
  }

  function filterModules(query) {
    if (!ui) return;
    const normalized = String(query || "").trim().toLocaleLowerCase("vi");
    let visibleCount = 0;
    ui.moduleButtons.forEach((button) => {
      const matches = !normalized || button.dataset.search.includes(normalized);
      button.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    ui.groupSections.forEach((section) => {
      section.hidden = ![...section.querySelectorAll(".module-button")].some((button) => !button.hidden);
    });
    ui.emptyState.hidden = visibleCount > 0;
  }

  function openPanel({ skipAutoLogin = false } = {}) {
    if (!ui) return;
    ui.panel.classList.add("panel-open");
    ui.launcher.classList.add("launcher-active");
    ui.panel.setAttribute("aria-hidden", "false");
    refreshStatus();
    window.clearInterval(statusTimer);
    statusTimer = window.setInterval(refreshStatus, 1500);
    window.setTimeout(() => ui.searchInput.focus(), 180);

    const account = getAccount();
    if (!account.userId || !account.password) {
      openSettings();
      return;
    }
    if (!skipAutoLogin && getPreferences().autoLoginOnOpen && getAuthState() !== "authenticated") {
      void continueLogin({ reset: true, source: "panel" });
    }
  }

  function closePanel() {
    if (!ui) return;
    ui.panel.classList.remove("panel-open");
    ui.launcher.classList.remove("launcher-active");
    ui.panel.setAttribute("aria-hidden", "true");
    ui.settingsOverlay.classList.remove("settings-open");
    hotkeyCapture = false;
    updateHotkeyLabels();
    window.clearInterval(statusTimer);
  }

  function togglePanel() {
    if (!ui) return;
    if (ui.panel.classList.contains("panel-open")) closePanel();
    else openPanel();
  }

  function openSettings() {
    if (!ui) return;
    const account = getAccount();
    const preferences = getPreferences();
    ui.userInput.value = account.userId;
    ui.passwordInput.value = account.password;
    ui.companyInput.value = account.companyId;
    ui.autoLoginInput.checked = preferences.autoLoginOnOpen;
    ui.closeAfterModuleInput.checked = preferences.closeAfterModule;
    applyTheme(preferences.theme);
    ui.passwordInput.type = "password";
    ui.togglePasswordButton.textContent = "Hiện";
    updateHotkeyLabels();
    ui.settingsOverlay.classList.add("settings-open");
    window.setTimeout(() => (account.userId ? ui.passwordInput : ui.userInput).focus(), 100);
  }

  function closeSettings() {
    if (!ui) return;
    ui.settingsOverlay.classList.remove("settings-open");
    hotkeyCapture = false;
    updateHotkeyLabels();
  }

  function openLog() {
    if (!ui) return;
    ui.logButton.classList.remove("has-alert");
    renderAutomationLog();
    ui.logOverlay.classList.add("log-open");
  }

  function closeLog() {
    if (!ui) return;
    ui.logOverlay.classList.remove("log-open");
  }

  function toggleLog() {
    if (!ui) return;
    if (ui.logOverlay.classList.contains("log-open")) closeLog();
    else openLog();
  }

  function saveSettings() {
    const userId = ui.userInput.value.trim();
    const password = ui.passwordInput.value;
    const companyId = ui.companyInput.value.trim() || "psh";
    if (!userId || !password) {
      showToast("User ID và Password không được để trống.", "warning");
      return;
    }
    const accountSaved = writeValue(STORAGE.account, { userId, password, companyId });
    const preferencesSaved = writeValue(STORAGE.preferences, {
      autoLoginOnOpen: ui.autoLoginInput.checked,
      closeAfterModule: ui.closeAfterModuleInput.checked,
      theme: getSelectedTheme(),
    });
    if (!accountSaved || !preferencesSaved) {
      showToast("Không thể lưu thiết lập Chrome Extension.", "error");
      return;
    }
    closeSettings();
    refreshStatus();
    showToast("Đã lưu thiết lập.", "success");
    if (ui.autoLoginInput.checked && getAuthState() !== "authenticated") {
      void continueLogin({ reset: true, source: "settings" });
    }
  }

  function buildModuleMarkup() {
    return MODULE_GROUPS.map((group) => `
      <section class="module-group" data-group="${group.name}">
        <div class="group-heading">
          <span class="group-accent accent-${group.accent}"></span>
          <span>${group.name}</span>
          <span class="group-count">${group.modules.length}</span>
        </div>
        <div class="module-grid">
          ${group.modules.map((module) => `
            <button class="module-button" type="button" data-module-id="${module.id}" data-search="${module.name.toLocaleLowerCase("vi")} ${group.name.toLocaleLowerCase("vi")}">
              <span class="module-icon accent-${group.accent}">${module.icon}</span>
              <span class="module-name">${module.name}</span>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5-5 5"/></svg>
            </button>
          `).join("")}
        </div>
      </section>
    `).join("");
  }

  function createUI() {
    if (document.getElementById(ROOT_ID)) return;
    const host = document.createElement("div");
    host.id = ROOT_ID;
    document.documentElement.appendChild(host);
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>${STYLES}</style>
      <button class="launcher" type="button" aria-label="Mở WFX Smart Automation" title="WFX Smart Automation">
        <svg viewBox="0 0 28 28" aria-hidden="true">
          <path class="logo-frame" d="M5.2 6.7 14 2.4l8.8 4.3v10.6L14 25.6l-8.8-8.3V6.7Z"/>
          <path class="logo-mark" d="m8.6 9.2 2.6 9.2 2.8-6.2 2.8 6.2 2.6-9.2"/>
        </svg>
        <span class="launcher-pulse"></span>
      </button>

      <aside class="panel" aria-hidden="true" aria-label="WFX Smart Automation">
        <div class="panel-glow"></div>
        <header class="panel-header">
          <div class="brand">
            <div class="brand-logo">
              <svg viewBox="0 0 28 28" aria-hidden="true"><path d="M5.2 6.7 14 2.4l8.8 4.3v10.6L14 25.6l-8.8-8.3V6.7Z"/><path class="brand-mark" d="m8.6 9.2 2.6 9.2 2.8-6.2 2.8 6.2 2.6-9.2"/></svg>
            </div>
            <div><strong>WFX Smart</strong><span>Automation workspace</span></div>
          </div>
          <div class="header-actions">
            <button class="icon-button log-button" type="button" aria-label="Nhật ký Catalog" title="Nhật ký Catalog">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7h11M8 12h11M8 17h7"/><path d="M4 7h.01M4 12h.01M4 17h.01"/></svg>
              <span class="log-alert" aria-hidden="true"></span>
            </button>
            <button class="icon-button settings-button" type="button" aria-label="Mở cài đặt" title="Cài đặt">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.3a3.3 3.3 0 1 0 0-6.6 3.3 3.3 0 0 0 0 6.6Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.55V21h-4v-.08A1.7 1.7 0 0 0 8.95 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.58 15 1.7 1.7 0 0 0 3 14H3v-4h.08A1.7 1.7 0 0 0 4.6 8.95a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.58 1.7 1.7 0 0 0 10 3V3h4v.08A1.7 1.7 0 0 0 15.05 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.42 9 1.7 1.7 0 0 0 21 10h.08v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>
            </button>
            <button class="icon-button close-button" type="button" aria-label="Đóng panel" title="Đóng">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </button>
          </div>
        </header>

        <div class="panel-body">
          <section class="catalog-card">
            <div class="catalog-heading">
              <div><span class="catalog-kicker">QUICK AUTOMATION</span><strong>Catalog Control</strong></div>
              <button class="catalog-open-button" type="button" data-catalog-action="prepare">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h6l2 2h8v12H4V5Z"/><path d="m9 14 2 2 4-5"/></svg>
                Mở Catalog
              </button>
            </div>
            <label class="catalog-category-row">
              <span>Category</span>
              <select class="catalog-category">
                ${Object.keys(CATEGORIES).map((name) => `<option value="${name}">${name}</option>`).join("")}
              </select>
            </label>
            <div class="catalog-query-row">
              <label><span>Code</span><input class="catalog-code" type="text" autocomplete="off" placeholder="Nhập article code..." /></label>
              <div class="catalog-query-actions">
                <button type="button" data-catalog-action="code-find">Tìm</button>
                <button class="destination-button" type="button" data-catalog-action="code-costsheet">Costsheet</button>
                <button class="destination-button" type="button" data-catalog-action="code-bom">BOM</button>
              </div>
            </div>
            <div class="catalog-query-row">
              <label><span>Buyer Reference</span><input class="catalog-buyer-reference" type="text" autocomplete="off" placeholder="Nhập buyer reference..." /></label>
              <div class="catalog-query-actions">
                <button type="button" data-catalog-action="buyer-find">Tìm</button>
                <button class="destination-button" type="button" data-catalog-action="buyer-costsheet">Costsheet</button>
                <button class="destination-button" type="button" data-catalog-action="buyer-bom">BOM</button>
              </div>
            </div>
            <div class="catalog-progress" data-tone="info" hidden>Sẵn sàng.</div>
          </section>

          <label class="search-box">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
            <input type="search" placeholder="Tìm nhanh module..." autocomplete="off" />
            <kbd class="hotkey-label">Ctrl + Alt + X</kbd>
          </label>

          <div class="modules-scroll">
            <div class="module-list">${buildModuleMarkup()}</div>
            <div class="empty-state" hidden>
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
              <strong>Không tìm thấy module</strong><span>Thử một từ khóa khác</span>
            </div>
          </div>
        </div>

        <footer class="panel-footer">
          <span><i></i> Chrome Extension active</span>
          <span>v${SCRIPT_VERSION}</span>
        </footer>

        <div class="settings-overlay" aria-label="Thiết lập WFX">
          <div class="settings-sheet">
            <div class="sheet-handle"></div>
            <div class="sheet-heading"><div><strong>Thiết lập thông minh</strong><span>Lưu riêng trong Chrome Extension trên máy này</span></div><button class="icon-button settings-close-button" type="button" aria-label="Đóng cài đặt"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div>
            <div class="settings-status">
              <div class="status-card" data-tone="neutral">
                <span class="status-orbit"><span></span></span>
                <div><strong class="status-title">Đang kiểm tra...</strong><span class="status-detail">WFX session</span></div>
              </div>
              <span class="account-chip">Chưa có account</span>
              <button class="primary-button login-button" type="button">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></svg>
                <span>Kết nối / Login</span>
                <i></i>
              </button>
            </div>
            <div class="form-grid">
              <label><span>User ID</span><input class="user-input" type="text" autocomplete="username" placeholder="WFX User ID" /></label>
              <label><span>Company ID</span><input class="company-input" type="text" autocomplete="organization" value="psh" /></label>
              <label class="password-field"><span>Password</span><div><input class="password-input" type="password" autocomplete="current-password" placeholder="WFX Password" /><button class="toggle-password" type="button">Hiện</button></div></label>
            </div>
            <div class="setting-row hotkey-row"><div><strong>Hotkey mở panel</strong><span>Nhấn nút rồi nhập tổ hợp mới</span></div><button class="hotkey-button" type="button">Ctrl + Alt + X</button></div>
            <label class="setting-row toggle-row"><div><strong>Tự login khi mở panel</strong><span>Chạy trên chính tab WFX hiện tại</span></div><input class="auto-login-input" type="checkbox" checked /><i></i></label>
            <label class="setting-row toggle-row"><div><strong>Đóng panel sau khi mở module</strong><span>Giữ màn hình làm việc gọn hơn</span></div><input class="close-module-input" type="checkbox" checked /><i></i></label>
            <div class="setting-row appearance-row"><div><strong>Giao diện</strong><span>Chọn nền sáng hoặc tối</span></div>
              <div class="segmented" role="group" aria-label="Giao diện">
                <button class="seg-button" type="button" data-theme-choice="light" aria-pressed="true"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>Sáng</button>
                <button class="seg-button" type="button" data-theme-choice="dark" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 13.5A8 8 0 1 1 10.5 4a6.3 6.3 0 0 0 9.5 9.5Z"/></svg>Tối</button>
              </div>
            </div>
            <div class="security-note"><svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg><span>Mật khẩu nằm trong vùng lưu trữ của extension, không đưa vào DOM hay localStorage của trang WFX.</span></div>
            <button class="save-button" type="button">Lưu thiết lập &amp; kết nối</button>
          </div>
        </div>

        <div class="settings-overlay log-overlay" aria-label="Nhật ký Catalog">
          <div class="settings-sheet log-sheet">
            <div class="sheet-handle"></div>
            <div class="sheet-heading">
              <div><strong>Nhật ký Catalog</strong><span>Chi tiết từng bước của lần chạy gần nhất</span></div>
              <div class="log-heading-actions">
                <button class="catalog-log-copy" type="button">Sao chép log</button>
                <button class="icon-button log-close-button" type="button" aria-label="Đóng nhật ký"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
              </div>
            </div>
            <pre class="catalog-log">Chưa có log Catalog.</pre>
          </div>
        </div>
      </aside>
      <div class="toast-stack" aria-live="polite"></div>
    `;

    ui = {
      shadow,
      host,
      launcher: shadow.querySelector(".launcher"),
      panel: shadow.querySelector(".panel"),
      closeButton: shadow.querySelector(".close-button"),
      settingsButton: shadow.querySelector(".settings-button"),
      loginButton: shadow.querySelector(".login-button"),
      statusCard: shadow.querySelector(".status-card"),
      statusTitle: shadow.querySelector(".status-title"),
      statusDetail: shadow.querySelector(".status-detail"),
      accountChip: shadow.querySelector(".account-chip"),
      catalogCard: shadow.querySelector(".catalog-card"),
      catalogCategory: shadow.querySelector(".catalog-category"),
      catalogCode: shadow.querySelector(".catalog-code"),
      catalogBuyerReference: shadow.querySelector(".catalog-buyer-reference"),
      catalogProgress: shadow.querySelector(".catalog-progress"),
      logButton: shadow.querySelector(".log-button"),
      logOverlay: shadow.querySelector(".log-overlay"),
      logCloseButton: shadow.querySelector(".log-close-button"),
      catalogLog: shadow.querySelector(".catalog-log"),
      catalogLogCopyButton: shadow.querySelector(".catalog-log-copy"),
      catalogActionButtons: [...shadow.querySelectorAll("[data-catalog-action]")],
      destinationButtons: [...shadow.querySelectorAll(".destination-button")],
      searchInput: shadow.querySelector(".search-box input"),
      hotkeyLabel: shadow.querySelector(".hotkey-label"),
      moduleButtons: [...shadow.querySelectorAll(".module-button")],
      groupSections: [...shadow.querySelectorAll(".module-group")],
      emptyState: shadow.querySelector(".empty-state"),
      settingsOverlay: shadow.querySelector(".settings-overlay"),
      settingsCloseButton: shadow.querySelector(".settings-close-button"),
      userInput: shadow.querySelector(".user-input"),
      companyInput: shadow.querySelector(".company-input"),
      passwordInput: shadow.querySelector(".password-input"),
      togglePasswordButton: shadow.querySelector(".toggle-password"),
      hotkeyButton: shadow.querySelector(".hotkey-button"),
      autoLoginInput: shadow.querySelector(".auto-login-input"),
      closeAfterModuleInput: shadow.querySelector(".close-module-input"),
      appearanceButtons: [...shadow.querySelectorAll("[data-theme-choice]")],
      saveButton: shadow.querySelector(".save-button"),
      toastStack: shadow.querySelector(".toast-stack"),
    };

    ui.launcher.addEventListener("click", togglePanel);
    ui.closeButton.addEventListener("click", closePanel);
    ui.settingsButton.addEventListener("click", openSettings);
    ui.settingsCloseButton.addEventListener("click", closeSettings);
    ui.logButton.addEventListener("click", toggleLog);
    ui.logCloseButton.addEventListener("click", closeLog);
    ui.logOverlay.addEventListener("click", (event) => {
      if (event.target === ui.logOverlay) closeLog();
    });
    ui.loginButton.addEventListener("click", () => void continueLogin({ reset: true, source: "login-button" }));
    ui.catalogCategory.addEventListener("change", saveCatalogForm);
    ui.catalogCode.addEventListener("input", saveCatalogForm);
    ui.catalogBuyerReference.addEventListener("input", saveCatalogForm);
    ui.catalogLogCopyButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void copyAutomationLog();
    });
    ui.catalogCode.addEventListener("keydown", (event) => {
      if (event.key === "Enter") startCatalogAction("search", "code");
    });
    ui.catalogBuyerReference.addEventListener("keydown", (event) => {
      if (event.key === "Enter") startCatalogAction("search", "buyer_reference");
    });
    ui.catalogActionButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const actions = {
          prepare: ["prepare", null, null],
          "code-find": ["search", "code", null],
          "code-costsheet": ["search", "code", "costsheet"],
          "code-bom": ["search", "code", "bom"],
          "buyer-find": ["search", "buyer_reference", null],
          "buyer-costsheet": ["search", "buyer_reference", "costsheet"],
          "buyer-bom": ["search", "buyer_reference", "bom"],
        };
        const args = actions[button.dataset.catalogAction];
        if (args) startCatalogAction(...args);
      });
    });
    ui.searchInput.addEventListener("input", (event) => filterModules(event.target.value));
    ui.searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (ui.searchInput.value) {
          ui.searchInput.value = "";
          filterModules("");
        } else closePanel();
      }
    });
    ui.moduleButtons.forEach((button) => {
      button.addEventListener("click", () => {
        // Module "Catalog" không chỉ mở trang Catalog mà chạy luôn pipeline Catalog → Master →
        // Floating Filter (giống nút "Mở Catalog"), dùng Category đang chọn trong Catalog Control.
        if (button.dataset.moduleId === "0003_6200") {
          startCatalogAction("prepare");
          return;
        }
        const module = ALL_MODULES.find((item) => item.id === button.dataset.moduleId);
        void openModule(module);
      });
    });
    ui.appearanceButtons.forEach((button) => {
      button.addEventListener("click", () => setTheme(button.dataset.themeChoice));
    });
    ui.settingsOverlay.addEventListener("click", (event) => {
      if (event.target === ui.settingsOverlay) closeSettings();
    });
    ui.togglePasswordButton.addEventListener("click", () => {
      const show = ui.passwordInput.type === "password";
      ui.passwordInput.type = show ? "text" : "password";
      ui.togglePasswordButton.textContent = show ? "Ẩn" : "Hiện";
    });
    ui.hotkeyButton.addEventListener("click", beginHotkeyCapture);
    // Bắt tổ hợp phím mới CHỈ khi chính nút này đang có focus (xem giải thích ở
    // handleHotkeyButtonKeydown) — không còn đăng ký gì trên document nữa cho việc này.
    ui.hotkeyButton.addEventListener("keydown", handleHotkeyButtonKeydown);
    // Rời khỏi nút mà chưa bấm tổ hợp nào (không qua Esc) thì tự huỷ chế độ, chỉ để cập nhật
    // lại nhãn hiển thị — không còn ảnh hưởng gì tới việc gõ/xoá ở ô khác dù có hay không.
    ui.hotkeyButton.addEventListener("blur", () => {
      if (hotkeyCapture) {
        hotkeyCapture = false;
        updateHotkeyLabels();
      }
    });
    ui.saveButton.addEventListener("click", saveSettings);
    ui.passwordInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") saveSettings();
    });
    restoreCatalogForm();
    updateHotkeyLabels();
    applyTheme(getPreferences().theme);
    refreshStatus();
  }

  function registerMenuCommands() {
    if (typeof GM_registerMenuCommand !== "function") return;
    GM_registerMenuCommand("Mở WFX Smart Automation", () => openPanel());
    GM_registerMenuCommand("Thiết lập tài khoản & hotkey", () => {
      openPanel({ skipAutoLogin: true });
      openSettings();
    });
    GM_registerMenuCommand("Đăng nhập trên tab này", () => void continueLogin({ reset: true, source: "menu" }));
  }

  async function resumePendingWork() {
    const pending = getPending(STORAGE.pendingLogin);
    if (!pending) {
      if (getAuthState() === "authenticated") await processPendingAction();
      return;
    }
    window.setTimeout(async () => {
      if (getAuthState() === "authenticated") {
        deleteValue(STORAGE.pendingLogin);
        setBusy(false);
        refreshStatus();
        showToast("Đăng nhập WFX thành công.", "success");
        await processPendingAction();
      } else {
        await continueLogin({ reset: false, source: pending.source });
      }
    }, 350);
  }

  const STYLES = String.raw`
    :host {
      all: initial; color-scheme: light;
      --bg: #eef2f5; --panel-bg: #f7fafb; --panel-border: rgba(15,45,60,.14);
      --surface: #ffffff; --surface-2: #eef3f6; --surface-3: rgba(15,45,60,.05); --surface-hover: rgba(12,148,174,.1);
      --border: rgba(15,45,60,.12); --border-strong: rgba(15,45,60,.2);
      --text: #10242f; --text-2: #46606b; --text-3: #6b828d;
      --accent: #0a94ae; --accent-strong: #0b7c93; --accent-soft: rgba(12,148,174,.1); --accent-border: rgba(12,148,174,.32);
      --accent-ink: #032027; --accent-grad: linear-gradient(105deg,#12b4d0,#0f9fb2 56%,#16b89f);
      --good: #0f9d68; --good-soft: rgba(18,168,110,.12);
      --warn: #b9741a; --warn-soft: rgba(200,130,20,.14);
      --bad: #cf3f57; --bad-soft: rgba(208,66,90,.12);
      --shadow: 0 26px 64px rgba(20,54,70,.2), 0 2px 8px rgba(20,54,70,.08); --shadow-sm: 0 12px 30px rgba(20,54,70,.14);
      --footer-bg: rgba(15,45,60,.035); --sheet-bg: #f7fafb;
      --code-bg: #0e2531; --code-text: #b7d0d9;
      --toast-bg: #ffffff; --toast-text: #17323d; --toast-border: rgba(15,45,60,.14);
      --scrim: rgba(20,40,52,.42); --launcher-grad: linear-gradient(145deg,#12b4d0,#0f9fb2 62%,#16b89f);
      --launcher-ink: #ffffff; --glow: rgba(20,180,205,.16);
    }
    :host([data-theme="dark"]) {
      color-scheme: dark;
      --bg: rgba(8,20,29,.97); --panel-bg: rgba(8,20,29,.97); --panel-border: rgba(164,220,235,.18);
      --surface: rgba(20,44,58,.72); --surface-2: #102a37; --surface-3: rgba(255,255,255,.035); --surface-hover: rgba(62,180,199,.1);
      --border: rgba(255,255,255,.08); --border-strong: rgba(255,255,255,.14);
      --text: #e9f4f8; --text-2: #a3b8c0; --text-3: #7d949e;
      --accent: #64deef; --accent-strong: #7ee5f2; --accent-soft: rgba(58,192,211,.1); --accent-border: rgba(102,222,239,.3);
      --accent-ink: #05202a; --accent-grad: linear-gradient(105deg,#6ceafb,#4bd5e9 56%,#73edc4);
      --good: #36e6a1; --good-soft: rgba(54,208,155,.1);
      --warn: #ffc36d; --warn-soft: rgba(255,188,91,.1);
      --bad: #ff6e7d; --bad-soft: rgba(255,86,105,.1);
      --shadow: 0 32px 90px rgba(0,0,0,.56); --shadow-sm: 0 13px 34px rgba(0,0,0,.32);
      --footer-bg: rgba(3,10,15,.22); --sheet-bg: #0d202b;
      --code-bg: rgba(2,12,18,.4); --code-text: #9eb6bf;
      --toast-bg: rgba(10,26,35,.97); --toast-text: #dcebef; --toast-border: rgba(255,255,255,.1);
      --scrim: rgba(1,7,11,.7); --launcher-grad: linear-gradient(145deg,#0d2637,#091722 62%,#112a39);
      --launcher-ink: #e9fbff; --glow: rgba(40,202,225,.12);
    }
    *, *::before, *::after { box-sizing: border-box; }
    button, input { font: inherit; }
    button { -webkit-tap-highlight-color: transparent; }
    .launcher {
      position: fixed; right: 24px; bottom: 24px; z-index: 2147483645; width: 56px; height: 56px;
      display: grid; place-items: center; border: 1px solid var(--accent-border); border-radius: 18px;
      color: var(--launcher-ink); cursor: pointer; background: var(--launcher-grad);
      box-shadow: var(--shadow-sm), inset 0 1px 0 rgba(255, 255, 255, .16);
      transition: transform .24s ease, box-shadow .24s ease, border-color .24s ease;
    }
    .launcher:hover { transform: translateY(-3px) scale(1.03); box-shadow: var(--shadow), 0 0 0 5px var(--accent-soft); }
    .launcher:active { transform: translateY(0) scale(.97); }
    .launcher svg { width: 31px; height: 31px; overflow: visible; }
    .logo-frame { fill: rgba(255,255,255,.14); stroke: var(--launcher-ink); stroke-width: 1.4; }
    .logo-mark { fill: none; stroke: var(--launcher-ink); stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
    .launcher-pulse { position: absolute; top: -3px; right: -3px; width: 13px; height: 13px; border: 3px solid var(--panel-bg); border-radius: 50%; background: var(--good); box-shadow: 0 0 12px var(--good); }
    .launcher-active { transform: scale(.9); opacity: .75; }

    .panel {
      position: fixed; z-index: 2147483646; right: 22px; bottom: 94px; width: min(520px, calc(100vw - 24px)); height: min(820px, calc(100vh - 118px));
      display: flex; flex-direction: column; overflow: hidden; color: var(--text);
      font-family: "Segoe UI Variable Text", "Segoe UI", Inter, system-ui, -apple-system, sans-serif;
      font-size: 14.5px; line-height: 1.4; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
      border: 1px solid var(--panel-border); border-radius: 24px; background: var(--panel-bg);
      box-shadow: var(--shadow), inset 0 1px 0 rgba(255,255,255,.07);
      opacity: 0; visibility: hidden; pointer-events: none; transform: translateY(20px) scale(.965); transform-origin: right bottom;
      transition: opacity .22s ease, transform .3s cubic-bezier(.2,.85,.25,1), visibility .22s;
    }
    .panel-open { opacity: 1; visibility: visible; pointer-events: auto; transform: translateY(0) scale(1); }
    .panel-glow { position: absolute; inset: -180px -120px auto auto; width: 340px; height: 340px; pointer-events: none; border-radius: 50%; background: var(--glow); filter: blur(55px); }
    .panel-header { position: relative; display: flex; align-items: center; justify-content: space-between; min-height: 68px; padding: 14px 16px 12px 18px; border-bottom: 1px solid var(--border); }
    .brand { display: flex; align-items: center; gap: 11px; }
    .brand-logo { width: 40px; height: 40px; display: grid; place-items: center; border: 1px solid var(--accent-border); border-radius: 13px; background: var(--accent-soft); }
    .brand-logo svg { width: 26px; fill: none; stroke: var(--accent); stroke-width: 1.4; }
    .brand-logo .brand-mark { fill: none; stroke: var(--text); stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .brand strong, .brand span { display: block; }
    .brand strong { color: var(--text); font-size: 17px; font-weight: 700; line-height: 1.25; letter-spacing: .01em; }
    .brand span { margin-top: 2px; color: var(--text-3); font-size: 11px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; }
    .header-actions { display: flex; gap: 7px; }
    .icon-button { width: 34px; height: 34px; display: grid; place-items: center; padding: 0; color: var(--text-2); cursor: pointer; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-3); transition: .2s ease; }
    .icon-button:hover { color: var(--accent-strong); border-color: var(--accent-border); background: var(--accent-soft); }
    .icon-button svg { width: 18px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

    .panel-body { min-height: 0; flex: 1; display: flex; flex-direction: column; padding: 12px 15px 0; }
    .settings-status { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; margin-bottom: 12px; padding: 12px; overflow: hidden; border: 1px solid var(--border); border-radius: 15px; background: var(--surface); }
    .settings-status .primary-button { width: 100%; }
    .login-button[hidden] { display: none; }
    .status-card { position: relative; z-index: 1; display: flex; align-items: center; gap: 9px; min-width: 0; }
    .status-orbit { width: 25px; height: 25px; display: grid; place-items: center; flex: 0 0 auto; border: 1px solid var(--border-strong); border-radius: 50%; color: var(--text-3); }
    .status-orbit span { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 9px currentColor; }
    .status-card[data-tone="success"] .status-orbit { border-color: var(--good); color: var(--good); }
    .status-card[data-tone="warning"] .status-orbit { border-color: var(--warn); color: var(--warn); }
    .status-card strong, .status-card span { display: block; }
    .status-card strong { overflow: hidden; color: var(--text); font-size: 14.5px; font-weight: 650; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
    .status-detail { max-width: 210px; margin-top: 3px; overflow: hidden; color: var(--text-2); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
    .account-chip { position: relative; z-index: 1; align-self: start; max-width: 160px; padding: 6px 9px; overflow: hidden; color: var(--text-2); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; border: 1px solid var(--border); border-radius: 8px; background: var(--surface-3); }
    .primary-button { position: relative; z-index: 1; grid-column: 1 / -1; height: 43px; display: flex; align-items: center; justify-content: center; gap: 9px; overflow: hidden; color: var(--accent-ink); font-size: 14px; font-weight: 750; cursor: pointer; border: 0; border-radius: 12px; background: var(--accent-grad); box-shadow: var(--shadow-sm); transition: transform .18s ease, filter .18s ease; }
    .primary-button:hover { filter: brightness(1.07); transform: translateY(-1px); }
    .primary-button:active { transform: scale(.985); }
    .primary-button:disabled { cursor: wait; opacity: .78; }
    .primary-button svg { width: 17px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .primary-button i { display: none; width: 14px; height: 14px; border: 2px solid rgba(5,32,42,.25); border-top-color: var(--accent-ink); border-radius: 50%; animation: spin .7s linear infinite; }
    .primary-button.is-loading svg { display: none; }
    .primary-button.is-loading i { display: block; }
    @keyframes spin { to { transform: rotate(360deg); } }

    .catalog-card { position: relative; margin-top: 10px; padding: 11px 12px; border: 1px solid var(--border); border-radius: 15px; background: var(--surface); box-shadow: var(--shadow-sm); transition: opacity .2s, border-color .2s; }
    .catalog-card.catalog-busy { border-color: var(--accent-border); }
    .catalog-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
    .catalog-heading strong, .catalog-heading span { display: block; }
    .catalog-heading strong { margin-top: 2px; color: var(--text); font-size: 15px; font-weight: 700; }
    .catalog-kicker { color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
    .catalog-open-button { height: 33px; display: flex; align-items: center; gap: 6px; padding: 0 11px; color: var(--accent-ink); font-size: 12px; font-weight: 700; cursor: pointer; border: 0; border-radius: 9px; background: var(--accent-grad); box-shadow: var(--shadow-sm); transition: .18s; }
    .catalog-open-button:hover { filter: brightness(1.06); transform: translateY(-1px); }
    .catalog-open-button svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .catalog-category-row { display: grid; grid-template-columns: 96px minmax(0,1fr); align-items: center; gap: 9px; margin-bottom: 7px; }
    .catalog-category-row > span, .catalog-query-row label > span { color: var(--text-2); font-size: 12px; font-weight: 650; }
    .catalog-card select, .catalog-card input { width: 100%; height: 34px; padding: 0 10px; color: var(--text); font-size: 14px; outline: 0; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2); transition: border-color .2s, background .2s; }
    .catalog-card select:focus, .catalog-card input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    .catalog-card select option { color: var(--text); background: var(--surface-2); }
    .catalog-card input::placeholder { color: var(--text-3); }
    .catalog-query-row { display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: end; gap: 8px; margin-top: 7px; }
    .catalog-query-row label > span { display: block; margin: 0 0 4px 2px; }
    .catalog-query-actions { display: flex; gap: 5px; padding-bottom: 1px; }
    .catalog-query-actions button { height: 34px; padding: 0 10px; color: var(--text-2); font-size: 12px; font-weight: 700; cursor: pointer; border: 1px solid var(--border); border-radius: 8px; background: var(--surface-3); transition: .18s; }
    .catalog-query-actions button:first-child { color: var(--accent-strong); border-color: var(--accent-border); background: var(--accent-soft); }
    .catalog-query-actions button:hover:not(:disabled) { color: var(--text); border-color: var(--accent-border); transform: translateY(-1px); }
    .catalog-query-actions button:disabled, .catalog-open-button:disabled { cursor: not-allowed; opacity: .38; }
    .catalog-progress { margin-top: 9px; padding: 8px 10px; color: var(--text-2); font-size: 12.5px; line-height: 1.4; border-left: 3px solid var(--accent); border-radius: 6px; background: var(--accent-soft); }
    .catalog-progress[hidden] { display: none; }
    .catalog-progress[data-tone="success"] { color: var(--text); border-left-color: var(--good); background: var(--good-soft); }
    .catalog-progress[data-tone="warning"] { color: var(--text); border-left-color: var(--warn); background: var(--warn-soft); }
    .catalog-progress[data-tone="error"] { color: var(--text); border-left-color: var(--bad); background: var(--bad-soft); }
    .log-button { position: relative; }
    .log-alert { position: absolute; top: -3px; right: -3px; width: 9px; height: 9px; border-radius: 50%; background: var(--bad); border: 2px solid var(--panel-bg); opacity: 0; transform: scale(.4); transition: .18s ease; }
    .log-button.has-alert .log-alert { opacity: 1; transform: scale(1); }
    .log-button.has-alert { color: var(--bad); border-color: var(--bad); }
    .log-overlay.log-open { visibility: visible; opacity: 1; }
    .log-overlay.log-open .settings-sheet { transform: translateY(0); }
    .log-heading-actions { display: flex; align-items: center; gap: 8px; }
    .catalog-log-copy { height: 30px; padding: 0 10px; color: var(--accent-strong); font-size: 11.5px; font-weight: 700; cursor: pointer; border: 1px solid var(--accent-border); border-radius: 8px; background: var(--accent-soft); }
    .catalog-log { max-height: 60vh; margin: 4px 0 0; padding: 11px 12px; overflow: auto; color: var(--code-text); font: 11.5px/1.6 Consolas, "SFMono-Regular", monospace; white-space: pre-wrap; word-break: break-word; border: 1px solid var(--border); border-radius: 10px; background: var(--code-bg); scrollbar-width: thin; }

    .search-box { height: 40px; display: flex; align-items: center; gap: 9px; margin: 11px 0 6px; padding: 0 11px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-3); transition: border-color .2s, background .2s; }
    .search-box:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    .search-box svg { width: 17px; flex: 0 0 auto; fill: none; stroke: var(--text-3); stroke-width: 1.8; stroke-linecap: round; }
    .search-box input { min-width: 0; flex: 1; color: var(--text); font-size: 13.5px; outline: 0; border: 0; background: transparent; }
    .search-box input::placeholder { color: var(--text-3); }
    kbd { padding: 4px 7px; color: var(--text-2); font-family: inherit; font-size: 11px; white-space: nowrap; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-2); }
    .modules-scroll { min-height: 0; flex: 1; overflow: auto; padding: 2px 3px 14px 0; scrollbar-width: thin; scrollbar-color: var(--border-strong) transparent; }
    .modules-scroll::-webkit-scrollbar { width: 6px; }
    .modules-scroll::-webkit-scrollbar-thumb { border-radius: 9px; background: var(--border-strong); }
    .module-group { margin-top: 10px; }
    .module-group:first-child { margin-top: 2px; }
    .module-group[hidden], .module-button[hidden] { display: none !important; }
    .group-heading { display: flex; align-items: center; gap: 7px; margin: 0 3px 6px; color: var(--text-2); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    .group-accent { width: 6px; height: 6px; border-radius: 50%; }
    .group-count { margin-left: auto; color: var(--text-3); font-size: 10px; font-weight: 600; }
    .module-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
    .module-button { min-width: 0; min-height: 44px; display: grid; grid-template-columns: 28px minmax(0,1fr) 12px; align-items: center; gap: 9px; padding: 7px 9px; color: var(--text); text-align: left; cursor: pointer; border: 1px solid var(--border); border-radius: 11px; background: var(--surface); transition: transform .18s ease, color .18s, border-color .18s, background .18s; }
    .module-button:hover { border-color: var(--accent-border); background: var(--surface-hover); transform: translateY(-1px); }
    .module-button:active { transform: scale(.985); }
    .module-icon { width: 28px; height: 28px; display: grid; place-items: center; font-size: 10px; font-weight: 800; letter-spacing: .03em; border: 1px solid currentColor; border-radius: 8px; }
    .accent-cyan { color: var(--accent); background-color: var(--accent-soft); }
    .accent-violet { color: #7c5cff; background-color: rgba(124,92,255,.1); }
    .accent-amber { color: #b9741a; background-color: rgba(200,130,20,.12); }
    :host([data-theme="dark"]) .accent-violet { color: #b7a0ff; background-color: rgba(145,113,255,.09); }
    :host([data-theme="dark"]) .accent-amber { color: #ffc36d; background-color: rgba(255,177,61,.09); }
    .group-accent.accent-cyan { background: currentColor; color: var(--accent); box-shadow: 0 0 8px currentColor; }
    .group-accent.accent-violet { background: currentColor; box-shadow: 0 0 8px currentColor; }
    .group-accent.accent-amber { background: currentColor; box-shadow: 0 0 8px currentColor; }
    .module-name { overflow: hidden; font-size: 14px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
    .module-button > svg { width: 12px; fill: none; stroke: var(--text-3); stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; transition: transform .18s, stroke .18s; }
    .module-button:hover > svg { stroke: var(--accent); transform: translateX(2px); }
    .empty-state { height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-3); text-align: center; }
    .empty-state[hidden] { display: none; }
    .empty-state svg { width: 28px; margin-bottom: 9px; fill: none; stroke: var(--text-3); stroke-width: 1.5; }
    .empty-state strong { color: var(--text-2); font-size: 12.5px; }
    .empty-state span { margin-top: 4px; font-size: 11px; }
    .panel-footer { min-height: 34px; display: flex; align-items: center; justify-content: space-between; padding: 0 18px; color: var(--text-3); font-size: 10.5px; border-top: 1px solid var(--border); background: var(--footer-bg); }
    .panel-footer span:first-child { display: flex; align-items: center; gap: 6px; }
    .panel-footer i { width: 5px; height: 5px; border-radius: 50%; background: var(--good); box-shadow: 0 0 7px var(--good); }

    .settings-overlay { position: absolute; z-index: 10; inset: 0; display: flex; align-items: flex-end; padding: 10px; visibility: hidden; opacity: 0; background: var(--scrim); backdrop-filter: blur(7px); transition: .2s ease; }
    .settings-open { visibility: visible; opacity: 1; }
    .settings-sheet { width: 100%; max-height: calc(100% - 10px); overflow: auto; padding: 8px 15px 16px; border: 1px solid var(--panel-border); border-radius: 21px; background: var(--sheet-bg); box-shadow: 0 -20px 60px rgba(0,0,0,.28); transform: translateY(20px); transition: transform .27s cubic-bezier(.2,.85,.25,1); scrollbar-width: thin; }
    .settings-open .settings-sheet { transform: translateY(0); }
    .sheet-handle { width: 38px; height: 4px; margin: 0 auto 9px; border-radius: 9px; background: var(--border-strong); }
    .sheet-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; }
    .sheet-heading strong, .sheet-heading span { display: block; }
    .sheet-heading strong { color: var(--text); font-size: 15px; font-weight: 700; }
    .sheet-heading span { margin-top: 3px; color: var(--text-3); font-size: 11px; }
    .form-grid { display: grid; grid-template-columns: 1.45fr .75fr; gap: 9px; }
    .form-grid label { min-width: 0; }
    .form-grid label > span { display: block; margin: 0 0 5px 2px; color: var(--text-2); font-size: 11px; font-weight: 650; }
    .form-grid input { width: 100%; height: 38px; padding: 0 10px; color: var(--text); font-size: 13px; outline: 0; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); transition: border-color .2s; }
    .form-grid input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    .password-field { grid-column: 1 / -1; }
    .password-field > div { position: relative; }
    .password-field input { padding-right: 54px; }
    .toggle-password { position: absolute; right: 5px; top: 5px; height: 28px; padding: 0 8px; color: var(--accent-strong); font-size: 11px; font-weight: 600; cursor: pointer; border: 0; border-radius: 7px; background: var(--accent-soft); }
    .setting-row { min-height: 50px; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 9px; padding: 8px 11px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
    .setting-row strong, .setting-row span { display: block; }
    .setting-row strong { color: var(--text); font-size: 12.5px; font-weight: 650; }
    .setting-row span { margin-top: 3px; color: var(--text-3); font-size: 11px; }
    .hotkey-button { min-width: 105px; padding: 8px; color: var(--accent-strong); font-size: 11.5px; font-weight: 700; cursor: pointer; border: 1px solid var(--accent-border); border-radius: 8px; background: var(--accent-soft); }
    .hotkey-button.capturing { color: var(--warn); border-color: var(--warn); animation: capture 1s ease infinite alternate; }
    @keyframes capture { to { box-shadow: 0 0 0 3px var(--warn-soft); } }
    .segmented { display: inline-flex; padding: 3px; gap: 3px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-3); }
    .seg-button { min-width: 54px; height: 30px; display: flex; align-items: center; justify-content: center; gap: 5px; padding: 0 12px; color: var(--text-2); font-size: 12px; font-weight: 700; cursor: pointer; border: 0; border-radius: 8px; background: transparent; transition: .18s; }
    .seg-button svg { width: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .seg-button:hover { color: var(--text); }
    .seg-button[aria-pressed="true"] { color: var(--accent-ink); background: var(--accent-grad); box-shadow: var(--shadow-sm); }
    .toggle-row { position: relative; cursor: pointer; }
    .toggle-row input { position: absolute; opacity: 0; pointer-events: none; }
    .toggle-row > i { position: relative; width: 37px; height: 21px; flex: 0 0 auto; border-radius: 20px; background: var(--border-strong); transition: .2s; }
    .toggle-row > i::after { content: ""; position: absolute; left: 3px; top: 3px; width: 15px; height: 15px; border-radius: 50%; background: var(--text-3); transition: .2s; }
    .toggle-row input:checked + i { background: var(--accent-soft); }
    .toggle-row input:checked + i::after { left: 19px; background: var(--accent); box-shadow: 0 0 9px var(--accent-soft); }
    .security-note { display: flex; gap: 8px; margin: 11px 2px; color: var(--text-3); font-size: 11px; line-height: 1.45; }
    .security-note svg { width: 17px; height: 17px; flex: 0 0 auto; fill: none; stroke: var(--accent); stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
    .save-button { width: 100%; height: 40px; color: var(--accent-ink); font-size: 13px; font-weight: 800; cursor: pointer; border: 0; border-radius: 11px; background: var(--accent-grad); box-shadow: var(--shadow-sm); transition: filter .18s, transform .18s; }
    .save-button:hover { filter: brightness(1.07); transform: translateY(-1px); }

    .toast-stack { position: fixed; z-index: 2147483647; right: 28px; bottom: 102px; width: min(340px, calc(100vw - 30px)); display: flex; flex-direction: column; align-items: flex-end; gap: 7px; pointer-events: none; font-family: "Segoe UI Variable Text", Inter,"Segoe UI",system-ui,sans-serif; }
    .panel-open + .toast-stack { right: 560px; }
    .toast { max-width: 100%; display: flex; align-items: center; gap: 8px; padding: 10px 12px; color: var(--toast-text); font-size: 12px; line-height: 1.35; border: 1px solid var(--toast-border); border-radius: 11px; background: var(--toast-bg); box-shadow: var(--shadow-sm); opacity: 0; transform: translateY(7px) scale(.98); transition: .2s ease; }
    .toast-visible { opacity: 1; transform: translateY(0) scale(1); }
    .toast-dot { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px currentColor; }
    .toast-success .toast-dot { color: var(--good); background: var(--good); }
    .toast-warning .toast-dot { color: var(--warn); background: var(--warn); }
    .toast-error .toast-dot { color: var(--bad); background: var(--bad); }

    @media (max-width: 760px) {
      .launcher { right: 13px; bottom: 13px; }
      .panel { right: 12px; bottom: 82px; width: calc(100vw - 24px); height: calc(100vh - 96px); }
      .panel-open + .toast-stack { right: 18px; bottom: 92px; }
    }
    @media (max-width: 430px) {
      .module-grid { grid-template-columns: 1fr; }
      .panel-body { padding-left: 13px; padding-right: 13px; }
      .hotkey-label { display: none; }
      .form-grid { grid-template-columns: 1fr; }
      .password-field { grid-column: auto; }
      .catalog-query-row { grid-template-columns: 1fr; }
      .catalog-query-actions button { flex: 1; }
      .catalog-category-row { grid-template-columns: 82px minmax(0,1fr); }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }
    }
  `;

  installPopupTracker();
  createUI();
  registerMenuCommands();
  document.addEventListener("keydown", handleKeydown, true);
  // Chrome Extension bridge dùng chrome.commands để không bị listener bàn phím của WFX chặn.
  document.addEventListener("wfx-smart-extension-toggle-panel", togglePanel);
  // Chỉ Chrome Extension dispatch event này (khi bridge.js phát hiện "Extension context
  // invalidated" sau khi extension được reload/cập nhật trong lúc tab vẫn mở — không có cách nào
  // tự phục hồi). Chrome Extension không bao giờ dispatch nên listener này vô hại/không chạy ở đó.
  document.addEventListener("wfx-smart-extension-context-lost", () => {
    showToast("Extension WFX Smart vừa được cập nhật. Hãy tải lại (F5) trang để tiếp tục dùng.", "warning", 8000);
  });
  window.addEventListener("pageshow", () => {
    refreshStatus();
    void resumePendingWork();
  });
  void resumePendingWork();
})();

  };

  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.origin !== window.location.origin ||
      event.data?.source !== MESSAGE_SOURCE
    ) {
      return;
    }
    const message = event.data;
    if (message.type === "bridge-ready") {
      post("main-ready");
      return;
    }
    if (message.type === "bootstrap" && typeof message.token === "string") {
      start(message.token, message.values);
      return;
    }
    if (message.type === "storage-update") {
      applyStorageUpdate(message.token, message.updates);
      return;
    }
    if (message.type === "extension-command") {
      handleExtensionCommand(message.token, message.command);
      return;
    }
    if (message.type === "extension-context-lost") {
      // Bridge (ISOLATED world) mất quyền truy cập chrome.storage/chrome.runtime vì extension
      // vừa được reload/cập nhật trong khi tab này vẫn mở. Không còn cách nào tự phục hồi — báo
      // cho core script (đã chạy trong scope start() bên dưới) qua CustomEvent trên `document`,
      // giống cách handleExtensionCommand chuyển tiếp lệnh toggle-panel.
      document.dispatchEvent(new CustomEvent("wfx-smart-extension-context-lost"));
    }
  });
  post("main-ready");
})();