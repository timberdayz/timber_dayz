# 数据浏览器功能移除说明

**版本**: v4.12.0  
**移除时间**: 2025-02-01  
**移除原因**: 数据浏览器功能修复多次仍无法正常使用，Metabase是更专业的BI工具

---

## 📋 移除原因

1. **功能重复**：Metabase是专业的BI工具，功能更强大，可以完全替代数据浏览器
2. **维护成本高**：数据浏览器功能修复多次仍存在问题，维护成本高
3. **DSS架构原则**：在DSS架构中，Metabase是主要的数据查询和分析工具
4. **用户体验**：Metabase提供更好的数据可视化和查询体验

---

## 🗑️ 已移除的内容

### 前端移除

1. **路由配置** (`frontend/src/router/index.js`)
   - 移除 `/data-browser` 路由

2. **菜单配置** (`frontend/src/config/menuGroups.js`)
   - 移除 `数据浏览器` 菜单项

3. **API调用** (`frontend/src/api/index.js`)
   - 移除 `getTables()` - 获取数据表列表
   - 移除 `queryData()` - 查询数据表数据
   - 移除 `getTableStats()` - 获取表统计信息
   - 移除 `getFieldMapping()` - 获取字段映射关系
   - 移除 `getFieldUsage()` - 获取字段使用链路
   - 移除 `exportData()` - 导出数据

4. **权限配置** (`frontend/src/stores/user.js`)
   - 移除 `data-browser` 权限

5. **组件文件**（保留但不使用）
   - `frontend/src/views/DataBrowser.vue` - 已注释路由，不再使用
   - `frontend/src/views/DataBrowserSimple.vue` - 已注释路由，不再使用

### 后端移除

1. **API路由** (`backend/main.py`)
   - 移除 `data_browser.router` 注册

2. **路由文件**（保留但不使用）
   - `backend/routers/data_browser.py` - 已注释导入和注册，不再使用

---

## ✅ Metabase替代方案

### 访问Metabase

1. **启动Metabase**：
   ```bash
   docker-compose -f docker-compose.metabase.yml up -d
   ```

2. **访问地址**：
   - 本地访问：`http://localhost:3000`
   - 首次访问需要设置管理员账号

3. **连接数据库**：
   - 主机：`postgres`（Docker网络内）或`localhost`（从主机访问）
   - 端口：`5432`
   - 数据库：`xihong_erp`
   - 用户名/密码：根据`.env`配置

### Metabase功能

1. **数据查询**：
   - 支持SQL查询
   - 支持可视化查询构建器
   - 支持多种图表类型

2. **数据可视化**：
   - 创建Dashboard
   - 创建Question
   - 支持多种图表类型（柱状图、折线图、饼图等）

3. **数据导出**：
   - 支持CSV、JSON、XLSX等格式导出
   - 支持定时导出

4. **数据质量分析**：
   - 创建数据质量检查Question
   - 创建数据质量Dashboard
   - 支持告警和通知

---

## 📝 迁移指南

### 从数据浏览器迁移到Metabase

1. **查看数据表**：
   - 数据浏览器：选择表 → 查看数据
   - Metabase：Browse Data → 选择数据库 → 选择表 → 查看数据

2. **查询数据**：
   - 数据浏览器：使用筛选器和搜索
   - Metabase：使用Query Builder或SQL查询

3. **导出数据**：
   - 数据浏览器：点击导出按钮
   - Metabase：在Question中点击导出按钮

4. **查看字段映射**：
   - 数据浏览器：点击字段查看映射关系
   - Metabase：查看表结构，或创建Question查看字段使用情况

---

## 🔗 相关文档

- [Metabase Dashboard设置指南](METABASE_DASHBOARD_SETUP.md)（如果存在）
- [数据同步管道验证文档](DATA_SYNC_PIPELINE_VALIDATION.md)
- [DSS架构文档](DSS_ARCHITECTURE_DATA_SYNC_MODIFICATIONS.md)

---

## ⚠️ 注意事项

1. **数据浏览器组件文件已完全删除**：
   - ✅ `frontend/src/views/DataBrowser.vue` - 已删除
   - ✅ `frontend/src/views/DataBrowserSimple.vue` - 已删除
   - ✅ `backend/routers/data_browser.py` - 已删除
   - ✅ 所有API调用已删除
   - ✅ 所有路由配置已移除

2. **Metabase配置**：
   - 确保Metabase容器正常运行
   - 确保端口映射正确（`3000:3000`）
   - 确保数据库连接配置正确

3. **用户培训**：
   - 需要培训用户使用Metabase
   - Metabase功能更强大，学习曲线可能较陡

---

## 📞 支持

如有问题，请：
1. 查看Metabase官方文档：https://www.metabase.com/docs/
2. 检查Metabase容器状态：`docker ps --filter "name=metabase"`
3. 查看Metabase日志：`docker logs xihong_erp_metabase`
4. 联系系统管理员

