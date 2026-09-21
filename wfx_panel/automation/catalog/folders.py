"""Đọc và chọn node trong cây folder của Catalog."""

from __future__ import annotations

from wfx_panel.automation._common import Any, Frame, Page, PlaywrightError, _wait, time
from wfx_panel.automation.catalog.navigation import _catalog_tree_frame_now


def _catalog_folder_nodes(frame: Frame) -> list[dict[str, Any]]:
    """Đọc toàn bộ cây con bên dưới Master từ DOM đã được WFX nạp."""
    nodes = frame.evaluate(
        """() => {
            const clean = value =>
                String(value || '').replace(/\\s+/g, ' ').trim();
            const roots = [...document.querySelectorAll('ul[nodecode]')];
            const root = roots.find(
                element => clean(element.getAttribute('nodecode')) === 'Master'
            );
            if (!root) return [];
            const directSpan = element =>
                [...element.children].find(child =>
                    child.matches?.('span[nodeid][onclick]')
                ) || null;
            return [...root.querySelectorAll('li > span[nodeid][onclick]')]
                .map(span => {
                    const li = span.closest('li');
                    if (!li) return null;
                    const path = [];
                    let current = li;
                    while (current && root.contains(current)) {
                        const own = directSpan(current);
                        if (own) path.unshift(clean(own.textContent));
                        current = current.parentElement?.closest('li') || null;
                    }
                    const childTree = [...li.children].find(child =>
                        child.matches?.('ul[nodecode]')
                    );
                    const nodeId = clean(span.getAttribute('nodeid'));
                    if (!nodeId || !path.length) return null;
                    return {
                        node_id: nodeId,
                        node_code: clean(childTree?.getAttribute('nodecode')),
                        name: path[path.length - 1],
                        path,
                        path_label: path.join(' / '),
                        kind: [...li.classList, ...span.classList].some(name =>
                            name.toLocaleLowerCase('en') === 'groupnode'
                        )
                            ? 'group'
                            : 'folder',
                        depth: path.length,
                    };
                })
                .filter(Boolean);
        }"""
    )
    return nodes if isinstance(nodes, list) else []


def _catalog_folder_for_node(
    frame: Frame,
    node_id: str,
) -> dict[str, Any] | None:
    for folder in _catalog_folder_nodes(frame):
        if str(folder.get("node_id") or "") == node_id:
            return folder
    return None


def _wait_catalog_folder_selected(
    page: Page,
    node_id: str,
    timeout_s: float = 10,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = _catalog_tree_frame_now(page)
        if frame is not None:
            try:
                selected = frame.locator(
                    f'span.clsTreeSelectedNode[nodeid="{node_id}"]'
                )
                if selected.count() > 0:
                    return True
            except PlaywrightError:
                pass
        _wait(page, 200)
    return False
