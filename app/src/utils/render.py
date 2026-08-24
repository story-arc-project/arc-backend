from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any


def render_experience_content(content: Mapping[str, Any]) -> str:
    """
    Render an experience's structured content into human-readable text
    suitable for LLM input.

    The database representation remains unchanged. This function only
    creates the textual representation used by AI analysis.

    Examples
    --------
    Input:
        {
            "title": "미술사 연구",
            "tags": ["미술사", "소논문", "무리요"],
            "research-paper": {
                "연구 기간": {
                    "start": "2024-10",
                    "end": "2024-12",
                }
            },
        }

    Output:
        제목: 미술사 연구
        tags: 미술사, 소논문, 무리요
        research-paper:
        연구 기간: 2024-10 ~ 2024-12

    Notes
    -----
    - None / empty values are omitted.
    - Lists are rendered as comma-separated natural text.
    - Dictionaries are rendered recursively.
    - {"start": ..., "end": ...} is rendered as a range.
    - Boolean values are rendered as Korean natural language.
    - JSON/Python representation is never used.
    """
    if not isinstance(content, Mapping):
        raise TypeError(
            f"Experience content must be a mapping, got {type(content).__name__}"
        )

    lines: list[str] = []

    for key, value in content.items():
        if _is_empty(value):
            continue

        label = _format_label(key)

        # The title is generally more natural as "제목".
        if key == "title":
            label = "제목"

        rendered = _render_field(label, value)

        if rendered:
            lines.append(rendered)

    return "\n".join(lines)


def _render_field(label: str, value: Any, indent: int = 0) -> str:
    """
    Render one field.

    Scalar:
        tags: 미술사

    List:
        tags: 미술사, 소논문, 무리요

    Mapping:
        research-paper:
        연구 기간: 2024-10 ~ 2024-12
    """
    prefix = " " * indent

    if _is_empty(value):
        return ""

    if isinstance(value, Mapping):
        # A mapping containing start/end is treated as a range.
        range_text = _render_range(value)

        if range_text:
            return f"{prefix}{label}: {range_text}"

        lines: list[str] = [f"{prefix}{label}:"]

        for key, child in value.items():
            if _is_empty(child):
                continue

            child_label = _format_label(key)
            rendered = _render_field(
                child_label,
                child,
                indent=indent + 2,
            )

            if rendered:
                lines.append(rendered)

        # Don't output "foo:" when every child was empty.
        if len(lines) == 1:
            return ""

        return "\n".join(lines)

    if _is_sequence(value):
        rendered_items = [
            _render_value(item)
            for item in value
            if not _is_empty(item)
        ]

        rendered_items = [
            item
            for item in rendered_items
            if item
        ]

        if not rendered_items:
            return ""

        return f"{prefix}{label}: {', '.join(rendered_items)}"

    return f"{prefix}{label}: {_render_value(value)}"


def _render_value(value: Any) -> str:
    """
    Convert an individual value into human-readable text.

    This function intentionally never calls repr(), str(dict), or
    json.dumps() for structured values.
    """
    if _is_empty(value):
        return ""

    if isinstance(value, Mapping):
        range_text = _render_range(value)

        if range_text:
            return range_text

        parts: list[str] = []

        for key, child in value.items():
            if _is_empty(child):
                continue

            rendered = _render_value(child)

            if rendered:
                parts.append(
                    f"{_format_label(key)}: {rendered}"
                )

        return ", ".join(parts)

    if _is_sequence(value):
        items = [
            _render_value(item)
            for item in value
            if not _is_empty(item)
        ]

        return ", ".join(
            item
            for item in items
            if item
        )

    if isinstance(value, bool):
        return "예" if value else "아니오"

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Enum):
        return str(value.value)

    return str(value).strip()


def _render_range(value: Mapping[str, Any]) -> str | None:
    """
    Render common start/end structures.

    Examples:
        {"start": "2024-10", "end": "2024-12"}
            -> "2024-10 ~ 2024-12"

        {"start": "2024-10"}
            -> "2024-10"

        {"end": "2024-12"}
            -> "2024-12"

    Returns None when the mapping is not a range.
    """
    if "start" not in value and "end" not in value:
        return None

    start = value.get("start")
    end = value.get("end")

    start_empty = _is_empty(start)
    end_empty = _is_empty(end)

    if start_empty and end_empty:
        return None

    if not start_empty and not end_empty:
        return f"{_render_value(start)} ~ {_render_value(end)}"

    if not start_empty:
        return _render_value(start)

    return _render_value(end)


def _format_label(key: Any) -> str:
    """
    Convert an internal field key into readable text.

    Examples:
        "research_period" -> "research period"
        "research-paper"  -> "research paper"
        "tags"            -> "tags"

    Korean labels are preserved.
    """
    label = str(key).strip()

    if not label:
        return ""

    # Convert common machine-oriented separators to spaces.
    label = label.replace("_", " ")
    label = label.replace("-", " ")

    # Avoid accidental repeated whitespace.
    return " ".join(label.split())


def _is_sequence(value: Any) -> bool:
    """
    Return True for list-like values but not strings/bytes.
    """
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _is_empty(value: Any) -> bool:
    """
    Determine whether a value should be omitted from the rendered text.

    Empty strings, None, empty collections, and whitespace-only strings
    are omitted. False and 0 are intentionally NOT considered empty.
    """
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, Mapping):
        return not any(
            not _is_empty(child)
            for child in value.values()
        )

    if _is_sequence(value):
        return not any(
            not _is_empty(item)
            for item in value
        )

    return False