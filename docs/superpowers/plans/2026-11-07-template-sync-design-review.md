# 模板 / 同步模块 · 设计层审查与根治方案

- 日期：2026-11-07
- 状态：**审查完成，方案待业务拍板后进入实施**
- 触发：用户在「店铺工作区」截图里发现幽灵店铺行 → 追查发现「模板 / 同步」模块存在系统性设计债，要求**先搞清业务概念、从根源解决**，而不是逐个打补丁
- 审查方式：代码走查 + **开发库实测**（容器 `xihong_erp_postgres`，库 `xihong_erp`）
- 涉及面：
  - 采集侧：`backend/domains/collection/routers/collection_config.py`（~2200 行）、`backend/services/collection_config_execution.py`、`backend/services/collection_contracts.py`、`modules/core/db/schema_parts/collection.py`
  - 同步侧：`backend/domains/data_platform/routers/data_sync.py`（**4489 行**）、`routers/field_mapping_*.py`（5 个）、`backend/services/data_sync_*.py`、`modules/core/db/schema_parts/data_platform.py`
  - 前端：`frontend/src/domains/collection/views/collection/CollectionConfig.vue`、`frontend/src/components/dataSync/*`（9 个）、`frontend/src/domains/data_platform/views/DataSyncTemplates.vue`

---

## 1. 业务概念地图（先把概念说清楚）

这个模块其实是**两段业务**，共用"模板"这个名字，但模型完全独立。

### 1.1 采集侧：决定"采什么"

| 概念 | 载体 | 含义 |
|---|---|---|
| **模板 Template** | `core.collection_config_templates`（13 行） | 某「主账号 + 粒度」的**默认采集计划**：默认日期口径、执行模式、cron、重试、默认店铺范围。唯一键 `(platform, main_account_id, granularity)` |
| **配置 Config** | `core.collection_configs`（14 行） | 某一个**具体时间窗口**的执行计划（今天 / 这一周 / 这个月） |
| **批次 Batch** | **不是表** —— 配置上的 `batch_key` / `batch_status` / `batch_note` / `batch_shop_overrides` 四列 | 配置沿时间窗推进产生的实例。`batch_key` 就是窗口标识（daily=`2026-11-07`、weekly=`2026-W45`、monthly=`2026-11`） |
| **店铺范围 Scope** | `core.collection_config_shop_scopes`（42 行） | 该配置在某个店上采哪些域、哪些子类型、是否参与 |
| **当前配置** | `_select_current_config_records`（`collection_config.py:433`） | 每个 `(platform, main_account, granularity)` 分组里 `batch_status='active'` 的那一个 |

### 1.2 同步侧：决定"文件怎么解释、怎么入库"

| 概念 | 载体 | 含义 |
|---|---|---|
| **字段映射模板** | `core.field_mapping_templates`（254 行） | 某平台/域/粒度的导出文件长什么样：表头列、日期列、**日期字面格式**、去重键 |
| **模板族 / 版本 / 变体** | `field_mapping_template_families`(27) / `_versions`(28) / `_variants`(28) | 模板的包装层。**`versions` 表不含解析规则**，规则实际挂在 `variants` 上，且**同时**复制一份在 legacy 模板行里（28/28 变体全部 `source_legacy_template_id` 非空） |
| **文件登记** | `public.catalog_files`（480 行） | 采集产物登记处。状态机 `pending → processing → ingested / quarantined / needs_shop / failed / template_update_required` |
| **模板契约** | `catalog_files.file_metadata['template_contract']` | 文件 ↔ 模板之间**唯一的真实关联**（template_id + version + columns_hash 的 JSON 快照） |

---

## 2. 问题清单

### P0-1 同一个事实被写进 4 个地方，没有单一事实源

「这个配置要采哪些店、哪些域」同时存在 4 份：

| # | 载体 | 谁写 | 何时算 |
|---|---|---|---|
| 1 | 模板 `default_shop_scopes` | 改模板时 | 写时 |
| 2 | 配置摘要 `account_ids/data_domains/sub_domains` | 建/改配置时 | 写时 |
| 3 | 配置的 `shop_scopes` 行 | 建/改配置时 | 写时 |
| 4 | 配置的 `batch_shop_overrides`（相对模板的差量） | **只有一条路径会算** | 写时 |

同步侧同理：解析规则同时存在于 `field_mapping_templates.field_parse_rules` 与 `field_mapping_template_variants.field_parse_rules`（28/28 双写，当前碰巧 0 分歧，但 DB 层无约束）。

**后果**：任一处变了其余不会跟着变 ⇒ 只能靠"事后检测漂移 + 补丁端点"收敛。

### P0-2 生效判定被拆成 6 个互不相干的开关，判定权散在多处

| 开关 | 含义 |
|---|---|
| `shop_accounts.enabled` | 店铺是否在营（主数据） |
| `collection_config_shop_scopes.enabled` | 该配置是否采这个店 |
| `collection_configs.is_active` | 配置是否启用 |
| `collection_configs.batch_status` | draft/active/completed/disabled |
| `collection_config_templates.is_active` | 模板是否启用 |
| `shop_account_capabilities.enabled` | 该店能否采某域 |

**关键错配**：执行侧真正生效的范围 =
`scope.enabled ∧ shop.enabled ∧ capability.enabled`
（`collection_config_execution.py:173-188, 277-280`），
而**摘要列 `account_ids` 只算了 `scope.enabled`**。

⇒ 「店铺总览 19 vs 身份/数据 18」对不上是**结构性**的，不是数据脏。

### P0-3 模板与文件的关系是"运行时猜出来的"

`template_matcher.py:105-204` 定义**三级降级**（账号专属 → 精确 → 忽略 sub_domain，services 域禁止降级）。文件靠 `platform/data_domain/granularity/sub_domain/account` 五个**同名维度列**去猜该由哪版模板解释。

代码自己都承认："「一个文件该由哪一版模板解释」这件事, 历史上散落在三处, 口径各不相同"（`template_matcher.py:207-215`）。

### P0-4 漂移指纹只覆盖列名，不覆盖列里值的形态

**这是 Shopee analytics 整文件入库失败的根本原因：**

- 漂移检测比的是 `header_changes.added_fields / removed_fields`（列名集合）+ `columns_hash`；
- 平台导出把日期从 `01/11/2026` 改成 `01-11-2026`，**列名一个没变** ⇒ 漂移检测**完全看不见**；
- 文件一路走到解析器才炸：`parse_date_by_declared_format`（`smart_date_parser.py:250-302`）用模板声明的 `%d/%m/%Y` 去 parse 连字符 ⇒ `raw_data_importer.py:626-632` 抛错 ⇒ **整个文件失败**。

保存端对 `date_format` **只查非空、不查合法性**（`field_mapping_templates.py:1079-1081`）；解析器白名单 `_DECLARED_SINGLE_FORMATS`（18 个 token，`smart_date_parser.py:34-53`）**保存路径从不调用**。

⇒ 模板里可以写一个解析器根本不认识的格式，保存时不报错。

### P1-1 模板体系 8 张表、两套模型并存、规则双写

`field_mapping_templates` / `_families` / `_versions` / `_variants` / `_items` / `field_mapping_dictionary` / `field_mappings` / `_audit`

- `_items`（**4748 行**）v4.6.0 已废弃（改用 `header_columns` JSONB），表与数据都还在；
- `field_mappings` **0 行**的空表，却还被迁移契约测试钉着；
- `families.source_mode='legacy_projection'` ⇒ 族/版本/变体三层**不是真模型**，只是 legacy 模板行的投影；
- `versions` 表**没有** `field_parse_rules` ⇒ 号称"版本快照"却不携带真正决定入库行为的那份数据。

### P1-2 模板历史没有治理

- 33 个五维组合 → 254 行，**30 个组合有多个版本**，最多一个组合 **20 个版本**（`tiktok/products/monthly`）；
- 只有 27 行 `published`；
- `miaoshou/products/snapshot` 有 18 行历史模板、**0 行 published** ⇒ 该组合当前**没有任何生效模板**；
- "当前生效"无显式指针，靠 `status='published' + version desc` 隐式排序（已核对：目前**没有**组合出现 2 个 published，唯一性成立但只是写入路径的副作用，不是约束）。

### P1-3 命名承载了非业务语义

`shopee_analytics__monthly_slash_v3`、`shopee_services_agent_monthly_slash_v2` —— `_slash` / `_dash` / `__` 是**文件名分隔符变体**，不是业务维度，却写进模板名与 `variant_key`，代码还要特判 `"dash"`（`template_family_service.py:270-271`）。

⇒ 同一 `version=3` 能有 `..._monthly_v3`(138) 与 `..._monthly_slash_v3`(321) 两行并存，"哪行对"要靠人眼。

### P1-4 "批次"不是实体，状态机是半成品

- 四列拼一个批次，约束散落在 5 个函数；历史配置靠 `POST /config-template-backfill` 补造（`batch_note='legacy backfill'`）；
- `batch_status` 允许 `completed`，但**后端没有任何一处写入它**；
- `batch_status` 与 `is_active` 互为镜像（`collection_config.py:1042`），两个字段表达同一件事。

### P1-5 用一批"补丁端点"维持副本一致

`collection_config.py` 的 10 个端点里有 6 个是为对齐副本而存在的：
`batch-remediate` / `clone-next` / `reapply-template` / `advance-current` / `advance-current-granularity` / `apply-time-selection` / `create-future-batches` / `config-template-backfill`。

`reapply-template` 这个端点的存在本身，就等于承认"模板和配置会漂移"。

### P2 工程债

- `collection_config.py` 里 **3 个端点被完整复制了两遍**（`/accounts`、`/accounts/grouped`、`/config-coverage`，约 180 行字节级相同）⇒ ruff F811；
- `data_sync.py` **4489 行**单文件；
- **两套迁移体系并存**：`migrations/`（97 版）与 `current_migrations/`（54 版）；
- 枚举重复：粒度 3 份、平台 4 份、data_domain 3 份、日期目标字段 3 份；
- "当前配置"的挑选逻辑在 `collection_config.py` 与 `collection_schedule.py` 各写了一遍。

---

## 3. 两个线上事故的设计解释

| 事故 | 设计层解释 |
|---|---|
| 采集工作区一行点不动的幽灵店铺 | 「是否参与」被拆成 `scope.enabled` 与 `shop.enabled` 两个开关，写入路径只管前者 ⇒ 停用店铺后没人回头；摘要列与执行侧口径不同 ⇒ 顶部数字对不上；模板默认范围又把死店带进新建配置 ⇒ 400 |
| Shopee analytics 整文件入库失败 | 平台导出格式变了，但漂移指纹只覆盖列名不覆盖值形态；模板把"平台导出的字面格式"当成硬编码断言；保存端不校验格式合法性 ⇒ 变更直到入库才炸，且炸的是**整个文件** |

⇒ **不是两个 bug，是同一条主线的两个断面**：同一件事被写在多个地方，没有单一事实源；不一致只能靠事后检测与补丁端点收敛，而检测覆盖不到真正的变化面。

---

## 4. 根治方案

**一句话：把"同一件事被写在多个地方"改成"每件事只有一个事实源，其余都是读时派生"；把"变更检测"从"事后比对列名"升级成"入库前拿真实文件试解析"。**

### 4.1 变化点总表

| # | 维度 | 改造前 | 改造后 | 直接收益 |
|---|---|---|---|---|
| 1 | 店铺清单 | 4 处副本 | 只 1 处（`shop_scopes`），模板不再存清单 | 改一次店不用同步 4 处；`reapply-template` / 前端 `syncTemplateShopScopes` / `batch-remediate` 可删 |
| 2 | 摘要数字 | 写时缓存，口径只算 `scope.enabled` | 读时由 `scope ∧ shop ∧ capability` 派生（与执行侧同口径） | "19 vs 18"对不上从根上消失；摘要重算的迁移/联动代码全可删 |
| 3 | 停用店铺 | 只改主数据 ⇒ 残留 ⇒ 靠写时级联补 | 只改主数据；**是否参与是读时求值结果**，不做级联 | 店铺域不再依赖采集域；写时级联引入的测试失败自然消失 |
| 4 | 模板↔文件 | 入库时按 5 维**猜**哪版模板 | 登记时用候选模板**试解析真实文件**，不过就地标"需更新"+精确原因 | 失败从"整文件 failed、事后才知道"变成"登记时就地提示" |
| 5 | 漂移指纹 | 只覆盖列名 | 覆盖**列名 + 每个日期列的实测字面格式集合** | 平台改格式，采集那一刻就被标"格式漂移" |
| 6 | 格式声明 | `date_format` 自由文本，保存只查非空 | 保存时必须在解析器白名单内；支持 `format_candidates` | 非法格式在保存模板那一刻就被挡下 |
| 7 | 批次 | 四列拼出来的；`completed` 没人写；与 `is_active` 镜像 | 承认"批次 = 配置沿时间窗推进"，删四列 | 半成品状态机与双字段镜像一起消失 |
| 8 | 模板版本 | 隐式 `published + version desc`；254 行 227 行垃圾；`versions` 不含规则 | 族上显式当前指针；规则与版本绑定；历史行清退 | "当前用哪版模板"一眼可查、可审计 |
| 9 | 枚举/常量 | 粒度 3 份、平台 4 份、data_domain 3 份、日期目标字段 3 份 | 各收敛成一份 SSOT | 少一类"改一处漏一处" |
| 10 | 死表/死代码 | `_items`(4748 行)、`field_mappings`(0 行)；3 端点复制两遍 | 清掉 | 表少 2 张、代码少 180 行、ruff F811 归零 |

### 4.2 落地批次

**批次 1 · 采集侧事实源收敛（收益最大）** —— 做 1 / 2 / 3 / 7 / 10

- `shop_scopes` 成为唯一店铺范围事实源；摘要三列改**读时派生**（保留列作缓存但读时不信它 ⇒ 不改 schema、不破坏下游看板）
- 取消停用/删除店铺时的**写时级联**，生效范围改读时求值
- 模板降级为"域集合 + 默认口径 + 默认 cron"，`default_shop_scopes` 只作**首次种子**，之后按账号派生
- 删 `batch_*` 四列；删 `reapply-template` / `batch-remediate` / 前端 `syncTemplateShopScopes` / `buildDefaultShopScopes`
- **存量模板一次性迁移**：`default_shop_scopes` 里的店铺项不再被当清单使用

**验收**：停用店铺 → 工作区不出现（**零写操作**）；新增店铺 → 不需要动任何模板/配置；顶部统计与实际生效范围 100% 一致（用一条不变量测试锁住）

**批次 2 · 同步侧 fail-early** —— 做 4 / 5 / 6

- 文件登记后**立刻**用候选模板试解析（只读、不落库）⇒ 不过就标 `template_update_required` + 精确原因（哪一列、什么格式、试了哪些候选）⇒ 不进 pending 队列
- 指纹升级为"列名 + 值形态"
- `date_format` 保存时校验白名单；模板支持多候选格式

**验收**：平台改导出格式 ⇒ 文件在登记阶段被标"格式漂移"，**不产生 failed、不污染队列**

**批次 3 · 模型与工程收敛** —— 做 8 / 9 / 10（剩余）

- 模板族显式当前指针 + 历史治理；清死表
- 枚举 SSOT；删重复路由块；`data_sync.py` 按职责拆分

### 4.3 代价与风险

| 项 | 说明 |
|---|---|
| 摘要改读时派生 | 多几次查询 —— 42 条 scope / 14 个配置，量级无压力，可按 config 批量算，不是 N+1 |
| 模板不再存店铺清单 | 已存在的 13 个模板要一次性迁移；前端"模板默认范围"交互要重画（**唯一有用户可见变化的地方**） |
| 删 `batch_*` 四列 | 动到历史数据（14 个配置，可控） |
| 批次 2 试解析 | 需要文件在登记时能读到表头与前若干行 —— 采集产物本来就在本地磁盘，可行 |

---

## 5. 与「停用店残留」补丁分支的关系

分支 `feature/shop-disabled-scope-cleanup` 的三层修复，按本方案**降级为批次 1 的第一步**：

| 原三层 | 新方案下 |
|---|---|
| 第一层（迁移清存量） | **保留**，仍是批次 1 的必要一步 |
| 第三层（停用店彻底不显示） | **保留**，读时过滤即是新方案的形态 |
| 第二层（停用时写时级联） | **取消** —— 被"读时求值"取代 |

该分支 18 条守护测试里，关于"迁移清存量""响应层不显示""口径等价"的部分**全部继续有效**；只有"停用时写时级联"几条要改成断言"**不发生写操作**"。

### 5.1 分支回归的 4 个新增失败 —— 归属判定

| 失败 | 归属 | 证据 |
|---|---|---|
| `test_shop_accounts_api::test_status_only_updates_...` | **本分支引入** | 第二层让 `shop_accounts` 路由要读 `collection_config_shop_scopes`，而该测试的 SQLite 夹具只建了 4 张表 ⇒ `no such table` |
| `test_shop_rename_flow::test_rename_end_to_end_...` | **本分支引入** | 同上 |
| `test_utf8_editor_guardrails_are_declared` | **环境差异** | worktree 缺 `.vscode/settings.json`（被 gitignore，未进 worktree） |
| `test_data_sync_governance_status_consistency::test_governance_detailed_coverage_skips_temp_development_sample_files` | **环境差异** | worktree 缺 `data/`（`data/**/*.json` 被 gitignore）；已用 `git stash` 隔离证明：**把我的改动 stash 掉后仍然失败** ⇒ 与本分支代码无关 |

⇒ 真正需要负责的只有前 2 个，而它们的根因恰好就是"写时级联"这个设计上该取消的东西。
