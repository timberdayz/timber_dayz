# 会话总纲：未完成工作全景与执行方案

> 生成时间：2026-11-07 15:09
> 仓库：`F:\Vscode\python_programme\AI_code\xihong_erp`
> 工作区：main（干净，`a15e5db3`）｜`feature/shop-disabled-scope-cleanup`｜`feature/semantic-core-field-refactor`
> 本文档是**总纲**：业务现象 → 未完成工作 → 执行阶段 → 验收口径。技术细节下沉到各专项文档（§11）。

---

## 0. 一句话现状

**该有的数据进不来、不该有的配置还留着；根因是同一件事被记了好几份，各份各改各的。**

---

## 1. 业务视角：四件未了事

| # | 业务现象 | 造成什么 | 严重度 |
|---|---|---|---|
| **A** | 店铺已停用，但仍留在采集配置和模板里 | 界面误导、整行勾不了、用模板新建配置直接报 400；**数据本身安全**（执行侧按启用状态过滤） | 中（阻断操作 + 误导） |
| **B** | 平台换个说法，同一份业务数据系统就不认 | 翻译命中率仅 3~6%；用户审一次的心血**不沉淀**、换个模板要重审；去重失效 ⇒ **重复入库** | 高（数据质量） |
| **C** | 平台把日期格式的斜杠改成横杠 | Shopee 流量域**整文件入不了库**；该域已**连续 4 个月无新数据**（7~9 月没采、10~11 月采到了但全失败） | 高（数据断档） |
| **D** | 改了这么多，还没在生产跑过一次完整链路 | 所有改动停留在"测试通过"，**没有端到端证据** | 高（风险不可知） |

---

## 2. 主线 1｜停用店残留（A）

**工作区**：`feature/shop-disabled-scope-cleanup`（3 改 + 4 新，**未提交、未合并**）

### 已完成
- 存量迁移 `20261122_remove_disabled_shop_collection_scopes`（置 `enabled=false` + 重算摘要 + 模板停用店项置失效）
- 停用联动（停用/删除店铺时同步失效其采集 scope）
- 响应层彻底过滤 + 前端兜底过滤（停用店**不再出现**）
- 18 例守护测试全过；全量回归 **NEW=4**，其中 2 个已查清为**本分支引入**（SQLite 测试夹具缺 2 张表）

### 未完成
| # | 事项 | 阻塞 |
|---|---|---|
| A1 | 迁移**未落开发库** | 需业务拍板分支处置后再走 `scripts/run_current_schema_migrations.py` |
| A2 | 2 个本分支引入的测试失败未修 | 修法二选一：补 SQLite 夹具 / 改为「读时求值、取消写时级联」 |
| A3 | 分支未提交、未合并 | 同 A1 |
| A4 | 开发库残留仍在：config 31/39 个 scope、template 16/17 个项仍 `enabled=true` | A1 |

> **决策点 D-1**：分支处置三选一 ——
> **A** 先做设计改造、分支暂不合并（推荐）／**B** 按现状合入并修两个测试夹具／**C** 只合第一层+第三层

---

## 3. 主线 2｜翻译层 / 核心字段重构（B）

**工作区**：`feature/semantic-core-field-refactor`（1 份规格文档，**未提交**）
**规格**：`2026-11-07-semantic-core-field-spec.md`（已定稿，4 条业务决策已拍板）

### 已完成
- 业务概念定稿（标准字典 / 翻译层 / 模板 / 变体 / 漂移；用户两级勾选；指纹按标准含义而非列名）
- 4 条决策拍板：① 指标可进 hash ② `hash_participates` 删除 ③ 别名**全局沉淀** ④ 必填契约**并入核心字段清单**
- 现状基线全部实测（4 份定义漂移、命中率 3~6%、24 族 28 变体 1:1 空转、27 个已发布模板核心字段实况）

### 未完成（5 个批次）
| 批次 | 业务目标 | 核心动作 |
|---|---|---|
| **A** | Shopee 流量域恢复入库 | 月度模板改 `auto_by_companion_period` + 显式候选；`field_parse_rules` 上移到 versions 表 |
| **B** | 让过期配置**提前暴露** | 保存闸门（格式白名单 + 样本试解析）+ 漂移加**值形态维度** + 新增「格式漂移」态 + 错误信息可诊断化 |
| **C** | 日期解析口径统一 | 7 套解析实现收成 2 套；「不确定 ⇒ 落 unknown + 报警」取代硬编码 day-first |
| **D** | 翻译层扶正 | 别名归一化匹配 + 全局别名沉淀表 + 命中率护栏（命中率 3~6% → ≥60%） |
| **E** | 漂移口径统一 | 语义契约并入核心字段清单 + `extra_raw_fields` 噪音治理 + 补齐 3 个无契约域 |

**后续批次**（依赖核心字段清单落地）
| 批次 | 业务目标 |
|---|---|
| **F** | 核心字段清单落地（`core_fields`）、`hash_participates` 下线、指标进 hash 生效 —— **需先做新旧口径 hash 离线回放**（影响 9~11 个模板） |
| **G** | 落库列收窄到核心字段（只为需要的字段建物理列）—— 触及 67 张表 |
| **H** | 变体回归业务维度（族 24→5、变体 ~30、去掉族里的 account 维度） |

### 前端与 API 契约（本次补齐）

#### 已有前端资产（比总纲初稿写得多）

| 区域 | 组件 / 页面 |
|---|---|
| 模板构建 | `TemplateBuilderWorkspace.vue`、`TemplateCreateWorkbenchDrawer.vue`、`TemplateUpdateWorkbenchDrawer.vue` |
| 核心字段选择 | **`DeduplicationFieldsSelector.vue`**（独立组件）、`TemplateDeduplicationReviewPanel.vue` |
| 变体 | `VariantCreateWorkbenchDrawer.vue`、`TemplateManualUpdateModeDialog.vue` |
| 治理 / 漂移 | `TemplateGovernancePanel.vue`、`TemplateNeedsUpdateTable.vue`、`TemplateChangeSummaryCard.vue`、`HeaderDiffViewer.vue`、`TemplateRawPreviewPanel.vue` |
| 页面 | `DataSyncTemplates.vue`、`DataSyncFiles.vue`、`DataSyncFileDetail.vue`、`DataSyncTasks.vue`、`DataSyncHistory.vue`、`DataSyncRefreshQueue.vue`、`DataConsistency.vue`、`DataQuarantine.vue` |
| 前端工具（**后端逻辑的副本**） | `headerBindings.js`、`deduplicationSelection.js`、`templateFieldParseRules.js`、`templateUpdateFieldParseRules.js`、`syncTaskErrorParser.js` |

#### 前端 9 个问题（本次审查新增）

| # | 问题 | 位置 | 业务影响 |
|---|---|---|---|
| **FE-1** | 标准字段定义**前端有副本**；`required` 全空、`hash_participates` 硬编码 `false` | `headerBindings.js:13, 544` | 用户在前端看到的选择项 ≠ 后端实际认定 |
| **FE-2** | 前端 `inferSemanticKey` **逐字相等**，且与后端**各维护一份** | `headerBindings.js:495` | 前端预览"已自动识别"，保存后后端可能不认 |
| **FE-3** | **只有一级勾选**——组件标题直接叫「Data Hash 字段确认」 | `DeduplicationFieldsSelector.vue:5` | "我要哪些数据"与"哪些参与去重"塌缩成一个列表 |
| **FE-4** | `auto_by_companion_period` 的**默认候选是全部 18 个**，未按语义族收窄 | `templateFieldParseRules.js:57-76` | 文件期间不准或缺失 ⇒ 命中歧义 ⇒ 文件失败 |
| **FE-5** | 日期格式选项是**第三份副本**，且区间格式**漏了 2 个**（缺 `yyyy-mm-dd-yyyy-mm-dd`、`yyyy/mm/dd-yyyy/mm/dd`） | `templateFieldParseRules.js:53-54` vs `smart_date_parser.py:58-63` | 用户选不到 yyyy 区间格式 |
| **FE-6** | 治理面板**没有「格式漂移」态**的表达 | `TemplateGovernancePanel.vue` | 显示不出"模板格式和文件对不上" |
| **FE-7** | **没有别名冲突裁决界面** | — | 全局沉淀后，同名列名撞不同含义无人能裁决 |
| **FE-8** | **没有「这列我确认过，忽略它」的 UI** | — | `extra_raw_fields` 永久噪音，用户无法消解 |
| **FE-9** | `syncTaskErrorParser.js` 解析的是旧错误文案 | `syncTaskErrorParser.js` | 用户看到"日期超出范围"，不知根因是格式反了 |

#### ⚠️ 重大发现：批次 A **不需要写迁移，前端已具备完整能力**

- `templateFieldParseRules.js:32` —— `DATE_FORMAT_OPTIONS` 第一项即 `auto_by_companion_period`（中文标签「**系统根据伴生周期自动判断**」）
- `templateFieldParseRules.js:78-89` —— `buildAutoCompanionFormatPayload` 在该模式下**自动补上** `format_candidates` + `resolution_source`
- `templateUpdateFieldParseRules.js:134-144` —— 模板更新路径同样处理

⇒ **用户直接在模板更新工作台把「日期格式」改成「系统根据伴生周期自动判断」并保存，analytics 即可恢复入库**，走的是既有「保存即发布、version=max+1、旧行归档」机制。

⇒ 但**必须先修 FE-4**：前端默认候选是全部 18 个（含 dd 族与 mm 族），文件期间一旦不准或缺失就会命中歧义而失败。
⇒ 建议候选收窄为**按语义族分组**：日期单值给 `["yyyy-mm-dd","yyyy/mm/dd","dd-mm-yyyy","dd/mm/yyyy","mm-dd-yyyy","mm/dd/yyyy"]`，
并由**后端按文件期间**二次判定是否真的歧义（配合 P4 值形态漂移检测）。

#### 需要的 API 契约变更（后端 ⇄ 前端）

| # | 契约 | 影响的前端 |
|---|---|---|
| **API-1** | 新增「标准字段定义」只读接口（标准字段 + 别名 + required + hash_eligible + domain 适用范围） | `headerBindings.js` 删副本，改接口取；**一次性消解 FE-1 / FE-2 / FE-5 的根因** |
| **API-2** | 核心字段清单读写（`core_fields`：`semantic_key` + `required` + `in_hash`） | `DeduplicationFieldsSelector.vue` 拆成**两级勾选**；消解 FE-3 |
| **API-3** | 保存闸门错误契约（400/409 带「缺哪个字段 / 影响什么 / 怎么修」） | `TemplateBuilderWorkspace.vue` / `TemplateUpdateWorkbenchDrawer.vue` 的错误展示 |
| **API-4** | 漂移状态新增 `format_drift`（含 `format_mismatch`、`sample_row`、`suggested_candidates`） | `TemplateGovernancePanel.vue`、`TemplateNeedsUpdateTable.vue`；消解 FE-6 |
| **API-5** | 别名沉淀与冲突接口（写入 raw_name→semantic_key；冲突返回 `conflict` 列表） | 新增「别名裁决」界面；消解 FE-7 |
| **API-6** | 「已确认的新列」忽略清单（`ignored_extra_fields`） | 治理面板 + 模板编辑；消解 FE-8 |
| **API-7** | 入库错误码结构化（区分「格式不匹配」/「日期超出文件期间」/「歧义」） | `syncTaskErrorParser.js`；消解 FE-9 |

---

## 4. 主线 3｜上线与端到端验证（D）

| # | 事项 | 阻塞 |
|---|---|---|
| D1 | 上生产（随下一 tag） | 待阶段 0~3 合并 |
| D2 | 跑一轮真实新采集 → 同步 → 看板端到端验证 | **被批次 A 硬阻塞**（Shopee 流量域整文件入不了库） |
| D3 | Shopee analytics **2026-07~09 采集断档**排查（无文件，属采集侧，非同步问题） | 独立待查 |
| D4 | 213 行 / 8 UV 停用店历史流量归属口径（维持现状 / 看板保留可查） | 待业务拍板 |

---

## 5. 执行方案（4 个阶段）

### 阶段 0 · 止血（**本周，只做这两件**）

> 选这两件的唯一理由：它们是**当下正在造成业务损失**的，其余是技术债。

| 动作 | 业务收益 | 验收 |
|---|---|---|
| **主线 1 合入**（D-1 拍板后） | 停用店从采集配置里消失；用模板新建配置不再报错 | 开发库 config/template 残留归零；18 例守护测试 + 全量回归零新增失败 |
| **批次 A-前端**（FE-4 收窄 auto 候选集） | 让「系统根据伴生周期自动判断」在真实文件上稳定命中、不撞歧义 | 用 4 个真实失败样本回放：唯一匹配、零歧义 |
| **批次 A-配置**（走既有 UI，不写迁移） | **用户在模板工作台改一次格式即恢复入库** | 模板更新工作台保存新版本后，`max(metric_date)` 推进到 2026-11 |
| **批次 A-后端**（仅在配置改动不足时补） | 月度模板解析规则落到「伴生周期自动判断」 | 4 个失败文件入库成功，`metric_date` = 2026-10-01 / 2026-11-01 |
| **批次 B-前端**（FE-9 错误可诊断化） | 报错说清"是格式反了"，而不是"日期超出范围" | 故意造错格式 ⇒ 提示指向具体列与候选格式 |

**风险**：批次 A 无回填风险（该模板至今 0 行落库）。迁移一律走 `scripts/run_current_schema_migrations.py`（fail-closed）。

> ⚠️ **批次 A 的落地路径已变**：前端 `DATE_FORMAT_OPTIONS` 已含「系统根据伴生周期自动判断」，
> `buildAutoCompanionFormatPayload` 会自动补 `format_candidates` ⇒ **不需要写迁移**，
> 走既有「模板更新工作台 → 保存新版本」即可。但**必须先修 FE-4**（默认候选 18 个过宽）。

### 阶段 1 · 立契约（让错误提前暴露）

| 批次 | 业务收益 |
|---|---|
| **B** | 配置过期在**保存时/审查时**就被拦住，不再等入库才炸 |
| **D** | 平台改列名系统自动认；用户审一次**全域永久生效**，不再审 N 次 |
| **API-1**（前端） | **标准字段定义收敛成一份**（前端删副本改接口取）⇒ 一次性消解 FE-1 / FE-2 / FE-5 |

**顺序**：B 先（护栏），D 可并行（文件不重叠）。
**D 的验收**：翻译命中率 3~6% → **≥60%**；用户手动对齐一个列名 ⇒ 其它模板自动命中。

### 阶段 2 · 收结构（一份清单管三件事）

| 批次 | 业务收益 |
|---|---|
| **C** | 日期口径统一，不再有 7 套各说各话；不确定时**报警而不是猜** |
| **F** | 一份核心字段清单同时决定「落哪些库列 / 哪些参与去重 / 哪些缺失要阻断」 |
| **H** | 一个数据域 = 1 份标准字典 + 1 个版本 + ~6 个变体；**账号从 12 涨到 44，模板数不变** |
| **API-2 + FE-3**（前端） | `DeduplicationFieldsSelector` 拆成**两级勾选**：「我要哪些数据」与「哪些参与去重」分开呈现，用户不再需要理解内部字段名 |
| **API-3**（前端） | 保存被拒时，界面直接说清「缺哪个字段 / 影响什么 / 怎么改」 |

**F 的前置**：必须先做**新旧口径 hash 离线回放**，产出「hash 变化/不变行数」报告；hash 变化的行给重算与回填方案，**不做静默双写**；口径切换做成显式开关，可一键回退。

### 阶段 3 · 收存储 + 上生产验证

| 批次 | 业务收益 |
|---|---|
| **G** | 只为真正需要的字段建库列；消除"每个业务字段存两份" |
| **E** | 漂移口径统一；治理面板不再有永久噪音 |
| **API-4 + FE-6**（前端） | 治理面板能显示「模板格式和文件对不上」，并直接给出可改的建议 |
| **API-5 + FE-7**（前端） | 新增「别名裁决」界面：同名列名撞不同含义时，人能当场决定 |
| **API-6 + FE-8**（前端） | 新列可以标记「我确认过，忽略它」⇒ 永久噪音消失 |

**阶段 4 · 端到端验证**：真实采集 → 同步 → 看板跑通一轮，产出证据。

---

## 6. 依赖与关键路径

```
阶段0-A-前端(FE-4) ──┬──▶ 阶段0-A-配置(走UI恢复入库) ──解锁──▶ D2(端到端验证)
主线1合入 ───────────┘
阶段1-B(护栏)+API-1 ─安全网/地基──▶ 阶段2-F(核心字段清单) ──▶ 阶段3-G(落库列收窄)
阶段1-D(翻译层)+API-1 ──可全程并行──▶
阶段2-F + API-2(FE-3 两级勾选) ──▶ 阶段3-G + API-4/5/6(前端裁决与噪音治理)
```

**关键路径**：批次 A → 端到端验证。其余可并行推进。

---

## 7. 全局护栏（每个阶段都适用）

| 护栏 | 规则 |
|---|---|
| 迁移 | 只走 `scripts/run_current_schema_migrations.py`（fail-closed）；**禁止**手工 `alembic stamp` 或改版本表；迁移自包含不 import backend |
| 回归 | 全量 `pytest backend/tests` 相对 `main` **零新增失败**（junit XML 前后 diff；before/after **独占串行**，不并发） |
| 语义 | **歧义宁可落 `unknown` + 报警，绝不静默猜一个** |
| 可逆 | 一律 `enabled=false` + 可逆，**不物理删除**（列、行、别名） |
| 隔离 | 所有开发在独立 worktree；**不碰**其它会话的 worktree |
| 文档 | 落 `docs/superpowers/plans/`；提交风格 `type(scope): 中文描述` |

---

## 8. 待拍板决策（本会话未闭合）

| # | 议题 | 选项 |
|---|---|---|
| **D-1** | 停用店分支处置 | A 先做设计改造暂不合并（推荐）／B 按现状合入并修夹具／C 只合第一层+第三层 |
| **D-2** | 213 行/8 UV 停用店历史流量归属 | (a) 维持现状（对数字零影响）／(b) 看板层保留「停用店历史可查」 |
| **D-3** | Shopee analytics 2026-07~09 采集断档 | 是否立即排查（属采集侧配置/调度，**不在本方案范围**） |
| **D-4** | 下一步起点 | **阶段 0 并行开工（推荐）**：主线 1 等 D-1 拍板后合；批次 A 我直接做（FE-4 收窄候选 + 工作台改配置）／先只做批次 A／先出更细的批次实施单 |
| **D-5** | 批次 A 的落地方式 | **走既有模板更新工作台改配置（推荐，不写迁移）**／写迁移直接改模板表／两者都做（迁移兜底 + UI 可维护） |

---

## 9. 已闭合（不需再动，仅备查）

- **店铺身份修复批次一**：七个工作包已合入 main（`1f13ab25`），开发库订正已落库（unknown 951→213 行、跨账号认领 1,946→0），回归零新增失败
- **模板/同步模块设计层审查**：已交付（概念地图、10 类根因、三批方案）
- **翻译层/核心字段规格**：已定稿

---

## 10. 文档索引

| 文档 | 位置 | 内容 |
|---|---|---|
| 本总纲 | `docs/superpowers/plans/2026-11-07-consolidated-execution-plan.md` | 未完成工作全景 + 执行阶段 |
| 翻译层/核心字段规格（定稿） | `feature/semantic-core-field-refactor`：`2026-11-07-semantic-core-field-spec.md` | 4 条决策、目标数据模型、5 批次、迁移风险、证据索引 |
| 停用店三层补丁 | `feature/shop-disabled-scope-cleanup`：`2026-11-07-disabled-shop-scope-cleanup.md` | 成因、三层实现、回归与失败归属 |
| 模板/同步设计审查 | `feature/shop-disabled-scope-cleanup`：`2026-11-07-template-sync-design-review.md` | 概念地图、10 类根因、三批方案 |

---

## 11. 执行记录（批次 A~G 全部落地，2026-11-07）

> 执行方式：全程在 **main** 直接推进（未开独立 worktree），A~G 共 **13 个提交**，逐批提交、逐批自测。

### 11.1 逐批落地与验收证据

| 批次 | 提交 | 落地内容 | 验收证据 |
|---|---|---|---|
| **A** | `df5bc0aa` | Shopee analytics 日期格式止血（白名单闸门 + 样本体检 + 模板迁移） | 4 个失败文件实跑入库成功；`max(metric_date)` 推进到 2026-11；故意错格式被拒 |
| **B** | `c9e22e80` | 值形态漂移检测 + `format_drift` 状态 + 结构化错误码 | 文件格式变了 ⇒ 治理面板报 `format_drift`，错误指向具体列与候选格式 |
| **C** | `e84563ea` | 日期解析 7 套收成 2 套 | 「不确定」落 `unknown` + 报警，**不猜**；入库路径不再引用宽松解析器 |
| **D** | `3b04c64c` / `f8c4940c` / `6893d6c1` | 归一化匹配 + 全局别名沉淀 + API-1 标准字段接口 + 前端删副本 | 命中率护栏 + 快照漂移守护；前端只保留**一份**口径（接口为权威、快照为生成物） |
| **E** | `a2dd3e93` / `eb8e7d58` / `97770ac7` | 核心字段清单落**版本级** + `hash_participates` 下线 + 指标可进 hash + 前端两级勾选 | hash 离线回放：488 行「切清单口径后 hash 变化 **0 行**」；清单覆盖 28/28 版本 + 27/27 已发布模板 |
| **F** | `e3a6f649` / `9bdaf623` / `3375bc8a` | 只为核心字段建列 + 非核心列只进 `raw_data` + 契约降为域级下限 + 「已确认的新列」忽略清单 | 建列实测 28 → **4**（无重复列）；契约 5 域 70 行；`extra_raw_fields` 噪音归零 |
| **G** | `01b92dc7` / `1cd6aa5f` / `63760cf2` | 模板族去掉**账号**维度 + 变体按**业务形态**识别 + 前端按业务维度建变体 | 守护测试「3 个账号 ⇒ 1 族 / 1 active 版本 / 3 变体」；`variant_kind` 存量 28/28 回填且与 Python 逐字一致 |

迁移链终点：`current_schema_20261129_template_variant_kind`（已落开发库，**只走** `scripts/run_current_schema_migrations.py`）。

### 11.2 总回归证据（junit 失败**集合** diff，不是计数）

| | 失败 | 通过 | 错误 | 收集到的用例 |
|---|---|---|---|---|
| before（`9f02e6a9`，批次 A 之前） | 137 | 4500 | 22 | 4666 |
| after（A~G 全部落地） | 137 | 4655 | 22 | 4821 |
| **失败集合差** | — | — | — | **NEW = 0 ／ FIXED = 0 ／ COMMON = 159** |

- 5 条 `REMOVED` 用例全部是**改名**（E 的 hash 口径、F 的契约口径、G 的账号维度），已逐条核对。
- 前端守卫测试：before / after **失败名单逐条一致**（8 个历史遗留，均不在数据同步模块内）。
- 前端构建：`npx vite build` ✓。

### 11.3 唯一未做的一条：批次 G 的「族 24→5」

批次 G 的验收原文是「5 个族 / 5 个 active 版本 / ~30 个变体」。本次交付了 **G-1（族去掉账号维度）、
G-2（变体按业务形态）、G-3（前端按业务维度建）**，但**没有**做「27 族合并成 5 个数据域族」，原因：

1. 批次 E 已定稿「核心字段清单 + 绑定 + 解析规则挂**版本级**」（E-1 / E-8，理由是「审一次全变体生效」）。
   合并成 5 个族意味着**一个版本同时代表多个平台的模板** ⇒ 版本级清单变成跨平台并集
   ⇒ 同一份数据的字段身份口径漂移。
2. 合并还要求**变体承载 platform / granularity / sub_domain**（否则 Shopee daily 的文件可能匹配到
   TikTok monthly 的变体 ⇒ 用错解析规则 ⇒ 入库出错）。
3. 真正保住口径的做法是把清单/绑定/规则**下移到变体级**（推翻 E-8），
   而这需要业务先定义「**每个数据域的公共标准字典 vs 平台特有字段**」——这是业务决策，代码推不出来。

⇒ 判定为 **V2 级建模改造**，不阻塞上线；「账号数变化不影响模板数」这条**核心业务目标已经达成**
（账号差异由变体承载，已由守护测试锁定）。

**决策（2026-11-07，用户拍板）**：**保持现状**，把「族 → 数据域合并」列为 **V2**。
⇒ 后续要做时，前置条件是业务先给出「每个数据域的公共标准字典 vs 平台特有字段」的划分，
再按 §11.3 的 3 条改造清单推进，并重做 hash 回放。

### 11.4 本次总验收补修的用例（批次 D 遗留）

全量 diff 曾报 3 条 NEW 失败，均为**批次 D 口径变更后用例过期**，已按新口径改正并补齐覆盖：

| 用例 | 问题 | 处理 |
|---|---|---|
| `test_template_confirmed_bindings_collect_raw_name_aliases` | 断言旧的「按域沉淀」，批次 D 已改为**全局沉淀**（D-3） | 改为断言全局作用域，并补 `global_scope=False` 的按域沉淀用例 |
| `test_template_confirmed_bindings_create_aliases_without_duplicates` | 同上 | 同上 |
| `test_frontend_semantic_registry_keys_match_backend_contract` | 断言前端 `headerBindings.js` 里有一份手抄字典，批次 D 已**删副本** | 改为新口径三条守护：前端不得再有手抄副本、注册表必须走 API-1、兜底快照（生成物）字段键与后端一致 |

---

## 12. 执行记录（看板自锁根治 + 采集侧 404 假冲突，2026-11-29）

> 详细根因分析见 `docs/superpowers/plans/2026-11-29-dashboard-self-lock-and-identity-probe-root-cause.md`。

### 12.1 起因：两个常驻告警都不是「正常工作」的提示

| 现象 | 真相 |
|---|---|
| 业务概览页常驻「数据刷新中 / Dashboard SQL 资产正在刷新」 | 状态机把**没人能修的状态**（刷新资产定义漂移）当成「正在刷新」，而修复方又把自己制造的「正在刷新」当成失败条件 ⇒ 退避重排 ⇒ **无限自锁**（实测攒出 **859 次 failed** 的修复任务） |
| 业务概览页常驻「采集期探测到 1 次店铺身份异常」 | 采集器打开到平台的 **404 页**，把 URL 上残留的**上一家店编号**当成探测结果 ⇒ 判成「被别的账号占着」 ⇒ **假冲突** |

### 12.2 看板侧根治（5 个断点）

| 断点 | 改动 | 落点 |
|---|---|---|
| 1 状态机去死区 | 刷新资产指纹漂移**不再**⇒`refreshing`（降级为可见性字段 `refresh_fingerprint_drift`）；刷新资产缺失 ⇒ **`drift`**（可自愈） | `backend/services/data_pipeline/dashboard_bootstrap.py` |
| 2 口径同源 | 新增 `DASHBOARD_ASSET_AVAILABLE_STATUSES = {ready, refreshing}`，验收方与运行期门禁**共用同一份定义**（守护测试用 `is` 比较锁定） | `dashboard_bootstrap.py` / `refresh_validation.py` / `dashboard_api_postgresql.py` |
| 3 安全网熔断 | 只对 `drift` 排修复；连续 3 次失败 ⇒ 熔断（30 分钟冷却后放一次半开；成功一次即自动解除） | `backend/tasks/refresh_queue_tasks.py` |
| 4 僵尸回收 | `ops.pipeline_run_log` 里超 30 分钟仍是 `running` 的看板刷新 run ⇒ 标记 `failed`（匹配条件与状态机读取口径逐字一致） | `backend/tasks/refresh_queue_tasks.py` |
| 5 前端分级 | 改用后端 `ready` 字段判定「不可用」；`refreshing` 单独提示 | `frontend/src/domains/business/views/BusinessOverview.vue` |

**效果（开发库实测，未改任何库数据）**：`python scripts/bootstrap_postgresql_dashboard.py --check --module business_overview --json`
⇒ `business_overview.status` 由 `refreshing` 变 **`ready`**、`ready=true`、`assets_drift=false`；页面提示消失。

### 12.3 采集侧根治（404 判探测失败）

- `modules/apps/collection_center/executor_v2.py`：新增 `_is_platform_error_page()`（只看 path 最后一段，命中 `404 / 404error / error / notfound / signin / login`）；
  `_extract_platform_shop_context()` 增 `is_error_page` 字段（证据仍留在 `current_url`）。
- `backend/services/platform_shop_discovery_service.py`：新增状态 `failed`（**刻意不在** `PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES` 里 ⇒ **不计入身份异常告警**，与 2026-04 那 3 条登录页历史记录同口径）；
  `record_runtime_discovery(..., probe_failed=True)` ⇒ 不做绑定判定、不写候选账号、**不把 URL 上的编号当探测值**（证据留在 `raw_payload`）。
- 正常页面上的同一编号**仍然**判 `conflict_detected`（改动只作用于错误页路径）。

### 12.4 守护测试与回归

| 项 | 结果 |
|---|---|
| `backend/tests/data_pipeline/test_dashboard_asset_self_lock_guardrails.py` | 新增 15 个 —— 守住 5 个断点 |
| `backend/tests/test_platform_shop_discovery_error_page.py` | 新增 14 个 —— 守住 404 判探测失败 |
| `backend/tests/data_pipeline/test_dashboard_bootstrap_locking.py` | 修好 3 条陈旧桩（原报 `KeyError: 'modules'`，其中一条还会空转 240 秒等锁） |
| 全量后端回归 | 见 §12.5 |
| 前端守卫测试 | 失败名单与基线**逐条一致**（8 个历史遗留，均不在本模块内） |
| 前端构建 | `npx vite build` ✓ |

### 12.5 全量后端回归（junit 失败**集合** diff）

| | 失败 | 通过 | 跳过 | 错误 | 收集到的用例 |
|---|---|---|---|---|---|
| before（批次 A~G 验收后，`da2a2a2a`） | 137 | 4655 | 7 | 22 | 4821 |
| after（本次改动落地） | 134 | 4687 | 7 | 22 | 4850 |
| **失败集合差** | — | — | — | — | **NEW = 0 ／ FIXED = 3 ／ COMMON = 156**（diff 脚本退出码 0） |

- **FIXED = 3**：`test_dashboard_bootstrap_locking.py` 的 3 条用例（桩与现行代码脱节 ⇒ `KeyError: 'modules'`；
  其中一条还会空转 240 秒等锁）。已按**现行行为**改正（其中一条随之改名为
  `test_bootstrap_deploy_mode_zeroes_statement_timeout_before_locking` ⇒ REMOVED 1 / ADDED 1）。
- **ADDED = 30**：本次新增的 29 个守护用例 + 1 条改名。

### 12.6 仍未闭环的两件事

1. **历史那条假冲突（id=72）保留原样**，不删历史。若要让运营侧告警归零，需要**人工确认**后把它改判为 `failed`（与 2026-04 的 3 条同口径）—— 这是改历史判定，必须由人拍板。
2. **资产指纹账本仍可能落后于文件**（迁移重建了资产但没回写账本）。现在只作为可见性字段存在，**不再驱动判定与重试**；
   要彻底消除需要「落库只有一个入口 + 由它回写账本」，列入 **V2**。

---

## 13. 采集 404 归位 + 库龄分档「彻底一致」（2026-11-29）

> 详细方案见 `docs/superpowers/plans/2026-11-29-404-landing-and-aging-tier-alignment.md`。
> 本节只记**结论与证据**。

### 13.1 404 根因（实测，非推断）

登录检测器对 Shopee 整站 URL 做**子串匹配**，「已登录关键词」里的 `"/seller"`
命中的是**域名** ⇒ `https://seller.shopee.cn/404?…` 与 `/account/signin` **都被判成 logged_in(0.85)**
⇒ 登录闸门放行 ⇒ 没有任何一层纠正页面 ⇒ 持久 profile 恢复出来的 404 被原样保留
⇒ 切店只改 query、保留 path ⇒ 一直在 404 上打转。

**TikTok 看起来没事不是它自己会重定向** —— 两边登录短路逻辑一模一样，
真正原因是我们的关键词是**路径级**、对 TikTok 拦得对、对 Shopee 放行错了。
结构性佐证：Shopee 把店铺编号明文放在 URL query（`cnsc_shop_id`），陈旧 URL 一恢复就带出上一家店的编号；
TikTok 的身份参数是 `shop_region`，探测只认 `cnsc_shop_id`/`shop_id` ⇒ 提取不到 ⇒ 根本不落记录。
**库里 28 条探测记录 100% 是 shopee**，一条 TikTok 都没有。

### 13.2 修法（用户拍板：404 确实是已登录页面，只是需要重新导航）

- **不改登录判定**（改了会让采集器白跑一遍重新登录、甚至弹验证码）；
- 新增 `runtime_session.ensure_platform_landing_page()`：**只有当前页确实是错误页时**
  才导航回平台入口，正常页面一次额外导航都不加 ⇒ 采集流程零影响；
- 探测读 URL 前先归位：成功读到**真实**身份，失败仍记「探测失败」，
  残留编号**连参数都不给它**（服务层丢弃是第二道防线），证据留在 `raw_payload`；
- 错误页判据下沉到 `modules/apps/collection_center/platform_error_page.py`
  （`runtime_session` 也要用 ⇒ 同文件会循环依赖），`executor_v2` 保留同名别名，
  迁移口径**逐字未变**；
- 顺手修掉 `get_platform_login_entry` 对未知平台抛 `ValueError` 会带崩采集的真 bug。

### 13.3 库龄分档「彻底一致」

- 粒度改 **SKU 级**（库龄取各仓最长、只算还有可售库存的仓）—— 与商品中心定价一致，
  货值与 SKU 数**互斥可加**；
- SQL 视图阈值**不写死**，直接读 `finance.sku_pricing_policies` 当前生效行
  ⇒ 业务改档位表，看板自动跟着变；
- 服务层两条 SQL 路径合并为一个 Python 汇总（`build_restock_tier_buckets`，唯一实现），
  不再两份 CASE 各写一遍阈值；
- 业务概览卡 + 库存概览页都改按业务档位展示，并补「共 N 行 · M 个 SKU」；
- 旧标准指标 `deep_stagnant_value`(≥180) / `mid_stagnant_value`(90~180) 口径**不变**、
  仍随接口返回（它们是「深度积压」独立指标，不是分档体系）；
- 指标词典「两套分档并存」⇒「**分档只有一套**」（两份副本同步）。

**改前 vs 改后（开发库实测）**：167 个 SKU / 货值 ¥50,648 原来在看板上是
「中度 0 / 重度 0 / 活跃」（30~90 无档）⇒ 现在落在「压60-90天」档，**看得见了**。

### 13.4 回归证据

| 项 | 结果 |
|---|---|
| `backend/tests/test_platform_landing_page.py`（新增） | 11 passed |
| `backend/tests/data_pipeline/test_inventory_backlog_tier_consistency.py`（新增） | 4 passed |
| 全量后端回归（junit 失败**集合** diff） | before 156 failed / 4850 collected → after **156 failed / 4869** collected；**NEW = 0 ／ FIXED = 0 ／ COMMON = 156**，diff 脚本退出码 0 |
| 前端守卫（全部 `.test.mjs`） | 失败名单与基线**逐条一致**（8 个历史遗留），零新增 |
| 前端构建 | `npx vite build` ✓ built in 14.21s |
| Python 汇总 vs SQL 视图（真实库对账） | **逐档完全一致**；档位货值合计 ¥232,560.05 == 总货值；档位 SKU 合计 511 == 总 SKU 数 |

### 13.5 本节新记的 V2 债务

1. `LoginStatusDetector` 的 `"/seller"` 是**域名级**关键词 ⇒ Shopee 整站任何页面都被判「已登录」。
   本次**刻意不动**（登录态判定是对的，改了会让采集流程冒风险）；根治应把 URL 关键词判定改成**只看 path**。
2. Shopee 切店组件只改 query、保留 path ⇒ `/404` 路径会被保留；本次靠「页面归位」兜住。
3. `finance.sku_pricing_policies` 的门槛与 `RESTOCK_TIER_THRESHOLDS` 仍是**两份拷贝**
   （本次用守护测试锁住一致）；根治应让 Python 侧从档位表派生。
4. `mart.inventory_backlog_base` 的 `days_since_restock` 缺失仍回落 0（老 V2 条目）——
   本次新增的 `unknown_restock_row_count` 让缺失**在数据上可见**，但底层「缺失伪装成 0 天」尚未修。


---

## 14. 本会话收口：基线红清理 + 中文乱码 + 采集组件缺陷 + hash 实跑回放

> 本节记录「把所有已知还没做完的内容一次性做完」这一轮的全部产出。
> 详细文档：`docs/superpowers/plans/2026-11-29-hash-replay-by-real-ingestion-path.md`
> （前序的 404 / 库龄见 `2026-11-29-404-landing-and-aging-tier-alignment.md`）

### 14.1 基线红（156 条历史失败）分五组清零

按域切成 5 组并行处理，每组限定「只能改自己清单内的测试文件 + 禁止改实现代码」，杜绝并行写冲突。

| 组 | 范围 | 条数 | 主要根因 | 验收 |
|---|---|---|---|---|
| A | task_center | 19 | sqlite fixture 漏 ATTACH `ops`/`semantic`；补齐后暴露 `a_class.operating_costs` 的 PG 专有 DDL；桩用户非管理员；桩签名过期 | 19 passed |
| B | collection | 20 | 断言过期（默认子型 / purchase 域 / interrupted 终态）；基建缺陷（缺表、`main_account_id` NOT NULL）；桩过期（按名导入导致打桩失效、全局 `asyncio` 污染） | 71 passed |
| C | data_pipeline 迁移契约 | 24 | 断言过期（别名治理下沉、ORM 已对齐）；路径过期（兼容壳降级、规则源退役）；资产过期（旧迁移链只读 ⇒ 改在临时库重放当前链基线） | 82 passed |
| D | 业务杂项 | 47 | **black 重排导致按固定偏移切片的断言失配**；功能已迁移/下线；桩过期；依赖被 `.gitignore` 的数据文件 | 192 passed |
| E | shopee 导出组件 | 25 | 桩打在了**转发层**而非承载逻辑的 helper 实例；报表行假数据不真实（缺业务前缀） | 78 passed |

**红线**：不允许把过期断言改成迎合实现的错误行为；发现真缺陷先修实现再让测试变绿。

几个值得记住的判定要点：

- **域迁移后 legacy 兼容壳打桩无效** —— `backend/routers/*.py` 现在只是 re-export 壳
  （`import ... as domain_module` + `__getattr__` 委托，或 `from ... import *`），
  桩必须直接打到真身模块路径；用 fixture 在壳与真身之间桥接会让 monkeypatch teardown
  把桥接函数**永久泄漏**回壳的 `__dict__`，下一条用例经 `__getattr__` 绕回自己 ⇒ `RecursionError`。
- **组件下沉 helper 后，桩要打在 helper 实例上** —— 仓库内既有正确范例：
  `picker = component._date_picker_helper()` + `monkeypatch.setattr(component, "_date_picker_helper", lambda: picker)`。
- **black 重排会让「按固定偏移切片取源码片段」的断言全部失配** —— 改用空白无关的压缩/正则匹配，
  断言语义不变。

#### 最后一条红：进程级环境变量污染造成的顺序依赖

清完 A~E 五组后，全量回归里**仅剩 1 条**红。它不是本轮引入的，而是**被测试基建失败掩盖的存量顺序依赖**
（基线上它的失败原因是 sqlite fixture 建表报错，断言根本没跑到）。

- **现象**：单独跑该文件 2 passed；跑 `cloud* + collection* + t*`（108 个文件）就复现
  `assert 'pending' == 'completed'`。
- **定位**（目录二分 → 临时诊断打印）：`CloudSyncAdminCommandService.update_settings()`
  会把自动同步开关**直接写进进程级环境变量** `os.environ["CLOUD_SYNC_AUTO_SYNC_ENABLED"]`；
  `test_cloud_sync_admin_command_service.py` 调用 `update_settings(enabled=False)` 后**不还原**
  ⇒ 同进程后续用例里 `CloudBClassAutoSyncWorker._auto_sync_enabled()` 读到 `false`
  ⇒ worker 直接不 claim 任务 ⇒ 任务永远停在 `pending`（与业务数据无关的假失败）。
- **修法**：给两个直接写该环境变量的测试文件加 autouse fixture，用例结束还原环境变量原值。
  **生产代码不动** —— 开关语义变更属于上线前不做大改的范围（相关产品级问题见 14.5 第 16 条）。

### 14.2 中文乱码（GBK 误解码）—— 生产功能实际失效

全仓扫描出 16 处「UTF-8 被按 GBK 解码」的中文串：

1. **选择器 / 判据（功能实际失效）**
   - `modules/platforms/tiktok/components/login.py:565` 登录态信号词「首页 / 数据分析 / 订单 / 商品」全是乱码
     ⇒ 中文信号**一个都不命中**，实际只剩 `TikTok Shop` / `Seller Center` 两个英文词在起作用；
   - `modules/platforms/tiktok/archive/export.py`「聊天详情」、`archive/shop_switch.py`「店铺代码」；
   - `modules/platforms/shopee/components/date_picker.py`「统计时间」
     —— 该文件里 `_find_date_summary_container` 还**被定义了两次**（乱码版 + 正确版），后者覆盖前者。
2. **用户可见错误消息**：`field_mapping_templates.py` / `hr_salary.py` / `performance_management.py`。
3. **测试基线**：`test_tiktok_login_component.py`（与实现同步修正）。

> `backend/tests/test_backend_startup_dashboard_log_contract.py` 里的 `"璧勪骇"` 是**故意的乱码守卫**
> （断言 `main.py` 不得含乱码），属于扫描误报，**不改**。

### 14.3 采集组件三处真缺陷（会导致导出到错店铺 / 日期口径错乱）

1. **店铺切换判定是纯子串匹配**（`shop_switch.py::_shop_name_looks_selected`）
   - 「所有店铺」聚合标签被判为**已切到目标店** ⇒ 切店失败也会判成功 ⇒ **导出拿到多店混合数据**；
   - **区域上下文形同虚设** —— `巴西 / chenewei666.sg` 配 SG 目标仍判 True。
   改法：新增聚合标签识别 + 「区域 / 店铺」标签的区域解析（显式带出且不符才否决）。
2. **日期摘要「容器优先」语义错** —— 容器常只印「统计时间」四个字，触发器才带「按月 2026.03 (GMT+08)」
   这种能判断「是否已应用」的信息 ⇒ 旧语义让「已应用则跳过」判断失效，每次都重选日期区间。
   改法：两个候选都在时取**信息更丰富者**。
3. **标签回退只认首个匹配** —— 同名文本常有多份（隐藏副本 / portal 末尾的菜单项）⇒ 改用
   `_pick_visible_locator` 择优**可见**项。

另外把「组件与 helper 共用同一套选择器」这条口径贯彻到底
（`ShopeeDatePicker` / `ShopeeShopSwitch` 接受组件传入的 `ProductsSelectors`），
消除了原先「组件层一套、helper 层一套」的日期文案/粒度口径。

### 14.4 hash 口径回放：按**实跑路径**重做

「翻 `SYNC_CORE_FIELDS_HASH_ENABLED` 前必须按实跑路径重做 hash 回放」这一条本次落地。

**旧回放为什么不能作数**（自己拼字段集合，与入库路径三处对不上）：
漏传 `identity_values`；`core_fields` 用推导值且 `field_parse_rules` 取自 `variants` 表
（入库用的是**版本行**的清单）；漏了 orders 域的 `prepare_orders_rows_for_b_class` 行改写。

**本次改造**：把 hash 计算抽成公共函数
`backend/services/data_ingestion_service.py::compute_ingestion_data_hashes()`，
**入库路径与回放脚本共用同一条链** ⇒ 结论与实跑同源，回放不会再漂移。
回放脚本只在**进程内**临时切换开关，不改任何持久化配置；**生产开关仍关闭**。

**实测结论（更正了早先的错误判断）**：

```
实跑回放合计: 1094 行, 口径切换后 hash 变化 0 行
```

⇒ **切换不会改任何一行的 `data_hash` ⇒ 无需回填**。

早先「字段数不同 ⇒ 键集合不同 ⇒ hash 会变」的推断是**错的**：切换只改「怎么取」，不改「取哪些键」——
键仍是完整字段链（含自动追加的 `platform_code` / `shop_id` / `metric_date` / orders 扩展 /
`_source_line_index`），清单只决定取值方式（逐字优先、语义兜底），所以键不变、值也不变。
**回放必须与实跑同源，否则结论不可用。**

### 14.5 本节新记的 V2 债务

**数据正确性（需要业务决策，优先级最高）**

1. **products 语义层别名缺口（最严重）** —— `sql/semantic/semantic_alias_registry.sql` 与
   `backend/services/semantic_alias_registry.py` 的 `BUILTIN_ALIASES` 两侧不同源, 且都缺
   「已付款订单 / 已确认订单 / 已确定订单」三变体与带币种后缀的表头
   ⇒ `semantic.fact_products_atomic` 里 shopee **25810 行**的
   `sales_amount / sales_volume / order_count / conversion_rate` **全为 0**（仅 tiktok 174 行有值）。
   影响 Shopee 商品维度指标与下游看板/利润口径。修它涉及别名登记单一来源化 + 视图重建 + 数据回填。
2. **部分文件在旧口径下「前 10 行 hash 相同」** —— `shopee/analytics/daily`、`tiktok/products/monthly`
   ⇒ 存量去重粒度问题（明细行算不出不同 hash ⇒ 去重会当重复行丢数据）。
3. **`shopee/services` 三个模板版本（1 / 53 / 60）解析规则与文件列名对不上**
   （用 `metric_date` 而文件是「日期」/「日期期间」）⇒ `[date_format_mismatch]`，**这些版本入库会直接失败**。

**接口健壮性**

4. **看板缺表不降级** —— `postgresql_dashboard_service.py:2792-2805` 查
   `finance.employee_labor_cost_allocations` 无 try/except（同文件 `:1411-1438` 明确写了
   「缺表必须降级」）⇒ 未跑完迁移的部署里看板整块 500；`:1441-1461` 的 `a_class.operating_costs` 同样。

**可维护性 / 测试基建**

5. `core_fields` 清单（DB 版本行）与 `derive_core_fields`（Python 推导）**并存** ⇒ 应收敛为单一来源。
6. `a_class.operating_costs` 的 `server_default=text("'[]'::jsonb")` 在 SQLite 建不了表
   ⇒ 任何在 SQLite 上做全量 `create_all` 的测试都会踩到（测试侧已按既有约定排除该表）。
7. `backend/utils/schema_cleanup_wave1_preplan.py` 仍硬编码 `source_schema="public"` /
   `operation="archive_rename"`，而当前事实源只建 `a_class.*` ⇒ 预演动作在当前 schema 下是空操作。
8. `collection_account_runtime_service.py:10` 按名导入 ⇒ 外部打桩**静默失效**（所有按旧路径打桩的测试都会
   走到真实 loader 并以 `shop_account_missing`(404) 失败）。
9. `collection_tasks.py:1612` 入库投影**无条件另开 DB 会话** ⇒ 按会话顺序断言很脆弱；
   `:1697` 浏览器参数是函数内延迟导入 ⇒ 预检失败时整链提前 return。
10. `hr_commission.py` 的 SQL 含 `id::text`（PG 专有）⇒ 该读路径无法用内存 sqlite 端到端覆盖。
11. `target_management.py` 的 409 守卫在旧校验之前 ⇒ 运营目标分支成为**不可达死代码**。
12. `excel_parser.py:71` 向 float64 列写空串 ⇒ pandas FutureWarning，未来版本会直接报错。
13. `backend/main.py` 与根 `run.py` 在 import 时 `load_project_env(override=True)`
    ⇒ 路由注册类用例变成顺序依赖。
14. `frontend/src/stores/user.js` 仍 import 已不再使用的 `hasPermissionForRoles`。
15. `tests/unit/test_template_hash_hygiene_audit.py` 2 条既有红（度量字段未被工作台剔除）
    —— 只依赖 `template_hash_policy` / `template_save_readiness_service`，与本轮改动无关。
16. **自动同步开关存在进程级环境变量里** —— `CloudSyncAdminCommandService.update_settings()`
    把 `CLOUD_SYNC_AUTO_SYNC_ENABLED` 写进 `os.environ`。后端是多进程部署（web / celery-worker /
    celery-beat 各自独立进程），管理端在 web 进程改开关，**其它进程读不到**
    （环境变量不跨进程共享）⇒「管理页显示已暂停」与「采集入库仍按开启执行」可能不一致。
    根治方向：开关只以 DB（`SystemConfig`）为事实源（worker 的 `_auto_sync_enabled()` 已支持读 DB），
    env 只作为进程启动默认值；本次**不动生产语义**。

### 14.6 回归证据

| 项 | 结果 |
|---|---|
| **全量后端回归**（junit 失败**集合** diff，脚本退出码 0） | before **156 failed** / 4869 collected → after **0 failed** / 4871 collected；**NEW = 0 ／ FIXED = 156 ／ COMMON = 0** |
| 分组验收 | A 19 passed ／ B 71 passed ／ C 82 passed ／ D 192 passed ／ E 78 passed |
| 本会话改动过的 64 个测试文件（组合跑） | 498 passed |
| `tests/unit`（**不在** `backend/tests` 全量范围内） | 137 passed / 2 failed（2 条为既有红，只依赖 `template_hash_policy` / `template_save_readiness_service`，与本轮无关） |
| 前端守卫（全部 `.test.mjs`） | 失败名单与基线**逐条一致**（8 个历史遗留），零新增；本会话**未改动任何前端源码** |
| 前端构建 | `npx vite build` ✓ built in 10.68s |
| hash 实跑回放（生产开关保持关闭） | 实跑回放合计 **1094 行**，口径切换后 hash 变化 **0 行** ⇒ 无需回填 |

**本会话提交（11 个）**：`5e472db2` 乱码 → `d6f10365` hash 实跑回放 → `9f77545b` 结论更正 →
`50ba79c4` 切店判定 → `9e7a0a5b` A 组 → `0a6bbda4` D 组 → `2bb6d7c6` B 组 → `503895b1` C 组 →
`679244bf` 日期摘要 → `fff13425` E 组 → `ba927bed` 环境变量隔离。

