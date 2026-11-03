"""
数据采集中心模块

提供多平台数据采集功能,支持Shopee、Amazon、妙手ERP等平台的数据采集

注(2026-11-03): 遗留 CLI 老程序(app.py / handlers.py)已退役。
正式采集走 POST /api/collection/tasks -> CollectionExecutorV2,
本包不再导出 CLI 应用类。
"""

__version__ = "1.0.0"
__author__ = "跨境电商ERP团队"

__all__: list[str] = []
