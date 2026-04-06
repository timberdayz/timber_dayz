#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database package exports.

Keep this module as a thin wrapper over `schema.py` so import sites can use:

    from modules.core.db import CollectionConfig

without maintaining a fragile hand-curated export list.
"""

from .schema import *  # noqa: F401,F403

__all__ = [name for name in globals() if not name.startswith("_")]
