from wfx_panel import constants, module_controllers


def test_every_module_has_its_own_controller_class():
    assert set(module_controllers.CONTROLLERS) == set(constants.MODULE_BY_ID)
    controller_types = {
        type(controller)
        for controller in module_controllers.CONTROLLERS.values()
    }
    assert len(controller_types) == len(constants.MODULE_BY_ID)


def test_catalog_controller_exposes_advanced_page_kind():
    controller = module_controllers.get("0003_6200")
    assert controller is not None
    manifest = controller.manifest()
    assert manifest["kind"] == "catalog"
    assert "Season" in manifest["description"]


def test_controller_delegates_to_login_module():
    calls = []

    class FakeLogin:
        @staticmethod
        def open_module(name, xpath, log):
            calls.append((name, xpath))
            return {"ok": True}

    controller = module_controllers.get("0004_0050_0020")
    assert controller.open(FakeLogin, lambda _line: None)["ok"] is True
    assert calls == [
        ("OC List", '//*[@id="0004_0050_0020"]/a')
    ]


def test_sample_and_sale_asn_list_enable_floating_filter():
    calls = []

    class FakeLogin:
        @staticmethod
        def open_module_with_floating_filter(name, xpath, log):
            calls.append((name, xpath))
            return {"ok": True, "code": "MODULE_FILTER_READY"}

    for module_id in ("0004_0056_4070", "0004_0070_0020"):
        result = module_controllers.get(module_id).open(
            FakeLogin, lambda _line: None
        )
        assert result["code"] == "MODULE_FILTER_READY"

    assert calls == [
        ("Sample List", '//*[@id="0004_0056_4070"]/a'),
        ("Sale ASN", '//*[@id="0004_0070_0020"]/a'),
    ]


def test_special_module_manifests_expose_page_kinds():
    assert module_controllers.get("0004_0050_0020").manifest()["kind"] == "oc"
    assert module_controllers.get("0004_0056_4070").manifest()["kind"] == "sample"
    assert module_controllers.get("0004_0070_0020").manifest()["kind"] == "sale_asn"
    assert module_controllers.get("0005_0010_1290").manifest()["kind"] == "supplier"
    assert module_controllers.get("0004_0010_1720").manifest()["kind"] == "buyer"
    assert (
        module_controllers.get("0090_0007").manifest()["kind"]
        == "company_setup"
    )
    user_indent = module_controllers.get("user_indent_list").manifest()
    assert user_indent["xpath"] == constants.USER_INDENT_XPATH
