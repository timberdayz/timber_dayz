from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator


class VerificationResumeRequest(BaseModel):
    captcha_code: Optional[str] = None
    otp: Optional[str] = None

    @model_validator(mode="after")
    def validate_exactly_one_value(self):
        captcha = (self.captcha_code or "").strip()
        otp = (self.otp or "").strip()
        filled = [value for value in (captcha, otp) if value]
        if len(filled) != 1:
            raise ValueError("exactly one of captcha_code or otp is required")
        self.captcha_code = captcha or None
        self.otp = otp or None
        return self
