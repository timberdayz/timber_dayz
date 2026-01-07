# 🏗️ 开发框架和规则 v2.0 - 智能字段映射系统

## 📋 框架概述

本开发框架专门为智能字段映射审核系统设计，基于现代化的技术栈和最佳实践，确保系统的可维护性、可扩展性和高性能。

## 🎯 核心原则

### 1. 模块化设计
- **单一职责**: 每个模块只负责一个核心功能
- **松耦合**: 模块间通过标准接口通信
- **高内聚**: 相关功能聚合在同一个模块内

### 2. 现代化技术栈
- **前端**: Vue.js 3 + Element Plus + Pinia
- **后端**: FastAPI + SQLAlchemy + Pydantic
- **数据库**: SQLite (开发) + PostgreSQL (生产)
- **测试**: Playwright + Pytest

### 3. 用户体验优先
- **响应式设计**: 支持多设备访问
- **实时反馈**: 操作状态实时更新
- **错误友好**: 清晰的错误信息和修复建议

## 🏛️ 系统架构

### 分层架构
```
┌─────────────────────────────────────────────────────────────┐
│                    表现层 (Presentation)                    │
│  Vue.js 3 + Element Plus + Pinia + Vue Router              │
├─────────────────────────────────────────────────────────────┤
│                    业务层 (Business)                        │
│  FastAPI + Pydantic + 业务逻辑 + 验证规则                   │
├─────────────────────────────────────────────────────────────┤
│                    数据层 (Data)                            │
│  SQLAlchemy ORM + 数据访问 + 缓存服务                       │
├─────────────────────────────────────────────────────────────┤
│                    存储层 (Storage)                         │
│  SQLite/PostgreSQL + Redis + 文件系统                       │
└─────────────────────────────────────────────────────────────┘
```

### 模块组织
```
modules/
├── core/                    # 核心框架
│   ├── registry.py         # 应用注册器
│   ├── base_app.py         # 应用基类
│   ├── config.py           # 配置管理
│   └── secrets_manager.py  # 密钥管理
├── services/               # 业务服务
│   ├── mapping_engine.py   # 智能映射引擎
│   ├── data_validator.py   # 数据验证器
│   ├── data_query_service.py # 数据查询服务
│   ├── catalog_scanner.py  # 文件扫描器
│   └── ingestion_worker.py # 数据入库器
└── apps/                   # 应用模块
    ├── vue_field_mapping/  # Vue字段映射应用
    ├── collection_center/  # 数据采集中心
    └── data_management_center/ # 数据管理中心
```

## 📁 文件组织规范

### 目录结构
```
project_root/
├── modules/                 # 核心模块
├── frontend_streamlit/     # Streamlit前端 (兼容)
├── docs/                   # 项目文档
├── config/                 # 配置文件
├── data/                   # 数据文件
├── temp/                   # 临时文件
├── tests/                  # 测试文件
├── scripts/                # 脚本文件
├── requirements.txt        # Python依赖
├── pyproject.toml          # 项目配置
├── run_new.py             # 主入口
└── README.md              # 项目说明
```

### 命名规范
- **文件和目录**: snake_case
- **类名**: PascalCase
- **函数和变量**: snake_case
- **常量**: UPPER_CASE
- **API端点**: kebab-case

## 🔧 开发规范

### 代码规范
1. **Python代码**
   ```python
   # 使用类型注解
   def process_file(file_path: Path, options: Dict[str, Any]) -> bool:
       """处理文件的函数"""
       pass
   
   # 使用docstring
   class DataValidator:
       """数据验证器类"""
       
       def validate_dataframe(self, df: pd.DataFrame) -> ValidationResult:
           """
           验证DataFrame数据
           
           Args:
               df: 要验证的数据框
               
           Returns:
               ValidationResult: 验证结果
           """
           pass
   ```

2. **Vue.js代码**
   ```vue
   <template>
     <!-- 使用语义化HTML -->
     <div class="field-mapping-container">
       <section class="file-preview">
         <!-- 内容 -->
       </section>
     </div>
   </template>
   
   <script setup>
   // 使用Composition API
   import { ref, computed, onMounted } from 'vue'
   
   // 响应式数据
   const isLoading = ref(false)
   
   // 计算属性
   const hasData = computed(() => data.value.length > 0)
   
   // 生命周期
   onMounted(() => {
     // 初始化逻辑
   })
   </script>
   ```

### API设计规范
1. **RESTful设计**
   ```
   GET    /api/files          # 获取文件列表
   POST   /api/files          # 创建文件
   GET    /api/files/{id}     # 获取特定文件
   PUT    /api/files/{id}     # 更新文件
   DELETE /api/files/{id}     # 删除文件
   ```

2. **响应格式**
   ```json
   {
     "success": true,
     "data": {},
     "message": "操作成功",
     "timestamp": "2025-01-16T10:30:00Z"
   }
   ```

3. **错误处理**
   ```json
   {
     "success": false,
     "error": {
       "code": "VALIDATION_ERROR",
       "message": "数据验证失败",
       "details": []
     }
   }
   ```

### 数据库规范
1. **表命名**
   - 维度表: `dim_*` (如 dim_products, dim_shops)
   - 事实表: `fact_*` (如 fact_orders, fact_transactions)
   - 配置表: `config_*` (如 config_mappings)
   - 日志表: `log_*` (如 log_operations)

2. **字段命名**
   - 主键: `id`
   - 外键: `{table}_id` (如 shop_id, product_id)
   - 时间戳: `created_at`, `updated_at`
   - 状态字段: `status`

3. **索引策略**
   ```sql
   -- 主键索引
   PRIMARY KEY (id)
   
   -- 外键索引
   INDEX idx_shop_id (shop_id)
   
   -- 查询索引
   INDEX idx_order_date (order_date)
   
   -- 复合索引
   INDEX idx_shop_date (shop_id, order_date)
   ```

## 🧪 测试规范

### 测试分层
1. **单元测试**: 测试单个函数或类
2. **集成测试**: 测试模块间交互
3. **端到端测试**: 测试完整用户流程
4. **性能测试**: 测试系统性能指标

### 测试文件组织
```
tests/
├── unit/                    # 单元测试
│   ├── test_mapping_engine.py
│   ├── test_data_validator.py
│   └── test_services/
├── integration/             # 集成测试
│   ├── test_api_endpoints.py
│   └── test_database.py
├── e2e/                     # 端到端测试
│   └── test_user_workflows.py
└── fixtures/                # 测试数据
    ├── sample_files/
    └── test_data.json
```

### 测试覆盖率要求
- **单元测试**: ≥80%
- **集成测试**: ≥70%
- **关键路径**: 100%

## 🚀 部署规范

### 环境配置
1. **开发环境**
   - SQLite数据库
   - 本地文件存储
   - 详细日志输出

2. **测试环境**
   - PostgreSQL数据库
   - 模拟文件存储
   - 测试数据隔离

3. **生产环境**
   - PostgreSQL集群
   - 对象存储
   - 监控和告警

### 容器化
```dockerfile
# 多阶段构建
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --only=production

FROM python:3.11-slim AS backend
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

### 配置管理
```yaml
# config/production.yaml
database:
  url: postgresql://user:pass@host:5432/db
  pool_size: 20
  max_overflow: 30

cache:
  redis_url: redis://localhost:6379
  ttl: 3600

logging:
  level: INFO
  format: json
```

## 📊 监控和日志

### 日志规范
1. **日志级别**
   - ERROR: 系统错误
   - WARNING: 警告信息
   - INFO: 一般信息
   - DEBUG: 调试信息

2. **日志格式**
   ```json
   {
     "timestamp": "2025-01-16T10:30:00Z",
     "level": "INFO",
     "logger": "modules.services.mapping_engine",
     "message": "Mapping completed",
     "context": {
       "file_count": 10,
       "mapping_count": 50
     }
   }
   ```

### 监控指标
1. **系统指标**
   - CPU使用率
   - 内存使用率
   - 磁盘I/O
   - 网络流量

2. **业务指标**
   - 文件处理数量
   - 映射准确率
   - 数据验证成功率
   - 用户操作响应时间

## 🔒 安全规范

### 数据安全
1. **敏感数据加密**
   ```python
   from cryptography.fernet import Fernet
   
   def encrypt_sensitive_data(data: str) -> str:
       """加密敏感数据"""
       key = get_encryption_key()
       f = Fernet(key)
       return f.encrypt(data.encode()).decode()
   ```

2. **访问控制**
   ```python
   @app.middleware("http")
   async def security_headers(request: Request, call_next):
       response = await call_next(request)
       response.headers["X-Content-Type-Options"] = "nosniff"
       response.headers["X-Frame-Options"] = "DENY"
       return response
   ```

### API安全
1. **输入验证**
   ```python
   from pydantic import BaseModel, validator
   
   class FileRequest(BaseModel):
       file_path: str
       
       @validator('file_path')
       def validate_file_path(cls, v):
           if not v.endswith(('.xlsx', '.xls', '.csv')):
               raise ValueError('Invalid file format')
           return v
   ```

2. **速率限制**
   ```python
   from slowapi import Limiter
   
   limiter = Limiter(key_func=get_remote_address)
   
   @app.post("/api/upload")
   @limiter.limit("10/minute")
   async def upload_file(request: Request):
       pass
   ```

## 📚 文档规范

### 代码文档
1. **函数文档**
   ```python
   def generate_mappings(
       source_columns: List[str], 
       target_fields: List[str],
       data_domain: str = "products"
   ) -> List[MappingResult]:
       """
       生成字段映射建议
       
       Args:
           source_columns: 源文件列名列表
           target_fields: 目标数据库字段列表
           data_domain: 数据域（products, orders等）
           
       Returns:
           List[MappingResult]: 映射结果列表
           
       Raises:
           ValueError: 当参数无效时
           
       Example:
           >>> mappings = generate_mappings(
           ...     ["商品名称", "价格"], 
           ...     ["product_name", "price"]
           ... )
       """
   ```

2. **API文档**
   ```python
   @app.post("/api/field-mapping", 
             response_model=FieldMappingResponse,
             summary="生成智能字段映射",
             description="基于AI算法自动生成字段映射建议")
   async def get_field_mapping(request: FieldMappingRequest):
       """获取智能字段映射建议"""
       pass
   ```

### 用户文档
1. **操作指南**: 详细的用户操作步骤
2. **API文档**: 完整的API接口说明
3. **故障排除**: 常见问题和解决方案
4. **最佳实践**: 使用建议和技巧

## 🔄 持续集成

### CI/CD流程
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest tests/
      - name: Run linting
        run: flake8 modules/
```

### 代码质量
1. **静态分析**: flake8, mypy, bandit
2. **代码格式化**: black, isort
3. **安全扫描**: safety, semgrep
4. **依赖检查**: pip-audit

## 📈 性能优化

### 数据库优化
1. **查询优化**
   ```sql
   -- 使用适当的索引
   EXPLAIN ANALYZE SELECT * FROM fact_orders 
   WHERE shop_id = 'shop123' AND order_date >= '2025-01-01';
   
   -- 批量操作
   INSERT INTO products (name, price) VALUES 
   ('Product 1', 10.0),
   ('Product 2', 20.0);
   ```

2. **连接池配置**
   ```python
   engine = create_engine(
       database_url,
       pool_size=20,
       max_overflow=30,
       pool_pre_ping=True
   )
   ```

### 缓存策略
1. **应用层缓存**
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=128)
   def get_mapping_rules(data_domain: str):
       """缓存映射规则"""
       pass
   ```

2. **数据库查询缓存**
   ```python
   @cached(ttl=300)  # 5分钟缓存
   def get_catalog_status(self) -> Dict[str, Any]:
       """缓存目录状态"""
       pass
   ```

---

**注意**: 此开发框架会随着项目发展持续更新和完善。所有团队成员都应遵循这些规范，确保代码质量和项目一致性。
