from __future__ import annotations

import pytest

from tests.fakes.module_reflection import _binding_sites
from wfx_panel import prefs, telemetry


@pytest.fixture(autouse=True)
def disable_production_telemetry_for_tests(monkeypatch):
    """Mọi test mặc định phải tuyệt đối im lặng với webhook production."""
    monkeypatch.delenv(telemetry.ENV_NAME, raising=False)
    monkeypatch.setattr(telemetry, "DEFAULT_WEBHOOK_URL", "")


@pytest.fixture(autouse=True)
def isolate_user_data_dir(tmp_path_factory, monkeypatch):
    """Không test nào được ghi vào dữ liệu thật của người đang chạy test.

    Khi chạy từ source, ``prefs.DATA_DIR`` chính là thư mục repo, nên bất kỳ
    test nào gọi ``PanelAPI``/``PanelApp`` mà không truyền ``base_dir`` sẽ ghi
    đè ``prefs.json``, ``jobs.json``, ``.env`` và ``crash.log`` thật — một test
    bật/tắt công tắc Settings là đủ để đổi cấu hình máy người dùng, và kết quả
    còn dính sang những test chạy sau. Fixture này trỏ DATA_DIR sang thư mục
    tạm riêng cho từng test; test nào cần base_dir riêng vẫn truyền như cũ.
    """
    data_dir = tmp_path_factory.mktemp("wfx-data")
    monkeypatch.setattr(prefs, "DATA_DIR", data_dir)
    # `paths` là nguồn gốc, còn các module khác `from ... import DATA_DIR` nên
    # phải vá đúng mọi nơi đã bind tên này.
    for module_name in ("wfx_panel.paths", "wfx_panel"):
        module = __import__(module_name, fromlist=["DATA_DIR"])
        for site in _binding_sites(module, "DATA_DIR"):
            monkeypatch.setattr(site, "DATA_DIR", data_dir)
    return data_dir
