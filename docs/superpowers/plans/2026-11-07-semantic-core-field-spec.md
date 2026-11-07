# 翻译层 / 核心字段 规格（定稿）

> **状态**：业务概念已由 Walter 拍板（2026-11-07）。本文是**概念落地的规格**，不是实施计划；实施批次见 §5。
> **配套**：`2026-11-07-template-sync-design-review.md`（10 类根因清单）、`2026-11-07-disabled-shop-scope-cleanup.md`（旁支补丁，与本规格无耦合）。
> **分支**：`feature/semantic-core-field-refactor`（独立 worktree `.worktrees/semantic-core-field-refactor`，基于 `main@a15e5db3`）。

---

## 0. 决策记录

| # | 议题 | 结论 | 依据 / 后果 |
|---|---|---|---|
| **D1** | 指标类字段能否参与 `data_hash` | **能**，放开为自由勾选 | 现状 `semantic_hash_policy_service.py:103-111` 对 `kind == "metric"` 硬性拒绝，理由"Metric fields are measures, not row identity fields"。这与「日期 + 订单数 + 店铺 = 这一行是什么」的业务概念**直接冲突**——后者是复合业务键，不是实体身份。 |
| **D2** | `hash_participates` 字段 | **删除该字段**；「参与去重」这个属性保留，搬到核心字段清单 | 该字段绑定级（某列→某语义键）、**已声明未接线**（不喂 `calculate_data_hash`）、与模板级 `deduplication_fields` 构成同一事实两处真相。 |
| **D3** | 用户手动对齐的别名沉淀范围 | **全局沉淀，一处生效** | 落点需新建（见 §3.3）；三张现有别名表均为静态字面量、零写入路径。 |
| **D4** | 「哪些字段缺失才算阻断」的归属 | **并入核心字段清单** | `core.semantic_field_contracts` 已有 32 行，且服务层**已支持读表**（`semantic_field_contract_service.py:282-291` DB 优先、常量兜底）⇒ 不必新建表，但必须把它从"另一份独立清单"降为"域级下限护栏"。 |

---

## 1. 业务概念（评审口径）

> 每个数据域有一份**标准字典**；用户在可视化页面**审一次**，决定两件事：**哪些业务数据要入库**、**拿什么判定「这是同一条记录」**；之后平台改列名，系统**自动认出来**，不用再审。

### 1.1 五个概念

| 概念 | 定义 |
|---|---|
| **标准字段** | 业务含义。`销售额` 就是 `销售额`；平台叫 `销售金额` / `Sales Amount` / `销售金额(SG)`，在系统里是同一个东西。 |
| **翻译层** | 列名 → 标准字段。**全局唯一、只增不改**。用户审一次 = 永久生效。 |
| **模板** | 一个数据域的翻译说明书：有哪些列、怎么解析、哪些必填、哪些参与去重。 |
| **变体** | 同一份说明书的**地区差异页**，不是新说明书。 |
| **漂移** | 平台改了文件结构。 |

### 1.2 用户的两个勾选

| 勾选 | 含义 | 决定什么 |
|---|---|---|
| **核心字段** | 这个域我要哪些业务数据 | **落哪些库列**（列名统一成标准字段键 ⇒ 跨平台同义列落进同一列） |
| **参与去重** | 其中哪些用来判定同一性 | **指纹怎么算** |

平台 / 店铺 / 数据域 / 时间粒度由系统自动附加，**不可取消**。

### 1.3 指纹怎么算

取你勾的字段的**内容**——**按标准含义取，不看列名叫什么**——加上系统自动附带的身份，算一个指纹。

- 指纹一样 ⇒ 同一条记录 ⇒ **更新**，不新增
- 指纹不同 ⇒ 新记录 ⇒ 新增

### 1.4 漂移怎么处理

| 情况 | 处理 |
|---|---|
| 核心字段变了（且是必填的） | **阻断**，等人处理 |
| 核心字段没变，只是**多了新列** | **不阻断，照常入库**；新列先原样存着，等有空再决定它是什么 |
| 列只是换了名字（含义没变） | **不阻断**，翻译层认出来即可 |

---

## 2. 现状基线（开发库实测，2026-11-07）

### 2.1 事实来源（四处并存，互不相认）

| 来源 | 位置 | 规模 | 现状 |
|---|---|---|---|
| 后端注册表 | `backend/services/semantic_field_registry.py` | 41 标准字段 / 180 别名 | **代码内常量**，读取路径零 DB 依赖 |
| 前端副本 | `frontend/src/domains/data_platform/utils/headerBindings.js` | `SEMANTIC_FIELD_ALIASES` / `SEMANTIC_FIELD_META` | **副本**，且**无任何 `required: true`** ⇒ 与后端已漂移 |
| DB 辞典 | `core.field_mapping_dictionary` | 34 行 | 全 `orders`；`synonyms` 全为 `[]`、`platform_synonyms` 全 NULL；`cn_name` 乱码；`field_code` 与注册表**编码体系不一致**（`buyer_paid_amount` vs 注册表 `paid_amount`） |
| 硬编码别名表 | `template_alias_registry.py:39`（16 条）、`semantic_field_contract_service.py:126`（2 域） | — | 纯静态字面量，**零写入路径** |

### 2.2 已有落点（可复用，不必新建）

| 表 | 行数 | 判定 |
|---|---|---|
| `core.semantic_field_contracts` | **32**（orders weekly/monthly + analytics daily/monthly，`platform` 全 NULL，`consumer='business_overview'`） | 服务层**已支持读表**，DB 优先、常量兜底。缺口：orders 无 `daily`、analytics 无 `weekly`（靠常量兜底侥幸没洞）。 |
| `b_class.entity_aliases` | 0 | 语义是**实体**别名（account/shop/store），**不适合**存字段别名。 |
| `core.field_mapping_dictionary` | 34 | 字段**定义**表，`synonyms`/`platform_synonyms` 本是为别名预留但全空；因 `field_code` 体系与注册表漂移，**不作为别名落点**。 |

### 2.3 翻译命中率（实测，逐字相等匹配）

| 数据域 | 文件列数 | 命中标准字段 |
|---|---|---|
| shopee / orders / monthly | 91 | 6 |
| shopee / products / monthly | 40 | **0** |
| miaoshou / inventory / snapshot | 28 | **0** |
| shopee / analytics / monthly | 9 | 1（仅「日期」） |

落空典型：`页面浏览次数`（别名只有 `浏览量`）、`跳出率`（只有 `跳失率`）、`商品访客数量`（只有 `商品访客数`）。

### 2.4 核心字段清单的现状（27 个已发布模板）

`core.field_mapping_templates`：`published` 27（**27 个都带 `deduplication_fields` 与 `header_bindings`**）；`archived` 227（仅 88 带 dedup、39 带 bindings）。

**`deduplication_fields` 里混着两种东西**——语义键与中文原始列名：

| 模板族 | `deduplication_fields` | 形态 |
|---|---|---|
| analytics × 6 | `["metric_date"]` | 语义键 |
| orders × 6 | `["product_id","platform_sku","sku_id","order_id"]` | 语义键（identity 类） |
| services / ai_assistant × 3 | `["metric_date"]` | 语义键 |
| inventory × 1 | `["*商品SKU","*商品名称","*规格","仓库"]` | **中文原始列名**（且带 `*` 占位符前缀） |
| products / shopee × 3 | `["商品编号","商品","规格编号","规格名称","全球商品货号"]` | **中文原始列名** |
| products / tiktok × 2 | `["ID","商品","状态"]` / `["product_id"]` | 混合 |
| services / agent × 3 | `["日期期间"]` | **中文原始列名** |
| services / agent / tiktok × 2 | `["客服ID","客服昵称","metric_date","被分配会话数","满意度"]` | **混合，且含 metric 类**（`被分配会话数` / `满意度`） |

⇒ 这两类字段在 `calculate_data_hash` 里走**不同分支**（语义键走 `resolve_semantic_value`；中文列名走 `row.keys()` 逐字匹配），**同一份清单内 hash 行为不一致**。

### 2.5 漂移判定链（现状）

| 层 | 位置 | 产出 |
|---|---|---|
| ① 表头比对 | `template_matcher.detect_header_changes` | `added_fields` / `removed_fields` / `is_exact_match` / `is_semantic_match` |
| ② 语义契约 | `semantic_field_contract_service.evaluate:136` | `missing_required_keys` / `missing_optional_keys` / `extra_raw_fields` → `semantic_contract_status` |
| ③ 是否阻断 | `data_sync_service._is_blocking_header_change:428` | 最终裁决 |
| ④ 定级 | `data_sync_template_status_service.py:373-391` | `ready` / `alias_only`(自动入库) / `update_required`(阻断) |

**新增列不阻断**：`extra_raw_fields` 非空 ⇒ `non_breaking_drift` ⇒ `should_auto_sync=True` ⇒ 照常入库，模板不必更新（`data_sync_service.py:1317` 标记 `semantic_drift_allowed`）。
**但**：这些列不会被翻译、不参与指纹、且**每次**被记成 `extra_raw_fields` ⇒ 治理面板上是一条永久噪音（系统没有"这列已确认，忽略它"的表达方式）。

### 2.6 与目标概念的四条差距

1. 「哪些是核心字段」有**两套**（用户勾的 `deduplication_fields` vs 代码/DB 的 `required` 契约），互不相认
2. 契约只覆盖 **2/5** 个域（`products` / `inventory` / `services` 无契约 ⇒ 恒 `not_configured` ⇒ 永不阻断 ⇒ 漂移无人管）
3. 用户审一次的成果**不沉淀**（三张别名表零写入路径），同一件事要审 N 次
4. 落库列**不是**按核心字段收窄：`ensure_columns_exist`（`dynamic_column_manager.py:156`）对**每个**文件表头列 `ADD COLUMN`，并在 `raw_data_importer.py:1436-1469` 逐列 UPDATE 赋值 ⇒ 每个业务字段**存两份**（JSONB + 物理 TEXT 列）

---

## 3. 目标数据模型

### 3.1 核心字段清单（新增，模板**版本**级）

**位置**：`core.field_mapping_template_versions` 新增 JSONB 列 `core_fields`。

```json
[
  {"semantic_key": "metric_date", "required": true,  "in_hash": true},
  {"semantic_key": "order_count", "required": false, "in_hash": true},
  {"semantic_key": "sales_amount","required": false, "in_hash": false}
]
```

**为什么落在版本级而不是域级**：
- 同一族的多个变体共享版本 ⇒ 共享清单 ⇒ **审一次，全变体生效**（对应 §1「审一次能用很久」）
- 改清单 = 发新版本 ⇒ 可回溯，与既有"发布即版本"机制一致
- 域级差异（某平台多一个必填）走**变体级覆盖**，不污染版本

**⚠️ 与 `field_parse_rules` 的层级归属必须一并定死**：

现状 `field_parse_rules` **不在 versions 表**，只在 `field_mapping_template_variants`（变体级）和 legacy `field_mapping_templates` 表上；而 `deduplication_fields` / `header_bindings` 在 versions 上。⇒ **规则被拆在两级**，改一处漏一处。

本规格的划分（须加守护测试锁住）：

| 归属 | 内容 | 理由 |
|---|---|---|
| **版本级** | `core_fields`（核心字段 + required + in_hash）、`header_bindings`（列→语义键） | **业务契约**：跨变体共享，改动走版本、可回溯 |
| **变体级** | `field_parse_rules`、`header_row`、`sheet_name_pattern`、`required_headers` | **文件形态**：同一业务在不同文件形态下解析方式不同 |

守护测试：版本的 `core_fields` 必须能被该版本下**每一个**变体满足（变体声明的解析规则要能产出 `core_fields` 要求的字段）。

**三处消费，一份真相**：

| 消费方 | 读什么 | 效果 |
|---|---|---|
| 落库列 | `core_fields` 全集 | 只为核心字段建物理列，列名 = 标准字段键 |
| `data_hash` | `core_fields` 中 `in_hash=true` 的 + 系统身份 | 指纹组成 |
| 漂移阻断 | `core_fields` 中 `required=true` 的 **∪** 域级契约 required | 缺失则阻断 |

⇒ 用户勾一次，三件事一起生效。这就是「同一事实一份副本」。

### 3.2 标准字段定义（收敛成一份）

- **后端 `semantic_field_registry` 保持代码内权威**：读取路径零 DB 依赖、启动即用、所有服务已从它读
- **前端删副本**：`headerBindings.js` 的 `SEMANTIC_FIELD_ALIASES` / `SEMANTIC_FIELD_META` 改为从接口取
- **`core.field_mapping_dictionary` 降级为只读参考**：34 行与注册表重复、`cn_name` 乱码、`field_code` 体系漂移 ⇒ 本批次**不动它**，但登记为已知债；**不得**把新别名写进去（会把第 4 份定义的漂移固化）

### 3.3 全局别名沉淀（D3 落点）

**新建** `core.semantic_field_aliases`：

| 列 | 说明 |
|---|---|
| `raw_name` | 平台原始列名（归一化后存，保留原始名于 `raw_name_original`） |
| `semantic_key` | 标准字段键 |
| `source` | `user_confirmed` / `system` |
| `origin_template_id` / `origin_binding` | 来源追溯 |
| `enabled` | 可撤销（不做物理删除） |
| `created_by` / `created_at` / `updated_by` / `updated_at` | 审计 |

**冲突规则**（遵守「歧义宁可落 unknown 报警，绝不静默猜一个」）：
- 同一 `raw_name` 已绑到**不同** `semantic_key` ⇒ **不静默覆盖**，落 `conflict` 状态并**报警**，由人裁决
- 同一 `raw_name` 绑到**相同** `semantic_key` ⇒ 幂等，记录来源（可多条来源）

**全局生效的代价与对策**：D3 选择"一处生效"，代价是**同名异义**风险（某平台「销售额」指已付款额、另一平台指总销售额）。对策 = 上面的冲突检测 + `enabled` 可撤销 + 命中后仍保留 `raw_name` 与 `semantic_key` 的可追溯性。

### 3.4 必填契约并入（D4 落点）

- `core.semantic_field_contracts` 保留，但**角色降为「域级下限护栏」**：它表达"这个域**无论哪个平台**都必须有的字段"
- 模板级 `core_fields.required` 是**主来源**（用户勾的）
- 约束关系：**模板级 required ⊇ 域级契约 required** ⇒ 由守护测试锁住
- 补齐 `core.semantic_field_contracts` 的粒度缺口（orders/daily、analytics/weekly），避免继续依赖常量兜底

### 3.5 `hash_participates` 下线（D2）

- **删除绑定级 `hash_participates` 字段**（含前端 `headerBindings.js:544/615/659` 的推导、`TemplateUpdateWorkbenchDrawer.vue:817` 的计数用途）
- 「参与去重」改由 `core_fields[].in_hash` 表达
- 保留 registry 的 `hash_eligible`（闸门）但**改口径**：从"按 identity/metric 分类一刀切"改为"能否唯一标识一行"（D1）⇒ `order_count` / `sales_amount` 等 metric 类可参与
- 保留 `required`（语义键级），与 `core_fields[].required` 对齐

---

## 4. 目标流程（采集 → 同步 → 使用）

**A · 采集**
1. 采集器按 `collection_config` 的 scope 拉文件 → `catalog_files`
2. 表头 → 翻译层：列名 → 标准字段（**归一化 + 域限定 + 值形态**；自动推断 + 人工审查兜底）→ `header_bindings`
3. 模板匹配：按 `(platform, domain, granularity, 变体)` 精确命中

**B · 同步（入库）**
4. 解析层：`field_parse_rules` 决定日期/数值解析（含 `format_candidates`）；失败 ⇒ 该文件**阻塞并告警**，不整批崩
5. 身份盖章：平台/账号/店 → `platform_code` / `shop_id`（定不了 ⇒ 落 unknown + 告警，绝不猜）
6. **语义归一收口**：所有同义列（`销售额` / `销售金额` / `销售金额(SG)`）在入库前归一到同一个语义键 —— **唯一收口点**
7. 指纹：`data_hash = f(core_fields[].in_hash 的语义归一值 + scope 身份 + 日期身份)`
8. 落库：**只为 `core_fields` 全集建物理列**；其余字段只进 `raw_data` JSONB 存档
9. 写入：UPSERT by `data_hash`

**C · 使用**
10. 下游读 `semantic` view / `mart` 表，**按标准字段键读列** ⇒ 跨平台同义列天然对齐，`UNION ALL` 拼同构表的必要性下降

---

## 5. 实现批次

| 批次 | 内容 | 风险 | 可独立上线 |
|---|---|---|---|
| **① 翻译层扶正** | 别名匹配从逐字相等升级为**归一化 + 域限定 + 值形态**（纯算法）；`core.semantic_field_aliases` 落地；用户手动对齐自动沉淀 + 冲突报警；命中率护栏测试 | 低（不改生产链路） | ✅ |
| **② 核心字段清单** | `core_fields` 列 + 迁移 27 个 published 模板；`hash_participates` 下线；`hash_eligible` 口径放开（D1）；三处消费接线 | **中**（改 hash 组成 ⇒ 口径变更） | ⚠️ 见 §6 |
| **③ 落库列收窄** | `ensure_columns_exist` 只按 `core_fields` 建列；历史列保留读兼容 | 中（触 67 张表） | ✅ 需独立迁移 |
| **④ 漂移口径统一** | 契约并入 + 粒度补齐；`extra_raw_fields` 噪音治理（"已确认的新列"可忽略）；补齐 3 个无契约域 | 低 | ✅ |

---

## 6. 迁移与风险

### 6.1 ⚠️ 指纹口径变更的影响面（批次 ② 的硬风险）

改动「按语义键取值 + 指标可进 hash」会**改变存量模板的 `data_hash`** ⇒ 历史行在下次采集时被判为新行 ⇒ **可能产生重复行**。

按 §2.4 盘点：

| 影响类型 | 模板数 | 例子 |
|---|---|---|
| `deduplication_fields` 含**中文原始列名** ⇒ 改走语义路径后取值口径变 | **9** | inventory × 1、products/shopee × 3、products/tiktok × 2、services/agent/shopee × 2、services/agent/tiktok × 1 |
| 含 **metric 类**语义键 ⇒ D1 放开后参与范围变 | **2** | `tiktok_services_agent__daily_v1`、`__monthly_v1`（`被分配会话数` / `满意度`） |
| `*商品SKU` 类**占位符列名** ⇒ 无法翻译 | **1** | `miaoshou_inventory__snapshot_v3` ⇒ 须降级为"逐字匹配"并明确告警 |

**处置**：
1. 批次 ② 上线前先跑**离线回放**：对存量 `catalog_files` + 样本行分别用旧/新口径算 hash，产出「hash 变化行数 / 不变行数」报告
2. hash **不变**的行：零影响
3. hash **变化**的行：给出**重算与回填**方案（按新旧 hash 对齐后 UPDATE，或标记为新版本行），**不做静默双写**
4. 口径切换必须是**显式开关**，可一键回退到旧口径

### 6.2 落库列收窄（批次 ③）的兼容策略

- **只对新增列生效**：历史已建的物理列**保留**（读兼容），不物理删除
- 新列只按 `core_fields` 建列；非核心字段只进 `raw_data` JSONB
- `MAX_COLUMNS_PER_TABLE=1600` 的上限压力缓解 ⇒ 67 张表的 67 种列结构逐步收敛
- ⚠️ 现有下游 `semantic` view 用 `UNION ALL` 拼同构原始表 ⇒ 列结构变化会**影响 view 定义**，必须同步走迁移 + 守护测试

### 6.3 其它风险

| 风险 | 对策 |
|---|---|
| D3 全局别名的**同名异义** | 冲突检测 + 报警 + `enabled` 可撤销（§3.3） |
| `data_hash` 对**值类型敏感**（`_normalize_hash_value` 只转 date/datetime，不做数值归一）⇒ 数字 `100` vs 字符串 `"100"` 指纹不同 | 批次 ② 内加**值归一**：去千分位、统一小数位、去尾零 |
| 翻译命中率低 ⇒ 静默退化为逐字匹配 | 命中率护栏测试 + 退化路径**告警**（当前只有 debug 日志） |
| 前端副本与后端注册表漂移 | 批次 ① 改为接口取，删副本；守护测试锁住一致 |

### 6.4 锚点事故：Shopee analytics 日期格式漂移（批次② 的验证样本，也是最硬的现存缺陷）

**现象**：模板 `shopee_analytics__monthly_slash_v3` 声明
`{"strict": true, "value_kind": "single_date", "date_format": "dd/mm/yyyy", "target_field": "metric_date", "source_column": "日期"}`，
而实际月度流量导出的「日期」列是 **`01-11-2026`（横杠）** ⇒ `raw_data_importer.py:625-628` 抛
`failed to parse metric_date from source_column=日期: 01-11-2026` ⇒ **整文件入库失败**（不是跳过该行）。

**不是解析器能力不足**：`dd-mm-yyyy` 就在白名单里（`modules/services/smart_date_parser.py:41`），
`strptime("01-11-2026", "%d-%m-%Y")` 直接解出 2026-11-01。`parse_date_by_declared_format:301` 是**严格模式、无回退**，
所以**模板声明与真实文件不符**是唯一病因。

**为什么系统一直没发现**（三层失守）：

| 层 | 失守点 |
|---|---|
| ① daily/weekly 逃过一劫（**不是修复**） | 它们声明 `source_column: "__file_date_from__"` ⇒ **根本不读表里的「日期」列**，用文件元数据期间 ⇒ `date_format` 写对写错都无所谓。**只有 monthly 真正读列** ⇒ 只有 monthly 会炸 |
| ② 漂移检测只看结构不看值形态 | 「日期」这一列还在 ⇒ 列名比对通过 ⇒ 判定 `ready` ⇒ **不提示更新模板** ⇒ 直到真文件进来才炸 |
| ③ 保存闸门不校验格式合法性 | `_validate_field_parse_rules`（`field_mapping_templates.py:1041`）只检查 `date_format` **非空**，不检查是否在白名单内，更不拿样本值试解析 ⇒ 任意字符串都能存进模板 |

**修法**（三选一，`(c)` 为推荐）：

| 方案 | 做法 | 评价 |
|---|---|---|
| (a) | 改 `date_format` 为 `dd-mm-yyyy` | 最小改动，平台下次再改又炸 ⇒ **治标** |
| (b) | 解析器宽松回退、试多个格式 | 违背「定不了就报警，绝不静默猜一个」⇒ **否决** |
| **(c)** | `date_format: "auto_by_companion_period"` + **显式** `format_candidates: ["dd-mm-yyyy","dd/mm/yyyy"]` | **推荐**（已用真实失败文件验证，见下） |

**(c) 为什么正确 —— 精确表述**：

- `strptime` 的**分隔符是硬约束**：`"01-10-2026"` 只有 `dd-mm-yyyy` 能解析成功，`dd/mm/yyyy` 直接 ValueError。
  ⇒ **同一语义的不同分隔符不会互相冲突**，companion period 消的不是分隔符歧义。
- 真正的歧义来自**月/日顺序**：`dd-mm-yyyy` 与 `mm-dd-yyyy` **都接受** `"01-10-2026"`，
  但前者 = 2026-10-01、后者 = 2026-01-10 ⇒ **语义相反，必须消歧**。
- `_parse_by_companion_period`（`smart_date_parser.py:209-247`）正是消这个：候选逐个试，
  **只有落在文件期间内的才算匹配**；零匹配 ⇒ 报错；多匹配 ⇒ 报「歧义」而非随便选一个。
- ⚠️ **`format_candidates` 必须显式给**：`_candidate_formats_for_auto:190-206` 在不传时返回**全部 18 个**
  `_DECLARED_SINGLE_FORMATS`，会引入大量无关候选、抬高「多匹配 ⇒ 报歧义」的概率，让本该过的文件反而被拒。
- ⚠️ **auto 模式有硬前提**：`_parse_by_companion_period:221-222` 要求 `companion_date_from` 与
  `companion_date_to` **均非空**，否则直接 raise。

**生产实证（开发库实测，2026-11-07）**：

| 验证项 | 结果 |
|---|---|
| 失败文件 | 4 个（`shopee_analytics_monthly_20261102/03/05/07_*.xlsx`），错误全部为 `failed to parse metric_date from source_column=日期: 01-10-2026` / `01-11-2026` ⇒ 实际格式是**横杠** |
| 文件期间元数据 | `date_from` / `date_to` **480/480 全部填充** ⇒ auto 模式前提成立 |
| 行日期是否落在文件期间内 | 用历史数据联表验证 `fact_shopee_analytics_monthly`（1748 行可关联）：`metric_date < date_from` **0 行**、`metric_date > date_to` **0 行** ⇒ 期间消歧**不会误杀** |
| 消歧唯一性 | `"01-10-2026"` 按 `dd-mm-yyyy` = 2026-10-01 ∈ [10-01, 10-31] ✓；按 `mm-dd-yyyy` = 2026-01-10 ∉ 期间 ⇒ **唯一匹配** |
| 报表粒度 | `fact_shopee_analytics_monthly` 2278 行 / **181 个不同 metric_date**（2026-02~07 ≈ 6 个月 × 30 天）⇒ **Shopee monthly 是逐日明细**；`fact_tiktok_analytics_monthly` 1374 行 / **9 个日期** ⇒ **TikTok monthly 每月一行** |
| 为何只有 monthly 读表头日期列 | 逐日明细必须按行取日期；daily/weekly 是一行汇总 ⇒ 用 `__file_date_from__` 即可 ⇒ **daily/weekly 是"恰好不受影响"，不是"设计正确"** |

**回填风险：无** —— 该模板至今 **0 行**落库（`max(metric_date)=2026-07-31`），改格式不产生历史行 hash 变化。

**⚠️ 附带发现：Shopee analytics 存在 4 个月数据断档**（`public.catalog_files` 按 `date_from` 分组实测）：

| 期间 | 文件数 | ingested | failed |
|---|---|---|---|
| 2026-02 ~ 2026-06 | 10/11/15/14/52 | 全部 ingested | 0 |
| 2026-06-06（daily） | 1 | 1 | 0 |
| **2026-07 ~ 2026-09** | **0** | — | **根本没采集** |
| **2026-10-01** | 3 | 0 | **3（全失败）** |
| **2026-11-01** | 1 | 0 | **1（全失败）** |

⇒ 2026-07~09 是**采集侧断档**（无文件），2026-10~11 是**同步侧格式漂移**（采到了但全部失败）。
⇒ 该域已连续 4 个月无新数据 —— 这正是「受店铺身份修复影响最大的域至今无新落库数据」的真正原因。

**根治还需补两条**（与批次①④ 对应）：
1. **保存闸门**：`date_format` 必须在 `_DECLARED_SINGLE_FORMATS` 白名单内；且用样本行**试解析一次**，不通过直接拒绝保存
2. **漂移检测加值形态维度**：抽 N 行样本验证声明格式能解出日期 ⇒ 解不出 ⇒ 判「格式漂移」并提示更新模板（而不是等入库才炸）

### 6.5 更根本的问题：日期解析器 **7 套并存**

上面那个事故只是症状。日期解析在仓库里有 **7 套独立实现**：

| # | 实现 | 位置 | 性质 | 风险 |
|---|---|---|---|---|
| 1 | `parse_date_by_declared_format` | `modules/services/smart_date_parser.py:250` | **严格声明式**（模板治理路径） | 无回退 ⇒ 声明错就整文件失败（**P1**） |
| 2 | `parse_date` | `modules/services/smart_date_parser.py:353` | 宽松启发式，**强制 day-first** | `:133-137` 只试 `_DAY_FIRST_DATE_FORMATS` ⇒ **美式格式静默错解**（**P5**） |
| 3 | `standardize_date_value` | `backend/services/data_standardizer.py:57` | 包装 2 + `detect_dayfirst` | 采样仅 3 个值 ⇒ 不确定时**猜 day-first 而非报警**（**P6**） |
| 4 | `data_validator_v2._parse_date` | `backend/services/data_validator_v2.py:40` | 又一套 | 口径漂移 |
| 5 | `data_validator._parse_date` | `backend/services/data_validator.py:83` | 又一套 | 口径漂移 |
| 6 | `source_freshness_service._parse_date` | `backend/services/data_pipeline/source_freshness_service.py:343` | 又一套 | 口径漂移 |
| 7 | `detect_date_range_format` | `backend/services/field_mapping/type_detector.py` | 又一套 | 口径漂移 |

⇒ 「同一事实多份副本」在日期解析上的重演。**入库路径只允许 1、2/3 两套，其余降级为预览/校验专用**。

**两个必须点名的违规点**（违反「定不了就报警，绝不静默猜一个」）：

| 违规 | 位置 | 行为 |
|---|---|---|
| **不确定时猜 day-first** | `smart_date_parser.py:97-101` + `data_standardizer.py:276-287` | `detect_dayfirst` 在 a、b 都 ≤12 时返回 `None`；`None` 传进 `parse_date` 后 `_parse_explicit_year_position_date` 仍只试 day-first ⇒ **静默按 dd/mm/yyyy 解** |
| **时间范围拆分硬编码 day-first** | `data_standardizer.py:471-472`、`:545-546` | `standardize_date_value(start_str, prefer_dayfirst=True, ...)`，注释写「因为原始数据可能是 dd/mm/yyyy」⇒ 对美式报表**必错** |

**一条好消息（数据安全底线在）**：`raw_data_importer._validate_business_dates_against_file_range:105-131`
与 `data_ingestion_service.validate_metric_date_contract` 会在入库前校验 `metric_date` 落在文件期间内
⇒ **即使宽松解析猜错月日顺序，也会被拒绝入库**，不会产生静默错解的数据。
⇒ 但错误信息是 `metric_date ... is earlier than file_date_from`，**看不出根因是格式反了** ⇒ 可诊断性差（**P9**）。

### 6.6 问题清单（按严重度）

| # | 问题 | 严重度 | 位置 |
|---|---|---|---|
| P1 | 模板声明与真实文件不符 ⇒ **整文件失败**，且每次采集重试失败 | 高 | `raw_data_importer.py:625-628` |
| P2 | 保存闸门**不校验 `date_format` 是否在解析器白名单内** | 高 | `field_mapping_templates.py:1079-1081` |
| P3 | 保存闸门**不用样本行试解析** | 高 | 同上 |
| P4 | 漂移检测**只看列名不看值形态** ⇒ 格式变了查不出来 | 高 | `template_matcher.detect_header_changes` |
| P5 | 宽松解析器**强制 day-first** ⇒ 美式格式静默错解 | 中 | `smart_date_parser.py:133-137` |
| P6 | `detect_dayfirst` 不确定时**猜 day-first 而非报警** | 中 | `smart_date_parser.py:97-101` |
| P7 | 时间范围拆分**硬编码 `prefer_dayfirst=True`** | 中 | `data_standardizer.py:471,545` |
| P8 | **7 套日期解析实现并存** | 中 | 见 §6.5 |
| P9 | 错误信息**不可诊断**（看不出是格式反了） | 低 | `raw_data_importer.py:110` |
| P10 | 状态体系里**没有「格式漂移」这一态** | 中 | `data_sync_status_semantics.py` |

---

## 7. 明确不做

- ❌ 不改 `b_class` 存储层既有表结构（除批次 ③ 的新增列收窄与必要的迁移）
- ❌ 不重建模板模型（families / versions / variants 三表结构保留）
- ❌ 不动下游 `mart` / `semantic` view 的业务逻辑（只随列结构变化同步迁移）
- ❌ 不物理删列、不物理删别名行（一律 `enabled=false` + 可逆）
- ❌ 不引入"系统自动猜一个语义键然后静默使用"——定不了就报警

---

## 8. 验收口径

| 项 | 验收标准 |
|---|---|
| 翻译命中率 | shopee/products/monthly 由 0 → ≥ 60%；miaoshou/inventory/snapshot 由 0 → ≥ 60%；全部域 ≥ 60% |
| 全局沉淀 | 用户在模板里手动对齐一个列名 ⇒ **其它模板**（不同平台/粒度/变体）遇到同一列名**自动命中**，无需再审 |
| 冲突 | 同一列名被对齐到两个不同标准字段 ⇒ 落 `conflict` + 报警，**不静默覆盖** |
| 指纹一致 | `销售额` / `销售金额` / `销售金额(SG)` 三个文件、同一业务含义 ⇒ `data_hash` 相同 ⇒ UPSERT 命中，**不新增行** |
| 值类型 | 数字 `100` 与字符串 `"100"` ⇒ `data_hash` 相同 |
| 落库列 | 非核心字段**不建物理列**（历史列保留读兼容） |
| 阻断 | 核心字段（`required=true`）缺失 ⇒ 阻断并给出「缺哪个、影响什么」；仅新增列 ⇒ **不阻断**，照常入库 |
| 回归 | 全量 `pytest backend/tests` 相对 `main` **零新增失败**（junit XML 前后 diff，before/after 独占串行） |
| 迁移 | 只走 `scripts/run_current_schema_migrations.py`（fail-closed），禁止手工 `alembic stamp` |

---

## 9. 证据索引

| 论断 | 位置 |
|---|---|
| 指标类被硬禁参与 hash | `backend/services/semantic_hash_policy_service.py:103-111` |
| `hash_participates` 只被保存/汇总/计数，不进 hash | `backend/domains/data_platform/routers/field_mapping_templates.py:829, 949`；`frontend/src/domains/data_platform/utils/headerBindings.js:544,615,659`；`frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue:817` |
| hash 用语义键作键、语义取值 | `backend/services/deduplication_service.py:166, 171-183`；`backend/services/semantic_field_registry.py:569` |
| scope 身份自动附加（只取一个身份键） | `backend/services/deduplication_service.py:243-286` |
| 全部文件列建物理列并赋值 | `backend/services/dynamic_column_manager.py:156`；`backend/services/raw_data_importer.py:800, 1436-1469` |
| 别名表零写入路径 | `backend/services/template_alias_registry.py:39`；`backend/services/semantic_field_registry.py`（`SEMANTIC_FIELD_ALIASES`）；`backend/services/semantic_field_contract_service.py:126` |
| 契约 DB 优先、常量兜底 | `backend/services/semantic_field_contract_service.py:282-291` |
| 新增列不阻断 | `backend/services/semantic_field_contract_service.py:199, 217-218`；`backend/services/data_sync_template_status_service.py:378-386`；`backend/services/data_sync_service.py:1317` |
| 前端标准字段副本无 `required` | `frontend/src/domains/data_platform/utils/headerBindings.js`（`SEMANTIC_FIELD_META`） |
