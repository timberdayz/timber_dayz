# 提案漏洞与遗漏分析（add-local-to-cloud-sync）

本文档列出审阅后发现的设计漏洞、边界未定项与实现时需补齐的点，便于在实现前或实现中闭环。

---

## 一、技术漏洞（实现时必须处理）

### 1. 云端建表外键导致 INSERT 失败

**问题**：`PlatformTableManager._create_base_table` 在云端建表时包含：

- `file_id INTEGER REFERENCES catalog_files(id) ON DELETE SET NULL`
- `template_id INTEGER REFERENCES field_mapping_templates(id) ON DELETE SET NULL`

同步到云端的数据行带有**本地的** `file_id`、`template_id`。云端若未同步 `catalog_files` / `field_mapping_templates`，或 id 不一致，INSERT 会因外键约束失败。

**建议**：设计已写「建表时外键可按需省略或设为 ON DELETE SET NULL」——**实现时必须明确**：在云端建 b_class 表时**不创建**对 `catalog_files`、`field_mapping_templates` 的外键（或仅在文档约定「云端不建这两张表时不得建该 FK」）。否则首笔数据同步即可能报错。

---

### 2. 结构对齐时「补列」只应对动态列、且类型固定为 TEXT

**问题**：设计写的是对「本地有而云端没有」的列执行 `ADD COLUMN IF NOT EXISTS col TEXT`。若实现时用「本地 information_schema 列集合 − 云端列集合」并全部按 TEXT 补列，会把**系统列**（如 `period_start_date`、`metric_date`）也当成缺失列补成 TEXT，导致类型错误或后续查询/同步异常。

**事实**：本地基础表已包含所有系统列（见 `_create_base_table`）；云端「无表则建表」会建齐系统列；真正会「缺失」的只有**动态列**（由 `DynamicColumnManager` 按模板追加，且均为 TEXT）。`DynamicColumnManager.SYSTEM_FIELDS` 未包含 `sub_domain`、`template_id`、`period_*`、`currency_code` 等，若用该集合过滤，仍有遗漏。

**建议**：实现时**显式维护一份「b_class 系统列」全集**（与 `_create_base_table` 及 `_ensure_period_columns_exist` 一致），结构对齐时仅对「本地有而云端无且不在系统列集合中」的列执行 `ADD COLUMN IF NOT EXISTS "col" TEXT`。或在 design/tasks 中写明：补列仅针对「动态列」，判断方式为「列名不在系统列集合中」。

---

### 3. 云端 UPSERT 的冲突键必须与本地一致

**问题**：本地写入使用唯一索引决定 ON CONFLICT 目标：

- **非 services**：`(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)`（表达式索引）
- **services**：`(data_domain, sub_domain, granularity, data_hash)`

若同步脚本在云端使用错误的冲突键（例如漏掉 COALESCE、或搞混 services/非 services），会导致重复行或更新错误。

**建议**：在 design 或 tasks 中明确约定：云端幂等写入必须与 `raw_data_importer` 一致——按**表名解析出 data_domain（及 services 时的 sub_domain）**，选用对应冲突子句；或从本地库查询该表的唯一索引定义再在云端复用。实现时需在脚本中写死或解析表名得到 data_domain/sub_domain，并据此选择 ON CONFLICT 表达式。

---

### 4. 主键 id 与序列（可选但建议约定）

**问题**：b_class 表为 `id BIGSERIAL PRIMARY KEY`。若同步时**带出本地 id** 插入云端，云端该表的 sequence 不会自动跟上，后续本地不存在的插入可能主键冲突；若不带 id、由云端自增，则云端 id 与本地不一致，若将来有「按 id 关联」的逻辑会出错。

**建议**：在 design 中二选一并写清：（A）同步行**不包含 id**，冲突仅按业务键 upsert，云端 id 自增；或（B）同步行**包含 id**，同步完成后对该表执行 `SELECT setval(pg_get_serial_sequence('b_class.\"table_name\"', 'id'), (SELECT MAX(id) FROM b_class.\"table_name\"))` 以修正序列。当前代码库入库不写 id（由 BIGSERIAL 生成），同步若也按「不写 id、按业务键 upsert」更一致，推荐（A）并在文档中写明。

---

## 二、边界与未决项（实现前或实现中需闭环）

### 5. last_sync 存储位置未定

**现状**：design 的 Open Questions 写「每表 last_sync 存于本地 DB 配置/状态表 或 脚本可写 JSON/文件，实现时按运维偏好选择」。

**风险**：若不在 tasks 中收口，实现可能各行其是（有人写 DB、有人写文件），不利于运维统一与文档说明。

**建议**：在 tasks 中增加一条「确定 last_sync 存储方式（DB 表 vs 文件）并在文档中写明」，或直接在 design 中选定一种（例如先采用「单文件 JSON：表名 -> last_sync 时间」），便于首次实现与文档一致。

---

### 6. 无时间字段表的策略未定

**现状**：design 写「若表无统一时间字段，则文档约定全量一次或跳过并记日志」；Non-Goals 写「不强制所有 B 类表必须有同一时间字段；可按表约定或跳过」。

**风险**：实现时若既不「全量一次」也不「跳过」，容易出现逻辑漏洞（例如每次全量且无断点，导致性能或重复写入问题）。

**建议**：在 design 或 tasks 中明确三选一并写进文档：对无 `ingest_timestamp`（及 fallback 字段）的表，（a）仅首次全量、之后跳过并记日志；（b）每次运行都全量（并说明适用场景）；（c）始终跳过并记日志。推荐（a）或（c），并在验收中加一条「无时间字段表行为符合文档约定」。

---

### 7. 首次运行（无 last_sync）的语义

**问题**：设计未写「第一次跑脚本、尚无 last_sync 时」是「全量同步该表」还是「不同步」。

**建议**：明确为：**无 last_sync 时视作全量**（无下界，或下界为 epoch），同步该表所有行后写入 last_sync = max(ingest_timestamp)。在 design 或 SYNC_FLOW 中补一句即可。

---

### 8. b_class 为空（0 张表）时的行为

**问题**：若本地 b_class 下没有表，脚本应正常退出（视为无事可做），退出码建议为 0，避免 Cron 误判失败。

**建议**：在 design 或 tasks 中写一句：「枚举结果为空时，记录日志并 exit 0」。

---

## 三、与现有脚本/代码的差异（避免误用）

### 9. migrate_selective_tables 默认不包含 b_class

**事实**：`get_table_names(engine)` 使用 `inspector.get_table_names()`，未传 schema，只返回 **public** 下的表；且 `SELECT * FROM {table_name}` 未带 schema，无法直接用于 b_class。

**结论**：若通过扩展 `migrate_selective_tables` 实现本提案，必须改为「按 schema 枚举」（如 `--schema b_class`）且所有 SQL 使用 `b_class."table_name"`；否则现有逻辑无法覆盖 b_class。新建独立脚本则不受此限，但需在文档中说明与 migrate_selective_tables 的职责边界。

---

### 10. information_schema 与 schema 限定

**事实**：枚举表、读列、ALTER TABLE 均需带 schema：`information_schema.tables WHERE table_schema = 'b_class'`，`information_schema.columns` 同理；ALTER 为 `ALTER TABLE b_class."{table_name}" ADD COLUMN ...`。

**建议**：在 tasks 中明确「所有对 b_class 的查询与 DDL 均使用 schema 限定（b_class）」，避免实现时漏写 schema 导致在 public 下建表或查错表。

---

## 四、安全与运维（已基本覆盖，可加强）

- **配置**：云端 URL 仅环境变量、不打印明文，design 已约定。
- **网络与权限**：SYNC_FLOW 已写「运行同步的机器须能同时连本地 DB 与云端 DB」；可补充「云端 DB 账号需具备 b_class 的 CREATE/ALTER 与 INSERT/UPDATE 权限」。
- **日志与退出码**：已约定单表失败不阻塞、退出码区分成功/失败、不用 Emoji，无漏洞，可保持。

---

## 五、建议的 design/tasks 补充（摘要）

| 项 | 建议补充内容 |
|----|----------------|
| 外键 | 在 design 或 tasks 中写明：云端建 b_class 表时**不创建**对 catalog_files / field_mapping_templates 的外键。 |
| 补列范围 | 在 design 或 tasks 中写明：结构对齐时仅对「非系统列」补列，且类型为 TEXT；系统列列表与 `_create_base_table` + period 列一致。 |
| UPSERT 冲突键 | 在 design 或 tasks 中写明：云端 ON CONFLICT 与 raw_data_importer 一致，按表名解析 data_domain/sub_domain 选用 (platform_code, COALESCE(shop_id,''), data_domain, granularity, data_hash) 或 (data_domain, sub_domain, granularity, data_hash)。 |
| id 与序列 | 在 design 中约定：同步行不包含 id，冲突按业务键 upsert；或约定带 id 时同步后修正 sequence，二选一。 |
| last_sync 存储 | 在 tasks 中增加「确定 last_sync 存储方式并写入文档」或直接在 design 选定方案。 |
| 无时间字段表 | 在 design 中明确（a）（b）（c）之一并写入文档与验收。 |
| 首次运行 | 在 design 或 SYNC_FLOW 中写：无 last_sync 时对该表全量同步，再写入 last_sync。 |
| 空 b_class | 在 design 或 tasks 中写：枚举为空时记录日志并 exit 0。 |
| schema 限定 | 在 tasks 中写：所有 b_class 相关 SQL 使用 schema='b_class' / b_class."table_name"。 |

---

以上漏洞与未决项闭环后，再按 tasks 实现可降低返工与线上故障风险。
