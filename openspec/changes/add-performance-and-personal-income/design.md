## Context

本变更是跨层改造：数据库 schema 迁移（public -> a_class/c_class）、后端 ORM 与路由更新、脚本与 Metabase SQL 同步、前端能力新增（我的收入）。  
其中 `sales_targets` 影响目标管理、TargetSyncService 与多个 Metabase Question，属于高耦合核心链路。

## Goals / Non-Goals

- Goals:
  - 在不破坏核心业务链路的前提下完成表迁移与引用更新
  - 固化「我的收入」接口契约与安全边界
  - 为后续 `add-performance-calculation-via-metabase` 提供稳定数据底座
- Non-Goals:
  - 不在本变更中实现绩效完整计算算法
  - 不迁移 `public.performance_config`（如需迁移，单独提案）

## Decisions

- Decision: 采用 Expand/Contract 迁移策略，而非直接硬切。
  - Expand 阶段：创建新表、回填数据、更新代码引用与 SQL、保留旧表只读兜底（短窗口）。
  - Contract 阶段：完成对账与业务验证后删除旧表。
  - Why: 降低一次性切换失败风险，便于回滚。

- Decision: 数据迁移使用显式列清单，禁止 `insert into ... select *`。
  - Why: 避免列顺序或字段新增导致错位写入。

- Decision: `GET /api/hr/me/income` 未关联员工场景固定为 `200 + linked=false`。
  - Why: 前端分支更稳定，契约更可测试，避免 404 与 200 双语义并存。

- Decision: 绩效计算能力未就绪时返回明确状态，禁止写入占位数据到正式表。
  - Why: 避免污染绩效与收入口径，降低后续审计与清理成本。

- Decision: `performance_config` 在当前阶段保持 `public.performance_config` 口径。
  - Why: 与现存实现与非目标保持一致，减少本变更范围膨胀。

- Decision: 员工级收入数据与店铺级绩效计算链路解耦。
  - 约束: `POST /api/performance/scores/calculate` 仅负责店铺绩效写入 `c_class.performance_scores`。
  - 员工提成/绩效写入由员工级定时任务或独立服务负责。
  - Why: 避免职责混淆与错误口径传导。

## Migration Plan

1. 预检查
   - 确认迁移对象存在性、行数、关键索引与外键现状
   - 备份 `public.sales_targets` 及关联关键数据
2. Expand
   - 创建 `a_class.sales_targets`、`c_class.performance_scores`、`c_class.shop_health_scores`、`c_class.shop_alerts`
   - 使用显式列清单回填数据
   - 更新 ORM、服务、脚本、Metabase SQL 引用
   - 更新并验证 `target_breakdown.target_id -> a_class.sales_targets.id`
3. 验证
   - 结构校验：表、索引、外键、schema 归属
   - 数据校验：迁移前后行数一致、关键字段空值率一致、抽样业务口径一致
   - 业务校验：目标管理 CRUD、TargetSyncService、业务概览 Questions、绩效公示
4. Contract
   - 删除 `public.sales_targets`、`public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts`
5. 回归
   - 运行 OpenSpec 与架构校验脚本

## Release Strategy

- 在同一发布窗口执行分阶段迁移：Expand -> Verify -> Contract。
- 禁止跨多个版本长期保留新旧表混跑状态。
- 若 Verify 未通过，停止进入 Contract 并按回滚方案处理。

## Rollback Plan

- 若 Expand 阶段失败：回滚 DDL/DML，保持旧表与旧引用可用。
- 若 Contract 前业务校验失败：回退应用引用到旧表，保留新表供排查。
- 若 Contract 后发现严重问题：通过 downgrade 反向迁移（a_class/c_class -> public），并恢复旧引用。

## Risks / Trade-offs

- 风险: 同批次部署失败导致核心报表不可用  
  Mitigation: 明确发布顺序、灰度窗口与回滚脚本演练

- 风险: 跨 schema 外键在迁移后出现约束异常  
  Mitigation: 在迁移验证中加入 FK 完整性检查和插入 smoke 测试

- 风险: 收入口径因占位数据被污染  
  Mitigation: 禁止占位写入正式表，仅允许返回未就绪状态

## Validation Criteria

- OpenSpec: `npx openspec validate add-performance-and-personal-income --strict` 通过
- 数据库: 迁移表归属正确，旧表删除时机正确，回滚可执行
- 契约: `GET /api/hr/me/income` 未关联场景固定 `200 + linked=false`
- 安全: 仅本人可查询，审计日志存在且敏感字段不明文输出
