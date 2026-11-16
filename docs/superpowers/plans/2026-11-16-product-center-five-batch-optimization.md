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
currency / effective_from / effective_to / status / source / notes`
当期唯一：`(platform_code, warehouse_code, min_weight_kg) WHERE status='active' AND effective_to IS NULL`
**刻意不建 FK 到 `dim_platforms`**（商品中心同步会 TRUNCATE 该表）。

**纯函数模块**：`backend/services/product_delivery_cost_service.py`
`select_delivery_tier(...)` / `compute_delivery_cost(...)` —— 无 ORM 无 DB；区间重叠返回 `None`
（歧义不猜）。

**缺重量降级**：按该仓最轻档 + 最贵仓保守估算并标 `estimated` —— 不让底线算不出来。

**两条落点**：① 利润测算（广告前利润要扣尾程）；② 成本底线 `(采购+尾程)÷D`。

**仓维度全线统一的 4 处连带**：
1. `list_skus` 加仓参数
2. `ops.price_adjust_baselines` 主键加 `warehouse_code`
3. `price_adjust_notify_service` 按 (平台×仓) 循环且只对有库存的仓发
4. 人工覆盖表 `sku_platform_pricing` **不下沉**（保持 SKU×平台）

---

## 5. 批次 5 · 收口遗留

- 老链路 `build_baseline_profit` / `preview_operating_profit` 的 revenue 口径统一（批次 1 已做大半）
- 第三份 profit 实现收口到一处
- `cost_completeness` 两套值域（`complete/partial/incomplete` vs `incomplete/estimated/mixed/actual`）统一
- `last_mile_cost` 标签改名：它是头程账单内的分段（港→仓），**不是买家快递**；UI 标签改「头程末端派送」，新概念叫「尾程配送费」

---

## 6. 已知阻塞与软依赖

| 项 | 影响 | 处理 |
|---|---|---|
| 生产库 `other_cost_rate` 运费占比未实测 | 批次 4 拆运费的依据 | 需生产库执行倒推 SQL（开发库订单表 0 行，测不了） |
| 1125 个 SKU 权重 0% | 尾程进底线后大量降级为 `estimated` | 需业务补录重量（批次 3 把重量改必填 + 表头改黑，为补录做准备） |
| `VERSION` 文件 v7.28.0 vs 最新 tag v7.30.0 | 发布版本号 | 发布前核对真源，与 tag 同提交 bump |
| `alembic.ini` 指向只读历史链 | 迁移命令跑错链 | **既有问题，批次外记录**，不趁机改 |

---

## 7. 发布

- 版本号待定（按 `docs/guides/RELEASE_CHECKLIST.md` 流程：VERSION 与 tag 同提交 bump）
- 推送方式：`git push origin vX.Y.Z`（GitHub SSH-443 触发部署；CNB 仅为镜像，tag 两镜像须同对象）
- 发布后独立 SSH 验证：`/healthz/ready` 与 `docker compose ps` 的版本号 == tag；`deploy-logs` 只多一个批次
