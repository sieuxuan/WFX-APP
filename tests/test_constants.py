from wfx_panel import constants


def test_categories_match_spec():
    assert constants.CATEGORIES["Apparel"] == "01"
    assert constants.CATEGORIES["Textiles/Fabric"] == "03"
    assert len(constants.CATEGORIES) == 6


def test_module_groups_counts():
    counts = {g["name"]: len(g["modules"]) for g in constants.MODULE_GROUPS}
    assert counts == {"Operation": 10, "Finance": 3, "Reports": 1, "Admin": 5}


def test_module_lookup_and_xpath():
    catalog = constants.MODULE_BY_ID["0003_6200"]
    assert catalog["name"] == "Catalog"
    assert constants.xpath_for("0003_6200") == '//*[@id="0003_6200"]/a'
    assert constants.MODULE_BY_ID["user_indent_list"]["xpath"] == (
        constants.USER_INDENT_XPATH
    )
    assert constants.MODULE_BY_ID["gdn_dispatch"]["xpath"] == (
        constants.GDN_DISPATCH_XPATH
    )
