# Docker部署验证清单

> **快速验证Docker部署是否成功**  
> v4.0.0 - 2025-10-23

---

## 📋 部署前检查清单

### ✅ 环境准备

- [ ] Docker已安装并运行
  ```bash
  docker --version  # 应显示版本号
  docker info       # 应显示Docker信息
  ```

- [ ] Docker Compose已安装
  ```bash
  docker-compose --version  # 应显示版本号
  ```

- [ ] 磁盘空间充足
  ```bash
  df -h  # Linux/Mac
  # Windows: 查看C盘空间
  # 至少需要10GB可用空间
  ```

- [ ] 内存充足
  ```bash
  free -h  # Linux
  # 至少需要4GB可用内存
  ```

### ✅ 配置文件

- [ ] 环境变量文件已创建
  ```bash
  ls -la .env  # 应存在.env文件
  ```

- [ ] 数据库密码已修改（生产环境）
  ```bash
  grep POSTGRES_PASSWORD .env
  # 不应该是默认密码
  ```

- [ ] API密钥已修改（生产环境）
  ```bash
  grep SECRET_KEY .env
  # 不应该是默认值
  ```

- [ ] 端口配置正确
  ```bash
  grep _PORT .env
  # 确认端口未被占用
  ```

### ✅ 文件权限

- [ ] 启动脚本有执行权限（Linux/Mac）
  ```bash
  ls -l docker/scripts/*.sh
  # 应显示 -rwxr-xr-x
  chmod +x docker/scripts/*.sh  # 如需添加权限
  ```

---

## 🚀 部署后验证清单

### ✅ 容器状态

- [ ] 所有容器正常运行
  ```bash
  docker-compose ps
  # 所有服务应显示 "Up" 状态
  ```

- [ ] PostgreSQL容器健康
  ```bash
  docker-compose exec postgres pg_isready -U erp_user -d xihong_erp
  # 应显示: "accepting connections"
  ```

- [ ] 后端容器健康（生产模式）
  ```bash
  curl -f http://localhost:8001/healthz/ready
  # 应返回: {"status":"healthy"}
  ```

- [ ] 前端容器健康（生产模式）
  ```bash
  curl -f http://localhost:5174
  # 应返回HTML内容
  ```

### ✅ 服务访问

- [ ] 数据库可访问
  ```bash
  # 使用psql或pgAdmin连接
  psql -h localhost -p 5432 -U erp_user -d xihong_erp
  # 应能成功登录
  ```

- [ ] pgAdmin可访问（开发模式）
  ```bash
  # 浏览器访问: http://localhost:5051
  # 应显示登录页面
  ```

- [ ] 后端API可访问
  ```bash
  # 浏览器访问API文档
  # http://localhost:8001/api/docs
  # 应显示Swagger UI
  ```

- [ ] 前端界面可访问
  ```bash
  # 浏览器访问
  # http://localhost:5174 (生产)
  # http://localhost:5173 (开发)
  # 应显示登录页面
  ```

### ✅ 数据库验证

- [ ] 数据库已创建
  ```sql
  -- 连接数据库后执行
  \l  -- 应列出xihong_erp数据库
  ```

- [ ] 表已创建
  ```sql
  \dt  -- 应显示所有表
  # 至少包含: accounts, data_files, field_mappings等
  ```

- [ ] 示例数据已插入
  ```sql
  SELECT COUNT(*) FROM accounts;
  # 应返回至少4条记录
  ```

- [ ] 索引已创建
  ```sql
  \di  -- 应显示所有索引
  ```

### ✅ 网络连通性

- [ ] 前端可访问后端
  ```bash
  # 在前端容器内测试
  docker-compose exec frontend wget -qO- http://backend:8000/health
  # 应返回健康信息
  ```

- [ ] 后端可访问数据库
  ```bash
  # 在后端容器内测试
  docker-compose exec backend python -c "from backend.models.database import engine; engine.connect()"
  # 应无错误输出
  ```

### ✅ 日志检查

- [ ] PostgreSQL日志正常
  ```bash
  docker-compose logs postgres | grep -i error
  # 应无关键错误
  ```

- [ ] 后端日志正常（生产模式）
  ```bash
  docker-compose logs backend | grep -i error
  # 应无关键错误
  ```

- [ ] 前端日志正常（生产模式）
  ```bash
  docker-compose logs frontend | grep -i error
  # 应无关键错误
  ```

### ✅ 性能检查

- [ ] 容器资源使用正常
  ```bash
  docker stats --no-stream
  # CPU和内存使用率应在合理范围
  ```

- [ ] API响应时间正常
  ```bash
  curl -w "响应时间: %{time_total}秒\n" -o /dev/null -s http://localhost:8001/healthz/ready
  # 应<2秒
  ```

### ✅ 数据持久化

- [ ] PostgreSQL数据卷已创建
  ```bash
  docker volume ls | grep postgres_data
  # 应显示 xihong_erp_postgres_data
  ```

- [ ] 数据目录已挂载
  ```bash
  ls -la data/
  # 应显示数据文件
  ```

- [ ] 日志目录已挂载
  ```bash
  ls -la logs/
  # 应显示日志文件
  ```

---

## 🔧 功能测试清单

### ✅ 基础功能

- [ ] 用户可以登录系统
- [ ] 可以查看数据看板
- [ ] 可以访问数据管理页面
- [ ] 可以访问账号管理页面
- [ ] 可以访问字段映射页面

### ✅ API测试

- [ ] 健康检查端点
  ```bash
  curl http://localhost:8001/healthz/ready
  ```

- [ ] API文档可访问
  ```bash
  curl http://localhost:8001/api/docs
  ```

- [ ] 数据查询API
  ```bash
  curl http://localhost:8001/api/dashboard/stats
  ```

### ✅ 数据操作

- [ ] 可以创建数据记录
- [ ] 可以读取数据记录
- [ ] 可以更新数据记录
- [ ] 可以删除数据记录

---

## 🛠️ 故障诊断清单

### ❌ 容器无法启动

- [ ] 检查Docker服务
  ```bash
  docker info
  ```

- [ ] 检查端口占用
  ```bash
  # Windows
  netstat -ano | findstr :5432
  # Linux/Mac
  lsof -i:5432
  ```

- [ ] 查看容器日志
  ```bash
  docker-compose logs <service-name>
  ```

### ❌ 数据库连接失败

- [ ] 检查数据库容器状态
  ```bash
  docker-compose ps postgres
  ```

- [ ] 检查数据库配置
  ```bash
  grep DATABASE_URL .env
  ```

- [ ] 测试数据库连接
  ```bash
  docker-compose exec postgres pg_isready
  ```

### ❌ 前端访问失败

- [ ] 检查前端容器状态
  ```bash
  docker-compose ps frontend
  ```

- [ ] 检查前端日志
  ```bash
  docker-compose logs frontend
  ```

- [ ] 检查Nginx配置
  ```bash
  docker-compose exec frontend nginx -t
  ```

### ❌ 后端API失败

- [ ] 检查后端容器状态
  ```bash
  docker-compose ps backend
  ```

- [ ] 检查后端日志
  ```bash
  docker-compose logs backend
  ```

- [ ] 测试健康端点
  ```bash
  curl http://localhost:8001/healthz/ready
  ```

---

## 📊 性能基准

### ✅ 响应时间

- [ ] 前端首页加载 < 2秒
- [ ] API健康检查 < 500ms
- [ ] 数据查询API < 1秒
- [ ] 数据库查询 < 500ms

### ✅ 资源使用

- [ ] PostgreSQL内存 < 1GB
- [ ] 后端内存 < 512MB
- [ ] 前端内存 < 256MB
- [ ] 总CPU使用 < 50%

### ✅ 并发能力

- [ ] 支持10个并发用户
- [ ] 支持100个并发请求
- [ ] 数据库连接池正常

---

## 🔒 安全检查清单

### ✅ 密码安全

- [ ] 数据库密码已修改
- [ ] API密钥已修改
- [ ] pgAdmin密码已修改
- [ ] 密码强度足够（至少12位）

### ✅ 网络安全

- [ ] 生产环境禁用pgAdmin
- [ ] CORS配置正确
- [ ] 仅必要端口对外开放
- [ ] 使用HTTPS（生产环境）

### ✅ 数据安全

- [ ] 数据定期备份
- [ ] 备份可正常恢复
- [ ] 敏感数据加密存储
- [ ] 日志不包含敏感信息

---

## 📝 验证报告模板

```
# Docker部署验证报告

**部署日期**: YYYY-MM-DD
**部署环境**: 开发/生产
**部署人**: 姓名

## 部署前检查
- [x] 环境准备: ✅ 通过
- [x] 配置文件: ✅ 通过
- [x] 文件权限: ✅ 通过

## 部署后验证
- [x] 容器状态: ✅ 所有容器运行正常
- [x] 服务访问: ✅ 所有服务可访问
- [x] 数据库验证: ✅ 数据库正常
- [x] 网络连通性: ✅ 网络正常
- [x] 日志检查: ✅ 无错误
- [x] 性能检查: ✅ 性能正常
- [x] 数据持久化: ✅ 数据持久化正常

## 功能测试
- [x] 基础功能: ✅ 通过
- [x] API测试: ✅ 通过
- [x] 数据操作: ✅ 通过

## 性能基准
- 前端首页加载: 1.2秒 ✅
- API响应时间: 300ms ✅
- PostgreSQL内存: 512MB ✅

## 安全检查
- [x] 密码安全: ✅ 通过
- [x] 网络安全: ✅ 通过
- [x] 数据安全: ✅ 通过

## 问题记录
无

## 验证结论
✅ 部署成功，系统运行正常

**验证人**: ___________
**日期**: ___________
```

---

## 📞 获取帮助

如果验证过程中遇到问题：

1. **查看日志**: `docker-compose logs -f`
2. **健康检查**: `make health` 或 `./docker/scripts/health-check.sh`
3. **查阅文档**: `docs/DOCKER_DEPLOYMENT.md`
4. **重新部署**: 先`docker-compose down`，再重新启动

---

**最后更新**: 2025-10-23  
**维护者**: 西虹ERP团队

