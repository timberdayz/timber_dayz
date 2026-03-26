from __future__ import annotations

from typing import Dict, Optional


class VerificationStateStore:
    """In-memory verification state store for recorder/test/task workflows."""

    def __init__(self):
        self._items: Dict[str, dict] = {}

    def save(self, payload: dict) -> dict:
        verification_id = str(payload["verification_id"])
        self._items[verification_id] = dict(payload)
        return self._items[verification_id]

    def get(self, verification_id: str) -> Optional[dict]:
        item = self._items.get(str(verification_id))
        return dict(item) if item else None

    def update_state(self, verification_id: str, state: str) -> dict:
        item = self._items[str(verification_id)]
        item["state"] = state
        return dict(item)
