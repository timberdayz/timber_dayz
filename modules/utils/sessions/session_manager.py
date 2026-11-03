#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
会话管理器 —— 登录态的**唯一载体是持久 profile**。

规范依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md`` 生效版 v3。

- R1 真相源唯一：登录态由 Chromium 持久 profile（``profiles/<平台>/<主账号ID>/``）
  承载，不再有第二份副本，也不需要任何「谁覆盖谁」的仲裁规则。
- D5：会话文件（``data/sessions/**``）**彻底废除** —— 它的读写、评分、
  保护、过期清理能力在这里一并下线。
- 2026-11 收尾：legacy 持久化上下文目录（``data/session_profiles/**``）
  **一并废除** —— 最后一个使用者（``modules/collectors/miaoshou_smart_login.py``）
  已改用本模块唯一的 :meth:`get_persistent_profile_path`。

所以本模块现在只负责一件事：**把「平台 + 主账号」解析成 profile 目录路径**。
"""

from pathlib import Path
from typing import Union
from loguru import logger

REPO_ROOT = Path(__file__).resolve().parents[3]


class SessionManager:
    """登录态路径解析器（会话文件体系废除后只剩这一项职责）。"""

    @staticmethod
    def _repo_relative(path: Union[str, Path]) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return REPO_ROOT / candidate

    def __init__(self) -> None:
        """初始化会话管理器。

        **不创建任何目录**：会话文件体系废除后，本模块没有任何写盘行为；
        凭空 mkdir 会让「查一下路径」变成「产生一个空目录」。
        """
        # 持久化 Profile 路径（每账号独立目录）—— 登录态的唯一载体
        self.persistent_profiles_path = self._repo_relative("profiles")

        logger.info(f"持久化Profile路径: {self.persistent_profiles_path}")

    def get_persistent_profile_path(self, platform: str, account_id: str) -> Path:
        """
        获取账号的持久化Profile路径

        这是登录态的**唯一**载体路径，也是全仓唯一的目录命名规则（规则 B）：

            profiles/<平台>/<主账号ID>      例：``shopee KR`` → ``profiles/shopee/shopeeKR``

        注意：**本方法没有 mkdir 副作用**。查路径不应该凭空创建空目录 ——
        否则「未登录账号」也会看起来像一个有登录态的 profile。

        Args:
            platform: 平台名称
            account_id: 主账号ID

        Returns:
            持久化Profile目录路径（可能尚不存在）
        """
        # 清理平台名称和账号ID,确保文件系统安全
        safe_platform = "".join(c for c in platform.lower() if c.isalnum() or c in "_-")
        safe_account_id = "".join(c for c in str(account_id) if c.isalnum() or c in "_-")

        return self.persistent_profiles_path / safe_platform / safe_account_id
