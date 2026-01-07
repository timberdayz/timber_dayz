"""
数据管理中心应用

集中管理后端数据库相关功能：文件清单扫描、入库执行、队列与失败诊断、快速预览与重试。

Version: 1.0.0
"""

from .app import DataManagementCenterApp

__version__ = "1.0.0"
__all__ = ["DataManagementCenterApp"]

