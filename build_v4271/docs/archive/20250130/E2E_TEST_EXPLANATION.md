# 端到端测试说明（E2E Test）

## 📚 什么是端到端测试？

**端到端测试**（End-to-End Test，简称E2E）是验证**整个系统从头到尾**是否正常工作的测试。

### 在我们的ERP系统中，端到端测试验证：

```
用户操作 → 前端界面 → HTTP请求 → 后端API → 数据库 → 返回结果 → 前端显示
   |          |           |          |         |         |          |
   ↓          ↓           ↓          ↓         ↓         ↓          ↓
 点击按钮   Vue.js      Axios      FastAPI  PostgreSQL  JSON     Element Plus
```

---

## 🎯 我们的端到端测试内容

### test_e2e_complete.py 测试的7个步骤：

#### Step 1: 后端健康检查
```
测试: GET http://localhost:8001/health
目的: 确认后端API服务正常运行
验证: HTTP 200 响应
```

#### Step 2: 文件扫描
```
测试: POST http://localhost:8001/api/field-mapping/scan
目的: 扫描data/raw目录，注册文件到catalog_files表
验证: 返回扫描结果（总数/新增/更新）
数据流: 文件系统 → catalog_scanner → PostgreSQL
```

#### Step 3: 文件分组查询
```
测试: GET http://localhost:8001/api/field-mapping/file-groups
目的: 按source_platform+data_domain分组查询文件
验证: 返回分组列表（shopee/products, tiktok/orders等）
数据流: PostgreSQL catalog_files → 聚合查询 → JSON返回
```

#### Step 4: 文件预览
```
测试: POST http://localhost:8001/api/field-mapping/preview
目的: 预览Excel文件内容和自动提取元数据
验证: 返回列名、数据、source_platform、quality_score等
数据流: catalog_files查询 → ExcelParser读取 → 数据返回
```

#### Step 5: 数据库查询
```
测试: SQL查询 catalog_files/fact_product_metrics/fact_orders
目的: 验证数据库表结构和数据
验证: 返回记录数
数据流: 直接PostgreSQL查询
```

#### Step 6: Schema验证
```
测试: 查询information_schema.columns
目的: 验证方案B+新字段是否存在
验证: source_platform/sub_domain/quality_score等字段存在
数据流: PostgreSQL元数据查询
```

#### Step 7: 完整工作流
```
测试: 综合验证所有步骤
目的: 确认整个系统端到端打通
验证: 6/6步骤全部通过
```

---

## 🔍 为什么需要端到端测试？

### 1. 发现集成问题
- ✅ 单元测试：测试单个函数（✓）
- ✅ 集成测试：测试模块间调用（✓）
- ✅ **端到端测试**：测试真实用户场景（← 最重要）

**例子**：
- 单元测试可能通过（每个函数正确）
- 但端到端失败（数据库连接失败、API路径错误等）

### 2. 验证真实环境
```
开发环境 vs 真实环境:
- 数据库：SQLite vs PostgreSQL ← 不同！
- 端口配置：8000 vs 8001 ← 可能不同！
- 网络：localhost vs Docker网络 ← 不同！
```

### 3. 用户视角验证
模拟真实用户操作：
1. 打开前端页面
2. 点击"扫描文件"
3. 选择文件预览
4. 执行字段映射
5. 数据入库
6. 查看结果

**如果任何一步失败，用户就无法使用系统！**

---

## ⚠️ 当前问题诊断

### 问题：后端健康检查超时

**您的诊断100%正确！**

**问题根源**：
```
后端配置: postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp
             ↑ 需要连接PostgreSQL

Docker Desktop状态:
  - xihong_erp容器: ✅ 运行中
  - PostgreSQL容器: ❌ 未显示（可能未启动）
             ↑ 问题所在！
```

**症状分析**：
1. 后端启动时尝试连接PostgreSQL
2. PostgreSQL未运行 → 连接失败
3. 后端卡在数据库连接 → 健康检查超时
4. API无法响应 → 前端timeout

---

## 🔧 解决方案

### 方案A：启动PostgreSQL容器（推荐）⭐

**检查docker-compose配置**：
```bash
# 查看docker-compose.yml
cat docker-compose.yml

# 启动PostgreSQL
docker-compose up -d postgres

# 或启动所有服务
docker-compose up -d
```

**验证PostgreSQL运行**：
```bash
# 检查容器
docker ps | findstr postgres

# 测试连接
psql -h localhost -p 5432 -U erp_user -d xihong_erp
```

### 方案B：切换到SQLite（快速临时）

**修改backend/utils/config.py**：
```python
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    # 临时使用SQLite
    "sqlite:///./data/unified_erp_system.db"
)
```

### 方案C：检查PostgreSQL状态

**如果您安装的是本地PostgreSQL**（非Docker）：
```bash
# 检查服务
sc query postgresql-x64-15

# 启动服务
net start postgresql-x64-15
```

---

## 💡 我的建议

**立即执行以下步骤**：

### Step 1: 检查Docker PostgreSQL
```bash
# 查看所有容器（包括停止的）
docker ps -a

# 如果看到postgres容器但未运行，启动它
docker start <postgres_container_name>

# 或使用docker-compose
docker-compose up -d postgres
```

### Step 2: 验证数据库连接
```bash
# 使用我创建的快速测试脚本
python scripts/check_db_schema.py
```

### Step 3: 重启后端
```bash
# 停止当前后端（Ctrl+C）
# 重新启动
python run.py --backend-only
```

### Step 4: 执行端到端测试
```bash
python scripts/test_e2e_complete.py
```

---

## 📊 端到端测试覆盖范围

我们的E2E测试验证了整个**数据采集→入库→查询**的完整链路：

```
┌─────────────────────────────────────────────────────────┐
│                   端到端测试范围                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  文件系统         数据库          后端API        前端     │
│     ↓              ↓               ↓            ↓       │
│  data/raw/   → catalog_files → /scan API  → Vue.js     │
│    413个文件      407条记录      扫描接口      扫描按钮   │
│                                                         │
│  .xlsx文件   → ExcelParser   → /preview    → 预览页面   │
│    解析元数据      读取数据        预览接口      字段列表   │
│                                                         │
│  字段映射     → field_mappings → /apply-template        │
│    智能匹配        模板存储        映射接口      映射表单   │
│                                                         │
│  数据入库     → fact_tables   → /ingest     → 入库按钮   │
│    UPSERT        商品/订单表      入库接口      状态显示   │
│                                                         │
│  数据查询     → PostgreSQL    → /dashboard  → 数据看板   │
│    SQL查询       索引优化        查询接口      图表展示   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**如果任何一个环节失败，整个链路就断了！**

---

**让我现在帮您诊断PostgreSQL状态：**

