# 云端 Metabase 首次进入后的后续配置清单

**适用场景**：已成功进入 Metabase（数据源已连接），需完成剩余配置以使 Dashboard KPI、init_metabase.py 等后端功能可用。

---

## 一、在 Metabase 中需完成的配置

### 1. 检查/完善数据源 Schema 过滤（如未包含 b_class）

若当前数据源只显示 `a_class`、`c_class`、`core`、`public`，**未显示 `b_class`**，需添加 Schema 过滤：

1. 进入 **设置 → 管理 → 数据库**
2. 点击数据源「测试ERPSQL数据库」（或「西虹ERP数据库」）
3. 点击 **编辑** / **Edit**
4. 展开 **显示高级选项** / **Show advanced options**
5. **Schema 过滤器** / **Schema filters**：设置为 `public,b_class,a_class,c_class,core,finance` 或选择 **全部** / **All schemas**
6. 保存后点击 **同步数据库 schema** / **Sync database schema now**，等待 1–2 分钟

**验证**：在数据库详情页的 Tables 中应能看到 `b_class` 下的业务表（如 `fact_shopee_*`、`fact_tiktok_*` 等）。

### 2. 创建 API Key（必须）

后端 Dashboard KPI、`init_metabase.py` 等依赖 Metabase API Key 调用 REST API。

1. 进入 **设置（齿轮）→ 身份验证（Authentication）→ API Keys**
2. 点击 **创建 API 密钥** / **Create API Key**
3. 名称：`xihong_erp`（或任意）
4. 权限组：**Administrators**
5. 复制生成的 API Key（格式：`mb_xxxxxxxxxxxxx=`），**妥善保存**

---

## 二、在云端服务器 .env 中需配置的内容

在服务器 `/opt/xihong_erp/.env` 或 `.env.production` 中确认/添加以下变量：

### 必须配置

| 变量 | 值 | 说明 |
|------|-----|------|
| `METABASE_API_KEY` | `mb_xxxxxxxxxxxxx=` | 上一步在 Metabase 中创建的 API Key |
| `MB_SITE_URL` | `http://www.xihong.site/metabase/` | 与 Nginx 代理访问地址一致，尾部斜杠保留 |

### 已有可保持不变

| 变量 | 说明 |
|------|------|
| `METABASE_URL` | `http://metabase:3000`（后端容器内调用） |
| `VITE_METABASE_URL` | `/metabase`（前端嵌入路径） |

### 配置后需重启

```bash
# 重启 backend 使 METABASE_API_KEY 生效
docker restart xihong_erp_backend
```

---

## 三、验证

1. **Metabase 嵌入**：访问 ERP 前端 Dashboard，确认 Metabase 看板可正常加载
2. **API 调用**：若有使用 `init_metabase.py` 或 Dashboard KPI 接口，确认无 401 错误

---

## 四、参考

- 提案：`openspec/changes/add-cloud-metabase-day1-access/proposal.md`
- 任务：`openspec/changes/add-cloud-metabase-day1-access/tasks.md`
- 简单配置：`docs/METABASE_SIMPLE_SETUP_GUIDE.md`
- API Key 配置：`docs/METABASE_DASHBOARD_SETUP.md`
