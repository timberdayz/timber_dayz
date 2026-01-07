"""
事件定义文件 - 数据流转流程自动化

定义系统内部事件类型和事件数据结构，用于实现数据流转流程自动化。

事件类型：
- DATA_INGESTED: B类数据入库完成
- MV_REFRESHED: 物化视图刷新完成
- A_CLASS_UPDATED: A类数据更新

事件流程：
1. B类数据入库 → 触发DATA_INGESTED事件 → 自动刷新物化视图
2. 物化视图刷新完成 → 触发MV_REFRESHED事件 → 自动计算C类数据
3. A类数据更新 → 触发A_CLASS_UPDATED事件 → 自动重新计算C类数据
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict


class EventType(str, Enum):
    """事件类型枚举"""
    DATA_INGESTED = "data_ingested"  # B类数据入库完成
    # ⚠️ v4.6.0 DSS架构重构：MV_REFRESHED已废弃（Metabase直接查询原始表，无需物化视图）
    # MV_REFRESHED = "mv_refreshed"  # 物化视图刷新完成（已废弃）
    A_CLASS_UPDATED = "a_class_updated"  # A类数据更新


@dataclass
class DataIngestedEvent:
    """B类数据入库完成事件"""
    event_type: str = EventType.DATA_INGESTED
    file_id: int = None
    platform_code: Optional[str] = None
    data_domain: str = None  # orders/products/inventory/traffic/services
    granularity: Optional[str] = None  # daily/weekly/monthly/snapshot
    row_count: int = 0
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class MVRefreshedEvent:
    """物化视图刷新完成事件（⚠️ v4.6.0已废弃，保留类定义以兼容旧代码）"""
    # ⭐ v4.18.2修复：MV_REFRESHED已从EventType枚举中移除，使用字符串常量
    event_type: str = "mv_refreshed"  # 已废弃，但保留类定义以兼容旧代码
    view_name: str = None
    view_type: Optional[str] = None  # sales/inventory/finance/traffic
    row_count: int = 0
    duration_seconds: float = 0.0
    triggered_by: str = "manual"  # manual/scheduled/event
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class AClassUpdatedEvent:
    """A类数据更新事件"""
    event_type: str = EventType.A_CLASS_UPDATED
    data_type: str = None  # sales_campaign/target/performance_config
    record_id: int = None
    action: str = None  # create/update/delete
    affected_shops: Optional[list] = None  # 受影响的店铺ID列表
    affected_platforms: Optional[list] = None  # 受影响的平台代码列表
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


# 事件类型到事件类的映射
EVENT_CLASS_MAP = {
    EventType.DATA_INGESTED: DataIngestedEvent,
    # ⚠️ v4.6.0 DSS架构重构：MV_REFRESHED已废弃
    # EventType.MV_REFRESHED: MVRefreshedEvent,  # 已废弃
    EventType.A_CLASS_UPDATED: AClassUpdatedEvent,
}

