# SCP 上传重试机制改进报告

**日期**: 2026-01-11  
**问题**: SCP 连接失败 `Connection reset by peer`  
**修复**: 添加重试机制、连接超时配置和 SSH 连接测试

---

## 问题背景

在生产部署过程中，SCP 上传文件时出现连接失败：

```
kex_exchange_identification: read: Connection reset by peer
Connection reset by *** port 22
scp: Connection closed
[FAIL] Failed to upload docker-compose.yml
```

**根本原因**：
- 网络连接不稳定（5MB 带宽服务器的网络波动）
- SSH 服务器暂时不可用或过载
- 没有重试机制，连接失败立即退出

---

## 修复内容

### 1. 添加 SCP 重试函数

**位置**: `.github/workflows/deploy-production.yml` - `Sync compose files to production server` 步骤

**功能**：
- 自动重试 3 次（可配置）
- 每次重试间隔 5 秒
- 添加 `ConnectTimeout=30` 配置
- 提供详细的错误诊断信息

**实现**：
```bash
scp_with_retry() {
  local file="$1"
  local remote_path="$2"
  local max_retries=3
  local retry_delay=5
  
  for i in $(seq 1 ${max_retries}); do
    echo "[INFO] Upload attempt ${i}/${max_retries} for $(basename ${file})..."
    if scp -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=10 \
        -o ConnectTimeout=30 \
        "${file}" ${PRODUCTION_USER}@${PRODUCTION_HOST}:${remote_path}; then
      echo "[OK] $(basename ${file}) uploaded successfully"
      return 0
    else
      if [ ${i} -eq ${max_retries} ]; then
        echo "[FAIL] Failed to upload $(basename ${file}) after ${max_retries} attempts"
        echo "[INFO] Possible causes:"
        echo "  - SSH server is temporarily unavailable"
        echo "  - Network connectivity issues"
        echo "  - SSH connection limit reached"
        echo "[INFO] Please check server SSH service and network status"
        return 1
      else
        echo "[WARN] Upload failed, retrying in ${retry_delay} seconds..."
        sleep ${retry_delay}
      fi
    fi
  done
}
```

### 2. 添加 SSH 连接测试

**功能**：
- 在上传文件前先测试 SSH 连接
- 提前发现连接问题
- 如果测试失败，记录警告但继续尝试（可能是临时问题）

**实现**：
```bash
echo "[INFO] Testing SSH connection..."
if ssh -o StrictHostKeyChecking=no \
    -o ConnectTimeout=10 \
    -o BatchMode=yes \
    ${PRODUCTION_USER}@${PRODUCTION_HOST} \
    "echo '[OK] SSH connection successful'" 2>/dev/null; then
  echo "[OK] SSH connection test passed"
else
  echo "[WARN] SSH connection test failed, but continuing with upload (may be transient issue)..."
fi
```

### 3. 更新所有 SCP 命令

**修改的文件**：
- `deploy-tag` job 的 `Sync compose files to production server` 步骤
- `deploy-manual` job 的 `Sync compose files to production server` 步骤

**修改内容**：
- 所有 SCP 命令都使用 `scp_with_retry` 函数
- 添加 `ConnectTimeout=30` 配置
- 统一错误处理和日志输出

---

## 改进效果

### 之前
- ❌ 连接失败立即退出
- ❌ 没有重试机制
- ❌ 没有连接超时配置
- ❌ 错误信息不够详细

### 现在
- ✅ 自动重试 3 次
- ✅ 每次重试间隔 5 秒
- ✅ 连接超时 30 秒
- ✅ SSH 连接预测试
- ✅ 详细的错误诊断信息

---

## 配置参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `max_retries` | 3 | 最大重试次数 |
| `retry_delay` | 5 | 重试间隔（秒） |
| `ConnectTimeout` | 30 | SSH 连接超时（秒） |
| `ServerAliveInterval` | 30 | 服务器存活检查间隔（秒） |
| `ServerAliveCountMax` | 10 | 最大存活检查次数 |

---

## 使用场景

### 场景 1：临时网络波动

**问题**：网络暂时不稳定，第一次连接失败  
**解决**：自动重试，通常第二次或第三次尝试会成功

### 场景 2：SSH 服务器暂时过载

**问题**：SSH 服务器连接数达到上限  
**解决**：重试机制给服务器时间释放连接

### 场景 3：持续的网络问题

**问题**：网络连接完全不可用  
**解决**：3 次重试后失败，提供详细的错误诊断信息

---

## 故障排查

如果重试 3 次后仍然失败，检查：

1. **服务器 SSH 服务状态**：
   ```bash
   sudo systemctl status sshd
   sudo tail -f /var/log/auth.log
   ```

2. **SSH 配置限制**：
   ```bash
   grep -E "MaxStartups|MaxSessions|MaxAuthTries" /etc/ssh/sshd_config
   ```

3. **当前连接数**：
   ```bash
   netstat -an | grep :22 | grep ESTABLISHED | wc -l
   ```

4. **网络连通性**：
   ```bash
   ping ${PRODUCTION_HOST}
   telnet ${PRODUCTION_HOST} 22
   ```

---

## 相关文件

- `.github/workflows/deploy-production.yml`：修复后的部署工作流
  - `deploy-tag` job：`Sync compose files to production server` 步骤
  - `deploy-manual` job：`Sync compose files to production server` 步骤

---

## 总结

✅ **修复完成**：所有 SCP 上传命令都添加了重试机制  
✅ **连接测试**：添加了 SSH 连接预测试  
✅ **错误处理**：提供详细的错误诊断信息  
✅ **配置优化**：添加连接超时配置

**下一步**：
1. 提交修复后的代码
2. 创建新的 tag（如 `v4.21.8`）触发自动部署
3. 验证 SCP 上传是否更稳定（特别是网络波动时）
