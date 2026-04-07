## 1. Canonical Sync Contract

- [ ] 1.1 明确本地到云端同步只搬运 B 类表的固定 canonical 字段，不同步动态列。
- [ ] 1.2 为每类 B 类表定义云端 canonical mirror 表结构，至少包含 `raw_data`、`header_columns`、`data_hash`、时间字段、来源字段和唯一约束。
- [ ] 1.3 确认云端冲突键与本地现有唯一索引语义一致，覆盖 `services` 与非 `services` 两类场景。

## 2. Sync Engine

- [ ] 2.1 新增或重构本地到云端同步入口，不再以 `migrate_selective_tables.py` 作为主实现。
- [ ] 2.2 运行时枚举本地 `b_class` 表，但每张表只读取固定 canonical 字段。
- [ ] 2.3 实现 per-table checkpoint，推荐使用 `(ingest_timestamp, id)` 作为高水位。
- [ ] 2.4 仅在目标端提交成功后推进 checkpoint，避免部分失败导致漏数。
- [ ] 2.5 写入云端时使用幂等 upsert，更新 `raw_data`、`header_columns`、`ingest_timestamp`、来源元数据等字段。

## 3. Dynamic Columns And Projection

- [ ] 3.1 从同步主链路中移除“云端运行时补齐动态列”的职责。
- [ ] 3.2 明确动态列仅用于查询便利，不作为同步真源。
- [ ] 3.3 设计独立 projection refresh 流程，由其从云端 `raw_data` 中生成分析/报表所需投影结构。

## 4. Field Lineage And Precision

- [ ] 4.1 保证历史记录中的 `raw_data` 不因字段改名或模板演化而被回写改名。
- [ ] 4.2 保证 `header_columns` 原样保留，用于追溯原始字段来源。
- [ ] 4.3 为字段别名/版本化投影规则预留设计接口，明确语义归并不在同步阶段完成。
- [ ] 4.4 验证货币后缀归一化、模板更新、字段轻微改名等场景下，历史数据仍可通过 `raw_data + header_columns` 正确解释。

## 5. Scheduling, Observability, Security

- [ ] 5.1 保留与采集错峰的四时段调度建议，并更新部署文档。
- [ ] 5.2 记录每张表的处理数量、成功/失败状态、checkpoint 推进情况和最终汇总结果。
- [ ] 5.3 单表失败不阻断其他表，但进程整体应返回非零退出码，便于 Cron 或监控告警。
- [ ] 5.4 云端连接信息通过环境变量注入，日志不得输出明文密钥或连接串。

## 6. Validation

- [ ] 6.1 验证首次全量同步后，云端 canonical mirror 中记录数与本地一致。
- [ ] 6.2 验证重复执行同步不会产生重复数据，且更新会覆盖到正确记录。
- [ ] 6.3 验证同一批次中存在相同 `ingest_timestamp` 的多行时，不会因断点推进漏数。
- [ ] 6.4 验证动态列不存在或投影刷新失败时，`raw_data` 同步仍成功。
- [ ] 6.5 验证字段改名/模板变更后，历史记录仍保留旧 `header_columns`，新记录写入新 payload，二者不会在同步阶段被错误混写。
