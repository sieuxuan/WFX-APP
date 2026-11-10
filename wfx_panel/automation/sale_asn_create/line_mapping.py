"""Định danh từng dòng Excel khi nhiều màu dùng chung PO và Style."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from wfx_panel.automation.sale_asn_create.values import _fold, _po_key


def _line_group(row: dict) -> tuple[str, str]:
    return _po_key(row.get("po_no")), _fold(row.get("style_no"))


def _order_style_matches(wanted: str, actual: str) -> bool:
    if not wanted or not actual:
        return False
    return f" {wanted} " in f" {actual} " or f" {actual} " in f" {wanted} "


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
    source_row = int(row["source_row"])
    bindings[source_row] = {
        "candidates": [dict(candidate) for candidate in candidates],
        "oc_refs": sorted(references),
    }
    if len(candidates) == 1 and (member := candidates[0].get("_combined_member")):
        bindings[member] = {"combined_into": source_row}


def _combined_line_owners(bindings: dict) -> dict[int, int]:
    return {
        int(source_row): binding["combined_into"]
        for source_row, binding in bindings.items()
        if "combined_into" in binding
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
