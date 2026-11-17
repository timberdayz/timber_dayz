# 商品中心全面优化 · 五批次实施计划（2026-11-16）

> 状态：**实施中** | 批次 1 已完成，批次 2–5 待做
> 决策：2026-11-16 用户批准「完成所有批次 → 验收 → 新版本推送与部署」
> 口径真源：`docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md` §2.4（2026-11-16 口径归一修订）
> 工作日志：仓库根 `task_plan.md` / `progress.md`（gitignored，不入库）

---

## 0. 业务侧最终形态（一句话版）

运营在商品中心填的**测算售价**就是折后到手价，系统按这个数算收入；每一件发出去的货都要
算**尾程配送费**；目标 ROI 填错（超平台上限、留空）会被当场拦下来；SKU 重量必须给。

```
商家实收 revenue = 测算售价
广告前利润 = revenue − (采购 + 头程 + 仓储 + 贴单 + 尾程 + 平台佣金 + 达人佣金 + 货损 + 退货)
广告费 = revenue ÷ 目标ROI（目标ROI 未填 ⇒ 不可算，不是 0）
投放后利润 = 广告前利润 − 广告费
保本ROI = revenue ÷ 广告前利润
建议ROI = min(round(round(保本ROI) × 1.2, 2), 平台可填上限)
成本底线 = (采购成本 + 尾程配送费) ÷ D
D = 1 − other_cost_rate_ex_shipping − 达人佣金率 − 货损率 − 退货率 − 目标利润率
最低售价 = max(成本底线, 纪律线)，人工覆盖优先
```

## 1. 批次顺序（硬约束：护栏必须先于尾程进底线）

| 批次 | 主题 | 内容 | 验收口径 |
|---|---|---|---|
| 1 | 口径归一 | 删优惠券列；`revenue = 测算售价` | 前后端链路零 `seller_coupon_amount`；利润 = 售价 − 全部成本 |
| 2 | ROI 护栏 | P1 超上限拦截 / P2 空目标ROI 不静默换口径 / P3 无档案广告费不恒 0 / P5 达人佣金缺失进缺失清单 / P6 三色判定带归因警示 | 6 条守护测试由红转绿 |
| 3 | 尾程只读 | 建 `finance.delivery_rate_rules` + 纯函数模块 + 费率端点 + 前端只读展示；重量必填 + 表头改黑 | 迁移可升可降；纯函数无 ORM 无 DB |
| 4 | 尾程进底线 | 尾程进 `(采购+尾程)÷D`；拆 `other_cost_rate` 运费；仓维度统一 4 处 | 底线含尾程；无重复扣运费 |
| 5 | 收口遗留 | 老链路 revenue / 第三份实现 / 完整度值域统一 / `last_mile_cost` 标签改名 | 无重复实现；口径一致 |
| 6 | 验收 + 发布 | 测试 + 守护 + 门禁 + tag 推送 | 全绿 + 生产 `/healthz/ready` 版本号 == tag |

> ⚠️ **硬顺序**：尾程进底线会使保本 ROI 从 2.19 → 3.91（+79%）。若护栏未修，
> 运营填超上限目标 ROI（TikTok 上限 20）会让广告费 ≈ 0、利润虚高 ⇒ 尾程的钱从广告费口子漏出。
> 所以**批次 2 必须先于批次 4 落地**。

---

## 2. 批次 1 · 口径归一（已完成 2026-11-16）

**业务问题**：运营填的「测算售价」是折后到手价，系统却按"标价"再扣一次卖家券当商家实收
⇒ 收入少算 ⇒ ROI 偏乐观、平台佣金少扣；且老口径的最低售价底线里根本没扣券 ⇒
「底线承诺的价」与「利润试算用的价」不是同一个数。

**改动清单**

| 文件 | 动作 |
|---|---|
| `backend/services/product_profit_service.py` | `build_platform_profit_preview` / `build_baseline_profit` 删除券参数；`revenue = 售价` |
| `backend/schemas/product_center.py` | 删除 `seller_coupon_amount` / `default_coupon_amount` / `coupon_amount`（请求 + 响应） |
| `backend/domains/business/routers/product_center.py` | 删读取 / 传参 / 回带 / 批量保存白名单；利润版本 `coupon_amount=None` |
| `backend/services/product_finance_service.py` | 删券读写；`selling_price = preview["net_revenue"]` |
| `backend/services/product_target_roi_backfill_service.py` | 删传参 |
| `backend/services/feishu_projection_service.py` | 列「优惠券」→「商家实收」，值取测算售价 |
| `backend/services/product_roi_service.py` | docstring 口径同步 |
| `frontend/src/domains/business/views/ProductCenter.vue` | 删优惠券列 / tooltip / 预填 / 提交 |
| `backend/tests/test_product_revenue_caliber.py` | **新增守护测试**（11 条） |

**数据库**：遗留列 `seller_coupon_amount` / `default_coupon_amount` / `coupon_amount`
保留（不动历史利润版本数据），但商品中心链路**不再读写**。

**验收**：新守护测试 11 条绿；受影响既有测试 25 条已按新口径改断言并全绿。

---

## 3. 批次 2 · ROI 与广告费护栏

| 编号 | 问题 | 位置 | 目标行为 |
|---|---|---|---|
| P1 | 超平台可填上限无校验 | `product_center.py:_evaluate_roi_guard` | `target_roi > platform.target_roi_ceiling` ⇒ **拦截**，不静默接受 |
| P2 | 清空目标ROI 静默换口径 | `product_profit_service.py:_ad_cost_and_profit` | 目标 ROI 为空 ⇒ 广告费**不可算**（None），**不回落** `expected_ad_rate` |
| P3 | 无经营档案时广告费恒为 0 | `product_center.py` 候选列表 | 缺档案 ⇒ 不可算 + 进缺失清单，不按 0 |
| P5 | 达人佣金缺失未进缺失清单 | `product_center.py` 候选列表 | 缺失时进 `missing_reasons` 并标 `creator_commission_source` |
| P6 | 三色判定无归因警示 | `ProductCenter.vue:roiVerdict` | 三色判定旁显示「平台报告 ROI 含自然/达人归因」警示 |

**P2 与 P3 的关系**：P2 是"目标 ROI 留空"，P3 是"整个经营档案都没有"。两者都导致
**广告费不可算**，但归因不同（P2 = 运营还没填；P3 = 档案缺失），缺失清单要分开标。

---

## 4. 批次 3/4 · 尾程配送费

**业务概念**：采购 → 头程 → 仓储贴单 → **尾程**。头程是已付库存成本（一次），尾程是
**每卖一件必付**。包邮 = 尾程由商家承担 = 按件成本。特快由买家付 ⇒ 不进成本。

**新表**：`finance.delivery_rate_rules`
列：`rule_id / platform_code / warehouse_code / min_weight_kg / max_weight_kg / unit_price /
currency / effective_from / effective_to / status / source / version / notes`
当期唯一：`(platform_code, warehouse_code, min_weight_kg) WHERE status='active' AND effective_to IS NULL`
**刻意不建任何外键**（`core.dim_platforms` / `core.dim_warehouses` 会被同步
`TRUNCATE ... CASCADE` ⇒ 建了外键会把费率规则一起删掉，静默失效）。
重量段区间是**左闭右开** `[min, max)`：`max_weight_kg IS NULL` = 往上不封顶；
相邻两档不重叠，边界归下一档。

**纯函数模块**：`backend/services/product_delivery_cost_service.py`
`match_delivery_tiers` / `select_delivery_tier` / `compute_delivery_cost` —— 无 ORM 无 DB。
三条硬规则：区间重叠 ⇒ **歧义不猜**（算不出来）；没配费率 ⇒ **不是 0**（尾程不免费）；
缺重量 ⇒ 保守估算（该仓最轻档 vs 同平台最贵仓的最轻档，取更贵的）+ `estimated=True`。

**取数层**：`ProductFinanceService.find_delivery_rate_tiers` / `find_delivery_cost`。

**端点**：`GET/POST/PATCH/DELETE /api/delivery-rate-rules`（同档位换价 = 旧行闭区间 +
新行今天起生效；重量段重叠 ⇒ 409）。

**批次 3 已落地**：表 + 迁移 + 纯函数 + 取数 + 端点 + 测算页「尾程配送费」**只读列**
（批次 4 才进利润与底线）+ 重量 kg 必填（表头去蓝 + 红星 + 保存校验）。
守护：`backend/tests/test_product_delivery_cost.py`（18 条，含真实 PG 上
upgrade → upgrade → downgrade → upgrade）。

**批次 4 落地**：尾程进广告前利润；尾程进成本底线 `(采购+尾程)÷D`；拆
`other_cost_rate` 里的运费；仓维度全线统一 4 处。

**批次 4 已落地（2026-11-16）**：

| 项 | 内容 |
|---|---|
| 尾程进利润 | `build_platform_profit_preview` 新增 `delivery_cost` 参数 ⇒ 扣进广告前利润。**尾程算不出来 ⇒ 利润算不出来**（不是按 0 计：尾程不免费，按 0 计等于凭空多一笔利润） |
| 尾程进底线 | `compute_cost_floor` 新增 `delivery_cost` + `delivery_cost_rate` ⇒ 分子加尾程、分母加回尾程占比 |
| 拆分基准 | 新增 `core.dim_platforms.delivery_cost_rate`（尾程占收入比）+ 迁移 `20261234_delivery_cost_rate_split` + 「定价设置」可维护 |
| 仓维度 | `/api/skus` 新增可选 `warehouse_code`；前端 SKU 资料页传当前仓 ⇒ 两页底线同口径 |
| 费率维护 UI | 「物流仓储管理」新增「尾程费率」tab（平台 × 仓 × 重量段 → 单件价，可增删改） |
| 守护 | `backend/tests/test_product_delivery_cost_floor.py`（13 条）+ 前端 4 条 |

### 批次 4 的关键判定：尾程**在** `other_cost_rate` 残差桶里（生产库实测）

`other_cost_rate` 是**恒等式反推的残差桶**：

```
other_cost_rate = 1 − 实测采购成本率 − 实测净利率 − 平均 SPU 退货损失率 − 平均 SPU 货损率 − 默认达人佣金率
```

「实测净利率」来自平台订单事实表的 `利润` 列，而平台的 `利润` **已经扣过运费**。
生产库 2026-11-16 只读实测（`b_class.fact_tiktok_orders_monthly` / `fact_shopee_orders_monthly`）：

- TikTok：`总费用 = −298,780.69`，其中 `|实际运费| 178,848.23 + |交易手续费| 27,557.05 + |达人佣金| 64,344.13 + |联盟佣金| 3,332.43 = 274,081.84`，
  残差 `24,698.85` 正好是平台佣金 ⇒ **`实际运费` 确实在「总费用」里** ⇒ 已从利润扣除 ⇒ 在残差桶内。
- Shopee：`卖家支付运费 = −1,121,042.21`（卖家从结算里扣的那笔）⇒ 同样在利润侧。

⇒ **尾程进底线的分子时，必须同时把残差里按收入摊的那份尾程剔出去，否则同一笔尾程扣两次。**

### 成对生效（钉死的硬规则）

```
分子 = 采购成本 + 尾程配送费
分母 = 1 − 平台其他成本率 + 尾程占收入比 − 达人佣金率 − 货损率 − 退货率 − 目标利润率
```

`delivery_cost` 与 `delivery_cost_rate` **必须同时有值**才生效：

| 情况 | 分子 | 分母 | 结果 |
|---|---|---|---|
| 两个都有 | +尾程 | +尾程占比 | 尾程进底线（不重复扣） |
| 只有尾程 | 不加 | 不加 | 尾程不进底线（缺 `missing_delivery_cost_rate_split`） |
| 只有占比 | 不加 | 不加 | 尾程不进底线（缺 `missing_delivery_cost`） |

少任何一半都**不进底线**（宁可不算，也不重复扣），并在 `min_selling_price_missing_reasons` 里点名缺了什么。

### 为什么 `delivery_cost_rate` **不预置种子值**

尾程占比的权威口径是「**我们自己的费率表**算出来的平台尾程均值 ÷ 平台平均售价」
（费率表是尾程的唯一真源，分子里的尾程也出自它 ⇒ 两边天然配对）。

而批次 3 刚建的 `finance.delivery_rate_rules` **目前没有任何费率数据**；
用平台订单事实表反推的运费占比又**混着头程**（平台的运费线 = 国内派送 + 国际头程），
拿它当尾程拆分会把头程也从残差里一并剔掉 ⇒ 底线偏低 ⇒ 危险。

⇒ **列先建好、语义定死、留空**：业务维护好尾程费率后，在「定价设置」里填这个平台级拆分比例，
尾程即进入成本底线。留空时**尾程不进成本底线**，界面上明确标「未计入底线」。

### 仓维度统一 4 处（批次 4 实际完成 2 处，另 2 处并入批次 5）

| # | 项 | 状态 |
|---|---|---|
| 1 | `list_skus` 加仓参数 | 批次 4：`warehouse_code` 可选参数；**不传仓就不取尾程档位**（不同仓的价不同，不能猜一个仓的价） |
| 2 | `ops.price_adjust_baselines` 主键加 `warehouse_code` | 并入批次 5（属调价通知链，需要改主键 + 迁移） |
| 3 | `price_adjust_notify_service` 按 (平台×仓) 循环、只对有库存的仓发 | 并入批次 5（同上） |
| 4 | 人工覆盖表 `sku_platform_pricing` **不下沉**到仓 | 批次 4 确认保持现状（人工覆盖是「SKU × 平台」的量；仓维度由底线口径承担） |

**已知缺口**：费率维护 UI 批次 4 已补（「物流仓储管理」→「尾程费率」tab）。

**已知缺口**：费率维护 UI 批次 4 已补（「物流仓储管理」→「尾程费率」tab）；其余两类规则
（物流服务商规则、仓储规则）在「物流仓储管理」tab 里有表格可维护。

---

## 5. 批次 5 · 收口遗留

- 老链路 `build_baseline_profit` / `preview_operating_profit` 的 revenue 口径统一（批次 1 已做大半）
- 第三份 profit 实现收口到一处
- `cost_completeness` 两套值域（`complete/partial/incomplete` vs `incomplete/estimated/mixed/actual`）统一
- `last_mile_cost` 标签改名：它是头程账单内的分段（港→仓），**不是买家快递**；UI 标签改「头程末端派送」，新概念叫「尾程配送费」

**批次 5 已落地（2026-11-16）**：

| 项 | 内容 |
|---|---|
| 老链路 revenue | 批次 1 已做完：`build_baseline_profit` 的 `revenue = 售价`，不再二次扣券；`preview_operating_profit` 走 `preview_profit` ⇒ 自动同口径 |
| 第三份 profit 实现 | 新增纯函数 `product_profit_service.build_profit_from_components`（收入 − 6 项成本 = 利润，利润率 = 利润 ÷ 收入）；`build_baseline_profit`（费率口径）与 `POST /api/product-profit-estimates`（金额口径）**都收口到它**，路由不再自己写一遍加减法 |
| 完整度值域 | **不用改代码**：`cost_completeness`（complete/partial/incomplete）与 `actual_recost_completeness`（incomplete/estimated/mixed/actual）是**两个独立列，各有 CHECK**（迁移 `20261114_add_sku_roi_columns.py`，约束名 `ck_sku_profit_estimate_cost_completeness` / `ck_sku_profit_estimate_actual_completeness`）。它们量的是两件不同的事，混进一列才是 bug |
| `last_mile_cost` 标签 | 物流账单明细页「尾程」→「**头程末端派送**」，并在表头写清它是头程账单内的分段（港→仓），与商品中心的新概念「尾程配送费」（仓→买家）区分开 |
| 调价通知仓维度 | 见下表 |

### 调价通知链下沉到仓维度（批次 5 落地）

底线拆到仓之后，通知链必须跟着走，否则 A 仓的底线变化会被记成所有仓的变化。

| 位置 | 改动 |
|---|---|
| `ops.price_adjust_baselines` 主键 | `(sku_id, platform_code)` → `(sku_id, platform_code, warehouse_code)`；迁移 `20261235_price_adjust_baseline_warehouse`，老行回填**空串** |
| `collect_pricing_states` | 键改 3 元组；按「平台 × **有库存的仓**」循环；每个仓用**自己的库龄**算档位；尾程按「平台 × 仓 × 重量段」算 |
| `load_baselines` / `detect_changes` / `advance_baselines` / `advance_baseline_for_sku` | 全部按 3 元组键读写 |
| 归因快照 | 新增 `warehouse_code` / `delivery_cost` / `delivery_cost_rate` |
| 飞书「调价记录表」 | 去重键带仓（`sku:platform:warehouse`）；payload 带仓；行里写进「备注」=「仓库：XXX」（表里没有「仓库」列 —— 那是外部 Base 的固定结构，不能擅自加列） |

**老基线自动失效，而且这是有意的**：老行 `warehouse_code = ''`，与任何真实仓都对不上 ⇒ 不会被拿来和新状态比较
⇒ **不会误报一批「底线变了」**。代价是上线后第一轮只重建基线、不通知 —— 安全的方向（宁可少报，不可错报）。

**仓维度数据整体缺失时**（状态层不可用 / 库存表为空）退回「SKU × 平台」口径（空串仓），
行为与批次 4 之前逐字一致 —— 宁可少一个维度，也不能什么都不通知。

### 顺手修掉的既有缺陷：通知去重闸把「第二次变化」吞掉了

去重闸原来只看 `business_key`（且把 `completed` 也算进「在途」）。同一个 SKU × 平台的底线会**反复变**
（今天涨、明天跌），于是第一次通知之后，这个键**永远**不会再通知 ⇒ 通知表退化成一次性快照，后续真实变化全被静默吞掉。

真正的「重复」是**同一次变化** —— 它的 payload 逐字相同 ⇒ 哈希相同。所以判据改成
**「去重键 + 载荷哈希」双因子**（`ops.feishu_projection_tasks` 的唯一约束本来就是
`uq_feishu_projection_task_payload (entity_type, business_key, payload_hash)`，闸与约束对齐）。

### 批次 4/5 引起的既有测试调整（不是改断言口径，是补输入）

「尾程算不出来 ⇒ 利润链算不出来」这条规则会让**所有**没传 `delivery_cost` 的
`build_platform_profit_preview` 调用返回 `None`。下面这些用例验的是**别的口径**
（广告费 / 贴单费 / 完整度 / ROI 分母），与尾程无关 ⇒ 显式给 `delivery_cost=0`（= 没有尾程）：

| 文件 | 调整 |
|---|---|
| `test_product_target_roi_backfill.py` | `_inputs()` 补 `delivery_cost=Decimal("0")` |
| `test_product_roi_guardrails_v2.py` / `test_product_revenue_caliber.py` | 同上（批次 4 已做） |
| `test_platform_sku_profit_workbench.py` | 9 处直接调用补 `delivery_cost` |
| `test_product_profit_calculator.py` / `test_sku_roi_guard.py` | `_preview` / `_preview_inputs` 补 `delivery_cost` |
| `test_product_roi_service.py` | 1 处直接调用补 `delivery_cost` |
| `test_sku_selling_price_tools.py` / `test_sku_operating_dimensions.py` | 假平台补 `delivery_cost_rate=None` 字段 |

仓维度引起的调整：

| 文件 | 调整 |
|---|---|
| `test_price_adjust_notification.py` | 2 元组键 → 3 元组键；SQLite fixture 补 `finance.delivery_rate_rules` |
| `test_sku_platform_pricing.py` | 状态/基线键改 3 元组；**历史迁移测试**按仓库既有范式「自己摆出迁移前的样子」（`_restore_pre_migration_baseline_shape`），因为隔离库已经是 head |
| `test_sku_platform_pricing_override.py` | 依赖上面那个测试把隔离库复原到 head |

---

## 6. 已知阻塞与软依赖

| 项 | 影响 | 处理 |
|---|---|---|
| 1125 个 SKU 权重 0% | 尾程进底线后大量降级为 `estimated` | 需业务补录重量（批次 3 把重量改必填 + 表头改黑，为补录做准备） |
| `VERSION` 文件 v7.28.0 vs 最新 tag v7.30.0 | 发布版本号 | 发布前核对真源，与 tag 同提交 bump |
| `alembic.ini` 指向只读历史链 | 迁移命令跑错链 | **既有问题，批次外记录**，不趁机改 |
| 飞书 SKU 镜像表列名「尾程单位成本 RMB」 | 它指的是**头程账单内**的末端派送分段，与商品中心新概念「尾程配送费」同名不同义 | **不动**（外部 Base 的固定列，改名会直接让投影写入失败）；只在 ERP 代码注释里写清区别 |

---

## 7. 发布

- 版本号：**v7.31.0**（VERSION 纯 7 字节 `v7.31.0`，与 tag 同提交）
- 推送方式：`git push origin vX.Y.Z`（GitHub SSH-443 触发部署；CNB 仅为镜像，tag 两镜像须同对象）
- 发布后独立 SSH 验证：`/healthz/ready` 与 `docker compose ps` 的版本号 == tag；`deploy-logs` 只多一个批次

### v7.31.0 发布记录（2026-11-16）

| 项 | 值 |
|---|---|
| tag 对象（双端同一对象） | `930d15eb`（annotated tag） |
| tag 指向的提交 | `37ea0484`（**VERSION 与 tag 同提交**） |
| 双镜像 main | GitHub SSH-443 与 CNB HTTPS **同为 `37ea0484`**（`git ls-remote` 核对） |
| 提交 | `c9e1dde4` 批次 4-5 代码 + 文档；`37ea0484` VERSION + CHANGELOG |
| 发版流水线 | **run `43933618944` = success**（check-config / 发布门禁 / 镜像构建推送 / 远端部署 全 success，22m59s，**恰好 1 个 run**） |
| main 的 CI 三线 | CI Pipeline ✓ / Validate Data Flow ✓ / Docker Build and Push ✓ |
| 生产容器 | backend-api / celery-worker / celery-beat / frontend **全部 v7.31.0** |
| 健康端点 | HTTP 200，`version=v7.31.0`，`database=connected`，`dashboard=ready` |
| 迁移版本 | `current_schema_alembic_version = current_schema_20261235_price_adjust_baseline_warehouse`（= 链头） |
| 新结构（只读核查） | `core.dim_platforms.delivery_cost_rate` 存在；`ops.price_adjust_baselines.warehouse_code` 存在且**主键已是** `(sku_id, platform_code, warehouse_code)` |
| 平台拆分基准 | tiktok / shopee 的 `delivery_cost_rate` 均为 **NULL**（刻意不预置种子）⇒ 尾程**不进底线** ⇒ 上线不会突然抬高底线 |
| 尾程费率表 | `finance.delivery_rate_rules` 行数 = 0（业务待录）⇒ 尾程算不出来 ⇒ 利润链显示不可算并点名原因，**不按 0 计** |
| 老基线 | 2238 行全部 `warehouse_code = ''` ⇒ **自动失效** ⇒ 上线后第一轮只重建基线、不通知（安全方向） |
| deploy-logs | 只多一个批次 `20261117_030730`（`rebuild_views` + `bootstrap_postgresql_dashboard` 一对） |

---

## 8. 上线后复核发现的既有缺陷：飞书「平台」单选字段（v7.31.1 补丁）

> 发现时间：2026-11-17 上午（v7.31.0 上线后的独立复核）。
> **不属于五个批次的范围** —— 它引入于 2026-11-07 的「底线下沉到 SKU × 平台」，
> v7.31.0 只是把它暴露出来。

### 8.1 症状与根因

| 项 | 实测 |
|---|---|
| 飞书「📠调价记录表」行数 | **174**（全部 2026-10-28 / 11-01 写的） |
| 失败任务 | **461 条** `price_adjust` 任务 100% failed，错误 `Feishu batch create failed: not_found: not_found` |
| 失败起点 | **2026-11-08**（`f51ceb46` 引入 `platform_code` 之后的第一轮） |
| 重试 | 无次数上限（退避封顶 1 小时）⇒ 每天约 461 条失败日志 |
| 权限 / 表结构 | **正常**（容器内用 ERP 应用凭据探测：`base/v3` 列表 `code=0`，19 个字段齐全） |

根因：`_price_adjust_payload` 把载荷里的**平台 code**（`tiktok`）直接写进飞书「平台」**单选**字段，
而该字段的选项名是 `TikTok` / `Shopee` / `Amazon` ⇒ 匹配不上 ⇒ base/v3 **整批拒绝**
（`not_found`），**一行写错拖垮整批 200 行**。

真表对照实验（临时表，验证完即删、零残留）：

| 写入的「平台」值 | 结果 |
|---|---|
| `tiktok` | `code 800030005 not_found`（被拒） |
| `TikTok` | `code 0`（成功） |

### 8.2 v7.31.1 改了什么

- `backend/services/feishu_projection_service.py`
  - 「平台」改写**飞书选项名**，选项名取自 `core.dim_platforms.name`（ORM 真源，不硬编码）；
  - 认不出选项名 ⇒ **不写这一格** + 告警（宁可空着，也不让整批被拒）；
  - 同族加固：「变动原因」「变动方向」也加选项白名单（ERP 侧是新增常量集合，
    飞书选项是手工维护的，两边不同步会重演同一故障）；
- `backend/tests/test_feishu_price_adjust_platform_option.py`（新增，9 个用例）
- `backend/tests/test_price_adjust_notification.py`：outbox SQLite fixture 补
  `core.dim_platforms`、载荷补 `platform_code`、假客户端记录实际行内容，
  并加一条端到端用例（投递出去的行「平台」= `TikTok`）；
- `scripts/abandon_stale_price_adjust_tasks.py`（新增，dry-run 默认 + `--apply`）：
  把 461 条旧任务标成 `abandoned`（**不删行**）——否则修好之后它们会被一次性重投，
  把 461 行旧口径记录倒进只增不改的飞书表。

### 8.3 为什么选择「作废」而不是「重投」

- 这些任务是 **11-08 ~ 11-15** 的旧口径：无仓维度（批次 4 之前）、
  去重键是老格式 `sku:platform`、基线也已按新口径重建；
- 飞书调价记录表**只增不改**，倒进去删不掉；
- 作废保留审计痕迹（载荷、投递日志、失败次数都在），新流程从干净基线重新开始。

### 8.4 v7.31.1 发布与部署验收（2026-11-17）

| 项 | 值 |
|---|---|
| tag 对象（双端同一对象） | `b04f2c07` |
| tag 指向的提交 | `48fa88ae`（VERSION 与 tag 同提交，VERSION 纯 7 字节 `v7.31.1`） |
| 双镜像 main | GitHub SSH-443 与 CNB HTTPS 同为 `48fa88ae` |
| 提交 | `5f4c10ac` 修复+测试+脚本；`48fa88ae` VERSION+CHANGELOG |
| 发版流水线 | run `44013238622` **attempt 2 = success**（attempt 1 卡在 CNB 镜像推送 34 分钟 ⇒ 取消后重跑；镜像内容不变，生产只部署 1 次） |
| main 的 CI 三线 | 全 success |
| 生产容器 | backend-api / celery-worker / celery-beat / frontend **全部 v7.31.1**、healthy |
| 公网 `healthz/ready` | HTTP 200，`version=v7.31.1`，`database=connected`，`dashboard=ready` |
| 迁移版本 | `current_schema_20261235_price_adjust_baseline_warehouse`（无新迁移） |
| 基线主键 / 行数 | `(sku_id, platform_code, warehouse_code)`；2238 空串仓 + 1022 仓维度 |
| 积压作废 | 461 条 `failed` → `abandoned`（dry-run 先确认命中范围），失败任务归零 |
| 飞书真实表 | 仍 174 行、`rev=281` 不变 ⇒ **没有往业务表写任何脏数据** |
| 生产代码真表写入 | 已部署代码 ⇒ `平台=TikTok` ⇒ 真实 `batch_create` 成功；临时表验证完即删，表数回到 12（零残留） |
| deploy-logs | 只多一个批次 `20261117_123908` |

> ⚠️ **教训（记给下一次发版）**：`Push backend image to CNB` 这一步**没有超时保护**，
> 挂住就是无限期挂住（本次 34 分钟无进展，上一版同一步 4 分 17 秒）。
> ⇒ 下次发版若该步超过 10 分钟无进展，直接 `gh run cancel` + `gh run rerun`（同 tag 同镜像），
> 不要干等。生产只应部署 1 次 —— 以 deploy-logs 的批次数为准。

---

## 9. 批次 6 · 重量段化 + 包邮开关（2026-11-17）

### 9.1 业务前提（两条用户拍板）

**① 承运商按「重量段」定价。** Shopee SG / TikTok SG 价目表都是「≤1kg / ≤5kg / ≤10kg …
一档价」，所以 SKU **不称重**，只报「落在哪一段」；承运商调价时**只改费率表那一行**
（平台 × 仓 × 重量段），不用回改每一个 SKU。

**② 跨境电商不是默认包邮，而是选择性包邮。** 同一个平台上，有的 listing 包邮、
有的不包邮 ⇒ 「包不包邮」是 **SKU × 平台** 的经营选择，与费率表（承运商报价）
**无关**：费率表回答「这一段运费多少钱」，包邮开关回答「这笔钱谁付」。

### 9.2 数据模型

| 变化 | 内容 |
|---|---|
| 新表 `core.dim_weight_tiers` | **全局一套**重量段：`tier_code` / `label` / `min_kg` / `max_kg` / `sort_order` / `status`。**不建外键**（会被同步 TRUNCATE CASCADE 连带清掉） |
| `core.dim_erp_sku` | **删** `weight_kg`；**加** `weight_tier_code` |
| `finance.delivery_rate_rules` | **删** `min_weight_kg` / `max_weight_kg`；**加** `weight_tier_code`；当期唯一索引改为 `(platform_code, warehouse_code, weight_tier_code)` |
| `finance.sku_platform_pricing` | **加** `free_shipping`（可空布尔：TRUE=包邮 / FALSE=明确不包邮 / NULL=未设置⇒按不包邮） |

标准档位（T01–T06）：`0-1 / 1-5 / 5-10 / 10-20 / 20-30 / 30 kg 以上`，
区间**左闭右开** `[min_kg, max_kg)`，`max_kg IS NULL` = 不封顶。

### 9.3 四条钉死的口径

1. **段定义全局一套。** 同一个 SKU 在不同平台卖的是**同一个包裹** —— 重量段是**货的属性**，
   不是渠道的属性。各平台各一套 ⇒ 运营维护 N 份段表 + 判断「TikTok 的 5kg 段」和
   「Shopee 的 5kg 段」是不是同一段 ⇒ 口径必然漂移。
2. **未选段 ⇒ 默认最轻段 + 标 estimated**（`missing_weight_tier`）。⚠️ 最轻段通常是最便宜的
   一档 ⇒ 这是**偏乐观**口径，界面必须提示「重货务必选段」。
3. **该段没配价 ≠ 尾程免费**（`missing_delivery_rate_for_tier`）：金额留空，
   绝不按 0（按 0 = 白送运费 = 利润虚高）。
4. **不包邮 ⇒ 尾程完全不适用**：不进底线分子、不进分母拆分、**不报**「缺尾程费率」、
   利润链尾程按 **0** 计（**不是**算不出来）。理由：不包邮的 SKU 压根不需要尾程费率，
   报缺是噪声，会把真缺料淹掉。

### 9.4 包邮开关怎么进计算链

```
包邮   ⇒ 尾程（费率表单件价）→ 成本底线分子
         ＋ 平台尾程占比 delivery_cost_rate → 成本底线分母（与分子**成对生效**）
         ＋ 利润链扣掉这笔尾程
不包邮 ⇒ 尾程 0：分子不加、分母不拆、利润链不扣、也不报缺费率
```

粒度 = **SKU × 平台**（与底线、人工覆盖同一粒度）：包邮是**渠道策略**，不是仓库属性 ⇒
同一平台的所有仓共用这一个决策。

### 9.5 仍然按重量计费的地方怎么办

SKU 的精确重量退役了，但**头程按重量计费**的规则（`billing_basis='weight'`）还在。
口径：**用重量段的代表重量 = 段上限**（不封顶段取下限）—— 宁高不低。
SKU **没选段** ⇒ 头程参考成本**算不出来**（报 `missing_sku_weight_tier`）：
不知道多重却按重量计费 = 凭空猜成本 ⇒ 宁可不算，也不要算错。
（生产 3 仓 + 6 条物流商规则**全部**按体积计费 ⇒ 这条分支当前不触发。）

### 9.6 迁移

| 迁移 | 内容 |
|---|---|
| `20261236_weight_tiers` | 建 `core.dim_weight_tiers` + 种 6 档；SKU 加段并**按老重量回填**；费率表加段并**按老重量下限回填**；删两处重量列；换当期唯一索引（建索引前先停用同段重复的当期行） |
| `20261237_free_shipping_flag` | `finance.sku_platform_pricing` 加 `free_shipping`（**不填种子值**：存量一律「未设置」⇒ 按不包邮） |

`core.dim_weight_tiers` 进 `PRODUCT_CENTER_TABLES`（**必须**在 `core.dim_erp_sku` 之前）：
漏了 ⇒ 云端没有段定义 ⇒ 下拉框空 ⇒ SKU 选不了段。

### 9.7 本地库复验（2026-11-17，真实服务层）

| 场景 | 结果 |
|---|---|
| 尾程按段命中（SKU 1768 = T01） | `22.34 CNY`，`rate_table`，`estimated=False` |
| 未选段 | `22.34`，`estimated=True`，`missing_weight_tier`（默认最轻段） |
| T06（30kg 以上）未配价 | `None`，`missing_delivery_rate_for_tier`（≠ 免费） |
| 底线（**包邮**） | **126.19**，尾程进底线 = True，缺料清单空 |
| 底线（**不包邮**） | **81.74**，尾程进底线 = False，缺料清单空（**不报**缺费率） |

### 9.8 遗留与风险

- **生产 1122 个 SKU 的重量段全空** ⇒ 按新规则全部落到最轻段（尾程立刻可算但偏乐观）
  ⇒ 运营需按实物批量归类。
- **生产 `finance.delivery_rate_rules` 仍 0 行** ⇒ 尾程仍算不出来；
  发版后需用新的「批量新增」按段录费率，并填平台尾程占比。
- **Shopee 两张价目表并存**：图 1「本地标准配送」（买家 0，2.03/2.87/3.38/5.42/10.00 SGD）
  与上轮「三方合」（买家 1.99 + 卖家，4.29/5.20/5.78/8.06/13.19 SGD）各对应什么渠道，
  待业务确认；本地库当前录的是后者。
- **TikTok SG 尾程价目表**尚未提供 ⇒ 本地无法录 TikTok 档位。
- **汇率 5.2077** 需业务认可（生产汇率表仍是 2025-11-01 的 5.2）。

### 9.9 全量回归暴露并修复的三类问题（2026-11-17）

批次 6 改完跑 `backend/tests` 全量，暴露 13 条失败，**根因全部在本批改动**，已逐条修掉：

| # | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | 利润链报 `decimal.InvalidOperation`（`Decimal(str(协程对象))`）、控制台刷「coroutine `_reference_logistics_from_rule` was never awaited」 | 批次 6 把 `_reference_logistics_from_rule` 改成 async（按重量段取代表重量），但**两个调用点漏了 `await`** —— `find_reference_logistics_cost` 与批量预取 `prefetch_platform_sku_profit_inputs` ⇒ 传进利润链的是协程对象 | 两个调用点补 `await`；全仓核对该方法只有这两处调用点 |
| 2 | `no such table: core.dim_weight_tiers`（SQLite 假库） | 老测试用「只建几张表」的 SQLite 假库，新表不在清单里 | 3 个 fixture 的建表清单补 `core.dim_weight_tiers`（SKU 页 / 通知页 / 平台定价页） |
| 3 | 底线断言 28.23 ≠ 33.03 | 口径变了：**跨境电商不是默认包邮** ⇒ 种子 SKU 默认「不包邮」⇒ 尾程不进底线 | 共享定价种子**显式**把该 SKU 标成包邮（种子语义 =「商家承担尾程」）；「默认不包邮 ⇒ 尾程不进底线、且不报缺费率」由 `test_free_shipping_switch.py` 覆盖 |

配套两处（同样是「口径改了，守护要跟着改」而不是「把守护改松」）：

- `price_adjust_notify_service` 的**归因快照**改记**实际计入**的尾程：不包邮 ⇒ 记 0、尾程占比记 None。
  否则归因会说「尾程涨了 5 元所以底线跳高」，而这笔尾程压根没进底线。
- `test_product_delivery_cost_floor.py` 的源码接线守护改认 `delivery_cost=applied_delivery_cost`
  （批次 6 起尾程先过包邮闸门，进利润链的是闸门后的值），并额外断言闸门变量存在。

> 教训：**把一个方法从同步改成 async，调用点不会自己报错** —— 漏 `await` 时传下去的是协程对象，
> 往往要到下游 `Decimal(str(x))` 才炸，而且只在**特定数据分支**上炸。
> ⇒ 改 async 后必须全仓核一遍调用点（本批用 grep 逐个核对），不能只看编译通过。

修完后的最终结论（2026-11-17）：

| 项 | 结果 |
|---|---|
| 后端全量 `backend/tests` | **6213 passed / 8 skipped / 0 failed**（515.63s） |
| 前端 `node --test frontend/tests/productCenterUi.test.mjs` | **99 / 99 pass** |
| `npm run build` | 成功（17.25s，ProductCenter chunk 116.49 kB） |
| black / ruff（本次变更的 27 个 .py） | 全绿 |
| 架构 SSOT / UTF-8 卫生 / 前端 API 方法 / 数据库字段 | 全绿（4/4、22 files、256 调用 0 缺失、0 警告） |
| 本地库复验（修 `await` 之后） | 尾程 T01 = **22.34**（rate_table）；T06 未配价 ⇒ 金额留空 + `missing_delivery_rate_for_tier`；底线 包邮 **126.19** / 不包邮 **81.74**；**利润试算的头程成本 = 3.80（真数字，不再是协程对象）** |

## 9.10 批次 7 · 定价设置修复 + 费率按官方牌价校准 + 本地控制台看门狗（2026-11-17）

### 9.10.1 起因：截图里的「定价设置是空的」

现象：SKU 资料页点「定价设置」，「平台成本率」tab 里**平台空、四个费率空、生效日期空、来源空、版本空** ——
一个纯空壳，运营改不了任何费率。

根因（代码链）：

1. SKU 资料页的按钮走 `openPlatformFeeDrawer('tiers')`（`frontend/src/domains/business/views/ProductCenter.vue:216`）
   ⇒ **只开「库龄档位规则」tab**；「平台成本率」tab 的表单**只在** `openPlatformFeeDrawer('platform')`
   分支里被初始化（`:2605-2630`）。
2. 该分支里的「平台」是一段**只读文本**（`:994`），平台身份靠测算页顶部的筛选条件
   `operatingQuery.platform_code`（`:442-452`）**隐式**传进来 ⇒ 从 SKU 资料页进抽屉没有平台上下文，
   表单保持初始空值（`:1455-1471`）⇒ 就是截图里那个空壳。
3. 更危险：保存时写入目标取的是 `operatingQuery.platform_code`（`:2667-2679`），**不是表单里的平台**；
   没有平台时 `if (!platformCode) return;` 是**静默返回**（不提示）。
   ⇒ 运营在这个空壳里填数点保存，会**静默写到别的平台行上**（界面上「平台」那一栏还是空的）。

修复（批次 7-A，纯前端，**不新增后端接口** —— `/api/sku-operating-dimensions` 已经把每个平台的
全部费率字段带回来了，`product_center.py:4819-4832`）：

- 抽屉**自带平台选择器**（`v-model="pricingDrawer.form.platform_code"`），切换平台即重装表单；
- 保存目标 = **抽屉里选中的平台**，没有平台就提示「请先选择平台」并禁用保存（不再静默）；
- 两个入口各叫各的：SKU 资料页 →「库龄档位规则」，测算页 →「平台成本率」（原来两个都叫「定价设置」）。

### 9.10.2 费率对官方牌价（Walter 2026-11-17 拍板）

**履约模式澄清**：我们**没有跨境直邮**，全部是「头程 → 当地本地仓 → 消费者」，本地仓是**自有/三方仓**。

| 项 | 旧值（实测残差 2026-01-07） | 新值（官方牌价） | 依据 |
|---|---|---|---|
| Shopee SG 平台佣金 | 14.87% | **16%**（含税） | 官方 2026-01-01 起：跨境直邮(SLS) 与三方仓(3PF) 统一 16%，官方海外仓(FBS) 11%。我们落 3PF 口径 |
| TikTok SG 平台佣金 | 7.37% | **8.175%**（含 GST） | 官方 2026-04-01 起：一般类目非 BXP 8.175%、BXP 7.085%、电子产品 6.54%/5.45%；另收交易手续费 3.27% |
| Shopee SG 尾程（5 档） | 4.29/5.20/5.78/8.06/13.19 SGD | **4.02/4.86/5.37/7.41/11.99 SGD** | 官方《3PF 收费标准》「新加坡站点 3PF 尾程费用标准」（2025-03-18 起）：买家 1.99 + 卖家 2.03/2.87/3.38/5.42/10.00 |

**口径澄清（第一轮的口径判断有误，此处更正）**：旧行的 4.29 不是「卖家承担」，
而是「买家 1.99 + 卖家 2.30（三方合非 SPA）」的**总额** —— 库里那 5 行的 `notes` 写得很清楚。
而系统里**包邮 = 商家承担尾程**，此时买家那份 1.99 也要商家扛 ⇒ 费率表记的必须是**总额**。
所以新值 = 1.99 + 卖家承担（2.03/2.87/3.38/5.42/10.00）= 4.02/4.86/5.37/7.41/11.99 SGD
⇒ 折人民币（5.2077）= **20.93 / 25.31 / 27.97 / 38.59 / 62.44 元**，降幅 **6~9%**（不是一半）。

**本轮明确不动的两个数**（没有重算依据 ⇒ 动了才是错）：

- `other_cost_rate`（残差桶 41.65% / 27.27%）：它是实测恒等式反推值，要用**新实测数据**重算；
  官方两次调涨后它偏低约 1.1pt（Shopee 16% − 14.87%），记为缺口。
- `delivery_cost_rate`（尾程占收入比）：权威口径是「**我们自己费率表**算出的尾程均值 ÷ 平台平均售价」
  （迁移 `20261234` 写明），重算前置条件是 ① SKU 段归类完成（现 1120/1122 段为空）
  ② 订单级 vs 单件摊的口径钉死。**当前无影响**：`free_shipping` 默认关闭 ⇒ 尾程不进任何底线。

迁移：`current_migrations/versions/20261238_official_platform_fee_rates.py`（幂等 upsert：有则改、无则插 ——
生产尾程费率 0 行，本地 5 行）。守护：`backend/tests/test_official_platform_fee_rates.py`（6 条）。

### 9.10.3 本地控制台看门狗：只加一条规则

事故复盘（2026-11-17）：后端一直正常响应（业务请求 200），控制台却按「启动超时（超过 600 秒）」
把**健康的**进程树杀了 —— 探针只有 3 秒预算且**要求 HTTP 200**，后端只是忙（本地采集把 Playwright 跑在
同一进程里）或健康检查降级返回 503，都会被判成「没启动」。

按「不要防御过重」的原则，**只加一条规则**（`scripts/local_console_processes.py`）：

> **杀进程之前，必须再确认一次「服务端口真的不通」。** TCP 连得上 ⇒ 服务还活着 ⇒ 绝不杀，
> 只把启动预算窗口重新计时。

实现：新增 `probe_service_liveness()`（只做 TCP 握手，**不看 HTTP 状态码**），
在启动超时的杀进程分支前先问它；活着 ⇒ 状态回到 `running`、不写失败结论；不通 ⇒ 保留原逻辑
（终止 + 留审计证据）。**没有**加「连续失败 N 次才计时」、**没有**拆 liveness/readiness 两档探针、
**没有**加后台巡检线程 —— 一条规则就堵住了事故。

守护：`tests/test_local_console_processes.py` 两条（端口通 ⇒ 不杀；端口不通 ⇒ 仍按启动超时终止并留证）。

**收尾时发现的第二层根因（本地开发环境配置，非代码缺陷）**

17:44 我改迁移文件 `current_migrations/versions/20261238_official_platform_fee_rates.py`，
本地后端（`logs/backend-local.launch.ps1`）**立刻消失**。查日志与状态文件查清了：

- 后端 **16:46:05** 起来，`Application startup complete`，之后**持续响应 15 万+ 次**
  `GET /healthz/ready 200 OK`（日志里全是 `200 OK`），一直活到 17:44；
- `logs/backend-local.err.log` 最后一行：
  `WARNING: WatchFiles detected changes in 'current_migrations\versions\20261238_official_platform_fee_rates.py'. Reloading...`
  ⇒ 紧接着日志**戛然而止**，重载后的进程没起来。

根因：启动命令是 `uvicorn ... --reload` 且**没有 `--reload-dir`** ⇒ WatchFiles 默认监听 **CWD（仓库根）**
⇒ **改任何一个 .py（包括与后端无关的迁移文件）都会触发后端热重载**，而重载窗口里进程可能被
看门狗判成「启动超时」而杀掉。`logs/local-console/local-console-state.json` 记录的后端
`last_error` 正是「启动超时（超过 600 秒）」。

⇒ **这不是产品代码缺陷，是本地开发环境配置问题**：要么把 `--reload` 限定到 `backend/`，
要么本地开发时不起 `--reload`。**本轮不动它**（属于环境脚本调整，不是批次 7 范围），
仅在此留档，避免下次再被"改个迁移文件后端就没了"绊住。

⚠️ 注意：16:37:53 那次「启动超时杀进程」发生时，控制台进程是 **16:06:19** 启动的，
加载的仍是**改动前**的旧模块 ⇒ 那次走的是旧逻辑。新的 liveness 规则要等控制台重启后才生效。

### 9.10.4 结果

| 项 | 结果 |
|---|---|
| 前端 `node --test frontend/tests/productCenterUi.test.mjs` | **102 / 102 pass**（新增 3 条） |
| `npm run build` | 成功（17.41s，ProductCenter chunk 117.36 kB） |
| 后端 `backend/tests/test_official_platform_fee_rates.py` | **6 passed** |
| 看门狗 `tests/test_local_console_processes.py` + `tests/test_local_console.py` | **34 passed** |
| 本地库复验（真实服务层，SKU 1768 = T01） | Shopee 底线：包邮 **126.19 → 121.43**（尾程 22.34 → 20.93）、不包邮 **81.74 不变**；TikTok T01 无尾程费率 ⇒ 报 `missing_delivery_cost` |
| 平台费率（校准后） | Shopee 佣金 0.16 / 达人 0.0111 / 其他 0.4165 / 尾程占比 0.1124；TikTok 佣金 0.08175 / 达人 0.0606 / 其他 0.2727 / 尾程占比 **空** |

**批次 7 收尾复跑（2026-11-17 晚）**

| 项 | 结果 |
|---|---|
| 后端全量 `pytest backend/tests` | **6219 passed / 8 skipped / 0 failed**（498.34s；批次 6 的 6213 + 本轮 6 条费率守护） |
| 根目录全量 `pytest tests` | **845 passed / 5 skipped / 0 failed**（359.33s） |
| 前端 `node --test frontend/tests/productCenterUi.test.mjs` | **102 / 102 pass** |
| `npm run build` | 成功（10.28s，ProductCenter chunk 117.36 kB） |
| black / ruff（本轮变更的 4 个 .py） | 全绿（`scripts/local_console_processes.py` 原有一处缩进被 black 收拢，已复跑 34 条看门狗守护仍全绿） |

**收尾时自查修掉的一个降级缺口（同一批次内闭环）**

迁移 `20261238` 的 `upgrade` 覆盖了平台费率的**生效日期**（`fee_rate_effective_from`），
但 `downgrade` 只还原了费率本身 ⇒ 降级后会留下一行自相矛盾的数据：
「费率是 2026-01-07 的实测残差、生效日期却是官方调价日（Shopee 2026-01-01 / TikTok 2026-04-01）」。
这个字段是产品中心保存费率时写下的生效日（`backend/domains/business/routers/product_center.py:4293`），
被迁移覆盖后若降级不还原，数据会一直错着。

- **修法**：`PLATFORM_FEE_ROLLBACK` 补上 `fee_rate_effective_from`（回 **2026-01-07**，与旧的
  `b_class_measured_2026_01_07` 来源对齐），`downgrade` 的 UPDATE 补写该列。
- **守护**：新增 `test_downgrade_restores_effective_from_too`（先红后绿：缺字段报 `KeyError`）。
- **实跑验证**（本地库真实 downgrade → upgrade 往返）：
  - 降级后：Shopee `0.1487` + **2026-01-07**、TikTok `0.0737` + **2026-01-07**、source 回到
    `b_class_measured_2026_01_07`、version 回到 `v2`；
  - 再升级后：Shopee `0.16` + 2026-01-01、TikTok `0.08175` + 2026-04-01、version `v3`；
  - Shopee SG 尾程 5 档全程不变（20.93 / 25.31 / 27.97 / 38.59 / 62.44 元）；
  - 链头仍为 `current_schema_20261238_official_platform_fee_rates`。

### 9.10.5 发布与部署后验收（v7.32.0，2026-11-17）

**发版动作**（按 `docs/guides/RELEASE_CHECKLIST.md` 的双镜像纪律）：

| 步骤 | 结果 |
|---|---|
| 提交（功能 + 发版记录两条） | `b25bfe55` feat(product-center) / `76efdc00` chore(release) |
| 同步 main 到双镜像 | `XIHONG_GIT_MIRROR_SYNCED=76efdc00`；独立核对 GitHub / CNB / 本地三方 SHA 一致 |
| 打标签 | `v7.32.0`（注解对象 `87afad00` → 提交 `76efdc00`） |
| **先推 CNB**（镜像，惰性） | tag 对象 `87afad00` 一致；生产**无新部署批次** ⇒ 确认推 CNB 不触发部署 |
| **再推 GitHub**（触发部署） | `* [new tag] v7.32.0`；流水线 run `44072174180` |
| 流水线 | **completed / success**（check-config → 发布门禁 → 构建推送 → 部署 全部 completed） |

**生产部署后验收**（只读通道实查，非推断）：

| 项 | 实测结果 |
|---|---|
| 容器 | 7 个全部 **healthy**（nginx / frontend / backend_api / celery_worker / celery_beat / postgres / redis） |
| API | `/healthz/ready` → **200**，`version: v7.32.0`，`runtime_mode: production`，数据库 connected |
| `/api/docs` | **200** |
| 迁移链头 | `current_schema_20261238_official_platform_fee_rates`（三条迁移全上） |
| `core.dim_weight_tiers` | 已建，**6 档** |
| `core.dim_erp_sku.weight_kg` | **已删除**（`weight_kg_still_exists = 0`） |
| `finance.delivery_rate_rules` | **5 行**（迁移写入官方 3PF 尾程） |
| Shopee 佣金 | **0.16**，生效 2026-01-01，source `official_3pf_commission_2026_01_01 + …`，version `v3` |
| TikTok 佣金 | **0.08175**，生效 2026-04-01，source `official_sg_2026_04_01 + …`，version `v3` |
| Shopee SG 尾程 5 档 | 20.93 / 25.31 / 27.97 / 38.59 / 62.44 元，source `shopee_sg_3pf_standard_2025_03_18` |
| 残差桶 `other_cost_rate` | **未动**（Shopee 0.4165 / TikTok 0.2727）✅ 与设计一致 |
| 前端资源 | 新 hash `ProductCenter-5b88fe02.js` 已上线，含平台选择器代码 |

⚠️ **上线后仍需业务录数**（与 §9.10.4 预判一致，生产实测已确认）：
`sku_weight_tier_set = 0` ⇒ **1122 个 SKU 重量段全空** ⇒ 尾程一律落最轻档并标 `estimated`
⇒ **成本底线偏低** ⇒ 需按实物批量归类重量段；包邮开关需逐 SKU 勾选（默认不包邮）。

## 9.11 批次 8 · 尾程费率「去汇率层 + 卡片式维护」（2026-11-17）

### 9.11.1 起因：Walter 2026-11-17 拍板的三条口径

> 1. 填入的就应该是**人民币**，系统不做汇率换算（给图片只是要帮忙折成人民币）；
> 2. 应该是一张**卡片**，用户只改「对应平台 + 仓库 + KG 段」的运费，
>    不要一条一条加（人工每条都要找平台和仓，很麻烦）；批量新增完之后要方便人工查看和修改；
> 3. **暂不补录数**（录数是人工的事），把系统本身做好交付人工使用。

### 9.11.2 口径一：去掉汇率录入层 —— **后端契约不动、迁移不写**

- **后端本来就只收人民币等值**：`backend/schemas/product_center.py:775-817`
  `DeliveryRateRuleCreateRequest.cny_only` —— `currency` 非 CNY 直接 `ValidationError`。
  ⇒ 那层「原币单价 / 币种 / 汇率→人民币」是**前端自己加的有害壳**：
  它制造了「照抄外币数字」的机会，而尾程计算链**不读汇率**
  （`backend/services/product_finance_service.py` 取数端过滤
  `func.coalesce(DeliveryRateRule.currency, "CNY") == "CNY"`）
  ⇒ 照抄 SGD 4.02 当人民币 ⇒ 尾程少算 5 倍 ⇒ **成本底线偏低 ⇒ 直接漏钱**。
- ⇒ **批次 8 只删前端汇率层**（`ProductCenter.vue` 里的 `deliveryCurrencyOptions` /
  `DELIVERY_FX_NOTE_PREFIX` / `deliveryRuleConvertedCny` / `deliveryBatchConvertedCny` /
  `deliveryRuleNotes` 全部删除），表格与批量弹窗都只留一列「单件尾程费（元）」。
- 外币的处理：**运营自行折算后填人民币**，原币与汇率写进**备注**（自由文本，不参与计算）。

### 9.11.3 口径二：卡片式维护 —— 一个「平台 × 仓」= 一张卡

- **卡内按全局段表固定顺序列全部 6 段**（不让人挑段 ⇒ 不会漏段、不会选错段）；
  缺价的段在卡上**看得见**（「未配置 ⇒ 该段尾程算不出来」）。
- 卡头两个选择器：平台 + 收货仓（候选项来自 `operatingDimensions`，
  **不是**只列已有费率的组合 ⇒ 任何平台×仓都能开新卡）。
- 原表格保留在 `el-collapse` 里作「全部档位明细」⇒ 跨平台对照、看历史与停用行。
- **批量新增只是铺价手段**：铺完自动把卡片定位到对应「平台 × 仓」。

### 9.11.4 口径三：改价只进不退 —— **本轮实测发现的硬伤（409）**

**症状**（真实本地栈复现，非推断）：卡片里改一个**已存在**档位的价 ⇒
`POST /api/delivery-rate-rules` 直接返回 **409「active delivery rate rule already exists」**
⇒ 用户最核心的动作（改对应平台/仓/段的运费）**不可用**。

**根因**：

1. 改价时前端把**原行的生效日**（生产里 Shopee SG 五档都是 `2026-01-01`）一起发出去；
2. 后端据此把旧行闭区间到 `生效日 - 1 天` = `2025-12-31`；
3. 旧行的区间**倒挂**（`effective_to < effective_from`）⇒ 撞数据库检查约束
   `ck_delivery_rate_rules_window`（`effective_to IS NULL OR effective_to >= effective_from`）
   ⇒ `IntegrityError` ⇒ 被兜底成 409「重复行」；
4. 就算没有那个约束，历史也会被**抹掉**（2026-01-01 起就算新价）
   ⇒ 事后对不上「当时按多少钱算的」—— 恰好是版本化要防的那件事。

**修法（口径收口到后端一处，符合 SSOT）**：

| 场景 | 新行 `effective_from` | 旧行 `effective_to` / `status` |
|---|---|---|
| 该档位**已有当期行**（= 改价） | `max(调用方给值, 今天)` | `新行生效日 - 1 天` / 今天起生效则置 `inactive` |
| 该档位**没有当期行**（= 首次录价） | 调用方给的值（可回填整张价目表的历史起点） | —— |
| 调用方给的是**未来日期**（官方价目表说明年生效） | 未来日期 | 未来日期 - 1 天 / **旧价继续当期**（避免空窗期 ⇒ 尾程算不出来） |

落地：`backend/domains/business/routers/product_center.py`
`create_delivery_rate_rule`（`payload["effective_from"] = effective_from`）。
前端同步改成**改价发「今天」**（`deliveryToday()`），并在卡片上只显示
**今天真正生效**的那一档（未来才生效的价不冒充当前价）。

### 9.11.5 落地物与守护

- **落地物**：`frontend/src/domains/business/views/ProductCenter.vue`、
  `backend/domains/business/routers/product_center.py`。**无迁移**（表结构未变）。
- **新增守护** `backend/tests/test_delivery_rate_card_save_flow.py`（6 条）：
  **真跑路由**（`ASGITransport` + 真实 `pg_database` 隔离库，每用例独立 database，
  用完 DROP ⇒ 不碰本地开发库、更不碰生产库）：
  改价新版本从今天起 / 回填的生效日被忽略（历史不被抹）/ 当期行仍只有一条 /
  只改备注不新建行 / 非 CNY 被拒 / 首次录价保留调用方给的生效日。
- **改写守护** `backend/tests/test_delivery_rate_currency_guard.py`（23 → 24 条）：
  删掉钉死「必须有原币单价/币种/汇率」的 2 条旧守护（口径已归一），
  换成 5 条钉新契约的守护 + 1 条「改价生效日由后端说了算」；
  `test_same_tier_price_change_is_not_rejected_as_overlap` 的字面量跟着新写法走，
  并**加严**（钉住 `max(body.effective_from, today)`，并断言旧写法不许回来）。
- **前端守护** `frontend/tests/productCenterUi.test.mjs` **107/107**（新增 2 条：
  改价发「今天」、卡片只显示今天生效的那一档）。

### 9.11.6 真实栈复验与本地库还原

本地后端（8001）实跑：

| 动作 | 结果 |
|---|---|
| 卡片改价（20.93 → 25.00，沿用原生效日 2026-01-01） | **201**；新行 `effective_from = 2026-11-17`（今天）；旧行 `effective_to = 2026-11-16` + `status = inactive` |
| 只改备注（PATCH） | **200**；行数 2 → 2（不新建行），单价不变 |

⚠️ 验完**已把本地库完整还原**：`finance.delivery_rate_rules` 回到 6 行，
rule_id=1 的价格 / 生效日 / 状态 / 来源 / 版本 / 备注**逐字段与原状一致**。

⚠️ 本地环境坑（**未改**，属环境脚本非产品缺陷）：实际在跑的本地后端是
`logs/backend-local.noreload.launch.ps1` 起的（**不带 `--reload`**）
⇒ 改了后端代码不会热生效，**必须重启进程**才能验到新代码。
（`logs/backend-local.launch.ps1` 那份带 `--reload` 的，脚本自己注明
watchfiles 会把 `temp/` 下的临时脚本也当变更来源 ⇒ 落盘就重启、端口会消失。）

### 9.11.7 未完成

- **提交 / 发版待授权**（v7.32.0 的授权只覆盖批次 6+7）。
- TikTok SG 尾程价目表仍缺 T01 / T03–T06；本地那档 T02 = 14.84 元的官方出处待确认。
- 生产 1122 个 SKU 重量段全空、平台 `delivery_cost_rate` 全 NULL、残差桶待重算、
  汇率 5.2077 待认可 —— 属**业务录数**，见 `docs/superpowers/plans/STATUS.md`「当前未结」#10。
