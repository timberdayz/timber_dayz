# Change: 重构本地到云端的 B 类数据同步设计

## Why

现有提案将问题建模为“按表枚举 + 定时脚本 + 运行时补齐动态列”的迁移方案，这已经不适合当前代码库的真实数据模型。

当前 B 类表的真实情况是：
- 每条记录已经以 `raw_data JSONB` 保存完整业务载荷。
- `header_columns` 保存原始表头，用于追溯字段来源。
- 动态列是为了查询便利而追加的镜像列，不是唯一真源。
- `data_hash` 与现有唯一索引共同承担幂等更新能力。

如果继续沿用旧提案的思路，会有几个问题：
- 同步过程与动态列强耦合，云端 schema 会被运行时 DDL 推着演化，难以治理。
- 动态列是 `TEXT` 投影，不适合作为高保真同步主源。
- 字段名归一化、货币后缀清理、模板更新后，历史数据和新数据的语义对齐缺少清晰边界。
- 使用通用迁移脚本扫描业务表，不符合“高保真、可追溯、可幂等”的同步目标。

因此需要把本变更重构为：以 B 类记录的固定系统字段 + `raw_data/header_columns` 为权威同步载荷，动态列仅作为派生查询层，数据同步与投影/schema 演化解耦。

## What Changes

- 重新定义 B 类同步的权威载荷：
  - 同步固定系统字段和元数据字段，如 `platform_code`、`shop_id`、`data_domain`、`granularity`、`sub_domain`、`metric_date`、`period_*`、`file_id`、`template_id`、`data_hash`、`ingest_timestamp`、`currency_code`
  - 同步 `raw_data JSONB`
  - 同步 `header_columns`
- 明确动态列不是同步真源：
  - 同步链路不依赖动态列存在与否
  - 同步链路不在运行时向云端追加动态列
  - 动态列或报表投影由独立的投影刷新流程负责
- 调整本地到云端的实现策略：
  - 当前阶段推荐“固定字段 canonical micro-batch sync”
  - 不再把现有 `migrate_selective_tables.py` 视为主实现
  - 未来如需升级到 CDC / logical replication，应先引入与动态列解耦的 canonical mirror 或 outbox/change-log
- 强化字段谱系与历史精度：
  - 历史 `raw_data` 不因字段改名或模板演进而被回写重写
  - 历史 `header_columns` 必须保留
  - 新旧字段语义对齐放到显式的字段别名/版本化投影规则中处理，而不是在同步阶段隐式改写历史记录
- 保留定时同步节奏，但收紧同步边界：
  - 可以继续采用与采集错峰的四时段运行方式
  - 但同步任务的职责仅限于可靠搬运 canonical payload，不负责运行时 schema 演化

## Recommended Direction

本变更推荐采用：

`本地 b_class 业务表 -> 读取固定 canonical 字段 + raw_data/header_columns -> 云端 canonical mirror 表 -> 独立投影/报表刷新`

推荐该方案的原因：
- 与当前代码库现状最匹配，改造成本最低。
- 不要求云端实时跟随动态列变更。
- 能把“数据保真”和“查询便利”分层处理。
- 对字段改名、模板变更、货币后缀归一化更稳健。

本变更不推荐直接使用 PostgreSQL logical replication 同步当前本地 B 类表本体，因为当前本地表仍物理包含动态列，直接复制会把云端重新拖回 schema 强耦合状态。若未来要采用 logical replication，应先引入不含动态列的 canonical mirror 表或独立 change-log。

## Impact

- Affected specs:
  - `deployment-ops`
- Affected code:
  - `scripts/` 下新增或重构本地到云端同步入口
  - `backend/services/` 下新增 canonical sync 相关服务
  - 云端 canonical mirror 表 bootstrap / migration
  - 投影刷新或查询适配逻辑
- Affected docs:
  - 部署文档
  - 同步设计文档
  - 运维手册

## Non-Goals

- 本变更不实现云端回写本地或双向同步。
- 本变更不要求历史 B 类记录在同步时被重新语义映射。
- 本变更不把动态列继续视为云端真源。
- 本变更不在同步任务中做运行时 `ADD COLUMN TEXT` 之类的 schema 演化。
- 本变更不强制当前阶段就落地 CDC / Debezium / logical replication。
