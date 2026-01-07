"""
统一验证码模块

支持多种验证码通道：
- 邮箱OTP（Email）
- 短信OTP（SMS，预留）
- TOTP（预留）
"""

from .verification_service import VerificationCodeService
from .email_otp_client import EmailOTPClient

__all__ = [
    "VerificationCodeService",
    "EmailOTPClient",
]
