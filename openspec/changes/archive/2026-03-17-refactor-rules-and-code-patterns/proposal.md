## Why

当前开发规则体系存在三个根本问题：（1）`.cursorrules` 超过 1200 行，包含大量重复内容、星级评分噪声和历史补丁，Agent 每次对话消耗约 4000 token 仅读取规则；（2）规则与代码实现脱节——声明了 Contract-First 原则，但 router 文件中存在 ~97 个内联 Pydantic 模型，声明了测试金字塔但缺少 `conftest.py` 共享 fixture，声明了三层架构但 ~40 个 Service 类无统一基类和标准模式；（3）`docs/DEVELOPMENT_RULES/` 共 18 个细化规则文件与 `.cursorrules` 大量交叉重复，Agent 无法判断权威来源。此外，作为面向 50~100 人同时使用的现代化 ERP 系统，缺乏事务管理、并发控制、缓存策略、审计集成等企业级基础设施标准。这些问题导致 Agent 开发效率低下、同类错误反复出现、代码风格不一致。

本次变更从基础层面重构规则体系并补齐代码基础设施，使规则从"文档声明"变为"代码可执行"，同时建立企业级 ERP 所需的并发安全、事务管理和可观测性标准。

## What Changes

### 规则体系重构

- **精简 `.cursorrules`**：从 ~1200 行压缩至 ~300 行，只保留零容忍规则和架构约束，代码模板移至 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`（按需查阅，不消耗每次对话 token）
- **重新定位 `CLAUDE.md`**：作为纯粹的快速入口（命令速查、架构一屏概览），消除与 `.cursorrules` 的重复
- **合并 `docs/DEVELOPMENT_RULES/`**：18 个文件先合并为 7 个核心聚焦文件（API 设计、数据库、测试、安全+部署、错误处理、UI 设计、代码模式），消除交叉重复，并为后续 approved change 预留扩展文件空间
- **渐进式 HTTP 状态码修正**：新异常体系支持语义化 HTTP 状态码（404/409/422），通过 `error_response_v2()` 渐进迁移，旧端点暂保持 200 包裹模式不变

### 代码基础设施补齐

- **测试基础设施**：创建 `backend/tests/conftest.py`，提供双模式 fixture——SQLite in-memory（快速单元测试）和 PostgreSQL testcontainers（集成测试，CI 必跑）
- **AsyncCRUDService 基类**：创建 `backend/services/base_service.py`，仅提供异步版本 `AsyncCRUDService[Model, CreateSchema, UpdateSchema]`（遵循项目 async-first 强制规则），集成可选的审计日志钩子、乐观锁检查和 savepoint 级事务装饰器
- **统一分页**：创建 `backend/utils/pagination.py`，提供 `async_paginate_query()` 工具函数，返回结果与现有 `api_response.pagination_response()` 对齐
- **统一异常体系**：扩展现有 `modules/core/exceptions.py` 的 `ERPException`，在 `backend/utils/exceptions.py` 创建 API 层异常子类，统一 `error_code` 为 `IntEnum` 类型，Router 层全局捕获
- **事务管理标准**：在 base_service 中提供 `@transactional` 装饰器和 savepoint 支持
- **并发控制**：定义乐观锁标准（ORM `version` 字段 + `OptimisticLockError`），在 base_service 的 update/remove 中集成
- **缓存策略标准**：定义标准缓存装饰器模式（`@cached(ttl=300)`），复用现有 `CacheService`
- **datetime 标准化**：全局替换 `datetime.utcnow()` 为 `datetime.now(timezone.utc)`（约 150+ 处），审计并统一 `schema.py` 中 193 个 `DateTime` 列为 `DateTime(timezone=True)`，ORM 层使用 `server_default=func.now()`

### 架构合规性修复

- **Contract-First 执行**：将 router 文件中的 ~97 个内联 Pydantic 模型迁移至 `backend/schemas/` 按业务域组织，迁移时添加兼容性 re-export 避免外部导入断裂
- **共享依赖提取**（Router 拆分前置条件）：将 `get_current_user`（被14个router导入）和 `require_admin`（被9个router导入）提取到 `backend/dependencies/auth.py`；将 `ConnectionManager` 提取到独立 service 模块——避免 Router 拆分时 23+ 处导入断裂
- **Router 拆分**：将超过 15 个端点的 4 个 router 文件全部拆分——`hr_management.py`（49端点）、`field_mapping.py`（30端点）、`collection.py`（22端点）、`users.py`（20端点）。拆分后原文件保留为 re-export 中转，确保外部脚本/测试不断裂
- **Service 依赖注入**：router 中的 Service 实例化改为通过 FastAPI `Depends()` 注入

## Capabilities

### New Capabilities

- `backend-code-patterns`: 后端代码标准模式——定义 AsyncCRUDService 基类（含审计钩子和乐观锁）、分页工具、事务管理、缓存标准、依赖注入、datetime 标准的规范和实现要求
- `exception-contract`: 异常契约——统一 `ERPException` → API 层异常的层级关系、error_code 类型标准化（IntEnum）、全局异常处理器与前端的契约
- `rule-hierarchy`: 规则层级体系——定义 L1/L2/L3 三层规则文件的职责边界、内容标准和维护规则

### Modified Capabilities

_(无现有 spec 的行为需求发生变更。本次变更聚焦于内部代码质量和开发效率提升，不改变任何面向用户的功能行为。)_

## Impact

- **受影响的规则文件**: `.cursorrules`, `CLAUDE.md`, `docs/DEVELOPMENT_RULES/` 全部 18 个文件
- **受影响的代码**: `backend/routers/*.py`（全部 router 的 Pydantic 模型迁移 + 4 个大文件拆分）, `backend/services/*.py`（~40 个 Service 类的基类适配）, `backend/schemas/`（新增按域组织的 schema 文件）, `modules/core/exceptions.py`（error_code 类型统一为 IntEnum）, `modules/core/db/schema.py`（DateTime 列审计 + 可选 version 字段）, `backend/utils/api_response.py`（新增 `error_response_v2()`）
- **新增代码**: `backend/tests/conftest.py`, `backend/services/base_service.py`, `backend/utils/pagination.py`, `backend/utils/exceptions.py`, `backend/dependencies/auth.py`, `backend/services/websocket_manager.py`, `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`, `specs/rule-hierarchy/spec.md`, `specs/exception-contract/spec.md`
- **依赖变更**: 新增 `testcontainers[postgres]`（仅 dev 依赖，用于集成测试）
- **执行顺序约束（关键）**：Phase 1 规则文档（零风险）→ Phase 2 新增文件（低风险）→ Phase 3 datetime（高风险，DB迁移必须先于代码替换）→ Phase 4 Schema 迁移 → Phase 5 共享依赖提取 → Phase 6 Router 拆分（高风险，必须在 Phase 5 后执行）→ Phase 7 DI 改造。每阶段设验收关口，不通过不进入下一阶段
- **致命风险**: (1) datetime 替换前若 DB 列（193个 DateTime 列）未迁移为 timezone-aware，会导致 naive/aware 比较 TypeError 崩溃；(2) Router 拆分前若未提取共享依赖（`get_current_user` 被14个文件导入），会导致 ImportError 后端无法启动
- **一般风险**: Schema 迁移需分批 + 兼容性 re-export；规则精简需 `verify_rules_completeness.py` 自动验证
