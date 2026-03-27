# Collection Path Legacy Inventory

日期：2026-03-27

## 目的

在正式采集主链路已经统一到 `data/raw/`、工作下载目录统一到 `downloads/` 之后，仍有部分 `temp/outputs` 残留存在于仓库中。

本清单用于明确这些残留的性质，避免后续把“必须保留的兼容层”和“可以继续删除的历史实现”混为一谈。

## 当前结论

正式采集主链路已经收口完成：

- 正式原始数据目录：`data/raw/`
- 工作下载目录：`downloads/`
- 浏览器 profile / state：`output/playwright/*`

当前剩余的 `temp/outputs` 命中，已经**不再构成正式采集双链路**，主要分为以下几类。

## A. 必须保留的兼容层

这些文件仍需要识别或解析历史 `temp/outputs` 路径，不能直接删除：

- `backend/services/data_ingestion_service.py`
- `backend/services/data_sync_service.py`
- `backend/services/file_path_resolver.py`
- `backend/services/file_repair.py`
- `modules/core/path_manager.py`

保留原因：

- 旧 `CatalogFile.file_path` 记录可能仍指向 `temp/outputs`
- 历史文件恢复、迁移、路径解析需要兼容旧目录
- 新链路已经不依赖它们写入旧路径，但读取兼容仍有价值

建议：

- 保留
- 仅在确认数据库和磁盘上的历史数据都已迁移后，才考虑下线

## B. 仅用于迁移或清理旧目录的脚本

这些文件保留 `temp/outputs` 是合理的，因为它们的职责就是处理旧目录：

- `scripts/migrate_paths.py`
- `scripts/cleanup_temp_files_v4_11_4.py`
- `docs/guides/OUTPUTS_NAMING.md` 中 legacy 清理说明

建议：

- 保留
- 在注释和文档中明确标注为 legacy migration tooling

## C. 报告 / 诊断 / 临时输出脚本

这些文件的 `temp/outputs` 用法不属于正式采集主链路，多数只是历史诊断报告路径：

- `scripts/business_overview_long_run.py`
- `scripts/business_overview_split_probe.py`
- `scripts/generate_validation_report.py`
- `scripts/high_frequency_pages_probe.py`
- `backend/run_performance_tests.py`
- `backend/routers/performance.py`
- `tests/test_multi_region_router.py`
- `tests/test_vpn_china_acceleration.py`
- `backend/tests/batch_import_test.py`
- `backend/tests/concurrent_test.py`
- `backend/tests/stability_test.py`
- `docs/reports/*` 中旧报告引用

建议：

- 可继续逐步迁移到 `temp/reports/` 或 `temp/artifacts/`
- 不影响正式采集主链路，可单独安排清债轮次

## D. 历史兼容实现 / 可后续删除候选

这些文件已经明显偏向历史实现或兼容组件，可在未来单独评估是否下线：

- `modules/services/enhanced_catalog_scanner.py`
- `modules/utils/collection_template_generator.py`
- `modules/utils/recording_maintenance.py`
- `modules/utils/otp/email_otp_client.py`

建议：

- 先标记为 legacy
- 确认没有运行时入口依赖后再删

## E. 测试中的 `temp/outputs`

测试中还会看到两类 `temp/outputs`：

1. **历史样例路径**
   - 已经尽量替换为 `data/raw` 或 `downloads`
2. **源码守卫测试**
   - 例如 `backend/tests/test_collection_center_app_path_regression.py`
   - 例如 `backend/tests/test_legacy_tool_path_regression.py`

第二类是故意保留的，因为它们在检查源码中不应再出现这些旧硬编码。

## 建议的后续顺序

1. 继续迁移报告/诊断脚本输出目录到 `temp/reports/`
2. 为兼容层补“何时可以删除”的退出条件
3. 标注或下线 `enhanced_catalog_scanner.py` 等历史实现

## 不建议做的事

- 不建议直接全仓库替换所有 `temp/outputs`
- 不建议在兼容层尚未下线前删除 `temp/outputs` 识别能力
- 不建议把 legacy 服务层目录协议直接搬进 `data/raw`
