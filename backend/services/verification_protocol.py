from __future__ import annotations

from typing import Any


MANUAL_COMPLETED_TOKEN = "__manual_completed__"
MANUAL_CONTINUE_TYPES = frozenset(
    {"slide_captcha", "manual_verification", "manual_intervention"}
)
OTP_TYPES = frozenset({"otp", "sms", "email_code"})


def verification_input_mode(verification_type: str | None) -> str:
    normalized = str(verification_type or "").strip().lower()
    if normalized in MANUAL_CONTINUE_TYPES:
        return "manual_continue"
    return "code_entry"


def extract_resume_submission(
    *,
    captcha_code: str | None = None,
    otp: str | None = None,
    manual_completed: bool | None = None,
) -> tuple[str | None, dict[str, Any]]:
    captcha = (captcha_code or "").strip()
    otp_value = (otp or "").strip()
    manual = bool(manual_completed)

    filled_count = sum(1 for value in (captcha, otp_value) if value) + (1 if manual else 0)
    if filled_count != 1:
        return None, {}

    if captcha:
        return captcha, {"captcha_code": captcha}
    if otp_value:
        return otp_value, {"otp": otp_value}
    return MANUAL_COMPLETED_TOKEN, {"manual_completed": True}


def apply_verification_result_to_params(
    params: dict[str, Any],
    *,
    verification_type: str | None,
    value: str | None,
) -> None:
    target = params.setdefault("params", {})
    normalized_type = str(verification_type or "").strip().lower()
    if normalized_type in OTP_TYPES:
        target["otp"] = value
        target.pop("captcha_code", None)
        target.pop("manual_completed", None)
        return
    if normalized_type in MANUAL_CONTINUE_TYPES:
        target["manual_completed"] = value == MANUAL_COMPLETED_TOKEN
        target.pop("captcha_code", None)
        target.pop("otp", None)
        return
    target["captcha_code"] = value
    target.pop("otp", None)
    target.pop("manual_completed", None)
