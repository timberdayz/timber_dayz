# 商品中心 SKU 采购价批量录入 v1

**状态**:设计稿待评审  
**日期**:2026-09-18  
**范围**:本地开发库 `core.dim_erp_sku.default_purchase_cost` 字段批量回填,数据源为 `product-catalog` skill 的 `sku-reverse-lookup.xlsx` 第 9 列。  
**非范围**:本文件不修改 `sku_operating_profiles.selling_price` / 不涉及云端库 / 不修改 SPU 级或品类数据 / 不重建 `sku-reverse-lookup.xlsx`。

---

## 1. 决策

### 1.1 一次性脚本(不是服务/定时任务)

通过单次执行的 Python 脚本 `scripts/import_purchase_prices.py` 完成录入。脚本参数化 `DATABASE_URL`(默认读 `.env`,可显式覆盖),先在本地开发库跑通验证后,再用同一脚本指向云端库跑第二次。

**不**走 `POST /api/skus/bulk` 接口 —— 该接口每次 PATCH 单条会触发审计日志,1121 条逐条走对服务有压力;直接 SQL 在单事务内完成,失败全回滚,符合"批量数据迁移"语义。

### 1.2 严格遵循 skill 的数据契约

采购价 ≠ 售价。skill `encoding.md` §11 明确:`第 9 列采购单价(元)` 是工厂报价 = 成本,不是平台售价。本 spec 只录"采购成本"语义,不触发任何定价/售价侧字段。

### 1.3 本地先、云端后(用户明确要求)

执行分两阶段:

| 阶段 | 目标库 | 触发条件 | 验证清单 |
|---|---|---|---|
| **阶段 1** | 本地开发库(localhost:15432,DB 名 `xihong_erp`) | 立即执行 | 见 §5 |
| **阶段 2** | 云端库(`CLOUD_DATABASE_URL` 或运行时指定) | **阶段 1 验证通过后,人工确认**才进入 | 同 §5 + 业务侧复核 |

两阶段使用**同一个脚本**,差异仅在 `--database-url` 参数。

---

## 2. 数据契约

### 2.1 输入数据源

| 字段 | 值 |
|---|---|
| 文件路径 | `F:\Work Tool\resource\skills\team-skills\product-catalog\sku-reverse-lookup.xlsx` |
| Sheet 名 | `SKU反查表`(实际工作表名) |
| 表头行 | 第 1 行,9 列 |
| 数据行数 | 1122 条 |
| 关键列 | 第 1 列 `SKU code`、第 9 列 `采购单价(元)` |

### 2.2 跳过规则

| 价格值 | 处理 | 原因 |
|---|---|---|
| 数字 > 0 | 写入 | 正常价格 |
| 数字 = 0 | **跳过**(本批次 0 条) | skill 表示这是"待报价"标记的退化形态 |
| 字符串 `—`(em-dash,U+2014) | **跳过**(本批次 36 条) | skill 明确"待报价"约定,不写 0 避免误读 |
| 字符串其他 | **报错退出**,把整条记录写入错误日志 | 不接受非数字价格 |
| 单元格为空 | **跳过**(本批次 0 条) | 与 `—` 同等对待 |

**本批次预计写入:1086 条**(1122 - 36)。

### 2.3 写入字段映射

| DB 字段(`core.dim_erp_sku`) | 来源 | 备注 |
|---|---|---|
| `default_purchase_cost` | xlsx 第 9 列(过滤后) | Float,只接受 > 0 |
| `purchase_cost_currency` | 固定 `CNY` | 与 skill §11 一致;DB 默认值,无需写入 |
| `purchase_cost_source` | 固定 `妙手导入` | 与 skill §11 「采购独家维护,运营只读」对齐;采购侧唯一可信源 |
| `purchase_cost_confidence` | 固定 `medium` | 批量从妙手导入,人工未逐条复核;不是 high |
| `purchase_cost_confirmed_at` | 脚本执行时刻(`datetime.now(timezone.utc)`) | 标记本次录入时间 |
| `updated_at` | DB 触发器自动 `now()` | 不显式写入 |

**不修改字段**:`sku_key` / `sku_name` / `status` / `erp_record_id` / `weight_kg` / `package_*` / `unit_volume_cbm` / `units_per_carton` / `turnover_class` / `reference_selling_price` 等。

### 2.4 匹配键

`xlsx 第 1 列 SKU code` ↔ `core.dim_erp_sku.sku_key`

匹配规则:
- 字符串相等(去除两端空白后)
- 大小写敏感(skill 中 SKU code 沿用妙手导出,大写为主)

---

## 3. 架构与组件

### 3.1 单一脚本(无外部依赖服务)

```
scripts/import_purchase_prices.py
├─ argparse: --database-url, --xlsx-path, --dry-run, --skip-backup
├─ openpyxl: 读 xlsx
├─ asyncpg: 连 PostgreSQL
└─ 输出到 output/ 目录
```

**外部依赖**(已在项目环境验证可用):
- `openpyxl` ✓(在 xlsx 读取时已验证)
- `asyncpg` ✓(在本次会话库存验证时已验证)
- `argparse` / `logging` / `json`(标准库)

### 3.2 数据流

```
            ┌─────────────────────────────────┐
            │ xlsx 1122 行                     │
            │  1086 行有价(>0)               │
            │    36 行 —  (待报价,跳过)       │
            └──────────────┬──────────────────┘
                           │ openpyxl
                           ▼
            ┌─────────────────────────────────┐
            │ 内存列表 [(sku_code, price)]    │
            └─────┬───────────────────────┬───┘
                  │                       │
                  │读 DB sku_key         │
                  │SELECT sku_key         │
                  │FROM dim_erp_sku       │
                  ▼                       ▼
      ┌─────────────────────┐  ┌──────────────────────────┐
      │ 对账:               │  │ 主流程:                  │
      │  - lookup_only      │  │  1086 条匹配 → UPDATE    │
      │    (lookup 有,      │  │  (单事务,失败全回滚)     │
      │     DB 没有)        │  └──────────────────────────┘
      │  - db_only          │
      │    (DB 有,          │
      │     lookup 没有)    │
      └─────────────────────┘
```

### 3.3 错误处理

| 场景 | 处理 |
|---|---|
| xlsx 文件不存在 / 不可读 | 退出码 2,日志写明 |
| xlsx 列结构不符合(列数 < 9 或表头不符) | 退出码 2,日志写明 |
| 价格列出现非数字、非 `—` 字符串 | 退出码 2,该行写入错误日志 |
| DB 连接失败 | 退出码 2,日志写明 |
| UPDATE 期间网络断开 / 约束冲突 | 自动 ROLLBACK,退出码 2 |
| 对账有差异(`lookup_only` 或 `db_only` 非空) | **不阻断**,写入对账文件,退出码 1(让用户决定是否继续) |
| 全部成功 | 退出码 0 |

---

## 4. 回滚方案

### 4.1 备份(执行前必做)

```sql
CREATE TABLE core.dim_erp_sku_backup_20260918 AS
SELECT * FROM core.dim_erp_sku;
```

- 备份表与原表同 schema、同结构、全量行
- 备份在 `core` schema(避免与业务表混淆)
- **保留 7 天**后再手动 DROP(避免误操作期间无法回滚)
- `--skip-backup` 参数可跳过(仅当用户明确确认已有备份时使用)

### 4.2 回滚方式

| 场景 | 操作 |
|---|---|
| 部分行写错 / 数据不准 | 从 `dim_erp_sku_backup_20260918` 反向 UPDATE:`UPDATE dim_erp_sku t SET default_purchase_cost = b.default_purchase_cost, purchase_cost_source = b.purchase_cost_source, purchase_cost_confirmed_at = b.purchase_cost_confirmed_at FROM dim_erp_sku_backup_20260918 b WHERE t.sku_id = b.sku_id` |
| 全表回滚(回到执行前状态) | `DROP TABLE core.dim_erp_sku; ALTER TABLE core.dim_erp_sku_backup_20260918 RENAME TO dim_erp_sku;`(需先 drop 约束,简单做法是直接 UPDATE 反向) |
| 备份本身失效 | dry-run 阶段生成的 `purchase_price_import_dryrun_20260918.csv` 含 old_price / new_price,可生成反向 UPDATE 脚本 |

### 4.3 不引入新表 / 不修改 schema

备份表是**临时**的(7 天后清理),不进 Alembic 迁移,不进 `Base.metadata`。

---

## 5. 验证

### 5.1 执行前(dry-run 阶段)

- dry-run 模式不写库,只生成 preview 文件
- preview 文件可人工抽样核对

### 5.2 执行后(必跑)

1. **覆盖率核对**:
   ```sql
   SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost IS NOT NULL;
   -- 期望 ≈ 成功更新数(允许 ±1 误差,因 DB 原已有 2 条)
   ```
2. **脏数据检查**:
   ```sql
   SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost < 0;
   -- 期望 = 0
   SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost = 0;
   -- 期望 = 0(skill 约定不用 0 表"待报价")
   ```
3. **元数据覆盖**:
   ```sql
   SELECT purchase_cost_source, COUNT(*) FROM core.dim_erp_sku
   WHERE default_purchase_cost IS NOT NULL
   GROUP BY purchase_cost_source;
   -- 期望 purchase_cost_source = '妙手导入' 占绝大多数
   ```
4. **抽样 10 条人工对比**:
   脚本输出 `purchase_price_sample_check_20260918.csv`,含 SKU code + xlsx 第9 列 + DB 当前值 + 差异标记

---

## 6. 输出文件(全部进 `output/`)

| 文件名 | 何时生成 | 用途 |
|---|---|---|
| `purchase_price_reconciliation_20260918.csv` | dry-run + 真实执行前 | 对账报告:lookup_only / db_only 两段 |
| `purchase_price_import_dryrun_20260918.csv` | dry-run | 预览即将变更的 1086 条(sku_code, old_price, new_price, status, confidence) |
| `purchase_price_import_log_20260918.txt` | 真实执行 | 执行日志:开始/结束时间、影响行数、错误明细 |
| `purchase_price_sample_check_20260918.csv` | 真实执行后 | 抽样 10 条供人工对比 |

日志格式:人类可读 + 时间戳,含阶段(RECONCILIATION / BACKUP / UPDATE / VERIFY)。

---

## 7. 接口

### 7.1 命令行

```bash
# 默认 dry-run 模式(读 .env 的本地库)
python scripts/import_purchase_prices.py

# 真实执行(本地)
python scripts/import_purchase_prices.py --apply

# 真实执行 + 指向云端库
python scripts/import_purchase_prices.py --apply \
    --database-url "postgresql://user:pass@cloud-host:5432/xihong_erp"

# 跳过备份(慎用)
python scripts/import_purchase_prices.py --apply --skip-backup
```

### 7.2 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--database-url` | `settings.DATABASE_URL`(即 `.env` 的本地库) | 覆盖数据库连接 |
| `--xlsx-path` | `F:\Work Tool\resource\skills\team-skills\product-catalog\sku-reverse-lookup.xlsx` | 数据源 |
| `--apply` | False | 不带 = dry-run,带 = 真实执行 |
| `--skip-backup` | False | 跳过备份表创建(默认 False,强烈不建议) |

### 7.3 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部成功,数据已写入 |
| 1 | 对账有差异(`lookup_only` / `db_only` 非空),需人工 review dry-run 报告 |
| 2 | 执行错误(已自动回滚或未启动写入) |

---

## 8. 责任分工

| 角色 | 职责 |
|---|---|
| 海川(Owner) | review spec、对账报告、阶段 2 启动决策 |
| 采购 | 工厂报价准确性最终责任人(本 spec 不修改其流程,只消费其输出) |
| agent(本会话执行) | 写脚本 + dry-run + 阶段 1 真实执行 + 阶段 2(待人工批准) |

---

## 9. 不做的事(防越权)

- ❌ 不修改 `sku_operating_profiles.selling_price`(售价,语义不同)
- ❌ 不修改 SPU 字段(`logistics_damage_rate` / `return_loss_rate` / `category_*`)
- ❌ 不重建 `sku-reverse-lookup.xlsx`(skill 维护者职责)
- ❌ 不引入 Alembic 迁移(无 schema 变更)
- ❌ 不修改后端 API / 前端
- ❌ 不对 `—` 行写 0
- ❌ 不在备份表进 Base / 进版本控制
- ❌ 不自动执行阶段 2(必须人工批准)