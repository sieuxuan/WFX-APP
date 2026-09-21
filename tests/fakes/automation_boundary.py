"""Seam dùng chung cho mọi entry point automation.

65 hàm trong `wfx_panel/automation` tự mở Playwright theo đúng một trong hai
hình dạng:

* **A** — `_active_wfx_page(playwright, log)` (oc, grn, dispatch, directory,
  sale_asn_*, bulk_style): một hàm gộp cả `_chrome_is_ready`, `_connect_to_chrome`
  và kiểm tra form đăng nhập.
* **B** — `_chrome_is_ready()` + `_connect_to_chrome(playwright)` +
  `_session_is_active(page)` + `_attach_dialog_handler(page, log)` (catalog,
  costing, modules, reports, color_combination, session).

Vì không có seam nào, test trước đây chỉ chạm được các hàm *bên trong*, còn vỏ
`try/except` — nơi sinh ra `CHROME_CLOSED`, `NOT_LOGGED_IN`, `*_NOT_READY`,
`*_FAILED`, `*_UNCONFIRMED` — chưa từng chạy. `wire_automation()` vá đúng những
ranh giới đó và KHÔNG vá gì khác, nên toàn bộ logic nghiệp vụ vẫn chạy thật.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from tests.fakes.wfx_dom import FakeClock, FakeLocator, FakeNode

WFX_URL = "https://wfx.test/wfx/default.aspx"

# Tên ranh giới mà `wire_automation` biết vá. Module nào không có tên nào trong
# danh sách này thì việc gọi helper là sai chỗ, và helper báo lỗi ngay.
BOUNDARY_NAMES = (
    "sync_playwright",
    "_active_wfx_page",
    "_connect_to_chrome",
    "_chrome_is_ready",
    "_session_is_active",
    "_attach_dialog_handler",
)


class FakeFrame:
    """Frame khai báo: map selector → node và map dấu hiệu JS → giá trị.

    Gặp selector hoặc script chưa khai báo thì raise ``AssertionError`` — fake
    không được im lặng trả mặc định.
    """

    def __init__(
        self,
        clock: FakeClock,
        *,
        url: str = WFX_URL,
        name: str = "",
        nodes: Mapping[str, Sequence[FakeNode]] | None = None,
        scripts: Mapping[str, Any] | None = None,
        empty_selectors: Iterable[str] = (),
    ) -> None:
        self.clock = clock
        self.url = url
        self.name = name
        self.nodes: dict[str, list[FakeNode]] = {
            key: list(value) for key, value in (nodes or {}).items()
        }
        self.scripts = dict(scripts or {})
        self.empty_selectors = set(empty_selectors)
        self.detached = False
        self.evaluated: list[str] = []

    # --- bề mặt Frame ---------------------------------------------------

    def is_detached(self) -> bool:
        return self.detached

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> FakeLocator:
        if selector in self.nodes:
            return FakeLocator(self.nodes[selector], selector)
        if selector in self.empty_selectors:
            return FakeLocator([], selector)
        raise AssertionError(
            f"FakeFrame({self.name or self.url}) chưa khai báo selector: {selector}"
        )

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self.evaluated.append(script)
        for marker, value in self.scripts.items():
            if marker in script:
                return value(arg) if callable(value) else value
        raise AssertionError(
            f"FakeFrame({self.name or self.url}) chưa hỗ trợ script: {script[:140]}"
        )

    def set_nodes(self, selector: str, nodes: Sequence[FakeNode]) -> None:
        self.nodes[selector] = list(nodes)


class FakePage:
    """Tab Chrome giả."""

    def __init__(
        self,
        clock: FakeClock,
        frames: Sequence[Any] = (),
        *,
        url: str = WFX_URL,
        nodes: Mapping[str, Sequence[FakeNode]] | None = None,
        empty_selectors: Iterable[str] = (),
    ) -> None:
        self.clock = clock
        self.url = url
        self.frames = list(frames)
        self.nodes: dict[str, list[FakeNode]] = {
            key: list(value) for key, value in (nodes or {}).items()
        }
        self.empty_selectors = set(empty_selectors)
        self.bring_to_front_calls = 0
        self.closed = False
        self.dialog_handlers: list[Any] = []
        self.context: Any = None

    def bring_to_front(self) -> None:
        self.bring_to_front_calls += 1

    def close(self, run_before_unload: bool = True) -> None:
        self.closed = True

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def on(self, event: str, handler: Any) -> None:
        self.dialog_handlers.append((event, handler))

    def frame(self, name: str | None = None, **_kwargs: Any) -> Any | None:
        return next(
            (item for item in self.frames if getattr(item, "name", "") == name),
            None,
        )

    def locator(self, selector: str) -> FakeLocator:
        if selector in self.nodes:
            return FakeLocator(self.nodes[selector], selector)
        if selector in self.empty_selectors:
            return FakeLocator([], selector)
        raise AssertionError(f"FakePage chưa khai báo selector: {selector}")


class FakeContext:
    def __init__(self, pages: Sequence[FakePage]) -> None:
        self.pages = list(pages)
        self.default_timeout: float | None = None
        self.new_pages = 0
        for page in self.pages:
            page.context = self

    def set_default_timeout(self, timeout: float) -> None:
        self.default_timeout = timeout

    def new_page(self) -> FakePage:  # pragma: no cover - nhánh fallback hiếm
        self.new_pages += 1
        raise PlaywrightError("Fake context không dựng page mới")


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.contexts = [context]
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeDriver:
    """Lease Playwright: test khẳng định flow luôn nhả driver ở `finally`."""

    def __init__(self, world: WfxWorld) -> None:
        self.world = world

    def stop(self) -> None:
        self.world.driver_stops += 1


class FakePlaywrightStarter:
    def __init__(self, world: WfxWorld) -> None:
        self.world = world

    def start(self) -> FakeDriver:
        self.world.driver_starts += 1
        return FakeDriver(self.world)


class WfxWorld:
    """Trình duyệt WFX giả dùng chung cho mọi module automation."""

    def __init__(
        self,
        clock: FakeClock,
        pages: Sequence[FakePage] | None = None,
    ) -> None:
        self.clock = clock
        self.pages = list(pages) if pages is not None else [FakePage(clock)]
        self.context = FakeContext(self.pages)
        self.browser = FakeBrowser(self.context)
        self.driver_starts = 0
        self.driver_stops = 0
        self.dialog_logs: list[Any] = []

    @property
    def page(self) -> FakePage:
        return self.pages[0]

    def add_page(self, page: FakePage) -> FakePage:
        self.context.pages.append(page)
        page.context = self.context
        return page


class WiringReport:
    """Những ranh giới đã thực sự được vá cho module đó."""

    def __init__(self, module_name: str, patched: Sequence[str]) -> None:
        self.module_name = module_name
        self.patched = list(patched)

    def __repr__(self) -> str:  # pragma: no cover - chỉ để đọc lỗi test
        return f"<WiringReport {self.module_name}: {', '.join(self.patched)}>"


def wire_automation(
    monkeypatch,
    module: Any,
    world: WfxWorld,
    *,
    chrome_ready: bool = True,
    logged_in: bool = True,
    clock: FakeClock | None = None,
) -> WiringReport:
    """Vá đúng ranh giới Playwright của `module`, giữ nguyên logic nghiệp vụ.

    `chrome_ready=False` và `logged_in=False` cho phép chạy thật hai nhánh mà
    CLAUDE.md đặc tả kỹ nhưng chưa có test nào: tự mở lại trình duyệt khi
    `CHROME_CLOSED`, và đăng nhập lại đúng một lần khi `NOT_LOGGED_IN`.
    """
    available = [name for name in BOUNDARY_NAMES if hasattr(module, name)]
    assert available, (
        f"{module.__name__} không có ranh giới Playwright nào để vá — "
        "kiểm tra lại tên hàm trong BOUNDARY_NAMES."
    )
    patched: list[str] = []

    def patch(name: str, value: Any) -> None:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            patched.append(name)

    if clock is not None and hasattr(module, "time"):
        monkeypatch.setattr(module, "time", clock)

    patch("sync_playwright", lambda: FakePlaywrightStarter(world))

    def active_wfx_page(_playwright: Any, log: Callable[[str], None]) -> tuple:
        if not chrome_ready:
            raise RuntimeError("CHROME_CLOSED")
        world.dialog_logs.append(log)
        if not logged_in:
            raise RuntimeError("NOT_LOGGED_IN")
        return world.browser, world.page

    patch("_active_wfx_page", active_wfx_page)
    patch(
        "_connect_to_chrome",
        lambda _playwright, **_kwargs: (world.browser, world.page),
    )
    patch("_chrome_is_ready", lambda: chrome_ready)
    patch("_session_is_active", lambda _page: logged_in)
    patch(
        "_attach_dialog_handler",
        lambda page, log: world.dialog_logs.append(log),
    )
    return WiringReport(module.__name__, patched)
