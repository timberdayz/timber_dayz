"""
API性能监控中间件（基础监控 - 日志记录）
记录API响应时间和错误率
"""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 慢请求阈值（毫秒）
SLOW_REQUEST_THRESHOLD_MS = 1000  # 1秒


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """
    API性能监控中间件
    
    功能：
    1. 记录API响应时间
    2. 记录慢请求（>1秒）
    3. 记录错误率（4xx/5xx）
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录请求开始时间
        start_time = time.time()
        
        # 获取请求信息
        method = request.method
        path = request.url.path
        query_params = str(request.query_params) if request.query_params else ""
        full_path = f"{path}?{query_params}" if query_params else path
        
        # 执行请求
        try:
            response = await call_next(request)
            
            # 计算响应时间（毫秒）
            duration_ms = (time.time() - start_time) * 1000
            
            # 获取响应状态码
            status_code = response.status_code
            
            # 记录响应时间日志
            if duration_ms >= SLOW_REQUEST_THRESHOLD_MS:
                # 慢请求：记录警告日志
                logger.warning(
                    f"[慢请求] {method} {full_path} - "
                    f"状态码: {status_code}, 响应时间: {duration_ms:.2f}ms"
                )
            else:
                # 正常请求：记录信息日志（仅在DEBUG模式下）
                logger.debug(
                    f"[API请求] {method} {full_path} - "
                    f"状态码: {status_code}, 响应时间: {duration_ms:.2f}ms"
                )
            
            # 记录错误日志（4xx/5xx）
            if status_code >= 400:
                error_type = "客户端错误" if 400 <= status_code < 500 else "服务器错误"
                logger.error(
                    f"[API错误] {method} {full_path} - "
                    f"状态码: {status_code} ({error_type}), 响应时间: {duration_ms:.2f}ms"
                )
            
            # 添加响应头（可选，用于前端监控）
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            return response
            
        except Exception as e:
            # 计算异常发生时的响应时间
            duration_ms = (time.time() - start_time) * 1000
            
            # 记录异常日志
            logger.error(
                f"[API异常] {method} {full_path} - "
                f"异常: {str(e)}, 响应时间: {duration_ms:.2f}ms",
                exc_info=True
            )
            
            # 重新抛出异常，让FastAPI的异常处理器处理
            raise

