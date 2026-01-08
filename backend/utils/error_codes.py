"""
统一错误码定义
企业级ERP标准：4位数字错误码，按模块细分
"""

from enum import IntEnum


class ErrorCode(IntEnum):
    """
    错误码枚举
    1xxx - 系统错误
    2xxx - 业务错误
    3xxx - 数据错误
    4xxx - 用户错误
    """
    
    # ========== 1xxx - 系统错误 ==========
    
    # 1001-1099: 数据库错误
    DATABASE_CONNECTION_ERROR = 1001
    DATABASE_QUERY_ERROR = 1002
    DATABASE_TRANSACTION_ERROR = 1003
    DATABASE_TIMEOUT = 1004
    
    # 1100-1199: 缓存错误
    CACHE_CONNECTION_ERROR = 1101
    CACHE_OPERATION_ERROR = 1102
    CACHE_TIMEOUT = 1103
    
    # 1200-1299: 消息队列错误
    MQ_CONNECTION_ERROR = 1201
    MQ_PUBLISH_ERROR = 1202
    MQ_CONSUME_ERROR = 1203
    
    # 1300-1399: 文件系统错误
    FILE_NOT_FOUND = 1301
    FILE_READ_ERROR = 1302
    FILE_WRITE_ERROR = 1303
    FILE_PERMISSION_ERROR = 1304
    
    # 1400-1499: 网络错误
    NETWORK_ERROR = 1401
    NETWORK_TIMEOUT = 1402
    
    # 1500-1599: 通用系统错误
    INTERNAL_SERVER_ERROR = 1500
    SERVICE_UNAVAILABLE = 1501
    UNKNOWN_ERROR = 1502
    
    # ========== 2xxx - 业务错误 ==========
    
    # 2001-2099: 订单业务错误
    ORDER_NOT_FOUND = 2001
    ORDER_ALREADY_EXISTS = 2002
    ORDER_STATUS_INVALID = 2003
    ORDER_CANNOT_CANCEL = 2004
    
    # 2100-2199: 库存业务错误
    INVENTORY_INSUFFICIENT = 2101
    INVENTORY_NOT_FOUND = 2102
    INVENTORY_ALREADY_EXISTS = 2103
    INVENTORY_OPERATION_FAILED = 2104
    
    # 2200-2299: 财务业务错误
    FINANCE_ACCOUNT_NOT_FOUND = 2201
    FINANCE_BALANCE_INSUFFICIENT = 2202
    FINANCE_TRANSACTION_FAILED = 2203
    
    # 2300-2399: 销售业务错误
    SALES_CAMPAIGN_NOT_FOUND = 2301
    SALES_CAMPAIGN_ALREADY_EXISTS = 2302
    SALES_CAMPAIGN_INVALID = 2303
    TARGET_NOT_FOUND = 2304
    TARGET_ALREADY_EXISTS = 2305
    TARGET_INVALID = 2306
    
    # 2400-2499: 数据同步错误
    DATA_SYNC_FAILED = 2401
    DATA_SYNC_TIMEOUT = 2402
    DATA_SYNC_CONFLICT = 2403
    
    # ========== 3xxx - 数据错误 ==========
    
    # 3001-3099: 数据验证错误
    DATA_VALIDATION_FAILED = 3001
    DATA_REQUIRED_FIELD_MISSING = 3002
    DATA_INVALID_FORMAT = 3003
    DATA_OUT_OF_RANGE = 3004
    
    # 3100-3199: 数据格式错误
    DATA_FORMAT_INVALID = 3101
    DATA_TYPE_MISMATCH = 3102
    DATA_ENCODING_ERROR = 3103
    
    # 3200-3299: 数据完整性错误
    DATA_INTEGRITY_VIOLATION = 3201
    DATA_FOREIGN_KEY_VIOLATION = 3202
    DATA_UNIQUE_CONSTRAINT_VIOLATION = 3203
    
    # 3300-3399: 数据隔离错误
    DATA_QUARANTINED = 3301
    DATA_ISOLATION_FAILED = 3302
    
    # 3400-3499: 数据查找错误
    DATA_NOT_FOUND = 3401
    DATA_ALREADY_EXISTS = 3402
    
    # ========== 4xxx - 用户错误 ==========
    
    # 4001-4099: 认证错误
    AUTH_REQUIRED = 4001
    AUTH_TOKEN_INVALID = 4002
    AUTH_TOKEN_EXPIRED = 4003
    AUTH_CREDENTIALS_INVALID = 4004
    AUTH_ACCOUNT_PENDING = 4005  # v4.19.0: 账号待审批
    AUTH_ACCOUNT_REJECTED = 4006  # v4.19.0: 账号已拒绝
    AUTH_ACCOUNT_SUSPENDED = 4007  # v4.19.0: 账号已暂停
    AUTH_ACCOUNT_INACTIVE = 4008  # v4.19.0: 账号未激活
    AUTH_ACCOUNT_LOCKED = 4009  # v4.19.0: 账户已锁定
    
    # 4100-4199: 权限错误
    PERMISSION_DENIED = 4101
    PERMISSION_INSUFFICIENT = 4102
    RESOURCE_ACCESS_DENIED = 4103
    
    # 4200-4299: 参数错误
    PARAMETER_MISSING = 4201
    PARAMETER_INVALID = 4202
    PARAMETER_OUT_OF_RANGE = 4203
    PARAMETER_FORMAT_ERROR = 4204
    
    # 4300-4399: 请求频率限制
    RATE_LIMIT_EXCEEDED = 4301
    
    # 4400-4499: API版本和废弃
    API_DEPRECATED = 4401
    API_VERSION_NOT_SUPPORTED = 4402


def get_error_type(code: int) -> str:
    """
    根据错误码获取错误类型
    
    Args:
        code: 错误码
    
    Returns:
        str: 错误类型（SystemError、BusinessError、DataError、UserError）
    """
    if 1000 <= code < 2000:
        return "SystemError"
    elif 2000 <= code < 3000:
        return "BusinessError"
    elif 3000 <= code < 4000:
        return "DataError"
    elif 4000 <= code < 5000:
        return "UserError"
    else:
        return "SystemError"  # 默认系统错误


def get_error_message(code: int, default_message: str = "操作失败") -> str:
    """
    根据错误码获取默认错误消息
    
    Args:
        code: 错误码
        default_message: 默认消息
    
    Returns:
        str: 错误消息
    """
    error_messages = {
        # 系统错误
        ErrorCode.DATABASE_CONNECTION_ERROR: "数据库连接失败",
        ErrorCode.DATABASE_QUERY_ERROR: "数据库查询失败",
        ErrorCode.CACHE_CONNECTION_ERROR: "缓存连接失败",
        ErrorCode.NETWORK_ERROR: "网络连接失败",
        
        # 业务错误
        ErrorCode.ORDER_NOT_FOUND: "订单不存在",
        ErrorCode.INVENTORY_INSUFFICIENT: "库存不足",
        ErrorCode.SALES_CAMPAIGN_NOT_FOUND: "销售战役不存在",
        ErrorCode.TARGET_NOT_FOUND: "目标不存在",
        
        # 数据错误
        ErrorCode.DATA_VALIDATION_FAILED: "数据验证失败",
        ErrorCode.DATA_FORMAT_INVALID: "数据格式无效",
        ErrorCode.DATA_INTEGRITY_VIOLATION: "数据完整性违反",
        ErrorCode.DATA_NOT_FOUND: "数据不存在",
        ErrorCode.DATA_ALREADY_EXISTS: "数据已存在",
        
        # 用户错误
        ErrorCode.AUTH_REQUIRED: "需要认证",
        ErrorCode.AUTH_TOKEN_INVALID: "认证令牌无效",
        ErrorCode.AUTH_ACCOUNT_PENDING: "账号待审批",
        ErrorCode.AUTH_ACCOUNT_REJECTED: "账号已拒绝",
        ErrorCode.AUTH_ACCOUNT_SUSPENDED: "账号已暂停",
        ErrorCode.AUTH_ACCOUNT_INACTIVE: "账号未激活",
        ErrorCode.PERMISSION_DENIED: "权限不足",
        ErrorCode.PARAMETER_INVALID: "参数无效",
        ErrorCode.RATE_LIMIT_EXCEEDED: "请求频率过高",
        ErrorCode.API_DEPRECATED: "API已废弃，请使用新API",
    }
    
    return error_messages.get(code, default_message)



