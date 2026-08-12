# Native Chrome Downloads 1.0.31 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bảo đảm download WFX thông thường luôn đi vào Windows Known Folder Downloads với Chrome history mở được file/thư mục, trong khi các module Save As vẫn giữ target người dùng chọn, rồi phát hành WFX Smart 1.0.31.

**Architecture:** `wfx_panel.automation.runtime` là nguồn duy nhất resolve Downloads và là ranh giới CDP duy nhất. Runtime dùng Windows Known Folder thay vì preference stale, giữ `no_defaults=True`, rồi reset browser-wide download behavior về `default` sau mỗi CDP attach; các flow Save As tiếp tục copy hoặc ghi trực tiếp vào target riêng hiện có.

**Tech Stack:** Python 3.11+, Playwright 1.61 CDP, pytest, Ruff, PyInstaller, Inno Setup, GitHub CLI/Release.

## Global Constraints

- Download mặc định phải dùng Windows Known Folder Downloads, kể cả redirect/OneDrive.
- Không dùng `Browser.setDownloadBehavior` với `allow`, `allowAndName`, `deny` hoặc `downloadPath`.
- Mọi `connect_over_cdp` production phải truyền `no_defaults=True`.
- Module có Save As phải giữ nguyên đường dẫn người dùng chọn.
- Chỉ sửa nguồn trong `wfx_panel/`; không sửa trực tiếp `dist/`.
- Nội dung người dùng là tiếng Việt Unicode NFC.
- Phiên bản phát hành là `1.0.31`; release phải có Setup và portable ZIP.

---

### Task 1: Khóa đường dẫn Downloads chuẩn và reset CDP

**Files:**
- Modify: `tests/test_automation_runtime.py`
- Modify: `wfx_panel/automation/runtime.py`
- Test: `tests/test_automation_runtime.py`

**Interfaces:**
- Consumes: `_windows_downloads_dir() -> Path | None`, `AutomationRuntime.connect_browser(playwright, cdp_url) -> Browser`.
- Produces: `_user_downloads_dir() -> Path` ưu tiên Known Folder; `AutomationRuntime._restore_native_download_behavior(browser) -> None` gửi CDP command `Browser.setDownloadBehavior` với `{"behavior": "default"}`.

- [ ] **Step 1: Viết test đỏ cho Known Folder thắng preference stale**

```python
def test_download_dir_prefers_windows_known_folder_over_stale_profile(...):
    monkeypatch.setattr(runtime, "_windows_downloads_dir", lambda: known)
    monkeypatch.setattr(runtime, "_profile_downloads_dir", lambda: stale)
    assert runtime._user_downloads_dir() == known
```

- [ ] **Step 2: Viết test đỏ cho reset behavior sau attach và reuse trong flow**

```python
class FakeCdpSession:
    def send(self, method, params=None):
        self.calls.append((method, params))

def test_cdp_attach_restores_chrome_native_download_behavior():
    first = worker.connect_browser(playwright, CDP_URL)
    second = worker.connect_browser(playwright, CDP_URL)
    assert first is second
    assert browser.session.calls == [
        ("Browser.setDownloadBehavior", {"behavior": "default"})
    ]
```

- [ ] **Step 3: Chạy test đích và xác nhận RED đúng nguyên nhân**

Run: `python -m pytest tests/test_automation_runtime.py -q`

Expected: test Known Folder nhận preference stale; test CDP thiếu session call.

- [ ] **Step 4: Cài đặt tối thiểu trong runtime**

```python
def _user_downloads_dir() -> Path:
    known_folder = _windows_downloads_dir()
    if known_folder is not None:
        return known_folder
    profile = os.getenv("USERPROFILE") or str(Path.home())
    return Path(profile) / "Downloads"

def _restore_native_download_behavior(self, browser: Browser) -> None:
    session = browser.new_browser_cdp_session()
    session.send("Browser.setDownloadBehavior", {"behavior": "default"})
    session.detach()
```

Gọi helper đúng một lần ngay sau mỗi `connect_over_cdp` mới; không gọi lại khi trả browser cache trong cùng flow. Nếu send thất bại, để exception xuyên lên để flow không tiếp tục với download mode không xác định; `detach()` chạy trong `finally` và lỗi detach không che lỗi chính.

- [ ] **Step 5: Chạy test runtime và toàn bộ test liên quan download**

Run: `python -m pytest tests/test_automation_runtime.py tests/test_login_helpers.py tests/test_reports.py tests/test_panel_app.py -q`

Expected: PASS.

- [ ] **Step 6: Commit task**

```powershell
git add wfx_panel/automation/runtime.py tests/test_automation_runtime.py
git commit -m "fix: restore native Chrome downloads on CDP attach"
```

### Task 2: Đồng bộ profile Chrome và bảo vệ Save As

**Files:**
- Modify: `tests/test_login_helpers.py`
- Modify: `wfx_panel/automation/browser.py` only if tests reveal profile sync is incomplete
- Test: `tests/test_login_helpers.py`
- Test: `tests/test_panel_app.py`

**Interfaces:**
- Consumes: `_user_downloads_dir() -> Path`, `_disable_password_manager(profile_dir: Path) -> None`.
- Produces: profile `download.default_directory` luôn bằng Known Folder ở lần launch; các result `export_path`/`download_path` riêng vẫn được `_handle_downloaded_excel()` mở đúng target.

- [ ] **Step 1: Viết test đỏ cho profile stale được ghi đè về Known Folder**

```python
def test_automation_profile_replaces_stale_download_directory(...):
    preferences.write_text(json.dumps({
        "download": {"default_directory": str(stale)}
    }))
    monkeypatch.setattr(browser, "_user_downloads_dir", lambda: known)
    browser._disable_password_manager(profile)
    assert json.loads(preferences.read_text())["download"] == {
        "default_directory": str(known),
        "directory_upgrade": True,
        "prompt_for_download": False,
    }
```

- [ ] **Step 2: Chạy test và xác nhận RED nếu hành vi chưa được phủ**

Run: `python -m pytest tests/test_login_helpers.py::test_automation_profile_replaces_stale_download_directory -q`

Expected: FAIL nếu profile không thay stale; nếu implementation hiện có đã đúng, điều chỉnh test để kiểm chứng integration Known Folder thật qua runtime thay vì trùng assertion cũ.

- [ ] **Step 3: Cài đặt phần profile tối thiểu nếu cần**

Giữ `_disable_password_manager()` ghi nguyên ba key download hiện tại nhưng lấy target độc quyền từ `_user_downloads_dir()`. Không thêm Save As hoặc download path override ở browser launch.

- [ ] **Step 4: Chạy test Save As/open target hồi quy**

Run: `python -m pytest tests/test_login_helpers.py tests/test_panel_app.py -q`

Expected: các test `export_path`/`download_path` tiếp tục PASS và đúng target riêng.

- [ ] **Step 5: Quét tĩnh code production**

Run: `rg -n "setDownloadBehavior|allowAndName|playwright-artifacts|connect_over_cdp" wfx_panel`

Expected: chỉ helper reset dùng `setDownloadBehavior` với `default`; mọi attach nằm ở runtime và dùng `no_defaults=True`; `playwright-artifacts` không xuất hiện trong code sản phẩm.

- [ ] **Step 6: Commit task nếu có thay đổi ngoài Task 1**

```powershell
git add wfx_panel/automation/browser.py tests/test_login_helpers.py tests/test_panel_app.py
git commit -m "test: protect Chrome profile and Save As downloads"
```

### Task 3: Tài liệu và phiên bản 1.0.31

**Files:**
- Modify: `CLAUDE.md`
- Modify: `wfx_panel/manual/01-bat-dau/mo-trinh-duyet.md`
- Modify: `wfx_panel/manual/whats_new.json`
- Generate: `docs/USER_FEATURES.md`
- Modify: `wfx_panel/version.py`
- Modify: `wfx_panel/version_info.txt`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `tests/test_version.py`
- Test: `tests/test_manual.py`
- Test: `tests/test_version.py`

**Interfaces:**
- Consumes: `APP_VERSION`, manual manifest/current-release validation.
- Produces: mọi metadata public là `1.0.31`; hướng dẫn nêu Downloads mặc định và ngoại lệ Save As.

- [ ] **Step 1: Đổi test version sang 1.0.31 để tạo RED**

```python
def test_public_version_is_1_0_31():
    assert APP_VERSION == "1.0.31"
    assert DISPLAY_VERSION == "1.0.31"
    assert RELEASE_TAG == "v1.0.31"
```

- [ ] **Step 2: Chạy test version và xác nhận RED**

Run: `python -m pytest tests/test_version.py -q`

Expected: FAIL vì source còn `1.0.30`.

- [ ] **Step 3: Bump toàn bộ metadata và cập nhật nội dung**

Đổi `version.py`, `version_info.txt`, `pyproject.toml`, tiêu đề/link artifact README và test sang `1.0.31`. Thêm mục đầu `whats_new.json` ngày `2026-08-12` với nội dung: download thường vào Downloads chuẩn; Chrome history mở file/thư mục được; Save As không đổi. Cập nhật `CLAUDE.md` và trang mở trình duyệt cùng quy tắc.

- [ ] **Step 4: Sinh lại tài liệu người dùng**

Run: `python scripts/generate_user_features.py`

Expected: `docs/USER_FEATURES.md` cập nhật từ manual source.

- [ ] **Step 5: Chạy test version/manual**

Run: `python -m pytest tests/test_version.py tests/test_manual.py -q`

Expected: PASS.

- [ ] **Step 6: Commit task**

```powershell
git add CLAUDE.md README.md pyproject.toml docs/USER_FEATURES.md tests/test_version.py wfx_panel/version.py wfx_panel/version_info.txt wfx_panel/manual
git commit -m "release: prepare WFX Smart 1.0.31"
```

### Task 4: Xác minh toàn diện và live smoke test

**Files:**
- No planned source changes; fix only regressions proven by verification.

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: evidence tests/lint pass and live Chrome connection is reset to native download mode.

- [ ] **Step 1: Chạy toàn bộ pytest**

Run: `python -m pytest`

Expected: PASS, zero failures.

- [ ] **Step 2: Chạy Ruff**

Run: `ruff check .`

Expected: `All checks passed!`.

- [ ] **Step 3: Chạy live attach không điều hướng WFX**

Run một script read-only dùng runtime attach vào `http://127.0.0.1:9222`, xác nhận connect thành công và helper reset không raise. Không click download thật hoặc thay dữ liệu WFX.

- [ ] **Step 4: Lập inventory và kiểm tra lại mọi flow download**

Run:

```powershell
rg -n "expect_download|save_native_download|wait_for_native_download|download_path|export_path|save_as|asksaveasfilename" wfx_panel tests
python -m pytest tests/test_automation_runtime.py tests/test_reports.py tests/test_color_combination.py tests/test_sale_asn_documents.py tests/test_panel_app.py tests/test_login_helpers.py tests/test_dispatch.py -q
```

Đối chiếu từng nhóm Catalog attachment, Reports/Color Combination, GDN report,
Sale ASN Invoice + PKL và mọi export/template có Save As. Download native phải
về Known Folder; Save As phải giữ target riêng; flow cần file vừa tải phải
snapshot rồi copy, không đọc artifact Playwright. Nếu tên test trong repo khác,
dùng inventory để chọn đúng test file hiện có và ghi lại lệnh thực tế.

- [ ] **Step 5: Kiểm tra Chrome profile sau đồng bộ**

Đọc `Default/Preferences` và Windows Known Folder, xác nhận hai đường dẫn trùng nhau; không in cookie, SessionID hoặc URL nhạy cảm.

- [ ] **Step 6: Kiểm tra diff và commit fix verification nếu phát sinh**

Run: `git diff --check` và `git status --short`.

Expected: chỉ thay đổi đúng scope; không có artifact build được stage.

### Task 5: Build và phát hành v1.0.31

**Files:**
- Generated, untracked/ignored: `dist/WFX-Panel/`, `dist/installer/`, portable ZIP.
- Modify only if release automation requires it: no source file planned.

**Interfaces:**
- Consumes: clean, verified source at version `1.0.31`.
- Produces: `WFX-Smart-Setup-v1.0.31.exe`, `WFX-Smart-v1.0.31-win64.zip`, Git tag/release `v1.0.31`.

- [ ] **Step 1: Build portable panel**

Run: `powershell -ExecutionPolicy Bypass -File .\build-panel.ps1`

Expected: `dist/WFX-Panel/WFX-Panel.exe` exists and embeds ProductVersion 1.0.31.

- [ ] **Step 2: Build installer và portable ZIP bằng release script chuẩn**

Run: `powershell -ExecutionPolicy Bypass -File .\build-installer.ps1`

Expected: Setup 1.0.31 exists; if script does not create ZIP, package `dist/WFX-Panel` under exact portable asset name used by `.github/workflows/release.yml`.

- [ ] **Step 3: Kiểm tra tên, hash và version artifact**

Run PowerShell `Get-Item`, `Get-FileHash -Algorithm SHA256` và FileVersionInfo cho hai asset; xác nhận file không rỗng và version đúng.

- [ ] **Step 4: Kiểm tra Git/GitHub trước mutation**

Run: `git status --short`, `git log -3 --oneline`, `git remote -v`, `gh auth status`, `gh release view v1.0.31`.

Expected: worktree sạch, auth hợp lệ, tag/release chưa tồn tại.

- [ ] **Step 5: Push commit, tạo tag và phát hành asset**

Run: `git push origin main`, tạo/push annotated tag `v1.0.31`, rồi `gh release create v1.0.31 <setup> <zip> --title "WFX Smart 1.0.31" --notes-from-tag` hoặc dùng workflow release chuẩn nếu repo quy định tag trigger.

Expected: remote main và tag cập nhật; GitHub Release có đúng hai asset.

- [ ] **Step 6: Xác minh release từ GitHub**

Run: `gh release view v1.0.31 --json tagName,isDraft,isPrerelease,assets,url`.

Expected: public release, không draft/prerelease, đúng Setup + portable ZIP và kích thước > 0.
