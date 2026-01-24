# 快速验证 Nginx 后端连接修复

## 🎯 核心验证命令（在服务器上执行）

```bash
cd /opt/xihong_erp

# ⭐ 最关键：检查后端应用实际使用的配置
docker exec xihong_erp_backend python -c "
from backend.utils.config import get_settings
settings = get_settings()
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
"
```

### 结果判断

- ✅ **修复生效**：输出包含 `'backend'`，例如：
  ```
  ALLOWED_HOSTS: ['localhost', '127.0.0.1', 'backend', '134.175.222.171', ...]
  ```

- ❌ **修复未生效**：输出只有默认值，例如：
  ```
  ALLOWED_HOSTS: ['localhost', '127.0.0.1']
  ```

---

## 📋 完整验证步骤

### 步骤1: 验证后端配置（最重要）

```bash
docker exec xihong_erp_backend python -c "
from backend.utils.config import get_settings
settings = get_settings()
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
print('类型:', type(settings.ALLOWED_HOSTS))
"
```

### 步骤2: 验证环境变量

```bash
docker exec xihong_erp_backend env | grep ALLOWED_HOSTS
```

### 步骤3: 测试健康检查

```bash
docker exec xihong_erp_nginx wget -O- http://backend:8000/health 2>&1 | head -10
```

### 步骤4: 检查后端日志

```bash
docker logs xihong_erp_backend 2>&1 | tail -30 | grep -i "invalid host\|trustedhost\|400" | head -5
```

---

## 🔧 如果修复未生效（需要重新部署）

### 检查代码是否已提交

```bash
# 在本地检查
git log --oneline -5 | grep -i "allowed_hosts\|config"
```

### 重新部署步骤

1. **确认代码已推送**（本地执行）
   ```bash
   git status
   git push origin main
   ```

2. **触发构建和部署**
   - 方式1: 推送代码到 main → 自动构建
   - 方式2: 创建并推送标签 → 自动部署
     ```bash
     git tag v4.22.28
     git push origin v4.22.28
     ```

3. **在服务器上重新创建容器**（等待构建完成后）
   ```bash
   cd /opt/xihong_erp
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate backend
   sleep 20
   ```

4. **再次验证**
   ```bash
   docker exec xihong_erp_backend python -c "
   from backend.utils.config import get_settings
   settings = get_settings()
   print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
   "
   ```

---

## 📊 诊断脚本（一键检查）

```bash
cd /opt/xihong_erp
bash scripts/diagnose_nginx_backend_connection.sh
```

---

## ✅ 修复成功的标志

1. ✅ 后端配置包含 `'backend'`
2. ✅ 健康检查返回 JSON（不是 400）
3. ✅ 前端可以正常访问和登录
