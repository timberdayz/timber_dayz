# PostgreSQL环境安装指南

## Phase 1: Docker Desktop安装（Windows）

### 步骤1：下载Docker Desktop

1. 访问Docker官网：https://www.docker.com/products/docker-desktop/
2. 点击"Download for Windows"按钮
3. 下载完成后，运行安装程序 `Docker Desktop Installer.exe`

### 步骤2：安装Docker Desktop

1. 双击运行安装程序
2. 在安装选项中，确保勾选：
   - ✅ Use WSL 2 instead of Hyper-V (推荐，性能更好)
   - ✅ Add shortcut to desktop
3. 点击"OK"开始安装
4. 安装完成后，**重启电脑**（重要！）

### 步骤3：启动Docker Desktop

1. 重启后，从桌面或开始菜单启动Docker Desktop
2. 首次启动会要求接受服务条款，点击"Accept"
3. 可以跳过登录（点击"Skip"）
4. 等待Docker Engine启动完成（左下角显示绿色"Engine running"）

### 步骤4：验证Docker安装

打开PowerShell或命令提示符，运行：

```powershell
docker --version
docker-compose --version
```

应该看到类似输出：
```
Docker version 24.0.x, build xxxxx
Docker Compose version v2.x.x
```

### 步骤5：配置Docker资源（可选但推荐）

1. 打开Docker Desktop
2. 点击右上角齿轮图标（Settings）
3. 进入"Resources"：
   - **CPUs**: 建议分配 4-6 个CPU核心
   - **Memory**: 建议分配 4-8 GB内存
   - **Disk image size**: 默认即可（至少20GB）
4. 点击"Apply & Restart"

## Phase 2: 启动PostgreSQL容器

### 方法1：使用docker-compose（推荐）

在项目根目录下，运行：

```powershell
# 启动PostgreSQL和pgAdmin
docker-compose up -d

# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f postgres
```

**预期输出**：
```
[+] Running 3/3
 ✔ Network xihong_erp_default       Created
 ✔ Container xihong_erp_postgres    Started
 ✔ Container xihong_erp_pgadmin     Started
```

### 方法2：手动启动（备选）

```powershell
# 创建Docker网络
docker network create xihong_erp_network

# 启动PostgreSQL容器
docker run -d `
  --name xihong_erp_postgres `
  --network xihong_erp_network `
  -e POSTGRES_USER=erp_user `
  -e POSTGRES_PASSWORD=erp_pass_2025 `
  -e POSTGRES_DB=xihong_erp `
  -p 5432:5432 `
  -v postgres_data:/var/lib/postgresql/data `
  postgres:15-alpine

# 启动pgAdmin容器
docker run -d `
  --name xihong_erp_pgadmin `
  --network xihong_erp_network `
  -e PGADMIN_DEFAULT_EMAIL=admin@xihong.com `
  -e PGADMIN_DEFAULT_PASSWORD=admin `
  -p 5050:80 `
  dpage/pgadmin4
```

## Phase 3: 验证数据库连接

### 方法1：使用psql命令行

```powershell
# 进入PostgreSQL容器
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp

# 在psql中运行测试命令
\dt  # 列出所有表
\d+ fact_product_metrics  # 查看分区表详情
SELECT * FROM dim_platform;  # 查询平台数据
\q  # 退出
```

**预期结果**：
- 应该看到初始化脚本创建的所有表
- dim_platform表中应有5条平台数据
- fact_product_metrics应显示为分区表

### 方法2：使用pgAdmin Web界面

1. 打开浏览器，访问：http://localhost:5050
2. 使用以下凭据登录：
   - Email: `admin@xihong.com`
   - Password: `admin`
3. 添加新服务器：
   - 右键"Servers" → "Register" → "Server"
   - **General标签**：
     - Name: `Xihong ERP`
   - **Connection标签**：
     - Host: `xihong_erp_postgres` (容器名)
     - Port: `5432`
     - Maintenance database: `xihong_erp`
     - Username: `erp_user`
     - Password: `erp_pass_2025`
     - 勾选"Save password"
4. 点击"Save"连接

### 方法3：使用Python测试脚本

创建并运行测试脚本：

```python
# test_postgres_connection.py
import psycopg2
from psycopg2 import sql

try:
    # 连接到PostgreSQL
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="xihong_erp",
        user="erp_user",
        password="erp_pass_2025"
    )
    
    print("✅ 成功连接到PostgreSQL数据库！")
    
    # 创建游标
    cursor = conn.cursor()
    
    # 查询PostgreSQL版本
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"\n📊 PostgreSQL版本: {version[0]}")
    
    # 查询所有表
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()
    print(f"\n📋 数据库中共有 {len(tables)} 张表：")
    for table in tables:
        print(f"  - {table[0]}")
    
    # 查询分区表信息
    cursor.execute("""
        SELECT 
            parent.relname AS parent_table,
            child.relname AS partition_name
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        WHERE parent.relname LIKE 'fact_%'
        ORDER BY parent.relname, child.relname;
    """)
    partitions = cursor.fetchall()
    print(f"\n📊 分区表信息：")
    for parent, child in partitions:
        print(f"  - {parent} → {child}")
    
    # 查询平台数据
    cursor.execute("SELECT platform_code, platform_name_cn FROM dim_platform;")
    platforms = cursor.fetchall()
    print(f"\n🏪 已配置的平台（{len(platforms)}个）：")
    for code, name in platforms:
        print(f"  - {code}: {name}")
    
    # 关闭连接
    cursor.close()
    conn.close()
    print("\n✅ 数据库验证完成！所有功能正常。")
    
except Exception as e:
    print(f"❌ 连接失败: {e}")
```

运行测试：

```powershell
python test_postgres_connection.py
```

## Phase 4: 常用Docker命令

### 容器管理

```powershell
# 查看运行中的容器
docker ps

# 查看所有容器（包括停止的）
docker ps -a

# 停止容器
docker-compose stop

# 启动容器
docker-compose start

# 重启容器
docker-compose restart

# 完全删除容器和数据卷
docker-compose down -v
```

### 日志查看

```powershell
# 查看PostgreSQL日志
docker-compose logs -f postgres

# 查看最近100行日志
docker-compose logs --tail=100 postgres

# 查看所有服务日志
docker-compose logs -f
```

### 数据备份

```powershell
# 导出数据库
docker exec xihong_erp_postgres pg_dump -U erp_user xihong_erp > backup_$(Get-Date -Format "yyyyMMdd_HHmmss").sql

# 导入数据库
docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < backup_20251022_120000.sql
```

### 进入容器

```powershell
# 进入PostgreSQL容器的bash
docker exec -it xihong_erp_postgres /bin/sh

# 直接进入psql
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp
```

## 故障排除

### 问题1：端口已被占用

**错误信息**：
```
Error: bind: address already in use
```

**解决方案**：
```powershell
# 查看占用5432端口的进程
netstat -ano | findstr :5432

# 停止占用端口的进程（替换<PID>为实际进程ID）
taskkill /PID <PID> /F

# 或者修改docker-compose.yml中的端口映射
# 将 "5432:5432" 改为 "5433:5432"
```

### 问题2：WSL 2未启用

**错误信息**：
```
WSL 2 installation is incomplete
```

**解决方案**：
1. 以管理员身份运行PowerShell
2. 运行以下命令：
```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```
3. 重启电脑
4. 下载并安装WSL 2内核更新：https://aka.ms/wsl2kernel
5. 设置WSL 2为默认版本：
```powershell
wsl --set-default-version 2
```

### 问题3：Docker Engine启动失败

**解决方案**：
1. 完全退出Docker Desktop（右键系统托盘图标 → Quit）
2. 以管理员身份重新启动Docker Desktop
3. 如果仍失败，重启电脑

### 问题4：容器无法连接到数据库

**解决方案**：
```powershell
# 检查容器是否健康
docker inspect xihong_erp_postgres | findstr "Health"

# 查看详细日志
docker logs xihong_erp_postgres

# 重启容器
docker-compose restart postgres
```

## 下一步

完成以上步骤后，PostgreSQL环境就准备好了！可以继续：

1. ✅ Phase 2: 数据库迁移（配置Alembic）
2. ✅ Phase 3: 代码适配（更新连接配置）
3. ✅ Phase 4: 入库逻辑实现
4. ✅ Phase 5: 前端集成
5. ✅ Phase 6: 测试验证

## 参考资源

- Docker Desktop官方文档：https://docs.docker.com/desktop/windows/
- PostgreSQL官方文档：https://www.postgresql.org/docs/15/
- pgAdmin官方文档：https://www.pgadmin.org/docs/
- Docker Compose文档：https://docs.docker.com/compose/

