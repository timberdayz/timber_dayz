# 本地→云端数据库同步：核心流程与涉及工具/文件

本文档在**执行提案实现之前**说明：同步的核心流程、会用到的工具与文件，便于团队达成一致理解。

---

## 一、核心流程（单次同步的一次完整运行）

一次同步由**运行在本地采集环境**上的**单个入口脚本**触发（手动或 Cron）。对每张 b_class 表执行「先结构对齐、再数据同步」，整体顺序如下。

```
┌─────────────────────────────────────────────────────────────────────────┐
│  触发：Cron 或手动执行入口脚本（如 sync_local_to_cloud.py）               │
│  运行位置：本地采集环境（能同时连本地 DB 与云端 DB 的机器）                 │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  1. 连接                                                                  │
│     本地 DB：DATABASE_URL（或默认当前环境）                                │
│     云端 DB：CLOUD_DATABASE_URL（环境变量）                               │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. 枚举待同步表                                                          │
│     SQL: information_schema.tables WHERE schema='b_class' AND ...        │
│     得到表名列表，如 fact_shopee_orders_daily, fact_shopee_products_daily │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. 对「每张表」循环执行：                                                │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │  3.1 结构对齐（先于数据同步）                                      │ │
│     │      · 从本地 information_schema.columns 取该表列名列表           │ │
│     │      · 若云端无此表 → 在云端建表（与 PlatformTableManager 一致）  │ │
│     │      · 若云端有此表 → 对「本地有、云端无」的列执行                │ │
│     │        ADD COLUMN IF NOT EXISTS "col" TEXT                       │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │  3.2 数据同步（增量）                                             │ │
│     │      · 按 last_sync 或 ingest_timestamp 取该表「之后」的行         │ │
│     │      · 在云端幂等写入（如 ON CONFLICT DO UPDATE）                 │ │
│     │      · 更新该表 last_sync 断点                                    │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│     单表失败：记日志，继续下一张表；不中断整次运行                         │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. 退出                                                                │
│     退出码：0=全部成功，非 0=存在失败；日志输出到指定文件（如 logs/...）   │
└─────────────────────────────────────────────────────────────────────────┘
```

要点：

- **结构对齐**：以本地 b_class 表结构为唯一来源，云端只「建表或补列」，不删列、不改类型。
- **数据同步**：按时间字段（优先 `ingest_timestamp`）增量 + 幂等 upsert，避免重复行。
- **单表失败不阻塞**：某表失败只记日志并继续其他表，便于重试与排查。

---

## 二、会用到的工具与脚本

| 类型 | 名称 | 状态 | 说明 |
|------|------|------|------|
| **入口脚本** | `scripts/sync_local_to_cloud.py` | **待实现** | 提案推荐的入口：无 `--tables` 时枚举 b_class、先结构对齐再按表增量同步、读/写断点、退出码与日志。Cron 建议调用此脚本。 |
| **可选复用** | `scripts/migrate_selective_tables.py` | 已有 | 当前支持 `--source`、`--target`、`--tables`、`--incremental`、`--where`；**不**支持：按 schema 枚举 b_class、结构对齐、last_sync 断点。若采用「扩展现有脚本」方案，需在此脚本中增加：不传 `--tables` 时枚举 b_class、每表先结构对齐再同步、断点存储与读取。 |
| **结构/建表参考** | `backend/services/platform_table_manager.py` | 已有 | `PlatformTableManager._create_base_table` 定义 b_class 表的基础 DDL（系统列 + 索引）。同步时「云端无表则建表」需与此逻辑一致（或复用、或从表名解析 platform/data_domain 等后生成同等 DDL）。 |
| **列补全参考** | `backend/services/dynamic_column_manager.py` | 已有 | 动态列为 `ADD COLUMN IF NOT EXISTS "col" TEXT`。结构对齐时「云端有表则补列」与之一致即可。 |
| **非 b_class 用** | `scripts/sync_schema_columns.py` | 已有 | 按 `schema.py`（Base.metadata）对**已存在表**补列，面向 ORM 定义的表；**不处理 b_class**（b_class 表不在 schema.py）。本地→云端 b_class 的结构对齐需单独实现（以 information_schema 为来源）。 |

结论：

- **入口**：以新建 `scripts/sync_local_to_cloud.py` 为推荐；若选扩展 `migrate_selective_tables.py`，需在文档中明确「无 --tables 时枚举 b_class + 结构对齐 + 断点」为该脚本的新行为。
- **结构对齐与建表**：不直接调用 `sync_schema_columns.py`，而是用 `information_schema` + 与 `PlatformTableManager` / `DynamicColumnManager` 一致的 DDL 逻辑（或封装成可复用函数供同步脚本调用）。

---

## 三、涉及的文件与配置

### 3.1 代码与脚本（实现时会涉及）

| 路径 | 用途 |
|------|------|
| `scripts/sync_local_to_cloud.py`（或扩展现有迁移脚本） | 同步入口：枚举 b_class、结构对齐、增量同步、断点、退出码与日志。 |
| `backend/services/platform_table_manager.py` | 参考或复用：云端「无表则建表」的 DDL 与表名解析规则。 |
| `backend/services/dynamic_column_manager.py` | 参考：动态列类型（TEXT）与 `ADD COLUMN IF NOT EXISTS` 行为。 |

### 3.2 配置

| 配置项 | 说明 |
|--------|------|
| `DATABASE_URL` | 本地 PostgreSQL 连接串（同步脚本所在环境，一般为采集环境）。 |
| `CLOUD_DATABASE_URL` | 云端 PostgreSQL 连接串；建议仅通过环境变量提供，不写死在代码或仓库。 |
| last_sync 存储 | 每表断点存于「本地 DB 的配置/状态表」或「脚本可写的 JSON/文件」；实现时二选一并在文档中写明。 |

### 3.3 文档（提案已约定需更新或引用）

| 路径 | 用途 |
|------|------|
| `docs/guides/DATA_MIGRATION_GUIDE.md` | 已有迁移与选择性表迁移说明；需增加「本地→云端 4 时段同步」章节：入口命令、Cron 示例、环境变量、结构对齐与增量策略。 |
| `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md` | 已有云端更新与本地验证；可在此增加「本地→云端 B 类表定时同步」小节或链接到 DATA_MIGRATION_GUIDE。 |
| `.env.example`（或部署文档） | 增加 `CLOUD_DATABASE_URL` 变量名与格式示例（不含真实密码）。 |

### 3.4 提案与设计（本变更）

| 路径 | 用途 |
|------|------|
| `openspec/changes/add-local-to-cloud-sync/proposal.md` | 变更动机、What Changes、Impact、Non-Goals。 |
| `openspec/changes/add-local-to-cloud-sync/design.md` | 决策：错峰、表枚举、增量与断点、结构对齐、错误与配置。 |
| `openspec/changes/add-local-to-cloud-sync/tasks.md` | 实现任务列表（含结构对齐、枚举、增量、验收）。 |
| `openspec/changes/add-local-to-cloud-sync/SYNC_FLOW_AND_ARTIFACTS.md` | 本说明：核心流程与涉及工具/文件。 |

---

## 四、Cron 与运行环境小结

- **谁执行**：本地采集环境上的 Cron（或运维手动）。
- **建议 Cron 表达式**：`30 6,12,18,22 * * *`（与采集 6:00、12:00、18:00、22:00 错开 30 分钟）。
- **示例命令**（路径按部署替换）：
  `30 6,12,18,22 * * * cd /path/to/xihong_erp && python scripts/sync_local_to_cloud.py >> logs/sync_local_to_cloud.log 2>&1`
- **网络与权限**：运行同步的机器必须能同时连接本地 DB 与云端 DB（防火墙/安全组、账号权限需放通）。

---

## 五、与「不执行提案」的边界

- 本文档仅描述**设计中的**核心流程和会用到/会改动的工具与文件，**不包含具体代码实现**。
- 在团队对上述流程与涉及工具/文件达成清晰一致后，再按 `tasks.md` 执行提案实现即可。
