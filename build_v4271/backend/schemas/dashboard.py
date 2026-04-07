"""
数据看板数据模式 - 西虹ERP系统
"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class KPIData(BaseModel):
    """KPI数据模式"""
    total_files: int
    processed_files: int
    pending_files: int
    failed_files: int

class PlatformDistribution(BaseModel):
    """平台分布数据模式"""
    name: str
    value: int
    color: Optional[str] = None

class DataDomainDistribution(BaseModel):
    """数据域分布数据模式"""
    name: str
    value: int

class RecentFile(BaseModel):
    """最近文件数据模式"""
    file_name: str
    platform: str
    data_domain: str
    status: str
    discovery_time: str
    last_processed: str

class SystemStats(BaseModel):
    """系统统计数据模式"""
    uptime: float
    memory_usage: float
    cpu_usage: float
    disk_usage: float

class DashboardResponse(BaseModel):
    """数据看板响应模式"""
    kpi_data: KPIData
    platform_distribution: List[PlatformDistribution]
    data_domain_distribution: List[DataDomainDistribution]
    recent_files: List[RecentFile]
    system_stats: SystemStats
