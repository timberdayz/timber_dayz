#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSRF Token 保护中间件

功能:
- 生成和验证 CSRF Token
- 防止跨站请求伪造攻击
- 支持 Double Submit Cookie 模式

实现原理:
1. 登录时生成 CSRF Token，存储在 Cookie 中（非 httpOnly，让前端可以读取）
2. 前端在每次 POST/PUT/DELETE 请求时，从 Cookie 读取 CSRF Token，并添加到请求头中
3. 后端验证请求头中的 CSRF Token 是否与 Cookie 中的一致

v6.0.0 新增：作为 modernize-auth-system Phase 3 的一部分
"""

import secrets
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from modules.core.logger import get_logger

logger = get_logger(__name__)

# CSRF Token 配置
CSRF_TOKEN_LENGTH = 32  # Token 长度（字节）
CSRF_COOKIE_NAME = "csrf_token"  # Cookie 名称
CSRF_HEADER_NAME = "X-CSRF-Token"  # Header 名称
CSRF_TOKEN_EXPIRE_SECONDS = 3600  # Token 过期时间（1小时）

# 不需要 CSRF 验证的路径前缀
CSRF_EXEMPT_PATHS = [
    "/auth/login",
    "/auth/refresh",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
]

# 不需要 CSRF 验证的 HTTP 方法
CSRF_SAFE_METHODS = ["GET", "HEAD", "OPTIONS", "TRACE"]


def generate_csrf_token() -> str:
    """
    生成 CSRF Token
    
    使用 secrets 模块生成安全的随机 token
    """
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def verify_csrf_token(cookie_token: Optional[str], header_token: Optional[str]) -> bool:
    """
    验证 CSRF Token
    
    使用时间恒定比较防止时序攻击
    
    Args:
        cookie_token: Cookie 中的 CSRF Token
        header_token: Header 中的 CSRF Token
    
    Returns:
        True: Token 有效
        False: Token 无效
    """
    if not cookie_token or not header_token:
        return False
    
    # 使用 hmac.compare_digest 进行时间恒定比较，防止时序攻击
    import hmac
    return hmac.compare_digest(cookie_token, header_token)


def is_csrf_exempt(path: str) -> bool:
    """
    检查路径是否豁免 CSRF 验证
    
    Args:
        path: 请求路径
    
    Returns:
        True: 豁免 CSRF 验证
        False: 需要 CSRF 验证
    """
    for exempt_path in CSRF_EXEMPT_PATHS:
        if path.startswith(exempt_path):
            return True
    return False


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF 保护中间件
    
    实现 Double Submit Cookie 模式：
    1. 在响应中设置 CSRF Token Cookie（非 httpOnly）
    2. 验证 POST/PUT/DELETE 请求的 CSRF Token
    """
    
    def __init__(self, app, exempt_paths: list = None, enabled: bool = True):
        """
        初始化 CSRF 中间件
        
        Args:
            app: FastAPI 应用
            exempt_paths: 额外的豁免路径列表
            enabled: 是否启用 CSRF 保护（可通过配置禁用）
        """
        super().__init__(app)
        self.exempt_paths = CSRF_EXEMPT_PATHS.copy()
        if exempt_paths:
            self.exempt_paths.extend(exempt_paths)
        self.enabled = enabled
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        处理请求
        
        1. 检查是否需要 CSRF 验证
        2. 验证 CSRF Token
        3. 在响应中设置/更新 CSRF Token Cookie
        """
        # 如果禁用 CSRF 保护，直接放行
        if not self.enabled:
            return await call_next(request)
        
        path = request.url.path
        method = request.method.upper()
        
        # 安全方法（GET, HEAD, OPTIONS, TRACE）不需要 CSRF 验证
        if method in CSRF_SAFE_METHODS:
            response = await call_next(request)
            # 为 GET 请求设置 CSRF Token Cookie（如果不存在）
            if method == "GET" and CSRF_COOKIE_NAME not in request.cookies:
                csrf_token = generate_csrf_token()
                response.set_cookie(
                    key=CSRF_COOKIE_NAME,
                    value=csrf_token,
                    max_age=CSRF_TOKEN_EXPIRE_SECONDS,
                    httponly=False,  # 允许 JavaScript 读取
                    secure=request.url.scheme == "https",
                    samesite="lax",
                    path="/"
                )
            return response
        
        # 检查路径是否豁免
        if is_csrf_exempt(path):
            return await call_next(request)
        
        # 对于 POST/PUT/DELETE 请求，验证 CSRF Token
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        
        if not verify_csrf_token(cookie_token, header_token):
            logger.warning(
                f"[CSRF] Token 验证失败: path={path}, method={method}, "
                f"cookie_token_exists={bool(cookie_token)}, header_token_exists={bool(header_token)}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed"
            )
        
        # Token 验证通过，继续处理请求
        response = await call_next(request)
        
        # 更新 CSRF Token（可选：每次请求后刷新 token）
        # 注意：这里我们不刷新 token，以避免并发请求问题
        # 如果需要更高安全性，可以在敏感操作后刷新 token
        
        return response


def get_csrf_token_from_request(request: Request) -> Optional[str]:
    """
    从请求中获取 CSRF Token
    
    Args:
        request: FastAPI Request 对象
    
    Returns:
        CSRF Token 或 None
    """
    return request.cookies.get(CSRF_COOKIE_NAME)


def set_csrf_token_cookie(response: Response, request: Request) -> str:
    """
    在响应中设置 CSRF Token Cookie
    
    Args:
        response: FastAPI Response 对象
        request: FastAPI Request 对象（用于判断是否 HTTPS）
    
    Returns:
        生成的 CSRF Token
    """
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=CSRF_TOKEN_EXPIRE_SECONDS,
        httponly=False,  # 允许 JavaScript 读取
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/"
    )
    return csrf_token


def delete_csrf_token_cookie(response: Response) -> None:
    """
    删除 CSRF Token Cookie
    
    Args:
        response: FastAPI Response 对象
    """
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        domain=None,
        samesite="lax"
    )

