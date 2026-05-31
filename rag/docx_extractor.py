from __future__ import annotations

import os

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph


def _iter_block_items(parent):
    if isinstance(parent, DocumentType):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("Unsupported DOCX parent container.")

    for child in parent_elm.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def _paragraph_text(paragraph: Paragraph) -> str:
    return paragraph.text.strip()


def _table_rows(table: Table) -> list[list[str]]:
    rows = []
    for row in table.rows:
        values = [cell.text.strip() for cell in row.cells]
        rows.append(values)
    return rows


def _looks_like_header(values: list[str]) -> bool:
    non_empty = [value for value in values if value]
    if len(non_empty) < 2:
        return False
    alpha_like = [value for value in non_empty if any(char.isalpha() for char in value)]
    return len(alpha_like) >= max(2, len(non_empty) // 2)


def extract_docx_structured(path: str) -> dict:
    if not os.path.exists(path):
        return {
            "success": False,
            "text": "",
            "file_type": "docx",
            "method": "python_docx_structured",
            "error": f"File not found: {path}",
        }

    try:
        document = Document(path)
    except Exception as exc:
        return {
            "success": False,
            "text": "",
            "file_type": "docx",
            "method": "python_docx_structured",
            "error": f"Failed to read DOCX file: {exc}",
        }

    blocks = []
    text_blocks = []
    paragraph_count = 0
    table_count = 0
    table_row_count = 0
    region_counts = {"paragraph": 0, "table_header": 0, "table_row": 0}

    for block_index, block in enumerate(_iter_block_items(document), start=1):
        if isinstance(block, Paragraph):
            text = _paragraph_text(block)
            if not text:
                continue
            paragraph_count += 1
            region_counts["paragraph"] += 1
            ref = f"Paragraph {paragraph_count}"
            block_text = f"[DOCX | Block: {block_index} | Ref: {ref} | Region: paragraph]\n{text}"
            blocks.append({
                "region_type": "paragraph",
                "block_index": block_index,
                "reference": ref,
                "text": block_text,
            })
            text_blocks.append(block_text)
            continue

        if isinstance(block, Table):
            table_count += 1
            rows = _table_rows(block)
            if not rows:
                continue

            headers = []
            data_start = 0
            if rows and _looks_like_header(rows[0]):
                headers = [value or f"Column_{index + 1}" for index, value in enumerate(rows[0])]
                header_text_lines = [f"{header}: {value}" for header, value in zip(headers, rows[0]) if value]
                header_ref = f"Table {table_count} Header"
                header_text = (
                    f"[DOCX | Block: {block_index} | Ref: {header_ref} | Region: table_header]\n"
                    + "\n".join(header_text_lines)
                ).strip()
                blocks.append({
                    "region_type": "table_header",
                    "block_index": block_index,
                    "reference": header_ref,
                    "text": header_text,
                })
                text_blocks.append(header_text)
                region_counts["table_header"] += 1
                data_start = 1
            else:
                max_cols = max(len(row) for row in rows) if rows else 0
                headers = [f"Column_{index + 1}" for index in range(max_cols)]

            for row_offset, row_values in enumerate(rows[data_start:], start=data_start + 1):
                normalized_values = row_values + [""] * (len(headers) - len(row_values))
                pairs = [f"{header}: {value}" for header, value in zip(headers, normalized_values) if value]
                if not pairs:
                    continue
                table_row_count += 1
                region_counts["table_row"] += 1
                row_ref = f"Table {table_count} Row {row_offset}"
                row_text = (
                    f"[DOCX | Block: {block_index} | Ref: {row_ref} | Region: table_row]\n"
                    + "\n".join(pairs)
                ).strip()
                blocks.append({
                    "region_type": "table_row",
                    "block_index": block_index,
                    "reference": row_ref,
                    "headers": headers,
                    "values": normalized_values,
                    "text": row_text,
                })
                text_blocks.append(row_text)

    if not text_blocks:
        return {
            "success": False,
            "text": "",
            "file_type": "docx",
            "method": "python_docx_structured",
            "error": "DOCX file contained no extractable text.",
            "paragraph_count": 0,
            "table_count": table_count,
            "table_row_count": table_row_count,
            "blocks": [],
            "region_counts": region_counts,
            "warnings": [],
        }

    return {
        "success": True,
        "text": "\n\n".join(text_blocks).strip(),
        "file_type": "docx",
        "method": "python_docx_structured",
        "error": None,
        "paragraph_count": paragraph_count,
        "table_count": table_count,
        "table_row_count": table_row_count,
        "blocks": blocks,
        "region_counts": region_counts,
        "warnings": [],
    }
