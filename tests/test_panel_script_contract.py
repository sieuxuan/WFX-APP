"""Hop dong nap script cua panel UI.

panel.js cu la MOT IIFE nen moi khai bao ham duoc hoist truoc khi bat ky lenh
top-level nao chay. Sau khi tach thanh nhieu script co dien, hoisting chi con
trong pham vi TUNG FILE: mot bang tra top-level doc ham cua file nap sau se
nem ReferenceError ngay luc tai trang. Cac canh duoi day chan dung lop loi do.
"""

from __future__ import annotations

import re
import subprocess

from tests.fakes.ui_source import panel_js, panel_script_paths

_DECLARATION = re.compile(r"^(?:(?:async )?function (\w+)|(?:const|let|var|class) ([\w$]+))")
_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")


def _function_owner() -> dict[str, str]:
    owner = {}
    for path in panel_script_paths():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _DECLARATION.match(line)
            if match and match.group(1):
                owner[match.group(1)] = path.name
    return owner


def _top_level_initialisers(path):
    """(ten, than) cua moi khai bao const/let/var/class o muc top-level."""
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        match = _DECLARATION.match(lines[index])
        if not match or not match.group(2):
            index += 1
            continue
        end = index
        while end < len(lines) and not (
            lines[end].rstrip().endswith((";", "};", "];", ");"))
            and lines[end][:1] not in (" ", "\t")
            or (end > index and lines[end].rstrip() in ("};", "];", ");"))
        ):
            end += 1
        yield match.group(2), "\n".join(lines[index:end + 1])
        index = end + 1


def test_no_top_level_initialiser_reads_a_function_defined_later():
    owner = _function_owner()
    order = {path.name: rank for rank, path in enumerate(panel_script_paths())}
    offenders = []
    for path in panel_script_paths():
        for name, body in _top_level_initialisers(path):
            for identifier in set(_IDENTIFIER.findall(body)) - {name}:
                home = owner.get(identifier)
                if home and order[home] > order[path.name]:
                    offenders.append(f"{path.name}:{name} -> {identifier} ({home})")
    assert not offenders, (
        "Khai bao top-level doc ham cua file nap sau — trang se nem "
        "ReferenceError ngay luc tai: " + ", ".join(sorted(offenders))
    )


def test_every_panel_script_parses():
    for path in panel_script_paths():
        done = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True
        )
        assert done.returncode == 0, f"{path.name} loi cu phap:\n{done.stderr}"


def test_bootstrap_loads_last_and_core_first():
    names = [path.name for path in panel_script_paths()]
    assert names[0] == "core.js", "core.js khai bao state dung chung, phai nap dau"
    assert names[-1] == "bootstrap.js", "bootstrap.js gan su kien, phai nap cuoi"
    assert names[-2] == "module_actions.js", (
        "module_actions.js giu bang tra tro toi moi handler nen phai nap ap chot"
    )


def test_every_script_declares_strict_mode():
    for path in panel_script_paths():
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first == chr(34) + "use strict" + chr(34) + ";", path.name


def test_concatenated_source_is_one_contiguous_program():
    source = panel_js()
    assert source.count(chr(34) + "use strict" + chr(34) + ";") == len(panel_script_paths())
    assert "(() => {" not in source.splitlines()[1]
