# 采集配置主账号级收口设计

**Date:** 2026-04-06

## Goal

将采集配置从“单平台配置”升级为“平台 + 主账号”级配置，补齐列表筛选和新建/编辑配置的联动边界，使用户可以在主账号范围内完成店铺 scope 管理，同时保持采集任务执行与调度主链路继续以 `config_id` 为中心。

## Key Decision

采用“平台 + 主账号”作为采集配置的正式归属边界，而不是仅在前端增加一个辅助筛选器。

这意味着：
- 一条采集配置只属于一个平台下的一个主账号
- 列表筛选、配置详情、弹窗右侧店铺 scope、覆盖统计都围绕同一边界展开
- 采集任务和调度仍然按 `config_id` 运行，不重写执行主链路

## Why

当前采集配置页面已经从平台级全局配置升级到店铺 scope 模型，但“配置属于谁”这个问题仍未收口。

现状中存在四个直接问题：

1. 平台下拉框显示异常，选中后无法明确识别当前平台。
2. 平台选项仍由页面手写，未复用账号管理中的真实平台集合。
3. 列表筛选只有平台和启停状态，缺少主账号、日期范围、执行模式、启用定时。
4. 新建/编辑弹窗右侧店铺 scope 只按平台加载，主账号多时会把大量无关店铺混在一起。

如果只加一个“主账号筛选”而不改变配置归属，后续会出现持续歧义：
- 这条配置究竟属于某个平台，还是某个平台下某个主账号？
- 列表筛选中的主账号条件是“查看角度”，还是“配置事实”？
- 覆盖统计和自动命名应该以平台为单位，还是以主账号为单位？

因此需要把配置边界正式收口到“平台 + 主账号”级。

## Scope

In scope:
- 为采集配置模型增加 `main_account_id`
- 调整配置创建、更新、列表查询、覆盖统计的筛选能力
- 让前端平台选项来源与账号管理一致
- 新建/编辑弹窗增加主账号选择，并让右侧 scope 严格联动当前主账号
- 修复平台下拉显示异常
- 保持执行链路和调度链路继续按 `config_id` 驱动

Out of scope:
- 旧采集配置自动迁移
- 为旧配置保留兼容编辑语义
- 改写采集执行器和调度器的主运行模型
- 跨主账号的批量配置编排

## Existing Constraints

- 前端必须保持 Vue 3 + Element Plus + Pinia + Vite
- 后端必须保持 FastAPI + SQLAlchemy async + Pydantic
- ORM SSOT 在 `modules/core/db/schema.py`
- 运行时代码保持 async-first
- 平台值必须严格统一为小写：
  - `miaoshou`
  - `shopee`
  - `tiktok`
- 历史配置允许直接删除并重建，不需要兼容迁移

## Current State

### Frontend

[CollectionConfig.vue](F:\Vscode\python_programme\AI_code\xihong_erp\.worktrees\codex-collection-config-main-account-scope\frontend\src\views\collection\CollectionConfig.vue) 当前具备以下特征：
- 列表筛选仅支持 `platform` 和 `is_active`
- 平台筛选和弹窗平台选项均为写死的 3 条 `el-option`
- 弹窗右侧店铺 scope 仅按平台加载
- 平台表单项外层多了一层测试容器，导致 `el-select` 没有稳定继承表单全宽样式

### Backend

[collection_config.py](F:\Vscode\python_programme\AI_code\xihong_erp\.worktrees\codex-collection-config-main-account-scope\backend\routers\collection_config.py) 当前具备以下特征：
- `GET /collection/configs` 只支持 `platform` 和 `is_active`
- `GET /collection/config-coverage` 只支持 `platform`
- 配置创建和更新的 scope 校验只校验平台，不校验主账号
- 配置执行和调度同步已经以 `config_id` 为中心

### Data Model

[schema.py](F:\Vscode\python_programme\AI_code\xihong_erp\.worktrees\codex-collection-config-main-account-scope\modules\core\db\schema.py) 中：
- `CollectionConfig` 还没有 `main_account_id`
- `CollectionConfigShopScope` 已经存在
- `ShopAccount` 已有 `main_account_id`

说明数据库层已经具备按主账号收口 scope 的基础，只差配置头显式表达主账号归属。

## Proposed Data Model

### CollectionConfig

为 `CollectionConfig` 增加：
- `main_account_id`

建议约束：
- 非空
- 外键指向 `core.main_accounts.main_account_id`
- 配置唯一性改为围绕 `platform + main_account_id + name`

保留现有字段：
- `name`
- `platform`
- `granularity`
- `date_range_type`
- `custom_date_start`
- `custom_date_end`
- `execution_mode`
- `schedule_enabled`
- `schedule_cron`
- `retry_count`
- `is_active`

保留 `account_ids / data_domains / sub_domains` 作为现有摘要字段，但它们不再代表“平台全局配置”，而是当前主账号下全部 scope 汇总结果。

### CollectionConfigShopScope

不新增主账号字段，仍由：
- `config_id`
- `shop_account_id`

表达归属关系。

主账号归属通过：
- `CollectionConfig.main_account_id`
- `ShopAccount.main_account_id`

在保存时做一致性校验。

## Proposed API Contract

### Config Query

`GET /collection/configs` 增加过滤参数：
- `platform`
- `main_account_id`
- `date_range_type`
- `execution_mode`
- `schedule_enabled`
- `is_active`

返回结果补充或显式包含：
- `main_account_id`
- `main_account_name`（如果当前已有响应层方便补充，建议一起返回）

### Coverage Query

`GET /collection/config-coverage` 增加：
- `main_account_id`

这样列表页顶部筛选与覆盖统计可以保持一致边界。

### Config Create / Update

`CollectionConfigCreate` 和 `CollectionConfigUpdate` 增加：
- `main_account_id`

保存校验增加：
1. `main_account_id` 必填
2. `shop_scopes` 中所有店铺必须属于该 `platform + main_account_id`
3. 不能混入其他主账号的店铺
4. 每个店铺至少一个数据域
5. 数据域仍需受店铺能力约束

## Frontend Interaction Design

### List Filters

列表页顶部筛选统一收口为 5 个：
- 平台
- 主账号
- 日期范围
- 执行模式
- 启用定时

筛选行为：
- 平台未选中时，主账号下拉禁用或为空
- 选择平台后，主账号下拉仅显示该平台下主账号
- 日期范围筛选直接映射 `date_range_type`
- 执行模式映射 `execution_mode`
- 启用定时映射 `schedule_enabled`

### Platform Options

平台选项不再写死在采集配置页面。

来源改为账号管理的真实平台集合，前端内部建立统一映射：
- value: `miaoshou` / `shopee` / `tiktok`
- label: `Miaoshou` / `Shopee` / `TikTok`

这样可以同时满足：
- 接口值稳定
- 页面展示统一
- 与账号管理真实数据保持一致

### Dialog Layout

新建/编辑弹窗左侧顺序调整为：
1. 配置名称
2. 平台
3. 主账号
4. 日期范围
5. 执行模式
6. 启用定时

右侧保持店铺 scope 列表，但只在已选择平台和主账号后加载。

### Scope Linkage

联动规则：
- 切换平台：清空主账号与 scope
- 切换主账号：按当前 `platform + main_account_id` 重建 scope
- 编辑配置：先读取配置详情，再按配置中的平台和主账号加载对应店铺
- 右侧只显示当前主账号下的店铺，不能看到其他主账号的店铺

### Platform Select Visibility Fix

平台下拉显示异常的修复策略：
- 去掉影响宽度继承的外层包裹，或者为包裹层和内部 `el-select` 明确设置 `width: 100%`
- 保留 `data-testid` 时不能破坏 Element Plus 在 `el-form-item` 中的默认宽度行为

目标是让用户能直接看到当前选中的平台，而不是只剩一个窄选择框。

## Naming Strategy

自动命名建议加入主账号标识：
- `<platform>-<main_account_id>-<granularity>-<domains>-vN`

示例：
- `shopee-main001-daily-orders-products-v1`

这样可以避免同平台多个主账号下配置名难以区分。

## Legacy Config Strategy

旧配置不做迁移兼容。

具体策略：
- 不自动拆分旧配置
- 不保留“平台级旧配置”的继续编辑语义
- 改造完成后允许直接清理旧配置
- 用户按新模型重新配置后再创建采集任务

这样可以避免：
- 跨主账号旧配置归属不清
- 旧调度任务与新配置语义混杂
- 前端列表和覆盖统计同时展示两套口径

## Runtime And Scheduler Impact

本次不改运行主链路，只改配置边界。

保持不变的部分：
- 手动执行仍按 `config_id` 触发
- 调度注册仍按 `config_id` 注册 job
- 调度器恢复和同步逻辑仍围绕 `config_id`

需要新增的保证：
- 创建/更新配置时，scope 只允许当前主账号下的店铺
- 查询和覆盖统计按主账号收口

因此本次风险主要集中在配置保存和查询层，不在采集任务执行器本身。

## Risks And Mitigations

### Risk 1: 旧配置仍残留在系统里

Mitigation:
- 直接允许删除旧配置
- 在交付时明确说明需要按新模型重建配置

### Risk 2: 主账号字段加到配置头后，查询和唯一性条件不一致

Mitigation:
- 同步修改 schema、Pydantic schema、查询接口和命名逻辑
- 用测试锁定 `main_account_id` 行为

### Risk 3: 前端主账号联动只做表面筛选，后端仍可写入脏 scope

Mitigation:
- 后端保存时强校验 `shop_scopes` 必须都属于当前主账号

### Risk 4: 平台选项展示值和提交值大小写不一致

Mitigation:
- 前端统一映射，所有接口提交值只使用小写枚举

## Testing Strategy

### Frontend

先写失败测试，再改实现，覆盖：
- 平台选项不再写死
- 平台下拉字段能正常显示选中值
- 列表页存在主账号筛选
- 列表页存在日期范围、执行模式、启用定时筛选
- 弹窗存在主账号字段
- scope 构建逻辑按 `platform + main_account_id` 限定店铺

### Backend

先写失败测试，再改实现，覆盖：
- 创建配置必须带 `main_account_id`
- `shop_scopes` 混入其他主账号店铺时保存失败
- `GET /collection/configs` 支持新过滤参数
- `GET /collection/config-coverage` 支持 `main_account_id`
- 手动执行配置仍能正常创建任务

### Verification

至少执行：
- 采集配置相关前端脚本测试
- 采集配置相关后端 pytest
- 必要时构建或类型检查命令

## Implementation Notes

- 实现应在独立 worktree / 分支中进行，避免影响其他会话
- 不在当前主工作树直接改代码
- 先完成 spec 和 plan，再进入实现
- 当前会话未显式授权 sub-agent，因此 spec review 采用本地自审

## Expected Outcome

交付后，采集配置的使用流程应变为：
1. 在列表页按平台和主账号定位配置
2. 新建配置时先选平台，再选主账号
3. 右侧只配置该主账号下的店铺 scope
4. 保存后该配置只代表该主账号的采集范围
5. 后续基于这些新配置去创建或调度采集任务
