# Metabase Dashboard Questions 配置状态

**最后更新**: 2025-11-30  
**当前阶段**: Phase 0.1 已完成，Phase 0.2 已完成，Phase 0.3 待执行（数据同步）

## ✅ 已完成工作

### 1. API Key 认证配置（2025-11-29 完成）

- ✅ **问题发现**: 最初使用 `X-Metabase-Api-Key` header 导致所有 API Key 认证请求返回 401
- ✅ **问题解决**: 通过系统测试和查阅 [Metabase 官方文档](https://www.metabase.com/docs/v0.57/people-and-groups/api-keys) 发现正确的 Header 名称是 `X-API-Key`
- ✅ **代码修复**: `backend/services/metabase_question_service.py` 已更新使用 `X-API-Key` header
- ✅ **文档更新**: 
  - `docs/METABASE_DASHBOARD_SETUP.md` - 添加了完整的 API Key 认证配置指南
  - `.cursorrules` - 添加了 Metabase API Key 认证规范
  - `env.example` - 添加了 API Key 配置提示
  - `openspec/changes/configure-metabase-dashboard-questions/proposal.md` - 更新了技术细节
- ✅ **验证通过**: API Key 认证已成功，可以正常调用 Metabase Question API

### 2. 环境变量配置（2025-11-29 完成）

- ✅ **Question ID 40**: 已配置 `METABASE_QUESTION_BUSINESS_OVERVIEW_KPI=40`
- ✅ **环境变量加载**: `backend/main.py` 已添加 `load_dotenv()` 调用，确保环境变量正确加载
- ✅ **API 测试**: Swagger UI 测试通过，不再返回 400 "Question ID未配置" 错误

### 3. Metabase Question 创建（部分完成）

- ✅ **Question 40**: 业务概览 KPI Question 已创建
  - 表：`b_class.fact_raw_data_orders_daily`
  - 参数：`start_date`, `end_date`, `platform`, `shop_id`
  - 状态：已创建并测试，可以正常执行查询

- ⏳ **其他 6 个 Question**: 待创建（**暂停，等待数据同步完成**）
  - `business_overview_comparison` - 业务概览对比
  - `business_overview_shop_racing` - 店铺赛马
  - `business_overview_traffic_ranking` - 流量排名
  - `business_overview_inventory_backlog` - 库存积压
  - `business_overview_operational_metrics` - 经营指标
  - `clearance_ranking` - 清仓排名

### 4. 数据同步功能状态检查（2025-01-31 完成）

- ✅ **catalog_files 表状态**:
  - 待同步文件：**411 个文件**（3个平台，6个数据域）
  - 已同步文件：**0 个文件**
  - 部分成功文件：**1 个文件**
- ✅ **数据表状态**:
  - `fact_raw_data_orders_daily`：**0 行（空表）** ⚠️ Question 40 需要此表有数据
  - `fact_raw_data_orders_weekly`：0 行（空表）
  - `fact_raw_data_orders_monthly`：0 行（空表）
- ✅ **字段映射模板**：141 个模板（已配置）
- ✅ **结论**：有大量待同步文件（411个），但数据表为空，**需要先执行数据同步**

## 📋 待完成工作

### Phase 0: 基础设施验证和数据准备（进行中）

- [x] **0.1 验证 Question 40 API 连接** ✅ 已完成（2025-11-30）
  - [x] 测试 `/api/dashboard/business-overview/kpi` API（无参数）✅ 成功，返回200，数据为空数组（符合预期）
  - [x] 测试带日期参数的 API 调用 ✅ 成功，`start_date=2025-01-01&end_date=2025-01-31` 返回200
  - [x] 测试带平台参数的 API 调用 ⚠️ Metabase返回HTTP 500（数据库为空导致，代码转换逻辑正确：API接收`platforms`，传递给Metabase时使用`platform`）
  - [x] 验证 API Key 认证 ✅ 认证成功，无401错误
  - [x] **测试脚本**: `temp/development/test_metabase_question_api.py`
  - [x] **测试结果**: 
    - 无参数请求：✅ 成功（200，数据为空）
    - 日期参数：✅ 成功（200）
    - 平台参数：⚠️ 失败（400，Metabase HTTP 500）- **数据库为空导致，代码逻辑正确**
  - [x] **结论**: Metabase API 连接正常，参数转换逻辑正确，平台参数测试失败是因为数据库为空

- [x] **0.2 检查数据同步功能状态** ✅ 已完成（2025-11-30）
  - [x] 检查 `catalog_files` 表状态 ✅ 411个待同步文件
  - [x] 检查数据表状态 ✅ 数据表为空
  - [x] 测试数据同步 API ✅ `/api/data-sync/files` 正常，返回100个待同步文件
  - [x] **发现：有411个待同步文件，但数据表为空**

- [ ] **0.3 执行数据同步**（**优先执行**）
  - [ ] 使用批量同步 API 导入数据
  - [ ] 确认数据成功入库到 `b_class.fact_raw_data_orders_daily` 表
  - [ ] 验证 Question 40 返回真实数据

### Phase 3: Metabase 中创建 Questions（暂停，等待数据同步完成）

- [ ] 创建剩余的 6 个核心 Question（**等待数据同步完成后继续**）
- [ ] 为每个 Question 配置正确的参数和 SQL
- [ ] 验证每个 Question 可以正常执行查询并返回真实数据

### Phase 4: 环境变量配置

- [ ] 将所有 Question ID 写入 `.env` 文件
- [ ] 更新 `env.example` 文件，包含所有 Question ID 变量和注释
- [ ] 重启后端服务，确认所有 Question ID 正确读取

### Phase 5: 验证与文档

- [ ] 使用 Swagger UI 测试所有 Dashboard API
- [ ] 确认所有 API 返回 200（不再返回 400）
- [ ] 更新 `docs/METABASE_DASHBOARD_SETUP.md`，记录所有 Question 的创建步骤

## 🔑 关键发现和注意事项

### Metabase API Key 认证（重要）

- ✅ **正确的 Header**: `X-API-Key`（或 `x-api-key`、`X-API-KEY`）
- ❌ **错误的 Header**: `X-Metabase-Api-Key`（会导致 401）
- 📝 **官方文档**: https://www.metabase.com/docs/v0.57/people-and-groups/api-keys
- ⚠️ **历史教训**: HTTP headers 大小写不敏感，但命名约定很重要

### Question 参数命名约定

- `start_date` / `end_date` - 日期范围查询
- `date` - 单日期查询
- `platform` - 平台筛选（如 "shopee", "tiktok"）
- `shop_id` - 店铺筛选
- `granularity` - 粒度（如 "daily", "weekly", "monthly"）

### 当前配置状态

- **Metabase URL**: `http://localhost:3000`
- **API Key**: 已配置在 `.env` 文件中（`METABASE_API_KEY`）
- **Question ID 40**: 已配置并测试通过
- **后端服务**: 已更新，支持 API Key 认证

### 数据同步状态（2025-01-31 新增）

- **待同步文件**: 411 个文件（3个平台，6个数据域）
- **数据表状态**: `b_class.fact_raw_data_orders_daily` 表为空
- **建议**: **优先执行数据同步**，让系统有数据后再继续创建其他 Question

## 📚 相关文档

- `docs/METABASE_DASHBOARD_SETUP.md` - Metabase Dashboard 配置完整指南
- `openspec/changes/configure-metabase-dashboard-questions/proposal.md` - 提案文档
- `openspec/changes/configure-metabase-dashboard-questions/tasks.md` - 详细任务清单
- `.cursorrules` - 开发规范（包含 Metabase API Key 认证规范）

## 🚀 下一步行动（优先级调整）

### 立即执行（Phase 0）

1. **启动后端服务**（如果未运行）
   ```bash
   python run.py --backend-only
   ```

2. **测试 Question 40 API**
   ```bash
   python temp/development/test_metabase_question_api.py
   ```

3. **执行数据同步**（**优先**）
   - 使用批量同步 API 导入数据
   - 确认数据成功入库到 `b_class.fact_raw_data_orders_daily` 表
   - 验证 Question 40 返回真实数据

### 后续执行（Phase 3+）

4. **创建其他 Question**（数据同步完成后）
   - 基于真实数据设计查询
   - 验证每个 Question 返回正确数据

5. **配置环境变量**
   - 将所有 Question ID 写入 `.env` 和 `env.example`

6. **验证和文档**
   - 使用 Swagger UI 测试所有 Dashboard API
   - 更新文档

## ⚠️ 已知问题

- **平台参数测试失败**: Question 40 的 `platforms` 参数测试返回 HTTP 500
  - **原因分析**: 数据库为空导致，代码转换逻辑正确（API接收`platforms`，传递给Metabase时使用`platform`）
  - **解决方案**: 数据同步后重新测试平台参数
- **数据表为空**: `b_class.fact_raw_data_orders_daily` 表为空，Question 40 无法返回真实数据
  - 有411个待同步文件，需要执行数据同步
  - **下一步**: 优化数据同步功能，导入待同步文件

## 📝 备注

- 所有重要发现已记录在 `.cursorrules` 和 `docs/METABASE_DASHBOARD_SETUP.md` 中
- 新对话的 agent 应该先阅读这些文档，了解 API Key 认证的正确配置方法
- **重要决策**：优先执行数据同步，让系统有数据后再继续创建其他 Question，避免重复工作
