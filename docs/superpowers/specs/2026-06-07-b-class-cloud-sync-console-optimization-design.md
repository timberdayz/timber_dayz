# B类云端追平控制台优化设计

**Date:** 2026-06-07  
**Status:** Approved in conversation  
**Supersedes:** `docs/superpowers/specs/2026-04-06-b-class-cloud-catch-up-console-design.md`

## Goal

将当前 `/cloud-sync` 从“可见但不够可用的管理页”优化为一个**面向管理员/运维的 B 类云端追平控制台**。

本次优化的目标不是增加更多调试功能，而是让管理员进入页面后可以稳定完成以下判断与操作：

1. 当前云端追平是否健康。
2. 当前云端数据是否已经追到最新。
3. 是否存在积压、失败或部分成功，需要人工介入。
4. 现在最应该执行的动作是什么。

## Users

本页面的第一使用人明确为：

- 管理员
- 运维

本页面不是面向：

- 普通业务用户
- 非管理员开发用户
- 需要直接执行数据库修复的工程工具使用者

## Product Positioning

页面产品定位定义为：

**采集环境到云端的 B 类数据追平控制台**

它服务于以下实际运行模型：

1. 采集环境完成 B 类数据采集与本地入库。
2. 本地 `b_class.fact_*` 表写入成功后，系统生成追平任务。
3. `backend-collector` 作为唯一常驻 owner 处理追平任务。
4. 管理员通过控制台确认整体状态、处理积压和恢复异常。

因此，页面核心问题不是：

- “我要操作哪张表？”

而是：

- “云端 B 类数据现在是否正常、是否最新、是否需要我处理？”

## Non-Goals

本次优化不追求以下目标：

- 把首页继续做成表级技术操作台
- 暴露所有底层字段给管理员
- 让管理员逐表完成日常追平
- 在页面上提供自由 SQL、连接串编辑或环境变量编辑
- 修改现有云端追平的核心同步架构
- 顺手重构无关的采集、B 类入库、C 类计算模块

## Existing Problems

当前实现已具备基础能力，但不满足“真正可用”的交付标准，主要问题如下：

### 1. 前端可读性问题

- 页面和状态文案存在大面积乱码
- 首页信息密度虽高，但主次不清
- 技术细节过早暴露在主路径中

### 2. 信息架构问题

- 首页将总览、技术诊断、单表操作混在一起
- 高风险/低频操作没有明显下沉
- 管理员必须理解表级概念才能判断下一步动作

### 3. 契约一致性问题

- 前端已具备任务、表、事件等视图，但后端查询契约仍偏底层
- 部分筛选和列表能力是“界面预留”，不是完整闭环
- 路由兼容层与测试替身注入方式不稳定，降低可验证性

### 4. 历史状态问题

- 旧的追平历史与 checkpoint 可以删除并重建
- 当前页面没有清晰定义“清空历史后的首次启用状态”

## Design Principles

本次优化遵循以下原则：

### 1. 总览优先，诊断下沉

首页优先展示整体健康与下一步动作，不以表级细节作为主入口。

### 2. 受控动作优先

首页只保留高频、低歧义、低学习成本的动作。

### 3. 危险操作延后

checkpoint 修复、projection 刷新、dry-run 等动作只出现在高级诊断区。

### 4. 运行态历史可重建

追平任务、运行记录、checkpoint 属于运行态数据，可在优化完成后清空并从干净状态重新建立。

### 5. 不改核心架构，只做控制面收口

保留现有 worker、dispatch、task、checkpoint、health 基础能力，不引入第二套并行同步系统。

## Target Scope

本控制台管理范围限定为：

- 本地 `b_class` schema 下的 `fact_*` 源表追平
- 云端 B 类 canonical mirror 的增量追平状态
- 追平相关任务、checkpoint、运行态、异常恢复

本控制台不直接负责：

- `semantic`
- `mart`
- `api`
- 非 B 类业务数据
- 原始采集文件管理
- 通用数据同步任务页

## Homepage Information Architecture

首页采用“4 层结构 + 1 个高级诊断折叠区”的信息架构。

### Layer 1: 总览状态区

目标：让管理员在 5-10 秒内完成整体判断。

展示卡片：

- 自动追平
- Worker 状态
- 云库连接
- 当前追平状态
- 异常任务
- 最近一次成功追平

其中：

- `自动追平` 只表达开关与是否会自动补齐
- `Worker 状态` 只表达运行态，不展示底层实现细节
- `当前追平状态` 使用业务语义词，而不是裸英文状态

### Layer 2: 主操作区

首页只保留以下 3 个主操作：

- `立即追平到最新`
- `暂停自动追平` / `恢复自动追平`
- `重试异常任务`

这是管理员主路径，也是首页唯一需要高可见度的动作集合。

首页移除以下主路径动作：

- 单表 trigger
- 单表 dry-run
- 单表 repair checkpoint
- 单表 refresh projection
- batch size 手动输入

### Layer 3: 当前运行区

目标：回答“系统现在做到哪一步”。

展示字段：

- 当前是否正在追平
- 当前任务 ID
- 当前表名
- 当前活跃任务数
- 最近心跳时间
- 最近错误摘要
- 建议动作

“建议动作”采用规则化提示，不直接把原始错误当作操作建议。

### Layer 4: 最近记录区

目标：回答“最近发生了什么”。

展示最近追平记录，字段收敛为：

- 任务编号
- 来源表
- 触发方式
- 结果
- 开始时间
- 结束时间
- 错误摘要

该区域是运维回看区，不是底层任务中心替代品。

### Layer 5: 高级诊断区

默认折叠，仅在排障时展开。

包含：

- 表级状态
- 任务队列明细
- 事件列表
- 单表 dry-run
- 单表 checkpoint 修复
- 单表 projection 刷新
- 单任务重试/取消

该区域明确标识为“高级诊断/排障专用”。

## Status Vocabulary

首页状态词统一为中文业务语义，避免直接暴露底层英文状态值。

建议映射如下：

- 自动追平：
  - `已开启`
  - `已暂停`

- Worker 状态：
  - `运行中`
  - `未启动`
  - `未配置`
  - `异常`

- 云库连接：
  - `连接正常`
  - `连接异常`
  - `未知`

- 当前追平状态：
  - `已追平最新`
  - `正在追平`
  - `存在积压`
  - `存在异常`

- 任务结果：
  - `成功`
  - `部分成功`
  - `失败`
  - `等待中`
  - `执行中`
  - `已取消`

## UX Behavior

### Primary UX

首页默认流程应当是：

1. 看总览状态
2. 看是否有异常和积压
3. 执行 3 个主操作之一
4. 如仍异常，再展开高级诊断

### Empty State

在以下场景必须有明确空状态：

- 历史已清空，尚未首次追平
- 当前没有待同步内容
- 当前没有异常任务
- Worker 尚未启用

空状态示例语义：

- `当前尚无追平记录`
- `当前没有待追平内容`
- `当前没有异常任务`
- `当前未启用自动追平，请先检查采集机配置`

### Recovery Guidance

页面必须能区分至少三类问题：

1. 环境问题
- 云库不可达
- SSH 隧道不可达
- Worker 未启动

2. 状态问题
- 有积压
- 有失败任务
- 长时间无心跳

3. 数据/任务问题
- 单表持续失败
- projection 刷新失败
- checkpoint 与本地高水位异常

每类问题都应提供一条简洁的“建议动作”。

## Backend Contract Reshape

后端接口按“控制面”和“诊断面”分层。

### 控制面接口

服务首页主路径，返回结构稳定、字段少、语义清晰。

- `GET /api/cloud-sync/overview`
- `GET /api/cloud-sync/health`
- `GET /api/cloud-sync/runtime`
- `GET /api/cloud-sync/settings`
- `PUT /api/cloud-sync/settings`
- `POST /api/cloud-sync/sync-now`
- `POST /api/cloud-sync/retry-failed`

### 诊断面接口

服务高级诊断区和排障操作。

- `GET /api/cloud-sync/tables`
- `GET /api/cloud-sync/tasks`
- `GET /api/cloud-sync/tasks/{job_id}`
- `GET /api/cloud-sync/events`
- `POST /api/cloud-sync/tasks/trigger`
- `POST /api/cloud-sync/tasks/{job_id}/retry`
- `POST /api/cloud-sync/tasks/{job_id}/cancel`
- `POST /api/cloud-sync/tables/{table_name}/dry-run`
- `POST /api/cloud-sync/tables/{table_name}/repair-checkpoint`
- `POST /api/cloud-sync/tables/{table_name}/refresh-projection`

### Contract Expectations

需要保证以下约束：

1. 首页接口字段稳定，尽量避免前端拼接多个底层状态自行推导。
2. 诊断接口按表、按任务、按事件的模型清晰分离。
3. 错误输出继续做敏感信息脱敏。
4. 表名校验继续使用严格白名单格式。
5. 管理员写操作继续保留服务端审计日志。

## History Reset Strategy

用户已明确接受删除旧追平历史。

本次优化完成后，允许清理以下运行态历史：

- `cloud_b_class_sync_tasks`
- `cloud_b_class_sync_runs`
- `cloud_b_class_sync_checkpoints`

清理目标是“状态重建”，不是“业务数据回滚”。

明确边界：

- 可以删除追平任务历史
- 可以删除运行记录
- 可以删除 checkpoint
- 不删除本地 `b_class.fact_*` 业务数据
- 不删除云端业务数据本体

### Reset Outcome

清理后系统应表现为：

- 首页显示“暂无追平历史”而不是报错
- 所有表视为待重新建立 checkpoint
- 首次 `sync-now` 或自动追平可以从干净状态重新建立运行轨迹

## Operational Topology Constraints

继续遵守既有部署边界：

- `backend-collector` 是唯一常驻云端追平 owner
- 本地开发 API 不应成为正式 worker owner
- `DATABASE_URL` 指向本地业务库
- `CLOUD_DATABASE_URL` 指向云端目标
- 当前 scope 继续由当前云库目标唯一决定

页面文案和说明应强化这一运行模型，避免误导管理员以为任何本地 API 进程都可以长期接管追平。

## Testing And Verification Requirements

本次优化的完成标准必须基于验证结果，而不是基于代码存在。

至少验证以下场景：

### Frontend

- 页面无乱码
- 首页结构符合总览优先
- 空状态可正确显示
- 高级诊断默认折叠
- 主操作按钮行为与提示一致

### Backend

- `overview` / `health` / `runtime` 返回契约稳定
- `sync-now` / `retry-failed` / `settings` 行为稳定
- 历史清空后接口仍能返回合理空状态
- 表级诊断与任务级诊断接口能正常工作
- 路由测试不再因为兼容层导出方式而误打真实数据库

### Operational

- Worker 未配置时首页提示正确
- 云库不可达时首页提示正确
- 有失败任务时首页提示正确
- 历史清空后首次进入无报错
- 重新触发追平后可建立新的任务与 checkpoint

## Recommended Implementation Strategy

建议采用**小范围控制面重构**，而不是大改同步引擎：

1. 修正文案乱码与页面信息架构
2. 收口首页数据模型
3. 下沉高级诊断动作
4. 增加历史清理后的空状态逻辑
5. 修复路由兼容层对测试替身的不友好结构
6. 补齐针对管理员主路径的测试

这样可以在 pre-launch 阶段以最小风险把模块提升到真正可用。

## Acceptance Criteria

当且仅当满足以下条件时，本次优化可以视为完成：

1. `/cloud-sync` 页面中文文案完整、无乱码、术语统一。
2. 管理员无需理解表级结构即可完成日常追平操作。
3. 首页只保留 3 个主操作，且动作语义清晰。
4. 高级诊断与主路径分层明显，不干扰首页使用。
5. 删除旧追平历史后，页面与接口均能稳定工作。
6. 后端相关测试可稳定验证控制面和诊断面主流程。
7. 优化后可从干净状态重新开始追平工作。
