from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class GateStatus(str, Enum):
    READY = "ready"
    PENDING_VERIFICATION = "pending_verification"
    FAILED = "failed"


@dataclass
class GateResult:
    stage: str
    status: GateStatus
    reason: str
    confidence: float = 0.0
    current_url: Optional[str] = None
    matched_signal: Optional[str] = None
    screenshot_path: Optional[str] = None


def evaluate_login_ready(
    *,
    status: str,
    confidence: float,
    current_url: Optional[str] = None,
    matched_signal: Optional[str] = None,
) -> GateResult:
    normalized = str(status or "").strip().lower()
    if normalized == "logged_in" and confidence >= 0.7:
        return GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="login confirmed",
            confidence=confidence,
            current_url=current_url,
            matched_signal=matched_signal,
        )

    return GateResult(
        stage="login_gate",
        status=GateStatus.FAILED,
        reason="login not confirmed",
        confidence=confidence,
        current_url=current_url,
        matched_signal=matched_signal,
    )


def evaluate_export_complete(*, file_path: Optional[str]) -> GateResult:
    if not file_path:
        return GateResult(
            stage="export",
            status=GateStatus.FAILED,
            reason="missing file path",
        )

    target = Path(file_path)
    if not target.exists():
        return GateResult(
            stage="export",
            status=GateStatus.FAILED,
            reason="download file missing",
        )

    if target.stat().st_size <= 0:
        return GateResult(
            stage="export",
            status=GateStatus.FAILED,
            reason="download file empty",
        )

    return GateResult(
        stage="export",
        status=GateStatus.READY,
        reason="download file confirmed",
        matched_signal="file_exists",
    )
