# 模板决策资产 SSOT 收敛 与 语义层标量函数性能治理 —— 优化方案

> 日期：2026-11-14
> 触发：v7.29.3 ~ v7.29.5 上线后，对库存维度「模板更新后仍提示需要更新 + 仍有字段对不上」
> 问题的复盘，顺带审出的一批存量债。
> 状态：待评审。实施顺序见 §9。

---

## 0. 一页摘要

本方案是**一次存量债清理**，不是新功能。分两大部分：

- **A 部分（SSOT 收敛）**：把「同一件事有两个说了算的地方」收敛掉，把「配置一漏就静默出错」的路堵死。
  共 5 个动作，全部**不动生产数据**，代码与文档级改动。
- **B 部分（性能治理）**：语义层原子视图里的**逐行标量函数调用（N+1）**。
  实测库存语义视图读一次 **197 ms**，底层表只要 **4.4 ms** ⇒ **45 倍**浪费。
  这是本轮**最高价值**的一项。

| # | 动作 | 性质 | 预估收益 | 风险 |
|---|---|---|---|---|
| A1 | 语义层视图消除逐行函数调用 | 性能 | 库存视图 197ms → 61ms（①②，已实测）→ ≤15ms（③④） | 中（需逐字等价验证） |
| B1 | 删掉域默认去重字段表（死代码） | SSOT | 堵死「漏配 ⇒ 算出错身份」静默路 | 低 |
| B2 | 清单 `in_hash` == 去重字段表，一致性检查推广到 27 维度 | SSOT | 防两处声明漂移 | 极低 |
| B3 | `SYNC_CORE_FIELDS_HASH_ENABLED` 加前置门禁 | 防呆 | 堵死「一键切口径」 | 低 |
| B4 | 规格 §3.1 表述修正 | 文档 | 防「照规格改实现」⇒ 又一次全量重建 | 极低 |
| B5 | 语义契约 consumer 补登记 | 可查性 | 让「改了字段影响谁」查得到 | 低 |
| B6 | 物理列通路去留（待定） | 待决策 | 少一份数据源 | 中（涉生产数据） |

**明确不做**（理由见 §10）：lint/格式全量清理、`VERSION` 文件同步、命名体系统一。

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
3. **行为不变的优化优先。** 视图改写必须**输出逐字相同**；先证明等价，再谈提速。
4. **预发布期不做大范围重构。** 只做能独立验证、能独立回滚的改动。
5. **保留「半迁移库能建起来」的兜底语义**，直到有替代方案（见 A1 的取舍）。

---

## 3. A 部分：性能治理（最高价值，先做）

### 3.1 目标

消除语义层原子视图里的 **N+1 逐行调用**：把「每行查一次小表」改成「一次算好集合 + 行级内存判断」。

### 3.2 涉及的四个逐行结构（库存视图实测）

| # | 结构 | 现状 | loops |
|---|---|---|---|
| ① | `semantic.is_collection_source_identifier(...)` | plpgsql STABLE；内部 `to_regclass` + `EXISTS` 查 `core.collection_source_identifiers`（5 行） | 3855 |
| ② | `semantic.resolve_warehouse_code(...)` | plpgsql STABLE；内部 `to_regclass` + `SELECT ... LIMIT 1` 查 `core.dim_warehouse_name_aliases`（5 行） | 3855 |
| ③ | `Seq Scan on shop_identity_resolution_candidates_v2_mv` | 物化视图 72 行，逐行全扫 | 3855 |
| ④ | `scoped` CTE 重算 | 带 `Sort`/`Unique`/`Limit` 的 CTE，被逐行重新求值 | 3855 |

①② 的单次代价实测：`is_collection_source_identifier` 54.3 ms / 3855 次；
`resolve_warehouse_code` 52.4 ms / 3855 次。

### 3.3 改法

**A1-①② —— 一次性取集合，行级做内存判断。**

新增两个「返回集合」的函数（沿用现有函数的 `to_regclass` 兜底写法，
保证迁移未跑的环境仍能建视图、行为不变）：

```sql
-- 采集方代号集合（替代逐行 is_collection_source_identifier）
CREATE OR REPLACE FUNCTION semantic.collection_source_identifier_set()
RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF to_regclass('core.collection_source_identifiers') IS NULL THEN
        RETURN ARRAY[]::TEXT[];
    END IF;
    RETURN ARRAY(SELECT csi.identifier FROM core.collection_source_identifiers csi
                  WHERE csi.is_active);
END;
$$;

-- 仓名 -> 仓码 映射（替代逐行 resolve_warehouse_code）
CREATE OR REPLACE FUNCTION semantic.warehouse_code_map()
RETURNS JSONB LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF to_regclass('core.dim_warehouse_name_aliases') IS NULL THEN
        RETURN '{}'::JSONB;
    END IF;
    RETURN COALESCE((
        SELECT jsonb_object_agg(a.source_warehouse_name, a.warehouse_code)
          FROM core.dim_warehouse_name_aliases a), '{}'::JSONB);
END;
$$;
```

视图里改成：

```sql
-- CTE 顶部一次算好
lookup AS (
    SELECT semantic.collection_source_identifier_set() AS csi_ids,
           semantic.warehouse_code_map() AS wh_map
),
...
-- 行级判断（原逐行函数调用 → 内存判断）
WHEN LOWER(COALESCE(...)) = ANY((SELECT csi_ids FROM lookup))
THEN 'unknown'
...
COALESCE(warehouse_code, (SELECT wh_map ->> warehouse_name FROM lookup))
```

**要点**：
- 兜底语义**逐字保留**（表不存在 ⇒ 空集合/空 map ⇒ 行为与现在完全一致）
- 函数体内仍是 plpgsql + `to_regclass`，**不引入动态 SQL**（遵守 SQL 资产约定）
- ⚠️ **CTE 必须写 `MATERIALIZED`** —— Postgres 会把只引用一次的非递归 CTE **内联展开**，
  内联后「一次算好集合」就退化成「每行调一次函数」，等于没改。**实测见下。**

**A1-①② 已实测验证（开发库，3855 行，2026-11-14）**

| 写法 | 耗时 |
|---|---|
| A. 现状：逐行调 `is_collection_source_identifier` | **90.3 ms** |
| B. CTE **不加** `MATERIALIZED`（被内联） | 13.0 ms |
| C. CTE **加** `MATERIALIZED`（只求值一次） | **2.4 ms** |
| D. 现状：逐行调 `resolve_warehouse_code` | **56.8 ms** |
| E. `warehouse_code_map` 一次取 + 内存查 | **8.4 ms** |

- **等价性校验**：逐行判定命中 3855 行 = 集合判定命中 3855 行 ⇒ **逐字一致**
- **集合函数返回值抽查**：
  `collection_source_identifier_set()` = `['xihong','miaoshou_real_001','unknown','none','']`；
  `warehouse_code_map()` = 5 个仓名 → 仓码
- **收益**：两个函数合计 147.1 ms → 10.8 ms ⇒ **省 136 ms**
- ⇒ 库存视图 197 ms → **约 61 ms**（只做 ①②）；做完 ③④ 才有望进 15 ms

⇒ 这也印证了 §3.2 的判断：**MATERIALIZED 是这个改法的成败关键，不是可选项。**

**A1-③④ —— 候选池物化 + scoped CTE 外提。**

- ③：把 `shop_identity_resolution_candidates_v2_mv` 的引用从「逐行标量相关子查询」
  改成「视图顶部一次取候选集合」
- ④：`scoped` CTE 从相关子查询里提到外层，做成一次性物化的候选集合
- ⚠️ 这两项触及身份候选池的口径 ⇒ **必须单独一批**，且要有逐字等价测试

**A2 —— 索引补齐（便宜的先做）**

| 表 | 现状 | 建议 |
|---|---|---|
| `core.collection_source_identifiers` | 只有 `identifier` 唯一索引 | 加 `(is_active, identifier)` 或确认 pkey 足够 |
| `core.dim_warehouse_name_aliases` | `source_warehouse_name` 唯一索引 ✓ | 无需加 |
| `semantic.semantic_field_aliases` | `(data_domain, standard_field, status)` ✓ | `resolve_alias` 还按 platform/granularity 过滤 ⇒ 评估补 `(data_domain, standard_field, status, platform_code, granularity)` |

### 3.4 验收标准

1. **逐字等价**：改写前后，语义层视图的**全量输出**（所有列、所有行、按 `data_hash` 排序）
   必须逐字节相同 ⇒ 用一条比对 SQL 做守护测试
2. **性能**（分两档，因为 ①② 与 ③④ 是两步）：
   - 只做 ①②（批次 1a）：库存视图 `count(*)` 从 197 ms 降到 **≤70 ms**
   - 做完 ③④（批次 1b）：降到 **≤15 ms**
3. **兜底不变**：在「`core.collection_source_identifiers` 不存在」的库上，视图仍能建起来，
   且输出与改写前一致
4. **回归**：data_pipeline 全量测试通过；`backend/tests/data_pipeline/test_inventory_warehouse_identity_ssot.py`
   与 `test_identity_candidates_materialization.py` 通过

### 3.5 风险与回滚

| 风险 | 应对 |
|---|---|
| 改写后输出与原来不一致（静默） | **逐字等价测试是硬门禁**，不通过就不合 |
| 集合语义与逐行语义有细微差别（如 NULL、大小写、空白） | 改写时**逐字复用现有表达式**；空值/空白/大小写各有专门断言 |
| 候选池口径改动影响身份判定 | ③④ 单独一批，先只做性能不改口径；口径改动另立任务 |

**回滚**：视图是 `CREATE OR REPLACE` 资产 ⇒ 回滚 = 还原 SQL 文件 + 重新执行资产。
无数据变更、无 schema 变更 ⇒ 回滚零风险。

### 3.6 推广路径

库存视图是试点（最简单、已有 13 项清单、有明确对照）。
①②③④ 的改法可复用到 `orders_atomic` / `analytics_atomic` / `products_atomic`
（`resolve_alias` 的 654 万次扫描在那一侧，见 F12）。

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

### B6 — 物理列通路的去留（**待决策，不在本次范围**）

**问题**（F8、F9）：26 个业务物理列全 NULL；3 个表头列没有物理列；1 个重复列 `商品`；
而**没有任何代码或 SQL 读这些列**。数据都在 `raw_data` 里，语义层/状态层/接口全部走 `raw_data`。

**两条出路**

| 方案 | 动作 | 代价 | 适合什么时候 |
|---|---|---|---|
| **甲：宣告弃用** | 库存维度不再建业务物理列；把 `core_fields` 的 `raw_name` 声明改成「仅声明需求、不落列」；现存 26 个空列标注为历史遗留 | 极低（文档 + 一处开关） | 确认没有外部系统在直查这些列 |
| **乙：保留并回填** | 用应用自身 `resolve_target_column` 算列名，把 `raw_data` 的 13 项值回填进物理列；补 3 个缺失列；清掉重复的 `商品` 列 | 中（新脚本 + 生产写库 + 备份） | 确认有 BI/外部系统在直查 |

**决策所需事实**：有没有外部系统（BI、ERP 对接、Excel 导出）直查
`b_class.fact_miaoshou_inventory_snapshot` 的业务列？
⇒ AGENTS.md 说 Metabase 是历史遗留、不在活跃运行时 ⇒ 仓库内已确认为「无」。
⇒ **但仓库外（运营手工导数、外部 BI）查不到 ⇒ 这一条需要业务确认。**

**如果选甲**，还需配套：
- 核心字段清单的 `raw_name` 语义要重新定义（当前它同时驱动「落列」和「阻断」）
- `core_field_storage_column_names()` 的调用方要能区分「落列」与「不落列」

⇒ **建议：先只做诊断（产出一份「谁在读这些列」的清单，含仓库内 + 部署后的访问统计），
再在甲/乙之间拍。** 本方案不预设结论。

---

## 5. 明确不做（含理由）

| 不做 | 理由 |
|---|---|
| `scripts/` lint / 格式全量清理 | 实测 `scripts/` 有 410/489 个文件 black 不合规、ruff 138 errors。全量重排会产生巨量 diff，掩盖真实变更、增加冲突风险；CI 本就只卡**改动文件** ⇒ 存量不会恶化。规矩保持：新写/改动文件必须 black-clean（本次两个新脚本已符合） |
| `VERSION` 文件同步 | F14：只是环境变量没注入时的兜底，不影响生产、不影响 CI |
| 命名体系全局统一（原始表头 ↔ 语义键对照表） | V2 大工程（27 维度 × 字段语义判定），预发布期不做。**但要立项**：它才是「清单只能声明语义键 / 只能声明原始名」的根因 |
| 让 `in_hash` 真正决定 hash 字段集合 | 会让 27 个维度的 hash 口径全变 ⇒ 又一次全量重建。**不做**；改为「一致性声明 + B2 检查」 |
| `resolve_alias` 优先级口径搬到 SQL | 会制造第二份口径 ⇒ 违反 SSOT。需先把口径抽成单一表达式，另立任务 |

---

## 6. 执行批次

### 批次 1a（性能，最高价值，先做）
1. A1-①②：两个「集合函数」 + 库存语义层视图改写（**CTE 必须 `MATERIALIZED`**）+ 逐字等价守护测试
2. A2：索引补齐评估与实施
3. **验收**：库存视图 197ms → ≤70ms；视图输出逐字相同；data_pipeline 全量通过

### 批次 1b（性能续做）
1. A1-③④：候选池物化 + `scoped` CTE 外提（口径不动）
2. **验收**：库存视图 → ≤15ms；身份候选池相关守护测试全过

### 批次 2（SSOT，不碰生产数据）
1. B1：删域默认 + 显式失败 + 守护测试
2. B2：一致性检查推广到 27 维度
3. B3：hash 开关门禁 + 守护测试
4. B4：规格 §3.1 表述修正
5. **验收**：库存维度「故意清空 dedup ⇒ 明确报错」；27/27 一致性检查通过；开关门禁两条路径都测到

### 批次 3（可查性 + 决策材料）
1. B5：consumer 补登记（先核真实标识）
2. B6 诊断：产出一份「谁在读业务物理列」的清单（仓库内静态搜索 + 生产访问统计 + 待业务确认项）
3. **验收**：治理看板可查库存影响面；B6 决策材料齐备

### 批次 4（决策后执行）
按 B6 的甲/乙结论执行；涉及生产写库的按「只读预演 → 备份 → 执行 → 逐项核对 → 守卫复验」走。

---

## 7. 验收总清单

| # | 验收项 | 方法 | 通过标准 |
|---|---|---|---|
| 1 | 视图输出等价 | 改写前后全量输出按 `data_hash` 排序比对 | 逐字节相同 |
| 2 | 性能 | `EXPLAIN ANALYZE` | 批次 1a ≤70ms；批次 1b ≤15ms |
| 2b | 集合判定等价 | 逐行判定 vs 集合判定命中数比对 | 3855 = 3855（已实测通过） |
| 2c | CTE 未被内联 | `EXPLAIN` 中 CTE 节点 `loops=1` | 必须为 1 |
| 3 | 半迁移库兜底 | 隐藏 `core.collection_source_identifiers` 的环境建视图 | 能建、输出一致 |
| 4 | 域默认已删 | 全仓搜 `DEFAULT_DEDUPLICATION_FIELDS` | 零引用 |
| 5 | 漏配显式失败 | 清空库存模板 dedup 后入库 | 明确报错，非静默 hash |
| 6 | 一致性检查 | 守护测试 | 27/27 通过，改坏即红 |
| 7 | 开关门禁 | 守护测试 | 无回放引用 ⇒ 拒绝启用 |
| 8 | 规格一致 | 人工检查 | 无「清单决定 hash 字段集合」表述 |
| 9 | consumer 登记 | SQL 查询 | inventory 域 4 个 consumer |
| 10 | 全量回归 | `pytest backend/tests` | 无新增失败 |

---

## 8. 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| 视图改写引入静默口径偏差 | 高 | 逐字等价测试作硬门禁；不通过不合 |
| 候选池口径改动影响身份判定 | 中 | ③④ 单独批次，先只做性能 |
| 删域默认暴露未纳管维度 | 中 | 先跑 27 维度 dry-run；错误信息指明配置路径 |
| 开关门禁挡住正常使用 | 低 | 回放引用可用环境变量指向；错误信息给出命令 |
| 批次 1~3 不做生产数据变更 | — | 全部是代码/文档/测试级改动 |

---

## 9. 与已有资产的关系

| 已有资产 | 关系 |
|---|---|
| `docs/superpowers/specs/2026-11-14-template-governance-v2-design.md` | 本文是它的**延续与修正**（B4 直接改它的 §3.1 表述） |
| `templates/README.md` | B2/B4 的结论要同步写进「改去重口径 ⇒ 先重建后投影」那一节 |
| `scripts/rebuild_inventory_snapshot_hash.py` | 本方案不动它；B1 删域默认后，它的 `_build_hash_fields` 路径不变（模板字段照常优先） |
| `backend/tests/data_pipeline/test_inventory_snapshot_hash_rebuild.py` | B2 把其中一条断言提升为通用版 |
| `sql/semantic/inventory_snapshot.sql` | A1-①② 的改写目标 |
| `sql/semantic/shop_identity_resolution_candidates.sql` | A1-③④ 的改写目标（口径不动） |
| `sql/semantic/semantic_alias_registry.sql` | A1-②③ 的推广目标（另立任务） |

---

## 10. 附：本次未动的存量债（V2 立项）

| 项 | 实测 | 建议 |
|---|---|---|
| `scripts/` lint / 格式 | 410/489 文件 black 不合规，ruff 138 errors | 维持「只卡改动文件」 |
| `VERSION` 文件 | 停在 v7.28.0 | 划掉 |
| 命名体系统一 | 清单两种形态并存 | **立项**：建「原始表头 ↔ 标准语义键」对照表 |
| `resolve_alias` 优先级口径 | 654 万次扫描 | **立项**：先抽单一表达式，再提速 |
| 物理列通路 | 26 列全 NULL / 3 列缺失 / 1 列重复 | 决策后执行（B6） |
