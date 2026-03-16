## 1. Phase 1: 规则体系重构（零风险，纯文档变更）

### 1A: 规则精简准备

- [ ] 1.1 建立当前 `.cursorrules` 规则清单（逐条编号），标记哪些是零容忍规则、哪些是模板、哪些是叙述/历史
- [ ] 1.2 创建 `scripts/verify_rules_completeness.py`：自动检查新 `.cursorrules` 是否包含所有零容忍规则关键词（如 "schema.py"、"get_async_db"、"response_model"、"禁止emoji" 等）

### 1B: .cursorrules 精简

- [ ] 1.3 精简 `.cursorrules`：移除所有星级评分标记（星号 emoji 和 `[*]` 到 `[*****]`）
- [ ] 1.4 精简 `.cursorrules`：移除历史事故叙述段落，只保留结论性规则
- [ ] 1.5 精简 `.cursorrules`：移除与 `CLAUDE.md` 和 `project.md` 重复的内容（命令速查、架构概览等）
- [ ] 1.6 精简 `.cursorrules`：移除内联代码模板，替换为一行指针"编写新 Service/Router/Schema 前，先查阅 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`"
- [ ] 1.7 在 `.cursorrules` 中添加新规则：禁止 `datetime.utcnow()`、AsyncCRUDService 强制继承、Router 大小限制（<=15端点）、Service 依赖注入（Depends()）
- [ ] 1.8 运行 `verify_rules_completeness.py` 验证精简后零容忍规则完整无遗漏
- [ ] 1.9 验证精简后的 `.cursorrules` 行数 <= 300 行

### 1C: CLAUDE.md 和 DEVELOPMENT_RULES 重构

- [ ] 1.10 更新 `CLAUDE.md`：确认作为纯快速入口（命令速查 + 架构一屏概览 + 文档导航），无与 `.cursorrules` 的重复
- [ ] 1.11 创建 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`：包含 AsyncCRUDService 模板、Router 模板、Schema 模板、conftest fixture 模板、事务管理模式、缓存模式、乐观锁模式、依赖注入模式
- [ ] 1.12 合并 `docs/DEVELOPMENT_RULES/` 文件：`API_DESIGN.md` + `REVIEW_PROCESS.md` + `CODE_REVIEW_CHECKLIST.md` → `API_AND_CONTRACTS.md`
- [ ] 1.13 在 `API_AND_CONTRACTS.md` 中记录 HTTP 状态码渐进迁移策略：旧端点保持 200 包裹、新端点使用语义状态码、`error_response_v2()` 使用指南
- [ ] 1.14 合并 `docs/DEVELOPMENT_RULES/` 文件：5个数据库相关文件 → `DATABASE.md`
- [ ] 1.15 合并 `docs/DEVELOPMENT_RULES/` 文件：`TESTING.md` + `CODE_QUALITY.md` → `TESTING_AND_QUALITY.md`
- [ ] 1.16 精简 `docs/DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md` → `ERROR_AND_LOGGING.md`：错误码说明改为"以 `backend/utils/error_codes.py` 为 SSOT"，不再重复列举码值
- [ ] 1.17 合并 `docs/DEVELOPMENT_RULES/` 文件：`SECURITY.md` + `DEPLOYMENT.md` + `MONITORING_AND_OBSERVABILITY.md` → `SECURITY_AND_DEPLOYMENT.md`
- [ ] 1.18 保留并审查 `UI_DESIGN.md`（无合并对象，仅精简冗余内容）
- [ ] 1.19 删除已合并的源文件和过时文件：`DUPLICATE_AND_HISTORICAL_PROTECTION.md`、`CURSORRULES_OPTIMIZATION_PLAN.md`
- [ ] 1.20 重建 `docs/DEVELOPMENT_RULES/README.md` 索引，至少指向 7 个核心主题文件，并允许后续 approved change 增加扩展文件

### 1D: Phase 1 验收关口

- [ ] 1.21 运行 `python scripts/verify_rules_completeness.py` 确认零容忍规则无遗漏
- [ ] 1.22 确认 `.cursorrules` 行数 <= 300 行
- [ ] 1.23 确认 `docs/DEVELOPMENT_RULES/` 至少包含 7 个核心主题文件 + 1 个 README，且 README 已覆盖全部扩展文件

## 2. Phase 2: 代码基础设施——新增文件（低风险，不修改已有代码）

### 2A: 异常体系统一（D2）

- [ ] 2.1 修改 `modules/core/exceptions.py`：将 `ERPException.error_code` 类型从 `str` 改为 `Union[str, IntEnum]`（向后兼容），更新 `__str__` 方法适配 IntEnum
- [ ] 2.2 搜索项目中所有 `ERPException` 子类的实例化点，验证 error_code 参数类型兼容性（已确认 backend/ 无直接使用）
- [ ] 2.3 创建 `backend/utils/exceptions.py`：定义 API 层异常子类（继承 `ERPException`），包括 `NotFoundError`（404）、`BusinessValidationError`（422）、`PermissionDeniedError`（403）、`ConflictError`（409）、`ExternalServiceError`（502）
- [ ] 2.4 在 `backend/utils/exceptions.py` 中创建 `error_response_v2()` 函数：根据异常类型自动映射语义化 HTTP 状态码，保持 `success: false` 响应体格式不变
- [ ] 2.5 在 `backend/main.py` 注册全局异常处理器：API 层异常映射到对应 HTTP 状态码，`ERPException` 映射到 500，未处理异常返回 500 + 日志记录
- [ ] 2.6 为异常体系编写单元测试

### 2B: AsyncCRUDService 基类（D3 + D9 + D10 + D12）

- [ ] 2.7 创建 `backend/services/base_service.py`：实现泛型 `AsyncCRUDService[ModelType, CreateSchemaType, UpdateSchemaType]`
- [ ] 2.8 实现核心 CRUD 方法：`get`/`get_multi`/`create`/`update`/`remove`，全部使用 `await db.execute(select(...))`
- [ ] 2.9 实现审计钩子：`on_after_create()`、`on_after_update()`、`on_after_delete()` 可选回调方法
- [ ] 2.10 实现乐观锁支持：`update()` 和 `remove()` 内置可选 `version` 字段检查
- [ ] 2.11 实现 `@transactional` 装饰器
- [ ] 2.12 实现 `soft_delete()` 可选方法
- [ ] 2.13 为 `AsyncCRUDService` 编写单元测试

### 2C: 分页工具（D4）

- [ ] 2.14 创建 `backend/utils/pagination.py`：实现 `async_paginate_query()`，返回 `(list, int)` 元组
- [ ] 2.15 为分页工具编写单元测试

### 2D: 测试基础设施（D5）

- [ ] 2.16 创建 `backend/tests/conftest.py`：定义 `sqlite_session` fixture
- [ ] 2.17 在 conftest.py 中定义 `pg_session` fixture（testcontainers）+ `pytest.mark.pg_only`
- [ ] 2.18 在 conftest.py 中定义 `async_client`、`auth_headers` fixture
- [ ] 2.19 在 `requirements-dev.txt` 中添加 `testcontainers[postgres]` 依赖
- [ ] 2.20 编写验证测试确认双模式 fixture 正常工作

### 2E: Phase 2 验收关口

- [ ] 2.21 运行 `pytest` 确认零失败
- [ ] 2.22 运行 `python run.py --local` 确认后端启动正常
- [ ] 2.23 访问 Swagger `/docs` 确认页面正常渲染

## 3. Phase 3: datetime 标准化（高风险，D8 强制分步）

**注意：以下步骤顺序不可颠倒，否则会出现 naive/aware datetime 混用导致 TypeError**

### 3A: Step 1-2 数据库列迁移（先改数据库）

- [ ] 3.1 审计 `modules/core/db/schema.py` 中所有 `DateTime` 列（当前共 193 个，全部为非 timezone-aware）：确认完整列表
- [ ] 3.2 创建 Alembic 迁移：将全部 193 个 `DateTime` 列统一为 `DateTime(timezone=True)`（幂等性检查），PG 的 `TIMESTAMP -> TIMESTAMPTZ` 无损转换
- [ ] 3.3 执行 Alembic 迁移（建议低峰期）

### 3B: 中间验收关口（数据库已迁移，代码未改）

- [ ] 3.4 运行 `pytest` 确认数据库迁移后现有代码仍正常（PG TIMESTAMPTZ 向后兼容 naive datetime）
- [ ] 3.5 运行 `python run.py --local` 确认系统正常运行

### 3C: Step 3-4 代码替换（数据库迁移确认后才执行）

- [ ] 3.6 全局搜索并替换 `datetime.utcnow()` 为 `datetime.now(timezone.utc)`（约150+处），更新相关 import 语句。**必须一次性完成，不能只改一半**
- [ ] 3.7 检查 ORM schema.py 中的 `default=datetime.utcnow` 并替换为 `server_default=func.now()`

### 3D: Phase 3 验收关口（重点验证时间相关流程）

- [ ] 3.8 运行 `pytest` 确认零失败
- [ ] 3.9 运行 `python run.py --local` 手动验证：
  - Token 过期/刷新机制正常
  - 采集任务调度（涉及时间比较）正常
  - 审计日志查询（涉及时间范围查询）正常
  - 数据看板时间筛选正常
- [ ] 3.10 使用 grep 确认代码中无残留 `datetime.utcnow()` 调用

## 4. Phase 4: Contract-First Schema 迁移（中风险，分批执行）

### 4A: P0 批次

- [ ] 4.1 搜索项目中是否有外部模块从 `hr_management.py` 导入 Pydantic 模型，记录列表
- [ ] 4.2 从 `hr_management.py` 提取 37 个内联 Pydantic 模型到 `backend/schemas/hr.py`
- [ ] 4.3 更新 `hr_management.py` 的 import 语句；如有外部导入，添加兼容性 re-export
- [ ] 4.4 更新 `backend/schemas/__init__.py`
- [ ] 4.5 运行 HR 相关测试确认无回归
- [ ] 4.6 搜索项目中是否有外部模块从 `component_versions.py` 导入 Pydantic 模型
- [ ] 4.7 从 `component_versions.py` 提取 12 个内联 Pydantic 模型到 `backend/schemas/component_version.py`
- [ ] 4.8 更新 `component_versions.py` 的 import 语句 + 兼容性 re-export
- [ ] 4.9 更新 `backend/schemas/__init__.py`
- [ ] 4.10 运行 component_version 相关测试确认无回归

### 4B: P1 批次

- [ ] 4.11 从 `config_management.py` 提取 6 个内联模型到 `backend/schemas/config.py`
- [ ] 4.12 从 `target_management.py` 提取 6 个内联模型到 `backend/schemas/target.py`
- [ ] 4.13 从 `sales_campaign.py` 提取 5 个内联模型到 `backend/schemas/sales_campaign.py`
- [ ] 4.14 更新上述三个 router 文件的 import 语句、兼容性 re-export 和 `schemas/__init__.py`
- [ ] 4.15 运行全部相关测试确认无回归

### 4C: P2 批次

- [ ] 4.16 从 `component_recorder.py` 提取 4 个内联模型到 `backend/schemas/component_recorder.py`
- [ ] 4.17 从 `performance_management.py` 提取 4 个内联模型到 `backend/schemas/performance.py`
- [ ] 4.18 从 `expense_management.py` 提取 4 个内联模型到 `backend/schemas/expense.py`
- [ ] 4.19 从 `rate_limit_config.py` 提取 4 个内联模型到 `backend/schemas/rate_limit.py`
- [ ] 4.20 从 `data_quarantine.py` 提取 4 个内联模型到 `backend/schemas/data_quarantine.py`
- [ ] 4.21 从 `auto_ingest.py` 提取 3 个内联模型到 `backend/schemas/auto_ingest.py`
- [ ] 4.22 从剩余 router 文件提取全部内联模型到对应 schema 文件
- [ ] 4.23 更新所有修改的 router 文件的 import 语句、兼容性 re-export 和 `schemas/__init__.py`

### 4D: Phase 4 验收关口

- [ ] 4.24 运行完整测试套件确认零失败
- [ ] 4.25 使用 grep 验证 `backend/routers/` 下不再有 `class.*BaseModel` 定义（零内联模型）
- [ ] 4.26 运行 `python run.py --local` 确认系统正常

## 5. Phase 5: 共享依赖提取（Router 拆分前置条件，D14）

### 5A: 认证/权限依赖提取

- [ ] 5.1 创建 `backend/dependencies/__init__.py`
- [ ] 5.2 创建 `backend/dependencies/auth.py`：从 `auth.py` 提取 `get_current_user`、`get_optional_user`；从 `users.py` 提取 `require_admin`、`require_role`
- [ ] 5.3 更新 `auth.py` 和 `users.py`：从 `backend.dependencies.auth` 导入并 re-export（保持向后兼容）
- [ ] 5.4 逐个更新 14 处 `from backend.routers.auth import get_current_user` 为 `from backend.dependencies.auth import get_current_user`
- [ ] 5.5 逐个更新 9 处 `from backend.routers.users import require_admin` 为 `from backend.dependencies.auth import require_admin`
- [ ] 5.6 运行 `pytest` 确认无回归

### 5B: WebSocket 管理器提取

- [ ] 5.7 创建 `backend/services/websocket_manager.py`：从 `collection_websocket.py` 提取 `ConnectionManager` 类
- [ ] 5.8 更新 `collection_websocket.py`：从新位置导入并 re-export
- [ ] 5.9 更新 `websocket_service.py` 和相关测试的导入
- [ ] 5.10 运行 `pytest` 确认无回归

### 5C: Phase 5 验收关口

- [ ] 5.11 运行 `python run.py --local` 确认后端启动正常
- [ ] 5.12 使用 grep 确认没有剩余的旧导入路径（除了 re-export 文件本身）
- [ ] 5.13 运行完整测试套件确认零失败

## 6. Phase 6: Router 拆分（D7，必须在 Phase 5 完成后执行）

### 6A: hr_management.py 拆分

- [ ] 6.1 分析 `hr_management.py` 的 49 个端点，识别废弃端点候选，按子域分组
- [ ] 6.2 创建 `backend/routers/hr_department.py`：部门管理相关端点
- [ ] 6.3 创建 `backend/routers/hr_income.py`：收入/薪资相关端点
- [ ] 6.4 创建 `backend/routers/hr_attendance.py`：考勤相关端点
- [ ] 6.5 创建 `backend/routers/hr_performance.py`：绩效相关端点
- [ ] 6.6 将 `hr_management.py` 改为 re-export 中转文件（带 DEPRECATED 注释）

### 6B: field_mapping.py 拆分

- [ ] 6.7 分析 `field_mapping.py` 的 30 个端点，按子域分组
- [ ] 6.8 创建 `backend/routers/field_mapping_config.py`
- [ ] 6.9 创建 `backend/routers/field_mapping_dictionary.py`
- [ ] 6.10 创建 `backend/routers/field_mapping_execution.py`
- [ ] 6.11 将 `field_mapping.py` 改为 re-export 中转文件

### 6C: collection.py 拆分

- [ ] 6.12 分析 `collection.py` 的 22 个端点，按子域分组
- [ ] 6.13 创建 `backend/routers/collection_tasks.py`
- [ ] 6.14 创建 `backend/routers/collection_config.py`
- [ ] 6.15 创建 `backend/routers/collection_status.py`
- [ ] 6.16 将 `collection.py` 改为 re-export 中转文件（特别注意 `_execute_collection_task_background` 的归属）

### 6D: users.py 拆分

- [ ] 6.17 分析 `users.py` 的 20 个端点，按子域分组
- [ ] 6.18 创建 `backend/routers/users_crud.py`
- [ ] 6.19 创建 `backend/routers/users_roles.py`
- [ ] 6.20 创建 `backend/routers/users_preferences.py`
- [ ] 6.21 将 `users.py` 改为 re-export 中转文件

### 6E: 路由注册更新

- [ ] 6.22 更新 `backend/main.py`：注册所有新拆分的 router（保持原 prefix）
- [ ] 6.23 记录拆分前 Swagger 的端点总数（用于拆分后对比验证）

### 6F: Phase 6 验收关口

- [ ] 6.24 验证 Swagger 端点数量与拆分前一致
- [ ] 6.25 验证所有 API URL 保持不变
- [ ] 6.26 运行完整测试套件确认零失败
- [ ] 6.27 运行 `python run.py --local` 手动验证核心流程

## 7. Phase 7: Service 依赖注入改造

- [ ] 7.1 在 `backend/services/base_service.py` 中创建标准的 `Depends()` 工厂函数模板
- [ ] 7.2 选择 1-2 个简单 router 作为试点，将直接 Service 实例化改为 `Depends()` 注入
- [ ] 7.3 为试点 router 编写测试，验证依赖注入的 mock 能力
- [ ] 7.4 将依赖注入迁移指南写入 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`

### 7A: Phase 7 验收关口

- [ ] 7.5 运行 `pytest` 确认零失败

## 8. 最终验证

- [ ] 8.1 运行完整测试套件 `pytest`，确认零失败
- [ ] 8.2 运行架构验证 `python scripts/verify_architecture_ssot.py`，确认 100% 合规
- [ ] 8.3 运行代码质量检查 `ruff check .`，确认无新增 lint 错误
- [ ] 8.4 运行 `python scripts/verify_rules_completeness.py`，确认零容忍规则无遗漏
- [ ] 8.5 验证 `.cursorrules` 最终行数 <= 300 行
- [ ] 8.6 验证 `docs/DEVELOPMENT_RULES/` 至少包含 7 个核心主题文件 + 1 个 README，且 README 已覆盖所有扩展文件
- [ ] 8.7 验证 `backend/routers/` 无内联 Pydantic 模型（grep 验证零结果）
- [ ] 8.8 验证 `backend/routers/` 中每个拆分后子文件 <= 15 个端点
- [ ] 8.9 验证代码中无 `datetime.utcnow()` 调用
- [ ] 8.10 验证 `modules/core/exceptions.py` 的 `error_code` 类型已统一
- [ ] 8.11 验证 `schema.py` 中所有 DateTime 列为 `DateTime(timezone=True)`
- [ ] 8.12 验证 `backend/dependencies/auth.py` 存在且被正确使用
- [ ] 8.13 运行 `python run.py --local`，完成完整的端到端冒烟测试
