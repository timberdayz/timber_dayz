"""Backend router package.

Keep package-level imports deterministic across runtime and pytest collection.
Cloud sync has moved into the data-platform domain router; tests and callers
should prefer the real implementation module for monkeypatching.
"""

from backend.domains.data_platform.routers import cloud_sync

__all__ = ["cloud_sync"]
