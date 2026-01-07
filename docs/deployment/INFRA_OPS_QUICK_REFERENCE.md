# 基础设施与运维工具快速参考

版本: v4.19.7  
更新时间: 2026-01-05

## 概述

本文档提供 Phase 1 & 2 实施的所有工具和脚本的快速参考，包括环境变量管理和数据备份相关工具。

---

## 环境变量管理工具

### 1. 生成环境变量配置文件

```bash
# 生成所有环境的配置文件
python scripts/generate-env-files.py

# 包含 Docker 配置
python scripts/generate-env-files.py --include-docker
```

**生成的文件**:
- `env.example` - 通用示例
- `env.development.example` - 开发环境
- `env.production.example` - 生产环境
- `env.docker.example` - Docker 环境（可选）

**基于模板**: `env.template`（Single Source of Truth）

---

### 2. 验证环境变量配置

```bash
# 基础验证（仅 P0 变量）
python scripts/validate-env.py --env-file .env

# 严格验证（P0 + P1 变量）
python scripts/validate-env.py --env-file .env --strict

# 开发环境（跳过 P1）
python scripts/validate-env.py --env-file .env --skip-p1

# JSON 输出（用于脚本消费）
python scripts/validate-env.py --env-file .env --json
```

**验证内容**:
- P0 变量是否存在
- 变量格式（URL、端口、布尔值）
- 默认密钥检测（生产环境）
- 变量值范围

---

### 3. 生成密钥

```bash
# 仅打印到终端
python scripts/generate-secrets.py --print

# 输出到文件（开发环境）
python scripts/generate-secrets.py --output .env.development

# 输出到文件（生产环境，需手动复制到服务器）
python scripts/generate-secrets.py --output secrets.txt
```

**生成的密钥**:
- `SECRET_KEY` - 应用密钥
- `JWT_SECRET_KEY` - JWT 签名密钥
- `ACCOUNT_ENCRYPTION_KEY` - 账号加密密钥（Fernet）

---

## 数据备份工具

### 1. 统一备份（推荐）

```bash
# 执行完整备份（数据库 + 文件 + 配置）
./scripts/backup_all.sh

# 指定备份目录
BACKUP_BASE_DIR=/backups ./scripts/backup_all.sh

# 指定项目根目录
PROJECT_ROOT=/app ./scripts/backup_all.sh
```

**备份内容**:
- 数据库（通过 `docker exec xihong_erp_postgres pg_dump`）
- 文件存储（`data/`, `uploads/`, `downloads/`, `temp/` 重要子目录）
- 配置文件（`.env` 脱敏、`config/`、`docker-compose*.yml`）
- 备份清单（`manifest.json`）

**备份位置**: `./backups/backup_YYYYMMDD_HHMMSS/`

---

### 2. 数据库备份（独立使用）

```bash
# Host 模式（Linux 宿主机，推荐）
BACKUP_MODE=host ./scripts/backup_database.sh

# Container 模式（容器内部）
BACKUP_MODE=container ./scripts/backup_database.sh

# 指定备份目录
BACKUP_DIR=/backups ./scripts/backup_database.sh
```

---

### 3. 验证备份

```bash
# 验证备份完整性
./scripts/verify_backup.sh ./backups/backup_20260105_020000
```

**验证内容**:
- 数据库备份文件完整性
- 文件备份完整性
- 配置备份完整性
- 校验和比对

---

### 4. 恢复演练（测试环境）

```bash
# 在测试环境中演练恢复流程
ENVIRONMENT=test ./scripts/test_restore.sh ./backups/backup_20260105_020000
```

**安全机制**:
- 环境变量检查（`ENVIRONMENT=test`）
- 交互确认（输入 `YES`）
- 容器命名检查（防止误操作生产环境）

---

## 自动化调度

### Linux Cron（推荐）

```bash
# 配置 cron 任务（每天凌晨 2:00）
./scripts/setup_backup_cron.sh

# 查看任务
crontab -l

# 编辑任务
crontab -e

# 删除任务
crontab -e  # 手动删除对应行
```

**自定义时间**:
```bash
BACKUP_HOUR=3 BACKUP_MINUTE=30 ./scripts/setup_backup_cron.sh
```

---

### Systemd Timer（可选）

```bash
# 1. 复制服务文件
sudo cp docker/systemd/backup.service /etc/systemd/system/
sudo cp docker/systemd/backup.timer /etc/systemd/system/

# 2. 编辑服务文件，修改路径
sudo vi /etc/systemd/system/backup.service

# 3. 启用定时器
sudo systemctl enable backup.timer
sudo systemctl start backup.timer

# 4. 查看状态
sudo systemctl status backup.timer
```

---

## 启动脚本集成

### 开发环境（Windows）

```bash
# 使用 Docker Compose 模式（自动验证环境变量）
python run.py --use-docker
```

**验证行为**:
- 检查 `.env` 文件是否存在
- 运行 `scripts/validate-env.py`（仅 P0 变量）
- 可通过 `SKIP_ENV_VALIDATION=true` 跳过验证

---

### 生产环境（Linux）

```bash
# 使用生产启动脚本（强制验证）
./docker/scripts/start-prod.sh
```

**验证行为**:
- 强制运行 `scripts/validate-env.py --strict`
- 双重检查 `SECRET_KEY` 和 `POSTGRES_PASSWORD`
- 验证失败时阻止启动

---

## Celery 定时任务

### 备份验证任务

```python
# 每天凌晨 4:00 执行
backend.tasks.scheduled_tasks.verify_backup
```

**功能**: 验证最新备份的完整性

---

### 备份清理任务

```python
# 每天凌晨 5:00 执行
backend.tasks.scheduled_tasks.cleanup_old_backups
```

**功能**: 按保留策略（默认 30 天）删除旧备份

---

### 触发系统备份

```python
# 按需执行（手动触发）
backend.tasks.scheduled_tasks.trigger_system_backup
```

**功能**: 从应用层触发系统级备份（调用 `backup_all.sh`）

---

## 常用工作流

### 首次部署

```bash
# 1. 生成环境变量配置文件
python scripts/generate-env-files.py

# 2. 生成密钥
python scripts/generate-secrets.py --print
# 手动复制密钥到 .env

# 3. 验证配置
python scripts/validate-env.py --env-file .env --strict

# 4. 启动服务
python run.py --use-docker  # 开发环境
# 或
./docker/scripts/start-prod.sh  # 生产环境
```

---

### 定期备份

```bash
# 1. 配置自动备份（Linux 服务器）
./scripts/setup_backup_cron.sh

# 2. 手动执行备份（测试）
./scripts/backup_all.sh

# 3. 验证备份
./scripts/verify_backup.sh ./backups/backup_YYYYMMDD_HHMMSS

# 4. 查看备份列表
ls -lth ./backups/ | head -10
```

---

### 恢复数据

```bash
# 1. 验证备份
./scripts/verify_backup.sh ./backups/backup_YYYYMMDD_HHMMSS

# 2. 测试环境演练
ENVIRONMENT=test ./scripts/test_restore.sh ./backups/backup_YYYYMMDD_HHMMSS

# 3. 生产环境恢复（参见 RESTORE_GUIDE.md）
# - 停止服务
# - 恢复数据库
# - 恢复文件
# - 恢复配置
# - 启动服务
```

---

## 文件位置参考

### 环境变量相关

- `env.template` - 主模板（SSOT）
- `scripts/generate-env-files.py` - 生成脚本
- `scripts/validate-env.py` - 验证脚本
- `scripts/generate-secrets.py` - 密钥生成工具
- `docs/deployment/ENVIRONMENT_VARIABLES_REFERENCE.md` - 详细参考文档

### 备份相关

- `scripts/backup_all.sh` - 统一备份脚本
- `scripts/backup_database.sh` - 数据库备份脚本
- `scripts/verify_backup.sh` - 备份验证脚本
- `scripts/test_restore.sh` - 恢复演练脚本
- `scripts/setup_backup_cron.sh` - Cron 配置脚本
- `docker/systemd/backup.service` - Systemd 服务
- `docker/systemd/backup.timer` - Systemd 定时器
- `docs/deployment/BACKUP_STRATEGY.md` - 备份策略文档
- `docs/deployment/RESTORE_GUIDE.md` - 恢复指南文档

---

## 故障排查

### 环境变量验证失败

```bash
# 查看详细错误
python scripts/validate-env.py --env-file .env --strict

# 常见问题：
# 1. SECRET_KEY 太短 → 使用 generate-secrets.py 生成
# 2. DATABASE_URL 格式错误 → 检查连接字符串格式
# 3. 缺少 P0 变量 → 检查 env.template
```

---

### 备份失败

```bash
# 1. 检查 Docker 容器
docker ps | grep xihong_erp_postgres

# 2. 检查备份目录权限
ls -ld ./backups

# 3. 查看备份日志
tail -f ./backups/backup_YYYYMMDD_HHMMSS/backup.log

# 4. 手动测试数据库备份
docker exec xihong_erp_postgres pg_dump -U erp_user -d xihong_erp | head -20
```

---

### 恢复失败

```bash
# 1. 验证备份完整性
./scripts/verify_backup.sh ./backups/backup_YYYYMMDD_HHMMSS

# 2. 检查数据库连接
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT 1"

# 3. 检查文件权限
ls -la data/ uploads/ downloads/

# 4. 查看恢复日志
# （恢复脚本会输出详细日志）
```

---

## 相关文档

- [环境变量参考文档](./ENVIRONMENT_VARIABLES_REFERENCE.md)
- [备份策略](./BACKUP_STRATEGY.md)
- [恢复指南](./RESTORE_GUIDE.md)
- [云端部署环境变量配置清单](./CLOUD_ENVIRONMENT_VARIABLES.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建快速参考文档

