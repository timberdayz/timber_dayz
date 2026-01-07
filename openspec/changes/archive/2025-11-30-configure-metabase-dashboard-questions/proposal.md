# Change: 配置业务概览和核心看板的 Metabase Questions

## Why

当前系统已完成 DSS 架构重构，后端 Dashboard API 已全部改为通过 Metabase Question 查询，但 Metabase 中尚未完整创建和配置这些 Question，导致：

- 后端大量返回 400 错误（Question ID 未配置或配置错误）
- 前端 Dashboard 虽然有完整的 UI 框架，但无法获取真实业务数据
- `.env` 中 Question ID 配置缺失，没有统一的配置文档和指南

**根本原因**：DSS 架构重构完成了后端和数据库层面的改造，但 Metabase 侧的 Question 创建和配置工作尚未完成，导致前后端无法正常协作。

## What Changes

### 核心变更

1. **创建必备 Metabase Questions**
   - 为业务概览页面创建 7 个核心 Question（KPI、对比、店铺赛马、流量排名、库存积压、经营指标、清仓排名）
   - 为每个 Question 设计最小可用的查询模型（表选择、维度、指标、过滤参数）
   - 确保 Question 的参数命名与后端 API 约定一致

2. **统一 Question ID 配置**
   - 将所有 Question ID 显式写入环境变量（`.env` + `env.example`）
   - 为每个环境变量添加注释说明（对应的 Question 含义、创建位置）
   - 提供配置验证脚本或文档，确保新环境可以快速完成配置

3. **完善配置文档**
   - 创建 Metabase Dashboard 配置指南（`docs/METABASE_DASHBOARD_SETUP.md`）
   - 列出所有必备 Question 及其用途
   - 提供步骤化的创建指南（可选截图）
   - 说明如何在新环境中重新配置 Question ID

### 技术细节

- **Question 设计原则**：
  - 最小可用：先保证基本功能可用，后续再优化
  - 参数统一：所有 Question 使用统一的参数命名约定（`start_date`/`end_date`/`date`/`platform`/`shop_id`/`granularity`）
  - 表选择：优先使用 `b_class.fact_raw_data_*` 系列表（按 data_domain + granularity 分表）

- **环境变量命名规范**：
  - `METABASE_QUESTION_{QUESTION_KEY}`（大写，下划线分隔）
  - 例如：`METABASE_QUESTION_BUSINESS_OVERVIEW_KPI`

- **Metabase API Key 认证规范（2025-11-29 重要发现）**：
  - ⚠️ **关键发现**：Metabase API Key 认证必须使用 `X-API-Key` header（或 `x-api-key`、`X-API-KEY`），**不是** `X-Metabase-Api-Key`
  - ✅ **官方文档确认**：根据 [Metabase v0.57 官方文档](https://www.metabase.com/docs/v0.57/people-and-groups/api-keys)，正确的 Header 名称是 `x-api-key`（curl）或 `X-API-KEY`（JavaScript）
  - ✅ **正确实现**：`backend/services/metabase_question_service.py` 已正确配置使用 `X-API-Key`（HTTP headers 大小写不敏感）
  - ❌ **错误示例**：`headers["X-Metabase-Api-Key"] = api_key` 会导致 401 认证失败
  - ✅ **正确示例**：`headers["X-API-Key"] = api_key` 返回 200 成功
  - 📝 **参考文档**：
    - `docs/METABASE_DASHBOARD_SETUP.md` - 完整的配置指南和故障排查
    - https://www.metabase.com/docs/v0.57/people-and-groups/api-keys - Metabase 官方文档
  - ⚠️ **历史教训**：我们曾因使用错误的 Header 名称导致所有 API Key 认证失败（401），通过系统测试和查阅官方文档发现正确格式为 `X-API-Key`

## Impact

### 受影响的规格（Affected Specs）

- **bi-layer** (修改规格) - 增加对 Metabase Question 配置的具体要求
  - 明确列出所有必备 Question 及其用途
  - 定义 Question 参数命名约定
  - 说明 Question ID 配置方法

- **dashboard** (修改规格) - 明确前端 Dashboard 依赖的 Question
  - 列出每个 Dashboard 页面依赖的 Question ID
  - 说明前端如何通过后端代理 API 调用 Question

- **frontend-api-contracts** (修改规格) - 确保 Dashboard API 错误语义清晰
  - 明确 Question 未配置时的错误响应格式
  - 说明 Question 配置错误时的错误处理

### 受影响的代码（Affected Code）

#### 需要修改的文件
- `.env` - 添加 Question ID 环境变量
- `env.example` - 添加 Question ID 环境变量模板和注释
- `docs/METABASE_DASHBOARD_SETUP.md` - 新建配置指南文档

#### 不需要修改的文件（仅验证）
- `backend/services/metabase_question_service.py` - 已实现 Question ID 读取逻辑，无需修改
- `backend/routers/dashboard_api.py` - 已实现 Question 查询逻辑，无需修改

### 破坏性变更（Breaking Changes）

**无破坏性变更** - 本 change 仅添加配置和文档，不修改现有代码逻辑。

## Non-Goals

- ❌ **不在本 change 中重构前端组件**：前端迁移工作由 `migrate-frontend-dashboard-to-metabase-api` 负责
- ❌ **不实现 HR 相关的高级 Question**：HR 管理相关 Question 和定时任务由后续 change 负责
- ❌ **不做性能调优**：复杂 JSONB 查询优化、索引优化等工作不在本 change 范围内
- ❌ **不创建复杂的 Dashboard**：仅创建 Question，不创建 Metabase Dashboard（Dashboard 创建由后续 change 负责）

## 成功标准

### Phase 1: Question 创建完成
- ✅ 所有 7 个核心 Question 已在 Metabase 中创建
- ✅ 每个 Question 的参数配置正确（与后端 API 约定一致）
- ✅ 每个 Question 可以正常执行查询（即使数据为空）

### Phase 2: 环境变量配置完成
- ✅ 所有 Question ID 已写入 `.env` 文件
- ✅ `env.example` 已更新，包含所有 Question ID 变量和注释
- ✅ 后端服务重启后可以正确读取 Question ID

### Phase 3: 验证通过
- ✅ 所有 Dashboard API 调用不再返回 400（Question ID 未配置错误）
- ✅ Metabase 可以正常返回 JSON 数据（即使数据为空）
- ✅ 配置文档完整，新环境可以按照文档完成配置

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Question 参数命名不一致 | 中 | 在文档中明确参数命名约定，创建 Question 时严格遵循 |
| 环境变量配置错误 | 低 | 提供配置验证脚本，在文档中提供示例值 |
| Metabase 表结构变更 | 低 | Question 设计时使用稳定的表名和字段名 |

## 预期收益

1. **消除 400 错误**：Dashboard API 不再因 Question ID 未配置而返回 400
2. **提升开发效率**：新环境可以快速完成 Metabase 配置，无需反复调试
3. **完善文档体系**：为后续 Metabase 相关开发提供清晰的配置指南

