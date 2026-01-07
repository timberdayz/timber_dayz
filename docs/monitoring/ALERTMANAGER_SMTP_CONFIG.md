# AlertManager SMTP 配置指南

> **创建日期**: 2026-01-04  
> **适用版本**: v4.19.0+

## 概述

AlertManager 用于接收 Prometheus 的告警并发送通知。本指南说明如何配置 SMTP 邮件通知。

## 配置方式

AlertManager 不支持在 YAML 配置文件中直接使用环境变量（如 `${VAR:-default}`），因此有两种配置方式：

### 方式 1: 手动编辑配置文件（推荐用于生产环境）

1. **编辑配置文件**

   编辑 `monitoring/alertmanager.yml`，修改以下配置项：

   ```yaml
   global:
     smtp_smarthost: 'smtp.example.com:587'  # 修改为实际 SMTP 服务器
     smtp_from: 'alerts@example.com'        # 修改为实际发件人邮箱
     smtp_auth_username: 'alerts@example.com'  # 修改为实际 SMTP 用户名
     smtp_auth_password: 'your_smtp_password_here'  # 修改为实际 SMTP 密码
   ```

2. **配置收件人邮箱**

   在 `receivers` 部分修改收件人邮箱：

   ```yaml
   receivers:
     - name: 'default'
       email_configs:
         - to: 'ops-team@example.com'  # 修改为实际收件人
   
     - name: 'critical'
       email_configs:
         - to: 'critical-alerts@example.com'  # 修改为实际收件人
   
     - name: 'celery'
       email_configs:
         - to: 'celery-alerts@example.com'  # 修改为实际收件人
   ```

3. **重启 AlertManager**

   ```bash
   docker-compose -f docker/docker-compose.monitoring.yml restart alertmanager
   ```

### 方式 2: 使用环境变量（需要 envsubst 工具）

如果需要在部署时动态替换配置，可以使用 `envsubst` 工具：

1. **创建配置模板**

   创建 `monitoring/alertmanager.yml.template`：

   ```yaml
   global:
     smtp_smarthost: '${SMTP_HOST}'
     smtp_from: '${SMTP_FROM}'
     smtp_auth_username: '${SMTP_USERNAME}'
     smtp_auth_password: '${SMTP_PASSWORD}'
   ```

2. **使用 envsubst 生成配置**

   在启动前运行：

   ```bash
   envsubst < monitoring/alertmanager.yml.template > monitoring/alertmanager.yml
   ```

3. **设置环境变量**

   在 `.env` 文件中设置：

   ```bash
   SMTP_HOST=smtp.example.com:587
   SMTP_FROM=alerts@example.com
   SMTP_USERNAME=alerts@example.com
   SMTP_PASSWORD=your_password
   ```

## 常见 SMTP 服务商配置

### Gmail

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'your-email@gmail.com'
  smtp_auth_username: 'your-email@gmail.com'
  smtp_auth_password: 'your-app-password'  # 需要使用应用专用密码
```

**注意**: Gmail 需要使用[应用专用密码](https://support.google.com/accounts/answer/185833)，不能使用普通密码。

### 腾讯企业邮箱

```yaml
global:
  smtp_smarthost: 'smtp.exmail.qq.com:465'
  smtp_from: 'alerts@your-domain.com'
  smtp_auth_username: 'alerts@your-domain.com'
  smtp_auth_password: 'your_password'
```

### 阿里企业邮箱

```yaml
global:
  smtp_smarthost: 'smtp.mxhichina.com:465'
  smtp_from: 'alerts@your-domain.com'
  smtp_auth_username: 'alerts@your-domain.com'
  smtp_auth_password: 'your_password'
```

### 163 邮箱

```yaml
global:
  smtp_smarthost: 'smtp.163.com:465'
  smtp_from: 'your-email@163.com'
  smtp_auth_username: 'your-email@163.com'
  smtp_auth_password: 'your_auth_code'  # 需要使用授权码
```

## 验证配置

### 1. 检查 AlertManager 配置

```bash
# 检查配置是否有效
docker exec xihong-alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

### 2. 测试邮件发送

```bash
# 在 Prometheus 中手动触发告警测试
# 或使用 amtool 发送测试告警
docker exec xihong-alertmanager amtool alert add \
  alertname=TestAlert \
  severity=warning \
  --alertmanager.url=http://localhost:9093
```

### 3. 查看 AlertManager 日志

```bash
docker logs xihong-alertmanager
```

## 安全建议

1. **密码保护**
   - 不要将密码提交到 Git 仓库
   - 使用环境变量或密钥管理服务
   - 定期轮换密码

2. **访问控制**
   - 限制 AlertManager Web UI 的访问（使用 Nginx 反向代理）
   - 使用 HTTPS 加密连接

3. **邮件内容**
   - 不要在邮件中包含敏感信息
   - 使用邮件模板自定义邮件格式

## 故障排查

### 问题 1: 邮件发送失败

**症状**: AlertManager 日志显示 `failed to send email`

**可能原因**:
- SMTP 服务器地址或端口错误
- 用户名或密码错误
- 防火墙阻止连接
- SMTP 服务器要求 TLS/SSL

**解决方法**:
1. 检查 SMTP 配置是否正确
2. 检查网络连接
3. 查看 AlertManager 详细日志

### 问题 2: 邮件被标记为垃圾邮件

**症状**: 收件人收不到邮件，或邮件进入垃圾箱

**解决方法**:
1. 配置 SPF 记录
2. 配置 DKIM 签名
3. 使用企业邮箱而非个人邮箱

### 问题 3: 告警未触发邮件

**症状**: Prometheus 有告警，但未收到邮件

**可能原因**:
- 告警路由规则配置错误
- 收件人邮箱配置错误
- 告警被抑制规则抑制

**解决方法**:
1. 检查 `route` 配置
2. 检查 `receivers` 配置
3. 检查 `inhibit_rules` 配置

## 相关文档

- [AlertManager 官方文档](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Prometheus 告警规则配置](../monitoring/alert_rules.yml)
- [监控系统部署指南](../deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)

