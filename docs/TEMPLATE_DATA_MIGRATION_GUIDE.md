# 模板数据迁移指南

## 问题诊断

容器化后看不到之前设置的模板，是因为：

1. **数据库实例不同**：容器数据库是新创建的独立实例
2. **数据未迁移**：之前创建的模板数据在本地数据库，未迁移到容器数据库

## 检查数据状态

### 1. 检查容器数据库

```bash
# 检查容器数据库中的模板数量
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c \
  "SELECT COUNT(*) as total_templates, COUNT(*) FILTER (WHERE status='published') as published FROM field_mapping_templates;"

# 查看模板详情
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c \
  "SELECT id, template_name, platform, data_domain, status FROM field_mapping_templates LIMIT 10;"
```

### 2. 使用诊断脚本

```bash
# 运行诊断脚本检查两个数据库
python scripts/check_template_data.py
```

## 迁移方案

### 方案1：使用Python迁移脚本（推荐）

如果您的模板数据在另一个PostgreSQL数据库中：

```bash
# 1. 设置环境变量（可选，或直接修改脚本中的默认值）
export LOCAL_DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/local_database"
export CONTAINER_DATABASE_URL="postgresql+asyncpg://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev"

# 2. 先进行模拟运行（不会实际修改数据库）
python scripts/migrate_templates_to_container.py --dry-run

# 3. 确认无误后执行实际迁移
python scripts/migrate_templates_to_container.py
```

### 方案2：使用pg_dump和psql（SQL方式）

如果您有本地PostgreSQL数据库的访问权限：

#### 步骤1：导出模板数据

```bash
# 从本地数据库导出模板表和模板项表
pg_dump -h localhost -p 5432 -U your_user -d your_database \
  -t field_mapping_templates \
  -t field_mapping_template_items \
  --data-only \
  --column-inserts \
  > templates_backup.sql
```

#### 步骤2：导入到容器数据库

```bash
# 方式1：通过psql命令导入（从宿主机）
psql -h localhost -p 15432 -U erp_dev -d xihong_erp_dev -f templates_backup.sql

# 方式2：通过Docker容器导入
cat templates_backup.sql | docker exec -i xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev
```

### 方案3：使用pgAdmin图形界面

1. **连接到源数据库**（本地PostgreSQL）
   - 打开pgAdmin
   - 连接到包含模板数据的数据库

2. **导出数据**
   - 右键点击 `field_mapping_templates` 表
   - 选择 "备份"
   - 选择 "仅数据" 模式
   - 导出为SQL文件

3. **连接到容器数据库**
   - 添加新服务器连接
   - 主机: `localhost`
   - 端口: `15432`
   - 数据库: `xihong_erp_dev`
   - 用户名: `erp_dev`
   - 密码: `dev_pass_2025`

4. **导入数据**
   - 右键点击 `xihong_erp_dev` 数据库
   - 选择 "查询工具"
   - 执行导出的SQL文件

### 方案4：直接从系统前端重新创建（最简单）

如果您记得之前的模板配置：

1. 打开前端界面：http://localhost:5173
2. 进入"数据同步" -> "模板管理"
3. 重新创建模板（使用之前的配置）

## 验证迁移结果

迁移完成后，验证数据：

```bash
# 1. 检查模板数量
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c \
  "SELECT COUNT(*) FROM field_mapping_templates WHERE status='published';"

# 2. 检查模板项数量
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c \
  "SELECT COUNT(*) FROM field_mapping_template_items;"

# 3. 在前端验证
# 访问 http://localhost:5173/data-sync/templates
# 应该能看到迁移的模板列表
```

## 常见问题

### Q1: 本地没有PostgreSQL，模板数据在哪里？

如果之前使用的是SQLite数据库，模板数据在：
- `data/erp_system.db` 文件中

迁移步骤：
1. 使用SQLite工具（如DB Browser for SQLite）打开 `data/erp_system.db`
2. 导出 `field_mapping_templates` 和 `field_mapping_template_items` 表数据为CSV或SQL
3. 转换为PostgreSQL格式后导入容器数据库

### Q2: 迁移后模板还是看不到？

检查以下几点：
1. 模板状态是否为 `published`（只有已发布的模板才会显示）
2. 前端是否刷新了页面
3. 检查浏览器控制台是否有错误
4. 检查后端日志：`docker logs xihong_erp_backend_dev`

### Q3: 迁移时遇到外键约束错误？

解决方法：
1. 先迁移 `field_mapping_templates` 表
2. 再迁移 `field_mapping_template_items` 表

或者临时禁用外键检查：
```sql
-- 在PostgreSQL中（不推荐，除非必要）
ALTER TABLE field_mapping_template_items DROP CONSTRAINT IF EXISTS field_mapping_template_items_template_id_fkey;
-- 导入数据后重新创建外键
ALTER TABLE field_mapping_template_items ADD CONSTRAINT field_mapping_template_items_template_id_fkey 
  FOREIGN KEY (template_id) REFERENCES field_mapping_templates(id);
```

## 长期解决方案

为了避免每次容器重建都丢失数据：

1. **使用Docker Volume持久化**（已配置）
   - 容器数据库数据存储在Docker Volume中
   - 只要Volume不被删除，数据会保留

2. **定期备份**
   ```bash
   # 备份容器数据库
   docker exec xihong_erp_postgres pg_dump -U erp_dev -d xihong_erp_dev | gzip > backup_$(date +%Y%m%d).sql.gz
   ```

3. **统一使用容器数据库**
   - 开发时也使用容器数据库（`localhost:15432`）
   - 保持数据一致性

## 快速检查命令

```bash
# 一键检查脚本
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "
SELECT 
  '模板总数' as type, COUNT(*)::text as count 
FROM field_mapping_templates
UNION ALL
SELECT 
  '已发布模板', COUNT(*)::text 
FROM field_mapping_templates 
WHERE status='published'
UNION ALL
SELECT 
  '模板项总数', COUNT(*)::text 
FROM field_mapping_template_items;
"
```

