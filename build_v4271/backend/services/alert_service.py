"""
告警服务：资源监控等超阈值时对接 Webhook / 钉钉 / 邮件

- 配置仅从环境变量读取，禁止硬编码敏感信息
- 告警冷却：同一类型在 N 分钟内只发一次
- 发送失败时重试上限 3 次并记录错误日志
"""

import os
import time
import asyncio
from typing import Optional, Dict, Any

import httpx
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 冷却 key -> 上次发送时间(epoch)
_cooldown: Dict[str, float] = {}
_cooldown_lock = asyncio.Lock()

# 从环境变量读取，禁止提交真实密钥
RESOURCE_ALERT_COOLDOWN_MINUTES = int(os.getenv("RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES", "5"))
ALERT_RETRY_MAX = 3
ALERT_HTTP_TIMEOUT = 10.0


async def _in_cooldown(alert_type: str) -> bool:
    """同一类型在冷却期内返回 True"""
    async with _cooldown_lock:
        last = _cooldown.get(alert_type, 0.0)
        return (time.time() - last) < (RESOURCE_ALERT_COOLDOWN_MINUTES * 60)


async def _mark_sent(alert_type: str) -> None:
    async with _cooldown_lock:
        _cooldown[alert_type] = time.time()


async def _send_webhook(url: str, body: Dict[str, Any]) -> bool:
    """发送 Webhook，失败重试最多 ALERT_RETRY_MAX 次"""
    for attempt in range(1, ALERT_RETRY_MAX + 1):
        try:
            async with httpx.AsyncClient(timeout=ALERT_HTTP_TIMEOUT) as client:
                r = await client.post(url, json=body)
                r.raise_for_status()
                return True
        except Exception as e:
            logger.warning(f"[Alert] Webhook 发送失败 (attempt {attempt}/{ALERT_RETRY_MAX}): {e}")
            if attempt < ALERT_RETRY_MAX:
                await asyncio.sleep(1.0 * attempt)
    logger.error(f"[Alert] Webhook 发送最终失败: {url}")
    return False


async def _send_dingtalk(webhook_url: str, token: str, body: Dict[str, Any]) -> bool:
    """钉钉机器人：优先 webhook_url，否则用 token 拼接 URL"""
    url = (webhook_url or "").strip()
    if not url and (token or "").strip():
        url = f"https://oapi.dingtalk.com/robot/send?access_token={(token or '').strip()}"
    if not url or url.startswith("YOUR_") or (token or "").strip() == "YOUR_DINGTALK_TOKEN":
        return False
    ding_body = {
        "msgtype": "text",
        "text": {"content": body.get("text", str(body))},
    }
    return await _send_webhook(url, ding_body)


async def send_resource_alert(
    alert_type: str,
    message: str,
    cpu_usage: Optional[float] = None,
    memory_usage: Optional[float] = None,
) -> None:
    """
    发送资源告警（带冷却与重试）。
    alert_type 建议: resource_cpu / resource_memory / resource_both
    """
    if await _in_cooldown(alert_type):
        logger.debug(f"[Alert] 告警冷却中，跳过: {alert_type}")
        return

    body = {
        "source": "xihong_erp_resource_monitor",
        "alert_type": alert_type,
        "message": message,
        "cpu_percent": cpu_usage,
        "memory_percent": memory_usage,
        "text": f"[资源告警] {message}",
    }

    sent = False
    # Webhook（通用）
    webhook_url = os.getenv("RESOURCE_MONITOR_WEBHOOK_URL", "").strip()
    if webhook_url and not webhook_url.startswith("YOUR_"):
        sent = await _send_webhook(webhook_url, body) or sent

    # 钉钉
    ding_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    ding_token = os.getenv("DINGTALK_ACCESS_TOKEN", "").strip()
    if ding_url or ding_token:
        sent = await _send_dingtalk(ding_url, ding_token, body) or sent

    # 邮件：仅当配置了 SMTP 时尝试（此处简化：仅记录日志，实际发邮件可接 smtplib）
    smtp_host = os.getenv("RESOURCE_MONITOR_SMTP_HOST", "").strip()
    if smtp_host and not smtp_host.startswith("YOUR_"):
        logger.info(f"[Alert] 邮件通道已配置，当前仅 Webhook/钉钉: {message}")

    if sent:
        await _mark_sent(alert_type)
