# 费用管理：店铺范围口径与分摊维度优化设计

- 日期：2026-11-28
- 范围：费用管理模块（`frontend/src/domains/business/views/finance/ExpenseManagement.vue` + `backend/domains/business/routers/expense_management.py`）
- 状态：待评审（业务已口头确认四项决策，见 §2）

---

## 1. 背景与问题

费用管理页「按月份查看」在 2026-11 出现已停用店铺 `1292370001`（ETERNALBLOOM_SG / eternalbloom.sg），且店铺名退化为裸 ID。经排查，这不是孤立显示 bug，而是四个问题叠加：

| # | 问题 | 现象 | 根因位置 |
|---|---|---|---|
| P1 | 未来月份存在"占位行" | 11/12 月出现无业务事实的费用行 | `a_class.operating_costs` 2026-06-09 15:51 批量预建全年 12 个月行 |
| P2 | 费用行可见性不看店铺状态 | 停用店的历史/未来行一律显示 | `expense_management.py:644-668`（`GET /expenses` 只查 operating_costs，不关联店铺主表） |
| P3 | 「按店铺查看」打开即空白 | 7 张汇总卡全 0、表格空、无任何提示 | `ExpenseManagement.vue:961-967`（`handleModeChange` 要求 `selectedShopId` 有值）+ `:1547-1557`（`onMounted` 未初始化该值）；且 `:1361-1366` 无空状态分支 |
| P4 | 快速拆分无分摊范围 | 一笔总额只能对全表平均摊，TikTok 预算也会摊到 Shopee 店 | `ExpenseManagement.vue:1159-1201`（`rowCount = monthlyTableData.length`） |

---

## 2. 业务概念与 SSOT 结论（已确认）

### 2.1 店铺的四层概念

| 层 | 载体 | 角色 | 结论 |
|---|---|---|---|
| 店铺账号 | `core.shop_accounts`（`enabled` / `business_role` / `internal_code` / `main_account_id`） | **权威 SSOT** | 费用、目标、权限均以此为准 |
| 平台店铺实体 | `core.dim_shops`（`is_active`） | 采集/订单侧维度 | **派生副本**（`backend/services/shop_sync_service.py:142` 由 `shop_accounts.enabled` 单向同步），已漂移 1 条（`1292370001`：`is_active=true` vs `enabled=false`）。**不得作为显示依据** |
| 租户/主账号 | `core.main_accounts` → `shop_accounts.main_account_id` | 签约、付租、预算主体 | 引入为分组二级维度 |
| 费用行 | `a_class.operating_costs`（`platform_code` + `shop_id` + `year_month`） | A 类费用唯一事实表 | 无外键，存快照键；唯一约束 `uq_operating_costs_a_platform_shop_month` **不动** |

### 2.2 现役租户结构

| 租户 | 平台 | 在营店数 |
|---|---|---|
| hongxikeji:main | shopee | 9 |
| shopee KR (Leslieshop:main) | shopee | 2 |
| chenewei666:main | shopee | 1 |
| Tiktok 1店 | tiktok | 3 |
| chenzeweinbnb@163.com | tiktok | 3 |

### 2.3 已确认的四项业务决策

1. **占位行**：直接清掉（软删，可恢复）。
2. **历史月份已停用店**：显示，并标注「已停用」。
3. **分组维度**：平台为主，租户为二级。
4. **按店铺视图**：修好现状（默认选店 + 空状态 + 补口径），不重做。

### 2.4 显示规则（核心口径）

费用是**历史事实**，可见性不能按"今天是否在营"一刀切。统一规则如下：

| 规则项 | 口径 |
|---|---|
| 表格行构成 | ① 该月**有费用记录**的店（全部，含已停用店，停用店带「已停用」标记）＋ ② 该月**在营且无记录**的店（空白行） |
| 空白行生成 | 仅 `enabled = true` 且 `business_role = 'operating_store'` 的店 |
| 快速拆分目标集合 | 仅 `enabled = true` 的店（已停用店即使当月有行也**不参与**分摊，其既有金额保持不变） |

推论：D1 清理占位行后，当前月与未来月份自然只剩在营店的空白行，**无需再写"按月份过滤"这类脆弱规则**；停用店若在当月确有真实费用记录，仍会显示并标注，只是不参与分摊。

真实录入数据显示租金为逐店等额（每店 50.30）、营销费用逐店不等，**现有数据是逐店口径，不是租户一笔再分摊** → 分组只改展示与操作范围，**不改行的归属口径**。

---

## 3. 目标与非目标

### 目标

- G1 清理未来月份占位行，消除「停用店出现在未来月份」的根因。
- G2 月度表格按「平台 → 租户 → 店铺」两级分组，停用店显式标注。
- G3 快速拆分支持按平台/租户限定分摊范围，且只作用于在营店铺。
- G4 「按店铺查看」打开即有内容，缺失时有明确空状态。
- G5 接口口径对齐 `platform_code + shop_id`（`docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` §5）。

### 非目标

- N1 不改费用行的归属口径与唯一约束。
- N2 不引入店铺营业时间轴（缺营业历史表，根治方案登记为 V2 债务）。
- N3 不做「平台台账 + 租户台账」双轴重构（V2 范畴）。
- N4 不扩展费用科目（文档 §2.2 方案 B 留口，暂不动）。

---

## 4. 方案总览

| 改动 | 层 | 性质 | 风险 |
|---|---|---|---|
| D1 占位行清理 | 数据 | 软删 113 行 | 低（可回滚） |
| D2 `/expenses/shops` 扩展 | 接口 | 加参数 + 加字段 | 低 |
| D3 `/expenses` 增强 | 接口 | 加过滤 + 加标记 + **修正店铺连接键** | 中 |
| D4 `/expenses/by-shop` 补口径 | 接口 | 加 platform_code | 低 |
| D5 月度视图两级分组 | 前端 | 展示 | 中 |
| D6 快速拆分分摊范围 | 前端 | 交互 | 中 |
| D7 按店铺视图修复 | 前端 | 交互 | 低 |

---

## 5. 详细设计

### D1 占位行清理（数据层）

**判定"纯占位行"**（与 `a_class.operating_costs` 实际列名一致）：

```sql
deleted_at IS NULL
AND COALESCE(rent_amount, 0)      = 0
AND COALESCE(marketing_amount, 0) = 0
AND COALESCE(utility_amount, 0)   = 0
AND COALESCE(ai_token_amount, 0)  = 0
AND COALESCE(other_amount, 0)     = 0
AND COALESCE(total_amount, 0)     = COALESCE(labor_amount, 0)
AND COALESCE(remark, '')          = ''
AND COALESCE(attachments, '[]'::jsonb) = '[]'::jsonb
```

**清理范围**：仅 `year_month BETWEEN '2026-06' AND '2026-12'`（未来 + 当月）。命中 **113 行**，labor 合计 118,947.37 元。

**为什么只清 06 及以后**：2026-01~05 命中 18 行同形态行，但属于历史月份，保留以免改写已结算口径（其中含真实录入行，混合口径不做自动判别）。

**执行方式**：
- 迁移文件：`current_migrations/versions/20261245_cleanup_expense_placeholder_rows.py`
  - `revision = "current_schema_20261245_cleanup_expense_placeholder_rows"`
  - `down_revision = "current_schema_20261244_drop_employee_shop_assignment_role"`（当前 head）
- **软删**：写 `deleted_at = now()` + `deleted_by = 4`（`core.dim_users` 中 `xihong` 超管，与既有软删行一致；该表主键列名为 `user_id`，不是 `id`）
- **批次标识**：同时写 `remark = '[占位行清理 2026-11-28]'`，使软删行在「已删除费用记录」区可识别
- `downgrade()` 按 `remark` 标记精确还原，谓词须为 `remark = '[占位行清理 2026-11-28]' AND deleted_at IS NOT NULL`（只还原本次批次的软删行，不碰存活行与其它软删行）
- `POST /expenses/{id}/restore`（`expense_management.py:1449-1456`）当前只清 `deleted_at` / `deleted_by`、**不清 `remark`** ⇒ 恢复后存活行仍带批次标记。需在该路由补：还原时一并清掉 `[占位行清理 ...]` 前缀，避免留下假标记。
- 执行前用仓库既有的 `perform_pre_migration_backup` 做法（见 `current_migrations/versions/20261243_*`）做快照
- 迁移天然幂等（`deleted_at IS NULL` 条件），重复执行命中 0 行

**预期效果**：年度累计从 363,783.89 降至 244,836.52；11/12 月表格只剩在营店的空白行（18 行），停用店不再出现。

> 注：清理后软删行会出现在页面「已删除费用记录」区（保留可恢复能力），属预期。

### D2 `GET /api/expenses/shops`

**当前**：`enabled = true AND business_role = 'operating_store'`（`expense_management.py:234-239`）。

**变更**：新增查询参数 `include_disabled: bool = false`；响应每项新增字段：

| 字段 | 说明 |
|---|---|
| `enabled` | 店铺账号是否启用 |
| `internal_code` | 内部编号（XHKJ11_SG） |
| `platform_shop_id` | 平台店铺 ID（**可能为空**：32 家停用 Shopee 店中有 30 家为空） |
| `shop_account_id` | 店铺账号 ID（TikTok 费用行用的就是这个） |
| `main_account_id` | 租户标识 |
| `main_account_name` | 租户名称（`core.main_accounts.main_account_name`） |

`include_disabled=true` 时返回全部 `business_role = 'operating_store'` 店铺（含停用），供前端判断「已停用」标注。

> 调用面已确认：前端仅 `ExpenseManagement.vue:930` 一处；另有 `scripts/high_frequency_pages_probe.py:179`、`scripts/test_expense_api.py:55` 两处脚本调用。**加参数为向后兼容变更**（不传 `include_disabled` 时行为不变），三处调用均无需修改。
>
> `internal_code` 与全站显示名口径一致（`frontend/src/utils/shopDisplay.js:65`：`internal_code` → `account_alias` → `store_name` → 键值）。前端 `availableShops` 已经过 `resolveShopDisplay` 装饰，**不得对已装饰对象二次装饰**，否则显示名会被 `internal_code` 顶替。

### D3 `GET /api/expenses`

- 新增 `platform_code: Optional[str]` 过滤参数；
- 新增 `year: Optional[str]` 年度过滤参数（服务 D7 的「按店铺」下拉集合：需要知道某年哪些店有记录）；
- 响应每项新增 `shop_enabled: bool`、`shop_internal_code`、`shop_main_account_id`、`shop_main_account_name`，供前端做「已停用」标注与租户分组。

**⚠ 店铺连接键规则（实施阻断项，必须按此实现）**：

```sql
LEFT JOIN core.shop_accounts sa
       ON sa.platform = oc."platform_code"
      AND (sa.platform_shop_id = oc."shop_id" OR sa.shop_account_id = oc."shop_id")
LEFT JOIN core.main_accounts ma ON ma.main_account_id = sa.main_account_id
```

- Shopee 店铺：`platform_shop_id` 为平台数字 ID（费用行用它）
- **TikTok 店铺：`platform_shop_id` 为空，费用行存的是 `shop_account_id`（如 `tiktok_sg_daone_mall_local`）**
  ⇒ 只按 `platform_shop_id` 连接会漏掉全部 6 家 TikTok 店（占存活行 71/228），`shop_enabled` 会变成 NULL，并被 D6 的 `enabled = true` 目标集合排除，「仅 TikTok 拆分到 6 家」验收必然失败。
- 连接必须带 `sa.platform = oc.platform_code`，避免跨平台同 shop_id 误连。
- 已实测：20 个 `shop_id` 各匹配且仅匹配 1 条 `shop_accounts`，连接前后行数 228 → 228，**无重复放大**；实施时仍建议用 `EXISTS` 子查询或 `DISTINCT` 兜底，防止后续数据出现一店多行。
- **前端匹配键**：Shopee 的 `shop_id` 是平台店铺 ID（`1292370001`）、TikTok 的是本地账号 ID（`tiktok_sg_daone_mall_local`）—— **两者语义不同**。因此前端统一用 **`(platform_code, shop_account_id)`** 匹配：店铺目录行取 D2 返回的 `shop_account_id`，费用行取 D3 回传的 `shop_shop_account_id`；匹配不到的孤儿行回退到 `shop_id`，天然不与任何店铺冲突。
- 查不到对应店铺账号（历史孤儿 shop_id）时 `shop_enabled` 保持 `NULL`，前端显示原始 ID +「状态未知」，不丢弃该行。

**数据校验（已实测）**：现存 233 行 `platform_code` 全为 `shopee` / `tiktok`，无 NULL、无大小写差异，且同一 `shop_id` 不跨平台 ⇒ 加 `platform_code` 过滤不会让历史行"消失"。

- 列表保持 `ORDER BY year_month DESC, shop_id` 不变（分组在前端做，避免影响既有调用方）。

### D4 `GET /api/expenses/by-shop`

- 新增 `platform_code: Optional[str]` 参数，与 `shop_id` 组合过滤，对齐文档 §5「按 `platform_code + shop_id` 连接」；
- 前端调用时必传 `platform_code`（取自 `availableShops`）。
- 已实测：历史行 `platform_code` 无 NULL、无大小写差异、`shop_id` 不跨平台 ⇒ 该过滤安全，不会让历史行消失。

### D5 月度视图两级分组（前端）

**⚠ 实现路径约束（实施阻断项）**：Element Plus `^2.3.8` 的 `el-table` **没有内置数据分组 prop**（源码中 `group` 仅为列 class 名），且**不引入树表**——树表会让平台/租户父行混入 `monthlyTableData`，污染 `:379` 的「拆分店铺数」与 `:1165` 的 `rowCount`。

**采用的分组形态**：
- **一级（平台）**：表格上方平台分段控件（全部 / Shopee / TikTok），沿用仓库既有范式（绩效管理用平台筛选器）。**分段会过滤表格行**：当前分段范围内的行才显示。
- **二级（租户）**：单表内按 `main_account_id` 排序，租户名以副标题形式显示在店铺名下（复用 `shopDisplay.js` 的 `secondary_name` 机制）。**禁止把分组标题作为伪行注入 `monthlyTableData`**（否则会污染 `:379` 与 `:1165`）——分组信息只渲染在店铺单元格内。
- **计数口径统一**：「拆分店铺数」（`:379`）与快速拆分弹窗的「共 N 家」都取 **当前分段范围内、`enabled = true` 的店铺数**；分段=全部时即 18 家（Shopee 12 + TikTok 6）。

**行数据组装**（`loadMonthlyExpenses`，`ExpenseManagement.vue:995-1032`）调整：

```
1. await loadShops()          ← 必须先 await（现实现未 await，见下）
2. allShops       = GET /expenses/shops?include_disabled=true   （含停用，带租户/内部编号）
   operatingShops = allShops.filter(s => s.enabled === true)    （18 家：Shopee 12 + TikTok 6）
3. existingData   = GET /expenses?year_month=...&page_size=1000 （每行自带 shop_enabled 等）
4. newRows        = operatingShops 中当月无记录者 → 空白行
5. 合并后按 platform_code → main_account_id → 店铺名排序
6. 每行注入 shop_enabled（false → 「已停用」标签）
```

**⚠ 首屏时序（实施阻断项）**：现 `onMounted`（`:1547-1557`）未 `await loadShops()` 就调 `loadMonthlyExpenses()`，此时 `availableShops` 尚未就绪 ⇒ 空白行不生成、首屏少 18 行。必须改为 `await loadShops()` 之后再加载月度数据。

**⚠ 店铺集合语义拆分（实施阻断项）**：D2 之后 `/expenses/shops` 返回 50 家（18 在营 + 32 停用）。若继续把停用店混在同一个集合里：
- 用它生成空白行 → 多出 32 行；
- 用它做分摊范围 → 已停用店被算进去。
必须拆成 `allShops`（标注与按店铺下拉用）与 `operatingShops`（空白行 + 分摊范围用），见上。

**可见性规则**：统一按 §2.4——有记录即显示（停用店加标注），空白行只给在营店。

**「已停用」呈现**：店铺列下拉旁加 `<el-tag type="info" size="small">已停用</el-tag>`；停用行下拉保持 `disabled`（现有 `:disabled="!!row.id"` 逻辑不变）。

### D6 快速拆分分摊范围（前端）

**对话框新增「分摊范围」选择**（`quickSplitForm` 同级新增 `quickSplitScope`）：

| 选项 | 含义 |
|---|---|
| 全部在营店铺 | 现状行为（默认） |
| 仅 Shopee | platform_code = 'shopee' |
| 仅 TikTok | platform_code = 'tiktok' |
| 按租户 | 二级选择具体 `main_account_id` |

**规则**：
- 分摊目标集合 = 范围内 **且 `enabled = true`**（即 `operatingShops`）的店铺行；已停用店即使当月有行也**不参与**分摊，其既有金额保持不变；
- 平台分段控件（§D5）与分摊范围联动：分段选中某平台时，分摊范围默认该平台；
- `distributeEvenly` 只在目标集合上计算（`ExpenseManagement.vue:1147-1157` 不变，调用方传入目标集合长度）；
- 确认弹窗文案随之改为：「将按 <范围描述> 共 N 家在营店铺平均拆分」；
- 落在范围外的行**不被清零**（现状 `handleApplyQuickSplit` 会覆盖全部行金额，改后仅覆盖目标集合行，避免误清空）。

> 这同时修掉一个现存隐患：现状 `handleApplyQuickSplit` 对全部行赋值（`:1190-1197`），会把范围外的既有金额清成 0。

### D7 「按店铺查看」修复（前端）

| 问题 | 修复 |
|---|---|
| 打开空白 | `onMounted` 在 `await loadShops()` 之后默认选中排序第一家在营店（`hx_home.sg` / `1391124228`）并触发加载 |
| 无提示 | 未选店时展示 `<el-empty description="请先选择店铺">`；已选店但无记录时展示「该店铺该年度暂无费用记录」 |
| 口径不全 | 调用 `/expenses/by-shop` 必传 `platform_code` |
| 缺状态 | 汇总卡与表格补「该店已停用」提示（若所选店已停用，允许只读查看历史） |

**下拉选项集**：D2 后店铺总数 50 家（18 在营 + 32 停用）。下拉只保留「在营店 ＋ 该年度有费用记录的停用店」，其余停用店不列出（32 家停用店大多从未有过业务数据）。

> 「该年度有记录的停用店」由 D3 新增的 `year` 过滤参数查出（`GET /expenses?year=YYYY&page_size=1000`）。
> ⚠️ **不可**用「当前选中店的行」推导该集合 —— 那会形成鸡生蛋：停用店永远进不了下拉，也就永远无法被查看历史。

> 断言基准：默认店 `hx_home.sg`（1391124228）在 2026 年清理前 12 行、**清理后 6 行**（其余月份为纯占位行，已软删）。验收断言用 **6 行**。

---

## 6. 数据流

```
[core.shop_accounts] ──(enabled/business_role/main_account_id)──┐
                                                                 ├─→ GET /expenses/shops?include_disabled=true
[core.main_accounts] ──(main_account_name)────────────────────────┘         │
                                                                           ▼
                                            availableShops（含停用、带租户信息）
                                                                           │
GET /expenses?year_month=&platform_code= ──(行 + shop_enabled)──┐          │
                                                                   ▼          ▼
                              有记录即显示（停用店标注）→ 平台/租户分组 → 表格 → 快速拆分（范围选择）
```

---

## 7. 边界与错误处理

| 边界 | 处理 |
|---|---|
| 店铺账号表里找不到对应行（历史孤儿 shop_id） | `shop_enabled` 视为 `null`，前端显示原始 ID + 「状态未知」标签，不静默丢弃该行 |
| `main_account_id` 为空 | 二级分组归入「未归属租户」组，不报错 |
| 停用店铺在当月有真实费用行 | 显示 + 标注；**不参与**快速拆分；金额仍可手工编辑保存 |
| 停用店铺在当月无任何行 | 不生成空白行（空白行只给在营店） |
| 软删的占位行出现在「已删除费用记录」区 | 带 `[占位行清理 2026-11-28]` 标记可识别；恢复会复活占位行并重新进入看板成本口径 ⇒ 恢复入口需二次确认并提示影响 |
| 清理后页面行数变化 | 前端行数从接口动态取，不写死 |
| `include_disabled` 未传 | 保持旧行为（仅在营），向后兼容 |
| 迁移已执行后的重复执行 | 迁移幂等（`deleted_at IS NULL` 条件天然幂等） |

---

## 8. 测试与验收

### 后端

| 用例 | 断言 |
|---|---|
| `GET /expenses/shops?include_disabled=true` | 返回含 `enabled=false` 的店铺，且带 `internal_code`/`main_account_id`/`main_account_name` |
| `GET /expenses/shops`（不带参数） | 与改造前一致（仅在营） |
| `GET /expenses?year_month=2026-11` | 每行含 `shop_enabled`；`1292370001` 的行 `shop_enabled=false` |
| `GET /expenses/by-shop?shop_id=X&platform_code=shopee` | 只返回该平台该店记录 |
| 迁移脚本 | 命中 113 行；`downgrade()` 可完全还原 |

### 前端

| 用例 | 断言 |
|---|---|
| 2026-11 视图 | 清理后该月无存量费用行 ⇒ 表格 18 行**全为空白行**（Shopee 12 + TikTok 6），无已停用店行 |
| 2026-01 视图 | 显示 CHENEWEI666_SG（1227491331）历史行，带「已停用」标签；ETERNALBLOOM_SG 最早出现在 **2026-02** |
| 分组 | 一级 Shopee(12) / TikTok(6)；二级按租户展开 |
| 快速拆分（仅 TikTok） | 只有 6 家 TikTok 行被赋值；Shopee 行金额保持不变 |
| 按店铺视图 | 打开即选中 `hx_home.sg` 并加载出 2026 年 **6 行**（清理后）；无记录店铺显示空状态 |
| 年度累计 | 清理后显示 244,836.52 |
| 迁移幂等 | 重复执行 `upgrade()` 命中行数为 0（`deleted_at IS NULL` 条件天然幂等） |
| 迁移回滚 | `downgrade()` 只还原本批次（按 `remark` 标记），不误还原其它软删行 |

### 回归

- `backend/tests/test_expense_management_routes.py`
- `backend/tests/test_expense_management_soft_delete_contract.py`
- `backend/tests/test_operating_cost_schema_contract.py`

---

## 9. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 清理误伤真实录入 | 判定条件含"无备注、无附件、其余科目全 0"；软删可恢复；执行前快照 |
| 历史利润口径变化 | 只清 2026-06 及以后；01~05 不动；`profit_basis_service` 走 `total - labor`，占位行净额 0，**不受影响**；但看板成本口径会变，见 §9.1 |
| 分组改变影响既有操作习惯 | 分组仅重排与标注，不改变行的归属键与保存接口 |
| 快速拆分行为变更 | 范围选择默认「全部在营店铺」，与现状等价；确认弹窗明示范围与店数 |

**回滚**：迁移 `downgrade()` 还原软删；前后端改动均为新增参数/字段，可独立回退。

### 9.1 看板成本口径的连带影响（⚠ 需业务确认）

`backend/services/postgresql_dashboard_service.py:1343-1359` 的看板成本 SQL 对 `total_amount` 求和，**仅当 `finance.employee_labor_cost_allocations` 有该月投影行时才扣掉 labor**；而该表当前只有 **2026-07、2026-10** 两个月的数据。

因此清理占位行后，看板业务概览的月度成本会发生变化（实测）：

| 月份 | 清理前 | 清理后 | 说明 |
|---|---|---|---|
| 2026-06 | 20,000.00 | `NULL`（前端显示 `--`） | 无费用行 |
| 2026-08 | 20,027.79 | 1,080.42 | 仅剩 1 行真实数据 |
| 2026-09 / 11 / 12 | 20,000.00 | `NULL`（`--`） | 无费用行 |
| 2026-07 / 10 | 不变 | 不变 | 有工资单投影，扣 labor 后口径一致 |

**两个口径的全年合计不要混用**：

| 口径 | 清理前 | 清理后 | 变化 |
|---|---|---|---|
| 看板业务概览（`postgresql_dashboard_service.py:1343-1359`，`total − labor`） | 386,488.96 | 287,541.59 | −98,947.37 |
| 费用页「年度累计」（`expense_management.py:406-421`，直接 `SUM(total_amount)`） | 363,783.89 | 244,836.52 | −118,947.37 |

差额 20,000.00 = **2026-10** 的 19 行占位行：10 月有工资单投影（`use_projected_labor = true`），`total − labor = 0`，删与不删都不进看板，但会进费用页年度累计。

**平台筛选下的差异**：2026-08 残留的 1,080.42 真实行属于 **shopee**；按 tiktok 筛选时该月为 `NULL`。看板的平台维度看板同样受影响。

**这 20,000 元/月是占位值，不是真实人力成本**，依据：

1. 由 2026-06-09 15:51 一次性预建，每店 1052.63 = 20000 ÷ 19，`remark` 与 `attachments` 均空，`created_at` 同一时刻；
2. 06~12 每个月金额**完全相同**（整 20,000），而真实工资单投影（07 月 31,184.61 / 10 月 25,291.93）并非常数；
3. 06/08/09/11/12 五个月在 `finance.employee_labor_cost_allocations` 里**没有任何投影行**，说明这五个月根本没有工资单数据。

**结论**：清理后这 5 个月看板显示 `--`（成本缺失）是**更真实**的状态，不是丢数据；这些月的人力成本应由工资单链路补齐，而不是依赖 `operating_costs` 的占位行。

**待业务确认**：接受这 5 个月看板成本变为 `--`；若不接受，替代方案是**不删行、改为仅前端隐藏**（则 §9.1 不成立，但 P1/P2 根因仍在库内）。

---

## 10. 登记为 V2 债务（本次不做）

1. **店铺营业时间轴**：新增 `core.shop_status_history`（或 `shop_accounts` 增开/停业月），使「某月是否在营」可查，费用行可见性由时间轴决定，彻底消除「有记录即显示」的近似规则。
2. **`core.dim_shops.is_active` 漂移治理**：明确其为派生副本或纳入同步闭环（当前 `1292370001` 已漂移）。
3. **费用科目扩展**：按文档 §2.2 方案 B 增加明确科目列。
4. **平台/租户双轴台账重构**。

---

## 11. 修订历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1 | 2026-11-28 | 初稿（业务已确认 §2.3 四项决策） |
| v2 | 2026-11-28 | 独立审查后修订：M1 补 TikTok 连接键规则（`platform_shop_id` 为空）；M2 增 §9.1 看板成本连带影响（原 §9 结论有误，已修正）；M3 补 `await loadShops()` 时序与 `allShops`/`operatingShops` 语义拆分；M4 §2.4 与 §7 可见性规则统一；M5 修正 2026-01/默认店行数等断言；M6 改用平台分段控件 + 租户副标题（`el-table` 无内置分组 prop）；M7 补 `deleted_by=4`、迁移 revision/down_revision、软删行批次标识与恢复提示 |
| v3 | 2026-11-28 | 二轮复审后修订：P1 拆分 §9.1 的看板口径与费用页年度累计口径两个全年合计（386,488.96→287,541.59 / 363,783.89→244,836.52，差额 20,000 = 2026-10 占位行）；P2 分组标题禁止注入伪行、`rowCount` 改为按 D6 目标集合计数；P3 平台分段控件明确过滤行为并统一计数口径；P4 `downgrade()` 谓词补 `deleted_at IS NOT NULL`、restore 路由需清批次标记；补 D2 返回 `platform_shop_id`/`shop_account_id`、D3 连接加 `DISTINCT`/`EXISTS` 兜底 |
