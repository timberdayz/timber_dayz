# 运营数据事实表实施总结

**版本**: v4.12.0  
**完成时间**: 2025-11-21  
**状态**: ✅ 表结构创建完成

---

## 📋 概述

本文档总结了运营数据事实表（FactTraffic、FactService、FactAnalytics）的实施情况。

---

## ✅ 实施内容

### 1. 数据库迁移脚本

**文件**: `migrations/versions/20251121_132800_create_operational_data_tables.py`

**创建的表**:
- `fact_traffic` - 流量数据表
- `fact_service` - 服务数据表
- `fact_analytics` - 分析数据表

**表结构特点**:
- ✅ 自增ID主键（便于外键引用和性能优化）
- ✅ shop_id为核心字段（运营数据主键设计规则）
- ✅ 业务唯一索引（platform_code + shop_id + date + granularity + metric_type + data_domain）
- ✅ account替代索引（当shop_id为NULL时）
- ✅ file_id外键关联（关联catalog_files表）
- ✅ attributes字段（JSONB类型，存储额外信息）

---

### 2. ORM模型定义

**文件**: `modules/core/db/schema.py`

**新增模型**:
- `FactTraffic` - 流量数据模型
- `FactService` - 服务数据模型
- `FactAnalytics` - 分析数据模型

**模型特点**:
- ✅ 符合运营数据主键设计规则（自增ID主键 + shop_id为核心的唯一索引）
- ✅ 字段类型和约束与数据库迁移脚本一致
- ✅ 包含完整的文档字符串说明

---

### 3. 模型导出

**文件**: `modules/core/db/__init__.py`

**更新内容**:
- ✅ 添加FactTraffic、FactService、FactAnalytics到导出列表

---

## 📊 表结构详情

### FactTraffic（流量数据表）

**核心字段**:
- `platform_code` - 平台代码（必填）
- `shop_id` - 店铺ID（可选，运营数据核心字段）
- `account` - 账号（可选，shop_id的替代）
- `traffic_date` - 流量日期（必填）
- `granularity` - 粒度（daily/weekly/monthly）
- `metric_type` - 指标类型（如visitors、page_views等）
- `metric_value` - 指标值（必填，默认0.0）

**业务唯一索引**:
- `uq_fact_traffic_business`: platform_code + shop_id + traffic_date + granularity + metric_type + data_domain
- `uq_fact_traffic_account`: platform_code + account + traffic_date + granularity + metric_type + data_domain（当shop_id为NULL时）

---

### FactService（服务数据表）

**核心字段**:
- `platform_code` - 平台代码（必填）
- `shop_id` - 店铺ID（可选，运营数据核心字段）
- `account` - 账号（可选，shop_id的替代）
- `service_date` - 服务日期（必填）
- `granularity` - 粒度（daily/weekly/monthly）
- `metric_type` - 指标类型（如service_count、unreplied_messages等）
- `metric_value` - 指标值（必填，默认0.0）

**业务唯一索引**:
- `uq_fact_service_business`: platform_code + shop_id + service_date + granularity + metric_type + data_domain
- `uq_fact_service_account`: platform_code + account + service_date + granularity + metric_type + data_domain（当shop_id为NULL时）

---

### FactAnalytics（分析数据表）

**核心字段**:
- `platform_code` - 平台代码（必填）
- `shop_id` - 店铺ID（可选，运营数据核心字段）
- `account` - 账号（可选，shop_id的替代）
- `analytics_date` - 分析日期（必填）
- `granularity` - 粒度（daily/weekly/monthly）
- `metric_type` - 指标类型（如conversion_rate、bounce_rate等）
- `metric_value` - 指标值（必填，默认0.0）

**业务唯一索引**:
- `uq_fact_analytics_business`: platform_code + shop_id + analytics_date + granularity + metric_type + data_domain
- `uq_fact_analytics_account`: platform_code + account + analytics_date + granularity + metric_type + data_domain（当shop_id为NULL时）

---

## ✅ 设计规则符合性

### 运营数据主键设计规则

- ✅ **自增ID主键**: 所有表使用自增ID作为主键
- ✅ **shop_id为核心**: 业务唯一索引以shop_id为核心字段
- ✅ **account替代**: 当shop_id为NULL时，使用account作为替代
- ✅ **唯一索引**: 使用部分索引（WHERE条件）确保业务唯一性

### 字段必填规则

- ✅ **金额字段**: metric_value使用NOT NULL，默认值为0.0
- ✅ **业务标识**: platform_code、date、granularity、metric_type为NOT NULL
- ✅ **可选字段**: shop_id、account允许NULL（根据数据归属规则）

### 数据归属规则

- ✅ **shop_id获取**: 从源数据或文件元数据中获取
- ✅ **account替代**: 当shop_id无法获取时，使用account
- ✅ **file_id关联**: 关联catalog_files表，支持数据溯源

---

## 📝 待完成工作

### 数据导入服务

**状态**: 待实施

**需要评估**:
- 现有运营数据的格式和结构
- 数据导入流程的集成点
- 字段映射规则的配置

**建议**:
- 参考FactOrder和FactProductMetric的数据导入流程
- 创建专门的数据导入服务（如`data_importer_traffic.py`）
- 支持从文件元数据（.meta.json）中提取shop_id和account信息

---

## 🔧 使用方法

### 运行数据库迁移

```bash
# 运行迁移
alembic upgrade head

# 或使用Python脚本
python scripts/run_migration.py
```

### 使用ORM模型

```python
from modules.core.db import FactTraffic, FactService, FactAnalytics

# 创建流量数据记录
traffic = FactTraffic(
    platform_code="shopee",
    shop_id="HXHOME",
    traffic_date=date(2025, 11, 21),
    granularity="daily",
    metric_type="visitors",
    metric_value=1000
)
db.add(traffic)
db.commit()
```

---

## 📚 相关文档

- [运营数据事实表设计文档](docs/OPERATIONAL_DATA_TABLES_DESIGN.md)
- [数据库设计规范](openspec/changes/establish-database-design-rules/specs/database-design/spec.md)
- [最终实施状态报告](docs/FINAL_IMPLEMENTATION_STATUS.md)

---

**最后更新**: 2025-11-21  
**维护**: AI Agent Team  
**状态**: ✅ 表结构创建完成，数据导入服务待实施

