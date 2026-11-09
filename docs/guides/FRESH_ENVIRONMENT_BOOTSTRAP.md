# 全新环境引导（空库从零建库）

> 面向：新环境搭建、迁移链断在 `20261116`、"账号不存在"报错的排查。

## 一、问题：空库上迁移链跑不完

`current_schema_20261116_add_tiktok_export_store_name_aliases` 是**数据修复型**迁移：
它给 6 个**已存在的** TikTok 店铺账号补「导出店名」别名，动手前做 fail-closed 前置检查
（账号存在 / 区域相符 / 已启用 / 是经营店 / 别名键没被别人认领）。

全新空库上 `core.shop_accounts` 里没有这些账号 ⇒ 前置检查必然失败 ⇒ 整条链在该步中止。

实测（临时 Postgres，不注入任何种子）：

```
[阶段1] alembic upgrade current_schema_20261115_add_sku_platform_pricing -> 退出码 0
[阶段2] run_current_schema_migrations.py                                 -> 退出码 1
        RuntimeError: TikTok 别名补录的前置检查未通过，拒绝继续：
        账号不存在: tiktok_sg_daone_mall_local（别名 DAONE Mall）；…… （共 6 条）
```

受影响的真实调用方：

| 调用方 | 现象 |
|---|---|
| `scripts/rebuild_local_current_schema.py` | drop 库 → create 空库 → 跑迁移 ⇒ 卡在 20261116 |
| `docker-compose.prod.yml` / `.dev.yml` 的 `migrate` 服务 | 同一个 runner ⇒ 同样卡住 |
| `docker/scripts/backend-entrypoint.sh` | 启动时跑同一个 runner ⇒ 同样卡住 |

## 二、为什么不能改迁移

1. **已应用迁移不可变**（`current_migrations/versions/20260914_warehouse_platform_profit.py:3`：
   "Previous migration files remain immutable"）；
2. **插一个新修订也不行**：链是严格线性的，要在 20261116 之前插入就得改 20261116 的
   `down_revision`，那同样是改已应用文件；
3. **让迁移在空库上 no-op 更不可接受**：那会把「全新环境缺 TikTok 导出别名」这个
   **真实部署缺陷**悄悄掩掉。

⇒ 唯一不动迁移的做法是**两段式引导**：

1. 先把链升到 **20261116 的前一个节点** `current_schema_20261115_add_sku_platform_pricing`
   （此时 `core.main_accounts` / `core.shop_accounts` 已由更早的迁移建好）；
2. 注入引导账号（主账号 + 6 个 TikTok 出口账号）；
3. 再把链升到 head。

## 三、怎么用

### 3.1 真实新环境（推荐路径）

```powershell
# 1) 打印清单模板
python scripts/bootstrap_fresh_environment.py --print-template > bootstrap.json

# 2) 填好真实值（主账号凭据 + 6 个店的显示名）
#    shop_account_id / shop_region 是固定的，不用改

# 3) 执行两段式引导
python scripts/bootstrap_fresh_environment.py --manifest bootstrap.json --database-url <你的库>
```

清单字段说明：

| 字段 | 谁提供 | 说明 |
|---|---|---|
| `main_account.platform` | 固定 `tiktok` | |
| `main_account.main_account_id` / `username` / `password_encrypted` / `main_account_name` | **运维** | 真实值；`password_encrypted` 存的是加密后的口令 |
| `shop_accounts[].shop_account_id` | 固定 | 必须来自清单里的 6 个 id，多一个少一个都会被拒 |
| `shop_accounts[].shop_region` | 固定 | 与迁移常量逐字一致；填错会被拒 |
| `shop_accounts[].store_name` | **运维** | 该店的显示名（看板显示用） |

校验不通过时**不会写库**，并一次性列出全部问题（缺哪个账号、哪个区域不符、
哪个字段空着、出现了未知账号 id）。

### 3.2 临时库门禁（占位值，仅限一次性临时库）

```powershell
python scripts/validate_migrations_fresh_db.py
```

它在全新临时 Postgres 上跑全量链，并额外校验迁移后的**数据同步关键列**与
**ORM Schema 一致性**。占位值 profile 只在这一条路径上使用。

### 3.3 本地重建

```powershell
python scripts/rebuild_local_current_schema.py --confirm REBUILD_LOCAL_XIHONG_ERP
```

本地库本来就被清空，默认用占位值 profile 让链跑通；要真实值就加
`--bootstrap-manifest <清单.json>`。

### 3.4 空库上直接跑迁移会看到什么

`scripts/run_current_schema_migrations.py` 的**写路径**现在会挡下空库，并给出
上面这段指引（读路径的判定契约不变：空库仍然如实报告"可以 upgrade"）：

```
MigrationSafetyError: 当前数据库是全新空库，current-schema 迁移链无法直接跑完：
迁移 current_schema_20261116_add_tiktok_export_store_name_aliases 需要 6 个已存在的 TikTok 出口账号（fail-closed 前置检查）……
现成入口：
  python scripts/bootstrap_fresh_environment.py --manifest <你的引导清单.json>
```

## 四、清单的唯一真相点

`scripts/bootstrap_seed_manifest.py` 是清单的真源，**三方逐字一致**由守护用例钉死：

| 守护对象 | 守护用例 |
|---|---|
| 清单 ≡ 迁移常量 `_TIKTOK_EXPORT_ALIASES` | `backend/tests/test_bootstrap_seed_manifest.py::test_manifest_accounts_match_migration_constants` |
| 清单 ≡ Python 侧归一化 `normalize_alias_key` | `…::test_manifest_alias_normalized_matches_python_normalizer` |
| 第一段目标 ≡ 迁移的 `down_revision` | `…::test_precheck_target_is_the_revision_right_before_the_data_migration` |
| 两段顺序（迁移 → 注入 → 迁移） | `…::test_two_phase_bootstrap_runs_phase_one_then_seed_then_phase_two` |
| 门禁复用同一份实现 | `backend/tests/test_migration_gate_seed_data_contract.py::test_gate_script_runs_seed_injection_between_the_two_migration_phases` |

以前门禁有一份**独立复制**的账号清单，靠人肉同步；漂移的表现是"门禁突然报『账号不存在』"，
极难定位。现在三处调用方共用一份清单。

## 五、相关文件

- `scripts/bootstrap_seed_manifest.py` —— 引导清单（唯一真相点）+ 两种 profile
- `scripts/bootstrap_fresh_environment.py` —— 两段式引导的唯一实现 + 真实环境入口
- `scripts/migration_gate_seed_data.py` —— 门禁 profile 的薄适配层
- `scripts/validate_migrations_fresh_db.py` —— 临时库门禁（调用共享实现）
- `scripts/run_current_schema_migrations.py` —— 空库写路径守卫
- `scripts/rebuild_local_current_schema.py` —— 本地重建（调用共享实现）
- `backend/tests/test_bootstrap_seed_manifest.py` —— 守护用例

## 六、尚未纳入自动门禁的部分（后续项）

`scripts/validate_migrations_fresh_db.py` 需要 Docker 且耗时较长，目前是**显式命令**，
未接进 `scripts/verify_release_local.py` 与 CI。CI 里已由**快**的守护用例覆盖了
真正会漂移的部分（清单 ≡ 迁移常量、清单 ≡ Python 归一化、两段顺序）。
把全量空库演练接进发布门禁属于后续立项项。
