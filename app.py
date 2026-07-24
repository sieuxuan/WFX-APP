from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

import login as wfx


APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"

MODULE_GROUPS = {
    "Module Operation": [
        ("Catalog", '//*[@id="0003_6200"]/a'),
        ("OC List", '//*[@id="0004_0050_0020"]/a'),
        ("Sample List", '//*[@id="0004_0056_4070"]/a'),
        ("Sale ASN", '//*[@id="0004_0070_0020"]/a'),
        ("RMPO List", '//*[@id="0005_0050_0020"]/a'),
        ("Indent List", '//*[@id="0005_0080_0020"]/a'),
        ("QA List", '//*[@id="0063_0030_0020"]/a'),
    ],
    "Module FA": [
        ("Advance PR List", '//*[@id="0065_0880_0010_0020"]/a'),
        ("Supplier Inv List", '//*[@id="0065_0880_0020_0020"]/a'),
        ("Expense Inv List", '//*[@id="0065_0880_0030_0020"]/a'),
    ],
    "Module Admin": [
        ("Org Structure", '//*[@id="0090_0001"]/a'),
        ("System Coding", '//*[@id="0090_0250"]/a'),
        ("Company Setup", '//*[@id="0090_0007"]/a'),
        ("Buyer List", '//*[@id="0004_0010_1720"]/a'),
        ("Supplier List", '//*[@id="0005_0010_1290"]/a'),
    ],
}

CATEGORIES = {
    "Apparel": "01",
    "Fixed Asset": "04",
    "Miscellaneous": "12",
    "Services": "06",
    "Textiles/Fabric": "03",
    "Trims": "05",
}


def _load_credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            try:
                values[key.strip()] = json.loads(value) if value.startswith('"') else value
            except json.JSONDecodeError:
                values[key.strip()] = value.strip('"')
    return (
        values.get("WFX_USER_ID", os.getenv("WFX_USER_ID", "")),
        values.get("WFX_PASSWORD", os.getenv("WFX_PASSWORD", "")),
    )


def _save_credentials(user_id: str, password: str) -> None:
    content = (
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}\n"
        f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}\n"
    )
    temp_path = ENV_PATH.with_suffix(".env.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(ENV_PATH)
    os.environ["WFX_USER_ID"] = user_id
    os.environ["WFX_PASSWORD"] = password


class WFXApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WFX Automation")
        self.root.geometry("1040x780")
        self.root.minsize(900, 690)

        self.logged_in = False
        self.busy = False
        self.catalog_ready = False
        self.module_buttons: list[ttk.Button] = []
        self.article_destination_buttons: list[ttk.Button] = []

        saved_user, saved_password = _load_credentials()
        self.user_var = tk.StringVar(value=saved_user)
        self.password_var = tk.StringVar(value=saved_password)
        self.account_var = tk.StringVar()
        self.category_var = tk.StringVar(value="Apparel")
        self.code_var = tk.StringVar()
        self.buyer_reference_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Đang kiểm tra phiên Chrome...")

        self._configure_style()
        self._build_ui()
        self._refresh_account_label()
        self.root.after(350, self.start_session_check)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=(10, 7))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        title_area = ttk.Frame(header)
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="WFX Automation", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_area, textvariable=self.account_var).pack(anchor="w", pady=(2, 0))
        self.settings_button = ttk.Button(header, text="Settings", command=self.open_settings)
        self.settings_button.pack(side="right", padx=(8, 0))
        self.login_button = ttk.Button(
            header,
            text="Kết nối / Login",
            command=self.start_login,
        )
        self.login_button.pack(side="right")

        modules = ttk.Frame(outer)
        modules.pack(fill="both", expand=True, pady=(14, 10))
        for column in range(3):
            modules.columnconfigure(column, weight=1)

        for column, (group_name, items) in enumerate(MODULE_GROUPS.items()):
            group = ttk.LabelFrame(modules, text=group_name, padding=10)
            group.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 5, 0),
            )
            group.columnconfigure(0, weight=1)
            for row, (module_name, xpath) in enumerate(items):
                button = ttk.Button(
                    group,
                    text=module_name,
                    state="disabled",
                    command=lambda name=module_name, path=xpath: self.start_module(name, path),
                )
                button.grid(row=row, column=0, sticky="ew", pady=3)
                self.module_buttons.append(button)

        catalog = ttk.LabelFrame(outer, text="Catalog Control", padding=10)
        catalog.pack(fill="x", pady=(0, 10))
        catalog.columnconfigure(1, weight=1)

        ttk.Label(catalog, text="Category").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.category_combo = ttk.Combobox(
            catalog,
            textvariable=self.category_var,
            values=list(CATEGORIES),
            state="disabled",
        )
        self.category_combo.grid(row=0, column=1, columnspan=4, sticky="ew")
        self.category_combo.bind("<<ComboboxSelected>>", self._category_changed)

        ttk.Label(catalog, text="Code").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=(8, 0),
        )
        self.code_entry = ttk.Entry(catalog, textvariable=self.code_var, state="disabled")
        self.code_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.code_entry.bind("<Return>", lambda _event: self.start_catalog_code())
        self.code_button = ttk.Button(
            catalog,
            text="Find Code",
            state="disabled",
            command=self.start_catalog_code,
        )
        self.code_button.grid(row=1, column=2, padx=(10, 0), pady=(8, 0))
        self.code_costsheet_button = ttk.Button(
            catalog,
            text="Costsheet",
            state="disabled",
            command=lambda: self.start_catalog_code("costsheet"),
        )
        self.code_costsheet_button.grid(row=1, column=3, padx=(6, 0), pady=(8, 0))
        self.code_bom_button = ttk.Button(
            catalog,
            text="BOM",
            state="disabled",
            command=lambda: self.start_catalog_code("bom"),
        )
        self.code_bom_button.grid(row=1, column=4, padx=(6, 0), pady=(8, 0))
        self.article_destination_buttons.extend(
            [self.code_costsheet_button, self.code_bom_button]
        )

        ttk.Label(catalog, text="Buyer Reference").grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=(8, 0),
        )
        self.buyer_reference_entry = ttk.Entry(
            catalog,
            textvariable=self.buyer_reference_var,
            state="disabled",
        )
        self.buyer_reference_entry.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        self.buyer_reference_entry.bind(
            "<Return>",
            lambda _event: self.start_buyer_reference(),
        )
        self.buyer_reference_button = ttk.Button(
            catalog,
            text="Find Buyer Ref",
            state="disabled",
            command=self.start_buyer_reference,
        )
        self.buyer_reference_button.grid(row=2, column=2, padx=(10, 0), pady=(8, 0))
        self.buyer_costsheet_button = ttk.Button(
            catalog,
            text="Costsheet",
            state="disabled",
            command=lambda: self.start_buyer_reference("costsheet"),
        )
        self.buyer_costsheet_button.grid(row=2, column=3, padx=(6, 0), pady=(8, 0))
        self.buyer_bom_button = ttk.Button(
            catalog,
            text="BOM",
            state="disabled",
            command=lambda: self.start_buyer_reference("bom"),
        )
        self.buyer_bom_button.grid(row=2, column=4, padx=(6, 0), pady=(8, 0))
        self.article_destination_buttons.extend(
            [self.buyer_costsheet_button, self.buyer_bom_button]
        )

        status = ttk.Frame(outer)
        status.pack(fill="x", pady=(0, 6))
        ttk.Label(status, text="Trạng thái:").pack(side="left")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(
            side="left", padx=(6, 0)
        )

        log_frame = ttk.LabelFrame(outer, text="Activity Log", padding=8)
        log_frame.pack(fill="both", expand=False)
        log_header = ttk.Frame(log_frame)
        log_header.pack(fill="x", pady=(0, 5))
        ttk.Label(log_header, text="Thời gian và chi tiết từng bước automation").pack(
            side="left"
        )
        ttk.Button(log_header, text="Xóa log", command=self._clear_log).pack(side="right")
        self.log_box = ScrolledText(
            log_frame,
            height=10,
            font=("Consolas", 9),
            state="disabled",
            wrap="word",
        )
        self.log_box.pack(fill="both")

        ttk.Label(outer, text="Đóng app không làm đóng Chrome automation.").pack(
            anchor="e", pady=(6, 0)
        )

    def _refresh_account_label(self) -> None:
        user_id = self.user_var.get().strip()
        self.account_var.set(
            f"Account: {user_id}" if user_id else "Account: chưa cấu hình — mở Settings"
        )

    def open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("WFX Settings")
        width, height = 440, 230
        self.root.update_idletasks()
        x = self.settings_button.winfo_rootx() + self.settings_button.winfo_width() - width
        y = self.settings_button.winfo_rooty() + self.settings_button.winfo_height() + 6
        x = max(0, min(x, window.winfo_screenwidth() - width))
        y = max(0, min(y, window.winfo_screenheight() - height - 40))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        window.lift()

        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Tài khoản WFX", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(frame, text="User ID").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        user_entry = ttk.Entry(frame, textvariable=self.user_var)
        user_entry.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Password").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="●")
        password_entry.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Thông tin được lưu cục bộ trong file .env.").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 12)
        )

        def save() -> None:
            user_id = self.user_var.get().strip()
            password = self.password_var.get()
            if not user_id or not password:
                self.status_var.set("Settings cần đủ User ID và Password")
                return
            _save_credentials(user_id, password)
            self._refresh_account_label()
            self._append_log("[SETTINGS] Đã lưu User ID/Password vào .env")
            self.status_var.set("Đã lưu Settings")
            window.destroy()

        ttk.Button(frame, text="Lưu Settings", command=save).grid(
            row=4, column=0, columnspan=2, sticky="e"
        )
        password_entry.bind("<Return>", lambda _event: save())
        (password_entry if self.user_var.get() else user_entry).focus_set()

    def _append_log(self, message: str) -> None:
        def update() -> None:
            if not self.root.winfo_exists():
                return
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.root.after(0, update)

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _category_changed(self, _event: tk.Event | None = None) -> None:
        # Category chỉ được áp dụng khi người dùng bấm một nút tìm kiếm.
        self._set_busy(self.busy)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.login_button.configure(state="disabled" if busy else "normal")
        module_state = "normal" if self.logged_in and not busy else "disabled"
        for button in self.module_buttons:
            button.configure(state=module_state)
        quick_search_enabled = not busy
        self.category_combo.configure(state="readonly" if quick_search_enabled else "disabled")
        self.code_entry.configure(state="normal" if quick_search_enabled else "disabled")
        self.code_button.configure(state="normal" if quick_search_enabled else "disabled")
        self.buyer_reference_entry.configure(
            state="normal" if quick_search_enabled else "disabled"
        )
        self.buyer_reference_button.configure(
            state="normal" if quick_search_enabled else "disabled"
        )
        destination_enabled = quick_search_enabled and self.category_var.get() == "Apparel"
        for button in self.article_destination_buttons:
            button.configure(state="normal" if destination_enabled else "disabled")

    def _run_background(
        self,
        operation: Callable[[], dict[str, Any]],
        finished: Callable[[dict[str, Any]], None],
    ) -> None:
        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:
                result = {
                    "ok": False,
                    "code": "APP_ERROR",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            self.root.after(0, lambda: finished(result))

        threading.Thread(target=worker, daemon=True).start()

    def start_session_check(self) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self._append_log("[SESSION] Đang kiểm tra phiên Chrome hiện tại...")
        self._run_background(
            lambda: wfx.check_session(self._append_log),
            self._session_check_finished,
        )

    def _session_check_finished(self, result: dict[str, Any]) -> None:
        self.logged_in = bool(result.get("ok"))
        self.status_var.set(str(result.get("message", "Hoàn tất")))
        self._append_log(str(result.get("message", "Hoàn tất")))
        self._set_busy(False)

    def start_login(self) -> None:
        if self.busy:
            return
        self.logged_in = False
        self.catalog_ready = False
        self._set_busy(True)
        self.status_var.set("Đang kết nối hoặc đăng nhập...")
        self._append_log("[LOGIN] Kiểm tra session trước khi đăng nhập")
        self._run_background(
            lambda: wfx.run(
                self.user_var.get().strip(),
                self.password_var.get(),
                wfx.COMPANY_ID,
                self._append_log,
            ),
            self._login_finished,
        )

    def _login_finished(self, result: dict[str, Any]) -> None:
        self.logged_in = bool(result.get("ok"))
        self.status_var.set(str(result.get("message", "Hoàn tất")))
        self._append_log(str(result.get("message", "Hoàn tất")))
        self._set_busy(False)
        if result.get("code") == "MISSING_CREDENTIALS":
            self.open_settings()

    def start_module(self, module_name: str, xpath: str) -> None:
        if self.busy or not self.logged_in:
            return
        self._set_busy(True)
        self.status_var.set(f"Đang mở {module_name}...")
        self._append_log(
            "Yêu cầu mở Catalog → Master → Floating Filter"
            if module_name == "Catalog"
            else f"Yêu cầu mở {module_name}"
        )
        self._run_background(
            lambda: wfx.open_module(module_name, xpath, self._append_log),
            lambda result: self._module_finished(module_name, result),
        )

    def _module_finished(self, module_name: str, result: dict[str, Any]) -> None:
        if result.get("code") in {"NOT_LOGGED_IN", "CHROME_CLOSED"}:
            self.logged_in = False
        if result.get("ok"):
            self.catalog_ready = module_name == "Catalog"
        self.status_var.set(str(result.get("message", "Hoàn tất")))
        self._append_log(str(result.get("message", "Hoàn tất")))
        self._set_busy(False)

    def start_catalog_category(self, _event: tk.Event | None = None) -> None:
        if self.busy or not self.catalog_ready:
            return
        category_name = self.category_var.get()
        self._set_busy(True)
        self.status_var.set(f"Đang chọn {category_name} và mở Master...")
        self._append_log(f"Yêu cầu Category: {category_name} → Master → Floating Filter")
        self._run_background(
            lambda: wfx.set_catalog_category(
                category_name,
                CATEGORIES[category_name],
                self._append_log,
            ),
            self._catalog_action_finished,
        )

    def start_catalog_code(self, destination: str | None = None) -> None:
        if self.busy:
            return
        article_code = self.code_var.get().strip()
        if not article_code:
            self.status_var.set("Vui lòng nhập Code")
            return
        self._set_busy(True)
        destination_label = {"costsheet": "Costsheet", "bom": "BOM"}.get(destination)
        self.status_var.set(
            f"Đang tìm {article_code}"
            + (f" và mở {destination_label}..." if destination_label else "...")
        )
        self._append_log(
            f"[QUICK SEARCH] Category={self.category_var.get()} | Code={article_code}"
            + (f" | Đích={destination_label}" if destination_label else "")
        )
        self._run_background(
            lambda: wfx.quick_find_catalog(
                self.category_var.get(),
                CATEGORIES[self.category_var.get()],
                "code",
                article_code,
                self.user_var.get(),
                self.password_var.get(),
                wfx.COMPANY_ID,
                self._append_log,
                destination=destination,
            ),
            self._catalog_action_finished,
        )

    def start_buyer_reference(self, destination: str | None = None) -> None:
        if self.busy:
            return
        buyer_reference = self.buyer_reference_var.get().strip()
        if not buyer_reference:
            self.status_var.set("Vui lòng nhập Buyer Reference")
            return
        self._set_busy(True)
        destination_label = {"costsheet": "Costsheet", "bom": "BOM"}.get(destination)
        self.status_var.set(
            f"Đang tìm Buyer Reference: {buyer_reference}"
            + (f" và mở {destination_label}..." if destination_label else "...")
        )
        self._append_log(
            f"[QUICK SEARCH] Category={self.category_var.get()} | "
            f"Buyer Reference={buyer_reference}"
            + (f" | Đích={destination_label}" if destination_label else "")
        )
        self._run_background(
            lambda: wfx.quick_find_catalog(
                self.category_var.get(),
                CATEGORIES[self.category_var.get()],
                "buyer_reference",
                buyer_reference,
                self.user_var.get(),
                self.password_var.get(),
                wfx.COMPANY_ID,
                self._append_log,
                destination=destination,
            ),
            self._catalog_action_finished,
        )

    def _catalog_action_finished(self, result: dict[str, Any]) -> None:
        if result.get("session_active"):
            self.logged_in = True
            self.catalog_ready = True
        if result.get("code") in {"CATALOG_NOT_OPEN", "CHROME_CLOSED"}:
            self.catalog_ready = False
        self.status_var.set(str(result.get("message", "Hoàn tất")))
        self._append_log(str(result.get("message", "Hoàn tất")))
        self._set_busy(False)
        if result.get("code") == "MISSING_CREDENTIALS":
            self.open_settings()


def main() -> None:
    root = tk.Tk()
    WFXApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
