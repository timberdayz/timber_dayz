"""
FastAPI OpenAPI响应示例配置
提供统一的响应格式示例，用于自动生成API文档
"""

from typing import Dict, Any

# 成功响应示例
SUCCESS_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": True,
    "data": {
        "id": 1,
        "name": "示例数据",
        "amount": 123.46,
        "date": "2025-01-16",
        "datetime": "2025-01-16T10:30:00Z"
    },
    "message": "操作成功",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 错误响应示例
ERROR_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": False,
    "error": {
        "code": 2001,
        "type": "BusinessError",
        "detail": "资源不存在",
        "recovery_suggestion": "请检查资源ID是否正确"
    },
    "message": "业务错误：资源不存在",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 分页响应示例
PAGINATION_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": True,
    "data": [
        {
            "id": 1,
            "name": "示例数据1",
            "amount": 123.46,
            "date": "2025-01-16"
        },
        {
            "id": 2,
            "name": "示例数据2",
            "amount": 456.79,
            "date": "2025-01-17"
        }
    ],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total": 100,
        "total_pages": 5,
        "has_previous": False,
        "has_next": True
    },
    "timestamp": "2025-01-16T10:30:00Z"
}

# 列表响应示例
LIST_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": True,
    "data": [
        {
            "id": 1,
            "name": "示例数据1"
        },
        {
            "id": 2,
            "name": "示例数据2"
        }
    ],
    "total": 100,
    "timestamp": "2025-01-16T10:30:00Z"
}

# 400错误响应示例
BAD_REQUEST_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": False,
    "error": {
        "code": 4201,
        "type": "UserError",
        "detail": "参数验证失败：page必须大于0",
        "recovery_suggestion": "请检查输入参数是否正确"
    },
    "message": "请求参数错误",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 401错误响应示例
UNAUTHORIZED_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": False,
    "error": {
        "code": 4001,
        "type": "UserError",
        "detail": "Token已过期",
        "recovery_suggestion": "请重新登录"
    },
    "message": "未认证，请重新登录",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 403错误响应示例
FORBIDDEN_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": False,
    "error": {
        "code": 4101,
        "type": "UserError",
        "detail": "权限不足",
        "recovery_suggestion": "请联系管理员获取权限"
    },
    "message": "权限不足",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 404错误响应示例
NOT_FOUND_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": False,
    "error": {
        "code": 2001,
        "type": "BusinessError",
        "detail": "资源不存在",
        "recovery_suggestion": "请检查资源ID是否正确"
    },
    "message": "资源不存在",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 500错误响应示例
INTERNAL_SERVER_ERROR_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "success": False,
    "error": {
        "code": 1001,
        "type": "SystemError",
        "detail": "数据库连接失败",
        "recovery_suggestion": "请稍后重试"
    },
    "message": "服务器错误，请稍后重试",
    "timestamp": "2025-01-16T10:30:00Z"
}

# 响应示例字典（用于FastAPI的responses参数）
RESPONSES: Dict[int, Dict[str, Any]] = {
    200: {
        "description": "成功响应",
        "content": {
            "application/json": {
                "example": SUCCESS_RESPONSE_EXAMPLE
            }
        }
    },
    400: {
        "description": "请求参数错误",
        "content": {
            "application/json": {
                "example": BAD_REQUEST_RESPONSE_EXAMPLE
            }
        }
    },
    401: {
        "description": "未认证",
        "content": {
            "application/json": {
                "example": UNAUTHORIZED_RESPONSE_EXAMPLE
            }
        }
    },
    403: {
        "description": "权限不足",
        "content": {
            "application/json": {
                "example": FORBIDDEN_RESPONSE_EXAMPLE
            }
        }
    },
    404: {
        "description": "资源不存在",
        "content": {
            "application/json": {
                "example": NOT_FOUND_RESPONSE_EXAMPLE
            }
        }
    },
    500: {
        "description": "服务器错误",
        "content": {
            "application/json": {
                "example": INTERNAL_SERVER_ERROR_RESPONSE_EXAMPLE
            }
        }
    }
}

# 分页响应示例（用于FastAPI的responses参数）
PAGINATION_RESPONSES: Dict[int, Dict[str, Any]] = {
    200: {
        "description": "成功响应（分页）",
        "content": {
            "application/json": {
                "example": PAGINATION_RESPONSE_EXAMPLE
            }
        }
    },
    400: {
        "description": "请求参数错误",
        "content": {
            "application/json": {
                "example": BAD_REQUEST_RESPONSE_EXAMPLE
            }
        }
    },
    500: {
        "description": "服务器错误",
        "content": {
            "application/json": {
                "example": INTERNAL_SERVER_ERROR_RESPONSE_EXAMPLE
            }
        }
    }
}

# 列表响应示例（用于FastAPI的responses参数）
LIST_RESPONSES: Dict[int, Dict[str, Any]] = {
    200: {
        "description": "成功响应（列表）",
        "content": {
            "application/json": {
                "example": LIST_RESPONSE_EXAMPLE
            }
        }
    },
    400: {
        "description": "请求参数错误",
        "content": {
            "application/json": {
                "example": BAD_REQUEST_RESPONSE_EXAMPLE
            }
        }
    },
    500: {
        "description": "服务器错误",
        "content": {
            "application/json": {
                "example": INTERNAL_SERVER_ERROR_RESPONSE_EXAMPLE
            }
        }
    }
}

