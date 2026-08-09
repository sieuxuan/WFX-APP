import json

from wfx_panel.sale_asn_buyers import SaleASNBuyerStore, normalise_buyers


def test_normalise_buyers_deduplicates_labels_case_insensitively():
    assert normalise_buyers(
        [
            {"label": " Buyer A ", "value": 1},
            {"label": "buyer a", "value": "duplicate"},
            {"label": "Buyer B", "value": None},
            None,
        ]
    ) == [
        {"label": "Buyer A", "value": "1"},
        {"label": "Buyer B", "value": ""},
    ]


def test_store_recovers_from_invalid_json_and_saves_atomically(tmp_path):
    path = tmp_path / "sale-asn-buyers.json"
    path.write_text("not-json", encoding="utf-8")
    store = SaleASNBuyerStore(path)

    assert store.load() == []
    saved = store.save([{"label": "Buyer A", "value": "10"}])

    assert saved == [{"label": "Buyer A", "value": "10"}]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["buyers"] == saved
    assert payload["updated_at"]
