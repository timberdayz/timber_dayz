# 🛠️ 西虹ERP系统 - 开发工作流指南

> **适用于**: 后端开发 + 字段映射系统开发  
> **架构**: 混合架构 v4.1.0  
> **更新时间**: 2025-10-23

---

## 📋 目录

1. [开发环境设置](#开发环境设置)
2. [后端API开发](#后端api开发)
3. [字段映射系统开发](#字段映射系统开发)
4. [前端开发](#前端开发)
5. [数据库管理](#数据库管理)
6. [测试和调试](#测试和调试)

---

## 🚀 开发环境设置

### 步骤1: 启动Docker数据库

```bash
# Windows
start-docker-dev.bat

# Linux/Mac
./docker/scripts/start-dev.sh
```

### 步骤2: 验证数据库

```bash
# 访问 pgAdmin
http://localhost:5051

# 登录信息
邮箱: admin@xihongerp.com
密码: admin123

# 连接到数据库
主机: postgres (Docker内部) 或 localhost (本地)
端口: 5432
数据库: xihong_erp
用户: erp_user
密码: erp_pass_2025
```

### 步骤3: 检查数据库表

```bash
# 方式1: 使用pgAdmin（推荐）
# 访问 http://localhost:5051 → 展开数据库 → 查看表

# 方式2: 使用命令行
docker-compose exec postgres psql -U erp_user -d xihong_erp -c "\dt"

# 应该看到16个表
```

---

## 🔧 后端API开发

### 目录结构

```
backend/
├── main.py                 # FastAPI应用入口
├── routers/                # API路由
│   ├── dashboard.py        # 数据看板API
│   ├── collection.py       # 数据采集API
│   ├── management.py       # 数据管理API
│   ├── accounts.py         # 账号管理API
│   ├── field_mapping.py    # 字段映射API ⭐
│   └── test_api.py         # 测试API
├── models/                 # 数据模型
│   └── database.py         # SQLAlchemy模型
├── services/               # 业务逻辑
│   ├── excel_parser.py     # Excel解析
│   ├── field_mapping/      # 字段映射服务 ⭐
│   ├── data_validator.py   # 数据验证
│   ├── data_importer.py    # 数据导入
│   └── progress_tracker.py # 进度跟踪
└── utils/                  # 工具函数
    ├── config.py           # 配置管理
    ├── logger.py           # 日志
    └── postgres_path.py    # PostgreSQL路径
```

### 启动后端服务

```bash
cd backend

# 安装依赖（首次）
pip install -r requirements.txt

# 启动服务（开发模式）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或使用
python main.py
```

### 访问API文档

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health

### 开发新API

#### 示例: 创建新的API路由

```python
# backend/routers/my_new_api.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.models.database import get_db

router = APIRouter()

@router.get("/my-endpoint")
async def my_endpoint(db: Session = Depends(get_db)):
    """我的新API端点"""
    # 业务逻辑
    return {"message": "Hello World"}
```

#### 注册路由

```python
# backend/main.py

from backend.routers import my_new_api

# 添加到路由
app.include_router(my_new_api.router, prefix="/api", tags=["我的API"])
```

### 调试技巧

```python
# 1. 使用日志
from backend.utils.logger import setup_logger
logger = setup_logger(__name__)

logger.info("这是一条信息")
logger.error("这是一条错误")

# 2. 使用断点
import pdb; pdb.set_trace()  # Python调试器

# 3. 查看SQL查询
# 在 backend/utils/config.py 设置
DATABASE_ECHO = True  # 打印SQL语句
```

---

## 🎯 字段映射系统开发

### 核心文件

```
backend/
├── routers/
│   └── field_mapping.py        # 字段映射API ⭐
└── services/
    ├── field_mapping/
    │   └── mapper.py           # 映射引擎 ⭐
    ├── excel_parser.py         # Excel解析
    ├── data_validator.py       # 数据验证
    └── data_importer.py        # 数据导入

frontend/
└── src/
    └── views/
        └── FieldMapping.vue    # 字段映射界面 ⭐
```

### 字段映射API端点

```bash
# 获取文件分组
GET /api/field-mapping/file-groups

# 预览文件
POST /api/field-mapping/preview

# 生成字段映射
POST /api/field-mapping/suggest

# 批量导入数据
POST /api/field-mapping/bulk-ingest

# 获取进度
GET /api/field-mapping/progress/{task_id}
```

### 开发字段映射功能

#### 1. 添加新的标准字段

```python
# backend/services/field_mapping/mapper.py

# 在 COMPREHENSIVE_ALIAS_DICTIONARY 中添加
COMPREHENSIVE_ALIAS_DICTIONARY: Dict[str, str] = {
    # 添加新字段映射
    "新字段名": "standard_field_name",
    "new field": "standard_field_name",
    # ...
}
```

#### 2. 修改映射算法

```python
# backend/services/field_mapping/mapper.py

def suggest_mappings(columns: List[str], domain: str = "products") -> Dict[str, Dict[str, Any]]:
    """生成字段映射建议"""
    # 修改映射逻辑
    # ...
```

#### 3. 添加数据验证规则

```python
# backend/services/data_validator.py

def validate_orders(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """订单数据验证"""
    # 添加新的验证规则
    # ...
```

### 测试字段映射

```bash
# 1. 启动后端
cd backend
uvicorn main:app --reload

# 2. 启动前端
cd frontend
npm run dev

# 3. 访问字段映射界面
http://localhost:5173/field-mapping

# 4. 测试流程
# 扫描文件 → 选择文件 → 生成映射 → 审核 → 导入
```

---

## 🎨 前端开发

### 启动前端服务

```bash
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

### 访问地址

- **开发服务器**: http://localhost:5173
- **字段映射**: http://localhost:5173/field-mapping
- **数据看板**: http://localhost:5173/dashboard

### 开发新页面

```vue
<!-- frontend/src/views/MyNewPage.vue -->

<template>
  <div class="my-new-page">
    <h1>我的新页面</h1>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// 组件逻辑
const message = ref('Hello World')
</script>

<style scoped>
.my-new-page {
  padding: 20px;
}
</style>
```

### 调用后端API

```javascript
// frontend/src/api/index.js

import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default {
  // 调用后端API
  async myApiCall(data) {
    const response = await axios.post(`${API_BASE_URL}/api/my-endpoint`, data)
    return response.data
  }
}
```

---

## 💾 数据库管理

### 使用pgAdmin（推荐）

```bash
# 访问 pgAdmin
http://localhost:5051

# 登录后添加服务器连接
名称: Xihong ERP
主机: postgres (Docker内部) 或 localhost (本地)
端口: 5432
数据库: xihong_erp
用户: erp_user
密码: erp_pass_2025
```

### 使用命令行

```bash
# 连接数据库
docker-compose exec postgres psql -U erp_user -d xihong_erp

# 查看所有表
\dt

# 查询数据
SELECT * FROM catalog_files LIMIT 10;

# 查看表结构
\d catalog_files

# 退出
\q
```

### 数据库备份

```bash
# 备份数据库
docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backup.sql

# 恢复数据库
cat backup.sql | docker-compose exec -T postgres psql -U erp_user -d xihong_erp
```

### 数据库迁移

```bash
# 使用Alembic（如果配置）
cd migrations

# 创建迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

---

## 🧪 测试和调试

### 后端测试

```bash
cd backend

# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_api.py

# 查看覆盖率
pytest --cov=backend --cov-report=html
```

### 前端测试

```bash
cd frontend

# 运行单元测试
npm run test

# 运行E2E测试
npm run test:e2e
```

### API测试

```bash
# 使用curl
curl http://localhost:8000/health

# 使用httpie（更友好）
http http://localhost:8000/health

# 使用Postman
# 导入 docs/postman_collection.json
```

### 调试Docker容器

```bash
# 进入容器
docker-compose exec postgres bash
docker-compose exec backend bash

# 查看日志
docker-compose logs -f postgres
docker-compose logs -f backend

# 重启服务
docker-compose restart postgres
```

---

## 📝 开发规范

### 代码风格

- **Python**: PEP 8 + Black格式化
- **JavaScript/Vue**: ESLint + Prettier
- **类型注解**: 使用TypeScript和Python类型提示

### Git提交规范

```bash
# 提交格式
git commit -m "[类型] 简短描述

详细描述（可选）
"

# 类型
# - feat: 新功能
# - fix: 修复bug
# - docs: 文档
# - style: 格式
# - refactor: 重构
# - test: 测试
# - chore: 构建/工具

# 示例
git commit -m "[feat] 添加字段映射批量导入功能

- 支持批量处理多个文件
- 添加进度跟踪
- 优化错误处理
"
```

### 文档规范

- 所有API必须有docstring
- 复杂逻辑必须有注释
- 重要变更必须更新文档

---

## 🚀 发布流程

### 开发环境 → 测试环境

```bash
# 1. 提交代码
git add .
git commit -m "[feat] 功能描述"
git push

# 2. 合并到develop分支
git checkout develop
git merge feature/your-feature

# 3. 在测试环境部署
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### 测试环境 → 生产环境

```bash
# 1. 合并到main分支
git checkout main
git merge develop

# 2. 打标签
git tag -a v1.0.0 -m "版本1.0.0"
git push --tags

# 3. 在生产环境部署
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

---

## 💡 最佳实践

1. ✅ **经常提交代码**: 每完成一个小功能就提交
2. ✅ **编写测试**: 重要功能必须有测试覆盖
3. ✅ **代码审查**: 重要变更由其他人审查
4. ✅ **文档同步**: 代码变更时同步更新文档
5. ✅ **定期备份**: 每天备份数据库
6. ✅ **性能监控**: 定期检查API响应时间
7. ✅ **安全意识**: 不提交敏感信息到Git

---

**祝开发顺利！** 🎉

