# 🚀 快速启动指南：所有功能一览

**版本**: v2.3 + v3.0  
**更新日期**: 2025-10-27  

---

## 1️⃣ 启动系统

### 启动命令

```bash
# 方式1：使用run.py（推荐）
python run.py

# 方式2：手动启动
# 后端
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# 前端（新终端）
cd frontend
npm run dev
```

### 访问地址

- 前端：http://localhost:5173
- 后端API文档：http://localhost:8001/docs
- Metabase数据看板：http://localhost:8080（端口从3000改为8080，避免Windows端口权限问题）

---

## 2️⃣ 字段映射系统（v2.3）

### 访问路径
http://localhost:5173/#/field-mapping

### 使用流程

```
步骤1：扫描文件
  - 点击"扫描采集文件"按钮
  - 系统自动扫描data/raw和downloads目录
  - 文件注册到catalog_files表

步骤2：选择文件
  - 选择平台（Shopee/TikTok/Amazon/妙手）
  - 选择数据域（订单/产品/流量）
  - 选择粒度（daily/weekly/monthly）
  - 下拉选择文件（显示：file_name (platform/domain/granularity, date_range)）

步骤3：预览数据
  - 设置表头行（默认1，妙手文件通常是3）
  - 点击"预览数据"
  - 查看数据表格（前20行）
  - 原始字段列显示实际列名 ✓

步骤4：配置字段映射
  - 点击"生成字段映射"（智能匹配）
  - 查看"智能字段映射"区域
  - 检查原始字段→标准字段映射是否正确
  - 可手动调整映射

步骤5：确认入库
  - 点击"确认映射并入库"
  - 系统自动：
    * 数据验证
    * COPY批量导入（高性能）
    * 状态更新（catalog_files.status='ingested'）
    * 后台提取图片（如果有，异步不阻塞）
  - 2-3秒完成

步骤6：查看结果
  - catalog状态统计
  - 数据查询验证
  - 查看产品管理（如果入库的是产品数据）
```

### 关键功能

- ✅ 4种Excel格式支持（.xlsx/.xls/OLE-XLSX/HTML）
- ✅ 合并单元格自动还原
- ✅ 智能字段映射（置信度>80%）
- ✅ 数据验证与隔离
- ✅ 批量入库（10000行<20秒）
- ✅ 异步图片提取（不阻塞）

---

## 3️⃣ 产品管理（v3.0）

### 访问路径
http://localhost:5173/#/product-management

### 使用流程

```
步骤1：查看产品列表
  - 自动加载所有产品（带缩略图）
  - 支持分页（默认20条/页）

步骤2：筛选产品
  - 平台筛选（Shopee/TikTok/Amazon/妙手）
  - 关键词搜索（SKU/产品名称）
  - 低库存筛选（仅显示库存<10的产品）
  - 点击"查询"按钮

步骤3：查看产品详情
  - 点击产品图片 或 "详情"按钮
  - 弹窗显示：
    * 图片轮播（如果有多张图片）
    * 完整产品信息（SKU、名称、分类、品牌等）
    * 库存状态
    * 销售指标（销量、销售额）
    * 流量指标（浏览量、转化率）

步骤4：图片管理（可选）
  - API已ready：/api/products/products/{sku}/images
  - 可手动上传产品图片
  - 自动压缩+生成缩略图
```

### 关键功能

- ✅ 产品列表（缩略图、筛选、搜索、分页）
- ✅ 产品详情（图片轮播、完整信息）
- ✅ 库存状态标识（低库存警告）
- ✅ 销售指标展示
- ✅ 图片上传管理

---

## 4️⃣ 销售看板（v3.0）

### 访问路径
http://localhost:5173/#/sales-dashboard-v3

### 功能说明

**概览卡片**：
- 总产品数
- 总库存
- 库存价值（¥）
- 低库存预警

**平台产品分布**：
- 各平台产品数量
- 各平台库存数量
- 表格展示

**产品销售排行TOP20**：
- 带产品图片（缩略图）
- 支持排序：
  * 按销售额
  * 按销量
  * 按浏览量
- 点击查看产品详情

**产品详情快速查看**：
- 点击产品图片或"查看"按钮
- 弹窗显示：
  * 图片轮播
  * 完整产品信息
  * 销售指标
  * 流量指标

---

## 5️⃣ 库存看板（v3.0）

### 访问路径
http://localhost:5173/#/inventory-dashboard-v3

### 功能说明

**库存概览**：
- 总库存
- 低库存预警（stock<10，红色标识）
- 缺货数量（stock=0，深红标识）
- 库存价值（¥）

**平台库存分布**：
- 各平台产品数量
- 各平台库存数量
- 库存占比

**库存健康度评分**：
- 智能100分制算法：
  * 100分 - (低库存比例×30) - (缺货比例×50)
- 评级：
  * 90-100分：健康 ✓ (绿色)
  * 70-89分：一般 ⚠ (橙色)
  * <70分：需关注 ✗ (红色)

**低库存预警列表**：
- 自动筛选stock<10的产品
- 带产品图片
- 库存状态标识：
  * stock=0：红色标签（缺货）
  * stock<5：红色标签（严重不足）
  * stock<10：橙色标签（低库存）
- 操作：
  * 查看详情
  * 补货入口

**产品详情快速查看**：
- 点击产品查看详情
- 弹窗显示完整信息

---

## 6️⃣ 数据准备

### 如果product_images表为空（无图片）

**方案A：自动提取（推荐）**
```
1. 使用字段映射系统入库含图片的Excel文件
2. 系统自动后台提取图片（1-2分钟）
3. 刷新产品管理/销售看板/库存看板，图片自动显示
```

**方案B：妙手文件转换**
```bash
# 妙手OLE格式XLSX文件（含图片）
python scripts/convert_miaoshou_files.py

# 转换后的文件在：downloads/miaoshou/converted/
# 重新使用字段映射系统入库
```

**方案C：手动上传**
```
1. 访问产品管理页面
2. 点击产品"详情"
3. 使用API手动上传图片：
   POST /api/products/products/{sku}/images
```

---

## 7️⃣ API快速参考

### 字段映射API

```javascript
// 文件分组
GET /api/field-mapping/file-groups

// 文件信息
GET /api/field-mapping/file-info?file_id=123

// 数据预览
POST /api/field-mapping/preview
{
  "file_id": 123,
  "header_row": 1
}

// 数据入库
POST /api/field-mapping/ingest
{
  "file_id": 123,
  "platform": "shopee",
  "domain": "products",
  "mappings": {...},
  "rows": [...]
}
```

### 产品管理API

```javascript
// 产品列表
GET /api/products/products?platform=shopee&page=1&page_size=20

// 产品详情
GET /api/products/products/{sku}?platform=shopee&shop_id=shop_001

// 平台汇总
GET /api/products/stats/platform-summary?platform=shopee

// 上传图片
POST /api/products/products/{sku}/images
FormData: file=...
```

---

## 8️⃣ 常见问题

### Q1：表头行设置错误怎么办？
**A**：修改"表头行"数值 → 点击"重新预览" → 原始字段列自动刷新 ✓

### Q2：字段映射不准确怎么办？
**A**：
1. 方案1：点击"修正低置信度"批量修正
2. 方案2：直接点击标准字段下拉框手动选择
3. 方案3：使用"套用模板"应用历史模板

### Q3：产品没有图片怎么办？
**A**：
1. 入库时会自动提取（如果Excel含图片）
2. 手动上传图片：产品详情 → 上传图片
3. 妙手文件：先转换再入库

### Q4：看板没有数据怎么办？
**A**：
1. 先使用字段映射系统入库产品数据
2. 刷新看板页面（数据来自fact_product_metrics表）
3. 确认数据已入库：字段映射页面查看catalog状态

### Q5：PostgreSQL性能慢怎么办？
**A**：
1. 查询慢SQL：pg_stat_statements（已启用）
2. 启用COPY批量导入：使用bulk_importer服务
3. 大数据量（>100万行）：执行月分区迁移脚本

---

## 9️⃣ 技术支持

### 日志位置

```
后端日志：backend/logs/
前端开发日志：浏览器控制台
数据库日志：PostgreSQL日志
```

### 调试模式

```bash
# 后端调试
cd backend
python -m pdb main.py

# 查看catalog状态
GET /api/field-mapping/catalog-status

# 查看隔离区数据
GET /api/field-mapping/quarantine-summary
```

### 数据库直接查询

```sql
-- 查看catalog状态
SELECT status, COUNT(*) FROM catalog_files GROUP BY status;

-- 查看产品数据
SELECT COUNT(*) FROM fact_product_metrics;

-- 查看产品图片
SELECT COUNT(*) FROM product_images;

-- 查看dim_date
SELECT COUNT(*) FROM dim_date;  -- 应该是4018条
```

---

## 🎯 快速测试流程（5分钟）

```
1. 启动系统（python run.py）
2. 访问字段映射页面
3. 扫描文件 → 选择文件 → 预览 → 生成映射 → 入库 ✓
4. 访问产品管理页面 → 查看产品列表 ✓
5. 访问销售看板 → 查看产品排行 ✓
6. 访问库存看板 → 查看库存监控 ✓

全流程<5分钟，验证所有功能可用！
```

---

**系统已完全ready，开始使用吧！** 🚀

**遇到问题请查看**：
- docs/ULTIMATE_DELIVERY_REPORT_20251027.md（终极交付报告）
- docs/FINAL_ANSWERS_TO_USER_QUESTIONS.md（用户问题解答）
- docs/USER_QUICK_START_GUIDE.md（用户快速入门）
- docs/METABASE_DASHBOARD_SETUP.md（Metabase配置指南）
- docs/DATA_BROWSER_AND_METABASE_TROUBLESHOOTING.md（Metabase故障排查）

---

## 9️⃣ Metabase数据看板（v4.12.0+）

### ⚠️ 重要变更

**v4.12.0移除**：数据浏览器功能已完全移除，使用Metabase替代。

**原因**：数据浏览器功能修复多次仍无法正常使用，Metabase是更专业的BI工具。

### 访问地址

- Metabase Web UI：http://localhost:8080（端口从3000改为8080）
- Metabase API健康检查：http://localhost:8080/api/health

### 配置步骤

1. **启动Metabase服务**：
   ```bash
   docker-compose -f docker-compose.metabase.yml up -d
   ```

2. **配置API密钥**（在`.env`文件中）：
   ```env
   METABASE_URL=http://localhost:8080
   METABASE_API_KEY=mb_xxxxxxxxxxxxx=
   ```

3. **访问Metabase**：
   - 首次访问：http://localhost:8080
   - 完成初始设置向导
   - 创建API Key（设置 → 认证 → API Keys）

### Metabase功能

- ✅ **数据查询**：SQL查询、可视化查询构建器
- ✅ **数据可视化**：多种图表类型、Dashboard
- ✅ **数据导出**：CSV、JSON、XLSX等格式
- ✅ **数据质量分析**：Question、Dashboard、告警

### 详细文档

- `docs/METABASE_DASHBOARD_SETUP.md` - Metabase配置完整指南
- `docs/DATA_BROWSER_AND_METABASE_TROUBLESHOOTING.md` - Metabase故障排查

