# 主账号 / 店铺账号切换 Runbook

**适用范围**
- 本次 `main_accounts / shop_accounts / shop_account_aliases / shop_account_capabilities / platform_shop_discoveries` 重构上线
- 迁移脚本: `migrations/versions/20260402_main_shop_account_domain_chain.py`
- 目标版本: `20260402_main_shop_accounts`

**目标**
- 把运行时账号模型切换为“主账号级会话 + 店铺账号级采集”
- 保持旧 `core.platform_accounts` 作为历史源表保留
- 在迁移后完成 API 冒烟、页面联调和回滚可控

---

## 1. 执行原则

1. 在维护窗口执行。
2. 先备份数据库，再跑迁移。
3. 先验证数据库，再放开页面和采集任务。
4. 在确认真实写流量切到新模型前，不删除旧表，不删除兼容层。
5. 如需回滚，优先按“是否已经产生新写入”决定是应用回滚还是数据库恢复。

---

## 2. 前置检查

### 2.1 代码与环境

- 当前代码应在已合并的 `main` 上。
- 本地验证基线应至少包含这组回归:

```powershell
pytest backend/tests/test_main_shop_account_schema_contract.py `
  backend/tests/test_main_shop_account_migration_contract.py `
  backend/tests/test_shop_account_loader_service.py `
  backend/tests/test_component_test_runtime_config.py `
  backend/tests/test_component_test_runtime_config_shop_accounts.py `
  backend/tests/test_main_accounts_api.py `
  backend/tests/test_shop_accounts_api.py `
  backend/tests/test_shop_account_aliases_api.py `
  backend/tests/test_platform_shop_discoveries_api.py `
  backend/tests/test_collection_frontend_contracts.py `
  backend/tests/test_collection_executor_reused_session_scope.py `
  backend/tests/test_collection_account_capability_alignment.py `
  backend/tests/test_component_recorder_gate_contract.py `
  backend/tests/test_recorder_segment_validator.py `
  backend/tests/test_component_tester_account_loading.py `
  backend/tests/test_target_management_extended_fields.py `
  backend/tests/test_add_performance_income_acceptance.py `
  backend/tests/test_account_management_import_path_removed.py -q
```

预期: `72 passed`

### 2.2 服务状态

- PostgreSQL 可连接
- Redis 可连接
- 后端服务和前端服务准备好重启
- 如有定时采集任务，先暂停维护窗口内的新任务创建

### 2.3 现状确认

迁移前先记录旧表规模，作为对账基线:

```powershell
@'
import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("select count(*) from core.platform_accounts")
print("platform_accounts", cur.fetchone()[0])
cur.execute("select count(*) from core.alembic_version")
print("core.alembic_version", cur.fetchone()[0])
cur.close()
conn.close()
'@ | python -
```

---

## 3. 备份步骤

### 3.1 必做备份

至少备份以下对象:
- 全库备份
- `core.platform_accounts`
- `core.alembic_version`

### 3.2 Docker Postgres 推荐方式

如果开发/测试环境使用仓库默认 Docker Postgres:

```powershell
$backupDir = "F:\Vscode\python_programme\AI_code\xihong_erp\temp\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
docker exec xihong_erp_postgres pg_dump -U erp_user -d xihong_erp -Fc -f "/tmp/xihong_erp_$stamp.dump"
docker cp "xihong_erp_postgres:/tmp/xihong_erp_$stamp.dump" "$backupDir\xihong_erp_$stamp.dump"
```

### 3.3 非 Docker 环境

确保 `DATABASE_URL` 指向目标库后执行:

```powershell
python -m alembic current
```

并使用你们标准 PostgreSQL 备份方式完成快照。

---

## 4. 迁移执行

### 4.1 设置数据库连接

先确认 `DATABASE_URL` 指向目标库:

```powershell
$env:DATABASE_URL="postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp"
python -m alembic current
```

迁移前预期版本应不高于 `20260401_public_alembic_archive`。

### 4.2 执行迁移

```powershell
python -m alembic upgrade head
```

### 4.3 迁移后确认版本

```powershell
python -m alembic current
```

预期输出包含:

```text
20260402_main_shop_accounts
```

---

## 5. 数据库核对

### 5.1 表是否存在

```powershell
@'
import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
select table_name
from information_schema.tables
where table_schema = 'core'
  and table_name in (
    'main_accounts',
    'shop_accounts',
    'shop_account_aliases',
    'shop_account_capabilities',
    'platform_shop_discoveries'
  )
order by table_name
""")
print(cur.fetchall())
cur.close()
conn.close()
'@ | python -
```

### 5.2 行数对账

```powershell
@'
import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
for sql in [
    "select count(*) from core.platform_accounts",
    "select count(*) from core.main_accounts",
    "select count(*) from core.shop_accounts",
    "select count(*) from core.shop_account_aliases",
    "select count(*) from core.shop_account_capabilities",
]:
    cur.execute(sql)
    print(sql, "=>", cur.fetchone()[0])
cur.close()
conn.close()
'@ | python -
```

核对规则:
- `shop_accounts` 应与旧 `platform_accounts` 一一对应
- `main_accounts` 应小于等于 `platform_accounts`
- `shop_account_aliases` 应等于旧表中非空 `account_alias` 的数量
- `shop_account_capabilities` 应等于旧 `capabilities` JSON 展开后的条目数

### 5.3 关键兜底检查

确认 `parent_account` 为空的旧记录是否回退为自身 `shop_account_id -> main_account_id`:

```powershell
@'
import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
select shop_account_id, main_account_id
from core.shop_accounts
where main_account_id = shop_account_id
limit 20
""")
print(cur.fetchall())
cur.close()
conn.close()
'@ | python -
```

---

## 6. 服务重启与 API 冒烟

### 6.1 重启后端和前端

按你们当前运行方式重启服务。

本地开发常用:

```powershell
python run.py --local
```

或单独重启后端/前端。

### 6.2 API 冒烟

至少检查以下接口:

- `GET /api/main-accounts`
- `GET /api/shop-accounts`
- `GET /api/shop-account-aliases/unmatched`
- `GET /api/platform-shop-discoveries`
- `GET /api/component-versions`

如需快速确认健康状态:

```powershell
Invoke-WebRequest http://127.0.0.1:8001/api/health -UseBasicParsing
```

---

## 7. 人工验收清单

### 7.1 账号管理页

页面: [AccountManagement.vue](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/AccountManagement.vue)

验收项:
- 能创建主账号ID + 店铺账号ID
- 主账号ID必填
- 店铺账号ID、平台店铺ID、店铺别名、店铺数据域能力文案正确
- 批量添加店铺仍可用
- 状态切换正常

### 7.2 组件版本页

页面: [ComponentVersions.vue](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/ComponentVersions.vue)

验收项:
- 测试弹窗显示“测试店铺”
- 店铺下拉能加载目标店铺账号
- 发起测试时请求体发送 `shop_account_id`
- 同主账号下切不同店铺不重复登录

### 7.3 运行时

关键文件: [executor_v2.py](F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/executor_v2.py)

验收项:
- 会话复用按 `main_account_id`
- 任务归属按 `shop_account_id`
- 登录后可写入 `platform_shop_discoveries`
- 需要店铺切换的平台在导出前先切店

---

## 8. 回滚决策

### 8.1 可以只回滚应用的情况

满足以下条件时，可以优先只回滚代码版本:
- 迁移已完成
- 还没有放开真实业务写入
- 只是新页面/API/运行时行为异常

原因:
- 本次迁移不会删除旧 `core.platform_accounts`
- 老版本代码仍可基于旧表运行

### 8.2 必须恢复数据库备份的情况

满足以下任一条件时，优先恢复数据库备份:
- 新版本已经开始产生真实账号/店铺写入
- 新版本已经写入了只存在于新表的数据
- 需要回到“迁移前完全一致”的数据状态

原因:
- `alembic downgrade` 只会删除新表
- 它不会把迁移后新增的业务写入自动回灌到旧 `platform_accounts`

### 8.3 不推荐作为主回滚手段

```powershell
python -m alembic downgrade 20260401_public_alembic_archive
```

这个命令只能作为“无新写入、仅快速撤回结构”的辅助操作，不应替代数据库恢复。

---

## 9. 故障处理

### 9.1 迁移命令失败

先检查:
- `python -m alembic current`
- `DATABASE_URL` 是否指向正确数据库
- `core.alembic_version` 当前版本号

如果失败且版本未推进:
- 修复后重新执行 `python -m alembic upgrade head`

如果失败且数据库处于不确定状态:
- 停止继续写入
- 恢复备份
- 再重新演练

### 9.2 迁移成功但页面异常

优先检查:
- `/api/main-accounts`
- `/api/shop-accounts`
- `/api/shop-account-aliases/unmatched`
- 浏览器控制台
- 后端日志

### 9.3 组件测试页没有店铺选项

优先检查:
- `shop_accounts` 是否有数据
- `/api/shop-accounts?platform=xxx&enabled=true` 是否返回店铺账号
- 页面是否真的部署了本次合并后的 `main`

---

## 10. 执行完成标准

完成切换的最低标准:
- Alembic 当前版本为 `20260402_main_shop_accounts`
- 新 5 张表全部存在
- `shop_accounts` 行数与旧 `platform_accounts` 对齐
- 账号管理页创建和编辑正常
- 组件测试页按“测试店铺”工作
- 至少一个真实主账号下的多店铺测试验证会话复用成功

只要以上任一项未通过，就不要宣布切换完成。
