# 最低售价变更 → 飞书多维表格通知闭环

**状态**: 已实现
**日期**: 2026-10-23
**范围**: 商品中心定价链路（`backend/domains/business/routers/product_center.py`、`backend/services/product_pricing_service.py`、`backend/services/sku_pricing_policy_service.py`）、新增共享取数层（`backend/services/product_pricing_query_service.py`、`backend/services/inventory/inventory_age_query_service.py`）、新增检测服务（`backend/services/price_adjust_notify_service.py`）、新增每日任务（`backend/tasks/price_adjust_notify_tasks.py`）、飞书投影（`backend/services/feishu_projection_service.py`、`backend/services/feishu_projection_client.py`）、schema（`modules/core/db/schema_parts/dimensions.py`、`modules/core/db/schema_parts/collection.py`）、迁移（`current_migrations/versions/20261023_price_adjust_notification.py`）、调度（`backend/celery_app.py`）。

**非范围**:
- 不做平台 SKU 粒度（第一版按 **SKU 粒度**）
- ERP 侧**只新增**：不做 update、不删行、不管行归档到哪
- 不管飞书机器人怎么设置（归用户）
- 不做阈值筛选 / 批量熔断 / 聚合推送——**凡是最低售价变了的 SKU 全部通知**
- 不做「是否亏本」字段（当前售价数据源不完整，填了会大面积为空反而误导）
- 不做人工覆盖值的护栏校验（覆盖值 < 系统底线 = 亏本卖），列为独立小任务
- 不修改利润测算公式 `build_platform_profit_preview`

---

## 1. 背景与动机

### 1.1 现状

商品中心已经能算出每个 SKU 的「最低售价」（底线），但**这个数是读时计算的，不落库**：

- `backend/services/product_pricing_service.py` 的 `compute_sku_pricing` 每次调用现算
- 库里只有一个静态的**人工覆盖值** `core.dim_erp_sku.min_selling_price_override`
- 底线会随七类输入变化：库龄档位 / 采购成本 / 平台费率 / SPU 两个率 / 参考售价 / 档位规则 / 人工覆盖

结果是：系统能回答「现在最低卖多少钱」，但**从来没有回答过「比上次是高了还是低了」**。

### 1.2 为什么要通知

底线变化的业务含义不一样，运营要做的事也不一样：

| 变化 | 业务含义 | 运营动作 |
|---|---|---|
| 底线**下降** | 授权更低价卖（清货机会） | 考虑降价促销 |
| 底线**上升** | 收权。**若平台售价没跟上，就是在亏本卖** | 立刻核对并调价 |
| 从"算得出"变成"算不出" | 底线保护没了 | 补数据 |

底部上升是最危险的一种：库存照卖、售价照旧，但成本已经吃掉利润。这类事如果没人盯着，月底才发现就是真金白银的亏损。

### 1.3 闭环

```
ERP 每日检测  ──►  飞书多维表格新增一行  ──►  人工勾选「完成」  ──►  飞书机器人归档
   (只新增)                (只新增，不改不删)                        (机器人管，ERP 不管)
```

---

## 2. 设计决策

### 2.1 零遗漏：不筛，系统只排序不丢弃

用户明确要求：**凡是最低售价变了的 SKU，全部通知**。

所以系统**不做任何前置筛选**——没有幅度阈值、没有批量熔断、没有「只通知重要的」。重要度不靠系统丢弃来体现，而是**作为字段写进表里**（「变动幅度」「变动方向」「变动原因」「库龄天数」「库存数量」「库存金额」），由运营自己在飞书里排序。

理由：系统判断「这条重不重要」的依据只有数值阈值，而阈值必然有边界情况——边界上被丢掉的那条，恰恰是运营最该看的。反过来，多推几条的代价只是运营多扫一眼表。

唯一被排除的是**语义上根本不成立的变更**（见 §2.5），那不是筛选。

### 2.2 ERP 只新增：没有补救动作，所以基线顺序不能反

ERP 侧只往飞书**新增**行，不 update、不删除、不管理 record_id。行归档由机器人负责。

这带来一个硬约束：**没有"重写旧行"这个补救动作**。所以基线推进的顺序不能反——

> 必须**投递成功之后**才回写基线。

否则飞书写失败（限流 1254291、网络抖动、token 过期）时基线已被推进，那次变化就永远不会再被检出，等于把**最该通知的变化静默吞掉**。

实现上复用现有的 outbox（`ops.feishu_projection_tasks`），分成两个事务：

1. **检测**：算价 → 比对基线 → 产出变更集 → 静默推进基线 → 建 outbox 任务 → commit
2. **投递**：批量新增到飞书 → 投递成功后回写基线 → commit

投递失败时任务**留在 outbox 里**等重试，不与检测结果一起回滚。

### 2.3 口径一致是结构性保证，不是靠一条测试

「商品中心按日常档显示、通知却按滞销档发」是最容易被忽略、但业务上最伤的一类 bug：两边各自实现一遍取数和算价，一旦分叉，页面和通知就自相矛盾，运营根本没法信。

本实现的处理是把取数与计算**收敛成一个模块**：

```
backend/services/product_pricing_query_service.py   ← 唯一实现
├── load_pricing_context(db, sku_ids)                取规则行 / 平台费率 / 库龄
├── compute_pricing_state(...)                       算价 + 命中的档位
└── compute_pricing_for_sku(...)                     只要定价字段

调用方：
├── backend/domains/business/routers/product_center.py
│     from ... import compute_pricing_for_sku as _compute_pricing_for_sku
│     from ... import load_pricing_context as _pricing_context
└── backend/services/price_adjust_notify_service.py
```

两边调用的是**同一个函数对象**——不是"照着写了两份一样的代码"。这条约束由
`backend/tests/test_price_adjust_notification.py::test_router_and_detection_share_one_pricing_implementation`
守着，且该用例跑在 **SQLite** 上，不依赖 pg 容器，任何环境都能验证。

库龄取数同理，收敛在 `backend/services/inventory/inventory_age_query_service.py`。

### 2.4 归因：固定优先级，取第一个匹配的

底线变了，运营要知道**主要因为什么**。归因用固定优先级，**不做贡献度拆解**（那需要大量额外计算和字段，而业务上运营只需要知道"主要因为什么"）：

| 顺序 | 变动原因 | 判据 |
|---|---|---|
| 1 | 数据缺失 | 降级链状态变了（缺料项集合不同） |
| 2 | 人工覆盖 | 人工接管 / 交回 |
| 3 | 采购成本 | 采购成本变了 |
| 4 | 平台费率 | 平台其他成本率 / 达人佣金率变了 |
| 5 | 库龄档位变化 | 命中的档位本身变了（跨档） |
| 6 | 规则调整 | 档位没变但折扣率变了 |
| 7 | 参考售价补齐 | 参考售价变了（纪律线开始生效） |
| 兜底 | 规则调整 | 目标利润率在同一档被改了 |

优先级从「最具体」到「最宽泛」：单个 SKU 的输入 → 全局规则 → 库龄档位。

**为什么需要上下文快照**：只存最低售价无法归因——无法区分「是库龄跨档了」还是「是采购成本变了」。所以新增 `last_notified_context` JSON 列，存归因需要的全部输入。

**payload 不含时间戳**：outbox 的 payload 哈希是去重依据，带时间戳会让同一次变化重跑时哈希不同、去重失效。「变动时间」由投递时取 outbox 任务的 `created_at` 补上。

### 2.5 排除「下架造成的跳高」

场景：库存清零 → 该 SKU 从库龄表消失 → 库龄回落第 1 档（日常，目标利润率最高）→ 底线跳回全档最高位。

但这个品**已经不卖了**，底线高低没有业务含义。不排除的话，机器人会持续收到"某个已下架的品，底线从 ¥90 涨到 ¥128"的通知。

判定：库龄来源从 `age_data` 变成 `fallback_no_age_data`，**且其它定价输入一个都没变**。只要还有别的输入也变了，这次变化就不只是"下架"造成的 → 仍然要通知。

**排除不是"筛选"**：排除的是语义上根本不成立的变更（已下架的品没有亏钱风险）。

但**基线仍要静默推进**——否则明天还会重复判定为同一次跳高，后续真实的变化反而被噪音挡住。

### 2.6 每天全量比对，不跟库龄同步触发

底线输入有七类，只有**库龄**是周节奏（库存采集每天，但库龄档位边界稀疏），其余都是事件驱动（成本录入、费率调整、规则改版、人工覆盖）。

所以每天全量比对一次 = 任何输入变化**最迟当天被抓住**。全天 1118 个 SKU 的算价成本可以接受。

调度时间定在 **10:00**，给 09:00 的库存采集留出缓冲（采集当天库龄才会真的前进）。

### 2.7 第一版不填「平台」「当前售价」

- **平台**：第一版按 SKU 粒度推送。平台粒度需要售价数据源打通后再细化。
- **当前售价**：目前没有可靠数据源——`SkuOperatingProfile.selling_price` 靠人工维护、覆盖率未知；`api.sku_clearance_ranking_module` 视图里没有售价列。**填一个可能错的数比留空更危险**。

同理**不加「是否亏本」字段**：当前售价数据源不完整，加了会大面积为空，反而误导。

---

## 3. 数据模型

### 3.1 ERP 侧新增

| 位置 | 字段 | 类型 | 用途 |
|---|---|---|---|
| `ops.price_adjust_baselines` | `sku_id` | `Integer`（PK） | 基线主键，对应 `core.dim_erp_sku.sku_id` |
| `ops.price_adjust_baselines` | `last_notified_min_price` | `Numeric(18,2)` | 上一次已处理的最低售价基线（NULL = 当时算不出，本身是有效基线） |
| `ops.price_adjust_baselines` | `last_notified_context` | `JSON` | 上一次已处理的定价输入快照（归因用） |
| `ops.feishu_projection_configs` | `price_adjust_table_id` | `String(64)` | 「调价记录表」的表 id |
| `ops.feishu_projection_configs` | `price_adjust_base_token` | `String(64)` | 该表所在的 base（留空回落 `FEISHU_PRODUCT_BASE_TOKEN`） |

**为什么基线单独一张表、而不是挂在 `core.dim_erp_sku` 上**（这是本次改动的一个关键决策，理由见 §5.6）：

商品中心的 SKU 主数据有一条「采集机 → 云端」的同步链路，它对 `core.dim_erp_sku`
做的是 **TRUNCATE + 全量重灌**。基线若住在那张表里，每次同步都会被抹成"从未处理过"，
**同步窗口内真实发生的底线变化会被静默吞掉** —— 与"一个都不能漏"直接冲突。
所以基线搬到 `ops` 域：它与 `feishu_projection_tasks`（通知 outbox）同域，语义一致
（都是"通知进度状态"，不是"商品主数据"），且不参与商品中心同步。

`price_adjust_table_id` 独立成列而不是复用现有三个镜像表 id：镜像是**按业务键 upsert**（覆盖更新），调价记录是**只增不改**（追加 + 机器人归档），语义不同。

迁移：
- `current_migrations/versions/20261023_price_adjust_notification.py`
  （revision `current_schema_20261023_price_adjust_notification`，down_revision `current_schema_20261021_inventory_template_v3`）——
  只加 `ops.feishu_projection_configs` 的两个配置列。
- `current_migrations/versions/20261024_price_adjust_baseline_table.py`
  （revision `current_schema_20261024_price_adjust_baseline_table`）——
  建 `ops.price_adjust_baselines`、**搬迁**旧基线数据（若存在）、**删掉** `core.dim_erp_sku` 上的两个旧列。
  建表、搬数据、删列都带存在性检查，**幂等**；downgrade 反向执行。

### 3.2 飞书侧

Base `UCRbbZSy2a3iXvsS7O8cxyBJnnb` / Table `tblRDvcTUjfOLkBH` / 表名「调价记录表」。**19 个字段，0 条记录**（原为空壳：默认「文本」字段 + 5 条空记录，空记录已删除）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `ERP SKU` | text（主字段） | 每次变化新增一行 |
| `SPU` | text | |
| `商品名称` | text | |
| `规格` | text | |
| `平台` | select | **第一版不填**（见 §2.7） |
| `上次最低售价` | currency CNY | |
| `新最低售价` | currency CNY | |
| `变动幅度` | number % | （新 − 旧）÷ 旧，负数 = 下降 |
| `变动方向` | select | 下降 / 上升 / 保护失效 |
| `变动原因` | select | 库龄档位变化 / 采购成本变化 / 平台费率变化 / 规则调整 / 参考售价补齐 / 数据缺失 / 人工覆盖 |
| `库龄天数` | number | |
| `命中档位` | text | |
| `当前售价` | currency | **第一版不填**（见 §2.7） |
| `库存数量` | number | |
| `库存金额` | currency | |
| `变动时间` | datetime | 取 outbox 任务的 `created_at` |
| `完成` | checkbox | **机器人监听这一列** |
| `处理人` | user | |
| `备注` | text | |

### 3.3 飞书 API 硬约束（**实测** + 官方文档）

> ⚠️ 2026-10-23 对真实表逐项实测过一轮，下面几行是**测出来的**，
> 其中两行与文档正文不一致——踩坑记录见 §5.4。

| 约束 | 值 | 错误码 | 应对 |
|---|---|---|---|
| **写入端点** | **`/open-apis/base/v3/bases/{base_token}/tables/{table_id}/records/batch_create`** | — | body key 是 `create_records` |
| ~~旧端点~~ | ~~`/open-apis/bitable/v1/apps/{token}/tables/{id}/records/batch_create`~~ | `99992402` | **不可用**，见 §5.4 |
| 单表记录数上限 | 20,000 | 1254103 | 行由机器人归档，ERP 侧不会堆积 |
| 单次批量添加 | **200**（base/v3 的上限，比旧版 bitable/v1 的 500 小） | 1254104 | 分块 |
| 批量新增频率 | 50 次/秒 | | |
| **同表不支持并发写** | — | 1254291 | **串行 + 块间 0.6 秒间隔** |

### 3.4 调价记录表在**哪个**多维表格

「调价记录表」建在 `UCRbbZSy2a3iXvsS7O8cxyBJnnb`（团队协作 base），而三张状态镜像表
（ERP-SPU经营 / ERP-SKU经营明细 / ERP-平台SKU利润）在**另一个** base——实测过
`UCRbbZSy2a3iXvsS7O8cxyBJnnb` 里 12 张表，只有「调价记录表」是 ERP 相关的。

所以 base token 必须**能独立配置**：

| 位置 | 字段 | 类型 | 用途 |
|---|---|---|---|
| `ops.feishu_projection_configs` | `price_adjust_table_id` | `String(64)` | 调价记录表的表 id |
| `ops.feishu_projection_configs` | `price_adjust_base_token` | `String(64)` | 调价记录表所在的 base；**留空回落** `FEISHU_PRODUCT_BASE_TOKEN` |

留空回落是为了不破坏既有三张镜像表的配置（它们共用 `FEISHU_PRODUCT_BASE_TOKEN`）。

---

## 4. 实现清单

### 4.1 新增文件

| 文件 | 职责 |
|---|---|
| `backend/services/product_pricing_query_service.py` | 定价取数与计算的**唯一**实现（§2.3） |
| `backend/services/inventory/inventory_age_query_service.py` | 库龄取数的**唯一**实现（容错：to_regclass 探测 + SAVEPOINT） |
| `backend/services/price_adjust_notify_service.py` | 检测服务：纯函数（方向/幅度/归因/排除）+ 服务类（取数/比对/推进基线） |
| `backend/tasks/price_adjust_notify_tasks.py` | 每日 Celery 任务，两段式 |
| `current_migrations/versions/20261023_price_adjust_notification.py` | 加 `ops.feishu_projection_configs` 的两个配置列 |
| `current_migrations/versions/20261024_price_adjust_baseline_table.py` | 建 `ops.price_adjust_baselines` + 搬迁旧基线 + 删旧列 |
| `backend/tests/test_price_adjust_notification.py` | 37 条非 pg 测试 + 1 条 pg_only 一致性测试 |

### 4.2 修改文件

| 文件 | 改动 |
|---|---|
| `backend/domains/business/routers/product_center.py` | `_pricing_context` / `_compute_pricing_for_sku` 改为 import 共享实现；删掉本地的 `_load_age_days_by_sku` |
| `backend/services/feishu_projection_client.py` | 新增 `batch_create_records()`（只新增、200/批、串行、间隔 0.6s） |
| `backend/services/feishu_projection_service.py` | `set_initialized` / `initialize_tables` / `status` 支持 `price_adjust_table_id`；新增 `_price_adjust_payload` / `_advance_price_adjust_baseline` / `_process_price_adjust_tasks`；`process_pending` 里 price_adjust 走批量、其余实体仍走原 upsert 路径；`_advance_price_adjust_baseline` 复用 `PriceAdjustNotifyService.advance_baseline_for_sku`（基线读写只有一处实现） |
| `backend/celery_app.py` | include 加任务模块；task_routes 加规则；beat_schedule 加 `price-adjust-notify-daily`（每天 10:00） |
| `backend/schemas/product_center.py` | `FeishuProjectionInitializeRequest` 加 `price_adjust_table_id` |
| `modules/core/db/schema_parts/dimensions.py` | `DimErpSku` **移除** `last_notified_min_price` / `last_notified_context` 两列（基线已搬到 `ops`） |
| `modules/core/db/schema_parts/collection.py` | `FeishuProjectionConfig` 加两个配置列；**新增** `PriceAdjustBaseline` 模型（schema=`ops`） |
| `modules/core/db/schema.py` | 导出 `PriceAdjustBaseline` |
| `env.example` / `env.development.example` | 补 `FEISHU_PRODUCT_PLATFORM_SKU_PROFIT_TABLE_ID`（原本代码引用但示例缺失）与 `FEISHU_PRODUCT_PRICE_ADJUST_TABLE_ID` / `FEISHU_PRODUCT_PRICE_ADJUST_BASE_TOKEN` |

### 4.3 关键实现细节

**分块成败独立**：`_process_price_adjust_tasks` 按 200 条分块（实测上限，见 §3.3），**每块独立成败**。不能"整批一次调用、失败就把所有任务标 failed"——第 3 块失败时第 1、2 块（400 行）其实已经写进飞书了，被一起标 failed 后重试会再写一遍。调价记录表是只增不改的，重复行不会被覆盖，只会一直堆着。

**基线读写只有一处实现**：批量推进走 `PriceAdjustNotifyService.advance_baselines`（一次 SELECT + 内存 upsert + flush），单条推进走 `advance_baseline_for_sku`（投递成功后回写）。后者被 `feishu_projection_service._advance_price_adjust_baseline` 直接复用——**不让"回写基线"这件事有两份实现**。单条推进用「先查后写」而不是方言专属的 `ON CONFLICT`：基线写入是低频（每天一次 × 变更数）且由单个任务串行执行，先查后写在 PostgreSQL / SQLite 上行为一致，不必写两套方言分支。

**在途去重闸**：`_existing_price_adjust_sku_ids` 检出已有在途任务的 SKU，避免为同一次变化反复建任务（payload 哈希相同撞唯一约束，或产生重复通知行）。

**无库龄的处理**：`select_age_tier(policies, None)` 与 `select_age_tier(policies, 0)` **都选第 1 档**，所以"库里没有这个 SKU"和"这个 SKU 库龄是 0 天"落到同一档，不会因为缺数据产生虚假的跨档跳变。

---

## 5. 验证

### 5.1 测试结果

| 范围 | 结果 |
|---|---|
| `backend/tests/test_price_adjust_notification.py` | **37 passed**（非 pg）+ 1 条 pg_only 用例在本机失败（环境问题，见 §5.2） |
| `backend/tests/test_product_pricing_guardrails.py` | 10 failed / 33 passed / 10 errors —— **与改动前基线完全一致** |
| `tests/test_current_schema_migration_contract.py` | 31 passed |
| 其余受影响的既有测试（商品中心、定价契约、迁移契约、schema 契约） | 全部通过 |
| **对真实飞书表写入 → 读回逐字段比对** | **14 个字段全部一致**（见 §5.4） |
| **基线换表后真实库复跑** | 1122 条基线全部命中，**0 通知 + 0 静默**（见 §5.6） |

### 5.2 环境既有的失败（**非本次引入**）

`test_product_pricing_guardrails.py` 的 10 failed / 10 errors 是 **Windows + pytest-asyncio + testcontainers** 的事件循环问题（`attached to a different loop` / `another operation is in progress`），与本次改动无关。

验证方式：`git stash push -u` 取改动前状态跑同一个文件，结果**完全相同**（10 failed / 33 passed / 10 errors），随后 `git stash pop` 完整恢复。

`test_schema_ssot_import_contract.py` 与 `test_platform_sku_profit_workbench.py` 的 4 个失败同样是既有失败（基线一致），原因分别是 `ShopAccountBusinessRole` 导出面不一致、利润测算预估口径，均与本次改动无关。

因此新增的口径一致性测试**特意做成 SQLite 版**，不依赖 pg 容器——在本机就能真正验证"页面与通知算出的最低售价相等"。

### 5.3 其它已验证项

- 导入检查：`backend.services.product_pricing_query_service`、`backend.services.price_adjust_notify_service`、`backend.tasks.price_adjust_notify_tasks`、`backend.domains.business.routers.product_center` 全部可导入
- 同一实现校验：路由的 `_compute_pricing_for_sku.__module__` == 通知服务的 `compute_pricing_state.__module__` == `backend.services.product_pricing_query_service`
- Celery：任务注册成功、queue = `scheduled`、beat schedule = 每天 10:00、task_routes 命中
- 飞书表：字段结构与实际写入已通过 `lark-cli` 实测

### 5.4 真实表写入实测（2026-10-23）

代码写完后**没有**只靠单测就收工——对着真实表打了一轮，发现并修掉了两个会让功能 100% 失效的问题。

**测法**：用生产代码 `_price_adjust_payload` 生成 payload → 用 httpx `MockTransport`
捕获 `FeishuProjectionClient.batch_create_records` 真实发出的 HTTP 请求 → 把捕获到的
body 原样打到真实表 → 读回逐字段比对 → 删除测试记录。

**发现一：写入端点错了**

| 端点 | body key | 结果 |
|---|---|---|
| `/open-apis/bitable/v1/apps/{token}/tables/{id}/records/batch_create` | `records` | ❌ `99992402 field validation failed` |
| `/open-apis/bitable/v1/apps/{token}/tables/{id}/records/batch_create` | `create_records` | ❌ `99992402 field validation failed` |
| `/open-apis/base/v3/bases/{token}/tables/{id}/records/batch_create` | `records` | ✅ OK |
| `/open-apis/base/v3/bases/{id}/tables/{id}/records/batch_create` | `create_records` | ✅ OK |

**连只带主字段的最小请求在旧端点都被拒** → 与字段内容无关，是端点本身的问题。
按错误码表，「单次添加记录数量超限」是 1254104，这里返回的是 99992402
（`invalid_parameters` / `field validation failed`），不是容量类错误。

**修法**：端点换成 `base/v3`，body key 用 `create_records`。由
`test_client_uses_base_v3_endpoint_and_create_records_key` 守着，防止回退。

**发现二：单次上限不是 500**

旧版 bitable/v1 的文档写 500，但 **base/v3 的上限是 200**（`lark-cli` 的类型化命令
明确提示 "Batch create supports max 200 records per call"）。`FEISHU_BATCH_CREATE_LIMIT`
因此从 500 改为 200。

**发现三：调价记录表不在镜像表那个 base**

实测 `UCRbbZSy2a3iXvsS7O8cxyBJnnb` 下共 12 张表（作战日历 / 常规待办 / 项目 / 任务 /
成员 / Checklist / 调价记录表 / 三个归档表 / 店铺源数据 / 动作标准），**三张 ERP 状态
镜像表一张都不在这个 base 里**。若沿用 `FEISHU_PRODUCT_BASE_TOKEN` 写表 id，
URL 里的 base 与表对不上 → 必然失败。

**修法**：新增 `ops.feishu_projection_configs.price_adjust_base_token`（留空回落
`FEISHU_PRODUCT_BASE_TOKEN`），由 `test_price_adjust_uses_its_own_base_token_when_configured` 守着。

**发现四：「变动时间」的时区语义是对的**

`task.created_at` 是 UTC 的 `DateTime(timezone=True)`，payload 里写的是
`2026-10-23T10:00:00+00:00`。读回得到 `2026-10-23T18:00:00.000+08:00`
（飞书按 `Asia/Hong_Kong` 呈现）——**同一个瞬间**，没有 8 小时错位。

顺带记录一个无害现象：**飞书写入后立刻 `record-list` 可能读不到**（读一致性延迟，
几秒后可见）。ERP 侧只增不改、写入后不回读，**不受影响**；只是写验收脚本时
必须重试等待，否则会误判成"没写进去"。

**端到端比对结果**（写入 → 读回，14 个字段全部一致）：

| 字段 | 写入 | 读回 |
|---|---|---|
| ERP SKU / SPU / 商品名称 / 规格 | 文本 | 一致 |
| 上次最低售价 / 新最低售价 | 128.56 / 90.82 | 一致 |
| 变动幅度 | -0.293 | 一致 |
| 库龄天数 / 库存数量 / 库存金额 | 75 / 42 / 1898.4 | 一致 |
| 命中档位 | 滞销30天 | 一致 |
| 变动方向 / 变动原因 | `["下降"]` / `["库龄档位变化"]` | 一致（单选字段用数组） |
| 变动时间 | `2026-10-23T10:00:00+00:00` | `2026-10-23T18:00:00.000+08:00`（同一瞬间） |
| 平台 / 当前售价 / 完成 / 处理人 / 备注 | 未写 | null（第一版刻意不填 / 人工填） |

### 5.5 真实库首次运行（2026-10-23）

配置落地后，用**真实本地库**（1122 个 active SKU）跑了一次完整检测，又逮到一个 bug。

**跑出来的现状**：

| 项 | 结果 |
|---|---|
| 参与计算 | 1122 个 active SKU |
| 算出最低售价 | 1083（96.6%） |
| 算不出 | 39（缺采购成本 39；缺 SPU 绑定 4，有重叠） |
| 命中档位 | 全部「日常」——库龄表 495 行且 `age_days` 全为 0，其余 627 个无库龄回落第 1 档，**两边同档，无虚假跨档** |
| 首次运行 | **0 通知 + 1122 条静默建基线**（符合设计） |
| 第二次运行 | 0 通知 |

**发现五：基线判据用错了列**

第二次跑时，仍有 **39 条**在反复重建基线——正是那 39 个算不出最低售价的 SKU。

原因：基线判据用的是 `last_notified_min_price IS NOT NULL`，而算不出底线的 SKU
它的基线价格本来就是 NULL → 被永远当成"从未处理过"。后果有两个：

1. 每天重复重建这 39 条基线，白写一次库；
2. **更糟**：等某个 SKU 哪天**算得出**底线了（补了采购成本），它仍被当成首次建基线 →
   「底线从算不出变成算得出」这个变化**永远不会通知**。
   而 `classify_direction` 里"从无到有 = 收权 = 必须通知"这个分支，实际永远走不到。

**修法**：判据改成「**上下文快照存在**」（`last_notified_context IS NOT NULL`），
而不是「价格列非 NULL」——算不出底线的 SKU 同样被处理过、同样有上下文。

**修完复跑**：静默推进从 39 → **0**。

**顺带修掉一个耦合**：原 `process_pending` 要求三张状态镜像表的 id 齐全才干活，
否则 `return 0`——而调价记录表和三张镜像表分属不同多维表格、配置上互不依赖。
这会让「镜像表没配 → 调价记录也一行都写不出去，而且不报错」。
现在调价记录表的投递只看它自己的表 id，镜像路径另走自己的检查。

**新增测试**：
`test_protection_recovery_produces_a_notification`（保护恢复必须通知）、
`test_baseline_with_null_price_is_still_treated_as_processed`（基线判据）。

### 5.6 基线换表（发现六，2026-10-23）

做完 §5.5 之后又回头审了一遍架构，发现基线**住在 `core.dim_erp_sku` 上是个定时炸弹**。

**问题**：商品中心的 SKU 主数据有一条「采集机 → 云端」的同步链路
（`scripts/sync_product_center_to_cloud.py`），它对 `core.dim_erp_sku` 做的是
**TRUNCATE + 全量重灌**（保证两边数据完全一致）。

基线若住在那张表里，每次同步都会被抹成"从未处理过"：

- 系统重新建基线（不发通知）——看起来没事；
- **但同步窗口内真实发生的底线变化会被静默吞掉** —— 与"一个都不能漏"直接冲突。

也就是说，功能在本地能跑、一切正常，但**上云之后每天同步一次，每次同步都会漏掉一批变化**。
这种 bug 不会报错、不会告警，只会表现为"有些调价没通知"，很难查。

**修法**：基线搬到 `ops.price_adjust_baselines` 独立表：

| 维度 | 理由 |
|---|---|
| 域 | `ops` 域与 `feishu_projection_tasks`（通知 outbox）同域——都是"通知进度状态"，不是"商品主数据" |
| 同步 | 不在商品中心同步的 16 张表清单里 → **不会被 TRUNCATE** |
| 语义 | 基线判据是「**有没有基线行**」，而不是「价格列是不是 NULL」——算不出底线的 SKU 同样被处理过、同样有上下文 |

顺带把 `core.dim_erp_sku` 上那两列**删掉**：留着空列是隐患，以后有人看到"这里有基线字段"会以为它是生效的。

**迁移**：`current_schema_20261024_price_adjust_baseline_table.py`
——建表 + 搬迁旧基线 + 删旧列，全程带存在性检查，幂等。

**实测搬迁结果**（本地真实库，1122 条基线）：

| 项 | 迁移前（`core.dim_erp_sku`） | 迁移后（`ops.price_adjust_baselines`） |
|---|---|---|
| 基线行数 | 1122 | **1122** |
| 有上下文 | 1122 | **1122** |
| 有价格 | 1083 | **1083** |
| 旧列 | 存在 | **已删除** |

**换表后真实库复跑检测**：1122 个 active SKU 全部读到基线，
**0 通知 + 0 静默** —— 没有重复建基线，也没有误报变更。

---

## 6. 需要机器人侧配合的约定

ERP 侧只新增、不管归档，因此有两条约定要落在机器人上：

1. **监听「完成」列**：`完成` 从未勾选变为勾选时触发归档动作。
2. **归档去向由机器人决定**：ERP 不关心行最终归档到哪（视图 / 其它表 / 标记状态）。

另有一条**运维约定**：

1. `ops.feishu_projection_configs.price_adjust_table_id` = 「调价记录表」的表 id（`tblRDvcTUjfOLkBH`）
2. `ops.feishu_projection_configs.price_adjust_base_token` = 该表所在的 base（`UCRbbZSy2a3iXvsS7O8cxyBJnnb`）

**两个都必须配**，否则投递环节直接跳过（不报错，但也不会有行写进去）。
留空 base token 则回落到 `FEISHU_PRODUCT_BASE_TOKEN`——注意那是三张状态镜像表所在的
另一个 base，与「调价记录表」不是同一个。

环境变量对应项（初始化接口会自动读，也可以直接调接口传）：
`FEISHU_PRODUCT_PRICE_ADJUST_TABLE_ID` / `FEISHU_PRODUCT_PRICE_ADJUST_BASE_TOKEN`。

### 6.1 本地已落地的配置（2026-10-23）

| 位置 | 值 | 状态 |
|---|---|---|
| 本地库 `ops.feishu_projection_configs.price_adjust_table_id` | `tblRDvcTUjfOLkBH` | ✅ 已写入 |
| 本地库 `ops.feishu_projection_configs.price_adjust_base_token` | `UCRbbZSy2a3iXvsS7O8cxyBJnnb` | ✅ 已写入 |
| 本地库 `ops.feishu_projection_configs.status` | `ready` | ✅ 已写入 |
| 本地库迁移 | `current_schema_20261023_price_adjust_notification` | ✅ 已应用 |
| 本地库迁移 | `current_schema_20261024_price_adjust_baseline_table` | ✅ 已应用（1122 条基线已搬迁，旧列已删） |
| 本地 `.env` `FEISHU_PRODUCT_PRICE_ADJUST_TABLE_ID` | `tblRDvcTUjfOLkBH` | ✅ 已写入 |
| 本地 `.env` `FEISHU_PRODUCT_PRICE_ADJUST_BASE_TOKEN` | `UCRbbZSy2a3iXvsS7O8cxyBJnnb` | ✅ 已写入 |
| 本地 `.env` `FEISHU_PRODUCT_APP_ID` | `cli_a960b804ecf85bda` | ✅ 已写入（与 lark-cli 同一个应用） |
| 本地 `.env` `FEISHU_PRODUCT_APP_SECRET` | `7aXi…Fn7R`（32 位） | ✅ **已写入并实测可用**（2026-10-23，见 §6.4） |
| 本地 `.env` `FEISHU_PRODUCT_BASE_TOKEN` | — | ⬜ **待填**：三张状态镜像表所在的 base（**调价记录表不需要它**） |
| `ops.feishu_projection_configs.spu_table_id / sku_table_id / platform_sku_profit_table_id` | — | ⬜ **待填**：本地库从来没有初始化过飞书投影（这几张镜像表也不在调价记录表那个 base 里） |

**应用身份权限已实测**：用 lark-cli 的应用身份（`--as bot`）对「调价记录表」写入成功，
说明这个飞书应用对这张表有读写权限。

**镜像投影是既有的独立缺口**：outbox 里还堆着 12 条 2026-09 的 sku/spu 待投递任务
（镜像表一直没配，从来投不出去）。这不是本次引入的，也不影响调价记录这条线。

> ℹ️ `FeishuProjectionClient.is_configured()` 仍然返回 `False`——因为它要求
> `FEISHU_PRODUCT_BASE_TOKEN`（**镜像表**的 base）非空。
> 调价记录这条线不受影响：`batch_create_records()` 只要求 app 凭证 + 目标 base，
> 且目标 base 由 `price_adjust_base_token` 独立提供（代码里有专门注释说明，
> 不能用 `is_configured()` 把这条路径堵死）。
> 镜像表那条路径（`create_table` / `upsert_record`）在镜像 base 确认前保持不可用——
> 这是既有缺口，与本次无关。

### 6.2 由哪个环境发送：**云端 ERP**（已拍板）

| 环境 | 角色 | 跑不跑定时任务 |
|---|---|---|
| 采集机（`APP_RUNTIME_MODE=collector`） | 妙手采集落库 → 同步到云端 | **不跑 beat**（compose 明确"常驻角色仅限 backend-collector"） |
| **云端**（`backend-api` + `celery-worker` + `celery-beat`） | 算价、比对基线、写飞书 | **跑 beat**，每天 10:00 触发 `price-adjust-notify-daily` |

所以**发送方是云端 ERP**。采集机只负责把数据同步过去，不参与通知。

这也直接决定了基线必须搬出 `core.dim_erp_sku`（§5.6）：
同步链路每天跑一次，基线住在被 TRUNCATE 的表里，每同步一次就漏一批变化。

### 6.3 云端：配置已落地，**迁移仍推迟到部署时**

按用户指示，**云端库的迁移不执行**（那是新版本部署那一步的事）。
但**配置已经先填好了**（2026-10-23），这样新版本一部署就是通的：

| 项 | 云端现状（2026-10-23 实测） | 状态 |
|---|---|---|
| 云端 `.env` | 已追加 `FEISHU_PRODUCT_APP_ID` / `APP_SECRET` / `PRICE_ADJUST_TABLE_ID` / `PRICE_ADJUST_BASE_TOKEN` / `FEISHU_OPEN_BASE_URL`；原文件已备份为 `.env.bak.priceadjust.20261023` | ✅ 已落地 |
| `ops.feishu_projection_configs` | **原为空** → 已写入 1 行：`price_adjust_table_id=tblRDvcTUjfOLkBH`、`price_adjust_base_token=UCRbbZSy2a3iXvsS7O8cxyBJnnb`、`status=ready` | ✅ 已落地 |
| `ops.feishu_projection_configs` 两个列 | 原表**没有**这两列 → 已用**与迁移 20261023 完全相同**的 `ADD COLUMN` 补上（可空、纯新增） | ✅ 已落地 |
| `ops.price_adjust_baselines` | 原不存在 → 已用**与迁移 20261024 完全相同**的 DDL 建表 + 建索引（空表） | ✅ 已落地 |
| `docker compose config` 校验 | 通过（`.env` 语法与变量名都合法） | ✅ |
| 运行中的容器 | 仍是旧镜像 `v7.11.25`，**未重启**（重启也不会有变化——旧代码里没有这条线；新版本部署时才注入这些变量） | 预期内 |
| 迁移 | 落后 **5 个**：`20261020_sku_pricing_guardrails` / `20261021_sku_pricing_creator_commission` / `20261021_inventory_template_v3` / `20261023_price_adjust_notification` / `20261024_price_adjust_baseline_table` | ⬜ **部署时执行** |
| 定价规则表 | **没有** `finance.sku_pricing_policies` | ⬜ 迁移补齐后才有档位规则 |
| `core.dim_erp_sku` 定价列 | 缺 `min_selling_price_override` / `creator_commission_rate` | ⬜ 迁移补齐 |
| 结论 | **云端 ERP 现在连最低售价都算不出来** | ⬜ 补齐迁移后才有意义 |
| 库龄 | 云端 `mart.inventory_age_current` 495 行（锚点 2026-09-14） | ✅ 已有，够用 |

**为什么可以安全地"先建对象、不跑迁移"**：
`20261023` / `20261024` 都是**幂等**迁移——每个对象都有存在性检查
（`ADD COLUMN` 前查列、`CREATE TABLE` 前查表、搬迁数据前查列）。
部署时它们跑起来会发现对象已存在，直接跳过并盖章版本号，不会重复创建、不会报错。

**⚠️ 但迁移链里有一条不属于本功能**：`20261021_inventory_template_v3`
会改 `core.field_mapping_templates` 的数据（归档/删除/发布采集模板），
属于采集组件那条线的成果。所以**没有为了写一行飞书配置而把整条链在生产上跑一遍**——
只补了本功能自己需要的两个对象。

**顺序很重要**：部署时先补迁移（否则算不出底线）→ 再确认飞书配置（已就绪）→ 最后开 beat。

### 6.4 凭证与端到端实测（2026-10-23）

`APP_SECRET` 的来源：`F:/Work Tool` 项目下
`Team work/研发/项目产出/飞书机器人/README.md` 里记录了这个应用（`cli_a960b804ecf85bda`）
的 app secret（与本地 `lark-cli` 用的是同一个应用）。
本机 `lark-cli` 自己把它存在注册表 `HKCU\Software\LarkCli\keychain\lark-cli`
（DPAPI 加密，键名 `appsecret:<appId>`），无法直接读出明文——所以走文档里的明文来源。

**实测结果**：

| 检查 | 结果 |
|---|---|
| `POST /open-apis/auth/v3/tenant_access_token/internal` | ✅ `code=0`，拿到 tenant_access_token |
| 用该 token 读「调价记录表」 | ✅ `code=0` |
| **生产代码**（`_price_adjust_payload` + `batch_create_records`）写入真实表 | ✅ 写入 1 条 |
| 读回逐字段比对 | ✅ 14 个字段全部正确（含「变动时间」`2026-10-23T20:42:38.001+08:00`） |
| 清理测试行 | ✅ 表回到 **0 条** |

---

## 7. 已知限制与后续

| 项 | 状态 | 说明 |
|---|---|---|
| 平台 / 当前售价字段为空 | 第一版刻意如此 | 售价数据源打通后再细化 |
| 「是否亏本」字段 | 不做 | 当前售价数据源不完整 |
| 人工覆盖值护栏 | 独立小任务 | 覆盖值 < 系统底线 = 亏本卖，应有校验 |
| 库龄管道本身 | 独立任务 | 采集调度当前未开（`schedule_enabled=false`），库龄只有 1 帧 |
| 平台 SKU 粒度 | 后续版本 | 等售价数据源就绪 |
| 单表 20,000 行上限 | 靠机器人归档规避 | ERP 只增不删，行不归档的话迟早撞上限 |
| 云端库补迁移 | **部署时做** | 云端落后 5 个迁移，缺定价规则表 → 现在算不出底线（见 §6.3） |
| 云端飞书配置 | ✅ **已落地** | `.env` + `ops.feishu_projection_configs` 都已写入；只等迁移补齐后开 beat |
| 本地 `FEISHU_PRODUCT_BASE_TOKEN` | ⬜ 待填 | 三张状态镜像表的 base（未知）；调价记录表不依赖它 |
