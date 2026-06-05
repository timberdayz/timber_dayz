#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
会话管理器

提供浏览器会话的持久化、加载、健康检查和自动刷新功能。
支持 storage_state 和持久化上下文两种模式。
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Any, Union, List
from datetime import datetime, timedelta
from loguru import logger
from modules.apps.collection_center.runtime_session import (
    tiktok_storage_state_meets_quality_gate,
    tiktok_storage_state_quality_score,
)
from modules.utils.login_status_detector import LOGIN_DETECTION_CONFIG

REPO_ROOT = Path(__file__).resolve().parents[3]


def _extract_state_payload(storage_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(storage_state, dict):
        return {}
    wrapped = storage_state.get("storage_state")
    if isinstance(wrapped, dict):
        return wrapped
    return storage_state


def _cookies_from_state(storage_state: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    payload = _extract_state_payload(storage_state)
    cookies = payload.get("cookies")
    return cookies if isinstance(cookies, list) else []


def _origins_from_state(storage_state: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    payload = _extract_state_payload(storage_state)
    origins = payload.get("origins")
    return origins if isinstance(origins, list) else []


def _auth_cookie_names_for_platform(platform: str) -> set[str]:
    config = LOGIN_DETECTION_CONFIG.get(str(platform or "").strip().lower(), {})
    values = config.get("auth_cookies") if isinstance(config, dict) else None
    return {str(item).strip() for item in values or [] if str(item).strip()}


def session_quality_score(platform: str, storage_state: Optional[Dict[str, Any]]) -> int:
    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform == "tiktok":
        return tiktok_storage_state_quality_score(storage_state)

    cookies = _cookies_from_state(storage_state)
    origins = _origins_from_state(storage_state)
    cookie_names = {str(cookie.get("name") or "").strip() for cookie in cookies if isinstance(cookie, dict)}
    auth_cookie_names = _auth_cookie_names_for_platform(normalized_platform)
    auth_hits = len(cookie_names.intersection(auth_cookie_names))
    score = 0
    score += min(len(cookies), 20)
    score += min(len(origins) * 3, 12)
    score += auth_hits * 5
    if len(cookies) >= 10:
        score += 5
    if len(cookies) >= 20:
        score += 5
    return score


def session_meets_quality_gate(platform: str, storage_state: Optional[Dict[str, Any]]) -> bool:
    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform == "tiktok":
        return tiktok_storage_state_meets_quality_gate(storage_state)

    cookies = _cookies_from_state(storage_state)
    origins = _origins_from_state(storage_state)
    cookie_names = {str(cookie.get("name") or "").strip() for cookie in cookies if isinstance(cookie, dict)}
    auth_cookie_names = _auth_cookie_names_for_platform(normalized_platform)
    auth_hits = len(cookie_names.intersection(auth_cookie_names))
    return auth_hits >= 1 and len(cookies) >= 3 and (len(origins) >= 1 or len(cookies) >= 8)


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.stem}-",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _session_freshness_timestamp(session_data: Optional[Dict[str, Any]]) -> float:
    if not isinstance(session_data, dict):
        return 0.0

    metadata = session_data.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    candidates = [
        metadata.get("saved_at"),
        session_data.get("last_used_at"),
        session_data.get("created_at"),
    ]
    numeric_values = [float(value) for value in candidates if isinstance(value, (int, float))]
    return max(numeric_values) if numeric_values else 0.0


class SessionManager:
    """会话管理器"""

    @staticmethod
    def _repo_relative(path: Union[str, Path]) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return REPO_ROOT / candidate

    def __init__(self, base_path: Union[str, Path] = "data/sessions"):
        """
        初始化会话管理器

        Args:
            base_path: 会话存储基础路径
        """
        self.base_path = self._repo_relative(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # 会话存储路径
        self.sessions_path = self.base_path
        self.profiles_path = self._repo_relative("data/session_profiles")
        self.profiles_path.mkdir(parents=True, exist_ok=True)

        # 持久化Profile路径(每账号独立目录)
        self.persistent_profiles_path = self._repo_relative("profiles")
        self.persistent_profiles_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"初始化会话管理器: {self.base_path}")
        logger.info(f"持久化Profile路径: {self.persistent_profiles_path}")

    def describe_storage_targets(self, platform: str, account_id: str) -> Dict[str, str]:
        return {
            "platform": str(platform or "").strip().lower(),
            "account_id": str(account_id or "").strip(),
            "session_path": str(self.get_session_path(platform, account_id)),
            "persistent_profile_path": str(self.get_persistent_profile_path(platform, account_id)),
            "legacy_profile_path": str(self.get_profile_path(platform, account_id)),
        }

    def get_session_metadata(self, platform: str, account_id: str) -> Dict[str, Any]:
        session = self.load_session(platform, account_id, max_age_days=None)
        if not isinstance(session, dict):
            return {}
        metadata = session.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    def get_persistent_profile_path(self, platform: str, account_id: str) -> Path:
        """
        获取账号的持久化Profile路径

        Args:
            platform: 平台名称
            account_id: 账号ID

        Returns:
            持久化Profile目录路径
        """
        # 清理平台名称和账号ID,确保文件系统安全
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
        
        # 使用账号ID作为目录名(安全的文件名)
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

            normalized_platform = str(platform or "").strip().lower()
            existing_session: Optional[Dict[str, Any]] = None
            if session_file.exists():
                try:
                    with open(session_file, "r", encoding="utf-8") as fh:
                        existing_session = json.load(fh)
                except Exception:
                    existing_session = None

            def _merge_tiktok_storage_state(
                old_state: Optional[Dict[str, Any]],
                new_state: Dict[str, Any],
            ) -> Dict[str, Any]:
                """
                TikTok 特殊处理：
                - storage_state 可能在页面尚未完成 bootstrap 时被读取，导致 origins/localStorage 为空
                - 一旦把“空 origins”的快照写回磁盘，会覆盖掉历史上更完整的会话，从而降低后续复用质量

                合并策略（尽量保守，避免降级）：
                - cookies：按 (name, domain, path) 去重，优先使用 new_state 的值
                - origins：按 origin 去重，localStorage 按 name 去重，优先使用 new_state 的值
                - 当 new_state.origins 为空时，保留 old_state.origins（不降级）
                """
                if not isinstance(new_state, dict):
                    return dict(old_state or {})
                if not isinstance(old_state, dict):
                    return dict(new_state)

                merged: Dict[str, Any] = dict(old_state)

                old_cookies = old_state.get("cookies") if isinstance(old_state.get("cookies"), list) else []
                new_cookies = new_state.get("cookies") if isinstance(new_state.get("cookies"), list) else []
                cookie_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}
                for cookie in old_cookies:
                    if not isinstance(cookie, dict):
                        continue
                    key = (
                        str(cookie.get("name") or ""),
                        str(cookie.get("domain") or ""),
                        str(cookie.get("path") or ""),
                    )
                    cookie_map[key] = cookie
                for cookie in new_cookies:
                    if not isinstance(cookie, dict):
                        continue
                    key = (
                        str(cookie.get("name") or ""),
                        str(cookie.get("domain") or ""),
                        str(cookie.get("path") or ""),
                    )
                    cookie_map[key] = cookie
                if cookie_map:
                    merged["cookies"] = list(cookie_map.values())

                old_origins = old_state.get("origins") if isinstance(old_state.get("origins"), list) else []
                new_origins = new_state.get("origins") if isinstance(new_state.get("origins"), list) else []

                def _norm_origin(value: Any) -> str:
                    return str(value or "").strip()

                def _merge_origin(old_origin: Dict[str, Any], new_origin: Dict[str, Any]) -> Dict[str, Any]:
                    merged_origin: Dict[str, Any] = dict(old_origin or {})
                    for key, value in (new_origin or {}).items():
                        if key != "localStorage":
                            merged_origin[key] = value

                    old_ls = old_origin.get("localStorage") if isinstance(old_origin.get("localStorage"), list) else []
                    new_ls = new_origin.get("localStorage") if isinstance(new_origin.get("localStorage"), list) else []
                    ls_map: Dict[str, Dict[str, Any]] = {}
                    for item in old_ls:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "").strip()
                        if not name:
                            continue
                        ls_map[name] = item
                    for item in new_ls:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "").strip()
                        if not name:
                            continue
                        ls_map[name] = item
                    if ls_map:
                        merged_origin["localStorage"] = list(ls_map.values())
                    return merged_origin

                origin_map: Dict[str, Dict[str, Any]] = {}
                for origin in old_origins:
                    if not isinstance(origin, dict):
                        continue
                    key = _norm_origin(origin.get("origin"))
                    if not key:
                        continue
                    origin_map[key] = origin

                for origin in new_origins:
                    if not isinstance(origin, dict):
                        continue
                    key = _norm_origin(origin.get("origin"))
                    if not key:
                        continue
                    if key in origin_map and isinstance(origin_map[key], dict):
                        origin_map[key] = _merge_origin(origin_map[key], origin)
                    else:
                        origin_map[key] = origin

                if origin_map:
                    merged["origins"] = list(origin_map.values())

                # Copy any extra fields from new_state (but do not erase old fields when new is missing).
                for key, value in new_state.items():
                    if key in {"cookies", "origins"}:
                        continue
                    merged[key] = value

                return merged

            old_state = None
            if existing_session and isinstance(existing_session.get("storage_state"), dict):
                old_state = existing_session.get("storage_state")

            merged_storage_state: Dict[str, Any] = storage_state or {}
            if normalized_platform == "tiktok":
                merged_storage_state = _merge_tiktok_storage_state(old_state, storage_state or {})
                old_score = tiktok_storage_state_quality_score(old_state)
                new_score = tiktok_storage_state_quality_score(storage_state or {})
                merged_score = tiktok_storage_state_quality_score(merged_storage_state)
                try:
                    old_origins = old_state.get("origins") if isinstance(old_state, dict) else None
                    new_origins = (storage_state or {}).get("origins") if isinstance(storage_state, dict) else None
                    merged_origins = merged_storage_state.get("origins") if isinstance(merged_storage_state, dict) else None
                    old_count = len(old_origins) if isinstance(old_origins, list) else 0
                    new_count = len(new_origins) if isinstance(new_origins, list) else 0
                    merged_count = len(merged_origins) if isinstance(merged_origins, list) else 0
                    logger.debug(
                        "TikTok session merge: old_origins=%s new_origins=%s merged_origins=%s (%s/%s)",
                        old_count,
                        new_count,
                        merged_count,
                        platform,
                        account_id,
                    )
                    logger.debug(
                        "TikTok session quality: old=%s new=%s merged=%s gate(new)=%s gate(merged)=%s (%s/%s)",
                        old_score,
                        new_score,
                        merged_score,
                        tiktok_storage_state_meets_quality_gate(storage_state or {}),
                        tiktok_storage_state_meets_quality_gate(merged_storage_state),
                        platform,
                        account_id,
                    )
                except Exception:
                    pass

            old_metadata = existing_session.get("metadata") if isinstance(existing_session, dict) else {}
            old_metadata = old_metadata if isinstance(old_metadata, dict) else {}
            incoming_metadata = metadata if isinstance(metadata, dict) else {}

            old_score = session_quality_score(normalized_platform, old_state)
            new_score = session_quality_score(normalized_platform, storage_state or {})
            merged_score = session_quality_score(normalized_platform, merged_storage_state)
            old_gate = session_meets_quality_gate(normalized_platform, old_state)
            merged_gate = session_meets_quality_gate(normalized_platform, merged_storage_state)
            old_protected = bool(old_metadata.get("protected") or old_metadata.get("manual_seeded"))
            incoming_manual = bool(incoming_metadata.get("manual_seeded"))

            selected_state = merged_storage_state
            selected_score = merged_score
            selected_gate = merged_gate

            if old_state is not None:
                if old_protected and not incoming_manual:
                    selected_state = old_state
                    selected_score = old_score
                    selected_gate = old_gate
                elif old_protected and selected_score < old_score:
                    selected_state = old_state
                    selected_score = old_score
                    selected_gate = old_gate
                elif selected_score < old_score and old_gate:
                    selected_state = old_state
                    selected_score = old_score
                    selected_gate = old_gate

            current_time = time.time()
            # created_at 保留首次创建时间；会话新鲜度由 saved_at/last_used_at 驱动。
            created_at = current_time
            if existing_session and isinstance(existing_session.get("created_at"), (int, float)):
                created_at = float(existing_session.get("created_at"))

            merged_metadata: Dict[str, Any] = {}
            merged_metadata.update(old_metadata)
            merged_metadata.update(incoming_metadata)
            merged_metadata["saved_at"] = current_time
            merged_metadata["quality_score"] = selected_score
            merged_metadata["quality_gate_passed"] = bool(selected_gate)
            if incoming_manual:
                merged_metadata["quality_source"] = "manual"
                merged_metadata["manual_seeded"] = True
                merged_metadata["protected"] = True
            else:
                if old_protected and selected_state is old_state:
                    merged_metadata["quality_source"] = (
                        str(old_metadata.get("quality_source") or "manual").strip().lower() or "manual"
                    )
                else:
                    merged_metadata["quality_source"] = "automatic"
                if old_protected:
                    merged_metadata["protected"] = True
                    if old_metadata.get("manual_seeded"):
                        merged_metadata["manual_seeded"] = True
            
            # 准备保存的数据
            session_data = {
                "platform": platform,
                "account_id": account_id,
                "storage_state": selected_state,
                "created_at": created_at,
                "last_used_at": current_time,
                "metadata": merged_metadata,
            }
            
            # 保存到文件
            _write_json_atomic(session_file, session_data)
            
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
            max_age_days: 最大有效期(天)
            
        Returns:
            会话数据,失败或过期返回None
        """
        try:
            session_file = self.get_session_path(platform, account_id)
            
            if not session_file.exists():
                logger.debug(f"未找到已保存会话 {platform}/{account_id}，将执行完整登录（首次采集或未保存过会话时属正常）")
                return None
            
            # 读取会话数据
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 检查会话年龄
            if max_age_days is not None:
                freshness_at = _session_freshness_timestamp(session_data)
                age_days = (time.time() - freshness_at) / 86400 if freshness_at else 0
                
                if age_days > max_age_days:
                    logger.warning(f"会话已过期 ({age_days:.1f} 天): {platform}/{account_id}")
                    return None
            
            # 更新最后使用时间
            session_data["last_used_at"] = time.time()
            _write_json_atomic(session_file, session_data)
            
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
                logger.debug(f"会话文件不存在,无需删除: {platform}/{account_id}")
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
            max_age_days: 最大有效期(天)
            
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
            freshness_at = _session_freshness_timestamp(session_data)
            age_days = (time.time() - freshness_at) / 86400 if freshness_at else 0
            
            return {
                "exists": True,
                "platform": platform,
                "account_id": account_id,
                "file_path": str(session_file),
                "created_at": created_at,
                "last_used_at": last_used_at,
                "freshness_at": freshness_at,
                "age_days": age_days,
                "created_date": datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown",
                "last_used_date": datetime.fromtimestamp(last_used_at).strftime("%Y-%m-%d %H:%M:%S") if last_used_at else "Unknown",
                "freshness_date": datetime.fromtimestamp(freshness_at).strftime("%Y-%m-%d %H:%M:%S") if freshness_at else "Unknown",
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
            max_age_days: 最大有效期(天)
            
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
