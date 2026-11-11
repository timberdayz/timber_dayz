# 律 3 落地：候选集物化副本改为「从正本取数」（2026-11-11）

> 本文是 `docs/superpowers/plans/2026-11-11-shop-identity-guard-activation.md`
> 遗留项的**执行记录**：把「派生层口径收回」从**仓库资产**变成**存量库里的事实**。

## 1. 问题是什么

候选池的口径**只有正本一处**定义：

```
semantic.shop_identity_resolution_candidates        (正本, 普通视图)
```

它的物化加速副本：

```
semantic.shop_identity_resolution_candidates_v2_mv  (副本)
```

副本资产（`sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`）早已改成
「**只从正本取数**」：

```sql
CREATE MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_v2_mv AS
SELECT platform_code, identity_value_normalized, ...
FROM semantic.shop_identity_resolution_candidates
```

但这个资产的刷新语义是「**存在则 REFRESH / 不存在则 CREATE**」——
`REFRESH` 只重算**数据**，不换**定义** ⇒ 存量库上的副本**永远不会被换成新定义**。

### 生产实测（2026-11-11，云端库只读探测）

| 项 | 结果 |
|---|---|
| 副本定义 | 仍是**手抄版**：`core.shop_accounts` / `core.shop_account_aliases` / `regexp_replace` / `active_shop_accounts` 都在 |
| 是否从正本取数 | **否** |
| 副本行数 / 正本行数 | 72 / 72 |
| 双向差集 | 0 / 0（*当前* 内容一致） |
| 依赖副本的对象 | `semantic.fact_analytics_atomic`、`semantic.fact_orders_atomic`（两个普通视图） |

⇒ **当前无功能影响**，但副本的**定义比正本少一条口径**：
正本末尾有 `AND NOT semantic.is_collection_source_identifier(...)`
（采集方代号不是店铺身份 ⇒ 不进候选池），副本**没有**。

⇒ 这就是「静默分叉」：现在恰好一致，但正本哪天多一条规则、候选池哪天出现一个
采集方代号，副本就**不会跟** —— 不报错、不告警，只会表现为「某个店没人了」
或「采集方代号被当成店铺身份」。

## 2. 为什么走**迁移**而不是改部署流水线

原计划是在 `deploy-production.yml` 的视图重建阶段前插一步「删掉旧定义的副本」。
实测后**否掉了这条路**，理由是硬约束：

1. 部署期跑的是 `scripts/rebuild_views.py --all-plain-views` ——
   它**只重建普通视图**（物化视图全量重算会超 `statement_timeout`，
   生产实测单个月粒度 MV 就 120s+）。副本不在那份清单里 ⇒
   流水线**根本不会**用它的新定义。
2. 「在流水线里直接 DROP 副本」会**打断解析函数**：
   `sql/semantic/shop_identity_resolver.sql` 是 `LANGUAGE sql` 函数，
   它对副本的依赖是**被跟踪**的 ⇒ 不先让开就 DROP 不掉；
   而让开/换回这两步必须与两个原子层普通视图**同步**做
   （它们存的是副本的 OID）⇒ 天然是一个**原子操作**，不是一个流水线步骤。

⇒ 复用迁移 `20261112_realign_identity_candidates_anchor` 已经走通过的
「让开 → DROP → 重建 → 换回 → 比对」路径（本次**不动**正本口径）。

## 3. 交付物

| 文件 | 作用 |
|---|---|
| `current_migrations/versions/20261225_rebuild_identity_candidates_copy.py` | 重建副本：让开 → `DROP`（**不带 CASCADE**）→ 按资产重建 → 换回 → **内容逐行比对** + **定义校验**（必须读正本、不得再有自算痕迹） |
| `backend/services/data_pipeline/cloud_sync_integrity_service.py` | 巡检**第五项**「候选集副本口径健康」：`missing` / `drifted` / `diverged` / `ok` / `unknown`，纳入 `is_success` |
| `scripts/verify_identity_candidates_copy.py` | **只读**探针；**直接复用**巡检的 `collect_identity_candidates_copy` ⇒ 脚本结论 = 巡检结论 |
| `tests/test_identity_candidates_copy_migration.py` | 14 条：步骤顺序 / DROP 不带 CASCADE / 定义只有资产一处 / 回滚目标是迁移前形态 / 脚本只读且口径不分叉 |
| `tests/test_identity_candidates_copy_guard.py` | 11 条：五种判定 + 与巡检结论的联动 |

### 顺带修掉的两个真问题

1. **巡检第五项的实现 bug**：`counts.one()` 被调用了两次，第二次抛
   `This result object is closed` ⇒ 真库实跑时该项恒为 `unknown`。
   已修，并把单测里的假 `Result` 改成**取过一次就关闭**（模拟真实行为），
   让同类 bug 在单测里就能暴露。
2. **守护脚本开箱不可用**：`verify_semantic_unknown_by_month.py` 与
   `verify_identity_candidates_copy.py` 原来只读进程环境变量，
   直接在仓库根跑会报「DATABASE_URL 未配置」。
   ⇒ 改为在 import 数据库模块**之前**调 `load_project_env(..., profile="collection")`
   （顺序很重要：`backend.models.database` 在 import 时就按 `DATABASE_URL` 建引擎）。

## 4. 验证记录

| 项 | 方法 | 结果 |
|---|---|---|
| 迁移可执行 | 本地开发库（PG 15.14）真跑 `alembic -c alembic-current.ini upgrade head` | 成功，版本 → `current_schema_20261225_rebuild_identity_candidates_copy` |
| 迁移效果 | 迁移后读本地库副本定义 | `FROM semantic.shop_identity_resolution_candidates`；`legacy_tokens = (none)`；72/72，差集 0/0 |
| 守护脚本（本地） | `python scripts/verify_identity_candidates_copy.py --target local` | 状态 `ok`，退出码 0 |
| 守护脚本（云端基线） | `python scripts/verify_identity_candidates_copy.py --target cloud` | 状态 **`drifted`**（副本自算），退出码 1 —— 这就是部署前的真实状态 |
| 逐月脚本 | `python scripts/verify_semantic_unknown_by_month.py --target local` | 生效日 2026-12-01、阈值 0 生效；11 月及之前全归 `known_legacy`，不报警 |

## 5. 部署后验收（判据）

```
python scripts/verify_identity_candidates_copy.py --target cloud
```

* 状态必须是 **`ok`**（不再是 `drifted`）；
* 「从正本取数 = 是」；
* 「仅正本有 = 0」「仅副本有 = 0」；
* 退出码 **0**。

巡检侧同时应当看到 `ops.pipeline_step_log` 里
`step_name = check_identity_candidates_copy` 的 `status = success`。
