# 发布检查清单

> 当前正式目录语义：正式采集原始数据目录为 `data/raw/`，工作下载目录为 `downloads/`，`temp/outputs/` 仅作 legacy 兼容或历史诊断用途。

## 采集路径统一相关发布检查

- [ ] 执行 Alembic 迁移：
  - `alembic upgrade head`
- [ ] 确认迁移 `20260327_catalog_file_source_data_raw.py` 已生效
- [ ] 抽查 `catalog_files.source` 的默认值已变为 `data/raw`
- [ ] 抽查正式采集产生的新文件进入 `data/raw/`
- [ ] 抽查 catalog 注册后的新记录 `source='data/raw'`
- [ ] 抽查旧 `temp/outputs` 历史记录仍可被兼容解析

## 推荐验证命令

```powershell
alembic upgrade head
```

```sql
SELECT column_default
FROM information_schema.columns
WHERE table_name = 'catalog_files'
  AND column_name = 'source';
```

预期：

- 默认值包含 `data/raw`

```sql
SELECT source, file_path
FROM catalog_files
ORDER BY id DESC
LIMIT 20;
```

预期：

- 新增正式采集记录优先显示 `source = 'data/raw'`

## 说明

- 本清单面向当前正式采集主链路发布
- 历史报告脚本、legacy 工具、archive 文档的进一步清理不阻塞本次发布
- 如需查看剩余 legacy 范围，请参考：
  - `docs/guides/COLLECTION_PATH_LEGACY_INVENTORY.md`
