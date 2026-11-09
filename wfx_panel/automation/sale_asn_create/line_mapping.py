"""Định danh từng dòng Excel khi nhiều màu dùng chung PO và Style."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from wfx_panel.automation.sale_asn_create.values import _fold, _po_key


def _line_group(row: dict) -> tuple[str, str]:
    return _po_key(row.get("po_no")), _fold(row.get("style_no"))


def _separate_line_groups(rows: Sequence[dict]) -> set[tuple[str, str]]:
    return {
        key
        for key, count in Counter(_line_group(row) for row in rows).items()
        if count > 1
    }


def _selection_identity(candidate: dict) -> tuple[str, str, str]:
    return tuple(
        str(candidate.get(key) or "")
        for key in (
            "selection_name",
            "selection_value",
            "selection_order_id",
        )
    )


def _remember_line_selection(
    bindings: dict, row: dict, candidates: Sequence[dict]
) -> None:
    references: set[str] = set()
    wanted_po = _po_key(row.get("po_no"))
    for candidate in candidates:
        values = candidate.get("cell_values") or ()
        for value in (candidate.get("po_no"), *values):
            prefix, separator, reference = str(value or "").partition("/")
            if (
                separator
                and _po_key(reference) in {wanted_po, f"{wanted_po} add"}
                and re.fullmatch(r"PS[WKG]-[^/]+", prefix.strip(), flags=re.IGNORECASE)
            ):
                references.add(_fold(prefix))
    bindings[int(row["source_row"])] = {
        "candidates": [dict(candidate) for candidate in candidates],
        "oc_refs": sorted(references),
    }


def _used_line_selections(
    bindings: dict, source_row: int
) -> list[tuple[str, str, str]]:
    return [
        _selection_identity(candidate)
        for key, binding in bindings.items()
        if int(key) != source_row
        for candidate in binding.get("candidates", ())
    ]
