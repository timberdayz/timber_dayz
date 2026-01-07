# 技术设计：完成数据同步管道验证

## Context

当前系统已完成 Metabase API 连接和 Question ID 配置验证，但由于数据库中缺少数据，无法进一步验证前端真实数据展示。需要验证完整的数据同步管道，确保数据从采集到入库的完整流程正常工作。

### 当前状态

- ✅ 数据采集功能已实现（Playwright 采集器）
- ✅ 文件注册功能已实现（catalog_scanner）
- ✅ 模板查找和配置功能已实现（TemplateMatcher，记录表头行和表头字段列表）
- ✅ 数据同步功能已实现（DataSyncService）
- ✅ 数据入库功能已实现（DataIngestionService）
- ✅ Metabase API 代理已实现（backend/routers/dashboard_api.py）
- ❓ 数据同步管道端到端验证缺失
- ❓ 数据库数据完整性验证缺失
- ❓ Metabase 集成验证缺失

### 问题分析

1. **数据采集 → 文件注册**：需要验证采集器是否正确注册文件到 `catalog_files` 表
2. **文件扫描 → 文件注册**：需要验证文件扫描服务是否正确发现和注册文件
3. **文件注册 → 数据同步**：需要验证数据同步服务是否正确处理文件
4. **数据同步 → 数据入库**：需要验证数据是否正确入库到B类数据表（fact_raw_data_*，JSONB格式）
5. **数据入库 → Metabase 查询**：需要验证 Metabase 是否可以查询B类数据表数据

## Goals / Non-Goals

### Goals

1. **验证数据同步管道完整性**
   - 确保数据从采集到入库的完整流程正常工作
   - 确保数据完整性（无丢失、字段完整）
   - 确保数据质量（验证通过、质量评分）

2. **验证 Metabase 集成（DSS架构）**
   - 确保 Metabase 可以连接数据库
   - 确保 Metabase Question 可以查询B类数据表（fact_raw_data_*）
   - 确保JSONB数据格式符合Metabase要求
   - 确保Metabase字段映射配置正确（原始表头字段 → 标准字段）
   - 确保Metabase业务逻辑验证规则配置正确

3. **提供验证工具和文档**
   - 创建端到端测试脚本
   - 创建数据完整性验证脚本
   - 创建验证文档和故障排查指南

### Non-Goals

- ❌ 不修改现有实现（仅验证和测试）
- ❌ 不优化性能（性能优化不在本 change 范围内）
- ❌ 不修改数据库结构（不添加新表或修改现有表结构）
- ❌ 不修改前端代码（前端迁移由其他 change 负责）

## Decisions

### Decision 1: 验证策略

**决策**：采用分层验证策略，从底层到顶层逐步验证。

**理由**：
- 底层验证（数据采集、文件注册）是基础，必须先验证
- 中层验证（数据同步、数据入库）依赖底层，需要底层验证通过
- 顶层验证（Metabase 集成）依赖中层，需要中层验证通过

**替代方案**：
- 端到端测试：可以快速发现问题，但难以定位问题根源
- 单元测试：可以验证单个组件，但无法验证集成问题

**选择**：分层验证 + 端到端测试，既保证完整性又便于问题定位。

### Decision 2: 测试脚本设计

**决策**：创建独立的验证脚本，不修改现有代码。

**理由**：
- 保持现有代码不变，降低风险
- 验证脚本可以独立运行，便于调试
- 验证脚本可以作为文档，说明系统使用方法

**替代方案**：
- 集成到现有测试框架：需要修改现有代码，风险较高
- 手动测试：效率低，难以重复执行

**选择**：独立验证脚本，便于维护和复用。

### Decision 3: 数据完整性验证方法

**决策**：采用统计和抽样相结合的方法验证数据完整性。

**理由**：
- 统计方法（行数统计）可以快速发现数据丢失问题
- 抽样方法（字段完整性检查）可以验证数据质量
- 结合使用可以全面验证数据完整性

**替代方案**：
- 全量验证：准确但效率低，不适合大数据量
- 抽样验证：效率高但可能遗漏问题

**选择**：统计 + 抽样，平衡效率和准确性。

### Decision 4: Metabase 集成验证方法

**决策**：通过 API 代理验证 Metabase 集成，不直接访问 Metabase。

**理由**：
- 通过 API 代理验证符合实际使用场景
- 可以验证数据格式转换是否正确
- 可以验证错误处理是否正确

**替代方案**：
- 直接访问 Metabase：需要配置 Metabase 连接，复杂度高
- 模拟 Metabase 响应：无法验证真实集成问题

**选择**：通过 API 代理验证，符合实际使用场景。

## Risks / Trade-offs

### Risk 1: 数据采集失败

**风险**：数据采集器可能因为网络、认证等问题失败。

**影响**：高 - 无法获取数据，后续验证无法进行。

**缓解措施**：
- 提供详细的错误日志和调试指南
- 支持手动文件上传作为备选方案
- 提供测试数据文件供验证使用

### Risk 2: 文件注册失败

**风险**：文件元数据提取可能失败，导致文件无法注册。

**影响**：中 - 文件无法注册，数据同步无法进行。

**缓解措施**：
- 验证文件元数据提取逻辑
- 提供手动注册选项
- 提供文件元数据修复工具

### Risk 3: 数据同步失败

**风险**：模板查找和配置或数据入库可能失败。

**影响**：高 - 数据无法入库，Metabase 无法查询数据。

**缓解措施**：
- 提供详细的同步日志和错误处理
- 支持重试机制
- DSS架构下不隔离数据，所有数据都入库（业务逻辑验证在Metabase中完成）

### Risk 4: 数据不完整

**风险**：数据可能在某个环节丢失，导致数据不完整。

**影响**：中 - 数据不完整，影响业务决策。

**缓解措施**：
- 提供数据完整性检查工具
- 验证数据行数和字段完整性
- 提供数据丢失追踪日志

### Risk 5: Metabase 查询失败

**风险**：Metabase 可能无法查询数据库或查询结果不正确。

**影响**：中 - Metabase 无法提供数据，前端无法展示。

**缓解措施**：
- 验证数据库连接和权限
- 验证 Metabase Question 配置
- 提供查询测试工具

## Migration Plan

### Phase 1: 文件扫描验证（1天）

1. 验证 catalog_scanner 服务
2. 验证文件扫描 API
3. 创建文件扫描验证脚本

### Phase 2: 数据同步验证（2-3天）

1. 验证单文件同步 API
2. 验证批量同步 API
3. 验证模板匹配逻辑
4. 验证数据入库流程
5. 创建数据同步验证脚本

### Phase 3: 数据完整性验证（1-2天）

1. 验证B类数据表数据完整性（DSS架构）
2. 验证数据关联完整性
3. 创建数据完整性验证脚本

### Phase 4: Metabase 集成验证（1天）

1. 验证 Metabase 数据库连接
2. 验证数据格式符合要求
3. 验证前端数据获取
4. 创建 Metabase 集成验证脚本

### Phase 5: 端到端测试（1-2天）

1. 创建端到端测试脚本
2. 运行端到端测试
3. 验证测试结果

### Phase 6: 路径配置管理优化（1天）

1. 创建统一路径配置管理工具（`modules/core/path_manager.py`）
2. 替换所有硬编码路径为统一路径管理函数
3. 支持环境变量配置（PROJECT_ROOT、DATA_DIR等）
4. 创建路径配置文档

### Phase 7: 修复功能按钮（数据浏览器已移除 - v4.12.0）

⚠️ **v4.12.0移除**：数据浏览器功能已完全移除，使用Metabase替代（http://localhost:3000）

1. **数据浏览器移除说明**：
   - 移除原因：数据浏览器功能修复多次仍无法正常使用，Metabase是更专业的BI工具
   - 已删除文件：`frontend/src/views/DataBrowser.vue`、`frontend/src/views/DataBrowserSimple.vue`、`backend/routers/data_browser.py`
   - 替代方案：使用Metabase进行数据查询和分析
   - Metabase功能：数据查询、数据可视化、数据导出、数据质量分析

2. 修复清理数据库功能
3. 修复刷新按钮功能
4. 验证空文件处理逻辑

### Phase 8: 数据采集验证（1-2天）⭐ 移到最后

1. 验证数据采集器文件下载
2. 验证文件注册到 catalog_files 表
3. 创建数据采集验证脚本

### Phase 9: 文档和总结（1天）

1. 创建验证文档
2. 更新相关文档
3. 总结和报告

## Open Questions

1. **测试数据来源**：
   - Q: 使用真实数据还是模拟数据？
   - A: 优先使用真实数据，如果没有则使用模拟数据。

2. **验证范围**：
   - Q: 验证所有平台还是只验证主要平台？
   - A: 优先验证主要平台（Shopee），其他平台可选。

3. **数据量要求**：
   - Q: 需要多少数据才能验证 Metabase 集成？
   - A: 至少需要 orders 和 products 域的数据，每个域至少 100 行。

4. **验证频率**：
   - Q: 验证脚本需要定期运行吗？
   - A: 建议在重要变更后运行，也可以作为 CI/CD 的一部分。

5. **错误处理**：
   - Q: 验证失败时如何处理？
   - A: 记录详细错误日志，提供故障排查指南，支持手动修复。

6. **⚠️ v4.12.0移除：数据浏览器功能已完全移除**：
   - Q: 如何查看数据库中的数据？
   - A: 使用Metabase进行数据查询和分析（http://localhost:3000）。Metabase提供更强大的数据查询、可视化和导出功能。

7. **清理数据库功能修复**：
   - Q: 清理数据库API路由不一致如何修复？
   - A: 前端调用路径缺少`/api`前缀。修复方案：前端修改为`/api/data-sync/cleanup-database`，或后端添加路由别名。后端实际路由在`backend/routers/data_sync.py`，清理B类数据表并重置catalog_files状态。

8. **刷新按钮功能修复**：
   - Q: 刷新按钮API调用失败如何修复？
   - A: 前端调用路径与后端完全不匹配。修复方案：前端修改为`/api/field-mapping/scan`，或后端添加路由别名`/collection/scan-files`。后端实际路由在`backend/routers/field_mapping.py`，扫描`data/raw/`目录并注册新文件。

9. **空文件处理逻辑**：
   - Q: 系统如何处理空文件？
   - A: 系统识别全0数据文件，标记为ingested但记录警告信息（[全0数据标识]），跳过数据入库，避免重复处理。

10. **路径配置管理**：
   - Q: 如何解决硬编码路径问题，确保项目可以迁移到其他电脑或服务器？
   - A: 创建统一路径配置管理工具（`modules/core/path_manager.py`），支持环境变量配置（PROJECT_ROOT、DATA_DIR等），替换所有硬编码路径为统一路径管理函数，确保项目可以从任意目录运行。

## 技术细节

### 数据流程验证点

1. **数据采集 → 文件注册**
   - 验证点：文件下载、文件注册、文件元数据提取
   - 验证方法：检查文件系统、查询 catalog_files 表

2. **文件扫描 → 文件注册**
   - 验证点：文件扫描、文件注册、文件去重
   - 验证方法：调用扫描 API、查询 catalog_files 表

3. **文件注册 → 数据同步（DSS架构）**
   - 验证点：模板查找和配置（表头行和表头字段列表）、数据预览
   - 验证方法：调用同步 API、检查同步结果

4. **数据同步 → 数据入库（DSS架构）**
   - 验证点：元数据补充、去重处理、数据入库到B类数据表
   - 验证方法：查询B类数据表（fact_raw_data_*）、检查数据行数、检查JSONB格式、检查data_hash唯一性

5. **数据入库 → Metabase 查询（DSS架构）**
   - 验证点：数据库连接、Question查询B类数据表、JSONB数据格式、字段映射配置、业务逻辑验证规则
   - 验证方法：调用 Metabase API、检查查询结果、验证字段映射配置

### 验证脚本设计

1. **test_data_collection.py**
   - 功能：验证数据采集和文件注册
   - 输入：测试账号配置
   - 输出：验证报告

2. **test_file_scanning.py**
   - 功能：验证文件扫描和注册
   - 输入：测试文件目录
   - 输出：验证报告

3. **test_data_sync.py**
   - 功能：验证数据同步和入库
   - 输入：测试文件 ID
   - 输出：验证报告

4. **verify_database_data.py**
   - 功能：验证数据完整性
   - 输入：数据库连接
   - 输出：验证报告

5. **test_metabase_integration.py**
   - 功能：验证 Metabase 集成
   - 输入：Metabase 配置
   - 输出：验证报告

6. **test_data_sync_pipeline.py**
   - 功能：端到端测试
   - 输入：完整测试配置
   - 输出：端到端测试报告

### 验证报告格式

```json
{
  "test_name": "数据同步管道验证",
  "timestamp": "2025-02-01T10:00:00Z",
  "results": {
    "data_collection": {
      "status": "passed",
      "files_downloaded": 5,
      "files_registered": 5,
      "errors": []
    },
    "file_scanning": {
      "status": "passed",
      "files_scanned": 10,
      "files_registered": 8,
      "files_skipped": 2,
      "errors": []
    },
    "data_sync": {
      "status": "passed",
      "files_synced": 8,
      "rows_ingested": 1000,
      "rows_quarantined": 0,  # DSS架构下不隔离数据
      "errors": []
    },
    "data_integrity": {
      "status": "passed",
      "b_class_tables": {
        "fact_raw_data_orders_daily": {"rows": 500, "integrity": "passed", "jsonb_format": "valid"},
        "fact_raw_data_products_snapshot": {"rows": 500, "integrity": "passed", "jsonb_format": "valid"}
      },
      "errors": []
    },
    "metabase_integration": {
      "status": "passed",
      "questions_tested": 5,
      "queries_successful": 5,
      "errors": []
    }
  },
  "summary": {
    "overall_status": "passed",
    "total_tests": 5,
    "passed_tests": 5,
    "failed_tests": 0
  }
}
```

