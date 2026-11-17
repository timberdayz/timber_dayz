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
