# 数据浏览器和Metabase故障排查指南

**版本**: v4.12.0  
**更新时间**: 2025-02-01  
**问题**: 数据浏览器表格未正常显示，Metabase未正常启动

---

## 📋 问题描述

1. **数据浏览器表格未正常显示**：选择表后，表格数据没有显示或显示异常
2. **Metabase未正常启动**：无法访问Metabase界面，无法查询数据质量

---

## 🔍 问题排查步骤

### 1. 检查数据浏览器API响应

#### 步骤1：检查后端API是否正常

```bash
# 测试数据浏览器查询API
curl http://localhost:8001/api/data-browser/query?table=fact_raw_data_inventory_snapshot&page=1&page_size=20
```

**预期响应**：
```json
{
  "success": true,
  "data": {
    "data": [...],
    "total": 100,
    "columns_detailed": [...],
    ...
  }
}
```

#### 步骤2：检查前端API调用

打开浏览器开发者工具（F12），查看：
- **Network标签**：检查 `/api/data-browser/query` 请求是否成功
- **Console标签**：查看是否有JavaScript错误

**常见问题**：
- API返回404：检查路由配置
- API返回500：查看后端日志
- 数据为空：检查表名是否正确（需要包含schema，如`b_class.fact_raw_data_inventory_snapshot`）

---

### 2. 检查Metabase配置

#### 步骤1：检查Metabase容器状态

```bash
# 检查Metabase容器是否运行
docker ps --filter "name=metabase"

# 检查Metabase日志
docker logs xihong_erp_metabase --tail 50
```

**预期状态**：
- 容器状态：`Up` 且 `healthy`
- 端口映射：`8080:3000`（或配置的端口，主机端口从3000改为8080，避免Windows端口权限问题）

#### 步骤2：检查Metabase端口映射

**问题**：如果docker-compose.yml中没有配置Metabase服务，需要添加：

```yaml
metabase:
  image: metabase/metabase:latest
  container_name: xihong_erp_metabase
  ports:
    - "8080:3000"  # 主机端口从3000改为8080，避免Windows端口权限问题
  environment:
    MB_DB_TYPE: postgres
    MB_DB_DBNAME: ${POSTGRES_DB:-xihong_erp}
    MB_DB_PORT: 5432
    MB_DB_USER: ${POSTGRES_USER:-erp_user}
    MB_DB_PASS: ${POSTGRES_PASSWORD:-erp_pass_2025}
    MB_DB_HOST: postgres
  networks:
    - erp_network
  depends_on:
    postgres:
      condition: service_healthy
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]  # 容器内部使用3000端口
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 60s
```

#### 步骤3：检查Metabase环境变量

检查 `.env` 文件中的Metabase配置：

```env
# Metabase配置
METABASE_URL=http://localhost:8080  # 端口从3000改为8080，避免Windows端口权限问题
METABASE_API_KEY=your_api_key_here
# 或使用用户名密码
METABASE_USERNAME=admin@xihong.com
METABASE_PASSWORD=your_password
```

#### 步骤4：访问Metabase界面

打开浏览器访问：`http://localhost:8080`（端口从3000改为8080）

**如果无法访问**：
1. 检查端口是否被占用：`netstat -ano | findstr :8080`
2. 检查防火墙设置
3. 检查Docker网络配置

---

### 3. 检查数据浏览器显示问题

#### 问题1：表格数据为空

**可能原因**：
1. 表名不正确（需要包含schema）
2. 表确实没有数据
3. API查询失败

**解决方案**：
1. 检查表名格式：`b_class.fact_raw_data_inventory_snapshot`（不是`fact_raw_data_inventory_snapshot`）
2. 检查数据库是否有数据：`SELECT COUNT(*) FROM b_class.fact_raw_data_inventory_snapshot`
3. 查看浏览器控制台错误信息

#### 问题2：JSONB字段（attributes）显示异常

**问题**：JSONB字段显示为`[object Object]`或无法查看

**解决方案**：
- ✅ 已修复：JSONB字段现在使用弹窗显示（鼠标悬停查看）
- ✅ 已修复：JSONB字段显示为标签（如"5 字段"），点击查看详情

#### 问题3：列信息未显示

**可能原因**：
1. API未返回`columns_detailed`
2. 前端未正确解析列信息

**解决方案**：
1. 检查API响应中的`columns_detailed`字段
2. 查看浏览器控制台日志（`[DataBrowser] 使用columns_detailed:`）

---

## 🛠️ 修复方案

### 修复1：数据浏览器JSONB字段显示

**已修复**（`frontend/src/views/DataBrowser.vue`）：
- JSONB字段使用弹窗显示（鼠标悬停）
- 格式化JSON显示（美化）
- 日期时间格式化

### 修复2：Metabase端口映射

**需要检查**：
1. `docker-compose.yml`中是否有Metabase服务配置
2. 如果没有，需要添加Metabase服务（见上方配置示例）

### 修复3：数据浏览器列信息获取

**已修复**（`backend/routers/data_browser.py` 和 `frontend/src/views/DataBrowser.vue`）：
- ✅ 正确返回`columns_detailed`字段（包含字段类型信息）
- ✅ 包含字段类型信息（包括jsonb类型）
- ✅ 前端优先使用`columns_detailed`，如果没有则从`columns_info`提取
- ✅ 如果没有列信息，从数据推断列名（兼容旧数据）
- ✅ 空状态提示更友好（显示表名和提示信息）

**修复位置**：
- `handleQuery`函数：增强列信息提取逻辑
- 空状态显示：添加表名和提示信息

---

## ✅ 验证步骤

### 1. 验证数据浏览器

1. 打开数据浏览器页面
2. 选择B类数据表（如`fact_raw_data_inventory_snapshot`）
3. 检查：
   - [ ] 表格数据是否显示
   - [ ] JSONB字段（attributes）是否显示为标签
   - [ ] 鼠标悬停JSONB字段是否显示详情
   - [ ] 列信息是否正确显示

### 2. 验证Metabase

1. 访问 `http://localhost:8080`
2. 检查：
   - [ ] Metabase界面是否正常加载
   - [ ] 是否可以连接到PostgreSQL数据库
   - [ ] 是否可以查询B类数据表
   - [ ] 是否可以创建Question和Dashboard

---

## 📝 常见错误和解决方案

### 错误1：`表不存在: b_class.fact_raw_data_inventory_snapshot`

**原因**：表名格式不正确或表确实不存在

**解决方案**：
1. 检查表名格式：使用`b_class.fact_raw_data_inventory_snapshot`（包含schema）
2. 检查表是否存在：`SELECT * FROM information_schema.tables WHERE table_schema = 'b_class' AND table_name = 'fact_raw_data_inventory_snapshot'`

### 错误2：`Metabase连接失败`

**原因**：Metabase容器未启动或端口未映射

**解决方案**：
1. 检查容器状态：`docker ps --filter "name=metabase"`
2. 检查端口映射：确保`8080:3000`已配置（主机端口8080，容器端口3000）
3. 重启Metabase容器：`docker restart xihong_erp_metabase`

### 错误3：`数据为空但数据库有数据`

**原因**：表名格式不正确或API查询条件错误

**解决方案**：
1. 检查表名：使用完整表名（包含schema）
2. 检查API参数：确保没有错误的筛选条件
3. 直接查询数据库验证：`SELECT COUNT(*) FROM b_class.fact_raw_data_inventory_snapshot`

---

## 🔗 相关文档

- [数据同步管道验证文档](DATA_SYNC_PIPELINE_VALIDATION.md)
- [路径配置文档](PATH_CONFIGURATION.md)
- [Metabase Dashboard设置指南](METABASE_DASHBOARD_SETUP.md)（如果存在）

---

## 📞 支持

如有问题，请：
1. 查看浏览器控制台错误信息
2. 查看后端日志（`logs/`目录）
3. 检查Docker容器日志
4. 联系系统管理员

