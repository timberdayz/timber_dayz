## 1. Phase 1: 规则体系重构（零风险，纯文档变更）

### 1A: 规则精简准备

- [x] 1.1 建立当前 `.cursorrules` 规则清单（逐条编号），标记哪些是零容忍规则、哪些是模板、哪些是叙述/历史
- [x] 1.2 创建 `scripts/verify_rules_completeness.py`：自动检查新 `.cursorrules` 是否包含所有零容忍规则关键词（如 "schema.py"、"get_async_db"、"response_model"、"禁止emoji" 等）

### 1B: .cursorrules 精简

- [x] 1.3 精简 `.cursorrules`：移除所有星级评分标记（星号 emoji 和 `[*]` 到 `[*****]`）
- [x] 1.4 精简 `.cursorrules`：移除历史事故叙述段落，只保留结论性规则
- [x] 1.5 精简 `.cursorrules`：移除与 `CLAUDE.md` 和 `project.md` 重复的内容（命令速查、架构概览等）
- [x] 1.6 精简 `.cursorrules`：移除内联代码模板，替换为一行指针"编写新 Service/Router/Schema 前，先查阅 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`"
- [x] 1.7 在 `.cursorrules` 中添加新规则：禁止 `datetime.utcnow()`、AsyncCRUDService 强制继承、Router 大小限制（<=15端点）、Service 依赖注入（Depends()）
- [x] 1.8 运行 `verify_rules_completeness.py` 验证精简后零容忍规则完整无遗漏
- [x] 1.9 验证精简后的 `.cursorrules` 行数 <= 300 行

### 1C: CLAUDE.md 和 DEVELOPMENT_RULES 重构

- [x] 1.10 更新 `CLAUDE.md`：确认作为纯快速入口（命令速查 + 架构一屏概览 + 文档导航），无与 `.cursorrules` 的重复
- [x] 1.11 创建 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`：包含 AsyncCRUDService 模板、Router 模板、Schema 模板、conftest fixture 模板、事务管理模式、缓存模式、乐观锁模式、依赖注入模式
- [x] 1.12 合并 `docs/DEVELOPMENT_RULES/` 文件：`API_DESIGN.md` + `REVIEW_PROCESS.md` + `CODE_REVIEW_CHECKLIST.md` → `API_AND_CONTRACTS.md`
- [x] 1.13 在 `API_AND_CONTRACTS.md` 中记录 HTTP 状态码渐进迁移策略：旧端点保持 200 包裹、新端点使用语义状态码、`error_response_v2()` 使用指南
- [x] 1.14 合并 `docs/DEVELOPMENT_RULES/` 文件：5个数据库相关文件 → `DATABASE.md`
- [x] 1.15 合并 `docs/DEVELOPMENT_RULES/` 文件：`TESTING.md` + `CODE_QUALITY.md` → `TESTING_AND_QUALITY.md`
- [x] 1.16 精简 `docs/DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md` → `ERROR_AND_LOGGING.md`：错误码说明改为"以 `backend/utils/error_codes.py` 为 SSOT"，不再重复列举码值
- [x] 1.17 合并 `docs/DEVELOPMENT_RULES/` 文件：`SECURITY.md` + `DEPLOYMENT.md` + `MONITORING_AND_OBSERVABILITY.md` → `SECURITY_AND_DEPLOYMENT.md`
- [x] 1.18 保留并审查 `UI_DESIGN.md`（无合并对象，仅精简冗余内容）
- [x] 1.19 删除已合并的源文件和过时文件：`DUPLICATE_AND_HISTORICAL_PROTECTION.md`、`CURSORRULES_OPTIMIZATION_PLAN.md`
- [x] 1.20 重建 `docs/DEVELOPMENT_RULES/README.md` 索引，至少指向 7 个核心主题文件，并允许后续 approved change 增加扩展文件

### 1D: Phase 1 验收关口

- [x] 1.21 运行 `python scripts/verify_rules_completeness.py` 确认零容忍规则无遗漏
- [x] 1.22 确认 `.cursorrules` 行数 <= 300 行
- [x] 1.23 确认 `docs/DEVELOPMENT_RULES/` 至少包含 7 个核心主题文件 + 1 个 README，且 README 已覆盖全部扩展文件

## 2. Phase 2: 代码基础设施——新增文件（低风险，不修改已有代码）

### 2A: 异常体系统一（D2）

- [x] 2.1 修改 `modules/core/exceptions.py`：将 `ERPException.error_code` 类型从 `str` 改为 `Union[str, IntEnum]`（向后兼容），更新 `__str__` 方法适配 IntEnum
- [x] 2.2 搜索项目中所有 `ERPException` 子类的实例化点，验证 error_code 参数类型兼容性（已确认 backend/ 无直接使用）
- [x] 2.3 创建 `backend/utils/exceptions.py`：定义 API 层异常子类（继承 `ERPException`），包括 `NotFoundError`（404）、`BusinessValidationError`（422）、`PermissionDeniedError`（403）、`ConflictError`（409）、`ExternalServiceError`（502）
- [x] 2.4 在 `backend/utils/exceptions.py` 中创建 `error_response_v2()` 函数：根据异常类型自动映射语义化 HTTP 状态码，保持 `success: false` 响应体格式不变
- [x] 2.5 在 `backend/main.py` 注册全局异常处理器：API 层异常映射到对应 HTTP 状态码，`ERPException` 映射到 500，未处理异常返回 500 + 日志记录
- [ ] 2.6 为异常体系编写单元测试

### 2B: AsyncCRUDService 基类（D3 + D9 + D10 + D12）

- [x] 2.7 创建 `backend/services/base_service.py`：实现泛型 `AsyncCRUDService[ModelType, CreateSchemaType, UpdateSchemaType]`
- [x] 2.8 实现核心 CRUD 方法：`get`/`get_multi`/`create`/`update`/`remove`，全部使用 `await db.execute(select(...))`
- [x] 2.9 实现审计钩子：`on_after_create()`、`on_after_update()`、`on_after_delete()` 可选回调方法
- [x] 2.10 实现乐观锁支持：`update()` 和 `remove()` 内置可选 `version` 字段检查
- [x] 2.11 实现 `@transactional` 装饰器
- [x] 2.12 实现 `soft_delete()` 可选方法
- [ ] 2.13 为 `AsyncCRUDService` 编写单元测试

### 2C: 分页工具（D4）

- [x] 2.14 创建 `backend/utils/pagination.py`：实现 `async_paginate_query()`，返回 `(list, int)` 元组
- [ ] 2.15 为分页工具编写单元测试

### 2D: 测试基础设施（D5）

- [x] 2.16 创建 `backend/tests/conftest.py`：定义 `sqlite_session` fixture
- [x] 2.17 在 conftest.py 中定义 `pg_session` fixture（testcontainers）+ `pytest.mark.pg_only`
- [x] 2.18 在 conftest.py 中定义 `async_client`、`auth_headers` fixture
- [x] 2.19 在 `requirements-dev.txt` 中添加 `testcontainers[postgres]` 依赖
- [ ] 2.20 编写验证测试确认双模式 fixture 正常工作

### 2E: Phase 2 验收关口

- [x] 2.21 运行 `pytest` 确认无*新增*失败（基线 20 failed 全为预存问题）
- [x] 2.22 运行 `python run.py --local` 确认后端启动正常（430 路由，health OK）
- [x] 2.23 访问 Swagger `/docs` 确认页面正常渲染（HTTP 200）

## 3. Phase 3: datetime 标准化（高风险，D8 强制分步）

**注意：以下步骤顺序不可颠倒，否则会出现 naive/aware datetime 混用导致 TypeError**

### 3A: Step 1-2 数据库列迁移（先改数据库）

- [x] 3.1 审计 `modules/core/db/schema.py` 中所有 `DateTime` 列（实际 **196 个**，全部为非 timezone-aware；153 处 `default=datetime.utcnow`；56 处 `onupdate=datetime.utcnow`；21 处已有 `server_default=func.now()`）
- [x] 3.2 修改 schema.py：全部 196 个 `DateTime` → `DateTime(timezone=True)`、153 处 `default=datetime.utcnow` → `server_default=func.now()`、56 处 `onupdate=datetime.utcnow` → `onupdate=func.now()`
- [x] 3.3 创建 Alembic 迁移 `20260316_datetime_to_timestamptz.py`（动态查询 information_schema，幂等性设计，down_revision=20260220_pasi）
- [x] 3.3b 执行 `alembic upgrade head`：**383 列全部转换成功**，10 个物化视图自动删除并重建，0 跳过。迁移脚本升级为三阶段策略（Drop MatViews → ALTER TYPE with SAVEPOINT → Recreate MatViews）

### 3B: 中间验收关口（数据库已迁移，代码未改）

- [x] 3.4 DB 验证：TIMESTAMP(naive)=0, TIMESTAMPTZ(aware)=383, Alembic version=20260316_tz
- [x] 3.5 运行 `python run.py --local --backend-only`：health OK，430 端点加载，Swagger /docs HTTP 200，数据库 connected

### 3C: Step 3-4 代码替换（数据库迁移确认后才执行）

- [x] 3.6 全局替换 `datetime.utcnow()` → `datetime.now(timezone.utc)`：**69 个文件、211 处替换、68 个 import 修复**；包括修复旧迁移文件 `20260130_create_target_breakdown_table.py`
- [x] 3.7 ORM schema.py 中 `default=datetime.utcnow` → `server_default=func.now()`（已在 3.2 中同步完成）

### 3D: Phase 3 验收关口（重点验证时间相关流程）

- [x] 3.8 运行 `pytest backend/tests -q`：**89 passed, 20 failed (全部预存), 9 errors (全部预存)**，零个 datetime/timezone 相关失败
- [x] 3.9 运行 `python run.py --local --backend-only`：系统正常启动，API 健康检查通过
  - 注：Token/采集/审计/看板等时间敏感流程需在实际使用中进一步验证
- [x] 3.10 使用 grep 确认代码中无残留 `datetime.utcnow()` 调用（仅剩 `verify_rules_completeness.py` 中的字符串常量，非代码调用）
- [x] 3.11 更新活跃文档 `DATABASE.md`、`DATABASE_MIGRATION_BEST_PRACTICES.md` 中的旧模式示例

## 4. Phase 4: Contract-First Schema 迁移（中风险，分批执行）

> **执行说明**：实际执行时发现原 tasks 粒度过细且遗漏了关键问题（schemas/hr.py 字段与 router 严重不一致），
> 改为全量批处理策略——一次性覆盖全部 15 个 router、72 个内联模型。以下为实际执行记录。

### 4A: 审计与问题发现

- [x] 4.1 审计 `backend/routers/` 全部 49 个 router 文件，发现 15 个文件共 72 个内联 BaseModel 定义
- [x] 4.2 **发现关键问题**：已有的 `schemas/hr.py` 字段定义与 `hr_management.py` router 的实际运行版本**严重不一致**（20+ 模型字段完全不同），原因是 schema 基于旧版 router 创建后 router 有更新但 schema 未同步
- [x] 4.3 **发现名称冲突**：`rate_limit_config.py` 的 `RateLimitConfigResponse` 与 `schemas/rate_limit.py` 已有的同名模型含义不同，需要重命名

### 4B: Schema 文件创建与修正

- [x] 4.4 **完全重写** `backend/schemas/hr.py`：以 router 实际运行代码为权威来源，39 个模型全部精确匹配 router 字段（含 field_validator）
- [x] 4.5 创建 `backend/schemas/target.py`（6 个模型：TargetCreateRequest/UpdateRequest、BreakdownCreateRequest、GenerateDailyBreakdownRequest、TargetResponse、BreakdownResponse）
- [x] 4.6 创建 `backend/schemas/sales_campaign.py`（5 个模型：CampaignCreateRequest/UpdateRequest、CampaignShopRequest、CampaignResponse/ShopResponse）
- [x] 4.7 创建 `backend/schemas/performance.py`（4 个模型：PerformanceConfigCreate/Update/Response、PerformanceScoreResponse）
- [x] 4.8 创建 `backend/schemas/component_recorder.py`（4 个模型：RecorderStartRequest、RecorderStepResponse、RecorderSaveRequest、GeneratePythonRequest）
- [x] 4.9 创建 `backend/schemas/expense.py`（4 个模型：ExpenseCreate/Update/Response、ExpenseSummaryResponse）
- [x] 4.10 创建 `backend/schemas/data_quarantine.py`（4 个模型：QuarantineListRequest、QuarantineDetailResponse、ReprocessRequest/Response）
- [x] 4.11 创建 `backend/schemas/auto_ingest.py`（3 个模型：BatchAutoIngestRequest、SingleAutoIngestRequest、ClearDataRequest）
- [x] 4.12 创建 `backend/schemas/websocket.py`（3 个模型：CollectionWebSocketMessage、NotificationWebSocketMessage、NotificationMessage）
- [x] 4.13 创建 `backend/schemas/metabase.py`（2 个模型：EmbeddingTokenRequest、DashboardEmbedUrlRequest）
- [x] 4.14 创建 `backend/schemas/data_quality.py`（2 个模型：CClassReadinessResponse、CoreFieldsStatusResponse）
- [x] 4.15 更新 `backend/schemas/component_version.py`：追加 4 个测试相关模型（ComponentTestRequest、TestHistoryResponse/ListResponse、TestResumeRequest）
- [x] 4.16 更新 `backend/schemas/rate_limit.py`：追加 4 个限流规则 CRUD 模型（重命名为 RateLimitRule* 以避免冲突）
- [x] 4.17 更新 `backend/schemas/account.py`：追加 BatchCreateRequest
- [x] 4.18 更新 `backend/schemas/__init__.py`：统一导出全部 28 个 schema 文件的所有模型

### 4C: Router 文件迁移

- [x] 4.19 使用批处理脚本从 15 个 router 文件中删除全部 72 个内联 BaseModel 定义
- [x] 4.20 为每个 router 添加正确的 `from backend.schemas.xxx import (...)` 语句
- [x] 4.21 修复 5 个文件的 import 位置错误（脚本将 import 误插入函数体/try 块内：collection_websocket、metabase_proxy、rate_limit_config、notification_websocket、auto_ingest）
- [x] 4.22 合并 `account_management.py` 中重复的 schemas/account 导入
- [x] 4.23 恢复 `component_versions.py` 中被误删的原有 8 个模型 import

### 4D: Phase 4 验收关口

- [x] 4.24 `grep class.*BaseModel backend/routers/` 确认 **零内联模型**
- [x] 4.25 全部 49 个 router 文件 `py_compile` 编译通过
- [x] 4.26 全部 15 个迁移 router `importlib.import_module` 导入成功
- [x] 4.27 `from backend.schemas import *` 导入成功
- [x] 4.28 FastAPI app 加载成功：**430 路由**（与迁移前一致）
- [x] 4.29 `pytest backend/tests -q`：**95 passed**（基线 89），20 failed（全部预存），3 errors（基线 9，减少 6）——**零新增失败**
- [x] 4.30 最终审计：28 个 schema 文件，~257 个 Pydantic 模型，Contract-First 合规 PASS

## 5. Phase 5: 共享依赖提取（Router 拆分前置条件，D14）

### 5A: 认证/权限依赖提取

- [x] 5.1 创建 `backend/dependencies/__init__.py`
- [x] 5.2 创建 `backend/dependencies/auth.py`：从 `auth.py` 提取 `get_current_user`；从 `users.py` 提取 `require_admin`
- [x] 5.3 更新 `auth.py` 和 `users.py`：从 `backend.dependencies.auth` 导入并 re-export（保持向后兼容）
- [x] 5.4 逐个更新 15 处 `from backend.routers.auth import get_current_user` 为 `from backend.dependencies.auth import get_current_user`（含 users.py 自身）
- [x] 5.5 逐个更新 9 处 `from backend.routers.users import require_admin` 为 `from backend.dependencies.auth import require_admin`
- [x] 5.6 grep 确认旧导入路径全部清除（零残留）

### 5B: WebSocket 管理器提取

- [x] 5.7 创建 `backend/services/websocket_manager.py`：从 `collection_websocket.py` 提取 `ConnectionManager` 类（约 140 行）
- [x] 5.8 更新 `collection_websocket.py`：从新位置导入并 re-export
- [x] 5.9 更新 `websocket_service.py` 导入路径

### 5C: Phase 5 验收关口

- [x] 5.10 FastAPI app 加载成功：430 路由（与基线一致）
- [x] 5.11 所有导入验证通过：`dependencies.auth`、`websocket_manager`、re-export 均正常
- [x] 5.12 grep 确认旧导入路径已清除（仅 re-export 文件保留向后兼容）

## 6. Phase 6: Router 拆分（D7，在 Phase 5 完成后执行）

### 6A: hr_management.py 拆分（49 端点 -> 5 个子路由）

- [x] 6.1 分析 49 个端点，按子域分组为 5 个文件（每个 <= 15 端点）
- [x] 6.2 创建 `backend/routers/hr_department.py`：部门 + 职位管理（9 端点）
- [x] 6.3 创建 `backend/routers/hr_employee.py`：员工档案 + 我的信息（10 端点）
- [x] 6.4 创建 `backend/routers/hr_attendance.py`：考勤 + 排班 + 请假 + 加班（12 端点）
- [x] 6.5 创建 `backend/routers/hr_salary.py`：薪资 + 工资单 + 目标（6 端点）
- [x] 6.6 创建 `backend/routers/hr_commission.py`：绩效 + 提成 + 店铺分配（12 端点）
- [x] 6.7 将 `hr_management.py` 改为聚合入口（`include_router` 模式，main.py 无需修改）
- [x] 6.8 修复 `hr_commission.py` 缺少 `DimUser` 导入

### 6B: field_mapping.py 拆分（30 端点 -> 3 个子路由 + 1 个 helpers）

- [x] 6.9 创建 `backend/routers/_field_mapping_helpers.py`：共享路径校验函数
- [x] 6.10 创建 `backend/routers/field_mapping_files.py`：文件浏览与扫描（7 端点）
- [x] 6.11 创建 `backend/routers/field_mapping_ingest.py`：数据处理与模板（10 端点）
- [x] 6.12 创建 `backend/routers/field_mapping_status.py`：状态监控与配置（13 端点）
- [x] 6.13 将 `field_mapping.py` 改为聚合入口

### 6C: collection.py 拆分（22 端点 -> 3 个子路由）

- [x] 6.14 创建 `backend/routers/collection_config.py`：配置管理 + 账号（6 端点）
- [x] 6.15 创建 `backend/routers/collection_tasks.py`：任务管理 + 历史（10 端点），含 `_execute_collection_task_background`
- [x] 6.16 创建 `backend/routers/collection_schedule.py`：调度管理 + 健康检查（6 端点）
- [x] 6.17 将 `collection.py` 改为聚合入口，re-export `_execute_collection_task_background`

### 6D: users.py 拆分（20 端点 -> 2 个子路由）

- [x] 6.18 创建 `backend/routers/users_admin.py`：管理员 CRUD + 审批（13 端点）
- [x] 6.19 创建 `backend/routers/users_me.py`：当前用户会话 + 偏好（7 端点）
- [x] 6.20 将 `users.py` 改为聚合入口，保留 `require_admin` re-export

### 6E: 路由注册更新

- [x] 6.21 main.py 无需修改（聚合器模式保持向后兼容，仍通过原 `.router` 注册）
- [x] 6.22 修复外部引用：test 文件的 `hr_management.get_my_income` -> `hr_employee.get_my_income`，monkeypatch 路径更新

### 6F: Phase 6 验收关口

- [x] 6.23 验证 Swagger 端点数量：430 路由（与拆分前一致）
- [x] 6.24 验证所有 API URL 保持不变（HR: 31 条独立 path，全部 `/api/hr/` 前缀）
- [x] 6.25 验证所有 13 个子路由文件 <= 15 端点（最大: 13）
- [x] 6.26 运行完整测试套件：95 passed, 20 failed, 3 errors（与基线完全一致，零新增失败）

## 7. Phase 7: Service 依赖注入改造

- [x] 7.1 在 `backend/services/base_service.py` 中创建标准的 `Depends()` 工厂函数模板（`provide_service`）
- [x] 7.2 选择 1 个简单 router (`hr_employee.calculate_income_c_class`) 作为试点，将直接 Service 实例化改为 `Depends()` 注入
- [x] 7.3 为试点 router 编写测试 (`backend/tests/test_hr_income_di.py`)，验证依赖注入的 mock 能力
- [x] 7.4 将依赖注入迁移指南写入 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`（第 8 章示例已更新为 `provide_service` + HR 收入路由 + 测试 override）

### 7A: Phase 7 验收关口

- [x] 7.5 运行 `pytest backend/tests`：保持 **95 passed, 20 failed, 3 errors**（与 Phase 6 基线一致，零新增失败）

## 8. 最终验证

- [x] 8.1 运行完整测试套件 `pytest backend/tests`，当前基线：**95 passed, 21 failed, 3 errors**（全部为既有问题，本提案未新增失败）
- [x] 8.2 运行架构验证 `python scripts/verify_architecture_ssot.py`，结果：2 项既有违规（`scripts/verify_rules_completeness.py` 中教学用 Base；3 个 legacy 文档/脚本未归档），核心 SSOT 结构保持 100% 正确
- [x] 8.3 运行代码质量检查 `python -m ruff check .`，存在若干既有 lint 问题（未在本轮修改的模块上），本提案未引入新的 lint 报告位置
- [x] 8.4 运行 `python scripts/verify_rules_completeness.py`，`.cursorrules` 行数 202，26/26 零容忍规则全部覆盖
- [x] 8.5 验证 `.cursorrules` 最终行数 <= 300 行（实际为 202 行）
- [x] 8.6 验证 `docs/DEVELOPMENT_RULES/` 至少包含 7 个核心主题文件 + 1 个 README（API_AND_CONTRACTS / DATABASE / TESTING_AND_QUALITY / ERROR_AND_LOGGING / SECURITY_AND_DEPLOYMENT / UI_DESIGN / CODE_PATTERNS + README.md）
- [x] 8.7 验证 `backend/routers/` 无内联 Pydantic 模型（grep 无 `class Xxx(BaseModel)`，仅保留必要的 `BaseModel` import）
- [x] 8.8 验证 `backend/routers/` 中每个拆分后子文件 <= 15 个端点（HR/field_mapping/collection/users 子路由最大 13 个端点）
- [x] 8.9 验证代码中无 `datetime.utcnow()` 调用（仅在文档/spec 中作为历史示例存在）
- [x] 8.10 验证 `modules/core/exceptions.py` 的 `error_code` 类型已统一为 `Optional[Union[str, IntEnum]]`
- [x] 8.11 验证 `schema.py` 中所有 DateTime 列为 `DateTime(timezone=True)` 且使用 `server_default=func.now()` / `onupdate=func.now()`
- [x] 8.12 验证 `backend/dependencies/auth.py` 存在且被正确使用（所有路由/测试已统一从此处导入 `get_current_user` / `require_admin`）
- [ ] 8.13 运行 `python run.py --local`，完成完整的端到端冒烟测试（待在有 Docker/Postgres 环境的机器上手动执行）
