# C类数据查询策略实现指南

**创建时间**: 2025-01-16  
**状态**: 📋 实施指南  
**目的**: 指导C类数据API迁移到混合查询策略

---

## 📋 概述

C类数据（计算数据）查询策略采用**混合查询模式**，根据查询条件自动选择最优查询方式：

1. **物化视图查询**（热数据层）：标准粒度 + 2年内 + 小规模筛选
2. **实时计算查询**（温数据层）：自定义范围 OR 超出2年 OR 大规模筛选
3. **归档表查询**（冷数据层）：5年以上数据（未来实现）

---

## 🏗️ 架构设计

### 分层存储架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端API调用                           │
│         /api/store-analytics/health-scores              │
│         /api/target-management/{id}/achievement         │
│         /api/dashboard/business-overview/shop-racing    │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│          C类数据查询服务（CClassDataService）            │
│              智能路由判断逻辑                            │
└──────────┬───────────────────────┬──────────────────────┘
           │                       │
           ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐
│   物化视图查询       │  │   实时计算查询        │
│   (热数据层)         │  │   (温数据层)          │
│   - 2年内数据        │  │   - 自定义范围        │
│   - 标准粒度         │  │   - 超出2年           │
│   - 小规模筛选       │  │   - 大规模筛选        │
│   - 查询速度<100ms   │  │   - 查询速度1-3s      │
└──────────────────────┘  └──────────────────────┘
```

### 智能路由判断矩阵

| 维度 | 物化视图条件 | 实时计算条件 |
|------|------------|------------|
| **时间范围** | ≤2年（730天） | >2年 OR 自定义范围 |
| **粒度** | daily/weekly/monthly | 其他粒度 |
| **店铺数** | ≤10个 | >10个 |
| **账号数** | ≤5个 | >5个 |
| **平台数** | ≤3个 | >3个 |

**判断规则**：所有条件都满足 → 物化视图，否则 → 实时计算

---

## 🔧 实现步骤

### 步骤1：使用C类数据查询服务

所有C类数据API都应该通过`CClassDataService`进行查询：

```python
from backend.services.c_class_data_service import CClassDataService

# 在API路由中
service = CClassDataService(db)
result = service.query_health_scores(
    start_date=start_date,
    end_date=end_date,
    granularity=granularity,
    platform_codes=platform_codes,
    shop_ids=shop_ids,
    page=page,
    page_size=page_size
)
```

### 步骤2：更新API参数格式

确保API支持以下参数格式：

```python
@router.get("/health-scores")
async def get_health_scores(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    platform_code: Optional[str] = Query(None, description="平台筛选（单个或多个，逗号分隔）"),
    shop_id: Optional[str] = Query(None, description="店铺筛选（单个或多个，逗号分隔）"),
    granularity: str = Query("daily", description="粒度：daily/weekly/monthly"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    # 解析平台和店铺列表
    platform_codes = None
    if platform_code:
        platform_codes = [p.strip() for p in platform_code.split(",") if p.strip()]
    
    shop_ids = None
    if shop_id:
        shop_ids = [s.strip() for s in shop_id.split(",") if s.strip()]
    
    # 使用C类数据查询服务
    service = CClassDataService(db)
    result = service.query_health_scores(...)
```

### 步骤3：处理查询结果

查询结果包含`query_type`字段，用于调试和监控：

```python
return pagination_response(
    data=result["data"],
    page=page,
    page_size=page_size,
    total=result["total"]
)

# 可选：添加查询类型信息（用于调试）
response_data = {
    "data": result["data"],
    "query_type": result.get("query_type", "unknown"),  # "materialized_view" 或 "realtime"
    "query_info": {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "granularity": granularity
    }
}
```

---

## 📝 API迁移清单

### 已完成迁移的API

- ✅ `/api/store-analytics/health-scores` - 店铺健康度评分查询

### 待迁移的API

#### 1. 达成率计算API

**API路径**: `/api/target-management/{target_id}/calculate`

**当前实现**: `backend/routers/target_management.py`

**迁移步骤**:
1. 在`CClassDataService`中添加`query_target_achievement()`方法
2. 实现物化视图查询方法（如果存在物化视图）
3. 实现实时计算查询方法（调用`TargetManagementService`）
4. 更新API路由使用`CClassDataService`

**示例代码**:
```python
# 在CClassDataService中添加
def query_target_achievement(
    self,
    target_id: int,
    start_date: date,
    end_date: date,
    granularity: str = "daily"
) -> Dict[str, Any]:
    """查询目标达成率（混合查询模式）"""
    use_mv = self.should_use_materialized_view(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity
    )
    
    if use_mv:
        return self.query_target_achievement_from_mv(...)
    else:
        return self.query_target_achievement_realtime(...)
```

#### 2. 排名数据API

**API路径**: `/api/dashboard/business-overview/shop-racing`

**当前实现**: `backend/routers/dashboard_api.py`

**迁移步骤**:
1. 在`CClassDataService`中添加`query_shop_ranking()`方法
2. 实现物化视图查询方法（如果存在物化视图）
3. 实现实时计算查询方法（从fact表查询）
4. 更新API路由使用`CClassDataService`

**示例代码**:
```python
# 在CClassDataService中添加
def query_shop_ranking(
    self,
    start_date: date,
    end_date: date,
    granularity: str,
    platform_codes: Optional[List[str]] = None,
    shop_ids: Optional[List[str]] = None,
    metric: str = "gmv"  # gmv/orders/conversion_rate
) -> Dict[str, Any]:
    """查询店铺排名（混合查询模式）"""
    use_mv = self.should_use_materialized_view(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        platform_codes=platform_codes,
        shop_ids=shop_ids
    )
    
    if use_mv:
        return self.query_shop_ranking_from_mv(...)
    else:
        return self.query_shop_ranking_realtime(...)
```

---

## 🧪 测试验证

### 测试场景1：物化视图查询

**测试条件**:
- 时间范围：最近30天（在2年内）
- 粒度：daily
- 店铺数：≤10个
- 平台数：≤3个

**预期结果**:
- `query_type` = "materialized_view"
- 响应时间 < 100ms

### 测试场景2：实时计算查询

**测试条件**:
- 时间范围：3年前（超出2年）
- 粒度：daily
- 店铺数：≤10个

**预期结果**:
- `query_type` = "realtime"
- 响应时间 1-3s

### 测试场景3：大规模筛选

**测试条件**:
- 时间范围：最近30天（在2年内）
- 粒度：daily
- 店铺数：>10个（超出阈值）

**预期结果**:
- `query_type` = "realtime"
- 自动降级到实时计算

---

## 📊 性能优化建议

### 1. 物化视图优化

- **保留期限**: 2年（730天）
- **粒度**: 只存储daily粒度，weekly/monthly从daily聚合计算
- **定期刷新**: 每15分钟刷新一次（已实现）
- **自动清理**: 定期清理过期数据（待实现）

### 2. 实时计算优化

- **索引优化**: 确保fact表有适当的索引（platform_code, shop_id, order_date_local）
- **查询优化**: 使用批量查询，避免N+1查询问题
- **缓存策略**: 对计算结果进行短期缓存（5-10分钟）

### 3. 归档表优化（未来实现）

- **归档策略**: 5年以上数据归档为monthly粒度
- **查询方式**: 从归档表查询，避免查询大量历史数据

---

## ⚠️ 注意事项

### 1. 物化视图数据时效性

- 物化视图数据可能不是实时的（最多延迟15分钟）
- 对于需要实时数据的场景，应该使用实时计算

### 2. 查询性能权衡

- 物化视图查询快但数据可能不实时
- 实时计算数据实时但查询较慢
- 根据业务需求选择合适的查询方式

### 3. 前端时间维度切换

- 前端切换时间维度（日→周→月）时，系统自动选择最优查询方式
- 前端自定义时间范围时，系统自动使用实时计算
- 前端无需关心查询方式，统一API接口

---

## 📚 相关文档

- [数据分类传输规范指南](DATA_CLASSIFICATION_API_GUIDE.md) - C类数据API规范
- [API契约开发指南](API_CONTRACTS.md) - API响应格式和调用规范
- [C类数据查询服务代码](backend/services/c_class_data_service.py) - 服务实现代码

---

**最后更新**: 2025-01-16  
**维护**: AI Agent Team  
**状态**: 📋 实施指南，待API迁移

