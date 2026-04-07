# 服务器.env配置文件生成和验证指南

**版本**: v4.19.7  
**适用**: 腾讯云2核4G Linux服务器  
**更新时间**: 2025-01-XX

---

## 📋 快速开始

### 方法1：使用生成脚本（推荐）

```bash
# 1. 在本地生成配置文件
python scripts/generate_production_env.py --server-ip YOUR_SERVER_IP

# 2. 验证配置文件
python scripts/validate_production_env.py

# 3. 上传到服务器
scp .env.production user@your-server-ip:/opt/xihong_erp/.env

# 4. 在服务器上验证
ssh user@your-server-ip
cd /opt/xihong_erp
python scripts/validate_production_env.py
```

### 方法2：手动创建

```bash
# 1. 复制模板
cp env.production.cloud.example .env

# 2. 编辑配置文件
nano .env

# 3. 生成密码和密钥
python scripts/check_passwords_and_registry.py --generate
```

---

## 🔧 配置文件生成

### 步骤1：生成配置文件

```bash
# 方式1：交互式（需要输入服务器IP）
python scripts/generate_production_env.py

# 方式2：命令行参数
python scripts/generate_production_env.py --server-ip 123.456.789.0

# 方式3：使用占位符（稍后手动修改）
python scripts/generate_production_env.py --skip-input
```

### 步骤2：检查生成的文件

生成的文件：
- `.env.production` - 生产环境配置文件
- `.env.production.passwords.txt` - 密码和密钥备份（仅用于参考）

**重要**：
- ⚠️ `.env.production.passwords.txt` 包含敏感信息，请妥善保管
- ⚠️ 上传到服务器后，建议删除本地密码文件

---

## ✅ 配置文件验证

### 本地验证

```bash
# 验证配置文件
python scripts/validate_production_env.py
```

验证项：
- ✅ 必需配置（ENVIRONMENT, APP_ENV, HOST等）
- ✅ 安全配置（密码和密钥强度）
- ✅ 性能优化配置（2核4G优化）
- ✅ 服务器配置（IP地址和域名）
- ✅ 功能配置（Playwright, 日志等）

### 服务器验证

```bash
# 1. SSH登录服务器
ssh user@your-server-ip

# 2. 进入项目目录
cd /opt/xihong_erp

# 3. 验证配置文件
python scripts/validate_production_env.py

# 4. 验证Docker Compose配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml config
```

---

## 📝 必须修改的配置项

### 1. 服务器IP地址

```bash
# 修改以下配置项为实际服务器IP
ALLOWED_ORIGINS=http://YOUR_SERVER_IP,https://your-domain.com
ALLOWED_HOSTS=YOUR_SERVER_IP,your-domain.com
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

### 2. 密码和密钥（已自动生成）

如果使用生成脚本，以下配置已自动生成：
- ✅ `POSTGRES_PASSWORD` - 数据库密码
- ✅ `REDIS_PASSWORD` - Redis密码
- ✅ `SECRET_KEY` - 应用密钥
- ✅ `JWT_SECRET_KEY` - JWT签名密钥
- ✅ `ACCOUNT_ENCRYPTION_KEY` - 账号加密密钥

**查看密码**：
```bash
cat .env.production.passwords.txt
```

---

## 🚀 部署到服务器

### 步骤1：上传配置文件

```bash
# 方式1：使用SCP
scp .env.production user@your-server-ip:/opt/xihong_erp/.env

# 方式2：使用SFTP
sftp user@your-server-ip
put .env.production /opt/xihong_erp/.env
exit

# 方式3：在服务器上直接创建
ssh user@your-server-ip
cd /opt/xihong_erp
nano .env
# 粘贴配置文件内容
```

### 步骤2：设置文件权限

```bash
# 在服务器上执行
chmod 600 .env  # 仅所有者可读写
chown $USER:$USER .env
```

### 步骤3：验证配置

```bash
# 在服务器上执行
cd /opt/xihong_erp
python scripts/validate_production_env.py
```

### 步骤4：测试Docker Compose配置

```bash
# 在服务器上执行
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml config
```

---

## 🔍 验证检查清单

### 必需配置检查

- [ ] `ENVIRONMENT=production`
- [ ] `APP_ENV=production`
- [ ] `HOST=0.0.0.0`
- [ ] `POSTGRES_PASSWORD` 已设置（强密码，至少24位）
- [ ] `SECRET_KEY` 已设置（32位随机字符串）
- [ ] `JWT_SECRET_KEY` 已设置（32位随机字符串）
- [ ] `ACCOUNT_ENCRYPTION_KEY` 已设置（Fernet密钥）
- [ ] `REDIS_PASSWORD` 已设置（强密码，至少16位）

### 服务器配置检查

- [ ] `ALLOWED_ORIGINS` 已修改为实际服务器IP
- [ ] `ALLOWED_HOSTS` 已修改为实际服务器IP
- [ ] `VITE_API_URL` 已修改为实际服务器IP和端口

### 性能优化检查

- [ ] `DB_POOL_SIZE=10`（2核4G优化）
- [ ] `DB_MAX_OVERFLOW=20`（2核4G优化）
- [ ] `MAX_CONCURRENT_TASKS=2`（2核4G优化）

### 功能配置检查

- [ ] `PLAYWRIGHT_HEADLESS=true`
- [ ] `VITE_MODE=production`
- [ ] `DATABASE_ECHO=false`
- [ ] `LOG_LEVEL=INFO`

---

## ⚠️ 安全注意事项

### 1. 密码管理

- ✅ **必须**：使用强随机密码（至少24位）
- ✅ **必须**：妥善保管密码文件
- ❌ **禁止**：在代码中硬编码密码
- ❌ **禁止**：将密码文件提交到Git仓库

### 2. 文件权限

```bash
# 设置正确的文件权限
chmod 600 .env  # 仅所有者可读写
chmod 600 .env.production.passwords.txt  # 密码文件
```

### 3. 备份管理

- ✅ 备份配置文件到安全位置
- ✅ 定期更换密码和密钥
- ✅ 使用密码管理器存储密码

---

## 🔄 更新配置

### 修改服务器IP

```bash
# 在服务器上编辑
nano /opt/xihong_erp/.env

# 修改以下配置
ALLOWED_ORIGINS=http://新IP地址
ALLOWED_HOSTS=新IP地址
VITE_API_URL=http://新IP地址:8000

# 重启服务
docker-compose restart
```

### 更换密码

```bash
# 1. 生成新密码
python scripts/generate_production_env.py --skip-input

# 2. 查看新密码
cat .env.production.passwords.txt

# 3. 更新服务器上的.env文件
# 4. 重启服务
docker-compose restart
```

---

## 📚 相关文档

- [环境配置对比](./ENV_DEVELOPMENT_VS_PRODUCTION.md)
- [生产环境配置指南](./PRODUCTION_ENV_CONFIG.md)
- [快速部署指南](./QUICK_DEPLOYMENT_GUIDE.md)
- [部署测试报告](./DEPLOYMENT_TEST_REPORT.md)

---

**最后更新**: 2025-01-XX
