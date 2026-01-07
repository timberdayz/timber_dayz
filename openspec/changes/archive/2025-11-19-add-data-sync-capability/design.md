## Context

数据同步功能是数据采集流程的关键环节，负责将已采集并完成字段映射的Excel文件自动入库到事实表。该功能在v4.12.0中实现，采用FastAPI BackgroundTasks实现异步处理，无需额外的Celery Worker。

### 业务背景

数据采集流程：
1. **数据采集**：使用Playwright自动化采集平台数据，下载Excel文件
2. **文件注册**：自动注册到catalog_files表，包含元数据（平台、数据域、粒度等）
3. **字段映射**：用户配置字段映射模板，将Excel列映射到标准字段
4. **数据同步**：自动应用模板，将数据入库到事实表（fact_orders、fact_order_items等）

### 技术约束

- **Windows平台兼容性**：主要开发环境为Windows 10/11
- **PostgreSQL优先**：使用PostgreSQL索引查询，禁止递归搜索文件系统
- **架构合规**：必须100%符合SSOT标准，禁止双维护
- **性能要求**：关键API响应时间P95 < 500ms

## Goals / Non-Goals

### Goals

- ✅ **异步处理**：API立即返回，后台异步处理，不阻塞用户
- ✅ **并发控制**：最多10个并发文件处理，避免资源耗尽
- ✅ **进度跟踪**：数据库持久化存储，支持任务查询和历史记录
- ✅ **数据质量Gate**：批量同步完成后自动质量检查
- ✅ **错误处理**：完善的错误处理和日志记录
- ✅ **服务复用**：复用现有服务（TemplateMatcher、DataIngestionService），不重复实现

### Non-Goals

- ❌ **不引入Celery**：使用FastAPI BackgroundTasks，无需额外的Celery Worker
- ❌ **不改变API接口**：保持向后兼容，不破坏现有集成
- ❌ **不修改现有服务**：复用现有服务，不重复实现业务逻辑

## Decisions

### Decision: 使用FastAPI BackgroundTasks而非Celery

**What**: 数据同步功能使用FastAPI内置的BackgroundTasks实现异步处理，而非Celery。

**Why**:
- FastAPI BackgroundTasks是内置功能，无需额外依赖
- 数据同步是短时任务（单文件处理<30秒），不需要分布式任务队列
- 减少系统复杂度，降低运维成本
- Celery保留用于定时任务（物化视图刷新、告警检查等）

**Alternatives considered**:
- **Celery + Redis**：功能强大但增加复杂度，需要额外的Worker进程
- **同步处理**：简单但会阻塞API，用户体验差
- **线程池**：可行但不如BackgroundTasks优雅

### Decision: 数据库持久化进度跟踪

**What**: 使用SyncProgressTracker（数据库存储）而非内存存储的ProgressTracker。

**Why**:
- 支持服务重启后恢复进度
- 支持历史记录查询
- 支持多实例部署（如果未来需要）
- 数据持久化，不丢失进度信息

**Alternatives considered**:
- **内存存储**：简单但服务重启后丢失进度
- **Redis存储**：需要额外依赖，增加复杂度

### Decision: 并发控制使用asyncio.Semaphore

**What**: 使用asyncio.Semaphore限制最多10个并发文件处理。

**Why**:
- 避免资源耗尽（数据库连接、内存、CPU）
- 控制处理速度，避免对系统造成压力
- 可配置的并发数，便于调优

**Alternatives considered**:
- **无限制并发**：可能导致资源耗尽
- **固定线程池**：不如asyncio.Semaphore灵活

### Decision: 复用现有服务而非重新实现

**What**: DataSyncService编排流程，调用现有服务（TemplateMatcher、DataIngestionService），不重复实现业务逻辑。

**Why**:
- 遵循DRY原则，避免代码重复
- 保持业务逻辑一致性
- 降低维护成本
- 符合SSOT原则

**Alternatives considered**:
- **重新实现**：违反DRY原则，增加维护成本
- **HTTP调用**：增加网络开销，不如直接函数调用

## Risks / Trade-offs

### Risks

- **服务重启丢失进度**：使用数据库持久化已解决
- **并发控制不当**：使用asyncio.Semaphore已解决
- **错误处理不完善**：完善的错误处理和日志记录已实现
- **数据血缘追踪失败**：v4.12.1修复 - upsert_orders_v2函数未设置file_id字段，导致数据无法追踪到fact层
- **任务日志查询错误**：v4.12.1修复 - data_quarantine表查询使用了错误的字段名（file_id → catalog_file_id）

### Trade-offs

- **性能 vs 复杂度**：选择FastAPI BackgroundTasks而非Celery，牺牲了分布式能力，但降低了复杂度
- **实时性 vs 持久化**：选择数据库持久化而非内存存储，牺牲了性能，但获得了持久化能力

## Known Issues (v4.12.1)

### Issue 1: 数据未到达Fact层

**问题描述**：
- 订单数据同步时，数据成功到达Staging层，但未到达Fact层
- 任务日志显示Fact层数量为0，丢失行数等于Staging层数量

**根本原因**：
- `upsert_orders_v2`函数在处理数据时，虽然`file_id`在核心字段列表中，但如果rows中没有`file_id`字段，且没有从`file_record`参数中设置，会导致`file_id`为None
- 虽然数据可能成功入库到fact_orders表，但由于`file_id`未设置，任务日志API无法通过`file_id`查询到这些数据

**解决方案**：
- 在`upsert_orders_v2`函数中，如果`core`中没有`file_id`且`file_record`存在，自动设置`core["file_id"] = file_record.id`
- 确保所有入库到fact表的数据都有正确的`file_id`字段，用于数据血缘追踪

**修复状态**：✅ 已修复（v4.12.1）

### Issue 2: 任务日志API查询错误

**问题描述**：
- 任务日志API查询data_quarantine表时使用错误的字段名`file_id`，应该使用`catalog_file_id`

**根本原因**：
- DataQuarantine表使用`catalog_file_id`字段关联catalog_files表，而非`file_id`
- 任务日志API代码中错误地使用了`file_id`字段名

**解决方案**：
- 修复任务日志API查询，使用正确的字段名`catalog_file_id`

**修复状态**：✅ 已修复（v4.12.1）

### Issue 3: 数据丢失问题（36行数据丢失）

**问题描述**：
- 订单数据同步时，692行数据到达Raw/Staging层，但只有656行到达Fact层
- 丢失36行数据，但隔离区显示为0，说明这些数据既没有成功入库也没有被隔离

**根本原因**：
- `upsert_orders_v2`函数在遇到入库错误（如主键冲突、数据类型错误等）时，会`continue`跳过该订单
- 这些失败的订单只记录错误日志，但没有被隔离到`data_quarantine`表
- 导致数据丢失但无法追踪原因

**解决方案**：
- 在`upsert_orders_v2`函数的异常处理中，添加自动隔离机制
- 当订单入库失败时，自动创建`DataQuarantine`记录，保存失败订单的原始数据和错误信息
- 确保所有失败的数据都能被追踪和恢复

**修复状态**：✅ 已修复（v4.12.1）

### Issue 4: 任务日志API缺少text导入

**问题描述**：
- 任务日志API返回500错误：`NameError: name 'text' is not defined`
- 错误发生在`backend/routers/auto_ingest.py`第477行

**根本原因**：
- `get_task_logs`函数使用了`text()`函数但没有导入
- 其他函数（如`get_file_logs`）有导入，但`get_task_logs`函数缺少导入

**解决方案**：
- 在`get_task_logs`函数中添加`from sqlalchemy import func, text`导入

**修复状态**：✅ 已修复（v4.12.1）

### Issue 5: 同步进度对话框无法关闭

**问题描述**：
- 同步进度对话框的关闭按钮和完成按钮都无法点击
- 用户无法关闭对话框

**根本原因**：
- `handleSyncDialogClose`函数在`completed=false`时会阻止关闭
- `before-close`事件处理逻辑过于复杂，导致对话框无法关闭

**解决方案**：
- 移除`before-close`事件处理
- 简化`handleSyncDialogClose`函数逻辑，允许用户随时关闭对话框
- 如果同步未完成，只提示用户但允许关闭

**修复状态**：✅ 已修复（v4.12.1）

### Issue 6: 字段映射未正确应用到数据入库

**问题描述**：
- 订单数据同步时，Staging数据中`platform_code`和`shop_id`都是`null`
- 字段映射可能没有正确应用到数据入库
- 39行数据丢失，但隔离区显示为0

**根本原因**：
- 字段映射是将原始列名转换为标准字段名，但如果原始数据中没有`platform_code`或`shop_id`字段，映射后这些字段就不存在
- `upsert_orders_v2`函数虽然会尝试从`file_record`获取`platform_code`，但这是在数据已经进入函数之后
- 如果字段映射中没有这些关键字段，数据在入库时可能因为缺少主键字段而失败

**解决方案**：
- 在`data_ingestion_service.py`的字段映射应用后，立即检查并补充`platform_code`和`shop_id`
- 如果字段映射中没有这些字段，从`file_record`中获取并添加到每一行数据中
- 确保所有数据在入库前都有正确的`platform_code`和`shop_id`

**修复状态**：✅ 已修复（v4.12.1）

### Issue 7: Pattern Matcher警告和数据丢失问题

**问题描述**：
- 后端日志显示Pattern Matcher警告：`No match found for field: '平台SKU'`, `'SKU ID'`, `'商品名称'`, `'店铺'`
- 但这些字段在模板中已经有明确的映射
- 数据同步精确度未达到100%，丢失37行数据（Staging: 695, Fact: 658）

**根本原因**：
1. **Pattern Matcher重复匹配**：`order_amount_ingestion.py`中的Pattern Matcher对所有原始列名进行匹配，包括已经通过模板映射的字段，导致警告
2. **shop_id处理不当**：`upsert_orders_v2`函数中，如果`shop_id`为空，设置为空字符串`""`，但`FactOrder`表的主键是`(platform_code, shop_id, order_id)`，空字符串可能导致主键冲突或数据丢失
3. **shop_id未从file_record获取**：虽然`platform_code`会从`file_record`获取，但`shop_id`没有相同的逻辑

**解决方案**：
1. **修复Pattern Matcher警告**：
   - 在`order_amount_ingestion.py`中，跳过已经映射的字段
   - 只对未映射的字段进行Pattern匹配
   - 避免对已映射字段产生警告

2. **修复shop_id处理**：
   - 优先从`file_record.shop_id`获取
   - 如果`file_record`没有`shop_id`，尝试从文件名提取（如：`shopee_orders_weekly_20250926_183956.xls`）
   - 最后的兜底：使用时间戳作为`shop_id`
   - 确保`shop_id`不为空，避免主键冲突

**修复状态**：✅ 已修复（v4.12.1）

### Issue 8: 对比报告丢失数据详情显示问题

**问题描述**：
- 用户反馈对比报告中看不到Staging→Fact丢失的数据详情
- 虽然已添加丢失数据详情查询功能，但可能查询逻辑或前端显示有问题

**根本原因**：
1. **前端条件判断过于严格**：前端要求`lost_data_details.lost_in_fact`存在且长度>0，但可能查询失败时该字段为空
2. **后端查询逻辑缩进错误**：后端查询丢失数据详情的循环缩进错误，导致循环未正确执行
3. **缺少异常处理**：查询失败时没有返回错误提示，导致前端无法显示

**解决方案**：
1. **修复前端显示逻辑**：
   - 放宽条件判断，即使`lost_data_details`为空也显示丢失数据提示
   - 添加"正在查询详情..."提示，当查询失败时显示错误信息
   
2. **修复后端查询逻辑**：
   - 修复缩进错误，确保循环正确执行
   - 添加详细日志记录，便于调试
   - 添加异常处理，确保查询失败时返回错误提示

**修复状态**：✅ 已修复（v4.12.1）

## 当前存在的问题（v4.12.1 - 需要深化解决）

### 问题1: 数据丢失问题持续存在

**问题描述**：
- 数据同步精确度未达到100%，持续存在数据丢失
- 最新测试：Raw: 693行，Staging: 692行，Fact: 656行，丢失37行
- 隔离区显示为0，说明丢失的数据没有被隔离

**可能原因**：
1. **自动隔离机制可能失败**：
   - 事务回滚时隔离记录可能被回滚
   - 数据库连接问题导致隔离失败
   - 隔离机制本身的异常处理不完善

2. **验证阶段失败未隔离**：
   - 数据验证失败时可能直接跳过，没有隔离
   - 验证错误可能没有被正确捕获

3. **Staging阶段失败未隔离**：
   - Staging失败时可能直接跳过，没有隔离
   - Staging错误可能没有被正确捕获

4. **数据库约束错误未隔离**：
   - 主键冲突、外键约束等错误可能导致数据丢失
   - 这些错误可能没有被隔离机制捕获

5. **关键字段处理问题**：
   - shop_id或其他关键字段处理逻辑可能仍有问题
   - 导致数据无法入库但也没有被隔离

**需要调查**：
- 检查自动隔离机制的日志，确认是否有隔离失败的记录
- 检查验证和staging阶段的错误处理
- 检查数据库约束错误处理
- 分析丢失数据的共同特征

### 问题2: 字段映射应用可能未完全解决

**问题描述**：
- 虽然已修复platform_code和shop_id的获取，但可能还有其他字段映射问题
- Pattern Matcher警告虽然已修复，但需要验证是否完全解决
- 某些字段可能没有正确映射到标准字段

**可能原因**：
- 字段映射应用的完整流程可能仍有问题
- Pattern Matcher的运行时机可能仍有问题
- 数据标准化函数可能没有正确处理所有字段

**需要调查**：
- 检查字段映射应用的完整流程
- 检查Pattern Matcher的运行时机
- 检查数据标准化函数
- 分析丢失数据的字段特征

### 问题3: 对比报告丢失数据详情需要验证

**问题描述**：
- 虽然已添加丢失数据详情显示功能，但需要验证是否正常工作
- 用户反馈对比报告中看不到丢失数据详情

**需要验证**：
- 测试对比报告API，确认是否正确返回丢失数据详情
- 测试前端显示，确认是否正确显示丢失数据详情表格
- 检查日志，确认查询逻辑是否正确执行

### 问题4: 数据流转追踪部分未解决

**问题描述**：
- 数据流转追踪在某些情况下显示"暂无流转数据"
- 虽然已修复FactProductMetric和DataQuarantine的字段引用，但可能还有其他问题

**需要调查**：
- 检查数据流转查询逻辑
- 检查file_id字段的设置
- 检查数据流转API的日志

## Migration Plan

### 当前状态

- ✅ 功能已实现（v4.12.0）
- ✅ API已部署
- ✅ 前端已集成
- ❌ 缺少OpenSpec规范

### 迁移步骤

1. **创建OpenSpec规范**（本变更提案）
   - 定义完整的需求和场景
   - 明确与其他能力的集成关系
   - 验证规范格式

2. **归档规范**
   - 将规范从changes移动到specs目录
   - 更新openspec/README.md

3. **更新相关文档**
   - 确保docs/DATA_SYNC_ARCHITECTURE.md与规范对齐
   - 更新其他相关文档

### Rollback

- 本变更仅添加规范文档，不修改代码
- 如需回滚，删除changes目录即可
- 不影响现有功能

## Open Questions

- [ ] 是否需要支持暂停/恢复同步任务？
- [ ] 是否需要支持优先级队列？
- [ ] 是否需要支持分布式部署（多实例）？

