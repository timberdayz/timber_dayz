# Project Context

## Purpose

西虹ERP系统是一个**现代化企业级跨境电商ERP系统**，对标SAP/Oracle ERP标准，提供完整的数据采集、字段映射、产品管理、财务管理和数据看板功能。

**核心目标**：
- 多平台数据采集（Shopee/TikTok/Amazon/妙手ERP等）
- 智能字段映射与自动入库（7个数据域支持）
- 企业级财务管理（CNY本位币、Universal Journal、移动加权平均成本）
- 实时数据看板（销售/库存/财务/健康度监控）
- 三层数据架构（Raw/Fact/MV）+ 三层数据分类（A类/B类/C类）

**当前版本**: v4.12.2  
**架构标准**: Single Source of Truth (SSOT) + 企业级ERP标准  
**状态**: ✅ 生产就绪

## Tech Stack

### 后端
- **Python**: 3.9+ (推荐3.11或3.13)
- **Web框架**: FastAPI (RESTful API)
- **数据库**: PostgreSQL 15+ (主数据库，企业级)
- **ORM**: SQLAlchemy 2.0+
- **数据库迁移**: Alembic
- **异步任务**: Celery + Redis
- **定时任务**: APScheduler
- **数据采集**: Playwright (替代Selenium，反检测能力强)
- **数据处理**: pandas, numpy, openpyxl, xlrd
- **日志**: loguru
- **配置管理**: PyYAML, python-dotenv
- **安全**: cryptography, PyJWT, passlib

### 前端
- **框架**: Vue.js 3 (Composition API)
- **UI组件库**: Element Plus (企业级组件库)
- **状态管理**: Pinia (Vuex的现代替代)
- **路由**: Vue Router 4
- **构建工具**: Vite (快速构建和热重载)
- **HTTP客户端**: Axios
- **图表库**: ECharts + Chart.js (专业数据可视化)
- **TypeScript**: 支持（重要组件使用）

### 基础设施
- **容器化**: Docker + Docker Compose
- **数据库**: PostgreSQL 15+ (Docker容器)
- **缓存**: Redis (可选)
- **反向代理**: Nginx (生产环境)
- **监控**: Prometheus + Grafana (可选)

### 开发工具
- **代码格式化**: Black (行长度88字符), Ruff (代码检查)
- **类型检查**: mypy (Python), vue-tsc (Vue)
- **测试**: pytest (Python), Jest (前端，可选)

## Project Conventions

### Code Style

#### Python代码规范
- **缩进**: 4个空格，严格禁用Tab键
- **行长度**: 88字符以内（Black标准）
- **命名规范**:
  - 变量和函数: `snake_case` (如: `sales_data`, `process_file`)
  - 类名: `PascalCase` (如: `PathManager`, `SalesAnalytics`)
  - 常量: 全大写加下划线 (如: `MAX_RETRY_COUNT`, `DEFAULT_PORT`)
  - 模块名: 小写加下划线 (如: `data_processor`, `sales_analytics`)
- **导入顺序** (PEP 8):
  1. 标准库导入
  2. 第三方库导入
  3. 本地应用/库导入
  每组之间用空行分隔
- **代码风格**:
  - 多行集合末尾添加逗号
  - 使用类型注解 (Type Hints)
  - 添加详细的docstring文档 (Google风格)
  - 使用有意义的变量名，避免单字母变量（除了循环索引）
- **字符串格式化**: 优先使用f-string

#### JavaScript/Vue代码规范
- **组件命名**: PascalCase (如: `DataDashboard.vue`)
- **Props验证**: 使用PropTypes或TypeScript接口验证
- **事件命名**: kebab-case (如: `@update-data`)
- **Composition API**: 优先使用Composition API而非Options API
- **TypeScript支持**: 重要组件使用TypeScript增强类型安全

#### 文件编码规范（Windows平台特定）
- **终端输出**: 禁止使用Emoji（会导致UnicodeEncodeError）
- **使用ASCII符号**: 如`[OK]`, `[ERROR]`, `*`, `+`, `-`等
- **文件编码**: Python文件使用UTF-8 with BOM或添加`# -*- coding: utf-8 -*-`
- **安全打印**: 所有终端输出必须使用try-except处理UnicodeEncodeError

### Architecture Patterns

#### 核心架构原则
- **Single Source of Truth (SSOT)**: 每个功能只在一处定义，其他地方只导入，不重复定义
- **三层架构**:
  - **Layer 1: Core Infrastructure** (`modules/core/`) - 基础设施层，提供全局共享的基础设施
  - **Layer 2: Backend API** (`backend/`) - API层，提供RESTful API
  - **Layer 3: Frontend** (`frontend/`) - 前端层，用户界面
- **混合架构** (v4.0.0):
  - 统一启动脚本: `run.py` (推荐)
  - 统一后端API: `backend/main.py` (唯一的FastAPI应用入口)
  - 统一前端界面: `frontend/` (唯一的Vue.js 3前端)
  - 业务模块层: `modules/apps/` (插件化业务模块)
  - 平台适配器: `modules/platforms/` (数据采集平台适配器)

#### 数据架构
- **三层数据分类**:
  - **A类**: 用户配置数据（销售战役、月度目标、绩效权重）
  - **B类**: 业务数据（订单、产品、库存、流量，Excel采集+字段映射）
  - **C类**: 计算数据（达成率、健康度评分、排名预警，系统自动计算）
- **三层数据存储**:
  - **Raw层**: 原始数据（catalog_files表）
  - **Fact层**: 事实表（fact_orders, fact_order_items等）
  - **MV层**: 物化视图（18个物化视图，OLAP优化）

#### 数据库设计规范
- **表设计原则**:
  - 所有表必须有主键（Primary Key）
  - 外键必须明确声明（Foreign Key Constraints）
  - 字段类型必须精确（避免VARCHAR(255)滥用）
  - 必须添加created_at/updated_at时间戳（审计字段）
  - 软删除支持：重要表添加deleted_at字段
- **索引设计原则**:
  - 唯一索引：业务唯一性约束
  - 联合索引：查询WHERE条件顺序（最左前缀原则）
  - 部分索引：WHERE条件过滤
  - GIN索引：JSONB字段查询
- **PostgreSQL索引优先原则**: 任何需要查找文件或数据的操作，优先使用PostgreSQL索引查询，禁止递归搜索文件系统

#### 模块边界与契约
- **应用类元数据**: 必须提供类级常量或字典以供注册器读取
- **__init__禁止副作用**: 不得执行I/O、网络、进程启动、持久化写入或全局注册
- **导入阶段零副作用**: 模块顶层只允许常量、类型、函数/类定义
- **依赖方向**: apps → services → core；禁止apps之间互相import
- **配置注入**: 通过config/与依赖注入传入，不在模块导入时读取

#### 严禁双维护（零容忍原则）
- ❌ **禁止重复定义数据库模型**: 唯一定义位置`modules/core/db/schema.py`（53张表）
- ❌ **禁止创建新的Base类**: Base类只能在schema.py定义
- ❌ **禁止重复配置管理类**: 模块配置`modules/core/config.py`，后端配置`backend/utils/config.py`
- ❌ **禁止重复Logger定义**: 唯一Logger工厂`modules/core/logger.py`
- ❌ **禁止拼音字段命名**: 强制使用英文标准命名（如`sales_amount_completed`，禁止`xiao_shou_sgd`）

### Testing Strategy

#### 测试金字塔
- **单元测试**: 70% - 核心业务逻辑、工具函数
- **集成测试**: 20% - API端点、数据库操作
- **E2E测试**: 10% - 关键业务流程

#### 测试覆盖率要求
- **核心模块**: ≥80%（数据库、ETL、API核心逻辑）
- **辅助模块**: ≥50%（工具函数、UI组件）
- **关键业务**: 100%（财务计算、订单处理）

#### 测试工具
- **Python**: pytest, pytest-asyncio (异步测试)
- **前端**: Jest (可选), Vue Test Utils
- **负载测试**: locust (Python)
- **覆盖率工具**: pytest-cov, coverage.py

#### 测试数据管理
- 测试数据隔离
- 数据工厂模式
- 测试后数据清理

#### 性能基准测试
- **关键API**: 响应时间基准测试（P95 < 500ms）
- **数据库查询**: 慢查询基准测试（< 100ms）
- **批量处理**: 吞吐量基准测试（如1000行/秒）

### Git Workflow

#### 分支策略
- **主分支**: `main` (生产环境)
- **开发分支**: `develop` (开发环境)
- **功能分支**: `feature/功能名称` (新功能开发)
- **修复分支**: `fix/问题描述` (Bug修复)
- **发布分支**: `release/版本号` (版本发布)

#### 提交规范
- **提交信息格式**: `<type>(<scope>): <subject>`
- **类型**:
  - `feat`: 新功能
  - `fix`: Bug修复
  - `docs`: 文档更新
  - `style`: 代码格式（不影响功能）
  - `refactor`: 重构
  - `test`: 测试相关
  - `chore`: 构建/工具相关
- **示例**: `feat(field-mapping): 添加Pattern-based Mapping支持`

#### 代码审查
- **Peer Review**: 所有代码修改必须经过至少1人审查
- **审查清单**: 功能正确性、代码规范、性能、安全性
- **自动化检查**: CI自动运行代码检查（通过后才能合并）

## Domain Context

### 跨境电商业务领域

#### 核心业务概念
- **平台**: Shopee, TikTok, Amazon, Lazada, 妙手ERP等
- **店铺**: 每个平台可以有多个店铺（shop_id）
- **账号**: 平台账号（account_id），包含登录凭证
- **数据域**: 7个数据域（orders/products/inventory/services/traffic/analytics/finance）
- **数据粒度**: daily/weekly/monthly/custom（时间聚合粒度）

#### 数据采集流程
1. **配置账号**: 在`local_accounts.py`配置平台账号和登录URL
2. **启动采集**: 通过Playwright自动化采集数据
3. **文件下载**: 下载Excel文件到`downloads/`目录
4. **文件注册**: 自动注册到`catalog_files`表（元数据索引）
5. **字段映射**: 通过字段映射系统配置字段映射规则
6. **自动入库**: 数据自动入库到对应的事实表

#### 字段映射系统
- **四层映射架构**: 原始字段 → 中文列名层 → 标准字段 → 数据库列名
- **智能匹配**: AI驱动的字段映射建议，支持置信度显示
- **Pattern-based Mapping**: 一个规则处理无限组合（v4.6.0新增）
- **全球货币支持**: 180+货币自动识别和转换（CNY本位币）
- **数据隔离区**: 查看和重新处理隔离数据

#### 财务管理
- **CNY本位币**: 所有交易存储原币金额 + CNY金额
- **Universal Journal**: 统一流水账模式（总账+库存+费用）
- **移动加权平均成本**: 实时计算库存成本
- **三单匹配**: PO-GRN-Invoice自动对账
- **费用分摊引擎**: 多驱动分摊到店铺/SKU/日

#### 物化视图语义层
- **18个物化视图**: 产品5个、销售5个、财务3个、库存3个、C类数据2个
- **一键刷新**: 30-60秒完成，效率10倍提升
- **自动定时刷新**: 每天凌晨2点（APScheduler）
- **依赖管理**: 自动按依赖顺序刷新

### 数据质量保障
- **数据验证**: 字段映射后的数据必须通过验证才能入库
- **数据隔离区**: 质量问题数据自动隔离，支持查看和重新处理
- **数据质量监控**: 实时监控数据质量指标
- **审计追溯**: 全量操作日志、变更历史

## Important Constraints

### 技术约束
- **Windows平台兼容性**: 主要开发环境为Windows 10/11，必须考虑编码、路径、进程管理等Windows特定问题
- **PostgreSQL优先**: 任何需要查找文件或数据的操作，优先使用PostgreSQL索引查询，禁止递归搜索文件系统
- **禁止双维护**: 零容忍原则，任何重复定义必须立即修正
- **架构合规**: 必须100%符合SSOT标准，运行`python scripts/verify_architecture_ssot.py`验证

### 业务约束
- **数据安全**: 敏感数据加密存储，实现访问控制机制
- **性能要求**: 关键API响应时间P95 < 500ms，数据库查询 < 100ms
- **可扩展性**: 支持新平台、新功能的快速集成
- **向后兼容**: 至少支持2个主要版本，破坏性修改必须提供迁移指南

### 开发约束
- **代码质量**: 核心模块测试覆盖率≥80%，关键业务100%
- **文档要求**: 所有公开函数必须有docstring，所有API必须有OpenAPI文档
- **代码复杂度**: 函数复杂度≤10，函数长度≤50行，类长度≤500行
- **依赖管理**: 依赖安装需显式授权，requirements.txt仅在获批后更新

### 安全约束
- **OWASP Top 10防护**: 完整防护OWASP Top 10所有风险
- **用户认证**: JWT Token认证机制（Access Token 15分钟，Refresh Token 7天）
- **权限控制**: 基于角色的访问控制(RBAC)
- **数据加密**: 敏感数据加密存储，传输使用HTTPS（TLS 1.2+）
- **安全审计**: 完整的操作日志记录，满足GDPR、SOC 2等合规要求

## External Dependencies

### 数据采集平台
- **Shopee**: 东南亚电商平台，支持订单/产品/库存/流量数据采集
- **TikTok Shop**: 短视频电商平台，支持订单/产品数据采集
- **Amazon**: 全球电商平台，支持订单/产品数据采集
- **妙手ERP**: 跨境电商ERP系统，支持多平台数据导出

### 数据服务
- **汇率服务**: 支持180+货币汇率转换（CNY本位币）
- **数据验证服务**: 字段映射数据验证
- **数据质量监控**: 实时数据质量指标监控

### 基础设施服务
- **PostgreSQL**: 主数据库（Docker容器运行）
- **Redis**: 缓存和异步任务队列（可选）
- **Nginx**: 反向代理（生产环境）
- **Prometheus + Grafana**: 监控和告警（可选）

### 开发工具服务
- **Git**: 版本控制
- **Docker**: 容器化部署
- **CI/CD**: 持续集成和部署（可选）

### API依赖
- **FastAPI自动文档**: `/api/docs` (Swagger UI)
- **OpenAPI 3.0**: API规范标准
