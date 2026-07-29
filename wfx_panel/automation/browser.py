"""Phát hiện/khởi chạy/kết nối trình duyệt automation cho WFX.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from wfx_panel.automation._common import (
    CDP_HOST,
    CDP_PORT,
    CDP_URL,
    DEFAULT_TIMEOUT_MS,
    URL,
    Any,
    Browser,
    Callable,
    Page,
    Path,
    Playwright,
    PlaywrightError,
    URLError,
    _result,
    _sleep,
    _write_log,
    dataclass,
    json,
    os,
    shutil,
    subprocess,
    time,
    urlopen,
)
from wfx_panel.automation.runtime import connect_browser, invalidate_browser


@dataclass(frozen=True)
class BrowserExecutable:
    name: str
    path: Path


def detect_browser() -> BrowserExecutable | None:
    """Tìm Chromium browser có hỗ trợ CDP trên Windows 10/11.

    Ưu tiên đường dẫn do người dùng cấu hình, sau đó Chrome Stable và các
    channel Chrome/Edge/Brave/Chromium thường gặp.
    """
    configured_path = os.getenv("WFX_CHROME_PATH")
    roots = [
        Path(value)
        for value in (
            os.getenv("PROGRAMFILES"),
            os.getenv("PROGRAMFILES(X86)"),
            os.getenv("LOCALAPPDATA"),
        )
        if value
    ]
    candidates: list[tuple[str, str | Path | None]] = [
        ("Trình duyệt đã cấu hình", configured_path),
        ("Google Chrome", shutil.which("chrome") or shutil.which("chrome.exe")),
    ]
    relative_paths = [
        ("Google Chrome", "Google/Chrome/Application/chrome.exe"),
        ("Google Chrome Beta", "Google/Chrome Beta/Application/chrome.exe"),
        ("Google Chrome Dev", "Google/Chrome Dev/Application/chrome.exe"),
        ("Google Chrome Canary", "Google/Chrome SxS/Application/chrome.exe"),
        ("Microsoft Edge", "Microsoft/Edge/Application/msedge.exe"),
        ("Microsoft Edge Beta", "Microsoft/Edge Beta/Application/msedge.exe"),
        ("Microsoft Edge Dev", "Microsoft/Edge Dev/Application/msedge.exe"),
        ("Microsoft Edge Canary", "Microsoft/Edge SxS/Application/msedge.exe"),
        ("Brave", "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("Chromium", "Chromium/Application/chrome.exe"),
    ]
    candidates.extend(
        (name, root / relative)
        for name, relative in relative_paths
        for root in roots
    )
    seen: set[str] = set()
    for name, candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return BrowserExecutable(name=name, path=path)
    return None


def _find_chrome() -> Path:
    """Alias tương thích ngược cho caller/test cũ."""
    browser = detect_browser()
    if browser is not None:
        return browser.path
    raise FileNotFoundError(
        "Không tìm thấy Chrome, Edge, Brave hoặc Chromium. "
        "Hãy cài một trình duyệt Chromium hoặc đặt WFX_CHROME_PATH tới file .exe."
    )


def _chrome_is_ready() -> bool:
    try:
        with urlopen(f"{CDP_URL}/json/version", timeout=1) as response:
            info = json.load(response)
        return bool(info.get("webSocketDebuggerUrl"))
    except (OSError, URLError, ValueError):
        return False


def _disable_password_manager(profile_dir: Path) -> None:
    """Tắt Password Manager chỉ trong profile automation của WFX.

    Không thay đổi profile Chrome/Edge cá nhân. Chromium đọc các preference
    này trước khi tạo cửa sổ đầu tiên, vì vậy popup Save/Remember password
    không xuất hiện sau thao tác login tự động.
    """
    preferences_path = profile_dir / "Default" / "Preferences"
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    preferences: dict[str, Any] = {}
    if preferences_path.is_file():
        try:
            loaded = json.loads(preferences_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                preferences = loaded
        except (OSError, json.JSONDecodeError):
            preferences = {}

    profile = preferences.setdefault("profile", {})
    if not isinstance(profile, dict):
        profile = {}
        preferences["profile"] = profile
    profile["password_manager_enabled"] = False
    preferences["credentials_enable_service"] = False
    preferences["password_manager_leak_detection"] = False

    temporary = preferences_path.with_name(preferences_path.name + ".tmp")
    temporary.write_text(
        json.dumps(preferences, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(preferences_path)


def _start_persistent_chrome(log: Callable[[str], None]) -> None:
    """Mở Chrome độc lập để Chrome không đóng khi app hoặc Playwright kết thúc."""
    if _chrome_is_ready():
        return

    browser = detect_browser()
    if browser is None:
        raise FileNotFoundError(
            "Không tìm thấy trình duyệt Chromium tương thích. "
            "Cài Chrome/Edge/Brave/Chromium hoặc đặt WFX_CHROME_PATH."
        )
    chrome_path = browser.path
    local_app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    profile_dir = local_app_data / "WFX-Automation" / "ChromeProfile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    _disable_password_manager(profile_dir)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        [
            str(chrome_path),
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-save-password-bubble",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-service-autorun",
            "--process-per-site",
            "--renderer-process-limit=4",
            "--disable-features=PasswordManagerOnboarding,PasswordManagerEnableAccountStorage,PasswordLeakDetection,MediaRouter,OptimizationHints",
            URL,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    _write_log(
        log,
        f"Đang mở {browser.name} với profile automation riêng.",
    )

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _chrome_is_ready():
            return
        _sleep(0.25)
    raise TimeoutError(f"Chrome không mở cổng điều khiển {CDP_URL} sau 15 giây.")


def start_chrome(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Mở/focus Chrome automation mà không tự đăng nhập hay đổi trang WFX."""
    try:
        was_ready = _chrome_is_ready()
        browser = detect_browser()
        if not was_ready and browser is None:
            return _result(
                False,
                "BROWSER_NOT_FOUND",
                "Không tìm thấy Chrome, Edge, Brave hoặc Chromium. "
                "Cài một trình duyệt tương thích hoặc cấu hình WFX_CHROME_PATH.",
                chrome_alive=False,
                browser_available=False,
            )
        _start_persistent_chrome(log)
        return _result(
            True,
            "CHROME_ALREADY_OPEN" if was_ready else "CHROME_OPENED",
            (
                "Trình duyệt automation đã sẵn sàng."
                if was_ready
                else f"{browser.name} automation đã sẵn sàng."
            ),
            chrome_alive=True,
            browser_available=True,
            browser_name=browser.name if browser else "Chromium",
        )
    except Exception as exc:
        message = f"Không mở được Chrome: {type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(
            False,
            "CHROME_OPEN_FAILED",
            message,
            chrome_alive=False,
        )


def browser_status() -> dict[str, Any]:
    browser = detect_browser()
    return {
        "chrome_alive": _chrome_is_ready(),
        "browser_available": browser is not None,
        "browser_name": browser.name if browser else None,
    }


def _connect_to_chrome(playwright: Playwright) -> tuple[Browser, Page]:
    browser = connect_browser(playwright, CDP_URL)
    try:
        contexts = browser.contexts
    except PlaywrightError:
        invalidate_browser(browser)
        browser = connect_browser(playwright, CDP_URL)
        contexts = browser.contexts
    if not contexts:
        raise RuntimeError("Đã kết nối Chrome nhưng không tìm thấy browser context.")

    context = contexts[0]
    context.set_default_timeout(DEFAULT_TIMEOUT_MS)
    # Luôn ưu tiên tab WFX chính, tránh bám nhầm popup Article Detail.
    page = next(
        (p for p in context.pages if "/wfx/default.aspx" in p.url.lower()),
        None,
    )
    if page is None:
        page = next(
            (p for p in context.pages if "worldfashionexchange.com" in p.url),
            None,
        )
    if page is None:
        page = next((p for p in context.pages if p.url in ("", "about:blank")), None)
    if page is None:
        page = context.new_page()
    page.bring_to_front()
    return browser, page


def _attach_dialog_handler(page: Page, log: Callable[[str], None]) -> None:
    """Giữ alert WFX hiện trên Chrome để người dùng đọc và xác nhận.

    Playwright tự dismiss dialog khi không có listener. Listener cũ lại accept
    ngay lập tức, vì vậy system alert chỉ chớp hoặc hoàn toàn không nhìn thấy.
    Chỉ gắn một listener tại một thời điểm; không gọi accept/dismiss để Chrome
    giữ dialog native cho đến khi người dùng trực tiếp xử lý.
    """
    def attach_to(target: Page) -> None:
        previous = getattr(target, "_wfx_dialog_handler", None)
        if previous is not None:
            try:
                target.remove_listener("dialog", previous)
            except Exception:
                pass

        def show_dialog(dialog: Any) -> None:
            text = (dialog.message or "").strip().replace("\n", " ")
            _write_log(
                log,
                "[WFX ALERT] Chrome đang chờ bạn xác nhận"
                f"{f': {text[:100]}' if text else '.'}",
            )
            try:
                dialog.page.bring_to_front()
            except Exception:
                pass

        target.on("dialog", show_dialog)
        try:
            target._wfx_dialog_handler = show_dialog
        except Exception:
            pass

    context = getattr(page, "context", None)
    pages = list(getattr(context, "pages", ()) or ()) if context else []
    for target in pages or [page]:
        attach_to(target)

    # Article Detail và các popup mở sau đó cũng phải giữ được alert.
    if context is not None:
        previous_page_handler = getattr(context, "_wfx_page_dialog_handler", None)
        if previous_page_handler is not None:
            try:
                context.remove_listener("page", previous_page_handler)
            except Exception:
                pass
        context.on("page", attach_to)
        try:
            context._wfx_page_dialog_handler = attach_to
        except Exception:
            pass


def automation_browser_pid() -> int | None:
    """PID đang listen CDP, dùng để panel bám đúng browser automation."""
    if os.name != "nt" or CDP_HOST not in {"127.0.0.1", "localhost", "::1"}:
        return None
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in completed.stdout.splitlines():
            columns = line.split()
            if len(columns) < 5 or columns[-2].upper() != "LISTENING":
                continue
            local_address = columns[1].strip("[]")
            if local_address.rsplit(":", 1)[-1] == str(CDP_PORT):
                pid = int(columns[-1])
                return pid if pid > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None
