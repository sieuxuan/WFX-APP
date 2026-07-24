# Catalog State Machine Fix Implementation Plan

> **For agentic workers:** This plan is executed **inline in the authoring session**, not
> dispatched to fresh subagents. Rationale: the fix is one cohesive rewrite of ~700 tightly
> interdependent lines in a single IIFE (`wfx-tampermonkey.user.js`), the spec (`claude.md` +
> `agent.md`) requires cross-referencing while editing every helper, and no live WFX session is
> reachable from this environment for automated integration testing — verification is a syntax
> check plus logic review, with real acceptance left to the user's manual checklist (`agent.md`).
> If resumed in a fresh session, read `agent.md` and `claude.md` first, then this file.

**Goal:** Fix the Catalog automation state machine in `wfx-tampermonkey.user.js` so it matches
the mandatory state machine in `claude.md` exactly, then rebuild the Chrome extension from `src`.

**Architecture:** Replace the ranked/fallback Master-click logic and the global-score grid/filter
resolution with the document-generation-tracked, strictly-scoped pipeline described in
`claude.md`'s Python reference (`mark_document` → `resolve-left` → `exact-master` →
`resolve-new-grid` → `grid-settled` → `ensure-floating-filter` → `fill-and-confirm-filter` →
`read-rendered-unique-results`). Each step only trusts a document it can prove is new (via direct
JS object identity, which is more reliable here than Playwright's synthetic markers since the
script runs in-page with live DOM references) or explicitly re-derives state after a click that
may have replaced the document.

**Tech Stack:** Vanilla JS (Tampermonkey IIFE), PowerShell build script, Chrome MV3 (unpacked
extension generated from the userscript — no bundler).

## Global Constraints

- Source of truth for behavior: `claude.md`'s state machine + Python reference; `agent.md` is the
  task brief; `login.py` is corroborating evidence for real WFX selectors only (its Catalog helpers
  are a simpler, older cut and must NOT be copied verbatim where they conflict with `claude.md`).
- Never click `img` or a `li`/`div`/`td` container for "Master" — only
  `span[onclick], a, button, [role="button"], input[type="button"]` with normalized text/value
  exactly `"Master"` (case-insensitive).
- Every Catalog log line must carry `runId` and `elapsedMs` (per `agent.md`'s logging
  requirements); URLs go through the existing `sanitizeUrlForLog`.
- Do not edit `chrome-extension/dist/**` by hand — only `wfx-tampermonkey.user.js`,
  `chrome-extension/src/*`, and `chrome-extension/build-extension.ps1`, then regenerate `dist` via
  the build script.
- Do not touch login/panel/hotkey/settings code — those are already correct per the 1.7.0/1.7.1
  changelog entries and are out of scope.
- Bump `// @version` in the userscript header and `version` in `chrome-extension/src/manifest.json`
  together (the build script hard-fails on mismatch) and update the zip filename in
  `build-extension.ps1`.

---

### Task 1: Rewrite the Catalog automation core in `wfx-tampermonkey.user.js`

**Files:**
- Modify: `wfx-tampermonkey.user.js:895-1637` (from `findContextWith` through the end of
  `runCatalogRequest`) — this is the entire Catalog pipeline; `startCatalogAction` at line 1639
  keeps its current signature and is unaffected.

**What changes and why (mapped to the two independent bugs `claude.md` documents):**

1. **Master (bug: "giữ candidate/document cũ quá lâu và thử cả node không có action đúng")**
   - Delete `getCatalogMasterCandidates` / `getCatalogMasterTarget` / `logMasterCandidates` and
     their rank-2 (`clickable-ancestor`) / rank-3 (`exact-text-fallback`) branches — these are what
     let the loop click `img`/`li`/`div` after the first correct click only reloaded `left`.
   - Add `markDocumentGeneration(doc)` / `snapshotContext(context)` / `isNewDocument(context,
     snapshot)` using a `WeakMap<Document, number>` — a document is "new" iff its object identity
     differs from the snapshot, which is simpler and more reliable here than Playwright's injected
     marker trick since this script holds live same-realm DOM references.
   - Add `findExactActionableMaster(leftContext)`: query
     `'span[onclick], a, button, [role="button"], input[type="button"]'`, keep only
     `elementIsUsable` nodes whose normalized `textContent` (or `.value` for `input`) casefolds to
     `"master"`, return the first match. No fallback selector, ever.
   - Rewrite `clickCatalogMaster` into a loop that: resolves `getCatalogLeftContexts()[0]`; logs
     `MASTER_FRAME` (with a generation number) only when the left document changed since the last
     iteration; finds the exact Master via the function above (retries the same node if not found
     yet — never switches to a broader selector); clicks it; waits up to ~4.5s for a *new*
     `wfxcataloglist` + `.ag-root-wrapper` context (`waitForNewGrid`, using `isNewDocument` against
     a grid snapshot taken before the Catalog click); if found, log `MASTER_OPENED` and return it;
     if not, loop back around (the top-of-loop generation check naturally reacquires `left` and
     re-clicks the same exact Master once it reloads). Throws `CATALOG_LEFT_NOT_FOUND` /
     `MASTER_NOT_FOUND` / `MASTER_CLICK_NO_NAVIGATION` exactly as today, chosen by what was
     actually observed (no left frame seen at all / left seen but no Master text ever matched /
     Master matched and clicked but no new grid before the overall deadline).

2. **Floating Filter (bug: "chỉ kiểm tra input tồn tại/usable, không kiểm tra grid đã nạp dữ liệu")**
   - Add `getGridRootElement(gridContext)` → `gridContext.document.querySelector(".ag-root-wrapper")`
     and `readGridState(gridRoot)` (loading overlay / no-rows overlay / rendered-row count, ported
     from the existing `gridElementIsRendered` viewport-intersection logic but scoped to the one
     confirmed `gridRoot`, never the whole document).
   - Add `waitGridSettled(runCtx, gridRoot)`: poll `readGridState` until `(!loading && (rows>0 ||
     noRows))` is stable for ≥700ms (mirrors the Python `wait_grid_settled` debounce), log
     `GRID_SETTLED` or throw `CATALOG_DATA_NOT_READY`. This runs unconditionally in both `prepare`
     and `search` modes, before floating filter is even considered — closing the exact gap in the
     log excerpt (`rawRows=0` yet `prepare` reported success).
   - Add `ensureFloatingFilterVisible(runCtx, gridContext)`: scoped strictly to the current grid's
     `.ag-root-wrapper` (delete `findBestGridFilter`'s whole-page scoring — it's the
     "chọn candidate bằng global score giữa nhiều grid" anti-pattern `claude.md` explicitly bans).
     Loop: if Code Filter Input is visible+enabled AND `readGridState` at that instant shows
     `!loading && (rows>0 || noRows)`, log `FILTER_VISIBLE` and return the context; otherwise, if
     `#showfloatingfilter` is visible (throttled to one click per 2s), click it; after any click,
     re-resolve the grid context by re-scanning for `wfxcataloglist` + `.ag-root-wrapper` (Angular
     may have replaced the document) rather than reusing a stale reference. Throws
     `FLOATING_FILTER_NOT_READY` on overall timeout.

3. **Result counting / filtering (bugs: "UI có 1 nhưng script đếm 32" and "Filter không hoạt động")**
   - Add `FILTER_DEFINITIONS` (code / buyer_reference → label, input selector, `col-id`).
   - Add `readRenderedUniqueResults(gridRoot, filterKind)`: same rendered-node filtering and
     case-insensitive dedup-by-value the current `readGridResults` already does, but always scoped
     to the exact `gridRoot` element passed in (never re-resolved via scoring).
   - Add `fillAndConfirmFilter(runCtx, gridRoot, filterKind, query)`: clear both Code and Buyer
     Reference inputs via the existing `dispatchFilledValue` (native setter + real event
     sequence — already equivalent to Playwright's `fill`), fill the target one, and throw
     `FILTER_VALUE_NOT_CONFIRMED` if `input.value !== query` right after.
   - Add `waitFilterResultsSettled(runCtx, gridRoot, filterKind, query)`: after the debounce, poll
     `readRenderedUniqueResults` + `readGridState` until every rendered value contains the query
     (casefolded) or the no-rows overlay is showing; throw `FILTER_RESULTS_NOT_READY` on timeout;
     log `FILTER_RESULTS` with `unique_count`/`codes` (max 20) once settled.
   - Rewrite `filterCatalogGrid` to call the three helpers above, then branch strictly on
     `codes.length`: `0` → `{outcome: "none"}`, `>1` → `{outcome: "multiple"}` (**delete**
     `chooseCatalogTargetCode`'s "auto-pick if one code matches the query exactly even among
     several" behavior — `claude.md` requires holding the grid open on any `>=2`, no exceptions),
     `1` → re-run `readRenderedUniqueResults` immediately before clicking (rows may have been
     recycled) and click the live button, returning `{outcome: "detached"}` (not a thrown error —
     matches `login.py`'s `RESULT_DETACHED` being a normal `ok:false` result) if it vanished.

4. **Cross-cutting: `runId` / `elapsedMs` logging (agent.md logging requirements)**
   - Add `createRunContext(request)` (a `runId` via `crypto.randomUUID()` fallback to a
     timestamp+random string, plus `startedAt`) and `logRun(runCtx, stage, message, details)` which
     calls the existing `logAutomation` with `runId` and `elapsedMs` merged into `details`.
   - Thread `runCtx` through every function touched above in place of bare `logAutomation` calls
     inside the Catalog pipeline only (login/module/hotkey logging is out of scope).
   - In `runCatalogRequest`: snapshot `left` and grid documents *before* clicking the Catalog menu
     (mirrors `login.py`'s `old_left`/`old_grid` captured before `catalog.click()`), create the
     `runCtx`, and rewire the call sequence to
     `resolveNewLeftFrame → selectCatalogCategory → clickCatalogMaster → waitGridSettled →
     ensureFloatingFilterVisible → (prepare: done | search: filterCatalogGrid → maybe
     openArticleDestination)`.
   - Update the error-message map: rename `ARTICLE_RESULT_DETACHED` usage away (it's now a
     returned outcome, not a thrown code), add `FILTER_VALUE_NOT_CONFIRMED` and
     `FILTER_RESULTS_NOT_READY` messages, and make `openArticleDestination` catch its internal
     `waitFor` timeout and rethrow `ARTICLE_DESTINATION_NOT_FOUND` (currently falls through to the
     generic `TIMEOUT` message).

- [ ] **Step 1: Apply the rewrite** as one `Edit` covering `wfx-tampermonkey.user.js:895-1637`,
  per the design above.
- [ ] **Step 2: Syntax-check** — no bundler exists for this file, so validate with Node directly:

```powershell
node --check wfx-tampermonkey.user.js
```

Expected: no output, exit code 0. (This only proves the IIFE parses; it cannot exercise DOM/AG
Grid behavior without a live WFX session — see Task 4.)

- [ ] **Step 3: Manual trace-through** against `agent.md`'s checklist table (Prepare with one
  left-reload / loading grid / genuinely empty grid / closed Floating Filter / exact single-row
  Code / near-match multi-row Code / Buyer Reference / row changing mid-click / blocked popup /
  Costsheet / BOM) — re-read the new code path for each row and confirm the state machine cannot
  short-circuit past the required confirmation for that row. Note any row that cannot be verified
  without a live browser.
- [ ] **Step 4: Commit** (only if the user asks for a commit — see plan header; this repo's
  convention per `CLAUDE.md`/session rules is to commit only on explicit request).

### Task 2: Bump versions and changelog

**Files:**
- Modify: `wfx-tampermonkey.user.js` (`// @version` header line, `SCRIPT_VERSION` constant, new
  `CHANGELOG 1.8.0` comment block above the IIFE describing the root cause and fix — not "added
  retry", per `agent.md`'s definition of done).
- Modify: `chrome-extension/src/manifest.json` (`"version"`).
- Modify: `chrome-extension/build-extension.ps1` (`$zipPath` version suffix).
- Modify: `chrome-extension/README.md` (zip filename in the "Build lại" section).

- [ ] **Step 1: Update all four files to `1.8.0`.**
- [ ] **Step 2: Verify version parity** (the build script already hard-fails on mismatch, so this
  doubles as a check):

```powershell
powershell -ExecutionPolicy Bypass -File .\chrome-extension\build-extension.ps1
```

Expected: prints `Chrome extension built successfully:` with both output paths; fails loudly with
`Version mismatch: ...` if the userscript and manifest versions disagree.

### Task 3: Rebuild the Chrome extension package

**Files:**
- Generated: `chrome-extension/dist/WFX-Smart-Chrome-Extension/main.js` (from the userscript core),
  plus copied `manifest.json`/`background.js`/`bridge.js`/`popup.*`/`README.md`.
- Generated: `chrome-extension/dist/WFX-Smart-Chrome-Extension-v1.8.0.zip`.

- [ ] **Step 1: Run the build** (same command as Task 2 Step 2 — already produces this output).
- [ ] **Step 2: Diff-check the generated adapter** — confirm `main.js` still opens with the
  `Generated Chrome MV3 main-world adapter` prefix and that the core body between prefix/suffix
  matches the userscript's IIFE body (spot check: `grep -c "MASTER_OPENED"` should return the same
  count in both files):

```powershell
Select-String -Path .\wfx-tampermonkey.user.js -Pattern "MASTER_OPENED" | Measure-Object | Select-Object -ExpandProperty Count
Select-String -Path ".\chrome-extension\dist\WFX-Smart-Chrome-Extension\main.js" -Pattern "MASTER_OPENED" | Measure-Object | Select-Object -ExpandProperty Count
```

Expected: identical non-zero counts.
- [ ] **Step 3: Load-unpacked sanity check** — confirm `manifest.json` in the built folder is valid
  JSON and `commands.toggle-panel` has no `suggested_key` (Chrome rejects `Ctrl+Alt+X` there per
  `agent.md` point 5):

```powershell
Get-Content .\chrome-extension\dist\WFX-Smart-Chrome-Extension\manifest.json | ConvertFrom-Json | Select-Object -ExpandProperty commands
```

Expected: `toggle-panel` present, no `suggested_key` property.

### Task 4: Verification summary and manual test handoff

**Files:** none (documentation of what was and wasn't verified goes in the final chat response,
not a new file — `claude.md`/`agent.md` already contain the authoritative checklist, no need to
duplicate it into a tracked doc).

- [ ] **Step 1: Re-read the full acceptance checklist** in `agent.md` ("Checklist test" table and
  "Tiêu chí nghiệm thu") against the Task 1 rewrite; list which rows are structurally satisfied by
  code inspection vs. which can only be confirmed by the user against live WFX (this environment
  has no WFX/Chrome session).
- [ ] **Step 2: Report to the user**: what changed, why (root cause per bug, not "added retry"),
  which checklist rows still need their own manual pass on live WFX + Chrome with the rebuilt
  unpacked extension, and how to load it (`chrome://extensions` → Developer mode → Load unpacked →
  `chrome-extension/dist/WFX-Smart-Chrome-Extension`).
