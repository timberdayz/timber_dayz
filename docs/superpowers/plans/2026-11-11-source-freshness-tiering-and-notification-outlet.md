# 批次 3.3 —— 数据新鲜度分档 + 补通知出口

- **日期**：2026-11-11
- **来源**：「店铺身份保未来」优化方案（`docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md`）批次 3.3，对应问题单 P2-4
- **代码基线**：`main` @ `52d01608`
- **分支**：`feature/2026-11-11-shop-identity-freshness-tiering`
- **状态**：已实现（含守护测试），待评审

---

## 0. 范围与硬约束

| 约束 | 本批次的处置 |
|---|---|
| 不改语义层计数口径 | ❌ 完全没碰 `count(DISTINCT c.resolved_shop_id)` 与任何语义层 SQL |
| 不动历史事实行 | ❌ 没写任何针对 `b_class.fact_*` 的迁移/回填 |
| 不新增第三方依赖 | ✅ 只用仓库既有依赖（SQLAlchemy / httpx / FastAPI 链） |
| 不改 CI 配置 | ✅ |
| 不硬编码连接串/口令 | ✅ 连接串一律从 `.env` 读；通知内容脱敏 |
| 不改别的 PR 占用的文件 | ✅ `cloud_sync_integrity_tasks.py` / `cloud_sync_integrity_service.py` / `shop_identity_reconciliation_service.py` / `dashboard_bootstrap.py` **一个都没动** |
| 不直推 main | ✅ 分支 + 两端推送，PR 由负责人开 |

---

## 1. 复核结论（已核实的事实）

| # | 主张 | 结论 | 证据 |
|---|---|---|---|
| 1 | 红灯没有出口 | ✅ 确认 | `backend/services/data_pipeline/source_freshness_service.py:447` 只有 `success` / `partial_failed`；全仓无消费方（前端零命中），只有后端 `/api/data-pipeline/source-freshness` 一个只读接口 |
| 2 | 「当前采集范围」没有定义 | ✅ 确认 | 代码里只有「可选域全集」`DEFAULT_CONFIG_DATA_DOMAINS`（`backend/services/collection_contracts.py:27`），与数据库里实际生效的配置是**两份**定义 |
| 3 | 源表是覆盖写入 | ✅ 确认 | `b_class.fact_*_analytics_*` / `_orders_*` 为覆盖式写入；**没被覆盖**的是 `semantic.fact_analytics_monthly_atomic`（`semantic` schema 的 **VIEW**，既不在 `b_class`，也被 `relkind IN ('r','p')` 排除） |
| 4 | 红灯来自「曾采过、现已停采」 | ✅ 确认 | 代码里没有「当前采集范围」概念；「从未被采」的表判 `empty` ⇒ `skipped`，**不进 `partial_failed`** |
| 5 | 阈值口径 | ✅ 确认 | 粒度默认（daily/weekly=365、monthly=60、snapshot=10）+ 2 条链级例外（`shopee/products[daily]`、`tiktok/products[daily]`=30）+ 环境变量覆盖 |

---

## 2. 采集范围 SSOT（**以数据库配置为准**）

### 2.1 核实到的 ORM 字段定义

`modules/core/db/schema_parts/collection.py`：

```python
class CollectionConfig(Base):
    __tablename__ = "collection_configs"          # schema = "core"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    platform     = Column(String(50), nullable=False)
    data_domains = Column(JSON, nullable=False)    # 域清单（JSON 数组）
    is_active    = Column(Boolean, default=True, nullable=False)
    ...

class CollectionConfigShopScope(Base):
    __tablename__ = "collection_config_shop_scopes"  # schema = "core"
    config_id      = Column(Integer, ForeignKey("core.collection_configs.id"), nullable=False)
    shop_account_id = Column(String(100), ForeignKey("core.shop_accounts.shop_account_id"), nullable=False)
    data_domains   = Column(JSON_COMPAT, nullable=False)   # 该店铺实际采的域（JSON 数组）
    sub_domains    = Column(JSON_COMPAT, nullable=True)
    enabled        = Column(Boolean, default=True, nullable=False)
    ...
```

⇒ **域是 JSON 数组**（不是逗号分隔字符串、不是 jsonb 数组列）：`["products","analytics","services"]`。

### 2.2 「当前生效」的口径（对齐执行侧）

执行侧 `backend/services/collection_config_execution.py::create_tasks_for_config` 推任务时：

1. 只认 `CollectionConfig.is_active == True`；
2. 店铺范围行按 `scope.enabled` 过滤；**一条启用的范围行都没有 ⇒ 不建任何任务**；
3. 真正用的域清单是 **店铺范围行的 `data_domains`**（再按店铺 capability 过滤）。

⇒ 本批次把「当前采集范围」定义为：

> **生效配置**（`is_active IS TRUE`）的**启用店铺范围行**（`enabled IS TRUE`）的
> `data_domains` 并集；某个配置**一条店铺范围行都没有**时，退回该配置自身的 `data_domains`
> （配置还没展开到店铺这一步）。

### 2.3 兜底与标注

- 数据库读不到（表不存在 / 连接失败）⇒ 兜底到 `DEFAULT_CONFIG_DATA_DOMAINS`，
  且 `scope_source = "fallback_default_domains"`，在 `to_summary()` 与运行日志 `context` 里**看得见**。
- 读到了表但**没有任何生效配置** ⇒ `platform_known = False` ⇒ 任何链都**判不了**（落 `unknown`），
  **不许**把告警整体静音。
- **不新建第三份定义**：代码里的 `DEFAULT_CONFIG_DATA_DOMAINS` **一个字节都没改**。

### 2.4 订单域的例外（复用既有 SSOT）

`backend/services/collection_contracts.py` 的 `ORDER_SOURCE_PROVIDER_BY_PLATFORM`
（shopee/tiktok 的订单由 **miaoshou** 采集器写入）**继续生效**：
判「shopee/orders 在不在采」时按 **miaoshou 的范围**算。
否则会把**正在正常更新**的订单链误判成「已停采」。

---

## 3. 分档口径

新增一档 `out_of_scope`（**曾采过、现已不在当前采集范围**）：

| 判定顺序 | 条件 | 结论 | 是否拉高红灯 |
|---|---|---|---|
| 1 | `row_count == 0`（从未被采过） | `empty`（**既有行为不变**） | ❌ |
| 2 | 域不在当前采集范围，且该平台**有**生效配置 | `out_of_scope`（新增） | ❌ |
| 3 | 平台/域解析不出来，或该平台**没有**生效配置 | 落回 `fresh` / `stale`（`unknown`） | 视新鲜度 |
| 4 | 落后天数 > 允许滞后上限 | `stale` | ✅ |
| 5 | 其余 | `fresh` | ❌ |

**阈值一条都没改**：分档只决定「结论落在哪一档」，不碰粒度默认、链级例外、环境变量覆盖。

### 3.1 改造前后对照表（本地开发库实测，now = 2026-11-11）

| 链（表） | 改造前 | 改造后 | 说明 |
|---|---|---|---|
| `fact_miaoshou_analytics_daily/weekly/monthly` | `empty`（skipped） | `empty`（skipped） | 空表优先，行为不变 |
| `fact_miaoshou_products_*` / `fact_miaoshou_services_*` | `empty`（skipped） | `empty`（skipped） | 同上 |
| `fact_shopee_inventory_snapshot` / `fact_tiktok_inventory_snapshot` | `empty`（skipped） | `empty`（skipped） | 同上 |
| `fact_miaoshou_purchase_*` | `empty`（skipped） | `empty`（skipped） | `purchase` 不在解析词表 ⇒ scope 判 `unknown` |
| `fact_shopee_orders_daily/monthly/weekly` | `fresh` | `fresh` | 订单由 miaoshou 采集 ⇒ 仍在范围内 |
| `fact_shopee_products_daily` | `stale`（红灯） | `stale`（红灯） | 域仍在采集范围内 ⇒ 真断流，不能藏 |
| `fact_shopee_products_monthly` | `stale`（红灯） | `stale`（红灯） | 同上 |
| `fact_shopee_services_agent_monthly` | `stale`（红灯） | `stale`（红灯） | 同上 |
| `fact_tiktok_products_daily` / `_monthly` | `stale`（红灯） | `stale`（红灯） | 同上 |
| `fact_tiktok_services_agent_monthly` | `stale`（红灯） | `stale`（红灯） | 同上 |
| **任一「域已停采、但表里还有历史数据」的链** | `stale`（**拉高红灯**） | **`out_of_scope`（不拉高红灯，台账里留痕）** | **本批次的核心改动** |

> 本地开发库里没有「有数据 + 域已停采」的链（所有已停采的域对应的表都是空表），
> 所以本地 `out_of_scope` 计数为 0、红灯条数不变。**这正是期望的诚实结果**：
> 本地这 6 条红灯链的域**确实仍在采集配置里**，它们是真的断流，不该被分档藏起来。

### 3.2 台账口径

- `ops.pipeline_run_log.status`：只有 `stale` 才 `partial_failed`；`out_of_scope` ⇒ 仍 `success`。
- `ops.pipeline_step_log.status`：`fresh`→`success`、`stale`→`failed`、
  `empty`→`skipped`、**`out_of_scope`→`skipped`**（不是失败，也不是成功），并在
  `error_message` 留痕 `out_of_scope_source_chain: ...`。

---

## 4. 通知出口（复用现成通道，不新造体系）

### 4.1 复用的通道

| 通道 | 入口 | 说明 |
|---|---|---|
| 站内信 | `backend/domains/platform/routers/notifications.py::create_notifications_for_admins` + `NotificationType.SYSTEM_ALERT` | 枚举早就预留好，此前零调用 |
| webhook / 钉钉 | `backend/services/alert_service.py::send_resource_alert` | 自带**进程内冷却**（`RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES`） |

**明确不用**：

- ⚠️ **`AlertRule`（`core.alert_rules`）**：只有 CRUD、**没有求值器**（前端写「开发中」）
  ⇒ 当不了现成通道。已在代码注释里写明，**别让它继续冒充 SSOT**。
- **飞书投影**（`feishu_projection_service`）：它是「业务记录 → 飞书多维表格」的**业务投影**
  （`entity_type` + 表 id + 字段映射），不是告警消息通道；接它要新增表与字段映射
  ⇒ 等于另造一套通知体系。

### 4.2 去重（不轰炸）

去重状态落在**既有的运行日志**里（**不加表、不加迁移**）：

```
ops.pipeline_run_log.context.notified_stale_chains
```

| 场景 | 行为 |
|---|---|
| 同一问题连续多轮断流 | 只在**第一次**通知；后续轮次读到 `notified_stale_chains` ⇒ 不再通知 |
| 链恢复（不再断流）后再次断流 | **重新通知**（它已不在上一轮的通知集合里） |
| 两条通道都失败 | 不记入已通知集合 ⇒ 下一轮重试 |

### 4.3 脱敏

通知内容里**只有**：链名、源表名、落后天数、允许滞后上限、巡检 `run_id`。
**连接串、口令、token、原始数据行一律不进通知**；另有
`mask_sensitive_text()` 做形态级兜底（`://user:pass@` ⇒ `://***:***@`，
`password=…` / `token=…` ⇒ `***`）。

---

## 5. 守护测试

`backend/tests/data_pipeline/test_source_freshness_tiering.py`（17 个用例）：

| # | 用例 | 断言 |
|---|---|---|
| 1 | 已停采的链分档正确 | `status == "out_of_scope"`、`scope_status == "out_of_scope"`、`is_success is True`、运行日志 `status == "success"`、步骤日志 `status == "skipped"` |
| 2 | 还在范围内的链照旧报警 | `status == "stale"`、`is_success is False` |
| 3 | **从没有被采过的链仍是 skipped（既有行为不许变）** | `status == "empty"`、步骤日志 `status == "skipped"`、不进 `partial_failed` |
| 4 | 不传 scope 时判定口径与改造前一致 | `classify_source_freshness` 三态断言 |
| 5 | 采集范围**从数据库读** | `scope_source == "database"`、SQL 含两张表名与 `is_active IS TRUE` |
| 6 | 数据库读不到 ⇒ **走兜底且结果里能看出用了兜底** | `scope_source == "fallback_default_domains"` + 摘要里的 `scope_detail` |
| 7 | 没有任何生效配置 ⇒ 不许把告警静音 | `scope_status == "unknown"`、仍判 `stale` |
| 8 | 订单域按真实采集器判范围 | `shopee/orders` ⇒ `in_scope` |
| 9 | 阈值：粒度默认 | 365/365/60/10 |
| 10 | 阈值：链级例外 | `shopee/products[daily] == 30` |
| 11 | 阈值：环境变量覆盖 | `SOURCE_FRESHNESS_MAX_AGE_MONTHLY` / `SOURCE_FRESHNESS_MAX_AGE_CHAINS` |
| 12 | 分档不动阈值数值 | `out_of_scope` 链的 `max_age_days` 仍是 30 |
| 13 | **通知去重：连续两轮同一问题只发一次** | 第一轮 2 次调用（站内信 + webhook），第二轮 0 次 |
| 14 | 已停采的链不通知 | 0 次调用 |
| 15 | 恢复后再次断流 ⇒ 重新通知 | 第 3 轮重新通知 1 次 |
| 16 | 通知内容脱敏 | 载荷里不含口令/token |
| 17 | 载荷只有安全字段 | 不含 `raw_data` |

---

## 6. 遗留问题与风险

| # | 问题 | 影响 | 处置 |
|---|---|---|---|
| 1 | 店铺维度再收窄（`core.shop_accounts.enabled`）未纳入范围判定 | 停用店铺的域仍算「在采」 | 保守方向（不会误静音），留 V2 |
| 2 | 采集配置**整个平台停用**时 → 该平台落 `unknown`（不是 `out_of_scope`） | 平台整体停用不会自动降档 | 保守方向；需业务确认「整体停用」是否算停采 |
| 3 | 域解析词表 `_DOMAINS` 不含 `purchase` | `fact_*_purchase_*` 的 scope 落 `unknown` | 不影响结论（表都是空表 ⇒ `empty`）；留 V2 |
| 4 | `granularity='manual'` 的表没有对应配置粒度 | 范围判定只看域、不看粒度（与 `data_domains` 口径一致） | 有意为之：范围 = 域集合 |
| 5 | `semantic.fact_analytics_monthly_atomic`（VIEW）**不在**巡检对象内 | 语义层的可解析性问题由批次 3.2 负责 | 本批次不碰 |
| 6 | `AlertRule` 仍是空壳 | 以后要接规则引擎得先补求值器 | 已在代码注释里标注，**不假装它是 SSOT** |
| 7 | 飞书告警通道未接 | 告警只到站内信 + webhook/钉钉 | 飞书投影是业务记录投影，接它=新造体系；另开批次 |
