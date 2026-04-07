from enum import IntEnum
from typing import Any, Optional

from fastapi import status

from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.exceptions import ERPException


class APIException(ERPException):
    """API 层基础异常,统一携带错误码和 HTTP 状态码。"""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        http_status_code: int,
        detail: Optional[Any] = None,
    ):
        self.http_status_code = http_status_code
        self.detail = detail
        super().__init__(message=message, error_code=error_code)


class NotFoundError(APIException):
    """资源不存在(404)。"""

    def __init__(
        self,
        message: str = "资源不存在",
        error_code: ErrorCode = ErrorCode.DATA_NOT_FOUND,
        detail: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            http_status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class BusinessValidationError(APIException):
    """业务校验失败/参数错误(422)。"""

    def __init__(
        self,
        message: str = "业务校验失败",
        error_code: ErrorCode = ErrorCode.DATA_VALIDATION_FAILED,
        detail: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            http_status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class PermissionDeniedError(APIException):
    """权限不足(403)。"""

    def __init__(
        self,
        message: str = "权限不足",
        error_code: ErrorCode = ErrorCode.PERMISSION_DENIED,
        detail: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            http_status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class ConflictError(APIException):
    """资源冲突(409)。"""

    def __init__(
        self,
        message: str = "资源冲突",
        error_code: ErrorCode = ErrorCode.DATA_INTEGRITY_VIOLATION,
        detail: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            http_status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class ExternalServiceError(APIException):
    """外部服务调用失败(502)。"""

    def __init__(
        self,
        message: str = "外部服务调用失败",
        error_code: ErrorCode = ErrorCode.SERVICE_UNAVAILABLE,
        detail: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            http_status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )


def _to_int_code(error_code: Any) -> int:
    if isinstance(error_code, IntEnum):
        return int(error_code)
    try:
        return int(error_code)
    except Exception:
        return int(ErrorCode.UNKNOWN_ERROR)


def error_response_v2(exc: ERPException, request_id: Optional[str] = None):
    """
    将 ERPException 及其子类转换为统一错误响应。

    - APIException: 使用自身携带的 ErrorCode + HTTP 状态码
    - 其他 ERPException: 统一映射为 INTERNAL_SERVER_ERROR(500)
    """
    if isinstance(exc, APIException):
        code = _to_int_code(exc.error_code)
        error_type = get_error_type(code)
        return error_response(
            code=code,
            message=str(exc),
            error_type=error_type,
            detail=exc.detail,
            status_code=exc.http_status_code,
            request_id=request_id,
        )

    # 非 API 层 ERPException: 统一视为内部错误
    code = int(ErrorCode.INTERNAL_SERVER_ERROR)
    return error_response(
        code=code,
        message=str(exc),
        error_type=get_error_type(code),
        detail=str(exc),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id,
    )

