"use strict";
(() => {
  const $ = (selector) => document.querySelector(selector);
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const escapeHtml = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  let book = null;
  let currentId = null;

  function renderToc() {
    $(".manual-toc").innerHTML = book.chapters.map((chapter) => {
      const links = chapter.entries.map((id) => {
        const entry = book.entries[id];
        return `<button class="manual-link" data-entry="${escapeHtml(id)}">`
          + `${escapeHtml(entry.title)}</button>`;
      }).join("");
      return `<div class="manual-chapter">${escapeHtml(chapter.title)}</div>${links}`;
    }).join("");
  }

  function renderHome() {
    const news = book.whats_new[0];
    const newsHtml = news
      ? `<section class="manual-news"><strong>Có gì mới trong bản ${
          escapeHtml(news.version)}</strong>${news.highlights.map((item) =>
          `<p><b>${escapeHtml(item.title)}</b> — ${escapeHtml(item.body)}</p>`
        ).join("")}</section>`
      : "";
    const cards = book.chapters.map((chapter) =>
      `<button class="manual-card" data-entry="${escapeHtml(chapter.entries[0])}">`
      + `<strong>${escapeHtml(chapter.title)}</strong>`
      + `<span>${escapeHtml(chapter.summary)}</span></button>`
    ).join("");
    $(".manual-home").innerHTML =
      `<h1>Hướng dẫn sử dụng WFX Smart</h1>`
      + `<p class="manual-crumb">Chọn một phần bên dưới, hoặc gõ vào ô tìm kiếm.</p>`
      + newsHtml
      + `<div class="manual-cards">${cards}</div>`;
  }

  function showEntry(entryId) {
    const entry = book.entries[entryId];
    if (!entry) return;
    currentId = entryId;
    $(".manual-home").hidden = true;
    $(".manual-content").hidden = false;
    $(".manual-content").innerHTML =
      `<p class="manual-crumb">${escapeHtml(entry.chapter_title)}</p>`
      + `<h1>${escapeHtml(entry.title)}</h1>${entry.html}`;
    $(".manual-content").scrollTop = 0;
    document.querySelectorAll(".manual-link").forEach((link) => {
      link.setAttribute("aria-current", String(link.dataset.entry === entryId));
    });
    syncNav();
  }

  function showHome() {
    currentId = null;
    $(".manual-content").hidden = true;
    $(".manual-home").hidden = false;
    syncNav();
  }

  function syncNav() {
    const position = book.order.indexOf(currentId);
    $(".manual-prev").disabled = position <= 0;
    $(".manual-next").disabled = position < 0 || position >= book.order.length - 1;
  }

  function snippet(entry, needle) {
    const text = entry.text;
    const at = text.toLowerCase().indexOf(needle);
    if (at < 0) return escapeHtml(entry.summary);
    const from = Math.max(0, at - 40);
    const raw = text.slice(from, from + 120);
    return escapeHtml(raw).replace(
      new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"),
      (hit) => `<mark>${hit}</mark>`
    );
  }

  function search(query) {
    const needle = query.trim().toLowerCase();
    const results = $(".manual-results");
    if (needle.length < 2) {
      results.hidden = true;
      $(".manual-toc").hidden = false;
      return;
    }
    const hits = book.search_index
      .filter((row) => row.haystack.includes(needle))
      .slice(0, 40);
    results.innerHTML = hits.length
      ? hits.map((hit) => {
          const entry = book.entries[hit.id];
          return `<button class="manual-link manual-hit" data-entry="${
            escapeHtml(hit.id)}"><b>${escapeHtml(entry.title)}</b>`
            + `<small>${snippet(entry, needle)}</small></button>`;
        }).join("")
      : `<p class="manual-chapter">Không tìm thấy nội dung phù hợp.</p>`;
    results.hidden = false;
    $(".manual-toc").hidden = true;
  }

  window.wfxManualGoTo = (target) => {
    if (!book || !target) { if (book) showHome(); return; }
    if (book.entries[target]) { showEntry(target); return; }
    const row = book.error_table.find((item) => item.code === target);
    if (row && row.entry) { showEntry(row.entry); return; }
    showHome();
  };

  async function bootstrap() {
    const bridge = api();
    if (!bridge) { setTimeout(bootstrap, 120); return; }
    book = await bridge.get_manual_book();
    document.documentElement.dataset.theme = book.theme === "dark" ? "dark" : "light";
    $(".manual-version").textContent = `WFX Smart ${book.version}`;
    renderToc();
    renderHome();
    window.wfxManualGoTo(book.target || "");
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-entry]");
    if (link) showEntry(link.dataset.entry);
  });
  $(".manual-search input").addEventListener("input",
    (event) => search(event.target.value));
  $(".manual-prev").addEventListener("click",
    () => showEntry(book.order[book.order.indexOf(currentId) - 1]));
  $(".manual-next").addEventListener("click",
    () => showEntry(book.order[book.order.indexOf(currentId) + 1]));
  window.addEventListener("keydown", (event) => {
    const input = $(".manual-search input");
    if (event.ctrlKey && event.key.toLowerCase() === "f") {
      event.preventDefault(); input.focus(); input.select(); return;
    }
    if (event.key === "Escape") {
      if (input.value) { input.value = ""; search(""); }
      else api()?.close_manual?.();
      return;
    }
    if (document.activeElement === input) return;
    if (event.key === "ArrowLeft" && !$(".manual-prev").disabled) $(".manual-prev").click();
    if (event.key === "ArrowRight" && !$(".manual-next").disabled) $(".manual-next").click();
  });

  window.addEventListener("pywebviewready", bootstrap);
  bootstrap();
})();
