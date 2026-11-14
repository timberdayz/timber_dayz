# 模板决策资产 SSOT 收敛 与 语义层标量函数性能治理 —— 优化方案

> 日期：2026-11-14
> 触发：v7.29.3 ~ v7.29.5 上线后，对库存维度「模板更新后仍提示需要更新 + 仍有字段对不上」
> 问题的复盘，顺带审出的一批存量债。
> 状态：待评审（等业务确认）。实施顺序见 §6。

---

## 0. 一页摘要

本方案是**一次存量债清理**，不是新功能。分两大部分：

- **A 部分（性能治理）**：语义层原子视图里的**逐行标量函数调用（N+1）**。
  实测库存语义视图读一次 **197 ms**，底层表只要 **4.4 ms** ⇒ **45 倍**浪费。
  这是本轮**最高价值**的一项。主方案 = **物化副本**（照搬仓库既有 3 个先例，口径零变化）。
- **B 部分（SSOT 收敛）**：把「同一件事有两个说了算的地方」收敛掉，把「配置一漏就静默出错」的路堵死。
  共 6 个动作（B1~B6），全部**不动生产数据**，代码与文档级改动。

| # | 动作 | 性质 | 预估收益 | 风险 |
|---|---|---|---|---|
| A1 | 语义层库存视图**物化副本**（照搬仓库既有 3 个先例，口径零变化） | 性能 | 库存取数 197ms → **毫秒级**；一次解决 4 处逐行结构 | 中（刷新顺序 + 判据要跟着改） |
| A2 | 物化视图的**刷新路径**优化（集合函数，降级为可选） | 性能 | REFRESH 成本再降；当前 197ms 不痛 | 低 |
| B1 | 删掉域默认去重字段表（死代码） | SSOT | 堵死「漏配 ⇒ 算出错身份」静默路 | 低 |
| B2 | 清单 `in_hash` == 去重字段表，一致性检查推广到 27 维度 | SSOT | 防两处声明漂移 | 极低 |
| B3 | `SYNC_CORE_FIELDS_HASH_ENABLED` 加前置门禁 | 防呆 | 堵死「一键切口径」 | 低 |
| B4 | 规格 §3.1 表述修正 | 文档 | 防「照规格改实现」⇒ 又一次全量重建 | 极低 |
| B5 | 语义契约 consumer 补登记 | 可查性 | 让「改了字段影响谁」查得到 | 低 |
| B6 | 物理列通路**宣告弃用**（业务已拍板：无外部系统直查） | SSOT | 业务字段不再双份存储 | 低（只关新写入，不删列） |

**明确不做**（理由见 §10）：lint/格式全量清理、`VERSION` 文件同步、命名体系统一、**改写语义层视图正文**（物化副本已把它挤出请求路径）。

---

## 1. 背景与证据

### 1.1 已完成的部分（v7.29.3 ~ v7.29.5，均已部署 success）

| 版本 | 内容 |
|---|---|
| v7.29.3 | 库存维度配 13 项核心字段清单 + 去重字段表改 2 项 + 新增重建脚本 |
| v7.29.4 | 重建脚本改用应用自身 session 工厂（v7.29.3 镜像里连不上生产库） |
| v7.29.5 | 投影时同步 `notes`（`save_template` 不写该列，守卫永远红） |

生产数据已修复：事实表 4111 → **3855** 行（删 256 组重复行）、行内 `shop_id` 100% 归一、
hash 100% 命中新口径、模板 v3 → v4（dedup 2 项 + 清单 13 项）、守卫 **27/27 一致**。

### 1.2 这次审视新查清的事实（全部实测）

**F1 — 重复行的根因不是「商品改名」，是作用域身份键换过。**
`shop_id` → `shop_account_id`（2026-11-03）。两批行按各自当时的口径算 hash ⇒ 都留下来。

**F2 — 参与 data_hash 的字段是 7 个**（去重字段表 4 项 + 系统身份 3 项）。
清单里的 `in_hash` **当前不改变 hash 的字段集合**（`deduplication_service.py:365`：
`fields = list(deduplication_fields or entry_by_key.keys())`）。

**F3 — 库存的真正消费方有 4 个模块**，不是只有商品中心：
滞销清单 `/inventory/clearance-ranking`、库存/经营概览库存卡、低库存告警定时任务、Metabase 模型。
商品中心读的是状态层 `mart.inventory_state`。

**F4 — 域默认去重字段表在 27 个维度上全是死代码。**
实测：27 个维度的模板**全部**配了 `deduplication_fields` ⇒
`get_deduplication_fields` 的域默认分支没有任何活路径会走到。
且它的内容是**标准字段键**（`platform_sku` / `product_id` / `warehouse_name`），
妙手表头里根本没有这些名字。

**F5 — 域默认一旦被走到，后果是灾难且静默。**
实测（开发库）：3 个不同 SKU 算出的 hash **完全相同**（`cdce587202df73f2`），
因为 4 个字段在 `raw_data` 里一个都取不到 ⇒ 同一天所有行塌成同一身份 ⇒
upsert 互相覆盖 ⇒ **一天只剩一行**，而且不报错。

**F6 — 清单 `in_hash` 与去重字段表 27/27 逐字一致**（按各自命名体系比对）。
⇒ 清单**不是假事实源**。但同一件事在两处各写一遍，靠人工保持同步；
库存维度有守护测试，**其余 26 个维度没有检查**。

**F7 — 清单支持两种形态，且是有意分工**（`template_matcher.py:557/579` 注释明写）：
- 带 `raw_name` 的条目 ⇒ 管「某个物理列是否可缺」→ 落列 + 漂移阻断
- 纯 `semantic_key` 的条目 ⇒ 管「这个语义键参与去重/校验」→ hash 取值 + 语义契约

**F8 — 库存事实表的 26 个业务物理列全部 NULL**，且：
表头 28 列里 3 列（次品库存/暂存库存/备注）**没有物理列**，
另多出一个**重复列 `商品`**（与 `商品SKU` 同语义）。
但 `raw_data` 里 3855/3855 全有值 ⇒ 数据没丢。

**F9 — 物理列这条路没有任何人走。**
- 语义层视图 `semantic.fact_inventory_snapshot` 只 UNION 系统列 + `raw_data`，**不取任何业务物理列**
- 全仓搜直查 `可用库存` / `库存总量` / `单价_元` 物理列 ⇒ **零命中**
  （命中的都是字段映射元数据、row dict 取值、mart 层别名、迁移脚本）
- Metabase 积压清单从 mart 层 CTE 取数，`available_stock AS "可用库存"` 是**输出别名**
- AGENTS.md 明确：数据流是 `b_class raw -> semantic -> mart -> api -> router -> frontend`，
  Metabase 是历史遗留、不在活跃运行时
⇒ 那 26 个空列是**一条没人走的通路的遗留物**。

**F10 — 性能瓶颈在语义层视图的逐行函数调用，不在 UNION。**
生产实测（3855 行）：

| 读法 | 耗时 |
|---|---|
| 直接读三张 `b_class` 表 | 0.5 ms |
| 读 `semantic.fact_inventory_snapshot` | **197 ms** |

逐节点耗时分解（`EXPLAIN ANALYZE, TIMING ON`）：

| 节点 | 实际耗时 |
|---|---|
| `Merge Append`（读三张 b_class 表） | 4.4 ms |
| `Result`（行级表达式 + 2 个标量函数） | 59 ms |
| `Seq Scan on shop_identity_resolution_candidates_v2_mv`（**loops=3855**） | 54 ms |
| `scoped` CTE 重算（**loops=3855**，带 Sort/Unique/Limit） | 58 ms |
| 外层 `Nested Loop Left Join` | 121 ms |
| `WindowAgg`（`identity_candidates` 构造） | 45 ms |

三个 `loops=3855` 的结构是主因 ⇒ 典型 **N+1 查询**。

**F11 — 被扫最多的对象不是事实表，是两张小对照表。**

| 对象 | 行数 | seq_scan | seq_tup_read | idx_scan |
|---|---|---|---|---|
| `semantic.semantic_field_aliases` | 319 | 6,544,825 | 4.04 亿 | 1.57 亿 |
| `semantic.shop_identity_resolution_candidates_v2_mv` | 72 | 6,102,275 | 4.23 亿 | 0 |
| `b_class.fact_miaoshou_inventory_snapshot` | 3855 | 474,685 | 2.16 亿 | 6,464 |

⇒ 扫得最多的是**查表函数**本身，不是数据表。

**F12 — `resolve_alias` 是全语义层通病，不止库存。**
`semantic.resolve_alias(...)` 用在 `orders_atomic`(25) / `analytics_atomic`(32) /
`analytics_monthly_atomic_mv`(27) / `products_atomic`(13) / `metabase_orders_model`(198) 等
**全部原子层视图** ⇒ 654 万次扫描的根源在这里。

**F12b — 仓库已经有 3 个「同构先例」：普通视图 + 物化副本。**
`refresh_registry.py` 的注释原文：

> 原子层的物化副本：正文与普通视图完全一致（`SELECT *`），只把「每行跑一次店铺别名解析」
> 从请求路径搬到刷新路径。口径零变化。
>
> 商品原子层的物化副本（2026-11-05）：商品日 KPI 读普通视图时每次请求都要重做
> 「多表 UNION + 逐行 JSON 解析 + 逐行身份解析」（**生产实测 14.1 秒**），
> 物化后请求侧毫秒级。正文 = 普通视图正文（`SELECT *`）⇒ 口径零变化。

已有三对：

| 普通视图（正本） | 物化副本 | 下游读谁 |
|---|---|---|
| `semantic.fact_orders_atomic` | `semantic.fact_orders_atomic_mv` | `mart.platform_day_kpi` 等直接读 `_mv` |
| `semantic.fact_analytics_atomic` | `semantic.fact_analytics_atomic_mv` | 同上 |
| `semantic.fact_products_atomic` | `semantic.fact_products_atomic_mv` | `mart.product_day_kpi` |

⇒ **库存是同一类问题的第 4 个**，解法已被验证过（14.1 秒 → 毫秒级）。

**F12c — 物化视图的刷新基础设施已齐备，不需要从零搭。**
`backend/services/data_pipeline/refresh_runner.py::_refresh_materialized_view()`：
- 目标名匹配 `_mv` ⇒ 自动走 `REFRESH MATERIALIZED VIEW`（**不执行**资产文件里的 `DROP ... CASCADE`）
- `pg_try_advisory_xact_lock` 刷新互斥锁（并发刷新安全）
- 语句超时临时抬到 **10 分钟**（因为 REFRESH 全量重算；生产实测订单 MV 刷一次 115 秒）
- REFRESH 后自动补齐资产文件里的 `CREATE INDEX IF NOT EXISTS`
- MV 不存在时**回落**去跑资产文件（资产自带「存在则 REFRESH / 不存在则 CREATE」的自愈）
- `refresh_registry.PIPELINE_DEPENDENCIES` 管刷新顺序，`ASSET_PREREQUISITES` 管建对象前置

**F12d — 物化化会牵动两处「容易漏」的判据。**
1. `backend/tasks/refresh_queue_tasks.py:136`
   ```python
   INVENTORY_FACT_TARGET = "semantic.fact_inventory_snapshot"
   ```
   这是「本次刷新有没有动库存事实 ⇒ 状态层要不要跟着重算」的**判据**。
   ⇒ 下游改读物化副本后，这个判据必须跟着指向 `_mv`，否则**状态层不会被触发刷新**
   ⇒ 库龄不推进、滞销榜不更新（且不报错）。
2. `refresh_queue_tasks.py:387-397` 的顺序必须保证
   `物化副本 REFRESH` → `InventoryStateRefreshService.refresh()` → `InventoryAgeRefreshService.refresh()`。

**F13 — `SYNC_CORE_FIELDS_HASH_ENABLED` 的真实语义**（与我先前的担心不同）：
打开后**不改变 hash 的字段集合**（集合仍由 `deduplication_fields` 决定，
`deduplication_service.py:365` 的 docstring 明写「绝不自己重建集合」），
只改变**取值方式**（清单驱动的「逐字优先 + 语义兜底」）。
但取值方式一变，**部分行的 hash 值就会变** ⇒ 已入库行被当成新数据 ⇒ 事实表膨胀。
规格 §6.1 要求「打开前必须先离线回放」，但**代码里没有任何强制**。

**F14 — `VERSION` 文件不构成风险。**
`backend/main.py:30` 优先读 `APP_VERSION`/`IMAGE_TAG`/`RELEASE_VERSION`，VERSION 只是兜底；
`tests/test_release_observability_contract.py` 只断言格式是 `vX.Y.Z`，不钉死值 ⇒ 不会让 CI 红。

**F15 — `core.data_files` 在生产是空表**，库存事实行的 `file_id`/`template_id` **3855 行全 NULL**
⇒ **无法靠「重新入库」修正**，只能就地重算（本次即如此）。

### 1.3 本次审视推翻的两处先前判断（留档，避免以后重犯）

| 先前判断 | 实际 | 错因 |
|---|---|---|
| 「20/27 维度 `in_hash` 与去重表不一致」 | **27/27 一致** | 其它维度用 `semantic_key` 声明，我却按 `raw_name` 比对 |
| 「清单两套填法是 SSOT 断裂」 | **是有意分工**，代码注释明写 | 把设计当缺陷 |

---

## 2. 设计原则

1. **一条规则，一个说了算的地方。** 同一件事不得在两处独立声明。
2. **静默出错的路必须堵死。** 「拿不到值就悄悄算个别的」比「明确报错」危险得多。
3. **口径零变化优先。** 物化副本正文 = 正本正文（`SELECT *`）⇒ 天然逐字相同；任何**改写正本表达式**的提速方案，都要逐字等价验证才准入。
4. **预发布期不做大范围重构。** 只做能独立验证、能独立回滚的改动。
5. **保留「半迁移库能建起来」的兜底语义**，直到有替代方案（见 A1 的取舍）。

---

## 3. A 部分：性能治理（最高价值，先做）

### 3.1 目标

把「每次请求都重算一遍标准化」变成「刷新时算一次、请求时读快照」。

- **主方案：物化副本** —— 照搬仓库既有的 3 个先例（见 F12b），**口径零变化**
- **A2（可选）：改写表达式** —— 把逐行函数改成集合判断，降级为「刷新路径」的优化

### 3.2 涉及的四个逐行结构（库存视图实测）

| # | 结构 | 现状 | loops |
|---|---|---|---|
| ① | `semantic.is_collection_source_identifier(...)` | plpgsql STABLE；内部 `to_regclass` + `EXISTS` 查 `core.collection_source_identifiers`（5 行） | 3855 |
| ② | `semantic.resolve_warehouse_code(...)` | plpgsql STABLE；内部 `to_regclass` + `SELECT ... LIMIT 1` 查 `core.dim_warehouse_name_aliases`（5 行） | 3855 |
| ③ | `Seq Scan on shop_identity_resolution_candidates_v2_mv` | 物化视图 72 行，逐行全扫 | 3855 |
| ④ | `scoped` CTE 重算 | 带 `Sort`/`Unique`/`Limit` 的 CTE，被逐行重新求值 | 3855 |

①② 的单次代价实测：`is_collection_source_identifier` 54.3 ms / 3855 次；
`resolve_warehouse_code` 52.4 ms / 3855 次。

### 3.3 主方案：物化副本（口径零变化）

照搬 `sql/semantic/analytics_atomic_mv.sql` 的既有写法：

```sql
-- sql/semantic/inventory_snapshot_mv.sql
CREATE SCHEMA IF NOT EXISTS semantic;

DO $$
BEGIN
    IF to_regclass('semantic.fact_inventory_snapshot_mv') IS NULL THEN
        EXECUTE 'CREATE MATERIALIZED VIEW semantic.fact_inventory_snapshot_mv
                 AS SELECT * FROM semantic.fact_inventory_snapshot';
    ELSE
        EXECUTE 'REFRESH MATERIALIZED VIEW semantic.fact_inventory_snapshot_mv';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_mv_gran_date
    ON semantic.fact_inventory_snapshot_mv (granularity, metric_date, platform_code);
CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_mv_hash
    ON semantic.fact_inventory_snapshot_mv (platform_code, shop_id, data_hash);
```

**为什么物化副本优于改写表达式**

| | 改写表达式（原 A1） | 物化副本（主方案） |
|---|---|---|
| 读性能 | 197 → 61 ms（还要再处理 ③④） | **毫秒级**（③④ 一并消失：整个计算被搬到刷新时） |
| 口径风险 | 要逐字改写表达式 ⇒ 必须逐字等价验证 | **零**（正文 `SELECT *`，口径一个字不动） |
| 数据新鲜度 | 实时 | 快照 ⇒ 靠刷新队列保证 |
| 改动面 | 1 个视图 + 2 个函数（**要动正本**） | 1 个新资产 + 几处登记（**正本不动**） |
| 仓库先例 | 无 | **3 个**（orders / analytics / products） |

⇒ 物化副本在「口径零变化」这点上明显更安全，性能也更好 ⇒ **选它**。

**必须配套的改动（漏任何一处都会静默出错）**

1. **新增资产** `sql/semantic/inventory_snapshot_mv.sql`（内容见上）
2. **`backend/services/data_pipeline/refresh_registry.py`**（**四处登记，缺一处就静默失配**）
   - `SQL_TARGET_PATHS` 增加
     `"semantic.fact_inventory_snapshot_mv": "sql/semantic/inventory_snapshot_mv.sql"`
   - `PIPELINE_DEPENDENCIES` 增加
     `"semantic.fact_inventory_snapshot_mv": ["semantic.fact_inventory_snapshot"]`
     （正本先刷、副本再刷）
   - `ASSET_PREREQUISITES` 增加
     `"semantic.fact_inventory_snapshot_mv": ["semantic.fact_inventory_snapshot"]`
     （副本的建对象前置 = 正本）
   - 下游依赖改指副本：
     `"mart.inventory_snapshot_history": ["semantic.fact_inventory_snapshot_mv"]`、
     `"mart.inventory_current": ["semantic.fact_inventory_snapshot_mv"]`、
     `"mart.inventory_state": ["semantic.fact_inventory_snapshot_mv"]`
   - ⚠️ **`_base_targets_for_refresh_domain()` 的 inventory 分支**（`refresh_registry.py:448-449`）
     现在只返回 `["semantic.fact_inventory_snapshot"]`
     ⇒ **刷新计划里根本不会出现副本** ⇒ 副本永远不被 REFRESH ⇒ 读的是上一次快照。
     照搬 orders/products 分支的写法（那两个分支的注释原文就是
     「物化副本必须显式列出来……副本不在链上 ⇒ 页面会永远读着一份旧快照」）：
     ```python
     if domain == "inventory":
         return [
             "semantic.fact_inventory_snapshot",
             "semantic.fact_inventory_snapshot_mv",
         ]
     ```
3. **下游视图正文改读物化副本**
   `sql/mart/inventory_snapshot_history.sql` 与 `sql/mart/inventory_current.sql` 的
   `FROM semantic.fact_inventory_snapshot` → `FROM semantic.fact_inventory_snapshot_mv`
   （`mart.inventory_state` 是**表**：资产文件建表 + `InventoryStateRefreshService` upsert，
   不是视图，不改它的正文）
4. ⚠️ **`backend/tasks/refresh_queue_tasks.py:136` 的判据**
   ```python
   # 现在: INVENTORY_FACT_TARGET = "semantic.fact_inventory_snapshot"
   # 改成: 正本或副本，命中任一即算「动了库存事实」
   INVENTORY_FACT_TARGETS = {
       "semantic.fact_inventory_snapshot",
       "semantic.fact_inventory_snapshot_mv",
   }
   ```
   这是「本次刷新有没有动库存事实 ⇒ 状态层要不要跟着重算」的**判据**。
   **漏改 ⇒ 状态层不再被触发刷新 ⇒ 库龄不推进、滞销榜不更新，而且不报错。**
   ⇒ 判据取「**任一命中**」而不是「直接改成副本」：刷新计划里两者都可能出现，
   只认一个 ⇒ 另一种触发方式就会漏。
5. ⚠️ **刷新顺序**：`refresh_queue_tasks.py:387-397` 必须保证
   `物化副本 REFRESH` → `sync_inventory_skus` → `InventoryStateRefreshService.refresh()`
   → `InventoryAgeRefreshService.refresh()`。

**为什么第 4、5 步特别危险**：它们**不报错**。状态层没被刷新时，页面照常显示旧数据，
没有任何告警 ⇒ 只能靠守护测试锁住（见 3.4）。

**刷新基础设施已齐备（F12c）**，不需要新造轮子：
`refresh_runner._refresh_materialized_view()` 已实现「识别 `_mv` 目标 → REFRESH（不跑
资产文件的 DROP CASCADE）→ advisory lock → 超时抬到 10 分钟 → 补索引 → 不存在时回落
跑资产文件自愈」。

### 3.4 验收标准

1. **行数一致**：物化副本行数 == 正本行数（生产 3855）
2. **下游不受影响**：`mart.inventory_snapshot_history` / `mart.inventory_current` /
   `mart.inventory_state` 行数与改前一致（3855 / 1122 / 1232）
3. **性能**：
   - 读物化副本：`EXPLAIN ANALYZE` **≤5 ms**
   - `REFRESH MATERIALIZED VIEW` 耗时 **≤1 秒**（当前全量重算 197 ms）
4. **刷新链路通**（**最关键的一项**）：
   - 造一行新事实 → 触发刷新 → 物化副本能见到 ⇒ 刷新没有断
   - 触发一次库存域刷新 ⇒ `_should_refresh_inventory_layers` 返回 `True`
     ⇒ 状态层确实跟着重算了（**这条专门盯第 4 步的判据**）
5. **守护测试**（扩展既有 `backend/tests/data_pipeline/test_atomic_materialized_views.py`，不新起炉灶）：
   - 把库存这一对加进既有清单 `MATERIALIZED_VIEW_ASSETS`（三元组 `(副本, 正本, 资产文件)`）
     ⇒ 自动继承既有断言：「已登记到 `SQL_TARGET_PATHS`」「`PIPELINE_DEPENDENCIES[副本] == [正本]`」
     「正文必须是 `SELECT * FROM <正本>`」「刷新计划里副本排在消费方之前」
   - 新增：`_base_targets_for_refresh_domain("inventory")` 必须包含副本
   - 新增：判据必须**同时**认正本与副本（任一命中即触发状态层刷新）
   - 新增：所有读 `semantic.fact_inventory_snapshot` 的下游 mart / api 资产都改读 `_mv`
6. **回归**：data_pipeline 全量测试通过；
   `test_inventory_warehouse_identity_ssot.py` / `test_identity_candidates_materialization.py` 通过

### 3.5 风险与回滚

| 风险 | 等级 | 应对 |
|---|---|---|
| **判据漏改** ⇒ 状态层不再刷新，库龄/滞销变陈旧且不报错 | **高** | 守护测试锁住判据「正本+副本都认」；上线后手动验证一次刷新链路 |
| **刷新目标里没有副本** ⇒ 副本永远不 REFRESH，页面读旧快照 | **高** | 守护测试锁住 `_base_targets_for_refresh_domain` 必须含副本；验收第 4 项实测 |
| **刷新顺序断了** ⇒ 状态层读到上一版物化副本 | **高** | 守护测试锁住 `PIPELINE_DEPENDENCIES` 顺序；验收第 4 项实测 |
| 物化副本与正本口径漂移 | 低 | 正文是 `SELECT *` ⇒ 口径**不可能**漂移；反倒是正本改了会跟着变 |
| `REFRESH` 全量重算持锁 | 低 | 3855 行 ≈ 197 ms；refresh_runner 已有 advisory lock 与 10 分钟超时预算 |
| 物化副本占存储 | 低 | 与正本同量级（3855 行），可接受 |
| 采集恢复后陈旧窗口 | 低 | 当前 `ENABLE_COLLECTION=false` ⇒ 此刻陈旧风险为零；采集恢复后由刷新队列覆盖（验收第 4 项覆盖） |

**回滚**：物化副本是**新增**资产 ⇒ 回滚 = 删副本 + 下游改回读正本 + 撤登记。
正本视图一个字没动 ⇒ 回滚不影响口径、不影响数据。

### 3.6 A2（可选）：把「集合函数」改写用在刷新路径上

**为什么降级**：物化副本成立后，**读侧**不再需要改写表达式（读的是快照）。
而**刷新侧**的成本是 197 ms（3855 行全量重算）⇒ 并不痛。

⇒ 原方案里的「集合函数 + `MATERIALIZED` CTE」改写，**收益几乎归零**：
它能省的是 REFRESH 的 197 ms ⇒ 只有当库存数据量涨一个量级、REFRESH 变成秒级时才值得做。

**保留它的唯一理由**：A1 落地后若 REFRESH 变慢，或要推广到
`orders_atomic` / `analytics_atomic` / `products_atomic`（那里有 654 万次 `resolve_alias` 扫描），
这套改写就是「降低刷新成本」的手段。

⚠️ **`resolve_alias` 的推广另立任务**：它的优先级排序逻辑（platform 匹配 > granularity 匹配 >
confidence > source 类型 > id）复制到 SQL 里有「第二份口径」风险 ⇒ 必须先把口径抽成
**视图级 CTE 里的排序表达式**（同一处），再谈提速。

---

## 4. B 部分：SSOT 收敛

### B1 — 删掉域默认去重字段表（死代码），让「模板没配」显式失败

**问题**（F4、F5）：`DEFAULT_DEDUPLICATION_FIELDS` 是第二份「哪些列参与身份」的声明。
27 个维度全部配了模板 ⇒ 它没有任何活路径 ⇒ 但一旦被走到（模板缺失、导入漏配），
就会用标准字段键算出「谁都一样」的 hash ⇒ 静默覆盖。

**改法**

1. 删掉 `backend/services/deduplication_fields_config.py` 里的
   `DEFAULT_DEDUPLICATION_FIELDS` / `SUB_DOMAIN_DEDUPLICATION_FIELDS` 及其回落分支
2. `get_deduplication_fields(...)` 的新语义：
   - `template_fields` 非空 ⇒ 用它（**唯一路径**）
   - `template_fields` 为空 ⇒ **抛错**（`TemplateDefinitionError` 或 `ValueError`），
     错误信息指明「该维度没有配置去重字段，请先配置模板」
3. 同步删除 `scripts/test_dynamic_columns_v4_14_0.py` 里「默认配置回退」那条断言
   （那是 `scripts/` 下的自测脚本，不是 CI 测试）
4. **保留** `append_required_identity_fields` / `append_auto_date_identity_fields`
   （系统身份值不是「第二份声明」，是**强制追加**的口径）

**验收**
- 27 个维度全部能正常入库（跑一遍 dry-run / 回放）
- 把库存模板的 `deduplication_fields` 清空 ⇒ **明确报错**，不是算出同一个 hash
- 守护测试：断言 27 个定义文件的 `deduplication_fields` 均非空

**风险**：低。若某个未纳管的维度依赖域默认，会在运行时暴露（而不是静默算错）—— 这正是想要的行为。

### B2 — 一致性检查从库存维度推广到 27 个维度

**问题**（F6）：「清单 `in_hash` == 去重字段表」在 27 个维度都成立，但**只有库存维度有测试**。

**改法**：把现有库存维度的断言（`test_inventory_snapshot_hash_rebuild.py` 里那条）
抽成通用守护测试：遍历 `templates/definitions/*.json`，
断言「`in_hash=true` 的条目键名集合 == `deduplication_fields` 集合」。

**验收**：27/27 通过；故意改坏一个维度 ⇒ 测试变红。

**风险**：极低。

### B3 — `SYNC_CORE_FIELDS_HASH_ENABLED` 加前置门禁

**问题**（F13）：规格 §6.1 写了「打开前必须先离线回放」，但代码里没人拦。
打开后 hash 的**取值方式**改变 ⇒ 部分行 hash 变 ⇒ 已入库行被当新数据 ⇒ 事实表膨胀
（与 v7.29.3 修的 256 组重复行是同一类病）。

**改法**：`core_fields_hash_enabled()` 在返回 `True` 前检查「本次环境是否做过离线回放」
（用环境变量 `SYNC_CORE_FIELDS_HASH_REPLAY_REF` 指向回放报告文件；文件不存在或过期 ⇒
`logger.error` + 抛错并提示执行 `scripts/replay_core_fields_hash.py`）。

**验收**
- 不设回放引用时打开开关 ⇒ 明确报错并给出命令
- 设了有效回放引用 ⇒ 正常启用
- 守护测试覆盖两条路径

**风险**：低。开关本来就是默认关闭的，加门禁不影响现状。

### B4 — 规格 §3.1 表述修正

**问题**：规格（`docs/superpowers/specs/2026-11-14-template-governance-v2-design.md:39`）
写「`data_hash` = 清单中 `in_hash=true` + 系统身份」，实现是「去重字段表 + 系统身份」，
清单的 `in_hash` **当前不参与 hash 字段集合**（F2）。
⇒ 下一个人照规格改实现 ⇒ 库存 hash 口径当场变 ⇒ 3855 行要重算。

**改法**（只改文档，不改实现）
- §3.1 的表格改成：「`data_hash` | **模板去重字段表** + 系统身份 | 指纹组成」，
  并加注：「清单的 `in_hash` 是**一致性声明**（由 B2 的检查保证与去重字段表逐字相同），
  当前实现以去重字段表为准」
- 补一段说明 F7 的有意分工：`raw_name` 形态管「物理列可缺」，`semantic_key` 形态管「语义键参与去重」

**验收**：文档里查不到「清单决定 hash 字段集合」这种说法。

**风险**：极低。

### B5 — 语义契约 consumer 补登记

**问题**：`core.semantic_field_contracts` 共 70 条，`platform` 全 NULL（通用契约）；
inventory 域只有 6 条，`importance` 全 `optional`，`consumer` 只有 `business_overview`。
而实际消费方有 4 个模块（F3）⇒ 规格说的「清单必填 ∪ 域级契约必填」在库存上
**只有清单这一条腿在撑**。

**改法**
1. **先从代码核出真实 consumer 标识**（不得编）：`business_overview` 之外，
   商品中心 / 滞销清单 / 低库存告警 各自的 consumer 标识以代码为准
2. 补登记这 4 个 consumer × 6 个语义键
3. `importance` 保持 `optional` ⇒ **不改变任何阻断口径**

**验收**：`SELECT DISTINCT consumer FROM core.semantic_field_contracts WHERE data_domain='inventory'`
返回 4 个；治理看板能查到库存的影响面。

**风险**：低（纯数据，可回滚）。

### B6 — 物理列通路：**宣告弃用**（业务已拍板 2026-11-14）

**业务结论**：**没有外部系统直查**（Metabase 是历史遗留、不在活跃运行时；仓库内静态搜索零命中）
⇒ 库存维度**不再建业务物理列**，业务字段只存 `raw_data`（JSONB）。

**事实**（F8、F9）：26 个业务物理列全部 NULL；表头 28 列里 3 列（次品库存/暂存库存/备注）
**没有物理列**，另多出一个重复列 `商品`（与 `商品SKU` 同语义）；
而语义层/状态层/接口**全部走 `raw_data`** ⇒ 那 26 个空列是**一条没人走的通路的遗留物**。

**⚠️ 一个容易搞反的技术点**（此处更正早前的口头口径）：`SYNC_CORE_FIELDS_CORE_COLUMNS_ENABLED`
（`core_fields_service.py:586-607`）是**「收窄」开关，不是「要不要存物理列」开关**：

| 开关值 | 实际行为 |
|---|---|
| 默认（开） | 只为**清单里的核心字段**建物理列（其余只进 `raw_data`） |
| 关 | **旧行为：所有表头列都建列** —— 建得**更多**，不是更少 |

⇒ 「把默认改成关」会让物理列**变多**，方向正好相反。
真正要表达「不存业务物理列」，得让入库侧传**空清单**而不是 `None`：
`core_columns=[]` ⇒ `dynamic_column_manager.ensure_columns_exist()` 里
`core_column_set` 为空集 ⇒ **一列都不建**；而 `None` ⇒ 全建。

**改法**

1. **新增开关** `SYNC_CORE_FIELDS_PHYSICAL_COLUMNS_ENABLED`（默认**关**）：
   - 关 ⇒ 入库侧传 `core_columns=[]` ⇒ 不建任何业务物理列，只写 `raw_data`
   - 开 ⇒ 恢复现状（只为核心字段建列）
   ⇒ 默认值即弃用语义，且保留一键回退
2. **把「存不存列」与「缺列要不要阻断」解耦**：
   - 阻断判定走的是 `template_matcher._required_raw_fields()` →
     `classify_drift(required_core_fields=...)`，它比对的是**上传文件的表头 vs 清单**
     ⇒ 与「库里有没有这列」**本来就没有耦合**。
   - 要做的是**把这个事实锁住**：新增守护测试断言「物理列关掉后，缺必填列仍然阻断」
     ⇒ 防止后人把两件事重新绑在一起。
3. **现存 26 个空列：保留 + 标注废弃，不删列**
   （删列不可逆；留着零成本；`raw_data` 里 3855/3855 行全有值，数据没丢）
4. **文档同步**：`templates/README.md` 与本方案写明「库存维度物理列已废弃，
   业务字段只在 `raw_data` 里」；表头 28 列与物理列的差异（3 列缺失 / 1 列重复）
   记入 §10 存量债，**不在本次修**（改表结构要迁移 + 生产写库，收益为零）。

**验收**

- 开关关 ⇒ 新入库的行**不新增任何业务物理列**（比对 `pg_attribute` 列数不变）
- 开关关 ⇒ 缺必填列**仍然阻断**（守护测试覆盖）
- 开关开 ⇒ 行为与今天**逐字一致**（回归）
- 语义层 / 状态层 / 接口输出**不变**（3855 / 1122 / 1232 行数与内容一致）

**风险**：低。理由：① 无人读这些列；② 数据在 `raw_data` 里没丢；
③ 存量列不删、不改；④ 开关可一键回退。

---

## 5. 明确不做（含理由）

| 不做 | 理由 |
|---|---|
| `scripts/` lint / 格式全量清理 | 实测 `scripts/` 有 410/489 个文件 black 不合规、ruff 138 errors。全量重排会产生巨量 diff，掩盖真实变更、增加冲突风险；CI 本就只卡**改动文件** ⇒ 存量不会恶化。规矩保持：新写/改动文件必须 black-clean（本次两个新脚本已符合） |
| `VERSION` 文件同步 | F14：只是环境变量没注入时的兜底，不影响生产、不影响 CI |
| 命名体系全局统一（原始表头 ↔ 语义键对照表） | V2 大工程（27 维度 × 字段语义判定），预发布期不做。**但要立项**：它才是「清单只能声明语义键 / 只能声明原始名」的根因 |
| 让 `in_hash` 真正决定 hash 字段集合 | 会让 27 个维度的 hash 口径全变 ⇒ 又一次全量重建。**不做**；改为「一致性声明 + B2 检查」 |
| `resolve_alias` 优先级口径搬到 SQL | 会制造第二份口径 ⇒ 违反 SSOT。需先把口径抽成单一表达式，另立任务 |
| **改写语义层视图正文**（集合函数 + `MATERIALIZED` CTE） | 物化副本成立后，④ 类结构已被整段搬出请求路径；改写正本表达式会引入口径风险、收益归零。降级为 A2 可选项（见 §3.6） |
| **删掉现存 26 个空物理列** | 删列不可逆；无人读、零成本、数据在 `raw_data` 里。保留 + 标注废弃即可 |

---

## 6. 执行批次

### 批次 1（性能，最高价值，先做）
1. **A1：库存语义视图物化副本**
   - 新增资产 `sql/semantic/inventory_snapshot_mv.sql`（照搬 `sql/semantic/analytics_atomic_mv.sql`）
   - `refresh_registry.py` **四处登记**：`SQL_TARGET_PATHS` / `PIPELINE_DEPENDENCIES` /
     `ASSET_PREREQUISITES` / `_base_targets_for_refresh_domain` 的 inventory 分支
   - 下游改读副本：`sql/mart/inventory_snapshot_history.sql`、`sql/mart/inventory_current.sql`
   - 判据 `refresh_queue_tasks.py:136` 改成「正本或副本命中任一」
   - 守护测试：把库存这一对加进 `test_atomic_materialized_views.py` 的既有清单 + 3 条新断言
2. **验收**：读副本 ≤5 ms；副本行数 = 3855 = 正本行数；
   下游 3855 / 1122 / 1232 行数不变；**刷新链路实测通**（造数据 → 副本见到 → 判据为真 → 状态层重算）；
   data_pipeline 全量通过
3. **A2（可选，不阻塞）**：刷新路径上的集合函数改写 —— 只在 REFRESH 变慢时才做

### 批次 2（SSOT，不碰生产数据）
1. B1：删域默认 + 显式失败 + 守护测试
2. B2：一致性检查推广到 27 维度
3. B3：hash 开关门禁 + 守护测试
4. B4：规格 §3.1 表述修正
5. **验收**：库存维度「故意清空 dedup ⇒ 明确报错」；27/27 一致性检查通过；开关门禁两条路径都测到

### 批次 3（物理列弃用 + 可查性）
1. **B6**：新增 `SYNC_CORE_FIELDS_PHYSICAL_COLUMNS_ENABLED`（默认关）
   + 「存列 / 阻断」解耦守护测试 + 26 个空列标注废弃（**不删列、不改表结构**）
2. B5：consumer 补登记（先核真实标识）
3. **验收**：开关关 ⇒ 新入库不再新增业务物理列；缺必填列仍阻断；
   治理看板可查库存影响面（4 个 consumer）

### 批次 4（部署与复验）
1. 按发布流程打附注 tag 部署（两端同一 tag 对象，不回填）
2. 生产复验：副本行数 / 下游行数 / 刷新链路 / 守卫 / 业务清单（滞销、库龄、告警）
3. **回滚预案**：批次 1 = 删副本 + 下游改回正本 + 撤登记（**正本一个字没动** ⇒ 不影响口径、不影响数据）；
   批次 3 = 把开关打开即回到今天的行为

---

## 7. 验收总清单

| # | 验收项 | 方法 | 通过标准 |
|---|---|---|---|
| 1 | **副本 = 正本** | 副本与正本全量输出按 `data_hash` 排序比对 | 逐字相同（正文是 `SELECT *` ⇒ 天然成立） |
| 2 | 行数 | 副本 / 正本 / `mart.inventory_snapshot_history` / `mart.inventory_current` / `mart.inventory_state` | 3855 / 3855 / 3855 / 1122 / 1232 |
| 3 | 读性能 | `EXPLAIN ANALYZE` 读副本 | **≤5 ms**（现在 197 ms） |
| 4 | 刷新成本 | `REFRESH MATERIALIZED VIEW` 计时 | ≤1 秒（当前全量重算 197 ms） |
| 5 | **刷新链路通**（最关键） | 造一行新事实 → 触发刷新 → 看副本；再触发一次库存域刷新看判据 | 副本见到新行；判据返回 `True`；状态层跟着重算 |
| 6 | 刷新登记 | 守护测试（扩展 `test_atomic_materialized_views.py`） | 四处登记齐全；副本排在消费方之前；判据认正本 + 副本 |
| 7 | 半迁移库兜底 | 隐藏 `core.collection_source_identifiers` 的环境建视图 | 能建、输出一致（**正本一个字没动 ⇒ 天然成立**） |
| 8 | 域默认已删 | 全仓搜 `DEFAULT_DEDUPLICATION_FIELDS` | 零引用 |
| 9 | 漏配显式失败 | 清空库存模板 dedup 后入库 | 明确报错，非静默 hash |
| 10 | 一致性检查 | 守护测试 | 27/27 通过，改坏即红 |
| 11 | hash 开关门禁 | 守护测试 | 无回放引用 ⇒ 拒绝启用 |
| 12 | 规格一致 | 人工检查 | 无「清单决定 hash 字段集合」表述 |
| 13 | consumer 登记 | SQL 查询 | inventory 域 4 个 consumer |
| 14 | **物理列弃用生效** | 开关关 → 新入库 → 比对 `pg_attribute` 列数 | 列数不增；缺必填列仍阻断；开关开时行为与今天一致 |
| 15 | 全量回归 | `pytest backend/tests` | 无新增失败 |

---

## 8. 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| **副本没被刷新** ⇒ 页面读旧快照，且不报错 | 高 | 守护测试锁住四处登记 + 判据认「正本 + 副本」；上线后实测刷新链路 |
| **状态层不再被触发刷新** ⇒ 库龄不推进、滞销榜陈旧，且不报错 | 高 | 同上；验收第 5 项专门盯这条 |
| 副本与正本口径漂移 | 低 | 正文是 `SELECT *` ⇒ **不可能**漂移；正本改了会跟着变 |
| 副本数据陈旧（采集恢复后） | 低 | 当前 `ENABLE_COLLECTION=false` ⇒ 陈旧窗口为零；采集恢复后由刷新队列覆盖（验收第 5 项覆盖） |
| 删域默认暴露未纳管维度 | 中 | 先跑 27 维度 dry-run；错误信息指明配置路径 |
| hash 开关门禁挡住正常使用 | 低 | 回放引用可用环境变量指向；错误信息给出命令 |
| 物理列弃用后有人真的要读那些列 | 低 | 业务已确认无人直查；存量列不删；开关一键回退 |
| 批次 1~3 不做生产数据变更 | — | 全部是代码/文档/测试级改动 |

---

## 9. 与已有资产的关系

| 已有资产 | 关系 |
|---|---|
| `docs/superpowers/specs/2026-11-14-template-governance-v2-design.md` | 本文是它的**延续与修正**（B4 直接改它的 §3.1 表述） |
| `templates/README.md` | B2/B4 的结论要同步写进「改去重口径 ⇒ 先重建后投影」那一节；B6 的「物理列已废弃」也写进去 |
| `scripts/rebuild_inventory_snapshot_hash.py` | 本方案不动它；B1 删域默认后，它的 `_build_hash_fields` 路径不变（模板字段照常优先） |
| `backend/tests/data_pipeline/test_inventory_snapshot_hash_rebuild.py` | B2 把其中一条断言提升为通用版 |
| `backend/tests/data_pipeline/test_atomic_materialized_views.py` | **A1 直接扩展它**（加一对三元组 + 3 条新断言），不新起炉灶 |
| `sql/semantic/analytics_atomic_mv.sql` | **A1 的照搬模板**（`DO $$ … CREATE/REFRESH … $$` + `CREATE INDEX IF NOT EXISTS`） |
| `sql/semantic/inventory_snapshot.sql` | **正本，一个字不动**（口径零变化的保证） |
| `sql/semantic/inventory_snapshot_mv.sql` | **A1 新增**（正文 = `SELECT * FROM semantic.fact_inventory_snapshot`） |
| `sql/mart/inventory_snapshot_history.sql` / `inventory_current.sql` | A1 的下游，改读副本 |
| `sql/mart/inventory_state.sql` | 表（非视图）：资产文件建表 + `InventoryStateRefreshService` upsert |
| `backend/services/data_pipeline/refresh_registry.py` | A1 的四处登记 + 下游依赖改指副本 |
| `backend/tasks/refresh_queue_tasks.py` | A1 的判据（`:136`）与刷新顺序（`:387-397`） |
| `backend/services/core_fields_service.py` / `data_ingestion_service.py` / `dynamic_column_manager.py` | B6 的落点（新增开关 + `core_columns=[]` 语义） |
| `sql/semantic/shop_identity_resolution_candidates.sql` | 本方案**不动**（A2 可选项才涉及） |
| `sql/semantic/semantic_alias_registry.sql` | `resolve_alias` 推广目标（另立任务，见 §10） |

---

## 10. 附：本次未动的存量债（V2 立项）

| 项 | 实测 | 建议 |
|---|---|---|
| `scripts/` lint / 格式 | 410/489 文件 black 不合规，ruff 138 errors | 维持「只卡改动文件」 |
| `VERSION` 文件 | 停在 v7.28.0 | 划掉 |
| 命名体系统一 | 清单两种形态并存 | **立项**：建「原始表头 ↔ 标准语义键」对照表 |
| `resolve_alias` 优先级口径 | 654 万次扫描 | **立项**：先抽单一表达式，再提速 |
| 物理列通路 | 26 列全 NULL / 3 列缺失 / 1 列重复 | **已拍板弃用**（B6）：关新写入、留存量列、标注废弃；表结构差异（3 列缺失 / 1 列重复）不在本次修 |
