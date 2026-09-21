"""Download native của Chrome và vòng đời driver/CDP của automation runtime.

CLAUDE.md đặt hai luật ở đây: Chrome tự quản file và lưu thẳng vào Known Folder
Downloads (không `downloadPath`, không artifact tạm), và runtime nhả driver/CDP
ngay khi flow xong để tab người dùng tự mở không bị auto-attach pause.
"""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from wfx_panel.automation import runtime


def _posix(monkeypatch):
    """Giả lập máy không phải Windows mà không đụng `os.name` toàn cục."""
    monkeypatch.setattr(
        runtime,
        "os",
        SimpleNamespace(name="posix", path=os.path, getenv=os.getenv),
    )


# --- thư mục Downloads --------------------------------------------------


def test_a_non_windows_machine_has_no_known_folder(monkeypatch):
    _posix(monkeypatch)

    assert runtime._windows_downloads_dir() is None


def test_a_registry_that_cannot_be_read_falls_back_instead_of_crashing(
    monkeypatch,
):
    import winreg

    def refuse(*_args, **_kwargs):
        raise OSError("không đọc được User Shell Folders")

    monkeypatch.setattr(winreg, "OpenKey", refuse)

    assert runtime._windows_downloads_dir() is None


def test_a_relative_registry_value_is_rejected_as_unusable(monkeypatch):
    import winreg

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(winreg, "OpenKey", lambda *_a, **_k: Key())
    monkeypatch.setattr(
        winreg, "QueryValueEx", lambda *_a: ("Downloads", 1)
    )

    assert runtime._windows_downloads_dir() is None


def test_the_registry_value_is_expanded_before_it_is_used(monkeypatch, tmp_path):
    import winreg

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setenv("WFX_TEST_DOWNLOADS", str(tmp_path))
    monkeypatch.setattr(winreg, "OpenKey", lambda *_a, **_k: Key())
    monkeypatch.setattr(
        winreg, "QueryValueEx", lambda *_a: ("%WFX_TEST_DOWNLOADS%", 2)
    )

    assert runtime._windows_downloads_dir() == tmp_path


def test_without_a_known_folder_the_user_profile_is_used(monkeypatch, tmp_path):
    _posix(monkeypatch)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert runtime._user_downloads_dir() == tmp_path / "Downloads"


def test_without_a_user_profile_the_home_directory_is_used(monkeypatch, tmp_path):
    _posix(monkeypatch)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    assert runtime._user_downloads_dir() == tmp_path / "Downloads"


# --- ảnh chụp thư mục ---------------------------------------------------


def test_a_downloads_folder_that_cannot_be_created_yields_an_empty_snapshot(
    monkeypatch, tmp_path
):
    target = tmp_path / "Downloads"
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: target)

    def refuse(*_args, **_kwargs):
        raise PermissionError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(Path, "mkdir", refuse)

    assert runtime.snapshot_downloads() == {}


def test_a_snapshot_records_size_and_mtime_of_every_regular_file(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)
    (tmp_path / "a.xlsx").write_text("abc", encoding="utf-8")
    (tmp_path / "sub").mkdir()

    snapshot = runtime.snapshot_downloads()

    assert list(snapshot) == [tmp_path / "a.xlsx"]
    assert snapshot[tmp_path / "a.xlsx"][0] == 3


def test_a_file_that_disappears_mid_scan_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)
    (tmp_path / "a.xlsx").write_text("abc", encoding="utf-8")
    real_stat = Path.stat

    def flaky(self, *args, **kwargs):
        if self.name == "a.xlsx":
            raise FileNotFoundError("file vừa bị xóa")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky)

    assert runtime.snapshot_downloads() == {}


def test_a_folder_that_becomes_unreadable_returns_what_was_read_so_far(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)

    def refuse(_self):
        raise PermissionError("không quét được thư mục")
        yield  # pragma: no cover - chỉ để hàm là generator

    monkeypatch.setattr(Path, "iterdir", refuse)

    assert runtime.snapshot_downloads() == {}


# --- nhận diện tên file Chrome đặt --------------------------------------


@pytest.mark.parametrize(
    ("name", "suggested", "matches"),
    [
        ("Report.xlsx", "Report.xlsx", True),
        ("report.XLSX", "Report.xlsx", True),
        ("Report (1).xlsx", "Report.xlsx", True),
        ("Report (12).xlsx", "Report.xlsx", True),
        # Chrome chỉ thêm số trong ngoặc; mọi hậu tố khác là file khác.
        ("Report (a).xlsx", "Report.xlsx", False),
        ("Report (1).csv", "Report.xlsx", False),
        ("Report copy.xlsx", "Report.xlsx", False),
        ("Other.xlsx", "Report.xlsx", False),
        ("Report (1)", "Report", True),
    ],
)
def test_chrome_deduplicated_names_are_recognised(name, suggested, matches):
    assert (
        runtime._matches_chrome_download_name(Path(name), suggested) is matches
    )


# --- tìm file vừa tải ---------------------------------------------------


def _downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)
    return tmp_path


def test_the_newest_matching_file_is_the_candidate(monkeypatch, tmp_path):
    _downloads(monkeypatch, tmp_path)
    older = tmp_path / "Report (1).xlsx"
    older.write_text("cu", encoding="utf-8")
    os.utime(older, ns=(1_000_000_000_000, 1_000_000_000_000))
    newer = tmp_path / "Report.xlsx"
    newer.write_text("moi", encoding="utf-8")
    os.utime(newer, ns=(2_000_000_000_000, 2_000_000_000_000))

    found = runtime.native_download_candidate(suggested_name="Report.xlsx")

    assert found is not None and found[0] == newer


def test_files_with_another_extension_are_filtered_out(monkeypatch, tmp_path):
    _downloads(monkeypatch, tmp_path)
    (tmp_path / "Report.csv").write_text("x", encoding="utf-8")

    assert (
        runtime.native_download_candidate(suffixes={".xlsx"}) is None
    )


def test_a_file_that_did_not_change_since_the_snapshot_is_not_the_download(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)
    existing = tmp_path / "Report.xlsx"
    existing.write_text("cu", encoding="utf-8")
    before = runtime.snapshot_downloads()

    assert runtime.native_download_candidate(before) is None


def test_a_directory_named_like_the_download_is_ignored(monkeypatch, tmp_path):
    _downloads(monkeypatch, tmp_path)
    (tmp_path / "Report.xlsx").mkdir()

    assert runtime.native_download_candidate(suggested_name="Report.xlsx") is None


def test_a_file_that_vanishes_while_being_measured_is_skipped(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)
    (tmp_path / "Report.xlsx").write_text("x", encoding="utf-8")
    real_stat = Path.stat

    def flaky(self, *args, **kwargs):
        if self.name == "Report.xlsx":
            raise FileNotFoundError("Chrome vừa đổi tên file tạm")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky)

    assert runtime.native_download_candidate() is None


def test_an_unreadable_downloads_folder_yields_no_candidate(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)

    def refuse(_self):
        raise PermissionError("không quét được thư mục")
        yield  # pragma: no cover - chỉ để hàm là generator

    monkeypatch.setattr(Path, "iterdir", refuse)

    assert runtime.native_download_candidate() is None


def test_waiting_for_a_download_that_never_arrives_names_the_file(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)

    with pytest.raises(FileNotFoundError, match="Report.xlsx"):
        runtime.wait_for_native_download(
            suggested_name="Report.xlsx", timeout=0.2
        )


def test_waiting_without_a_name_still_reports_something_readable(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)

    with pytest.raises(FileNotFoundError, match="file vừa tải"):
        runtime.wait_for_native_download(timeout=0.2)


def test_a_download_is_only_accepted_after_two_identical_observations(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)
    target = tmp_path / "Report.xlsx"
    target.write_text("x", encoding="utf-8")

    found = runtime.wait_for_native_download(
        suggested_name="Report.xlsx", timeout=5
    )

    assert found == target


# --- sao chép file về nơi flow cần --------------------------------------


class FakeDownload:
    def __init__(self, name="Report.xlsx"):
        self.suggested_filename = name


def test_saving_a_download_copies_it_without_moving_the_original(
    monkeypatch, tmp_path
):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    source = downloads / "Report.xlsx"
    source.write_text("excel", encoding="utf-8")
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: downloads)
    claimed: list[object] = []
    monkeypatch.setattr(runtime, "claim_download", claimed.append)
    target = tmp_path / "nghiep-vu" / "OC.xlsx"

    download = FakeDownload()
    saved = runtime.save_native_download(download, target)

    assert saved == target
    assert target.read_text(encoding="utf-8") == "excel"
    assert source.exists(), "file native phải ở lại Downloads cho Chrome"
    assert claimed == [download]


def test_saving_onto_the_download_itself_does_not_copy_a_file_over_itself(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "claim_download", lambda _download: None)
    source = tmp_path / "Report.xlsx"
    source.write_text("excel", encoding="utf-8")

    saved = runtime.save_native_download(FakeDownload(), source)

    assert saved.read_text(encoding="utf-8") == "excel"


def test_a_path_that_cannot_be_resolved_is_still_copied(monkeypatch, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "Report.xlsx").write_text("excel", encoding="utf-8")
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: downloads)
    monkeypatch.setattr(runtime, "claim_download", lambda _download: None)
    real_resolve = Path.resolve

    def flaky(self, *args, **kwargs):
        if self.name == "OC.xlsx":
            raise OSError("đường dẫn quá dài")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", flaky)
    target = tmp_path / "OC.xlsx"

    assert runtime.save_native_download(FakeDownload(), target) == target
    assert target.read_text(encoding="utf-8") == "excel"


# --- lease Playwright ---------------------------------------------------


def test_a_lease_forwards_everything_except_stop():
    playwright = SimpleNamespace(chromium="chromium-object", stop=lambda: 1 / 0)
    lease = runtime._PlaywrightLease(playwright)

    assert lease.chromium == "chromium-object"
    # Flow cũ vẫn gọi stop() mỗi lượt; runtime mới sở hữu lifecycle nên lời gọi
    # đó phải là no-op thay vì giết driver dùng chung.
    assert lease.stop() is None


# --- log và download chưa ai nhận --------------------------------------


def test_a_log_sink_that_throws_never_breaks_a_flow():
    engine = runtime.AutomationRuntime()

    def explode(_message):
        raise UnicodeEncodeError("utf-8", "x", 0, 1, "console cũ")

    engine.log_sink = explode

    engine._log("thử")


def test_nothing_is_logged_when_no_sink_is_attached():
    engine = runtime.AutomationRuntime()
    engine.log_sink = None

    engine._log("thử")


def test_download_tracking_skips_contexts_that_refuse_listeners():
    engine = runtime.AutomationRuntime()
    attached: list[str] = []

    class Context:
        def __init__(self, ok):
            self.ok = ok

        def on(self, event, _handler):
            if not self.ok:
                raise RuntimeError("context đã đóng")
            attached.append(event)

    browser = SimpleNamespace(contexts=[Context(False), Context(True)])

    engine._track_downloads(browser)
    engine._track_downloads(browser)

    assert attached == ["download"], "context đã gắn không được gắn lại"


def test_an_unclaimed_download_is_logged_at_its_native_path(monkeypatch, tmp_path):
    engine = runtime.AutomationRuntime()
    lines: list[str] = []
    engine.log_sink = lines.append
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)
    engine._on_download(FakeDownload("Report.xlsx"))

    engine._finish_unclaimed_downloads()

    assert str(tmp_path / "Report.xlsx") in lines[0]
    assert engine._unclaimed_downloads == []


def test_a_download_object_that_breaks_does_not_stop_the_others(
    monkeypatch, tmp_path
):
    engine = runtime.AutomationRuntime()
    lines: list[str] = []
    engine.log_sink = lines.append
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)

    class Broken:
        @property
        def suggested_filename(self):
            raise RuntimeError("target đã đóng")

    engine._on_download(Broken())
    engine._on_download(FakeDownload("Report.xlsx"))

    engine._finish_unclaimed_downloads()

    assert len(lines) == 1


def test_a_download_a_flow_claimed_is_not_logged_as_a_rescue(
    monkeypatch, tmp_path
):
    engine = runtime.AutomationRuntime()
    lines: list[str] = []
    engine.log_sink = lines.append
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: tmp_path)
    mine = FakeDownload("OC.xlsx")
    engine._on_download(mine)

    engine.claim_download(mine)
    engine.claim_download(FakeDownload("khong-co-trong-danh-sach.xlsx"))
    engine._finish_unclaimed_downloads()

    assert lines == []


# --- nhả driver sau mỗi flow -------------------------------------------


def test_releasing_asks_every_page_to_collect_garbage_then_drops_the_driver():
    engine = runtime.AutomationRuntime()
    collected: list[str] = []

    class Page:
        def __init__(self, name):
            self.name = name

        def request_gc(self):
            collected.append(self.name)

    engine._browser = SimpleNamespace(
        contexts=[SimpleNamespace(pages=[Page("a"), Page("b")])]
    )
    stopped: list[str] = []
    engine._playwright = SimpleNamespace(stop=lambda: stopped.append("stop"))

    engine._release_connections()

    assert collected == ["a", "b"]
    assert stopped == ["stop"]
    assert engine._browser is None
    assert engine._playwright is None


def test_releasing_survives_a_browser_that_is_already_gone():
    engine = runtime.AutomationRuntime()

    class DeadBrowser:
        @property
        def contexts(self):
            raise RuntimeError("Target closed")

    engine._browser = DeadBrowser()

    def explode():
        raise RuntimeError("driver đã chết")

    engine._playwright = SimpleNamespace(stop=explode)

    engine._release_connections()

    assert engine._browser is None
    assert engine._playwright is None


def test_releasing_survives_a_context_and_a_page_that_throw():
    engine = runtime.AutomationRuntime()

    class DeadContext:
        @property
        def pages(self):
            raise RuntimeError("context đã đóng")

    class DeadPage:
        def request_gc(self):
            raise RuntimeError("page đã đóng")

    engine._browser = SimpleNamespace(
        contexts=[DeadContext(), SimpleNamespace(pages=[DeadPage()])]
    )

    engine._release_connections()

    assert engine._browser is None


def test_releasing_survives_a_broken_download_rescue(monkeypatch):
    engine = runtime.AutomationRuntime()

    def explode():
        raise RuntimeError("Downloads không đọc được")

    monkeypatch.setattr(engine, "_finish_unclaimed_downloads", explode)

    engine._release_connections()


# --- hàng đợi tác vụ ----------------------------------------------------


def test_a_task_started_from_the_worker_itself_runs_inline():
    engine = runtime.AutomationRuntime()
    engine._thread_id = threading.get_ident()

    assert engine.execute(lambda: "ngay") == "ngay"


def test_a_task_whose_worker_vanished_is_revived_instead_of_hanging(monkeypatch):
    engine = runtime.AutomationRuntime()
    attempts: list[int] = []

    def ensure_thread():
        attempts.append(1)
        if len(attempts) >= 2:
            task = engine._queue.get_nowait()
            task.result = "worker mới đã chạy"
            task.done.set()

    monkeypatch.setattr(engine, "_ensure_thread", ensure_thread)

    assert engine.execute(lambda: "không bao giờ") == "worker mới đã chạy"
    assert len(attempts) >= 2


# --- vòng đời driver/CDP ------------------------------------------------


class FakeBrowser:
    def __init__(self, *, connected=True, session=None):
        self._connected = connected
        self.contexts: list = []
        self.session = session or SimpleNamespace(
            send=lambda *_a: None, detach=lambda: None
        )

    def is_connected(self):
        if self._connected is Ellipsis:
            raise RuntimeError("Target closed")
        return self._connected

    def new_browser_cdp_session(self):
        return self.session


class FakePlaywright:
    def __init__(self, browser):
        self.calls: list[dict] = []
        self.chromium = SimpleNamespace(connect_over_cdp=self._connect)
        self._browser = browser

    def _connect(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._browser


def test_a_helper_running_outside_the_worker_gets_its_own_driver(monkeypatch):
    engine = runtime.AutomationRuntime()
    started: list[str] = []
    monkeypatch.setattr(
        runtime,
        "_sync_playwright",
        lambda: SimpleNamespace(
            start=lambda: started.append("start") or "driver"
        ),
    )

    assert engine.playwright_start() == "driver"
    assert started == ["start"]
    assert engine._playwright is None, "driver rời không được runtime giữ"


def test_connecting_outside_the_worker_never_reuses_the_shared_browser():
    engine = runtime.AutomationRuntime()
    browser = FakeBrowser()
    playwright = FakePlaywright(browser)
    engine._browser = FakeBrowser()

    assert engine.connect_browser(playwright, "http://127.0.0.1:9222") is browser
    assert playwright.calls[0]["no_defaults"] is True
    assert playwright.calls[0]["timeout"] == runtime.CDP_CONNECT_TIMEOUT_MS


def test_connecting_reuses_the_shared_browser_while_it_is_alive():
    engine = runtime.AutomationRuntime()
    engine._thread_id = threading.get_ident()
    browser = FakeBrowser()
    engine._browser = browser
    playwright = FakePlaywright(FakeBrowser())

    assert engine.connect_browser(playwright, "http://127.0.0.1:9222") is browser
    assert playwright.calls == []


def test_a_browser_that_cannot_answer_is_replaced_not_reused():
    engine = runtime.AutomationRuntime()
    engine._thread_id = threading.get_ident()
    engine._browser = FakeBrowser(connected=Ellipsis)
    fresh = FakeBrowser()
    playwright = FakePlaywright(fresh)

    assert engine.connect_browser(playwright, "http://127.0.0.1:9222") is fresh
    assert engine._browser is fresh


def test_every_attach_resets_the_download_behaviour_to_chrome_default():
    engine = runtime.AutomationRuntime()
    sent: list[tuple] = []
    session = SimpleNamespace(
        send=lambda method, payload: sent.append((method, payload)),
        detach=lambda: sent.append(("detach", None)),
    )
    playwright = FakePlaywright(FakeBrowser(session=session))

    engine.connect_browser(playwright, "http://127.0.0.1:9222")

    assert sent[0] == (
        "Browser.setDownloadBehavior",
        {"behavior": "default"},
    )
    assert sent[1][0] == "detach"


def test_a_session_that_cannot_detach_does_not_fail_the_attach():
    engine = runtime.AutomationRuntime()

    def explode():
        raise RuntimeError("session đã mất")

    session = SimpleNamespace(send=lambda *_a: None, detach=explode)
    browser = FakeBrowser(session=session)

    engine._restore_native_download_behavior(browser)


def test_invalidating_only_drops_the_browser_the_caller_named():
    engine = runtime.AutomationRuntime()
    browser = FakeBrowser()
    engine._browser = browser

    engine.invalidate_browser(FakeBrowser())
    assert engine._browser is browser

    engine.invalidate_browser(browser)
    assert engine._browser is None


def test_recycling_outside_the_worker_stops_the_old_driver_and_starts_a_new_one(
    monkeypatch,
):
    engine = runtime.AutomationRuntime()
    monkeypatch.setattr(
        runtime,
        "_sync_playwright",
        lambda: SimpleNamespace(start=lambda: "driver-moi"),
    )
    stopped: list[str] = []

    assert engine.recycle_playwright(
        SimpleNamespace(stop=lambda: stopped.append("stop"))
    ) == "driver-moi"
    assert stopped == ["stop"]


def test_recycling_ignores_an_old_driver_that_cannot_be_stopped(monkeypatch):
    engine = runtime.AutomationRuntime()
    monkeypatch.setattr(
        runtime,
        "_sync_playwright",
        lambda: SimpleNamespace(start=lambda: "driver-moi"),
    )

    def explode():
        raise RuntimeError("driver đã chết")

    assert engine.recycle_playwright(
        SimpleNamespace(stop=explode)
    ) == "driver-moi"


# --- tắt máy ------------------------------------------------------------


def test_shutting_down_without_a_worker_does_nothing():
    engine = runtime.AutomationRuntime()

    engine.shutdown()

    assert engine._closed is True


def test_a_full_queue_leaves_the_worker_to_notice_the_cancel_flag():
    engine = runtime.AutomationRuntime()
    engine._thread = threading.current_thread()
    engine._queue.put_nowait(
        runtime._Task(action=lambda: None, done=threading.Event())
    )

    engine.shutdown(timeout=0.1)

    assert engine._queue.qsize() == 1
    with pytest.raises(queue.Empty):
        engine._queue.get_nowait()
        engine._queue.get_nowait()


# --- các hàm module -----------------------------------------------------


def test_the_module_level_helpers_all_go_through_the_shared_runtime(
    monkeypatch,
):
    calls: list[tuple] = []
    stub = SimpleNamespace(
        playwright_start=lambda: calls.append(("start",)) or "driver",
        connect_browser=(
            lambda playwright, url: calls.append(("connect", url)) or "browser"
        ),
        invalidate_browser=lambda browser: calls.append(("invalidate", browser)),
        claim_download=lambda download: calls.append(("claim", download)),
        recycle_playwright=(
            lambda playwright: calls.append(("recycle",)) or "driver-moi"
        ),
    )
    monkeypatch.setattr(runtime, "RUNTIME", stub)

    assert runtime.sync_playwright().start() == "driver"
    assert runtime.connect_browser(None, "http://127.0.0.1:9222") == "browser"
    runtime.invalidate_browser("b")
    runtime.claim_download("d")
    assert runtime.recycle_playwright("p") == "driver-moi"

    assert calls == [
        ("start",),
        ("connect", "http://127.0.0.1:9222"),
        ("invalidate", "b"),
        ("claim", "d"),
        ("recycle",),
    ]


def test_files_that_do_not_carry_the_suggested_name_are_skipped(
    monkeypatch, tmp_path
):
    _downloads(monkeypatch, tmp_path)
    other = tmp_path / "Packing List.xlsx"
    other.write_text("khac", encoding="utf-8")
    os.utime(other, ns=(9_000_000_000_000, 9_000_000_000_000))
    wanted = tmp_path / "Report.xlsx"
    wanted.write_text("dung", encoding="utf-8")
    os.utime(wanted, ns=(1_000_000_000_000, 1_000_000_000_000))

    found = runtime.native_download_candidate(suggested_name="Report.xlsx")

    # File kia mới hơn nhưng không phải file của lượt tải này.
    assert found is not None and found[0] == wanted


def test_a_slow_task_is_waited_on_while_its_worker_is_still_alive():
    engine = runtime.AutomationRuntime()
    try:
        assert engine.execute(lambda: _slow_action()) == "xong"
    finally:
        engine.shutdown(timeout=2)


def _slow_action():
    import time as _time

    _time.sleep(0.4)
    return "xong"


def test_a_task_finished_between_two_checks_is_not_queued_a_second_time(
    monkeypatch,
):
    engine = runtime.AutomationRuntime()

    class RacyEvent(threading.Event):
        """Worker hoàn tất đúng giữa `wait()` và `is_set()` của caller."""

        def wait(self, timeout=None):
            already = super().is_set()
            self.set()
            return already

    monkeypatch.setattr(
        runtime,
        "threading",
        SimpleNamespace(
            get_ident=threading.get_ident,
            Event=RacyEvent,
            Thread=threading.Thread,
        ),
    )
    monkeypatch.setattr(engine, "_ensure_thread", lambda: None)

    assert engine.execute(lambda: "không chạy") is None
    assert engine._queue.qsize() == 1
