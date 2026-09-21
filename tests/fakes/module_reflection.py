"""Phản chiếu module/package automation cho test.

Các module automation lớn đã tách thành package (``costing``, ``catalog``…).
Test vẫn nói chuyện với một cái tên duy nhất — ``costing`` — nên helper ở đây
lo phần "cái tên đó giờ trải trên nhiều file": vá attribute tới đúng mọi nơi
bind nó, và đọc source của cả package thay vì một file.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import ModuleType


def _submodules(module: ModuleType) -> list[ModuleType]:
    """Mọi submodule đã nạp của ``module`` (rỗng nếu nó không phải package)."""
    if getattr(module, "__path__", None) is None:
        return []
    prefix = f"{module.__name__}."
    return [
        submodule
        for name, submodule in sys.modules.items()
        if name.startswith(prefix) and submodule is not None
    ]


def _binding_sites(module: ModuleType, name: str) -> list[ModuleType]:
    """Chính module và mọi submodule của nó đang bind ``name``.

    ``costing/__init__.py`` chỉ re-export, nên gắn thẳng lên đó không tới được
    thân hàm trong submodule — chúng đã ``from ... import`` tên này vào
    namespace riêng. Helper trả về đủ mọi nơi cần gắn để test không phải biết
    symbol đang nằm ở file con nào.
    """
    sites = [module] if hasattr(module, name) else []
    sites += [sub for sub in _submodules(module) if hasattr(sub, name)]
    return sites


def patch_automation(
    monkeypatch, module: ModuleType, name: str, value, *, raising: bool = True
) -> None:
    """Thay ``name`` trên một module automation, kể cả khi nó là package."""
    sites = _binding_sites(module, name)
    if raising:
        assert sites, f"{module.__name__} không bind {name!r} ở đâu cả"
    for site in sites or [module]:
        monkeypatch.setattr(site, name, value, raising=raising)


def module_source(module: ModuleType) -> str:
    """Toàn bộ source của module — với package là bản nối mọi file con.

    Dùng cho các canh "code phải chứa selector/comment này". Chúng canh nội
    dung, không canh file nào chứa, nên tách file không được làm chúng đỏ.
    """
    file_path = getattr(module, "__file__", None)
    assert file_path, f"{module.__name__} không có __file__"
    path = Path(file_path)
    if path.name != "__init__.py":
        return path.read_text(encoding="utf-8")
    return "\n".join(
        sibling.read_text(encoding="utf-8")
        for sibling in sorted(path.parent.glob("*.py"))
    )


def module_files(module: ModuleType) -> list[Path]:
    """Mọi file nguồn của module — với package là toàn bộ file con."""
    file_path = getattr(module, "__file__", None)
    assert file_path, f"{module.__name__} không có __file__"
    path = Path(file_path)
    if path.name != "__init__.py":
        return [path]
    return sorted(path.parent.glob("*.py"))


def module_trees(module: ModuleType) -> list[tuple[Path, ast.Module]]:
    """AST của mọi file nguồn, cho các canh quét toàn bộ call site."""
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in module_files(module)
    ]
