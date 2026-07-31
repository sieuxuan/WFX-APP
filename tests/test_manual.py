from wfx_panel import manual_book


def test_slugify_bo_dau_tieng_viet():
    assert manual_book.slugify("Tìm Style trên WFX") == "tim-style-tren-wfx"
    assert manual_book.slugify("Gặp lỗi thì sao?") == "gap-loi-thi-sao"


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
