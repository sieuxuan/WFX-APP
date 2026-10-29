"""Hàng `Gần đây` của các form Tìm module: store, controller, bridge và UI.

Giống Catalog: danh sách theo đúng tài khoản + nhóm form, mới nhất trước,
không trùng, có trần, chịu được JSON hỏng, và chỉ nhớ lượt tìm thành công.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_catalog_controller import _api
from wfx_panel.controllers.search_recent import SEARCH_RECENT_GROUPS
from wfx_panel.stores.search_recent import FILE_NAME, PER_SCOPE, SearchRecentStore

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "wfx_panel" / "ui"


@pytest.fixture
def store(tmp_path):
    return SearchRecentStore(tmp_path)


@pytest.fixture
def api(tmp_path):
    api = _api(tmp_path)
    api._account = lambda: {"user_id": "xuan"}
    return api


def test_the_latest_search_comes_first_without_duplicates(store):
    store.remember("u1", "oc", ["PSG-1"], "oc_no")
    store.remember("u1", "oc", ["JACKET"], "style")
    recent = store.remember("U1", "oc", ["psg-1"], "OC_NO")

    assert recent == [
        {"kind": "OC_NO", "values": ["psg-1"]},
        {"kind": "style", "values": ["JACKET"]},
    ]


def test_the_same_value_under_another_kind_is_a_separate_entry(store):
    store.remember("u1", "sample", ["S-1", "", "", ""])
    recent = store.remember("u1", "sample", ["S-1", "", "", ""], "files")

    assert [item["kind"] for item in recent] == ["files", ""]


def test_each_account_and_group_keeps_its_own_short_list(store):
    for index in range(PER_SCOPE + 3):
        store.remember("u1", "rmpo", ["", f"R-{index}"])
    store.remember("u2", "rmpo", ["SUP", ""])
    store.remember("u1", "buyer", ["NIKE"])

    mine = store.load("u1", "rmpo")
    assert len(mine) == PER_SCOPE
    assert mine[0]["values"] == ["", f"R-{PER_SCOPE + 2}"]
    assert store.load("u2", "rmpo") == [{"kind": "", "values": ["SUP", ""]}]
    assert store.load("u1", "buyer") == [{"kind": "", "values": ["NIKE"]}]
    assert store.load("", "rmpo") == []


def test_empty_searches_and_missing_owner_are_not_written(store):
    assert store.remember("u1", "oc", ["   "]) == []
    assert store.remember("", "oc", ["PSG-1"]) == []
    assert not store.path.exists()


def test_a_broken_file_reads_as_empty(store):
    store.path.write_text("{không phải json", encoding="utf-8")
    assert store.load("u1", "oc") == []
    assert store.remember("u1", "oc", ["PSG-1"]) == [
        {"kind": "", "values": ["PSG-1"]}
    ]


def test_only_successful_searches_are_remembered(api):
    api._modules.search_oc = lambda kind, query: {
        "ok": False,
        "code": "MODULE_SEARCH_NO_RESULTS",
    }
    failed = api.search_oc("oc_no", "PSG-404")
    assert "recent_searches" not in failed

    api._modules.search_oc = lambda kind, query: {
        "ok": True,
        "code": "MODULE_SEARCH_APPLIED",
    }
    found = api.search_oc("style", " JACKET ")
    assert found["recent_searches"] == {
        "group": "oc",
        "items": [{"kind": "style", "values": ["JACKET"]}],
    }
    assert api.recent_searches("oc")["recent_searches"]["items"] == [
        {"kind": "style", "values": ["JACKET"]}
    ]


def test_delegators_store_values_in_form_order(api):
    api._inventory.search_rmpo = lambda supplier, order_no: {"ok": True}
    api._modules.search_indent = lambda *args: {"ok": True}
    api._directory.find_supplier_in_category = lambda category, query: {"ok": True}

    api.search_rmpo("ACME", "PSG-9")
    api.search_indent("user_indent_list", "S", "A", "I-1", "ST")
    api.find_supplier_in_category("Trims", "YKK")

    assert api.recent_searches("rmpo")["recent_searches"]["items"] == [
        {"kind": "", "values": ["ACME", "PSG-9"]}
    ]
    assert api.recent_searches("indent")["recent_searches"]["items"] == [
        {"kind": "user_indent_list", "values": ["S", "A", "I-1", "ST"]}
    ]
    assert api.recent_searches("supplier")["recent_searches"]["items"] == [
        {"kind": "Trims", "values": ["YKK"]}
    ]


def test_an_unknown_group_is_never_written(api, tmp_path):
    answer = api._search_recent.remember("lạ", ["x"], {"ok": True})
    assert "recent_searches" not in answer
    assert api.recent_searches("lạ")["recent_searches"]["items"] == []
    assert not (tmp_path / FILE_NAME).exists()


def test_the_recent_file_never_holds_secrets(api, tmp_path):
    api._modules.search_oc = lambda kind, query: {"ok": True}
    api.search_oc("oc_no", "PSG-1")

    stored = json.loads((tmp_path / FILE_NAME).read_text(encoding="utf-8"))
    assert set(stored["searches"][0]) == {
        "user_id", "group", "kind", "values", "searched_at",
    }


def test_every_group_has_a_recent_row_and_matches_the_ui_groups():
    html = (UI / "index.html").read_text(encoding="utf-8")
    forms = (UI / "panel" / "forms.js").read_text(encoding="utf-8")
    rows = set(re.findall(r'class="search-recent" data-recent-group="([a-z-]+)"', html))
    assert rows == set(SEARCH_RECENT_GROUPS)
    start = forms.index("const INPUT_VALIDATION_GROUPS")
    block = forms[start:forms.index("};", start)]
    for group, size in SEARCH_RECENT_GROUPS.items():
        key = re.escape(group)
        match = re.search(rf'(?:"{key}"|\b{key}): \[([^\]]*)\]', block)
        assert match, group
        assert len(re.findall(r'"\.[a-z-]+"', match.group(1))) == size, group


# --- UI: chạy thật hàm render/chạy lại bằng Node -------------------------

node = shutil.which("node")


def _function_source(source: str, name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(", source, re.M)
    assert match is not None, name
    depth = 0
    for index in range(source.index("{", match.end()), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise AssertionError(name)


HARNESS = r"""
const vm = require("vm");
const source = __SOURCE__;
const field = (label, value) => ({
  value,
  closest: () => ({ querySelector: () => ({ textContent: ` ${label} ` }) }),
  getAttribute: () => "",
});
const inputs = {
  ".sample-no-query": field("Sample Order No.", ""),
  ".sample-style-query": field("Style", "old"),
  ".sample-created-by-query": field("Created By", ""),
  ".sample-buyer-query": field("Buyer", ""),
};
const host = { hidden: true, dataset: { recentGroup: "sample" } };
const list = { innerHTML: "" };
host.querySelector = () => list;
const ran = [];
const ctx = {
  INPUT_VALIDATION_GROUPS: { sample: Object.keys(inputs), indent: [".a"] },
  INPUT_ENTER_ACTIONS: { sample: "sample-search", indent: "indent-search" },
  RECENT_SEARCH_FILTER_GROUPS: {},
  busy: false,
  selectedModule: { id: "user_indent_list" },
  moduleActions: {
    "sample-search": () => ran.push("search"),
    "sample-check-file": () => ran.push("files"),
  },
  escapeHtml: (value) => String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;"),
  $: (selector) => selector.startsWith(".search-recent[") ? host : (inputs[selector] || null),
  $$: () => [],
  hideStaleInputGroupResults: () => {},
  syncInputValidation: () => {},
  setModuleFilterKind: () => {},
  withButtonLoading: (_button, run) => run(),
  JSON,
};
vm.createContext(ctx);
vm.runInContext(source, ctx);
(async () => {
  ctx.renderRecentSearches("sample", [
    { kind: "files", values: ["S-1", "", "", '<b>"x"'] },
    { kind: "", values: ["", "", "", ""] },
    null,
  ]);
  const html = list.innerHTML;
  const hidden = host.hidden;
  const values = /data-recent-values="([^"]*)"/.exec(html)[1]
    .replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  const chip = {
    closest: () => host,
    dataset: { recentValues: values, recentKind: "files" },
  };
  await ctx.runRecentSearch(chip);
  ctx.busy = true;
  await ctx.runRecentSearch(chip);
  ctx.busy = false;
  const indent = ctx.visibleRecentSearches("indent", [
    { kind: "0005_0080_0020", values: ["x"] },
    { kind: "user_indent_list", values: ["y"] },
  ]);
  ctx.renderRecentSearches("sample", []);
  process.stdout.write(JSON.stringify({
    html, hidden, ran,
    filled: Object.values(inputs).map((input) => input.value),
    indent: indent.map((item) => item.values[0]),
    emptyHidden: host.hidden,
  }));
})();
"""


@pytest.mark.skipif(node is None, reason="Cần Node để chạy forms.js")
def test_recent_chips_render_escaped_and_rerun_the_right_action(tmp_path):
    forms = (UI / "panel" / "forms.js").read_text(encoding="utf-8")
    source = "\n\n".join(
        _function_source(forms, name)
        for name in (
            "recentSearchKindLabel",
            "recentSearchFieldLabel",
            "visibleRecentSearches",
            "renderRecentSearches",
            "applyRecentSearchKind",
            "runRecentSearch",
        )
    )
    script = tmp_path / "harness.js"
    script.write_text(
        HARNESS.replace("__SOURCE__", json.dumps(source)), encoding="utf-8"
    )
    completed = subprocess.run(
        [node, str(script)], capture_output=True, text=True, encoding="utf-8",
        timeout=30, check=True,
    )
    out = json.loads(completed.stdout)

    assert out["hidden"] is False
    assert out["html"].count("search-recent-chip") == 1
    assert "<b>" not in out["html"]
    assert ">File · S-1 · &lt;b&gt;&quot;x&quot;</button>" in out["html"]
    # Mục `files` chạy Xem file đính kèm và điền đủ ô, xóa ô cũ không còn dùng.
    assert out["ran"] == ["files"]
    assert out["filled"] == ["S-1", "", "", '<b>"x"']
    assert out["indent"] == ["y"]
    assert out["emptyHidden"] is True
