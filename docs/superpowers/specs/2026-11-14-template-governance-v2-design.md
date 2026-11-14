# 模板治理闭环 v2 设计（2026-11-14）

> 状态：**批次 0–4 已全部实施完毕**（2026-11-14）。
> 实施记录与验证证据见 **§7**；本文 §1–§6 保留原始设计推导，不回改。
>
> 上游文档：
> - 规格：`docs/superpowers/plans/2026-11-07-semantic-core-field-spec.md`（2026-11-07 业务拍板，核心字段 = 需求）
> - ADR：`docs/adr/2026-11-13-template-drift-classification-ssot.md`（判定口径 SSOT）
> - 复盘：`docs/reports/2026-11-13-template-governance-closure.md`（v7.26.0 发布记录）
> - 事故现象：TikTok 订单月报文件 `catalog_files.id=3059` 保存模板后仍提示「仍有字段对不上」

---

## 0. 一句话

**这次事故的根因不是某个函数写错，而是 2026-11-13（v7.26.0）新写的 L3 漂移判定入口，把一条基于过期技术事实的规则（「多一列 ⇒ 阻断 ⇒ 静默丢数据」）提升成了全系统 SSOT，与它下面的 L1/L2 两层、以及 11-07 的业务规格同时矛盾。** 修复方向不是推翻规则，而是**把口径拉回 11-07 规格**，并补上「模板决策资产版本化」与「闭环可观测」两块地基。

---

## 1. 证据链

### 1.1 规格原文（11-07 业务拍板）

`docs/superpowers/plans/2026-11-07-semantic-core-field-spec.md` §1.4：

| 情况 | 规格规定 |
|---|---|
| 核心字段变了（且是必填的） | **阻断**，等人处理 |
| 核心字段没变，只是**多了新列** | **不阻断，照常入库**；新列先原样存着，等有空再决定它是什么 |
| 列只是换了名字（含义没变） | **不阻断**，翻译层认出来即可 |

同文 §8 验收口径：「仅新增列 ⇒ **不阻断**，照常入库」。

§3.1「三处消费，一份真相」：

| 消费方 | 读什么 | 效果 |
|---|---|---|
| 落库列 | `core_fields` 全集 | 只为核心字段建物理列 |
| `data_hash` | `core_fields` 中 `in_hash=true` + 系统身份 | 指纹组成 |
| **漂移阻断** | `core_fields` 中 `required=true` ∪ 域级契约 required | **缺失才阻断** |

> ⚠️ **2026-11-14 更正（指纹口径）**：上表是 **11-07 规格原文的引用**，
> 其中 `data_hash` 那一行（「`core_fields` 中 `in_hash=true` + 系统身份」）
> **与当前实现不一致** ⇒ 引用保留原貌，但**不要照它改实现**。
>
> | 消费方 | 实际读什么（**权威口径**） | 实现位置 |
> |---|---|---|
> | `data_hash` | **模板去重字段表 `deduplication_fields`** + 系统身份 | `backend/services/deduplication_service.py:365`（`fields = list(deduplication_fields or entry_by_key.keys())`） |
>
> 为什么不能让清单决定 hash 字段集合
> --------------------------------
> 清单里的 `in_hash` **当前只是「一致性声明」** —— 由
> `backend/tests/data_pipeline/test_core_fields_hash_consistency.py`
> 保证与去重字段表**逐字一致**（27 个维度全查），它**不参与** hash 字段集合的构成。
>
> ⇒ 若改成「清单决定 hash 字段集合」：27 个维度的 hash 口径**全部变**
> ⇒ 已入库的行被当成新数据 ⇒ **又要一次全量重建**
> ⇒ 与 v7.29.3 修掉的 256 组重复行是同一类病。
>
> ⇒ 结论：**清单是声明，去重字段表是权威**；两者的一致性交给机器检查，
> 不靠「让实现去迁就规格」。

**规格里从来没有「多一列就阻断」这一条。**

### 1.2 现状：三层判定里只有 L3 与规格矛盾

| 层 | 位置 | 对「多一列」的态度 |
|---|---|---|
| L1 事实（表头比对） | `backend/services/template_matcher.py:1082-1084`（注释原文） | 「多一列 ⇒ **不阻断**（原始数据完整保留, 映射按列名走）」 |
| L2 语义契约 | `backend/services/semantic_field_contract_service.py:299-358` | 多出来的列进 `extra_raw_fields` ⇒ `NON_BREAKING_DRIFT` ⇒ `should_block=False` ⇒ **不阻断** |
| **L3 结论（SSOT）** | `backend/services/data_sync_status_semantics.py:468-474` | 多出来的列 ⇒ **blocking** ⇒ **阻断** |

⇒ **L3 是唯一与规格和上下两层都冲突的一层**，而它恰恰是 11-13 新引入的「唯一入口」。
⇒ 这次事故不需要新设计，只需要把 L3 改回 L1/L2/规格已经一致的那条口径。

### 1.3 代码内自相矛盾的注释（铁证）

同一次改动只改了 L3 的实现，**没改 L1 的注释**：

```python
# backend/services/template_matcher.py:1080-1086
# [*] L3: **唯一**的漂移判定入口。
#
# 业务口径(见 ``data_sync_status_semantics.classify_drift`` 文档):
#   多一列 ⇒ 不阻断(原始数据完整保留, 映射按列名走);      ← 指向 L3 文档
#   少了必填字段 / 值形态变了 ⇒ 阻断。
```

而 L3 的文档（`data_sync_status_semantics.py:267-290`）写的是：

```
# 业务口径(本模块是它的唯一实现)
# **多一列, 算问题 —— 直到模板把它纳入为止。**
```

⇒ **同一个口径，两处文档，一个说不阻断一个说阻断。**

### 1.4 「多一列会静默丢数据」这个前提已经过期

v7.26.0 的论证原文（`data_sync_status_semantics.py:271-282`）：

> 模板没声明的列**不会被写进事实表** ⇒ 放行等于**静默丢数据**。

批次 E/F 落地后，这个前提不成立：

| 事实 | 位置 |
|---|---|
| `raw_data` 存的是**整行原始数据**（所有列），不是模板声明的列 | `backend/services/raw_data_importer.py:834` |
| 核心字段清单生效时：**只为心字段建物理列；其余字段只进 `raw_data` JSONB 存档** | `backend/services/raw_data_importer.py:763-765` |
| 下游语义视图**全部**从 `raw_data->>'某列'` 取值（不依赖物理动态列） | `sql/semantic/*.sql`；护栏 `test_core_fields_storage_guardrails.py` 第 5 条 |

⇒ **新列的数据本来就不会丢，它原样躺在 `raw_data` 里。**

### 1.5 为什么这个回退躺了两天才被发现

| # | 原因 | 位置 |
|---|---|---|
| 1 | 守护测试**锁死了错误口径**：`test_added_column_blocks_until_template_catches_up` 断言「多一列 ⇒ 阻断」 | `backend/tests/data_pipeline/test_drift_classification_ssot.py:118` |
| 2 | 11-13 复盘自己写着「本机与生产都没有 `template_update_required` 的真实文件 ⇒ 端到端闭环仍需人工实测」 | `docs/reports/2026-11-13-template-governance-closure.md` §五.1、§七.5.2 |
| 3 | 缺一个指标：**模板发布后 T 分钟内受影响文件完成重估的比例** —— 没有它，闭环是否闭上只能靠人工点一次保存肉眼看弹窗 | — |
| 4 | 发布即重检的维度谓词未归一（`sub_domain='N/A'`），重检静默 0 命中、**一行日志都不打** | `backend/services/template_recheck_service.py:316, 333-334` |

---

## 2. 业务概念修正（Walter 已拍板）

### 2.1 四条边界

| # | 议题 | 结论 |
|---|---|---|
| B1 | 核心字段清单为空的维度 | **阻断并提示去配置**（不静默放行；符合规格 §7「定不了就报警」） |
| B2 | 新列不阻断后，已入库历史行不自动补列 | **接受该代价**，**不纳入本次**回填机制 |
| B3 | 模板进 Git 的形态 | **决策资产进 Git**（核心字段清单 / 别名 / 解析规则）；运行时状态留 DB |
| B4 | `data_hash` 的字段集合由谁决定 | **模板去重字段表**（权威）；清单的 `in_hash` 只是**一致性声明**，由机器检查保证逐字相同（§1.1 更正说明）。**不让实现去迁就 11-07 的规格原文** |

### 2.2 目标判定表（口径回退后的 SSOT）

| 情形 | 判定 | 理由 |
|---|---|---|
| 多一列（非核心） | **不阻断**，进 `non_blocking_changes` | 规格 §1.4；数据完整留在 `raw_data` |
| 少一列，核心字段 `required=false` | 不阻断 | 它不是需求 |
| 少一列，核心字段 `required=true` / 域级契约 required | **阻断** | 业务算不出要的数 |
| 少一列，无任何语义绑定（**清单已配置**） | **不阻断** | 不在清单里 ⇒ 不是需求 |
| 少一列（**清单为空**，B1） | **阻断**，文案明确「该维度还没定义核心字段清单」 | 配置缺口 ≠ 数据问题 |
| 值形态漂移（列名没变、值形态变了） | **阻断** | 入库必然整份失败 |
| 列改名（别名可救） | 不阻断 | 缺的是列名，不是数据 |

### 2.3 状态语义调整

`update_required`（模板待更新）的含义从「**列**对不上」收窄为「**核心字段**对不上」。
- **不新增状态**（避免牵动状态映射表、前端标签、守护测试）——复用 `TEMPLATE_STATUS_UPDATE_REQUIRED`；
- 通过 `reason` 文案区分两种阻断：**「核心字段缺失」** vs **「该维度尚未定义核心字段清单」**；
- 面板文案随之改（见批次 2）。

---

## 3. 分批实施

> 每批满足 `docs/guides/PRE_LAUNCH_RULES.md` 的范围要求：**解决的上线问题 / 预期改动的文件 / 刻意不动的模块 / 验证命令 / 回退方式**，且跨模块不超过 3 个主要模块。

### 批次 0：凭据清理（独立，可与批次 1 并行）

| 项 | 内容 |
|---|---|
| 上线问题 | `scripts/sync_templates_to_cloud.ps1:12` 把本地数据库密码**硬编码提交进仓库** |
| 改动文件 | `scripts/sync_templates_to_cloud.ps1`（参数化 + 从环境/`.env` 读取）、`.env.example`（如需） |
| 刻意不动 | 脚本的业务逻辑（导出/上传流程） |
| 验证 | `git grep -n "erp_pass" -- scripts/` 无命中；`-DryRun` 参数走通 |
| 回退 | 单文件还原 |

### 批次 1：闭环真 bug（不改业务口径）

| 项 | 内容 |
|---|---|
| 上线问题 | ① 发布即重检静默漏检（`sub_domain='N/A'`）⇒ 文件 15 分钟才自愈；② 保存接口吞掉 `recheck` ⇒ 前端拿不到三态；③ 文件级结论只写在 `covered` 行 ⇒ 面板误报「还有字段对不上」 |
| 改动文件 | `backend/services/template_recheck_service.py`、`backend/schemas/field_mapping_template.py`、`backend/domains/data_platform/routers/data_sync.py`、`frontend/src/domains/data_platform/views/DataSyncTemplates.vue` |
| 改动点 1 | `recheck_dimension`：`sub_domain`/`account` 先 `_normalize_dimension()` 归一（`'N/A'→None`），并改用 `template_matcher.match_dimension_condition` 构造谓词，与模板匹配/入库前置校验同一口径；**0 命中时补一行 INFO 日志** |
| 改动点 2 | `TemplateSaveData` 增加 `recheck: Optional[Dict[str, Any]] = None`（Pydantic 不再静默丢弃） |
| 改动点 3 | `data_sync.py` 覆盖统计：`needs_update` / `current_needs_update` 行也写 `sample_update_required`（文件级结论） |
| 改动点 4 | 前端：① 三态文案区分「用户待办 / 系统待办 / 已放行」；② 文件级结论查找范围补 `covered` 行；③ 去掉「取不到布尔值就当还对不上」的保守回退 |
| 刻意不动 | 漂移判定规则本身（批次 2）；`template_recheck_service` 的判定链路（复用 `get_file_sync_readiness`） |
| 验证 | **新建** `backend/tests/data_pipeline/test_template_recheck_dimension_filter.py`（覆盖 `sub_domain='N/A'` 必须能命中 `sub_domain IS NULL` 的文件、0 命中要有日志）；`pytest backend/tests/data_pipeline/test_drift_classification_ssot.py backend/tests/data_pipeline/test_core_fields_guardrails.py backend/tests/data_pipeline/test_format_drift_guardrails.py`；`pytest backend/tests -k "template or drift or recheck or governance"`；`npx vue-tsc --noEmit`；`npx vite build`；**端到端**：制造一个多列文件 → 保存模板 → 面板应立刻三态之一（不再等 15 分钟） |
| 回退 | 4 个文件逐个还原；改动点 3 可用 feature flag 回退 |

### 批次 2：口径回退（业务变更，需离线回放 + 开关）

| 项 | 内容 |
|---|---|
| 上线问题 | 多一列被阻断 ⇒ 每天的平台新列都会卡住整个维度（本次 TikTok 订单即中招）；与 11-07 规格矛盾 |
| 改动文件 | `backend/services/data_sync_status_semantics.py`（L3）、`backend/services/template_matcher.py`（传参）、`backend/services/data_sync_template_status_service.py`（编排/文案）、`backend/tests/data_pipeline/test_drift_classification_ssot.py`（守护）、`frontend/.../DataSyncTemplates.vue`（文案） |
| 改动点 1 | L3 `classify_drift` 规则 4：**多一列一律 non_blocking**（不再依赖 `confirmed_extra_fields` 才放行）；`DRIFT_RULE_IDS` 中 `added_column_blocks_until_template_catches_up` → `added_column_never_blocks`（仅 2 处引用，改名影响面可忽略） |
| 改动点 2 | L3 少列规则：`unmapped_removed_raw_fields` 在**清单已配置**时判 non_blocking；新增入参 `core_fields_configured: bool` |
| 改动点 3 | B1：清单为空 ⇒ 阻断，`reason` 明确「该维度尚未定义核心字段清单」（复用 `update_required` 状态，不新增状态） |
| 改动点 4 | `ignored_extra_fields` 语义降级：从「阻断豁免」变为「**已阅标记**」（不再决定能否放行，只用于面板去噪）；字段与 UI 文案同步 |
| 改动点 5 | 编排层：`update_required` 的 `reason`/文案改成「核心字段缺失」；「事后追平」判据（`data_sync_template_status_service.py:556-579`）在多列不阻断后的行为回归验证 |
| 刻意不动 | `raw_data` 存储模型、`ensure_columns_exist` 建列收窄、语义层 view（**数据层一律不动**） |
| 上线闸门 | ① **离线回放**（沿用规格 §6.1 方法论）：对存量 `catalog_files` + 样本行分别用旧/新口径算，产出「结论变化文件数 / 变化明细」报告；② 规则改动**显式开关**，可一键回退旧口径；③ 先在只读通道验证生产数据影响面 |
| 验证 | `pytest backend/tests/data_pipeline/test_drift_classification_ssot.py`（改写为「多一列不阻断」+ 新增「清单为空 ⇒ 阻断」+「核心字段缺失 ⇒ 阻断」三条行为断言）；`pytest backend/tests -k "template or drift or semantic_contract or core_field or governance or ingest"`；`python scripts/verify_architecture_ssot.py`；`npx vue-tsc --noEmit`；`npx vite build` |
| 回退 | 开关切回旧口径；`git revert` 本批提交 |

### 批次 3：模板决策资产进 Git

| 项 | 内容 |
|---|---|
| 上线问题 | 模板是运行时数据、靠 `pg_dump` 脚本拷环境（`scripts/sync_templates_to_cloud.ps1`）⇒ 各环境各一份、口径漂移无人察觉、版本号靠运行时递增（本次已跳号到 v12） |
| 形态 | **决策进 Git、状态留 DB**：核心字段清单 / 别名对齐 / 解析规则 / hash 参与列进仓库；`published` 指向、文件入库状态、契约指向留在运行时库 |
| 改动文件 | 新建 `templates/`（声明式定义）；新建投影脚本（`scripts/apply_template_definitions.py`，仿 Alembic 的「声明 → 投影」）；`scripts/sync_templates_to_cloud.ps1` 降级/退役；CI 守卫脚本 |
| 关键约束 | ① **只迁决策，不迁运行时状态**；② 生产可能有本机没有的真实数据推导列 ⇒ 采用**基线 + 环境 overlay** 两层，overlay 必须显式声明；③ 迁移期双轨：新定义投影后**校验等价**（列集合/核心字段/hash 参与列逐项比对）才切换 |
| 验证 | 投影幂等性测试（同一定义连投两次结果一致）；等价性校验脚本；`pytest backend/tests -k "template"`；CI 上跑「仓库定义 vs 库内实例」差异检查 |
| 回退 | 投影脚本只增不改或带 `--dry-run`；保留原 `pg_dump` 路径作为过渡期回退 |

### 批次 4：契约语义拆分 + 闭环可观测

| 项 | 内容 |
|---|---|
| 上线问题 | ① 契约字段同时承担「登记事实」与「现在该用哪版」，为保住新列数据必须改写审计事实；② 没有「发布后 T 分钟内完成重估」的可观测指标，闭环是否闭上只能靠人工点一次保存 |
| 改动点 1 | 契约：登记事实不可变；「当前应使用」另设字段（`template_contract` 只读留档 + 新增当前指向），存量数据回填（不改历史行） |
| 改动点 2 | 指标：`模板发布后 T 分钟内受影响文件完成重估的比例`（默认 T=5min）；重估 0 命中、无待更新文件也要计数，避免「静默成功」 |
| 验证 | 指标端到端跑一轮（改模板 → 观测指标）；契约回填前后 `catalog_files.file_metadata->'template_contract'` 对比 |
| 回退 | 新字段可空，旧逻辑读空时回退 |

---

## 4. 风险与副作用

| 风险 | 缓解 |
|---|---|
| 批次 2 口径回退放行更多文件 ⇒ 入库量上升 | 离线回放报告先行；开关可回退；先只读验证生产影响面 |
| 多列不阻断 ⇒ 新列的**语义接入滞后**（数据在 `raw_data`，但下游 view 不自动包含） | 明确记录为「待语义接入」清单，不阻断但可见（`non_blocking_changes`）；B2 已确认接受该代价 |
| 已入库历史行不会自动补物理列 | B2 已确认接受；如需回填另立任务，不混进本批 |
| 批次 3 迁决策资产可能与生产实际不符 | 基线 + overlay 两层；等价性校验后才切换；迁移期保留旧同步路径 |
| 本次诊断已产生模板版本跳号 v9–v12 | 记录在案；批次 3 的「决策资产版本化」正是该问题的根治手段 |

---

## 5. 验收口径

| 批次 | 验收标准 |
|---|---|
| 1 | 多列文件保存模板 ⇒ 面板**立刻**给出三态之一（不再等 15 分钟）；日志出现 `[TemplateRecheck] 维度重检完成 ... checked=N`；接口响应含 `recheck` |
| 2 | 「多一列」不再阻断；「核心字段缺失」仍阻断并给出「缺哪个、影响什么」；离线回放报告中结论变化文件均可解释 |
| 3 | 仓库定义可幂等投影进库；「仓库定义 vs 库内实例」差异检查在 CI 中为 0 |
| 4 | 契约登记事实不再被改写；「发布后 T 分钟内完成重估比例」指标可查且非 0 |

---

## 6. 与本次诊断的衔接

- 业务数据现状：文件 3059 已 `ingested`（204 行入库），契约指向 v11，漂移快照已清空；全库 `template_update_required` = 0（无待办积压）。
- 模板版本现状：`tiktok/orders/monthly` 已到 v12（`published`），内容与 Walter 的 v8 完全一致（186 列、`ignored_extra_fields=['商家成长服务费']`、同一 `format_signature`）；v9–v12 由诊断动作产生。
- 仓库工作树：干净（`git status --porcelain` 无输出），本次诊断未改动任何代码。

---

## 7. 实施记录（2026-11-14）

> 本节是**实际做了什么**与**验证到哪一步**的记录；上面的 §1–§6 是设计推导，保持原貌不回改。

### 7.1 各批次实际改动

| 批次 | 实际改动文件 | 刻意未动 |
|---|---|---|
| **0** 凭据清理 | `scripts/sync_templates_to_cloud.ps1`（整脚本重写为纯 ASCII、运行时解析凭据、修复 `$ProjectRoot` 多退一层） | 导出/上传流程本身 |
| **1** 闭环真 bug | `backend/services/template_matcher.py`（新增 `normalize_dimension_placeholder`）、`backend/services/template_recheck_service.py`（谓词归一 + 0 命中留痕）、`backend/schemas/field_mapping_template.py`（`TemplateSaveData.recheck`）、`backend/domains/data_platform/routers/data_sync.py`（`needs_update` 行补文件级结论）、`frontend/src/domains/data_platform/views/DataSyncTemplates.vue`（三态文案 + 查找范围 + 去掉保守回退） | 漂移判定规则本身（留给批次 2） |
| **2** 口径回退 | `backend/services/data_sync_status_semantics.py`（L3 SSOT 重写）、`backend/services/template_matcher.py`（`_required_raw_fields` / `effective_core_fields`）、`backend/services/data_sync_template_status_service.py`（传参 + `drift_origin` 与阻断解耦） | `raw_data` 存储模型、落库列收窄、语义层 view |
| **3** 决策资产进 Git | 新增 `templates/`（README + 27 份定义 + overlay 示例）、`scripts/template_definitions.py`（格式 SSOT）、`scripts/export_template_definitions.py`、`scripts/apply_template_definitions.py`、`.github/workflows/ci.yml`（新增 CI 步骤）；`scripts/sync_templates_to_cloud.ps1` 头部降级说明 | `scripts/sync_templates_to_cloud.ps1` 的功能（云端仍需完整模板表） |
| **4** 契约拆分 + 闭环指标 | `backend/services/template_contract_service.py`（登记事实 / 当前基准 / 晋升历史三分）、`backend/services/data_sync_template_status_service.py`（判定用当前基准、追溯用登记事实）、`backend/services/template_recheck_service.py`（晋升改写当前基准 + 闭环埋点）、`backend/services/cloud_sync_auto_recovery_service.py`、`modules/services/catalog_scanner.py`（写清「重新采集 vs 晋升」的边界）；新增 `scripts/template_release_sla_metric.py` | 表结构（**不需要 DDL 迁移**，见 §7.3） |

### 7.2 验证证据

| 验证 | 结果 |
|---|---|
| 批次 0 守护 | `test_powershell_repo_hygiene.py` **5 passed**（无硬编码凭据 / 纯 ASCII 无 BOM / GBK 代码页下 `ParseFile` 通过 / `scripts/` 下 `.ps1` 无 BOM） |
| 批次 1 守护 | `test_template_recheck_dimension_filter.py` **8 passed** |
| 批次 2 守护 | `test_drift_classification_ssot.py` + `test_data_sync_template_drift_service.py` + `test_contract_promotion.py` + `test_template_contract_service.py` **58 passed** |
| 批次 3 守护 | `test_template_definitions_guardrails.py` **16 passed** |
| 批次 4 守护 | `test_template_release_sla_metric.py` **10 passed** |
| **宽回归** | `pytest backend/tests -k "template or drift or semantic_contract or core_field or hash or contract or governance or ingest"` → **1688 passed / 3 skipped / 0 failed** |
| 静态门禁 | `ruff check`（本次新增/改动文件）**All checks passed**；`black --check` 22 files unchanged |
| 前端 | `npx vue-tsc --noEmit` exit=0；`npx vite build` **built in 20.91s**，exit=0 |
| 定义差异守卫 | `apply_template_definitions.py --check` → **27/27 完全一致，0 差异，退出码 0**；**负向验证**：人为翻转 `core_fields[0].required` + 截断 `header_columns` → 精确检出两类差异并返回退出码 1，恢复后回到 0 |
| 投影前置路径 | `apply_template_definitions.py --apply --dry-run` → 「仓库定义与库内实例一致, 无需投影」，退出码 0 |

> [!IMPORTANT]
> **后续修正（v7.29.2，2026-11-14 晚）**：上面两行的「27/27 完全一致」是在
> **本机开发库**上测的 —— 批次 3 的定义基线是从开发库导出的。
> 守卫真正装进生产镜像后（v7.29.1）第一次运行就报 **6 个维度不一致**：
> 开发库与生产库本来就不一样，而且开发库的 `tiktok/orders/monthly` 是
> §6 说的**诊断产物**（186 列 / `ignored_extra_fields=['商家成长服务费']`），
> 生产真实文件与生产模板都只有 184 列。
> ⇒ **基线已改从生产库重新导出**（6 份替换，其余 21 份字节级一致），
> 上线后生产 `--check` ⇒ 27/27 一致、退出码 0。
> ⇒ 本机开发库与仓库定义**继续不一致**（正常），不要拿开发库的 `--check` 当生产结论。
> 详见 `CHANGELOG.md` v7.29.2 与 `docs/guides/TEMPLATE_GOVERNANCE_V2_RUNBOOK.md` §4.5.3。

### 7.3 口径回退与契约拆分的影响面（离线回放）

回放脚本：`scripts/replay_drift_caliber.py`（**只读**，同一批文件、同一批表头，两套口径各跑一遍）。

| 指标 | 结果 |
|---|---|
| 评估文件数 | **497** |
| 结论不变 | **497**（口径回退对存量数据**零影响**） |
| 旧口径阻断 / 新口径阻断 | 75 / 75 |
| 新放行（旧阻断 → 新可入库） | **0** |
| 新阻断（旧可入库 → 新阻断） | **0** |
| 含新增列的文件 | 148 |
| 含缺失列的文件 | 98 |
| 必填语义键缺失 | 0 |
| 值形态漂移 | **75**（现存阻断**全部**来自值形态漂移，与本次口径变更无关） |
| 纯多列文件 | 54（其中旧口径阻断 **0** —— 这些列早已在「已确认的新列」清单里，故新旧口径都不阻断） |

**这个「零影响」结论有硬证据，不是脚本失效造成的假象**：

- 探针自检：`两套口径对「多一列」结论不同 = True`（口径确实生效）；
- 构成统计显示存量里**没有一个「多列且未被确认」**的文件 ⇒ 口径回退在存量上不可能改变结论；
- 契约拆分实施后**再跑一遍**，数字与上表**逐项一致** ⇒ 契约拆分同样对存量判定零影响。

> 回放脚本的前两轮结果曾是**假象**（patch 目标打在模块而非使用方属性、判定键取错），
> 第三轮修正后才得到上表；上表数字以修正后为准。

**关于「存量数据回填」**：批次 4-1 原计划新增列并回填。实施后确认**不需要**：

- `template_contract_current` 是 `catalog_files.file_metadata`（JSONB）内的**键**，不是新列 ⇒ 无 DDL 变更 ⇒ 不需要走 `scripts/run_current_schema_migrations.py`；
- 判定链路读「当前基准，缺失则回退登记事实」，而存量 **497 个文件里带 `template_contract_current` 的为 0** ⇒ 判定结果与拆分前**完全一致**；
- 实测存量仅 **1 个**文件被契约晋升过（`source=contract_promotion`），其**原始登记版本在旧实现里已被覆盖、无法还原** ⇒ 回填也补不回来，只能靠「登记事实从此不再被改写」保证今后不再丢。

⇒ 故批次 4-1 **没有产生任何数据库写入**，也**没有新增迁移风险**。

### 7.4 闭环指标为什么「当前无数据」

`scripts/template_release_sla_metric.py` 的口径：

- **发布事件** = 模板表的一行（保存模板 = 归档旧 + 插入新，新行 id 自增 ⇒ 每个模板行唯一对应一次发布），时刻取 `created_at`；
- **重估记录** = `file_metadata.auto_ingest.last_recheck_at`（重估时刻）+ `last_recheck_template_id`（重估时生效的模板 id = 对应的发布事件）。

实测：**261 个发布事件、0 条可用重估记录 ⇒ 闭环比例 = 无数据**。原因有二，均已如实报告在脚本输出里：

1. 埋点（`last_recheck_at` / `last_recheck_template_id`）是本批**新增**的，存量文件没有；
2. 存量 278 个带 `auto_ingest` 的文件里，只有 25 个有 `last_rechecked_at`、9 个有 `last_recovered_at`，且 `last_status` 分布是 `claimed=276 / auto_enqueued=2` ⇒ **生产上重检闭环几乎没跑过**，且没有一个能说清「针对哪次发布重检」。

⇒ 指标**从下一次真实的模板发布开始才有数**。脚本坚持把「无数据」与「达标」分开计数，**绝不**把没数据算成按时完成（守护测试 `test_events_without_recheck_records_are_not_counted_as_on_time` 锁死这一点）。

### 7.5 副作用与未完成项（如实披露）

| # | 事项 | 状态 |
|---|---|---|
| 1 | **模板版本跳号 v9–v12**（`tiktok/orders/monthly`） | 诊断动作产生，内容与 v8 完全一致。批次 3 已把**决策内容**纳入 Git，但**版本号仍是 DB 运行时状态** ⇒ 跳号本身未根治 |
| 2 | **硬编码凭据已从公开仓库清除** | 该密码曾在公开仓库里 ⇒ **应视为已泄露**，建议轮换（属运维动作，本会话未做） |
| 3 | `scripts/` 下存量 `.ps1` 含中文但 GBK 下恰好解析通过 | 属运气好；已记为 V2 技术债（仓库形态约定为无 BOM，但未强制「纯 ASCII」） |
| 4 | `scripts/` 目录存量 ruff 告警 138 处 | 存量问题，按预发布期规则不处理，记 V2 |
| 5 | `apply_template_definitions.py --apply` 的**写库路径未在真实库实测** | 避免产生 v13 之类的又一次版本跳号；已验证前置逻辑（dry-run 正确报告「无需投影」）与代码路径存在，**写库路径需在有版本跳号许可的环境里先试一次** |
| 6 | 采集侧容器仍是旧镜像且当前 `Exited(137)` | **本会话不动容器**；需要单独决策（重建/重启采集侧 worker 与 beat）才能让批次 1/2 的修复在采集链路生效 |
| 7 | 闭环指标在真实发布后才有数 | 见 §7.4 |
| 8 | **实施中发现并修掉一个潜伏 bug** | `TemplateRecheckService.apply_recheck` 是 `@staticmethod`，却写成 `self._promotion_note(...)`。该表达式只在**真的发生契约晋升**时才求值 ⇒ 平时所有用例都绿，等第一次晋升就会 `AttributeError`。已改为类名调用，并补了「发生晋升」的守护用例（`test_recheck_with_contract_promotion_records_promotion_history`）。**这是本批差点漏到线上的问题** |

### 7.6 V2 技术债清单

1. `scripts/` 全量 ruff 清理（138 处存量告警）；
2. 仓库形态 `.ps1` 统一为纯 ASCII（当前只有 `sync_templates_to_cloud.ps1` 达标）；
3. 模板**版本号**也进 Git（当前只有决策内容进 Git，版本仍是运行时状态）；
4. 契约晋升历史的可查询界面（当前只在 `file_metadata` 里留痕）；
5. 闭环指标接入监控告警（当前只有只读脚本，无阈值告警）。
