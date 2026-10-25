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
| 把窗口计算接进采集执行链 | 见 §8.11.4：需要先定「运营怎么表达『这次要用水位线窗口』」——这是**运营可见的产品决策**，不擅自改 |
| B1 真实页面复验 | 需要真实妙手环境（Walter 自己跑） |
| B5 零库存宽限期（下架探测） | Walter 的需求描述里没有下架检测；属「商品中心自动化待拍板」那批 |

#### 8.11.4 接进采集执行链：三个方案（**待 Walter 拍板**）

现状：`MiaoshouInventoryExport` 从 `ctx.config["inventory_incremental_range"]` 读增量区间，
**没配就整段跳过**（全量采集行为不变）。所以只差「谁把这个键算出来放进任务参数」。

算窗口需要 DB（读状态层水位线），而采集链的 `normalize_time_selection` /
`build_date_range_from_time_selection` 都是**纯函数**（`backend/services/collection_time_window.py`），
策略注册表 `DYNAMIC_STRATEGY_TO_GRANULARITY` 是**封闭集合**、且策略语义与平台无关
（orders / products / inventory 共用）。把「库存水位线」塞进那个注册表会污染所有数据域 → 不做。

| 方案 | 做法 | 代价 | 需要动的地方 |
|---|---|---|---|
| **A（建议）** | `core.collection_configs` 加一个**开关字段**（如 `incremental_enabled`），只对 `platform=miaoshou` + `data_domains 含 inventory` 生效 | 一次迁移 + 模型/API/前端多一个开关 | 新迁移 + `schema_parts/collection.py` + 配置 API/前端 + 执行器在建任务时算窗口 |
| B | `date_range_type` 加一个新值（如 `auto_inventory`） | 要把新值塞进 `TIME_PRESET_TO_GRANULARITY` 等封闭映射里，且与「粒度」语义混在一起 | `collection_time_window.py` 的映射表 + 配置页下拉 + 执行器 |
| C | 不做开关：**每次都算窗口**，配置里的日期区间只在「运营显式指定 custom」时优先 | 零配置成本，但运营失去「这次要采全量」的控制权 | 只改执行器 |

> 三个方案都**只改库存域**：其它数据域的采集行为一律不变。
> 不管选哪个，都**不能**把水位线策略塞进通用策略注册表（PRE_LAUNCH_RULES：禁止新增重复实现）。
