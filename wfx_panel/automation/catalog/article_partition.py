"""Chia nhỏ danh sách Article của WFX bằng bộ lọc ``contains`` theo Code.

``WFXCommon/GetData`` (objectName ``CatalogList``) luôn trả tối đa 100 dòng mới
nhất và bỏ qua ``pagingParams``, sắp xếp, lọc ngày, ``startsWith`` lẫn set
filter; thứ duy nhất server áp dụng là ``contains``/``equals`` trên cột
``lnkArticleCode``. Muốn lấy đủ Article thì phải chia không gian Code thành
các truy vấn ``contains`` đủ hẹp để mỗi truy vấn trả dưới 100 dòng.

Lập luận đầy đủ: một mã X luôn chứa mọi tiền tố của chính nó. Đi từ ký tự
đầu X[0] rồi nối dần ký tự sang phải, sẽ tới một tiền tố mà truy vấn
``contains`` trả dưới 100 dòng — lúc đó kết quả là TẤT CẢ mã chứa tiền tố ấy,
gồm cả X. Vậy chỉ cần:

* mở rộng nút bão hòa (đủ 100 dòng) bằng mọi ký tự có thể đứng sau;
* chỉ mở rộng gốc là ký tự đầu của ít nhất một mã đã thấy — gốc như ``W``
  trong ``SWV…`` chỉ lặp lại cả họ mã ``SWV`` và nhân số truy vấn lên vài lần.

Hai heuristic giảm số truy vấn, đều tự phục hồi khi dữ liệu trái giả định:

* sau một chữ số chỉ mở 0–9 cộng các ký tự từng thấy đứng sau chữ số;
* 100 dòng đúng bằng ``q`` + đủ 100 tổ hợp hai chữ số được coi là trọn.

Bảng ký tự lớn dần theo dữ liệu đọc được; khi gặp ký tự mới, mọi nút bão hòa
đã mở rộng được bổ sung đúng nhánh còn thiếu. Module này là Python thuần.
"""

from __future__ import annotations

import csv
import io
import string
from collections.abc import Iterable
from dataclasses import dataclass, field

SERVER_ROW_CAP = 100
DIGITS = frozenset(string.digits)
BASE_ALPHABET = frozenset(string.ascii_uppercase) | DIGITS
# Ký hiệu hiếm trong mã: hỏi riêng từng ký hiệu là thu trọn mọi mã chứa nó, kể
# cả mã có ký hiệu đứng sau chữ số mà luật "sau chữ số chỉ mở 0–9" bỏ qua.
SYMBOL_ROOTS = frozenset("-/_.&()+#, ")
CSV_HEADER = ("Article_Code", "Article_Name", "Buyer_Reference", "Article_Category")


def normalize_code(value: object) -> str:
    return " ".join(str(value or "").split()).upper()


def is_full_digit_block(query: str, codes: Iterable[str]) -> bool:
    """100 mã đúng bằng ``query`` + mọi tổ hợp hai chữ số: không thể còn mã khác cùng dạng."""
    suffixes = set()
    for code in codes:
        if not code.startswith(query) or len(code) != len(query) + 2:
            return False
        tail = code[len(query):]
        if not tail.isdigit():
            return False
        suffixes.add(tail)
    return len(suffixes) == SERVER_ROW_CAP


@dataclass
class PartitionPlanner:
    """Kế hoạch truy vấn ``contains`` cho một Category.

    Vòng đời: ``next_batch()`` lấy các truy vấn kế tiếp, ``record()`` nạp kết
    quả của từng truy vấn, lặp tới khi ``done``.
    """

    max_queries: int = 4000
    rows: dict[str, dict] = field(default_factory=dict)
    queried: set[str] = field(default_factory=set)
    saturated: list[str] = field(default_factory=list)
    assumed_complete_blocks: int = 0
    ignored_queries: list[str] = field(default_factory=list)
    _pending: list[str] = field(default_factory=list)
    _alphabet: set[str] = field(default_factory=lambda: set(BASE_ALPHABET))
    _after_digit: set[str] = field(default_factory=lambda: set(DIGITS))
    _first_chars: set[str] = field(default_factory=set)
    _saturated_roots: set[str] = field(default_factory=set)
    _expanded: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # Truy vấn rỗng = không lọc. Category dưới 100 Article xong ngay ở đây.
        self._pending = [""]

    # -- truy vấn ---------------------------------------------------------
    @property
    def query_count(self) -> int:
        return len(self.queried)

    @property
    def exhausted(self) -> bool:
        return self.query_count >= self.max_queries

    @property
    def done(self) -> bool:
        return not self._pending or self.exhausted

    def next_batch(self, size: int) -> list[str]:
        batch: list[str] = []
        while self._pending and len(batch) < size and (
            self.query_count + len(batch) < self.max_queries
        ):
            query = self._pending.pop()
            if query in self.queried or query in batch:
                continue
            batch.append(query)
        return batch

    def _enqueue(self, query: str) -> None:
        if query not in self.queried:
            self._pending.append(query)

    # -- kết quả ------------------------------------------------------------
    def _children_chars(self, query: str) -> set[str]:
        return set(self._after_digit) if query[-1] in DIGITS else set(self._alphabet)

    def _expand(self, query: str) -> None:
        self._expanded.add(query)
        for char in sorted(self._children_chars(query), reverse=True):
            self._enqueue(query + char)

    def _learn(self, codes: Iterable[str]) -> None:
        new_alphabet: set[str] = set()
        new_after_digit: set[str] = set()
        new_first: set[str] = set()
        for code in codes:
            if not code:
                continue
            if code[0] not in self._first_chars:
                new_first.add(code[0])
            for index, char in enumerate(code):
                if char not in self._alphabet:
                    new_alphabet.add(char)
                if index and code[index - 1] in DIGITS and char not in self._after_digit:
                    new_after_digit.add(char)
        self._alphabet |= new_alphabet
        self._after_digit |= new_after_digit
        # Ký tự lạ vừa lộ ra cũng là một gốc cần hỏi riêng.
        for char in sorted(new_alphabet):
            self._enqueue(char)
        self._first_chars |= new_first
        # Ký tự mới: bổ sung nhánh còn thiếu cho các nút đã mở rộng trước đó.
        if new_alphabet or new_after_digit:
            for query in sorted(self._expanded):
                for char in self._children_chars(query) & (
                    new_alphabet | new_after_digit
                ):
                    self._enqueue(query + char)
        # Gốc bão hòa vừa lộ ra là ký tự đầu của một mã: giờ mới cần mở rộng.
        for root in sorted(self._saturated_roots & new_first):
            if root not in self._expanded:
                self._expand(root)

    def record(self, query: str, rows: list[dict]) -> None:
        self.queried.add(query)
        codes = []
        for row in rows:
            code = normalize_code(row.get("code"))
            if not code:
                continue
            codes.append(code)
            self.rows.setdefault(code, row)
        saturated = len(rows) >= SERVER_ROW_CAP
        if query and any(query.upper() not in code for code in codes):
            # Server không áp bộ lọc này (cắt khoảng trắng, bỏ ký hiệu…): kết
            # quả chỉ là 100 mã mới nhất, mở rộng nó chỉ nhân truy vấn vô ích.
            self.ignored_queries.append(query)
            self._learn(codes)
            return
        if saturated and is_full_digit_block(query, codes):
            self.assumed_complete_blocks += 1
            saturated = False
        if saturated and not query:
            self.saturated.append(query)
            self._pending.extend(sorted(BASE_ALPHABET | SYMBOL_ROOTS))
        elif saturated:
            self.saturated.append(query)
            if len(query) == 1:
                self._saturated_roots.add(query)
                if query in self._first_chars or query in {c[0] for c in codes}:
                    self._expand(query)
                elif query not in DIGITS:
                    # Chữ cái chỉ thấy ở giữa mã: mã có chữ này đứng sau chữ số
                    # không đi qua nhánh nào khác, hỏi thẳng "<số><chữ>".
                    for digit in sorted(DIGITS, reverse=True):
                        self._enqueue(digit + query)
            else:
                self._expand(query)
        self._learn(codes)

    @property
    def unexpanded_roots(self) -> list[str]:
        """Gốc bão hòa chưa từng thấy đứng đầu mã nào — rủi ro sót duy nhất."""
        return sorted(self._saturated_roots - self._expanded)


def articles_csv(rows_by_category: dict[str, Iterable[dict]]) -> str:
    """CSV cùng định dạng ``Article List.csv`` (BOM do caller ghi)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for category in sorted(rows_by_category):
        for row in sorted(
            rows_by_category[category],
            key=lambda item: normalize_code(item.get("code")),
        ):
            writer.writerow(
                (
                    str(row.get("code") or "").strip(),
                    " ".join(str(row.get("name") or "").split()),
                    " ".join(str(row.get("buyer_reference") or "").split()),
                    category,
                )
            )
    return buffer.getvalue()
