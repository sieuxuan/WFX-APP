"""Phân tích và kiểm tra tổ hợp phím cho hotkey toàn cục.

Các hàm trong module này không truy cập bàn phím hoặc GUI để có thể kiểm thử
độc lập. Luật an toàn cố ý chặt: một hotkey toàn cục dùng Backspace/Enter có
thể chặn thao tác nhập liệu trên toàn máy.
"""

from __future__ import annotations

DEFAULT = "ctrl+shift+x"
MODIFIERS = ("ctrl", "alt", "shift", "windows")
UNSAFE_KEYS = frozenset(
    {"backspace", "delete", "enter", "return", "tab", "space", "escape", "esc"}
)

_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "win": "windows",
    "windows": "windows",
    "meta": "windows",
    "cmd": "windows",
    "super": "windows",
}
_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "windows": "Win"}


def _is_function_key(key: str) -> bool:
    """Chỉ F2-F12 được phép đứng một mình; F1 dành cho Trợ giúp."""
    return (
        len(key) >= 2
        and key[0] == "f"
        and key[1:].isdigit()
        and 2 <= int(key[1:]) <= 12
    )


def normalize(spec: str) -> str:
    parts = [part.strip().lower() for part in str(spec).split("+") if part.strip()]
    if not parts:
        raise ValueError("Chưa nhận được tổ hợp phím.")

    modifiers: list[str] = []
    keys: list[str] = []
    for part in parts:
        alias = _MODIFIER_ALIASES.get(part)
        if alias is not None:
            if alias not in modifiers:
                modifiers.append(alias)
        else:
            keys.append(part)

    if len(keys) != 1:
        raise ValueError(
            "Tổ hợp phải có đúng một phím chính ngoài Ctrl/Alt/Shift/Win."
        )

    key = keys[0]
    if key in UNSAFE_KEYS:
        raise ValueError(
            f"Không dùng {key.upper()} làm hotkey được: phím này sẽ bị chặn "
            "trên toàn máy, khiến bạn không gõ hoặc xoá chữ được ở mọi ứng dụng."
        )
    if not modifiers and not _is_function_key(key):
        raise ValueError(
            "Tổ hợp phải có ít nhất một phím bổ trợ (Ctrl/Alt/Shift/Win), "
            "hoặc dùng một phím F2–F12."
        )

    ordered = [modifier for modifier in MODIFIERS if modifier in modifiers]
    return "+".join(ordered + [key])


def is_valid(spec: str) -> bool:
    try:
        normalize(spec)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def format_label(spec: str) -> str:
    parts = normalize(spec).split("+")
    labels = [
        _LABELS.get(part, part.upper() if len(part) <= 3 else part.capitalize())
        for part in parts
    ]
    return " + ".join(labels)


def from_event(event: dict) -> str:
    """Dựng hotkey spec từ payload ``keydown`` của trình duyệt."""
    parts = []
    if event.get("ctrl"):
        parts.append("ctrl")
    if event.get("alt"):
        parts.append("alt")
    if event.get("shift"):
        parts.append("shift")
    if event.get("meta"):
        parts.append("windows")

    code = str(event.get("code") or "")
    key = str(event.get("key") or "")
    if code.startswith("Key") and len(code) == 4:
        base = code[3].lower()
    elif code.startswith("Digit") and len(code) == 6:
        base = code[5]
    elif code.startswith("Numpad") and len(code) > 6:
        base = code[6:].lower()
    elif len(code) >= 2 and code[0] == "F" and code[1:].isdigit():
        base = code.lower()
    else:
        base = key.lower()

    parts.append(base)
    return normalize("+".join(parts))
