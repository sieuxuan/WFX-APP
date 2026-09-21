"""Controller của bridge pywebview — mỗi màn nghiệp vụ một file.

``PanelAPI`` là bề mặt duy nhất mà JavaScript gọi tới, nên nó phải có đủ mọi
method. Nhưng logic thì không cần nằm chung một class: mỗi controller ở đây sở
hữu state nghiệp vụ của chính nó và mượn hạ tầng dùng chung của panel (``_run``
kèm khoá + lịch sử, ``_account``, ``_prefs``, ``_log``, ``_login``) qua tham
chiếu ``panel``. Cùng package nên coupling chặt là chấp nhận được, đổi lại
bridge gọn và từng luồng test được độc lập.
"""

from __future__ import annotations

from wfx_panel.controllers.catalog import CatalogController
from wfx_panel.controllers.directory import DirectoryController
from wfx_panel.controllers.finance import FinanceController
from wfx_panel.controllers.inventory import InventoryController
from wfx_panel.controllers.jobs import JobsController
from wfx_panel.controllers.oc import OCController
from wfx_panel.controllers.reports import ReportsController
from wfx_panel.controllers.sale_asn import SaleASNController
from wfx_panel.controllers.settings import SettingsController

__all__ = [
    "CatalogController",
    "DirectoryController",
    "FinanceController",
    "InventoryController",
    "JobsController",
    "OCController",
    "ReportsController",
    "SaleASNController",
    "SettingsController",
]
