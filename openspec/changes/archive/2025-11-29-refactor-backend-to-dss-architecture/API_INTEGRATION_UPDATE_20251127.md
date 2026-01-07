# 前端集成策略更新 - 从Dashboard嵌入改为API调用

## 更新日期
2025-11-27

## 更新原因

用户需求：
- 在Metabase中做好前端所有需要的数据来源内容
- 前端单独使用Vue.js进行设计
- 避免触碰Metabase需要收费的功能内容

## 主要变更

### 1. 前端集成策略变更

**之前（方式1 - Dashboard嵌入）**：
- 前端嵌入Metabase Dashboard（iframe）
- 需要配置Metabase Embedding功能（可能收费）
- UI控制度低

**现在（方式2 - API调用）**：
- 前端调用Metabase Question API获取数据
- 使用ECharts自己渲染图表
- 完全控制UI设计
- 避免使用Metabase收费功能

### 2. 更新的文件

#### 提案文档
- ✅ `proposal.md` - 更新前端集成策略说明
- ✅ `design.md` - 更新决策3，说明选择API调用的理由
- ✅ `tasks.md` - 更新相关任务，从嵌入改为API调用

#### 规格文档
- ✅ `specs/dashboard/spec.md` - 更新Dashboard规格，改为API调用模式
- ✅ `specs/frontend-api-contracts/spec.md` - 更新API契约，改为Question API
- ✅ `specs/backend-architecture/spec.md` - 更新后端架构规格
- ✅ `specs/bi-layer/spec.md` - 更新BI层规格

#### 新增文档
- ✅ `docs/METABASE_API_INTEGRATION_GUIDE.md` - Metabase API集成指南

### 3. 技术实现变更

#### 后端API变更
- **之前**：`POST /api/metabase/embedding-token` - 生成嵌入token
- **现在**：`GET /api/metabase/question/{question_id}/query` - 获取Question查询结果

#### 前端组件变更
- **之前**：`MetabaseChart.vue` - iframe嵌入组件
- **现在**：`MetabaseChart.vue` - ECharts渲染组件（调用API获取数据）

#### 数据流变更
- **之前**：前端 → 后端（生成token） → Metabase（iframe嵌入）
- **现在**：前端 → 后端（代理API） → Metabase（Question API） → 前端（ECharts渲染）

### 4. 环境变量变更

**移除**：
- `METABASE_EMBEDDING_SECRET_KEY`（不再需要）

**新增**：
- `METABASE_API_KEY`（Metabase API密钥，用于调用REST API）

### 5. 任务更新

#### Phase 4任务更新
- ✅ 4.1节：从"Metabase Dashboard嵌入"改为"Metabase Question API集成"
- ✅ 4.2节：从"替换为Metabase仪表盘"改为"调用Metabase Question API，使用ECharts渲染"
- ✅ 移除：Metabase Embedding配置任务
- ✅ 新增：Metabase Question创建任务
- ✅ 新增：Metabase Question API代理开发任务

## 优势

### 1. 避免收费功能
- ✅ 使用免费的REST API
- ✅ 不使用收费的Embedding功能

### 2. 完全控制UI
- ✅ 前端完全控制图表样式
- ✅ 可以自定义交互逻辑
- ✅ 可以使用任何图表库（ECharts、Chart.js等）

### 3. 灵活性高
- ✅ 可以根据业务需求自定义图表类型
- ✅ 可以组合多个Question的数据
- ✅ 可以实现复杂的交互逻辑

## 实施步骤

### Step 1: Metabase中创建Question
1. 登录Metabase
2. 创建所有需要的Question（查询）
3. 记录每个Question的ID

### Step 2: 配置Metabase API密钥
1. 在Metabase中：Settings → Admin → API Keys
2. 创建API密钥
3. 配置到环境变量：`METABASE_API_KEY`

### Step 3: 实现后端代理API
1. 扩展`backend/routers/metabase_proxy.py`
2. 添加`GET /api/metabase/question/{question_id}/query`端点
3. 实现Metabase REST API调用

### Step 4: 实现前端服务
1. 创建/更新`frontend/src/services/metabase.js`
2. 实现`getQuestionData(questionId, filters)`函数

### Step 5: 更新前端组件
1. 更新`frontend/src/views/Dashboard.vue`
2. 调用Metabase Question API获取数据
3. 使用ECharts渲染图表

## 验证

- ✅ 提案验证通过：`openspec validate refactor-backend-to-dss-architecture --strict`
- ✅ 所有spec文件已更新
- ✅ 所有任务已更新

## 参考文档

- `docs/METABASE_API_INTEGRATION_GUIDE.md` - 详细的集成指南
- [Metabase REST API文档](https://www.metabase.com/docs/latest/api)
- [Metabase Question API](https://www.metabase.com/docs/latest/api/card#execute-a-question-query)

