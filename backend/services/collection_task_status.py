from __future__ import annotations

"""
Collection task status SSOT.

Rationale:
- Avoid duplicated hard-coded status strings across routers/executor/services.
- Keep semantics consistent for API responses, DB persistence, and WS events.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionTaskStatus:
    # Lifecycle
    PENDING: str = "pending"
    QUEUED: str = "queued"
    RUNNING: str = "running"

    # Terminal
    COMPLETED: str = "completed"
    PARTIAL_SUCCESS: str = "partial_success"
    FAILED: str = "failed"
    CANCELLED: str = "cancelled"

    # Verification / pauses
    VERIFICATION_REQUIRED: str = "verification_required"
    VERIFICATION_SUBMITTED: str = "verification_submitted"
    MANUAL_INTERVENTION_REQUIRED: str = "manual_intervention_required"

    # Legacy / ambiguous (kept for compatibility; avoid introducing new usages)
    PAUSED: str = "paused"


STATUS = CollectionTaskStatus()

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.COMPLETED,
        STATUS.PARTIAL_SUCCESS,
        STATUS.FAILED,
        STATUS.CANCELLED,
    }
)

ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.PENDING,
        STATUS.QUEUED,
        STATUS.RUNNING,
        STATUS.VERIFICATION_REQUIRED,
        STATUS.VERIFICATION_SUBMITTED,
        STATUS.MANUAL_INTERVENTION_REQUIRED,
        STATUS.PAUSED,  # legacy
    }
)

PAUSE_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.VERIFICATION_REQUIRED,
        STATUS.MANUAL_INTERVENTION_REQUIRED,
        STATUS.PAUSED,  # legacy
    }
)


def is_terminal(status: str | None) -> bool:
    return str(status or "").strip() in TERMINAL_STATUSES


def is_pause(status: str | None) -> bool:
    return str(status or "").strip() in PAUSE_STATUSES

