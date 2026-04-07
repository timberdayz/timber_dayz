# 模板数据云端同步指南（方案A：压缩传输优化）

## 概述

本指南介绍如何使用压缩传输方式将本地数据库中的模板数据同步到云端服务器。该方案通过gzip压缩和SSH压缩传输，显著减少传输时间（通常减少70-90%），特别适用于国内外网络环境。

## 前置要求

1. **PostgreSQL客户端工具**：确保已安装PostgreSQL客户端，`pg_dump`命令可用
2. **SSH访问**：确保可以SSH连接到云端服务器
3. **SSH密钥**：确保SSH私钥路径正确（默认：`C:\Users\18689\.ssh\github_actions_deploy`）

## 使用方法

### 方法1：使用批处理文件（推荐）

```batch
cd f:\Vscode\python_programme\AI_code\xihong_erp
scripts\sync_templates_to_cloud.bat -DryRun
```

### 方法2：直接使用PowerShell脚本

```powershell
cd f:\Vscode\python_programme\AI_code\xihong_erp
powershell -ExecutionPolicy Bypass -File scripts\sync_templates_to_cloud.ps1 -DryRun
```

### 方法3：手动执行命令（如果脚本有问题）

#### 步骤1：导出本地模板数据

```powershell
$env:PGPASSWORD="erp_pass_2025"
pg_dump -h localhost -p 15432 -U erp_user -d xihong_erp `
  -t field_mapping_templates `
  --data-only `
  --column-inserts `
  -f temp/templates_export.sql
```

#### 步骤2：压缩SQL文件

```powershell
# 使用PowerShell压缩
$inputFile = [System.IO.File]::OpenRead("temp/templates_export.sql")
$outputFile = [System.IO.File]::Create("temp/templates_export.sql.gz")
$gzipStream = New-Object System.IO.Compression.GZipStream($outputFile, [System.IO.Compression.CompressionMode]::Compress)
$inputFile.CopyTo($gzipStream)
$gzipStream.Close()
$outputFile.Close()
$inputFile.Close()
Remove-Item "temp/templates_export.sql" -Force
```

#### 步骤3：上传到云端服务器

```powershell
scp -i C:\Users\18689\.ssh\github_actions_deploy `
  -o Compression=yes `
  -o StrictHostKeyChecking=no `
  temp/templates_export.sql.gz `
  deploy@134.175.222.171:/tmp/templates_export.sql.gz
```

#### 步骤4：在云端服务器导入

```powershell
ssh -i C:\Users\18689\.ssh\github_actions_deploy `
  -o Compression=yes `
  deploy@134.175.222.171 `
  "cd /opt/xihong_erp && gunzip -c /tmp/templates_export.sql.gz | docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp"
```

#### 步骤5：验证

```powershell
ssh -i C:\Users\18689\.ssh\github_actions_deploy deploy@134.175.222.171 `
  "docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -t -c \"SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE status='published') as published FROM field_mapping_templates;\""
```

#### 步骤6：清理临时文件

```powershell
# 清理本地文件
Remove-Item "temp/templates_export.sql.gz" -Force -ErrorAction SilentlyContinue

# 清理云端文件
ssh -i C:\Users\18689\.ssh\github_actions_deploy deploy@134.175.222.171 "rm -f /tmp/templates_export.sql.gz"
```

## 参数说明

脚本支持以下参数：

- `-SSH_KEY`: SSH私钥路径（默认：`C:\Users\18689\.ssh\github_actions_deploy`）
- `-SSH_USER`: SSH用户名（默认：`deploy`）
- `-SSH_HOST`: 云端服务器地址（默认：`134.175.222.171`）
- `-LOCAL_DB_HOST`: 本地数据库主机（默认：`localhost`）
- `-LOCAL_DB_PORT`: 本地数据库端口（默认：`15432`）
- `-LOCAL_DB_USER`: 本地数据库用户名（默认：`erp_user`）
- `-LOCAL_DB_PASSWORD`: 本地数据库密码（默认：`erp_pass_2025`）
- `-LOCAL_DB_NAME`: 本地数据库名称（默认：`xihong_erp`）
- `-CLOUD_DB_USER`: 云端数据库用户名（默认：`erp_user`）
- `-CLOUD_DB_NAME`: 云端数据库名称（默认：`xihong_erp`）
- `-DryRun`: 模拟模式，只导出不上传

## 优化特性

1. **gzip压缩**：减少传输时间70-90%
2. **SSH压缩传输**：进一步加速传输
3. **自动清理**：自动清理本地和云端临时文件
4. **错误处理**：完善的错误处理和提示

## 故障排除

### 问题1：找不到pg_dump

**解决方案**：
- 确保PostgreSQL客户端已安装
- 将PostgreSQL bin目录添加到PATH环境变量
- 或使用完整路径：`C:\Program Files\PostgreSQL\*\bin\pg_dump.exe`

### 问题2：SSH连接失败

**解决方案**：
- 检查SSH密钥路径是否正确
- 检查SSH密钥权限（Windows上通常不需要特殊权限）
- 检查网络连接和防火墙设置

### 问题3：上传速度慢

**解决方案**：
- 确保启用了SSH压缩（`-o Compression=yes`）
- 检查网络连接质量
- 考虑使用方案B（在服务器上执行迁移）

## 注意事项

1. **数据备份**：在执行同步前，建议先备份云端数据库
2. **数据冲突**：如果云端已有模板数据，导入可能会产生冲突，建议先清空云端模板表
3. **网络稳定性**：确保网络连接稳定，避免传输中断
4. **权限检查**：确保有足够的权限访问数据库和服务器

## 相关文件

- `scripts/sync_templates_to_cloud.ps1`: PowerShell同步脚本
- `scripts/sync_templates_to_cloud.bat`: 批处理包装脚本
- `scripts/migrate_templates_to_container.py`: Python迁移脚本（备用方案）
