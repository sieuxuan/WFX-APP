"""Bằng chứng xác nhận màn New — nhánh mà marker chưa đọc được trước khi click.

CLAUDE.md: `New` chỉ được báo thành công khi thấy đúng trang đích đọc từ chính
link menu, hoặc khi đã đặt được dropdown mặc định của màn New. Một frame đổi
document là KHÔNG đủ, vì menu WFX cũng tự reload sau cú click.

QA Request là entry duy nhất không có dropdown mặc định, nên với nó marker trang
đích là bằng chứng duy nhất. Nếu marker đọc hụt ngay trước khi click — link menu
chưa attach, WFX còn đang render — app không được lặng lẽ hạ chuẩn xuống "có
frame nào đó đổi document".
"""

from __future__ import annotations

from types import SimpleNamespace

from wfx_panel.automation import modules

QA_MODULE_ID = "0063_0030_0020"
QA_DESTINATION = "https://wfx.example/WFXQAInspectionRequest.aspx?Action=New"
MENU_FRAME = "https://wfx.example/wfx_Home.aspx"


class _Frame:
    def __init__(self, url: str) -> None:
        self.url = url
        self.marker = ""

    def evaluate(self, _script, marker=None):
        if marker is None:
            return self.marker
        self.marker = marker
        return None


def _run_qa_new(monkeypatch, frame_urls, *, markers):
    """`markers`: kết quả lần lượt của mỗi lời gọi `_menu_target_markers`.

    Lần đầu chạy trước khi click, lần sau (nếu có) chạy sau khi click — mô phỏng
    link menu chỉ attach xong sau khi WFX render.
    """
    reads = list(markers)
    page = SimpleNamespace(
        frames=[_Frame(url) for url in frame_urls],
        wait_for_timeout=lambda _ms: None,
    )
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[page])])

    monkeypatch.setattr(modules, "MODULE_NEW_CONFIRM_SECONDS", 0.3)
    monkeypatch.setattr(
        modules,
        "sync_playwright",
        lambda: SimpleNamespace(start=lambda: SimpleNamespace(stop=lambda: None)),
    )
    monkeypatch.setattr(modules, "_active_wfx_page", lambda *_a: (browser, page))
    monkeypatch.setattr(modules, "_click_module_menu_on_page", lambda *_a: True)
    monkeypatch.setattr(modules, "_document_changed", lambda *_a: True)
    monkeypatch.setattr(modules, "_wait", lambda *_a, **_k: None)
    monkeypatch.setattr(
        modules,
        "_menu_target_markers",
        lambda *_a: reads.pop(0) if len(reads) > 1 else reads[0],
    )
    return modules.open_module_new(QA_MODULE_ID, lambda _line: None)


def test_an_unreadable_menu_link_is_not_a_confirmation(monkeypatch):
    """Link menu chưa attach lúc đọc marker: click xong vẫn phải có bằng chứng."""
    result = _run_qa_new(monkeypatch, [MENU_FRAME], markers=[(), ()])

    assert result["ok"] is False, (
        "Không đọc được trang đích mà vẫn báo đã mở màn New"
    )
    assert result["code"] == "MODULE_FAILED"


def test_the_destination_page_still_confirms_when_markers_arrive_late(
    monkeypatch,
):
    """Marker đọc hụt trước click nhưng màn New đã mở thật thì vẫn phải thành công."""
    result = _run_qa_new(
        monkeypatch,
        [QA_DESTINATION],
        markers=[(), ("wfxqainspectionrequest.aspx",)],
    )

    assert result["ok"] is True, result
    assert result["code"] == "MODULE_NEW_READY"


def test_markers_read_before_the_click_keep_working(monkeypatch):
    result = _run_qa_new(
        monkeypatch,
        [QA_DESTINATION],
        markers=[("wfxqainspectionrequest.aspx",)],
    )

    assert result["code"] == "MODULE_NEW_READY", result
