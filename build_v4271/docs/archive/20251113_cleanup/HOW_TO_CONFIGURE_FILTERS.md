# 📋 如何使用数据库浏览器配置筛选项

## 🎯 场景：配置产品管理页面的筛选项

### 问题背景
产品管理页面当前只有3个筛选项：
1. 平台（platform）
2. 关键词（keyword）
3. 低库存（low_stock）

**需求**：想要添加更多筛选项，比如：
- 分类筛选
- 价格区间筛选
- 销量筛选
- 状态筛选

**问题**：不知道有哪些字段可用？字段对应的数据库列名是什么？

---

## 🔍 解决方案：使用数据库浏览器的"接线员"功能

### 第1步：查看产品数据表

1. 打开**数据库浏览器**：`http://localhost:5173/#/data-browser`
2. 在左侧表列表中，找到**"事实表"**分类
3. 点击 `fact_product_metrics` 表
4. 中间面板显示产品数据，右侧显示32个字段

**您会看到**：
```
表结构信息
├── 表名: fact_product_metrics
├── 总行数: 1,234 (假设有数据)
└── 字段数: 32

字段列表:
- id
- platform_code          ← 平台
- shop_id               ← 店铺
- platform_sku          ← SKU
- product_name          ← 产品名称
- category              ← 分类 ⭐ 可用于筛选
- price                 ← 价格 ⭐ 可用于区间筛选
- currency              ← 货币
- stock                 ← 库存
- available_stock       ← 可售库存 ⭐ 可用于筛选
- total_stock          ← 总库存
- sales_volume         ← 销量 ⭐ 可用于筛选
- revenue              ← 营收
- page_views           ← 浏览量
- conversion_rate      ← 转化率
- rating               ← 评分 ⭐ 可用于筛选
- review_count         ← 评论数
- status               ← 状态 ⭐ 可用于筛选
- metric_date          ← 数据日期
- ... (更多字段)
```

---

### 第2步：使用"接线员"功能查看字段详情

**操作示例**：想要添加"分类筛选"

1. 在中间数据表格中，**点击 `category` 列头**
2. 弹出对话框，显示两个标签页

**映射关系标签页显示**：
```
🟢 直接匹配 (置信度: 100%)

数据库字段：category
映射辞典Field Code：product_category
中文名称：产品分类
数据域：products
字段分组：基础信息
是否必填：选填
数据类型：string
同义词：类目、品类、分类
示例值：Electronics, Clothing, Home & Garden
```

**使用链路标签页显示**：
```
后端API使用 (1个端点)
- API端点：/api/products/products
- 参数名：category
- 使用类型：filter
- 文件：backend/routers/product_management.py

前端组件使用 (1个组件)
- 组件名称：ProductManagement.vue
- 参数名：filters.category
- 文件：frontend/src/views/ProductManagement.vue

数据流向：
[数据库] category → [后端API] /api/products/products → [前端] ProductManagement.vue
```

---

### 第3步：根据字段信息配置前端筛选项

**现在您知道了**：
- ✅ 数据库字段名：`category`
- ✅ 后端API参数名：`category`（如果已实现）或需要添加
- ✅ 数据类型：字符串
- ✅ 可选值：需要从数据库查询distinct值

**在浏览器中查询可选值**：
1. 在数据库浏览器中，点击 `category` 列
2. 查看数据中有哪些不同的分类值（比如：电子产品、服装、家居等）

---

## 💻 实际配置代码示例

### 方案A：后端API已支持该字段（直接配置前端）

**前端代码修改** - `frontend/src/views/ProductManagement.vue`：

```vue
<!-- 添加分类筛选 -->
<el-form-item label="分类">
  <el-select v-model="filters.category" placeholder="选择分类" clearable style="width: 150px;">
    <el-option label="全部" value="" />
    <el-option label="电子产品" value="Electronics" />
    <el-option label="服装" value="Clothing" />
    <el-option label="家居用品" value="Home & Garden" />
  </el-select>
</el-form-item>

<!-- 添加价格区间筛选 -->
<el-form-item label="价格区间">
  <el-input v-model="filters.min_price" placeholder="最低价" style="width: 100px;" />
  <span style="margin: 0 8px;">-</span>
  <el-input v-model="filters.max_price" placeholder="最高价" style="width: 100px;" />
</el-form-item>

<!-- 添加状态筛选 -->
<el-form-item label="状态">
  <el-select v-model="filters.status" placeholder="选择状态" clearable style="width: 120px;">
    <el-option label="全部" value="" />
    <el-option label="在售" value="active" />
    <el-option label="已下架" value="inactive" />
  </el-select>
</el-form-item>
```

### 方案B：后端API不支持该字段（需要添加后端支持）

**步骤1：检查后端API是否支持**

在数据库浏览器中查看"使用链路"标签：
- 如果显示该字段在API中使用 ✅ 直接配置前端
- 如果没有显示 ❌ 需要先添加后端支持

**步骤2：添加后端API支持** - `backend/routers/product_management.py`：

```python
@router.get("/products")
async def get_products(
    platform: Optional[str] = None,
    keyword: Optional[str] = None,
    low_stock: bool = False,
    category: Optional[str] = None,      # ⭐ 新增：分类筛选
    min_price: Optional[float] = None,   # ⭐ 新增：最低价格
    max_price: Optional[float] = None,   # ⭐ 新增：最高价格
    status: Optional[str] = None,        # ⭐ 新增：状态筛选
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(FactProductMetric)
    
    # 平台筛选
    if platform:
        query = query.filter(FactProductMetric.platform_code == platform)
    
    # 分类筛选 ⭐ 新增
    if category:
        query = query.filter(FactProductMetric.category == category)
    
    # 价格区间筛选 ⭐ 新增
    if min_price is not None:
        query = query.filter(FactProductMetric.price >= min_price)
    if max_price is not None:
        query = query.filter(FactProductMetric.price <= max_price)
    
    # 状态筛选 ⭐ 新增
    if status:
        query = query.filter(FactProductMetric.status == status)
    
    # 关键词搜索
    if keyword:
        query = query.filter(
            (FactProductMetric.platform_sku.ilike(f"%{keyword}%")) |
            (FactProductMetric.product_name.ilike(f"%{keyword}%"))
        )
    
    # 低库存筛选
    if low_stock:
        query = query.filter(FactProductMetric.stock < 10)
    
    # 分页
    total = query.count()
    products = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "success": True,
        "data": products,
        "total": total
    }
```

**步骤3：更新前端API调用** - `frontend/src/views/ProductManagement.vue`：

```javascript
const loadProducts = async () => {
  loading.value = true
  try {
    const response = await api.getProducts({
      platform: filters.platform,
      keyword: filters.keyword,
      low_stock: filters.low_stock,
      category: filters.category,      // ⭐ 新增
      min_price: filters.min_price,    // ⭐ 新增
      max_price: filters.max_price,    // ⭐ 新增
      status: filters.status,          // ⭐ 新增
      page: pagination.page,
      page_size: pagination.pageSize
    })
    // ...
  }
}
```

---

## 🎯 使用数据库浏览器的优势

### 传统方式（盲目开发）
```
问题1：不知道有哪些字段可用
→ 需要查看数据库文档、问同事、看代码

问题2：不知道字段的数据类型
→ 需要查看schema.py、看数据库结构

问题3：不知道字段是否已在API中使用
→ 需要全局搜索代码、看API文档

问题4：不知道字段的实际数据分布
→ 需要写SQL查询、导出数据分析

总耗时：30-60分钟 ⏱️
```

### 使用数据库浏览器（智能配置）
```
步骤1：在数据库浏览器选择fact_product_metrics表
→ 立即看到所有32个字段

步骤2：点击字段列头查看详情
→ 看到映射关系、数据类型、使用链路

步骤3：在中间数据表格中查看实际数据
→ 看到字段的实际值、数据分布

步骤4：根据信息快速配置前端筛选项
→ 复制粘贴字段名，添加el-select组件

总耗时：3-5分钟 ⏱️
效率提升：10-20倍 🚀
```

---

## 📝 推荐的筛选项配置清单

基于`fact_product_metrics`表，这些字段适合做筛选项：

| 字段名 | 中文名称 | 筛选类型 | 优先级 | 说明 |
|--------|----------|----------|--------|------|
| `platform_code` | 平台 | 下拉选择 | ⭐⭐⭐ | 已实现 |
| `category` | 分类 | 下拉选择 | ⭐⭐⭐ | 推荐添加 |
| `status` | 状态 | 下拉选择 | ⭐⭐⭐ | 推荐添加 |
| `price` | 价格 | 区间输入 | ⭐⭐ | 推荐添加 |
| `stock` | 库存 | 区间输入 | ⭐⭐ | 已有低库存筛选 |
| `rating` | 评分 | 区间选择 | ⭐ | 可选添加 |
| `sales_volume` | 销量 | 区间输入 | ⭐ | 可选添加 |
| `metric_date` | 数据日期 | 日期范围 | ⭐ | 可选添加 |

---

## 🎬 立即演示：点击字段查看映射关系

**现在请您操作**：

1. 在当前数据库浏览器页面
2. 在左侧点击 **`fact_product_metrics`** 表
3. 等待数据加载
4. 在中间数据表格的列头，**点击 `category` 字段**
5. 查看弹出的对话框（映射关系 + 使用链路）

**您将看到**：
- ✅ 该字段对应的映射辞典信息
- ✅ 该字段的数据类型和示例值
- ✅ 该字段在哪些API中使用
- ✅ 该字段在哪些前端组件中显示

**有了这些信息，您就知道如何配置筛选项了！**

---

## 📚 下一步建议

1. **先体验功能**：点击几个字段看看映射关系和使用链路
2. **确定筛选字段**：决定要添加哪些筛选项
3. **告诉我需求**：比如"我想添加分类筛选和价格区间筛选"
4. **我来实现**：我会帮您完成后端API和前端界面的配置

**准备好了吗？请在浏览器中点击 `fact_product_metrics` 表，然后点击任意字段列头体验"接线员"功能！** 🚀

