"""Đưa cờ WebView2 của app vào đúng `AdditionalBrowserArguments` của pywebview.

pywebview 5.x (`webview/platforms/edgechromium.py`, `EdgeChrome.__init__`) luôn
tạo `CoreWebView2CreationProperties` và gán `AdditionalBrowserArguments`. Khi
environment được tạo kèm options như vậy, WebView2 bỏ qua biến môi trường
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`, nên giới hạn renderer đặt qua biến môi
trường chưa từng có hiệu lực. Sửa giá trị sau `__init__` cũng không kịp: chính
`__init__` gọi `EnsureCoreWebView2Async` và WebView2 đọc tham số ngay lúc đó.

Vì vậy app thay class options trong module `edgechromium` bằng subclass .NET
chặn mọi lần pywebview gán tham số (`=` rồi `+=`) và ghép thêm cờ của app. Cờ
pywebview tự thêm (`--allow-file-access-from-files`, `--remote-debugging-port`)
được giữ nguyên.
"""

from __future__ import annotations

import os
import re
from typing import Any

ENV_NAME = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"

# Giới hạn WebView2 của panel/bubble/menu/Manual trên máy 8 GB RAM.
APP_BROWSER_ARGUMENTS = (
    "--renderer-process-limit=3 --process-per-site "
    "--disable-background-networking --disable-component-update "
    "--disable-sync --no-service-autorun"
)

# Chromium chỉ giữ lần xuất hiện cuối của một switch, nên danh sách feature của
# hai nguồn phải gộp thành một switch thay vì để switch sau đè switch trước.
_FEATURE_SWITCHES = ("--enable-features", "--disable-features")
_TOKEN = re.compile(r'(?:[^\s"]+|"[^"]*")+')
_PATCH_MARKER = "_wfx_browser_arguments"


def desired_browser_arguments(environ: Any = None) -> str:
    """Cờ app cần thêm; quản trị viên override toàn bộ bằng biến môi trường."""
    environ = os.environ if environ is None else environ
    override = str(environ.get(ENV_NAME) or "").strip()
    return override or APP_BROWSER_ARGUMENTS


def _switch_name(token: str) -> str:
    return token.split("=", 1)[0] if token.startswith("-") else token


def merge_browser_arguments(base: str | None, extra: str | None) -> str:
    """Ghép `extra` vào cuối `base`; gọi lại nhiều lần vẫn cho cùng kết quả.

    Switch trùng tên trong `extra` thắng switch của `base`. Riêng
    `--enable-features`/`--disable-features` được hợp danh sách feature.
    """
    base_tokens = _TOKEN.findall(base or "")
    extra_tokens = _TOKEN.findall(extra or "")
    extra_names = {_switch_name(token) for token in extra_tokens}

    features: dict[str, list[str]] = {}
    merged: list[str] = []
    for token, from_base in [
        *((token, True) for token in base_tokens),
        *((token, False) for token in extra_tokens),
    ]:
        name = _switch_name(token)
        if name in _FEATURE_SWITCHES:
            values = features.setdefault(name, [])
            for value in token.partition("=")[2].split(","):
                value = value.strip()
                if value and value not in values:
                    values.append(value)
        elif not (from_base and name in extra_names) and token not in merged:
            merged.append(token)

    merged.extend(
        f"{name}={','.join(values)}" for name, values in features.items() if values
    )
    return " ".join(merged)


def install(edgechromium: Any, extra: str | None = None) -> bool:
    """Thay class options của pywebview để mọi WebView2 nhận cờ của app.

    Trả `False` nếu pywebview đổi cấu trúc nội bộ; app vẫn chạy bình thường,
    chỉ không có giới hạn renderer.
    """
    extra = desired_browser_arguments() if extra is None else extra
    base = getattr(edgechromium, "CoreWebView2CreationProperties", None)
    if base is None:
        return False
    if getattr(base, _PATCH_MARKER, None) is not None:
        setattr(base, _PATCH_MARKER, extra)
        return True
    native = getattr(base, "AdditionalBrowserArguments", None)
    if native is None or not hasattr(native, "__set__"):
        return False

    def _get(self: Any) -> str:
        return native.__get__(self, base)

    def _set(self: Any, value: str) -> None:
        native.__set__(
            self,
            merge_browser_arguments(value, getattr(type(self), _PATCH_MARKER)),
        )

    patched = type(
        "WfxCoreWebView2CreationProperties",
        (base,),
        {
            "__namespace__": "WfxPanel.WebView2",
            "AdditionalBrowserArguments": property(_get, _set),
            _PATCH_MARKER: extra,
        },
    )
    edgechromium.CoreWebView2CreationProperties = patched
    return True
