## Context

西虹ERP项目经过多个版本迭代和多 Agent 协同开发，积累了以下技术债务：

**规则层面**：`.cursorrules`（~1200行）是所有 Agent 的必读文件，包含大量星级评分标记（如 `[*****]`）、历史事故叙述、重复声明。`CLAUDE.md` 和 `docs/DEVELOPMENT_RULES/`（18个文件，~5300行）存在大量交叉重复，Agent 无法判断权威来源。

**代码层面**：规则声明了 Contract-First 但 router 中有 ~97 个内联 Pydantic 模型；声明了测试金字塔但无 `conftest.py`；~40 个 Service 类无统一基类，每个都从零实现 CRUD；分页逻辑在各 router 中手动重复实现。

**企业级缺失**：作为面向 50~100 人同时使用的现代化 ERP 系统，缺乏事务管理标准、并发控制（乐观锁）、缓存策略标准、审计日志集成等企业级基础设施。此外，`modules/core/exceptions.py`（ERPException，error_code 为 str）与 `backend/utils/error_codes.py`（ErrorCode，IntEnum）两套错误码类型不统一，存在 SSOT 冲突风险。

**当前技术栈**：FastAPI + SQLAlchemy 2.0 + PostgreSQL 15+（多schema: public/b_class/a_class/c_class/core/finance）+ Vue 3，已有 `backend/schemas/common.py` 定义了 `PaginatedResponse` 模型但无配套查询工具，已有 `backend/utils/api_response.py` 提供统一响应函数（`error_response()` 默认 status_code=200）。

## Goals / Non-Goals

**Goals:**

1. `.cursorrules` 行数降至 300 行以内，仅含零容忍规则和架构约束，Agent token 消耗减少 75%+
2. 消除规则文件间的交叉重复，建立清晰的三层权威层级（L1快速入口 / L2零容忍规则 / L3详细参考）
3. 创建可复用的企业级代码基础设施（AsyncCRUDService 基类、分页工具、统一异常体系、事务管理、并发控制、缓存标准、测试 fixture）
4. 将 router 中的 ~97 个内联 Pydantic 模型全部迁移至 `backend/schemas/`
5. 建立可执行的代码模式文档 `CODE_PATTERNS.md`，使 Agent 能复制模板而非从零编写
6. 统一异常体系——消除 `ERPException`（str error_code）与 `ErrorCode`（IntEnum）的类型冲突

**Non-Goals:**

1. 不改变任何面向用户的 API 行为（HTTP 状态码变更采用渐进式，旧端点不受影响）
2. 不重写现有 Service 的业务逻辑，仅提供可选基类（新 Service 强制使用）
3. 不修改前端代码（前端 API 层组织和 Axios 拦截器适配作为后续独立变更）
4. 不引入 API 版本化机制（记录为后续规划，本次不实施）
5. 不强制现有 ORM 模型添加 `version` 字段（仅在新表中强制，旧表按需添加）

## Decisions

### D1: 规则文件层级体系

**决策**：建立三层规则体系，每层有明确职责，禁止交叉重复。

| 层级 | 文件 | 职责 | 目标行数 |
|------|------|------|----------|
| L1 快速入口 | `CLAUDE.md` | 命令速查 + 架构一屏概览 + 文档导航 | ~130行 |
| L2 开发规范 | `.cursorrules` | 零容忍规则 + 架构约束 + 指向 L3 的指针 | ~300行 |
| L3 详细参考 | `docs/DEVELOPMENT_RULES/*.md` | 按主题的深度参考 + 代码模式模板 | 7个文件 |

**关键变更（相比原方案）**：代码模式模板从 `.cursorrules` 移至 `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`。`.cursorrules` 仅添加一行指引："编写新 Service/Router/Schema 前，先查阅 `CODE_PATTERNS.md`"。这样避免每次 Agent 对话都消耗模板 token。

**L2 精简原则**：
- 移除所有星级评分标记（`[*]`, `[***]`, `[*****]` 等，以及 emoji 星号）
- 移除历史事故叙述，只保留结论性规则
- 移除与 `CLAUDE.md` 和 `project.md` 重复的内容
- 用一行指针替代内联代码模板

**L3 合并方案**：18个文件先合并为7个核心主题文件，后续 approved change 可在不破坏核心结构的前提下增加扩展文件：

| 合并后 | 合并来源 |
|--------|----------|
| `API_AND_CONTRACTS.md` | `API_DESIGN.md` + `REVIEW_PROCESS.md` + `CODE_REVIEW_CHECKLIST.md` |
| `DATABASE.md` | `DATABASE_DESIGN.md` + `DATABASE_DESIGN_CHECKLIST.md` + `DATABASE_DESIGN_EXAMPLES.md` + `DATABASE_CHANGE_CHECKLIST.md` + `DATABASE_MIGRATION.md` |
| `TESTING_AND_QUALITY.md` | `TESTING.md` + `CODE_QUALITY.md` |
| `ERROR_AND_LOGGING.md` | `ERROR_HANDLING_AND_LOGGING.md`（精简，移除样板，error_code 说明指向 `error_codes.py` 作为 SSOT） |
| `SECURITY_AND_DEPLOYMENT.md` | `SECURITY.md` + `DEPLOYMENT.md` + `MONITORING_AND_OBSERVABILITY.md` |
| `UI_DESIGN.md` | 保留现有（无合并对象） |
| `CODE_PATTERNS.md`（新增） | Service 模板 + Router 模板 + Schema 模板 + conftest 模板 + 事务模式 + 缓存模式 |

移除：`DUPLICATE_AND_HISTORICAL_PROTECTION.md`（内容融入 `.cursorrules` 零容忍规则）、`CURSORRULES_OPTIMIZATION_PLAN.md`（历史文档，完成后删除）、`README.md`（合并后重建索引）。

**精简后验证机制**：创建 `scripts/verify_rules_completeness.py`，自动检查新 `.cursorrules` 是否包含所有零容忍规则关键词，确保精简过程无遗漏。

**替代方案考虑**：
- 方案A：完全删除 `docs/DEVELOPMENT_RULES/`，全部写入 `.cursorrules` → 否决，会使 `.cursorrules` 再次膨胀
- 方案B：保持 18 个文件不变 → 否决，交叉重复无法消除
- 方案C（原方案）：代码模板写入 `.cursorrules`（~500行） → 否决，每次对话消耗过多 token

### D2: 异常体系设计（统一 ERPException + API 层扩展）

**决策**：扩展现有 `modules/core/exceptions.py` 的 `ERPException` 体系，在 `backend/utils/exceptions.py` 创建 API 层专用子类。统一 `error_code` 类型为 `IntEnum`（与 `backend/utils/error_codes.py` 对齐）。

**异常层级**：

```
ERPException (modules/core/exceptions.py, error_code: IntEnum)
├── ValidationError          (已有, 保留)
├── ConfigurationError       (已有, 保留)
├── ConnectionError          (已有, 保留)
├── ...                      (已有9个子类, 全部保留)
│
└── [API层扩展] (backend/utils/exceptions.py)
    ├── NotFoundError          → HTTP 404
    ├── BusinessValidationError → HTTP 422
    ├── PermissionDeniedError  → HTTP 403
    ├── ConflictError          → HTTP 409
    └── ExternalServiceError   → HTTP 502
```

**SSOT 统一要点**：
- `ERPException.error_code` 类型从 `str` 改为 `Optional[IntEnum]`（向后兼容：接受 str 但推荐 IntEnum）
- API 层异常的 `error_code` 强制使用 `ErrorCode`（IntEnum）
- `ERROR_AND_LOGGING.md` 中的错误码说明改为"以 `backend/utils/error_codes.py` 为 SSOT"，不再重复列举码值

**关键决策：HTTP 状态码渐进迁移**
- 当前 `error_response()` 默认 `status_code=200`，350+ 端点广泛使用
- 新增 `error_response_v2()` 函数，根据异常类型自动映射语义化 HTTP 状态码
- **新代码**：使用异常体系 + `error_response_v2()`（语义状态码）
- **旧代码**：保持不变（HTTP 200 + success:false），不做强制迁移
- 前端 Axios 拦截器已同时处理两种模式（200+success:false 和 4xx/5xx），无需立即修改
- 当所有端点迁移完成后，废弃 `error_response()`（后续独立变更）

**替代方案**：
- 一次性改全部 HTTP 状态码 → 否决，350+ 端点破坏性变更太大
- 每个 router 手动 try-except → 否决，当前状态，97% 重复代码
- 创建独立的 `AppException` 体系 → 否决，违反 SSOT，与 `ERPException` 形成双维护

### D3: AsyncCRUDService 基类设计（async-first）

**决策**：创建 `backend/services/base_service.py`，仅提供异步版本。遵循项目"所有路由函数必须使用 `get_async_db()`"的强制规则，不提供同步 `CRUDService`。

```python
class AsyncCRUDService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, id: int) -> Optional[ModelType]: ...
    async def get_multi(self, *, skip: int = 0, limit: int = 20) -> List[ModelType]: ...
    async def create(self, *, obj_in: CreateSchemaType) -> ModelType: ...
    async def update(self, *, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType: ...
    async def remove(self, *, id: int) -> Optional[ModelType]: ...
```

**企业级扩展**：
- **审计钩子**：提供 `on_after_create()`、`on_after_update()`、`on_after_delete()` 可选回调方法，子类可覆盖以集成审计日志（复用现有 `audit_service.py`）
- **乐观锁**：`update()` 和 `remove()` 方法内置可选的 `version` 字段检查，版本不匹配时抛出 `OptimisticLockError`
- **软删除**：提供可选的 `soft_delete()` 方法，标记 `deleted_at` 字段而非物理删除。启用软删除后，`get()` 和 `get_multi()` 自动添加 `WHERE deleted_at IS NULL` 过滤条件；如需查询已删除记录，使用 `get(id, include_deleted=True)`

**设计原则**：
- 基类仅提供最基础的 CRUD，不假设业务逻辑
- 业务 Service 通过继承覆盖特定方法
- 现有 ~40 个 Service 不强制迁移，新 Service 必须继承基类
- `db: AsyncSession` 在构造函数中注入，通过 `Depends()` 工厂函数创建

**为什么不提供同步版本**：
- 项目规则明确"新代码禁止使用 `get_db()`"
- 同步版本只在非 API 场景（脚本/迁移）有意义，这些场景不需要 CRUD 基类
- 避免开发者误用同步版本违反 async-first 规则

**替代方案**：
- 同时提供同步+异步版本 → 否决，与项目 async-first 强制规则矛盾
- 使用 SQLModel 替代分离的 ORM + Pydantic → 否决，改动范围过大
- 使用 FastAPI-CRUD-Router 等第三方库 → 否决，灵活性不足

### D4: 分页工具设计（与现有 api_response 对齐）

**决策**：创建 `backend/utils/pagination.py`，仅提供异步版本，返回结果可直接传入现有 `pagination_response()` 函数。

```python
async def async_paginate_query(
    query: Select,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
) -> tuple[list, int]:
    """
    返回 (data_list, total_count)。
    调用方可直接传入 pagination_response(data, page, page_size, total)。
    """
```

**关键特性**：
- 自动 clamp `page_size` 到 `max_page_size`
- 使用 `SELECT COUNT(*)` 子查询（而非 `.count()` 方法）避免性能问题
- 返回值为 `(list, int)` 元组，与现有 `pagination_response()` 参数对齐
- 不重复创建响应格式函数，复用 `api_response.pagination_response()`

**与现有代码的关系**：`backend/utils/api_response.py` 的 `pagination_response()` 负责格式化响应，`pagination.py` 的 `async_paginate_query()` 负责查询和计数——职责分离，不重叠。

### D5: 测试基础设施设计（双模式）

**决策**：创建 `backend/tests/conftest.py`，提供双模式数据库 fixture。

**核心 fixture**：
- `sqlite_session`: SQLite in-memory 会话（快速单元测试，无需外部依赖）
- `pg_session`: PostgreSQL 容器会话（集成测试，CI 必跑），使用 `testcontainers[postgres]`
- `async_client`: 覆盖 `get_async_db` 依赖的异步 TestClient 实例
- `auth_headers`: Mock JWT 认证头（避免测试依赖真实登录）
- `sample_user`: 标准测试用户数据

**双模式策略**：
- **SQLite（默认，本地快速反馈）**：适用于不依赖 PostgreSQL 特性的纯业务逻辑测试
- **PostgreSQL（CI/集成测试）**：适用于涉及多 schema（b_class/a_class/c_class）、search_path、分区表等 PG 特性的测试
- 通过 `pytest.mark.pg_only` 标记需要 PostgreSQL 的测试
- CI 流程中两种模式都运行

**数据隔离**：
- 通过 `@pytest.fixture(scope="session")` 创建表结构
- 通过 `@pytest.fixture(scope="function")` + 事务回滚隔离每个测试的数据

**替代方案**：
- 只用 SQLite → 否决，无法覆盖项目的 PostgreSQL 特有功能（多schema等）
- 只用 PostgreSQL 容器 → 否决，本地开发反馈太慢
- 使用共享远程测试数据库 → 否决，测试不可重复，状态污染

### D6: Contract-First 迁移策略

**决策**：分批将 router 中的内联 Pydantic 模型迁移至 `backend/schemas/`。

**迁移优先级**（按内联模型数量排序）：
1. P0: `hr_management.py`（37个模型）→ `schemas/hr.py`（已部分开始）
2. P0: `component_versions.py`（12个模型）→ `schemas/component_version.py`
3. P1: `config_management.py`（6个模型）→ `schemas/config.py`
4. P1: `target_management.py`（6个模型）→ `schemas/target.py`
5. P1: `sales_campaign.py`（5个模型）→ `schemas/sales_campaign.py`
6. P2: 其余 16 个 router（各1-4个模型）

**Schema 文件命名规范**：
- 文件名与业务域对应：`schemas/{domain}.py`
- 类命名：`{Domain}{Action}{Type}`，如 `HrIncomeCreateRequest`, `HrIncomeResponse`
- 每个 schema 文件必须在 `schemas/__init__.py` 中注册导出

**兼容性 re-export**：迁移时检查是否有外部模块从 router 导入这些模型。如有，在原 router 文件添加临时 re-export（带 `# DEPRECATED: import from backend.schemas.xxx` 注释），避免导入断裂。后续清理时移除。

### D7: Router 拆分策略（扩展为4个大文件）

**决策**：超过 15 个端点的 4 个 router 文件全部拆分为子域文件。

**拆分计划**：

| 原文件 | 端点数 | 拆分方案 |
|--------|--------|----------|
| `hr_management.py`（49端点） | 49 | `hr_department.py` + `hr_income.py` + `hr_attendance.py` + `hr_performance.py` |
| `field_mapping.py`（30端点） | 30 | `field_mapping_config.py` + `field_mapping_dictionary.py` + `field_mapping_execution.py` |
| `collection.py`（22端点） | 22 | `collection_tasks.py` + `collection_config.py` + `collection_status.py` |
| `users.py`（20端点） | 20 | `users_crud.py` + `users_roles.py` + `users_preferences.py` |

**拆分原则**：
- 每个子文件 <= 15 个端点
- 使用 `APIRouter(prefix=..., tags=[...])` 保持 URL 不变
- 在 `main.py` 中注册新 router，移除旧 router
- 拆分前先识别并清理废弃端点
- **拆分后原文件保留为 re-export 中转**（见 D14），确保外部导入不断裂

**前置条件**：必须先完成 D14（共享依赖提取），否则拆分会导致 23+ 处跨 router 导入断裂

### D8: datetime 标准化（含列类型审计，强制分步执行）

**决策**：
- Python 代码：`datetime.utcnow()` → `datetime.now(timezone.utc)`（约150+处）
- ORM 层：`default=datetime.utcnow` → `server_default=func.now()`
- 审计 `modules/core/db/schema.py` 中全部 193 个 `DateTime` 列（当前 0 个使用 `timezone=True`），统一为 `DateTime(timezone=True)`（timezone-aware），创建 Alembic 迁移修正
- 理由：`datetime.utcnow()` 在 Python 3.12 中已被 deprecated；naive/aware datetime 混用会导致比较和查询问题

**强制执行顺序（不可颠倒）**：

`datetime.utcnow()` 返回 naive datetime（无时区），`datetime.now(timezone.utc)` 返回 aware datetime（带时区）。如果数据库 `DateTime` 列不带时区，ORM 返回 naive datetime，与 aware datetime 比较会抛出 `TypeError: can't compare offset-naive and offset-aware datetimes`。因此必须严格按以下顺序执行：

1. **Step 1**：审计 `schema.py` 中所有 `DateTime` 列，列出哪些不带 `timezone=True`
2. **Step 2**：创建 Alembic 迁移，将数据库列统一为 `TIMESTAMP WITH TIME ZONE`（PostgreSQL 支持无损转换）
3. **Step 3**：在**数据库迁移完成并验证后**，才全局替换 `datetime.utcnow()` → `datetime.now(timezone.utc)`
4. **Step 4**：替换 ORM `default=datetime.utcnow` → `server_default=func.now()`

**注意**：Step 2→3 之间建议在低峰期执行，或有短暂的维护窗口。Step 2 涉及 193 个 DateTime 列的类型变更。Step 3 涉及约 150+ 处代码修改，必须一次性完成（不能只改一半，否则同一张表的不同查询会出现 naive/aware 混用）

### D9: 事务管理标准

**决策**：在 `backend/services/base_service.py` 中提供事务管理工具。

**与 `get_async_db()` 的协调（关键设计点）**：

当前 `get_async_db()` 已在请求级别实现自动 commit/rollback（请求成功则 commit，异常则 rollback）。`@transactional` 不能与之冲突，因此采用 **savepoint 嵌套策略**：

- `@transactional` 使用 `begin_nested()`（PostgreSQL savepoint），而非顶层 `begin()`
- 方法正常返回时释放 savepoint（变更保留在外层事务中），方法异常时回滚 savepoint（仅回滚本方法的变更）
- 最终的 commit 仍由 `get_async_db()` 在请求结束时统一执行
- 这样保证：同一请求内多个 `@transactional` 方法互相隔离，一个失败不影响其他已完成的方法

**嵌套调用处理**：
- 一个 `@transactional` 方法调用另一个 `@transactional` 方法时，内层方法创建更深一级的 savepoint
- SQLAlchemy 的 `begin_nested()` 原生支持多级嵌套

**提供两种模式**：

1. **装饰器模式**（简单场景）：
```python
@transactional
async def transfer_funds(self, from_id: int, to_id: int, amount: Decimal):
    await self.debit(from_id, amount)
    await self.credit(to_id, amount)
```

2. **上下文管理器模式**（需要细粒度控制的复杂场景）：
```python
async with self.db.begin_nested() as savepoint:
    await self.create_order(order_data)
    try:
        await self.reserve_inventory(items)
    except InsufficientStockError:
        await savepoint.rollback()
        # 部分回滚，订单仍然创建但标记为待补货
```

**设计原则**：
- 事务边界在 Service 层，而非 Router 层
- `@transactional` 使用 `begin_nested()`（savepoint），不调用顶层 `begin()`/`commit()`
- 最终 commit 由 `get_async_db()` 在请求结束时统一执行
- 嵌套的 `@transactional` 调用创建多级 savepoint，互不干扰
- Router 层不处理事务，仅调用 Service 方法

### D10: 并发控制策略

**决策**：定义乐观锁标准，在 `AsyncCRUDService` 中集成。

**乐观锁实现**：
- 新表在 `schema.py` 中添加 `version = Column(Integer, nullable=False, default=1)` 字段
- `AsyncCRUDService.update()` 自动检查 version：`WHERE id = :id AND version = :expected_version`
- 版本不匹配时抛出 `OptimisticLockError`（复用 `TaskService` 中已有的异常定义）
- 更新成功时自动 `version += 1`

**适用规则**：
- 新建的需要并发写入保护的表：强制添加 `version` 字段
- 现有表：按需添加，不强制迁移
- 纯读取或低并发表（如配置表）：无需 version 字段

**补充策略**（不在本次实现，记录为模式）：
- 幂等性：POST 请求建议携带 `Idempotency-Key` header，Service 层检查去重
- 连接池：当前 `pool_size` 和 `max_overflow` 配置已在 `database.py` 中，50-100并发下建议 `pool_size=20, max_overflow=30`（记录在 `CODE_PATTERNS.md`）

### D11: 缓存策略标准

**决策**：定义标准缓存模式，复用现有 `CacheService`，记录在 `CODE_PATTERNS.md` 中。

**缓存分层**：

| 层级 | 场景 | TTL | 失效策略 |
|------|------|-----|----------|
| L1 进程内 | 配置项、枚举值、权限树 | 300s | 写入时主动清除 |
| L2 Redis | 用户会话、频繁查询的列表 | 600s | 写入时主动清除 + TTL 兜底 |
| 不缓存 | 交易数据、审计日志 | - | - |

**标准模式**（记录在 CODE_PATTERNS.md，不在本次创建新代码）：
```python
from backend.services.cache_service import CacheService

class MyService(AsyncCRUDService[...]):
    async def get_config(self, key: str) -> dict:
        cache_key = f"config:{key}"
        cached = await CacheService.get(cache_key)
        if cached:
            return cached
        result = await self._fetch_from_db(key)
        await CacheService.set(cache_key, result, ttl=300)
        return result

    async def update_config(self, key: str, data: dict):
        await self._update_in_db(key, data)
        await CacheService.delete(f"config:{key}")
```

**本次实现范围**：仅在 `CODE_PATTERNS.md` 中记录标准模式。缓存装饰器（`@cached`）作为后续独立变更。

### D12: 审计日志集成

**决策**：在 `AsyncCRUDService` 中通过可选的 hook 方法集成审计日志。

**实现方式**：
```python
class AsyncCRUDService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    enable_audit: bool = False  # 子类可覆盖

    async def create(self, *, obj_in: CreateSchemaType) -> ModelType:
        result = await self._do_create(obj_in)
        if self.enable_audit:
            await self.on_after_create(result)
        return result

    async def on_after_create(self, obj: ModelType) -> None:
        """子类覆盖以记录审计日志。默认空实现。"""
        pass
```

**与现有代码的关系**：`backend/services/audit_service.py` 已存在，审计 hook 调用 `AuditService` 的方法。不创建新的审计机制。

### D13: API 版本化路线图（仅记录，本次不实施）

**决策**：本次不引入 API 版本化。记录为后续规划。

**推荐方案**（供后续变更参考）：
- 使用 URL 前缀版本化：`/api/v1/`, `/api/v2/`
- 在 HTTP 状态码完全迁移后（所有端点使用语义化状态码），引入 v2 版本
- v1 版本保持向后兼容，设定 6 个月废弃窗口

**记录在 Open Questions 中**，不创建任何代码或 spec。

### D14: 共享依赖提取（Router 拆分前置条件）

**决策**：在 Router 拆分（D7）之前，必须先将被多个 router 共享的工具函数/类提取到独立模块，避免拆分时导致 23+ 处导入断裂。

**现状分析**（通过代码搜索确认的跨 router 导入关系）：

| 被导入的符号 | 来源文件 | 被多少个文件导入 | 风险等级 |
|-------------|---------|-----------------|---------|
| `get_current_user` | `auth.py` | 14 个 router | 极高 |
| `require_admin` | `users.py` | 9 个 router | 极高 |
| `connection_manager` / `ConnectionManager` | `collection_websocket.py` | 2 个 service + 3 个测试 | 高 |
| `notify_*` 系列函数 | `notifications.py` | `auth.py`, `users.py` 等 | 高 |
| `_execute_collection_task_background` | `collection.py` | `collection_scheduler.py` | 中 |

**提取方案**：

| 当前位置 | 提取到 | 包含内容 |
|---------|--------|---------|
| `auth.py` → `get_current_user` | `backend/dependencies/auth.py` | `get_current_user()`, `get_optional_user()` |
| `users.py` → `require_admin` | `backend/dependencies/auth.py` | `require_admin()`, `require_role()` |
| `collection_websocket.py` → `ConnectionManager` | `backend/services/websocket_manager.py` | `ConnectionManager` 类 |

**不提取的部分**：
- `notifications.py` 的 `notify_*` 函数：该文件本身不会被拆分，保持原位
- Router 特有的业务函数（如 `_execute_collection_task_background`）：随 router 拆分移入对应子文件

**Router 拆分后的 re-export 中转策略**：
拆分后原文件不立即删除，保留为 re-export 中转，避免外部脚本/测试的导入断裂：
```python
# backend/routers/users.py（拆分后保留为中转）
# DEPRECATED: 此文件将在下一版本删除，请从子模块或 backend.dependencies 导入
from backend.routers.users_crud import *       # noqa: F401,F403
from backend.routers.users_roles import *      # noqa: F401,F403
from backend.routers.users_preferences import *  # noqa: F401,F403
from backend.dependencies.auth import require_admin  # noqa: F401 兼容旧导入
```

**执行顺序**：D6（Schema 迁移）→ D14（提取共享依赖）→ D7（Router 拆分）

### D15: 每阶段验收关口（运行时安全保障）

**决策**：每个 Phase 完成后设置强制验收关口，确认系统可用后才进入下一阶段。

**验收关口标准**：

| 验收项 | 方式 | 阻塞条件 |
|--------|------|----------|
| 后端启动 | `python run.py --local` 启动成功 | 启动报错即阻塞 |
| API 可达 | 访问 `/docs` Swagger 页面正常渲染 | 页面 404 或路由缺失即阻塞 |
| 核心流程 | 登录 → 至少1个列表页 → 创建/查询操作 | 任何500错误即阻塞 |
| 自动测试 | `pytest backend/tests/` 通过 | 新增失败即阻塞 |
| 架构合规 | `python scripts/verify_architecture_ssot.py` 100% | 低于100%即阻塞 |

**特别关注的高风险阶段**：
- datetime 替换后（Phase 3）：必须验证含时间比较的关键流程（采集任务调度、审计日志查询、Token 过期检查）
- Router 拆分后（Phase 6）：必须验证 Swagger 文档中端点数量与拆分前一致

## Risks / Trade-offs

| 风险 | 影响 | 严重度 | 缓解措施 |
|------|------|--------|----------|
| **datetime naive/aware 混用** | `TypeError` 导致运行时崩溃 | **致命** | D8 强制分步：先迁移 DB 列 → 再替换代码（不可颠倒） |
| **Router 拆分导致 23+ 处导入断裂** | `ImportError` 导致后端无法启动 | **致命** | D14 前置：先提取共享依赖 → 再拆分；拆分后原文件保留 re-export 中转 |
| Pydantic 模型迁移引入导入路径断裂 | API 运行时错误 | 高 | 分批迁移 + 兼容性 re-export + 每批后运行完整测试套件 |
| `.cursorrules` 精简可能遗漏关键规则 | Agent 开发质量下降 | 中 | 精简前建立规则清单 + `verify_rules_completeness.py` 自动对比 |
| AsyncCRUDService 可能不适合所有业务场景 | 强制使用导致代码扭曲 | 中 | 设计为可选继承，不强制现有 Service 迁移 |
| HTTP 状态码渐进迁移导致新旧模式共存 | 前端需同时处理两种响应模式 | 低 | 前端拦截器已支持两种模式，共存期无额外影响 |
| `ERPException.error_code` 类型变更 | 现有代码使用 str 类型可能中断 | 低 | backend/ 未使用 ERPException（已验证），采用 Union 过渡 |
| testcontainers 引入新 dev 依赖 | CI 构建时间增加 | 低 | SQLite 测试先跑快速反馈，PG 测试并行执行 |
| DateTime(timezone=True) 列类型变更 | 现有数据兼容性 | 低 | PostgreSQL `TIMESTAMP → TIMESTAMPTZ` 支持无损转换 |

## Migration Plan

**执行顺序原则**：零风险优先，高风险操作设置前置条件和验收关口。每个 Phase 完成后必须通过 D15 验收关口。

### Phase 1: 规则重构（零风险，纯文档变更）
1. 建立规则清单 + 创建 `verify_rules_completeness.py`
2. 精简 `.cursorrules`（目标 ~300 行）
3. 更新 `CLAUDE.md`
4. 合并 `docs/DEVELOPMENT_RULES/` 18→7 个文件（含新建 `CODE_PATTERNS.md`）
5. 在 `API_AND_CONTRACTS.md` 中记录 HTTP 状态码渐进迁移策略
6. **验收关口**：`verify_rules_completeness.py` 通过 + `.cursorrules` <= 300 行

### Phase 2: 代码基础设施——新增文件（低风险，不修改已有代码）
7. 统一 `ERPException.error_code` 类型（str → Union[str, IntEnum]）
8. 创建 `backend/utils/exceptions.py`（API 层异常 + `error_response_v2()`）+ 全局异常处理器
9. 创建 `backend/services/base_service.py`（AsyncCRUDService + 审计钩子 + 乐观锁 + 事务装饰器）
10. 创建 `backend/utils/pagination.py`（async_paginate_query）
11. 创建 `backend/tests/conftest.py`（双模式 fixture）
12. **验收关口**：`pytest` 通过 + `python run.py --local` 启动正常 + Swagger 页面正常

### Phase 3: datetime 标准化（高风险，按 D8 强制顺序执行）
13. **Step 1**：审计 `schema.py` 中 DateTime 列，列出非 timezone-aware 列
14. **Step 2**：创建并执行 Alembic 迁移（`DateTime → DateTime(timezone=True)`）
15. **验收关口（中间）**：数据库迁移成功 + 现有代码仍可正常运行（因为 PG 的 TIMESTAMPTZ 向后兼容 naive datetime）
16. **Step 3**：全局替换 `datetime.utcnow()` → `datetime.now(timezone.utc)`（一次性完成，约150+处）
17. **Step 4**：替换 ORM `default=datetime.utcnow` → `server_default=func.now()`
18. **验收关口**：`pytest` 通过 + 手动验证关键时间流程（Token 过期、采集调度、审计日志查询）

### Phase 4: Contract-First Schema 迁移（中风险，分批执行）
19. 迁移 P0 router 的内联模型（hr, component_versions）+ 兼容性 re-export
20. 迁移 P1 router 的内联模型（config, target, sales_campaign）
21. 迁移 P2 router 的内联模型（其余16个router）
22. **验收关口**：`pytest` 通过 + grep 验证零内联模型

### Phase 5: 共享依赖提取（Router 拆分前置条件，D14）
23. 创建 `backend/dependencies/auth.py`，提取 `get_current_user` + `require_admin`
24. 更新所有 23 处导入（14个导入 get_current_user + 9个导入 require_admin）
25. 提取 `ConnectionManager` 到 `backend/services/websocket_manager.py`
26. 更新 `collection_websocket.py`、`websocket_service.py`、相关测试的导入
27. **验收关口**：`pytest` 通过 + `python run.py --local` 启动正常 + grep 确认旧导入路径已全部更新

### Phase 6: Router 拆分（高风险，有前置条件）
28. 拆分 `hr_management.py`（49端点 → 4个子文件）+ 原文件保留 re-export
29. 拆分 `field_mapping.py`（30端点 → 3个子文件）+ 原文件保留 re-export
30. 拆分 `collection.py`（22端点 → 3个子文件）+ 原文件保留 re-export
31. 拆分 `users.py`（20端点 → 3个子文件）+ 原文件保留 re-export
32. 更新 `main.py` 路由注册
33. **验收关口**：Swagger 端点数量与拆分前一致 + 所有 URL 不变 + `pytest` 通过

### Phase 7: Service 依赖注入改造
34. 创建标准 `Depends()` 工厂函数模板
35. 试点 1-2 个 router 改为 `Depends()` 注入
36. 编写迁移指南（嵌入 `CODE_PATTERNS.md`）
37. **验收关口**：`pytest` 通过

**回滚策略**：
- Phase 1: 无需回滚（纯文档）
- Phase 2: 删除新建文件即可
- Phase 3: `alembic downgrade -1` + git revert（需要维护窗口）
- Phase 4-7: git revert（URL 不变，前端不受影响）

## Open Questions

1. ~~前端 Axios 拦截器是否已按 HTTP 状态码分类处理？~~ **已确认**：前端拦截器同时处理 200+success:false 和 4xx/5xx 两种模式，渐进迁移无前端阻塞
2. 现有 ~40 个 Service 是否有可以优先迁移到 AsyncCRUDService 的候选？建议从新建的 Service 开始强制使用
3. `hr_management.py` 的 49 个端点是否有废弃候选？拆分前可以先清理
4. `field_mapping_dictionary.py`（13端点）是否应一并纳入拆分范围？当前接近 15 端点阈值
5. **API 版本化**：当 HTTP 状态码完全迁移后，是否需要引入 `/api/v2/` 前缀？建议作为独立提案评估
6. **前端代码模式标准化**：前端同样存在 API 调用/Store/组件组织模式不统一的问题，建议作为后续独立提案规划其优先级和范围
7. 连接池参数（`pool_size=20, max_overflow=30`）是否足够支撑 100 并发用户？需要负载测试验证
