"""Dialect-portable JSON scalar extraction (M7).

``json_text(col, "key")`` reads the scalar at top-level ``key`` of a JSON-text
column and compiles to the right SQL per backend:

- SQLite      → ``json_extract(col, '$.key')``
- PostgreSQL  → ``CAST(col AS jsonb) ->> 'key'``

One construct so the alert queries (sort/filter by ``snapshot`` fields) work
unchanged on both. The value is text; wrap in ``cast(..., Float)`` for numeric
comparisons exactly as before.
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement


class json_text(ColumnElement):  # noqa: N801 — SQL-construct naming (lowercase like func.*)
    """Portable ``col -> 'key'`` scalar extraction. See module docstring."""

    inherit_cache = True
    type = String()

    def __init__(self, col: ColumnElement, key: str) -> None:
        # keys are hard-coded literals in call sites; validate anyway since the
        # key is interpolated into SQL text (no bound param for a JSON path).
        if not key or not key.replace("_", "").isalnum():
            raise ValueError(f"json_text key must be alphanumeric/underscore: {key!r}")
        self.col = col
        self.key = key


@compiles(json_text)
def _json_text_default(element: json_text, compiler, **kw) -> str:
    # Default covers SQLite (and any dialect without an override).
    return f"json_extract({compiler.process(element.col, **kw)}, '$.{element.key}')"


@compiles(json_text, "postgresql")
def _json_text_postgresql(element: json_text, compiler, **kw) -> str:
    return f"(CAST({compiler.process(element.col, **kw)} AS jsonb) ->> '{element.key}')"
