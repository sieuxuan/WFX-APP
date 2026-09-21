"""Đọc bảng Color/Size Dependency: được thử lại, và hỏng thì báo đúng lỗi.

`_scan_dependency_table()` phải mở popup Dependency của WFX rồi đọc từng dòng,
nên một lượt hỏng vì popup chưa kịp hiện là chuyện bình thường. Nếu không thử
lại, `_dependency_scan_incomplete()` bật và **đổ cả lượt Export** — người dùng
phải chạy lại từ đầu.

Trước đây vòng thử lại viết `for attempt in range(1)` kèm `if attempt == 0:
_sleep(0.2)`: chỉ chạy đúng một lượt, ngủ 0,2 giây rồi bỏ cuộc. Mọi chỗ khác
trong repo (`directory.py`, `oc.py`, `panel_api.py`) đều dùng `range(2)`.
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import FakeFrame
from tests.fakes.wfx_dom import FakeNode, install_fake_clock
from wfx_panel.automation import _common, costing


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, costing, _common)


@pytest.fixture
def frame(clock):
    return FakeFrame(clock, name="body", nodes={"body": [FakeNode()]})


def _document(*, mapping_value: str = "") -> dict:
    """Một Article đang để Color Dependency ở chế độ [Table]."""
    return {
        "fields": [
            {
                "section_key": "fabric",
                "item_key": "F-001",
                "field_key": "colColorDependency",
                "value": "[Table]",
            },
            {
                "section_key": "fabric",
                "item_key": "F-001",
                "field_key": "colMaterialColorList",
                "value": "RED",
            },
            {
                "section_key": "fabric",
                "item_key": "F-001",
                "field_key": "colColorDependencyMapping",
                "value": mapping_value,
                "_live": {"dependency_kind": "Color", "row_index": 3},
            },
        ]
    }


def _mapping_field(document: dict) -> dict:
    return document["fields"][2]


@pytest.fixture
def no_page_data(monkeypatch):
    """Ép đi vào đường chậm: đọc popup thay vì lấy thẳng từ page data."""
    monkeypatch.setattr(
        costing,
        "_scan_dependency_tables_from_page_data",
        lambda *_a, **_k: ({}, {"Color": [], "Size": []}),
    )


def test_a_popup_that_opens_late_is_read_on_the_second_attempt(
    monkeypatch,
    frame,
    no_page_data,
):
    attempts: list[int] = []

    def flaky(_frame, _field, _known):
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise costing.PlaywrightTimeoutError("popup chưa hiện")
        return "RED => Style A", ["Style A", "Style B"]

    monkeypatch.setattr(costing, "_scan_dependency_table", flaky)
    document = _document()

    costing._scan_costing_dependency_tables(frame, document)

    assert len(attempts) == 2, "Lượt đầu hỏng phải được thử lại đúng một lần"
    assert _mapping_field(document)["value"] == "RED => Style A"
    assert _mapping_field(document)["options"] == ["Style A", "Style B"]
    assert costing._dependency_scan_incomplete(document) is False


def test_a_first_attempt_that_works_is_never_repeated(
    monkeypatch,
    frame,
    no_page_data,
):
    attempts: list[int] = []

    def once(_frame, _field, _known):
        attempts.append(len(attempts))
        return "RED => Style A", ["Style A"]

    monkeypatch.setattr(costing, "_scan_dependency_table", once)

    costing._scan_costing_dependency_tables(frame, _document())

    assert len(attempts) == 1, "Mở lại popup thừa làm Export chậm gấp đôi"


def test_the_retry_is_bounded(monkeypatch, frame, no_page_data):
    """Popup hỏng hẳn thì phải dừng, không quay vòng vô hạn trên WFX."""
    attempts: list[int] = []

    def always_fails(_frame, _field, _known):
        attempts.append(len(attempts))
        raise costing.PlaywrightTimeoutError("popup không mở")

    monkeypatch.setattr(costing, "_scan_dependency_table", always_fails)
    document = _document()

    costing._scan_costing_dependency_tables(frame, document)

    assert len(attempts) == costing.DEPENDENCY_TABLE_ATTEMPTS == 2
    assert costing._dependency_scan_incomplete(document) is True


def test_every_failed_attempt_closes_the_popup_it_opened(
    monkeypatch,
    frame,
    no_page_data,
):
    """Popup còn mở sẽ che grid và làm field kế tiếp hỏng theo dây chuyền."""
    monkeypatch.setattr(
        costing,
        "_scan_dependency_table",
        lambda *_a: (_ for _ in ()).throw(costing.PlaywrightError("detach")),
    )

    costing._scan_costing_dependency_tables(frame, _document())

    assert frame.nodes["body"][0].keys == ["Escape", "Escape"]


def test_a_value_already_read_from_page_data_skips_the_popup(monkeypatch, frame):
    """Đường nhanh vẫn phải được ưu tiên: mở popup là đắt nhất trong Export."""
    monkeypatch.setattr(
        costing,
        "_scan_dependency_tables_from_page_data",
        lambda *_a, **_k: (
            {(3, "Color"): "RED => Style A"},
            {"Color": ["Style A"], "Size": []},
        ),
    )
    monkeypatch.setattr(
        costing,
        "_scan_dependency_table",
        lambda *_a: pytest.fail("Đã có giá trị thì không được mở popup"),
    )
    document = _document()

    costing._scan_costing_dependency_tables(frame, document)

    assert _mapping_field(document)["value"] == "RED => Style A"


# --- Mã lỗi phải đọc được ----------------------------------------------


def test_an_incomplete_dependency_scan_keeps_its_own_code():
    """Trước đây lỗi này rơi vào nhánh cuối và in `RuntimeError: ...` ra UI."""
    result = costing._costing_scan_error(
        RuntimeError("COSTING_DEPENDENCY_SCAN_INCOMPLETE"),
        "SKN0000188",
        lambda _line: None,
    )

    assert result["code"] == "COSTING_DEPENDENCY_SCAN_INCOMPLETE"
    assert "RuntimeError" not in result["message"]
    assert "COSTING_" not in result["message"]
    assert "Dependency" in result["message"]
