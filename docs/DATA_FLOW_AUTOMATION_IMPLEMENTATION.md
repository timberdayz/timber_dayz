# 数据流转流程自动化实现文档

## 概述

本文档记录了数据流转流程自动化的实现，实现了事件驱动的数据流转机制，确保B类数据入库后自动刷新物化视图，物化视图刷新后自动计算C类数据，A类数据更新后自动重新计算C类数据。

## 实现状态

### ✅ 已完成

1. **事件定义系统** (`backend/utils/events.py`)
   - ✅ 定义了`DATA_INGESTED`事件（B类数据入库完成）
   - ✅ 定义了`MV_REFRESHED`事件（物化视图刷新完成）
   - ✅ 定义了`A_CLASS_UPDATED`事件（A类数据更新）
   - ✅ 定义了完整的事件数据结构

2. **事件监听器** (`backend/services/event_listeners.py`)
   - ✅ 实现了`handle_data_ingested`方法（监听B类数据入库事件）
   - ✅ 实现了`handle_mv_refreshed`方法（监听物化视图刷新事件）
   - ✅ 实现了`handle_a_class_updated`方法（监听A类数据更新事件）
   - ✅ 实现了智能判断逻辑（根据数据域、粒度、视图类型判断需要执行的操作）

3. **Celery任务**
   - ✅ `backend/tasks/mv_refresh.py` - 物化视图刷新任务
   - ✅ `backend/tasks/c_class_calculation.py` - C类数据计算任务
   - ✅ 已在`backend/celery_app.py`中注册

4. **事件触发机制**
   - ✅ B类数据入库后触发`DATA_INGESTED`事件（`data_ingestion_service.py`）
   - ✅ 物化视图刷新后触发`MV_REFRESHED`事件（`materialized_view_service.py`）

### ✅ 已完成

1. **A类数据更新事件触发**
   - ✅ 在销售战役API路由中添加事件触发（`backend/routers/sales_campaign.py`）
     - `create_campaign`：创建后触发事件
     - `update_campaign`：更新后触发事件
     - `delete_campaign`：删除后触发事件
   - ✅ 在目标管理API路由中添加事件触发（`backend/routers/target_management.py`）
     - `create_target`：创建后触发事件
     - `update_target`：更新后触发事件
     - `delete_target`：删除后触发事件
   - ✅ 在绩效管理API路由中添加事件触发（`backend/routers/performance_management.py`）
     - `create_performance_config`：创建后触发事件
     - `update_performance_config`：更新后触发事件

## 架构设计

### 事件流程

```
B类数据入库
  ↓
触发 DATA_INGESTED 事件
  ↓
事件监听器判断需要刷新的视图
  ↓
Celery任务刷新物化视图
  ↓
触发 MV_REFRESHED 事件
  ↓
事件监听器判断需要计算的C类数据
  ↓
Celery任务计算C类数据
```

```
A类数据更新（销售战役/目标/绩效配置）
  ↓
触发 A_CLASS_UPDATED 事件
  ↓
事件监听器判断需要重新计算的C类数据
  ↓
Celery任务重新计算C类数据
```

### 核心组件

1. **事件定义** (`backend/utils/events.py`)
   - `EventType`: 事件类型枚举
   - `DataIngestedEvent`: B类数据入库事件
   - `MVRefreshedEvent`: 物化视图刷新事件
   - `AClassUpdatedEvent`: A类数据更新事件

2. **事件监听器** (`backend/services/event_listeners.py`)
   - `EventListener`: 事件监听器类
   - `handle_data_ingested`: 处理B类数据入库事件
   - `handle_mv_refreshed`: 处理物化视图刷新事件
   - `handle_a_class_updated`: 处理A类数据更新事件

3. **Celery任务**
   - `refresh_materialized_views_task`: 刷新物化视图任务
   - `calculate_c_class_data_task`: 计算C类数据任务
   - `recalculate_c_class_data_task`: 重新计算C类数据任务

## 使用方法

### 触发B类数据入库事件

在数据入库服务中，入库完成后自动触发：

```python
from backend.utils.events import DataIngestedEvent
from backend.services.event_listeners import event_listener

event = DataIngestedEvent(
    file_id=file_id,
    platform_code=platform,
    data_domain=domain,
    granularity=granularity,
    row_count=imported
)
event_listener.handle_data_ingested(event)
```

### 触发物化视图刷新事件

在物化视图服务中，刷新完成后自动触发：

```python
from backend.utils.events import MVRefreshedEvent
from backend.services.event_listeners import event_listener

event = MVRefreshedEvent(
    view_name=view_name,
    view_type=view_type,
    row_count=row_count,
    duration_seconds=duration,
    triggered_by=triggered_by
)
event_listener.handle_mv_refreshed(event)
```

### 触发A类数据更新事件

在A类数据更新API路由中，更新完成后触发：

```python
from backend.utils.events import AClassUpdatedEvent
from backend.services.event_listeners import event_listener

event = AClassUpdatedEvent(
    data_type="sales_campaign",  # 或 "target" 或 "performance_config"
    record_id=campaign_id,
    action="create",  # 或 "update" 或 "delete"
    affected_shops=[shop_id1, shop_id2],
    affected_platforms=[platform_code1, platform_code2]
)
event_listener.handle_a_class_updated(event)
```

## 配置说明

### Celery配置

Celery任务已在`backend/celery_app.py`中配置：

```python
include=[
    "backend.tasks.data_processing",
    "backend.tasks.scheduled_tasks",
    "backend.tasks.mv_refresh",  # 物化视图刷新任务
    "backend.tasks.c_class_calculation"  # C类数据计算任务
]
```

### 任务重试配置

- `max_retries`: 3次
- `default_retry_delay`: 60秒

## 开发模式支持

如果Celery未配置或不可用，事件监听器会自动降级为同步模式：

- 物化视图刷新：直接调用`MaterializedViewService.refresh_views()`
- C类数据计算：直接调用相应的服务方法

## 后续工作

1. **完善C类数据计算逻辑**
   - 实现健康度评分的具体计算逻辑
   - 实现达成率的具体计算逻辑
   - 实现排名的具体计算逻辑

3. **添加测试**
   - 单元测试：测试事件定义和事件监听器
   - 集成测试：测试完整的数据流转流程
   - 性能测试：测试Celery任务的性能

4. **监控和告警**
   - 添加事件触发监控
   - 添加Celery任务执行监控
   - 添加失败告警机制

## 相关文档

- [数据分类传输规范指南](docs/DATA_CLASSIFICATION_API_GUIDE.md)
- [C类数据查询策略指南](docs/C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md)
- [API契约标准](docs/API_CONTRACTS.md)

