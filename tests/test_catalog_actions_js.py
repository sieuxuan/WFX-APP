"""Chạy thật các hàm race-prone của ``ui/panel/catalog.js`` bằng Node.

``tests/test_panel_js.py`` chỉ assert chuỗi trong source, nên các lỗi thứ tự
async của ô tìm Catalog không test nào bắt được:

* Enter/click dòng khi đang chạy gọi bridge lần hai; lượt đó nhận
  ``ACTION_IN_PROGRESS`` nhưng ``finally`` của nó nhả busy của lượt đầu.
* Gõ phím giữa lượt chạy xóa ``catalogPendingDestination``, nên dòng
  ``MULTIPLE_RESULTS`` về sau chỉ chạy Tìm thay vì Costing/BOM/File.
* Gợi ý còn chờ debounce bật lại danh sách đè lên lượt tìm vừa bắt đầu.

Test trích đúng thân hàm từ file nguồn rồi chạy trong ``vm`` với stub tối thiểu.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CATALOG_JS = ROOT / "wfx_panel" / "ui" / "panel" / "catalog.js"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="Cần Node để chạy catalog.js")


def _function_source(source: str, name: str) -> str:
    """Thân một hàm top-level, cắt theo cặp ngoặc nhọn cân bằng."""
    match = re.search(rf"^(?:async )?function {name}\(", source, re.M)
    assert match is not None, f"catalog.js không còn hàm {name}"
    depth = 0
    for index in range(source.index("{", match.end()), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise AssertionError(f"Không cân được ngoặc của {name}")


HARNESS = r"""
const vm = require("vm");
const functions = __FUNCTIONS__;

function sandbox() {
  const timers = new Map();
  let nextTimer = 1;
  const elements = {
    ".catalog-category": { value: "Apparel" },
    ".catalog-query": { value: "AB12" },
    ".catalog-article-suggestions": { hidden: true, innerHTML: "" },
  };
  const context = {
    busy: false,
    catalogKind: "code",
    catalogPendingDestination: null,
    articleSuggestionTimer: 0,
    articleSuggestionGeneration: 0,
    bridgeCalls: [],
    statuses: [],
    rendered: [],
    elements,
    $: (selector) => elements[selector] || null,
    setStatus: (kind, text) => context.statuses.push([kind, text]),
    clearCatalogResult: () => {},
    hideCatalogResults: () => {},
    renderArticleSuggestions: (result) => {
      context.rendered.push(result);
      elements[".catalog-article-suggestions"].hidden = false;
    },
    window: {
      setTimeout: (fn) => { const id = nextTimer++; timers.set(id, fn); return id; },
      clearTimeout: (id) => { timers.delete(id); },
    },
    runTimers: () => {
      const pending = [...timers.values()];
      timers.clear();
      pending.forEach((fn) => fn());
    },
  };
  vm.createContext(context);
  // `var` để harness đọc/ghi được, như `let` dùng chung global của panel.
  vm.runInContext(functions, context);
  return context;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const scenarios = {
  async busy_run_never_reaches_the_bridge() {
    const ctx = sandbox();
    ctx.busy = true;
    ctx.catalogPendingDestination = "bom";
    ctx.runSelectedModuleAction = async (...args) => { ctx.bridgeCalls.push(args); };
    const result = await ctx.runCatalogAction("code", "F0001", "costsheet");
    return {
      result,
      bridgeCalls: ctx.bridgeCalls.length,
      pending: ctx.catalogPendingDestination,
    };
  },

  async typing_mid_run_keeps_the_destination_for_multiple_results() {
    const ctx = sandbox();
    const answer = deferred();
    ctx.runSelectedModuleAction = (...args) => {
      ctx.bridgeCalls.push(args);
      return answer.promise;
    };
    const running = ctx.runCatalogAction("buyer_reference", "PO-99", "costsheet");
    // Ô input bắt `input`: catalogPendingDestination = null.
    ctx.catalogPendingDestination = null;
    answer.resolve({ code: "MULTIPLE_RESULTS" });
    await running;
    return {
      pending: ctx.catalogPendingDestination,
      sent: ctx.bridgeCalls[0],
    };
  },

  async a_single_result_leaves_no_pending_destination() {
    const ctx = sandbox();
    ctx.runSelectedModuleAction = async () => ({ code: "CATALOG_DESTINATION_OPENED" });
    await ctx.runCatalogAction("code", "F0001", "bom");
    return { pending: ctx.catalogPendingDestination };
  },

  async hiding_cancels_a_suggestion_still_in_its_debounce() {
    const ctx = sandbox();
    ctx.callQuiet = async () => ({ suggestions: [{ article_code: "AB12" }] });
    ctx.scheduleArticleSuggestions();
    ctx.hideArticleSuggestions();
    ctx.runTimers();
    await new Promise((done) => setImmediate(done));
    return {
      rendered: ctx.rendered.length,
      hidden: ctx.elements[".catalog-article-suggestions"].hidden,
    };
  },

  async hiding_drops_a_suggestion_already_waiting_on_the_bridge() {
    const ctx = sandbox();
    const answer = deferred();
    ctx.callQuiet = () => answer.promise;
    ctx.scheduleArticleSuggestions();
    ctx.runTimers();
    ctx.hideArticleSuggestions();
    answer.resolve({ suggestions: [{ article_code: "AB12" }] });
    await new Promise((done) => setImmediate(done));
    return {
      rendered: ctx.rendered.length,
      hidden: ctx.elements[".catalog-article-suggestions"].hidden,
    };
  },

  async an_untouched_suggestion_still_renders() {
    const ctx = sandbox();
    ctx.callQuiet = async () => ({ suggestions: [{ article_code: "AB12" }] });
    ctx.scheduleArticleSuggestions();
    ctx.runTimers();
    await new Promise((done) => setImmediate(done));
    return { rendered: ctx.rendered.length };
  },
};

(async () => {
  const out = {};
  for (const [name, run] of Object.entries(scenarios)) {
    try { out[name] = await run(); }
    catch (error) { out[name] = { error: String(error && error.stack || error) }; }
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory) -> dict:
    source = CATALOG_JS.read_text(encoding="utf-8")
    functions = "\n\n".join(
        _function_source(source, name)
        for name in (
            "runCatalogAction",
            "hideArticleSuggestions",
            "scheduleArticleSuggestions",
        )
    )
    script = tmp_path_factory.mktemp("catalog_js") / "harness.js"
    script.write_text(
        HARNESS.replace("__FUNCTIONS__", json.dumps(functions)),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [node, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    results = json.loads(completed.stdout)
    for name, value in results.items():
        assert "error" not in value, f"{name}: {value['error']}"
    return results


def test_a_run_started_while_busy_never_reaches_the_bridge(outcomes):
    outcome = outcomes["busy_run_never_reaches_the_bridge"]
    assert outcome["result"] is None
    assert outcome["bridgeCalls"] == 0
    assert outcome["pending"] == "bom", "lượt bị chặn không được đụng state"


def test_typing_mid_run_keeps_the_destination_of_that_run(outcomes):
    outcome = outcomes["typing_mid_run_keeps_the_destination_for_multiple_results"]
    assert outcome["pending"] == "costsheet"
    assert outcome["sent"] == [
        "catalog_action", "Apparel", "buyer_reference", "PO-99", "costsheet",
    ]


def test_a_single_result_leaves_no_pending_destination(outcomes):
    assert outcomes["a_single_result_leaves_no_pending_destination"]["pending"] is None


@pytest.mark.parametrize(
    "scenario",
    [
        "hiding_cancels_a_suggestion_still_in_its_debounce",
        "hiding_drops_a_suggestion_already_waiting_on_the_bridge",
    ],
)
def test_hidden_suggestions_never_come_back_on_their_own(outcomes, scenario):
    assert outcomes[scenario] == {"rendered": 0, "hidden": True}


def test_suggestions_still_render_when_nothing_hid_them(outcomes):
    assert outcomes["an_untouched_suggestion_still_renders"]["rendered"] == 1
