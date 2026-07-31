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
    const shortcuts =
      `<div class="manual-shortcuts">`
      + `<button class="manual-card" data-entry="su-co-tra-ma-loi">`
      + `<strong>Tra nhanh mã lỗi</strong>`
      + `<span>Xem ý nghĩa và cách xử lý các mã đang gặp.</span></button>`
      + `<button class="manual-card" data-entry="su-co-gioi-han">`
      + `<strong>Câu hỏi thường gặp</strong>`
      + `<span>Xem các giới hạn và tình huống dễ gặp khi sử dụng.</span></button>`
      + `</div>`;
    $(".manual-home").innerHTML =
      `<h1>Hướng dẫn sử dụng WFX Smart</h1>`
      + `<p class="manual-crumb">Chọn một phần bên dưới, hoặc gõ vào ô tìm kiếm.</p>`
      + newsHtml
      + `<div class="manual-cards">${cards}</div>`
      + shortcuts;
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
    if (entryId === "su-co-tra-ma-loi") {
      const rows = book.error_table.map((row) =>
        `<tr data-error-code="${escapeHtml(row.code)}"><td>`
        + `<b class="ui-label">${escapeHtml(row.code)}</b></td>`
        + `<td>${escapeHtml(row.title)}</td>`
        + `<td>${escapeHtml(row.suggestion)}`
        + (row.entry
            ? ` <button class="manual-link" data-entry="${escapeHtml(row.entry)}">`
              + `Xem hướng dẫn</button>`
            : "")
        + `</td></tr>`
      ).join("");
      $(".manual-content").insertAdjacentHTML("beforeend",
        `<table id="bang-ma-loi"><thead><tr><th>Mã</th><th>Nghĩa là gì</th>`
        + `<th>Cách xử lý</th></tr></thead><tbody>${rows}</tbody></table>`);
    }
    $(".manual-content").scrollTop = 0;
    document.querySelectorAll(".manual-link").forEach((link) => {
      link.setAttribute("aria-current", String(link.dataset.entry === entryId));
    });
    syncNav();
  }

  function showErrorTable(code = "") {
    showEntry("su-co-tra-ma-loi");
    if (!code) return;
    window.requestAnimationFrame(() => {
      const row = [...document.querySelectorAll("[data-error-code]")]
        .find((item) => item.dataset.errorCode === code);
      if (!row) return;
      row.classList.add("manual-error-target");
      row.scrollIntoView({ block: "center" });
    });
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
    const exactError = book.error_table.find(
      (row) => row.code.toLowerCase() === needle
    );
    if (exactError) {
      showErrorTable(exactError.code);
      results.innerHTML =
        `<button class="manual-link manual-hit" data-error-target="${
          escapeHtml(exactError.code)}"><b>${escapeHtml(exactError.code)}</b>`
        + `<small>${escapeHtml(exactError.title)} — ${
          escapeHtml(exactError.suggestion)}</small></button>`;
      results.hidden = false;
      $(".manual-toc").hidden = true;
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
    if (target === "co-gi-moi") { showHome(); return; }
    if (book.entries[target]) { showEntry(target); return; }
    const row = book.error_table.find((item) => item.code === target);
    if (row && row.entry) { showEntry(row.entry); return; }
    if (row) { showErrorTable(row.code); return; }
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
    const errorTarget = event.target.closest("[data-error-target]");
    if (errorTarget) { showErrorTable(errorTarget.dataset.errorTarget); return; }
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
    if (event.ctrlKey && event.key.toLowerCase() === "p") {
      event.preventDefault(); window.print(); return;
    }
    if (event.key === "Escape") {
      if (input.value) { input.value = ""; search(""); }
      else api()?.close_manual?.();
      return;
    }
    if (document.activeElement === input) {
      if (event.key === "Enter") $(".manual-results .manual-hit")?.click();
      return;
    }
    if (event.key === "ArrowLeft" && !$(".manual-prev").disabled) $(".manual-prev").click();
    if (event.key === "ArrowRight" && !$(".manual-next").disabled) $(".manual-next").click();
  });

  window.addEventListener("pywebviewready", bootstrap);
  bootstrap();
})();
