"""账号巡店就绪状态（**只读**）。

为什么要有这一份
----------------
「这个账号现在能不能巡店 / 会不会撞车」有**两处**要看：

1. CLI 体检脚本 ``scripts/check_account_readiness.py``
2. 巡店面板只读接口 ``GET /api/accounts/readiness``

两处各写一套判定 ⇒ 必然漂移（面板说"已首登"、体检说"未首登"，
或者面板漏了 machine_id 隔离这一项）。
所以**判据只此一份**，两边都从这里取。

本模块**不写库、不写盘**：只读 profile 目录与画像文件。

判定项
------
==================  ==========================================================
项                  判据
==================  ==========================================================
``logged_in``       profile 内存在 Chromium cookie 库
                    （``Default/Network/Cookies`` 或旧版 ``Default/Cookies``）
``has_device_profile``  ``<profile>/.device_profile.json`` 存在且版本可识别
``machine_id``      profile 的 ``Local State`` 里的
                    ``user_experience_metrics.machine_id``
``machine_id_isolated`` 上述值 == 按 account_id 确定性派生的账号专属值
``proxy_enabled``   出口 IP 是否已配（**提示项**，当前不强制）
==================  ==========================================================

为什么 machine_id 单独成项
--------------------------
Chromium 的 ``machine_id`` 来自 Windows MachineGuid ⇒ **同一台机器上所有 profile
必然相同** ⇒ 不隔离的话，平台一眼就能把这批账号认成"同一台电脑"。
这是「账号间不可关联」最容易漏、也最致命的一项。

依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md``（R8 及其设备画像小节）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from modules.utils.sessions.account_device_profile import (
    derive_machine_id,
    read_device_profile,
)


#: Chromium cookie 库的可能路径（新版 / 旧版）。
#:
#: 不能用「目录非空」判断登录态：Chromium 只要启动过一次（哪怕登录失败）
#: 就会写 ``Default/``、``Crashpad/`` 等 ⇒ 会把「没登录」误判成「有登录态」。
PROFILE_COOKIE_RELATIVE_PATHS = ("Default/Network/Cookies", "Default/Cookies")


def profile_contains_state(profile_path: Path | str) -> bool:
    """profile 里是否真的有 Chromium 写下的 cookie 库（= 人工首登过）。

    与采集侧 :func:`modules.apps.collection_center.runtime_session.runtime_profile_exists`
    **同源** —— 采集侧那一份已经委托到这里，避免两处判定漂移。
    """
    root = Path(profile_path)
    try:
        return any((root / relative).exists() for relative in PROFILE_COOKIE_RELATIVE_PATHS)
    except OSError:
        return False


def read_profile_machine_id(profile_dir: Path | str) -> str:
    """读 profile 的 ``machine_id``（读不到 ⇒ 空串）。

    Chromium 把机器级标识写在 ``Local State`` 的
    ``user_experience_metrics.machine_id``。
    """
    path = Path(profile_dir) / "Local State"
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    metrics = payload.get("user_experience_metrics")
    if not isinstance(metrics, dict):
        return ""
    return str(metrics.get("machine_id") or "").strip()


def build_profile_state(
    profile_dir: Path | str,
    *,
    platform: str,
    account_id: str,
) -> Dict[str, Any]:
    """profile 目录的只读快照。

    Returns:
        ``logged_in`` / ``has_device_profile`` / ``machine_id`` /
        ``machine_id_isolated`` / ``device``（画像摘要，没有则 ``None``）/
        ``profile_exists``。
    """
    root = Path(profile_dir)
    device_payload = read_device_profile(root)
    machine_id = read_profile_machine_id(root)
    expected_machine_id = derive_machine_id(platform, account_id)

    device_summary: Optional[Dict[str, Any]] = None
    if device_payload:
        device = device_payload.get("device") or {}
        device_summary = {
            "os": device.get("os"),
            "browser": device.get("browser"),
            "browser_version": device.get("browser_version"),
            "locale": device.get("locale"),
            "timezone_id": device.get("timezone_id"),
            "viewport": device.get("viewport"),
        }

    return {
        "profile_exists": root.exists(),
        "logged_in": profile_contains_state(root),
        "has_device_profile": device_payload is not None,
        "machine_id": machine_id,
        "machine_id_isolated": bool(machine_id) and machine_id == expected_machine_id,
        "expected_machine_id": expected_machine_id,
        "device": device_summary,
    }


def build_account_readiness(
    platform: str,
    account_id: str,
    *,
    profiles_root: Optional[Path | str] = None,
    proxy_enabled: bool = False,
    display_name: str = "",
) -> Dict[str, Any]:
    """账号的巡店就绪状态（只读聚合）。

    Args:
        platform: 平台代码。
        account_id: 主账号 ID。
        profiles_root: profile 根目录覆盖（默认取 ``SessionManager`` 的仓库内路径）。
            **只换根目录，不换命名规则** —— 目录名仍由 ``SessionManager`` 给出
            （规则 B：``profiles/<平台>/<主账号ID净化后>``），避免两处各写一份净化逻辑。
        proxy_enabled: 该账号是否已配出口 IP（由调用方从库里取，**不含凭据**）。
        display_name: 展示名（仅回显，不参与判定）。

    Returns:
        见模块文档的「判定项」表；另含 ``platform`` / ``account_id`` /
        ``display_name`` / ``proxy_enabled``。
    """
    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager()
    default_dir = manager.get_persistent_profile_path(platform, account_id)
    if profiles_root is None:
        profile_dir = default_dir
    else:
        relative = default_dir.relative_to(manager.persistent_profiles_path)
        profile_dir = Path(profiles_root) / relative

    state = build_profile_state(profile_dir, platform=platform, account_id=account_id)

    return {
        "platform": platform,
        "account_id": account_id,
        "display_name": display_name or account_id,
        "profile_dir": str(profile_dir),
        "proxy_enabled": bool(proxy_enabled),
        **state,
    }


def readiness_summary(payload: Dict[str, Any]) -> str:
    """一行话摘要（给日志 / CLI 用）。"""
    bits: list[str] = []
    bits.append("已首登" if payload.get("logged_in") else "未首登")
    bits.append("画像已分配" if payload.get("has_device_profile") else "画像未分配")
    bits.append(
        "machine_id 已隔离" if payload.get("machine_id_isolated") else "machine_id 未隔离"
    )
    bits.append("已配出口" if payload.get("proxy_enabled") else "未配出口")
    return " · ".join(bits)
