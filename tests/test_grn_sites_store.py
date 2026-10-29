"""Site nhận kho GRN nhớ theo User ID + Division."""

from __future__ import annotations

from wfx_panel.stores.grn_sites import GrnSiteStore, clean_sites


def test_sites_are_kept_per_account_and_division(tmp_path):
    store = GrnSiteStore(tmp_path)
    store.remember("User", "WOVEN", ["Hanoi", "HCM"])
    store.remember("user", "KNIT", ["Bac Ninh"])

    assert store.load("USER", "woven") == ["Hanoi", "HCM"]
    assert store.load("user", "KNIT") == ["Bac Ninh"]
    assert store.load("other", "WOVEN") == []


def test_nothing_is_written_without_a_user_id(tmp_path):
    store = GrnSiteStore(tmp_path)

    assert store.remember("", "WOVEN", ["Hanoi"]) == []
    assert not store.path.exists()


def test_an_empty_read_never_wipes_the_remembered_list(tmp_path):
    store = GrnSiteStore(tmp_path)
    store.remember("u", "WOVEN", ["Hanoi"])

    assert store.remember("u", "WOVEN", []) == ["Hanoi"]


def test_a_corrupt_file_reads_as_empty(tmp_path):
    store = GrnSiteStore(tmp_path)
    store.path.write_text("{not json", encoding="utf-8")

    assert store.load("u", "WOVEN") == []
    assert store.remember("u", "WOVEN", ["Hanoi"]) == ["Hanoi"]


def test_sites_are_trimmed_and_deduplicated_in_wfx_order():
    assert clean_sites(["  Ha  Noi ", "HCM", "ha noi", "", None]) == ["Ha Noi", "HCM"]
