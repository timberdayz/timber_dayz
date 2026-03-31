# Catalog File Delete Design

## 背景

当前文件列表仅支持同步，不支持删除。测试阶段如果出现问题文件，只能整体清理本地测试数据，无法对单个问题文件做定向治理。这会放大排查成本，也会让文件列表持续积累脏数据。

在当前仓库的数据流中，文件删除不能只删本地文件。文件一旦注册到 `catalog_files`，并可能进一步进入 `data_quarantine`、`staging_*`、`b_class.fact_*`，就必须围绕 `catalog_files.id` 做定向清理。

## 目标

为文件列表增加“单文件删除”能力，满足测试阶段对问题文件的定向治理需求。

功能目标：

- 支持删除未同步文件
- 支持删除已同步文件
- 已同步文件删除前必须先展示影响范围并二次确认
- 删除后同时清理关联数据库记录和本地落地文件

非目标：

- 不做批量删除第一版
- 不做回收站第一版
- 不做恢复/回滚第一版
- 不做历史兼容和历史数据迁移
- 不面向生产环境开放第一版

## 设计边界

该功能只作用于文件列表中的单条 `catalog_files` 记录，删除的是一条文件及其直接派生影响，而不是“隐藏”一条记录。

删除对象分两类：

### 1. 未同步文件

删除内容：

- 本地文件
- `.meta.json` 伴生文件
- `catalog_files`
- `data_quarantine` 中以该文件为来源的记录

### 2. 已同步文件

在上述基础上，继续删除：

- 关联 `staging_*` 记录
- 关联 `b_class.fact_*` 记录

删除必须围绕 `file_id` 或 `catalog_file_id` 做精准删除，不允许按平台、日期、数据域做模糊清理。

## 前端交互设计

文件列表每行新增一个 `删除` 按钮，与现有 `同步` 并列。

### 未同步文件

点击 `删除` 后展示普通确认框。

确认框内容：

- 将删除该文件
- 将删除伴生 `.meta.json`
- 将删除注册记录
- 此操作不可撤销

操作按钮：

- `取消`
- `确认删除`

### 已同步文件

点击 `删除` 后，先调用影响分析接口，再展示“影响分析确认框”。

确认框展示字段：

- 文件名
- 平台
- 来源平台
- 数据域
- 粒度
- 当前状态
- 本地文件是否存在
- 伴生文件是否存在
- 将删除的 `data_quarantine` 行数
- 将删除的 `staging_*` 行数
- 将删除的事实表名
- 将删除的事实表行数

强调文案：

- 该文件已同步，删除将同时清理关联入库数据
- 仅建议测试环境使用
- 此操作不可撤销

操作按钮：

- `取消`
- `确认删除`

交互细节：

- 删除按钮执行时显示 loading
- 成功后刷新列表并提示删除成功
- 失败后保留弹窗并展示错误原因
- 文件列表建议直接显示 `未同步` / `已同步` 标签，降低误删风险

## 后端接口设计

第一版新增两个接口。

### 1. 查询删除影响

`GET /api/field-mapping/files/{file_id}/delete-impact`

用途：

- 为前端删除确认弹窗提供影响范围
- 不执行删除

返回字段：

- `file_id`
- `file_name`
- `platform_code`
- `source_platform`
- `data_domain`
- `granularity`
- `status`
- `local_file_exists`
- `meta_file_exists`
- `quarantine_rows`
- `staging_rows`
- `fact_table_name`
- `fact_rows`
- `can_delete`
- `warnings`

### 2. 执行删除

`DELETE /api/field-mapping/files/{file_id}`

用途：

- 执行实际删除

返回字段：

- `file_id`
- `deleted_file`
- `deleted_meta`
- `deleted_catalog`
- `deleted_quarantine_rows`
- `deleted_staging_rows`
- `deleted_fact_rows`
- `fact_table_name`

异常约束：

- `file_id` 不存在返回 404
- 本地文件不存在不视为失败
- `.meta.json` 不存在不视为失败
- 数据库删除失败时整体回滚

## 服务层设计

不把删除逻辑堆在 router 中。新增独立 service：

`backend/services/catalog_file_delete_service.py`

职责：

- `analyze_delete_impact(file_id)`
- `delete_catalog_file(file_id, force=True)`

Router 只负责参数解析和响应封装。

## 删除逻辑设计

### 影响分析

读取 `catalog_files` 后，计算：

- 本地文件路径
- `.meta.json` 路径
- `data_quarantine` 中 `catalog_file_id = file_id` 的数量
- `staging_*` 中 `file_id = file_id` 的数量
- 动态事实表名
- 事实表中 `file_id = file_id` 的数量

动态事实表名沿用当前规则：

- `platform_code + data_domain + sub_domain + granularity`
- 若 `sub_domain` 为空，则不进入表名

### 执行删除顺序

删除顺序必须固定为：

1. 读取并锁定 `catalog_files` 记录
2. 计算目标事实表名
3. 删除事实表中 `file_id = file_id` 的数据
4. 删除 `staging_*` 中 `file_id = file_id` 的数据
5. 删除 `data_quarantine` 中 `catalog_file_id = file_id` 的数据
6. 删除 `catalog_files`
7. 提交数据库事务
8. 事务成功后删除本地文件和 `.meta.json`

原因：

- 先清数据库派生影响，后删锚点记录
- `catalog_files` 作为整条链路的锚点，应最后删除
- 文件物理删除必须晚于事务提交，避免“文件已没、数据库仍在”的脏状态

### 失败策略

- 事务内任一步失败，整体回滚
- 事务成功后，本地文件删除失败只记 warning，不回滚数据库事务
- 第一版以数据库一致性优先

## 测试策略

### 1. Service 单元测试

覆盖：

- 未同步文件影响分析
- 已同步文件影响分析
- 目标事实表不存在时影响分析返回 `fact_rows = 0`
- 删除未同步文件
- 删除已同步文件
- 本地文件不存在时删除成功
- `.meta.json` 不存在时删除成功
- 中途数据库异常时事务回滚

### 2. API 测试

覆盖：

- `GET /delete-impact/{file_id}` 契约正确
- 不存在的 `file_id` 返回 404
- `DELETE /files/{file_id}` 删除成功
- 删除后文件列表中不再出现该文件

### 3. 前端交互测试

覆盖最小核心流程：

- 未同步文件显示普通确认框
- 已同步文件显示影响分析确认框
- 确认后调用删除接口
- 删除成功后刷新列表

## 推荐方案

第一版采用：

- 单文件删除
- 未同步文件直接确认删除
- 已同步文件先影响分析再二次确认
- 仅本地/测试环境开放
- 不做回收站
- 不做恢复

这是当前仓库中实现成本、可控性和实用性最平衡的方案。
