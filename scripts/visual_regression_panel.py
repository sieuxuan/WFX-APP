from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageGrab

ROOT = Path(__file__).resolve().parent.parent
UI_INDEX = ROOT / "wfx_panel" / "ui" / "index.html"
DEFAULT_OUTPUT = ROOT / "build" / "visual-regression"
DPI_FACTORS = {100: 1.0, 125: 1.25, 150: 1.5, 200: 2.0}
THEMES = ("light", "dark")
STATES = ("home", "tooltip", "catalog", "sale-asn", "settings")
WINDOW_WIDTH = 440
WINDOW_HEIGHT = 620


def _visual_state(theme: str) -> dict[str, Any]:
    return {
        "version": "visual-test",
        "theme": theme,
        "user_id": "VISUAL.TEST",
        "has_credentials": True,
        "hotkey_label": "Ctrl + Shift + X",
        "autostart": True,
        "start_hidden": False,
        "toast_enabled": True,
        "focus_chrome_on_module": True,
        "open_costing_file_after_export": True,
        "always_on_top": True,
        "return_to_list_after_action": False,
        "favorite_module_ids": ["0003_6200"],
        "manual_error_codes": [],
        "manual_has_news": True,
        "admin_access": False,
        "admin_module_ids": [],
        "admin_mode": False,
        "chrome_alive": True,
        "browser_available": True,
        "browser_name": "Chrome",
        "session_active": True,
        "current_division": "woven",
        "division_label": "WOVEN",
        "division_name": "Prosports Woven",
        "catalog_default_folder": None,
        "article_library": {},
        "costing_special_options": {},
        "jobs": [],
        "logs": [],
    }


class _VisualAPI:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def get_initial_state(self) -> dict[str, Any]:
        return self._state

    def set_panel_pointer_inside(self, _inside: bool) -> dict[str, bool]:
        return {"ok": True}

    def request_panel_hide(self) -> dict[str, bool]:
        return {"ok": True}

    def set_theme(self, _theme: str) -> dict[str, bool]:
        return {"ok": True}


def _window_rect(title: str) -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        raise RuntimeError(f"Không tìm thấy cửa sổ visual-regression: {title}")

    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = Rect()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return rect.left, rect.top, rect.right, rect.bottom


def _capture_window(title: str, destination: Path) -> tuple[int, int]:
    rect = _window_rect(title)
    image = ImageGrab.grab(bbox=rect, all_screens=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return image.size


def _wait_for_ui(window: Any, timeout_seconds: float = 15) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if window.evaluate_js(
                "Boolean(window.wfxBootstrap && document.querySelector('.module-button'))"
            ):
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError("Panel pywebview không sẵn sàng để chụp")


def _read_metrics(window: Any) -> dict[str, Any]:
    return window.evaluate_js(
        """(() => {
          const panel = document.querySelector('.panel').getBoundingClientRect();
          const visible = element => {
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return !element.hidden && style.display !== 'none' &&
              style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          };
          const buttons = [...document.querySelectorAll('button')].filter(visible);
          return {
            dpr: window.devicePixelRatio,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            scrollWidth: document.documentElement.scrollWidth,
            scrollHeight: document.documentElement.scrollHeight,
            theme: document.documentElement.dataset.theme,
            nativeTitles: document.querySelectorAll('[title]').length,
            tooltipTriggers: document.querySelectorAll('[data-tooltip]').length,
            panel: {x: panel.x, y: panel.y, width: panel.width, height: panel.height},
            visibleButtons: buttons.length,
            tinyButtons: buttons.filter(button => {
              const rect = button.getBoundingClientRect();
              return rect.width < 22 || rect.height < 22;
            }).map(button => button.className || button.textContent.trim()).slice(0, 20),
          };
        })()"""
    )


def _apply_dpi_emulation(window: Any, factor: float, port: int) -> tuple[Any, Any]:
    from playwright.sync_api import sync_playwright

    driver = sync_playwright().start()
    deadline = time.monotonic() + 12
    browser = None
    while time.monotonic() < deadline:
        try:
            browser = driver.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}",
            )
            break
        except Exception:
            time.sleep(0.15)
    if browser is None:
        driver.stop()
        raise RuntimeError(f"Không kết nối được CDP WebView2 ở cổng {port}")

    pages = [
        page
        for context in browser.contexts
        for page in context.pages
        if page.url.lower().endswith("/wfx_panel/ui/index.html")
    ]
    if len(pages) != 1:
        driver.stop()
        raise RuntimeError(f"Cần đúng một panel WebView2, nhận được {len(pages)}")
    page = pages[0]
    session = page.context.new_cdp_session(page)
    width = int(window.evaluate_js("window.innerWidth"))
    height = int(window.evaluate_js("window.innerHeight"))
    session.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": factor,
            "mobile": False,
            "screenWidth": width,
            "screenHeight": height,
        },
    )
    return driver, session


def _capture_one(theme: str, dpi: int, suite: str, output: Path) -> None:
    factor = DPI_FACTORS[dpi]
    port = 9400 + list(DPI_FACTORS).index(dpi) + (10 if theme == "dark" else 0)
    existing_args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        f"{existing_args} --renderer-process-limit=3 --process-per-site"
    ).strip()

    import webview

    webview.settings["REMOTE_DEBUGGING_PORT"] = port

    title = f"WFX Smart Visual · {theme} · {dpi}%"
    state = _visual_state(theme)
    destination = output / suite
    manifest_path = destination / f"{theme}-{dpi}.json"
    manifest: dict[str, Any] = {
        "theme": theme,
        "dpi": dpi,
        "expectedDpr": factor,
        "captures": {},
    }

    window = webview.create_window(
        title,
        url=UI_INDEX.as_uri(),
        js_api=_VisualAPI(state),
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        x=24,
        y=24,
        resizable=False,
        frameless=True,
        easy_drag=False,
        on_top=True,
        background_color="#f7fafb" if theme == "light" else "#08141d",
    )

    capture_errors: list[BaseException] = []

    def run_capture() -> None:
        dpi_driver = None
        dpi_session = None
        try:
            _wait_for_ui(window)
            dpi_driver, dpi_session = _apply_dpi_emulation(window, factor, port)
            window.evaluate_js(f"window.wfxBootstrap({json.dumps(state)});")
            time.sleep(0.7)

            for view_name, setup in (
                ("home", "document.activeElement?.blur()"),
                ("tooltip", "document.querySelector('.manual-button').focus()"),
                (
                    "catalog",
                    "document.activeElement?.blur();"
                    "document.querySelector('[data-module-id=\"0003_6200\"]').click()",
                ),
                (
                    "sale-asn",
                    "document.querySelector('.module-back-button').click();"
                    "document.querySelector("
                    "'[data-module-id=\"0004_0070_0020\"]'"
                    ").click()",
                ),
                (
                    "settings",
                    "document.querySelector('.module-back-button').click();"
                    "document.querySelector('.settings-button').click()",
                ),
            ):
                window.evaluate_js(setup)
                time.sleep(0.55 if view_name == "tooltip" else 0.4)
                filename = f"panel-{theme}-{dpi}-{view_name}.png"
                size = _capture_window(title, destination / filename)
                manifest["captures"][view_name] = {
                    "file": filename,
                    "width": size[0],
                    "height": size[1],
                }

            manifest["metrics"] = _read_metrics(window)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except BaseException as error:
            capture_errors.append(error)
        finally:
            if dpi_session is not None:
                try:
                    dpi_session.detach()
                except Exception:
                    pass
            if dpi_driver is not None:
                dpi_driver.stop()
            window.destroy()

    # Không truyền storage_path: pywebview 5.4 tạo CoreWebView2Environment riêng
    # khi có storage_path và làm rơi CreationProperties/remote debugging args.
    webview.start(run_capture, private_mode=True)
    if capture_errors:
        raise capture_errors[0]


def _run_suite(suite: str, output: Path) -> None:
    for theme in THEMES:
        for dpi in DPI_FACTORS:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--capture-one",
                "--theme",
                theme,
                "--dpi",
                str(dpi),
                "--suite",
                suite,
                "--output",
                str(output),
            ]
            subprocess.run(command, cwd=ROOT, check=True)


def _significant_difference(baseline: Image.Image, current: Image.Image) -> float:
    if baseline.size != current.size:
        return 1.0
    difference = ImageChops.difference(
        baseline.convert("RGB"),
        current.convert("RGB"),
    )
    significant = sum(
        1 for pixel in difference.get_flattened_data() if max(pixel) > 10
    )
    return significant / max(1, baseline.width * baseline.height)


def _validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    metrics = manifest.get("metrics") or {}
    expected_dpr = float(manifest["expectedDpr"])
    actual_dpr = float(metrics.get("dpr") or 0)
    if abs(actual_dpr - expected_dpr) > 0.06:
        errors.append(f"DPR {actual_dpr} != {expected_dpr}")
    if metrics.get("theme") != manifest["theme"]:
        errors.append(f"theme {metrics.get('theme')} != {manifest['theme']}")
    if metrics.get("nativeTitles") != 0:
        errors.append(f"còn {metrics.get('nativeTitles')} title native")
    if metrics.get("scrollWidth", 0) > metrics.get("innerWidth", 0):
        errors.append("tràn ngang viewport")
    if metrics.get("tinyButtons"):
        errors.append(f"button nhỏ hơn 22px: {metrics['tinyButtons']}")
    return errors


def _compare(output: Path, tolerance: float) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ok": True,
        "tolerance": tolerance,
        "comparisons": [],
        "errors": [],
    }
    for theme in THEMES:
        for dpi in DPI_FACTORS:
            current_manifest_path = output / "current" / f"{theme}-{dpi}.json"
            manifest = json.loads(current_manifest_path.read_text(encoding="utf-8"))
            report["errors"].extend(
                f"{theme}-{dpi}: {error}" for error in _validate_manifest(manifest)
            )
            for view_name in STATES:
                filename = f"panel-{theme}-{dpi}-{view_name}.png"
                baseline_path = output / "baseline" / filename
                current_path = output / "current" / filename
                with (
                    Image.open(baseline_path) as baseline,
                    Image.open(current_path) as current,
                ):
                    ratio = _significant_difference(baseline, current)
                row = {
                    "theme": theme,
                    "dpi": dpi,
                    "state": view_name,
                    "differenceRatio": round(ratio, 8),
                    "ok": ratio <= tolerance,
                }
                report["comparisons"].append(row)
                if not row["ok"]:
                    report["errors"].append(
                        f"{theme}-{dpi}-{view_name}: sai khác {ratio:.4%}"
                    )
    report["ok"] = not report["errors"]
    report_path = output / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chụp visual-regression trên pywebview/WebView2 thật.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--suite", choices=("baseline", "current"))
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--tolerance", type=float, default=0.002)
    parser.add_argument("--capture-one", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--theme", choices=THEMES, help=argparse.SUPPRESS)
    parser.add_argument(
        "--dpi", type=int, choices=tuple(DPI_FACTORS), help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    output = args.output.resolve()

    if args.capture_one:
        if not args.theme or not args.dpi or not args.suite:
            parser.error("capture-one cần theme, dpi và suite")
        _capture_one(args.theme, args.dpi, args.suite, output)
        return 0
    if args.suite:
        _run_suite(args.suite, output)
    if args.compare:
        report = _compare(output, args.tolerance)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    if not args.suite:
        parser.error("chọn --suite hoặc --compare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
