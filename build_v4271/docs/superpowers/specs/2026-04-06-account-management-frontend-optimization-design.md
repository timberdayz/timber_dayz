# Account Management Frontend Optimization Design

**Date:** 2026-04-06

## Goal

将账号管理页面从“全量店铺平铺的大宽表”调整为适合多店铺场景的分层管理界面，在不改后端 API 的前提下，显著降低页面滚动成本并提升定位、筛选和批量管理效率。

## Key Decision

采用“平台 > 主账号”的两级信息架构：
- 平台作为最高层分组
- 主账号作为核心管理单元
- 店铺账号作为当前主账号下的明细列表

页面主体使用 master-detail 结构：
- 左侧为平台与主账号索引
- 右侧为当前主账号摘要、店铺明细和相关操作

## Why

当前账号管理页的核心问题不是“数据不够”，而是“信息组织方式不适合未来规模”。

现状中：
- 全部店铺账号直接平铺在单个固定高度表格中
- 表格列很多，信息横向分散
- 店铺数量增长后，用户需要在全局范围内做大量纵向和横向滚动
- 主账号与店铺的从属关系没有成为页面的第一层导航结构

这会导致三个直接问题：
- 很难快速定位某个主账号下的全部店铺
- 批量管理天然缺乏边界，操作对象不够聚焦
- 页面在店铺数量继续增长后会进一步失效

## Scope

In scope:
- 重组账号管理页面的信息架构与主体布局
- 新增按平台与主账号组织的派生视图逻辑
- 保留并重排现有统计卡片、筛选器、未匹配别名提示、创建/编辑/探测能力
- 将店铺表格收缩为“当前主账号下的明细表格”
- 增加主账号摘要、店铺数量统计、局部批量上下文
- 为新布局补充前端轻量测试与验证

Out of scope:
- 新增后端 API
- 改写账号、主账号、别名、探测的后端领域模型
- 全量替换 Element Plus 表格或引入新的表格库
- 本次就做复杂拖拽编排、跨主账号批量迁移流程
- 移动端专门适配

## Existing Constraints

- 前端技术栈必须保持 Vue 3 + Element Plus + Pinia + Vite
- 数据仍来自现有 `accounts` store 与 `accountsApi`
- 仓库使用 superpowers 工作流，复杂改动先有 spec 与 plan
- 页面属于管理员配置页，应遵循高密度 operations-console 风格

## Current State

当前 [AccountManagement.vue](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/AccountManagement.vue) 包含：
- 顶部 `PageHeader`
- 未匹配店铺别名提示
- 4 个统计卡片
- 一组全局筛选与操作按钮
- 一个固定高度 `500` 的全量店铺表格
- 创建/编辑、批量创建、当前店铺探测相关对话框

优点：
- 现有功能完整
- 后端能力齐全
- 全局筛选和探测操作已经可用

问题：
- 单表格承载了全局导航和局部编辑两类任务
- 主账号层级没有变成导航入口
- 对于“主账号下很多店铺”的真实运营方式支持不足

## Proposed Information Architecture

### Global Page Layout

页面保留以下顶部区域：
- 页面标题与说明
- 未匹配别名警示
- 统计卡片
- 全局筛选与全局操作工具栏

页面主体改为双栏：
- 左栏：主账号导航区
- 右栏：当前主账号详情区

### Left Column: Platform And Main Account Navigator

左侧承担“找对象”的职责。

结构：
- 按平台分组显示
- 每个平台下显示主账号列表
- 每个主账号条目展示：
  - 主账号名称
  - 主账号 ID
  - 店铺数量
  - 启用店铺数量
  - 异常提示数量（如缺少平台店铺 ID）

行为：
- 点击主账号即切换右侧详情
- 支持基于当前全局搜索条件实时过滤
- 若仅剩一个主账号，默认自动选中

### Right Column: Main Account Detail Workspace

右侧承担“看清楚并操作”的职责。

内容顺序：
1. 当前主账号摘要卡
2. 当前主账号下的操作按钮
3. 当前主账号下的店铺明细表格

摘要卡展示：
- 平台
- 主账号名称
- 主账号 ID
- 登录用户名
- 店铺总数 / 启用数 / 停用数

操作按钮优先保留现有动作的可见性：
- 添加店铺账号
- 批量添加店铺账号
- 探测当前店铺
- 刷新

### Shop Detail Table

店铺表格不再代表“全量系统账号”，而是“当前主账号上下文中的店铺账号集合”。

保留高密度编辑能力，但缩减信息噪音：
- 店铺名称
- 店铺账号 ID
- 店铺别名
- 平台店铺 ID
- 区域
- 店铺类型
- 数据域能力
- 启用状态
- 操作列

这样可以保留当前表格编辑效率，同时避免全局平铺导致的认知负担。

## Interaction Model

### Filters

顶部过滤器保持全局语义：
- 平台
- 启用状态
- 历史记录开关
- 店铺类型
- 搜索词

过滤结果同时作用于：
- 左侧主账号分组
- 右侧当前主账号的店铺明细

### Selection Fallback

当过滤条件变化时：
- 如果当前主账号仍存在，则保持选中
- 如果当前主账号被过滤掉，则自动选中第一个可见主账号
- 如果没有可见主账号，则右侧显示空态

### Empty States

需要明确三类空态：
- 系统没有任何账号数据
- 当前筛选条件下无结果
- 左侧有主账号但当前主账号下无店铺

## Technical Design

### Data Source Strategy

继续使用现有 store：
- `accountsStore.accounts`
- `accountsStore.mainAccounts`
- `accountsStore.stats`
- `accountsStore.unmatchedShopAliases`

新增前端派生视图逻辑：
- 从 `accountsStore.accounts` 生成 `platformGroups`
- 从每个分组中生成 `mainAccountGroups`
- 从 `mainAccountGroups` 派生当前选中的 `selectedMainAccountGroup`

这使得本次重构保持前端内聚，不需要调整后端。

### Code Structure

保持现有页面为主入口，但抽出纯函数 helper：
- 负责将原始店铺账号列表转换为“平台 > 主账号 > 店铺”的结构
- 负责生成主账号摘要计数
- 便于用现有 `node:test` 做 TDD

推荐新增：
- `frontend/src/utils/accountManagementView.js`

继续修改：
- `frontend/src/views/AccountManagement.vue`
- `frontend/scripts/accountManagement*.test.mjs`

### Styling Direction

页面属于 admin / operations-console 家族，应遵循：
- 低装饰、高密度
- 明确分区
- 强调导航与工作区边界
- 在桌面端优先优化扫描和点击路径

视觉上：
- 左栏使用轻量分组卡片或列表面板
- 右栏使用标准 `el-card` + `el-table`
- 减少“整页都在滚”的感觉，改为“先选主账号，再处理局部数据”

## Risks And Trade-offs

### Risk: 用户习惯当前全量平铺

改版后，用户不再一次看到所有店铺。

Mitigation:
- 保留全局搜索和过滤器
- 在左栏展示清晰的主账号数量与店铺数
- 右栏表格仍保留高密度信息

### Risk: 视图逻辑比现在复杂

分组与选中逻辑会增加状态管理复杂度。

Mitigation:
- 将 grouping 与 summary 抽成纯函数
- 用测试锁定过滤和选中回退行为

### Risk: 过度组件化导致改动面过大

如果为了“结构更优雅”一次拆太多组件，风险会上升。

Mitigation:
- 本次优先小范围重构
- 先保留主页面作为整合入口
- 只抽纯 helper，不强行拆多个新组件

## Implementation Notes

- 先用测试锁定新的分组视图和关键文案，再做模板重组
- 不移除现有创建、编辑、批量创建、探测对话框
- 不修改现有 API 请求入口
- 如果后续还需要“跨主账号全局表格视图”，可在本次结构稳定后追加“全局视图”切换，而不是保留当前默认模式
