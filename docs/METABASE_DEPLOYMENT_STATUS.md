# Metabase部署状态

## 部署完成时间
2025-11-25 14:00

## 已完成工作

### 1. Superset清理 ✅
- ✅ 停止并删除所有Superset相关容器：
  - `superset`
  - `superset_worker`
  - `superset_beat`
  - `superset_redis`

### 2. Metabase部署 ✅
- ✅ 创建Docker Compose配置：`docker-compose.metabase.yml`
- ✅ 配置环境变量（已添加到`env.example`）
- ✅ 启动Metabase容器：`xihong_erp_metabase`
- ✅ 容器状态：**healthy**（健康运行）
- ✅ 端口映射：`0.0.0.0:3000->3000/tcp`

### 3. 自动化脚本 ✅
- ✅ 创建初始化脚本：`scripts/init_metabase_tables.py`
- ✅ 创建使用文档：`docs/METABASE_TABLE_INIT_GUIDE.md`

## 当前状态

### Metabase容器
- **容器名**: `xihong_erp_metabase`
- **状态**: Up and healthy
- **访问地址**: http://localhost:3000
- **网络**: `xihong_erp_erp_network`（与PostgreSQL在同一网络）

### 下一步操作

#### 1. 首次访问Metabase（必须手动完成）
1. 打开浏览器访问：http://localhost:3000
2. 完成初始设置向导：
   - 设置管理员账号（建议：admin@xihong.com / admin）
   - 选择语言：中文
   - 完成其他基本设置

#### 2. 运行自动化初始化脚本
```bash
# 设置环境变量（如果使用非默认值）
export METABASE_EMAIL=admin@xihong.com
export METABASE_PASSWORD=admin

# 运行初始化脚本
python scripts/init_metabase_tables.py
```

脚本将自动：
- 登录Metabase
- 创建PostgreSQL数据库连接
- 同步10个表/视图

#### 3. 验证数据库连接
在Metabase UI中：
- Admin → Databases
- 确认"西虹ERP数据库"连接已创建
- 测试连接：点击"Test connection"

#### 4. 创建Dashboard和Question
参考文档：
- `docs/METABASE_DASHBOARD_MANUAL_SETUP.md`（待创建）
- Metabase官方文档

## 容器管理命令

### 查看Metabase状态
```bash
docker ps --filter "name=metabase"
```

### 查看Metabase日志
```bash
docker logs xihong_erp_metabase
docker logs -f xihong_erp_metabase  # 实时日志
```

### 停止Metabase
```bash
docker-compose -f docker-compose.metabase.yml --profile dev down
```

### 重启Metabase
```bash
docker-compose -f docker-compose.metabase.yml --profile dev restart
```

### 完全删除（包括数据卷）
```bash
docker-compose -f docker-compose.metabase.yml --profile dev down -v
```

## 网络配置

Metabase使用外部网络 `xihong_erp_erp_network`，与以下服务在同一网络：
- `xihong_erp_postgres` (PostgreSQL)
- `xihong_erp_pgadmin` (pgAdmin)

这确保了Metabase可以直接通过服务名 `postgres` 访问PostgreSQL数据库。

## 数据持久化

Metabase数据存储在Docker卷中：
- **卷名**: `xihong_erp_metabase_data`
- **挂载路径**: `/metabase-data`
- **包含内容**:
  - Metabase内部数据库（H2）
  - 用户配置
  - Dashboard和Question定义

## 环境变量

已配置的环境变量（在`env.example`中）：
- `METABASE_PORT=3000`
- `METABASE_ENCRYPTION_SECRET_KEY`（生产环境必须修改）
- `METABASE_EMBEDDING_SECRET_KEY`（生产环境必须修改）

## 故障排查

### Metabase无法访问
1. 检查容器状态：`docker ps --filter "name=metabase"`
2. 查看日志：`docker logs xihong_erp_metabase`
3. 检查端口占用：`netstat -ano | findstr :3000`

### 数据库连接失败
1. 确认PostgreSQL容器运行：`docker ps --filter "name=postgres"`
2. 检查网络连接：`docker network inspect xihong_erp_erp_network`
3. 测试PostgreSQL连接：`docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp`

### 初始化脚本失败
1. 确认Metabase已完全启动（等待2-3分钟）
2. 确认已完成首次设置向导
3. 检查账号密码是否正确
4. 查看脚本日志输出

## 相关文档

- `docs/METABASE_TABLE_INIT_GUIDE.md` - 表/视图初始化指南
- `scripts/init_metabase_tables.py` - 自动化初始化脚本
- `docker-compose.metabase.yml` - Docker Compose配置

