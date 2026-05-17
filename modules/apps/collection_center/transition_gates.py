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


@dataclass(frozen=True)
class LoginGateEvidence:
    detector_status: str
    detector_confidence: float
    auth_cookies_present: bool
    login_form_visible: bool
    logged_in_markers_present: bool
    current_url: Optional[str] = None
    matched_signal: Optional[str] = None
    detected_by: Optional[str] = None


def evaluate_login_gate_evidence(
    *,
    platform: str,
    evidence: LoginGateEvidence,
) -> GateResult:
    normalized_status = str(evidence.detector_status or "").strip().lower()
    normalized_url = str(evidence.current_url or "").strip().lower()
    normalized_platform = str(platform or "").strip().lower()
    login_page_markers = ("/login", "/signin", "/account/login", "redirect=")

    if evidence.login_form_visible:
        return GateResult(
            stage="login_gate",
            status=GateStatus.FAILED,
            reason="login form visible",
            confidence=evidence.detector_confidence,
            current_url=evidence.current_url,
            matched_signal=evidence.matched_signal,
        )

    if evidence.logged_in_markers_present:
        return GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="logged-in markers confirmed",
            confidence=evidence.detector_confidence,
            current_url=evidence.current_url,
            matched_signal=evidence.matched_signal,
        )

    if (
        normalized_status == "logged_in"
        and evidence.auth_cookies_present
        and not any(marker in normalized_url for marker in login_page_markers)
    ):
        if normalized_platform == "tiktok" and "/homepage" not in normalized_url and "/compass/" not in normalized_url:
            return GateResult(
                stage="login_gate",
                status=GateStatus.FAILED,
                reason="tiktok cookie-only session missing seller target",
                confidence=evidence.detector_confidence,
                current_url=evidence.current_url,
                matched_signal=evidence.matched_signal,
            )
        return GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="cookie-backed session confirmed",
            confidence=evidence.detector_confidence,
            current_url=evidence.current_url,
            matched_signal=evidence.matched_signal,
        )

    if normalized_status == "logged_in" and evidence.detector_confidence >= 0.7:
        return GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="login confirmed",
            confidence=evidence.detector_confidence,
            current_url=evidence.current_url,
            matched_signal=evidence.matched_signal,
        )

    return GateResult(
        stage="login_gate",
        status=GateStatus.FAILED,
        reason="login not confirmed",
        confidence=evidence.detector_confidence,
        current_url=evidence.current_url,
        matched_signal=evidence.matched_signal,
    )


def evaluate_login_ready(
    *,
    status: str,
    confidence: float,
    current_url: Optional[str] = None,
    matched_signal: Optional[str] = None,
    detected_by: Optional[str] = None,
) -> GateResult:
    normalized = str(status or "").strip().lower()
    normalized_detector = str(detected_by or "").strip().lower()
    evidence = LoginGateEvidence(
        detector_status=status,
        detector_confidence=confidence,
        auth_cookies_present=normalized == "logged_in" and normalized_detector == "cookie",
        login_form_visible=normalized == "not_logged_in" and normalized_detector == "element",
        logged_in_markers_present=normalized == "logged_in" and normalized_detector == "element",
        current_url=current_url,
        matched_signal=matched_signal,
        detected_by=detected_by,
    )
    return evaluate_login_gate_evidence(platform="generic", evidence=evidence)


def _allows_missing_export_file(
    *,
    component_name: Optional[str] = None,
    success_message: Optional[str] = None,
) -> bool:
    normalized_component = str(component_name or "").strip().lower()
    normalized_message = str(success_message or "").strip().lower()

    if normalized_component != "tiktok/services_agent_export":
        return False

    return "no exportable agent service data" in normalized_message or "暂无数据" in normalized_message


def evaluate_export_complete(
    *,
    file_path: Optional[str],
    component_name: Optional[str] = None,
    success_message: Optional[str] = None,
) -> GateResult:
    if not file_path:
        if _allows_missing_export_file(
            component_name=component_name,
            success_message=success_message,
        ):
            return GateResult(
                stage="export",
                status=GateStatus.READY,
                reason="successful no-data export without file",
                matched_signal="no_file_success",
            )
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


def evaluate_navigation_ready(
    *,
    current_url: Optional[str],
    expected_url: Optional[str] = None,
    target_marker_visible: bool = False,
) -> GateResult:
    current = str(current_url or "").strip()
    expected = str(expected_url or "").strip()

    if expected and expected not in current:
        return GateResult(
            stage="navigation",
            status=GateStatus.FAILED,
            reason="target url not reached",
            current_url=current or None,
        )

    if not target_marker_visible:
        return GateResult(
            stage="navigation",
            status=GateStatus.FAILED,
            reason="target marker not visible",
            current_url=current or None,
        )

    return GateResult(
        stage="navigation",
        status=GateStatus.READY,
        reason="navigation confirmed",
        current_url=current or None,
        matched_signal="url_and_marker" if expected else "marker_visible",
    )


def evaluate_date_picker_ready(
    *,
    value_applied: bool = False,
    panel_closed: bool = False,
) -> GateResult:
    if value_applied:
        return GateResult(
            stage="date_picker",
            status=GateStatus.READY,
            reason="date picker value applied",
            matched_signal="value_applied",
        )

    if panel_closed:
        return GateResult(
            stage="date_picker",
            status=GateStatus.READY,
            reason="date picker panel closed",
            matched_signal="panel_closed",
        )

    return GateResult(
        stage="date_picker",
        status=GateStatus.FAILED,
        reason="date picker state not confirmed",
    )


def evaluate_filters_ready(
    *,
    results_refreshed: bool = False,
    filter_value_applied: bool = False,
) -> GateResult:
    if results_refreshed:
        return GateResult(
            stage="filters",
            status=GateStatus.READY,
            reason="filter results refreshed",
            matched_signal="results_refreshed",
        )

    if filter_value_applied:
        return GateResult(
            stage="filters",
            status=GateStatus.READY,
            reason="filter value applied",
            matched_signal="filter_value_applied",
        )

    return GateResult(
        stage="filters",
        status=GateStatus.FAILED,
        reason="filter state not confirmed",
    )
