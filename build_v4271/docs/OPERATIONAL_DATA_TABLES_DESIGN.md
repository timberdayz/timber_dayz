# 运营数据事实表设计文档

**版本**: v4.12.0  
**创建时间**: 2025-11-21  
**状态**: 📋 设计文档

---

## 📋 设计概述

根据数据库设计规范，运营数据（traffic、services、analytics）应该与经营数据（orders、products、inventory）分离存储，使用不同的主键设计规则。

**核心原则**:
- **经营数据**: 以SKU为核心标识（如FactProductMetric）
- **运营数据**: 以shop_id为核心标识（需要创建新表）

---

## 🎯 设计目标

创建运营数据事实表，支持以下数据域：
1. **traffic** - 流量数据（UV、PV、转化率等）
2. **services** - 服务数据（客服、AI助手等）
3. **analytics** - 分析数据（数据分析指标）

---

## 📊 表结构设计

### FactTraffic（流量数据表）

**主键设计**: 自增ID + 业务唯一索引

**业务唯一索引**: `(platform_code, shop_id, metric_date, metric_type, granularity)`

**核心字段**:
- `id` (Integer, Primary Key, Auto Increment)
- `platform_code` (String(32), NOT NULL)
- `shop_id` (String(64), NOT NULL)
- `metric_date` (Date, NOT NULL)
- `granularity` (String(16), NOT NULL, default='daily')  # daily/weekly/monthly
- `metric_type` (String(32), NOT NULL)  # uv/pv/conversion_rate/bounce_rate等
- `metric_value` (Float, nullable=True)
- `metric_value_rmb` (Float, nullable=True)  # 如果需要货币转换
- `attributes` (JSONB, nullable=True)  # 其他扩展字段
- `file_id` (Integer, ForeignKey, nullable=True)
- `created_at` (DateTime, NOT NULL)
- `updated_at` (DateTime, NOT NULL)

**索引设计**:
- 主键索引: `id`
- 业务唯一索引: `(platform_code, shop_id, metric_date, metric_type, granularity)`
- 查询索引: `(platform_code, shop_id, metric_date)`
- 查询索引: `(metric_type, metric_date)`

---

### FactService（服务数据表）

**主键设计**: 自增ID + 业务唯一索引

**业务唯一索引**: `(platform_code, shop_id, metric_date, metric_type, granularity)`

**核心字段**:
- `id` (Integer, Primary Key, Auto Increment)
- `platform_code` (String(32), NOT NULL)
- `shop_id` (String(64), NOT NULL)
- `metric_date` (Date, NOT NULL)
- `granularity` (String(16), NOT NULL, default='daily')
- `metric_type` (String(32), NOT NULL)  # customer_service_count/ai_assistant_count/unreplied_messages等
- `metric_value` (Float, nullable=True)
- `attributes` (JSONB, nullable=True)  # 其他扩展字段
- `file_id` (Integer, ForeignKey, nullable=True)
- `created_at` (DateTime, NOT NULL)
- `updated_at` (DateTime, NOT NULL)

**索引设计**:
- 主键索引: `id`
- 业务唯一索引: `(platform_code, shop_id, metric_date, metric_type, granularity)`
- 查询索引: `(platform_code, shop_id, metric_date)`
- 查询索引: `(metric_type, metric_date)`

---

### FactAnalytics（分析数据表）

**主键设计**: 自增ID + 业务唯一索引

**业务唯一索引**: `(platform_code, shop_id, metric_date, metric_type, granularity)`

**核心字段**:
- `id` (Integer, Primary Key, Auto Increment)
- `platform_code` (String(32), NOT NULL)
- `shop_id` (String(64), NOT NULL)
- `metric_date` (Date, NOT NULL)
- `granularity` (String(16), NOT NULL, default='daily')
- `metric_type` (String(32), NOT NULL)  # 各种分析指标类型
- `metric_value` (Float, nullable=True)
- `attributes` (JSONB, nullable=True)  # 其他扩展字段
- `file_id` (Integer, ForeignKey, nullable=True)
- `created_at` (DateTime, NOT NULL)
- `updated_at` (DateTime, NOT NULL)

**索引设计**:
- 主键索引: `id`
- 业务唯一索引: `(platform_code, shop_id, metric_date, metric_type, granularity)`
- 查询索引: `(platform_code, shop_id, metric_date)`
- 查询索引: `(metric_type, metric_date)`

---

## 🔄 数据入库流程

### shop_id获取规则

1. **优先级1**: 从源数据获取shop_id
2. **优先级2**: 从文件元数据（file_record）获取shop_id
3. **优先级3**: 从.meta.json文件获取shop_id和account信息
4. **优先级4**: 如果都没有，允许shop_id为NULL（平台级数据）

### platform_code获取规则

1. **优先级1**: 从源数据获取platform_code
2. **优先级2**: 从文件元数据（file_record）获取platform_code
3. **优先级3**: 使用默认值"unknown"

### 数据验证规则

- 主键字段（platform_code、shop_id、metric_date、metric_type）必须存在
- 如果主键字段缺失，数据应隔离到data_quarantine表

---

## 📝 实施计划

### 阶段1: 表结构设计（待完成）
- [ ] 设计FactTraffic表结构
- [ ] 设计FactService表结构
- [ ] 设计FactAnalytics表结构

### 阶段2: 数据库迁移（待完成）
- [ ] 创建Alembic迁移脚本
- [ ] 更新schema.py，添加ORM模型
- [ ] 运行数据库迁移

### 阶段3: 数据导入服务（待完成）
- [ ] 创建数据导入服务，支持运营数据入库
- [ ] 更新data_ingestion_service.py，支持运营数据域
- [ ] 更新data_importer.py，添加upsert_traffic、upsert_service、upsert_analytics函数

### 阶段4: 数据验证（待完成）
- [ ] 创建数据验证服务，验证运营数据
- [ ] 更新data_validator.py，添加validate_traffic、validate_service、validate_analytics函数

### 阶段5: 物化视图（待完成）
- [ ] 创建mv_traffic_summary主视图（已创建）
- [ ] 创建mv_service_summary主视图
- [ ] 创建mv_analytics_summary主视图

---

## ⚠️ 注意事项

1. **当前状态**: 
   - 目前traffic、services、analytics数据可能存储在FactProductMetric表中
   - 需要评估现有数据，决定是否需要数据迁移

2. **向后兼容**:
   - 创建新表后，需要保持与现有系统的兼容性
   - 可能需要数据迁移脚本，将现有数据从FactProductMetric迁移到新表

3. **性能考虑**:
   - 运营数据表应该优化查询性能
   - 需要创建合适的索引，支持常见查询场景

---

## 📚 参考文档

- [数据库设计规范](openspec/changes/establish-database-design-rules/specs/database-design/spec.md)
- [数据库设计规则实施总结](docs/DATABASE_DESIGN_RULES_IMPLEMENTATION_SUMMARY.md)
- [Schema.py合规性审查报告](docs/SCHEMA_COMPLIANCE_REVIEW.md)

---

**最后更新**: 2025-11-21  
**维护**: AI Agent Team  
**状态**: 📋 设计文档

