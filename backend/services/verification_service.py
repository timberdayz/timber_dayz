from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.services.verification_state_store import VerificationStateStore


class VerificationService:
    """Shared verification state builder and transition helper."""

    def __init__(self, *, store: VerificationStateStore):
        self.store = store

    def raise_required(
        self,
        *,
        owner_type: str,
        owner_id: str,
        verification_type: str,
        phase: str,
        current_url: str | None,
        screenshot_url: str | None,
        message: str,
        account_id: str | None = None,
        store_name: str | None = None,
        expires_in_seconds: int = 300,
    ) -> dict:
        now = datetime.now(timezone.utc)
        payload = {
            "state": "verification_required",
            "verification_type": verification_type,
            "verification_id": uuid4().hex,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "phase": phase,
            "current_url": current_url,
            "screenshot_url": screenshot_url,
            "message": message,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=expires_in_seconds)).isoformat(),
            "attempt_count": 0,
            "account_id": account_id,
            "store_name": store_name,
        }
        return self.store.save(payload)

    def mark_submitted(self, *, verification_id: str) -> dict:
        return self.store.update_state(verification_id, "verification_submitted")

    def mark_retrying(self, *, verification_id: str) -> dict:
        return self.store.update_state(verification_id, "verification_retrying")

    def mark_resolved(self, *, verification_id: str) -> dict:
        return self.store.update_state(verification_id, "verification_resolved")

    def mark_failed(self, *, verification_id: str) -> dict:
        return self.store.update_state(verification_id, "verification_failed")
