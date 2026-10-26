# 库存域改造 · 落地工作清单

> 状态：汇总稿（待评审）
> 日期：2026-10-24
> 汇总自：库存增量采集设计（`2026-10-24-miaoshou-inventory-incremental-collection-design.md`）
> + DOS 指标口径与命名决策（`2026-10-24-dos-metric-naming-and-caliber-design.md`）

---

## 1. 一句话概括

把妙手库存域从「每天全量搬 1113 行」改成「只搬有变化的行」，把下游取数从「批次级排序键」改成「行级时间戳」，
再把**真正用来做生意的那个指标**（DOS）从错口径换成对口径，并让滞销模块和商品中心最低售价用同一份 DOS。

四件事，环环相扣：**先让数据能对得上，再让指标说得清，最后才谈改页面。**

---

## 2. 必须先解决的三个「现在就是错的」问题

这三条不是「优化」，是**当前系统就在给出错误结论**，优先级高于一切增量改造：

| # | 问题 | 现状（实测） | 影响面 |
|---|---|---|---|
| **P1** | 滞销模块顶部三张卡是假的 | `backlog_30d` = `backlog_60d` = `backlog_90d` = 217787.41，**三个数字完全相同** | 业务看板上「30/60/90 天积压」毫无区分度 |
| **P2** | 滞销判定被 9999 哨兵污染 | `mart.inventory_backlog_base` 499 行 `estimated_turnover_days = 9999`（订单口径无 miaoshou 数据）→ risk_level 全 high | 整个滞销名单的排序和风险等级失真 |
| **P3** | 最新批次进不了「最新」视图 | `metric_date` 是批次级错戳，1113 行最新批次只贡献 **4 行**进 `mart.inventory_snapshot_latest` | 下游所有取「最新」的逻辑都读到了旧批次 |

---

## 3. 工作包

### W1 采集层：加「更新时间 + 区间」筛选（B1）

**做什么**：新增组件 `miaoshou/inventory_date_filter`，复用订单域同一套 `date_picker` 与采集配置字段，多一步「先切维度」。

**关键点（都是实测踩出来的，不能省）**：

1. 妙手两处**静默失败**——维度没切、点「确定」没点，页面照常显示不报错。所以每步都要断言：
   - 切维度后 `modelvaluegroup` 以 `gmtModified` 开头
   - 填完区间点「确定」后 `modelvaluegroup` 含目标起止时间
   - 点搜索后「SKU 总数」文本变化且 > 0
2. 「确定」= `button.jx-picker-panel__link-btn.is-plain`，「清空」= `.is-text` → **必须用完整 class 区分，否则误点清空**
3. 维度下拉只有 2 项：创建时间 `gmtCreate` / 更新时间 `gmtModified`
4. 维度选错是静默失败：同区间按更新时间 147 SKU，按创建时间仅 3 SKU
5. 不用「近7天/近30天」快捷项作采集入口——相对今天 ≠ 从水位线接着采，会漏

**产出**：新组件 + 编排改造 + 行为测试（覆盖维度未切/未点确定/搜索无刷新三条失败路径）

---

### W2 落盘层：行级时间戳 + 状态层 upsert（B2）

**做什么**：

1. `semantic.fact_inventory_snapshot` 视图新增 `observed_at`（行最后修改时间）/ `created_at`（行创建时间）
2. `mart.inventory_snapshot_latest` / `inventory_current` 排序键从 `metric_date DESC` 改为 `observed_at DESC`
3. 状态层：每 SKU×仓 永续一行，增量下也保持完整（upsert）

**效果（已用现有两批数据实测）**：

| 排序键 | 最新批次贡献 | 旧批次贡献 |
|---|---|---|
| `metric_date`（现状） | **4 行** | 1226 行 |
| `observed_at`（目标） | **469 行** | 761 行 |

**不做**：不新增物理列（平铺列已 100% 覆盖）；不订正历史 `metric_date`（新模型下它只表示「这批的配置区间」，订正会丢可追溯性）。

> ⚠️ **W1 与 W2 必须同批发布**。单独上 W1 会让「增量批次进不了 latest」更严重（旧批次 09-14 依然压过新批次）。

---

### W3 水位线与断档补采（B3）

**做什么**：水位线表 + 自动推进 + 断档补采规则。

**⚠️ 2026-10-24 晚间修正：不再有全量档**（Walter 拍板：后面只有「配置采集 + 增量更新」）。
原「五条全量回退规则」改为：

| 原规则 | 改为 |
|---|---|
| 首次强制全量 | 不需要——现有 1113 行就是基线 |
| 断档 > 3~5~7 天 → 回退全量 | **长窗口补采**：把增量区间向前拉长覆盖断档期 |
| 上一批失败 → 下一批回退全量 | 下一批把窗口拉长到覆盖失败期 + 记日志 |
| 周期性全量兜底 | **取消** → 见下方「删除/下架怎么办」 |
| 全量同时刷新 DOS 口径 | **作废**——DOS 已降级为参考，不需要全量刷新 |

**删除/下架怎么办**（取消全量后唯一剩下的真问题）：增量看不到被删/下架的 SKU，
状态层会残留幽灵行 → 库存价值虚高。三条对策：
① **零库存宽限期**（连续 N 天未被采集到且库存为 0 → 标「疑似下架」，保留行不硬删）——建议立刻做；
② **商品档案的上下架状态**交叉——**待取证**（妙手有没有这个可取的口子未知）；
③ **季度级核对批次**——与「不再全量」的字面要求冲突，但这是唯一能发现「被删除」的手段，
而「总库存价值」是业务概览顶部第一张卡。

**变更判定必须双闸**（2026-10-24 晚间新增）：

| 闸 | 判定 | 作用 |
|---|---|---|
| 闸 1（妙手侧） | 用「更新时间」维度 + 区间**缩小候选集** | 只决定这次导出哪些行 |
| 闸 2（我方侧） | 与上一批同 SKU×仓比对**可用库存 / 库存总量 / 预占库存** | 决定是否推进 `stock_changed_at`、是否写入观测层 |

理由（实测）：file 2764 有 **535 行（43.7%）** 的更新时间被一次 bulk UPDATE 批量戳成
`2026-05-08 10:36:36~39`——只信妙手的「更新时间」会把假变更当业务变更，
还会污染停滞时长。闸 2 **不比较销量**（销量在增量下本就不更新）。
详见 DOS 设计稿 §4.2.2 / §4.8 与增量设计稿 §6.3。

---

### W4 滞销判据：库存停滞时长（取代 DOS 做判据）

**做什么**：把滞销模块的地基从「DOS（分母会漂移）」换成「库存停滞时长（事件时刻，不漂移）」。

1. **落盘层维护 `stock_changed_at`**——库存数量最后一次**真实变动**的时间，由闸 2 的行内容 diff 产出
   （不信妙手的「更新时间」）；现有两批对比中 388 行可算出真实变动时间，其余行第二轮起完全自维护
2. **停滞天数 = 今天 − `stock_changed_at`**，分档：<30 活跃 / 30–90 观察 / 90–180 中度 / ≥180 重度
3. **DOS 保留为参考列**（简化计算，标注「参考」），**不做入选、不做排序主键、不做汇总卡口径**
4. **实测支撑**（file 3004 / 1113 行）：
   - 单调性成立：DOS 判「快断货/30-90」的行里**没有一行**是停滞 ≥180 天
   - DOS 会误判新货：「DOS 说零销量但停滞只有几天」有 **169 行 / ¥12,098**（刚补货刚上架）
   - 停滞时长判滞销覆盖 10.9% 货值，DOS 判滞销覆盖 74.3% 货值（后者门槛太松）
5. **零销量不再作为独立档**——停滞 ≥180 天的 488 行本来就全部落在零销量，已被覆盖

### W5 DOS 口径与命名（降级为参考）

**做什么**：DOS 从「错口径 + 名字含糊」变成「口径清晰 + 唯一实现」，但**只作参考值**。

1. **语义层暴露销量列**——`semantic.fact_inventory_snapshot` 目前**没有任何 sales 列**，必须先投影 `近7/30/60/90天销量数据` 4 个窗口
2. **DOS 计算唯一实现**（纯函数 + 唯一取数路径），但**只有滞销模块的参考列**调用它
3. **禁止哨兵**：不可算时返回 NULL + 独立状态标签（`zero_sales` / `no_stock` / `computable`），不允许 9999
4. **命名定稿**（详见 DOS 设计稿）：
   - `checklist_dos_sales30` / `checklist_dos_sales90` — 清单口径，状态 `observe`
   - `order_dos_sales30` / `order_dos_sales90` — 订单口径，状态 `blocked`（无 miaoshou 订单数据）
   - 禁用：`quick_dos` / `platform_dos_*`（与 `platform_code` 语义冲突）/ `dos_30d`（会被读成档位）
5. **指标词典登记**——`references/metrics-dictionary.md` + `references/metric-status.md` + `references/platform-mapping.md`；⚠️ 该 skill 有**两份副本**：正本 `team-skills-bundle/`、副本 `docs/team-skills/`。
   2026-10-24 实测两份此前**并不一致**（`metrics-dictionary.md` 与 `platform-mapping.md` 分叉，副本还缺 `agents/openai.yaml`），已按正本对齐，现 **7/7 文件 SHA256 一致**。改这个 skill 一律**改正本再同步副本**
6. **新鲜度契约**（2026-10-24 晚间新增）——DOS **只认全量批次**；输出增加 `dos_as_of`（数据时点）
   与 `dos_stale`（超期标记）；取数服务必须按批次类型过滤；前端必须显示数据截止时间；
   指标词典条目必须写明「只认全量批次」与「能证明什么 / 不能证明什么」

**为什么 90 天窗口当主口径**：有 74 行「近90天卖过、近30天没动」，30 天窗口会直接误判成滞销；90 天能识别。且 DOS-30 判「<30天」的 37 行，在 DOS-90 下无一落到 ≥180 天，两口径不矛盾。

---

### W6 滞销模块改造（B4）

**去掉**（都是错的）：风险等级 high/medium/low、清理优先级（含 9999 的假分数）、估算积压天数、连续积压快照数、顶部「60天+」假卡

**判据换成库存停滞时长**（W4）：入选 = 有库存 且 停滞天数 ≥ 90；分中度（90–180）/ 重度（≥180）

**新增列**：仓库、**停滞天数**、最后库存变动时间、滞销状态标签；
**DOS-30 / DOS-90 保留但标注「参考」**（不参与入选、不参与排序、不进汇总卡口径）

**顶部四张卡**：总库存价值 / 滞销货值（停滞 ≥180）/ 中度积压货值（停滞 90–180）/ 滞销占比

**排序**：停滞天数降序 + 同档货值降序

**表格粒度已是 SKU×仓**：1230 行 / 1122 去重 SKU；同一 SKU 跨仓显示成多行像重复——加仓库列后这件事自然说清。

---

### W7 商品中心最低售价选档 → 用库存停滞时长（不用 DOS）

**⚠️ 2026-10-24 晚间定案**：原方案「改用 DOS 选档」**方向性错误**，已撤回。
商品中心的 `min_age_days` 存的**本来就是库龄门槛**——它要的就是库龄；
名实不符要修的是 `tier_label` 文案，不是把数据源换掉。

**但库龄这个数据现在是坏的，商品中心的四档折扣从未生效过**（逐 SKU 复算 1122 个 active SKU）：

| 命中档位 | SKU 数 | 库存货值 |
|---|---|---|
| 日常（0.10） | **1122** | ¥214,489.41 |
| 滞销30天 / 滞销60天 / 滞销60天以上 | **0** | ¥0 |

两条路都掉进日常档：① 495 个 SKU 有 `age_days` 但全在 0~13 天（锚点用 `snapshot_date` 差算）
② 627 个（56%）没有 `age_days` → `select_age_tier` 回落最小门槛行 = 日常档。

**锚点修好后库龄仍不够用**：妙手「创建时间」= 库存记录首次创建时间（≈ 首次铺货），
98.5% 的行 ≥180 天；其中「还在卖的老品」430 行 / ¥187,980，是真滞销（136 行 / ¥32,569）的 5.8 倍。
SKU 级落档：库龄 → 重度档 1060/1076（99%），平均折扣 0.2979（等于全场清仓）；
停滞时长 → 重度档 485/1076（45%），平均折扣 0.2025。两者 585 个 SKU 不一致且**100% 是库龄更深**。

**落地要求**：

1. 选档依据 → **`inventory_stall_days`**，SKU 级取**各仓最长**（**不用 DOS、不用妙手「创建时间」**）
2. 列名 `min_age_days` → **`min_stall_days`**；`tier_label` 改成「日常 / 压30-90天 / 压90-180天 / 压180天以上」
3. 阈值 0 / 30 / 90 / 180；**折扣率与目标毛利不动**
4. 档位来源标注要改：4 档当前 `platform_basis='tiktok'`、`source='industry_benchmark_2026'`
5. **唯一实现纪律**：商品中心与滞销模块共用同一个 `inventory_stall_days` 实现，不允许各写一份
6. **库龄锚点仍要修**（`age_days` 改用 `created_at`）——它保留为「商品生命周期视角」，但不再用于选档
7. **`select_age_tier` 的 None 兜底要改**：缺料不得回落日常档（现在最该降价的反而拿 0.10 最低折扣）

**规模参考**：重度档占 45% 的 SKU，但只占 7.2% 的货值（¥16,442）。

---

### W8 配套（低优先级）

- **下架探测**：零库存宽限期 + 商品档案上下架状态（**待取证**）+ 季度级核对批次
- `api.clearance_ranking_module` 重写（消除 statement timeout）
- 飞书 sku/spu 投影链路（配表 ID + celery 定时扫 pending）

---

## 4. 排期与依赖

| 批次 | 内容 | 依赖 | 风险 | 说明 |
|---|---|---|---|---|
| **B1** | 采集组件 + 编排 + 行为测试 | 需真实页面复验 | 低 | 只加筛选不改落盘 |
| **B2** | 语义层行级时间戳 + 排序键 + 状态层 + `stock_changed_at` | 无 | 低 | 视图改动可回滚 |
| **B3** | 水位线 + 断档补采 + 双闸变更判定 | B1 B2 | 中 | 取消全量档 |
| **B4** | 库龄锚点 + 停滞时长 + 9999 拆分 + 滞销模块 | B2 | 中 | 最大的一块；DOS 只作参考列 |
| **B5** | 下架探测（零库存宽限期 + 商品档案状态取证） | B3 | 低 | 商品中心自动化**待拍板**，不在本批 |

**两条硬约束**：

1. **B1 与 B2 同批发布**（否则增量批次进不了 latest）
2. **`stock_changed_at` 维护先于滞销模块改造**（否则停滞时长没有分子，判据落不了地）

---

## 5. 全局验收（每批都要过）

- 采集测试面全绿（当前基线 149 项）
- `black --line-length 88` / `ruff` 全过
- 函数 ≤ 50 行、类 ≤ 500 行（`TESTING_AND_QUALITY.md` 硬门禁）
- lint 基线不劣化（当前全仓库 385 条 / 656 处）
- 镜像同步走 `scripts/sync_main_mirrors.ps1` + 独立 worktree；origin/main 与 cnb/main 同 commit

---

## 6. 还需你拍板的 8 件事（1–7 已定，8 待拍板）

| # | 事项 | 结论 | 依据 |
|---|---|---|---|
| 1 | DOS 分档阈值 | ✅ 已定：90 / 180 两档进滞销；<30 天判快断货**不进榜** | A 档仅 30 行 / 4.4% 货值，且是补货信号 |
| 2 | DOS 库存口径 | ✅ 已定：可用库存 | 两种口径差异 ≤3 行 |
| 3 | 商品中心用哪档 | ⏸️ **撤下**——DOS 已降级为参考，见第 8 项 | DOS 不做判定依据 |
| 4 | 快断货是否进滞销模块 | ✅ 已定：不进，顶部单独提示 | 与「滞销」业务含义相反 |
| 5 | 指标词典登记 | ✅ 已做（两份副本已对齐） | 唯一能真正防住后续 agent 混淆的机制 |
| 6 | **DOS 的定位** | ✅ **Walter 拍板：降级为参考值，不做全域使用**；滞销判据改用**库存停滞时长** | 采集策略已定不再全量 → 「DOS 只认全量批次」不成立；实测增量只覆盖 13.6% SKU；停滞时长是事件时刻、不漂移、增量下始终准确（DOS 设计稿 §4.8 / §6.6） |
| 7 | **商品中心最低售价的选档** | ✅ **定案：用「库存停滞时长」选档，不用 DOS、也不直接用妙手「创建时间」**；`min_age_days` → `min_stall_days`，标签改名，阈值 0/30/90/180，折扣率不动 | 商品中心要的是库龄这个**业务概念**，数据上对应「这批货多久没动」；原方案「换 DOS」是方向性错误。实测四档折扣**从未生效过**（1122 个 active SKU 全落日常档 0.10）；库龄锚点修好后 99% SKU 会被打到最深档，在卖的老品货值是真滞销的 5.8 倍（DOS 设计稿 §6.7） |
| 8 | **下架探测怎么做** | ❓ **待拍板**（建议：零库存宽限期立刻做 + 商品档案上下架状态取证 + 保留季度级核对批次） | 取消全量后，增量看不到被删/下架的 SKU → 幽灵行会让「总库存价值」虚高（增量设计稿 §6.3） |

**另外两个前置依赖**（不阻塞 B1~B4，但决定 DOS 能否升级为 `stable`）：

- **采 miaoshou 订单域**（P0-1）→ 订单口径 DOS 才有原料，也才能做清单口径 vs 订单口径的交叉校验
- **库龄锚点修正**（B4 内）→ `mart.inventory_age_current.age_days` 当前 max 仅 13 天、`>30 天` 的 SKU 为 0，导致商品中心 56% SKU 走 `fallback_no_age_data` 兜底

---

## 7. 一次说清「DOS、库存停滞时长、库龄」三者的关系

这是最容易被后续 agent 弄混的一点，单独列：

| | DOS | 库存停滞时长 `inventory_stall_days` | 库龄（在库时长） |
|---|---|---|---|
| 回答什么 | 这批货按当前卖法还能卖多久 | **这批货多久没动过** | 这个 SKU 在这个仓存在了多久 |
| 数据性质 | 流量近似 → 分母会漂移 | **事件时刻** → 不漂移 | 事件时刻（首次创建） |
| 增量模式下 | 只对采到的 13.6% 新鲜 | **始终准确** | 准确（但太粗） |
| 用在哪 | **只作参考列** | **滞销判据 + 商品中心选档** | 商品生命周期视角 |
| 能不能互相替代 | **不能** | **不能** | **不能** |

实测关键对比（file 3004 / 1113 行）：

- DOS 判「快断货/30-90」的行里，**没有一行**是停滞 ≥180 天 → 停滞时长判滞销的集合完全被 DOS 包含
- 「DOS 说零销量、但停滞只有几天」= **169 行 / ¥12,098** → 这些是刚补货的新货，DOS 会误判，停滞时长不会
- 库龄 ≥180 天的 1096 行里，「还在卖的老品」430 行 / ¥187,980 vs 「真滞销」136 行 / ¥32,569
  → **库龄分不开这两类**（在卖的老品货值是真滞销的 5.8 倍）

→ **三个都要留，各司其职**：滞销模块与商品中心用**库存停滞时长**（唯一实现，共用）；
DOS 只作参考；库龄保留为生命周期视角。

⚠️ **最容易被搞混的一点**：业务说的「库龄」=「这批货压了多久」，
数据上对应的是**库存停滞时长**，**不是**妙手的「创建时间」（那是首次铺货时间）。
直接把 `created_at` 当库龄用，会把「两年前上架、一直在卖」的老品
和「两年前铺货、一直压着」的滞销品混为一谈。

---

## 8. 逐文件施工清单（B4 滞销模块 + W7 商品中心）

> **进度**：B2 落盘层 ✅ 已落地并实测（见增量设计稿 §5.6）。
> 下面这份是 B4 + W7 的**逐文件**施工依据，照单执行即可，不需再重新调研。

### 8.1 B4-1 · SQL 层（口径的唯一来源）

| 文件 | 改动 |
|---|---|
| `sql/mart/inventory_backlog_base.sql` | **删**：`estimated_turnover_days`（含 9999 哨兵）、`daily_avg_sales`、`risk_level`、`clearance_priority_score`、`is_stagnant`、`estimated_stagnant_days`、`stagnant_snapshot_count`<br>**删** `sales_30d` CTE（`semantic.fact_orders_atomic` 对 miaoshou 全空）<br>**加**：`stock_changed_at`、`row_seen_at`、`checklist_sales_30d`、`checklist_sales_90d`（原子事实）<br>**不做**：任何除法、任何分档（口径只写在 Python） |
| `sql/api_modules/business_overview_inventory_backlog_module.sql` | 跟随上游增删字段 |
| `sql/api_modules/inventory_backlog_summary_module.sql` | 汇总口径从「周转天数分档」改为「停滞天数分档」；删 `high/medium/low_risk_sku_count` 与 `avg/max_clearance_priority_score` |
| `sql/api_modules/clearance_ranking_module.sql` | 同步（`mart.inventory_backlog_base` → 状态层） |

### 8.2 B4-2 · 服务层（Python）

| 位置 | 改动 |
|---|---|
| `backend/services/inventory/inventory_stall_service.py` | ✅ **已建**（唯一实现：`compute_stall_days` / `classify_stall_tier` / `aggregate_sku_stall_days`） |
| `backend/services/inventory/inventory_dos_service.py` | **新建**：DOS 参考值纯函数 `compute_dos`（不可算返回 `None`，**禁止 9999**） |
| `backend/services/inventory/inventory_stall_query_service.py` | **新建**：照 `inventory_age_query_service.py` 样板 —— `to_regclass` 探测 → 不发出会失败的查询；`db.begin_nested()` SAVEPOINT 容错；**必须留日志** |
| `backend/services/postgresql_dashboard_service.py` | 删 `_classify_inventory_backlog_risk` / `_inventory_backlog_priority_score`；改 `summarize_inventory_backlog_rows`（四张卡口径）、`_load_inventory_backlog_summary`、`_load_ranked_inventory_backlog_module_rows`（排序改「停滞天数降序 + 同档货值降序」） |
| `backend/schemas/inventory.py` | 删 7 个字段；加 `stall_days`、`stall_tier`、`checklist_dos_sales90`（参考，列名带 `checklist_` 前缀）；summary 的 `by_risk_level` → `by_stall_tier` |

### 8.3 B4-3 · 前端（`frontend/src/domains/business/views/BusinessOverview.vue`）

| 位置 | 改动 |
|---|---|
| 顶部 4 张卡（963–1022） | 总库存价值 / 滞销货值（停滞≥180）/ 中度积压货值（停滞 90–180）/ 滞销占比；**删**「60天+」假卡 |
| 表格列（1052–1109） | **删**：`预计周转天数`（`estimated_turnover_days`）、`估算积压天数`、`连续积压快照数`、`风险等级`、`清理优先级`<br>**加**：`仓库`、`停滞天数`、`最后库存变动时间`、`可售天数（参考）`、`滞销状态标签` |
| 表格上方 | 加一条「快断货（停滞<30 天）」可筛选提示；**不加**第 5 张卡 |
| 排序 | 停滞天数降序 + 同档货值降序 |

### 8.4 W7 · 商品中心

| 位置 | 改动 |
|---|---|
| `finance.sku_pricing_policies` | 列名 `min_age_days` → `min_stall_days`；`tier_label` 改名（「日常 / 压30-90天 / 压90-180天 / 压180天以上」）；阈值 0/30/90/180；**折扣率与目标毛利不动**；`platform_basis` / `source` 改成实际来源 |
| `backend/services/product_pricing_service.py` | `select_age_tier` → `select_stall_tier`；**缺料不得回落日常档**（当前 `age_days is None` → 落最小门槛行 = 0.10 折扣，最该降价的反而拿最低折扣） |
| `backend/services/product_pricing_query_service.py` | 取数从 `mart.inventory_age_current` 换成状态层的 SKU 级停滞时长（**各仓取最长**）；`compute_pricing_state` 的 `age_days` → `stall_days` |
| `mart.inventory_age_current.age_days` | 锚点仍要修（改用 `created_at`），但**不再用于选定价档**，只作生命周期视角 |

### 8.5 验收口径（B4 + W7 一起过）

- 滞销榜入选 = 有库存 且 **距上次进货 ≥ 60 天**（门槛与商品中心档位表同源）
- 分档：60–90 轻 / 90–120 中 / ≥120 重（≥120 = 公司要想办法清理掉的库存）
- 顶部卡：总库存价值 / 滞销货值（≥60）/ 重度积压货值（≥120）/ 滞销占比
- DOS 列必须标注「参考」，且**不参与**入选 / 排序 / 汇总卡
- 商品中心：`days_since_restock` 缺失 → 独立标记，**不得回落日常档**
- 两处都用 `inventory_restock_service` 的**同一个实现**（唯一实现纪律）

### 8.6 ⚠️ 纪律：存量库存数据是陈旧的，不得用于论证口径或商业影响

**2026-10-25 Walter 纠正**：本次曾用存量库存快照算出「403 个 SKU 落最深档 / 36% / ¥157,605」
并据此建议收紧门槛或分两步执行 —— **这是错的**。

原因：现有库存快照里大量 SKU 的库存是**没更新**的，用它推导出来的落档分布、
折扣率、货值占比**都不能作为判断口径设计或商业影响的依据**。

**当前实测的反面例子**（把新判据喂进这批存量快照）：

| 距上次进货天数 | 仓级行数 | 货值 |
|---|---|---|
| ≥120 天 | 1202 | ¥224,723.57（占总货值 97%） |
| 60–90 天 | 8 | ¥2,501.00 |
| <60 天 | 20 | ¥3,298.00 |

**这个「几乎全是重度积压」是数据缺陷，不是业务事实** —— 快照只有 2 个时间点，
中间发生过多少次补货**根本还原不出来**，只能用 `created_at` 当初值，于是所有老 SKU
都显得「很久没进货」。真实分布要等增量采集跑起来、`stock_added_at` 自然积累才有意义。

→ **规则**：
1. 存量数据只能用来验证**机制**（相对比较，例如「补货会不会重置计时器」），
   **不能**用来论证口径设计好坏或商业影响。
2. 任何基于存量数据得出的「多少 SKU 会被打折 / 折扣率会变成多少」的结论，
   **一律不得进入设计决策**。
3. 真实分布的结论，必须等增量采集积累到可用的补货历史之后再做。

### 8.7 进度（2026-10-25 中午）

| 批次 | 状态 |
|---|---|
| **B2 落盘层** | ✅ 已落地并实测（增量设计稿 §5.6） |
| **B4-1 SQL 层** | ✅ `mart.inventory_backlog_base` 重写：删 9999 哨兵 / `risk_level` / `clearance_priority_score` / `daily_avg_sales` / `is_stagnant` / `estimated_stagnant_days` / `stagnant_snapshot_count`；加 `stock_changed_at` / `row_seen_at` / `row_written_at` / `stall_days` / 4 个销量列；`api.business_overview_inventory_backlog_module` / `api.inventory_backlog_summary_module` / `api.clearance_ranking_module` 同步 |
| **B4-2 服务层** | ✅ 删 `_classify_inventory_backlog_risk` / `_inventory_backlog_priority_score` / `build_inventory_backlog_rows`（死代码，仍在造 9999）；`summarize_inventory_backlog_rows` / `_load_inventory_backlog_summary` / `_load_ranked_inventory_backlog_module_rows` 全换口径；新增 `inventory_dos_service`（DOS 参考值唯一实现） |
| **B4-3 前端** | ✅ `BusinessOverview.vue`：顶部 4 张卡换成「总库存价值 / 重度积压 / 中度积压 / 滞销占比」；表格删 5 列（预计周转天数 / 估算积压天数 / 连续积压快照数 / 风险等级 / 清理优先级），加 5 列（仓库 / 停滞天数 / 最后库存变动 / 滞销状态 / 可售天数（参考））；`inventorySummary` 契约同步 |
| **B4-4 SKU 级清单链** | ✅ 视图（改判据、补 `available_stock > 0`）+ service + schema + 路由 + API 参数 + 前端全部换口径；落地时挖出 4 个真问题，见 §8.10.2 |
| **W7 商品中心** | ✅ 列名 `min_age_days` → `min_restock_days`（**门槛 0/60/90/120、折扣率、目标毛利一律不动**）；`select_age_tier` → `select_restock_tier`；取数从库龄换成「距上次进货天数」；「缺料兜底」按 C 保留现状（§8.9.4） |
| **指标词典** | ✅ `inventory_stall_days` → `days_since_restock`；三个**已不存在**的 `inventory_backlog_*_value` 换成真实存在的四个键；两份副本 7/7 SHA256 一致 |
| **B1 增量筛选组件** | ✅ 新组件 + 编排改造 + 行为测试（11 passed）；**真实页面复验待 Walter 跑**，见 §8.11.1 |
| **B3 水位线与断档补采** | ✅ 窗口计算（纯函数）+ 水位线/失败期取数 + 测试（15 passed）；接进采集执行链待做，见 §8.11.3 |
| **B5 下架探测** | ⬜ Walter 的需求描述里没有下架检测，属「商品中心自动化待拍板」那批 |

### 8.8 判据口径修正（2026-10-25 已落地）

| 项 | 修正前 | 修正后 |
|---|---|---|
| 字段 | `stock_changed_at`（任何库存数量变化都推进） | **`stock_added_at`**（**只有库存总量增加（进货）才推进**） |
| 首次观测初值 | 妙手「更新时间」 | **`created_at`**（首次铺货 ≈ 首次进货） |
| 进货判定 | 可用/总量/预占任一变化 | **库存总量增加**（订单占用只动可用不动总量，不会误判） |
| 判据服务 | `inventory_stall_service`（库存停滞时长） | **`inventory_restock_service`**（距上次进货天数），门槛 60/90/120 与档位表同源 |

**实测依据**（两批快照对比 1109 个共同 SKU×仓 —— 相对比较，可用于验证机制）：
- 妙手「创建时间」= 首次铺货时间，补货**不会**重置（1109/1109 行不变）
- 妙手「更新时间」每次写入都变，**连销售都会变**（0/1109 行相同）
- 可用库存与库存总量变化方向 100% 一致；总量多捕捉 2 行（预占变化）

### 8.9 W7 商品中心 · 逐处施工清单（下一轮直接照单执行）

> **硬约束（Walter 拍板）**：
> - **门槛 0 / 60 / 90 / 120 天 —— 一个字不许改**
> - **折扣率 0.10 / 0.15 / 0.20 / 0.30 —— 一个字不许改**
> - 目标毛利 0.25 / 0.22 / 0.18 / 0.10 —— 一个字不许改
> - **列名与文案可以改**（`min_age_days` 已名不副实，实际含义是「距上次进货天数」的下限）

#### 8.9.1 数据库

| 项 | 动作 |
|---|---|
| 列改名 | `finance.sku_pricing_policies.min_age_days` → **`min_restock_days`** |
| 迁移 | 新建 Alembic 迁移 `current_migrations/versions/`，执行 `ALTER TABLE finance.sku_pricing_policies RENAME COLUMN min_age_days TO min_restock_days;`（约束与索引 PostgreSQL 自动跟随） |
| 存量数据 | **不动**（门槛与折扣率原样保留） |
| ⚠️ 不要动 | `current_migrations/versions/20261020_sku_pricing_guardrails.py`（历史建表迁移，改了会让新库与现有库不一致） |

#### 8.9.2 后端（按文件）

| 文件 | 改动 |
|---|---|
| `modules/core/db/schema_parts/business.py` | `SkuPricingPolicy.min_age_days` → `min_restock_days`；docstring「按 SKU 当前库龄档位」→「按距上次进货天数档位」 |
| `backend/schemas/product_center.py` | `SkuPricingPolicyCreateRequest` / `SkuPricingPolicyUpdateRequest` / `SkuPricingPolicyResponse` 的 `min_age_days` → `min_restock_days` |
| `backend/services/sku_pricing_policy_service.py` | `load_current_policies` 的排序键、`to_policy_rows` 的 dict key |
| `backend/services/product_pricing_service.py` | `select_age_tier(policies, age_days)` → **`select_restock_tier(policies, days_since_restock)`**；读 `p["min_restock_days"]` |
| `backend/services/product_pricing_query_service.py` | `load_pricing_context` 取数从 `mart.inventory_age_current.age_days` 换成 **`mart.inventory_state` 的 SKU 级「距上次进货天数」**（各仓取最长，只算有库存的仓）；返回键 `age_days` → `days_since_restock` |
| `backend/services/inventory/sku_clearance_service.py` | `_build_item` 用 `select_restock_tier(policy_rows, days_since_restock)`；`age_days` 参数 → `days_since_restock` |
| `backend/domains/business/routers/product_center.py` | 路径参数 `/api/sku-pricing-policies/{min_age_days}` → `{min_restock_days}`；请求体字段同步 |
| `backend/domains/business/routers/inventory_domain.py` | 滞销清单查询参数 `min_age_days` / `max_age_days` → `min_restock_days` / `max_restock_days`；summary 文案「真库龄口径」→「距上次进货天数口径」 |
| `backend/schemas/inventory.py` | `SkuClearanceRankingItemResponse`：`age_days` / `age_bucket` → `days_since_restock` / `restock_tier` |
| `sql/api_modules/sku_clearance_ranking_module.sql` | 视图输出列同步改名；**列顺序不变**（否则 `CREATE OR REPLACE VIEW` 会报错） |

#### 8.9.3 前端

| 文件 | 改动 |
|---|---|
| `frontend/src/domains/business/views/ProductCenter.vue` | 档位编辑抽屉 `row.min_age_days` → `row.min_restock_days`；更新接口的路径参数与请求体同步 |
| `frontend/src/domains/business/views/inventory/InventoryAging.vue` | 筛选参数 `min_age_days` / `max_age_days` → `min_restock_days` / `max_restock_days`；label「库龄」→「距上次进货天数」 |
| `frontend/tests/inventoryAgingUi.test.mjs` | 断言里的字段名同步 |

#### 8.9.4 「缺料兜底」的处置（**本轮不擅自改，需确认**）

现状：`select_age_tier` 在 `age_days is None` 时**回落最小门槛行 = 日常档 0.10**。
即「算不出库龄」被当成「最新鲜」→ 最该降价的反而拿最高折扣（1122 个 SKU 里 627 个走这条路）。

三个选项：

| 方案 | 做法 | 风险 |
|---|---|---|
| **A（建议）** | 缺料 → 显式标 `restock_days_unavailable`，**不自动改价**（沿用人工覆盖价），页面上标「不可算」 | 需改 `compute_sku_pricing` 对 `policy=None` 的处理 |
| B | 缺料 → 回落最深档（0.30） | 缺料 SKU 会被自动降价，误降风险高 |
| C | 维持现状（回落日常档 0.10） | 「最该降价的反而不降」的问题保留 |

**Walter 未表态 → 本轮不动**，按 C 保留现状，等他给方向。

#### 8.9.5 验收

- 档位表 4 行的 `min_restock_days` = 0 / 60 / 90 / 120（**门槛不变**）
- 4 行的 `discount_rate` = 0.10 / 0.15 / 0.20 / 0.30（**折扣率不变**）
- `target_margin_rate` = 0.25 / 0.22 / 0.18 / 0.10（**不变**）
- 商品中心与 SKU 级滞销清单命中**同一个**档位表、**同一个** `select_restock_tier`
- 迁移可重复执行（幂等）

### 8.10 2026-10-25 下午：B4-4 + W7 落地记录

#### 8.10.1 本轮落地清单

| 工作包 | 状态 | 说明 |
|---|---|---|
| **B4-4 SKU 级滞销清单链** | ✅ | 视图 + service + schema + 路由 + API 参数 + 前端 + 测试（20 passed） |
| **W7 商品中心选档** | ✅ | 列名迁移 + `select_restock_tier` + 取数换「距上次进货天数」+ 能力探测回落 |
| **积压口径统一** | ✅ | 积压 = **还有库存** 且久未补货（见 §8.10.4） |
| **指标词典同步** | ✅ | 判据换名 + 删掉三个不存在的指标 + 两份副本字节一致 |

#### 8.10.2 落地时挖出的真问题（都是实现问题，不是设计问题）

| # | 现象 | 根因 | 处理 |
|---|---|---|---|
| 1 | 端点 `sort_by` 白名单还是旧值（`clearance_priority_score` / `age_days`），与 service 不一致 | 路由只改了参数名，忘了改 `Literal` | 白名单改成 `days_since_restock` / `inventory_value` / `current_qty`，默认值 `days_since_restock`；补端点级 422 用例 |
| 2 | 滞销视图的 `state` CTE **没有** `available_stock > 0` 过滤（文件注释写了，SQL 没做） | 注释与实现脱节 | 补上过滤，与商品中心取数口径**逐字对齐**；实测 507 共同 SKU、**0 个天数不一致** |
| 3 | DOS 参考列**永远是 null** | service 读 `row["checklist_dos_sales90"]`，视图列名其实是 `checklist_sales_90d` | 改走 `inventory_dos_service.compute_dos`（唯一实现）；实测 500 行里 366 行算得出 |
| 4 | `/api/inventory-overview/summary` 500 | B4-2 重写汇总视图时删掉了 `high/medium/low_risk_sku_count`，概览服务还在读 | 视图补三个**去重 SKU 数**（卡片写「SKU 数」就不能给 SKU×仓 的行数），schema / service / 前端同步换新口径 |
| 5 | `product_pricing_query_service` 里残留 `p["min_age_days"]` | 列名迁移时漏了一处生产代码 | 改成 `p["min_restock_days"]`（现在会直接 KeyError） |
| **6** | **状态层 upsert 没有生产调用方** | `InventoryStateRefreshService` **只在测试里被调过** —— 采集完状态层不动 → 距上次进货天数永远不推进 → 增量窗口永远是同一个 → **闭环是断的** | `refresh_queue_tasks.py` 的 inventory 分支补上调用（顺序：同步 SKU 身份 → 状态层 upsert → 刷库龄）；状态层自己先刷一遍上游，不依赖调用方刷过 |
| **7** | **基表 DROP 撞上下游依赖** | `mart.inventory_backlog_base` 删了列 → 必须 `DROP` 重建 → 但四个下游 api 视图依赖它 → PostgreSQL 拒绝（`cannot drop view ... because other objects depend on it`）→ 启动时的资产 bootstrap 整条链失败 → 资产指纹不更新 → **业务概览永久降级、相关 API 503** | ① 基表文件先 DROP 四个下游再 DROP 自己；② **积压资产组（基表 + 四个下游）整体收进 `clearance_ranking` 一个模块** —— 谁重建基表谁就能重建全部下游；③ 采集后刷新（refresh pipeline）的 inventory 域目标补齐四个下游。**三条执行路径（bootstrap / 采集后刷新 / 安全网自愈）全覆盖** |
| **8** | **增量窗口撞 `date_range` 契约** | 我把增量窗口作为**嵌套 dict** 塞进任务的 `date_range`，但响应契约是 `Dict[str, str]` → FastAPI 响应校验失败 → **采集任务列表页 500** | 改成**两个平铺的字符串键** `inventory_incremental_range_start` / `..._end`，契约天然满足；并加契约测试锁住 |

#### 8.10.7 资产链的「DROP 顺序」是一条硬规则（踩过两次的坑）

`mart.inventory_backlog_base` 删了列 → PostgreSQL 的 `CREATE OR REPLACE VIEW` 不能删列 →
**必须 DROP 重建** → DROP 会**连带删掉它的下游视图**。

而「重建基表」这件事有**三条执行路径**，每条都只重建「自己计划里列出来的」目标：

| 路径 | 谁触发 | 计划从哪来 |
|---|---|---|
| 启动/部署时的资产 bootstrap | `scripts/bootstrap_postgresql_dashboard.py` | `DASHBOARD_MODULE_TARGETS` 的模块 core_targets |
| 采集后的刷新 | `refresh_queue_tasks` 的 refresh pipeline | `resolve_refresh_targets_for_source_table` 的依赖图 |
| 安全网自愈 | `dashboard_safety_net_repair` | 同样来自模块 core_targets |

→ **规则：基表与它的全部下游必须同属一个模块 / 同一条刷新目标列表。**
少列一个，就会在「跑完之后某个视图 missing」的形式下复发。

> 复现与验证方式（都已做成契约测试）：
> `backend/tests/data_pipeline/test_inventory_backlog_asset_contract.py`
> 1. 基表文件必须先 DROP 下游再 DROP 自己
> 2. refresh pipeline 的 inventory 域目标必须带齐四个下游
> 3. 基表与全部下游必须同属一个模块
> 4. 增量窗口必须是两个平铺字符串键（不是嵌套 dict）

**另一个坑：`celery worker` 挂载了代码但进程内是旧模块。**
改了 SQL 资产 / 模块定义后必须**重启容器**，否则旧进程会一直用旧的模块定义删视图。

#### 8.10.6 「可以开始采集了吗」的答案：**链路已闭环，但还没在真实页面上验过**

采集前必须知道的两件事：

| 项 | 状态 |
|---|---|
| 落盘 → 状态层 upsert → 判据 → 档位 → 定价 | ✅ 闭环（本轮才补上状态层 upsert 的生产调用方，见 §8.10.2 第 6 条） |
| 妙手页面上的「更新时间维度 + 区间」筛选 | ⚠️ **代码写完了，从没在真实页面上跑过** —— 选择器与维度下拉交互都没有真实证据 |
| 端到端增量采集（真实页面 → 落盘 → 状态层推进） | ⚠️ **没跑过**：现有两批真实数据（file 2764 / 3004）都是**全量**采的 |

→ **可以开始「人工跑一次采集」，但不要开自动调度。** 顺序：

1. 重新登录妙手（现有登录态已失效，探针会明确报）
2. 跑 `scripts/probe_miaoshou_inventory_date_filter.py` —— 只读取证，拿维度下拉的真实结构
3. 按真实结构校正 `inventory_config.py` 的选择器
4. 人工跑一次增量采集 → 检查状态层 `stock_added_at` 是否按预期推进
5. 再考虑开调度

#### 8.10.3 状态层字段「精简」的结论：**保留**（原建议撤回）

原建议是去掉 `mart.inventory_state` 的 `created_at` 初值特例与 `row_written_at`。落地时发现两个都不能删：

- `created_at` 不是冗余，是**首次观测的唯一锚点**：没有它，新出现的 SKU×仓 拿不到进货时间 →
  `days_since_restock` 为 NULL → **不进滞销清单**（而不是「被当成最新鲜」）。删掉它等于把新货漏出榜单。
- `row_written_at` 是妙手「更新时间」的**留档**：它不参与判定，但它是「妙手时间戳会被 bulk UPDATE 批量污染」这个结论的证据，
  以后排查采集异常要看它。

→ 状态层就这点宽度，没有可再瘦的地方。

#### 8.10.4 积压口径统一：**积压 = 还有库存，且久未补货**

落地时发现业务概览与 SKU 滞销清单**互相打脸**：

| 口径 | 判据 | 结果 |
|---|---|---|
| 业务概览「重度积压 SKU」 | ≥180 天（**未过滤零库存行**） | 1,109 |
| SKU 滞销清单（≥180 天） | **只算还有库存的仓** | 496 |

差出来的 613 个是**已经卖空的老品**——它们没有任何资金占用，却占着「重度积压」的名额。

改法收口在唯一源头 `mart.inventory_backlog_base`（加 `available_stock > 0`），
三个 api 视图全部继承，三处口径一次对齐：

| 指标 | 修正前 | 修正后 |
|---|---|---|
| 积压基表行数 / SKU 数 | 1,230 行 / 1,122 SKU | **510 行 / 507 SKU** |
| 重度积压（≥180 天）SKU | 1,109 | **496** |
| 中度积压（90~180 天）SKU | 5 | **4** |
| 总库存货值 | ¥230,522.57 | ¥230,027.57（零库存行的残留货值 ¥495 被剔除） |

> ⚠️ **重建顺序**（PostgreSQL 不允许删掉被依赖的视图）：
> `DROP api.* → DROP mart.inventory_backlog_base → 建 mart → 建 api.*`

#### 8.10.5 验收实测（真实库，非模拟）

- SKU 滞销清单端到端：507 个 SKU / 在库 11,259 件 / 货值 ¥230,027.57 / 缺参考售价 491 个
- 档位分组（门槛**全部来自档位表**，代码里不硬编码）：

  | 档位 | 门槛 | SKU 数 | 货值 |
  |---|---|---|---|
  | 日常 | ≥0 天 | 0 | ¥0.00 |
  | 滞销30天 | ≥60 天 | 7 | ¥2,501.00 |
  | 滞销60天 | ≥90 天 | 0 | ¥0.00 |
  | 滞销60天以上 | ≥120 天 | 500 | ¥227,526.57 |

- 档位表数值核对（改名后，**一个数字未动**）：
  `(0,'日常',0.10,0.25) (60,'滞销30天',0.15,0.22) (90,'滞销60天',0.20,0.18) (120,'滞销60天以上',0.30,0.10)`
- 回归：
  - data_pipeline **25 failed / 442 passed** —— 与 HEAD 基线**逐条一致，零回归**
  - 定价护栏 10 failed + 10 errors、飞书通知 1 failed + 1 error —— 均为既有 asyncpg fixture 问题（`different loop`），与本项目无关
  - 库存相关 31 passed / 商品中心 83 passed / SKU 滞销清单 20 passed / 前端 inventoryAging 17 passed

### 8.11 2026-10-25 晚间：B1（增量筛选组件）+ B3（水位线与断档补采）落地

#### 8.11.1 B1 · 增量筛选组件

新增 `modules/platforms/miaoshou/components/inventory_date_filter.py`：
把仓库清单的筛选器设成「更新时间维度 + 自定义区间」，并交出**三类可断言的落地证据**：

| 证据 | 判据 | 挡住哪种静默失败 |
|---|---|---|
| 维度 | 维度下拉的 `modelvaluegroup` 以 `gmtModified` 开头 | **维度没切**（默认「创建时间」：同区间 3 个 SKU vs 按更新时间 147 个） |
| 区间 | 点完「确定」后筛选器根的 `modelvaluegroup` 含目标起止时间 | **「确定」没点**（区间填了没提交，筛选器还是旧值） |
| 结果 | 搜索后「SKU总数」> 0 且不超过筛选前 | **搜索没刷新** / 筛选把范围清空 |

- 「确定」= `button.jx-picker-panel__link-btn.is-plain`，「清空」= `...is-text`
  → **必须用完整 class 区分**，只匹配 `is-plain` 会误点「清空」（第三种静默失败）。
- 编排：新增 `MiaoshouInventoryIncrementalMixin`，把「搜索前设筛选 + 搜索后断言刷新」接进
  `MiaoshouInventoryExport`。**没配 `ctx.config["inventory_incremental_range"]` 就整段跳过**
  → 全量采集场景行为完全不变。
- 行为测试 `backend/tests/test_miaoshou_inventory_date_filter.py`（11 项）：三条静默失败 +
  确定/清空防呆 + 计数断言（空结果 / 反而变多 / 读不到）。

> ⚠️ **未做真实页面复验**：断言逻辑有单测守住，但选择器与「维度下拉」的交互必须在
> **真实妙手页面**上验一次 —— 这正是 §4 排期里 B1 标注的「需真实页面复验」风险。
> 复验通过前，增量模式**不要上线**。

#### 8.11.2 B3 · 水位线与断档补采

新增 `backend/services/inventory/inventory_collection_window_service.py`。

**水位线不另建表** = 该平台 `mart.inventory_state` 的 `MAX(row_seen_at)`：
- 用**我方采集时钟**：妙手时间戳会被一次 bulk UPDATE 戳穿（535 行 / 43.7%），
  拿它当水位线会**跳过整段真实变更**
- 不建表的另一个好处：水位线**随状态层 upsert 天然推进**，不需要额外的写路径

**窗口计算（纯函数）**：

| 情形 | 窗口 | 理由 |
|---|---|---|
| 配置了 custom 区间 | **原样使用**（不裁剪、不回填） | custom 是**一次性补数**，用户意图最高 |
| 未配置（自动推进） | `[水位线 − 重叠余量, now]` | 从上次采到的地方接着采 |
| 断档（距今 > 阈值） | 起点再向前拉到 `now − 长窗口天数` | 断档越久，水位线精度越不可信 |
| 上一批失败 | 起点向前拉到失败批次起点 | 失败期不能漏 |

「长窗口补采」是**下限**，不是收窄：窗口起点 = `min(水位线 − 重叠余量, now − 长窗口天数)`。
水位线比长窗口更久 → **以水位线为准** —— 收窄 = 跳过中间那几天 = 静默漏采，
是这个模块最不能犯的错。

失败期覆盖复用既有 `core.collection_config_runs`（有 `status` / `started_at`），
**不需要新建水位线表**。

测试 `backend/tests/data_pipeline/test_inventory_collection_window.py`（15 项）。

#### 8.11.3 还没做的（下一轮）

| 项 | 为什么没做 |
|---|---|
| 把窗口计算接进采集执行链 | ✅ 已按方案 C 落地（全自动、运营零操作），见 §8.11.4 |
| B1 真实页面复验 | 需要真实妙手环境（Walter 自己跑） |
| B5 零库存宽限期（下架探测） | Walter 的需求描述里没有下架检测；属「商品中心自动化待拍板」那批 |

#### 8.11.4 接进采集执行链：**已按方案 C 落地**（全自动，运营零操作）

> **2026-10-25 定案**：Walter 问「采集到应用数据不都是自动化的吗」——对，自动化是通的，
> 之前列 A/B/C 是把问题复杂化了。**默认就该是全自动增量**，加开关反而是给自动化加人工步骤。
> 故按 **方案 C** 落地：**不加任何配置开关、不改 UI**。

##### 断在哪一环（原来）

采集自动化本身是通的（配置 → 调度 → 执行器 → 组件 → 落盘 → 状态层 upsert → 判据 → 档位 → 定价）。
断的是**组件那一环**：

| 妙手数据域 | 有没有日期筛选组件 | 配置里的日期区间是否生效 |
|---|---|---|
| orders | ✅ `MiaoshouDatePicker` | ✅ 生效 |
| purchase | ✅ `MiaoshouDatePicker` | ✅ 生效 |
| **inventory** | ❌ **从来没有** | ❌ **一直是空转** |

→ 妙手仓库清单每次都**导全量**（1113 行）。现有 3 条妙手配置里，库存的日期区间设了也白设。

##### 现在的接法

**专用键 `inventory_incremental_range`**：任务的日期区间是**所有数据域共享**的
（orders 与 inventory 在同一个 task 里），改它会连带改掉订单域的范围 →
库存窗口必须走**只有库存导出组件读**的专用键，别的数据域一点不受影响。

| 环节 | 改动 |
|---|---|
| 决策 | `resolve_incremental_range()`：运营显式指定区间 → 用它；**没有水位线** → 不设筛选（导全量建基线）；否则 → 水位线窗口 |
| 接入点 | `collection_config_execution.py` 建任务时算一次窗口，塞进任务的 `date_range` JSON |
| 透传 | `normalize_collection_date_range` 保留该键；执行器 `_build_runtime_task_params` 放进 `params`（2 行，**执行器主体不动**） |
| 消费 | `MiaoshouInventoryExport` 读到就设筛选器；读不到就**完全不设筛选**（= 今天的行为） |

**规则**（运营零操作）：

| 情形 | 库存域这一次采什么 |
|---|---|
| 运营配了 custom 区间 | 按那个区间（一次性补数 / 指定窗口） |
| 没配 + 状态层已有水位线 | 按「上次采到的地方 → 现在」自动筛（断档会自动拉长） |
| 没配 + 状态层还没有这个平台 | **不设筛选，导全量建基线**（与今天一致，不会因接增量丢基线） |

实测（真实库）：水位线 `2026-10-23 04:39:53` → 窗口 `2026-10-23 04:39:53 ~ 2026-10-25 12:50:29`（gap 1 天），
共享区间 `date_from/date_to` **原样不动**（订单域不受影响）。

##### 仍需你确认的两点

1. **B1 真实页面复验**：选择器与维度下拉的交互必须在真实妙手页面验一次。
   **复验通过前，先别开自动调度**（现有 3 条妙手配置的 `schedule_enabled` 都是关的，正好）。
2. **全量兜底没了**：全量档已按你的决定取消。库存数不会丢（落盘 upsert + 状态层永续），
   但如果妙手时间筛选有最大跨度、或某天妙手侧异常，没有全量对账。
   → 建议保留一条 custom 区间很宽的月度配置做兜底（现有 config 27 `monthly-inventory` 已是这个形态，只需把区间放宽并开 schedule）。
### 8.12 2026-10-26 凌晨：B1 采集组件按**真实页面**重校准

#### 8.12.1 失败现象（真实任务 `7b302e24`）

Walter 手动跑了一次妙手库存采集，失败。步骤日志原文：

```
[step_start]  设置更新时间维度与采集区间
[step_failed] 导出流程失败
   reason=仓库清单日期筛选面板打不开
   matched_signal=date_filter:modelvaluegroup
   current_url=https://erp.91miaoshou.com/warehouse/checklist
```

失败在**第 3 步**（设置时间筛选）。**搜索和导出根本没开始** —— 这也印证了
「设置筛选」这一步在旧实现里就是一道硬门槛。

#### 8.12.2 根因：组件假设了一个**根本不存在的面板**

上一版组件把妙手的筛选器当成 jx-ui 的 picker 面板：

| 旧选择器 | 假设 |
|---|---|
| `.jx-picker-panel` | 存在一个筛选面板 |
| `.jx-picker-panel .jx-select` | 维度下拉在面板里 |
| `.jx-picker-panel .jx-select-dropdown li` | 维度选项在面板里 |
| `.jx-picker-panel input.jx-range-input` | 区间输入框在面板里 |
| `button.jx-picker-panel__link-btn.is-plain` | 面板底部有「确定」按钮 |

真实页面（2026-10-26 页面截图 + 失败现场）**没有这个面板**：

```
[仓库: 全选 ✕ +4] [商品SKU ▾] [双击补录…]
[是否有预占库存: 请选择] [可用库存 ▾]
[创建时间 ▴] [🕐 开始时间 ______ - 结束时间 ______] [🔍 搜索] [重置]
                └─ 下拉展开后浮层里只有两项：创建时间 / 更新时间
```

- 时间维度是**筛选栏里的内联下拉**，触发器上直接显示当前维度名
- 下拉浮层里就两项：「创建时间」「更新时间」
- 日期区间是**内联的两个输入框**（占位文字「开始时间」「结束时间」）
- 填完**直接点「搜索」** —— 页面**没有「确定 / 清空」按钮**

→ `_open_panel()` 等 `.jx-picker-panel` 永远超时 → 抛「面板打不开」→ 整段失败。

> **教训（写进组件约定）**：class 是 UI 库的实现细节、随版本变；
> **业务文案（「创建时间 / 更新时间 / 开始时间 / 结束时间」）才是稳定锚点**。
> 上一版把全部赌注押在 class 上，一次页面改版就全线崩。

#### 8.12.3 新策略：文案 / placeholder 驱动 + 幂等 + 顺序无关

| 环节 | 旧（猜 class） | 新（认文案） |
|---|---|---|
| 维度下拉 | `.jx-picker-panel .jx-select` | 找**可见**的「创建时间 / 更新时间」文字 |
| 维度落地证据 | `modelvaluegroup` 以 `gmtModified` 开头 | 触发器文案变成「更新时间」（人能读） |
| 浮层可见 | 等 `.jx-picker-panel` 出现 | 等「更新时间」**变得可见**（浮层展开 = 它出现） |
| 区间输入框 | `.jx-picker-panel input.jx-range-input` | `input[placeholder*='开始时间']` / `'结束时间'` |
| 「确定」 | **必经步骤**，找不到就失败 | **可选**：有就点，没有不算失败 |
| 区间证据 | 读筛选器根的 `modelvaluegroup` | 输入框回填值（真实页面）/ 属性（老路径） |

另外三条健壮性：

1. **幂等**：已经是「更新时间」就**不碰下拉** —— 用户（Walter）可能已经手动选过，
   重复点反而把状态点乱。
2. **顺序无关**：读当前维度前先 `Escape` 收起浮层，
   避免把浮层里的选项误当成触发器上的当前值。
3. **格式自愈**：填 `2026-10-01 00:00:00` 没落进去，自动降级成 `2026-10-01` 再试。

#### 8.12.4 流程改动：先搜索拿基线 → 再设筛选 → 再搜索

仓库范围和日期区间是**两套独立筛选条件**：仓库选完不点搜索，页面上显示的还是
上一次的搜索结果。所以增量模式改成**搜索两次**：

```
1. 全选仓库
2. 搜索 #1  → 读「SKU总数」当基线（筛选前的真实口径）
3. 设「更新时间维度 + 目标区间」
4. 搜索 #2  → 让筛选生效，再读一次「SKU总数」
5. 断言：筛选后总数不得超过基线
```

**全量模式完全不变**（没配增量区间 → 仍然只搜索一次）。

#### 8.12.5 顺带修掉的一个**假断言**

原实现里 `_sku_total_before` 是在**筛选之后**才读的 —— 基线和结果永远是同一个数，
于是「筛选是否生效」这条断言永远走「相等 → 只警告」分支，**永远不报错**。
现在基线改到搜索 #1 之后读，断言才真正有牙齿。

同时修掉一个隐性 bug：读输入框值时把 `input_value()`（无参）和
`get_attribute("value")`（有参）混用 → 两者双双失败 → 永远读到空值。

#### 8.12.6 取证探针重写（下次页面开着时一次抓全）

旧探针**也假设**了 `.jx-picker-panel`，所以它跟组件一起错、一直没能给出真证据。
新探针：

- **不假设任何结构**，直接把真实 DOM 抓下来：维度元素（含 class 与 outerHTML）、
  所有 input 的 placeholder/class/type、「确定/清空/搜索/重置」按钮、下拉浮层结构
- **用组件自己的定位逻辑**跑一遍 `probe_state()` → 探针的结论就是组件的结论，
  不会再出现「探针能找到、组件找不到」
- 输出 `output/probe_inventory_date_filter.json` + 截图
- 只读保证不变：不 save 登录态、不填区间、不点搜索、不点导出

#### 8.12.7 前端：任务详情抽屉比例 + 5 处乱码

- 抽屉宽度 `520px` → `min(720px, 92vw)`；`el-descriptions` 固定 `label-width="128px"`
  —— 之前 label 列被挤到一字一行（中文竖排）
- 长文本（URL / 错误串）现在能断行，不再撑破表格
- 顺手修了 5 处**源码里就是乱码**的 label 与 3 处乱码值
  （2026-05-18 那次提交加进来时编码就坏了，一直没人看见 —— 因为这些字段平时没值）

#### 8.12.8 验收状态

| 项 | 状态 |
|---|---|
| 组件行为测试 | 12 passed（新增：无「确定」按钮走通、幂等不碰下拉、浮层选项不误判） |
| data_pipeline 回归 | 25 failed / 468 passed（与基线逐条一致，**零回归**） |
| 前端相关测试 | 与 HEAD 逐条一致（既有失败不变） |
| 长度门禁 | 函数 ≤50 行、类 ≤500 行 通过 |
| **真实页面复验** | ⏳ **未做** —— 页面已关闭，必须等下一次登录后跑新探针 |

> ⚠️ **复验通过前，先别开自动调度**（现有 3 条妙手配置的 `schedule_enabled` 仍是关的）。
> 这次改的是「定位方式」，不是「口径」；但**没在真实页面上跑过一次**，
> 就仍然只是纸面正确。

---

## 8.13 2026-10-26 下午：第二次失败现场 —— 表格表头把下拉选项顶掉了

Walter 重启电脑后重跑采集，仍然失败：

```
task_id = 5526faf9-05c2-4ffc-b889-16bfe572d39a
date_filter_failed: stage=date_filter_ready status=failed
reason=维度未切到「更新时间」（下拉触发器上的文案没变）
matched_signal=date_filter:dimension_text
```

Walter 的现场描述：「可以准确打开创建时间和更新时间的框，但是最后点击只点击了创建时间的内容」。

### 8.13.1 根因（真实 DOM 取证，不是推测）

探针在**真实页面**上抓到的证据：

```
page.get_by_text("更新时间", exact=True)  →  2 个可见命中
  ├─ index 0: <div class="cell">更新时间</div>          ← ★表格表头的排序列
  │            <th class="jx-table_1_column_23_column_24 … is-sortable">
  └─ index 1: <li class="jx-select-dropdown__item" role="option">更新时间</li>
```

**结果表格的表头里本来就有「创建时间」「更新时间」两列（可排序）**，
和下拉浮层里的选项**同名**。组件原来取 `.nth(0)` → 点到的是**表头**
→ 触发的是「按更新时间排序」→ 维度根本没切 → 报「维度未切到」。

一句话：**全页 `get_by_text` 命中的是同名表头，不是下拉选项。**

同一个根因还污染了「读当前维度」：全页找「创建时间/更新时间」会同时命中表头和触发器，
判定永远落在「两个都在 → 保守按未切换处理」分支。

### 8.13.2 修复：所有维度定位都**限定范围**

| 动作 | 修复前（全页） | 修复后（限定范围） |
|---|---|---|
| 找触发器 | `get_by_text(维度文案)` | `[modelvaluegroup*='gmt']` —— 维度键挂在触发器根上（`modelvaluegroup="gmtCreate,"`），**表头没有这个属性** |
| 读当前维度 | 全页找两个文案 | **只从触发器读**（先读维度键 `gmtCreate/gmtModified`，读不到再读文案） |
| 找「更新时间」选项 | 全页找 → 命中表头 | **可见的下拉浮层容器内**找（`.jx-select-dropdown:visible` → `li.jx-select-dropdown__item`） |
| 点触发器 | 找「创建时间」文字的祖先 | 点触发器内的 `.jx-select__wrapper` |

关键结构（真实取证）：

```html
<!-- 触发器：维度键就在这儿 -->
<div class="jx-select jx-select--small pro-select" fieldtype="select"
     modelvaluegroup="gmtCreate," style="width:100px">
  <div class="jx-select__wrapper jx-tooltip__trigger">
    <div class="jx-select__selected-item jx-select__placeholder">
      <span>创建时间</span>

<!-- 下拉浮层（.jx-select-dropdown 有十几个，每个 select 一个） -->
<div class="jx-select-dropdown pro-select-popper">
  <div class="jx-scrollbar">
    <div class="jx-select-dropdown__wrap jx-scrollbar__wrap">
      <ul class="jx-scrollbar__view jx-select-dropdown__list" role="listbox">
        <li class="jx-select-dropdown__item is-selected" role="option">创建时间 </li>
        <li class="jx-select-dropdown__item" role="option">更新时间 </li>
```

⚠️ 维度那个下拉浮层在 DOM 里排在**很靠后**（十几个 select 依次排开）
→ 扫描时必须先用 `:visible` 精准命中，不能指望按顺序扫到。

### 8.13.3 顺带修掉的第三个假东西：`read_sku_total`

原来读的是「包含 SKU总数 的那个元素的全文里的**第一个数字**」——
那块区域里还有「库存总数 / 库存总价值 / …」，实测取到过 **0**。
现在改成用正则**紧跟在「SKU总数」后面**取数
（`SKU总数[:：]?\s*([\d,]+)`）。这条数字是「搜索有没有刷新」的判据，
取错就等于这条断言没有牙齿。

### 8.13.4 探针也修了两个自己的毛病

| 毛病 | 后果 | 修法 |
|---|---|---|
| 把**外层包装**的 storage_state 喂给 Playwright | 顶层没有 `cookies` 键 → 实际 cookie 数 = 0 → 永远跳回登录页 → 被误判成「妙手把登录踢下线了」 | 按 `executor_v2` 的同一规则取**内层**（真凶在探针，不在妙手） |
| 「提示」通知**异步弹出** | 关掉第一个之后 ~7 秒又来一个，挡住点击 | 持续巡检到**连续 3 轮安静**才算关完 |

### 8.13.5 验收状态

| 项 | 状态 |
|---|---|
| 组件行为测试 | **15 passed**（新增：点下拉选项而不是表头、读维度不把表头算进来、找不到维度 select 明确失败） |
| 旧逻辑对照 | 把组件改回 2026-10-26 的定位逻辑 → 同样报错、表头被点 1 次、选项被点 0 次 → **新测试有牙齿** |
| 妙手相关测试 | 99 passed（另 2 条 `test_collection_time_selection_contract` 是既有失败，基线复验一致） |
| data_pipeline 回归 | **26 failed / 467 passed**，失败清单与 HEAD 基线**逐条同名同序** → 零回归 |
| 长度门禁 | 函数 ≤50 行、类 ≤500 行 通过（主类 384 → 523 行，拆出 `inventory_dimension_mixin.py` 后回到 478 行） |
| black / ruff | 通过 |
| **真实页面复验** | ✅ **通过** —— 探针 `--mode verify` 在真实妙手页面上 `ok=True`，`final_dimension='更新时间'`，截图可见触发器已显示「更新时间」 |

> ✅ 上一版 §8.12 里「⏳ 真实页面复验未做」这条**已闭环**：
> §8.12 的修法（文案驱动）方向没错，但**定位范围**错了 —— 必须限定在触发器和浮层容器内。
> 这次是在真实页面上跑通并截图确认的。

> ⚠️ 仍然**先别开自动调度**（现有 3 条妙手配置的 `schedule_enabled` 还是关的）。
> 组件这一环已经通了，但**完整增量采集链路**（两次搜索 + 区间生效 + 结果集刷新）
> 还需要在真实任务里跑一次，确认状态层水位线真的在推进。

---

---

## 8.14 维度切通之后挖到的下一个坑：区间填了，但**收面板的方式**把它弄丢了

§8.13 把维度切通了，真实页面验收也过了。但把验收范围从「维度」扩到
「维度 + 区间」（直接调采集真正用的 ``apply_incremental_range``）之后，
挖出**另一个更隐蔽的问题**。

### 8.14.1 现象（真实页面取证）

点开筛选栏的区间输入框，妙手会弹出一个**日期选择面板**：

```html
<div class="jx-picker-panel jx-date-range-picker has-sidebar has-time"
     actualvisible="true" format="YYYY-MM-DD HH:mm:ss"
     modelvalue="" isrange="false" clearable="true">
  <div class="jx-picker-panel__sidebar">  今天 / 昨天 / 近7天 / 近30天 / 近90天 </div>
  <div class="jx-picker-panel__body">      左右两个月 + 时间编辑器 </div>
  <div class="jx-picker-panel__footer">
    <button class="jx-button jx-button--small is-text jx-picker-panel__link-btn">清空</button>
    <button aria-disabled="true" disabled=""
            class="jx-button jx-button--small is-disabled is-plain jx-picker-panel__link-btn">确定</button>
  </div>
</div>
```

填完区间后，面板的「确定」**仍是 disabled** —— 看起来像是
「值没进 picker 的 v-model → 区间没生效」。

### 8.14.2 找到最硬的落地判据：搜索请求的参数

妙手点「搜索」打的是：

```
POST /api/warehouse/goods/searchGoodsSkuWarehouseList
body = pageSize=20&page=1&...&
       gmtCreateStart=&gmtCreateEnd=&gmtModifiedStart=&gmtModifiedEnd=&...
```

**日期条件就是 ``gmtCreateStart/End``（维度=创建时间）与
``gmtModifiedStart/End``（维度=更新时间）**。
所以「区间到底生效没有」不该看输入框长什么样，
而该看**点搜索时请求里的这两个参数是不是非空**。

### 8.14.3 结论：**区间是生效的**，问题在「怎么收面板」

用请求参数当判据做对照实验，结论反转了：

| 收面板的方式 | picker 收到值吗 | 输入框里的值 | 请求里的日期参数 |
|---|---|---|---|
| 按 **Escape** | ❌（「确定」仍 disabled） | **被回滚清空** | **空** |
| 按 **Tab**（真实 blur） | ✅（「确定」变可用） | **保留** | `gmtCreateStart=2026-10-01 00:00:00&gmtCreateEnd=2026-10-25 23:59:59` |

（实验里没切维度，所以落在 `gmtCreate*`；维度=更新时间时落在 `gmtModified*`。）

→ 之前那版组件用 **Escape** 收面板 = **把好不容易填进去的区间弄丢了**；
而它的落地证据读的是**填充瞬间**的输入框值 → 读到还没被回滚的值
→ **误判成成功**。

这就是最危险的一类静默失败：**增量采集悄悄变成全量采集**。

### 8.14.4 顺带发现：妙手授权已经过期（**阻断性**）

探针在页面上撞到一个反复出现的 message box，点不掉：

```
<div role="dialog" class="jx-overlay-message-box">
  <div class="jx-message-box__message"><p>您的授权已经过期，请重新登录</p></div>
  … 取消 / 重新登录 …
</div>
```

- 这个弹窗**每次被关掉又立刻弹回来**（授权确实过期，每次请求都触发）
- 它会**挡住页面上任何点击**（Playwright 报 `… intercepts pointer events`）
- 探针里 **SKU总数 恒为 0** 就是它造成的 —— 不是仓库没选，是**查不到数据**

→ 采集时间点是 12:07（当时页面正常、有 1112 行数据），探针跑到 12:50 时授权已过期。
→ **需要人工重新登录妙手**。

### 8.14.5 修复（提交 `29ff2fb3` + 区间收面板修正）

1. **填完区间必须收面板** —— 面板开着会挡住「搜索」按钮
   （`… .jx-picker-panel__sidebar … intercepts pointer events` → 采集卡死）
2. **收面板用 Tab（真实 blur），不能用 Escape** —— Escape 会回滚掉没提交的值
3. **落地证据必须在收面板之后重新读输入框** —— 填充瞬间读到的值不作数
4. **「确定」按钮要分清三种情况**：
   - 页面**没有**这个按钮 → 不算失败（真实页面筛选栏上就没有）
   - 按钮**在、但 disabled** → **不能当成功**（这说明 picker 还没收到值）
   - 按钮**可用** → 点它（点它才算提交草稿）
5. 收面板的完整顺序：「确定」(可用时) → 拉回焦点按 **Tab** → 还开着就再点一次
   「确定」（草稿提交后它才变可用）→ 还是收不掉就**明确失败**，
   不带着开着的面板去点搜索
6. 顺手删掉重复实现：原来的 `_click_confirm_if_present` 与
   `_click_confirm_if_enabled` 是同一段逻辑的两份拷贝，
   合并成一个带 disabled 判断的实现

### 8.14.6 端到端验收（真实页面，探针 ``--mode verify``）

```
final_dimension      = '更新时间'
range_start_value    = '2026-10-01 00:00:00'      ← 收面板后仍在
range_end_value      = '2026-10-25 23:59:59'      ← 收面板后仍在
date_panel           = 已收起（visible=False）
search_request_dates = {
    'gmtCreateStart': '', 'gmtCreateEnd': '',
    'gmtModifiedStart': '2026-10-01 00:00:00',    ← ★ 落在 gmtModified（更新时间）
    'gmtModifiedEnd':   '2026-10-25 23:59:59',
}
```

→ **维度、区间、面板收起、搜索请求参数，四项全部对上**。
→ B1 增量筛选组件在这条链路上**端到端打通**。

### 8.14.7 测试（22 项行为测试，有牙齿）

`backend/tests/test_miaoshou_inventory_date_filter.py`

假页面**刻意复刻**真实页面的三个陷阱：

- 表格表头里有**同名**的「创建时间 / 更新时间」两列 —— 全页搜索第一个命中是表头
- 填完区间会弹出日期面板，面板**开着会挡住「搜索」按钮**
- 「确定」按钮**填完之后是 disabled**，草稿提交（Tab 失焦）之后才变可用；
  按 Escape 会把没提交的值**回滚清空**

对照实验：

- 把收面板方式退回 **Escape** → **8 项变红**
- 把维度定位退回全页 `get_by_text(...).nth(0)` → 同样变红
  （表头被点 1 次、选项被点 0 次 → 报「维度未切到」）

→ 测试是真的在守这两条行为，不是摆设。

> ⚠️ 仍然**先别开自动调度**（现有 3 条妙手配置的 `schedule_enabled` 还是关的）：
> 筛选器这一环通了，但**完整采集链路**（两次搜索 + 导出 + 落盘 + 状态层水位线推进）
> 还需要在真实任务里跑一次，确认状态层水位线真的在往前走。

## 8.15 端到端验收：增量采集真跑通了（2026-10-26 13:30）

Walter 人工跑了一次配置 27（custom 2026-10-01 → 2026-10-10），
任务 644（`3b38c158-4663-4627-a481-ac50b0d24c4a`）**completed**，1 个文件，83 秒。
本节只记**已核实的事实**。

### 8.15.1 区间真的生效了 —— 决定性证据是「行数变了」

| 文件 | 妙手「更新时间」窗口 | 导出行数 |
|---|---|---|
| 3004（10-24 全量） | 2026-09-01 → 2026-09-30 | **1113 行** |
| 3005（本次增量） | 2026-10-01 → 2026-10-10 | **48 行** |

- 48 行的 `observed_at`（妙手侧更新时间）全部落在 2026-10-01 00:00 ~ **2026-10-10 07:47:03**
- 同一个接口、同一个页面、同一个导出按钮：上次 1113 行，这次 48 行
- → 区间若没生效，必然还是 1113 行。**这一条同时验掉了「维度没切」和「区间没落进去」两个坑。**

任务日志留痕：`[step_success] 搜索结果就绪（incremental）`
任务 `date_range` 里带的是**专用键**：
`inventory_incremental_range_start = 2026-10-01 00:00:00` / `..._end = 2026-10-10 23:59:59`
（没动共享区间 `date_range`，所以订单域不受影响）

### 8.15.2 状态层：水位线推进了，闸 2 判定也正确

- `mart.inventory_state`：1230 行，其中 **48 行 `source_file_id = 3005`**
- `max(row_seen_at)`：2026-10-24 04:39:53 → **2026-10-26 05:32:39+00**（= 13:32:39 本地）
- `max(stock_added_at)`：仍是 2026-10-14 04:00:13，**没动** —— 这是对的：
  本次 48 行的 `on_hand_stock` 变化**全是减少或不变，没有一行是增加**
  → 按「库存有增长才清零计时」的规则，就不该清零

库龄层同步验证了这 48 行的行为：`reset_reason` 全是 `continued`（继续累加），
没有一个被清成 `stock_increase`。

### 8.15.3 下游全部刷新到新数据

| 目标 | 行数 | 最新时间 |
|---|---|---|
| `b_class.fact_miaoshou_inventory_snapshot` | 2387 | max(file_id) = 3005 |
| `semantic.fact_inventory_snapshot` | 2387 | ingest 05:32:39 |
| `mart.inventory_state` | 1230 | 48 行来自 3005 |
| `mart.inventory_age_current` | 494 | updated 05:33:54 |
| `mart.inventory_age_history` | 2246 | created 05:33:54 |
| `mart.inventory_snapshot_latest` / `_company_daily` / `_change` / `_history` | 1230 / 2246 / 1230 / 2387 | ingest 05:32:39 |
| `mart.inventory_backlog_base` | 510 | row_seen_at 05:32:39 |
| `mart.spu_operating_current` | 283 | — |
| `api.inventory_age_summary_module` | 494 SKU / 10,797 件 / ¥213,114.31 | — |
| 云端镜像 `fact_miaoshou_inventory_snapshot` | — | last_ingest 05:32:39, completed |

### 8.15.4 档位与定价：数值一个没动，端到端对得上

`finance.sku_pricing_policies` 4 行，门槛 / 折扣率 / 目标毛利**逐字未动**：

| min_restock_days | tier_label | discount_rate | target_margin_rate |
|---|---|---|---|
| 0 | 日常 | 0.10 | 0.25 |
| 60 | 滞销30天 | 0.15 | 0.22 |
| 90 | 滞销60天 | 0.20 | 0.18 |
| 120 | 滞销60天以上 | 0.30 | 0.10 |

实调 `SkuClearanceService`（只读）返回：`days_since_restock = 656` →
`tier_label = 滞销60天以上` → `current_discount_rate = 0.3` →
`current_target_margin_rate = 0.1` → `min_selling_price = 90.87`（`cost_floor`）。

### 8.15.5 UI 上那 8 条提示与库存无关

`auto_ingest_20261026051502_92000222`（12:15 与 13:15 各一次，8/8 文件，partial_success）：
8 条 warning 全是 `blocked_missing_template` / `NO_TEMPLATE`，
file 2756~2763，文件名都是 `miaoshou_orders_*` / `miaoshou_purchase_*` 的 2025-09-14 旧文件。
**没有一个是库存文件。**

### 8.15.6 刷新队列那条任务标了 failed —— PostgreSQL 死锁（数据没丢）

`core.refresh_queue_tasks` id=1191（05:32:40 入队，05:33:00 → 05:35:10 跑完）：

```
refresh pipeline partial_failed:
  mart.inventory_backlog_base, mart.inventory_snapshot_history, semantic.fact_orders_atomic
```

`ops.pipeline_run_log` 里的原始报错：

```
asyncpg.exceptions.DeadlockDetectedError: deadlock detected
DETAIL: Process 4693 waits for AccessExclusiveLock on relation 1992999;
        blocked by process 4591.
        Process 4591 waits for AccessShareLock on relation 1992994;
```

- relation 1992999 = `mart.inventory_snapshot_history`（**视图**）
- relation 1992994 = `semantic.fact_inventory_snapshot`（**视图**）
- **死锁双方抢的都是视图** → 视图本来就自动反映底层数据 → **数据没丢**
  （这两个视图现在的数据都是新的：ingest 05:32:39）

**根因（2026-10-26 17:5x 两次更正，最终版）**

刷新流程里 9 个目标，**6 个是普通视图**，每个都是 `CREATE OR REPLACE VIEW`：

```
semantic.fact_inventory_snapshot      普通视图   ← 视图链的顶端
  └─ mart.inventory_snapshot_history  普通视图
       ├─ mart.inventory_snapshot_latest          普通视图
       │    └─ mart.inventory_backlog_base        普通视图
       │         └─ api.business_overview_inventory_backlog_module / api.clearance_ranking_module …
       ├─ mart.inventory_snapshot_change          普通视图
       └─ mart.inventory_snapshot_company_daily   普通视图
            └─ mart.inventory_age_history
```

**死锁是 ABBA 型，成因是「两个刷新进程同时沿同一条视图链往下走」**：

| 进程 | 手上持有 | 下一步要 | 被谁挡 |
|---|---|---|---|
| 4693 | `fact_inventory_snapshot` 的 **ACCESS EXCLUSIVE**（它正在**重建**这个视图） | `mart.inventory_snapshot_history` 的 ACCESS EXCLUSIVE（**重建下游**） | 4591 |
| 4591 | `mart.inventory_snapshot_history` 的锁（它正在**重建**这个视图） | `semantic.fact_inventory_snapshot` 的 ACCESS SHARE（**重建时要解析上游引用**） | 4693 |

→ 重建视图要拿「目标视图的排他锁」+「被引用视图的共享锁」；
两个进程沿同一条链反向推进，就是教科书式的 ABBA 死锁。

**两处此前的误判**（都已更正）：

- ❌ 「另一个进程在**读**视图」→ 读只拿 ACCESS SHARE，只会**等**，不会成环；
  死锁的双方**都是刷新进程**（uvicorn 后端的 ingest 后台流程 + celery worker 的刷新队列任务）
- ❌ 「根因是 `_OPS_TABLES_LOCK` 是进程内 `asyncio.Lock`」→ 那个锁只保护
  「ops 四张日志表是否已建好」的一次性检查（`_OPS_TABLES_READY_SIGNATURE` 缓存），
  **与视图重建、与本死锁都无关**

**为什么「物化视图刷新不阻塞读」在这里不适用**：

- **物化视图**：`REFRESH MATERIALIZED VIEW` 刷的是**数据**（物理表内容）→
  拿 `SHARE UPDATE EXCLUSIVE` 锁 → **不阻塞读**
- **普通视图**：没有物理数据，数据是查询时**实时算**的；
  我们对它做的是 `CREATE OR REPLACE VIEW` = **改写查询规则** →
  必须拿 `ACCESS EXCLUSIVE` → **阻塞一切读**
- 而普通视图**压根不需要"刷新"** —— 每次数据刷新都重建它，是**纯粹多余的动作**，
  而且正是这个多余动作制造了死锁

**为什么现有的重试救不回来**：`execute_sql_target` 的重试用的是
`async with db.begin_nested()`（SAVEPOINT），只救**语句级**错误。
而 PostgreSQL 的死锁是**事务级**失败 —— 事务被标记 aborted 后，
SAVEPOINT 回滚无效，必须**回滚整个事务再重开**。
所以现在死锁必然把任务打成 failed。

**治本方向随之明确**：数据刷新流程**不该碰普通视图**。
视图定义归 migration（部署时改一次），刷新只做表的 DML / 物化视图的 REFRESH；
或把 `CREATE OR REPLACE VIEW` 换成 `CREATE VIEW IF NOT EXISTS`
（已存在就跳过 → 不拿排他锁），定义变更仍走 migration 兜底。

### 8.15.7 发现：两套「距上次进货天数」并存，且差了 19~656 天

**两套实现的规则完全相同**（有增长才清零；减少/不变就沿用），**差别只在
「一个 SKU 第一次出现时从哪天起算」**：

| | A. 库龄层 `mart.inventory_age_current` | B. 状态层 `mart.inventory_state.stock_added_at` |
|---|---|---|
| 比数量跟谁比 | 把快照按时间排队**逐帧**比 | 跟状态层里存的上一批数量比 |
| 有增长 | 清零（`stock_increase`） | 清零（`restocked`） |
| 减少 / 不变 | 沿用（`continued`） | 沿用（`unchanged`） |
| **首次出现的起算点** | 它第一次出现的那一帧（`first_positive`） | **妙手「商品创建时间」**（`first_observation`） |
| 实测同 458 个 SKU | **17 ~ 30 天** | **655 ~ 656 天** |

- 458 行里 **0 行一致**，差值 19~656 天
- 原因：状态层是 **2026-10-14 才建立的**，09-14 那次真实进货它没看见；
  等它第一次看到这个 SKU 时已经没有参照，只能拿妙手「商品创建时间」凑数
  —— 那是**上架时间**，跟进货是两回事
- 消费方：`api.sku_clearance_ranking_module`（滞销/定价，`MAX(CURRENT_DATE - stock_added_at::date)`）
  与 `mart.inventory_backlog_base`（积压，同一算法）→ **档位、折扣、最低售价、积压
  四条链全部读的是 B**
- 库龄层 A 的 `age_anchor_date` 只有三个取值（2026-09-01 / 09-14 / 10-01），
  因为它只有这几帧快照可回放；204 行的 `stock_increase` 全部落在 2026-09-14 那一帧

> ⚠️ 这个取舍（以哪套为唯一真相源、要不要改粒度）**属于口径决策，未定**。
> 在定下来之前，档位/折扣的输出维持现状（B）。

## 8.16 「准备同步」时页面报内部错误：并发共享数据库会话（系统性修复 + 两道自动化守卫）

### 8.16.1 现象

Walter 采集完妙手 10-01~10-26 的「库存 + 订单」两个数据域，任务 645 显示**完成**，
但到「数据治理 → 文件列表」准备做文件同步时，页面顶部弹出红色错误，
「数据治理概览」七个卡片**整片显示 `--`**。

### 8.16.2 取证：500 的来源与根因

后端日志 `temp/logs/backend_main.log`（14:11:27 / 14:11:32 / 14:11:38 / 14:12:32 四次）：

```
[未处理异常] GET /api/data-sync/governance/stats - 错误类型: IllegalStateChangeError,
错误消息: Method 'close()' can't be called here; method 'commit()' is already in progress
and this would cause an unexpected state change to <SessionTransactionState.CLOSED: 5>
```

traceback 精确到 `backend/models/database.py:455 in get_async_db → await session.close()`：
**请求结束时关会话，撞上了一个还在进行中的 `commit()`。**

根因在 `backend/domains/data_platform/routers/data_sync.py`：

```python
data_sync_service = DataSyncService(db)          # ← 拿的是**请求级**会话
readiness_list = await asyncio.gather(*[          # ← N 个协程并发
    data_sync_service.get_file_sync_readiness(   # ← 每个协程都碰同一个 session
        file_record.id, use_template_header_row=True,
    )
    for file_record in pending_files
])
```

`AsyncSession` **不是并发安全的**（SQLAlchemy 明令禁止同一 session 被多协程同时用）。
一个协程在 `commit()` 时另一个在 `execute()` / `close()` → 竞态 → 整个接口 500。

**触发条件**：pending 文件数 ≥ 2 才会真的并发。
之前 `pending_count = 0` → `gather` 空转 → 从不触发；
2026-10-26 14:11:13 采集注册了 3006/3007/3008 三个 pending 文件 → **第一次触发**。

复现（把三个 `get_file_sync_readiness` 放同一个 session 并发跑）立刻抛：

```
sqlalchemy.exc.InvalidRequestError: Method 'execute()' can't be called here;
method 'commit()' is already in progress
```

—— 与线上的 `close()` 撞 `commit()` 是同一个竞态的两副面孔。

### 8.16.3 为什么「同步」按钮像是坏了

- `POST /api/data-sync/single`（真正建同步任务的那个接口）**实测 200 正常**
  （ASGI 全栈复现 3006/3007/3008 三个文件都返回 200 并建出任务）
- 页面上的红色错误来自**概览接口** `GET /api/data-sync/governance/stats` 500
- 概览一挂，前端 `governanceStatsActionDisabled` 变 true → **「同步全部可同步文件」按钮被禁用**
  → 想点的那一下点不动，人自然以为「同步」坏了

### 8.16.4 修复：不是打补丁，是「这类错误不能再犯」

Walter 的要求：**「不能修好一次，后续还会发生此类错误」**。所以做了三层：

**① 本处修复**（与仓库既有惯例一致 —— `data_sync.py:1651` 早就有
「每个协程使用独立的数据库会话，避免并发冲突」的写法）

```python
async def _readiness_with_own_session(file_id: int) -> dict:
    session_factory = AsyncSessionLocal
    async with session_factory() as own_db:
        return await DataSyncService(own_db).get_file_sync_readiness(...)
```

`gather` 的实参里不再出现任何请求级会话 → 竞态消失，并发度也保住了。

**② 静态守卫**（新）：`scripts/check_async_session_concurrency.py`

AST 规则，扫 `backend/` `modules/` `scripts/`：

- 识别**请求级会话变量**（形参注解是 `AsyncSession` / 默认值含 `get_async_db` / 名字像 db·session）
- 识别**间接持有**（`X = SomeService(db)` → X 持有该会话）
- 在 `asyncio.gather` / `asyncio.create_task` / `asyncio.ensure_future`
  的实参里引用到它们 → 报错
- `AsyncSessionLocal()` 属于**独立会话** → 豁免
- 只认 `asyncio.xxx(...)` 属性形式 → 不会把业务里同名的 `create_task` 误判

已挂进 `scripts/run_lint.py`（仓库唯一的 lint 入口）→ **CI 自动拦**。

对照实验：把修复退回共享 session 写法 → 守卫立刻报出
`[gather] 间接持有请求级会话的变量 'data_sync_service' 被并发调用 gather() 使用`。

**③ 运行期巡检**（新）：`scripts/check_backend_session_race.py`

静态守卫看不穿跨模块传递、藏在方法内部的共享 session、第三方封装。
这一层从后端日志里捞 SQLAlchemy 的会话并发异常特征：

```
IllegalStateChangeError / InvalidRequestError
  + "Method 'xxx()' can't be called here"
  + "is already in progress"
```

只统计**带时间戳的事件行**（一次事故在日志里是几十行 traceback，只能算一次）。
实测：把今天 14:11~14:12 那次事故捞出来 = 4 次（两个日志文件各 4 条），
接口名、时间全对得上。

**④ 两道守卫自己都有测试**：`backend/tests/test_async_session_concurrency_guard.py`
（6 项：能抓到共享写法、不误报独立会话、不误报同名业务函数、巡检按事件计数不按 traceback 行数…）

### 8.16.5 全仓审计结果

修完之后跑静态守卫：**全仓 0 处**。
另有两处 `asyncio.gather` 人工审过，确认安全：

| 位置 | 为什么安全 |
|---|---|
| `backend/tasks/data_sync_tasks.py:282` | 每个协程自己 `AsyncSessionLocal()` 并在 `finally` 里 close |
| `backend/domains/business/routers/dashboard_api_postgresql.py:612` | 看板 service 是无参单例，方法内部自开会话，不碰请求级会话 |

### 8.16.6 顺带发现（未修，另记）

- `GET /api/data-sync/files` 慢到 **15.6 秒**（3.25 MB 的 xls 每次都全量解析 + 比对表头，
  日志里刷屏 `[HeaderChange] 匹配率 0.0%`）→ 读文件这种 CPU/IO 活儿放在 async 里阻塞事件循环
- 8 个文件卡在 `status='processing'`（2025-09-14 的 purchase 旧文件，
  错误信息「自动入库任务超时，已回退等待重试」）

## 8.17 这次采集其实**已经自动入库完成**了（Walter 不需要手动同步）

§8.16 那个 500 查完之后，顺着时间线倒推，发现完整顺序是这样：

| 时刻 | 发生了什么 |
|---|---|
| 14:07:37 | 任务 645 开始采集（库存 + 订单：shopee / tiktok） |
| 14:11:13 | 三个文件注册进 `catalog_files`（状态 = pending） |
| 14:11:21 | 采集完成，共 3 个文件 |
| **14:11:27 / 14:11:32 / 14:11:38 / 14:12:32** | Walter 打开文件列表页 → `governance/stats` 500 ×4（pending ≥2 → gather 并发 → 竞态） |
| **14:15:02** | **后台 auto_ingest 定时任务**（每 15 分钟一次）开始处理这三个 pending 文件 |
| 14:15:04 ~ 14:15:19 | 三个文件**全部自动入库**完成 |
| 14:15:04 / 14:15:15 | 刷新队列 1192 / 1193 两条任务 **completed** |

→ **Walter 看到的那个「内部服务错误」，是旁边那块概览塌了，不是同步失败；
   而同步在他报错之前/同时，已经由后台任务自动做完了。**

### 8.17.1 入库结果

| 文件 | 数据域 | 业务事实表 | 入库行数 |
|---|---|---|---|
| 3006 `miaoshou_inventory_snapshot_20261026_141113.xls`（3.25 MB） | inventory | `b_class.fact_miaoshou_inventory_snapshot` | **387 行** |
| 3007 `shopee_orders_monthly_20261026_141113.xls`（1.05 MB） | orders:shopee | `b_class.fact_shopee_orders_monthly` | **1920 行** |
| 3008 `tiktok_orders_monthly_20261026_141113.xls`（290 KB） | orders:tiktok | `b_class.fact_tiktok_orders_monthly` | **333 行** |

三个文件的模板匹配结论（`get_file_sync_readiness` 实调）：

| file_id | template_status | exact_match | semantic_match | should_auto_sync |
|---|---|---|---|---|
| 3006 | `ready` | ✅ | ✅ | ✅ |
| 3007 | `alias_only`（别名漂移，非阻断） | ❌ | ❌ | ✅ |
| 3008 | `ready` | ✅ | ✅ | ✅ |

→ 三个都**能自动同步**，没有需要人工确认表头的阻塞项。

### 8.17.2 状态层与库龄层也跟着推进了

- `mart.inventory_state`：仍是 1230 行，其中 **387 行来自 file 3006**（upsert 生效，
  2400 行没变、387 行被更新 —— 同一批 SKU×仓 覆盖写）
- **`max(row_seen_at)`：2026-10-26 05:32:39 → 06:15:04+00**（= 14:15:04 本地）
  → **水位线又往前推了一格**
- **`max(stock_added_at)`：2026-10-14 04:00:13 → 2026-10-26 04:47:29+00**
  → **有行被判定为「进货」，计时器按定义清零并重置**
- `mart.inventory_age_current`：这次带来 309 行
  → **44 行 `stock_increase`（清零重算）+ 213 行 `continued`（继续累加）**
  → age_days 落在 0~30

> ⚠️ 口径提醒：状态层判「进货」用的是**库存总量**（`on_hand_stock`），
> 不是可用库存 —— 订单占用/取消订单只动可用库存不动总量，
> 用可用库存会把这类变动误判成进货。

## 8.18 往深一层挖：500 的真正触发链是「接口慢 → 客户端超时 → 请求被取消」

§8.16 定位到「并发共享会话」，但用它做对照实验时**复现不出 500**（同一场景修复前后都 200）。
继续往下挖，发现 §8.16 只抓到了**竞态的形态**，没抓到**触发它的原因**。

### 8.18.1 会话收尾的写法本身就是雷

`backend/models/database.py` 的 `get_async_db`：

```python
try:
    yield session
    await session.commit()   # ← 自动提交
except Exception:
    await session.rollback()
    raise
finally:
    await session.close()    # ← 紧接着就关
```

`close()` 会撞上「**还在进行中的** `commit()`」→
`IllegalStateChangeError: Method 'close()' can't be called here; method 'commit()' is already in progress`

**什么时候 commit 会「还在进行中」？** 客户端超时断开 → FastAPI 取消该请求 →
`await session.commit()` 抛 `CancelledError`（它继承 `BaseException`，**不被** `except Exception` 捕获）
→ 直接跳到 `finally` → 此时 commit 的异步 IO 还没结束 → `close()` 撞上去。

### 8.18.2 那次请求为什么会被客户端超时取消

概览接口要算每个待同步文件的「就绪判定」，而就绪判定 =
**全量解析 xls + 逐列比对表头**。三个新文件里有一个 3.25 MB。

- 实测 `GET /api/data-sync/files` 最慢 **15.6 秒**（日志里刷屏 `[HeaderChange] 匹配率 0.0%`）
- 仓库里**本来就有**模板状态缓存（`_template_status_cache`，TTL 180 秒），
  但它**只接在 `list_files` 上**，概览接口走的 `get_file_sync_readiness` **完全没走缓存**
  → 每次刷新概览都要重新全量解析一遍

→ 完整触发链：

```
采集注册 3 个 pending 文件（含 3.25 MB 的）
  → 概览接口逐个全量解析 xls → 十几秒
  → 前端 axios 超时 → 断开
  → FastAPI 取消请求 → commit 被取消
  → 收尾 close() 撞上还在进行的 commit → IllegalStateChangeError
  → 500 → 页面概览整片变成 --，「同步全部可同步文件」按钮被禁用
```

§8.16 里「pending ≥2 才触发」只是**并发度**的门槛（pending=0 时 gather 空转），
真正的门槛是**接口耗时超过客户端超时**。

### 8.18.3 三层收口（每一层都能独立挡住这类事故）

| 层 | 位置 | 作用 |
|---|---|---|
| **① 消除竞态源** | `data_sync.py` 的 `asyncio.gather` 改用独立会话 | 并发协程不再共享请求级 session（§8.16） |
| **② 通用兜底** | `database.py` 的 `get_async_db` 收尾 | 关会话失败**只记日志不上抛** —— 收尾不该把一次本来正常的请求打成 500，**这一层挡住所有形态**（含未来未知的写法） |
| **③ 治本** | service 层就绪判定缓存 + 概览接口超时保护 | 让接口不再慢到超时：<br>· `DataSyncService.get_file_sync_readiness` 加 180 秒缓存（文件/状态/修改时间进键）<br>· 概览接口给就绪判定加 8 秒整体超时，超时按部分结果返回并打 `stats_stale`（前端已有这个提示位） |

**为什么第 ② 层最关键**：它不依赖「我们有没有写对」，而是**不让收尾异常改写请求结果**。
哪怕将来有人又写出一种会触发竞态的写法，最坏也只是日志里多一条告警，而不是页面白板。

### 8.18.4 每层都有对照实验

| 对照实验 | 结果 |
|---|---|
| 把 ① 退回共享 session | 静态守卫立刻报出；`test_governance_stats_async_api.py` 的会话独立断言变红 |
| 把 ② 的兜底删掉 | `test_async_db_session_teardown.py` 变红（1 failed） |
| 就绪判定加缓存 | 同一批文件的第二次概览不再重新解析大文件 |

### 8.18.5 顺带记下：数据库会话的两条通用规矩

1. **收尾异常不上抛**（`get_async_db`）—— 收尾失败只说明「连接可能没干净归还」
2. **并发上下文里不共享请求级会话**（`asyncio.gather` / `create_task`）——
   每个协程自己开一个，或干脆把重活挪出 async（读文件用 `run_in_executor`）

第 2 条现在有机器守卫（§8.16 的静态守卫，已挂进 `scripts/run_lint.py`），
第 1 条有单测守着（`backend/tests/test_async_db_session_teardown.py`）。

## 8.19 「上次进货时间」收到一个实现：口径统一（含真实数据对照）

§8.15 记下了一个事实：库龄层与状态层对「距上次进货天数」给出**两个答案**
（库龄层 17~30 天、状态层 655~656 天，458 行 0 行一致）。
而档位 / 折扣率 / 最低售价 / 积压这四条业务线读的是**状态层那个**。

### 8.19.1 根因不是算法，是两处细节

| | 起算点 | 信号字段 |
|---|---|---|
| 库龄层 | 读**全部历史快照**逐帧比 → 准 | **可用库存** → 取消订单会把它推高 → **假进货** |
| 状态层 | 只跟**自己入库后**的上一批比 → 第一次见某 SKU 没有上一笔可比 → 只能拿妙手「商品创建时间」凑 → **那是上架时间，不是进货时间** | **库存总量** → 对 |

### 8.19.2 收口：一个实现，两个调用点

新增 `backend/services/data_pipeline/inventory_restock_timeline.py`：

- `compute_restock_transition(...)` —— **判定内核**（唯一一份）：
  库存清零不活跃 / 首次出现起算 / 从 0 变正重新起算 / 总量增加=进货清零 / 减少或不变沿用
- `replay_restock_timeline(rows)` —— **仓级逐帧回放**（读行级快照事实）
- `aggregate_sku_timeline(timelines)` —— SKU 级「各仓取最长」
  （滞销链 SQL 里那段聚合的**可执行定义**，用测试锁住，防止两边漂移）

两个层都调它：

| 层 | 粒度 | 取值 | 谁在用 |
|---|---|---|---|
| 状态层 `mart.inventory_state.stock_added_at` | SKU×仓 | 回放锚点 | 滞销 / 档位 / 折扣 / 最低售价 / 积压 |
| 库龄层 `mart.inventory_age_current.age_anchor_date` | SKU | 回放锚点（总量口径） | 库龄看板 / 库龄清单 / SPU 运营 |

> 粒度不同**不是重复**：滞销/定价看 SKU（全国一价），积压看仓。
> 重复的是「何时算进货」这个规则 —— 现在只有一份。

### 8.19.3 真实数据对照（只读回放，2026-10-26）

行级事实 2726 行 → 仓级 1230 个 → SKU 级 1122 个；有库存的 SKU 503 个。

| | 旧（状态层自己 upsert diff） | 新（快照回放） |
|---|---|---|
| 两边都有数的 SKU | 498 个 | 498 个 |
| **完全一致** | — | **0 个** |
| 差值 | — | 最小 25 天 / 最大 630 天 / **平均 460 天** |

档位分布（只看有库存的 SKU）：

| 档位 | 旧 | 新 | 折扣率 |
|---|---|---|---|
| 日常 | 1 | **498** | 0.10 |
| 滞销30天 | 6 | 0 | 0.15 |
| 滞销60天 | 0 | 0 | 0.20 |
| 滞销60天以上 | **491** | 0 | 0.30 |

抽样：`A-00002-BLACK` 655 → 25 天；`A-00001-Army green` 656 → 42 天。

### 8.19.4 落库：必须**全量**校正

增量刷新只处理「水位线之后的行」（48 行），存量 1182 行的 `stock_added_at` 仍是旧口径
→ 会变成**一半新一半旧**的撕裂状态。所以两层都跑了一次 `force_full=True`：

- 状态层：`incoming_row_count=2726, state_key_count=1230, stock_changed_count=0`
- 库龄层：`mode=full, replayed_key_count=1122`

### 8.19.5 校正后：锚点统一了，剩 0.4% 的边缘差异

**比「锚点」（上次进货日）而不是「天数」** —— 天数差会被基准日搅乱：

| 指标 | 结果 |
|---|---|
| 共同 SKU | 498 个 |
| **锚点完全一致** | **496 个** |
| 锚点不一致 | **2 个**（`HKR-2260-pink-035` / `HKR-2260-white-035`，差 13 天） |

那 2 个来自 SKU 级汇总方式的细微差别（各仓取最早 vs SKU 总量序列），
影响面 **0.4%**。

> ⚠️ 两层的**天数**仍然会差一截，但那是**基准日不同**，不是两套算法：
> 库龄看板的 `age_days` 是「**截至上次盘点**压了多久」（逐帧历史），
> 状态层 / 滞销链的 `days_since_restock` 是「**截至今天**压了多久」（现在值）。
> 两个不同的问题，锚点才是唯一的真相源。

### 8.19.6 口径修正后的业务分布（存量数据，只记机制）

| 视图 | 结果 |
|---|---|
| 状态层（503 个有库存 SKU） | 全部 1~59 天，**无一个 ≥60 天** |
| 滞销视图 `api.sku_clearance_ranking_module` | 503 个 SKU，25~55 天 |
| 积压视图 `mart.inventory_backlog_base` | 506 行，货值 ¥225,567.78，25~55 天 |
| 库龄看板摘要 `api.inventory_age_summary_module` | 516 SKU / 11,006 件 / ¥223,287.47（全部 0-30 桶） |
| 滞销清单（筛 ≥60 天） | **0 条** |

档位分布从「≥120 天 491 个 / 日常 1 个」变成「**日常 503 个**」——
即这批货不再按滞销档打 0.3 折。

> ⚠️ 这批是**存量**数据，按 2026-10-26 的规矩不用于论证商业影响；
> 这里只记录**机制**：两个层曾经对同一件事给出两个答案，而业务读的是错的那个。

### 8.19.7 对照实验

- 把状态层的 `stock_added_at` 退回「自己 upsert diff」→ 又变回 655~656 天
- 共享模块 7 项单测覆盖：首次起算 / 进货清零 / 销售不重置 /
  **取消订单（只有可用库存涨）不算进货** / 各仓取最早 / 空仓不计入仓数 / 帧序

## 8.20 死锁的两道对策（治本 + 兜底），以及「多人同时用商品中心」的并发结论

§8.15.6 查清了死锁机制（两个刷新进程沿视图链 ABBA）。这一节落地修法，
并把 Walter 关心的「多人同时用商品中心」做了实测。

### 8.20.1 并发实测结论（2026-10-26）

| 场景 | 结论 | 实测 |
|---|---|---|
| 多人同时**看**看板 | 安全 | 读视图拿 ACCESS SHARE，彼此兼容 |
| 多人同时**改不同 SKU** | 安全 | 写落在表上，行级锁只锁那几行 → 不同行天然并行。两个事务各 **0.003 / 0.005 秒**完成 |
| 多人同时**改同一个 SKU** | 安全（排队） | 后写的等先写的提交；真正的死锁要「甲按 A→B 改、乙按 B→A 改」才发生 |
| **刷新进程重建视图时，商品中心保存** | **被挡住** | 持有 ACCESS EXCLUSIVE 时 UPDATE **3 秒未完成** |

→ **风险不在「视图是普通视图」，在「每次数据刷新都重建视图」这个多余动作。**
ACCESS EXCLUSIVE 期间**写和读都被挡**（看板转圈、商品中心保存卡住）。

### 8.20.2 对策一（治本）：数据刷新不再重建普通视图

普通视图的数据是**查询时实时算**的 → 数据刷新时根本没有东西可刷。
而 `CREATE OR REPLACE VIEW` 要拿 ACCESS EXCLUSIVE 排他锁 → 挡住所有并发读写，
两个刷新进程还会沿视图链 ABBA 死锁。

改动（`backend/services/data_pipeline/refresh_runner.py`）：

- `execute_sql_target` / `execute_refresh_plan` 新增 `recreate_views: bool = False`
- 目标**是普通视图且已存在** → **跳过**（记 step log `status=skipped`，
  `reason=view_not_recreated_on_data_refresh`）
- 目标**不存在** → 仍然创建（否则下游查询直接失败）
- 目标**是物化视图** → 仍然重建（它的数据是物理存的，刷新就是刷数据）

**代价与配套**：改了 `sql/` 里的视图定义不再自动生效 →
新增 `scripts/rebuild_views.py` 作为显式重建入口：

```
python scripts/rebuild_views.py                  # 重建全部视图（当前 47 个）
python scripts/rebuild_views.py --target mart.inventory_state
python scripts/rebuild_views.py --dry-run
```

它**单进程串行**执行（不会并发），按依赖顺序重建，重建期间会短暂挡住看板查询。

### 8.20.3 对策二（兜底）：死锁当「可重试」，不当「失败」

死锁不代表数据有问题，只代表「这次没抢到，重来」。

改动（`backend/tasks/refresh_queue_tasks.py`）：

- `_is_retryable_lock_error(exc)`：识别 PostgreSQL 死锁（sqlstate `40P01`）
  与序列化失败（`40001`）
- `_run_plan_with_lock_retry`：在**整个刷新计划的外层**重试：
  捕获 → **`await db.rollback()`（回滚整个事务）** → 退避（2s × 次数）→ 重开事务重跑
  最多 3 次

**为什么必须放在外层**：死锁是**事务级**失败，PostgreSQL 把事务标记 aborted 后
SAVEPOINT（`db.begin_nested()`）回滚无效 —— 语句级的重试救不回来。
这也解释了为什么改动前的死锁**必然**把任务打成 failed。

### 8.20.4 两道对策都有测试守着

新增 `backend/tests/data_pipeline/test_refresh_view_skip_and_lock_retry.py`（9 项）：
普通视图被跳过 / 物化视图仍重建 / 不存在的视图仍创建 / 显式重建强制重建 /
死锁可重试 / 序列化失败可重试 / 普通错误不可重试 /
**死锁 → 回滚整个事务 → 退避 → 重跑整个计划** / 普通错误不重试。

对照实验：
- 撤掉「跳过普通视图」的判断 → `test_data_refresh_skips_rebuilding_existing_plain_view` 变红
- 撤掉「死锁重试」的判断 → `test_deadlock_rolls_back_whole_transaction_and_retries` 变红

### 8.20.5 回归

- data_pipeline + refresh_queue 全量：**26 failed / 500 passed**
- 失败清单与基线**逐条一致**（stash 掉改动重跑后比对）→ **零回归**
- ruff / 长度门禁通过

## 8.21 真机验证通过（2026-10-26 19:5x）

Walter 在**真机**上验证通过，本轮工作收尾。状态快照：

| 项 | 状态 |
|---|---|
| 后端进程 | 18:37:12 重启（真机验证跑的就是新代码） |
| celery worker / beat / postgres / redis | 全部 healthy |
| git | local / origin/main / cnb/main **三处同 commit**，工作区干净 |
| 本轮提交 | `bb60c7ab` `c8342006` `f8088dd8` `d7d2a55c` `f4b189f1` `2420b60b` `3cb9a727` `ad5b7302` `d9ecb65a` |

### 8.21.1 本轮做完了什么（按业务链路）

| 环节 | 之前 | 现在 |
|---|---|---|
| 妙手采集的维度切换 | 点到了表格表头，维度没切 | 限定范围定位，维度切得准 |
| 妙手采集的区间 | Escape 收面板把区间回滚掉（增量悄悄变全量） | Tab 收面板，区间生效并有落地证据 |
| 采集产物 | — | 48 行（对比全量 1113 行）→ 区间真实生效 |
| 状态层水位线 | 建层时缺历史 → 天数错 | 快照回放给锚点 → 水位线逐轮推进 |
| 「距上次进货天数」 | 两套实现差 19~656 天，档位读错的那套 | 收到一个实现，锚点 496/498 一致 |
| 文件列表页 500 | 并发共享会话 + 客户端超时 | 三层收口 + 两道自动化守卫 |
| 刷新队列死锁 | 任务标红 | 治本（不重建视图）+ 兜底（死锁自动重试） |

### 8.21.2 留给下一轮的三件事

1. **档位/滞销/积压的输出变了**（491 个 SKU 从「≥120 天」落回「日常」）——
   这是口径修正的必然结果，但**存量数据按 2026-10-26 的规矩不用于论证商业影响**，
   真要用它做决策，得先补一轮新的采集数据。
2. **刷新队列并发仍是 4**（celery `--concurrency=4`）——
   本次靠「不重建视图」消除了环，但若将来又要重建视图，仍需考虑
   「刷新并发降为 1」或 advisory lock（§8.20.3 的第三层）。
3. **视图定义变更要显式重建**：`python scripts/rebuild_views.py`
   （这是本次引入的新规矩）。

### 8.21.3 订单域的性能债（本次未动）

| 对象 | 耗时 |
|---|---|
| `semantic.fact_orders_atomic` | 23.6 秒 |
| `api.clearance_ranking_module` | > 2 分钟（statement_timeout） |

→ 属订单域，跟库存域无关；库存域相关对象都在 **0.1 秒**级。
要优化的话，方向是给这两者做物化视图或改写查询，**不是**改库存链。
