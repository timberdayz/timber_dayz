# 数据备份策略

版本: v4.19.7  
更新时间: 2026-01-05

## 概述

本文档描述西虹ERP系统的数据备份策略，包括：
- 备份频率和保留策略
- 备份内容（数据库、文件、配置）
- 自动化调度
- 备份验证
- 云存储策略（可选）

---

## 备份内容

### 数据库备份

- **内容**: PostgreSQL 数据库完整备份
- **格式**: SQL 格式（gzip 压缩）
- **脚本**: `scripts/backup_database.sh`
- **执行方式**: 通过 `docker exec xihong_erp_postgres pg_dump`（宿主机视角）

### 文件存储备份

- **内容**:
  - `data/` - 业务数据目录
  - `uploads/` - 上传文件
  - `downloads/` - 下载文件
  - `temp/outputs/`, `temp/cache/`, `temp/logs/` - 重要临时文件
- **格式**: tar.gz 归档
- **脚本**: `scripts/backup_all.sh`（集成）

### 配置备份

- **内容**:
  - `.env` - 环境变量（已脱敏）
  - `config/` - 配置文件（排除敏感文件）
  - `docker-compose*.yml` - Docker Compose 配置
- **格式**: tar.gz 归档（已脱敏）
- **脚本**: `scripts/backup_all.sh`（集成）

---

## 备份频率

### 生产环境

- **全量备份**: 每天凌晨 2:00
- **保留策略**: 30 天
- **自动清理**: 超过 30 天的备份自动删除

### 开发/测试环境

- **全量备份**: 每周一次（可选）
- **保留策略**: 7 天

---

## 自动化调度

### Linux Cron（推荐）

```bash
# 配置 cron 任务
./scripts/setup_backup_cron.sh

# 查看任务
crontab -l

# 编辑任务
crontab -e
```

**默认配置**: 每天凌晨 2:00 执行

### Systemd Timer（可选）

```bash
# 安装服务
sudo cp docker/systemd/backup.service /etc/systemd/system/
sudo cp docker/systemd/backup.timer /etc/systemd/system/

# 修改路径（编辑 backup.service）
sudo vi /etc/systemd/system/backup.service

# 启用定时器
sudo systemctl enable backup.timer
sudo systemctl start backup.timer

# 查看状态
sudo systemctl status backup.timer
```

---

## 备份验证

### 自动验证

每次备份完成后自动验证：
- 数据库备份：`gunzip -t` 检查完整性
- 文件备份：`tar -tzf` 检查完整性
- 配置备份：`tar -tzf` 检查完整性

### 手动验证

```bash
# 验证备份
./scripts/verify_backup.sh ./backups/backup_20260105_020000
```

**验证内容**:
- 备份文件完整性
- 数据库备份格式
- 文件备份校验和
- 配置备份校验和

---

## 备份清单

每次备份生成 `manifest.json`，包含：
- 备份时间戳
- 备份类型（full/incremental）
- 文件列表和大小
- 系统信息

**示例**:
```json
{
  "backup_timestamp": "20260105_020000",
  "backup_date": "2026-01-05T02:00:00+08:00",
  "backup_type": "full",
  "files": [
    {"type": "database", "file": "database.sql.gz", "size": "150M"},
    {"type": "files", "file": "files.tar.gz", "size": "500M"},
    {"type": "config", "file": "config.tar.gz", "size": "1M"}
  ],
  "system_info": {
    "hostname": "server01",
    "user": "root"
  }
}
```

---

## 云存储策略（P2 可选）

### 支持的后端

- 阿里云 OSS
- AWS S3
- 腾讯云 COS

### 配置

在 `backup_all.sh` 中设置：
```bash
ENABLE_CLOUD_BACKUP=true
CLOUD_BACKEND=oss  # 或 s3, cos
```

### 上传脚本

```bash
# 上传备份到云存储
python scripts/upload_backup_to_cloud.py \
    --backup-dir ./backups/backup_20260105_020000 \
    --backend oss
```

---

## 备份恢复

详细恢复流程参见 [恢复指南](./RESTORE_GUIDE.md)。

### 快速恢复

```bash
# 1. 验证备份
./scripts/verify_backup.sh ./backups/backup_20260105_020000

# 2. 恢复演练（测试环境）
ENVIRONMENT=test ./scripts/test_restore.sh ./backups/backup_20260105_020000

# 3. 生产恢复（手动执行，参见 RESTORE_GUIDE.md）
```

---

## 监控和告警

### 备份失败告警

- 备份脚本返回非零退出码时记录日志
- 可通过 Celery 定时任务检查备份状态
- 预留邮件/Webhook 通知接口

### 备份状态检查

```bash
# 检查最新备份
ls -lth ./backups/ | head -5

# 检查备份日志
tail -f ./logs/backup_cron.log
```

---

## 相关文档

- [恢复指南](./RESTORE_GUIDE.md)
- [环境变量配置](./ENVIRONMENT_VARIABLES_REFERENCE.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建统一备份策略文档

