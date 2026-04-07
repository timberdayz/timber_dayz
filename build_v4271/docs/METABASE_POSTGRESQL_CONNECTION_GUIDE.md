# Metabase PostgreSQL连接配置指南

## 连接信息

### 方式1：使用连接字符串（推荐）

在Metabase的"Connection string (optional)"字段中填入：

```
jdbc:postgresql://postgres:5432/xihong_erp
```

**注意**：由于Metabase运行在Docker容器中，与PostgreSQL在同一Docker网络，使用服务名 `postgres` 作为主机地址。

### 方式2：手动填写各个字段

如果连接字符串不工作，可以手动填写以下信息：

| 字段 | 值 | 说明 |
|------|-----|------|
| **显示名称** | 西虹ERP数据库 | 自定义名称，方便识别 |
| **主机地址** | `postgres` | Docker网络中的PostgreSQL服务名 |
| **端口** | `5432` | PostgreSQL标准端口 |
| **数据库名称** | `xihong_erp` | 数据库名 |
| **用户名** | `erp_user` | 数据库用户名 |
| **密码** | `erp_pass_2025` | 数据库密码（或.env中的值） |
| **Schema** | `全部` | 选择"全部"以同步所有schema |
| **使用安全连接 (SSL)** | ❌ 关闭 | 本地Docker网络不需要SSL |
| **使用SSH-tunnel** | ❌ 关闭 | 不需要SSH隧道 |

## 配置步骤

1. **填写连接字符串**（推荐）
   - 在"Connection string (optional)"字段填入：`jdbc:postgresql://postgres:5432/xihong_erp`
   - 点击"连接数据库"按钮
   - Metabase会自动填充其他字段

2. **或手动填写各个字段**
   - 按照上表填写每个字段
   - 确保"主机地址"填写为 `postgres`（不是localhost）

3. **配置 Schema filters（重要）**
   - 点击"Show advanced options"（显示高级选项）
   - **Schema filters**：设置为 `public,b_class,a_class,c_class,core,finance`
   - **或者**：选择 **"全部"** / **"All schemas"**（推荐）
   - ⚠️ **重要**：必须包含 `b_class` schema，否则看不到按平台分表的表

4. **测试连接**
   - 点击"连接数据库"按钮
   - 等待连接测试完成
   - 如果成功，会显示"连接成功"

5. **完成设置**
   - 连接成功后，点击"完成"或"下一步"
   - Metabase会自动开始同步数据库schema
   - ⚠️ **Metabase 会自动发现所有表，不需要任何脚本！**

## 常见问题

### Q1: 连接失败，提示"无法连接到数据库"

**原因**：
- 主机地址填写错误（使用了localhost而不是postgres）
- PostgreSQL容器未运行
- 网络配置问题

**解决方案**：
1. 确认主机地址填写为 `postgres`（Docker服务名）
2. 检查PostgreSQL容器状态：`docker ps --filter "name=postgres"`
3. 检查网络连接：`docker network inspect xihong_erp_erp_network`

### Q2: 连接字符串不工作

**原因**：
- 连接字符串格式错误
- Metabase版本不支持连接字符串

**解决方案**：
- 使用手动填写方式，逐个填写字段
- 确保主机地址为 `postgres`，不是 `localhost`

### Q3: 认证失败

**原因**：
- 用户名或密码错误
- 数据库用户权限不足

**解决方案**：
1. 检查`.env`文件中的数据库配置
2. 确认用户名：`erp_user`
3. 确认密码：`erp_pass_2025`（或.env中的实际值）
4. 测试PostgreSQL连接：`docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp`

### Q4: 从宿主机访问Metabase时连接失败

**说明**：
- 如果Metabase运行在Docker中，应该使用 `postgres` 作为主机地址
- 如果Metabase运行在宿主机上，应该使用 `localhost` 或 `127.0.0.1`

**当前配置**：
- Metabase运行在Docker容器中
- 应该使用 `postgres` 作为主机地址

## 验证连接

连接成功后，在Metabase中：

1. **查看数据库列表**
   - Admin → Databases
   - 应该看到"西虹ERP数据库"

2. **测试查询**
   - 点击数据库名称
   - 点击"浏览数据"
   - 应该能看到表列表

3. **同步Schema**
   - 在数据库详情页面
   - 点击"同步数据库schema now"
   - 等待同步完成（可能需要几分钟）

## 下一步

连接成功后，下一步操作：

1. **等待自动同步**
   - Metabase 会自动同步数据库 Schema
   - 等待 1-2 分钟让同步完成
   - 或手动点击 "Sync database schema now" 按钮

2. **验证表列表**
   - 在数据库详情页，点击 "Tables"（表）标签
   - 应该能看到所有 Schema 中的表
   - 展开 `b_class` schema，应该能看到 26 个按平台分表的表

⚠️ **重要**：Metabase 会自动发现所有表，不需要任何脚本！

2. **创建Dashboard和Question**
   - 参考 `docs/METABASE_DASHBOARD_MANUAL_SETUP.md`

