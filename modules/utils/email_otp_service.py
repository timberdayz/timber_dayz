#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
邮箱 OTP 服务：从 IMAP 邮箱里自动提取验证码（OTP）。

说明：
- 仅做“读取 + 提取”用途，不发送邮件。
- 终端/日志输出避免使用 emoji 或特殊符号，保证 Windows 下稳定显示。
"""

from __future__ import annotations

import email
import email.message
import imaplib
import logging
import re
import time
from email.header import decode_header
from typing import Any, Dict, List, Optional, cast

logger = logging.getLogger(__name__)


EMAIL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "163.com": {
        "imap_server": "imap.163.com",
        "imap_port": 993,
        "smtp_server": "smtp.163.com",
        "smtp_port": 587,
    },
    "qq.com": {
        "imap_server": "imap.qq.com",
        "imap_port": 993,
        "smtp_server": "smtp.qq.com",
        "smtp_port": 587,
    },
    "gmail.com": {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
    },
    "outlook.com": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp.office365.com",
        "smtp_port": 587,
    },
}


class EmailOTPService:
    def __init__(self, email_config: Dict[str, Any]) -> None:
        self.email_config = email_config
        self.email = email_config.get("email", "")
        self.password = email_config.get("password", "")
        self.imap_server = email_config.get("imap_server", "")
        self.imap_port = email_config.get("imap_port", 993)

        self.otp_keywords = [
            "验证码",
            "verification code",
            "otp",
            "one-time password",
            "security code",
            "authentication code",
            "login code",
            "shopee",
            "amazon",
            "lazada",
            "妙手",
            "erp",
        ]

        self.otp_patterns = [
            r"\b\d{4,6}\b",
            r"[A-Z0-9]{4,8}",
            r"\b\d{3}-\d{3}\b",
            r"\b\d{4}-\d{4}\b",
        ]

    def connect_imap(self) -> Optional[imaplib.IMAP4_SSL]:
        try:
            logger.info(f"[LINK] Connect IMAP {self.imap_server}:{self.imap_port}")
            imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            imap.login(self.email, self.password)
            logger.info("[OK] IMAP connected")
            return imap
        except Exception as exc:
            logger.error(f"[FAIL] IMAP connect failed: {exc}")
            return None

    def search_otp_emails(self, imap: imaplib.IMAP4_SSL, minutes_back: int = 10) -> List[str]:
        try:
            imap.select("INBOX")
            search_criteria = f'(SINCE "{self._get_date_string(minutes_back)}")'
            logger.info(f"[SEARCH] Search mail: {search_criteria}")

            status, messages = imap.search(None, search_criteria)
            if status != "OK":
                logger.error(f"[FAIL] IMAP search failed: {status}")
                return []

            email_ids = messages[0].split()
            logger.info(f"[MAIL] Found {len(email_ids)} emails")

            otp_email_ids: List[str] = []
            for email_id in email_ids:
                try:
                    status, msg_data = imap.fetch(email_id, "(BODY[HEADER])")
                    if status != "OK":
                        continue

                    if not msg_data:
                        continue
                    first = msg_data[0]
                    if not isinstance(first, tuple) or len(first) < 2:
                        continue
                    raw_bytes = first[1]
                    if not isinstance(raw_bytes, (bytes, bytearray)):
                        continue
                    email_message = email.message_from_bytes(cast(bytes, raw_bytes))
                    subject = self._decode_header(email_message.get("subject") or "")
                    if self._contains_otp_keywords(subject):
                        otp_email_ids.append(email_id.decode())
                        logger.info(f"[OK] OTP keyword hit subject: {subject}")
                except Exception as exc:
                    logger.debug(f"Process email {email_id!r} failed: {exc}")
                    continue

            logger.info(f"[MAIL] OTP candidate emails: {len(otp_email_ids)}")
            return otp_email_ids
        except Exception as exc:
            logger.error(f"[FAIL] Search OTP emails failed: {exc}")
            return []

    def extract_otp_from_email(self, imap: imaplib.IMAP4_SSL, email_id: str) -> Optional[str]:
        try:
            status, msg_data = imap.fetch(email_id, "(RFC822)")
            if status != "OK":
                logger.error(f"[FAIL] Fetch mail content failed: {status}")
                return None

            if not msg_data:
                return None
            first = msg_data[0]
            if not isinstance(first, tuple) or len(first) < 2:
                return None
            raw_bytes = first[1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                return None
            email_message = email.message_from_bytes(cast(bytes, raw_bytes))
            body = self._get_email_body(email_message)
            if not body:
                logger.warning("[WARN] Email body is empty")
                return None

            otp = self._extract_otp_from_text(body)
            if otp:
                logger.info(f"[OK] Extracted OTP: {otp}")
                return otp

            logger.warning("[WARN] OTP not found in email")
            return None
        except Exception as exc:
            logger.error(f"[FAIL] Extract OTP failed: {exc}")
            return None

    def get_latest_otp(self, minutes_back: int = 10, max_attempts: int = 3) -> Optional[str]:
        for attempt in range(max_attempts):
            try:
                logger.info(f"[RETRY] Attempt {attempt + 1}/{max_attempts} to fetch OTP")

                imap = self.connect_imap()
                if not imap:
                    continue

                try:
                    otp_email_ids = self.search_otp_emails(imap, minutes_back)
                    if not otp_email_ids:
                        logger.warning("[WARN] No OTP emails found")
                        time.sleep(5)
                        continue

                    latest_email_id = otp_email_ids[-1]
                    otp = self.extract_otp_from_email(imap, latest_email_id)
                    if otp:
                        return otp
                finally:
                    try:
                        imap.close()
                        imap.logout()
                    except Exception:
                        pass

                if attempt < max_attempts - 1:
                    logger.info("[WAIT] Sleep 10 seconds before retry")
                    time.sleep(10)
            except Exception as exc:
                logger.error(f"[FAIL] Attempt {attempt + 1} failed: {exc}")
                if attempt < max_attempts - 1:
                    time.sleep(5)

        logger.error("[FAIL] All attempts failed")
        return None

    def _get_date_string(self, minutes_back: int) -> str:
        import datetime

        now = datetime.datetime.now()
        past_time = now - datetime.timedelta(minutes=minutes_back)
        return past_time.strftime("%d-%b-%Y")

    def _decode_header(self, header: str) -> str:
        try:
            decoded_parts = decode_header(header)
            decoded_string = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding, errors="ignore")
                    else:
                        decoded_string += part.decode("utf-8", errors="ignore")
                else:
                    decoded_string += str(part)
            return decoded_string
        except Exception as exc:
            logger.debug(f"Decode header failed: {exc}")
            return header

    def _contains_otp_keywords(self, text: str) -> bool:
        text_lower = text.lower()
        for keyword in self.otp_keywords:
            if keyword.lower() in text_lower:
                return True
        return False

    def _get_email_body(self, email_message: email.message.Message) -> str:
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, (bytes, bytearray)):
                            body += bytes(payload).decode(errors="ignore")
                    except Exception:
                        pass
        else:
            try:
                payload = email_message.get_payload(decode=True)
                if isinstance(payload, (bytes, bytearray)):
                    body = bytes(payload).decode(errors="ignore")
            except Exception:
                pass
        return body

    def _extract_otp_from_text(self, text: str) -> Optional[str]:
        for pattern in self.otp_patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[-1]
        return None


def create_email_otp_service(account_config: Dict[str, Any]) -> Optional[EmailOTPService]:
    """
    Create EmailOTPService from an account config.

    Expected keys:
    - email
    - email_password (preferred) or password
    - imap_server, imap_port (optional)
    """
    try:
        email_value = account_config.get("email", "")
        password_value = account_config.get("email_password", "") or account_config.get("password", "")

        email_config: Dict[str, Any] = {
            "email": email_value,
            "password": password_value,
            "imap_server": account_config.get("imap_server", ""),
            "imap_port": account_config.get("imap_port", 993),
            "smtp_server": account_config.get("smtp_server", ""),
            "smtp_port": account_config.get("smtp_port", 587),
        }

        if not email_config["email"] or not email_config["password"]:
            logger.warning("[WARN] Email config incomplete (email/password required)")
            return None

        if not email_config["imap_server"]:
            email_domain = email_config["email"].split("@")[-1].lower()
            defaults = EMAIL_CONFIGS.get(email_domain)
            if not defaults:
                logger.warning(f"[WARN] Unknown email domain: {email_domain}")
                return None
            email_config["imap_server"] = defaults["imap_server"]
            email_config["imap_port"] = defaults["imap_port"]

        return EmailOTPService(email_config)
    except Exception as exc:
        logger.error(f"[FAIL] Create EmailOTPService failed: {exc}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[TEST] EmailOTPService self-check")

    test_config = {
        "email": "test@163.com",
        "password": "test_password",
        "imap_server": "imap.163.com",
        "imap_port": 993,
    }

    service = EmailOTPService(test_config)
    print(f"[OK] Service created for {service.email}")

    test_text = "Your verification code is 123456, valid for 5 minutes."
    otp = service._extract_otp_from_text(test_text)
    print(f"[OK] Extract OTP: {otp}")
