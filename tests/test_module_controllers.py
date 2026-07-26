from wfx_panel import constants, module_controllers


def test_every_module_has_its_own_controller_class():
    assert set(module_controllers.CONTROLLERS) == set(constants.MODULE_BY_ID)
    controller_types = {
        type(controller)
        for controller in module_controllers.CONTROLLERS.values()
    }
    assert len(controller_types) == len(constants.MODULE_BY_ID)


def test_catalog_controller_exposes_advanced_modal_kind():
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
