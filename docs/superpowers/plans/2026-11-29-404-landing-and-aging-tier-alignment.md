# 2026-11-29 · 采集 404 归位 + 库龄分档「彻底一致」

> 本文档记录本批次的两件事：
> 1. **采集侧 404 死结的根因与修复**（不是改登录判定，是加「页面归位」）；
> 2. **看板库龄分档与业务定价档位对齐**（0/60/90/120，SKU 级，门槛读档位表）。
>
> 两件事的共同纪律：**唯一实现 + 守护测试锁死**，任何一边漂移都立刻暴露。

---

## 一、采集侧 404：根因与修复

### 1.1 事实（实测，不是推断）

2026-11-29 实测 `LoginStatusDetector._check_url`（`modules/utils/login_status_detector.py`）：

| URL | 判定 | 命中 |
|---|---|---|
| `https://seller.shopee.cn/404?cnsc_shop_id=1391124228` | **logged_in 0.85** | `/seller` |
| `https://seller.shopee.cn/account/signin?next=…` | **logged_in 0.85** | `/seller` |
| `https://seller.shopee.cn/?cnsc_shop_id=1227491331` | logged_in 0.85 | `/seller` |
| `https://seller.tiktokshopglobalselling.com/404?…` | **unknown 0.3** | — |
| `https://seller.tiktokshopglobalselling.com/account/login` | not_logged_in 0.85 | `/account/login` |

Shopee 的「已登录关键词」里有 `"/seller"`，而判定是对**整个 URL 做子串匹配**
⇒ `https://seller.shopee.cn/…` 天然命中 ⇒ **Shopee 域名下的任何页面（含 404、含登录页）
都被判成「已登录」**。TikTok 用的是路径级关键词（`/homepage`、`/compass/`…），不会误命中。

### 1.2 四层叠加形成的死结

1. `runtime_session.open_persistent_runtime_bundle`（`modules/apps/collection_center/runtime_session.py:639`）
   打开持久 profile 后**不导航任何 URL**，直接取 Chromium 恢复的 `pages[0]`
   ⇒ 上次会话停在 404，这次开箱即 404。
2. `prime_runtime_page_for_login_gate` 默认只在 `about:blank` 时导航
   （`force_navigate=False`），executor 调用时**没传 `force_navigate=True`** ⇒ 404 被原样保留。
3. 登录闸门把 404 判成「已登录」⇒ 放行 ⇒ **没有任何一层去纠正它**。
4. `ShopeeShopSwitch._rewrite_cnsc_shop_id` 只改 query 里的 `cnsc_shop_id`、**保留 path**
   ⇒ `/404?cnsc_shop_id=旧` 变成 `/404?cnsc_shop_id=新` ⇒ 一直在 404 上打转。

### 1.3 为什么 TikTok「看起来没事」

**不是因为 TikTok 自己会自动重定向** —— 两边的登录短路逻辑一模一样
（`shopee/components/login.py:467` vs `tiktok/components/login.py:709`），
两边都**不会**主动导航。真正原因是：**我们对 TikTok 拦得对、对 Shopee 放行错了**，
于是只有 TikTok 会走「重新导航」那条路。

结构性佐证：Shopee 把店铺编号明文放在 URL query（`cnsc_shop_id`），
陈旧 URL 一恢复就带出上一家店的编号；TikTok 的身份参数是 `shop_region`（区域），
探测函数只认 `cnsc_shop_id`/`shop_id` ⇒ 提取不到 ⇒ 根本不落探测记录。
**库里 28 条探测记录 100% 是 shopee**，一条 TikTok 都没有 —— 不是 TikTok 没错，
是这个错对 TikTok 不产生后果。

### 1.4 修复方案：加「页面归位」，**不改登录判定**

用户明确指出：**404 确实是已登录的页面，它其实已经进去了，只是需要重新导航一下**。
所以修复**不是**把 404 判成「未登录」（那会让采集器白跑一遍重新登录、甚至弹验证码），
而是**把页面导航回平台入口**，让平台自己导回带店铺编号的正常页。

新增 `runtime_session.ensure_platform_landing_page()`：

- **只有当前页确实是错误页时才导航**；正常页面**一次额外导航都不加** ⇒ 采集流程零影响；
- 导航目标 = 平台标准入口（Shopee `https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome`），
  **不拼目标店编号** —— 拼了就等于自己给自己写答案，失去探测意义；
- 归位失败（跳登录页 / 仍停在错误页 / goto 异常 / 无平台入口）⇒ 明确返回失败原因，**不抛给采集流程**；
- `get_platform_login_entry` 对未知平台会抛 `ValueError` ⇒ 已兜住。

探测链路：`executor_v2._record_platform_shop_discovery_async` 在读 URL 前，
若当前页是错误页 ⇒ 先归位 ⇒ 再读编号：

- 归位成功 ⇒ 读到**真实**身份，按正常探测落库；
- 归位失败 ⇒ 仍按「探测失败」落库，**残留编号连参数都不给它**（服务层也会丢弃，是第二道防线），
  证据（URL）留在 `raw_payload` 里。

### 1.5 附带修掉的一个真 bug

`get_platform_login_entry(platform)` 对未知平台**抛 ValueError**。
原实现直接调用它 ⇒ 归位失败会把采集流程带崩。已兜住并有守护测试。

### 1.6 判据下沉到独立模块

错误页判据从 `executor_v2.py` 移到 `modules/apps/collection_center/platform_error_page.py`：

- `runtime_session`（导航实现的唯一归属）也要用它，而 `executor_v2` 依赖 `runtime_session`
  ⇒ 放同一文件会循环依赖；
- `executor_v2` 保留同名别名 `_is_platform_error_page` / `_ERROR_PAGE_PATH_SEGMENTS`，
  迁移守护测试与既有调用方按这个名字引用，**口径一个字没改**。

---

## 二、库龄分档：与业务定价档位「彻底一致」

### 2.1 原状（实测，开发库）

| | 旧看板口径 | 业务定价档位 |
|---|---|---|
| 门槛 | `<30 / 90~180 / ≥180` | `0 / 60 / 90 / 120` |
| 30~90 天 | **整段无档** | 归「库龄≥60天」 |
| 覆盖 | 货值全量，行数/SKU 只覆盖 <30 的行 | — |

实测：库里 28 条探测…（见 §一）；库龄侧开发库 516 行 / 511 SKU / ¥232,560，
其中 **167 个 SKU（货值 ¥50,648）落在 60~90 区间** —— 旧口径下这批货
在看板上是「中度 0 / 重度 0 / 活跃」，**货值整段看不见**。

### 2.2 口径决定（用户已拍板）

**按业务定价档位分组（0/60/90/120），彻底一致；不动 `days_since_restock` 判定口径。**

### 2.3 分组粒度：SKU 级（不是仓级）

商品中心的定价是 **SKU 级**（一个仓压着没补货，就是这货整体压着），
所以档位必须按 SKU 算：

- SKU 库龄 = 各仓**最长**（只算还有可售库存的仓）= `aggregate_sku_restock_days`（唯一实现）；
- SKU 货值 = 该 SKU 全部仓的货值之和；
- ⇒ **货值与 SKU 数都互斥可加**（加起来正好等于总数，不会出现「各档加起来比总数多」）。

仓级分档（行级明细里的 `restock_tier`）保持不变 —— 那是另一个粒度的问题。

### 2.4 阈值不写死：直接读业务档位表

`sql/api_modules/inventory_backlog_summary_module.sql` 改成从
`finance.sku_pricing_policies` 当前生效行取门槛：

- 业务改档位表 ⇒ 看板**自动**跟着变，不需要改 SQL；
- 每行归到「它命中的**最高**门槛」（`MAX(min_restock_days) WHERE min_restock_days <= days`），
  与 Python `classify_restock_tier` 同义。

### 2.5 服务层：两条 SQL 路径 → 一个 Python 汇总

旧实现有**两条 SQL 路径**（带期间走一段 CASE、不带期间读视图），
两份 CASE 各写一遍阈值 ⇒ 迟早漂移；而且阈值写死在 SQL 里。

现在两条路径**共用同一个 Python 汇总**：

- `inventory_restock_service.build_restock_tier_buckets(rows)` —— **唯一实现**；
- `postgresql_dashboard_service.summarize_inventory_backlog_rows(rows)` —— 薄封装；
- `_load_inventory_backlog_summary` 两条路径都**取行 → 调同一个汇总**。

### 2.6 旧标准指标保留原义

`deep_stagnant_value`（≥180 天）、`mid_stagnant_value`（90~180 天）是
「深度积压」这一**独立指标**（回答「压了多久没动」），**口径一个字不改**，
仍随接口返回；看板不再把它们当分层展示。

指标词典里那句「两套分档并存，别混用」已更新为
「**分档只有一套（0/60/90/120），别再另起**」（两份副本同步）。

### 2.7 页面改动

| 页面 | 改前 | 改后 |
|---|---|---|
| 业务概览 · 库存积压卡 | 总库存价值 / 重度（压180+）/ 中度（压90-180）/ 滞销占比 | 总库存价值（含活跃占比）+ 压60-90 / 压90-120 / 压120+；下方补「共 N 行 · M 个 SKU」 |
| 库存概览页 | 重度积压SKU / 中度积压SKU / 活跃SKU（<30） | 活跃 / 压60-90 / 压90-120 / 压120+（SKU 级，互斥可加） |

卡片与页面上「行数 / SKU 数」现在覆盖**全部行**，不再是「货值全量、计数只覆盖 30 行」。

---

## 三、验证证据

| 项 | 结果 |
|---|---|
| 新增守护测试 `backend/tests/test_platform_landing_page.py` | 11 passed |
| 既有错误页 + 迁移口径守护测试 | 69 passed |
| 新增守护测试 `backend/tests/data_pipeline/test_inventory_backlog_tier_consistency.py` | 4 passed |
| `backend/tests/data_pipeline`（全量） | 839 passed / 14 failed —— 14 条**全在基线 156 内**，零新增 |
| 前端守卫（全部 `.test.mjs`） | 失败名单与基线**逐条一致**（8 个历史遗留），零新增 |
| `npx vite build` | ✓ built in 14.21s |
| Python 汇总 vs SQL 视图（真实库对账） | **逐档完全一致**；档位货值合计 ¥232,560.05 == 总货值；档位 SKU 合计 511 == 总 SKU 数 |
| 真库视图输出 | 日常 344 SKU / ¥181,911.74；库龄≥60天 167 SKU / ¥50,648.31；≥90 / ≥120 各 0 |

---

## 四、V2 遗留（本次不做，已记录）

1. **`LoginStatusDetector` 的 `"/seller"` 是域名级关键词** ⇒ Shopee 整站任何页面都被判「已登录」。
   本次**刻意不动**（登录态判定是对的，且改了会让采集流程冒风险）；
   建议后续把 URL 关键词判定改成**只看 path**，并补登录页的显式排除。
2. **Shopee 切店组件只改 query、保留 path** ⇒ `/404` 路径会被保留。
   本次靠「页面归位」兜住；根治要让切店组件在 path 是错误页时改走标准落地路径。
3. **`finance.sku_pricing_policies` 的门槛与 `RESTOCK_TIER_THRESHOLDS` 是两份拷贝**
   （Python 侧 + DB 侧）。本次用守护测试锁住一致（`test_policy_thresholds_match_python_unique_implementation`），
   但仍是两份；根治应让 Python 侧从档位表派生。
4. **`mart.inventory_backlog_base` 的 `days_since_restock` 缺失仍回落 0**（`COALESCE` 脆弱点，
   老 V2 条目）—— 本次新增的 `unknown_restock_row_count` 让缺失**在数据上可见**，
   但底层的「缺失伪装成 0 天」尚未修。
