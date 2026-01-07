# 用户使用手册

**版本**: v1.0  
**适用系统**: 跨境电商ERP数据管理系统  
**更新日期**: 2025-10-16  

---

## 📋 目录

- [快速开始](#快速开始)
- [系统概览](#系统概览)
- [数据采集](#数据采集)
- [数据管理](#数据管理)
- [数据看板](#数据看板)
- [字段映射](#字段映射)
- [常见问题](#常见问题)

---

## 快速开始

### 第一次使用

#### 1. 启动系统

```bash
# 方式1：启动Streamlit前端
streamlit run frontend_streamlit/main.py

# 方式2：使用命令行工具
python scripts/etl_cli.py --help
```

#### 2. 准备数据

将您的Excel数据文件放到以下目录：

```
temp/outputs/
├── shopee/
│   ├── account1/
│   │   └── products_20241016.xlsx
│   └── account2/
│       └── orders_20241016.xlsx
└── tiktok/
    └── shop123/
        └── products_20241016.xlsx
```

#### 3. 执行入库

**方式1：使用命令行**

```bash
# 一键完成扫描+入库
python scripts/etl_cli.py run temp/outputs --verbose

# 查看状态
python scripts/etl_cli.py status
```

**方式2：使用Web界面**

1. 打开浏览器访问 `http://localhost:8501`
2. 进入"数据管理中心"
3. 点击"📁 扫描目录并登记"
4. 点击"🏭 执行一次入库"

---

## 系统概览

### 功能模块

| 模块 | 功能 | 访问方式 |
|------|------|----------|
| 数据采集中心 | 自动采集平台数据 | 页面1 |
| 数据管理中心 | 管理数据入库 | 页面2 |
| 账号管理 | 管理账号配置 | 页面3 |
| 字段映射审核 | 审核和调整字段映射 | 页面4 |
| 统一数据看板 | 查看核心指标和趋势 | 页面5 |

### 数据流程

```
1. 数据采集
   ↓
2. 文件存储 (temp/outputs/)
   ↓
3. 文件扫描 (catalog_files表)
   ↓
4. 字段映射 (field_mappings.yaml)
   ↓
5. 数据入库 (dim_*/fact_*表)
   ↓
6. 数据查询 (DataQueryService)
   ↓
7. 前端展示 (Streamlit看板)
```

---

## 数据采集

### 自动采集

**支持平台**:
- ✅ Shopee（虾皮）
- ✅ TikTok Shop（抖音小店）
- ✅ 妙手ERP

**采集内容**:
- 产品数据（SKU、标题、图片、价格）
- 订单数据（订单号、金额、状态）
- 流量数据（浏览、访客、转化率）
- 财务数据（收入、支出、利润）

### 操作步骤

1. **配置账号**
   - 进入"账号管理"页面
   - 添加平台账号信息
   - 配置登录URL

2. **设置采集任务**
   - 进入"数据采集中心"
   - 选择平台和账号
   - 选择数据类型
   - 点击"开始采集"

3. **查看采集结果**
   - 采集完成后文件自动保存到`temp/outputs/`
   - 可以在"数据管理中心"查看文件列表

---

## 数据管理

### 数据入库

#### 方式1：命令行（推荐）

```bash
# 完整流程
python scripts/etl_cli.py run temp/outputs --verbose

# 分步执行
python scripts/etl_cli.py scan temp/outputs    # 步骤1：扫描
python scripts/etl_cli.py ingest --limit 100   # 步骤2：入库
python scripts/etl_cli.py status                # 步骤3：查看
```

#### 方式2：Web界面

1. 进入"数据管理中心"
2. 点击"📁 扫描目录并登记"
3. 点击"🏭 执行一次入库"
4. 观察进度和结果

#### 方式3：字段映射审核

1. 进入"字段映射审核"页面
2. 选择要处理的文件
3. 确认字段映射正确
4. 点击"✅ 确认映射并入库"

### 查看入库状态

**Web界面**:
- 进入"数据管理中心"
- 查看"Catalog状态概览"
- 查看"按数据域+状态统计"

**命令行**:
```bash
python scripts/etl_cli.py status --detail
```

### 处理失败文件

**查看失败原因**:

1. Web界面查看
   - 进入"数据管理中心"
   - 查看"最近失败的文件"列表

2. 命令行查看
   ```bash
   python scripts/etl_cli.py status --quarantine
   ```

**重试失败文件**:

1. 命令行重试
   ```bash
   # 重试所有失败文件
   python scripts/etl_cli.py retry --all
   
   # 重试特定文件
   python scripts/etl_cli.py retry --pattern "%shopee%"
   ```

2. Web界面重试
   - 进入"数据管理中心"
   - 点击"🔁 将最近N条失败重置为pending"

---

## 数据看板

### 统一数据看板

#### 访问方式

进入"统一数据看板"页面（页面5）

#### 核心功能

**1. 关键指标卡片**
- 总GMV（RMB）
- 订单总数
- 总销量
- 平均订单额

**2. GMV趋势图**
- 折线图展示每日GMV
- 可交互（hover查看详细数据）
- 可缩放、拖动

**3. Top 10产品榜单**
- 表格形式
- 水平柱状图
- 按GMV/销量排序

**4. 平台对比分析**
- 各平台GMV对比
- 饼图占比展示

**5. 订单趋势分析**
- 双Y轴图（订单数+金额）
- 每日明细表格

#### 筛选功能

**时间范围**:
- 近7天
- 近14天
- 近30天
- 近60天
- 近90天

**平台筛选**:
- 全部平台
- Shopee
- TikTok
- 妙手ERP
- Lazada

**指标类型**:
- GMV（销售额）
- 销量
- 浏览量
- 订单数

#### 使用技巧

**技巧1：对比分析**

1. 选择"全部平台"，查看整体趋势
2. 选择特定平台，查看单平台表现
3. 切换时间范围，观察长短期趋势

**技巧2：发现爆款**

1. 选择指标类型为"GMV"或"销量"
2. 查看Top 10产品榜单
3. 点击产品名称复制，用于进一步分析

**技巧3：刷新数据**

点击底部"🔄 刷新数据"按钮，清除缓存并重新加载。

---

## 字段映射

### 自动映射

系统会自动识别Excel文件中的字段，并映射到标准字段。

**支持的标准字段**:

| 标准字段 | 常见别名 |
|----------|----------|
| SKU | 商品SKU, Seller SKU, Item SKU, 款号 |
| 产品名称 | 商品名称, Product Name, Title |
| 销量 | 已售数量, 销售数量, Units Sold |
| 销售额 | GMV, 商品交易总额, Revenue |
| 订单号 | 订单编号, Order ID, 单号 |
| 下单时间 | 订单日期, Order Date, 支付时间 |

### 审核流程

1. **选择文件**
   - 进入"字段映射审核"页面
   - 选择平台、数据域
   - 选择要审核的文件

2. **查看预览**
   - 系统显示Excel前20行
   - 查看数据是否正确

3. **确认映射**
   - 查看"智能字段映射"结果
   - 确认映射是否正确

4. **执行入库**
   - 点击"✅ 确认映射并入库"
   - 等待处理完成
   - 查看结果统计

### 自定义映射

如果自动映射不准确，可以编辑配置文件：

**文件**: `config/field_mappings.yaml`

```yaml
your_platform:
  sku:
    - "自定义SKU列名"
  product_name:
    - "自定义产品名列名"
  sales:
    - "自定义销量列名"
```

编辑后重新扫描文件即可生效。

---

## 常见问题

### Q1: 文件扫描后找不到？

**检查**:
1. 文件是否在`temp/outputs/`目录下
2. 文件格式是否支持（.xlsx/.xls/.csv）
3. 文件是否被其他程序占用

**解决**:
```bash
# 重新扫描
python scripts/etl_cli.py scan temp/outputs

# 查看catalog
python scripts/etl_cli.py status
```

---

### Q2: 入库失败，怎么办？

**查看失败原因**:
1. Web界面："数据管理中心" → "最近失败的文件"
2. 命令行：`python scripts/etl_cli.py status --quarantine`

**常见失败原因**:
- 缺少必填字段（SKU、Shop ID）
- 数据格式错误
- Excel文件损坏

**解决方法**:
1. 检查Excel文件格式
2. 补充缺失字段
3. 使用字段映射审核页面手动确认

---

### Q3: 数据看板显示"暂无数据"？

**原因**:
1. 数据还没有入库
2. 筛选条件太严格
3. 数据库没有该时间范围的数据

**解决**:
1. 先执行数据入库
2. 调整筛选条件（扩大时间范围）
3. 点击"刷新数据"

---

### Q4: 如何清理旧数据？

**命令行方式**:
```bash
# 清理30天前已入库的catalog记录
python scripts/etl_cli.py cleanup --days 30 --dry-run  # 预览
python scripts/etl_cli.py cleanup --days 30            # 执行
```

**数据库方式**:
```sql
-- 删除旧的catalog记录
DELETE FROM catalog_files
WHERE status = 'ingested'
AND processed_at < date('now', '-30 days');

-- VACUUM优化
VACUUM;
```

---

### Q5: 性能慢怎么办？

**检查**:
1. 缓存是否生效？
2. 数据库索引是否存在？
3. 查询limit是否合理？

**优化**:
1. 使用缓存（5分钟自动缓存）
2. 运行性能优化迁移：
   ```bash
   python -m alembic upgrade head
   ```
3. 减小查询范围（时间、limit）

---

### Q6: 如何备份数据？

**备份数据库**:
```bash
# 复制数据库文件
cp data/unified_erp_system.db backups/db_20241016.db

# 或使用SQLite dump
sqlite3 data/unified_erp_system.db ".dump" > backup.sql
```

**备份数据文件**:
```bash
# 复制temp/outputs目录
cp -r temp/outputs backups/outputs_20241016/
```

---

### Q7: 如何导出数据？

**Web界面导出**:
1. 进入"数据管理中心"
2. 选择"数据导出"分区
3. 输入SQL查询（仅SELECT）
4. 点击"执行查询"
5. 复制数据到Excel

**命令行导出**:
```bash
# 导出订单数据
sqlite3 data/unified_erp_system.db -header -csv \
  "SELECT * FROM fact_orders WHERE order_date_local >= '2024-10-01';" \
  > orders_export.csv
```

---

## 💡 使用技巧

### 技巧1：批量入库

**场景**: 积累了大量文件需要批量处理

**方法**:
```bash
# 一次处理1000个文件
python scripts/etl_cli.py ingest --limit 1000 -v

# 或分批处理
for i in {1..10}; do
    python scripts/etl_cli.py ingest --limit 100
    sleep 5
done
```

### 技巧2：自动化定时入库

创建定时任务脚本：

```python
# scripts/scheduled_etl.py
import schedule
import time

def hourly_job():
    # 每小时执行ETL
    os.system('python scripts/etl_cli.py run temp/outputs')

schedule.every().hour.at(":05").do(hourly_job)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### 技巧3：监控数据质量

定期检查：
1. Catalog失败率（应该<5%）
2. 数据隔离表（data_quarantine）
3. 字段映射准确率

---

## 🔧 高级功能

### 自定义SQL查询

进入"数据管理中心" → "数据导出"：

```sql
-- 查询近30天每日GMV
SELECT 
    metric_date,
    SUM(metric_value_rmb) as daily_gmv
FROM fact_product_metrics
WHERE metric_type = 'gmv'
AND metric_date >= date('now', '-30 days')
GROUP BY metric_date
ORDER BY metric_date DESC;
```

### 性能监控

**查看缓存统计**:
```python
from modules.services.cache_service import get_cache_stats

stats = get_cache_stats()
print(f"内存缓存: {stats['memory_cache_count']}")
print(f"文件缓存: {stats['file_cache_count']}")
print(f"总大小: {stats['total_size_mb']:.2f} MB")
```

---

## 📞 获取帮助

### 文档资源

- **API参考**: `docs/API_REFERENCE.md`
- **故障排查**: `docs/TROUBLESHOOTING.md`
- **开发指南**: `docs/DEVELOPMENT_ROADMAP.md`

### 常用命令速查

```bash
# 查看帮助
python scripts/etl_cli.py --help

# 扫描文件
python scripts/etl_cli.py scan temp/outputs

# 查看状态
python scripts/etl_cli.py status --detail

# 执行入库
python scripts/etl_cli.py ingest --limit 100 -v

# 完整流程
python scripts/etl_cli.py run temp/outputs

# 重试失败
python scripts/etl_cli.py retry --all

# 清理旧数据
python scripts/etl_cli.py cleanup --days 30
```

---

## 🎓 最佳实践

### 1. 数据文件命名

**推荐格式**:
```
{platform}__{account}__{shop_id}__{data_type}__YYYYMMDD.xlsx
```

**示例**:
```
shopee__my_account__shop123__products__20241016.xlsx
tiktok__shop456__shop456__orders__20241016.xlsx
```

**优势**:
- ✅ 系统自动识别平台
- ✅ 自动推断shop_id
- ✅ 自动推断数据类型
- ✅ 自动推断日期

### 2. 定期维护

**每天**:
- 执行数据入库
- 检查失败文件
- 查看数据看板

**每周**:
- 清理旧catalog记录
- 检查数据质量
- 备份数据库

**每月**:
- VACUUM数据库
- 归档旧文件
- 性能优化检查

### 3. 数据安全

**重要**:
- ✅ 定期备份数据库
- ✅ 不要删除原始文件
- ✅ 失败数据会自动隔离
- ✅ 操作前先dry-run

---

**手册版本**: v1.0  
**最后更新**: 2025-10-16  
**适用版本**: ERP系统 v3.0+  
**技术支持**: 查看文档或联系开发团队

