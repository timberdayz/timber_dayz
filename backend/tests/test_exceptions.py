"""
2.6 异常体系单元测试

覆盖:
- ERPException 基类行为
- APIException 及各子类 (NotFoundError / BusinessValidationError /
  PermissionDeniedError / ConflictError / ExternalServiceError)
- error_response_v2() 返回正确 HTTP 状态码和响应体格式
"""

import json

import pytest
from fastapi import status

from backend.utils.error_codes import ErrorCode
from backend.utils.exceptions import (
    APIException,
    BusinessValidationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
    error_response_v2,
)
from modules.core.exceptions import ERPException


# ---------------------------------------------------------------------------
# ERPException 基类
# ---------------------------------------------------------------------------


class TestERPException:
    def test_message_only(self):
        exc = ERPException(message="something went wrong")
        assert str(exc) == "something went wrong"
        assert exc.error_code is None

    def test_str_error_code(self):
        exc = ERPException(message="bad", error_code="MY_CODE")
        assert str(exc) == "[MY_CODE] bad"

    def test_int_enum_error_code(self):
        exc = ERPException(message="not found", error_code=ErrorCode.DATA_NOT_FOUND)
        assert str(exc) == f"[{int(ErrorCode.DATA_NOT_FOUND)}] not found"

    def test_is_exception(self):
        exc = ERPException(message="err")
        assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# APIException 基类
# ---------------------------------------------------------------------------


class TestAPIException:
    def test_carries_http_status(self):
        exc = APIException(
            message="test",
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=500,
        )
        assert exc.http_status_code == 500

    def test_carries_detail(self):
        exc = APIException(
            message="test",
            error_code=ErrorCode.DATA_NOT_FOUND,
            http_status_code=404,
            detail={"field": "id"},
        )
        assert exc.detail == {"field": "id"}

    def test_is_erp_exception(self):
        exc = APIException(
            message="test",
            error_code=ErrorCode.UNKNOWN_ERROR,
            http_status_code=500,
        )
        assert isinstance(exc, ERPException)


# ---------------------------------------------------------------------------
# 各子类默认值
# ---------------------------------------------------------------------------


class TestNotFoundError:
    def test_default_http_status(self):
        exc = NotFoundError()
        assert exc.http_status_code == status.HTTP_404_NOT_FOUND

    def test_default_message(self):
        exc = NotFoundError()
        assert "不存在" in exc.message

    def test_custom_message(self):
        exc = NotFoundError(message="订单不存在", detail="order_id=99")
        assert exc.message == "订单不存在"
        assert exc.detail == "order_id=99"


class TestBusinessValidationError:
    def test_default_http_status(self):
        exc = BusinessValidationError()
        assert exc.http_status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_custom_error_code(self):
        exc = BusinessValidationError(
            message="日期格式错误",
            error_code=ErrorCode.DATA_INVALID_FORMAT,
        )
        assert exc.error_code == ErrorCode.DATA_INVALID_FORMAT


class TestPermissionDeniedError:
    def test_default_http_status(self):
        exc = PermissionDeniedError()
        assert exc.http_status_code == status.HTTP_403_FORBIDDEN


class TestConflictError:
    def test_default_http_status(self):
        exc = ConflictError()
        assert exc.http_status_code == status.HTTP_409_CONFLICT


class TestExternalServiceError:
    def test_default_http_status(self):
        exc = ExternalServiceError()
        assert exc.http_status_code == status.HTTP_502_BAD_GATEWAY


# ---------------------------------------------------------------------------
# error_response_v2()
# ---------------------------------------------------------------------------


def _parse_body(response) -> dict:
    """从 JSONResponse 中解析 body。"""
    return json.loads(response.body)


class TestErrorResponseV2:
    def test_not_found_returns_404(self):
        exc = NotFoundError(message="资源不存在")
        resp = error_response_v2(exc)
        assert resp.status_code == 404

    def test_business_validation_returns_422(self):
        exc = BusinessValidationError(message="参数错误")
        resp = error_response_v2(exc)
        assert resp.status_code == 422

    def test_permission_denied_returns_403(self):
        exc = PermissionDeniedError()
        resp = error_response_v2(exc)
        assert resp.status_code == 403

    def test_conflict_returns_409(self):
        exc = ConflictError()
        resp = error_response_v2(exc)
        assert resp.status_code == 409

    def test_external_service_returns_502(self):
        exc = ExternalServiceError()
        resp = error_response_v2(exc)
        assert resp.status_code == 502

    def test_response_body_success_false(self):
        exc = NotFoundError()
        body = _parse_body(error_response_v2(exc))
        assert body["success"] is False

    def test_response_body_has_error_code(self):
        exc = NotFoundError(message="not found")
        body = _parse_body(error_response_v2(exc))
        assert "error" in body
        assert body["error"]["code"] == int(ErrorCode.DATA_NOT_FOUND)

    def test_response_body_message(self):
        exc = NotFoundError(message="订单不存在")
        body = _parse_body(error_response_v2(exc))
        assert body["message"] == "[3401] 订单不存在"

    def test_non_api_erp_exception_returns_500(self):
        exc = ERPException(message="core layer error", error_code="CORE_ERR")
        resp = error_response_v2(exc)
        assert resp.status_code == 500

    def test_non_api_erp_exception_body_success_false(self):
        exc = ERPException(message="internal error")
        body = _parse_body(error_response_v2(exc))
        assert body["success"] is False

    def test_with_request_id(self):
        exc = NotFoundError()
        body = _parse_body(error_response_v2(exc, request_id="req-123"))
        assert body.get("request_id") == "req-123"

    def test_detail_included_in_response(self):
        exc = NotFoundError(message="not found", detail={"hint": "check id"})
        body = _parse_body(error_response_v2(exc))
        assert body["error"]["detail"] == {"hint": "check id"}
