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