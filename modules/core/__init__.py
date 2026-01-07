"""
跨境电商ERP系统 - 核心模块

提供系统的核心组件和基础功能，包括：
- 应用基类
- 配置管理
- 日志系统
- 异常定义
- 标准接口

Version: 1.0.0
Author: ERP Team
"""

from .base_app import BaseApplication
from .config import ConfigManager
from .logger import get_logger
from .exceptions import ERPException, ValidationError
from .interfaces import ApplicationInterface
from .registry import ApplicationRegistry, get_registry
from .secrets_manager import (
    SecretsManager,
    get_secrets_manager,
    get_secret,
    get_database_path,
    get_encryption_key
)
from .config_validator import (
    ConfigValidator,
    ConfigValidationError,
    validate_configs,
    validate_configs_strict
)
from .migration_manager import (
    MigrationManager,
    MigrationError,
    get_migration_manager,
    auto_migrate,
    check_migration_status
)
from .data_quality import (
    DataQualityScorer,
    score_dataframe,
    validate_schema
)
from .file_naming import (
    StandardFileName,
    generate_filename,
    parse_filename,
    validate_filename
)
from .path_manager import (
    get_project_root,
    get_data_dir,
    get_data_raw_dir,
    get_data_processed_dir,
    get_data_input_dir,
    get_downloads_dir,
    get_output_dir,
    get_temp_dir,
    get_config_dir,
    get_logs_dir,
    get_media_dir,
    get_path,
    reset_cache
)

__version__ = "1.0.0"
__all__ = [
    "BaseApplication",
    "ConfigManager",
    "get_logger",
    "ERPException",
    "ValidationError",
    "ApplicationInterface",
    "ApplicationRegistry",
    "get_registry",
    "SecretsManager",
    "get_secrets_manager",
    "get_secret",
    "get_database_path",
    "get_encryption_key",
    "ConfigValidator",
    "ConfigValidationError",
    "validate_configs",
    "validate_configs_strict",
    "MigrationManager",
    "MigrationError",
    "get_migration_manager",
    "auto_migrate",
    "check_migration_status",
    "DataQualityScorer",
    "score_dataframe",
    "validate_schema",
    "StandardFileName",
    "generate_filename",
    "parse_filename",
    "validate_filename",
    # Path management (v4.12.0)
    "get_project_root",
    "get_data_dir",
    "get_data_raw_dir",
    "get_data_processed_dir",
    "get_data_input_dir",
    "get_downloads_dir",
    "get_output_dir",
    "get_temp_dir",
    "get_config_dir",
    "get_logs_dir",
    "get_media_dir",
    "get_path",
    "reset_cache"
]