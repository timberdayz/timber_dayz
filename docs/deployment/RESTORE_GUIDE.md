# 数据恢复指南

版本: v4.19.7  
更新时间: 2026-01-05

## 概述

本文档描述西虹ERP系统的数据恢复流程，包括：
- 数据库恢复
- 文件恢复
- 配置恢复
- 完整灾难恢复流程

**⚠️ 重要提示**:
- 恢复操作会覆盖现有数据，请先备份当前数据
- 生产环境恢复需要停机维护窗口
- 建议先在测试环境演练恢复流程

---

## 前置检查

### 1. 确认备份可用

```bash
# 验证备份完整性
./scripts/verify_backup.sh ./backups/backup_20260105_020000
```

### 2. 备份当前数据

```bash
# 备份当前数据（防止恢复失败）
./scripts/backup_all.sh
```

### 3. 确认恢复环境

- **测试环境**: 使用 `ENVIRONMENT=test` 和恢复演练脚本
- **生产环境**: 需要停机维护，多重确认

---

## 数据库恢复

### 方法 1: 使用 pg_restore（推荐）

```bash
# 1. 停止应用服务
docker-compose stop backend celery-worker

# 2. 解压备份文件
gunzip -c ./backups/backup_20260105_020000/database.sql.gz > /tmp/restore.sql

# 3. 恢复数据库（方式 A：清空后恢复）
docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp <<EOF
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO erp_user;
GRANT ALL ON SCHEMA public TO public;
EOF

docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < /tmp/restore.sql

# 4. 验证恢复
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM accounts;"

# 5. 启动应用服务
docker-compose start backend celery-worker
```

### 方法 2: 使用临时数据库验证

```bash
# 1. 创建临时数据库
docker exec xihong_erp_postgres psql -U erp_user -c "CREATE DATABASE xihong_erp_restore_test;"

# 2. 恢复到临时数据库
gunzip -c ./backups/backup_20260105_020000/database.sql.gz | \
    docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp_restore_test

# 3. 验证数据
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp_restore_test -c "SELECT COUNT(*) FROM accounts;"

# 4. 确认无误后，再恢复到生产数据库（参考方法 1）
```

---

## 文件恢复

### 恢复文件存储

```bash
# 1. 停止应用服务（可选，避免文件冲突）
docker-compose stop backend

# 2. 备份当前文件（防止覆盖）
mv data data_backup_$(date +%Y%m%d_%H%M%S)
mv uploads uploads_backup_$(date +%Y%m%d_%H%M%S)
mv downloads downloads_backup_$(date +%Y%m%d_%H%M%S)

# 3. 恢复文件
tar -xzf ./backups/backup_20260105_020000/files.tar.gz -C ./

# 4. 验证文件
ls -lh data/ uploads/ downloads/

# 5. 启动应用服务
docker-compose start backend
```

---

## 配置恢复

### 恢复配置文件

```bash
# 1. 备份当前配置
cp .env .env.backup_$(date +%Y%m%d_%H%M%S)

# 2. 解压配置备份
tar -xzf ./backups/backup_20260105_020000/config.tar.gz -C /tmp/

# 3. 查看恢复的配置（注意：已脱敏）
cat /tmp/config_backup/.env.redacted

# 4. 手动恢复配置（因为已脱敏，需要手动填入敏感信息）
# 复制非敏感配置
cp /tmp/config_backup/.env.redacted .env
# 手动编辑 .env，填入 SECRET_KEY、JWT_SECRET_KEY 等敏感信息

# 5. 恢复 docker-compose 配置（如果需要）
cp /tmp/config_backup/docker-compose*.yml ./
```

---

## 完整灾难恢复流程

### 场景：生产环境完全恢复

```bash
# ============================================
# 步骤 1: 前置准备
# ============================================

# 1.1 确认备份可用
./scripts/verify_backup.sh ./backups/backup_20260105_020000

# 1.2 备份当前数据（防止恢复失败）
./scripts/backup_all.sh

# 1.3 停止所有服务
docker-compose down

# ============================================
# 步骤 2: 数据库恢复
# ============================================

# 2.1 启动数据库服务（仅数据库）
docker-compose up -d postgres

# 2.2 等待数据库就绪
sleep 10

# 2.3 恢复数据库
gunzip -c ./backups/backup_20260105_020000/database.sql.gz | \
    docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp

# 2.4 验证数据库
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "\dt"

# ============================================
# 步骤 3: 文件恢复
# ============================================

# 3.1 恢复文件
tar -xzf ./backups/backup_20260105_020000/files.tar.gz -C ./

# 3.2 验证文件
ls -lh data/ uploads/ downloads/

# ============================================
# 步骤 4: 配置恢复
# ============================================

# 4.1 恢复配置（注意脱敏）
tar -xzf ./backups/backup_20260105_020000/config.tar.gz -C /tmp/
# 手动编辑 .env，填入敏感信息

# ============================================
# 步骤 5: 启动服务
# ============================================

# 5.1 启动所有服务
docker-compose up -d

# 5.2 健康检查
curl http://localhost:8001/health

# 5.3 验证功能
# - 登录系统
# - 检查关键数据
# - 检查文件上传/下载

# ============================================
# 步骤 6: 回滚准备（如果恢复失败）
# ============================================

# 6.1 如果恢复失败，使用步骤 1.2 的备份回滚
# （重复步骤 2-5，使用步骤 1.2 的备份）
```

---

## 恢复演练（测试环境）

### 使用恢复演练脚本

```bash
# 在测试环境中演练恢复流程
ENVIRONMENT=test ./scripts/test_restore.sh ./backups/backup_20260105_020000
```

**脚本特性**:
- 多重防护机制（环境变量 + 交互确认）
- 仅在测试环境执行
- 不覆盖生产数据
- 生成恢复报告

---

## 回滚策略

### 如果恢复失败

1. **停止恢复操作**
   ```bash
   docker-compose down
   ```

2. **使用恢复前的备份**
   ```bash
   # 使用步骤 1.2 创建的备份
   ./scripts/test_restore.sh ./backups/backup_before_restore_YYYYMMDD_HHMMSS
   ```

3. **验证回滚结果**
   ```bash
   docker-compose up -d
   curl http://localhost:8001/health
   ```

---

## 常见问题

### Q1: 数据库恢复失败，提示权限错误

**解决**:
```bash
# 检查数据库用户权限
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "\du"

# 重新授权
docker exec xihong_erp_postgres psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE xihong_erp TO erp_user;"
```

### Q2: 文件恢复后权限不正确

**解决**:
```bash
# 修复文件权限
chown -R appuser:appuser data/ uploads/ downloads/
chmod -R 755 data/ uploads/ downloads/
```

### Q3: 配置恢复后服务无法启动

**解决**:
1. 检查 `.env` 文件格式
2. 确认所有敏感信息已正确填入
3. 运行环境变量验证：`python scripts/validate-env.py --env-file .env --strict`

---

## 相关文档

- [备份策略](./BACKUP_STRATEGY.md)
- [环境变量配置](./ENVIRONMENT_VARIABLES_REFERENCE.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建恢复指南文档

