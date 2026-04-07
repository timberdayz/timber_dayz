# 自动同步数据入库问题修复

**问题**: 自动同步虽然标记文件为"成功"，但实际没有数据入库（imported=0）

**根本原因**:
1. 自动同步只检查了`success`标志，没有检查`imported`字段
2. ingest API返回的是`imported`字段，不是`rows_ingested`
3. 即使`imported=0`，只要`success=True`，文件也会被标记为"成功"

**修复内容**:
1. ✅ 检查`imported`字段（实际入库行数）
2. ✅ 如果`imported=0`且`quarantined=0`，标记为失败（除非是全0数据文件）
3. ✅ 记录实际的入库行数、隔离行数、暂存行数
4. ✅ 改进日志记录，便于调试

**修复文件**: `backend/services/auto_ingest_orchestrator.py`

**验证步骤**:
1. 清理数据库
2. 重新执行自动同步
3. 检查：
   - 文件状态是否正确（失败的文件应该标记为failed）
   - 实际入库的数据量（fact_product_metrics表）
   - 日志中是否有警告或错误信息

