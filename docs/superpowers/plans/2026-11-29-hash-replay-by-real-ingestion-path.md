# 批次 E 前置 · 新旧口径 hash「按实跑路径」的回放报告

- 日期：2026-11-29
- 范围：口径开关 `SYNC_CORE_FIELDS_HASH_ENABLED`（默认**关闭**，本次**不开**）
- 结论先行：**实测 1094 行，口径切换后 `data_hash` 变化 0 行 ⇒ 无需回填**。
  但有 2 个**独立于本次改造**的存量问题被回放暴露出来（见 §3.2）。

---

## 1. 为什么必须重做（早先版本的回放不能作数）

早先的 `scripts/replay_core_fields_hash.py` **自己拼** hash 的字段集合再调 `batch_calculate_data_hash`，
与真实入库路径（`backend/services/data_ingestion_service.py`）有 **三处对不上**：

| # | 早先回放 | 真实入库路径 | 后果 |
|---|---|---|---|
| 1 | 没传 `identity_values` | `_build_hash_identity_values(...)` + `merge_hash_identity_values(...)`（auto-date 身份 + orders 身份值） | 回放的 hash 输入里**少了身份维度**，行级差异结论失真 |
| 2 | `core_fields` 用 `derive_core_fields(...)` 推导；`field_parse_rules` 取自 `variants` 表 | `core_fields` / `field_parse_rules` 取自 **`core.field_mapping_template_versions`** 版本行 | 回放用的清单与线上真正生效的清单**不是同一份** |
| 3 | 没有 orders 域的 `prepare_orders_rows_for_b_class` 行改写 | orders 行在算 hash 前会被改写并产出 `orders_identity_values` | orders 域的 rows 与线上不同 ⇒ hash 不可比 |

所以旧回放**证明不了**新口径的等价性。本次的动作是：把 hash 计算抽成**入库路径与回放共用的一个函数**，
再按该函数重做回放。

---

## 2. 本次改造：单一事实源

### 2.1 抽出公共函数

新增 `backend/services/data_ingestion_service.py::compute_ingestion_data_hashes(...)`
（返回 `IngestionHashResult`），把下面这些**原本散在入库流程里的步骤**收敛到一处：

- 口径字段集合：`get_deduplication_fields(...)` + `append_auto_date_identity_fields(...)`
- orders 行改写：`prepare_orders_rows_for_b_class(...)` + `extend_orders_deduplication_fields(...)`
- 身份维度：`_build_hash_identity_values(...)` + `merge_hash_identity_values(...)`
- 批次 E 开关判定：`core_fields_hash_enabled()` → `effective_core_fields`

入库路径（`DataIngestionService`）改为调用它，回放脚本也调用它 ⇒ **结论与实跑天然同源**，
以后入库口径再变，回放不会漂移。

> 行为等价性：入库路径调用前后的 `data_hash` 计算逻辑逐行未变，只是搬进了公共函数；
> `valid_rows`（orders 改写后）、`final_deduplication_fields`、`hash_identity_values` 由函数返回给调用方继续使用。

### 2.2 重写回放脚本

`scripts/replay_core_fields_hash.py` 重写为：

1. 从 `core.field_mapping_template_versions` 取**版本行**的 `deduplication_fields` / `header_bindings` /
   `core_fields` / `field_parse_rules`（与入库同一份来源）；
2. 按 `(platform_code, data_domain, granularity)` 找**真实已入库文件**（`public.catalog_files`）；
3. 用与入库一致的读表 + 规范化方式读出数据行；
4. 在**同一进程内**分别以「开关关」「开关开」两种状态各走一次
   `compute_ingestion_data_hashes(...)`，比对行级 `data_hash`；
5. 输出逐维度结论 + **回填方案**（只出方案，不执行）。

脚本**不会**改任何持久化配置，只在进程内临时设置/恢复环境变量；
`SYNC_CORE_FIELDS_HASH_ENABLED` 在生产仍是关闭状态。

---

## 3. 回放结果

实跑回放（`python scripts/replay_core_fields_hash.py --limit 50`，2026-11-29）：

```
实跑回放合计: 1094 行, 口径切换后 hash 变化 0 行
```

- 覆盖模板版本 **31 个**，其中 **22 个维度有已入库文件可回放**（合计 1094 行）；
- 每个维度都做了**两次自检**（同一开关状态下算两遍必须一致）⇒ 结果稳定，无隐藏状态；
- 结论：**切换到 `core_fields` 不会改任何一行的 `data_hash`**。

### 3.1 为什么字段数不同、hash 却不变

日志里能看到两套口径的字段**数量**确实不同（例如 shopee/products/monthly：旧口径 10 项、新口径 6 项），
但 hash **逐行相同**。原因在 `backend/services/core_fields_service.py` 的设计里已经写明：

- **键集合**仍由旧口径决定 —— `batch_calculate_data_hash` 的入参 `deduplication_fields`
  依旧是完整的字段链（含 `get_deduplication_fields` 自动追加的 `platform_code` / `shop_id` /
  `metric_date` / orders 扩展 / `_source_line_index` 等维度字段）；
- **取值方式**才由清单驱动 —— `core_fields` 只决定「从清单里取哪些值、按什么语义取」，
  且规则是「**逐字优先, 语义兜底**」：键名取 `raw_name` 优先，所以旧口径能逐字取到的值**一模一样**。

即：**切换只改「怎么取」，不改「取哪些键」** ⇒ 键不变、值不变 ⇒ hash 不变。
（若平台改了列名导致旧口径**丢掉**某字段，清单口径才会把它救回来 —— 这正是清单的价值。）

> ⚠️ 早先的回放脚本因为**自己拼字段集合**，把「字段数不同」当成了「键集合不同」，
> 从而得出「切换会改 hash、要回填」的**错误结论**。本次按实跑路径重做后结论反转。
> 这也说明：**回放必须与实跑同源**，否则结论不可用。

### 3.2 回放暴露的两个存量问题（与本次改造无关，但必须登记）

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| 1 | **shopee/services 的三个模板版本解析规则与文件列名对不上** | 回放报 `[date_format_mismatch] failed to parse metric_date from source_column=日期: None`（版本 1 / 53 / 60 用 `metric_date`，而文件里是「日期」/「日期期间」） | 这些版本**入库会直接失败**；换用「日期期间」那个版本（21 / 55 / 59）即可正常回放 |
| 2 | **部分文件在旧口径下「前 10 行 hash 相同」** | `shopee/analytics/daily`、`tiktok/products/monthly`（`e0536bad...`） | **存量**去重粒度问题：这些文件的明细行算不出不同 hash，去重会把它们当重复行。**先于本次改造存在**，新口径下同样存在 |

> 问题 2 说明「清单口径字段更少」本身也有风险：若核心字段勾选得不够细，
> 同一文件内多行会得到同一个 hash。回填/切开关前应先看**新口径下的 hash 唯一率**。

## 4. 回填方案

> 前提：`SYNC_CORE_FIELDS_HASH_ENABLED` 保持**关闭**。

**本次结论：不需要回填**（口径切换不改 hash）。

若后续口径再变、需要回填，步骤如下（只出方案，不执行）：

1. **圈定范围**：按回放报告列出的维度，找出受影响的已入库文件与其入库时间窗；
2. **备份**：把受影响行的 `(id, data_hash)` 备份到临时表（回填前必须可回滚）；
3. **重算**：用**与回放同一个函数**（`compute_ingestion_data_hashes`，开关置开）重算这些文件的行 hash，
   生成 `(id, new_data_hash)` 清单；
4. **校验**：新旧清单逐行比对，**只允许 hash 不同的行**进入回填清单；
5. **回填**：`UPDATE <fact_table> SET data_hash = :new_hash WHERE id = :id;`
   —— 分批 + 事务，每批提交后校验受影响行数；
6. **复跑**：回填后重跑 `python scripts/replay_core_fields_hash.py`，确认「口径切换 hash 变化」归零。

### 4.1 风险点

- **新口径可能命中「一行多粒度」**：新口径字段更少（见 3.1），若核心字段选得不够细，
  不同明细行可能算出**同一个 hash** ⇒ 去重会把它们当成重复行而丢数据。§3.2 问题 2 已经是实证。
- **回填与采集并发**：回填窗口内应暂停该数据域的入库任务，避免新旧 hash 混写。

---

## 5. 遗留（V2）

- `core_fields_service.RESTOCK...` 等 Python 阈值与数据库阈值是两份拷贝，靠守护测试锁一致（见库龄分档改造）；
  hash 口径同理 —— `core_fields` 清单（DB）与 `derive_core_fields`（推导）并存，建议后续收敛为单一来源。
- `a_class.operating_costs` 的 `server_default=text("'[]'::jsonb")` 无法在 SQLite 建表，
  任何在 SQLite 上做全量 `create_all` 的测试都会踩到（测试侧已按既有约定排除该表）。

---

## 6. 复现方式

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
$env:DATABASE_URL='postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp'
python scripts\replay_core_fields_hash.py            # 实跑回放
python scripts\replay_core_fields_hash.py --static-only   # 只做静态盘点
```
