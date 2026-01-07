"""
异常定义

定义系统中使用的所有自定义异常类，提供统一的错误处理机制。
"""


class ERPException(Exception):
    """ERP系统基础异常"""
    
    def __init__(self, message: str, error_code: str = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)
    
    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class ValidationError(ERPException):
    """数据验证异常"""
    
    def __init__(self, message: str, field: str = None):
        self.field = field
        error_code = "VALIDATION_ERROR"
        if field:
            message = f"字段 '{field}' 验证失败: {message}"
        super().__init__(message, error_code)


class ConfigurationError(ERPException):
    """配置错误异常"""
    
    def __init__(self, message: str, config_key: str = None):
        self.config_key = config_key
        error_code = "CONFIG_ERROR"
        if config_key:
            message = f"配置项 '{config_key}' 错误: {message}"
        super().__init__(message, error_code)


class ConnectionError(ERPException):
    """连接错误异常"""
    
    def __init__(self, message: str, target: str = None):
        self.target = target
        error_code = "CONNECTION_ERROR"
        if target:
            message = f"连接 '{target}' 失败: {message}"
        super().__init__(message, error_code)


class DataProcessingError(ERPException):
    """数据处理异常"""
    
    def __init__(self, message: str, data_type: str = None):
        self.data_type = data_type
        error_code = "DATA_PROCESSING_ERROR"
        if data_type:
            message = f"处理 '{data_type}' 数据失败: {message}"
        super().__init__(message, error_code)


class CollectionError(ERPException):
    """数据采集异常"""
    
    def __init__(self, message: str, platform: str = None, account: str = None):
        self.platform = platform
        self.account = account
        error_code = "COLLECTION_ERROR"
        
        if platform and account:
            message = f"平台 '{platform}' 账号 '{account}' 采集失败: {message}"
        elif platform:
            message = f"平台 '{platform}' 采集失败: {message}"
        
        super().__init__(message, error_code)


class AuthenticationError(ERPException):
    """认证异常"""
    
    def __init__(self, message: str, platform: str = None):
        self.platform = platform
        error_code = "AUTH_ERROR"
        if platform:
            message = f"平台 '{platform}' 认证失败: {message}"
        super().__init__(message, error_code)


class PermissionError(ERPException):
    """权限异常"""
    
    def __init__(self, message: str, operation: str = None):
        self.operation = operation
        error_code = "PERMISSION_ERROR"
        if operation:
            message = f"操作 '{operation}' 权限不足: {message}"
        super().__init__(message, error_code)


class ResourceError(ERPException):
    """资源异常"""
    
    def __init__(self, message: str, resource: str = None):
        self.resource = resource
        error_code = "RESOURCE_ERROR"
        if resource:
            message = f"资源 '{resource}' 错误: {message}"
        super().__init__(message, error_code)


class TimeoutError(ERPException):
    """超时异常"""
    
    def __init__(self, message: str, timeout: int = None):
        self.timeout = timeout
        error_code = "TIMEOUT_ERROR"
        if timeout:
            message = f"操作超时 ({timeout}秒): {message}"
        super().__init__(message, error_code) 