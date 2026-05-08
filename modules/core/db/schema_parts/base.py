from __future__ import annotations

"""
Compatibility exports for the unified ORM schema.

Repository constraint: SQLAlchemy Base must be defined only in `modules/core/db/schema.py`.
Schema part modules may import `Base` / `JSON_COMPAT` from here for convenience.
"""

from ..schema import Base, JSON_COMPAT  # noqa: F401

