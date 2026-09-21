"""Cây folder Catalog và vị trí Apparel mặc định.

CLAUDE.md: vị trí Apparel mặc định được chỉnh bằng nút icon nhỏ cạnh `Mở
Catalog`; cache cây folder khóa theo User ID, và khi User ID đổi thì cache đó
phải bị hạ ngay chứ không được phục vụ cây của người khác.
"""

from __future__ import annotations

import pytest

from tests.test_panel_api import FakeLogin, make_api
from wfx_panel import constants


@pytest.fixture
def api(tmp_path):
    instance, _fake = make_api(tmp_path)
    return instance


@pytest.fixture
def folders(api):
    return api._catalog.folders


def _folder(node_id="12", name="Jacket"):
    return {
        "node_id": node_id,
        "node_code": f"G{node_id}",
        "name": name,
        "path": ["Master", name],
        "path_label": f"Master / {name}",
        "kind": "folder",
        "depth": 2,
    }


def _scanner(monkeypatch, api, folders_payload, code="CATALOG_FOLDERS_SCANNED"):
    monkeypatch.setattr(
        api._login,
        "scan_catalog_folders",
        lambda _name, _value, _log: {
            "ok": True,
            "code": code,
            "message": "Đã quét cây Catalog.",
            "folders": list(folders_payload),
        },
        raising=False,
    )


# --- chỉ Apparel ---------------------------------------------------------


def test_scanning_folders_for_another_category_is_refused(api):
    result = api.scan_catalog_folders("Trims")

    assert result["code"] == "CATALOG_DEFAULT_APPAREL_ONLY"


def test_setting_a_default_folder_for_another_category_is_refused(api):
    result = api.set_catalog_default_folder("Trims", "12")

    assert result["code"] == "CATALOG_DEFAULT_APPAREL_ONLY"


# --- bản automation cũ ---------------------------------------------------


def test_an_automation_build_that_cannot_scan_folders_says_so(
    tmp_path, monkeypatch
):
    class NoScanner(FakeLogin):
        scan_catalog_folders = None

    from wfx_panel import prefs
    from wfx_panel.panel_api import PanelAPI

    api = PanelAPI(
        login_module=NoScanner(), prefs_module=prefs, base_dir=tmp_path
    )

    result = api.scan_catalog_folders("Apparel")

    assert result["code"] == "CATALOG_FOLDER_SCAN_UNSUPPORTED"


# --- cache ---------------------------------------------------------------


def test_a_second_scan_reuses_the_tree_already_saved(api, monkeypatch):
    _scanner(monkeypatch, api, [_folder()])
    api._account = lambda: {"user_id": "tester", "password": "x"}
    first = api.scan_catalog_folders("Apparel")
    assert first["code"] == "CATALOG_FOLDERS_SCANNED"

    monkeypatch.setattr(
        api._login,
        "scan_catalog_folders",
        lambda *_a: pytest.fail("đã có cache thì không được quét lại WFX"),
        raising=False,
    )

    second = api.scan_catalog_folders("Apparel")

    assert second["code"] == "CATALOG_FOLDERS_CACHED"
    assert second["value"] == constants.CATEGORIES["Apparel"]
    assert [item["node_id"] for item in second["folders"]] == ["12"]


def test_forcing_a_scan_ignores_the_cache(api, monkeypatch):
    api._account = lambda: {"user_id": "tester", "password": "x"}
    _scanner(monkeypatch, api, [_folder()])
    api.scan_catalog_folders("Apparel")
    _scanner(monkeypatch, api, [_folder("13", "Pant")])

    result = api.scan_catalog_folders("Apparel", True)

    assert [item["node_id"] for item in result["folders"]] == ["13"]


def test_nodes_wfx_returned_without_a_numeric_id_are_dropped(api, monkeypatch):
    api._account = lambda: {"user_id": "tester", "password": "x"}
    _scanner(monkeypatch, api, [_folder(), {"node_id": "abc"}, "hỏng"])

    result = api.scan_catalog_folders("Apparel")

    assert [item["node_id"] for item in result["folders"]] == ["12"]


def test_a_disk_that_cannot_save_the_tree_does_not_fail_the_scan(
    api, monkeypatch
):
    api._account = lambda: {"user_id": "tester", "password": "x"}
    _scanner(monkeypatch, api, [_folder()])

    def refuse(*_args, **_kwargs):
        raise OSError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(api._prefs, "save_catalog_folder_cache", refuse)

    result = api.scan_catalog_folders("Apparel")

    assert result["code"] == "CATALOG_FOLDERS_SCANNED"


def test_an_old_prefs_module_without_a_folder_cache_still_scans(
    api, monkeypatch
):
    api._account = lambda: {"user_id": "tester", "password": "x"}
    monkeypatch.setattr(
        api._prefs, "load_catalog_folder_cache", None, raising=False
    )
    monkeypatch.setattr(
        api._prefs, "save_catalog_folder_cache", None, raising=False
    )
    _scanner(monkeypatch, api, [_folder()])

    assert api.scan_catalog_folders("Apparel")["code"] == (
        "CATALOG_FOLDERS_SCANNED"
    )


# --- đổi tài khoản giữa lúc quét -----------------------------------------


def test_a_tree_scanned_for_another_account_is_never_shown(api, monkeypatch):
    # Người dùng bấm `Đổi tài khoản` ngay giữa lượt quét: lượt quét này thuộc
    # về tài khoản cũ nên không được hiển thị cho tài khoản mới.
    switched = {"yes": False}

    def account():
        user_id = "nguoi-khac" if switched["yes"] else "tester"
        return {"user_id": user_id, "password": "x"}

    def scan(_name, _value, _log):
        switched["yes"] = True
        return {
            "ok": True,
            "code": "CATALOG_FOLDERS_SCANNED",
            "message": "Đã quét cây Catalog.",
            "folders": [_folder()],
        }

    api._account = account
    monkeypatch.setattr(api._login, "scan_catalog_folders", scan, raising=False)

    result = api.scan_catalog_folders("Apparel")

    assert result["code"] == "CATALOG_SCAN_ACCOUNT_CHANGED"
    assert result["ok"] is False


# --- vị trí mặc định không còn quyền xem ---------------------------------


def test_a_default_folder_the_user_lost_access_to_falls_back_to_master(
    api, monkeypatch
):
    api._account = lambda: {"user_id": "tester", "password": "x"}
    _scanner(monkeypatch, api, [_folder()])
    api.scan_catalog_folders("Apparel")
    assert api.set_catalog_default_folder("Apparel", "12")["ok"]

    _scanner(monkeypatch, api, [_folder("13", "Pant")])

    result = api.scan_catalog_folders("Apparel", True)

    assert result["default_folder"]["kind"] == "master"
    assert "đã chuyển về Master" in result["message"]


def test_a_default_folder_the_user_still_sees_is_kept(api, monkeypatch):
    api._account = lambda: {"user_id": "tester", "password": "x"}
    _scanner(monkeypatch, api, [_folder()])
    api.scan_catalog_folders("Apparel")
    api.set_catalog_default_folder("Apparel", "12")

    result = api.scan_catalog_folders("Apparel", True)

    assert result["default_folder"]["node_id"] == "12"
