"use strict";
// WFX Smart website: Tải về, Có gì mới, Hướng dẫn và Đề xuất tính năng.
// Nội dung Manual/Có gì mới đọc từ /content/site.json (sinh bởi
// scripts/export_site_content.py); bản phát hành và đề xuất đọc từ /api/*.

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

const PRIORITY = {
  // Khóa giữ nguyên trong D1; chỉ nhãn đổi. Đây là đề xuất tính năng nên đo
  // mức có ích, không đo độ khẩn.
  nice: { level: 1, label: "Có thì tốt", note: "Tiện hơn, thỉnh thoảng mới dùng" },
  need: { level: 2, label: "Cần", note: "Dùng thường xuyên, tiết kiệm được thời gian" },
  urgent: { level: 3, label: "Rất cần", note: "Tốn nhiều thời gian mỗi ngày hoặc dễ sai sót khi làm tay" },
};
const STATUS = {
  new: "Mới", reviewing: "Đang xem xét", planned: "Đã lên kế hoạch", done: "Đã có trong app", declined: "Chưa thực hiện",
};
const OPEN_STATUSES = new Set(["new", "reviewing", "planned"]);
const FREQ = { daily: "Hằng ngày", weekly: "Hằng tuần", monthly: "Hằng tháng", rare: "Thỉnh thoảng" };
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const MAX_IMAGES = 6;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

const store = {
  get(key, fallback) {
    try { const raw = localStorage.getItem(key); return raw == null ? fallback : JSON.parse(raw); } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
};
const session = {
  get(key) { try { return sessionStorage.getItem(key) || ""; } catch { return ""; } },
  set(key, value) { try { value ? sessionStorage.setItem(key, value) : sessionStorage.removeItem(key); } catch {} },
};

const state = {
  content: null,
  release: null,
  requests: null,
  voter: store.get("wfx-voter", null),
  voted: new Set(store.get("wfx-voted", [])),
  owner: store.get("wfx-owner", {}),
  mine: new Set(store.get("wfx-mine", [])),
  identity: store.get("wfx-identity", null),
  adminKey: session.get("wfx-admin"),
  filter: { status: "all", module: "all", sort: "votes", q: "" },
  detailId: "",
  pending: [],
};
for (const id of Object.keys(state.owner)) state.mine.add(id);
if (!state.identity) {
  // Lần đầu: lấy tên + bộ phận người dùng đã gõ ở form gửi đề xuất.
  const draft = store.get("wfx-request-draft", {});
  state.identity = draft.name ? { name: draft.name, team: draft.team || "" } : { name: "", team: "" };
}
function saveIdentity(name, team) {
  state.identity = { name: name.trim(), team: team.trim() };
  store.set("wfx-identity", state.identity);
}
if (!state.voter) {
  state.voter = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/[^a-z0-9-]/gi, "");
  store.set("wfx-voter", state.voter);
}

const embed = new URLSearchParams(location.search).has("embed");
if (embed) document.body.classList.add("embed");

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children.flat()) if (child != null && child !== false) node.append(child);
  return node;
}
// replaceChildren() in null thành chữ "null"; el() đã bỏ qua null nên mọi chỗ thay nội dung đều đi qua đây.
const fill = (node, ...children) => node.replaceChildren(...children.flat().filter((c) => c != null && c !== false));
const fmtDate = (iso, withTime = false) => {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", withTime
    ? { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "2-digit", year: "numeric" }).format(d);
};
const fmtSize = (bytes) => bytes ? `${(bytes / 1024 / 1024).toFixed(bytes > 100 * 1024 * 1024 ? 0 : 1)} MB` : "";
const normalize = (text) => String(text || "").normalize("NFD").replace(/\p{Mn}/gu, "")
  .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase().replace(/\s+/g, " ").trim();
const href = (path) => (embed ? `${path}${path.includes("?") ? "&" : "?"}embed=1` : path);

let toastTimer = 0;
function toast(text) {
  const t = $("#toast");
  t.textContent = text; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3600);
}

/* ---------------- Router ---------------- */

function parseRoute() {
  const parts = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
  const view = ["co-gi-moi", "huong-dan", "de-xuat", "tai-ve"].includes(parts[0]) ? parts[0] : "tai-ve";
  return { view, sub: parts[1] ? decodeURIComponent(parts[1]) : "" };
}

function navigate(path, replace = false) {
  const target = href(path);
  if (replace) history.replaceState(null, "", target); else history.pushState(null, "", target);
  render(true);
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href]");
  if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
  const url = new URL(link.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/") || link.target === "_blank" || link.hasAttribute("download")) return;
  event.preventDefault();
  navigate(url.pathname + url.hash);
});
window.addEventListener("popstate", () => render(true));

const TITLES = { "tai-ve": "Tải về", "co-gi-moi": "Có gì mới", "huong-dan": "Hướng dẫn", "de-xuat": "Đề xuất tính năng" };

function render(scroll = false) {
  const { view, sub } = parseRoute();
  $$(".view").forEach((v) => { v.hidden = v.dataset.view !== view; });
  $$("[data-nav]").forEach((a) => {
    a.href = href(a.getAttribute("href").split("?")[0]);
    if (a.dataset.nav === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  document.title = `${TITLES[view]} · WFX Smart`;
  if (view === "tai-ve") renderDownload();
  if (view === "co-gi-moi") renderChangelog();
  if (view === "huong-dan") renderManual(sub);
  if (view === "de-xuat") loadRequests().then(() => syncDetail(sub));
  else if (detailDialog.open) detailDialog.close();
  if (scroll && !(view === "de-xuat" && (sub || state.detailId))) window.scrollTo({ top: 0 });
}

/* ---------------- Dữ liệu ---------------- */

async function loadContent() {
  const response = await fetch("/content/site.json");
  if (!response.ok) throw new Error("content " + response.status);
  state.content = await response.json();
  fillModuleSelect();
}

async function loadRelease() {
  if (state.release) return state.release;
  try {
    const response = await fetch("/api/release");
    state.release = await response.json();
  } catch {
    state.release = { ok: false, error: "Chưa kết nối được máy chủ." };
  }
  return state.release;
}

/* ---------------- Tải về ---------------- */

async function renderDownload() {
  const content = state.content;
  const latestNotes = content.whats_new[0];
  const side = $("#dl-whatsnew");
  fill(side,
    el("h2", { text: `Có gì mới ở ${latestNotes.version}` }),
    el("ul", {}, latestNotes.highlights.slice(0, 4).map((h) => el("li", { text: h.title }))),
    el("a", { href: href("/co-gi-moi"), text: "Xem toàn bộ thay đổi" })
  );
  const install = content.entries["bat-dau-cai-dat"];
  if (install) {
    fill($("#dl-install"),
      el("h2", { text: "Cách cài đặt" }),
      el("div", { class: "prose", html: install.html }),
      el("a", { href: href("/huong-dan/bat-dau-cai-dat"), text: "Mở trong Hướng dẫn sử dụng" })
    );
    wrapTables($("#dl-install"));
  }

  const release = await loadRelease();
  const actions = $("#dl-actions");
  if (!release.ok) {
    fill(actions,
      el("a", { class: "btn btn-primary", href: "https://github.com/sieuxuan/WFX-APP/releases/latest", target: "_blank", rel: "noopener", text: "Mở trang phát hành" })
    );
    $("#dl-meta").textContent = release.error || "Chưa đọc được bản phát hành mới nhất.";
    return;
  }
  $("#dl-title").textContent = `WFX Smart ${release.version}`;
  const buttons = [];
  if (release.setup) {
    buttons.push(el("a", { class: "btn btn-primary", href: release.setup.url, target: "_blank", rel: "noopener" },
      "Tải bộ cài cho Windows", el("small", { text: `.exe · ${fmtSize(release.setup.size)}` })));
  }
  if (release.portable) {
    buttons.push(el("a", { class: "btn", href: release.portable.url, target: "_blank", rel: "noopener" },
      "Bản portable", el("small", { text: `.zip · ${fmtSize(release.portable.size)}` })));
  }
  fill(actions, ...buttons);
  fill($("#dl-meta"),
    `Phát hành ngày ${fmtDate(release.published_at)}. Windows 10/11 64-bit, cài cho riêng tài khoản của bạn, không cần quyền quản trị, tự cập nhật. Bản portable chỉ cần giải nén rồi chạy `,
    el("b", { text: "WFX-Panel.exe" }), "."
  );
}

/* ---------------- Có gì mới ---------------- */

function renderChangelog() {
  const list = $("#changelog");
  if (list.childElementCount) return;
  const versions = state.content.whats_new;
  const card = (release, index) => el("li", { class: "release" },
    el("div", { class: "release-tag" },
      el("b", { text: release.version }),
      el("span", { text: fmtDate(release.date) }),
      index === 0 ? el("span", { class: "latest", text: "Mới nhất" }) : null
    ),
    el("ul", { class: "highlights" }, release.highlights.map((h) => el("li", {},
      el("h3", { text: h.title }),
      el("p", { text: h.body }),
      h.entry && state.content.entries[h.entry]
        ? el("a", { href: href(`/huong-dan/${h.entry}`), text: `Hướng dẫn: ${state.content.entries[h.entry].title} →` })
        : null
    )))
  );
  const recent = versions.slice(0, 6).map(card);
  fill(list, ...recent);
  if (versions.length > 6) {
    list.append(el("li", {}, el("details", { class: "older" },
      el("summary", { text: `Các bản cũ hơn (${versions.length - 6})` }),
      el("ol", { class: "timeline" }, versions.slice(6).map((r, i) => card(r, i + 6)))
    )));
  }
}

/* ---------------- Hướng dẫn ---------------- */

function renderManualToc(currentId) {
  const { chapters, entries } = state.content;
  const currentChapter = entries[currentId]?.chapter;
  const toc = $("#manual-toc");
  fill(toc,
    el("a", { href: href("/huong-dan"), text: "Tổng quan", "aria-current": currentId === "" ? "page" : null }),
    ...chapters.map((chapter) => el("details", { open: chapter.id === currentChapter || !currentChapter },
      el("summary", { text: chapter.title }),
      el("ul", {}, chapter.entries.map((id) => el("li", {},
        el("a", { href: href(`/huong-dan/${id}`), text: entries[id].title, "aria-current": id === currentId ? "page" : null })
      )))
    )),
    el("a", { href: href("/huong-dan/ma-loi"), text: "Tra mã lỗi", "aria-current": currentId === "ma-loi" ? "page" : null })
  );
}

function renderManual(sub) {
  const { chapters, entries, order } = state.content;
  renderManualToc(sub);
  const body = $("#manual-body");
  if (sub === "ma-loi") return renderErrorTable(body);

  const entry = entries[sub];
  if (!entry) {
    fill(body,
      el("h1", { text: "Hướng dẫn sử dụng" }),
      el("p", { class: "lead", text: `Giống cửa sổ Hướng dẫn trong app bản ${state.content.version}. Chọn một chương, hoặc gõ vào ô tìm kiếm (có dấu hay không dấu đều được).` }),
      el("div", { class: "chapter-grid" }, chapters.map((chapter) => el("a", { class: "chapter-card", href: href(`/huong-dan/${chapter.entries[0]}`) },
        el("b", { text: chapter.title }),
        el("span", { text: chapter.summary })
      )))
    );
    return;
  }
  const chapter = chapters.find((c) => c.id === entry.chapter);
  const index = order.indexOf(entry.id);
  const prev = entries[order[index - 1]];
  const next = entries[order[index + 1]];
  fill(body,
    el("span", { class: "crumb", text: chapter ? chapter.title : "" }),
    el("h1", { text: entry.title }),
    entry.summary ? el("p", { class: "lead", text: entry.summary }) : null,
    el("div", { class: "prose", html: entry.html }),
    el("nav", { class: "pager", "aria-label": "Chuyển mục" },
      prev ? el("a", { href: href(`/huong-dan/${prev.id}`), text: `← ${prev.title}` }) : el("span"),
      next ? el("a", { href: href(`/huong-dan/${next.id}`), text: `${next.title} →` }) : el("span")
    )
  );
  wrapTables(body);
}

function renderErrorTable(body, query = "") {
  const needle = normalize(query);
  const rows = state.content.errors.filter((row) => !needle || row.haystack.includes(needle));
  const input = el("input", { type: "search", placeholder: "Gõ mã lỗi hoặc nội dung thông báo", value: query, "aria-label": "Lọc mã lỗi" });
  input.addEventListener("input", () => {
    const pos = input.selectionStart;
    renderErrorTable(body, input.value);
    const again = $("input[type=search]", body);
    again.focus(); again.setSelectionRange(pos, pos);
  });
  fill(body,
    el("span", { class: "crumb", text: "Cài đặt, cập nhật và xử lý sự cố" }),
    el("h1", { text: "Tra mã lỗi" }),
    el("p", { class: "lead", text: "Thanh trạng thái của app hiện mã lỗi khi một thao tác không thành công. Tìm mã đó ở đây để biết nguyên nhân và cách xử lý." }),
    el("label", { class: "search" }, input),
    el("div", { class: "table-wrap prose" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Mã" }), el("th", { text: "Ý nghĩa" }), el("th", { text: "Cách xử lý" }))),
      el("tbody", {}, rows.map((row) => el("tr", { class: "error-row" },
        el("td", { text: row.code }),
        el("td", {}, row.title, row.entry ? [el("br"), el("a", { href: href(`/huong-dan/${row.entry}`), text: "Xem hướng dẫn" })] : null),
        el("td", { text: row.suggestion })
      )))
    )),
    rows.length ? null : el("p", { class: "hint", text: "Không có mã lỗi nào khớp." })
  );
}

function wrapTables(root) {
  $$(".prose > table, .prose table", root).forEach((table) => {
    if (table.parentElement.classList.contains("table-wrap")) return;
    const wrap = el("div", { class: "table-wrap" });
    table.replaceWith(wrap); wrap.append(table);
  });
}

$("#manual-search").addEventListener("input", (event) => {
  const box = $("#manual-results");
  const tokens = normalize(event.target.value).split(" ").filter(Boolean);
  if (!tokens.length) { box.hidden = true; return; }
  const { entries, chapters, errors } = state.content;
  const chapterTitle = Object.fromEntries(chapters.map((c) => [c.id, c.title]));
  const hits = Object.values(entries).filter((e) => tokens.every((t) => e.search.includes(t))).slice(0, 10);
  const errorHits = errors.filter((r) => tokens.every((t) => r.haystack.includes(t))).slice(0, 4);
  fill(box,
    ...hits.map((e) => el("a", { href: href(`/huong-dan/${e.id}`) }, el("b", { text: e.title }), el("small", { text: chapterTitle[e.chapter] }))),
    ...errorHits.map((r) => el("a", { href: href("/huong-dan/ma-loi") }, el("b", { text: r.code }), el("small", { text: r.title }))),
    hits.length || errorHits.length ? null : el("span", { class: "hint", text: "Không tìm thấy mục nào." })
  );
  box.hidden = false;
});
$("#manual-results").addEventListener("click", (e) => { if (e.target.closest("a")) { $("#manual-search").value = ""; $("#manual-results").hidden = true; } });

/* ---------------- Đề xuất: danh sách ---------------- */

async function loadRequests(force = false) {
  if (state.requests && !force) { renderRequests(); return; }
  try {
    const response = await fetch("/api/requests", { cache: "no-store" });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error);
    state.requests = data.requests;
  } catch {
    fill($("#req-list"), el("div", { class: "empty" },
      el("b", { text: "Chưa tải được danh sách đề xuất." }),
      el("span", { text: "Kiểm tra kết nối mạng rồi tải lại trang." })));
    return;
  }
  renderRequests();
  if (state.detailId) renderDetail();
}

function moduleOrder() {
  return state.content.module_groups.flatMap((g) => g.modules.map((m) => m.name));
}
const lastActivity = (r) => (r.comments.length ? r.comments[r.comments.length - 1].created_at : r.created_at);
const replies = (r) => r.comments.filter((c) => c.kind === "comment" || c.body);
const statusKey = (r) => (STATUS[r.status] ? r.status : "new");

function renderRequests() {
  const all = state.requests || [];
  const { status, module, sort, q } = state.filter;

  const tabs = [
    ["all", "Tất cả", all.length],
    ["open", "Đang mở", all.filter((r) => OPEN_STATUSES.has(r.status)).length],
    ["done", "Đã xong", all.filter((r) => r.status === "done").length],
    ["mine", "Của tôi", all.filter((r) => state.mine.has(r.id)).length],
  ];
  fill($("#status-tabs"), ...tabs.map(([key, label, n]) => el("button", {
    type: "button", class: "tab", "aria-pressed": String(status === key),
    onclick: () => { state.filter.status = key; renderRequests(); },
  }, label, el("em", { text: String(n) }))));

  const byModule = new Map();
  for (const r of all) byModule.set(r.module, (byModule.get(r.module) || 0) + 1);
  const modules = moduleOrder().filter((m) => byModule.has(m));
  for (const m of byModule.keys()) if (!modules.includes(m)) modules.push(m);
  if (module !== "all" && !byModule.has(module)) state.filter.module = "all";
  fill($("#req-module"),
    el("option", { value: "all", text: "Mọi module" }),
    ...modules.map((m) => el("option", { value: m, text: `${m} (${byModule.get(m)})`, selected: m === state.filter.module }))
  );

  const needle = normalize(q);
  let items = all.filter((r) => {
    if (status === "open" && !OPEN_STATUSES.has(r.status)) return false;
    if (status === "planned" && r.status !== "planned") return false;
    if (status === "done" && r.status !== "done") return false;
    if (status === "mine" && !state.mine.has(r.id)) return false;
    if (module !== "all" && r.module !== module) return false;
    if (needle) {
      const text = `${r.id} ${r.title} ${r.wish} ${r.current_flow} ${r.name} ${r.team} ${r.comments.map((c) => c.body).join(" ")}`;
      if (!normalize(text).includes(needle)) return false;
    }
    return true;
  });
  const byNew = (a, b) => b.created_at.localeCompare(a.created_at);
  items = items.sort(
    sort === "votes" ? (a, b) => b.votes - a.votes || byNew(a, b)
      : sort === "active" ? (a, b) => lastActivity(b).localeCompare(lastActivity(a))
        : byNew
  );

  const list = $("#req-list");
  if (!all.length) {
    fill(list, el("div", { class: "empty" },
      el("b", { text: "Chưa có đề xuất nào." }),
      el("span", { text: "Đề xuất bạn gửi sẽ hiện ở đây, xếp theo module, để cả nhóm cùng theo dõi." }),
      el("button", { type: "button", class: "btn btn-primary", text: "Gửi đề xuất đầu tiên", onclick: openForm })));
    return;
  }
  if (!items.length) {
    fill(list, el("div", { class: "empty" },
      el("b", { text: "Không có đề xuất nào khớp bộ lọc." }),
      el("button", { type: "button", class: "btn btn-sm", text: "Xem tất cả", onclick: () => {
        state.filter = { ...state.filter, status: "all", module: "all", q: "" };
        $("#req-search").value = "";
        renderRequests();
      } })));
    return;
  }
  const groups = new Map();
  for (const r of items) { if (!groups.has(r.module)) groups.set(r.module, []); groups.get(r.module).push(r); }
  const order = moduleOrder();
  const orderedGroups = [...groups.keys()].sort((a, b) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999));
  fill(list, ...orderedGroups.map((name) => el("section", { class: "group" },
    el("div", { class: "group-head" }, el("h2", { text: name }), el("span", { text: String(groups.get(name).length) })),
    el("div", { class: "rows" }, groups.get(name).map(ticket))
  )));
}

const statusPill = (r) => el("span", { class: `pill status s-${statusKey(r)}`, text: STATUS[statusKey(r)] });
// Ảnh thu nhỏ ngay trên dòng đề xuất; bấm để phóng to (nằm trên lớp click của dòng).
function imageStrip(keys, max) {
  const shown = keys.slice(0, max);
  return el("div", { class: "strip" }, shown.map((key, i) => el("button", {
    type: "button", class: "strip-img", "aria-label": `Phóng to ảnh ${i + 1}`,
    onclick: (e) => { e.stopPropagation(); openLightbox(`/api/images/${key}`); },
  }, el("img", { src: `/api/images/${key}`, alt: "", loading: "lazy" }),
    i === shown.length - 1 && keys.length > max ? el("span", { class: "more", text: `+${keys.length - max}` }) : null)));
}

// Mức độ chỉ hiện trong chi tiết: thang 3 nấc + nhãn + giải thích, không đưa ra danh sách.
function priorityBlock(r) {
  const p = PRIORITY[r.priority];
  if (!p) return null;
  return el("div", { class: `priority lv-${p.level}` },
    el("span", { class: "meter", "aria-hidden": "true" }, [1, 2, 3].map((n) => el("i", { class: n <= p.level ? "on" : null }))),
    el("span", {}, el("b", { text: p.label }), el("span", { class: "hint", text: ` · ${p.note}` }))
  );
}
const who = (name, team) => [name, team].filter(Boolean).join(" · ");

function voteButton(r) {
  const voted = state.voted.has(r.id);
  return el("button", {
    type: "button", class: "vote", "aria-pressed": String(voted),
    "aria-label": `${voted ? "Bỏ" : "Đánh dấu"} tôi cũng cần, ${r.votes} người`, title: "Tôi cũng cần tính năng này",
    onclick: (e) => { e.stopPropagation(); toggleVote(r); },
  }, el("span", { html: ARROW_UP }), el("b", { text: String(r.votes) }));
}
const ARROW_UP = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 2 11 9H1z" fill="currentColor"/></svg>';

function ticket(r) {
  const thread = replies(r);
  const mine = state.mine.has(r.id);
  const meta = [mine ? `${r.name} (bạn)` : r.name, r.team, fmtDate(r.created_at),
    thread.length ? `${thread.length} trả lời` : ""].filter(Boolean);
  return el("article", { class: `ticket s-${statusKey(r)}${r.status === "done" ? " is-done" : ""}` },
    voteButton(r),
    el("div", { class: "ticket-body" },
      el("button", { type: "button", class: "ticket-title", text: r.title, onclick: () => openDetail(r.id) }),
      el("p", { class: "wish", text: r.wish }),
      r.images.length ? imageStrip(r.images, 4) : null,
      el("div", { class: "meta", text: meta.join(" · ") })
    ),
    el("div", { class: "ticket-side" }, statusPill(r))
  );
}

async function toggleVote(r) {
  const on = !state.voted.has(r.id);
  if (on) state.voted.add(r.id); else state.voted.delete(r.id);
  r.votes += on ? 1 : -1;
  store.set("wfx-voted", [...state.voted]);
  rerender();
  try {
    const response = await fetch(`/api/requests/${r.id}/vote`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ voter: state.voter, on }),
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error);
    r.votes = data.votes;
  } catch {
    if (on) state.voted.delete(r.id); else state.voted.add(r.id);
    r.votes += on ? -1 : 1;
    store.set("wfx-voted", [...state.voted]);
    toast("Chưa ghi nhận được, thử lại sau.");
  }
  rerender();
}

function rerender() {
  renderRequests();
  if (state.detailId) renderDetail();
}

$("#req-search").addEventListener("input", (e) => { state.filter.q = e.target.value; renderRequests(); });
$("#req-sort").addEventListener("change", (e) => { state.filter.sort = e.target.value; renderRequests(); });
$("#req-module").addEventListener("change", (e) => { state.filter.module = e.target.value; renderRequests(); });

/* ---------------- Đề xuất: chi tiết + trao đổi ---------------- */

const detailDialog = $("#detail-dialog");
const KIND_TEXT = { done: "đã đánh dấu xong", reopen: "đã mở lại đề xuất", status: "đã đổi trạng thái", priority: "đã đổi mức độ cần thiết" };
const kindText = (c) => (c.kind === "status" ? `${KIND_TEXT.status} sang “${STATUS[c.status] || c.status}”`
  : c.kind === "priority" ? `${KIND_TEXT.priority} sang “${PRIORITY[c.status]?.label || c.status}”`
    : KIND_TEXT[c.kind] || "");
const initials = (name) => name.split(/\s+/).map((w) => w.replace(/[^\p{L}\p{N}]/gu, "")).filter(Boolean)
  .slice(0, 3).slice(-2).map((w) => w[0]).join("").toUpperCase() || "?";

function openDetail(id) {
  navigate(`/de-xuat/${id}`);
}

function syncDetail(sub) {
  const id = /^FR-\d{6}-[A-Z0-9]{4}$/.test(sub) ? sub : "";
  state.detailId = id;
  if (!id) { if (detailDialog.open) detailDialog.close(); return; }
  if (!state.requests) return;
  if (!state.requests.some((r) => r.id === id)) {
    toast("Đề xuất này không còn tồn tại.");
    navigate("/de-xuat", true);
    return;
  }
  renderDetail();
  if (!detailDialog.open) detailDialog.showModal();
}

detailDialog.addEventListener("close", () => {
  if (state.detailId) { state.detailId = ""; navigate("/de-xuat", true); }
});
$("#close-detail").addEventListener("click", () => detailDialog.close());

function renderDetail() {
  const r = (state.requests || []).find((x) => x.id === state.detailId);
  if (!r) return;
  const canMark = Boolean(state.adminKey || state.owner[r.id]);
  const effort = [FREQ[r.frequency], r.minutes ? `khoảng ${r.minutes} phút mỗi lần` : ""].filter(Boolean).join(", ");
  const doneEvent = [...r.comments].reverse().find((c) => c.kind === "done");

  fill($("#detail-badges"), el("span", { class: "code", text: r.id }), statusPill(r), el("span", { class: "pill module", text: r.module }));

  const keepDraft = $("#reply-text")?.value || "";
  const body = $("#detail-body");
  fill(body,
    el("div", { class: "detail-grid" },
      el("div", { class: "detail-top" },
        voteButton(r),
        el("div", {},
          el("h2", { class: "detail-title", id: "detail-title", text: r.title }),
          el("div", { class: "facts" },
            el("span", {}, "Người gửi ", el("b", { text: who(r.name, r.team) })),
            el("span", {}, "Gửi lúc ", el("b", { text: fmtDate(r.created_at, true) })),
            effort ? el("span", {}, "Tần suất ", el("b", { text: effort })) : null
          )
        )
      ),
      r.status === "done" ? el("div", { class: "done-banner" },
        doneEvent ? `${who(doneEvent.name, doneEvent.team)} đã đánh dấu xong lúc ${fmtDate(doneEvent.created_at, true)}.` : "Đề xuất này đã có trong app.") : null,
      PRIORITY[r.priority] ? el("div", { class: "block" }, el("h3", { text: "Mức độ cần thiết" }), priorityBlock(r)) : null,
      el("div", { class: "block" }, el("h3", { text: "Mong muốn" }), el("p", { text: r.wish })),
      r.current_flow ? el("div", { class: "block" }, el("h3", { text: "Hiện tại đang làm" }), el("p", { text: r.current_flow })) : null,
      r.images.length ? el("div", { class: "block" }, el("h3", { text: "Ảnh minh họa" }),
        el("div", { class: "thumbs" }, r.images.map((key, i) => el("button", {
          type: "button", class: "thumb", "aria-label": `Phóng to ảnh ${i + 1}`, onclick: () => openLightbox(`/api/images/${key}`),
        }, el("img", { src: `/api/images/${key}`, alt: `Ảnh minh họa ${i + 1}`, loading: "lazy" }))))) : null
    ),
    el("div", { class: "block thread-block" },
      el("h3", { text: replies(r).length ? `Trao đổi (${replies(r).length})` : "Trao đổi" }),
      r.comments.length ? el("ol", { class: "thread" }, r.comments.map(threadItem)) : el("p", { class: "thread-empty", text: "Chưa có trả lời nào. Hãy là người đầu tiên góp ý hoặc hỏi thêm." })
    ),
    composer(r, canMark, keepDraft),
    state.adminKey ? adminRow(r) : null
  );
}

const ROLE_LABEL = { admin: "Quản trị", owner: "Người gửi" };

function threadItem(c) {
  // Quản trị chưa nhập tên thì tên gửi đi chính là "Quản trị": không lặp nhãn.
  const roleTag = ROLE_LABEL[c.role] && c.name !== ROLE_LABEL[c.role]
    ? el("span", { class: `role role-tag-${c.role}`, text: ROLE_LABEL[c.role] }) : null;
  if (c.kind !== "comment") {
    return el("li", { class: `msg event k-${c.kind}` },
      el("span", { class: "avatar", "aria-hidden": "true", text: c.kind === "done" ? "✓" : "↺" }),
      el("div", { class: "event-line" },
        el("span", {}, el("b", { text: who(c.name, c.team) }), roleTag ? [" ", roleTag] : null, " ", kindText(c), " · ", el("time", { datetime: c.created_at, text: fmtDate(c.created_at, true) })),
        c.body ? el("div", { class: "bubble" }, el("p", { text: c.body })) : null
      )
    );
  }
  return el("li", { class: `msg role-${c.role}` },
    el("span", { class: "avatar", "aria-hidden": "true", text: initials(c.name) }),
    el("div", { class: "bubble" },
      el("div", { class: "bubble-head" }, el("b", { text: c.name }), c.team ? el("span", { class: "hint", text: c.team }) : null, roleTag,
        el("time", { datetime: c.created_at, text: fmtDate(c.created_at, true) })),
      el("p", { text: c.body })
    )
  );
}

function composer(r, canMark, keepDraft) {
  const id = state.identity;
  const hasIdentity = Boolean(id.name);
  const nameInput = el("input", { id: "reply-name", type: "text", maxlength: "80", placeholder: "Tên của bạn", value: id.name, autocomplete: "name" });
  const teamInput = el("input", { id: "reply-team", type: "text", maxlength: "60", placeholder: "Bộ phận / Team", value: id.team });
  const editing = { on: !hasIdentity };
  // Lưu ngay khi gõ để lần sau (và form gửi đề xuất) tự điền lại.
  const remember = () => saveIdentity(nameInput.value, teamInput.value);
  nameInput.addEventListener("input", remember);
  teamInput.addEventListener("input", remember);
  const identityBox = el("div", { class: "identity" });
  const paintIdentity = () => {
    fill(identityBox, ...(editing.on
      ? [el("div", { class: "grid-2" }, nameInput, teamInput)]
      : [el("span", {}, "Trả lời với tên ", el("b", { text: who(state.identity.name, state.identity.team) }), state.adminKey ? " (Quản trị)" : state.owner[r.id] ? " (Người gửi)" : ""),
        el("button", { type: "button", class: "link-btn", text: "Đổi", onclick: () => { editing.on = true; paintIdentity(); nameInput.focus(); } })]));
  };
  paintIdentity();

  const text = el("textarea", { id: "reply-text", rows: "3", maxlength: "2000", placeholder: "Viết trả lời, hỏi thêm hoặc bổ sung thông tin…", "aria-label": "Nội dung trả lời" });
  text.value = keepDraft;
  const msg = el("span", { class: "form-msg", role: "status" });
  const send = async (action) => {
    const name = editing.on ? nameInput.value.trim() : state.identity.name;
    const team = editing.on ? teamInput.value.trim() : state.identity.team;
    if (!name) { msg.textContent = "Hãy nhập tên của bạn."; msg.className = "form-msg error"; nameInput.focus(); return; }
    if (action === "comment" && !text.value.trim()) { msg.textContent = "Hãy nhập nội dung trả lời."; msg.className = "form-msg error"; text.focus(); return; }
    saveIdentity(name, team);
    $$("button", box).forEach((b) => { b.disabled = true; });
    msg.textContent = "Đang gửi…"; msg.className = "form-msg";
    const ok = await postComment(r, { action, body: text.value, name, team });
    if (ok) {
      text.value = "";
      toast(action === "done" ? `Đã đánh dấu xong ${r.id}` : action === "reopen" ? `Đã mở lại ${r.id}` : "Đã gửi trả lời");
      await loadRequests(true);
    } else {
      $$("button", box).forEach((b) => { b.disabled = false; });
    }
  };
  const box = el("div", { class: "composer" },
    identityBox,
    text,
    el("div", { class: "composer-actions" },
      msg, el("span", { class: "spacer" }),
      canMark && r.status !== "done" ? el("button", { type: "button", class: "btn btn-sm btn-success", text: "✓ Đánh dấu đã xong", title: "Nội dung ô trả lời (nếu có) được gửi kèm", onclick: () => send("done") }) : null,
      canMark && r.status === "done" ? el("button", { type: "button", class: "btn btn-sm", text: "Mở lại", onclick: () => send("reopen") }) : null,
      el("button", { type: "button", class: "btn btn-sm btn-primary", text: "Gửi trả lời", onclick: () => send("comment") })
    ),
    canMark ? null : el("p", { class: "hint", text: "Người gửi (trên trình duyệt đã dùng để gửi) hoặc quản trị đánh dấu được đã xong." })
  );
  box.postError = (text) => { msg.textContent = text; msg.className = "form-msg error"; };
  return box;
}

async function postComment(r, payload) {
  const headers = { "Content-Type": "application/json" };
  if (state.adminKey) headers.Authorization = `Bearer ${state.adminKey}`;
  try {
    const response = await fetch(`/api/requests/${r.id}/comments`, {
      method: "POST", headers, body: JSON.stringify({ ...payload, owner_token: state.owner[r.id] || undefined }),
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error);
    return true;
  } catch (error) {
    const msg = $(".composer .form-msg");
    if (msg) { msg.textContent = error.message || "Chưa gửi được, thử lại."; msg.className = "form-msg error"; }
    return false;
  }
}

/* ---------------- Đề xuất: quản trị ---------------- */

function adminRow(r) {
  const select = el("select", { id: "admin-status" },
    Object.entries(STATUS).map(([k, t]) => el("option", { value: k, text: t, selected: k === r.status })));
  const prio = el("select", { id: "admin-priority" },
    Object.entries(PRIORITY).map(([k, p]) => el("option", { value: k, text: p.label, selected: k === r.priority })));
  const msg = el("span", { class: "form-msg" });
  // Một nút lưu cả hai: mỗi thay đổi là một dòng riêng trong luồng trao đổi;
  // nội dung ô trả lời đi kèm thay đổi đầu tiên.
  const apply = el("button", { type: "button", class: "btn btn-sm btn-primary", text: "Lưu thay đổi", onclick: async () => {
    const changes = [];
    if (select.value !== r.status) changes.push({ action: "status", status: select.value });
    if (prio.value !== r.priority) changes.push({ action: "priority", priority: prio.value });
    if (!changes.length) { msg.textContent = "Chưa có gì thay đổi."; msg.className = "form-msg"; return; }
    apply.disabled = true;
    const text = $("#reply-text");
    const author = { name: state.identity.name || ROLE_LABEL.admin, team: state.identity.team };
    let ok = true;
    for (const [i, change] of changes.entries()) {
      ok = await postComment(r, { ...change, ...author, body: i === 0 && text ? text.value : "" });
      if (!ok) break;
    }
    apply.disabled = false;
    if (ok) { if (text) text.value = ""; toast(`Đã lưu thay đổi ${r.id}`); loadRequests(true); }
  } });
  let armed = false;
  const del = el("button", { type: "button", class: "btn btn-sm btn-danger", text: "Xóa đề xuất", onclick: async () => {
    if (!armed) { armed = true; del.textContent = "Bấm lần nữa để xóa"; return; }
    del.disabled = true;
    const ok = await adminCall(`/api/admin/requests/${r.id}`, { method: "DELETE" }, msg);
    if (ok) { toast(`Đã xóa ${r.id}`); detailDialog.close(); loadRequests(true); }
  } });
  return el("div", { class: "admin-row" },
    el("span", { class: "hint", text: "Quản trị: nội dung ô trả lời phía trên (nếu có) được gửi kèm thay đổi." }),
    el("label", { class: "admin-field" }, el("span", { text: "Trạng thái" }), select),
    el("label", { class: "admin-field" }, el("span", { text: "Mức độ" }), prio),
    apply, el("span", { class: "spacer" }), del, msg);
}

async function adminCall(url, init, msgNode) {
  try {
    const response = await fetch(url, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${state.adminKey}` } });
    const data = await response.json();
    if (response.status === 401) { state.adminKey = ""; session.set("wfx-admin", ""); updateAdminToggle(); rerender(); toast("Mã quản trị hết hiệu lực, mở lại chế độ quản trị."); return false; }
    if (!data.ok) throw new Error(data.error);
    return true;
  } catch (error) {
    if (msgNode) msgNode.textContent = error.message || "Chưa lưu được.";
    return false;
  }
}

const adminDialog = $("#admin-dialog");
$("#admin-toggle").addEventListener("click", () => {
  if (state.adminKey) { state.adminKey = ""; session.set("wfx-admin", ""); rerender(); toast("Đã thoát chế độ quản trị."); updateAdminToggle(); return; }
  $("#admin-msg").textContent = "";
  adminDialog.showModal();
});
$("[data-close]", adminDialog).addEventListener("click", () => adminDialog.close());
$("#admin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const key = $("#admin-key").value.trim();
  const response = await fetch("/api/admin/check", { headers: { Authorization: `Bearer ${key}` } }).catch(() => null);
  if (!response || !response.ok) { $("#admin-msg").textContent = "Mã quản trị không đúng."; $("#admin-msg").className = "form-msg error"; return; }
  state.adminKey = key; session.set("wfx-admin", key);
  $("#admin-key").value = "";
  adminDialog.close();
  updateAdminToggle();
  rerender();
  toast("Đã bật chế độ quản trị.");
});
function updateAdminToggle() { $("#admin-toggle").textContent = state.adminKey ? "Thoát quản trị" : "Quản trị"; }
updateAdminToggle();

/* ---------------- Đề xuất: form gửi ---------------- */

const formDialog = $("#form-dialog");
const form = $("#req-form");
const DRAFT_KEY = "wfx-request-draft";
const draftFields = ["name", "team", "title", "module", "wish", "current_flow", "frequency", "minutes"];

function fillModuleSelect() {
  const select = $("#f-module");
  fill(select, el("option", { value: "", text: "Chọn module" }),
    ...state.content.module_groups.map((g) => el("optgroup", { label: g.name },
      g.modules.map((m) => el("option", { value: m.name, text: m.name, title: m.description })))));
  const prio = $("#f-priority");
  $$("input, label:not(legend)", prio).forEach((n) => n.remove());
  for (const [key, p] of Object.entries(PRIORITY)) {
    prio.append(
      el("input", { type: "radio", name: "priority", id: `p-${key}`, value: key, checked: key === "need" }),
      el("label", { for: `p-${key}` }, p.label, el("small", { text: p.note }))
    );
  }
  restoreDraft();
}

function restoreDraft() {
  const draft = store.get(DRAFT_KEY, {});
  for (const name of draftFields) if (typeof draft[name] === "string" && form.elements[name]) form.elements[name].value = draft[name];
  if (draft.priority && PRIORITY[draft.priority]) $(`#p-${draft.priority}`).checked = true;
  if (draft.current_flow || draft.frequency || draft.minutes) $("#more-fields").open = true;
  updateCounter();
}
function saveDraft() {
  const draft = {};
  for (const name of draftFields) draft[name] = form.elements[name].value;
  draft.priority = form.elements.priority.value;
  store.set(DRAFT_KEY, draft);
}
function updateCounter() {
  const n = $("#f-wish").value.length;
  $("#wish-count").textContent = `${n.toLocaleString("vi-VN")} / 3.000`;
}
form.addEventListener("input", (e) => {
  saveDraft(); updateCounter();
  if (e.target === form.elements.name || e.target === form.elements.team) saveIdentity(form.elements.name.value, form.elements.team.value);
});

function setFormMsg(text, kind = "") {
  const m = $("#form-msg");
  m.textContent = text; m.className = `form-msg${kind ? " " + kind : ""}`;
}

let formOpenedWith = "";
const formSnapshot = () => JSON.stringify([...draftFields.map((n) => form.elements[n].value), form.elements.priority.value, state.pending.length]);

function openForm() {
  setFormMsg("");
  // Tên + bộ phận đã nhập ở ô trả lời cũng dùng cho form gửi.
  if (!form.elements.name.value && state.identity.name) {
    form.elements.name.value = state.identity.name;
    form.elements.team.value = state.identity.team;
    saveDraft();
  }
  if (!formDialog.open) { formDialog.showModal(); formOpenedWith = formSnapshot(); }
  if (!form.elements.name.value) form.elements.name.focus();
}
$("#open-form").addEventListener("click", openForm);
$("#close-form").addEventListener("click", () => formDialog.close());

async function shrinkImage(file) {
  // Ảnh quá 8 MB (thường là ảnh chụp màn hình 4K) được thu về JPEG ≤ 2560px.
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 2560 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.86));
  return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
}

async function addFiles(files) {
  const notes = [];
  for (let file of files) {
    if (state.pending.length >= MAX_IMAGES) { notes.push(`Chỉ đính kèm tối đa ${MAX_IMAGES} ảnh.`); break; }
    if (!IMAGE_TYPES.includes(file.type)) { notes.push(`"${file.name || "Ảnh dán"}" không phải PNG, JPG, GIF hoặc WebP.`); continue; }
    if (file.size > MAX_IMAGE_BYTES) {
      try { file = await shrinkImage(file); } catch { notes.push(`"${file.name}" lớn hơn 8 MB.`); continue; }
      if (file.size > MAX_IMAGE_BYTES) { notes.push(`"${file.name}" vẫn lớn hơn 8 MB.`); continue; }
    }
    state.pending.push({ file, url: URL.createObjectURL(file) });
  }
  renderPending();
  setFormMsg(notes.join(" "), notes.length ? "error" : "");
}
function renderPending() {
  fill($("#pending"), ...state.pending.map((p, i) => el("div", { class: "thumb" },
    el("img", { src: p.url, alt: `Ảnh đính kèm ${i + 1}` }),
    el("button", { type: "button", class: "remove", "aria-label": `Bỏ ảnh ${i + 1}`, text: "×", onclick: () => {
      URL.revokeObjectURL(p.url); state.pending.splice(i, 1); renderPending();
    } })
  )));
}
const drop = $("#drop");
const fileInput = $("#f-files");
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener("change", () => { addFiles([...fileInput.files]); fileInput.value = ""; });
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles([...(e.dataTransfer?.files || [])]));
document.addEventListener("paste", (e) => {
  if (parseRoute().view !== "de-xuat") return;
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  e.preventDefault();
  openForm();
  addFiles(files.map((f, i) => (f.name && f.name !== "image.png") ? f : new File([f], `anh-chup-${Date.now()}-${i}.png`, { type: f.type })));
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const v = (name) => form.elements[name].value.trim();
  if (!v("name")) { setFormMsg("Hãy nhập tên của bạn.", "error"); form.elements.name.focus(); return; }
  if (!v("title")) { setFormMsg("Hãy đặt tên cho tính năng bạn cần.", "error"); form.elements.title.focus(); return; }
  if (!v("module")) { setFormMsg("Hãy chọn module liên quan.", "error"); form.elements.module.focus(); return; }
  if (v("wish").length < 10) { setFormMsg("Hãy mô tả mong muốn ít nhất 10 ký tự.", "error"); form.elements.wish.focus(); return; }

  const data = new FormData(form);
  data.delete("images");
  for (const p of state.pending) data.append("images", p.file, p.file.name);
  const button = $("#submit");
  button.disabled = true;
  setFormMsg(state.pending.length ? `Đang gửi kèm ${state.pending.length} ảnh…` : "Đang gửi…");
  try {
    const response = await fetch("/api/requests", { method: "POST", body: data });
    const result = await response.json().catch(() => ({ ok: false, error: "Máy chủ trả về dữ liệu lạ." }));
    if (!result.ok) { setFormMsg(result.error || "Chưa gửi được.", "error"); return; }
    if (result.id) { state.mine.add(result.id); store.set("wfx-mine", [...state.mine]); }
    if (result.id && result.owner_token) { state.owner[result.id] = result.owner_token; store.set("wfx-owner", state.owner); }
    saveIdentity(form.elements.name.value, form.elements.team.value);
    for (const name of ["title", "module", "wish", "current_flow", "frequency", "minutes"]) form.elements[name].value = "";
    $("#p-need").checked = true;
    state.pending.forEach((p) => URL.revokeObjectURL(p.url));
    state.pending = []; renderPending();
    saveDraft(); updateCounter();
    formDialog.close();
    toast(result.id ? `Đã gửi ${result.id}. Cảm ơn bạn!` : "Đã gửi. Cảm ơn bạn!");
    state.filter.status = "all";
    loadRequests(true);
  } catch {
    setFormMsg("Mất kết nối khi gửi. Nội dung vẫn còn, bấm Gửi lại.", "error");
  } finally {
    button.disabled = false;
  }
});

/* ---------------- Xem ảnh ---------------- */

const lightbox = $("#lightbox");
// <dialog> để nằm trên cả hộp chi tiết đang mở; Esc chỉ đóng ảnh, không đóng hộp bên dưới.
function openLightbox(src) { $("#lightbox-img").src = src; if (!lightbox.open) lightbox.showModal(); }
lightbox.addEventListener("click", () => lightbox.close());

/* ---------------- Bấm nền tối để đóng hộp thoại ---------------- */

// Chỉ đóng khi không làm mất gì; đang nhập dở thì giữ hộp và nhắc dùng nút ×.
function closeOnBackdrop(dialog, isDirty) {
  const outside = (e) => {
    if (e.target !== dialog) return false;
    const box = dialog.getBoundingClientRect();
    return e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom;
  };
  let pressed = false;
  dialog.addEventListener("pointerdown", (e) => { pressed = outside(e); });
  dialog.addEventListener("click", (e) => {
    if (!pressed || !outside(e)) return;
    pressed = false;
    if (isDirty()) toast("Bạn đang nhập dở. Bấm × nếu muốn đóng.");
    else dialog.close();
  });
}
closeOnBackdrop(detailDialog, () => Boolean($("#reply-text")?.value.trim()));
closeOnBackdrop(formDialog, () => formSnapshot() !== formOpenedWith);
closeOnBackdrop(adminDialog, () => Boolean($("#admin-key").value));

/* ---------------- Giao diện sáng/tối ---------------- */

// Mặc định theo màu hệ thống. Bấm nút để chọn màu ngược lại thì nhớ trong trình
// duyệt; bấm về đúng màu hệ thống thì bỏ ghi nhớ để trang lại đi theo hệ thống.
$("#theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const systemDark = matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : systemDark;
  const nextDark = !dark;
  try {
    if (nextDark === systemDark) { delete root.dataset.theme; localStorage.removeItem("wfx-theme"); }
    else { root.dataset.theme = nextDark ? "dark" : "light"; localStorage.setItem("wfx-theme", root.dataset.theme); }
  } catch {
    root.dataset.theme = nextDark ? "dark" : "light";
  }
});

/* ---------------- Khởi động ---------------- */

(async function start() {
  try {
    await loadContent();
  } catch {
    fill($("#main"), el("div", { class: "empty" }, el("b", { text: "Chưa tải được nội dung trang." }), el("span", { text: "Tải lại trang sau ít phút." })));
    return;
  }
  render();
})();
