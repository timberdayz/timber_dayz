"""
数据采集中心模块

提供多平台数据采集功能，支持Shopee、Amazon、妙手ERP等平台的数据采集
"""

__version__ = "1.0.0"
__author__ = "跨境电商ERP团队"

from .app import CollectionCenterApp

__all__ = ["CollectionCenterApp"] 