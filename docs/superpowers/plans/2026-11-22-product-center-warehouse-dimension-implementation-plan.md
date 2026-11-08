# 商品中心 · 仓维度落地与前端列重排 —— 实施计划（阶段 6）

> 状态：已定稿，待实施
> 基线：`main` @ `004e1a62`（含 v7.15.5 / v7.16.0）
> 分支：`feature/product-center-stage6`（worktree `.worktrees/product-center-stage6`）
> 需求来源：Walter 问卷答复（2026-11-22）
>   Q1 同一 ERP SKU 在 TikTok SG 站与 MY 站 → **两个独立商品，各站可分别定价（按站点分开做）**
>   Q2 本轮先做 → ① 前端列重排 + 固定左侧三列 ② 库龄还原成 SKU×仓级 ③ 跨仓差异提示（优先调拨而非降价）

---

## 一、事实基线（全部经生产库/代码只读核查，非推测）

### 1.1 库存与仓维度

| 事实 | 值 | 来源 |
|---|---|---|
| `mart.inventory_state` 主键 | `(platform_code, sku_key, warehouse_name)` | `sql/mart/inventory_state.sql:45` |
| 生产 `platform_code` 取值 | 恒为 `miaoshou`（是数据来源，**不是销售渠道**） | 生产只读核查 |
| 生产 `warehouse_name` 取值 | `新加坡`、`马来仓`、`菲律宾1店-儿童书包`、`菲律宾仓库（维修工具）`、`菲律宾3店-时尚箱包` | 生产只读核查 |
| 生产行数 / SKU 数 | 1232 行 / 1122 SKU | 生产只读核查 |
| 跨仓 SKU | 105 个（2 仓 100 个 + 3 仓 5 个） | 生产只读核查 |
| 有库存（`available_stock>0`）行 | 518 行；库龄分档：<60天 351 行、60–90天 167 行 | 生产只读核查 |
| **SG 与 MY 同时有库存的 SKU** | **0 个**（sg_only=283、my_only=90） | 生产只读核查 |
| 有库存行中跨仓且库龄差 ≥60 天 | **0 个** | 生产只读核查 |

### 1.2 仓主数据与「仓↔站」桥

- `core.dim_warehouses`（`modules/core/db/schema_parts/dimensions.py:103`）5 行：
  `SG-01/新加坡仓/SG`、`MY-01/马来仓/MY`、`PH-01-CHILD`、`PH-REPAIR`、`PH-03-FASHION`（后三者 `country_code=PH`）。
- **仓名两边不一致**：`mart.inventory_state.warehouse_name` = `新加坡`/`马来仓`/`菲律宾1店-儿童书包`/…，
  `core.dim_warehouses.warehouse_name` = `新加坡仓`/`马来仓`/`菲律宾1店-儿童书包仓`/…
  → **必须显式归一，不能靠字符串拼接硬猜**。
- 归一可行性已验证：`mart.inventory_state` 5 个仓名 → `dim_warehouses` 5 个仓**一一对应无歧义**
  （`新加坡`→`SG-01`、`马来仓`→`MY-01`、`菲律宾1店-儿童书包`→`PH-01-CHILD`、
  `菲律宾仓库（维修工具）`→`PH-REPAIR`、`菲律宾3店-时尚箱包`→`PH-03-FASHION`）。
- **仓↔站桥已存在**：`core.dim_warehouses.country_code`（SG/MY/PH）
  ↔ `core.dim_shops.region`（SG/MY/PH/VN/TH/TW/…）。
  `core.shop_accounts.shop_region` 同口径（TikTok 有 FIORO/KIDD0 × SG/MY/PH 六站）。
  ⇒ **不需要新建任何映射表**。

### 1.3 定价链路现状（问题定位）

| 环节 | 粒度 | 仓维度 | 位置 |
|---|---|---|---|
| `mart.inventory_state` | SKU×仓 | ✅ | `sql/mart/inventory_state.sql` |
| 库龄取数 `load_current_restock_days` | **SKU 级跨仓取 MAX** | ❌ **压平点 1** | `backend/services/inventory/inventory_restock_query_service.py:35-43` |
| 清货排名视图 `api.sku_clearance_ranking_module` | **SKU 级跨仓 MAX** | ❌ **压平点 2** | `sql/api_modules/sku_clearance_ranking_module.sql:70` |
| 经营档案 `finance.sku_operating_profiles` | SKU×平台×仓 | ✅ | `modules/core/db/schema_parts/business.py:1194` |
| 平台级人工覆盖 `finance.sku_platform_pricing` | SKU×平台 | ❌ | `business.py:1263` |
| 调价基线 `ops.price_adjust_baselines` | SKU×平台 | ❌ | `collection.py:1197` |
| 商品中心测算接口 | 平台×仓（`warehouse_code` **必填**） | ✅ | `product_center.py:4059` |
| 飞书投影去重键 | SKU×平台 | ❌ | `backend/tasks/price_adjust_notify_tasks.py:65` |

**结论**：`product_center.py:4169` 的 `_pricing_context(db, sku_ids, [platform_code])` **没有传仓**，
所以「新加坡仓视图」看到的底线，用的是**全仓最长库龄**——马来仓滞销 120 天 ⇒ 新加坡仓底线被压到滞销档。
**这就是 Walter 描述的 bug 的确切机制。**

### 1.4 库龄档位门槛（生产 `finance.sku_pricing_policies`）

| 档位 | min_restock_days | discount_rate | target_margin_rate |
|---|---|---|---|
| 日常 | 0 | 10% | 25% |
| 库龄≥60天 | 60 | 15% | 22% |
| 库龄≥90天 | 90 | 20% | 18% |
| 库龄≥120天 | 120 | 30% | 10% |

⇒ **跨仓差异的判定门槛 = 60 天**（与「库龄≥60天」档同门槛）。

### 1.5 前端现状

「平台SKU利润测算」tab 列定义在 `frontend/src/domains/business/views/ProductCenter.vue:444-640`，共 **31 列**，
**除「操作」列 `fixed="right"` 外无任何固定列**，无视觉分区。前 3 列有 `prop`（`spu`/`sku_key`/`sku_name`），其余 28 列全走 `#default` 插槽。

### 1.6 附带发现（不属本轮范围，但需记录）

- **飞书投影凭据缺失**：生产 7 条 `price_adjust` 任务失败于 `Feishu app credentials are not configured`
  （`backend/services/feishu_projection_client.py:94-97`）。近 7 天无任何 completed 投影。
  根因方向：生产 compose 里 `celery-worker` 是**独立 service、无 `env_file`、且 `environment:` 未列 FEISHU_\***，
  而 base compose 的 `env_file: .env` 只挂在 `backend-api` 上 ⇒ **跑投影任务的 celery 容器拿不到凭据**。
  最后一次成功投影 2026-11-01；v7.15.5 部署于 2026-11-07 ⇒ 高度疑似**部署引入的回归**，非既有缺陷。
  **本轮不动它**（生产发布窗口需 Walter 决策），但**必须在发版前告知**。
- 飞书「调价记录表」现有 19 列（`ERP SKU`/`商品名称`/`规格`/`平台`/`上次最低售价`/`变动幅度`/`变动方向`/`新最低售价`/`变动原因`/`库龄天数`/`当前售价`/`库存数量`/`库存金额`/`变动时间`/`完成`/`处理人`/`备注`/`命中档位`/`SPU`），
  **无仓库列** ⇒ 若要把仓维度推进飞书，需要「加列→切代码→删旧列」同窗口操作。

---

## 二、设计决策（逐条对应口径纪律）

### D1 库龄还原成 SKU×仓，但**不引入第二套口径**

- `load_current_restock_days` 保留**现有 SKU 级跨仓 MAX** 语义不动（它是「整体资金压货」的量，
  被 `sku_clearance_service` 与基线通知共用）。
- **新增** `load_restock_days_by_warehouse(db, sku_ids)`：返回 `{sku_id: {warehouse_code: {...}}}`，
  每仓独立算 `days_since_restock`（`available_stock > 0` 才算，与现有过滤逐字对齐）。
- 商品中心测算链路的底线**改用「当前所选仓」的库龄**。
  ⇒ 口径纪律：**同一函数被页面与通知共用**这条不变；
  变的是「取哪个仓的库龄」这个**入参**，不是算法。

### D2 仓名归一：用显式映射，不猜字符串

- 新增 `mart.inventory_state.warehouse_code` 列（迁移补齐 + 采集侧写入）。
- 归一来源：`core.dim_warehouses` 的 `warehouse_name`，但**两边名字不一致** ⇒
  新增一张**归一映射表** `mart.warehouse_name_aliases`（妙手仓名 → `warehouse_code`），
  由 `dim_warehouses` 播种 + 人工可维护，采集侧查表归一。
- **不匹配仓名的处理**：仓名不在映射表 ⇒ `warehouse_code` 留空 + 记日志（**不静默归到一个仓**）。
  空 `warehouse_code` 的库存行**不参与**仓级定价，但**仍参与** SKU 级聚合（保证老口径不丢数据）。

### D3 底线作用域：保持 SKU×平台，**不新建 SKU×平台×仓的覆盖表**

- 底线是「SKU × 平台」的量（人工覆盖表 `finance.sku_platform_pricing` 的 PK 就是 `(sku_id, platform_code)`）。
- 本轮**不**改这张表的 PK（那是大手术，且 Walter 未要求「覆盖分仓」）。
- 改的是**底线计算用的库龄**：从「全仓最长」改为「**当前所选仓**」。
- ⇒ 效果：同一 SKU 在 TikTok 上，选新加坡仓视图 → 用新加坡仓库龄算档位；
  选马来仓视图 → 用马来仓库龄算档位。**SG 不再被 MY 拖累。**

### D4 跨仓差异提示：**提示，不自动改价**

- 新增纯函数 `detect_warehouse_divergence(per_warehouse_rows, policies)`：
  同一 SKU 在 ≥2 仓有库存，且**各仓命中的档位不同**（或库龄差 ≥60 天）⇒ 判定「跨仓差异」。
- 提示文案方向：**「优先调拨而非降价」**——库存该从滞销仓挪到好卖仓，
  而不是把全平台底线压下去。
- **只提示，不改底线、不自动调价**（库存调拨是运营决策，系统不越权）。

### D5 前端列重排：四段式 + 左侧固定三列

采纳 Walter 提的字段顺序，前置「不可编辑、基本信息」区，后置决策与结果区；
并按「事实 → 输入 → 决策 → 结果」分四段，加**视觉分区**（表头样式）。
ROI 四列**拆开**：保本/建议属结果，目标/平台报告属输入。

---

## 三、实施步骤（每步一个提交，均可独立验证）

### 阶段 6.1 仓名归一（地基）
1. 迁移 `current_schema_20261122_warehouse_name_aliases`：建 `mart.warehouse_name_aliases`；
   给 `mart.inventory_state` 加 `warehouse_code` 列 + 幂等回填。
2. `backend/services/inventory/inventory_state_warehouse_map_service.py`：
   查映射表 → `{妙手仓名: warehouse_code}`，带缓存。
3. 采集侧 `inventory_state_refresh_service.persist_rows` 写入 `warehouse_code`。
4. 测试：归一映射 5 条一一对应；未映射仓名不静默归仓。

### 阶段 6.2 仓级库龄取数
5. `inventory_restock_query_service` 新增 `load_restock_days_by_warehouse`。
6. 测试：跨仓 SKU 各仓天数独立；`available_stock=0` 的仓不参与。

### 阶段 6.3 定价档位按仓
7. `product_pricing_query_service.load_pricing_context` 增加 `warehouse_code` 形参；
   传了仓 ⇒ `days_since_restock` 用该仓库龄；不传 ⇒ 保持现状（**老调用方零影响**）。
8. `product_center.py:4169` 的 `_pricing_context` 传 `warehouse_code`。
9. 测试：同一 SKU 在 SG/MY 两仓分别命中不同档位；不传仓时行为与改造前逐字一致。

### 阶段 6.4 跨仓差异提示
10. 纯函数 `detect_warehouse_divergence` + 后端字段回带。
11. 测试：跨档位 ⇒ 提示；同档位 ⇒ 不提示。

### 阶段 6.5 前端列重排 + 固定列
12. `ProductCenter.vue` 列重排 + `fixed="left"` 三列 + 四段表头样式。
13. `frontend/tests/productCenterUi.test.mjs`：更新列序断言（保持 ROI 相对序约束）。

### 阶段 6.6 收尾
14. 后端全量相关测试 + 前端 `vite build` + 前端测试。
15. 迁移三步可重复验证（down→up→down）。
16. 合并 main → 发版。

---

## 四、验收口径

| # | 验收项 | 判据 |
|---|---|---|
| A1 | 仓名归一 | 生产 5 个妙手仓名全部映射到唯一 `warehouse_code`；无映射的不静默归仓 |
| A2 | 仓级库龄 | 跨仓 SKU 各仓天数独立；`available_stock=0` 的仓不参与 |
| A3 | 档位按仓 | 同一 SKU 在 SG/MY 两仓视图命中不同档位时，SG 的底线不受 MY 影响 |
| A4 | 口径不回归 | 不传仓参数的调用方（清货排名、基线通知）输出与改造前**逐字一致** |
| A5 | 跨仓提示 | 跨档位 ⇒ 给出「优先调拨而非降价」提示；同档位 ⇒ 无提示 |
| A6 | 前端列重排 | 左侧 SPU/ERP SKU/商品名称 三列固定；四段分区可辨；ROI 相对序保持 |
| A7 | 迁移 | up→down→up 三步幂等；单 head |

---

## 五、本轮不做（明确留到后续，需 Walter 决策）

1. ~~**飞书投影凭据缺失修复**（生产可见缺陷，疑似 v7.15.5 部署引入）——需生产发布窗口。~~
   **→ 已在 v7.17.0 一并修复并随发布上线**，详见 §六。其余四项仍留到后续。
2. **飞书「调价记录表」加仓库列**——需「加列→切代码→删旧列」同窗口操作。
3. **调价基线 / 人工覆盖下沉到仓**（`ops.price_adjust_baselines`、`finance.sku_platform_pricing` 的 PK 加仓）
   —— Walter Q1 答「各站可分别定价」指向这条，但工作量大且涉及存量迁移，建议下一轮单独做。
4. **「平台店铺 ↔ 平台商品 ↔ ERP SKU」映射数据链**（生产 `core.bridge_erp_sku_keys` 1118 行 `source_shop_id` 全 NULL）
   —— 站点级定价的真实地基；本轮用「仓 ↔ 国家 ↔ 站」桥替代。
5. **清货排名改仓级**（`api.sku_clearance_ranking_module`）——本轮保持 SKU 级，避免与口径纪律冲突。

---

## 六、落地结果留档（v7.17.0，2026-11-08）

### 6.1 提交

| 提交 | 内容 |
|---|---|
| `7c946c13` | 后端 6.1–6.4：仓名归一 / 仓级库龄取数 / 按仓定价 / 跨仓差异提示 |
| `4069c355` | 本方案文档 |
| `6c0600fa` | 前端 6.5–6.6：列重排 + 固定左侧三列 + 四段分区 + 库龄（仓）列 + 跨仓提示列 |
| `051d0695` → `1e8db144` | 生产缺陷修复：飞书投影凭据缺失（celery-worker 补 `env_file`） |

发布：`main` = `1e8db144`（GitHub + CNB 双镜像同 commit），tag `v7.17.0`。

### 6.2 验收口径逐条结论

| 验收项 | 结论 | 证据 |
|---|---|---|
| A1 仓名归一 | ✅ | 生产 5 个妙手仓名全部映射到唯一 `warehouse_code`；未登记仓名留空 + 记日志 |
| A2 仓级库龄 | ✅ | 实测 `HKR-2260-white-035`：SG-01=55 天 / PH-REPAIR=68 天，各仓独立；`available_stock=0` 的仓不参与 |
| A3 档位按仓 | ✅ | 传 SG-01 后 `days_since_restock` 从 68 → 55，SG 站回到「日常」档，不受 MY 影响 |
| A4 口径不回归 | ✅ | 不传仓时输出与改造前逐字一致；清货排名与基线通知仍走 SKU 级跨仓 MAX |
| A5 跨仓提示 | ✅ | 跨档位给出调拨建议；同档位不提示 |
| A6 前端列重排 | ✅ | 左侧三列 `fixed="left"`；四段表头着色 + 图例；结果段内 ROI 相对序保持 |
| A7 迁移 | ✅ | Docker 临时库 up→down→up 三步全过；commit 内单 head（`20261203` → `20261205`） |

### 6.3 验证记录

- 后端：新增 `backend/tests/test_warehouse_dimension.py` 16 条；定价与商品中心回归 195 passed；库存采集链路 38 passed。
- 前端：UI 断言 77 passed；`vite build` 通过；CI 前端哑测试门禁通过。
- 迁移隔离：版本表预置为 `down_revision` 模拟真实生产路径，up → down → up 三步全过。
- 真库端到端：接口响应确认 `warehouse_restocks` / `warehouse_divergence` / `pricing_days_since_restock` 三个字段确实存在且取值正确。

### 6.4 附带修复：飞书投影凭据缺失

- **现象**：最后一次成功投影停在 2026-11-01；2026-11-07 部署后 7 条 `price_adjust` 任务全部失败于
  `Feishu app credentials are not configured`。
- **根因**：`celery-worker` 只定义在 `docker-compose.prod.yml`（base 的 `docker-compose.yml` 没有这个
  service），因此拿不到 base 里 `backend-api` 用的 `env_file: .env` ⇒ 跑投影任务的 celery 容器没有 app 凭据。
  API 容器有凭据（投影配置 `status=ready`、`initialized_at=2026-10-23`），所以坏的只有 celery 这条路径。
- **修复**：`celery-worker` 补 `env_file: .env`。刻意**不**在 `environment` 里重复声明 `FEISHU_*` ——
  `environment` 优先级高于 `env_file`，插不出值时会用空串覆盖 `env_file` 里的真值，比不修还糟。

### 6.5 本轮发现但未处理的既有问题

1. **`validate_migrations_fresh_db.py`（全新空库跑全链）失败**：卡在
   `20261116_add_tiktok_export_store_name_aliases` 的前置检查（要求库里已有 TikTok 店铺账号，空库没有）。
   **在 `origin/main` 基线上同样失败，是既有缺陷，不是本轮引入**；生产走「已有库增量升级」，不受影响。
   建议下一轮修（让该迁移在没有店铺数据时跳过或降级），否则这个门禁对「空库全链」永远没有信号。
2. **本地 `alembic upgrade head` 在开发库不可用**：开发库版本号指向语义层会话尚未提交的
   `20261204_semantic_orders_alias_resolve` ⇒ 仓库里找不到该 revision。本轮迁移因此保持
   `down_revision = current_schema_20261203_semantic_alias_normalized_refresh`（分支自洽、单 head）；
   **待对方提交后，需要把本轮迁移的 `down_revision` 改到对方的 revision 之后**，否则会出现双 head。

## 七、阶段 7：当前仓库存与「仅有库存」筛选（2026-11-08）

### 7.0 触发与事实基线

运营反馈「测算表『库龄（仓）』列没显示」。**只读核查结论：这是数据事实，不是 bug** ——
反馈截图上的 12 个 SKU 在新加坡仓 `available_stock = 0`（已清空），
而**已清空的仓不参与库龄**（阶段 6 的既定口径：清空的仓不压资金）。

| 事实 | 核查结果 |
|---|---|
| 新加坡仓 `SG-01` | 852 行，其中仅 278 行有可用货 |
| 截图那批 SKU | 在 SG-01 全部 `available_stock = 0` |
| 接口返回 | `pricing_days_since_restock=None`、`warehouse_restocks=[]`、`pricing_tier_source=fallback_no_restock_days` ⇒ 前端显示正确 |
| 有货的行 | `A-00001-BLACK` 7 天 / `A-00001-Army green` 55 天 / `A-000` 68 天，库龄显示正常 |

**问题不在"库龄算错了"，而在"页面没告诉运营这个仓已经清空了这批货"** ——
运营看到空的库龄，只会觉得系统坏了。因此本轮补的是**事实展示**，不是改口径。

### 7.1 设计决策

**D6 库龄与库存拆成两条口径（核心）**

- 库龄（距上次进货天数）：只看**还有库存**的仓 —— 已清空的仓不压资金。**口径一个字不动**（阶段 6 的 A1–A7 全部不受影响）。
- 库存数量：**零库存的行也要列出来** —— 零就是"这个仓清过这货"这条事实本身。

两者混在一条口径里，运营看到「库龄 -」时分不清是"压了 90 天"还是"早清空了"，
于是把清仓 SKU 当滞销品去降价。新取数放在独立模块
`backend/services/inventory/inventory_warehouse_stock_query_service.py`，
**只出数量、不参与档位与底线计算**。

**D7「仅有库存」筛选必须在后端做 + 有货优先排序**

- 前端筛只筛当前这一页 ⇒ 总数对不上、翻页漏行。所以顺序是：
  **候选全集 → 按当前仓库存过滤与排序 → 再分页**。
- 排序规则：**有货优先**（运营先看到还能卖的那批），组内仍按 ERP SKU 升序（翻页顺序稳定）。
- 筛选**默认打开**：测算表是"给还在卖的货定价"的表。
- 状态层不可用时**不筛**（而不是把整张表筛空）：整表空掉会被读成"这个仓没货"，比不筛更坏。

**D8 误报告警只改措辞、不动口径**

`product_pricing_query_service` 里那句 `inventory_state unavailable` 在"这批 SKU 都无库存"时
**每次都误报**，而且报完还回落到注释自称"坏的"旧库龄口径（恒 0~13 天）。
但**该行为与改造前逐字一致**，改动它会破坏 A4（不传仓的老调用方输出必须一致）。
本轮只做两件事：

1. 探一次状态层在不在，把两种情况分开说 ——
   **"状态层不可用"（管道坏了，要人去修，warning）** vs
   **"这批 SKU 没有有库存的记录"（业务事实，info）**；
2. **回落口径一个字不改**（保 A4）。

顺带记录一个**既有缺陷**（不在本轮范围）：不传仓的老调用方在"这批 SKU 无库存"时，
拿到的仍是那个 0~13 天的坏口径，需要单独一轮做口径修正。

### 7.2 实施步骤

| 步骤 | 内容 | 提交 |
|---|---|---|
| 7.1 | 后端：仓级库存快照取数（含零库存行）+ 状态词 + 筛选排序纯函数 | `见 7.4` |
| 7.2 | 后端：候选接口接入「仅有库存」筛选 + 有货优先排序 + 「当前仓库存」输出；误报告警措辞修正 | `见 7.4` |
| 7.3 | 前端：「当前仓库存」列（已清仓显式标注）+「仅有库存」筛选默认打开 | `见 7.4` |

### 7.3 验收口径

| 验收项 | 口径 |
|---|---|
| A8 口径不串 | 库存快照 SQL **不带** `available_stock > 0`；库龄那两条**必须带** |
| A9 状态可辨 | 在卖 / 已清仓 / 这个仓没这货 / 取不到，四种状态分得开 |
| A10 筛选在分页前 | 筛选后的行数才是 `total`；翻页不漏行 |
| A11 A4 不回归 | 不传仓的老调用方输出与改造前逐字一致（回落口径未改） |

### 7.4 落地结果留档（v7.18.0，2026-11-08）

| 提交 | 内容 |
|---|---|
| `c1fc3a37` | 后端 7.1–7.2：仓级库存快照取数 + 「仅有库存」筛选与有货优先排序 + 误报告警措辞 |
| `b08b753f` | 前端 7.3：「当前仓库存」列 + 「仅有库存」筛选默认打开 |
| `f0b6cb2d` | 阶段 7 代码按 black 格式化（CI 的 Code formatting check 要求） |
| `ea22fc1d` | 阶段 7 方案与决策补记（**v7.18.0 tag 指向此提交**） |

发布：`main` = `30c4e682`（合并提交；GitHub + CNB 双镜像同 commit），
tag `v7.18.0` → `ea22fc1d`，部署流水线 `42484464805` **success**。

#### 验收结论

| 验收项 | 结论 | 证据 |
|---|---|---|
| A8 口径不串 | ✅ | 库存快照 SQL 不带 `available_stock > 0`，库龄那两条仍带（单测守门） |
| A9 状态可辨 | ✅ | 生产 SG-01：有货 283 行 / 零库存 569 行，零库存行能被取到并标 `cleared` |
| A10 筛选在分页前 | ✅ | 生产实测：`only_in_stock=True` → total=283 = 该仓有货行数；`False` → total=1119 = 全部在售 SKU |
| A11 A4 不回归 | ✅ | 库龄/档位/底线未受影响（`A-000` 库龄 68 天 → 库龄≥60天档 → 底线 75.33） |

生产只读验收：`mart.inventory_state` 五仓事实核对 + 候选接口层实测（用已发布代码跑生产库）。
本机无生产 HTTP 隧道（仅 PostgreSQL/Redis 隧道），HTTP 侧以部署流水线自身的健康检查为准
（`[OK] Backend is healthy`、`Deployment completed. Tags: Backend=v7.18.0`）。

#### 顺带修正的既有缺陷

`product_pricing_query_service` 的误报告警：以前「状态层不可用」与「这批 SKU 没有有库存的记录」
都报成前者，日志里每次筛出清仓 SKU 就冒一条"系统不可用"，把真故障淹掉了。
现在用一次状态层探测把两者分开说（前者 warning，后者 info），**回落口径一个字未改**（保 A4）。

#### 本次发布范围说明（重要）

`v7.18.0` 的 tag 指向 `ea22fc1d`，即**阶段 6 + 阶段 7**。
本地 `main` 上另有语义层会话的 19 笔提交（orders/analytics 域 SSOT 改造及其迁移
`20261206`–`20261208`），**不随本 tag 上线** —— 那批工作由其负责会话自行验收发版。
因此生产迁移版本保持 `current_schema_20261205_warehouse_name_aliases` 不变（部署日志已确认
`current_revision == head_revision`）。

#### 遗留

1. **main 的 CI 仍是红的**：卡在 `backend/services/semantic_field_registry.py` 未过 black
   （语义层会话的文件，不在本轮范围内）。阶段 7 自己的三个文件已格式化并复跑通过。
2. **飞书调价记录表写入 `800030005 not_found`**：凭据缺陷已随 v7.17.0 修复，但暴露出第二个独立缺陷。
   已逐项证伪：不是请求体形态（11-06 同一份代码成功写入 174 行）、不是表结构与字段名
   （19 列齐全、代码写的 15 个列名全在）、不是字段名解析（错列名报的是另一个错误码 `800030201`）、
   不是读权限（fields/records/base meta 全部可读）。**写侧目标解析/写入权限**指向飞书侧，
   待明天 10:00（北京时间）生产定时任务自然重试这 7 条时再定性。

