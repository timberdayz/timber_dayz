# D7 方案：变体接管匹配（**已实施**）

> 日期：2026-10-29　状态：**已实施并验证**（2026-10-29 用户确认「按照你的建议执行」）
> 前置：第 1 批（D1 模板契约 / D5 缓存键 / D2 状态枚举+DB CHECK）、第 2 批（D3/D4/D6）、第 4 批（D8）已完成
> 关联：`docs/reports/2026-10-28-tiktok-products-template-rebuild-checklist.md`、`task_plan.md`
>
> **实施结果速览**：25 个 `template_update_required` 文件中 **21 个被跨 family 变体接管**（匹配率 100%），
> 契约已回填、状态已复位为 `pending`、判定复检为 `ready`；
> 另 4 个（175 列版）因缺失 2 列不满足门槛，**属另一个变体**，需单独登记（见 §7）。

---

## 一、现象（本地库 + 真实文件实测，2026-10-28/29）

`public.catalog_files` 里 `tiktok/products` 共 55 个文件，按「文件名粒度 × 状态」分布：

| 粒度 | 状态 | 文件数 |
|---|---|---|
| daily | ingested（已入库） | 6 |
| monthly | failed | 24 |
| monthly | template_update_required | 25 |

**三组文件的表头结构完全一样**（都是 176 列模板口径，实际读到 172/176 列，
前 6 列均为「全部」—— 多 SKU 重复列，与模板里 `去重点击次数.4` 这类后缀对应）。

逐文件与 `tiktok/products` 全族 33 个模板做表头比对（按每份模板自己的 `header_row` 读表头）：

```
25 个 template_update_required 文件
  → 最佳匹配全部是 id=362（granularity=daily，status=published，176 列，header_row=3）
  → 匹配率 99.4%（3 个文件，175 列）/ 100%（22 个文件，176 列）
```

而这些文件按自身粒度（monthly）匹配到的 published 模板是 **id=350（38 列）**：

```
匹配率 0.0%   —— 文件 176 列与模板 38 列一个都对不上
auto_ingest.last_reason = "新增176个字段, 删除38个字段 (匹配率: 0.0%)"
```

### 模板库现状（`core.field_mapping_templates`，platform=tiktok / data_domain=products）

| 粒度 | published | 列数 | 归档模板列数分布 |
|---|---|---|---|
| daily | id=362 (v6) | **176** | 176, 38, 33 |
| monthly | id=350 (v16) | **38** | 38, 33 |
| weekly | id=256 (v1) | **38** | 38, 33 |

---

## 二、根因

**TikTok 商品导出实际只有一种表结构（176 列）**，daily / monthly / weekly 只是采集时间范围不同。
但模板是**按粒度分别登记**的：

- daily 登记的是新版 176 列模板（id=362）→ **daily 的 6 个文件能入库**
- monthly 登记的还是旧版 38 列模板（id=350）→ **monthly 的 49 个文件全军覆没**

于是形成一条**自我强化的死循环**：

```
monthly 模板停留在旧格式
  → monthly 文件撞旧模板 = 0% 匹配
  → 判定「结构漂移」→ template_update_required
  → 系统建议「更新模板」
  → 但只要更新 monthly 模板，新模板也只能是 176 列（=daily 那份）
  → 另一边 daily 模板已经是 176 列，于是两份同内容模板并存
  → monthly 的旧模板继续躺在那里，下一批 monthly 文件继续撞它
```

**这不是「多地区多套模板」那种真变体，而是同一个导出格式被登记成了两个粒度，其中一个粒度停在了旧版本。**

第 1 批做的 `template_contract`（D1）已经铺好了「一个文件可以被某一版模板解释」的机制；
但它只在**新采集文件**上生效，存量 495 个文件仍无契约 —— 这 25 个文件正好落在存量里。

---

## 三、三条候选方案

### 方案 A：只修数据（不发版，最快）

给 `tiktok/products/monthly` 补一份 176 列的 published 模板（复制 id=362 的列清单，
版本接到 v17），把 id=350 归档。

- ✅ 立刻解开 25 个文件的 0% 匹配
- ❌ 只是把「粒度错配」这个坑再填一次；下一个平台（shopee / miaoshou）同样会踩
- ❌ 需要手工操作，用户侧负担

### 方案 B：跨粒度变体接管（系统级，D7 本体）

**在模板匹配里增加一个兜底层**：目标粒度下没有能匹配上的模板时，
允许**同族（platform + data_domain）其他粒度**的模板作为变体候选参与匹配。

命中后不改动模板库状态，而是：

1. 把命中的模板（id/version/header_row）写进该文件的
   `file_metadata['template_contract']` —— 复用第 1 批的 D1 契约机制；
2. 该文件此后以这份模板为基准解释，**不再判结构漂移**；
3. published 唯一索引不受影响（被接管的模板仍是 daily 粒度那一份，不会产生两个 published）。

匹配门槛（建议）：表头匹配率 ≥ 95% 且缺失列 ≤ 1 —— 本例区分度极大
（正确模板 99.4~100%，错误模板 0.0%），门槛可以卡得很死。

- ✅ 治本：粒度登记错配不再导致文件永久卡死
- ✅ 复用已有 family/variant/resolver 机制，不新增数据模型
- ✅ 复用 D1 契约机制，不新增迁移
- ⚠️ 需要定义「跨 family」的边界（是否允许跨 platform？建议**只允许同 platform + 同 data_domain**）
- ⚠️ 需要决定**存量 25 个文件要不要回填契约**（回填 = 一次性修复；不回填 = 只对以后新采集的文件生效）

### 方案 C：模板「变体」显式建模 —— ⚠️ 已不成立（2026-10-29 修正）

~~在 `core.field_mapping_templates` 上加「变体」维度~~

**变体机制早已存在**，无需再建模：`core.field_mapping_template_families`（27 行）/
`_versions`（27 行）/ `_variants`（27 行）三层表齐全，
`TemplateResolver._select_variant()`（`backend/services/template_family_service.py:852`）
已按 `header_row` / `sheet_name_pattern` / `required_headers` / 表头相似度打分选变体，
且已被主链路（`data_sync.py` / `data_sync_service.py` / `data_sync_template_status_service.py` /
`field_mapping_ingest.py` / `field_mapping_templates.py`）接入。
legacy 表通过 `project_legacy_templates()` 投影进 family（`source_mode=legacy_projection`）。

⇒ 方案 C 已被既有的 family 层取代，**只需在 resolver 上加一层跨 family 兜底**（即方案 B）。

---

## 四、推荐

**先做方案 B（跨 family 变体接管），暂不做 A。**

理由：

1. A 是 B 的一个特例 —— 有了跨 family 接管，那 25 个存量文件回填契约即可解开，
   不需要手工造一份 monthly 模板；
2. **变体机制已存在**（见方案 C 的修正说明），B 只是给 `TemplateResolver` 加一层兜底，
   不新增数据模型、不新增迁移，风险可控；
3. 病灶已精确定位到 family 层（见 §6.2）：family 27（monthly）还挂在旧的 38 列变体上，
   而 family 23（daily）已经把 176 列格式建模完了。

---

## 五、需要用户拍板的 4 个点

| # | 问题 | 我的建议 |
|---|---|---|
| 1 | 跨粒度接管的边界 | **只允许同 platform + 同 data_domain**；不允许跨 platform |
| 2 | 匹配门槛 | 匹配率 ≥ 95% 且缺失列 ≤ 1；命中后在治理视图里标注「跨粒度接管」而非静默通过 |
| 3 | 存量 25 个文件 | **回填契约**（一次性解开）；否则它们会一直卡到被人工重导 |
| 4 | 存量 495 个文件的契约回填 | 是否一并做？（D1 只对新采集文件生效；存量回填是独立工作项，与本次 D7 可分开） |

另有两个**本次已记录但不在 D7 范围**的遗留（来自 D8 排查）：

- `modules.platforms.shopee.components.config_registry` 模块已被删除，
  但 `app.py` 仍有 4 处从它 import —— 这些代码路径**一直是死的**，
  修复需要重建组件注册中心，属独立工作项；
- 服务域拼写仍是单数 `service`（白名单与库内数据都是 `services`），
  改它会改变实际入库值，需单独确认。

---

## 六、方案 B 的实施要点（供决策后参考，尚未动代码）

> ⚠️ **2026-10-29 修正**：本节初稿写的是「改 `find_best_template` 增加跨粒度兜底层」。
> 进一步核查后发现**变体机制早已完整存在**，真正的落点不是 legacy 表，而是 **family 层**。
> 下面按修正后的结论写。

### 6.1 已存在的能力（不必新造）

`core` 库里三层结构齐全，且**已接入主链路**：

| 表 | 行数 | 作用 |
|---|---|---|
| `core.field_mapping_template_families` | 27 | 模板族（platform + data_domain + granularity + sub_domain + account），带 `active_version_id`、`governance_status` |
| `core.field_mapping_template_versions` | 27 | 版本，带 `status=active`、`legacy_template_ids` |
| `core.field_mapping_template_variants` | 27 | 变体，带 `variant_key`、`match_priority`、`header_row`、`sheet_name_pattern`、`required_headers`、`source_legacy_template_id` |

- 选择器：`backend/services/template_family_service.py` → `TemplateResolver._select_variant()`（:852），
  按 `header_row` / `sheet_name_pattern` / `required_headers` / 表头相似度打分选变体
- 主链路已接入：`data_sync.py`、`data_sync_service.py`、`data_sync_template_status_service.py`、
  `field_mapping_ingest.py`、`field_mapping_templates.py`
- legacy 表通过 `project_legacy_templates()` **投影**进 family（`source_mode=legacy_projection`）
- 治理状态已能区分：`governance_status = "ready" if selected_variant else "missing_variant"`

### 6.2 真正的病灶（精确到 family）

`tiktok/products` 有 3 个 family，各自的 active version 指向不同的 legacy 模板：

| family | 粒度 | active version | variant key | header_row | 指向 legacy 模板 | 列数 | required_headers |
|---|---|---|---|---|---|---|---|
| 5 | weekly | 5 | `weekly_dash` | 2 | id=256 | 38 | 旧的 38 列 |
| 23 | daily | 23 | `daily_header_3_f40e8338` | 3 | **id=362** | **176** | **新的 176 列** |
| 27 | monthly | 27 | `monthly_dash` | 2 | **id=350** | **38** | **旧的 38 列** |

⇒ **family 23 已经把 176 列格式建模完了**（变体 key、header_row=3、required_headers 都是新的），
但 **family 27 还挂在旧的 38 列变体上**。25 个 monthly 文件是 176 列 / header_row=3，
在 family 27 里自然一个变体都匹配不上 → `missing_variant` / 漂移。

### 6.3 修正后的实施要点

1. **`backend/services/template_family_service.py` → `TemplateResolver`**
   在「本 family 内无匹配 variant」时，增加**跨 family 兜底**：允许同 `platform + data_domain`
   的其他 family 的变体参与匹配（本例：family 27 找不到时，去 family 23 找到
   `daily_header_3_f40e8338`，匹配率 100%）。
   —— 这是**在已有机制上加一层**，不是新造变体机制。
2. **命中后写契约**：`backend/services/template_contract_service.py`
   把命中的 legacy 模板（id=362 / version / header_row=3）写进该文件的
   `file_metadata['template_contract']`，复用第 1 批 D1 的契约机制。
   —— 不新增数据模型、不新增迁移。
3. **判定基准**：`backend/services/data_sync_template_status_service.py`
   已有契约优先逻辑（第 1 批 D1 落地），存量文件回填契约后自动脱离漂移状态。
4. **处置模型**：`backend/services/data_sync_file_state_service.py`
   区分「跨 family 变体接管命中」与「真漂移」，避免混为一谈（D3/D4 已建立这套语义区分）。
5. **治理视图**：把「跨 family 接管」显式暴露（谁接管的、接管到哪个 family/variant），
   不要让它伪装成普通 `ready`。

### 6.4 备选（若不做 6.3 的跨 family 兜底）

把 **family 27 的 active version 指向 176 列的 legacy 模板**（即把 id=350 换成 id=362 的列，
`header_row` 改 3），本质是「方案 A 的 family 版」。
优点：改动小、直接见效；缺点：仍是手工把粒度错配改对，下一个平台同样会踩，
且 175 列变体（4 个文件）还得再登记一次。

---

## 七、实施结果（2026-10-29）

### 7.1 落点与新增文件

| 文件 | 作用 |
|---|---|
| `backend/services/template_variant_takeover.py`（新增） | **判定 SSOT**：门槛常量、`evaluate_variant_takeover()`、`build_takeover_report()`、`select_best_takeover()`、`template_explains_columns()` |
| `backend/services/template_variant_takeover_service.py`（新增） | **表头行感知**的候选发现 + 共享基准判定 `resolve_baseline_for_file()` |
| `backend/services/template_contract_backfill_service.py`（新增） | 存量契约回填（判定口径与在线链路完全同源） |
| `backend/services/template_family_service.py` | `list_cross_family_variants()` + resolver 层跨 family 兜底 + 表头行一致性过滤 |
| `backend/services/data_sync_template_status_service.py` | 显式接受 `baseline_template_override` / `baseline_kind_override` / `takeover` / `header_row` |
| `backend/services/data_sync_service.py` | 判定链路 + **入库链路**都用同一把尺子 |
| `backend/services/data_sync_file_state_service.py` | 处置模型区分「跨 family 接管」与「真漂移」 |
| `backend/domains/data_platform/routers/data_sync.py` | 治理视图暴露接管来源 |

### 7.2 实施中发现并修正的关键点：**表头行感知**

原方案（§6.3）假设「先按当前模板的 `header_row` 读表头，再去找能解释它的变体」。
**实测证明这是错的**：

- monthly 模板声明 `header_row=2`，但源文件真实表头在 **0-based 行 3**
  （行 2 是「全部/全部/…」分组行，读出来是 172 个 `全部.N` 垃圾列）
- 先按行 2 读 → 拿去和任何变体比对，匹配率必然是 **0%** → 接管**永远不可能命中**

⇒ 接管必须是「**按候选变体自己的 `header_row` 读表头，再评估**」。

落地方式：`CrossFamilyTakeoverService.find_candidate()` 对每个候选变体按其
**自带的** `header_row` 读表头（同一行只读一次，带缓存），再逐个评估。
resolver 层作为兜底时，用 `_variant_header_row_matches()` 过滤掉行号不一致的变体。

### 7.3 实施中第二个关键修正：**自家变体必须优先**

接管的前提是「**自己家解释不了**，才让别人接管」。候选池里必须包含**自身 family**
的变体，并且排序时自家优先。

实测反例（本地库）：

| family | 粒度 | variant key | header_row | legacy 模板 | required_headers |
|---|---|---|---|---|---|
| 7 | daily | `daily_dash` | 2 | id=273 | 11 列客服指标 |
| 8 | monthly | `monthly_dash` | 2 | id=274 | **同样 11 列客服指标** |

⇒ 两个变体的 `required_headers` 与 `header_row` **完全相同**，匹配率都是 100%。
若候选池只放「其他 family」，`tiktok_services_agent_monthly` 的文件会被
**daily 的变体**抢走解释权 —— 基准模板从 id=274 变成 id=273。

修正：`select_best_takeover()` 的排序键改为
`(自家优先, -匹配率, match_priority, variant_id)`。

顺带修掉一个**账号维度**的口径错误：

- 模板族几乎都是 `account=None`（与店铺无关的通用模板），而 `catalog_files.account`
  是具体店铺（实测本地库 34 个 family 全部 `account=None`）
- 若按字面相等判断「自家」，**自家 family 永远匹配不上** → 接管继续抢自家文件
- 修正：`_account_dimension_matches()` —— `family.account is None` 表示「适用任意账号」

### 7.4 契约与接管的优先级

判定链路（`resolve_baseline_for_file()`）的基准优先级：

```
契约(且仍能解释文件表头) > 自家变体 > 跨 family 接管 > 当前已发布模板
```

- 契约**必须对照文件真实表头校验**：采集登记时是按粒度选模板的，而导出格式
  不一定跟着粒度走 ⇒ 契约可能指向一个已经过时的模板（tiktok monthly 就是这种）
- 契约解释不了文件时 → 由跨 family 接管接手，并把 `contract_stale=True` 暴露出来
- 契约与接管指向**同一个模板**时 → 契约优先（不重复标记为接管）
- **自家变体命中不算接管**：只是把基准落到自家变体对应的模板上

### 7.5 实测结果（本地库，2026-10-29）

25 个 `template_update_required` 文件逐个判定：

| 结果 | 数量 | 说明 |
|---|---|---|
| 接管命中 → `ready` | **21** | 变体 `daily_header_3_f40e8338`（family 23 / daily），匹配率 **100%**，缺失 0 列 |
| 未命中 → 仍 `update_required` | **4** | id=2765 / 2995 / 2997 / 3000，175 列版 |

**4 个未命中的原因**：它们相对 176 列变体缺失 **2 列**
（`发品状态` + `promoting_creators_metric_name_short_ui`），
匹配率 98.9% 但**缺失列 > 上限 1** ⇒ 按门槛拒绝。
这是**另一个变体**，不是「176 列版的缺列版」⇒ 需要单独登记（属 products 模板重建范畴）。

**回填结果**（`template_contract_backfill_service`）：

- 21 个文件写入 `file_metadata['template_contract']`
  （`source = cross_family_variant_takeover`，含 `takeover` 接管来源留痕）
- 重检通过后状态由 `template_update_required` 复位为 `pending`
  （与 `scheduled_tasks._recover_template_update_required_files` 的既有语义一致）
- 复检结果：`template_status=ready` / `baseline=contract` / `should_auto_sync=True`

### 7.6 已知边界

1. **契约校验依赖读表头** ⇒ 判定链路每读一个文件会多读 1~2 行表头（有行级缓存）。
2. **变体表不可用时必须容错**：SQLite 测试库 / 未迁移的库没有
   `core.field_mapping_template_families` ⇒ 接管查询失败必须回退到「当前已发布模板」，
   **不能拖垮判定链路**（这是实施中实测到并修正的一处回归）。
3. **入库链路也要走同一把尺子**：判定说「通过」而入库按另一行的表头读，
   写进去的是垃圾数据 —— 比判定不过更危险。
4. **175 列变体**（4 个文件）需要单独登记变体后才能接管，属 products 模板重建范畴。

