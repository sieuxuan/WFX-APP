from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path

from wfx_panel.atomic_io import write_json_atomic


def normalise_buyers(items: object) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    buyers: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "").strip()
        identity = label.casefold()
        if not label or identity in seen:
            continue
        seen.add(identity)
        buyers.append({"label": label, "value": str(item.get("value") or "")})
    return buyers


class SaleASNBuyerStore:
    """Cache Buyer Sale ASN, tách biệt khỏi bridge và chịu được JSON hỏng."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[dict[str, str]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        return normalise_buyers(raw.get("buyers") if isinstance(raw, Mapping) else None)

    def save(self, buyers: object) -> list[dict[str, str]]:
        cleaned = normalise_buyers(buyers)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            self.path,
            {
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "buyers": cleaned,
            },
            indent=2,
        )
        return cleaned
