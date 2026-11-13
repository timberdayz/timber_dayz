# 模板治理闭环复盘(2026-11-13)

> 面向业务的一句话：**「模板已保存，但该样本文件仍未通过治理复核」**这句话是假的 ——
> 保存其实成功了，是判定口径、面板读数、刷新时机三件事叠在一起，把它说成了失败。
> 本次把三件事一起修掉，并补上「同维度多格式并存」与「入库批量刷新」两件历史欠账。

- 影响环境：**生产(云端)**。本机(`F:\xihong_erp`)是采集机，判定口径与模板数据在两个环境里各有一份；
  本次改动**两端都要**才有意义(代码统一走 git，模板数据另有一条同步链路)。
- 关联文档：
  - ADR: `docs/adr/2026-11-13-template-drift-classification-ssot.md`(判定口径 SSOT)
  - ADR: `docs/adr/2026-11-13-template-multi-format-and-batch-refresh.md`(多格式并存 + 批量刷新)
  - 事故复盘: `docs/reports/2026-11-07-shop-identity-and-template-sync-incident.md`(问题 2 / 3 / 5)

---

## 一、现象与根因

用户在治理面板更新模板后，界面仍然提示「模板已保存，但该样本文件仍未通过治理复核」。
实测(本地库 + 真实样本文件 `data/raw/2026/tiktok_orders_monthly_20261113_122006.xls`)，
**三个原因叠在一起**：

| # | 根因 | 位置 | 表现 |
|---|---|---|---|
| 1 | 「什么算阻断漂移」有**三份**定义 | `template_matcher._classify_header_changes` / `semantic_field_contract_service.evaluate` / `data_sync_status_semantics` | 各域行为不一致；业务口径只能靠 `if` 打补丁(`shopee/orders/monthly` 单开豁免)，TikTok 订单接进来时没人想到要一起打 |
| 2 | 面板读的是**漂移快照**，不是实时判定 | `backend/domains/data_platform/routers/data_sync.py` 治理覆盖统计 + 前端文案 | 做对了却看不到效果 —— 快照里的 `breaking_drift` 在重检通过前一直保留 |
| 3 | 保存模板**不触发重检** | `backend/tasks/scheduled_tasks.py::_recover_template_update_required_files` 只在 15 分钟轮询里跑 | 用户改完模板要等下一轮才可能看到结果 |

外加两条**历史欠账**(不在本次用户诉求里，但决定了「改了模板还是补不回历史数据」)：

| # | 欠账 | 根因 | 影响 |
|---|---|---|---|
| A | 同维度只能有一种格式 | published 唯一键只是「维度」；`save_template` 把同维度全部 published 一起归档 | 平台改一次导出格式 ⇒ 历史格式的文件再也找不到能解释它的模板(tiktok 8 月数据补不回来) |
| B | 每入库一个文件刷一轮 25 个物化视图 | 刷新队列只合并「pending」的任务，正在跑的那条吸收不到新事件 | 一轮入库刷出好几轮完整刷新(单次 170 秒以上) |

---

## 二、处置(按批次)

### P0-1 判定口径收敛为唯一入口(SSOT)

- 新增 **L3 唯一判定入口** `data_sync_status_semantics.classify_drift`，三层分离：
  L1 事实(`template_matcher`) → L2 语义(`semantic_field_contract_service`) → **L3 结论(`classify_drift`)**；
  编排层(`data_sync_template_status_service`)**只消费不定义**。
- 业务口径(**对所有域一致**):
  > **多一列 ⇒ 阻断，直到模板把它纳入；少了必填字段 ⇒ 阻断；可选列与列顺序变化 ⇒ 不阻断。**

  - 「多一列要阻断」的理由: 模板没声明的列**不会写进事实表** ⇒ 放行等于**静默丢数据**。
    先拦一道，把「模板落后」变成待办; 用户更新模板(新版本纳入该列)⇒ 契约晋升 ⇒ 新列的数据这才真正落库。
    唯一例外 = 用户在「已确认的新列」里勾掉的列。
  - 取消 `shopee/orders/monthly` 平台特判(它原本会造成新列被静默丢弃);
    `预估回款金额` 保留在 L3 的存量兼容名单以免行为回归。
- 顺带修掉一条荒谬状态: 纯列顺序变化曾被判「阻断漂移」，面板同时显示「匹配率 100.0%」。

### P0-2 模板发布即闭环

- 新增 `backend/services/template_recheck_service.py`(重检与放行的 SSOT):
  模板保存成功后**立刻**重检同维度待更新文件，能过的当场放行(并完成契约晋升与快照搬移);
- 定时巡检(`scheduled_tasks._recover_template_update_required_files`)**复用同一份**逻辑，两处不再各写一套;
- 判定复用 `DataSyncService.get_file_sync_readiness`(与入库前置校验同一条链路)，避免「面板说过了、入库说没过」。

### P0-3 面板与文案

- 治理覆盖统计同时给**组合级**与**文件级**结论: 漂移快照保待办不消失，实时判定回答「这个样本文件此刻行不行」;
- 前端按**三态**提示: 放行 / 仍待重检 / 仍有字段对不上;
- 文案不再说「仍未通过治理复核」这种把成功说成失败的句子。

### P1 语义契约升级为业务可用性判据

- 少列按**能否证明它可缺**分三种归宿: 已证明可选 / 别名救回 / 其余阻断;
- **该域没有语义契约时保守阻断**(把「没有结论」与「结论是可选」区分开)。

### P2-a 同维度多格式并存(`format_signature`)

- 模板表加 `format_signature`，取值与变体 `variant_kind` **同一份实现**(列集合 + 解析方式 + 表头行 + 工作表名);
- published 唯一键从「维度」改为 **(维度, 格式签名)**; 迁移 `20261229_template_format_signature.py`(加列 → 回填 → 换索引，可回滚);
- 归档范围按**保存意图**分: `new_version`(更新既有模板)= **替换**; `create`(新建 / 创建变体)= **并存**;
- 「当前已发布模板」限定在**同格式内**: 两种格式并存时, 不把「并存」误报成「我们升级过模板」;
  但基准那一版**已被归档**(被新版顶掉)时, 仍用「当前已发布模板」做对照 —— 升级信号照常成立。

### P2-b 入库批量刷新

- 刷新队列的合并范围从「pending」扩到「pending + running」: 正在跑的那条吸收后来到的事件并打 `rerun_requested` 标记;
- 它跑完看到标记 ⇒ 重新排回 pending ⇒ **再刷一轮收口**;
- ⇒ 一轮入库至多「跑中的那一轮 + 收口的那一轮」，而不是「每个文件一轮」。

---

## 三、口径变更(需要业务知晓)

| 变更 | 以前 | 现在 | 理由 |
|---|---|---|---|
| 多一列 | 平台特判放行(shopee) / 其它域阻断 | **一律阻断**(除非用户已确认) | 放行会静默丢数据 |
| 少一列 | 语义层自己判 | 无契约域**保守阻断** | 「没有结论」≠「结论是可选」 |
| 列顺序变化 | 报阻断漂移 | **不阻断** | 匹配率 100% 却报阻断是自相矛盾 |
| 「更新模板」的含义 | 同维度全部 published 归档 | 只替换被编辑的那一版; **其它格式继续生效** | 更新 ≠ 新增一种格式 |
| 「创建变体」的含义 | 同上 | 同格式的才替换, **别的格式并存** | 变体 = 同业务的另一种文件格式 |

---

## 四、验证结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 判定口径守护 | `pytest backend/tests/data_pipeline/test_drift_classification_ssot.py` | 21 passed |
| 多格式守护 | `pytest backend/tests/data_pipeline/test_template_format_signature_guardrails.py` | 13 passed |
| 批量刷新守护 | `pytest backend/tests/data_pipeline/test_refresh_queue_batch_coalescing.py` | 5 passed |
| 宽回归(判定/模板/契约/治理/入库) | `pytest backend/tests -k "template or drift or semantic_contract or core_field or hash or contract or governance or ingest"` | 1537 passed / 3 skipped / **0 failed** |
| 架构 SSOT | `python scripts/verify_architecture_ssot.py` | 4/4 PASSED |
| UTF-8 卫生 | `python scripts/verify_utf8_source_hygiene.py` | 8 files PASS |
| 规则完整性 | `python scripts/verify_rules_completeness.py` | PASS |
| 前端类型检查 | `npx vue-tsc --noEmit` | exit 0 |
| 前端构建 | `npx vite build` | built in 35.50s |
| 迁移链 | `alembic heads` | 单 head: `current_schema_20261229_template_format_signature` |
| 采集机本地库 | `python output/run_current_migrations_local.py --with-backup` | 已升级到新 head; 唯一键无重复 |
| 全量失败集 diff | `scripts/diff_pytest_junit.py output/junit_before.xml output/junit_after.xml` | **NEW failures = 0**；COMMON = 3（与基线同 3 条既有失败）；ADDED cases = 41；exit 0 |
| 全量(rebase 后) | `pytest backend/tests tests` | 6664 passed / **3 failed** / 13 skipped（与基线同 3 条既有失败；第 4 条 `.ps1` 编码失败已在后续批次按「形态分」修正守护后消解） |

---

## 五、未解决 / 留给 V2

1. **本机与生产都没有 `template_update_required` 的真实文件**
   (本地库 20 个文件全是 `ingested`；生产库 `public.catalog_files` 为 `ingested=215 / failed=26`)
   ⇒ 端到端闭环只能用**真实模板 + 真实文件列**构造夹具验证;
   **v7.26.0 已上线，仍需人工实测一遍**(改一个模板 → 看面板三态 → 看该文件是否当场放行)。
2. 治理面板的「维度行」还没按格式拆分展示(判定已按格式，展示仍是「最新一版」)。
3. 物化视图仍是全量 `REFRESH MATERIALIZED VIEW`，没改成增量刷新(问题 5 的另一半建议)。
4. 全量 pytest 的既有基线污染(`test_project_env.py` 泄漏 `DEPLOYMENT_ROLE=local`)按仓库规则属非阻塞 V2 债;
   本次用**失败集 diff** 证明无新增失败。
5. **另一类既有污染**(本次实测确认, 与本次改动无关):
   `tests/test_executor_v2.py` 跑在 `pytest.mark.anyio` 上, 而 `backend/tests` 里用
   testcontainers 的文件(既有的 `test_template_family_business_form_guardrails.py` 与本次新增的
   `test_template_format_signature_guardrails.py` 同样)会在 teardown 时留下
   「Event loop is closed」的 error。**既有文件同样能触发** ⇒ 属既有交互, 不在本次范围。

---

## 六、上线前检查(本机是采集机, 不是生产)

1. **先让采集机跟上并验证**：本机跑通 `pytest` + `vite build` 后，再打 tag 发生产。
   (生产发布 = push tag `vX.Y.Z`, **需要显式确认**。) —— ✅ 本次已完成：采集机全量/宽回归/前端构建全绿，
   生产发布 run #285 结论 success（详见第七章）。
2. **采集机的本地库必须先跑迁移**（本次已踩到并修好）：
   ORM 已经在读 `core.field_mapping_templates.format_signature`，而本地库还没这一列 ⇒
   任何走真实库的链路（采集登记 → 模板匹配）都会报
   `column field_mapping_templates.format_signature does not exist`，
   事务被 abort ⇒ 文件登记失败 ⇒ 采集任务退化成 `partial_success`。
   ⇒ **代码与库必须同时到位**；顺序是「先跑迁移，再上新代码」。
   本次已在采集机执行 `python output/run_current_migrations_local.py --with-backup`
   （备份 + 漂移检查 + advisory lock 的 fail-closed 入口），
   本地库现处 `current_schema_20261229_template_format_signature`。
3. **代码走 git，模板数据走另一条链路**：`scripts/sync_templates_to_cloud.ps1` 是模板数据的同步通道，
   本次**没有**改模板数据的同步口径, 但迁移会改 `core.field_mapping_templates` 的索引 ⇒
   云端升级时该迁移会跑(加列 + 回填 + 换索引), 回填是纯 UPDATE, 不锁业务表。
4. **迁移顺序**：新迁移接在 `current_schema_20261228_bridge_spu_sku_binding_status_constraint` 之后,
   链头唯一(`alembic heads` 已核对)。
5. **上线后自查**：
   - 唯一键实际是 **6 列**（`platform, data_domain, granularity, sub_domain, account, format_signature`，
     `status='published'` 时生效）⇒ 自查必须按**完整键**分组，只按「维度 + 签名」查会把
     `granularity/sub_domain/account` 不同的合法并存行误判成重复：

     ```sql
     -- 期望：空结果（无重复）
     select platform, data_domain, granularity, sub_domain, account, format_signature, count(*)
     from core.field_mapping_templates where status='published'
     group by 1,2,3,4,5,6 having count(*)>1;
     ```
   - 随便改一个模板并保存 ⇒ 面板应立刻给出「已放行 / 仍待重检 / 仍有字段对不上」三态之一, 而不是「仍未通过治理复核」。

---

## 七、发布与生产验收记录（2026-11-13）

### 1. 版本号为什么是 v7.26.0 而不是 v7.25.0

本批开工时远端是 `0e6ec9c8`（v7.24.0）；发版前 `git fetch` 发现远端已被**另一批**推进到
`d908fa96` 并打好了 `v7.25.0`（商品中心 SPU 缺陷收口 + 接口去重挂载 + 密钥门禁补强，已完成生产验收）。
⇒ 本批 **rebase 到 `origin/main`** 再发布，版本号顺延为 **v7.26.0**（版本号不可复用）。

- 代码提交：`2839cad5`（模板治理闭环）、`bfd976f8`（本复盘报告）、`05a359a1`（发布提交）
- tag：`v7.26.0` → `05a359a1`（annotated）

### 2. 发布前的门禁自检（这三处不修会**阻塞**流水线）

| 门禁 | 问题 | 处理 |
|---|---|---|
| CI 格式检查（`black` 比对 `git diff`） | 7 个改动文件未格式化 | 已格式化并入发布提交 |
| CI Linting（`ruff check`） | `backend/tasks/scheduled_tasks.py` 残留未使用赋值 `now = datetime.now(timezone.utc)`（F841，旧实现遗留） | 删除该行（行为不变） |
| `.ps1` 编码约定 | v7.26.0 给 `watch_cloud_sync_tunnel.ps1` 补了 UTF-8 BOM 并**写进了仓库** —— 那是把**采集机专属形态泄漏进仓库**（仓库 HEAD 里 27 个 `.ps1` 全部无 BOM；采集机形态的 BOM 属 30 项本地适配，不入库） | 远端 v7.26.0 之后已把看门狗改回**纯 ASCII + 无 BOM**；本批把守护改成**按形态分**：仓库形态无 BOM、采集机形态含非 ASCII 必须带 BOM（本地 25 个适配 `.ps1` 的 BOM 形态原样保留、未入库） |

另本地逐条跑过流水线上的 **7 道 Release Gate**：API 契约（0 错误 / 65 警告，与既有基线同）、
前端 API 方法（0 缺失）、数据库字段、迁移契约（3 passed）、关键表外键、远程部署契约、
库存流水线（31 passed）—— 流水线上的 `Validate Data Flow (Release Gate)` job 亦为 **success**。

### 3. 流水线

- run **#285**（`43402306171`，`deploy-production.yml`）：
  `check-config` ✓ → `Validate Data Flow (Release Gate)` ✓ → `Build and Push Images (Release Tag)` ✓
  → `Deploy to Production (Tag Release)` ✓ ⇒ **conclusion = success**（17:56:43 CST 完成）。
- 生产 API 自报：`{"status":"ready","version":"v7.26.0","checks":{"database":{"status":"connected"}}}`（`/healthz/ready`）。

### 4. 生产只读验收（走 `deploy@` 只读通道，未做任何写操作）

| 断言 | 结果 |
|---|---|
| 迁移版本 | `current_schema_20261228_...` → **`current_schema_20261229_template_format_signature`** ✅ |
| `core.field_mapping_templates.format_signature` 列 | 存在（`character varying`，可空）✅ |
| published 唯一索引 | `uq_field_mapping_templates_published_dimension_format` 已生效，旧索引已退场 ✅ |
| 完整唯一键下 published 重复 | **0 条** ✅ |
| `format_signature` 回填完整性 | 27 / 27 行有值，**0 缺失** ✅ |
| 容器与镜像 | 7 个容器全部 **healthy**（backend_api / celery_worker / celery_beat / frontend / nginx / postgres / redis），应用镜像均为 `v7.26.0` ✅ |
| 后端启动日志 | 632 个路由注册，启动 0.94 秒，**无 ERROR / Traceback** ✅ |

### 5. 仍未完成 / 需人工

1. **CNB 镜像未同步**：本机两条 CNB 通道都不通（HTTPS 无凭据、SSH 22 端口超时）⇒
   `v7.26.0` 目前**只在 GitHub** 上。CNB Git 是代码镜像、**不触发部署**，生产不受影响；
   但按双镜像纪律需在有凭据的环境补推（tag 必须与 GitHub 侧是**同一个 tag object**）。
2. **端到端闭环仍需人工实测**：生产上当前 `public.catalog_files` 的状态分布是
   `ingested=215 / failed=26`，**没有 `template_update_required` 的文件** ⇒
   「改模板 → 面板三态 → 该文件当场放行」这条链在生产上没有现成样本，
   需要人工改一个模板（或让某个已有文件产生漂移）才能实测。
