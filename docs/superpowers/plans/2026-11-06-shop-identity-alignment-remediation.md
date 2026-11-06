# 店铺身份未对齐问题单 · 复核与优化方案

- 日期：2026-11-06
- 状态：**复核完成，待业务确认 P1/P3 口径项后进入实施**
- 范围：`modules/apps/collection_center/executor_v2.py`、`backend/services/platform_shop_discovery_service.py`、`backend/services/shop_rename_service.py`、`sql/semantic/*`、`core.shop_accounts` / `core.shop_account_aliases` / `b_class.fact_*_analytics_monthly`
- 复核方式：代码走查 + **live 开发库实测**（本地 `xihong_erp_postgres` 容器，库 `xihong_erp`）

---

## 0. 复核口径与环境

| 项目 | 值 |
|---|---|
| 代码基线 | `main` @ `d2d4e05f` |
| 实测库 | 容器 `xihong_erp_postgres`（postgres:15-alpine），库 `xihong_erp` |
| 语义层对象 | `semantic.fact_analytics_monthly_atomic_mv`（3634 行）、`semantic.fact_orders_monthly_atomic`（34085 行）、`semantic.shop_identity_resolution_candidates`（138 行） |
| 原始层对象 | `b_class.fact_shopee_analytics_monthly`（2278 行）、`b_class.fact_tiktok_analytics_monthly`（1356 行）、`b_class.fact_shopee_orders_monthly`（28973 行） |
| 账号主数据 | `core.shop_accounts`（shopee 44 / tiktok 6）、`core.shop_account_aliases`（23 行）、`core.platform_shop_discoveries`（26 行） |

> **口径对齐说明**：问题单的「开发库」与本机 live 库不是同一快照（问题单：209 条 discoveries / 22 条告警；本机：26 条 discoveries / 2026-10 告警 1 条）。下文所有数字均来自本机 live 实测，**结论按「机制是否成立」判断，不按「数字是否相同」判断**。

### 0.1 贯穿全案的一条原则：**`shop_account_id` 是唯一正确的锚点**

| 锚点 | 会不会变 | 跨平台一致 | 会不会被污染 | 结论 |
|---|---|---|---|---|
| **`shop_account_id`**（账号主键） | **改名不变** | 是 | 不会 | **唯一正确锚点**（spec D14「稳定身份编号落库」的立意；`data_hash` 作用域已切到 `scope:shop_account_id`） |
| `platform_shop_id`（平台店铺编号） | 平台换 ID 就变 | 否 | **会被采集器污染**（缺陷 1） | 不可单独作为权威 |
| 店名 / 别名 | 改名就变 | 否 | 会被改错 | 只能兜底 |
| URL 参数 | 随时变 | 否 | 读到的是"上一家店" | 只能当"确认"，不能当"权威" |

**这个原则直接决定了三件事：**
1. **采集链路**（缺陷 1）：URL 读到的值只能用来**跟目标账号对账**，不能反过来定义目标账号 → P0-1；
2. **事实层**：每行数据都必须盖上 `shop_account_id` 戳 → P0-2b（补历史）+ P2-1（变门禁）；
3. **语义层**：`shop_account_id` 必须是**最高优先级**的候选锚点 → P1-1。

> 实测佐证：主路径（本地采集，2026-06-26 起）**已经在 100% 执行这条原则**；洞只在 2026-06-09 那批历史导入（2195 行分析数据）和云同步路径（13106 行订单）——**不是设计缺失，是执行没铺满**。

### 0.2 范围收窄（2026-11-06 追加）：**只保未来，历史数据不管**

业务决定：本环境是**开发环境**，历史数据不修，**只保证后续采集的数据不再出问题**。

| 原任务 | 处置 | 理由 |
|---|---|---|
| P0-2 原始层身份回填（46 + 1116 行） | ❌ **移出范围** | 纯历史数据修正 |
| P0-2b 补 `shop_account_id` 戳（2195 行） | ❌ **移出范围** | 纯历史数据修正 |
| P0-3 清自别名 + 补 6 条 `former_name` 别名 | ❌ **移出范围** | 改名联动**已经实现**（batch2 Task 16：`update_shop_account` → `apply_store_name_rename` → 写 `former_name` 别名），将来改名会自动留底，不需要额外做事 |
| **P0-1 采集守卫** | ✅ **保留，升为第一位** | 这是「未来数据出问题」的**唯一根源**：一次污染，该账号后续所有采集都错位，还会写进新文件 |
| **P2-1 入库硬门禁** | ✅ **保留** | 这是「未来数据不再依赖店名」的保证 |
| **P1-1 锚点优先级倒置** | ✅ **保留** | 让最稳的锚点说了算 |
| **P1-2 停用账号口径** | ✅ **保留**（**已改判为「补漏抄的过滤」，不再需要业务拍板**） | 全系统只有候选池漏了 `enabled` / `business_role` 过滤；代价 8 UV，可忽略 |
| **P2-2 ~ P2-4 监控与守护测试** | ✅ **保留** | 让问题下次自己冒出来，而不是等人查 |

**下文 §2 ~ §6 的分析保留为证据基础**（用于判断"机制是否成立"），但其中的**历史数据修复动作已按上表移出范围**。

### 0.3 「只保未来」要额外盯的两件事（收窄范围后新发现的）

#### ① 下一次采集，`b_class.shop_id` 的语义会自动变（方向是好的，但要守住）

`backend/services/data_ingestion_service.py:123-130` 的 `resolve_file_identity` 优先级是 **`shop_account_id` > `platform_shop_id` > `shop_id`**，而 `catalog_files.shop_account_id` 已在 v7.12.6 补齐（实测 **473/474** 已填，最近的 shopee analytics 文件如 id=3036 `shopee_sg_eternalbloom_local` 已带值）。

⇒ **下一次 shopee analytics 采集入库时，`b_class.shop_id` 会从「平台店铺编号」变成「账号 ID」**（因为 shopee 的导出文件没有店铺列，行内 `shop_id` 只能由文件级身份回填）。

实测过消费方，**不会破坏看板**：只有 `sql/semantic/analytics_atomic.sql` 与 `sql/semantic/analytics_monthly_atomic_mv.sql` 读 `b_class.<fact>.shop_id`，且**只当身份候选**；MV 输出的 `shop_id` 始终是规范平台编号（`COALESCE(canonical.platform_shop_id, resolved.resolved_shop_id)`）。

**要做的是**：加一条测试断言「新建文件的 `b_class.shop_id` == `shop_account_id`」，并把 `raw_shop_id` 这个诊断列的含义写清楚（它会从"平台编号"变成"账号 ID"）。

#### ② 锚点优先级倒置会连带 `dim_shops`，**必须同步改**

`backend/services/shop_sync_service.py:49` 的 `resolve_dim_shop_id` 的 docstring 写着：

> **必须与语义层逐字一致** —— 语义层的身份解析用的是：`resolved_shop_id = COALESCE(platform_shop_id, shop_account_id, id::text)`。派生不一致 ⇒ 看板显示名的 JOIN 永远落空 ⇒ 维度表等于没有。

且 `backend/tests/test_dim_shops_alignment.py:74-85` 明确断言 `platform_shop_id > shop_account_id > id`。

⇒ **P1-1 倒置优先级时，必须连带改 `resolve_dim_shop_id` + 对应迁移 `current_migrations/versions/20261107_align_dim_shops_with_shop_accounts.py`**，否则看板显示名 JOIN 会落空。
另：`sql/semantic/shop_identity_resolution_candidates.sql`（正本）与 `sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`（物化副本）**两份必须同步改**（有内容指纹守护测试 + 迁移 `20261105` 的指纹比对）。

---

## 1. 结论速览

| # | 问题单的缺陷 | 复核结论 | 关键依据 |
|---|---|---|---|
| 缺陷 1 | 采集器把「读到的 URL」当成账号主数据，直接覆盖 `platform_shop_id` | ✅ **成立，是主因** | discoveries 里留有实测指纹：`hx_home.sg` 探测到 `1292370001`（其实是 eternalbloom 的 ID）、`zewei_toys.sg` 探测到 `1227491331`（其实是 chenewei666 的 ID）——读到的确实是「上一家店」 |
| 缺陷 2 | 语义层「候选计数」与「归属选取」两套口径 | ⚠️ **现象成立，但问题单的修法会造成静默错配，建议改成「修数据 + 收紧候选池」，不要改计数口径** | 本机 live 实测**双认领 = 0**；且把计数改成「按优先级分层」会把 18 行歧义行判成唯一，然后选中**被污染的** `platform_shop_id` → 把 xhkj11.sg 的流量归给 xhkj11.ph |
| 缺陷 3 | analytics 链路缺区域消歧 | ❌ **不成立，且与仓库既有设计决策 + 守护测试直接冲突** | `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py:103` 有反向守护测试 `test_analytics_assets_do_not_get_region_column`，断言两条 analytics 路径**不得**出现区域列；2026-11-01 设计规格 §2.5 明确「区域感知匹配只对有站点信息的 orders 两条路径生效」 |
| — | 问题单**未提及** | 🔴 **真正的 unknown 大头：TikTok 改名后没有曾用名别名** | live 实测 unknown 共 738 行 / 117,173 UV，其中 **720 行 / 108,764 UV（93%）是 `unmatched_shop_label`（候选数 = 0）**，根因是别名表里 `former_name` 一条都没有 |

**一句话结论**：问题单方向对了一半 —— 缺陷 1 是真的主因，但**按它的三个缺陷去改，最多只能覆盖 7% 的 unknown**；另外 93% 来自「改名没有留曾用名别名」，与采集器、与语义层口径都无关。

---

## 2. 缺陷 1 复核：成立，是主因（但问题单漏了 2 个入口、1 条数据后果）

### 2.1 代码层：确认存在，且比问题单描述的更广

**入口 A —— 采集运行时探测（问题单已指出）**

`modules/apps/collection_center/executor_v2.py:157-179` 的 `_extract_platform_shop_context` 只从 `page.url` 的 query 里抠 `cnsc_shop_id` / `shop_id`；三个调用点（`:1161` 顺序路径登录后、`:3364` 并行路径登录后、`:6090` 主账号登录后）都在**切店组件还没跑**的位置取 URL。

`backend/services/platform_shop_discovery_service.py:138-146` 的 `record_runtime_discovery` 无条件覆盖主数据：

```python
if shop_account is not None:
    previous_platform_shop_id = shop_account.platform_shop_id
    shop_account.platform_shop_id = detected_platform_shop_id      # ← 无归属校验
    shop_account.platform_shop_id_status = "auto_bound"
    await retain_previous_platform_shop_id_as_alias(db, shop_account, previous_platform_shop_id)
```

对比**人工改号路径** `backend/domains/collection/routers/shop_accounts.py:225-251` 的 `_assert_platform_shop_id_unique` —— 人工路径有唯一性校验（409），采集路径**没有**。这是不对称的。

**入口 B —— 问题单漏掉的第 4 个改主数据的入口**

`platform_shop_discovery_service.py:207-223` 的 `record_manual_discovery` 的 `auto_bound` 分支，同样直接 `shop_account.platform_shop_id = detected_platform_shop_id`，同样没有归属校验。

**入口 C —— 问题单漏掉的第 5 个入口**

`platform_shop_discovery_service.py:275-282` 的 `confirm_discovery`，同样直接覆盖。

> 现有守护测试 `backend/tests/test_shop_platform_id_rebind_alias.py:227-246` 只断言「三个入口都留了旧值别名」，**没有一条断言「不得覆盖别人的 ID」**。这就是这个洞能活这么久的原因。

### 2.2 live 证据：发现表里就是指纹

`core.platform_shop_discoveries` 实测（按时间倒序）：

| id | detected_store_name | detected_platform_shop_id | 该 ID 的真实归属 | created_at |
|---|---|---|---|---|
| 70 | hx_home.sg | `1292370001` | **shopee_sg_eternalbloom_local** | 2026-11-05 12:08:39 |
| 69 | eternalbloom.sg | `1319440256` | 不属于任何账号 | 2026-11-05 12:07:42 |
| 66 | eternalbloom.sg | `1292370001` | shopee_sg_eternalbloom_local（自己） | 2026-11-03 12:56:57 |
| 65 | eternalbloom.sg | `1592747015` | 不属于任何账号 | 2026-11-02 12:22:35 |
| 23 | zewei_toys.sg | `1202833705` | 不属于任何账号 | 2026-06-09 05:37:11 |
| 22/21/20/19 | zewei_toys.sg | `1227491331` | **shopee_sg_chenewei666_local** | 2026-06-07 ~ 06-08 |

`hx_home.sg` 探测到 eternalbloom 的 ID、`zewei_toys.sg` 探测到 chenewei666 的 ID —— **「整体错位一位」的机制在 live 数据里逐条对得上**。

### 2.3 缺陷 1 已经污染了原始层（问题单只提到主数据，没提到这一层）

`b_class.fact_shopee_analytics_monthly` 实测，`shop_id` 列与 `raw_data->>'shop_account_id'` 不一致的批次：

| b_class.shop_id | 该 ID 的真实归属 | raw_data 里的真实账号 | 行数 | 时间 |
|---|---|---|---|---|
| `1419169771` | shopee_ph_xhkj11_local | **shopee_sg_xhkj11_local** | 9 | 2026-07-03 05:15:11 |
| `1540271739` | shopee_my_xhkj1_local | **shopee_ph_xh_home_local** | 9 | 2026-07-03 05:15:04 |
| `1638198770` | 不属于任何账号 | shopee_my_xhkj12_local | 28 | 2026-06-29 09:15:03 |

这 **46 行**就是缺陷 1 从采集侧漏进事实层的全部痕迹。其中 18 行（9+9）因为污染值恰好撞上了另一个账号的 `platform_shop_id`，在语义层被判成歧义 → `unknown`（8,409 UV）。

> **好消息**：原始行**自带正确身份**（`raw_data->>'shop_account_id'`、`raw_data->>'store_name'` 都在），`file_id` 为空也无所谓 —— **不需要重采，纯 SQL 回填即可修复**。

### 2.4 还发现一处「部分修复」留下的自别名

`core.shop_account_aliases` 里两条 `former_platform_shop_id` 别名：

| 拥有者 | alias_value | 自己的 platform_shop_id | alias created_at |
|---|---|---|---|
| shopee_sg_eternalbloom_local | `1292370001` | `1292370001` | 2026-11-05 12:07:42 |
| shopee_sg_hx_home_local | `1391124228` | `1391124228` | 2026-11-05 12:08:39 |

两条别名的创建时间**精确等于** discoveries id=69 / id=70 的时间戳 —— 这就是缺陷 1 在 live 上真实触发过的铁证。之后的 13:23:30 有人把两个账号的 `platform_shop_id` 改回了正确值，但**没删掉这两条自动生成的别名**，于是留下「自别名」（别名值 == 自己的当前 ID）。

自别名**不会**造成歧义（同一个账号 `count(DISTINCT resolved_shop_id)` 仍是 1），但它：
- 污染候选集（每个多一条 priority-3 行）；
- 是「采集链路确实改过主数据」的数据指纹；
- 与问题单里「删掉 9 个错的 former 别名」是**同一件事**，只是数量不同（本机 2 条、且都是自别名）。

---

## 3. 缺陷 2 复核：现象成立，但问题单的修法会造成**静默错配**

### 3.1 两套口径的确切位置

`sql/semantic/analytics_monthly_atomic_mv.sql:394-427` 同一个 `LEFT JOIN LATERAL` 里：

- **计数子查询 `agg`（:403-411）**：`count(DISTINCT c.resolved_shop_id)`，对**所有优先级**的候选行去重计数；
- **归属子查询 `best`（:412-424）**：`DISTINCT ON (resolved_shop_id) … ORDER BY resolution_priority` 取最优，**再**在外层 `LIMIT 1`。

两者不是同一口径 —— 问题单描述属实。

### 3.2 为什么「按优先级分层计数」是危险的（这一点必须纠正）

设候选值 `V1` 被账号 A 以 priority 1 认领（`V1` 其实是 A 被污染后的 `platform_shop_id`），`V2` 被账号 B 以 priority 2/4 认领（`V2` 是 `shop_account_id` / 店名，**是这批数据真正的主人**）。

- 现状：`count(DISTINCT resolved_shop_id)` = 2 → 判歧义 → `unknown` → **报错但不含错**；
- 按问题单修法（计数只数「胜出那一档优先级」）：最高档是 priority 1，只有 A → count = 1 → `best` 取 A → **把 B 的流量悄悄归给 A**。

这就是 `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py:29-43` 那条守护测试注释里写的：

> 「而 `count(*) OVER ()` 在无 GROUP BY 时恒为 1 → 所有多候选都会被判成 1 个 → 永远不落 `ambiguous_shop_label` → **正是 D13/A6 要防的静默错配**。」

**本仓库的既定原则是：歧义宁可落 `unknown` 报警，也不猜。** 所以缺陷 2 的修法不能是「让计数跟 best 对齐」，而应是「**消除不该有的歧义源**（修数据 + 收紧候选池）」。

### 3.3 live 实测：当前**双认领 = 0**

```
SELECT identity_value_normalized, count(DISTINCT resolved_shop_id)
FROM semantic.shop_identity_resolution_candidates GROUP BY 1 HAVING count(DISTINCT resolved_shop_id) > 1;
→ (0 rows)
```

问题单列的 9 个双认领 ID（`1308200825 / 1308200830 / 1391124228 / 1419165604 / 1419165607 / 1419169771 / 1540271739 / 1540271741 / 1540271744`）在本机 live 上**已经不存在**。它们对应的账号当前 `platform_shop_id` 与 `backend/services/shopee_shop_id_resolver.py` 的硬编码基准表 **11/11 完全一致**（另 3 个账号 `xhkj12.my=1540271741`、`xh_home.ph=1419165604`、`xhkj11.sg=1308200825` 不在基准表里，但各自唯一、无冲突）。

⇒ **结论：问题单里「9 个双认领」是修复前的快照状态，当前 live 上这一项验收标准已经天然满足，不需要靠改 SQL 达成。**

### 3.4 真正还活着的口径缺陷（问题单没提）：候选池**不按 `enabled` 过滤**

`sql/semantic/shop_identity_resolution_candidates.sql:7-22` 的 CTE 叫 `active_shop_accounts`，但 `FROM core.shop_accounts sa` **没有 `WHERE enabled`**（v2 物化副本 `shop_identity_resolution_candidates_v2_mv.sql:81-96` 同样没有）。

live 实测：

```
候选行 138 条 → 来自 enabled 账号 69 条 / 来自 disabled 账号 69 条（50%）
```

后果实测 —— 有流量被归到了**已停用**的账号上：

| 被归属账号 | enabled | 流量行数 | UV |
|---|---|---|---|
| shopee_sg_eternalbloom_local | **f** | 152 | 7 |
| shopee_sg_chenewei666_local | **f** | 61 | 1 |

共 **213 行流量挂在已停用店铺上**。

> ⚠️ 这一项**不是显然的 bug**：「停用」= 不再采集，**不等于**「历史要抹掉」。所以它是一个**口径决策项**（见 §7 的 P1-2），需要业务拍板，不能由开发单方面改成「只认 enabled 账号」。

### 3.5 建议保留的口径收紧（低风险、可验证）

在不改变「歧义 ⇒ unknown」这一原则的前提下，把**假歧义源**掐掉：

1. 候选池只收 `enabled = true` 的账号（**待业务确认**，见 P1-2）；
2. `alias_match` 分支排除「别名值 == 该账号自己的 `platform_shop_id`」的自别名（§2.4 的两条）；
3. `alias_match` 分支排除「别名值 == 别的账号的 `platform_shop_id`」的跨账号认领（真冲突，应在数据层解决，不该靠计数口径兜）。

> 这三条**都不改变 `count(DISTINCT c.resolved_shop_id)` 的写法**，因此 `test_all_semantic_paths_use_candidate_view_and_pure_aggregate_count` 的守护断言不受影响。

---

## 4. 缺陷 3 复核：**不成立** —— 与既有设计决策和守护测试直接冲突

### 4.1 仓库有反向守护测试

`backend/tests/data_pipeline/test_shop_identity_resolution_sql.py:103-123`：

```python
def test_analytics_assets_do_not_get_region_column():
    """反向护栏：两条 analytics 路径**不得**出现区域列。
    它们没有站点来源（raw 里 `站点` / `店铺` 都是 0 行），
    加了只会是永远 NULL 的列，还会让"区域感知匹配"的适用范围变得含糊。"""
    assert not re.search(r"AS\s+source_region\b", text, re.I)
    assert not re.search(r"WHEN\s+'[^']+'\s+THEN\s+'[A-Z]{2}'", text)
```

### 4.2 设计规格已明确划界

`docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md` §2.5：

> 「**区域感知匹配（D10b）只对有站点信息的 orders 两条路径生效** —— analytics 两条路径的 raw 里既没有站点也没有店铺标签，它们靠 `shop_account_id`（稳定锚点）匹配，不会出现同名品牌歧义。」

第二批 Task 17 因此**只**改 orders 两条路径。

### 4.3 live 数据复核：analytics 的身份锚点确实不是站点

- `b_class.fact_tiktok_analytics_monthly` 的 `shop_id` 列装的是**店名标签**（`DAWIE Mall` / `Malaysia(Flora Mall)` / …），**不是平台店铺 ID**；
- 1356 行里 **636 行带 `shop_account_id` 戳**（45%），其余只有店名标签；
- shopee 侧 2278 行里 `raw_data->>'店铺'` **0 行有值**，身份全靠 `shop_id` 列与 `raw_data->>'shop_account_id'`。

⇒ analytics 的身份锚点是 **`shop_account_id` + 店名**，不是站点。按问题单加区域消歧，不但解决不了 unknown，还会打破守护测试、引入一个永远是 NULL 的列。

### 4.4 结论

**缺陷 3 不作为缺陷处理。** 它描述的是一条**已知的、被测量支撑的设计边界**。如果业务确实需要 analytics 参与跨区同名消歧，正确路径是**先让 analytics 的 raw 里有站点/区域信号**（改采集导出），再按 D10b 的方式接入候选集 —— 那是独立需求，不是这次的缺陷修复。

---

## 5. 问题单漏掉的真正大头（占 unknown 的 93%）

### 5.1 live 实测的 unknown 分布

`semantic.fact_analytics_monthly_atomic_mv`：

| 平台 | 告警码 | 行数 | UV | 占全量 UV |
|---|---|---|---|---|
| tiktok | `unmatched_shop_label`（**候选数 = 0**） | **720** | **108,764** | **16.2%** |
| shopee | `ambiguous_shop_label`（候选数 = 2） | 18 | 8,409 | 1.2% |
| — | 合计 unknown | 738 | 117,173 | **17.4%** |
| — | 正常归属 | 2,896 | 556,324 | 82.6% |

### 5.2 TikTok 720 行的根因：改名后没有留曾用名别名

`core.shop_account_aliases` 的 alias_type 分布实测：

| alias_type | 行数 | 样例 |
|---|---|---|
| `claimed` | 19 | `TK新加坡1店` / `马来1店` / `新加坡3店` … |
| `former_platform_shop_id` | 2 | `1292370001` / `1391124228`（自别名，见 §2.4） |
| `legacy_account_alias` | 2 | `3C店` / `菲律宾1店`（均 `is_active=false`） |
| **`former_name`** | **0** | — |

6 个 TikTok 账号现在的 `store_name` 已经从旧英文名改成了新名：

| shop_account_id | 现在的 store_name | 历史流量里的旧店名 |
|---|---|---|
| tiktok_sg_daone_mall_local | **FIORO SG** | DAONE Mall |
| tiktok_my_dawie_mall_local | **FIORO MY** | DAWIE Mall |
| tiktok_ph_explorers_mall_local | **FIORO PH** | Explorers Mall |
| tiktok_my_flora_mall_local | **KIDD0 MY** | Malaysia(Flora Mall) |
| tiktok_sg_hx_home_local | **KIDD0 SG** | Singapore(HX Home) |
| tiktok_ph_daju_mall_local | **KIDD0 PH** | Philippines(DAJU Mall) |

旧英文名**在候选集里一条都匹配不到**（`store_name_match` 只按当前 `store_name` 规范化，`alias_match` 又没有 `former_name`）⇒ **候选数 = 0 ⇒ `unmatched_shop_label` ⇒ `unknown`**。

> 这也解释了为什么订单侧「正常」而流量侧不正常：**妙手导出的订单「店铺」列填的是我们自己的中文别名**（`TK菲律宾1店` 等，alias 表里有），而**流量导出填的是平台真实英文店名**。改名后订单不受影响、流量全部失配。

### 5.3 修复路径已实测验证（不需要重采）

两条路都验证过：

**路径 A（推荐）—— 补 `former_name` 别名**

给 6 个 TikTok 账号各补一条 `former_name` 别名（旧英文名，`is_active=true`, `is_primary=false`）。历史流量的店名立刻命中 `store_name_match` ⇒ 候选数 1 ⇒ 归属正确。
风险：需要保证这 6 个旧名在全平台唯一（实测唯一，6 个互不相同，也不与任何 `claimed` 别名冲突）。

**路径 B —— 从 `public.catalog_files` 回填原始层身份**

```
b_class.fact_tiktok_analytics_monthly → public.catalog_files → shop_account_id
实测：1356 行中 1116 行可解析（82%），6 个店名标签 → 账号的映射 100% 正确、零歧义
```

| b_class.shop_id | catalog_files.shop_account_id | 行数 |
|---|---|---|
| DAWIE Mall | tiktok_my_dawie_mall_local | 203 |
| DAONE Mall | tiktok_sg_daone_mall_local | 200 |
| Explorers Mall | tiktok_ph_explorers_mall_local | 200 |
| Philippines(DAJU Mall) | tiktok_ph_daju_mall_local | 171 |
| Singapore(HX Home) | tiktok_sg_hx_home_local | 171 |
| Malaysia(Flora Mall) | tiktok_my_flora_mall_local | 171 |

路径 B 只能覆盖 82%，路径 A 能覆盖 100%（720 行里 `stamped_in_raw` 只有 636 行）。**建议 A + B 一起做**：A 修语义层（治本），B 修原始层（治标，为将来的 `shop_account_id` 戳补齐做铺垫）。

### 5.4 【关键补充】这 720 行不是"随机缺戳",而是**一个确定的批次** —— 2026-06-09

实测戳的时间线（`b_class.fact_tiktok_analytics_monthly`）：

| 入库日期 | 行数 | 有 `shop_account_id` 戳 |
|---|---|---|
| **2026-06-09** | **720** | **0** |
| 2026-07-03 ~ 2026-11-03 | 636 | **636（100%）** |

shopee 侧完全同构：**2026-06-09 的 1475 行 0 戳**，2026-06-26 起 100% 有戳。

把四个事实表的戳覆盖率拉齐看：

| 事实表 | 总行数 | 无戳 | 无戳行的日期区间 | 无戳行靠什么认身份 |
|---|---|---|---|---|
| `b_class.fact_shopee_analytics_monthly` | 2278 | **1475** | **2026-06-09（全部）** | 只有店名 → 46 行错配 |
| `b_class.fact_tiktok_analytics_monthly` | 1356 | **720** | **2026-06-09（全部）** | 只有店名 → 720 行 unmatched |
| `b_class.fact_shopee_orders_monthly` | 28973 | 11195 | 2026-07-07 ~ 11-05（云同步行） | 导出里的「店铺」中文别名 → 侥幸可用 |
| `b_class.fact_tiktok_orders_monthly` | 5112 | 1911 | 2026-07-07 ~ 11-05（云同步行） | 同上 |

**按入库路径拆开看，规律非常干净：**

| 入库路径 | `file_id` | `shop_account_id` 戳 | 认身份靠什么 |
|---|---|---|---|
| 本地采集入库（2026-06-26 / 07-03 起） | 有 | **有** | 戳（最稳） |
| 本地采集入库（**2026-06-09 那一批**） | 有 | **无** | 只能靠店名 → 失配 |
| 云同步接收（分析数据） | 无 | **有**（源带过来） | 戳 |
| 云同步接收（订单数据） | 无 | **无** | 导出「店铺」中文别名 → 侥幸可用 |

⇒ **结论：仓库其实早就定了「只认 `shop_account_id`」这条规矩（spec D14「稳定身份编号落库」，`data_hash` 作用域已从 `scope:shop_id` 切到 `scope:shop_account_id`），而且主路径已经在执行了。洞只有两个：**
1. **2026-06-09 的历史批量导入**（shopee 1475 + tiktok 720 = **2195 行**，涉及 **73 个文件**）没走盖章路径；
2. **云同步来的订单行**（11195 + 1911 = **13106 行**）没带戳，靠中文别名兜底 —— 目前能用，但依赖「别名表永远齐全」这个前提。

**为什么会出现 2026-06-09 这个洞**：`public.catalog_files.shop_account_id` 是在 v7.12.6（2026-11-01）才从 **87/460 补到 460/460** 的（见 `docs/superpowers/plans/STATUS.md`）。**补上游 ≠ 补下游** —— catalog_files 补齐了，已经躺在 `b_class` 里的历史行不会自动长出戳。

**而且这批数据完全可救**：实测这 2195 行涉及的 **73 个 catalog_files 现在全部都有 `shop_account_id`** ⇒ 一句 UPDATE 就能让它们 100% 恢复正确归属，**不需要重采**。

---

## 6. 其它已实测的隐患

| # | 现象 | 实测 | 性质 |
|---|---|---|---|
| H1 | 停用账号仍在吃流量 | 213 行（eternalbloom 152 + chenewei666 61） | 口径决策项，需业务拍板 |
| H2 | 候选池 50% 来自停用账号 | 138 条候选中 69 条来自 disabled | 与 H1 同源 |
| H3 | 自别名 | 2 条（alias 值 == 自己当前 ID） | 数据残留，清理即可 |
| H4 | `core.platform_shop_discoveries` 与账号状态不一致 | 26 条 discoveries，其中 6 条的 detected 值与任何账号都对不上 | 需要「探测失败」状态位（见 P2-2） |
| H5 | `b_class.fact_*_analytics_monthly.shop_id` 与 `raw_data->>'shop_account_id'` 不同源 | shopee 46 行身份错位；tiktok 720 行缺账号戳；订单侧 13106 行（云同步行）无戳 | 事实层缺少一致性校验（见 P2-1） |
| H6 | `core.shop_accounts` 有 `platform='验证码测试账号'` 脏行 | 1 行，且进入候选池 | 既有技术债，2026-11-01 规格 §2.8 已登记 |

---

## 7. 优化方案

### 7.0 批次划分原则（对齐 `docs/guides/PRE_LAUNCH_RULES.md`）

- **P0 止血**：堵住继续污染 + 修数据，让看板数字先可信。范围窄、可独立验证、不改口径。
- **P1 口径收敛**：动语义层与候选集，需要业务先拍板 H1。
- **P2 防护**：守护测试 + 监控告警，让同类问题下次自己冒出来。
- **P3 推迟**：真·大重构（V2），本次只登记不动手。

> **一个硬约束**：所有改动都不得让「歧义」静默变成「猜一个」——这是仓库既有原则（D13/A6），本次审查发现的缺陷 2 修法风险正源于此。

---

### P0 止血（**只保未来**：不做历史数据回填）

> **范围**：按 §0.2，只做「让后续采集不再出错」。历史数据修复（回填 2195 行戳、原始层 46 行身份、自别名清理）**已移出范围**。

#### P0-1 采集链路不得覆盖别人的主数据（**最高优先级**）

**改哪**：`backend/services/platform_shop_discovery_service.py`

**怎么改**（三个入口统一走一个守卫）：

1. 新增 `_assert_platform_shop_id_belongs_to(db, platform, detected_id, shop_account_id)`：
   - `detected_id` 已等于该账号当前值 → 放行（幂等）；
   - `detected_id` 已被**另一个**账号占用 → **拒绝覆盖**，把该条 discovery 落成 `status='conflict_detected'`（新增状态），记 warning 日志，**不碰**主数据；
   - 无人占用 → 放行（走原有的「旧值转别名」）。
2. `record_runtime_discovery` / `record_manual_discovery` 的 `auto_bound` 分支 / `confirm_discovery` **三处都调用**这个守卫。
3. `record_runtime_discovery` 额外加一条：**探测值必须与本次任务的目标账号一致** —— 即 `detected_platform_shop_id` 必须等于目标账号的 `platform_shop_id`，否则说明「切店还没生效 / 读到的是上一家店」，直接丢弃本次探测（这才是缺陷 1 的真正堵点）。

> 为什么不只是「加唯一性校验」：唯一性校验只能挡住「撞库」，挡不住「读到上一家店的合法 ID」（如 `zewei_toys.sg` 探测到 `1227491331` = chenewei666 的合法 ID，唯一性校验放行，但归属明显错）。**必须同时校验「探测值 == 目标账号自己的 ID」。**

**守护测试**（参照 `backend/tests/test_shop_platform_id_rebind_alias.py` 的写法）：

- `test_runtime_discovery_must_not_overwrite_another_accounts_platform_shop_id`
- `test_runtime_discovery_ignores_id_belonging_to_a_different_account`
- `test_manual_auto_bound_and_confirm_paths_share_the_same_guard`（计数式断言：三个入口都调用具名守卫）

> ⚠️ 现有测试 `test_all_discovery_binding_paths_keep_the_previous_id_as_alias` 断言源码里 `previous_platform_shop_id = shop_account.platform_shop_id` 出现 **3 次**、`await retain_previous_platform_shop_id_as_alias(` 出现 **3 次**。新增守卫时**不要改动这三处的结构**，否则会误红。

#### P0-2 修数据：原始层身份回填（46 行 Shopee + 740 行 TikTok） —— ❌ **已移出范围（历史数据）**

**改哪**：`b_class.fact_*_analytics_monthly` 的 `shop_id` 与 `raw_data->>'shop_id'`（**只修身份字段，不动指标**）

**怎么修**（纯 SQL，不重采）：

```sql
-- ① Shopee 46 行：raw_data 自带正确账号，按账号回填平台店铺ID
UPDATE b_class.fact_shopee_analytics_monthly b
   SET shop_id = sa.platform_shop_id,
       raw_data = jsonb_set(b.raw_data, '{shop_id}', to_jsonb(sa.platform_shop_id), true)
  FROM core.shop_accounts sa
 WHERE sa.shop_account_id = b.raw_data->>'shop_account_id'
   AND sa.platform = 'shopee'
   AND b.shop_id IS DISTINCT FROM sa.platform_shop_id;

-- ② TikTok 740 行：从 catalog_files 回填账号身份（可解析的 1116 行里取存量）
UPDATE b_class.fact_tiktok_analytics_monthly b
   SET shop_id = cf.shop_account_id,
       raw_data = jsonb_set(b.raw_data, '{shop_account_id}', to_jsonb(cf.shop_account_id), true)
  FROM public.catalog_files cf
 WHERE cf.id = b.file_id
   AND cf.shop_account_id IS NOT NULL
   AND b.raw_data->>'shop_account_id' IS NULL;
```

**执行前必做**：先跑 SELECT 版本核对命中行数（预期 ① 46 行、② 1116 行），再跑 UPDATE；**执行后重建** `semantic.fact_analytics_monthly_atomic_mv`（`DROP ... CASCADE` + 重建 + 连带刷新下游）。

> ⚠️ `data_hash` 口径在 v7.12.6 已从 `scope:shop_id` 切到 `scope:shop_account_id`（见 `docs/superpowers/plans/STATUS.md`）。**改 `b_class.shop_id` 会改变行的内容**，必须确认不会触发重复入账或历史文件重入库 —— **严禁**对历史月份文件手动重触发 ingest。

#### P0-2b 补 `shop_account_id` 戳（把 2026-06-09 那批接回主路径） —— ❌ **已移出范围（历史数据）**

**为什么单独列一条**：§5.4 已证明，`shop_account_id` 戳是仓库**既定的唯一正确锚点**（spec D14），主路径 2026-06-26 起 100% 在执行。**这 2195 行不是"缺功能"，是"补上游没补下游"** —— v7.12.6 把 `public.catalog_files.shop_account_id` 从 87/460 补到 460/460，但已躺在 `b_class` 里的历史行不会自动长出戳。

**实测可救率：100%** —— 这 2195 行涉及的 73 个 `catalog_files` **现在全部都有 `shop_account_id`**。

```sql
-- ③ 给 2026-06-09 那批分析数据补戳（shopee 1475 + tiktok 720 = 2195 行）
UPDATE b_class.fact_shopee_analytics_monthly b
   SET raw_data = jsonb_set(b.raw_data, '{shop_account_id}', to_jsonb(cf.shop_account_id), true)
  FROM public.catalog_files cf
 WHERE cf.id = b.file_id
   AND cf.shop_account_id IS NOT NULL
   AND b.raw_data->>'shop_account_id' IS NULL;

UPDATE b_class.fact_tiktok_analytics_monthly b
   SET raw_data = jsonb_set(b.raw_data, '{shop_account_id}', to_jsonb(cf.shop_account_id), true)
  FROM public.catalog_files cf
 WHERE cf.id = b.file_id
   AND cf.shop_account_id IS NOT NULL
   AND b.raw_data->>'shop_account_id' IS NULL;
```

**执行前必做**：SELECT 版本核对命中行数（预期 **2195 行**），执行后重建语义层 MV。

**补戳之后，那 720 行 TikTok 流量会直接变成 `candidate_count = 1`（`shop_account_id` 命中唯一账号）** ⇒ 归位正确、告警消失 —— **这一步就足以让 TikTok 的 720 行 unknown 归零，不必等 P0-3 补 `former_name` 别名**（别名补上是为了**将来**改名时不再失联，以及覆盖没有 `file_id` 的历史行）。

> ⚠️ 同样受 `data_hash` 约束：**只补身份戳，不动指标列**；严禁重触发历史文件 ingest。

#### P0-3 修数据：账号主数据 + 别名对齐 —— ❌ **已移出范围（历史数据）**
> 改名联动（写 `former_name` 别名）**已经实现**，不需要额外做事；自别名清理属历史数据。

**改哪**：`core.shop_accounts`、`core.shop_account_aliases`

1. 用 `backend/services/shopee_shop_id_resolver.py` 的硬编码基准表核对 11 个 shopee 账号的 `platform_shop_id`（当前 **11/11 已一致**，本项是**巡检**，不是修复）；
2. `platform_shop_id_status` 从 `auto_bound` 收敛为 `confirmed`（当前仅 `shopee_sg_zewei_toys_local` 一条是 `auto_bound`）；
3. **清理自别名 2 条**（§2.4）：`alias_value == 拥有者自己的 platform_shop_id` 的 `former_platform_shop_id` 别名；
4. **补 6 条 TikTok `former_name` 别名**（§5.3 路径 A）：旧英文名 → 对应账号；
5. 核对「`identity_value` → >1 个账号」的双认领清单（当前 0 条）。

**守护测试**：新增「别名值不得等于拥有者自己的 `platform_shop_id`」「`former_name` 别名必须落在改名链路上」两条断言。

---

### P1 口径收敛（**需业务先拍板 H1**）

#### P1-1 语义层：候选集收紧 + **锚点优先级倒过来**（不改计数口径）

**改哪**：`sql/semantic/shop_identity_resolution_candidates.sql` + `sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`

**改什么**：

1. **⭐ 锚点优先级倒过来：`shop_account_id` 升为 priority 1，`platform_shop_id` 降到 priority 2。**

   现状（`shop_identity_resolution_candidates.sql:24-48`）：`platform_shop_id`(1) → `shop_account_id`(2) → `alias_match`(3) → `store_name_match`(4)。
   **问题：最不稳定、最会被污染的那个排在第一，最稳的排在第二。** `platform_shop_id` 既会被采集器污染（缺陷 1），也会在平台换 ID 时失效；而 `shop_account_id` 是**账号主键，改名不变、跨平台一致**（spec D14 的立意）。

   实测后果（live，2026-06-22 ~ 06-30 的 18 行歧义行）：

   | `shop_id` | 声称的 `resolved_shop_account_id` | 实际数据属于 | `identity_source_value` |
   |---|---|---|---|
   | unknown | `shopee_my_xhkj1_local` ❌ | **shopee_ph_xh_home_local** | 1540271739（xhkj1.my 的编号） |
   | unknown | `shopee_ph_xhkj11_local` ❌ | **shopee_sg_xhkj11_local** | 1419169771（xhkj11.ph 的编号） |

   → 歧义判定本身是**对的**（`shop_id` 正确落 `unknown`，没有静默错配）；但**它"声称"的账号是错的**，于是看板健康检查里的 `identity_conflict` **报给了被污染的邻居，而不是真正的当事账号**（`postgresql_dashboard_service.py:2375-2389` 按 `resolved_shop_account_id` 分组）。

   **把 `shop_account_id` 提到 priority 1 之后**：
   - 歧义判定**完全不变**（候选数仍是 2 → 仍然落 `unknown`，安全属性零变化）；
   - 但「声称的账号」和「冲突报给谁」同时变对。

   ⚠️ 这**不是**问题单里"缺陷 2"那种改法 —— 那个改法动的是**计数口径**（把 count 收窄），会把歧义变成"猜一个"，必须否决；本条只动**候选排序**，歧义时选谁去"代表"这行数据变对，但**判不判歧义完全不动**。

2. `alias_match` 分支排除自别名（别名值 == 拥有者自己的 `platform_shop_id`）与跨账号认领（别名值 == 别的账号的 `platform_shop_id`）；
3. 若 P1-2 拍板「停用账号不参与匹配」，则在**两条**候选资产里都加 `WHERE sa.enabled IS TRUE`。

**为什么不能只留 `shop_account_id`、把别名路拆掉**：妙手导出的订单「店铺」列填的是**我们自己的中文别名**，而云同步来的 13106 行订单**既没有 `file_id`、也没有 `shop_account_id` 戳**（实测 11195 + 1911 行全部 `from_cloud` 且 `raw_data->>'shop_account_id'` 为空），它们**只能**靠别名认身份。所以别名这条路必须保留，只是排序上垫底。

**改哪条测试**：`backend/tests/data_pipeline/test_identity_candidates_materialization.py` 守着两处副本与正本的**内容指纹一致**（行数 + 全量 md5）—— 改了正本必须同步改副本，且**迁移 `20261105` 的指纹比对**要能过。另外 `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py:29-43` 断言四条语义路径都必须含 `count(DISTINCT c.resolved_shop_id)` —— 本条**不动计数写法**，断言不受影响。

**⚠️ 连带改动（漏一处就看板显示名 JOIN 落空）**：
- `backend/services/shop_sync_service.py:49` `resolve_dim_shop_id` —— docstring 明确要求「必须与语义层逐字一致」；
- `backend/tests/test_dim_shops_alignment.py:74-85` —— 断言 `platform_shop_id > shop_account_id`，需同步改断言；
- `current_migrations/versions/20261107_align_dim_shops_with_shop_accounts.py` —— `dim_shops.shop_id` 的派生口径要跟着对齐；
- `sql/semantic/shop_identity_resolution_candidates_v2_mv.sql` —— 物化副本与正本**两份都要改**（内容指纹守护）。

#### P1-2 候选池补齐过滤条件（**不是业务决策，是补漏抄的过滤**）

> **2026-11-06 复核后改判**：原方案把这一项列为"需业务拍板"，复核发现**全系统其他每一个环节都已经过滤了 `enabled`，只有语义层候选池漏了** ⇒ 它不是一条新口径，而是**一处实现不一致**。建议直接选 B（补过滤），无需业务拍板。

**语义层候选池 vs 其他环节的过滤一致性：**

| 环节 | 代码位置 | 过滤 `enabled` | 过滤 `business_role` |
|---|---|---|---|
| 采集时挑账号 | `backend/services/account_loader_service.py:129 / :160 / :194 / :222` | ✅ | — |
| 员工绩效 / 提成分配 | `employee_target_allocation_service.py:107`、`hr_income_calculation_service.py:868`、`personal_performance_workbench_service.py:306`、`operation_performance_shop_scope_service.py:19` | ✅ | ✅ `operating_store` |
| 探测匹配 | `backend/services/platform_shop_discovery_service.py:64 / :81 / :92` | ✅ | ✅ `operating_store` |
| 数据同步清理 | `backend/services/data_sync_cleanup_service.py:75` | ✅（取反，专清停用店） | — |
| **语义层候选池** | `sql/semantic/shop_identity_resolution_candidates.sql:21` | ❌ **漏** | ❌ **漏** |

候选池 138 行的实测构成：

| 来源 | 候选行数 | 占比 |
|---|---|---|
| `enabled = false` 的停用店 | **69** | **50%** |
| `business_role = 'collection_source'`（采集源，不是经营店） | 2 | 1.4% |
| 正常经营店 | 67 | 48.6% |

**代价实测（可忽略）**：

| 归属 | 行数 | UV |
|---|---|---|
| 挂在停用店名下 | 213 | **8**（全是每天一行、指标为 0 的日报行） |
| 挂在在营店名下 | 2701 | 574,725 |

⇒ 补上过滤后，停用店名下的 213 行会变成 `unknown`，但**它们加起来只有 8 个 UV，对看板数字没有任何贡献**。

**做法**：在正本与物化副本里都加

```sql
FROM core.shop_accounts sa
WHERE sa.enabled IS TRUE
  AND sa.business_role = 'operating_store'
```

**⚠️ 影响与回退**：
- 停用店在看板上的卡片会变空（历史流量落 `unknown`）。如果业务上要保留"停用店历史可查"，**正确做法是在看板/dim_shops 层单独处理**，而不是让语义层的号码簿继续混着两种状态；
- 将来要恢复某家店，把它改回 `enabled = true` 即可，数据自动归位；
- **本条必须与 P1-1 的优先级倒置同批发布**（都改候选集的两份资产 + 都要过内容指纹守护）。

---

### P2 防护（让同类问题下次自己冒出来）

#### P2-1 事实层身份一致性校验（把 `shop_account_id` 变成**硬门禁**）

这是"全部按 `shop_account_id` 来"的**制度化落点** —— 机制已经有了（`backend/services/data_ingestion_service.py:540-541` 从 `catalog_files.shop_account_id` 盖戳），缺的是**门禁**：现在文件缺 `shop_account_id` 照样入库，于是才有了 2026-06-09 那 2195 行。

三条断言，建议都做到"入库前拦截"级别：

1. **文件级门禁（本地采集入库）**：`public.catalog_files.shop_account_id` 为空 ⇒ **拒绝入库**并写明原因（现在只是"拿不到就留空"）。→ 杜绝再出现第二个 2026-06-09。
2. **行级一致性校验**：`b_class.<fact>.shop_id` 必须与 `raw_data->>'shop_account_id'` 解析出的账号自洽；不自洽就打 `sync_standardization_quality_service` 的质量分 + 落告警，**不再默默入库**。
3. **云同步路径**：`shop_account_id` 列为**必传字段**，缺失即拒收；同步过来的行必须与 `file_id`/`catalog_files` 的身份对得上（实测目前云同步的分析数据行带戳、订单行不带 —— 两者都不该靠"碰巧有别名"兜底）。

> 补完这三条，**"只认 `shop_account_id`" 就是真的实现了**，而不是"主路径实现了、历史和云同步是例外"。

#### P2-2 探测状态机补齐

`core.platform_shop_discoveries.status` 增加 `conflict_detected` / `stale_url` 两种状态（H4：当前 26 条里有 6 条的 detected 值对不上任何账号，但状态全是 `detected_single_bound`，看起来像成功）。

#### P2-3 看板侧把 unknown 拆开显示

`get_business_overview_identity_health` 现在把三类原因（`identity_conflict` / `traffic_without_order_match_due_to_identity` / `identity_warning_code`）混在一个 `warning_count` 里。建议按 `identity_warning_code` 分组返回（`unmatched` / `ambiguous` / `conflict`），并各自给 UV 与 PV —— 本次 738 行 unknown 里 93% 是 unmatched、7% 是 ambiguous，混在一起会让排查方向跑偏。

#### P2-4 回归测试补齐

| 用例 | 落点 |
|---|---|
| 探测到他人 ID 时不得覆盖账号主数据 | `backend/tests/test_shop_platform_id_rebind_alias.py`（问题单已要求） |
| 三个改主数据入口共用同一守卫 | 同上 |
| 改名后旧店名仍能解析回原账号 | `backend/tests/test_shop_rename_flow.py` |
| 候选池不产生自别名 | `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py` |
| analytics 资产**不得**出现区域列（反向护栏，已存在） | 保持不变 |
| unknown 按原因分组 | `backend/tests/data_pipeline/test_business_overview_module_consistency.py` |

---

### P3 推迟（登记为 post-launch V2 债务，本次不动）

| # | 债务 | 为什么现在不做 |
|---|---|---|
| V2-1 | analytics 接入区域感知匹配 | 需要先让 analytics 导出带站点信号；当前有反向守护测试挡着，属独立需求 |
| V2-2 | 采集链路「切店完成后再探测」的时序改造 | 现在的守卫（P0-1）已经能挡住误覆盖；时序改造涉及采集编排，影响面大 |
| V2-3 | 候选集统一到单一 SSOT（正本/副本/v2 三份定义） | 已有内容指纹守护，暂不急 |
| V2-4 | `platform='验证码测试账号'` 脏行清理 | 需要业务确认归属 |

> 按 `AGENTS.md`「非阻塞技术债记入 post-launch V2 清单，不顺手改」的要求登记。

---

## 8. 验收标准（对问题单验收项的修正）

| # | 问题单的验收项 | 复核后修正版 | 判定方式 |
|---|---|---|---|
| A1 | `get_business_overview_identity_health(granularity='monthly', target_date='2026-10-01')` → `warning_count = 0` | ⚠️ **不可作为唯一验收**：TikTok 那 720 行是「改名没有曾用名」，与采集器无关 | 拆成 A1a / A1b |
| A1a | —（新增） | Shopee 侧 `identity_warning_code = 'ambiguous_shop_label'` 的行数 **= 0**（当前 18 行） | `semantic.fact_analytics_monthly_atomic_mv` |
| A1b | —（新增） | TikTok 侧 `identity_warning_code = 'unmatched_shop_label'` 的行数 **= 0**（当前 720 行） | 同上 |
| A2 | `semantic.shop_identity_resolution_candidates` 里 shopee 无 `identity_value` 对应 >1 个账号 | ✅ 保留（**当前已满足**，作为回归护栏） | `GROUP BY identity_value_normalized HAVING count(DISTINCT resolved_shop_id) > 1` → 0 行 |
| A3 | 流量排名不再出现「未匹配店铺」 | ✅ 保留 | 看板流量排名 + 上述 A1a/A1b |
| A4 | 新增 discoveries 不得改变 `core.shop_accounts.platform_shop_id` | ✅ 保留，并**加强**：探测到「他人 ID」与「非本账号 ID」都必须拒绝覆盖 | 新增守护测试 + 连续采集 2 轮后比对账号主数据快照 |
| A5 | 回归测试：探测到他人 ID 时不得覆盖 | ✅ 保留，并扩充到三个入口 | `backend/tests/test_shop_platform_id_rebind_alias.py` |
| A6 | —（新增） | **shopee 侧**：`b_class.fact_shopee_analytics_monthly` 中 `shop_id` ≠ `raw_data->>'shop_account_id'` 对应账号的平台店铺ID 的行数 **= 0**（当前 46 行） | P2-1 的质量检查查询 |
| A6b | —（新增） | **tiktok 侧**：`b_class.fact_tiktok_analytics_monthly` 中既没有 `shop_account_id` 戳、店名又匹配不到任何账号的行数 **= 0**（当前 720 行 / 1356 行） | 同上 |
| A6c | —（新增） | **戳覆盖率**：四个事实表 `raw_data->>'shop_account_id'` 缺失行数 **= 0**（当前 shopee 分析 1475 / tiktok 分析 720 / shopee 订单 11195 / tiktok 订单 1911） | `P0-2b` + `P2-1` 后复查 |
| A6d | —（新增） | **歧义行归属正确**：18 行歧义行的 `resolved_shop_account_id` 必须指向**真正当事账号**（xh_home.ph / xhkj11.sg），而不是被污染的邻居 | `P1-1` 优先级倒置后复查 |
| A7 | —（新增） | 别名表中 `alias_value == 拥有者自己的 platform_shop_id` 的行数 **= 0**（当前 2） | `core.shop_account_aliases` 自查 |
| A8 | —（新增） | 候选集中来自 `enabled = false` 账号的行数：按 P1-2 决策取「0」或「记录在案」 | `shop_identity_resolution_candidates` 分组统计 |

**流程校正**：问题单末尾写「改动 `sql/semantic/` 下的资产按仓库规矩需要配一条 openspec 变更提案」。这条**与仓库现行规则冲突** —— `AGENTS.md:29` 与 `docs/architecture/PROJECT_STRUCTURE.md:77` 都写明 `openspec/` 是**历史归档**、不是活动规则来源。本仓库的现行做法是 `brainstorming` → `writing-plans`，产物落在 **`docs/superpowers/specs/` 与 `docs/superpowers/plans/`**（见 `docs/superpowers/README.md`）。本方案即按该约定产出。

---

## 9. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 回填 `b_class.shop_id` 触发 `data_hash` 变化 → 历史文件重入库 | **重复入账**（v7.12.6 踩过，见 STATUS.md「重复入账边界」） | ① 先在只读副本核对命中行数；② 严禁对历史月份文件重触发 ingest；③ 回填只改身份字段，不改 `data_hash` 作用域字段（`scope:shop_account_id` 口径下不变量）；④ 生产执行前先在开发库跑通同一条 SQL 并比对行数 |
| `DROP ... CASCADE` 重建 MV 连带清空下游看板视图 | 看板短暂空窗 | 走 `scripts/bootstrap_postgresql_dashboard.py --module all` 全量重建；选低峰执行 |
| 候选池加 `enabled` 过滤导致历史流量落 `unknown` | 停用店历史消失 | 由 P1-2 业务拍板决定；选 B 时先在开发库跑前后对比 |
| 补 `former_name` 别名与 `claimed` 别名撞车 | 唯一约束冲突 | 本次 6 个旧名实测互不相同、且与现有 21 条别名不冲突；执行前先跑冲突预检 |
| 守卫拦截导致采集任务「失败率上升」 | 运营感知 | 守卫**不抛异常**，只跳过覆盖 + 落 `conflict_detected` 状态 + 告警日志，不影响采集主流程 |

---

## 10. 建议执行顺序

```
P0-1 采集守卫（纯代码，可独立发布）      ← 最高优先级：唯一的"未来出错"根源
P2-1 入库硬门禁（shop_account_id 必填）  ← 保证未来数据不再依赖店名
P1-1 锚点优先级倒置 + dim_shops 同步对齐  ← 让最稳的锚点说了算
P2-2~P2-4 探测状态机 / 看板拆因 / 守护测试
P1-2 停用账号口径（并行，等业务拍板）
—— 以下已按 §0.2 移出范围（历史数据）——
P0-2 / P0-2b / P0-3  历史数据回填与清理
```

**优先级说明（收窄范围后重排）**：
- **P0-1 排第一**：它是「未来数据出问题」的**唯一根源** —— 主数据被污染一次,该账号之后**每一次**采集都会错位,而且会一路写进新文件。不堵这条,后面做得再好都会被它带偏。
- **P2-1 排第二**：它是「未来数据不再依赖店名」的保证 —— 店名会改、账号 ID 不会。而且这个戳**天生免疫缺陷 1**（缺陷 1 污染的是 `platform_shop_id`,不是 `shop_account_id`),所以它是一道便宜的保险。
- **P1-1 排第三**：让「最稳的锚点」说了算。歧义判定完全不动（仍落 unknown,安全属性零变化），只修"歧义时报给谁"和"靠什么认身份"。
- **§0.3 两件事是"不修就会自己出事"的**：① `b_class.shop_id` 语义即将变（方向对，但要加测试守住）；② 优先级倒置漏改 `dim_shops` 会让看板显示名 JOIN 落空。

**每一步都必须自带验证**，按 `docs/guides/VERIFICATION_MATRIX.md`：
- 目标测试：`backend/tests/test_shop_platform_id_rebind_alias.py`、`backend/tests/test_shop_rename_flow.py`、`backend/tests/data_pipeline/test_shop_identity_resolution_sql.py`、`backend/tests/data_pipeline/test_identity_candidates_materialization.py`、`backend/tests/data_pipeline/test_analytics_shop_identity_alignment.py`
- 回归判定用 **junit XML 前后 diff**（`python scripts/diff_pytest_junit.py`），不要用失败计数（仓库有既有失败基线）
- 改 `sql/semantic/` 资产后：`python scripts/verify_architecture_ssot.py` + `scripts/rebuild_views.py` / `scripts/bootstrap_postgresql_dashboard.py --module all`

---

## 11. 需要业务确认的事

> **2026-11-06 复核后：原本两项待确认，现在只剩一项。**

1. ~~停用店铺的历史流量还要不要算在该店名下~~ → **已改判为实现不一致，不需要业务拍板**（见 P1-2）。唯一残留的业务点是：如果业务上确实要保留"停用店历史可查"，应改在看板/dim_shops 层处理，而不是让语义层号码簿混着两种状态。
2. **（保留）`b_class` 事实层的数据修正需要同意在开发库先行验证、生产择时执行**（低峰 + 备份）—— 若后续决定也修历史数据。

> 其余部分（缺陷 1 守卫、入库硬门禁、锚点优先级倒置、候选池补过滤、守护测试）均为**纯技术修复**，不依赖业务决策，可直接进入实施计划。

---

## 12. 实施记录（2026-11-06 落地情况）

> 落地方式：独立 git worktree `feature/shop-identity-alignment`，与主仓隔离；完整验证通过后合并回 main。

### 12.1 逐项状态

| 项 | 状态 | 落点 | 关键结论 |
|---|---|---|---|
| **P0-1** 采集守卫 | ✅ 已提交（`e18e2c75`） | `backend/services/platform_shop_discovery_service.py` | 运行时探测**只记录证据、不改主数据**；三个会改主数据的入口统一走具名归属守卫 `_guard_platform_shop_id_binding()` |
| **P2-1** 入库硬门禁 | ✅ 已落地 | 新增 `backend/services/shop_identity_gate_service.py`；`data_ingestion_service` / `data_sync_service` / `data_sync_file_state_service` / `catalog_scanner` / `field_mapping_status` | 缺 `shop_account_id` 的店铺数据**在盖戳前拒收**，落 `needs_shop` 终态（**不落 failed**：重试必然再失败，不是可重试故障） |
| **P1-1** 锚点优先级倒置 | ✅ 已落地 | `sql/semantic/shop_identity_resolution_candidates.sql` + `..._v2_mv.sql`（正本与副本**指纹一致**） | `shop_account_id` 升 priority 1、`platform_shop_id` 降 2；**计数口径一字未动**（歧义行仍落 `unknown`） |
| **P1-2** 候选池补过滤 | ✅ 已落地 | 同上 | `enabled IS TRUE` + `business_role='operating_store'` —— **补的是系统其它环节都有的过滤**，不是新口径 |
| **P2-2** 探测状态机 | ✅ 已落地 | `platform_shop_discovery_service.py` / `platform_shop_discoveries.py` / `postgresql_dashboard_service.py` | 见 §12.2 |
| **P2-3** 看板拆因 | ✅ 已落地 | `backend/services/postgresql_dashboard_service.py` | `warning_breakdown` 按 `unmatched` / `ambiguous` / `conflict` / `other` 分组，各给 UV / PV / 订单数；`warning_count` 改为**真实总数**（列表仍只展示前 50 条） |
| **P2-4** 守护测试 | ✅ 已落地 | 新增 3 个测试文件 + 补齐既有守护 | 见 §12.3 |

### 12.2 P2-2 探测状态机：补上的那个洞

方案原文只说「status 增加 `conflict_detected` / `stale_url`」（已随 P0-1 落地）。实施时发现判定还有**第三个分支没覆盖**：

> 账号自己**还没有**平台编号时，探测值谁都对不上 —— 以前会落进 `detected_single_bound`，
> **看起来像成功**，实际是压根没绑上。

开发库实测佐证：26 条探测记录里有 3 条（id 23 / 65 / 69）的 `detected_platform_shop_id` 对不上任何账号，状态却是 `detected_single_bound`。

⇒ 新增状态 **`unmatched_platform_shop_id`**，并把状态判定与「问题态清单」收拢成**具名常量**（看板与列表引用同一份，避免两边漂移）。

可见性落在两处：

1. **列表层**：`GET /platform-shop-discoveries` 支持 `?status=a,b` 与 `?only_issues=true`；新增 `GET /platform-shop-discoveries/issues/summary`（问题态汇总）与 `GET /platform-shop-discoveries/statuses`（状态字典）。
2. **看板层**：`get_business_overview_identity_health` 新增 `discovery_issues` 区块 —— 这是**第二层信号**：
   - 语义层告警（`warning_count`）= **事后**信号：数据已经落错、已经进了看板；
   - 采集期探测异常 = **事前**信号：这次采集读到的编号就对不上账号。
   
   只有事后信号 ⇒ 问题会反复出现。前端「店铺身份未对齐」告警文案把两层合并展示。

### 12.3 守护测试补齐

| 用例 | 落点 | 状态 |
|---|---|---|
| 探测到他人 ID 不得覆盖账号主数据 | `backend/tests/test_shop_platform_id_rebind_alias.py` | ✅ |
| 三个改主数据入口共用同一守卫 | 同上（按**计数**断言） | ✅ |
| 改名后旧店名仍能解析回原账号 | `backend/tests/test_shop_rename_flow.py` | ✅ 既有 |
| 候选池不产生自别名 / 不跨账号认领 | `backend/tests/data_pipeline/test_shop_identity_candidate_anchor.py` | ✅ 新增 |
| analytics 资产不得出现区域列 | `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py` | ✅ 既有 |
| unknown 按原因分组 | `backend/tests/data_pipeline/test_business_overview_module_consistency.py` | ✅ 新增（P2-3） |
| 入库身份门禁（文件级 + 行级） | `backend/tests/test_shop_identity_ingest_gate.py` | ✅ 新建（14 条） |
| 探测状态机（含 `unmatched`） | `backend/tests/test_platform_shop_discovery_state_machine.py` | ✅ 新建（14 条） |
| 候选集锚点重锚（5 条不变量 A~E） | `backend/tests/data_pipeline/test_shop_identity_candidate_anchor.py` | ✅ 新建（13 条） |

### 12.4 迁移：live 开发库实测

迁移：`current_migrations/versions/20261112_realign_identity_candidates_anchor.py`
（revision `current_schema_20261112_realign_identity_candidates_anchor`，down_revision 接在链头 `current_schema_20261111_...` 之后）。

**upgrade → downgrade → upgrade 三段在 live 开发库跑通**，且每段都校验：

- 正本与物化副本**内容指纹一致**（`md5` 逐行聚合）；
- `semantic.fact_analytics_atomic_mv` / `mart.shop_day_kpi` / `api.business_overview_traffic_ranking_module` **一个没少**；
- 验证脚本跑完**显式回滚**，开发库回到原状（候选集 138 行、alembic 版本未变）。

三条**硬约束**（live 实测得出，勿回退）：

1. 解析函数 `semantic.resolve_shop_identity` 是 `LANGUAGE sql`，被 `fact_inventory_snapshot` / `fact_products_atomic` / `fact_services_atomic` 依赖 ⇒ **不能 `DROP FUNCTION`**（报 `DependentObjectsStillExist`），必须先把函数体里的副本引用换成正本（`CREATE OR REPLACE` 保持 OID）。
2. 两个原子层普通视图 `fact_orders_atomic` / `fact_analytics_atomic` **也**对副本有被跟踪依赖 ⇒ DROP 副本前必须先重建它们指向正本。
3. `sql/semantic/analytics_atomic.sql` 顶部的 `DROP VIEW ... CASCADE` **会连带删掉 10 个对象** ⇒ 迁移里用 `_strip_cascade_drop()` 去掉该语句，改用 `CREATE OR REPLACE VIEW`（保持视图 OID）。

### 12.5 口径影响实测（单事务内受控前后对比）

| 项 | 结果 |
|---|---|
| 候选集规模 | 138 → **66** 行（shop_account_id 18 / platform_shop_id 12 / alias 18 / store_name 18） |
| 自别名 | 2 → **0** |
| A2 不变量（一个 identity_value 对应 >1 账号） | 仍为 **0** 行 |
| analytics 月度 MV 的 18 行歧义行 | 归属**全部改对**（`shopee_my_xhkj1_local → shopee_ph_xh_home_local` 9 行 / `shopee_ph_xhkj11_local → shopee_sg_xhkj11_local` 9 行） |
| 停用店流量 | 213 行（eternalbloom 152 + chenewei666 61）落 `unmatched` —— 合计仅 **8 UV** |
| **看板 UV 变化** | **0**（`shop_id` 变化 213 行，UV 零变化）⇒ A6d 达成，看板数字零变化 |
| orders 月度 MV（34085 行） | `shop_id` / `warning_code` / 金额**全部零变化** |

### 12.6 验证结论（junit XML 前后 diff）

按 `docs/guides/VERIFICATION_MATRIX.md`：回归判定用**失败用例集合的差**，不用失败计数。
为了让「新增失败」判定可靠，**在 `main` 的对照 worktree 上用同一份文件清单跑了一遍 before**，
再与本分支的 after 逐组对比。

| 组 | 文件范围 | before | after | 新增失败(回归) | 既有失败(两边一致) | 新增用例 |
|---|---|---|---|---|---|---|
| A | 候选集 / 盖戳 / 改名 / 采集守卫 / 前端单测 | 113 例 / 1 失败 | 163 例 / 1 失败 | **0** | 1 | 59 |
| B | 语义层 PG 链路 + 看板模块（testcontainers） | 125 例 / 1 失败 | 130 例 / 1 失败 | **0** | 1 | 5 |
| C | 受影响的其它测试文件（数据同步 / 扫描器 / 探测 API 等） | 138 例 / 2 失败 | 142 例 / 2 失败 | **0** | 2 | 12 |

**新增失败总数 = 0** ⇒ 零回归。

3 个既有失败（**在本分支与 main 上表现完全一致**，与本次改动无关）：

| 用例 | 现象 |
|---|---|
| `test_business_overview_frontend_units::test_business_overview_frontend_expense_tooltip_includes_labor_cost` | 断言 `人力费用` 字样，Vue 里没有（文案口径问题） |
| `test_dashboard_router_switch::test_switched_app_serves_real_postgresql_dashboard_routes` | comparison 端点 500（`:443`） |
| `test_data_sync_governance_status_consistency::test_governance_detailed_coverage_skips_temp_development_sample_files` | `IndexError`（临时开发样例文件） |

另有 `scripts/verify_architecture_ssot.py` 报 1 项既有违规（2 个未归档 legacy 文件），**main 上完全相同**，与本次改动无关。

#### 落地过程中被守护测试抓出来、并已修掉的问题

| 问题 | 根因 | 处置 |
|---|---|---|
| PG 组 2 条用例 `column sa.enabled does not exist` | 候选池加了 `enabled` / `business_role` 过滤，但 **6 处测试桩的 `core.shop_accounts` 表没这两列**（真实表本来就有） | 补齐 6 处桩表列定义（带生产同款默认值） |
| 迁移守护测试 2 条误判 | 断言去源码里找 `CASCADE` / `DROP VIEW` 字样，把**解释性 docstring**当成了执行 | 改成**行为断言**：把真实资产喂给迁移的 `_strip_cascade_drop()`，看结果里还有没有 `DROP VIEW` / `CASCADE` |


---

## 13. Shopee 歧义的成因与修法（2026-11 复核，取代 §12.5 的归属表述）

### 13.1 成因：采集侧的硬编码覆盖表**漏了 3 个在营店**

`backend/services/shopee_shop_id_resolver.py` 里两张硬编码覆盖表
（`SHOPEE_PLATFORM_SHOP_ID_OVERRIDES` / `SHOPEE_STORE_NAME_OVERRIDES`，各 11 条）
是本次事故的直接病因：

* 开发库共 **13 个在营 Shopee 店**，覆盖表只命中 **10 个**；
* 没命中的正好是出错的那 3 个：`shopee_sg_xhkj11_local`(xhkj11.sg)、
  `shopee_ph_xh_home_local`(xh_home.ph)、`shopee_my_xhkj12_local`(xhkj12.my)；
* 这 3 个店落到 `shopee_shop_id_resolver.py:61-67` 的**回退分支** ——
  去拿「账号上下文里的 `platform_shop_id`/`shop_id`」，来路不明 ⇒ 拿到**别的店**的编号；
* ⇒ 行内 ``shop_id``（别的店的编号）与 ``store_name`` / ``shop_account_id``（本店的）
  互相矛盾 ⇒ 语义层候选数 2 ⇒ 整行落 ``unknown``。

覆盖表与守卫由 commit `1cabb3cb`（2026-06-09）引入；错数据采于 2026-06-22 ~ 06-30
（守卫已在但没拦住 —— 因为守卫的「期望编号」复用同一个坏解析器）。

配套证据：12 个在营 Shopee 店 **12/12 有** `core.shop_accounts.platform_shop_id`（零缺口），
TikTok 6 个在营店 **0/6 有**（TikTok 的锚点只能是别名表）。

### 13.2 「编号权威」的硬证据：UV 量级

§12.5 曾把 18 行歧义行的归属写成「改成 `shop_account_id` 所属账号」。
本节用 UV 量级复核后**纠正**这一表述 —— 正确的归属是**编号所属账号**。

| 标签所属店 | 正常行 UV avg | 错配行 UV avg | 编号所属店 | 正常行 UV avg |
|---|---|---|---|---|
| `shopee_sg_xhkj11_local` | **314.7** | **786.9** | `shopee_ph_xhkj11_local` | **896.4** |
| `shopee_ph_xh_home_local` | **362.6** | **147.4** | `shopee_my_xhkj1_local` | **141.2** |

错配行的 UV 吻合**编号所属**的店，不吻合**标签所属**的店 ⇒
**数据是编号那个店的，标签被整组贴错了**。

> 复现脚本：`temp/verify_reconcile_matches_migration.py`（只读，不写库）

这条证据同时说明**标签两票一致并不代表标签对** ——
`raw_data.store_name` 与 `raw_data.shop_account_id` 实测 **0 行**不一致
（两者同源于账号上下文 ⇒ 一起错），只有编号是独立来源。

⇒ 结论：**平台店铺编号是权威的**。语义层候选池早在 2026-11-06 就写过同样的判断
（「`platform_shop_id` 会被采集器污染」），本次事故是那条警告的兑现。

### 13.3 本批次落地范围（2026-11 用户拍板）

用户拍板：**三条源头全做 + 历史清理 + 别名补录**；**硬编码覆盖表直接删除**（不降级为兜底）；
**入库时收敛改写 `raw_data` 为主数据值**（不是校验拒收）。

| 工作包 | 交付物 | 状态 |
|---|---|---|
| WP-1 采集侧单一源头 | 删 `shopee_shop_id_resolver.py`，新建 `shop_account_identity_service.py`，改 6 处调用点 | **完成**（守护测试 11 passed） |
| WP-2 入库收敛 | 新建 `backend/services/shop_identity_reconciliation_service.py`，接入 `data_ingestion_service.py` | **完成**（守护测试 25 passed） |
| WP-3 门禁兜底 | `shop_identity_gate_service.py` 新增 `evaluate_row_identity_consistency()`（收敛后复核） | **完成** |
| WP-4 同步放大器 | `cloud_b_class_sync_service.py`：①``shop_id`` 与 ``raw_data`` **绑定**（同进同退，不再一个更新一个不动）；②upsert 前拦截「列与 raw_data 不同源」的行，不写云端并计数 | **完成**（守护测试 9 passed） |
| WP-5 冲突告警 | 看板新增 ``platform_shop_id_conflict`` 原因码 + **查询期诊断**（直查事实行，不改 MV） | **完成**（守护测试 5 passed；开发库实测检出 18 行 / 8,409 UV） |
| WP-6 历史订正 | `20261117_remediate_shopee_row_identity_conflicts.py` | **完成**（行为守护测试 9 passed + 单事务实测通过） |
| WP-7 别名补录 | `20261116_add_tiktok_export_store_name_aliases.py`（TikTok 6 条导出店名别名） | **完成**（守护测试 12 passed + 单事务实测通过） |

> ⚠️ **WP-5 为什么不做成「语义层 MV 加列」**：
> 给物化视图加列必须**重建 MV**（``REFRESH`` 只能重算数据、不能改定义），
> 而 ``DROP MATERIALIZED VIEW ... CASCADE`` 会连删下游对象
> （历史上 ``analytics_atomic.sql`` 的 ``DROP VIEW CASCADE`` 连删过 10 个对象）。
> ⇒ 改用**查询期诊断**：在看板告警查询里直查事实行算「编号与标签打架」，
> 零迁移、零 MV 重建、零下游影响。判据与历史订正迁移同构。

> ⚠️ **WP-4 的两处改动缺一不可**：
> 只做 ②（拦截不自洽行）能挡住「新造的混合行」；
> 只做 ①（绑定）挡不住「冲突键撞车后 ``raw_data`` 被覆盖」。
> 两者一起才闭环。


### 13.4 入库收敛的口径

| 项 | 规则 |
|---|---|
| 信号优先级 | `platform_shop_id` → `shop_id` → `shop_account_id` → `store_name`（编号权威） |
| 归属判定 | 第一个**唯一命中**账号的信号决定归属；命中多账号的信号**不可用**（跳过），换下一个 |
| 全都定不了 | **不收敛**（原样保留 ⇒ 语义层落 `unknown` + 看板告警）—— 绝不静默挑一个 |
| 收敛值 | 一律取 `core.shop_accounts` 的登记值，不从行内观测值推导 |
| 改动范围 | **只改身份键**（`shop_id` / `shop_account_id` / `store_name` / `platform_shop_id` 及其中文别名键），业务字段一个不动 |
| `shop_id` 列 | **有**平台编号才改（Shopee）；**没有**则保留原值（TikTok）—— 改了会动文件级 upsert 冲突键 ⇒ 重采会插重复行 |
| `data_hash` | 不变（作用域取文件级值，与行内身份无关）⇒ 重采覆盖同一行，不重复入库 |

### 13.5 验证结果

| 项 | 结果 |
|---|---|
| 收敛守护测试 | `backend/tests/test_shop_identity_reconciliation.py` **25 passed** |
| 收敛 vs 迁移口径一致 | 1,946 行矛盾行 **100% 吻合**（0 不一致 / 0 无法确定）⇒ 新采数据与历史数据不分叉 |
| 语义层候选数前后对比 | 收敛前候选数 = **2**（⇒ unknown）；收敛后 = **1**（⇒ 唯一命中）|
| 迁移行为守护测试 | `backend/tests/data_pipeline/test_shopee_row_identity_remediation.py` **9 passed**（隔离库自造数据，订正方向 / 只改身份字段 / data_hash 不变 / 幂等 / 回滚 / 停用店不动 / 未登记编号不动） |
| 别名迁移守护测试 | `backend/tests/data_pipeline/test_tiktok_export_store_name_aliases.py` **12 passed** |
| 采集侧守护测试 | `backend/tests/test_shop_account_identity_service.py` **11 passed** |
| 同步侧守护测试 | `backend/tests/test_cloud_sync_identity_guard.py` **9 passed** |
| 看板告警守护测试 | `backend/tests/test_dashboard_identity_conflict_alert.py` **5 passed** |
| **本次新增 + 改动的 9 个测试文件** | 全量回归里 **108/108 全过、零失败**（含 4 个被适配的既有测试文件 25+7+5+5 = 42 例） |
| 看板诊断实测 | 开发库上精确检出 **18 行 / 8,409 UV** 的编号与标签打架 —— 与事故影响面完全吻合 |
| 两个迁移单事务实测 | unknown 行 951 → **213**（剩余 213 = 停用店，8 UV，属预期）、ambiguous 18 → **0**、跨账号认领 1,946 → **0**；总行数/总 UV 不变；重跑幂等；回滚后与改动前完全一致 |
| 架构 SSOT 校验 | `scripts/verify_architecture_ssot.py` 3 PASS / 1 FAIL —— 唯一 FAIL 是 §12 已记录的**既有违规**（2 个未归档 legacy 文件），与本次改动无关 |


> ⚠️ 迁移链注意事项：`20261116` 的 `down_revision` 目前指向 `current_schema_20261114_add_sku_roi_columns`。
> 应用迁移必须走 `python scripts/run_current_schema_migrations.py`（fail-closed），
> **禁止**手工 `alembic stamp`。

> ⚠️ **本分支的基线是 `main@e69a29e3`**，而 main 在本批次期间又前进到了 `1e61a3c9`
> （product-center 阶段 1 的 6 个提交，含 `20261113` / `20261114` 两个新迁移）。
> ⇒ 本 worktree 里**看不到**那两个迁移文件，静态查链会误报「双头」。
> ⇒ 正确顺序：**先 commit → 把 main 合进本分支 → 再跑最终回归**，
> 这样最终验证跑的是「main 最新内容 + 本次全部改动」。

---

### 13.6 当前状态与交接动作（2026-11-07）

**已完成**：代码已合并回 `main`（快进，`76d3d911`），回归零新增失败。

**尚未完成：迁移尚未应用到开发库。** 原因是**外部依赖**，不是本次改动的问题：

| 项 | 现状 |
|---|---|
| 开发库版本 | `current_schema_20261115_add_sku_platform_pricing` |
| 该迁移文件是否在 main | **否** —— 只在 `feature/product-center-stage0` 分支（commit `f51ceb46`） |
| 守护入口判定 | `failure_code=environment_invalid`，`'…20261115…' is not a supported current revision`，`recommended_action=manual_source_approval` |
| 本次能否绕过 | **不能**，也不应该 —— 绕过 fail-closed 正是仓库明令禁止的 |

#### 交接动作（顺序不能颠倒）

1. **等 product-center 会话把 `20261115_add_sku_platform_pricing` 合入 main**；
2. 立刻把 `20261116_add_tiktok_export_store_name_aliases.py` 的 `down_revision`
   从 `current_schema_20261114_add_sku_roi_columns` 改成
   `current_schema_20261115_add_sku_platform_pricing`；
   （不改会双头 —— `20261114` 有两个后继；改早了会链断 —— 引用不存在的 revision。
   **两种情形都是 fail-closed，不会损坏数据**，但第 2 步必须在第 1 步之后做。）
3. `python scripts/run_current_schema_migrations.py`（走守护入口）；
4. `python temp/refresh_identity_mvs.py` 刷物化视图 ——
   **清单由脚本自己从两个迁移文件解析 `_REQUIRED_REFRESH_TARGETS` 取并集 = 6 个**
   （`shop_identity_resolution_candidates_v2_mv` / `fact_analytics_atomic_mv` /
   `fact_analytics_monthly_atomic_mv` / `fact_orders_atomic_mv` /
   `fact_orders_monthly_atomic_mv` / `fact_products_atomic_mv`），
   顺序按依赖排列（候选集最先）；
   ⚠️ **漏刷 `shop_identity_resolution_candidates_v2_mv` ⇒ TikTok 新别名不生效**
   （别名表是实时读的，但候选集是它的**物化副本**）⇒ 720 行仍然落 `unknown`
   ⇒ 验收必然不过 —— 所以这一步的清单**不能手写**（手写过一次，正好漏了这 3 个）。
5. `python temp/verify_identity_remediation_outcome.py` 验收（**看退出码，不看打印文字**）：
   - `0` ⇒ 通过：unknown 行 951 → **213**（剩余 213 = 停用店，8 UV，属预期）、
     unknown UV 117,181 → **8**、ambiguous 18 → **0**、ambiguous UV 8,409 → **0**、
     跨账号认领 1,946 → **0**、总行数/总 UV **不变**（3,634 / 683,497）、别名 **+6**；
   - `2` ⇒ **迁移尚未落库**（版本链还没走到 `20261117`）⇒ **不算通过**；
     此时指标等于订正前基线是正常的，要回头查第三步是否真的应用了
     （看 `public.current_schema_alembic_version.version_num`），**绝不要**手工改版本表；
   - `1` ⇒ 已落库但指标与目标不符 ⇒ 如实报告哪些指标不符。

⚠️ 两个迁移的 SQL 逻辑本身**已在真实开发库上单事务实测通过**（unknown 951→213、
ambiguous 18→0、跨账号认领 1,946→0、幂等、回滚后完全复原）——
即「订正本身是有效的」，待补的只是**走守护入口的正式落库**这一步。

---

### 13.7 自动续接已就位 + 交接脚本的三处修正（2026-11-07）

按用户授权（「迁移落库被外部依赖阻塞时，设定时检查，就绪后自动跑完剩余步骤并报结果」），
已注册定时任务接管 §13.6 的五步：

| 项 | 值 |
|---|---|
| cronId | `644823b3-6593-45c4-8a67-ea7f980ba8eb` |
| 名称 | 店铺身份订正 · 迁移落库自动续接 |
| 频率 | `*/15 * * * *`（Asia/Hong_Kong） |
| 绑定会话 | `sessionId` = 本会话（`mvs_706fd47e912847d09c642f7943b44884`） |
| 每轮逻辑 | 先**只读**查 `main` 上有没有 `20261115` ⇒ 没有就一句话跳过、不做任何写操作；⇒ 有就按 §13.6 全流程跑完 |
| 自删条件 | 仅当**验收脚本退出码为 0** 才 `cron_delete` 自删；任一步失败 ⇒ 保留任务等下一轮 |

> ⚠️ 隔离纪律：任务 prompt 里写死「不要碰 `.worktrees/inventory-aging-pipeline-recovery`
> 与 `.worktrees/product-center-stage0`」「不要在 main 上改除 20261116 迁移文件以外的任何文件」。

**首轮已实测触发**（02:40:00，`triggerSource=scheduled`）；`main` HEAD 保持 `90facb9c`
未被改动 —— 符合「依赖未就绪 ⇒ 只读检查后跳过」的预期。

#### 交接脚本的三处修正（都是会**真实打断**自动流程的缺陷）

| # | 缺陷 | 后果 | 修正 |
|---|---|---|---|
| ① | 三个交接脚本打印 `✓` / `⇒` / `⚠️`，而 Windows 控制台默认 **GBK** | 脚本在打印时抛 `UnicodeEncodeError`，**退出码非 0** ⇒ 自动流程把它们当成「这一步失败」而中止 | 脚本内 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`（顺带把乱码中文也修成可读） |
| ② | 验收脚本的判定是**单向**的（`after <= before`） | 迁移**根本没落库**时，所有指标仍等于订正前基线 ⇒ 脚本照样打印「全部通过」+ 退出码 0 ⇒ 定时任务会**误判成功并自删**，自动续接能力就此丢失 | 改为「**先判迁移落没落库**（静态解析迁移链，判断版本表 head 是否在 `20261117` 的下游）⇒ 落库后再按**目标值严格比对**」；退出码 `0`=通过 / `2`=未落库 / `1`=指标不符 |
| ③ | 刷新脚本的 MV 清单是**手写**的 3 个 | 漏了 `shop_identity_resolution_candidates_v2_mv`（别名生效的唯一入口）⇒ TikTok 720 行仍落 `unknown` ⇒ 验收必然不过 | 改为**从两个迁移文件解析 `_REQUIRED_REFRESH_TARGETS` 取并集**（= 6 个），顺序按依赖排列 |

> 三者都在 `temp/`（已 gitignore）⇒ 不进仓库、不影响 `main` 的代码与迁移；
> 但**会**影响自动流程的成败，所以必须修。

#### 修正后的实测（2026-11-07，开发库仍是订正前状态）

| 脚本 | 结果 |
|---|---|
| `temp/check_migration_chain.py` | 退出码 **0**，输出「[OK] 迁移链单头」；链单头（head = `20261117`），49 个迁移文件 |
| `temp/refresh_identity_mvs.py`（只解析，不刷库） | 目标清单解析出 **6** 个，顺序 = 候选集 → analytics → analytics 月度 → orders → orders 月度 → products |
| `temp/verify_identity_remediation_outcome.py` | 退出码 **2** + 明确报错「迁移尚未落库」⇒ **不会**在未落库时误判通过 |
| `temp/verify_reconcile_matches_migration.py`（只读） | 矛盾行 1,946 / 口径一致 **1,946** / 不一致 **0** / 无法确定 **0** |

### 13.8 落库完成（2026-11-07 04:0x，外部依赖已解除）

**触发**：product-center 会话把 `20261115` 合入 main（main HEAD = `f25b0b01`，
`main..feature/product-center-stage0` = 0 提交）⇒ 定时任务本轮自动续接。

**第二步实际无需执行** —— product-center 合并时已把 `20261116.down_revision`
改成 `current_schema_20261115_add_sku_platform_pricing`，链为
`20261114 → 20261115 → 20261116 → 20261117`，**单头**（`check_migration_chain.py` 退出码 0）。
⇒ 没有改文件、没有产生空提交。

**迁移落库**：开发库 `public.current_schema_alembic_version` 已是
`current_schema_20261117_remediate_shopee_row_identity_conflicts` ——
即 product-center 会话跑迁移时，把链上我这两个迁移**一并应用了**。
本次再跑守护入口为 no-op（`[OK] Current-schema migration action completed: upgrade`，退出码 0）。

**别名产物已确认落库**：`core.shop_account_aliases` 中 `source='shop_identity_remediation'` = **6 条**
（DAONE Mall / DAWIE Mall / Explorers Mall / Malaysia(Flora Mall) /
Philippines(DAJU Mall) / Singapore(HX Home)，区域全对）。

**验收结果**（`temp/verify_identity_remediation_outcome.py`，退出码 **0**，8 项全 OK）：

| 指标 | 订正前 | 实测 | 目标 | 判定 |
|---|---|---|---|---|
| unknown 行数 | 951 | **213** | 213 | OK |
| unknown UV | 117,181 | **8** | 8 | OK |
| ambiguous 行数 | 18 | **0** | 0 | OK |
| ambiguous UV | 8,409 | **0** | 0 | OK |
| 跨账号认领行数 | 1,946 | **0** | 0 | OK |
| 总行数 | 3,634 | **3,634** | 3,634 | OK |
| 总 UV | 683,497 | **683,497** | 683,497 | OK |
| 补录别名数 | 0 | **6** | 6 | OK |

⇒ **8,409 UV 的歧义行归零、1,946 行跨账号认领归零、720 行 TikTok 导出流量归位，
且总行数与总 UV 一字未动**（只改身份归属，不搬数据）。

#### 刷 MV 前的安全检查

刷之前先确认 6 个目标在库里都是 **物化视图**（`pg_class.relkind='m'`）——
`execute_sql_target` 对**普通视图**会改走资产文件路径，而资产文件里带
`DROP VIEW ... CASCADE`（历史上连删过 10 个对象）。确认后 6 个全走**原地 REFRESH**。

#### 本轮又暴露的第 4 个脚本缺陷（`refresh_identity_mvs.py`）

| 现象 | 根因 | 修正 |
|---|---|---|
| `ModuleNotFoundError: No module named 'backend'` | 脚本在 `temp/` 下直接运行 ⇒ `sys.path[0]` 是 `temp/` 而不是仓库根 | 显式把仓库根插进 `sys.path` |
| `ImportError: cannot import name 'AsyncSessionLocal' from 'modules.core.db'` | 入口写错了 —— 正确出处是 `backend.models.database`（与 `scripts/rebuild_views.py` 一致） | 改用 `from backend.models.database import AsyncSessionLocal` |

> 前三个缺陷在 §13.7 已记；这第四个是**真跑到那一步**才暴露的 ——
> 说明「脚本存在」不等于「脚本可跑」，交接脚本必须**真跑一遍**才算数。






