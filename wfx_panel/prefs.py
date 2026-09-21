from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from wfx_panel import hotkey as hotkey_spec
from wfx_panel import secret
from wfx_panel.atomic_io import write_json_atomic, write_text_atomic
from wfx_panel.paths import (  # noqa: F401
    APP_DIR,
    DATA_DIR,
    RESOURCE_DIR,
    _catalog_cache_path,
    _costing_article_cache_path,
    _costing_special_options_cache_path,
    _env_path,
    _legacy_data_candidates,
    _migrate_legacy_files,
    _prefs_path,
    _resolve_data_dir,
)
from wfx_panel.stores.panel_cache import (  # noqa: F401
    _SPECIAL_COST_SECTION_KEYS,
    _normalise_catalog_folder,
    _normalise_catalog_tree_node,
    _normalise_costing_article_section,
    _normalise_costing_special_section,
    load_catalog_folder_cache,
    load_costing_article_cache,
    load_costing_special_options_cache,
    save_catalog_folder_cache,
    save_costing_article_cache,
    save_costing_special_options_cache,
)
from wfx_panel.version import APP_VERSION

# save_prefs là read-modify-write. Nó được gọi từ UI thread (Settings), từ
# automation worker (_refresh_admin_access, scan_catalog_folders) và từ thread
# poll cập nhật (_check_update_once). Không có khóa thì hai lần ghi song song
# mất một trong hai thay đổi (write_text_atomic chỉ chống hỏng file, không
# chống lost-update của chu trình đọc-sửa-ghi).
_WRITE_LOCK = threading.RLock()












class CredentialProtectionError(RuntimeError):
    """Không thể lưu credential an toàn bằng DPAPI trên Windows."""


































# Các key account do prefs quản lý; mọi dòng .env khác (webhook, key tuỳ biến)
# phải được giữ nguyên khi save_account ghi lại file.
_ACCOUNT_ENV_KEYS = frozenset(
    {"WFX_USER_ID", "WFX_PASSWORD", "WFX_PASSWORD_ENC"}
)
_SYNC_ADMIN_ENV_KEYS = frozenset(
    {"WFX_SYNC_ADMIN_KEY", "WFX_SYNC_ADMIN_KEY_ENC"}
)


def _parse_env_value(value: str) -> str:
    value = value.strip()
    try:
        return json.loads(value) if value.startswith('"') else value
    except json.JSONDecodeError:
        return value.strip('"')


def load_account(base_dir: Path | None = None) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _env_path(base_dir)
    values: dict[str, str] = {}
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        # Đọc tài khoản là bước đầu của get_initial_state. File bị khóa bởi
        # antivirus/sync hoặc quyền sai không được làm panel không mở lên nổi.
        raw_lines = []
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _parse_env_value(value)
    encrypted = values.get("WFX_PASSWORD_ENC", "")
    if encrypted:
        # Không giải được (DPAPI vắng mặt, đổi máy/user, blob hỏng) => coi như
        # chưa có mật khẩu để buộc người dùng nhập lại, không lộ token.
        decrypted = secret.unprotect(encrypted)
        password = decrypted if decrypted is not None else ""
    else:
        # Tương thích ngược: bản cũ và file migrate còn WFX_PASSWORD plaintext.
        password = values.get("WFX_PASSWORD", "")
        if password and os.name == "nt":
            # Đọc legacy lần đầu là thời điểm migration: ghi lại ngay bằng DPAPI
            # để plaintext không tiếp tục nằm trên đĩa tới lần người dùng Save.
            # Migration là tác dụng phụ của một lần ĐỌC: nếu DPAPI hoặc ổ đĩa
            # lỗi, vẫn phải trả về credential vừa đọc được thay vì ném lỗi ra
            # get_initial_state và làm panel trống trơn.
            try:
                save_account(
                    values.get("WFX_USER_ID", ""),
                    password,
                    base_dir=base_dir,
                )
            except (CredentialProtectionError, OSError):
                pass
    return {
        "user_id": values.get("WFX_USER_ID", ""),
        "password": password,
    }


def credential_status(base_dir: Path | None = None) -> str:
    """``ok`` | ``empty`` | ``unreadable``.

    ``unreadable`` là trường hợp riêng quan trọng: trên đĩa CÓ blob DPAPI
    nhưng tài khoản Windows/máy hiện tại không giải mã được (copy profile,
    đổi máy, đổi user). Nếu chỉ báo "chưa có mật khẩu" thì người dùng tưởng
    app quên dữ liệu của họ.
    """
    base_dir = DATA_DIR if base_dir is None else base_dir
    values = _env_values(Path(base_dir))
    encrypted = values.get("WFX_PASSWORD_ENC", "")
    if encrypted and secret.unprotect(encrypted) is None:
        return "unreadable"
    account = load_account(base_dir=base_dir)
    if account["user_id"].strip() and account["password"].strip():
        return "ok"
    return "empty"


def save_account(user_id: str, password: str, base_dir: Path | None = None) -> None:
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _env_path(base_dir)
    preserved: list[str] = []
    if path.is_file():
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                stripped = raw.strip()
                key = (
                    stripped.split("=", 1)[0].strip()
                    if "=" in stripped and not stripped.startswith("#")
                    else ""
                )
                if key in _ACCOUNT_ENV_KEYS:
                    continue
                preserved.append(raw)
        except OSError:
            preserved = []

    protected = secret.protect(password)
    if protected is not None:
        password_line = (
            f"WFX_PASSWORD_ENC={json.dumps(protected, ensure_ascii=False)}"
        )
    else:
        if os.name == "nt" and password:
            # Trên Windows không bao giờ hạ cấp im lặng từ DPAPI xuống plaintext.
            raise CredentialProtectionError(
                "Windows không mã hóa được mật khẩu bằng DPAPI; chưa lưu thay đổi."
            )
        # Hỗ trợ môi trường phát triển không phải Windows.
        password_line = (
            f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}"
        )
    lines = [
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}",
        password_line,
        *[line for line in preserved if line.strip()],
    ]
    with _WRITE_LOCK:
        write_text_atomic(path, "\n".join(lines) + "\n")
    # KHÔNG ghi mật khẩu vào os.environ. Chrome automation được khởi chạy như
    # tiến trình con nên nó kế thừa toàn bộ environment của panel, và trên
    # Windows mọi tiến trình cùng tài khoản đều đọc được environment của tiến
    # trình khác — làm vậy là vô hiệu hóa chính lớp DPAPI ở trên. Mọi flow đều
    # nhận credential qua tham số (panel_api.login/_restore_expired_session);
    # env chỉ còn là fallback đọc cho người chạy CLI tự đặt biến.
    os.environ.pop("WFX_PASSWORD", None)
    os.environ["WFX_USER_ID"] = user_id


def _env_values(base_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = _env_path(base_dir).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _parse_env_value(value)
    return values


def load_sync_admin_key(base_dir: Path | None = None) -> str:
    """Đọc admin key đã bảo vệ; không bao giờ đưa key vào prefs.json."""
    base_dir = DATA_DIR if base_dir is None else Path(base_dir)
    runtime = os.getenv("WFX_SYNC_ADMIN_KEY", "").strip()
    if runtime:
        return runtime
    values = _env_values(base_dir)
    encrypted = values.get("WFX_SYNC_ADMIN_KEY_ENC", "")
    if encrypted:
        return str(secret.unprotect(encrypted) or "").strip()
    return str(values.get("WFX_SYNC_ADMIN_KEY") or "").strip()


def save_sync_admin_key(value: str, base_dir: Path | None = None) -> bool:
    """Lưu admin key bằng DPAPI và giữ nguyên mọi cấu hình .env khác."""
    base_dir = DATA_DIR if base_dir is None else Path(base_dir)
    key_value = str(value or "").strip()
    path = _env_path(base_dir)
    preserved: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for raw in lines:
        stripped = raw.strip()
        key = (
            stripped.split("=", 1)[0].strip()
            if "=" in stripped and not stripped.startswith("#")
            else ""
        )
        if key not in _SYNC_ADMIN_ENV_KEYS:
            preserved.append(raw)
    if key_value:
        protected = secret.protect(key_value)
        if protected is not None:
            preserved.append(
                "WFX_SYNC_ADMIN_KEY_ENC="
                + json.dumps(protected, ensure_ascii=False)
            )
        elif os.name == "nt":
            raise CredentialProtectionError(
                "Windows không mã hóa được Admin key bằng DPAPI."
            )
        else:
            preserved.append(
                "WFX_SYNC_ADMIN_KEY="
                + json.dumps(key_value, ensure_ascii=False)
            )
    with _WRITE_LOCK:
        write_text_atomic(
            path,
            "\n".join(line for line in preserved if line.strip()) + "\n",
        )
    if key_value:
        os.environ["WFX_SYNC_ADMIN_KEY"] = key_value
    else:
        os.environ.pop("WFX_SYNC_ADMIN_KEY", None)
    return bool(key_value)


def load_prefs(base_dir: Path | None = None) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _prefs_path(base_dir)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    stored_hotkey = str(data.get("hotkey") or hotkey_spec.DEFAULT)
    if not hotkey_spec.is_valid(stored_hotkey):
        stored_hotkey = hotkey_spec.DEFAULT
    else:
        stored_hotkey = hotkey_spec.normalize(stored_hotkey)
    def optional_int(key: str) -> int | None:
        value = data.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    compact_offset_x = optional_int("compact_offset_x")
    compact_offset_y = optional_int("compact_offset_y")
    panel_offset_x = optional_int("panel_offset_x")
    panel_offset_y = optional_int("panel_offset_y")
    theme = data.get("theme")
    favorite_module_ids: list[str] = []
    stored_favorites = data.get("favorite_module_ids", [])
    if not isinstance(stored_favorites, list):
        stored_favorites = []
    for value in stored_favorites:
        module_id = str(value or "").strip()
        if module_id and module_id not in favorite_module_ids:
            favorite_module_ids.append(module_id)
        if len(favorite_module_ids) >= 50:
            break
    return {
        "theme": theme if theme in {"light", "dark", "system"} else "light",
        "favorite_module_ids": favorite_module_ids,
        "hotkey": stored_hotkey,
        "hotkey_label": hotkey_spec.format_label(stored_hotkey),
        # Mặc định bật cho cài đặt mới. Giá trị False đã được người dùng lưu
        # vẫn luôn được tôn trọng ở các lần chạy sau.
        "autostart": data.get("autostart", True) is not False,
        "start_hidden": data.get("start_hidden", False) is True,
        "toast_enabled": data.get("toast_enabled", True) is not False,
        "focus_chrome_on_module": data.get(
            "focus_chrome_on_module", True
        ) is not False,
        "always_on_top": data.get("always_on_top", True) is not False,
        "admin_mode": data.get("admin_mode", False) is True,
        "update_channel": (
            "current"
            if data.get("update_channel") == "current"
            else "stable"
        ),
        "last_update_notice": str(data.get("last_update_notice") or ""),
        # Cài mới ghi luôn phiên bản hiện tại nên người dùng mới không bị báo
        # tin của chính bản họ vừa cài. Chấm báo chỉ xuất hiện sau khi cập nhật.
        "manual_seen_version": str(
            data.get("manual_seen_version") or APP_VERSION
        ),
        "compact_offset_x": compact_offset_x,
        "compact_offset_y": compact_offset_y,
        "panel_offset_x": panel_offset_x,
        "panel_offset_y": panel_offset_y,
        "catalog_default_folder": _normalise_catalog_folder(
            data.get("catalog_default_folder")
        ),
        "costing_export_dir": str(
            data.get("costing_export_dir") or ""
        ).strip()[:32_000],
        "report_export_dir": str(
            data.get("report_export_dir") or ""
        ).strip()[:32_000],
        "sale_asn_import_dir": str(
            data.get("sale_asn_import_dir") or ""
        ).strip()[:32_000],
        "sale_asn_stages": _clean_sale_asn_stages(
            data.get("sale_asn_stages")
        ),
        "sale_asn_po_search_fields": _clean_sale_asn_po_search_fields(
            data.get("sale_asn_po_search_fields")
        ),
        # Tùy chọn mới áp dụng cho mọi workbook app tạo/tải. Kế thừa key
        # Costing cũ để không làm đổi lựa chọn của người dùng sau khi nâng cấp.
        "open_excel_file_after_download": data.get(
            "open_excel_file_after_download",
            data.get("open_costing_file_after_export", True),
        ) is not False,
        "open_costing_folder_after_export": data.get(
            "open_costing_folder_after_export", False
        ) is True,
        # One-shot: bật để lần Costing kế tiếp bỏ qua cache dropdown chi phí.
        # Controller tự tắt lại ngay sau một lần scan thành công.
        "costing_special_options_rescan": data.get(
            "costing_special_options_rescan", False
        ) is True,
        # User ID của lần đăng nhập WFX gần nhất do chính app thực hiện.
        # Phiên WFX trong Chrome sống lâu hơn app, nên phải nhớ xuyên phiên
        # thì lần mở app sau mới biết phiên đang mở là của ai. Không phải bí
        # mật: đây chỉ là tên đăng nhập, mật khẩu vẫn nằm trong .env đã mã hóa.
        "session_user_id": str(data.get("session_user_id") or "").strip()[:120],
    }


SALE_ASN_STAGES = ("po", "order_details", "style_details", "shipping_info")
SALE_ASN_PO_SEARCH_FIELDS = ("po", "style", "destination")


def _clean_sale_asn_stages(value: object) -> list[str]:
    """Giữ đúng thứ tự bước của flow; giá trị hỏng thì quay về đủ bốn bước."""
    if not isinstance(value, list):
        return list(SALE_ASN_STAGES)
    selected = {str(item or "").strip() for item in value}
    cleaned = [stage for stage in SALE_ASN_STAGES if stage in selected]
    # Không cho lưu trạng thái rỗng: user sẽ mở app ra mà không chạy được gì.
    return cleaned or list(SALE_ASN_STAGES)


def _clean_sale_asn_po_search_fields(value: object) -> list[str]:
    """Giữ thứ tự PO → Style → Destination và không cho cấu hình rỗng."""

    if not isinstance(value, list):
        return list(SALE_ASN_PO_SEARCH_FIELDS)
    selected = {str(item or "").strip() for item in value}
    cleaned = [field for field in SALE_ASN_PO_SEARCH_FIELDS if field in selected]
    return cleaned or list(SALE_ASN_PO_SEARCH_FIELDS)


def _clean_favorite_module_ids(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        module_id = str(value or "").strip()
        if not module_id or module_id in seen:
            continue
        seen.add(module_id)
        cleaned.append(module_id)
        if len(cleaned) >= 50:
            break
    return cleaned


def _apply_simple_preference_updates(
    current: dict,
    *,
    boolean_values: dict[str, bool | None],
    integer_values: dict[str, int | None],
) -> None:
    current.update(
        {
            key: bool(value)
            for key, value in boolean_values.items()
            if value is not None
        }
    )
    current.update(
        {
            key: int(value)
            for key, value in integer_values.items()
            if value is not None
        }
    )


def save_prefs(
    base_dir: Path | None = None,
    *,
    theme: str | None = None,
    favorite_module_ids: list[str] | None = None,
    hotkey_label: str | None = None,
    hotkey: str | None = None,
    autostart: bool | None = None,
    start_hidden: bool | None = None,
    toast_enabled: bool | None = None,
    focus_chrome_on_module: bool | None = None,
    always_on_top: bool | None = None,
    admin_mode: bool | None = None,
    update_channel: str | None = None,
    last_update_notice: str | None = None,
    manual_seen_version: str | None = None,
    compact_offset_x: int | None = None,
    compact_offset_y: int | None = None,
    panel_offset_x: int | None = None,
    panel_offset_y: int | None = None,
    catalog_default_folder: dict | None = None,
    costing_export_dir: str | None = None,
    report_export_dir: str | None = None,
    sale_asn_import_dir: str | None = None,
    sale_asn_stages: list[str] | None = None,
    sale_asn_po_search_fields: list[str] | None = None,
    open_excel_file_after_download: bool | None = None,
    open_costing_folder_after_export: bool | None = None,
    costing_special_options_rescan: bool | None = None,
    session_user_id: str | None = None,
) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    with _WRITE_LOCK:
        return _save_prefs_locked(
            base_dir,
            theme=theme,
            favorite_module_ids=favorite_module_ids,
            hotkey=hotkey,
            autostart=autostart,
            start_hidden=start_hidden,
            toast_enabled=toast_enabled,
            focus_chrome_on_module=focus_chrome_on_module,
            always_on_top=always_on_top,
            admin_mode=admin_mode,
            update_channel=update_channel,
            last_update_notice=last_update_notice,
            manual_seen_version=manual_seen_version,
            compact_offset_x=compact_offset_x,
            compact_offset_y=compact_offset_y,
            panel_offset_x=panel_offset_x,
            panel_offset_y=panel_offset_y,
            catalog_default_folder=catalog_default_folder,
            costing_export_dir=costing_export_dir,
            report_export_dir=report_export_dir,
            sale_asn_import_dir=sale_asn_import_dir,
            sale_asn_stages=sale_asn_stages,
            sale_asn_po_search_fields=sale_asn_po_search_fields,
            open_excel_file_after_download=open_excel_file_after_download,
            open_costing_folder_after_export=open_costing_folder_after_export,
            costing_special_options_rescan=costing_special_options_rescan,
            session_user_id=session_user_id,
            hotkey_label=hotkey_label,
        )


def _save_prefs_locked(
    base_dir: Path,
    *,
    theme: str | None,
    favorite_module_ids: list[str] | None,
    hotkey: str | None,
    autostart: bool | None,
    start_hidden: bool | None,
    toast_enabled: bool | None,
    focus_chrome_on_module: bool | None,
    always_on_top: bool | None,
    admin_mode: bool | None,
    update_channel: str | None,
    last_update_notice: str | None,
    manual_seen_version: str | None,
    compact_offset_x: int | None,
    compact_offset_y: int | None,
    panel_offset_x: int | None,
    panel_offset_y: int | None,
    catalog_default_folder: dict | None,
    costing_export_dir: str | None,
    report_export_dir: str | None,
    sale_asn_import_dir: str | None,
    sale_asn_stages: list[str] | None,
    sale_asn_po_search_fields: list[str] | None,
    open_excel_file_after_download: bool | None,
    open_costing_folder_after_export: bool | None,
    costing_special_options_rescan: bool | None,
    session_user_id: str | None,
    hotkey_label: str | None,
) -> dict:
    current = load_prefs(base_dir)
    _apply_simple_preference_updates(
        current,
        boolean_values={
            "autostart": autostart,
            "start_hidden": start_hidden,
            "toast_enabled": toast_enabled,
            "focus_chrome_on_module": focus_chrome_on_module,
            "always_on_top": always_on_top,
            "admin_mode": admin_mode,
            "open_excel_file_after_download": open_excel_file_after_download,
            "open_costing_folder_after_export": open_costing_folder_after_export,
            "costing_special_options_rescan": costing_special_options_rescan,
        },
        integer_values={
            "compact_offset_x": compact_offset_x,
            "compact_offset_y": compact_offset_y,
            "panel_offset_x": panel_offset_x,
            "panel_offset_y": panel_offset_y,
        },
    )
    if theme is not None:
        current["theme"] = theme if theme in {"light", "dark", "system"} else "light"
    if sale_asn_import_dir is not None:
        current["sale_asn_import_dir"] = str(sale_asn_import_dir).strip()[:32_000]
    if sale_asn_stages is not None:
        current["sale_asn_stages"] = _clean_sale_asn_stages(sale_asn_stages)
    if sale_asn_po_search_fields is not None:
        current["sale_asn_po_search_fields"] = _clean_sale_asn_po_search_fields(
            sale_asn_po_search_fields
        )
    if favorite_module_ids is not None:
        current["favorite_module_ids"] = _clean_favorite_module_ids(
            favorite_module_ids
        )
    if hotkey is not None:
        current["hotkey"] = hotkey_spec.normalize(hotkey)
        current["hotkey_label"] = hotkey_spec.format_label(current["hotkey"])
    if update_channel is not None:
        current["update_channel"] = (
            "current" if update_channel == "current" else "stable"
        )
    if last_update_notice is not None:
        current["last_update_notice"] = str(last_update_notice)
    if manual_seen_version is not None:
        current["manual_seen_version"] = str(manual_seen_version)
    if catalog_default_folder is not None:
        current["catalog_default_folder"] = _normalise_catalog_folder(
            catalog_default_folder
        )
    if costing_export_dir is not None:
        current["costing_export_dir"] = str(costing_export_dir).strip()[:32_000]
    if report_export_dir is not None:
        current["report_export_dir"] = str(report_export_dir).strip()[:32_000]
    if session_user_id is not None:
        current["session_user_id"] = str(session_user_id).strip()[:120]
    # Nhận tham số cũ để không phá caller, nhưng nhãn luôn được dẫn xuất từ
    # hotkey thật và không được ghi riêng xuống prefs.json.
    _ = hotkey_label

    payload = {key: value for key, value in current.items() if key != "hotkey_label"}
    write_json_atomic(_prefs_path(base_dir), payload, indent=2)
    return current
