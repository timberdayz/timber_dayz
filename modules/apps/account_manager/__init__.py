"""
账号管理模块

提供多平台账号的统一管理功能，包括：
- 账号添加和编辑
- 账号状态验证
- 批量账号管理
- 账号配置同步

Version: 1.0.0
"""

from .app import AccountManagerApp

__version__ = "1.0.0"
__all__ = ["AccountManagerApp"] 