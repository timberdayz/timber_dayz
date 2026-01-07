# 后端服务DSS架构重构检查清单

## 概述

本文档用于检查后端服务是否已经完全适配DSS（决策支持系统）架构。

**创建时间**: 2025-11-27  
**架构版本**: DSS v4.6.0  
**检查状态**: ⚠️ **未完成**

---

## 核心原则

根据DSS架构设计：
1. **后端只负责ETL**：数据采集、清洗、验证、入库
2. **移除KPI计算逻辑**：不再在Python中硬编码计算逻辑
3. **移除物化视图依赖**：Metabase直接查询原始表
4. **移除标准字段映射**：直接保存原始中文表头
5. **C类数据由Metabase计算**：不再在后端计算

---

## 检查清单

### ✅ 已完成的项目

#### 1. 数据库配置
- [x] PostgreSQL `search_path` 配置完成（`backend/models/database.py`）
- [x] 支持多schema访问（public, b_class, a_class, c_class, core, finance）
- [x] 数据库连接配置正确

#### 2. 数据入库服务
- [x] B类数据入库服务重构完成（`backend/services/raw_data_importer.py`）
- [x] 支持JSONB格式存储（中文字段名作为键）
- [x] 按data_domain+granularity分表存储
- [x] 多层去重策略实现

#### 3. 字段映射系统
- [x] 字段映射系统重构完成（不再映射到标准字段）
- [x] 直接保存原始中文表头
- [x] 模板匹配逻辑更新

#### 4. 数据浏览器API
- [x] 多schema支持完成（`backend/routers/data_browser.py`）
- [x] 支持查询所有schema中的表

#### 5. A类数据管理API
- [x] 销售目标API实现（`backend/routers/config_management.py`）
- [x] 复制上月目标功能实现
- [x] 批量计算达成率功能实现

#### 6. Metabase集成
- [x] Metabase代理API实现（`backend/routers/metabase_proxy.py`）
- [x] Metabase性能测试脚本创建（`scripts/test_metabase_performance.py`）

---

### ❌ 需要重构的项目

#### 1. 物化视图相关代码（需要移除或标记废弃）

**问题**: 根据DSS架构，Metabase直接查询原始表，不再需要物化视图。

**需要处理的文件**:

1. **`backend/main.py`** (第198-204行, 238-244行)
   - [ ] 移除或注释物化视图刷新调度器启动代码
   - [ ] 移除或注释物化视图刷新调度器停止代码
   - **状态**: ⚠️ 仍然启动物化视图刷新调度器

2. **`backend/routers/materialized_views.py`**
   - [ ] 标记为废弃（Deprecated）
   - [ ] 添加废弃说明和替代方案
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被注册和使用

3. **`backend/routers/field_mapping_dictionary_mv_display.py`**
   - [ ] 标记为废弃（Deprecated）
   - [ ] 添加废弃说明和替代方案
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被注册和使用

4. **`backend/tasks/materialized_view_refresh.py`**
   - [ ] 标记为废弃（Deprecated）
   - [ ] 添加废弃说明
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被调用

**替代方案**: 
- 使用Metabase直接查询原始表（`b_class.fact_raw_data_*`）
- 使用Metabase的查询缓存功能
- 使用Metabase的定时计算任务（C类数据）

---

#### 2. 废弃的Dashboard API（需要标记废弃）

**问题**: 根据DSS架构，Dashboard数据应该由Metabase提供，不再需要后端计算KPI。

**需要处理的文件**:

1. **`backend/routers/dashboard_api.py`**
   - [ ] 添加Deprecated标记
   - [ ] 添加废弃说明和替代方案（使用Metabase Dashboard）
   - [ ] 返回410 Gone状态码或警告信息
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被注册和使用

2. **`backend/routers/metrics.py`**
   - [ ] 添加Deprecated标记
   - [ ] 添加废弃说明和替代方案（使用Metabase Question）
   - [ ] 返回410 Gone状态码或警告信息
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被注册和使用

3. **`backend/routers/store_analytics.py`**
   - [ ] 添加Deprecated标记
   - [ ] 添加废弃说明和替代方案（使用Metabase Dashboard）
   - [ ] 返回410 Gone状态码或警告信息
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被注册和使用

4. **`backend/routers/main_views.py`**
   - [ ] 添加Deprecated标记
   - [ ] 添加废弃说明和替代方案（使用Metabase直接查询原始表）
   - [ ] 返回410 Gone状态码或警告信息
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被注册和使用

**替代方案**:
- 使用Metabase Dashboard嵌入（`frontend/src/views/Dashboard.vue`）
- 使用Metabase Question API查询数据
- 使用Metabase Embedding功能

---

#### 3. C类数据计算调度器（需要移除或标记废弃）

**问题**: 根据DSS架构，C类数据应该由Metabase定时计算任务计算，不再在后端计算。

**需要处理的文件**:

1. **`backend/main.py`** (第206-215行, 246-252行)
   - [ ] 移除或注释C类数据计算调度器启动代码
   - [ ] 移除或注释C类数据计算调度器停止代码
   - **状态**: ⚠️ 仍然启动C类数据计算调度器

2. **`backend/services/scheduler_service.py`**
   - [ ] 标记为废弃（Deprecated）
   - [ ] 添加废弃说明和替代方案（使用Metabase定时计算任务）
   - [ ] 在Phase 6删除
   - **状态**: ⚠️ 仍然被调用

**替代方案**:
- 使用Metabase定时计算任务（每20分钟执行一次）
- 使用Metabase Question API查询计算结果
- 计算结果存储在C类数据表（`c_class.*`）

---

#### 4. KPI计算逻辑（需要检查）

**问题**: 根据DSS架构，KPI计算应该由Metabase完成，不再在后端计算。

**需要检查的文件**:

1. **`backend/services/`** 目录下的所有服务文件
   - [ ] 检查是否有KPI计算逻辑
   - [ ] 标记需要移除的KPI计算代码
   - [ ] 添加废弃说明和替代方案

2. **`backend/routers/`** 目录下的所有路由文件
   - [ ] 检查是否有KPI计算API
   - [ ] 标记需要移除的KPI计算API
   - [ ] 添加废弃说明和替代方案

---

## 重构计划

### Phase 1: 标记废弃（当前阶段）

**目标**: 标记所有需要废弃的API和服务，但不删除代码。

**步骤**:
1. 在所有废弃的API文件中添加Deprecated标记
2. 添加废弃说明和替代方案
3. 返回410 Gone状态码或警告信息
4. 更新文档说明废弃原因

**预计时间**: 1天

### Phase 2: 前端迁移（Phase 4）

**目标**: 前端迁移到使用Metabase Dashboard和Question API。

**步骤**:
1. 修改前端Dashboard页面，使用Metabase嵌入
2. 修改前端其他页面，使用Metabase Question API
3. 移除对废弃API的调用

**预计时间**: 2周

### Phase 3: 代码清理（Phase 6）

**目标**: 删除所有废弃的代码。

**步骤**:
1. 删除废弃的API文件
2. 删除废弃的服务文件
3. 删除物化视图相关代码
4. 删除C类数据计算调度器代码
5. 更新文档

**预计时间**: 1周

---

## 检查命令

### 检查物化视图相关代码
```bash
grep -r "materialized.*view\|物化视图\|mv_\|refresh.*mv\|MaterializedView" backend/ --include="*.py"
```

### 检查废弃的API
```bash
grep -r "dashboard_api\|metrics\.py\|store_analytics\|main_views" backend/ --include="*.py"
```

### 检查KPI计算逻辑
```bash
grep -r "KPI\|kpi\|计算.*率\|达成率\|转化率" backend/services/ --include="*.py"
```

---

## 当前状态总结

**完成度**: 约70%

**已完成**:
- ✅ 数据库配置和schema分离
- ✅ 数据入库服务重构
- ✅ 字段映射系统重构
- ✅ 数据浏览器API多schema支持
- ✅ A类数据管理API
- ✅ Metabase集成基础

**待完成**:
- ❌ 移除物化视图相关代码
- ❌ 标记废弃的Dashboard API
- ❌ 移除C类数据计算调度器
- ❌ 检查并移除KPI计算逻辑

---

## 下一步行动

1. **立即行动**（可以完成）:
   - [ ] 标记所有废弃的API为Deprecated
   - [ ] 添加废弃说明和替代方案
   - [ ] 注释掉物化视图刷新调度器启动代码
   - [ ] 注释掉C类数据计算调度器启动代码

2. **Phase 4行动**（前端迁移）:
   - [ ] 前端迁移到Metabase Dashboard
   - [ ] 移除对废弃API的调用

3. **Phase 6行动**（代码清理）:
   - [ ] 删除所有废弃的代码
   - [ ] 清理物化视图相关代码
   - [ ] 清理C类数据计算调度器代码

---

**最后更新**: 2025-11-27  
**维护**: AI Agent Team

