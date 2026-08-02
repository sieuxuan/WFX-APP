import json
import unicodedata

import pytest

from tests import _manual_surface as surface
from wfx_panel import manual_book, telemetry
from wfx_panel.version import APP_VERSION


def test_slugify_bo_dau_tieng_viet():
    assert manual_book.slugify("Tìm Style trên WFX") == "tim-style-tren-wfx"
    assert manual_book.slugify("Gặp lỗi thì sao?") == "gap-loi-thi-sao"


def test_chuan_hoa_tim_kiem_bo_dau_tieng_viet():
    assert manual_book.normalize_search_text("Tìm Style ĐÃ MỞ") == "tim style da mo"
    assert manual_book.normalize_search_text("  Mã   lỗi  ") == "ma loi"


def test_render_inline_escape_truoc_khi_dinh_dang():
    assert manual_book.render_inline("a < b & c") == "a &lt; b &amp; c"
    assert manual_book.render_inline("bấm `Mở Catalog`") == (
        'bấm <b class="ui-label">Mở Catalog</b>'
    )
    assert manual_book.render_inline("**quan trọng**") == (
        "<strong>quan trọng</strong>"
    )


def test_render_markdown_tieu_de_co_id():
    html = manual_book.render_markdown("## Các bước\n")
    assert html == '<h2 id="cac-buoc">Các bước</h2>'


def test_render_markdown_danh_sach_co_so_va_khong_so():
    html = manual_book.render_markdown("1. Mở panel\n2. Chọn Division\n")
    assert html == "<ol><li>Mở panel</li><li>Chọn Division</li></ol>"
    html = manual_book.render_markdown("- Một\n- Hai\n")
    assert html == "<ul><li>Một</li><li>Hai</li></ul>"


def test_render_markdown_bang_bo_dong_gach_ngang():
    source = "| Hiện tượng | Cách xử lý |\n|---|---|\n| Treo | Chờ 10 giây |\n"
    html = manual_book.render_markdown(source)
    assert "<thead><tr><th>Hiện tượng</th><th>Cách xử lý</th></tr></thead>" in html
    assert "<td>Treo</td><td>Chờ 10 giây</td>" in html
    assert "---" not in html


def test_render_markdown_ba_loai_khoi_nhan_manh():
    html = manual_book.render_markdown("> [!meo]\n> Gõ 2 ký tự là có gợi ý.\n")
    assert '<div class="callout callout-meo"><b>Mẹo</b>' in html
    assert "Gõ 2 ký tự là có gợi ý." in html
    assert manual_book.CALLOUT_LABELS["luuy"] == "Lưu ý"
    assert manual_book.CALLOUT_LABELS["loi"] == "Gặp lỗi thì sao"


def test_render_markdown_khong_cho_html_tho():
    html = manual_book.render_markdown("<script>alert(1)</script>\n")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_strip_html_tra_ve_van_ban_thuan():
    assert manual_book.strip_html("<p>Xin <strong>chào</strong></p>") == "Xin chào"


def test_manifest_ton_tai_va_dung_cau_truc():
    manifest = manual_book.load_manifest()
    assert isinstance(manifest["chapters"], list)
    for chapter in manifest["chapters"]:
        assert chapter["id"] and chapter["title"]
        for entry in chapter["entries"]:
            assert entry["id"] and entry["title"] and entry["file"]
            assert isinstance(entry.get("keywords", []), list)
            covers = entry.get("covers", {})
            for key in ("modules", "actions", "settings", "errors"):
                assert isinstance(covers.get(key, []), list), key


def test_moi_file_trong_manifest_deu_ton_tai():
    manifest = manual_book.load_manifest()
    for chapter in manifest["chapters"]:
        for entry in chapter["entries"]:
            path = manual_book.MANUAL_DIR / entry["file"]
            assert path.is_file(), entry["file"]


def test_khong_co_file_md_mo_coi():
    manifest = manual_book.load_manifest()
    declared = {
        entry["file"].replace("\\", "/")
        for chapter in manifest["chapters"]
        for entry in chapter["entries"]
    }
    on_disk = {
        path.relative_to(manual_book.MANUAL_DIR).as_posix()
        for path in manual_book.MANUAL_DIR.rglob("*.md")
    }
    assert on_disk == declared


def test_id_muc_la_duy_nhat():
    manifest = manual_book.load_manifest()
    ids = [
        entry["id"]
        for chapter in manifest["chapters"]
        for entry in chapter["entries"]
    ]
    assert len(ids) == len(set(ids))


def test_noi_dung_khong_chua_tu_cam_va_khong_bo_trong():
    for path in manual_book.MANUAL_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for word in manual_book.FORBIDDEN_WORDS:
            assert word.lower() not in lowered, f"{path.name} chứa '{word}'"
        for placeholder in ("todo", "tbd", "chưa viết"):
            assert placeholder not in lowered, f"{path.name} còn '{placeholder}'"
        assert "<" not in text, f"{path.name} có HTML thô"


def test_noi_dung_manual_dung_chinh_ta_va_dau_tieng_viet_thong_nhat():
    paths = [manual_book.MANUAL_DIR / "manifest.json"]
    paths.extend(manual_book.MANUAL_DIR.rglob("*.md"))
    nonstandard = (
        "xoá",
        "Xoá",
        "huỷ",
        "Huỷ",
        "mã hoá",
        "Mở ẩn trong tray",
        "Hotkey mở panel",
        "trình duyệt automation",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert text == unicodedata.normalize("NFC", text), path
        for phrase in nonstandard:
            assert phrase not in text, f"{path.name} còn dùng '{phrase}'"


def test_moi_muc_co_du_hai_phan_bat_buoc():
    for path in manual_book.MANUAL_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "## Dùng để làm gì" in text, path.name
        assert "## Các bước" in text, path.name


def test_load_book_dung_html_va_van_ban_tim_kiem():
    book = manual_book.load_book()
    assert book["version"]
    assert book["order"]
    first = book["entries"][book["order"][0]]
    assert first["html"].startswith("<")
    assert first["text"] and "<" not in first["text"]
    assert first["chapter_title"]


def test_load_book_bao_loi_khi_thieu_file(tmp_path, monkeypatch):
    monkeypatch.setattr(manual_book, "MANUAL_DIR", tmp_path)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "id": "x",
                        "title": "X",
                        "entries": [
                            {"id": "x-1", "title": "Một", "file": "khong-co.md"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(manual_book.ManualContentError):
        manual_book.load_book()


def test_bang_ma_loi_phu_het_error_code_info():
    book = manual_book.load_book()
    codes = {row["code"] for row in book["error_table"]}
    assert codes == set(telemetry.ERROR_CODE_INFO)
    for row in book["error_table"]:
        title, suggestion = telemetry.ERROR_CODE_INFO[row["code"]]
        assert row["title"] == title
        assert row["suggestion"] == suggestion


def test_bang_ma_loi_tro_ve_muc_da_khai_bao_phu():
    book = manual_book.load_book()
    rows = {row["code"]: row["entry"] for row in book["error_table"]}
    assert rows["LOGIN_FAILED"] == "bat-dau-dang-nhap"


def test_whats_new_co_muc_cho_phien_ban_hien_tai():
    versions = {item["version"] for item in manual_book.load_whats_new()}
    assert APP_VERSION in versions, (
        f"whats_new.json thiếu mục cho phiên bản {APP_VERSION}"
    )


def test_whats_new_tham_chieu_muc_co_that():
    book = manual_book.load_book()
    for release in book["whats_new"]:
        for highlight in release["highlights"]:
            entry_id = highlight.get("entry")
            if entry_id:
                assert entry_id in book["entries"], entry_id


def test_chi_muc_tim_kiem_gom_tieu_de_tu_khoa_va_noi_dung():
    book = manual_book.load_book()
    row = next(
        item for item in book["search_index"] if item["id"] == "bat-dau-mo-panel"
    )
    assert "hotkey" in row["haystack"]
    assert "ctrl + shift + x" in row["haystack"]
    assert "mo va dong bang dieu khien" in row["haystack"]
    assert row["haystack"] == row["haystack"].lower()


def test_bang_ma_loi_co_chi_muc_tim_kiem_khong_dau():
    book = manual_book.load_book()
    row = next(item for item in book["error_table"] if item["code"] == "LOGIN_FAILED")

    assert "dang nhap" in row["haystack"]


def test_helper_trich_dung_so_luong_hien_co():
    assert len(surface.module_ids()) == 17
    assert "0003_6200" in surface.module_ids()
    assert len(surface.module_actions()) == 36
    assert surface.catalog_actions() == {
        "browse",
        "find",
        "costsheet",
        "bom",
        "files",
        "refresh-folders",
    }
    assert surface.costing_actions() == {
        "export-xlsx",
        "validate-file",
        "import",
        "apply",
        "cancel-plan",
        "clear-dependencies",
    }
    assert surface.style_actions() == {
        "refresh-groups",
        "template",
        "import",
        "cancel",
        "prepare-row",
    }
    assert surface.settings_controls() == {
        "return-list-input",
        "focus-chrome-input",
        "open-costing-file-input",
        "autostart-input",
        "start-hidden-input",
        "admin-mode-input",
        "always-on-top-input",
        "toast-input",
        "hotkey",
        "theme",
    }


def test_helper_doc_duoc_khai_bao_phu():
    assert "hotkey" in surface.covered("settings")
    assert "LOGIN_FAILED" in surface.covered("errors")


def test_chuong_bat_dau_phu_cai_dat_khoi_dong():
    covered = surface.covered("settings")
    for control in (
        "hotkey",
        "start-hidden-input",
        "autostart-input",
        "always-on-top-input",
    ):
        assert control in covered, control


def test_moi_cong_tac_cai_dat_deu_co_huong_dan():
    missing = surface.settings_controls() - surface.covered("settings")
    assert not missing, f"Chưa có hướng dẫn cho: {sorted(missing)}"


def test_moi_nut_catalog_deu_co_huong_dan():
    missing = surface.catalog_actions() - surface.covered("actions")
    assert not missing, f"Chưa có hướng dẫn cho nút Catalog: {sorted(missing)}"


def test_module_catalog_co_huong_dan():
    assert "0003_6200" in surface.covered("modules")


def test_moi_nut_costing_deu_co_huong_dan():
    missing = surface.costing_actions() - surface.covered("actions")
    assert not missing, f"Chưa có hướng dẫn cho nút Costing: {sorted(missing)}"


def test_moi_nut_tao_style_deu_co_huong_dan():
    missing = surface.style_actions() - surface.covered("actions")
    assert not missing, f"Chưa có hướng dẫn cho nút Tạo Style: {sorted(missing)}"


def test_cong_tac_quet_lai_chi_phi_co_huong_dan():
    assert "catalog-special-rescan-input" in surface.covered("settings")


def test_nhom_don_hang_co_du_huong_dan():
    covered = surface.covered("actions")
    missing = {
        action
        for action in surface.module_actions()
        if action.startswith(("oc-", "gdn-", "sample-", "sale-asn-"))
    } - covered
    assert not missing, f"Chưa có hướng dẫn cho: {sorted(missing)}"
    for module_id in (
        "0004_0050_0020",
        "gdn_dispatch",
        "0004_0056_4070",
        "0004_0070_0020",
    ):
        assert module_id in surface.covered("modules"), module_id


def test_moi_module_deu_co_huong_dan():
    missing = surface.module_ids() - surface.covered("modules")
    assert not missing, f"Module chưa có hướng dẫn: {sorted(missing)}"


def test_moi_nut_thao_tac_module_deu_co_huong_dan():
    missing = surface.module_actions() - surface.covered("actions")
    assert not missing, f"Nút chưa có hướng dẫn: {sorted(missing)}"


def test_muc_tra_ma_loi_ton_tai():
    book = manual_book.load_book()
    assert "su-co-tra-ma-loi" in book["entries"]


def test_covers_khong_khai_bao_ma_loi_khong_ton_tai():
    unknown = surface.covered("errors") - set(telemetry.ERROR_CODE_INFO)
    assert not unknown, f"Mã lỗi không có thật: {sorted(unknown)}"


def test_moi_ma_loi_deu_nam_trong_bang_tra():
    book = manual_book.load_book()
    codes = {row["code"] for row in book["error_table"]}
    assert set(telemetry.ERROR_CODE_INFO) <= codes


def test_user_features_dong_bo_voi_manual():
    import sys

    root = manual_book.MANUAL_DIR.parent.parent
    sys.path.insert(0, str(root / "scripts"))
    import generate_user_features

    expected = generate_user_features.build_user_features(manual_book.load_book())
    actual = (root / "docs" / "USER_FEATURES.md").read_text(encoding="utf-8")

    assert actual == expected, (
        "docs/USER_FEATURES.md đã lệch. Chạy: "
        "python scripts/generate_user_features.py"
    )


def test_huong_dan_viet_manual_liet_ke_du_tu_cam():
    root = manual_book.MANUAL_DIR.parent.parent
    text = (root / "docs" / "MANUAL_AUTHORING.md").read_text(encoding="utf-8")
    for word in manual_book.FORBIDDEN_WORDS:
        assert word in text, word
    for label in manual_book.CALLOUT_LABELS.values():
        assert label in text, label


def test_huong_dan_viet_manual_dung_khuon_va_quy_tac_chinh_ta_hien_tai():
    root = manual_book.MANUAL_DIR.parent.parent
    text = (root / "docs" / "MANUAL_AUTHORING.md").read_text(encoding="utf-8")

    assert "## Dùng để làm gì" in text
    assert "## Các bước" in text
    assert "Unicode NFC" in text
    assert "xóa, hủy, hóa" in text
    assert "## Khi nào dùng" not in text
    assert "## Cách làm" not in text
