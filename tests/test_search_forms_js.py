"""Chạy thật ``ui/panel/forms.js`` bằng Node: Enter, Esc và nút Xóa điều kiện.

``tests/test_panel_js.py`` chỉ assert chuỗi trong source. Lỗi Enter chạy Search
khi form còn trống từng lọt qua đúng vì vậy: nút đã bị disable nhưng đường bàn
phím gọi thẳng ``moduleActions`` mà không đọc trạng thái nút.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "wfx_panel" / "ui"
FORMS_JS = UI / "panel" / "forms.js"

node = shutil.which("node")


HARNESS = r"""
const vm = require("vm");
const source = __SOURCE__;

function element(extra = {}) {
  return {
    value: "", hidden: false, disabled: false, attributes: {}, events: [],
    focused: false,
    setAttribute(name, value) { this.attributes[name] = value; },
    focus() { this.focused = true; },
    dispatchEvent(event) { this.events.push(event.type); },
    addEventListener() {},
    ...extra,
  };
}

function sandbox() {
  const inputs = {
    ".sample-no-query": element(), ".sample-style-query": element(),
    ".sample-created-by-query": element(), ".sample-buyer-query": element(),
  };
  const searchButton = element({ dataset: {} });
  const clearButton = element({ dataset: { clearGroup: "sample" } });
  const hint = element();
  const byAttribute = {
    '[data-validation-group="sample"]': [searchButton],
    '[data-validation-hint="sample"]': [hint],
    '[data-clear-group="sample"]': [clearButton],
    '[data-module-action="sample-search"]': [searchButton],
  };
  const context = {
    busy: false,
    calls: [],
    hidden: [],
    inputs, searchButton, clearButton, hint,
    $: (selector) => inputs[selector] || (byAttribute[selector] || [])[0] || null,
    $$: (selector) => byAttribute[selector] || [],
    withButtonLoading: (_button, run) => run(),
    hideSampleFileResults: () => context.hidden.push("sample"),
    hideRmpoResults: () => context.hidden.push("rmpo"),
    Event: class { constructor(type) { this.type = type; } },
  };
  context.moduleActions = {
    "sample-search": () => context.calls.push("sample-search"),
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

function key(target, keyName, extra = {}) {
  const event = {
    key: keyName, target, isComposing: false, prevented: false, stopped: false,
    preventDefault() { this.prevented = true; },
    stopPropagation() { this.stopped = true; },
    ...extra,
  };
  return event;
}

const results = {};

{
  const ctx = sandbox();
  ctx.syncInputValidation("sample");
  const input = ctx.inputs[".sample-no-query"];
  ctx.handleSearchInputKeydown(key(input, "Enter"), "sample");
  results.emptyEnterCalls = ctx.calls.length;
  results.emptyHintHidden = ctx.hint.hidden;
  results.emptyClearHidden = ctx.clearButton.hidden;

  input.value = "SO-1";
  ctx.syncInputValidation("sample");
  results.filledHintHidden = ctx.hint.hidden;
  results.filledClearHidden = ctx.clearButton.hidden;
  ctx.handleSearchInputKeydown(key(input, "Enter", { isComposing: true }), "sample");
  results.composingCalls = ctx.calls.length;
  ctx.handleSearchInputKeydown(key(input, "Enter"), "sample");
  results.filledEnterCalls = ctx.calls.slice();

  ctx.busy = true;
  ctx.syncInputValidation("sample");
  ctx.handleSearchInputKeydown(key(input, "Enter"), "sample");
  results.busyEnterCalls = ctx.calls.length;
}

{
  const ctx = sandbox();
  const input = ctx.inputs[".sample-style-query"];
  input.value = "ABC";
  const filled = key(input, "Escape");
  ctx.handleSearchInputKeydown(filled, "sample");
  results.escapeValue = input.value;
  results.escapeStopped = filled.stopped;
  results.escapeEvents = input.events;
  const empty = key(input, "Escape");
  ctx.handleSearchInputKeydown(empty, "sample");
  results.emptyEscapeStopped = empty.stopped;
}

{
  const ctx = sandbox();
  ctx.inputs[".sample-style-query"].value = "ABC";
  ctx.inputs[".sample-buyer-query"].value = "JL";
  ctx.syncInputValidation("sample");
  ctx.clearInputGroup("sample");
  results.clearedValues = Object.values(ctx.inputs).map((item) => item.value);
  results.clearedHidden = ctx.hidden;
  results.clearedClearHidden = ctx.clearButton.hidden;
  results.clearedHintHidden = ctx.hint.hidden;
  results.clearedSearchDisabled = ctx.searchButton.disabled;
  results.clearedFocus = ctx.inputs[".sample-no-query"].focused;
}

console.log(JSON.stringify(results));
"""


@pytest.fixture(scope="module")
def results() -> dict:
    if node is None:
        pytest.skip("Cần Node để chạy forms.js")
    script = HARNESS.replace(
        "__SOURCE__", json.dumps(FORMS_JS.read_text(encoding="utf-8"))
    )
    output = subprocess.run(
        [node, "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    return json.loads(output.stdout)


def test_enter_khong_chay_search_khi_form_trong_hoac_dang_ban(results):
    assert results["emptyEnterCalls"] == 0
    assert results["filledEnterCalls"] == ["sample-search"]
    assert results["busyEnterCalls"] == 1


def test_enter_khi_bo_go_dang_chot_chu_khong_chay_search(results):
    assert results["composingCalls"] == 0


def test_goi_y_va_nut_xoa_dieu_kien_loai_tru_nhau(results):
    assert results["emptyHintHidden"] is False
    assert results["emptyClearHidden"] is True
    assert results["filledHintHidden"] is True
    assert results["filledClearHidden"] is False


def test_esc_xoa_rieng_o_dang_co_chu_va_khong_dong_man_module(results):
    assert results["escapeValue"] == ""
    assert results["escapeStopped"] is True
    assert results["escapeEvents"] == ["input"]
    assert results["emptyEscapeStopped"] is False


def test_xoa_dieu_kien_xoa_het_o_an_ket_qua_cu_va_dua_focus_ve_o_dau(results):
    assert results["clearedValues"] == ["", "", "", ""]
    assert results["clearedHidden"] == ["sample"]
    assert results["clearedClearHidden"] is True
    assert results["clearedHintHidden"] is False
    assert results["clearedSearchDisabled"] is True
    assert results["clearedFocus"] is True


def _object_keys(source: str, name: str) -> set[str]:
    body = re.search(rf"const {name} = \{{(.*?)\n\}};", source, re.S)
    assert body is not None, name
    return set(re.findall(r'^\s*"?([\w-]+)"?\s*:', body.group(1), re.M))


def test_bang_enter_va_xoa_dieu_kien_tro_dung_nhom_nut_va_html():
    forms = FORMS_JS.read_text(encoding="utf-8")
    actions_js = (UI / "panel" / "module_actions.js").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    groups = _object_keys(forms, "INPUT_VALIDATION_GROUPS")
    enter = dict(
        re.findall(
            r'^\s*"?([\w-]+)"?: "([\w-]+)",',
            re.search(r"const INPUT_ENTER_ACTIONS = \{(.*?)\n\};", forms, re.S).group(1),
            re.M,
        )
    )
    assert set(enter) <= groups
    for action in enter.values():
        assert f'"{action}":' in actions_js, action
        assert f'data-module-action="{action}"' in html, action
    clearable_body = re.search(
        r"const CLEARABLE_INPUT_GROUPS = new Set\(\[(.*?)\]\);", forms, re.S
    )
    assert clearable_body is not None
    clearable = set(re.findall(r'"([\w-]+)"', clearable_body.group(1)))
    assert clearable <= groups
    html_groups = set(re.findall(r'data-clear-group="([\w-]+)"', html))
    assert html_groups == clearable
    for group in clearable:
        assert html.count(f'data-clear-group="{group}"') == 1, group
