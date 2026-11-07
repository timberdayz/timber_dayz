# 最终工作方案：模板 / 同步模块根治

> 生成时间：2026-11-07 15:19
> 仓库：`F:\Vscode\python_programme\AI_code\xihong_erp`
> 工作区：main（干净，`a15e5db3`）｜`feature/shop-disabled-scope-cleanup`｜`feature/semantic-core-field-refactor`
> 本文档是**可执行总方案**：问题 → 决策 → 目标形态 → 批次任务 → 验收 → 风险。技术细节下沉到专项文档（§10）。

---

## 0. 结论摘要

**我们要在做的，不是修几个 bug，而是把「同一件事被记了好几份」这件事收掉。**

最终形态：**一个数据域 = 1 份标准字典 + 1 个 active 版本 + ~6 个变体**；用户在一个可视化页面审一次，
勾两件事（**我要哪些数据** / **哪些参与去重**），此后平台改列名系统自动认、配置过期在保存时就拦、数据落库只为真正需要的字段建列。

---

## 1. 要解决的 5 个问题（业务语言）

| # | 业务现象 | 真实后果 | 技术锚点 |
|---|---|---|---|
| **P-1** | 店铺已停用，但仍留在采集配置和模板里 | 界面误导、整行勾不了、用模板新建配置报 400；数据本身安全 | `collection_config.py` / `shop_accounts.py` / scope 表 |
| **P-2** | 平台换个说法，同一份业务数据系统就不认 | 翻译命中率 **3~6%**；用户审一次不沉淀、换模板要重审；去重失效 ⇒ **重复入库** | `semantic_field_registry.py` + `headerBindings.js` 双副本 |
| **P-3** | 平台把日期格式的斜杠改成横杠 | Shopee 流量域**整文件入不了库**，该域**连续 4 个月无新数据**（7~9 月没采、10~11 月全失败） | `shopee_analytics__monthly_slash_v3` 声明 `dd/mm/yyyy` vs 实际 `dd-mm-yyyy` |
| **P-4** | 「哪些字段是重要的」有两套标准 | 用户勾的 `deduplication_fields` 与系统判漂移的 `required` 契约**互不相认**；3/5 个域**没有契约 ⇒ 漂移无人管** | `deduplication_fields` vs `core.semantic_field_contracts` |
| **P-5** | 改了这么多，还没在生产跑过一次完整链路 | 全是"测试通过"，**没有端到端证据** | — |

---

## 2. 已拍板的决策（不可再讨论）

| # | 议题 | 结论 | 影响 |
|---|---|---|---|
| **D-1** | 指标类字段能否参与 `data_hash` | **能**，放开为自由勾选 | 改 `semantic_hash_policy_service.py:103-111` 的 metric 硬禁 |
| **D-2** | `hash_participates` 字段 | **删除该字段**；「参与去重」搬到核心字段清单 | 删 `field_mapping_templates.py:829/949` + 前端 3 处 |
| **D-3** | 用户手动对齐的别名沉淀范围 | **全局沉淀，一处生效** | 新建 `core.semantic_field_aliases` |
| **D-4** | 「哪些字段缺失才算阻断」归属 | **并入核心字段清单**；域级契约表降为**下限护栏** | `core.semantic_field_contracts` 保留但不独立 |
| **D-5** | 批次 A 的落地方式 | **走既有模板更新工作台改配置，不写迁移** | 前提：先修 FE-4 |

---

## 3. 目标形态

```
┌─ 翻译层（全局唯一、只增不改）────────────────────────────┐
│  列名 → 标准字段                                         │
│  来源：registry（代码内权威）+ core.semantic_field_aliases │
│        （用户手动对齐沉淀，全局生效，冲突即报警）          │
└──────────────────────────────────────────────────────────┘
              ↓
┌─ 模板层（一个数据域一份，审一次）────────────────────────┐
│  族 family      = 域级：标准字典 + 核心字段清单           │
│  版本 version    = 不可变快照（core_fields 在这里）        │
│  变体 variant    = 文件形态差异（平台×粒度×子域）        │
│                                                       │
│  核心字段清单 core_fields:                              │
│    [{semantic_key, required, in_hash}]                 │
│      全集     → 落哪些库列                             │
│      in_hash  → data_hash 的组成                       │
│      required → 漂移是否阻断                           │
└──────────────────────────────────────────────────────────┘
              ↓
┌─ 同步层 ────────────────────────────────────────────────┐
│  解析（field_parse_rules，变体级）→ 身份盖章 → 指纹 → 落库 │
│  指纹 = 语义归一后的核心字段值 + 平台/店铺/域/粒度        │
│  落库：只为 core_fields 建物理列，其余只进 raw_data 档案   │
└──────────────────────────────────────────────────────────┘
```

---

## 4. 批次任务（7 个批次）

### 批次 A · 日期止血（**先做，前端为主**）

| 项 | 内容 |
|---|---|
| **目标** | Shopee 流量域恢复入库，止住 4 个月数据断档 |
| **A-1 前端** | `templateFieldParseRules.js:57-76` —— `COMPANION_AUTO_DATE_FORMAT_CANDIDATES` 从「全部 18 个」收窄为**按语义族分组**：日期单值给 `["yyyy-mm-dd","yyyy/mm/dd","dd-mm-yyyy","dd/mm/yyyy","mm-dd-yyyy","mm/dd/yyyy"]`；同时保留"用户可手动增补候选"入口 |
| **A-2 前端** | `templateFieldParseRules.js:31-55` —— `DATE_FORMAT_OPTIONS` 补齐后端已有但前端缺失的区间格式（`yyyy-mm-dd-yyyy-mm-dd`、`yyyy/mm/dd-yyyy/mm/dd`） |
| **A-3 后端** | `field_mapping_templates.py:1041-1086` `_validate_field_parse_rules` —— 校验 `date_format` ∈ 后端白名单 ∪ `{auto_by_companion_period}`；并校验 `format_candidates` 每项都在白名单内 |
| **A-4 配置** | 在模板更新工作台把 `shopee_analytics__monthly_slash_v3` 的 `metric_date` 规则改成「系统根据伴生周期自动判断」并保存（走既有"保存即发布、version=max+1、旧行归档"） |
| **A-5 验证** | 用 4 个真实失败文件样本离线回放 ⇒ 唯一匹配、无歧义；再实跑入库，`max(metric_date)` 推进到 2026-11 |
| **验收** | 4 个 failed 文件入库成功；`metric_date` = 2026-10-01 / 2026-11-01 |
| **依赖** | 无 |
| **风险** | **无回填风险**（该模板至今 0 行落库）。回滚 = 把模板改回原格式 |
| **实测依据** | `date_from/date_to` 480/480 全填充；历史 1748 行 `metric_date` **0 行**越界 ⇒ 期间消歧不误杀 |

### 批次 B · 护栏（让过期配置提前暴露）

| 项 | 内容 |
|---|---|
| **B-1** | 保存闸门：**用样本行试解析一次**，解不出直接拒绝保存（`field_mapping_templates.py:1041` 段） |
| **B-2** | 漂移检测加**值形态维度**：`template_matcher.detect_header_changes` 抽 N 行样本验证声明格式 ⇒ 解不出判 **`format_drift`**（新状态） |
| **B-3** | 状态词汇新增 `format_drift`（`data_sync_status_semantics.py`），并在 `data_sync_template_status_service.py:373-391` 定级、`_is_blocking_header_change:428` 接入 |
| **B-4 前端** | `TemplateGovernancePanel.vue` + `TemplateNeedsUpdateTable.vue` 显示格式漂移（**API-4**） |
| **B-5 前端** | `syncTaskErrorParser.js` 解析结构化错误码（**API-7**）：区分「格式不匹配」/「日期超出文件期间」/「歧义」 |
| **验收** | 故意把模板改成 `dd/mm/yyyy` 再存 ⇒ **保存被拒**；文件格式变了不换模板 ⇒ 治理面板报 `format_drift` 而非入库时炸 |
| **依赖** | A（模板本身得先合法） |

### 批次 C · 日期解析收口（7 套 → 2 套）

| 项 | 内容 |
|---|---|
| **C-1** | 入库路径**只允许**严格声明式（`parse_date_by_declared_format`）；宽松解析器降级为**探测/预览专用** |
| **C-2** | `smart_date_parser.py:126-139` `_parse_explicit_year_position_date` 强制 day-first ⇒ 改「不确定 ⇒ 落 unknown + **报警**」；`detect_dayfirst:77-101` 在 a、b 都 ≤12 时返回 `None` ⇒ **不再猜** |
| **C-3** | `data_standardizer.py:471-472`、`:545-546` 硬编码 `prefer_dayfirst=True` 去除 |
| **C-4** | 其余 4 套日期解析（`data_validator.py:83`、`data_validator_v2.py:40`、`source_freshness_service.py:343`、`type_detector.detect_date_range_format`）**统一委派**给唯一实现 |
| **C-5** | 守护测试：锁住「只有严格声明式能进入库路径」 |
| **验收** | 「11/01/2026」在不确定时**落报警**而非静默按 day-first 解 |
| **依赖** | B |

### 批次 D · 翻译层扶正（**命中率 3~6% → ≥60%**）

| 项 | 内容 |
|---|---|
| **D-1** | 别名匹配从**逐字相等**升级为**归一化 + 域限定 + 值形态**（纯算法）：`semantic_field_registry.normalize_semantic_key` + `resolve_semantic_value:569` |
| **D-2** | 新建 `core.semantic_field_aliases`（raw_name → semantic_key + source + origin + `enabled` + 审计）；**冲突不静默覆盖**，落 `conflict` + 报警 |
| **D-3** | 用户在模板里手动对齐 ⇒ **自动沉淀**到全局别名表（走 D-3 决策） |
| **D-4 后端** | 新增「标准字段定义」只读接口（**API-1**）：标准字段 + 别名 + `required` + `hash_eligible` + 域适用范围 |
| **D-5 前端** | `headerBindings.js` **删副本**改从接口取 ⇒ 一次性消解 FE-1 / FE-2 / FE-5 |
| **D-6 前端** | 新增「别名裁决」界面（**API-5**）：同名列名撞不同含义时当场裁决 |
| **D-7** | 命中率护栏测试（4 个实测域各留基线） |
| **验收** | shopee/products/monthly 0 → ≥60%；miaoshou/inventory/snapshot 0 → ≥60%；全域 ≥60%；用户对齐一次 ⇒ **其它模板自动命中** |
| **依赖** | 可与 A/B/C 并行 |

### 批次 E · 核心字段清单（一份清单管三件事）

| 项 | 内容 |
|---|---|
| **E-1** | `core.field_mapping_template_versions` 新增 JSONB 列 `core_fields` = `[{semantic_key, required, in_hash}]`（**版本级**；变体共享 ⇒ 审一次全变体生效） |
| **E-2** | 迁移 27 个 published 模板：`deduplication_fields` → `core_fields`（`in_hash` 全继承；`required` 取 registry 值 + 域级契约 required） |
| **E-3** | `hash_participates` 下线（D-2）：删后端 `field_mapping_templates.py:829/949` + 前端 `headerBindings.js:544/615/659` + `TemplateUpdateWorkbenchDrawer.vue:817` |
| **E-4** | `hash_eligible` 口径放开（D-1）：`semantic_hash_policy_service.py:103-111` 的 metric 硬禁改为「能否唯一标识一行」 |
| **E-5** | 三处消费接线：`ensure_columns_exist`（落库列）、`calculate_data_hash`（指纹）、契约判定（阻断） |
| **E-6 前端** | `DeduplicationFieldsSelector.vue` **拆成两级勾选**（**API-2**）：「我要哪些数据」+「哪些参与去重」；组件标题从「Data Hash 字段确认」改为业务语言 |
| **E-7 前端** | 保存闸门错误引导（**API-3**）：说清「缺哪个 / 影响什么 / 怎么改」 |
| **E-8** | `field_parse_rules` **上移到 versions 表**（与 `core_fields` 同级）；变体级只留 `header_row` / `sheet_name_pattern` / `required_headers` |
| **验收** | 一份清单同时决定落库列 / 指纹 / 阻断；前端两级勾选可用 |
| **依赖** | B（护栏先行） |
| **⚠️ 前置** | **必须先做新旧口径 hash 离线回放**，产出「hash 变化/不变行数」报告；hash 变化的行给重算与回填方案，**不做静默双写**；切换做成显式开关，可一键回退 |

### 批次 F · 落库列收窄 + 漂移口径统一

| 项 | 内容 |
|---|---|
| **F-1** | `dynamic_column_manager.py:156` `ensure_columns_exist` 只按 `core_fields` 建列；历史已建列**保留读兼容**，不物理删 |
| **F-2** | 非核心字段只进 `raw_data` JSONB；`raw_data_importer.py:1436-1469` 不再对非核心列 UPDATE |
| **F-3** | `core.semantic_field_contracts` 粒度补齐（orders/daily、analytics/weekly），不再依赖常量兜底；角色降为「域级下限护栏」，约束「模板级 required ⊇ 域级 required」由守护测试锁住 |
| **F-4** | `extra_raw_fields` 噪音治理：新增「已确认的新列」忽略清单（**API-6**）+ 前端勾选入口（**FE-8**） |
| **F-5 前端** | 治理面板显示格式漂移与可忽略列（API-4 / API-6） |
| **验收** | 非核心字段不建物理列；治理面板无永久噪音；3/5 无契约域补齐 |
| **依赖** | E |
| **⚠️ 注意** | 下游 `semantic` view 用 `UNION ALL` 拼同构原始表 ⇒ 列结构变化会**影响 view 定义**，必须同步走迁移 + 守护测试 |

### 批次 G · 变体归位（族 24→5）

| 项 | 内容 |
|---|---|
| **G-1** | 族维度从 `platform×domain×sub_domain×granularity×account` 收敛为**数据域级**（去掉 `account` ⇒ 账号从 12 涨到 44 模板数不变） |
| **G-2** | 变体承载**业务形态差异**（列集合不同 / 解析方式不同 / 表头行不同），不再按文件名分隔符切分（`daily_dash`/`monthly_slash` 这类 `variant_key` 退役） |
| **G-3 前端** | `VariantCreateWorkbenchDrawer.vue` 改为按业务维度建变体 |
| **验收** | 5 个族 / 5 个 active 版本 / ~30 个变体；账号数变化不影响模板数 |

---

## 5. 执行顺序与关键路径

```
批次A-前端(FE-4,FE-5) ──┬──▶ 批次A-配置(走UI) ──解锁──▶ 端到端验证
主线1合入(D-1拍板后) ────┘
批次B(护栏) ──────────安全网──▶ 批次E(核心字段清单) ──▶ 批次F(落库收窄)
批次C(日期收口) ──依赖B────────▲
批次D(翻译层+API-1) ─可全程并行──▲
批次G(变体归位) ──依赖E────────▲
```

**关键路径只有一条**：批次 A → 端到端验证。

---

## 6. 全局护栏

| 护栏 | 规则 |
|---|---|
| 迁移 | 只走 `scripts/run_current_schema_migrations.py`（fail-closed）；**禁止**手工 `alembic stamp` 或改版本表；迁移自包含不 import backend；口径漂移用守护测试锁住 |
| 回归 | 全量 `pytest backend/tests` 相对 `main` **零新增失败**（junit XML 前后 diff；before/after **独占串行**） |
| 语义 | **歧义宁可落 `unknown` + 报警，绝不静默猜一个** |
| 可逆 | 一律 `enabled=false` + 可逆，**不物理删除**（列、行、别名、模板） |
| 隔离 | 所有开发在独立 worktree；**不碰** `.worktrees/inventory-aging-pipeline-recovery`、`.worktrees/product-center-stage0`、`Temp/xh_head_wt` |
| 文档 | 落 `docs/superpowers/plans/`；提交风格 `type(scope): 中文描述` |

---

## 7. 验收总表

| 批次 | 验收标准 |
|---|---|
| **A** | 4 个 failed 文件入库成功；`max(metric_date)` 推进到 2026-11；故意错格式时保存被拒 |
| **B** | 文件格式变了 ⇒ 治理面板报 `format_drift`；错误提示指向具体列与候选格式 |
| **C** | 「11/01/2026」不确定时落报警；`grep` 确认入库路径不引用宽松解析器 |
| **D** | 翻译命中率 3~6% → **≥60%**（4 个实测域各有基线）；用户对齐一次 ⇒ 其它模板自动命中；别名冲突落 `conflict` + 报警 |
| **E** | 一份清单同时决定落库列 / 指纹 / 阻断；`hash_participates` 全代码库零引用；前端两级勾选可用 |
| **F** | 非核心字段不建物理列（历史列保留读兼容）；`semantic` view 定义同步迁移且守护测试全过；治理面板无永久噪音 |
| **G** | 5 族 / 5 active 版本 / ~30 变体；账号数变化不新增模板 |
| **全部** | 全量回归**零新增失败**；迁移只走守护入口 |

---

## 8. 风险登记册

| 风险 | 影响 | 对策 | 状态 |
|---|---|---|---|
| 指纹口径变更 ⇒ 历史行被判新行 ⇒ 重复行 | 高 | 批次 E 前置**离线回放**；重算与回填方案；显式开关可回退 | 待办 |
| `deduplication_fields` 存的是中文原始列名（9 个模板） | 高 | 迁移时转成语义键；无法翻译的降级为逐字匹配并**告警** | 待办 |
| `*商品SKU` 类占位符列名无法翻译（1 个模板） | 中 | 明确降级路径 + 告警 | 待办 |
| 全局别名的**同名异义** | 中 | 冲突检测 + 报警 + `enabled` 可撤销 | 已决策 D-3 |
| 落库列收窄影响下游 `UNION ALL` view | 中 | 同步迁移 + 守护测试；不物理删列 | 待办 |
| Shopee analytics **2026-07~09 采集断档**（无文件） | 高 | **不在本方案范围**，需单独查采集配置/调度 | **待业务确认是否立即排查** |
| 213 行 / 8 UV 停用店历史流量归属 | 低 | 维持现状（对数字零影响） | 待业务拍板 |

---

## 9. 主线 1：停用店残留（独立合入）

| 项 | 内容 |
|---|---|
| **工作区** | `feature/shop-disabled-scope-cleanup`（3 改 + 4 新，**未提交未合并**） |
| **已完成** | 存量迁移、停用联动、彻底不显示、18 例守护测试全过；全量回归 NEW=4（2 个本分支引入 = SQLite 夹具缺 2 张表；2 个 worktree 环境差异） |
| **未完成** | ① 迁移未落开发库 ② 2 个自引入失败未修 ③ 分支未提交未合并 ④ 开发库残留（config 31/39、template 16/17 仍启用态） |
| **决策 D-1** | **A** 先做设计改造暂不合并（推荐）／**B** 按现状合入并修夹具／**C** 只合第一层+第三层 |
| **落库前** | 只走 `scripts/run_current_schema_migrations.py`（fail-closed） |

---

## 10. 文档索引

| 文档 | 位置 | 内容 |
|---|---|---|
| **本方案** | `feature/semantic-core-field-refactor`：`2026-11-07-final-work-plan.md` | 可执行总方案（7 批次 + 验收 + 风险） |
| 会话总纲 | 同上：`2026-11-07-consolidated-execution-plan.md` | 未完成工作全景 + 前端 9 问题 + API 7 契约 |
| 翻译层/核心字段规格 | 同上：`2026-11-07-semantic-core-field-spec.md` | 4 条决策、目标数据模型、5 批次、迁移风险、证据索引 |
| 停用店三层补丁 | `feature/shop-disabled-scope-cleanup`：`2026-11-07-disabled-shop-scope-cleanup.md` | 成因、三层实现、回归与失败归属 |
| 模板/同步设计审查 | 同上：`2026-11-07-template-sync-design-review.md` | 概念地图、10 类根因、三批方案 |

---

## 11. 实证基线（开发库实测 2026-11-07，方案的事实依据）

| 项 | 实测值 |
|---|---|
| `core.field_mapping_dictionary` | 34 行，全 orders；`synonyms` 全 `[]`、`platform_synonyms` 全 NULL；`cn_name` 乱码；`field_code` 与 registry 漂移（`buyer_paid_amount` vs `paid_amount`） |
| `core.semantic_field_contracts` | 32 行（orders weekly/monthly + analytics daily/monthly），`platform` 全 NULL；服务层**已优先读表** |
| `b_class.entity_aliases` | 0 行；语义是**实体**别名，不适合字段别名 |
| `core.field_mapping_templates` | published **27**（27/27 带 dedup + bindings）；archived 227（88/39） |
| 模板族 / 版本 / 变体 | **24 族**（每族 1~2 版本）→ **每版本恰好 1 变体** ⇒ 变体机制空转 |
| `deduplication_fields` 形态 | 混着**语义键**与**中文原始列名**（9 个模板存中文列名，2 个含 metric 类，1 个是 `*` 占位符） |
| `catalog_files` | 480 个；`date_from`/`date_to` **100% 填充** |
| shopee/analytics | 107 文件（103 ingested，**4 failed**）；2026-07~09 **无文件**（采集断档） |
| `fact_shopee_analytics_monthly` | 2278 行 / **181 个不同 metric_date** ⇒ 逐日明细 |
| `fact_tiktok_analytics_monthly` | 1374 行 / **9 个不同 metric_date** ⇒ 每月一行 |
| 行日期越界验证 | 联表 1748 行：`metric_date < date_from` **0**、`> date_to` **0** ⇒ 期间消歧不误杀 |
| 翻译命中率 | shopee/orders/monthly 91→6；shopee/products/monthly 40→**0**；miaoshou/inventory/snapshot 28→**0**；shopee/analytics/monthly 9→1 |
| 标准字段定义份数 | **4 份**（后端 registry / 前端副本 / DB dictionary / 硬编码别名表） |
| 日期解析实现份数 | **7 套** |
