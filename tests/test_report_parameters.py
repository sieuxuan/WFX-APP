import json
import threading

from wfx_panel.report_parameters import ReportParameterStore


def test_store_rejects_invalid_roots_and_cleans_values(tmp_path):
    path = tmp_path / "report-parameters.json"
    path.write_text("[]", encoding="utf-8")
    store = ReportParameterStore(path)

    assert store.load("user", "report") == {}

    saved = store.save(
        "user",
        "report",
        {" text ": 12, "flag": False, "items": [1, None, "x"], "bad": {}},
    )

    assert saved == {"text": "12", "flag": False, "items": ["1", "x"]}
    assert store.load("user", "report") == saved


def test_parallel_stores_do_not_lose_each_others_report(tmp_path):
    path = tmp_path / "report-parameters.json"
    first = ReportParameterStore(path)
    second = ReportParameterStore(path)
    barrier = threading.Barrier(2)

    def save(store, report_id):
        barrier.wait(timeout=2)
        store.save("user", report_id, {"value": report_id})

    workers = [
        threading.Thread(target=save, args=(first, "one")),
        threading.Thread(target=save, args=(second, "two")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)
        assert not worker.is_alive()

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["user"] == {
        "one": {"value": "one"},
        "two": {"value": "two"},
    }
