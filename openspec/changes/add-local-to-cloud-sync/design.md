## Context

当前本地采集环境会把 B 类数据写入 `b_class` schema 下的动态分表。每张表都包含两类内容：
- 固定系统字段和同步元数据字段
- 动态列镜像

同时，每条记录还保留：
- `raw_data JSONB`：完整业务载荷
- `header_columns`：原始表头/字段来源信息
- `data_hash`：幂等更新与去重依据

这意味着当前真实的数据真源已经不是动态列，而是“固定字段 + `raw_data/header_columns`”。旧提案的问题在于把动态列也纳入同步契约，并尝试在云端运行时补齐 schema。这会把同步层和分析投影层混在一起，导致稳定性差、历史语义不清晰。

## Goals / Non-Goals

- Goals:
  - 保证本地采集库到云端数据库的 B 类数据同步不丢失、可重跑、可追溯。
  - 明确同步真源是 canonical payload，而不是动态列。
  - 保留现有四时段错峰同步模式。
  - 让字段改名、模板演化、货币后缀清理等变化不会破坏历史记录的可解释性。
  - 将“数据搬运”和“报表投影/schema 演化”分离。
- Non-Goals:
  - 不做双向同步。
  - 不在同步链路中做云端动态列补齐。
  - 不在本变更中重写所有历史记录的字段语义。
  - 不在当前阶段强制落地 Debezium、DMS 或 PostgreSQL logical replication。

## Approaches Considered

### 1. 旧方案：按表枚举 + 运行时补齐动态列 + 增量 upsert

- 优点:
  - 容易基于现有脚本快速落地。
- 缺点:
  - 将动态列误当成同步契约的一部分。
  - 云端 schema 在同步期间被隐式演化，难以治理。
  - 字段归一化后可能出现语义混淆，但没有清晰处理边界。
  - 失败面广，排障困难。

结论：不采用。

### 2. 直接对当前 B 类表做 PostgreSQL logical replication

- 优点:
  - 从数据库复制角度更主流。
  - 事务级增量捕获能力强。
- 缺点:
  - 当前本地 B 类表物理包含动态列，直接复制会把云端重新耦合到动态 schema。
  - DDL 不会自动复制，动态列演化仍需单独治理。
  - 在不先引入 canonical mirror 的前提下，不适合直接作为当前变更的落地方案。

结论：作为未来演进方向保留，但不作为当前 change 的推荐实现。

### 3. 推荐方案：canonical micro-batch sync + 独立 projection refresh

- 优点:
  - 与当前代码结构最匹配。
  - 同步层只搬运高保真数据。
  - 动态列、报表、投影可以单独失败、单独刷新，不影响同步正确性。
  - 便于后续再升级到 CDC。
- 缺点:
  - 比直接脚本迁移多一层设计约束。
  - 需要明确云端 canonical mirror 表结构与 checkpoint 机制。

结论：采用。

## Decisions

### 1. 同步真源定义为 canonical payload

每张本地 B 类表向云端同步时，只同步以下内容：
- 业务主键/幂等相关字段：`platform_code`、`shop_id`、`data_domain`、`granularity`、`sub_domain`、`data_hash`
- 时间相关字段：`metric_date`、`period_start_date`、`period_end_date`、`period_start_time`、`period_end_time`、`ingest_timestamp`
- 追溯相关字段：`file_id`、`template_id`、`currency_code`
- 原始业务载荷：`raw_data`
- 原始表头信息：`header_columns`

动态列不属于同步真源，即使本地存在也不参与云端同步契约。

### 2. 云端目标表使用 canonical mirror 结构

云端为每张逻辑上的 B 类表维持一个 canonical mirror 表，表名可以与本地表名保持一致，但列结构只包含固定字段：
- 不包含动态列
- 不依赖运行时 `ADD COLUMN`
- 必须具备与本地幂等语义一致的唯一约束或唯一索引

这允许云端稳定保存每条记录的完整 `raw_data`，同时不被动态列变化拖动 schema。

### 3. 同步策略采用定时 micro-batch + 高水位断点

同步继续使用与采集错峰的四时段模型，但每张表的断点不再仅靠裸 `last_sync` 时间，而是使用稳定高水位：
- 推荐断点：`(ingest_timestamp, id)` 组合
- 若无法直接使用 `id`，则至少保证 `ingest_timestamp` 单调推进且断点只在目标端提交成功后更新

这样做的原因：
- 仅用时间戳会遇到同一秒/同一事务多行的边界问题。
- 使用高水位组合可以降低漏数和重放歧义。

### 4. 幂等写入保持与本地现有唯一键一致

云端写入必须沿用当前本地 B 类表的唯一键语义：
- 非 `services` 域：`(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)`
- `services` 域：`(data_domain, sub_domain, granularity, data_hash)`

冲突时更新的字段至少包括：
- `raw_data`
- `header_columns`
- `ingest_timestamp`
- `file_id`
- `template_id`
- `currency_code`
- 时间范围字段（如实现中确认需要）

这样才能保证：
- 重跑不会重复插入
- 新采集结果可以覆盖旧载荷
- 历史来源信息仍可追溯

### 5. 动态列只作为派生查询层

动态列的存在价值是查询便利，不是数据保真。基于此：
- 本地同步任务不关心动态列是否补齐成功
- 云端同步任务不创建动态列
- 如云端需要报表列、Metabase 查询列或物化视图，应该由独立的 projection refresh 过程从 `raw_data` 中提取生成

这相当于：
- 同步层负责“搬运真相”
- 投影层负责“提供好查的数据形态”

### 6. 字段改名与模板演化通过字段谱系解决，而不是回写历史 raw_data

这是本设计最关键的边界：
- 历史 `raw_data` 不做回写重命名
- 历史 `header_columns` 必须原样保留
- 同步任务不对历史记录做“旧字段改成新字段”的隐式修复

新旧字段如何在查询层正确归位，依赖：
- `header_columns`
- `template_id`
- 显式字段别名/版本化映射规则

这意味着：
- 同步层保证“数据不丢、上下文不丢”
- 语义归并交给投影规则显式处理

如果未来需要进一步增强，应引入：
- 字段别名注册表
- 版本化字段映射
- 基于 `template_id` 或 `header_signature` 的投影规则选择

但本 change 至少要先把这个边界写清楚，避免同步层继续承担不该承担的语义改写职责。

### 7. 为什么当前不直接采用 logical replication

logical replication 是更主流的数据库复制模式，但它更适合“固定 schema 的 canonical 表”。当前本地 B 类表还带有动态列，因此如果直接复制：
- 云端仍需跟随动态列演化
- DDL 治理复杂度不会消失
- 设计目标“动态列降级为派生层”无法成立

所以当前更稳妥的路径是：
- 先把同步契约收敛到 canonical payload
- 后续如果要升级到 logical replication，再引入不含动态列的 canonical mirror / outbox 表

## Data Flow

1. 本地采集与入库继续写入现有 `b_class` 表。
2. 定时同步任务枚举本地 `b_class` 表。
3. 对每张表只读取固定 canonical 字段，不读取动态列。
4. 按每张表的高水位断点分批读取。
5. 写入云端对应 canonical mirror 表，并执行幂等 upsert。
6. 目标端提交成功后，更新该表 checkpoint。
7. 独立的 projection refresh 任务再基于云端 `raw_data` 生成报表/投影结构。

## Risks / Trade-offs

- 风险：云端查询若仍严重依赖动态列，将需要额外投影层改造。
  - Mitigation：把 projection refresh 作为明确子任务，而不是把动态列同步继续塞回主链路。

- 风险：字段名归一化可能让两个不同原始字段落到同一个 normalized key。
  - Mitigation：同步层保留 `header_columns` 与来源元数据；投影层引入显式字段别名规则；必要时在后续变更中增加冲突检测。

- 风险：仅靠时间戳断点可能漏数。
  - Mitigation：使用 `(ingest_timestamp, id)` 高水位，且只在目标提交成功后推进断点。

- 风险：未来升级到 logical replication 时需要再次调整数据面。
  - Mitigation：当前先把 canonical payload 边界立住，这本身就是后续 CDC 化的前置条件。

## Migration Plan

1. 在文档和 delta spec 中确认新的同步契约。
2. 为云端目标表定义 canonical mirror DDL。
3. 重写同步入口，按固定字段读取和 upsert。
4. 引入 per-table checkpoint。
5. 将动态列补齐逻辑从同步主链路中移除。
6. 增加 projection refresh 说明或独立任务。
7. 验证字段改名、模板变更、重复重跑、部分失败等场景。

## Open Questions

- 云端 canonical mirror 是否沿用本地表名，还是增加单独 schema 前缀。
- checkpoint 存储在本地数据库状态表，还是独立状态文件/云端状态表。
- 投影层是否在本 change 内落最小实现，还是只定义契约并在后续 change 实现。
