from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls = []

    def run(self, user_id, password, company_id="psh", log=print):
        self.calls.append(("run", user_id, password, company_id))
        log("[SESSION] fake login")
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    def check_session(self, log=print):
        self.calls.append(("check_session",))
        return {"ok": False, "code": "NOT_LOGGED_IN", "message": "no"}

    def open_module(self, module_name, xpath, log=print):
        self.calls.append(("open_module", module_name, xpath))
        return {"ok": True, "code": "MODULE_OPENED", "message": module_name}

    def set_catalog_category(self, category_name, category_value, log=print):
        self.calls.append(("set_catalog_category", category_name, category_value))
        return {"ok": True, "code": "CATEGORY_SELECTED", "message": category_name}

    def quick_find_catalog(self, category_name, category_value, filter_kind, query,
                           user_id, password, company_id="psh", log=print, destination=None):
        self.calls.append(("quick_find_catalog", category_name, category_value,
                           filter_kind, query, user_id, password, destination))
        return {"ok": True, "code": "RESULT_OPENED", "message": query, "codes": [query]}


def make_api(tmp_path):
    fake = FakeLogin()
    api = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    return api, fake


def test_find_code_calls_quick_find(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    result = api.find_code("Apparel", "ABC123", destination="bom")
    assert result["code"] == "RESULT_OPENED"
    assert ("quick_find_catalog", "Apparel", "01", "code", "ABC123", "u", "p", "bom") in fake.calls


def test_find_buyer_reference_uses_buyer_kind(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    api.find_buyer_reference("Apparel", "PO-9")
    assert ("quick_find_catalog", "Apparel", "01", "buyer_reference", "PO-9", "u", "p", None) in fake.calls


def test_open_module_builds_xpath(tmp_path):
    api, fake = make_api(tmp_path)
    api.open_module("0004_0050_0020")
    assert ("open_module", "OC List", '//*[@id="0004_0050_0020"]/a') in fake.calls


def test_prepare_catalog_opens_then_selects(tmp_path):
    api, fake = make_api(tmp_path)
    api.prepare_catalog("Apparel")
    names = [c[0] for c in fake.calls]
    assert names == ["open_module", "set_catalog_category"]


def test_log_sink_receives_lines(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    lines = []
    api.set_log_sink(lines.append)
    api.login()
    assert any("fake login" in line for line in lines)
    assert ("run", "u", "p", "psh") in fake.calls


def test_get_initial_state(tmp_path):
    prefs.save_account("bob", "pw", base_dir=tmp_path)
    prefs.save_prefs(base_dir=tmp_path, theme="dark")
    api, _ = make_api(tmp_path)
    state = api.get_initial_state()
    assert state["user_id"] == "bob"
    assert state["theme"] == "dark"
    assert state["hotkey_label"] == "Ctrl + Shift + X"


def test_save_account_persists(tmp_path):
    api, _ = make_api(tmp_path)
    api.save_account("carol", "s3cret")
    assert prefs.load_account(base_dir=tmp_path)["user_id"] == "carol"


def test_save_account_blank_password_keeps_existing(tmp_path):
    # Password input trên UI không bao giờ được điền lại khi mở Settings, nên
    # nếu người dùng chỉ đổi User ID rồi lưu, password gửi lên sẽ luôn rỗng.
    # Không được ghi đè mật khẩu đã lưu bằng chuỗi rỗng.
    api, _ = make_api(tmp_path)
    api.save_account("dave", "s3cret")
    result = api.save_account("dave2", "")
    assert result["ok"] is True
    assert result["code"] == "ACCOUNT_SAVED"
    loaded = prefs.load_account(base_dir=tmp_path)
    assert loaded == {"user_id": "dave2", "password": "s3cret"}


def test_save_account_blank_password_and_no_stored_password_fails(tmp_path):
    api, _ = make_api(tmp_path)
    result = api.save_account("erin", "   ")
    assert result["ok"] is False
    assert result["code"] == "PASSWORD_REQUIRED"
    assert "mật khẩu" in result["message"].lower()
    # Không được ghi bất cứ thứ gì xuống .env khi từ chối lưu.
    assert prefs.load_account(base_dir=tmp_path) == {"user_id": "", "password": ""}
