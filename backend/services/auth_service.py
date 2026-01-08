"""
JWT认证服务
"""

import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from backend.utils.config import get_settings
from modules.core.logger import get_logger

# 获取配置实例
settings = get_settings()
logger = get_logger(__name__)

class AuthService:
    """认证服务类"""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    
    def hash_password(self, password: str) -> str:
        """哈希密码"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """创建刷新令牌"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # 检查令牌类型
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )
            
            # 检查过期时间
            exp = payload.get("exp")
            if exp is None or datetime.utcnow().timestamp() > exp:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired"
                )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    def create_token_pair(self, user_id: int, username: str, roles: list) -> Dict[str, str]:
        """创建令牌对（访问令牌 + 刷新令牌）"""
        token_data = {
            "user_id": user_id,
            "username": username,
            "roles": roles
        }
        
        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """使用刷新令牌获取新的访问令牌"""
        payload = self.verify_token(refresh_token, "refresh")
        
        # 创建新的访问令牌
        token_data = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "roles": payload.get("roles")
        }
        
        return self.create_access_token(token_data)
    
    def _get_redis_client(self):
        """获取 Redis 客户端（用于 Refresh Token 黑名单）"""
        try:
            from backend.services.cache_service import get_cache_service
            cache_service = get_cache_service()
            return cache_service.redis_client if cache_service else None
        except Exception as e:
            logger.debug(f"[Auth] Redis 客户端不可用: {e}")
            return None
    
    async def _is_refresh_token_blacklisted(self, refresh_token: str) -> bool:
        """
        检查 Refresh Token 是否在黑名单中（异步）
        
        [*] v6.0.0新增：防止 Refresh Token 重用攻击
        [*] v6.0.0修复：改进 Redis 连接失败时的降级策略（记录警告）
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            # [*] v6.0.0修复：Redis 不可用时，记录严重警告（安全风险）
            logger.warning("[Auth] Redis 不可用，Refresh Token 黑名单机制失效（安全风险）")
            # 注意：返回 False 允许通过，但这是降级策略（可用性优先）
            # 在生产环境中，应该确保 Redis 可用性
            return False
        
        try:
            # 使用 Redis 检查 token 是否在黑名单中
            # 键格式：refresh_token_blacklist:{token_hash}
            import hashlib
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            blacklist_key = f"xihong_erp:refresh_token_blacklist:{token_hash}"
            
            # 异步检查
            exists = await redis_client.exists(blacklist_key)
            return exists > 0
        except Exception as e:
            # [*] v6.0.0修复：Redis 操作失败时，记录警告（安全风险）
            logger.warning(f"[Auth] 检查 Refresh Token 黑名单失败: {e}（安全风险）")
            return False
    
    async def _add_refresh_token_to_blacklist_atomic(self, refresh_token: str, expire_seconds: int) -> bool:
        """
        将 Refresh Token 添加到黑名单（原子操作）
        
        [*] v6.0.0新增：防止 Refresh Token 重用攻击
        [*] v6.0.0修复：使用 Redis SETNX 原子操作，防止竞态条件
        
        Args:
            refresh_token: 要加入黑名单的 refresh token
            expire_seconds: 黑名单过期时间（秒），通常等于 refresh token 的过期时间
        
        Returns:
            True: token 成功加入黑名单（首次加入）
            False: token 已在黑名单中（重复使用，应该拒绝）
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            # Redis 不可用时，无法使用黑名单机制（降级处理）
            logger.warning("[Auth] Redis 不可用，跳过 Refresh Token 黑名单（安全风险）")
            return True  # 降级：假设成功（允许通过）
        
        try:
            import hashlib
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            blacklist_key = f"xihong_erp:refresh_token_blacklist:{token_hash}"
            
            # [*] v6.0.0修复：使用 SETNX 原子操作（SET if Not eXists）
            # 如果键不存在，设置键并返回 True；如果键已存在，返回 False
            # 这样可以防止竞态条件：两个请求同时检查黑名单，都通过，然后都尝试加入黑名单
            result = await redis_client.set(blacklist_key, "1", ex=expire_seconds, nx=True)
            
            if result:
                # 首次加入黑名单（成功）
                logger.debug(f"[Auth] Refresh Token 已加入黑名单: {token_hash[:8]}... (过期时间: {expire_seconds}秒)")
                return True
            else:
                # 已在黑名单中（重复使用，应该拒绝）
                logger.warning(f"[Auth] Refresh Token 已在黑名单中（重复使用）: {token_hash[:8]}...")
                return False
        except Exception as e:
            logger.warning(f"[Auth] 添加 Refresh Token 到黑名单失败: {e}（安全风险）")
            return True  # 降级：假设成功（允许通过）
    
    async def refresh_token_pair(self, refresh_token: str) -> Dict[str, str]:
        """
        使用刷新令牌获取新的令牌对（访问令牌 + 刷新令牌）
        
        [*] v6.0.0新增：支持 Refresh Token 轮换（每次刷新时生成新的 refresh token）
        [*] v6.0.0修复：防止 Refresh Token 重用攻击（检查黑名单，使用原子操作）
        
        Note: 此方法现在是异步的，因为需要访问 Redis 黑名单
        """
        # [*] v6.0.0修复：检查 Refresh Token 是否在黑名单中
        if await self._is_refresh_token_blacklisted(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked"
            )
        
        payload = self.verify_token(refresh_token, "refresh")
        
        # [*] v6.0.0修复：将旧的 refresh token 加入黑名单（使用原子操作）
        # 计算过期时间（refresh token 的剩余过期时间）
        exp = payload.get("exp")
        if exp:
            current_time = datetime.utcnow().timestamp()
            expire_seconds = int(exp - current_time)
            
            # [*] v6.0.0修复：确保 expire_seconds 为正数且合理（边界情况处理）
            if expire_seconds <= 0:
                # Token 已过期或即将过期，不需要加入黑名单（verify_token 应该已经捕获）
                logger.debug(f"[Auth] Refresh Token 已过期或即将过期，跳过黑名单: expire_seconds={expire_seconds}")
            elif expire_seconds > self.refresh_token_expire_days * 24 * 60 * 60:
                # 过期时间异常大，可能是计算错误，使用默认值
                logger.warning(f"[Auth] Refresh Token 过期时间异常: {expire_seconds}秒，使用默认值")
                expire_seconds = self.refresh_token_expire_days * 24 * 60 * 60
            else:
                # [*] v6.0.0修复：使用原子操作加入黑名单
                # 如果返回 False，说明 token 已在黑名单中（重复使用），应该拒绝
                added = await self._add_refresh_token_to_blacklist_atomic(refresh_token, expire_seconds)
                if not added:
                    # Token 已在黑名单中（重复使用），拒绝请求
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Refresh token has been revoked (reuse detected)"
                    )
        
        # 创建新的令牌对
        token_data = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "roles": payload.get("roles")
        }
        
        new_access_token = self.create_access_token(token_data)
        new_refresh_token = self.create_refresh_token(token_data)
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }

# 全局认证服务实例
auth_service = AuthService()
