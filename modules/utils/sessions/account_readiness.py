"""账号巡店就绪状态（**只读**）。

为什么要有这一份
-----------------

「这个账号现在能不能巡店」有**两处**要看：

1. CLI 体检脚本 ``scripts/check_account_readiness.py``
2. 巡店面板只读接口 ``GET /api/accounts/readiness``

两处各写一套判定 ⇒ 必然漂移（面板说"已首登"、体检说"未首登"）。
所以**判据只此一份**，两边都从这里取。

本模块**不写库、不写盘**：只读 profile 目录。

判定项
------
==================  ==========================================================
项                  判据
==================  ==========================================================
``profile_exists``  profile 目录存在（登录态的载体）
``logged_in``       profile 内存在 Chromium cookie 库
                    （``Default/Network/Cookies`` 或旧版 ``Default/Cookies``）
``proxy_enabled``   出口 IP 是否已配（**提示项**，当前不强制）
==================  ==========================================================

为什么只有这三项
----------------

2026-11-14 方向修订后，**不再检查「设备指纹隔离」**，理由（实测见计划文档）：

* 平台做账号关联看的是**账号状态层**（cookie / localStorage / 缓存 / 登录态 /
  平台自己的设备令牌）—— 这层由「每个账号一个独立 profile 目录」天然隔开；
* **设备指纹层**（GPU/渲染器、CPU 核数、字体、canvas）同机必然相同，且
  **同型号同配置的机器大量重复** ⇒ 平台不可能拿它当"同一台电脑"的判据；
* Chromium 的 ``machine_id`` **网页读不到** ⇒ 平台看不到它，检查它没有意义。

⇒ 账号之间真正要分开的是**状态层**，而这一层不由「画像」保证，而由
「**一个账号一个 profile 目录**」保证 —— 那在建号时检查（目录不撞车），
不在运行时检查。

依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md``（R8）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


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
        return any(
            (root / relative).exists() for relative in PROFILE_COOKIE_RELATIVE_PATHS
        )
    except OSError:
        return False


def build_profile_state(
    profile_dir: Path | str,
) -> Dict[str, Any]:
    """profile 目录的只读快照。

    Returns:
        ``profile_exists`` / ``logged_in``。
    """
    root = Path(profile_dir)
    return {
        "profile_exists": root.exists(),
        "logged_in": profile_contains_state(root),
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

    state = build_profile_state(profile_dir)

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
    bits.append("已配出口" if payload.get("proxy_enabled") else "未配出口")
    return " · ".join(bits)
