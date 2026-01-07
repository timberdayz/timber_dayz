"""
请求ID中间件
为每个请求生成唯一的request_id，并在响应中包含
"""

import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    请求ID中间件
    
    功能：
    1. 为每个请求生成唯一的request_id（UUID）
    2. 将request_id添加到请求状态（request.state.request_id）
    3. 将request_id添加到响应头（X-Request-ID）
    4. 支持从请求头读取request_id（如果客户端已提供）
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 尝试从请求头获取request_id（如果客户端已提供）
        client_request_id = request.headers.get("X-Request-ID")
        
        # 如果客户端提供了request_id，使用它；否则生成新的
        if client_request_id:
            request_id = client_request_id
        else:
            request_id = str(uuid.uuid4())
        
        # 将request_id添加到请求状态（供后续处理使用）
        request.state.request_id = request_id
        
        # 执行请求
        response = await call_next(request)
        
        # 将request_id添加到响应头
        response.headers["X-Request-ID"] = request_id
        
        return response

