# Linux 服务器部署指南 - 包含 Playwright 数据采集

**版本**: v4.19.7  
**更新时间**: 2026-01-06  
**适用环境**: Linux 服务器（生产环境）

---

## 📋 目录

1. [部署前准备](#部署前准备)
2. [文件路径配置](#文件路径配置)
3. [Playwright 容器化部署](#playwright-容器化部署)
4. [数据采集服务部署](#数据采集服务部署)
5. [完整部署步骤](#完整部署步骤)
6. [故障排查](#故障排查)

---

## 🎯 部署前准备

### 1. 服务器要求

#### 基础要求

- **操作系统**: Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- **CPU**: 4 核心或更多（Playwright 需要）
- **内存**: 8GB 或更多（推荐 16GB）
- **磁盘**: 至少 50GB 可用空间
- **Docker**: 20.10+ 和 Docker Compose 2.0+

#### Playwright 特殊要求

- **共享内存**: 至少 2GB（`/dev/shm`）
- **字体支持**: 需要中文字体（已包含在 Dockerfile 中）
- **浏览器依赖**: Chromium 及其依赖（自动安装）

### 2. 目录结构规划

推荐的生产环境目录结构：

```bash
# 在服务器上创建项目目录
/opt/xihong_erp/              # 项目根目录
├── docker-compose.prod.yml   # 生产环境配置
├── docker-compose.collection.yml  # 采集服务配置
├── .env                      # 环境变量配置
├── data/                     # 数据目录（卷挂载）
│   ├── raw/                  # 原始数据（采集输出目录）⭐
│   │   └── 2024/            # 按年分区
│   ├── processed/            # 处理后数据
│   └── input/                # 输入数据
├── logs/                     # 日志目录
├── temp/                     # 临时文件
├── uploads/                  # 上传文件
└── config/                   # 配置文件
```

**重要**: 采集的数据文件应该保存在 `/opt/xihong_erp/data/raw/` 目录下。

---

## 📁 文件路径配置

### 问题说明

在容器化环境中，`get_project_root()` 无法自动检测项目根目录（因为目录是分别挂载的），需要**明确指定路径环境变量**。

### 已修复的配置

所有 Docker Compose 配置文件已添加路径环境变量：

```yaml
environment:
  # ⭐ 路径配置（Linux服务器部署必需）
  PROJECT_ROOT: /app # 容器内项目根目录
  DATA_DIR: /app/data # 数据目录
  DATA_RAW_DIR: /app/data/raw # 原始数据目录（采集输出）
  DOWNLOADS_DIR: /app/downloads
  TEMP_DIR: /app/temp
  LOGS_DIR: /app/logs
```

### 卷挂载配置

```yaml
volumes:
  # ⭐ 关键：挂载服务器上的数据目录到容器内
  - /opt/xihong_erp/data:/app/data # 数据目录
  - /opt/xihong_erp/logs:/app/logs # 日志目录
  - /opt/xihong_erp/temp:/app/temp # 临时文件
  - /opt/xihong_erp/uploads:/app/uploads # 上传文件
```

### 路径映射关系

| 服务器路径                        | 容器内路径             | 说明                    |
| --------------------------------- | ---------------------- | ----------------------- |
| `/opt/xihong_erp/data/raw/`       | `/app/data/raw/`       | **采集数据输出目录** ⭐ |
| `/opt/xihong_erp/data/processed/` | `/app/data/processed/` | 处理后数据              |
| `/opt/xihong_erp/logs/`           | `/app/logs/`           | 日志文件                |
| `/opt/xihong_erp/temp/`           | `/app/temp/`           | 临时文件                |

**关键点**:

- ✅ 采集程序应该将文件保存到服务器的 `/opt/xihong_erp/data/raw/` 目录
- ✅ 容器会自动通过卷挂载访问这些文件
- ✅ 不需要手动复制文件到容器内

---

## 🎭 Playwright 容器化部署

### 架构说明

Playwright 数据采集服务使用**独立的容器**运行：

```
┌─────────────────────────────────────┐
│  主应用容器（backend）               │
│  - FastAPI 后端                     │
│  - 不包含 Playwright                │
└─────────────────────────────────────┘
              ↓ HTTP API
┌─────────────────────────────────────┐
│  采集服务容器（collection）          │
│  - Playwright + Chromium            │
│  - 数据采集组件                     │
│  - 浏览器自动化                     │
└─────────────────────────────────────┘
              ↓ 写入文件
┌─────────────────────────────────────┐
│  共享数据目录（卷挂载）              │
│  /opt/xihong_erp/data/raw/          │
└─────────────────────────────────────┘
```

### 为什么分离部署？

1. **资源隔离**: Playwright 需要大量内存（每个浏览器实例约 500MB-1GB）
2. **独立扩展**: 可以根据采集需求独立扩展采集服务
3. **故障隔离**: 采集服务崩溃不影响主应用
4. **版本管理**: 可以独立更新 Playwright 版本

### Dockerfile.collection 说明

采集服务使用专门的 Dockerfile（`Dockerfile.collection`）：

```dockerfile
# 包含完整的 Playwright 环境
- Python 3.11
- Chromium 浏览器
- 所有浏览器依赖库
- 中文字体支持
- 2GB 共享内存（Chromium 必需）
```

### 环境变量配置

```yaml
environment:
  # Playwright 配置
  PLAYWRIGHT_HEADLESS: "true" # 无头模式（生产环境必需）
  PLAYWRIGHT_TIMEOUT: "30000" # 超时时间（毫秒）

  # 采集配置
  MAX_COLLECTION_TASKS: "3" # 最大并发任务数
  COMPONENT_TIMEOUT: "300" # 单组件超时（秒）
  TASK_TIMEOUT: "1800" # 单任务超时（秒）

  # 路径配置（必需）
  PROJECT_ROOT: /app
  DATA_DIR: /app/data
  DATA_RAW_DIR: /app/data/raw
```

---

## 🚀 数据采集服务部署

### 方式 1: 集成部署（推荐）

在主应用的 `docker-compose.prod.yml` 中添加采集服务：

```yaml
services:
  # ... 其他服务 ...

  # 数据采集服务
  collection:
    build:
      context: .
      dockerfile: Dockerfile.collection
    container_name: xihong_erp_collection_prod
    restart: always
    environment:
      # 数据库配置（连接到主数据库）
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

      # Playwright 配置
      PLAYWRIGHT_HEADLESS: "true"
      MAX_COLLECTION_TASKS: "3"

      # ⭐ 路径配置（必需）
      PROJECT_ROOT: /app
      DATA_DIR: /app/data
      DATA_RAW_DIR: /app/data/raw
    volumes:
      - /opt/xihong_erp/data:/app/data
      - /opt/xihong_erp/logs:/app/logs
      - /opt/xihong_erp/temp:/app/temp
    ports:
      - "8002:8000" # 采集服务 API 端口
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - xihong_erp_network
    # ⭐ 重要：Playwright 需要大共享内存
    shm_size: "2gb"
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 4G
```

### 方式 2: 独立部署（分布式场景）

使用独立的 `docker-compose.collection.yml`：

```bash
# 在服务器上部署采集服务
docker-compose -f docker-compose.collection.yml up -d
```

**使用场景**:

- 多服务器部署（采集服务独立服务器）
- 高并发采集需求
- 资源隔离需求

---

## 📝 完整部署步骤

### 步骤 1: 服务器准备

```bash
# 1. 创建项目目录
sudo mkdir -p /opt/xihong_erp/{data/{raw,processed,input},logs,temp,uploads,config}
sudo chown -R $USER:$USER /opt/xihong_erp

# 2. 创建数据目录（按年分区）
mkdir -p /opt/xihong_erp/data/raw/2024
mkdir -p /opt/xihong_erp/data/raw/2025
```

### 步骤 2: 配置环境变量

创建 `.env.production` 文件：

```bash
# 数据库配置
POSTGRES_USER=erp_user
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=xihong_erp

# Redis 配置
REDIS_PASSWORD=your_redis_password_here

# 安全配置（必须修改）
SECRET_KEY=your-random-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here

# Playwright 配置
PLAYWRIGHT_HEADLESS=true
MAX_COLLECTION_TASKS=3

# 路径配置（容器内路径，不需要修改）
PROJECT_ROOT=/app
DATA_DIR=/app/data
DATA_RAW_DIR=/app/data/raw
```

### 步骤 3: 修改 docker-compose.prod.yml

确保卷挂载指向正确的服务器路径：

```yaml
services:
  backend:
    volumes:
      - /opt/xihong_erp/data:/app/data # ⭐ 修改为服务器路径
      - /opt/xihong_erp/logs:/app/logs
      - /opt/xihong_erp/temp:/app/temp

  collection:
    volumes:
      - /opt/xihong_erp/data:/app/data # ⭐ 与 backend 共享数据目录
      - /opt/xihong_erp/logs:/app/logs
      - /opt/xihong_erp/temp:/app/temp
```

### 步骤 4: 构建和启动

```bash
# 1. 构建镜像（包含 Playwright）
docker-compose -f docker-compose.prod.yml build collection

# 2. 启动所有服务
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d

# 3. 查看日志
docker-compose -f docker-compose.prod.yml logs -f collection
```

### 步骤 5: 验证部署

```bash
# 1. 检查容器状态
docker ps | grep xihong_erp

# 2. 检查采集服务健康状态
curl http://localhost:8002/api/collection/health

# 3. 检查路径配置
docker exec xihong_erp_collection_prod python -c "
from modules.core.path_manager import get_data_raw_dir
print('DATA_RAW_DIR:', get_data_raw_dir())
"
# 应该输出: /app/data/raw

# 4. 检查文件扫描
docker exec xihong_erp_backend_prod python -c "
from modules.core.path_manager import get_data_raw_dir
import os
print('路径存在:', os.path.exists(get_data_raw_dir()))
print('文件列表:', os.listdir(get_data_raw_dir()) if os.path.exists(get_data_raw_dir()) else 'None')
"
```

---

## 🔧 故障排查

### 问题 1: 扫描不到文件

**症状**: 文件列表刷新后没有文件

**检查步骤**:

```bash
# 1. 检查服务器上是否有文件
ls -la /opt/xihong_erp/data/raw/2024/

# 2. 检查容器内是否能访问
docker exec xihong_erp_backend_prod ls -la /app/data/raw/

# 3. 检查路径配置
docker exec xihong_erp_backend_prod env | grep DATA_DIR

# 4. 检查卷挂载
docker inspect xihong_erp_backend_prod | grep -A 10 Mounts
```

**解决方案**:

- ✅ 确保卷挂载路径正确
- ✅ 确保文件在服务器的正确目录下
- ✅ 确保环境变量 `DATA_RAW_DIR=/app/data/raw` 已设置

### 问题 2: Playwright 无法启动浏览器

**症状**: 采集任务失败，日志显示浏览器启动错误

**检查步骤**:

```bash
# 1. 检查共享内存
docker exec xihong_erp_collection_prod df -h /dev/shm
# 应该显示至少 2GB

# 2. 检查 Playwright 安装
docker exec xihong_erp_collection_prod playwright --version

# 3. 检查浏览器
docker exec xihong_erp_collection_prod ls -la /ms-playwright/
```

**解决方案**:

- ✅ 确保 `shm_size: '2gb'` 已配置
- ✅ 重新构建镜像：`docker-compose build collection`
- ✅ 检查容器资源限制（内存至少 4GB）

### 问题 3: 路径错误（`/app/modules/data/raw`）

**症状**: 扫描路径错误，找不到文件

**原因**: 环境变量未设置，`get_project_root()` 检测失败

**解决方案**:

- ✅ 确保所有服务都设置了 `PROJECT_ROOT=/app` 和 `DATA_DIR=/app/data`
- ✅ 重启容器：`docker-compose restart`

### 问题 4: 权限问题

**症状**: 无法写入文件或创建目录

**解决方案**:

```bash
# 1. 设置目录权限
sudo chown -R 1000:1000 /opt/xihong_erp/data
sudo chmod -R 755 /opt/xihong_erp/data

# 2. 检查容器用户
docker exec xihong_erp_collection_prod id
```

---

## ✅ 部署检查清单

### 部署前

- [ ] 服务器资源充足（CPU 4+ 核心，内存 8GB+）
- [ ] Docker 和 Docker Compose 已安装
- [ ] 目录结构已创建
- [ ] 环境变量文件已配置

### 部署中

- [ ] 镜像构建成功
- [ ] 所有容器启动成功
- [ ] 数据库连接正常
- [ ] Redis 连接正常

### 部署后

- [ ] 路径环境变量已设置（`PROJECT_ROOT`, `DATA_DIR`）
- [ ] 卷挂载路径正确
- [ ] 文件扫描功能正常
- [ ] Playwright 采集服务正常运行
- [ ] 日志正常输出

---

## 📚 相关文档

- [Docker 启动完整指南](DOCKER_STARTUP_COMPLETE_GUIDE.md)
- [环境变量配置清单](deployment/CLOUD_ENVIRONMENT_VARIABLES.md)
- [Playwright 使用规范](../.cursorrules#playwright使用规范)

---

## 💡 最佳实践

1. **数据目录规划**:

   - 使用按年分区的目录结构（`data/raw/2024/`, `data/raw/2025/`）
   - 定期清理旧数据（超过 1 年的数据）

2. **资源管理**:

   - Playwright 容器限制并发任务数（`MAX_COLLECTION_TASKS=3`）
   - 监控内存使用，避免 OOM

3. **安全配置**:

   - 使用强密码（数据库、Redis、密钥）
   - 限制容器网络访问
   - 定期更新镜像

4. **日志管理**:
   - 配置日志轮转
   - 定期清理旧日志
   - 监控错误日志

---

**最后更新**: 2026-01-06  
**维护者**: 系统架构组
