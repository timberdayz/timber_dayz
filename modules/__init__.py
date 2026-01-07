"""
业务模块包

提供数据采集、浏览器管理、自动化操作等核心功能模块。

架构说明 v4.3.1:
- 所有配置管理已统一到 modules.core.config
- 所有Logger已统一到 modules.core.logger
- modules.utils 仅保留工具函数，不包含配置/日志类
"""

# v4.3.1: 移除已删除的modules.utils.config_loader和modules.utils.logger
# 使用统一架构:
#   - from modules.core.config import config_manager
#   - from modules.core.logger import get_logger

__all__ = []