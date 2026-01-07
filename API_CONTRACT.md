# API 契约（唯一真源）

版本: v1.1
更新日期: 2025-01-31
状态: 稳定

本文件定义后端查询与字段映射相关接口的入参、出参与约束，前后端以及脚本均以此为唯一参考，不在其他文档重复维护。

**重要说明**：
- **响应格式标准**：所有API响应格式必须符合 `docs/API_CONTRACTS.md` 中定义的统一响应格式标准
- **错误处理标准**：所有API错误处理必须符合 `docs/API_CONTRACTS.md` 中定义的错误处理标准
- **格式规范**：本文件定义具体接口的入参、出参，格式规范请参考 `docs/API_CONTRACTS.md`

## v1.1更新摘要（2025-01-31）

- 新增：数据隔离区API（5个端点）
- 更新：/ingest响应新增amount_imported字段（v4.6.0多货币支持）
- 新增：Pattern-based Mapping支持
- 新增：数据质量监控API（3个端点，C类数据核心字段优化计划）

## 1. 看板查询 API

路径: `GET /api/dashboard/overview`

入参（Query）:
- `platforms: string[]` 可选
- `accounts: string[]` 可选
- `shops: string[]` 可选
- `start_date: string` 必选，YYYY-MM-DD
- `end_date: string` 必选，YYYY-MM-DD
- `granularity: string` 可选，daily|weekly|monthly，默认daily

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
  "kpi": {
    "gmv": 12345.67,
    "orders": 890,
    "conversion_rate": 0.034,
    "aov": 13.88
  },
  "last_update": "2025-10-30T12:00:00Z",
  "source": "mv_sales_day_shop_sku"
  },
  "timestamp": "2025-01-31T10:00:00Z"
}
```

错误码:
- 400 参数错误（时间范围非法等）
- 500 服务端异常

约束:
- 查询只读、无DDL；超时5s回退到最近一次MV快照。

## 2. 字段映射 - 智能建议 API

路径: `POST /api/field-mapping/apply-template`

入参（JSON Body）:
```json
{
  "source_platform": "shopee",
  "domain": "orders",
  "sub_domain": "",
  "granularity": "daily",
  "columns": ["订单号", "下单时间", "sku", "数量", "销售额"]
}
```

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
  "source": "ai_suggested|template",
  "mappings": {
    "订单号": {"standard": "order_id", "confidence": 1.0, "method": "exact_match"}
  }
  },
  "timestamp": "2025-01-31T10:00:00Z"
}
```

约束:
- 关键字段仅在置信度≥阈值或人工确认后写入事实表；其余进入attributes。

## 3. 数据隔离摘要 API（用于审核）

路径: `GET /api/ingest/quarantine/summary?file_id=123`

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
  "file_id": 123,
  "errors": 12,
  "warnings": 5,
  "top_issues": [
    {"type": "missing_key_field", "count": 8},
    {"type": "fx_missing", "count": 4}
  ]
  },
  "timestamp": "2025-01-31T10:00:00Z"
}
```

## 4. 数据隔离区 API（v4.6.0新增）⭐

### 4.1 查询隔离数据列表

路径: `GET /api/data-quarantine/list`

入参（Query）:
- `file_id: int` 可选，文件ID
- `platform: string` 可选，平台代码
- `data_domain: string` 可选，数据域
- `error_type: string` 可选，错误类型
- `page: int` 可选，页码（默认1）
- `page_size: int` 可选，每页数量（默认20，最大100）

返回（200 JSON）:
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "file_id": 123,
      "file_name": "shopee_orders_20250131.xlsx",
      "platform_code": "shopee",
      "data_domain": "orders",
      "row_index": 5,
      "error_type": "validation_error",
      "error_message": "订单号为空",
      "created_at": "2025-01-31T10:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

### 4.2 查看隔离数据详情

路径: `GET /api/data-quarantine/detail/{quarantine_id}`

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "file_id": 123,
    "file_name": "shopee_orders_20250131.xlsx",
    "file_path": "/path/to/file.xlsx",
    "platform_code": "shopee",
    "data_domain": "orders",
    "row_index": 5,
    "raw_data": {"订单号": "", "销售额": 100},
    "error_type": "validation_error",
    "error_message": "订单号为空",
    "validation_errors": {"order_id": "必填字段缺失"},
    "created_at": "2025-01-31T10:00:00"
  }
}
```

### 4.3 重新处理隔离数据

路径: `POST /api/data-quarantine/reprocess`

入参（JSON Body）:
```json
{
  "quarantine_ids": [1, 2, 3],
  "corrections": {"order_id": "123456"}
}
```

返回（200 JSON）:
```json
{
  "success": true,
  "processed": 3,
  "succeeded": 2,
  "failed": 1,
  "errors": [
    {"quarantine_id": 3, "error": "数据仍不符合验证规则"}
  ]
}
```

### 4.4 获取隔离数据统计

路径: `GET /api/data-quarantine/stats`

入参（Query）:
- `platform: string` 可选，平台代码

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "total": 100,
    "by_platform": {"shopee": 60, "miaoshou": 40},
    "by_error_type": {"validation_error": 50, "missing_required_field": 30},
    "by_data_domain": {"orders": 70, "products": 30}
  }
}
```

### 4.5 批量删除隔离数据

路径: `DELETE /api/data-quarantine/delete`

入参（JSON Body）:
```json
{
  "quarantine_ids": [1, 2, 3]
}
```

返回（200 JSON）:
```json
{
  "success": true,
  "deleted": 3
}
```

---

## 5. 数据质量监控 API（C类数据核心字段优化计划新增）⭐

### 5.1 C类数据计算就绪状态查询

路径: `GET /api/data-quality/c-class-readiness`

入参（Query）:
- `platform_code: string` 可选，平台代码
- `shop_id: string` 可选，店铺ID
- `metric_date: string` 可选，指标日期（YYYY-MM-DD），默认今天

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "c_class_ready": true,
    "b_class_completeness": {
      "orders": 100.0,
      "products": 95.0,
      "inventory": 100.0
    },
    "missing_core_fields": [],
    "data_quality_score": 98.5,
    "warnings": [],
    "timestamp": "2025-01-31T10:00:00"
  }
}
```

**字段说明**:
- `c_class_ready`: C类数据计算就绪状态（true=所有核心字段完整）
- `b_class_completeness`: B类数据完整性（orders/products/inventory域，0-100分）
- `missing_core_fields`: 缺失的核心字段列表（如["orders.total_amount_rmb"]）
- `data_quality_score`: 数据质量评分（0-100分）
- `warnings`: 警告信息列表

**错误码**:
- 500 服务端异常

---

### 5.2 B类数据完整性检查

路径: `GET /api/data-quality/b-class-completeness`

入参（Query）:
- `platform_code: string` 必填，平台代码
- `shop_id: string` 必填，店铺ID
- `start_date: string` 可选，开始日期（YYYY-MM-DD），默认30天前
- `end_date: string` 可选，结束日期（YYYY-MM-DD），默认今天

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "platform_code": "shopee",
    "shop_id": "shop001",
    "date_range": {
      "start": "2024-01-01",
      "end": "2024-01-31"
    },
    "daily_checks": [
      {
        "date": "2024-01-01",
        "orders_complete": true,
        "products_complete": false,
        "inventory_complete": true,
        "data_quality_score": 85.0,
        "missing_fields": ["products.conversion_rate"],
        "warnings": ["产品字段conversion_rate存在但值为NULL"]
      }
    ],
    "summary": {
      "total_days": 31,
      "avg_quality_score": 90.5,
      "complete_days": 25,
      "incomplete_days": 6
    }
  }
}
```

**字段说明**:
- `daily_checks`: 每日数据质量检查结果
- `summary`: 汇总统计信息

**错误码**:
- 400 参数错误（platform_code或shop_id缺失）
- 500 服务端异常

---

### 5.3 核心字段状态查询

路径: `GET /api/data-quality/core-fields-status`

入参（Query）:
- `data_domain: string` 可选，数据域（orders/products/inventory）

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "total_fields": 17,
    "present_fields": 15,
    "missing_fields": 2,
    "fields_by_domain": {
      "orders": {
        "total": 6,
        "present": 6,
        "missing": 0,
        "present_fields": ["order_id", "order_date_local", "total_amount_rmb", ...],
        "missing_fields": []
      },
      "products": {
        "total": 8,
        "present": 7,
        "missing": 1,
        "present_fields": ["unique_visitors", "order_count", "rating", ...],
        "missing_fields": ["conversion_rate"]
      },
      "inventory": {
        "total": 2,
        "present": 2,
        "missing": 0,
        "present_fields": ["available_stock", "sales_volume_30d"],
        "missing_fields": []
      }
    },
    "timestamp": "2025-01-31T10:00:00"
  }
}
```

**字段说明**:
- `total_fields`: 核心字段总数（17个）
- `present_fields`: 已存在的字段数
- `missing_fields`: 缺失的字段数
- `fields_by_domain`: 按数据域分组的字段状态

**错误码**:
- 500 服务端异常

**约束**:
- 查询只读，无DDL
- 检查字段在`field_mapping_dictionary`表中的存在性

---

### 5.4 货币策略说明

**货币策略定义**:
- **orders域**: CNY本位币（必须为CNY，禁止多币种）
- **products域**: 无货币（只采集数量指标，禁止货币字段）
- **inventory域**: CNY本位币（必须为CNY，统一从妙手ERP导出）

**数据源优先级**:
- **运营数据**（Shopee、TikTok）: 只采集数量指标，货币数据统一从妙手ERP获取
- **经营数据**（妙手ERP）: 统一CNY本位币，所有金额字段必须为CNY

**详细说明**: 参见`docs/CURRENCY_POLICY.md`

---

## 6. 数据入库 API（v4.6.0增强）⭐

路径: `POST /api/field-mapping/ingest`

入参（JSON Body）:
```json
{
  "file_id": 123,
  "platform": "shopee",
  "domain": "orders",
  "mappings": {...},
  "rows": [...]
}
```

返回（200 JSON）- **v4.6.0新增amount_imported字段**:
```json
{
  "success": true,
  "message": "入库完成，成功导入10条记录，同时导入30条金额维度记录（v4.6.0多货币支持）",
  "staged": 10,
  "imported": 10,
  "amount_imported": 30,
  "quarantined": 0,
  "validation": {
    "total_rows": 10,
    "valid_rows": 10,
    "error_rows": 0,
    "warnings": 0
  },
  "analysis": {
    "all_zero_data": false,
    "quarantine_summary": null
  }
}
```

**v4.6.0变更说明**：
- 新增`amount_imported`字段：表示导入到fact_order_amounts维度表的记录数
- 计算方式：每行数据的每个pattern-based字段（如"销售额（已付款）（BRL）"）生成一条维度记录
- 示例：1行数据 × 3个pattern-based字段 = 3条amount_imported

---

## 7. C类数据计算 API（v4.11.1新增）⭐

### 6.1 销售战役达成率计算

路径: `POST /api/sales-campaigns/{campaign_id}/calculate`

入参（Path）:
- `campaign_id: int` 必选，战役ID

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "campaign_name": "双11大促",
    "target_amount": 100000.0,
    "actual_amount": 85000.0,
    "achievement_rate": 85.0,
    "status": "active"
  },
  "message": "达成情况计算完成"
}
```

### 6.2 目标达成率计算

路径: `POST /api/target-management/{target_id}/calculate`

入参（Path）:
- `target_id: int` 必选，目标ID

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "target_name": "11月销售目标",
    "target_amount": 500000.0,
    "achieved_amount": 450000.0,
    "achievement_rate": 90.0,
    "status": "active"
  },
  "message": "达成情况计算完成"
}
```

### 6.3 店铺健康度评分计算

路径: `POST /api/store-analytics/health-scores/calculate`

入参（Query）:
- `platform_code: string` 必选，平台代码
- `shop_id: string` 必选，店铺ID
- `metric_date: string` 可选，指标日期（YYYY-MM-DD），默认昨天
- `granularity: string` 可选，粒度（daily/weekly/monthly），默认daily

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "health_score": 85.5,
    "gmv_score": 28.0,
    "conversion_score": 22.0,
    "inventory_score": 20.0,
    "service_score": 15.5,
    "risk_level": "low",
    "risk_factors": []
  }
}
```

### 6.4 店铺健康度历史趋势

路径: `GET /api/store-analytics/health-scores/{shop_id}/history`

入参（Path + Query）:
- `shop_id: string` 必选，店铺ID
- `platform_code: string` 可选，平台筛选
- `start_date: string` 可选，开始日期（YYYY-MM-DD），默认30天前
- `end_date: string` 可选，结束日期（YYYY-MM-DD），默认今天
- `granularity: string` 可选，粒度（daily/weekly/monthly），默认daily

返回（200 JSON）:
```json
{
  "success": true,
  "data": [
    {
      "date": "2025-11-14",
      "health_score": 85.5,
      "gmv_score": 28.0,
      "conversion_score": 22.0,
      "inventory_score": 20.0,
      "service_score": 15.5,
      "risk_level": "low"
    }
  ],
  "shop_id": "shop_1",
  "granularity": "daily"
}
```

### 6.5 店铺预警查询

路径: `GET /api/store-analytics/alerts`

入参（Query）:
- `platform_code: string` 可选，平台筛选
- `shop_id: string` 可选，店铺筛选
- `alert_level: string` 可选，预警级别（critical/warning/info）
- `is_resolved: boolean` 可选，是否已解决
- `page: int` 可选，页码（默认1）
- `page_size: int` 可选，每页数量（默认20，最大100）

返回（200 JSON）:
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "platform_code": "shopee",
      "shop_id": "shop_1",
      "shop_name": "店铺1",
      "alert_type": "health_score_critical",
      "alert_level": "critical",
      "title": "店铺健康度严重不足",
      "message": "店铺健康度评分仅为55.0分，需要立即关注",
      "metric_value": 55.0,
      "threshold": 60.0,
      "is_resolved": false,
      "created_at": "2025-11-15T10:00:00Z"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "has_more": false
}
```

### 6.6 店铺预警解决

路径: `POST /api/store-analytics/alerts/{alert_id}/resolve`

入参（Path）:
- `alert_id: int` 必选，预警ID

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "is_resolved": true,
    "resolved_at": "2025-11-15T12:00:00Z"
  },
  "message": "预警已标记为已解决"
}
```

### 6.7 店铺预警统计

路径: `GET /api/store-analytics/alerts/stats`

入参（Query）:
- `platform_code: string` 可选，平台筛选
- `shop_id: string` 可选，店铺筛选

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "total": 25,
    "resolved": 10,
    "unresolved": 15,
    "by_level": {
      "critical": 5,
      "warning": 15,
      "info": 5
    },
    "by_type": {
      "health_score_critical": 3,
      "conversion_rate_warning": 8,
      "inventory_turnover_warning": 4
    }
  }
}
```

### 6.8 店铺赛马排名（增强版 - 含环比）

路径: `GET /api/business-overview/shop-racing`

入参（Query）:
- `granularity: string` 必选，数据粒度（daily/weekly/monthly）
- `date: string` 必选，具体日期（YYYY-MM-DD）
- `group_by: string` 可选，分组方式（shop/platform），默认shop
- `platforms: string` 可选，平台筛选（逗号分隔）

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "groups": [
      {
        "group_name": "A组",
        "shops": [
          {
            "shop_id": "shop_1",
            "shop_name": "店铺1",
            "target": 100.0,
            "achieved": 88.0,
            "achievement_rate": 88.0,
            "rank": 1,
            "mom_growth_rate": 15.5,
            "compare_amount": 76.2,
            "order_count": 120
          }
        ]
      }
    ],
    "granularity": "daily",
    "date": "2025-11-15"
  }
}
```

**v4.11.1新增字段**:
- `mom_growth_rate`: 环比增长率（%）
- `compare_amount`: 对比期间销售额（万元）

### 6.9 经营指标查询（增强版 - 从sales_targets读取目标）

路径: `GET /api/business-overview/operational-metrics`

入参（Query）:
- `date: string` 可选，查询日期（YYYY-MM-DD），默认今天
- `platforms: string` 可选，平台筛选（逗号分隔）
- `shops: string` 可选，店铺筛选（逗号分隔）

返回（200 JSON）:
```json
{
  "success": true,
  "data": {
    "time_progress": 50.0,
    "monthly_target": 100.0,
    "monthly_total_achieved": 85.0,
    "today_sales": 3.5,
    "monthly_achievement_rate": 85.0,
    "time_gap": 35.0,
    "estimated_gross_profit": 12.75,
    "estimated_expenses": 31.0,
    "operating_result": -18.25,
    "operating_result_text": "亏损",
    "monthly_order_count": 1200,
    "today_order_count": 50
  }
}
```

**v4.11.1变更说明**:
- `monthly_target`字段现在从`sales_targets`表读取，而非使用默认值
- 如果未找到目标，则使用历史平均值或当前达成值的120%作为默认值

---

## 变更流程
- 破坏性修改需在此文件先更新契约，并在`CHANGELOG.md`记录；前端/脚本变更后同步合并。
- 本文件为根目录白名单文档之一：README.md / CHANGELOG.md / API_CONTRACT.md。


