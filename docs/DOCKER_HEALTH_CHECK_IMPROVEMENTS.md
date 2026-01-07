# Docker 健康检查改进文档

## 改进概述

本次改进了 `run.py` 脚本中的健康检查等待逻辑，使其能够更早地发现容器启动失败的问题，并提供更好的诊断信息。

## 主要改进点

### 1. 定期容器状态检查
- **改进前**: 只等待健康检查端点响应，无法及时发现容器崩溃
- **改进后**: 每100秒（10次重试）检查一次容器是否仍在运行
- **好处**: 如果容器因启动错误而退出，可以立即发现并显示错误信息

### 2. 主动错误检测
- **改进前**: 只有健康检查失败时才显示日志
- **改进后**: 定期检查容器日志，主动检测 "Application startup failed" 或 "ERROR" 等错误
- **好处**: 可以在等待期间就发现启动错误，而不需要等到超时

### 3. 更详细的诊断信息
- **改进前**: 只显示最后50行日志和基本诊断建议
- **改进后**: 
  - 区分不同类型的错误（容器停止 vs 健康检查失败）
  - 提供更具体的诊断建议
  - 在不同阶段显示不同的提示信息

### 4. 数据库连接预检查
- **新增功能**: 在启动后端容器前，先测试 PostgreSQL 数据库连接
- **好处**: 及早发现数据库配置问题，避免容器启动后才发现

## 代码改进详情

### 改进的健康检查循环

```python
# ⭐ 改进：定期检查容器日志，及早发现启动失败
if i > 0 and i % log_check_interval == 0:
    safe_print(f"  [诊断] 检查容器状态（尝试 {i}/{max_health_retries}）...")
    # 检查容器是否仍在运行
    if not check_docker_container_running(backend_container):
        # 显示错误信息和诊断建议
        ...
    # 检查容器日志中是否有错误
    logs = show_docker_container_logs(backend_container, 30)
    if "Application startup failed" in logs or "ERROR" in logs.upper():
        # 主动显示错误日志
        ...
```

### 数据库连接预检查

```python
# ⭐ 新增：检查PostgreSQL数据库连接（诊断数据库用户问题）
safe_print("  [检查] PostgreSQL数据库连接...")
try:
    result = subprocess.run(
        ["docker", "exec", "xihong_erp_postgres", "psql", "-U", "erp_dev", "-d", "xihong_erp_dev", "-c", "SELECT 1"],
        ...
    )
    if result.returncode != 0:
        # 提供诊断建议
        ...
```

## 常见问题诊断

### 问题1: 容器启动失败 - 数据库用户不存在

**症状**:
```
ERROR: Application startup failed
sqlalchemy.exc.OperationalError: password authentication failed for user "erp_dev"
```

**原因**: PostgreSQL 数据卷使用了旧的配置创建，数据库中不存在 `erp_dev` 用户

**解决方案**:
1. **推荐方案**: 重新创建数据库容器和数据卷
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v
   python run.py --use-docker
   ```

2. **手动修复**: 使用修复脚本
   ```bash
   python scripts/fix_database_user.py
   ```

### 问题2: 健康检查超时

**症状**: 脚本长时间停留在 "后端服务健康检查..." 环节

**原因**:
- 后端服务启动缓慢（首次启动需要初始化）
- 数据库连接问题
- 其他配置错误

**诊断步骤**:
1. 查看容器状态: `docker ps -a | grep backend`
2. 查看容器日志: `docker logs xihong_erp_backend_dev -f`
3. 测试健康检查端点: `curl http://localhost:8001/health`
4. 检查环境变量: `docker exec xihong_erp_backend_dev env | grep DATABASE`

### 问题3: 容器状态显示 "unhealthy"

**症状**: `docker ps` 显示容器状态为 `(unhealthy)`

**原因**: Docker Compose 的健康检查配置失败

**解决方案**:
1. 查看容器日志确定具体错误
2. 检查健康检查端点是否正常响应
3. 如果服务实际正常运行，可以临时禁用健康检查或调整健康检查配置

## 改进后的工作流程

1. **启动基础服务** (Redis, PostgreSQL)
   - 等待服务完全启动（8秒）
   
2. **数据库连接预检查**
   - 测试 PostgreSQL 连接
   - 如果失败，显示诊断建议

3. **启动后端容器**
   - 构建镜像（首次可能需要5分钟）
   - 启动容器
   
4. **验证容器状态**
   - 等待容器进入 "running" 状态（最多20秒）
   
5. **健康检查等待**（改进的核心）
   - 每10秒检查一次健康检查端点
   - 每100秒检查一次容器状态和日志
   - 主动检测错误并显示诊断信息
   - 最多等待5分钟

6. **启动 Celery Worker**
   - 类似的后端启动流程

## 使用建议

### 首次启动
```bash
# 清理旧容器和数据卷（如果有问题）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v

# 启动系统
python run.py --use-docker
```

### 查看实时日志
```bash
# 后端日志
docker logs xihong_erp_backend_dev -f

# Celery Worker 日志
docker logs xihong_erp_celery_worker_dev -f

# 所有服务日志
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
```

### 诊断问题
```bash
# 检查容器状态
docker ps -a

# 检查数据库连接
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "SELECT 1"

# 测试健康检查端点
curl http://localhost:8001/health

# 使用修复脚本
python scripts/fix_database_user.py
```

## 性能影响

- **额外检查开销**: 每100秒检查一次容器状态和日志，影响极小
- **总体等待时间**: 最多5分钟（可配置），但正常情况下1-2分钟即可完成
- **诊断价值**: 显著提升，可以及早发现问题，避免长时间等待

## 未来改进方向

1. **可配置的超时时间**: 允许用户通过环境变量配置健康检查超时
2. **更智能的错误识别**: 识别常见错误模式，提供自动修复建议
3. **健康检查指标收集**: 记录健康检查时间，优化启动流程
4. **并行启动**: 后端和 Celery Worker 可以并行启动，减少总启动时间

