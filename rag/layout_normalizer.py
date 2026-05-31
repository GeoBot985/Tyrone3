from __future__ import annotations

import re

from app.config import LAYOUT_COLUMN_GAP_THRESHOLD, LAYOUT_SHORT_LINE_MAX


def _normalize_plain(lines: list[str]) -> str:
    return "\n".join(line.rstrip() for line in lines if line.strip()).strip()


def _is_table_like(lines: list[str]) -> bool:
    candidate_lines = [line for line in lines if line.strip()]
    if len(candidate_lines) < 3:
        return False
    spaced = sum(1 for line in candidate_lines if re.search(r"\S\s{2,}\S", line))
    piped = sum(1 for line in candidate_lines if line.count("|") >= 2)
    return spaced >= max(2, len(candidate_lines) // 2) or piped >= max(2, len(candidate_lines) // 2)


def _normalize_table_like(lines: list[str]) -> str:
    normalized = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        normalized.append(re.sub(r"[ \t]{2,}", " | ", stripped))
    return "\n".join(normalized).strip()


def _is_likely_two_column(lines: list[str]) -> tuple[bool, int | None]:
    candidates = [line.rstrip("\n") for line in lines if line.strip()]
    if len(candidates) < 4:
        return False, None

    gap_positions = []
    short_lines = 0
    for line in candidates:
        if len(line.strip()) <= LAYOUT_SHORT_LINE_MAX:
            short_lines += 1
        match = re.search(rf"\s{{{LAYOUT_COLUMN_GAP_THRESHOLD},}}", line)
        if match:
            gap_positions.append(match.start())

    if short_lines < len(candidates) // 2 or len(gap_positions) < len(candidates) // 2:
        return False, None

    dominant_gap = min(gap_positions)
    clustered = sum(1 for gap in gap_positions if abs(gap - dominant_gap) <= 6)
    if clustered < len(gap_positions) // 2:
        return False, None
    return True, dominant_gap


def _reflow_two_column(lines: list[str], split_at: int) -> str:
    left_lines = []
    right_lines = []
    for line in lines:
        if not line.strip():
            continue
        if len(line) > split_at and re.search(rf"\s{{{LAYOUT_COLUMN_GAP_THRESHOLD},}}", line):
            left = line[:split_at].strip()
            right = line[split_at:].strip()
            if left:
                left_lines.append(left)
            if right:
                right_lines.append(right)
        else:
            left_lines.append(line.strip())
    return "\n".join(left_lines + ([""] if right_lines else []) + right_lines).strip()


def normalize_layout_aware_text(text: str, file_type: str) -> dict:
    lines = text.splitlines()
    warnings: list[str] = []

    if file_type == "xlsx":
        return {
            "text": _normalize_plain(lines),
            "layout_mode": "row_preserved",
            "warnings": warnings,
            "applied": False,
            "heuristic": "spreadsheet_row_preserved",
        }

    is_two_column, split_at = _is_likely_two_column(lines)
    if is_two_column and split_at is not None:
        warnings.append("Likely two-column layout detected; applied conservative left-then-right reflow.")
        return {
            "text": _reflow_two_column(lines, split_at),
            "layout_mode": "column_reflow",
            "warnings": warnings,
            "applied": True,
            "heuristic": "dominant_internal_gap",
        }

    if _is_table_like(lines):
        warnings.append("Table-like spacing detected; preserved row boundaries with spacing normalization.")
        return {
            "text": _normalize_table_like(lines),
            "layout_mode": "table_like",
            "warnings": warnings,
            "applied": True,
            "heuristic": "table_spacing_pattern",
        }

    return {
        "text": _normalize_plain(lines),
        "layout_mode": "plain",
        "warnings": warnings,
        "applied": False,
        "heuristic": "none",
    }
