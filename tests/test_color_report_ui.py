"""Chạy JavaScript thật: giữ mode, cascade và OC lỗi khi bấm chạy lại."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from wfx_panel.automation import color_combination as color


@pytest.mark.parametrize(
    "oc_labels,select_all,checked,popup_open",
    [
        ([], False, False, False),
        (["1-L0527-PS"], False, True, False),
        (["1-L0527-PS"], False, False, False),
        (["1-L0527-PS"], False, True, True),
        (["OC001", "OC002"], False, True, False),
        (["OC001", "OC002"], True, True, False),
    ],
)
def test_oc_popup_keeps_first_real_oc_with_or_without_select_all(
    oc_labels,
    select_all,
    checked,
    popup_open,
):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            rows = "".join(
                f'<span><input id="oc{index}" type="checkbox" {"checked" if checked else ""}'
                f' onclick="window.ocClicks=(window.ocClicks||0)+1">'
                f'<label for="oc{index}">{label}</label></span>'
                for index, label in enumerate(oc_labels)
            )
            all_row = (
                """<label><input id="all" type="checkbox" checked
                onclick="document.querySelectorAll('#oc_divDropDown input[type=checkbox]').forEach(e=>e.checked=this.checked)">(Select All)</label>"""
                if select_all
                else ""
            )
            page.set_content(f"""
                <table id="ParameterTable_rptCustomReportViewer_ctl04"><tr>
                  <td>OCNum</td><td><input id="oc_txtValue" readonly>
                    <input id="oc_ddDropDownButton" type="image"
                      onclick="const p=document.getElementById('oc_divDropDown');
                        p.style.display=p.style.display==='none'?'block':'none'; return false;">
                  </td></tr></table>
                <div id="oc_divDropDown" style="display:{"block" if popup_open else "none"}">
                  {all_row}{rows}<input type="hidden" value="0">
                </div>
            """)
            parameter = color._read_oc_parameter(page)
            assert [option["label"] for option in parameter["options"]] == oc_labels
            assert not page.locator("#oc_divDropDown").is_visible()
            if not oc_labels:
                assert parameter["value"] == []
                return
            color._select_ocnums(page, [oc_labels[-1]])
            assert color._read_oc_parameter(page)["value"] == [
                f"oc{len(oc_labels) - 1}"
            ]
            color._select_ocnums(page, None)
            assert len(color._read_oc_parameter(page)["value"]) == len(oc_labels)
        finally:
            browser.close()


def test_batch_style_picker_and_no_oc_result_are_not_duplicated_or_errors():
    ui = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
    html = (ui / "index.html").read_text(encoding="utf-8")
    markup = re.search(
        r'<section class="color-report-workspace"[\s\S]*?</section>', html
    )[0]
    markup = markup.replace(
        'class="color-report-workspace" hidden', 'class="color-report-workspace"'
    )
    css = (ui / "style.css").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content(f"<style>{css}</style>{markup}")
            page.add_script_tag(
                content="""
                const $ = s => document.querySelector(s);
                const escapeHtml = s => String(s || '');
                let selectedReportId = 'color_combination_production';
                const colorReportState = {levels:{},styleRefs:[{value:'r1',label:'STYLE'}], selected:new Set(['r1'])};
            """
            )
            page.add_script_tag(path=str(ui / "panel" / "reports.js"))
            page.evaluate("renderColorReportStyles()")
            assert page.locator(".color-report-style-block").is_visible()
            assert not page.locator(".color-report-single-style").is_visible()
            page.evaluate(
                "$('.color-report-batch-toggle').checked=false; renderColorReportStyles()"
            )
            assert not page.locator(".color-report-style-block").is_visible()
            assert page.locator(".color-report-single-style").is_visible()
            page.evaluate(
                "renderColorReportResult({saved:[],failed:[],skipped:[{style_ref:'STYLE'}]})"
            )
            card = page.locator(".color-report-result-card")
            assert card.is_visible()
            assert "Không tìm thấy OC" in card.inner_text()
            assert "lỗi" not in card.inner_text()
            assert (
                card.locator('[data-color-report-result-action="retry"]').count() == 0
            )
            assert page.locator(".color-report-export-mode").count() == 0
            page.evaluate("""() => {
                selectedReportId = 'color_combination_po_wise';
                renderColorReportLevels({levels:{
                  division:{value:'d1',options:[{value:'d1',label:'Division'}]},
                  buyer:{value:'b1',options:[{value:'b1',label:'Buyer'}]},
                  season:{value:'s1',options:[{value:'s1',label:'Season'}]},
                  po_no:{options:[{value:'p1',label:'PO001'}]},
                  style_ref:{options:[{value:'wrong',label:'WRONG STYLE'}]}
                }});
            }""")
            assert page.locator(".color-report-single-select").input_value() == ""
            assert "PO001" in page.locator(".color-report-single-select").inner_text()
            assert (
                "WRONG STYLE"
                not in page.locator(".color-report-single-select").inner_text()
            )
        finally:
            browser.close()


@pytest.mark.parametrize(
    "report_id,choice_key",
    [
        ("color_combination_production", "style_ref"),
        ("color_combination_po_wise", "po_no"),
    ],
)
def test_color_parameters_and_choices_restore_only_after_user_saves(
    report_id, choice_key
):
    ui = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
    html = (ui / "index.html").read_text(encoding="utf-8")
    markup = re.search(
        r'<section class="color-report-workspace"[\s\S]*?</section>', html
    )[0]
    markup = markup.replace(
        'class="color-report-workspace" hidden', 'class="color-report-workspace"'
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content(markup)
            page.add_script_tag(
                content="""
                const $ = s => document.querySelector(s);
                const escapeHtml = s => String(s || '');
                let selectedReportId = '';
                let colorReportRunActive = false;
                const colorReportState = {levels:{},styleRefs:[],selected:new Set(),singleValue:'',outputDir:'X:/out'};
                const reportParameterCache = new Map();
                const calls = [];
                let userSaved = {};
                async function call(method, ...args) {
                  calls.push({method,args});
                  if (method === 'save_report_parameters') userSaved = structuredClone(args[1]);
                  return {ok:true,saved:[],failed:[],skipped:[]};
                }
            """
            )
            page.add_script_tag(path=str(ui / "panel" / "reports.js"))
            page.evaluate("value => selectedReportId=value", report_id)
            levels = {
                key: {
                    "value": key[0] + "1",
                    "options": [{"value": key[0] + "1", "label": key}],
                }
                for key in ("division", "buyer", "season")
            }
            levels[choice_key] = {
                "options": [
                    {"value": "r1", "label": "First"},
                    {"value": "r2", "label": "Second"},
                ]
            }
            stale = {key: dict(value) for key, value in levels.items()}
            stale["division"] = {**stale["division"], "value": ""}
            page.evaluate(
                "levels => renderColorReportLevels({levels,saved_parameters:{}})", stale
            )
            for key in ("division", "buyer", "season"):
                assert (
                    page.locator(
                        f'.color-report-level[data-level="{key}"]'
                    ).input_value()
                    == ""
                )
            assert page.locator(".color-report-style").count() == 0
            page.evaluate("levels => renderColorReportLevels({levels})", levels)
            assert page.locator(".color-report-style:checked").count() == 0
            page.locator('.color-report-style[value="r2"]').check()
            page.evaluate("saveSelectedReportParameters()")
            saved = page.evaluate("userSaved")
            assert saved["selected_values"] == ["r2"]
            assert (
                saved["division"] == "d1"
                and saved["buyer"] == "b1"
                and saved["season"] == "s1"
            )
            page.locator('.color-report-style[value="r1"]').check()
            page.evaluate("runColorReportBatch()")
            assert (
                page.evaluate(
                    "calls.filter(c=>c.method==='save_report_parameters').length"
                )
                == 1
            )
            assert page.evaluate("userSaved.selected_values") == ["r2"]
            page.evaluate(
                "levels => renderColorReportLevels({levels,saved_parameters:userSaved})",
                levels,
            )
            assert not page.locator('.color-report-style[value="r1"]').is_checked()
            assert page.locator('.color-report-style[value="r2"]').is_checked()
            page.evaluate(
                "$('.color-report-batch-toggle').checked=false; renderColorReportStyles()"
            )
            page.locator(".color-report-single-select").select_option("r1")
            page.evaluate("saveSelectedReportParameters()")
            page.evaluate(
                "levels => renderColorReportLevels({levels,saved_parameters:userSaved})",
                levels,
            )
            assert not page.locator(".color-report-batch-toggle").is_checked()
            assert page.locator(".color-report-single-select").input_value() == "r1"
        finally:
            browser.close()


def test_oc_popup_uses_click_handlers_and_restores_all_ocnums():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content("""
                <table id="ParameterTable_rptCustomReportViewer_ctl04"><tr>
                  <td>OCNum</td><td>
                    <input id="oc_txtValue" readonly>
                    <input id="oc_ddDropDownButton" type="image"
                      onclick="const p=document.getElementById('oc_divDropDown');
                        p.style.display=p.style.display==='none'?'block':'none'; return false;">
                  </td></tr></table>
                <div id="oc_divDropDown" style="display:none">
                  <label><input id="all" type="checkbox" checked
                    onclick="document.querySelectorAll('#oc_divDropDown input').forEach(e=>e.checked=this.checked)">(Select All)</label>
                  <label><input id="oc1" type="checkbox" checked
                    onclick="window.ocClicks=(window.ocClicks||0)+1">OC001</label>
                  <label><input id="oc2" type="checkbox" checked
                    onclick="window.ocClicks=(window.ocClicks||0)+1">OC002</label>
                </div>
            """)
            color._select_ocnums(page, ["OC002"])
            assert color._read_oc_parameter(page)["value"] == ["oc2"]
            assert page.evaluate("window.ocClicks") == 1
            assert not page.locator("#oc_divDropDown").is_visible()
            color._select_ocnums(page, None)
            assert color._read_oc_parameter(page)["value"] == ["oc1", "oc2"]
            assert page.evaluate("window.ocClicks") == 2
        finally:
            browser.close()


def test_po_retry_uses_the_original_report_and_only_failed_style_codes():
    ui = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
    html = re.sub(
        r"<script\b[^>]*>[\s\S]*?</script>",
        "",
        (ui / "index.html").read_text(encoding="utf-8"),
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            page.add_script_tag(
                content="""
                const $ = s => document.querySelector(s);
                const escapeHtml = s => String(s || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;');
                let colorReportRunActive = false;
                let selectedReportId = 'color_combination_po_wise';
                const colorReportState = {styleRefs: [{value:'r1',label:'STYLE'}],
                  selected: new Set(['r1']), outputDir: 'D:/original'};
                const calls = [];
                async function call(method, selection, refs, directory) {
                  calls.push({method, selection, refs, directory});
                  return {ok:true, report_id:'color_combination_po_wise', output_dir:directory,
                    saved:[{po_value:'r1',po_no:'PO',style_ref:'STYLE',style_ref_value:'s1',style_code_value:'c1',file_name:'PO - STYLE - CODE1.xlsx'}],
                    failed:[{po_value:'r1',po_no:'PO',style_ref:'STYLE',style_ref_value:'s1',style_code_value:'c2',message:'Error'}]};
                }
                async function callQuiet() {}
            """
            )
            page.add_script_tag(path=str(ui / "panel" / "reports.js"))
            page.evaluate("""async () => {
                $('.color-report-level[data-level="buyer"]').innerHTML = '<option value="b1">Buyer 1</option>';
                await runColorReportBatch();
            }""")
            assert page.evaluate("calls[0].method") == "run_color_po_report_batch"
            assert page.evaluate("calls[0].refs") == ["r1"]
            # Người dùng đổi màn hình/lựa chọn sau lượt tải: Retry vẫn thuộc lượt cũ.
            page.evaluate("""() => {
                selectedReportId = 'color_combination_production';
                $('.color-report-level[data-level="buyer"]').innerHTML = '<option value="b2">Buyer 2</option>';
                colorReportState.outputDir = 'D:/changed';
                $('[data-color-report-result-action="retry"]').click();
            }""")
            page.wait_for_function("calls.length === 2")
            retry = page.evaluate("calls[1]")
            assert retry["method"] == "run_color_po_report_batch"
            assert retry["selection"]["buyer"] == "b1"
            assert retry["selection"]["retry_items"] == [
                {"po_value": "r1", "style_ref_value": "s1", "style_code_value": "c2"}
            ]
            assert retry["refs"] == ["r1"]
            assert retry["directory"] == "D:/original"
        finally:
            browser.close()
