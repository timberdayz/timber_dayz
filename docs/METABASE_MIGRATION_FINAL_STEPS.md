# Metabase迁移最终步骤

## ⚠️ 当前问题

**Python脚本连接到了本地PostgreSQL，而不是Docker PostgreSQL**

- 本地PostgreSQL：PostgreSQL 18.0 on Windows（已迁移，有表）
- Docker PostgreSQL：PostgreSQL 15.14 on Alpine Linux（未迁移，无表）
- Metabase连接：Docker PostgreSQL（所以看不到新表）

## 🔧 解决方案

### 方案1：停止本地PostgreSQL服务（推荐）

1. **查找PostgreSQL服务**
   ```powershell
   Get-Service | Where-Object {$_.DisplayName -like "*PostgreSQL*"}
   ```

2. **停止服务**（根据实际服务名调整）
   ```powershell
   Stop-Service postgresql-x64-18
   # 或
   Stop-Service postgresql-x64-15
   ```

3. **验证端口释放**
   ```powershell
   netstat -ano | Select-String ":5432"
   # 应该只剩下Docker容器的端口
   ```

4. **重新运行迁移**
   ```bash
   python temp/development/force_migrate_docker.py
   ```

### 方案2：使用Docker网络IP连接

如果必须保留本地PostgreSQL，可以使用Docker网络内部IP：

1. **获取Docker PostgreSQL IP**
   ```bash
   docker inspect xihong_erp_postgres --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
   ```

2. **修改迁移脚本使用Docker IP**
   ```python
   DOCKER_DB_URL = "postgresql://erp_user:erp_pass_2025@172.28.0.5:5432/xihong_erp"
   ```

3. **运行迁移**

## 📋 验证步骤

### 1. 确认连接到Docker PostgreSQL

```bash
python -c "from sqlalchemy import create_engine, text; engine = create_engine('postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp'); conn = engine.connect(); result = conn.execute(text('SELECT version()')); print(result.scalar())"
```

**期望输出**：应该包含 "Alpine" 或 "musl"（Docker PostgreSQL）

### 2. 执行迁移

```bash
python temp/development/force_migrate_docker.py
```

### 3. 验证Docker PostgreSQL中的表

```bash
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name LIKE 'fact_raw_data%';"
```

**期望结果**：13

### 4. 在Metabase中同步Schema

1. 访问 http://localhost:3000
2. Admin → Databases → XIHONG_ERP
3. 点击 "Sync database schema now"
4. 验证新表出现

## ⚠️ 注意事项

1. **端口冲突**：本地PostgreSQL和Docker PostgreSQL都在5432端口，但通过不同方式访问
2. **数据持久化**：Docker PostgreSQL数据存储在Docker卷中，重启容器不会丢失数据
3. **服务自动启动**：Windows PostgreSQL服务可能设置为自动启动，需要手动停止

## 📚 相关文档

- `docs/METABASE_MIGRATION_SUCCESS.md` - 迁移成功报告
- `docs/METABASE_MIGRATION_STATUS.md` - 迁移状态报告
- `temp/development/force_migrate_docker.py` - 强制迁移脚本

---

**最后更新**: 2025-11-26 17:00  
**状态**: ⏳ 等待停止本地PostgreSQL服务

