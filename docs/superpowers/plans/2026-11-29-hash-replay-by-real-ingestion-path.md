# 批次 E 前置 · 新旧口径 hash「按实跑路径」的回放报告

- 日期：2026-11-29
- 范围：口径开关 `SYNC_CORE_FIELDS_HASH_ENABLED`（默认**关闭**，本次**不开**）
- 结论先行：**切换会改写已入库行的 `data_hash` ⇒ 翻开关前必须先回填**，不能静默双写

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

见下方「回放结论」小节（由 `python scripts/replay_core_fields_hash.py` 产出）。

### 3.1 字段集合对比（口径切换的根因）

`data_hash` 的键集合 = 参与 hash 的字段名清单。旧口径来自 `deduplication_fields`
（含平台/店铺/日期等**自动追加**的维度字段），新口径来自**核心字段清单**。
两者**字段数与成员都不同** ⇒ 键集合不同 ⇒ **hash 必然变化**。

---

## 4. 回填方案（待执行，本次不执行）

> 前提：`SYNC_CORE_FIELDS_HASH_ENABLED` 保持**关闭**。

### 4.1 步骤

1. **圈定范围**：按回放报告列出的维度，找出受影响的已入库文件与其入库时间窗；
2. **备份**：把受影响行的 `(id, data_hash)` 备份到临时表（回填前必须可回滚）；
3. **重算**：用**与回放同一个函数**（`compute_ingestion_data_hashes`，开关置开）重算这些文件的行 hash，
   生成 `(id, new_data_hash)` 清单；
4. **校验**：新旧清单逐行比对，**只允许 hash 不同的行**进入回填清单；
   若某行新旧相同（键集合虽不同但取值恰好一致），不必动它；
5. **回填**：`UPDATE <fact_table> SET data_hash = :new_hash WHERE id = :id;`
   —— 分批 + 事务，每批提交后校验受影响行数；
6. **复跑**：回填后重跑 `python scripts/replay_core_fields_hash.py`，确认「口径切换 hash 变化」归零。

### 4.2 风险点

- **新口径可能命中「一行多粒度」**：新口径字段更少（见 3.1），若核心字段选得不够细，
  不同明细行可能算出**同一个 hash** ⇒ 去重会把它们当成重复行而丢数据。
  回填前必须先看新口径下的 hash 唯一率（回放报告里的「前 10 行 hash 相同」告警正是这个信号）。
- **事实表与幂等键**：回填只改 `data_hash`，不改业务字段；但如果业务上有依赖 `data_hash` 做 UPSERT 的
  逻辑，回填期间要注意幂等表的唯一键冲突。
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
