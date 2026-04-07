# Nginx 到后端 400 Bad Request 错误排查指南

**问题**: Nginx 代理到后端时返回 `400 Bad Request`，错误信息为 "Invalid host header"

**根本原因**: `backend/utils/config.py` 中的 `ALLOWED_HOSTS` 配置硬编码，无法从环境变量读取

**修复状态**: ✅ 已修复（需要重新构建和部署镜像）

---

## 📋 快速验证步骤

### 在服务器上执行以下命令验证当前状态：

```bash
cd /opt/xihong_erp

# 步骤1: 检查后端应用实际使用的配置
docker exec xihong_erp_backend python -c "
from backend.utils.config import get_settings
settings = get_settings()
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
"

# 步骤2: 检查后端容器环境变量
docker exec xihong_erp_backend env | grep ALLOWED_HOSTS

# 步骤3: 测试 Nginx 到后端的连接
docker exec xihong_erp_nginx wget -O- http://backend:8000/health 2>&1 | head -5
```

### 预期结果

#### ✅ 如果代码已更新（修复生效）
- 步骤1 输出: `ALLOWED_HOSTS: ['localhost', '127.0.0.1', 'backend', '134.175.222.171', ...]`（包含 backend）
- 步骤3 输出: 返回 JSON 响应（`{"status": "healthy", ...}`）或 200 OK

#### ❌ 如果代码未更新（修复未生效）
- 步骤1 输出: `ALLOWED_HOSTS: ['localhost', '127.0.0.1']`（只有默认值，不包含 backend）
- 步骤3 输出: `wget: server returned error: HTTP/1.1 400 Bad Request`

---

## 🔍 完整诊断脚本

执行诊断脚本（自动检查所有相关配置）：

```bash
cd /opt/xihong_erp
bash scripts/diagnose_nginx_backend_connection.sh
```

---

## 🔧 修复步骤（如果代码未更新）

如果验证结果显示代码未更新，需要重新构建和部署：

### 方法1: 通过 GitHub Actions（推荐）

1. **确认代码已提交并推送**
   ```bash
   # 本地检查
   git status
   git log --oneline -5
   ```

2. **触发构建和部署**
   - 推送代码到 `main` 分支 → 自动构建镜像
   - 创建并推送版本标签 → 自动部署
     ```bash
     git tag v4.22.28
     git push origin v4.22.28
     ```

3. **等待部署完成**（查看 GitHub Actions）

4. **在服务器上重新创建后端容器**
   ```bash
   cd /opt/xihong_erp
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate backend
   sleep 20
   
   # 验证修复
   docker exec xihong_erp_backend python -c "
   from backend.utils.config import get_settings
   settings = get_settings()
   print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
   "
   ```

### 方法2: 手动构建和部署（紧急情况）

如果 GitHub Actions 不可用，可以手动构建：

```bash
# 在服务器上
cd /opt/xihong_erp

# 拉取最新代码
git pull origin main

# 重新构建后端镜像
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build backend

# 重新创建容器
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate backend

# 验证
sleep 20
docker exec xihong_erp_backend python -c "
from backend.utils.config import get_settings
settings = get_settings()
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
"
```

---

## ✅ 验证修复成功

修复成功后，应该看到：

1. **配置包含 backend**
   ```bash
   docker exec xihong_erp_backend python -c "
   from backend.utils.config import get_settings
   settings = get_settings()
   print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
   "
   # 输出应该包含 'backend'
   ```

2. **健康检查通过**
   ```bash
   docker exec xihong_erp_nginx wget -O- http://backend:8000/health 2>&1
   # 应该返回 JSON 响应，而不是 400 Bad Request
   ```

3. **前端可以正常访问**
   - 浏览器访问网站，应该可以正常登录和使用

---

## 📝 修复内容总结

### 修复的文件
- `backend/utils/config.py`

### 修复的配置项
1. **ALLOWED_HOSTS**: 从硬编码改为从环境变量读取
2. **ALLOWED_ORIGINS**: 从硬编码改为从环境变量读取

### 修复前后对比

**修复前（硬编码）**:
```python
ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
ALLOWED_ORIGINS: List[str] = ["http://localhost:8080", ...]
```

**修复后（从环境变量读取）**:
```python
_allowed_hosts_str = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1")
ALLOWED_HOSTS: List[str] = [h.strip() for h in _allowed_hosts_str.split(",") if h.strip()]

_allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "默认值...")
ALLOWED_ORIGINS: List[str] = [o.strip() for o in _allowed_origins_str.split(",") if o.strip()]
```

---

## 🔗 相关文档

- [部署指南](deployment/DEPLOYMENT_GUIDE.md)
- [配置管理指南](deployment/DOCKER_COMPOSE_CONFIG_MANAGEMENT.md)
