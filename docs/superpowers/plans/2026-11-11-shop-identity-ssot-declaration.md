# 店铺身份唯一台账声明 + 认人优先级收敛(SSOT-1)

- 日期：2026-11-11
- 批次：店铺身份「保未来」优化 · 批次 3.2 补充（批次编号 **SSOT-1**）
- 上游方案：`docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md`（业务语言决策版）
  §十一「SSOT 三条铁律」→ 律 1「真源只能有一个，而且必须写在纸上」
- 分支：`feature/2026-11-11-shop-identity-ssot-declaration`
- base：`feature/2026-11-10-shop-identity-future-proofing`（PR #3 的分支）

---

## 1. 为什么要做这一批

两处裂缝（2026-11-11 复核确认）：

1. **没有一份真源声明**。仓库里自称「SSOT 单一权威定义」的
   `modules/core/fact_identity_columns.py`，对象只是**事实表的 `shop_id` 某一列**；
   「规范店铺键由语义层输出」那句把规范键的定义权交给了语义层。
   两份成文声明各自成立，合起来没有一份说清「谁是台账 / 谁是派生 / 谁只是快照」。
2. **认人优先级写在三个地方**。权威文件的散文、Python 侧 `SIGNAL_PRIORITY`、
   两份 SQL 资产的 `resolution_priority` 数字。三处不一致时，同一行在入库侧与
   语义层会解析到**不同的账号**（2026-11 已经因此出过一次事故，方向恰好相反）。

⇒ 本批只做**声明与收敛**，不改任何数据口径。

---

## 2. 改动清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `modules/core/shop_identity_ssot.py`（新增） | 《店铺身份唯一台账声明》：四层身份数据（台账 / 派生 / 快照 / 映射）逐层写明「谁能写 / 权威性 / 出问题怎么办」；认人优先级**唯一定义处**；台账层对象名常量；输出键口径的已知例外与解除条件 |
| 2 | `backend/services/shop_identity_reconciliation_service.py` | `SIGNAL_PRIORITY` 不再自己写死，改为引用 SSOT 的同一个元组（对外名字不变）；docstring 与注释改指新 SSOT |
| 3 | `modules/core/fact_identity_columns.py` | 删掉自己那份优先级散文，只留指向 SSOT 的指针；补「规范键平台编号优先 = 已知例外」的说明 |
| 4 | `backend/services/data_ingestion_service.py` | 注释指针改指新 SSOT（**纯注释**，无行为变化） |
| 5 | `backend/tests/test_shop_identity_ssot_declaration.py`（新增） | 守护测试：声明 == 两份 SQL 资产、Python 侧引用同一来源、分层常量指向台账、方向守卫（行为） |

### 2.1 认人优先级（唯一口径）

| 位次 | Python 信号 | SQL `resolution_method` | 为什么排这个位置 |
|---|---|---|---|
| 1 | `shop_account_id` | `shop_account_id`（priority 1） | 账号章：改名不变、跨平台一致、采集器写不坏 |
| 2 | `platform_shop_id` | `platform_shop_id`（priority 2） | 平台编号：会被采集器污染、平台换 ID 就失效 |
| 3 | `shop_id` | `alias_match`（priority 3） | 行内那列：编号查不到就退回别名索引 |
| 4 | `store_name` | `store_name_match`（priority 4） | 店名，兜底 |

两个世界第三、四路的**名字**不同，**顺序**才是口径。

### 2.2 一处已知例外（本轮明确不动）

- **归属判定**（这串身份值属于哪个店）：账号章优先；
- **输出键**（报表那一列最终填什么值）：`COALESCE(platform_shop_id, shop_account_id, id)`，
  即**平台编号优先**，与归属判定方向相反。

输出键被看板显示名映射表 `core.dim_shops.shop_id` 的键依赖锁死 ⇒ 改了显示名整片落空。
本轮只登记为已知风险，**不动**；解除条件 = 看板显示名映射表先解耦键依赖。

---

## 3. 边界（不做的事）

- ❌ 不改语义层计数口径（`count(DISTINCT c.resolved_shop_id)` 保持不动；歧义仍落 `unknown`）；
- ❌ 不动历史事实行（不写任何针对 `b_class.fact_*` 的迁移 / 回填）；
- ❌ 不改 `sql/semantic/*.sql`（由另一个 PR 负责，本批**只读不写**）；
- ❌ 不改「歧义绝不猜一个」原则、不改 `IdentityIndex` 的平台过滤逻辑；
- ❌ 不新增第三方依赖、不改 CI 配置、连接串一律从 `.env` 读。

---

## 4. 验证

- 守护测试（新增）14 条：全绿；
- 回归目标集（`test_shop_identity_reconciliation` / `test_shop_identity_enum_normalization` /
  `test_shop_platform_id_rebind_alias` / `test_shop_account_identity_service` /
  `test_inventory_warehouse_identity_ssot`）：**84 passed / 0 failed**（基线同结果，无新增失败）；
- 格式：`black==25.1.0` 侧校验通过（本地 3.13 + CI 侧 3.11 容器复验）；
- 断言写法按 **3.11 侧**排版（不用 `assert 条件, (消息)` 的括号换行写法）。

---

## 5. 后续（不在本批）

- 律 2「真源只能由人落笔，自动流程只能提案」→ 把「谁有权改台账」写成规则 + 反向守护；
- 律 3「派生层只能有一份口径」→ 副本改为从正本取数 + 指纹一致性与收敛闸门；
- 输出键口径解耦（需先解开 `core.dim_shops.shop_id` 的键依赖）。
