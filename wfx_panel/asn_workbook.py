"""Ghép hai workbook report Sale ASN mà không làm biến dạng report WFX."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from openpyxl import load_workbook

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
WORKSHEET_REL_TYPE = f"{DOC_REL_NS}/worksheet"
WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", DOC_REL_NS)


class ASNWorkbookError(ValueError):
    """Workbook report WFX không thể đọc hoặc ghép an toàn."""


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _xml(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def _xml_bytes(root: ET.Element, *, default_namespace: str = MAIN_NS) -> bytes:
    ET.register_namespace("", default_namespace)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ET.register_namespace("", MAIN_NS)
    return data


def _safe_sheet_title(value: str, existing: set[str]) -> str:
    cleaned = "".join(
        " " if character in "[]:*?/\\" else character for character in value
    )
    cleaned = " ".join(cleaned.split()).strip(" '") or "Report"
    cleaned = cleaned[:31].rstrip()
    candidate = cleaned
    suffix = 2
    while candidate.casefold() in existing:
        tail = f" ({suffix})"
        candidate = f"{cleaned[: 31 - len(tail)].rstrip()}{tail}"
        suffix += 1
    existing.add(candidate.casefold())
    return candidate


_STYLE_SECTION_ORDER = (
    "numFmts",
    "fonts",
    "fills",
    "borders",
    "cellStyleXfs",
    "cellXfs",
    "cellStyles",
    "dxfs",
    "tableStyles",
    "colors",
    "extLst",
)


def _style_section(root: ET.Element, name: str) -> ET.Element:
    section = root.find(_tag(MAIN_NS, name))
    if section is not None:
        return section
    section = ET.Element(_tag(MAIN_NS, name))
    wanted = _STYLE_SECTION_ORDER.index(name)
    for index, child in enumerate(root):
        local = child.tag.rsplit("}", 1)[-1]
        if local in _STYLE_SECTION_ORDER and _STYLE_SECTION_ORDER.index(local) > wanted:
            root.insert(index, section)
            break
    else:
        root.append(section)
    return section


def _set_count(section: ET.Element) -> None:
    section.set("count", str(len(section)))


def _append_components(
    base_styles: ET.Element,
    source_styles: ET.Element,
    section_name: str,
) -> dict[int, int]:
    base = _style_section(base_styles, section_name)
    source = source_styles.find(_tag(MAIN_NS, section_name))
    offset = len(base)
    if source is None:
        return {}
    mapping: dict[int, int] = {}
    for source_index, item in enumerate(source):
        mapping[source_index] = offset + source_index
        base.append(deepcopy(item))
    _set_count(base)
    return mapping


def _merge_number_formats(
    base_styles: ET.Element,
    source_styles: ET.Element,
) -> dict[int, int]:
    base = _style_section(base_styles, "numFmts")
    source = source_styles.find(_tag(MAIN_NS, "numFmts"))
    formats_by_code: dict[str, int] = {}
    used_ids: set[int] = set()
    for item in base:
        number_id = int(item.get("numFmtId", "0"))
        used_ids.add(number_id)
        formats_by_code[str(item.get("formatCode") or "")] = number_id
    mapping: dict[int, int] = {}
    if source is None:
        return mapping
    next_id = max([163, *used_ids]) + 1
    for item in source:
        old_id = int(item.get("numFmtId", "0"))
        code = str(item.get("formatCode") or "")
        if code in formats_by_code:
            mapping[old_id] = formats_by_code[code]
            continue
        while next_id in used_ids:
            next_id += 1
        copied = deepcopy(item)
        copied.set("numFmtId", str(next_id))
        base.append(copied)
        mapping[old_id] = next_id
        formats_by_code[code] = next_id
        used_ids.add(next_id)
        next_id += 1
    _set_count(base)
    return mapping


def _remap_xf(
    item: ET.Element,
    *,
    font_map: dict[int, int],
    fill_map: dict[int, int],
    border_map: dict[int, int],
    number_format_map: dict[int, int],
    style_xf_map: dict[int, int] | None = None,
) -> ET.Element:
    copied = deepcopy(item)
    component_maps = {
        "fontId": font_map,
        "fillId": fill_map,
        "borderId": border_map,
        "numFmtId": number_format_map,
    }
    for attribute, mapping in component_maps.items():
        if attribute not in copied.attrib:
            continue
        old_value = int(copied.get(attribute, "0"))
        copied.set(attribute, str(mapping.get(old_value, old_value)))
    if style_xf_map is not None and "xfId" in copied.attrib:
        old_value = int(copied.get("xfId", "0"))
        copied.set("xfId", str(style_xf_map.get(old_value, old_value)))
    return copied


def _merge_styles(base_data: bytes, source_data: bytes) -> tuple[bytes, dict[int, int], dict[int, int]]:
    base_styles = _xml(base_data)
    source_styles = _xml(source_data)
    number_format_map = _merge_number_formats(base_styles, source_styles)
    font_map = _append_components(base_styles, source_styles, "fonts")
    fill_map = _append_components(base_styles, source_styles, "fills")
    border_map = _append_components(base_styles, source_styles, "borders")

    base_style_xfs = _style_section(base_styles, "cellStyleXfs")
    source_style_xfs = source_styles.find(_tag(MAIN_NS, "cellStyleXfs"))
    style_xf_map: dict[int, int] = {}
    if source_style_xfs is not None:
        offset = len(base_style_xfs)
        for source_index, item in enumerate(source_style_xfs):
            style_xf_map[source_index] = offset + source_index
            base_style_xfs.append(
                _remap_xf(
                    item,
                    font_map=font_map,
                    fill_map=fill_map,
                    border_map=border_map,
                    number_format_map=number_format_map,
                )
            )
        _set_count(base_style_xfs)

    base_cell_xfs = _style_section(base_styles, "cellXfs")
    source_cell_xfs = source_styles.find(_tag(MAIN_NS, "cellXfs"))
    cell_style_map: dict[int, int] = {}
    if source_cell_xfs is not None:
        offset = len(base_cell_xfs)
        for source_index, item in enumerate(source_cell_xfs):
            cell_style_map[source_index] = offset + source_index
            base_cell_xfs.append(
                _remap_xf(
                    item,
                    font_map=font_map,
                    fill_map=fill_map,
                    border_map=border_map,
                    number_format_map=number_format_map,
                    style_xf_map=style_xf_map,
                )
            )
        _set_count(base_cell_xfs)

    base_dxfs = _style_section(base_styles, "dxfs")
    source_dxfs = source_styles.find(_tag(MAIN_NS, "dxfs"))
    dxf_map: dict[int, int] = {}
    if source_dxfs is not None:
        offset = len(base_dxfs)
        for source_index, item in enumerate(source_dxfs):
            dxf_map[source_index] = offset + source_index
            base_dxfs.append(deepcopy(item))
        _set_count(base_dxfs)
    return _xml_bytes(base_styles), cell_style_map, dxf_map


def _remap_sheet_styles(
    source_data: bytes,
    cell_style_map: dict[int, int],
    dxf_map: dict[int, int],
) -> bytes:
    root = _xml(source_data)
    for item in root.iter():
        local = item.tag.rsplit("}", 1)[-1]
        attribute = "style" if local == "col" else "s"
        if local in {"c", "row", "col"} and attribute in item.attrib:
            old_value = int(item.get(attribute, "0"))
            item.set(attribute, str(cell_style_map.get(old_value, old_value)))
        if "dxfId" in item.attrib:
            old_value = int(item.get("dxfId", "0"))
            item.set("dxfId", str(dxf_map.get(old_value, old_value)))
    return _xml_bytes(root)


def _relationship_member(target: str) -> str:
    cleaned = target.replace("\\", "/").lstrip("/")
    if cleaned.startswith("xl/"):
        return cleaned
    return str(PurePosixPath("xl") / cleaned)


def _sheet_records(
    workbook_root: ET.Element,
    relationships_root: ET.Element,
) -> list[tuple[ET.Element, str]]:
    targets = {
        str(item.get("Id") or ""): _relationship_member(str(item.get("Target") or ""))
        for item in relationships_root.findall(_tag(PACKAGE_REL_NS, "Relationship"))
        if item.get("Type") == WORKSHEET_REL_TYPE
    }
    sheets = workbook_root.find(_tag(MAIN_NS, "sheets"))
    if sheets is None:
        return []
    records: list[tuple[ET.Element, str]] = []
    for sheet in sheets.findall(_tag(MAIN_NS, "sheet")):
        relationship_id = str(sheet.get(_tag(DOC_REL_NS, "id")) or "")
        member = targets.get(relationship_id)
        if member:
            records.append((sheet, member))
    return records


def _next_relationship_id(used: set[str]) -> str:
    index = 1
    while f"rId{index}" in used:
        index += 1
    value = f"rId{index}"
    used.add(value)
    return value


def _update_defined_names(
    base_workbook: ET.Element,
    source_workbook: ET.Element,
    invoice_positions: dict[int, int],
    packing_positions: dict[int, int],
) -> None:
    base = base_workbook.find(_tag(MAIN_NS, "definedNames"))
    source = source_workbook.find(_tag(MAIN_NS, "definedNames"))
    if base is not None:
        for item in base:
            if "localSheetId" in item.attrib:
                old_value = int(item.get("localSheetId", "0"))
                item.set("localSheetId", str(invoice_positions.get(old_value, old_value)))
    if source is None:
        return
    if base is None:
        base = ET.Element(_tag(MAIN_NS, "definedNames"))
        sheets = base_workbook.find(_tag(MAIN_NS, "sheets"))
        insert_at = list(base_workbook).index(sheets) + 1 if sheets is not None else 0
        base_workbook.insert(insert_at, base)
    for item in source:
        copied = deepcopy(item)
        if "localSheetId" not in copied.attrib:
            continue
        old_value = int(copied.get("localSheetId", "0"))
        copied.set("localSheetId", str(packing_positions.get(old_value, old_value)))
        base.append(copied)


def _merge_packages(
    packing_path: Path,
    buyer_path: Path,
    target: Path,
    invoice_label: str,
) -> None:
    with ZipFile(buyer_path) as buyer_zip, ZipFile(packing_path) as packing_zip:
        buyer_workbook = _xml(buyer_zip.read("xl/workbook.xml"))
        packing_workbook = _xml(packing_zip.read("xl/workbook.xml"))
        buyer_relationships = _xml(buyer_zip.read("xl/_rels/workbook.xml.rels"))
        packing_relationships = _xml(packing_zip.read("xl/_rels/workbook.xml.rels"))
        buyer_records = _sheet_records(buyer_workbook, buyer_relationships)
        packing_records = _sheet_records(packing_workbook, packing_relationships)
        if not buyer_records or not packing_records:
            raise ASNWorkbookError("Hai report Sale ASN phải có ít nhất một sheet.")

        for _sheet, member in packing_records:
            name = PurePosixPath(member).name
            relationship_member = f"xl/worksheets/_rels/{name}.rels"
            if relationship_member in packing_zip.namelist():
                raise ASNWorkbookError(
                    "Packing List có đối tượng liên kết chưa thể ghép nguyên trạng."
                )

        merged_styles, cell_style_map, dxf_map = _merge_styles(
            buyer_zip.read("xl/styles.xml"),
            packing_zip.read("xl/styles.xml"),
        )

        buyer_names = [str(item.get("name") or "") for item, _member in buyer_records]
        packing_names = [str(item.get("name") or "") for item, _member in packing_records]
        collisions = {name.casefold() for name in buyer_names} & {
            name.casefold() for name in packing_names
        }
        existing = {
            name.casefold()
            for name in [*buyer_names, *packing_names]
            if name.casefold() not in collisions
        }
        for sheet, _member in buyer_records:
            if str(sheet.get("name") or "").casefold() in collisions:
                sheet.set(
                    "name",
                    _safe_sheet_title(f"INVOICE {invoice_label}", existing),
                )

        used_relationship_ids = {
            str(item.get("Id") or "")
            for item in buyer_relationships.findall(
                _tag(PACKAGE_REL_NS, "Relationship")
            )
        }
        used_sheet_ids = [
            int(item.get("sheetId", "0")) for item, _member in buyer_records
        ]
        used_sheet_numbers = [
            int(match.group(1))
            for name in buyer_zip.namelist()
            if (match := re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", name))
        ]
        next_sheet_id = max([0, *used_sheet_ids]) + 1
        next_sheet_number = max([0, *used_sheet_numbers]) + 1
        packing_output: list[tuple[ET.Element, str, bytes]] = []
        for source_sheet, source_member in packing_records:
            source_name = str(source_sheet.get("name") or "")
            if source_name.casefold() in collisions:
                target_name = _safe_sheet_title(
                    f"PKL {invoice_label}",
                    existing,
                )
            else:
                target_name = source_name
            relationship_id = _next_relationship_id(used_relationship_ids)
            target_member = f"xl/worksheets/sheet{next_sheet_number}.xml"
            sheet = ET.Element(
                _tag(MAIN_NS, "sheet"),
                {
                    "name": target_name,
                    "sheetId": str(next_sheet_id),
                    _tag(DOC_REL_NS, "id"): relationship_id,
                },
            )
            buyer_relationships.append(
                ET.Element(
                    _tag(PACKAGE_REL_NS, "Relationship"),
                    {
                        "Type": WORKSHEET_REL_TYPE,
                        "Target": f"/{target_member}",
                        "Id": relationship_id,
                    },
                )
            )
            packing_output.append(
                (
                    sheet,
                    target_member,
                    _remap_sheet_styles(
                        packing_zip.read(source_member),
                        cell_style_map,
                        dxf_map,
                    ),
                )
            )
            next_sheet_id += 1
            next_sheet_number += 1

        sequence: list[tuple[str, int, ET.Element]] = []
        for index in range(max(len(buyer_records), len(packing_output))):
            if index < len(buyer_records):
                sequence.append(("invoice", index, buyer_records[index][0]))
            if index < len(packing_output):
                sequence.append(("packing", index, packing_output[index][0]))
        sheets = buyer_workbook.find(_tag(MAIN_NS, "sheets"))
        if sheets is None:
            raise ASNWorkbookError("Buyer Invoice không có danh sách sheet.")
        sheets[:] = [item for _kind, _index, item in sequence]
        invoice_positions = {
            old_index: final_index
            for final_index, (kind, old_index, _item) in enumerate(sequence)
            if kind == "invoice"
        }
        packing_positions = {
            old_index: final_index
            for final_index, (kind, old_index, _item) in enumerate(sequence)
            if kind == "packing"
        }
        _update_defined_names(
            buyer_workbook,
            packing_workbook,
            invoice_positions,
            packing_positions,
        )

        content_types = _xml(buyer_zip.read("[Content_Types].xml"))
        for _sheet, member, _data in packing_output:
            content_types.append(
                ET.Element(
                    _tag(CONTENT_TYPE_NS, "Override"),
                    {
                        "PartName": f"/{member}",
                        "ContentType": WORKSHEET_CONTENT_TYPE,
                    },
                )
            )

        replacements = {
            "[Content_Types].xml": _xml_bytes(
                content_types,
                default_namespace=CONTENT_TYPE_NS,
            ),
            "xl/workbook.xml": _xml_bytes(buyer_workbook),
            "xl/_rels/workbook.xml.rels": _xml_bytes(
                buyer_relationships,
                default_namespace=PACKAGE_REL_NS,
            ),
            "xl/styles.xml": merged_styles,
        }
        with ZipFile(target, "w", compression=ZIP_DEFLATED) as output_zip:
            for info in buyer_zip.infolist():
                output_zip.writestr(info, replacements.get(info.filename, buyer_zip.read(info)))
            for _sheet, member, data in packing_output:
                output_zip.writestr(member, data)


def merge_sale_asn_reports(
    packing_list_path: str | Path,
    buyer_invoice_path: str | Path,
    output_path: str | Path,
    *,
    invoice_no: str = "",
) -> Path:
    """Ghép report ở cấp OOXML để giữ nguyên khung của cả Invoice và PKL."""
    packing_path = Path(packing_list_path).expanduser().resolve()
    buyer_path = Path(buyer_invoice_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if target.suffix.casefold() != ".xlsx":
        raise ASNWorkbookError("File Sale ASN phải có đuôi .xlsx.")
    for source in (packing_path, buyer_path):
        if not source.is_file() or source.stat().st_size <= 0:
            raise ASNWorkbookError(f"Không đọc được report: {source.name}.")
    invoice_label = str(invoice_no or target.stem).strip() or "Invoice"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _merge_packages(packing_path, buyer_path, target, invoice_label)
        verified = load_workbook(target, read_only=True, data_only=False)
        verified.close()
    except ASNWorkbookError:
        target.unlink(missing_ok=True)
        raise
    except (BadZipFile, KeyError, ET.ParseError) as error:
        target.unlink(missing_ok=True)
        raise ASNWorkbookError(
            f"Report WFX không phải workbook Excel hợp lệ: {error}"
        ) from error
    except Exception as error:
        target.unlink(missing_ok=True)
        raise ASNWorkbookError(f"Không ghép được hai report Sale ASN: {error}") from error
    return target


def sale_asn_sheet_names(path: str | Path) -> list[str]:
    """Đọc tên sheet thực tế sau khi ghép để UI không báo tên giả định."""
    source = Path(path).expanduser().resolve()
    try:
        workbook = load_workbook(source, read_only=True, data_only=False)
    except Exception as error:
        raise ASNWorkbookError(f"Không đọc được tên sheet Sale ASN: {error}") from error
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()
