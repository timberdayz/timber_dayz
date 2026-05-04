from fastapi import HTTPException, Request

from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.utils.exceptions import error_response_v2
from modules.core.exceptions import ERPException


async def handle_http_exception(logger, request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"[HTTP异常] {request.method} {request.url.path} - "
        f"状态码: {exc.status_code}, 错误: {exc.detail}, "
        f"请求ID: {request_id}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
            "error_detail": str(exc.detail),
        },
    )

    status_to_code = {
        400: ErrorCode.PARAMETER_INVALID,
        401: ErrorCode.AUTH_REQUIRED,
        403: ErrorCode.PERMISSION_DENIED,
        404: ErrorCode.FILE_NOT_FOUND,
        500: ErrorCode.DATABASE_QUERY_ERROR,
    }

    error_code = status_to_code.get(exc.status_code, exc.status_code)
    error_type = get_error_type(error_code)

    return error_response(
        code=error_code,
        message=str(exc.detail) if exc.detail else "请求失败",
        error_type=error_type,
        detail=str(exc.detail) if exc.detail else None,
        status_code=exc.status_code,
        request_id=request_id,
    )


async def handle_erp_exception(logger, request: Request, exc: ERPException):
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"[ERP异常] {request.method} {request.url.path} - "
        f"错误类型: {type(exc).__name__}, "
        f"错误消息: {str(exc)}, "
        f"请求ID: {request_id}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "query_params": str(request.query_params) if request.query_params else None,
            "client_host": request.client.host if request.client else None,
        },
    )

    return error_response_v2(exc, request_id=request_id)


async def handle_general_exception(logger, settings, request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"[未处理异常] {request.method} {request.url.path} - "
        f"错误类型: {type(exc).__name__}, "
        f"错误消息: {str(exc)}, "
        f"请求ID: {request_id}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "query_params": str(request.query_params) if request.query_params else None,
            "client_host": request.client.host if request.client else None,
        },
    )

    return error_response(
        code=ErrorCode.DATABASE_QUERY_ERROR,
        message="内部服务器错误",
        error_type="SystemError",
        detail=str(exc) if settings.DEBUG else None,
        recovery_suggestion="请稍后重试；如问题持续存在请联系系统管理员并提供请求ID",
        status_code=500,
        request_id=request_id,
    )
