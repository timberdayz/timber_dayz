from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class VerificationStateStore:
    """Verification state store with optional JSON-file persistence."""

    def __init__(self, *, storage_path: str | Path | None = None):
        self.storage_path = Path(storage_path) if storage_path else None
        self._lock = threading.RLock()
        self._items: Dict[str, dict] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._items = {
                    str(key): dict(value)
                    for key, value in data.items()
                    if isinstance(value, dict)
                }
        except Exception:
            # Keep the in-memory snapshot if the file is unreadable.
            return

    def _save_to_disk(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._items, f, ensure_ascii=False, indent=2)
        temp_path.replace(self.storage_path)

    def save(self, payload: dict) -> dict:
        verification_id = str(payload["verification_id"])
        with self._lock:
            self._load_from_disk()
            self._items[verification_id] = dict(payload)
            self._save_to_disk()
            return dict(self._items[verification_id])

    def get(self, verification_id: str) -> Optional[dict]:
        with self._lock:
            self._load_from_disk()
            item = self._items.get(str(verification_id))
            return dict(item) if item else None

    def update_state(
        self,
        verification_id: str,
        state: str,
        *,
        increment_attempt: bool = False,
        extra_updates: Optional[dict] = None,
    ) -> dict:
        with self._lock:
            self._load_from_disk()
            item = dict(self._items[str(verification_id)])
            item["state"] = state
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            if increment_attempt:
                item["attempt_count"] = int(item.get("attempt_count", 0) or 0) + 1
            if extra_updates:
                item.update(extra_updates)
            self._items[str(verification_id)] = item
            self._save_to_disk()
            return dict(item)
