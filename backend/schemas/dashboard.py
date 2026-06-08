"""
数据看板数据模式 - 西虹ERP系统
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
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


class BusinessOverviewFlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class BusinessOverviewKpiPayload(BusinessOverviewFlexibleModel):
    gmv: Optional[float] = None
    order_count: Optional[int] = None
    visitor_count: Optional[int] = None
    page_views: Optional[int] = None
    impressions: Optional[int] = None
    conversion_rate: Optional[float] = None
    uv_conversion_rate: Optional[float] = None
    pv_conversion_rate: Optional[float] = None
    visit_rate: Optional[float] = None
    browse_depth: Optional[float] = None
    exposure_order_rate: Optional[float] = None
    avg_order_value: Optional[float] = None
    attach_rate: Optional[float] = None
    labor_efficiency: Optional[float] = None
    profit: Optional[float] = None


class BusinessOverviewMetricComparison(BusinessOverviewFlexibleModel):
    today: Optional[float] = None
    yesterday: Optional[float] = None
    average: Optional[float] = None
    change: Optional[float] = None


class BusinessOverviewComparisonPayload(BusinessOverviewFlexibleModel):
    metrics: Dict[str, BusinessOverviewMetricComparison] = Field(default_factory=dict)
    target: Dict[str, Any] = Field(default_factory=dict)


class BusinessOverviewOperationalMetricsPayload(BusinessOverviewFlexibleModel):
    monthly_target: Optional[float] = None
    monthly_total_achieved: Optional[float] = None
    today_sales: Optional[float] = None
    monthly_achievement_rate: Optional[float] = None
    time_gap: Optional[float] = None
    estimated_gross_profit: Optional[float] = None
    estimated_expenses: Optional[float] = None
    operating_result: Optional[float] = None
    operating_result_text: Optional[str] = None
    monthly_order_count: Optional[int] = None
    today_order_count: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class BusinessOverviewRankingItem(BusinessOverviewFlexibleModel):
    name: Optional[str] = None
    rank: Optional[int] = None
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    shop_account_id: Optional[str] = None
    main_account_id: Optional[str] = None
    main_account_name: Optional[str] = None
    is_unmatched: Optional[bool] = None
    gmv: Optional[float] = None
    profit: Optional[float] = None
    target_amount: Optional[float] = None
    achievement_rate: Optional[float] = None
    order_count: Optional[float] = None
    visitor_count: Optional[float] = None
    page_views: Optional[float] = None
    conversion_rate: Optional[float] = None
    uv_conversion_rate: Optional[float] = None
    pv_conversion_rate: Optional[float] = None


class BusinessOverviewBootstrapPayload(BusinessOverviewFlexibleModel):
    kpi: BusinessOverviewKpiPayload
    comparison: BusinessOverviewComparisonPayload
    operational_metrics: BusinessOverviewOperationalMetricsPayload
    traffic_ranking: List[BusinessOverviewRankingItem] = Field(default_factory=list)
    shop_racing: List[BusinessOverviewRankingItem] = Field(default_factory=list)
