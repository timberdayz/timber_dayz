#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
会话管理器

提供浏览器会话的持久化、加载、健康检查和自动刷新功能。
支持 storage_state 和持久化上下文两种模式。
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Any, Union, List
from datetime import datetime, timedelta
from loguru import logger


class SessionManager:
    """会话管理器"""

    def __init__(self, base_path: Union[str, Path] = "data/sessions"):
        """
        初始化会话管理器

        Args:
            base_path: 会话存储基础路径
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # 会话存储路径
        self.sessions_path = self.base_path
        self.profiles_path = Path("data/session_profiles")
        self.profiles_path.mkdir(parents=True, exist_ok=True)

        # 持久化Profile路径（每账号独立目录）
        self.persistent_profiles_path = Path("profiles")
        self.persistent_profiles_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"初始化会话管理器: {self.base_path}")
        logger.info(f"持久化Profile路径: {self.persistent_profiles_path}")

    def get_persistent_profile_path(self, platform: str, account_id: str) -> Path:
        """
        获取账号的持久化Profile路径

        Args:
            platform: 平台名称
            account_id: 账号ID

        Returns:
            持久化Profile目录路径
        """
        # 清理平台名称和账号ID，确保文件系统安全
        safe_platform = "".join(c for c in platform.lower() if c.isalnum() or c in "_-")
        safe_account_id = "".join(c for c in str(account_id) if c.isalnum() or c in "_-")

        profile_path = self.persistent_profiles_path / safe_platform / safe_account_id
        profile_path.mkdir(parents=True, exist_ok=True)

        return profile_path

    def get_session_path(self, platform: str, account_id: str) -> Path:
        """
        获取会话文件路径
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            
        Returns:
            会话文件路径
        """
        platform_path = self.sessions_path / platform.lower()
        platform_path.mkdir(parents=True, exist_ok=True)
        
        # 使用账号ID作为目录名（安全的文件名）
        safe_account_id = self._safe_filename(account_id)
        account_path = platform_path / safe_account_id
        account_path.mkdir(parents=True, exist_ok=True)
        
        return account_path / "storage_state.json"
    
    def get_profile_path(self, platform: str, account_id: str) -> Path:
        """
        获取持久化上下文目录路径
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            
        Returns:
            持久化上下文目录路径
        """
        platform_path = self.profiles_path / platform.lower()
        platform_path.mkdir(parents=True, exist_ok=True)
        
        safe_account_id = self._safe_filename(account_id)
        return platform_path / safe_account_id
    
    def save_session(
        self, 
        platform: str, 
        account_id: str, 
        storage_state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        保存会话状态
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            storage_state: 浏览器状态数据
            metadata: 额外的元数据
            
        Returns:
            保存是否成功
        """
        try:
            session_file = self.get_session_path(platform, account_id)
            
            # 准备保存的数据
            session_data = {
                "platform": platform,
                "account_id": account_id,
                "storage_state": storage_state,
                "created_at": time.time(),
                "last_used_at": time.time(),
                "metadata": metadata or {}
            }
            
            # 保存到文件
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            logger.success(f"会话已保存: {platform}/{account_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存会话失败: {e}")
            return False
    
    def load_session(
        self, 
        platform: str, 
        account_id: str,
        max_age_days: Optional[int] = 30
    ) -> Optional[Dict[str, Any]]:
        """
        加载会话状态
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            max_age_days: 最大有效期（天）
            
        Returns:
            会话数据，失败或过期返回None
        """
        try:
            session_file = self.get_session_path(platform, account_id)
            
            if not session_file.exists():
                logger.debug(f"会话文件不存在: {platform}/{account_id}")
                return None
            
            # 读取会话数据
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 检查会话年龄
            if max_age_days is not None:
                created_at = session_data.get("created_at", 0)
                age_days = (time.time() - created_at) / 86400
                
                if age_days > max_age_days:
                    logger.warning(f"会话已过期 ({age_days:.1f} 天): {platform}/{account_id}")
                    return None
            
            # 更新最后使用时间
            session_data["last_used_at"] = time.time()
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"会话已加载: {platform}/{account_id}")
            return session_data
            
        except Exception as e:
            logger.error(f"加载会话失败: {e}")
            return None
    
    def restore_session(
        self, 
        page: 'Page', 
        account_config: Dict[str, Any]
    ) -> bool:
        """
        恢复浏览器会话
        
        Args:
            page: Playwright页面对象
            account_config: 账号配置信息
            
        Returns:
            会话恢复是否成功
        """
        try:
            platform = account_config.get('platform', 'unknown').lower()
            account_id = account_config.get('account_id', '')
            
            # 加载会话数据
            session_data = self.load_session(platform, account_id)
            if not session_data:
                logger.debug(f"没有找到有效的会话数据: {platform}/{account_id}")
                return False
            
            # 应用会话状态到页面
            storage_state = session_data.get('storage_state', {})
            if storage_state:
                # 设置cookies
                cookies = storage_state.get('cookies', [])
                for cookie in cookies:
                    try:
                        page.context.add_cookies([cookie])
                    except Exception as e:
                        logger.warning(f"设置cookie失败: {e}")
                
                # 设置localStorage
                origins = storage_state.get('origins', [])
                for origin_data in origins:
                    origin = origin_data.get('origin', '')
                    localStorage = origin_data.get('localStorage', [])
                    
                    if origin and localStorage:
                        try:
                            # 导航到目标域名以设置localStorage
                            page.goto(origin)
                            for item in localStorage:
                                key = item.get('name', '')
                                value = item.get('value', '')
                                if key:
                                    page.evaluate(f"localStorage.setItem('{key}', '{value}')")
                        except Exception as e:
                            logger.warning(f"设置localStorage失败: {e}")
                
                logger.info(f"会话恢复成功: {platform}/{account_id}")
                return True
            else:
                logger.warning(f"会话数据为空: {platform}/{account_id}")
                return False
                
        except Exception as e:
            logger.error(f"恢复会话失败: {e}")
            return False

    def delete_session(self, platform: str, account_id: str) -> bool:
        """
        删除会话
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            
        Returns:
            删除是否成功
        """
        try:
            session_file = self.get_session_path(platform, account_id)
            
            if session_file.exists():
                session_file.unlink()
                logger.info(f"会话已删除: {platform}/{account_id}")
                return True
            else:
                logger.debug(f"会话文件不存在，无需删除: {platform}/{account_id}")
                return True
                
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False
    
    def is_session_valid(
        self, 
        platform: str, 
        account_id: str,
        max_age_days: Optional[int] = 30
    ) -> bool:
        """
        检查会话是否有效
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            max_age_days: 最大有效期（天）
            
        Returns:
            会话是否有效
        """
        session_data = self.load_session(platform, account_id, max_age_days)
        return session_data is not None
    
    def get_session_info(self, platform: str, account_id: str) -> Dict[str, Any]:
        """
        获取会话信息
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            
        Returns:
            会话信息字典
        """
        try:
            session_file = self.get_session_path(platform, account_id)
            
            if not session_file.exists():
                return {
                    "exists": False,
                    "platform": platform,
                    "account_id": account_id,
                    "file_path": str(session_file)
                }
            
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            created_at = session_data.get("created_at", 0)
            last_used_at = session_data.get("last_used_at", 0)
            age_days = (time.time() - created_at) / 86400 if created_at else 0
            
            return {
                "exists": True,
                "platform": platform,
                "account_id": account_id,
                "file_path": str(session_file),
                "created_at": created_at,
                "last_used_at": last_used_at,
                "age_days": age_days,
                "created_date": datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown",
                "last_used_date": datetime.fromtimestamp(last_used_at).strftime("%Y-%m-%d %H:%M:%S") if last_used_at else "Unknown",
                "metadata": session_data.get("metadata", {})
            }
            
        except Exception as e:
            logger.error(f"获取会话信息失败: {e}")
            return {
                "exists": False,
                "platform": platform,
                "account_id": account_id,
                "error": str(e)
            }
    
    def list_sessions(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有会话
        
        Args:
            platform: 可选的平台过滤
            
        Returns:
            会话信息列表
        """
        sessions = []
        
        try:
            if platform:
                platform_path = self.sessions_path / platform.lower()
                if platform_path.exists():
                    platforms_to_scan = [platform_path]
                else:
                    platforms_to_scan = []
            else:
                platforms_to_scan = [p for p in self.sessions_path.iterdir() if p.is_dir()]
            
            for platform_path in platforms_to_scan:
                platform_name = platform_path.name
                
                for account_path in platform_path.iterdir():
                    if account_path.is_dir():
                        account_id = account_path.name
                        session_info = self.get_session_info(platform_name, account_id)
                        if session_info.get("exists"):
                            sessions.append(session_info)
            
        except Exception as e:
            logger.error(f"列出会话时出错: {e}")
        
        return sessions
    
    def cleanup_expired_sessions(self, max_age_days: int = 30) -> int:
        """
        清理过期的会话
        
        Args:
            max_age_days: 最大有效期（天）
            
        Returns:
            清理的会话数量
        """
        cleaned_count = 0
        
        try:
            sessions = self.list_sessions()
            current_time = time.time()
            
            for session_info in sessions:
                if session_info["age_days"] > max_age_days:
                    try:
                        platform = session_info["platform"]
                        account_id = session_info["account_id"]
                        
                        if self.delete_session(platform, account_id):
                            cleaned_count += 1
                            logger.info(f"清理过期会话: {platform}/{account_id} (年龄: {session_info['age_days']:.1f} 天)")
                    except Exception as e:
                        logger.error(f"清理会话时出错: {e}")
            
            if cleaned_count > 0:
                logger.success(f"已清理 {cleaned_count} 个过期会话")
            else:
                logger.info("没有发现过期会话")
                
        except Exception as e:
            logger.error(f"清理过期会话时出错: {e}")
        
        return cleaned_count
    
    def _safe_filename(self, filename: str) -> str:
        """
        转换为安全的文件名
        
        Args:
            filename: 原始文件名
            
        Returns:
            安全的文件名
        """
        # 替换不安全的字符
        unsafe_chars = '<>:"/\\|?*'
        safe_name = filename
        
        for char in unsafe_chars:
            safe_name = safe_name.replace(char, '_')
        
        # 限制长度
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        
        return safe_name
