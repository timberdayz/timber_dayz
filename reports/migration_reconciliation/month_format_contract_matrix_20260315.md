# 月份参数契约矩阵（前后端）

- 生成时间：2026-03-15
- 目的：排查 `YYYY-MM` / `YYYY-MM-DD` 混用导致的月份切换报错

## 1. 已修复的问题

### 1.1 目标管理按月查询

- 前端入口：`frontend/src/views/target/TargetManagement.vue`
  - 月份组件：`value-format="YYYY-MM"`
  - 调用：`api.getTargetByMonth(monthStr, "shop")`
- 后端接口：`GET /api/targets/by-month`（`backend/routers/target_management.py`）
  - 之前：仅接受 `YYYY-MM`，`YYYY-MM-DD` 会报“月份格式须为 YYYY-MM”
  - 现在：兼容 `YYYY-MM` 与 `YYYY-MM-DD`（自动归一到 `YYYY-MM`）

### 1.2 人员归属统计（月度）

- 前端入口：`frontend/src/views/hr/ShopAssignment.vue`
  - 月份组件：`value-format="YYYY-MM"`
  - 调用：`api.getHrShopProfitStatistics({ month })`
- 后端接口：`GET /api/hr/shop-profit-statistics`（`backend/routers/hr_management.py`）
  - 之前：仅接受 `YYYY-MM`
  - 现在：兼容 `YYYY-MM` 与 `YYYY-MM-DD`（统一走月份规范化工具）

## 2. 月份契约核对结果

| 模块 | 前端格式 | 后端约定 | 结果 |
|---|---|---|---|
| 目标管理（月度） | `YYYY-MM` | `YYYY-MM`（兼容 `YYYY-MM-DD`） | [OK] |
| 配置管理-销售目标 | `YYYY-MM` | `year_month: YYYY-MM` | [OK] |
| HR-我的收入 | `YYYY-MM` | `year_month: YYYY-MM` | [OK] |
| HR-绩效管理/公示 | `YYYY-MM` | `period: YYYY-MM` | [OK] |
| HR-店铺归属/利润统计 | `YYYY-MM` | `month: YYYY-MM`（兼容 `YYYY-MM-DD`） | [OK] |
| 业务概览-KPI | `YYYY-MM-01` | `month: YYYY-MM-DD(月初)` | [OK] |
| 业务概览-数据对比 | `YYYY-MM` 或 `YYYY-MM-DD` | `date: YYYY-MM 或 YYYY-MM-DD`（后端归一） | [OK] |
| 业务概览-店铺赛马 | `YYYY-MM` | `date: YYYY-MM` 前端传后端再转 `YYYY-MM-DD` | [OK] |
| 年度总结（月维度） | `YYYY-MM` | `period: YYYY-MM` | [OK] |
| 费用管理 | `YYYY-MM` | `year_month: YYYY-MM` | [OK] |

## 3. 代码级收口措施

- 新增统一工具：`backend/utils/year_month_utils.py`
  - `normalize_year_month(value)`：将 `YYYY-MM-DD` 归一为 `YYYY-MM`
  - `year_month_to_first_day(value)`：转换为月初 `date`
- 已接入：
  - `backend/routers/target_management.py`（`GET /targets/by-month`）
  - `backend/routers/hr_management.py`（`GET /api/hr/shop-profit-statistics`）

## 4. 回归测试

- 新增：`backend/tests/test_year_month_format_compatibility.py`
  - 验证月份工具兼容 `YYYY-MM-DD`
  - 验证 `get_target_by_month` 接收 `YYYY-MM-DD` 不报格式错
- 联合回归：`12 passed`

## 5. 结论

本次“月份格式须为 YYYY-MM”报错的根因已修复，且对同类高风险入口完成了收口与回归验证；当前未发现新的同类格式漂移问题。
