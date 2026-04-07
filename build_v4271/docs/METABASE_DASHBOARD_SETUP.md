## Metabase Dashboard 配置指南（DSS 架构）

本指南帮你在本地 Metabase 中**从零配置**业务概览相关的 Questions，并把 Question ID 写入环境变量，配合 `configure-metabase-dashboard-questions` change 使用。

目标：先把**最小闭环**打通——后端 Dashboard API 全部 200，前端切到新 Question API 后不再报 400。

---

## ⚠️ 重要：Metabase API Key 认证配置（2025-11-29 更新）

### **关键发现：正确的 Header 名称**

**Metabase API Key 认证必须使用 `X-API-Key` header（或 `x-api-key`），而不是 `X-Metabase-Api-Key`！**

根据 [Metabase 官方文档 v0.57](https://www.metabase.com/docs/v0.57/people-and-groups/api-keys)，API Key 认证的正确 Header 名称是：
- `x-api-key`（小写，官方 curl 示例）
- `X-API-KEY`（大写，官方 JavaScript 示例）
- `X-API-Key`（混合大小写，HTTP headers 大小写不敏感，我们的代码使用此格式）

#### **错误示例（会导致 401 认证失败）**：
```python
headers = {"X-Metabase-Api-Key": api_key}  # ❌ 错误！会返回 401
headers = {"X-Metabase-ApiKey": api_key}   # ❌ 错误！会返回 401
```

#### **正确示例（根据官方文档）**：
```python
# ✅ 正确：使用 X-API-Key（我们的代码使用此格式）
headers = {"X-API-Key": api_key}

# ✅ 正确：使用 x-api-key（官方 curl 示例）
headers = {"x-api-key": api_key}

# ✅ 正确：使用 X-API-KEY（官方 JavaScript 示例）
headers = {"X-API-KEY": api_key}
```

**注意**：HTTP headers 是大小写不敏感的，所以以上三种格式都可以工作。我们的代码使用 `X-API-Key`（混合大小写，符合常见命名约定）。

### **配置步骤**

1. **在 Metabase 中创建 API Key**：
   - 登录 Metabase：`http://localhost:8080`（端口从3000改为8080，避免Windows端口权限问题）
   - 进入：设置 → 认证 → API Keys
   - 点击"创建 API 密钥"
   - 输入名称（如 `xihong_erp`）
   - 选择权限组（推荐：Administrators）
   - 复制生成的 API Key（格式：`mb_xxxxxxxxxxxxx=`）

2. **在 `.env` 文件中配置**：
   ```env
   # Metabase认证方式(二选一)
   # 方式1:使用API Key(推荐)
   METABASE_API_KEY=mb_DVLzqBiuCnqja4VHFRkuLamo37cj5illnEZtkOprkoM=
   
   # 方式2:使用用户名密码(不推荐,仅开发环境)
   # METABASE_USERNAME=admin@example.com
   # METABASE_PASSWORD=your-password
   ```

3. **后端代码会自动使用正确的 Header**：
   - `backend/services/metabase_question_service.py` 已配置使用 `X-API-Key` header
   - 无需手动修改代码

### **常见问题排查**

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| HTTP 401 Unauthenticated | Header 名称错误 | 使用 `X-API-Key` 而不是 `X-Metabase-Api-Key` |
| HTTP 401 Unauthenticated | API Key 未配置 | 检查 `.env` 文件中的 `METABASE_API_KEY` |
| HTTP 401 Unauthenticated | API Key 格式错误 | 确保 API Key 以 `mb_` 开头，长度约 47 字符 |
| HTTP 401 Unauthenticated | API Key 权限不足 | 在 Metabase 中将 API Key 分配给 Administrators 组 |

### **历史教训**

- **问题**：我们最初使用了 `X-Metabase-Api-Key` header，导致所有 API Key 认证请求都返回 401
- **原因**：Metabase 的 API Key 认证使用简化的 `X-API-Key` header（或 `x-api-key`），而不是常见的 `X-{Service}-Api-Key` 格式
- **解决**：通过系统测试发现正确的 Header 名称是 `X-API-Key`，与 [Metabase 官方文档](https://www.metabase.com/docs/v0.57/people-and-groups/api-keys) 一致
- **教训**：API 认证 Header 名称可能不符合常见命名约定，遇到认证问题时应该：
  1. 优先查阅官方文档
  2. 测试不同的 Header 名称
  3. 参考官方示例代码（curl/JavaScript）

### **官方文档参考**

- **Metabase API Keys 文档**：https://www.metabase.com/docs/v0.57/people-and-groups/api-keys
- **官方示例**：
  - curl: `curl -H 'x-api-key: YOUR_API_KEY' -X GET 'http://localhost:8080/api/permissions/group'`
  - JavaScript: `headers: { "X-API-KEY": API_KEY }`

---

## 0. 前置条件检查

1. **PostgreSQL 表结构已就绪**
   - 数据库中存在以下 Schema 和表（无数据也可以）：
     - `b_class.fact_raw_data_orders_daily/weekly/monthly`
     - `b_class.fact_raw_data_products_daily/weekly/monthly`
     - `b_class.fact_raw_data_traffic_daily/weekly/monthly`
     - `b_class.fact_raw_data_services_daily/weekly/monthly`
     - `b_class.fact_raw_data_inventory_snapshot`
     - `b_class.entity_aliases`
     - `a_class.*` / `c_class.*`（本指南主要用到 B 类表）

2. **Metabase 已连接数据库**
   - 浏览器打开 `http://localhost:8080`
   - 管理员账号已创建并登录
   - 在 `Admin → Databases` 中能看到连接的 `xihong_erp` 数据库
   - 点击数据库右侧 “Sync database schema now”，确保最新表结构已同步

3. **确认后端使用的 Question key**
   - 在 `backend/services/metabase_question_service.py` 中已经约定的 key：
     - `business_overview_kpi`
     - `business_overview_comparison`
     - `business_overview_shop_racing`
     - `business_overview_traffic_ranking`
     - `business_overview_inventory_backlog`
     - `business_overview_operational_metrics`
     - `clearance_ranking`

接下来，我们为每个 key 创建一个 Question，并记录 ID。

---

## 1. business_overview_kpi（业务概览 KPI 卡片）

**用途**：顶部 2–4 个汇总指标（GMV、订单数等）。

### 1.1 在 Metabase 中创建 Question

1. 进入 Metabase 首页，点击右上角 **New → Question**。
2. 选择 **Simple question**。
3. 选择数据源：
   - Database: 选择你的 PostgreSQL 连接（例如 `xihong_erp`）。
   - Table: 选择 `b_class.fact_raw_data_orders_daily`。
4. 配置过滤条件（右侧 “Filter” 面板）：
   - `metric_date` → “Filter” → “Between” → 选择 “Field filter” 类型：
     - 命名：`start_date` / `end_date`（两个单独的 filter，Metabase 会自动生成参数）
   - `platform_code` → “Filter” → “Is” → 勾选 “Field filter”：
     - 命名：`platform`
   - `shop_id` → “Filter” → “Is” → 勾选 “Field filter”：
     - 命名：`shop_id`
5. 配置汇总（点击上方 “Summarize”）：
   - 添加度量 1：
     - 自定义表达式：
       - `sum( CAST([raw_data->>'销售额'] AS NUMERIC) )`
     - 命名：`gmv`
   - 添加度量 2：
     - 自定义表达式：
       - `sum( CAST([raw_data->>'订单数'] AS NUMERIC) )`
     - 命名：`order_count`
6. 可视化类型可以暂时使用 “Table” 或 “Scalar”，不影响后端使用。

### 1.2 保存并记录 ID

1. 点击右上角 **Save**：
   - Collection：可以放在 `Our analytics` 或创建一个 `DSS Dashboard` 目录。
   - Name：推荐 `Business Overview - KPI`。
2. 保存后浏览器地址栏会类似：
   - `http://localhost:8080/question/101-business-overview-kpi`
   - 此时 **101** 就是 Question ID。
3. 记录下 ID：`BUSINESS_OVERVIEW_KPI_ID = 101`（示例）。

---

## 2. business_overview_comparison（日/周/月对比折线）

**用途**：按粒度展示 GMV / 订单趋势（折线图）。

### 2.1 创建 Question

1. 新建 Question → Simple question。
2. 表：依然选择 `b_class.fact_raw_data_orders_daily`（先只做日度；后续可以复制为 weekly/monthly）。
3. 过滤条件：
   - `metric_date` → Field filter：
     - 类型：Date
     - 参数名：`date`（单日期或日期范围均可）
   - `platform_code` → Field filter，参数名 `platform`
   - `shop_id` → Field filter，参数名 `shop_id`
   - 额外添加一个 “原始值字段” 维度字段 `granularity` 的变量（可选，方便后续扩展）：
     - 如在 Metabase 中增加变量 `granularity`，暂时不用在 SQL 中约束。

4. Summarize：
   - 按字段 `metric_date` 分组（Group by）。
   - 添加度量 GMV 和 Order Count（同上）。
5. 在可视化里选择 **Line**，X 轴为 `metric_date`，Y 轴为 GMV/订单数两条线。

### 2.2 保存并记录 ID

1. 保存名称：`Business Overview - Comparison`。
2. 记录 URL 中的 ID，例如：`102`。

---

## 3. business_overview_shop_racing（店铺赛马 TopN）

**用途**：按店铺维度的 GMV TopN 排行。

### 3.1 创建 Question

1. 新建 Question，表选 `b_class.fact_raw_data_orders_daily`。
2. 过滤：
   - `metric_date` → Field filter，参数名 `date`。
   - `platform_code` → Field filter，参数名 `platform`。
3. Summarize：
   - Group by：`shop_id`。
   - 度量：GMV（`sum( CAST([raw_data->>'销售额'] AS NUMERIC) )`）。
4. 在 “Sort” 中按 GMV Desc 排序。
5. 在 “Rows to show” 中限制 Top 20（或 50）。

### 3.2 保存并记录 ID

1. 保存名称：`Business Overview - Shop Racing`。
2. 记录 ID，例如 `103`。

---

## 4. business_overview_traffic_ranking（流量排名）

**用途**：按店铺的 UV/PV 排名。

### 4.1 创建 Question

1. 表：`b_class.fact_raw_data_traffic_daily`。
2. 过滤：
   - `metric_date` → Field filter，参数名 `date`。
   - `platform_code` → Field filter，参数名 `platform`。
   - `shop_id` → Field filter，参数名 `shop_id`（可选）。
3. Summarize：
   - Group by：`shop_id`。
   - 度量：
     - UV：`sum( CAST([raw_data->>'访客数'] AS NUMERIC) )`
     - PV：`sum( CAST([raw_data->>'浏览量'] AS NUMERIC) )`
4. 排序按 UV Desc。

### 4.2 保存并记录 ID

1. 名称：`Business Overview - Traffic Ranking`。
2. 记录 ID，例如 `104`。

---

## 5. business_overview_inventory_backlog（库存积压）

**用途**：筛出长时间未动销 / 积压库存，为清仓提供输入。

### 5.1 创建 Question

1. 表：`b_class.fact_raw_data_inventory_snapshot`。
2. 创建一个 Custom Field（在 “Columns → Add custom column”）：
   - 名称：`is_backlog`
   - 表达式（示例）：  
     `CASE WHEN CAST([raw_data->>'最近成交天数'] AS INTEGER) > {{days}} THEN 1 ELSE 0 END`
   - 这里的 `{{days}}` 可以使用 Metabase 变量（也可以先写死，如 30）。
3. 过滤：
   - `is_backlog = 1`
   - `platform_code` → Field filter，参数名 `platform`
   - `shop_id` → Field filter，参数名 `shop_id`
4. Summarize：
   - Group by：`shop_id` 或 SKU（取决于你想看“店铺维度”还是“SKU 维度”）。
   - 指标：
     - 积压 SKU 数：`count(*)`
     - 积压库存金额：`sum( CAST([raw_data->>'库存金额'] AS NUMERIC) )`（字段名根据实际 JSONB 决定）

### 5.2 保存并记录 ID

1. 名称：`Business Overview - Inventory Backlog`。
2. 记录 ID，例如 `105`。

---

## 6. business_overview_operational_metrics（经营指标表格）

**用途**：店铺维度的 GMV / 订单 / 客单价 / 退货率等经营指标。

### 6.1 创建 Question

1. 表：`b_class.fact_raw_data_orders_daily`。
2. 过滤：
   - `metric_date` → Field filter，参数名 `date`。
   - `platform_code` → Field filter，参数名 `platform`。
   - `shop_id` → Field filter，参数名 `shop_id`（可选）。
3. Summarize：
   - Group by：`shop_id`。
   - 指标：
     - GMV：同前
     - Order Count：同前
4. 添加 Custom Fields（列）：
   - 客单价：  
     `GMV / NULLIF([Order Count], 0)`
   - 退货率（占位）：可以先设为 0 或简单表达式，后续再精化。

### 6.2 保存并记录 ID

1. 名称：`Business Overview - Operational Metrics`。
2. 记录 ID，例如 `106`。

---

## 7. clearance_ranking（清仓排名）

**用途**：为清仓策略提供排序（按折扣力度 / 库存压力）。

### 7.1 创建 Question

1. 表：`b_class.fact_raw_data_inventory_snapshot`。
2. 创建 Custom Field：
   - 名称：`discount_rate`
   - 表达式：  
     `CASE WHEN CAST([raw_data->>'原价'] AS NUMERIC) = 0 THEN NULL ELSE CAST([raw_data->>'现价'] AS NUMERIC) / CAST([raw_data->>'原价'] AS NUMERIC) END`
3. Summarize：
   - Group by：SKU（`raw_data->>'SKU'` 或 `raw_data->>'商品ID'`）。
   - 指标：
     - 当前库存：`sum( CAST([raw_data->>'库存'] AS NUMERIC) )`
     - 折扣率：可以取 `min(discount_rate)` 或 `max(discount_rate)`，根据业务定义
4. 排序：
   - 先按折扣率升序（折扣越低越“划算”），再按库存降序。
   - 在 “Rows to show” 里限制 Top N（10/50）。

### 7.2 保存并记录 ID

1. 名称：`Clearance Ranking`。
2. 记录 ID，例如 `107`。

---

## 8. 配置环境变量（.env / env.example）

拿到所有 ID 之后，在项目根目录的 `.env` 中添加或更新：

```env
# Metabase base config
METABASE_URL=http://localhost:8080
METABASE_API_KEY=你的_API_Key_或留空_使用用户名密码

# Dashboard Questions
METABASE_QUESTION_BUSINESS_OVERVIEW_KPI=101
METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON=102
METABASE_QUESTION_BUSINESS_OVERVIEW_SHOP_RACING=103
METABASE_QUESTION_BUSINESS_OVERVIEW_TRAFFIC_RANKING=104
METABASE_QUESTION_BUSINESS_OVERVIEW_INVENTORY_BACKLOG=105
METABASE_QUESTION_BUSINESS_OVERVIEW_OPERATIONAL_METRICS=106
METABASE_QUESTION_CLEARANCE_RANKING=107
```

> 数值替换为你实际在 Metabase URL 中看到的 ID。

同时更新 `env.example`，把以上变量加上去，并在注释中说明它们的用途，方便新环境配置。

---

## 9. 验证 Checklist

1. **后端日志不再有 “Question ID 未配置”**
   - 重启后端（`python run.py`），刷新业务概览页面，
   - 观察后端终端日志，不再出现 `Question ID未配置: ...`。

2. **Swagger / API 层验证**
   - 打开 `http://localhost:8001/api/docs`
   - 依次调用：
     - `GET /api/dashboard/business-overview/kpi`
     - `GET /api/dashboard/business-overview/comparison`
     - `GET /api/dashboard/business-overview/shop-racing`
     - `GET /api/dashboard/business-overview/traffic-ranking`
     - `GET /api/dashboard/business-overview/inventory-backlog`
     - `GET /api/dashboard/business-overview/operational-metrics`
     - `GET /api/dashboard/clearance-ranking`
   - 确认全部返回 HTTP 200（即使 data 为空）。

3. **前端 Dashboard 验证（基础）**
   - 访问前端业务概览页：
     - 不再看到 “Question ID 未配置” 的顶部错误条。
     - KPI 卡片/图表可以正确加载（没有报错，只是数据可能是 0）。

至此，**Metabase Questions + 后端配置链路就打通了**，可以进入 `migrate-frontend-dashboard-to-metabase-api` change，把前端全面切换到新 API。 


