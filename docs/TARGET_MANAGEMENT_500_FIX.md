# 目标管理「查询失败」/ 500 问题检查与修复说明

## 问题现象

- 目标管理页请求 `GET /api/targets?page=1&page_size=20` 返回 **500 Internal Server Error**
- 前端显示「查询失败」，表格「暂无数据」

## 根因结论（已确认）

**数据库中 `sales_targets` 表存在，但缺少 ORM 所需的英文字段（如 `target_name`）。**

例如报错：

```text
column sales_targets.target_name does not exist
```

说明当前库里的 `sales_targets` 要么是早年其它迁移建的、要么从别的库拷来的，表结构与 `modules/core/db/schema.py` 里 `SalesTarget` 不一致（例如缺少 `target_name`、`target_type` 等）。

## 已做修改

### 1. 后端 `list_targets` 计数方式（`backend/routers/target_management.py`）

- **原逻辑**：`select(func.count()).select_from(query.subquery())`，用子查询做总数。
- **现逻辑**：用单独的 `select(func.count(SalesTarget.id)).select_from(SalesTarget)`，并复用与列表相同的筛选条件。
- **目的**：避免在部分驱动/库版本下因子查询导致的兼容性问题，同时行为与列表筛选一致。

### 2. 表结构修复迁移（`migrations/versions/20260125_fix_sales_targets_columns.py`）

- **作用**：当 `sales_targets` 已存在但缺少 `target_name` 等列时，自动补齐缺失列，使表与 `SalesTarget` 定义一致。
- **用法**：在**与后端使用同一数据库**的环境下执行：
  ```bash
  python -m alembic upgrade head
  ```
- **注意**：若当前 Alembic 的 head 不是 `v5_0_0_schema_snapshot`，需先解决迁移链，再执行到包含本迁移的 head。

### 3. 诊断脚本（`scripts/check_targets_api.py`）

- **作用**：在**与后端相同环境**（同一 `DATABASE_URL`）下，直接查 `sales_targets`，快速判断表是否存在、是否可读、是否缺列。
- **用法**：
  ```bash
  python scripts/check_targets_api.py
  ```
- **输出**：
  - 表存在且可读：会打印「sales_targets 表存在，当前条数: N」以及「最近 5 条目标可读」。
  - 缺列或其它错误：会打印错误类型与信息（如 `UndefinedColumnError: column sales_targets.target_name does not exist`）。

### 4. 测试中保留 500 详情（`tests/test_target_management_api.py`）

- `test_targets_list_authenticated_capture_500_detail` 在覆写 `get_current_user` 后调用 `GET /api/targets`，若返回 500 会通过 AssertionError 打出响应里的 `error.detail`，便于在 CI/本地复现时直接看到后端报错。

## 建议操作顺序

1. **确认环境**：后端、迁移、诊断脚本使用同一数据库（同一 `.env` / `DATABASE_URL`）。
2. **跑诊断脚本**：
   ```bash
   python scripts/check_targets_api.py
   ```
   若出现「target_name does not exist」或类似缺列错误，继续下一步。
3. **执行迁移**：
   ```bash
   python -m alembic upgrade head
   ```
4. **再次跑诊断脚本**：应看到「表存在」「最近 N 条目标可读」。
5. **重启后端**，再打开目标管理页，确认列表正常、不再 500。

## 若迁移不能直接跑到 head

- 说明当前库的 Alembic 版本链与仓库不一致（例如报错 `Can't locate revision identified by '20260111_complete_missing'`），需要先对齐迁移历史再跑 `upgrade head`。
- **方案二（推荐在此情况下使用）**：不依赖 Alembic，用独立脚本直接对 `sales_targets` 补齐缺失列：
  ```bash
  python scripts/fix_sales_targets_columns_standalone.py
  ```
  脚本会读取与后端相同的 `DATABASE_URL`，对每个存在 `sales_targets` 的 schema 检查并执行等价的 `ALTER TABLE ... ADD COLUMN ...`，使表与 `SalesTarget` 一致。执行完成后重启后端即可。
- 也可在**备份库后**在目标库中手工执行迁移文件里与 `sales_targets` 相关的 `ALTER TABLE ... ADD COLUMN ...` 语句（或运行上述脚本），使表具备 `target_name`、`target_type`、`period_start`、`period_end`、`target_amount`、`target_quantity`、`achieved_amount`、`achieved_quantity`、`achievement_rate`、`status`、`description`、`created_by`、`created_at`、`updated_at` 等列，类型与 `schema.py` 中 `SalesTarget` 一致。

## A 类表结构审查

目标管理所用表（`sales_targets`、`target_breakdown`）属于 A 类数据表。可与其它 A 类表（`sales_campaigns`、`sales_campaign_shops`、`performance_config`）一并做结构审查，避免类似「表存在但缺列」问题：

- **审查脚本**：`python scripts/check_a_class_tables_schema.py --report`
- **报告输出**：`docs/A_CLASS_TABLES_AUDIT_REPORT.md`（对比库中列与 schema.py，列出缺失列/多余列）

表结构有变更或新环境上线前建议复跑一次。

## 相关文件

- `backend/routers/target_management.py`：列表接口与计数逻辑
- `modules/core/db/schema.py`：`SalesTarget` 表定义
- `migrations/versions/20260125_fix_sales_targets_columns.py`：表结构修复迁移
- `scripts/fix_sales_targets_columns_standalone.py`：方案二独立脚本（不依赖 Alembic 直接改表）
- `scripts/check_a_class_tables_schema.py`：A 类表结构审查脚本
- `scripts/check_targets_api.py`：诊断脚本
- `tests/test_target_management_api.py`：目标管理接口测试（含 500 详情抓取）
