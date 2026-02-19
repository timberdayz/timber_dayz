# Tasks: 本地→云端 B 类表定时同步（4 时段）

## 1. 表枚举与入口

- [ ] 1.1 实现「无 --tables 时从 information_schema 枚举 b_class 下所有 BASE TABLE」
  - SQL: `SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'b_class' AND table_type = 'BASE TABLE'`
  - 脚本支持：显式 `--tables`（兼容现有用法）与「不传 --tables 则自动枚举 b_class」两种模式
- [ ] 1.2 确定同步脚本入口：扩展现有 `scripts/migrate_selective_tables.py` 或新建 `scripts/sync_local_to_cloud.py`，并在文档中注明推荐入口与参数

## 2. 增量与断点

- [ ] 2.1 为每张 b_class 表确定增量策略：优先按时间字段（如 `updated_at`/`created_at`）过滤；若无则约定「全量一次」或跳过，并在文档说明
- [ ] 2.2 实现断点记录：每表 last_sync 时间或游标存于本地（配置表或脚本可读写的状态文件），下次同步仅同步该时间之后的数据
- [ ] 2.3 云端写入采用幂等 upsert（如 ON CONFLICT DO UPDATE），避免重复执行产生重复行

## 3. 错误与可观测性

- [ ] 3.1 单表同步失败时记录日志并继续其他表；不因单表失败而中断整次运行
- [ ] 3.2 退出码约定：0=全部成功，非 0=存在失败（可选区分部分失败/全部失败），便于 Cron 告警或监控
- [ ] 3.3 日志输出到可配置路径（如 `logs/sync_local_to_cloud.log`），避免 Windows 下使用 Emoji，使用 ASCII 符号（如 [OK]、[ERROR]）

## 4. 配置与安全

- [ ] 4.1 云端库连接使用环境变量（如 `CLOUD_DATABASE_URL`），不硬编码；在 .env.example 或部署文档中说明变量名与示例格式（不含真实密码）
- [ ] 4.2 确保脚本不打印敏感信息（仅 masked 或「已设置」提示）

## 5. 文档与 Cron 示例

- [ ] 5.1 在 `docs/deployment/` 或 `docs/guides/` 中新增或更新「本地→云端同步」说明，包含：4 时段与采集错峰理由、Cron 示例（`30 6,12,18,22 * * *`）、表枚举策略、环境变量、推荐命令示例
- [ ] 5.2 Cron 示例命令（供复制）：`30 6,12,18,22 * * * cd /path/to/xihong_erp && python scripts/sync_local_to_cloud.py >> logs/sync_local_to_cloud.log 2>&1`（路径按实际部署替换）

## 6. 验收

- [ ] 6.1 验收：不传 --tables 时脚本能正确枚举 b_class 下所有表并对每表执行同步（或跳过无时间字段的表并记日志）
- [ ] 6.2 验收：某表故意失败（如权限/网络）时，其他表仍能同步完成，且退出码非 0、日志中有该表错误信息
- [ ] 6.3 验收：再次运行同一同步，仅增量写入（或 upsert 无重复行），断点/时间过滤生效
