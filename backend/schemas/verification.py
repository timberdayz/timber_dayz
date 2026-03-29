from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator


class VerificationResumeRequest(BaseModel):
    captcha_code: Optional[str] = None
    otp: Optional[str] = None
    manual_completed: Optional[bool] = None

    @model_validator(mode="after")
    def validate_exactly_one_value(self):
        captcha = (self.captcha_code or "").strip()
        otp = (self.otp or "").strip()
        manual_completed = bool(self.manual_completed)
        filled_count = sum(1 for value in (captcha, otp) if value) + (1 if manual_completed else 0)
        if filled_count != 1:
            raise ValueError("exactly one of captcha_code, otp, or manual_completed is required")
        self.captcha_code = captcha or None
        self.otp = otp or None
        self.manual_completed = True if manual_completed else None
        return self
