# 采集任务步骤可观测说明

## 概述

采集任务执行过程中会写入**步骤级日志**到 `CollectionTaskLog`，并更新任务的 `current_step`、`progress`、`started_at`、`completed_at`。前端可在「任务详情」中查看按时间排序的步骤时间线，便于排错与观察进度。

## 步骤日志含义

执行器在以下节点成对打点（开始/结束）：

| 步骤 | step_id 示例 | 说明 |
|------|----------------|------|
| 登录 | `login` | 平台登录开始与结束（成功/失败） |
| 数据域导出 | `export_orders`、`export_products`、`export_services_agent` 等 | 各数据域（含子域）导出开始与结束 |
| 文件处理 | `file_process` | 下载文件解析与入库开始与结束 |

失败时该条日志的 `level` 为 `error`，`details` 中会包含 `error` 字段。

## details 字段结构

写入 `CollectionTaskLog.details`（JSON）的约定结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `step_id` | string | 步骤标识，如 `login`、`export_orders`、`file_process` |
| `component` | string | 组件名，如 `login`、`orders_export`、`file_process` |
| `data_domain` | string \| null | 数据域（含子域时如 `services:agent`），登录与文件处理为 null |
| `success` | boolean | 可选，步骤是否成功（结束打点时存在） |
| `duration_ms` | number | 可选，步骤耗时毫秒（结束打点时存在） |
| `error` | string | 可选，失败时的错误信息 |

## 前端查看方式

1. **任务详情（步骤时间线）**：在采集任务列表中点击任务的「详情」或行，打开详情页/抽屉；下半部分为「步骤时间线」，按 `timestamp` 排序展示每条日志的时间、message、level；若 `details` 含 `step_id`/`component` 会展示为步骤名；失败步骤高亮，`details.error` 可展开查看。
2. **查看日志弹窗**：保留原有「查看日志」弹窗，展示原始日志流；与任务详情中的步骤时间线互补。

## 任务开始/结束时间

- **started_at**：任务实际开始执行时由后端写入（执行器进入 run 流程时）。
- **completed_at**：任务进入终态（completed / failed / cancelled）时由后端写入。
- 任务详情页展示的「开始时间」「结束时间」即来自 API 返回的 `started_at`、`completed_at`；总耗时可由两者差值计算。

## 相关代码与表

- 表：`collection_tasks`（含 `current_step`、`progress`、`started_at`、`completed_at`）、`collection_task_logs`（含 `level`、`message`、`details`）。
- 执行器打点：`modules/apps/collection_center/executor_v2.py` 中 `_update_status(..., details=...)`；回调逻辑在 `backend/routers/collection.py` 的 `_execute_collection_task_background` 中注入。
