# 📸 产品图片管理完整指南

**版本**: v4.6.1  
**更新日期**: 2025-11-04  
**适用范围**: 西虹ERP系统产品图片管理

---

## 📋 目录

1. [系统架构](#系统架构)
2. [快速开始](#快速开始)
3. [三种入库方式](#三种入库方式)
4. [字段映射配置](#字段映射配置)
5. [前端显示配置](#前端显示配置)
6. [高级功能](#高级功能)
7. [故障排查](#故障排查)

---

## 🏗️ 系统架构

### 数据库设计

#### 1. DimProduct表（产品维表）

**用途**: 存储产品基础信息和主图

```sql
CREATE TABLE dim_products (
    platform_code VARCHAR(32),
    shop_id VARCHAR(64),
    platform_sku VARCHAR(128),
    product_title VARCHAR(512),
    
    -- 图片字段 ⭐
    image_url VARCHAR(1024),              -- 图片URL（列表显示用）
    image_path VARCHAR(512),              -- 本地图片路径（可选）
    image_last_fetched_at TIMESTAMP,      -- 图片最后获取时间
    
    -- 其他字段...
    PRIMARY KEY (platform_code, shop_id, platform_sku)
);
```

**设计理念**:
- `image_url`: 主图URL，用于列表快速显示
- `image_path`: 下载后的本地路径（离线访问）
- `image_last_fetched_at`: 图片更新追踪

---

#### 2. ProductImage表（独立图片管理）

**用途**: 支持多图管理和高级功能

```sql
CREATE TABLE product_images (
    id SERIAL PRIMARY KEY,
    
    -- 产品标识（三元组）
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    platform_sku VARCHAR(128) NOT NULL,
    
    -- 图片URL
    image_url VARCHAR(1024) NOT NULL,      -- 原图URL
    thumbnail_url VARCHAR(1024) NOT NULL,  -- 缩略图URL
    
    -- 图片类型和顺序
    image_type VARCHAR(20) DEFAULT 'main', -- main/detail/spec
    image_order INTEGER DEFAULT 0,         -- 显示顺序
    is_main_image BOOLEAN DEFAULT FALSE,   -- 是否主图
    
    -- 图片元数据
    file_size INTEGER,                     -- 文件大小(bytes)
    width INTEGER,                         -- 宽度(px)
    height INTEGER,                        -- 高度(px)
    format VARCHAR(10),                    -- JPEG/PNG/GIF
    quality_score FLOAT,                   -- 质量评分(0-100, AI识别)
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    INDEX idx_product_images_sku (platform_sku),
    INDEX idx_product_images_product (platform_code, shop_id, platform_sku)
);
```

**设计理念**:
- 支持一个SKU多张图片
- 图片类型分类（主图、详情图、规格图）
- 图片质量评分（预留AI功能）
- 显示顺序控制

---

### 图片类型分类

| image_type | 中文名 | 用途 | 显示位置 |
|-----------|--------|------|---------|
| main | 主图 | 产品主要展示图 | 列表页、搜索结果 |
| detail | 详情图 | 产品细节展示 | 详情页轮播 |
| spec | 规格图 | 尺寸、参数图 | 详情页规格区域 |

---

## 🚀 快速开始（5分钟）

### miaoshou产品快照图片入库

#### 步骤1: 准备工作（已完成）✅

- ✅ image_url字段已添加到辞典
- ✅ snapshot粒度已支持
- ✅ 产品管理页面已支持图片显示

#### 步骤2: 字段映射配置

**操作流程**:
```
1. 打开"字段映射审核"页面
   
2. 文件选择：
   选择平台: miaoshou
   选择数据域: 产品
   选择粒度: 📸 快照（全量导出）
   选择文件: miaoshou_products_snapshot_*.xlsx
   
3. 预览数据：
   点击"预览数据"按钮
   查看前100行数据
   确认"商品图片"列存在

4. 字段映射：
   找到"商品图片"行
   点击"标准字段"下拉框
   选择"image_url" ← 关键！
   
5. 其他字段映射：
   商品SKU → platform_sku ✅
   商品名称 → product_name ✅
   商品图片 → image_url ⭐
   规格 → specification
   单价(元) → price
   库存总量 → total_stock
   在途库存 → stock_in_transit
   可用库存 → available_stock
   仓库 → warehouse
   
6. 确认入库：
   点击"确认映射并入库(25个字段)"
   等待入库完成
```

#### 步骤3: 验证结果

```
1. 进入"产品管理"页面
   导航: 产品与库存 → 产品管理
   
2. 筛选miaoshou产品：
   选择平台: 妙手
   点击"查询"
   
3. 查看图片：
   产品列表左侧应该显示产品图片
   点击图片可以预览大图
```

---

## 🎨 三种入库方式详解

### 方式1: URL字段映射（推荐）⭐⭐⭐⭐⭐

#### 适用场景
- miaoshou的"商品图片"列是**图片URL字符串**
- 图片托管在稳定的CDN或服务器
- 不需要本地存储

#### 数据流程
```
miaoshou Excel
  ↓ 商品图片列
"https://img.miaoshou.com/products/123.jpg"
  ↓ 字段映射
image_url字段
  ↓ 数据入库
dim_products表
  ↓ 前端查询
ProductManagement页面
  ↓ 显示
<el-image :src="image_url" />
```

#### 实施步骤
1. ✅ 字段映射: 商品图片 → image_url
2. ✅ 数据入库
3. ✅ 前端自动显示

#### 优缺点

**优点**:
- ✅ 5分钟配置完成
- ✅ 零额外服务
- ✅ 零存储开销
- ✅ 实时显示最新图片
- ✅ 图片更新自动生效

**缺点**:
- ⚠️ 依赖外部URL可用性
- ⚠️ 图片加载受网络影响
- ⚠️ 外部URL失效会显示占位图

---

### 方式2: Excel嵌入图片提取（自动）⭐⭐⭐⭐

#### 适用场景
- Excel文件中**嵌入了实际图片**（不是URL）
- 需要本地化存储
- 有Celery运行环境

#### 数据流程
```
miaoshou Excel
  ↓ 嵌入图片
[Excel中插入的图片对象]
  ↓ 数据入库完成
自动触发Celery异步任务
  ↓ 图片提取
openpyxl提取嵌入图片
  ↓ 关联SKU
按行匹配SKU
  ↓ 图片处理
压缩 + 生成缩略图(200x200)
  ↓ 保存
ProductImage表
  ↓ 前端JOIN查询
显示多图+缩略图
```

#### 后端实现

**Celery任务** (`backend/tasks/image_extraction.py`):
```python
@celery_app.task(name="extract_product_images")
def extract_product_images_task(file_id, file_path, platform_code, shop_id):
    """
    异步提取Excel中的产品图片
    
    步骤:
    1. 读取Excel，查找SKU列
    2. 提取所有嵌入图片
    3. 按行关联图片到SKU
    4. 压缩和生成缩略图
    5. 保存到ProductImage表
    """
    # 1. 提取图片
    extractor = get_image_extractor()
    sku_images = extractor.extract_with_sku_mapping(
        file_path, 
        sku_column='商品SKU'
    )
    
    # 2. 处理图片
    processor = get_image_processor()
    for sku, images in sku_images.items():
        for idx, img_data in enumerate(images):
            # 压缩和缩略图
            result = processor.process_product_image(img_data, sku, idx)
            
            # 保存到数据库
            ProductImage(
                platform_sku=sku,
                image_url=result['original_url'],
                thumbnail_url=result['thumbnail_url'],
                is_main_image=(idx == 0)
            )
```

#### 环境配置

**1. 安装Redis**:
```bash
docker run -d -p 6379:6379 --name erp-redis redis:alpine
```

**2. 配置环境变量**:
```bash
# .env
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

**3. 启动Celery Worker**:
```bash
cd F:\Vscode\python_programme\AI_code\xihong_erp
celery -A backend.celery_app worker --loglevel=info --pool=solo
```

#### 触发方式

**自动触发**:
```python
# backend/routers/field_mapping.py (第1115-1135行)
# 数据入库成功后自动触发
if extract_images and imported > 0:
    extract_product_images_task.delay(
        file_id=file_id,
        file_path=file_record.file_path,
        platform_code=platform,
        shop_id=file_record.shop_id
    )
```

#### 优缺点

**优点**:
- ✅ 全自动处理，无需手动操作
- ✅ 支持多图（一个SKU多张图片）
- ✅ 图片本地化存储
- ✅ 缩略图优化加载
- ✅ 图片元数据完整

**缺点**:
- ⚠️ 需要Celery+Redis环境
- ⚠️ 需要配置图片存储目录
- ⚠️ 占用本地存储空间
- ⚠️ Excel文件需要嵌入图片

---

### 方式3: URL下载本地化（计划中）⭐⭐⭐

#### 适用场景
- 已有image_url数据
- 需要图片本地化
- 提升加载速度

#### 数据流程
```
dim_products.image_url（已入库）
  ↓ 定时任务
下载图片到本地
  ↓ 保存
data/images/{platform}/{shop}/{sku}.jpg
  ↓ 更新数据库
dim_products.image_path
  ↓ 前端优先使用
本地路径（更快）
```

#### 实现示例

```python
# backend/tasks/image_download.py（待开发）
@celery_app.task(name="download_product_images")
def download_product_images():
    """定时下载产品图片到本地"""
    
    # 1. 查询需要下载的产品
    products = db.query(DimProduct).filter(
        DimProduct.image_url.isnot(None),      # 有URL
        DimProduct.image_path.is_(None)        # 但无本地路径
    ).limit(100).all()  # 每次100个
    
    for product in products:
        try:
            # 2. 下载图片
            response = requests.get(product.image_url, timeout=10)
            image_data = response.content
            
            # 3. 保存到本地
            local_dir = Path('data/images') / product.platform_code / product.shop_id
            local_dir.mkdir(parents=True, exist_ok=True)
            
            local_path = local_dir / f"{product.platform_sku}.jpg"
            local_path.write_bytes(image_data)
            
            # 4. 更新数据库
            product.image_path = str(local_path)
            product.image_last_fetched_at = datetime.now()
            
            logger.info(f"[Download] 图片已下载: {product.platform_sku}")
            
        except Exception as e:
            logger.error(f"[Download] 下载失败: {product.platform_sku}, {e}")
            continue
    
    db.commit()
```

#### 定时配置

```python
# backend/celery_app.py
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'download-product-images': {
        'task': 'download_product_images',
        'schedule': crontab(hour=2, minute=0),  # 每天凌晨2点
    },
}
```

#### 优缺点

**优点**:
- ✅ 图片本地化（不依赖外部）
- ✅ 加载速度快
- ✅ 离线可用
- ✅ 图片CDN失效不影响

**缺点**:
- ⚠️ 需要开发下载任务（~2小时）
- ⚠️ 需要定期更新图片
- ⚠️ 占用存储空间（大约每个产品100-500KB）
- ⚠️ 需要处理URL失效情况

---

## 📝 字段映射配置

### 标准字段定义

#### image_url字段（已添加）✅

```json
{
  "field_code": "image_url",
  "cn_name": "商品图片URL",
  "en_name": "Product Image URL",
  "synonyms": [
    "商品图片", "产品图片", "图片链接", "图片地址", 
    "图片URL", "image", "picture", "photo", "商品图", "图片"
  ],
  "data_domain": "products",
  "is_required": false,
  "data_type": "string",
  "description": "产品图片URL地址，支持http/https链接",
  "example_values": [
    "https://img.example.com/product.jpg",
    "https://cdn.miaoshou.com/123.png"
  ]
}
```

### miaoshou产品快照字段映射表

| 原始字段（miaoshou） | 标准字段（系统） | 优先级 | 说明 |
|---------------------|----------------|--------|------|
| *商品SKU | platform_sku | ⭐⭐⭐ | 必填，唯一标识 |
| 商品名称 | product_name | ⭐⭐⭐ | 必填，产品标题 |
| **商品图片** | **image_url** | **⭐⭐** | **推荐**，图片URL |
| 规格 | specification | ⭐ | 产品规格 |
| 单价(元) | price | ⭐⭐ | 商品价格 |
| 库存总量 | total_stock | ⭐⭐ | 库存数量 |
| 在途库存 | stock_in_transit | ⭐ | 在途数量 |
| 可用库存 | available_stock | ⭐⭐ | 可售库存 |
| 仓库 | warehouse | ⭐ | 仓库位置 |
| 近7天销量数据 | sales_last_7_days | ⭐ | 近期销售 |
| 近30天销量数据 | sales_last_30_days | ⭐ | 月度销售 |

### 智能匹配规则

系统会自动匹配"商品图片"字段到`image_url`：

**匹配逻辑**:
```python
# 原始列名："商品图片"
# 同义词列表: ["商品图片", "产品图片", "图片链接", ...]
# 匹配方式: 精确匹配或模糊匹配
# 置信度: 95%+
```

---

## 🖼️ 前端显示配置

### 产品列表页面（ProductManagement.vue）

#### 当前实现

```vue
<template>
  <el-table :data="products">
    <!-- 产品图片列 -->
    <el-table-column label="产品图片" width="100">
      <template #default="{ row }">
        <el-image 
          :src="row.thumbnail_url || row.image_url || '/placeholder.png'"
          fit="cover"
          style="width: 60px; height: 60px; border-radius: 4px; cursor: pointer;"
          :preview-src-list="row.all_images || [row.image_url]"
          lazy
          @click="viewProduct(row)"
        >
          <template #error>
            <div class="image-placeholder">
              <el-icon :size="24" color="#ccc"><Picture /></el-icon>
            </div>
          </template>
        </el-image>
      </template>
    </el-table-column>
    
    <!-- 其他列... -->
  </el-table>
</template>
```

#### 图片显示逻辑

```javascript
// 图片优先级
const getProductImage = (product) => {
    // 优先级1: 缩略图（ProductImage表）
    if (product.thumbnail_url) return product.thumbnail_url
    
    // 优先级2: 主图URL（dim_products表）
    if (product.image_url) return product.image_url
    
    // 优先级3: 占位图
    return '/placeholder.png'
}
```

#### 图片预览功能

```vue
<!-- 点击图片预览大图 -->
<el-image 
  :preview-src-list="row.all_images"  <!-- 支持多图预览 -->
>
```

**all_images格式**:
```javascript
[
  'https://img.miaoshou.com/product1.jpg',
  'https://img.miaoshou.com/product2.jpg',
  'https://img.miaoshou.com/product3.jpg'
]
```

---

### 产品详情页面（ProductDetail.vue - 计划中）

#### 多图轮播展示

```vue
<template>
  <el-card class="product-detail">
    <!-- 图片轮播 -->
    <el-row :gutter="20">
      <el-col :span="12">
        <el-carousel :interval="5000" arrow="always" height="500px">
          <el-carousel-item v-for="(image, index) in product.images" :key="index">
            <el-image 
              :src="image.image_url" 
              fit="contain"
              style="width: 100%; height: 100%;"
            />
          </el-carousel-item>
        </el-carousel>
        
        <!-- 缩略图选择 -->
        <div class="thumbnail-list">
          <el-image 
            v-for="(image, index) in product.images" 
            :key="index"
            :src="image.thumbnail_url"
            fit="cover"
            style="width: 80px; height: 80px; cursor: pointer;"
            @click="selectImage(index)"
          />
        </div>
      </el-col>
      
      <!-- 产品信息 -->
      <el-col :span="12">
        <h2>{{ product.product_name }}</h2>
        <p>SKU: {{ product.platform_sku }}</p>
        <p>价格: ¥{{ product.price }}</p>
        <p>库存: {{ product.total_stock }}</p>
        <!-- 更多信息... -->
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'

const product = ref({})

const loadProductDetail = async (sku) => {
  // 查询产品基础信息
  const response = await api.getProduct(sku)
  product.value = response.data
  
  // 查询产品图片（JOIN ProductImage表）
  const imagesResponse = await api.getProductImages(sku)
  product.value.images = imagesResponse.data
}

onMounted(() => {
  loadProductDetail(route.params.sku)
})
</script>
```

---

## 🔧 高级功能

### 1. 图片质量检测（预留）

```python
# backend/services/image_quality.py（待开发）
def analyze_image_quality(image_path):
    """
    AI图片质量分析
    
    检查项：
    - 分辨率（推荐≥800x800）
    - 文件大小（推荐<500KB）
    - 图片清晰度
    - 是否有水印
    - 背景是否干净
    
    返回：
    - quality_score: 0-100分
    - suggestions: 改进建议
    """
    from PIL import Image
    
    img = Image.open(image_path)
    width, height = img.size
    
    score = 100
    suggestions = []
    
    # 分辨率检查
    if width < 800 or height < 800:
        score -= 20
        suggestions.append(f"分辨率较低({width}x{height})，建议≥800x800")
    
    # 文件大小检查
    file_size = Path(image_path).stat().st_size
    if file_size > 500 * 1024:
        score -= 10
        suggestions.append(f"文件过大({file_size/1024:.0f}KB)，建议压缩")
    
    return {
        'quality_score': score,
        'width': width,
        'height': height,
        'file_size': file_size,
        'suggestions': suggestions
    }
```

---

### 2. 图片CDN优化（未来）

#### 架构设计

```
原始图片URL
  ↓ 上传
阿里云OSS / 腾讯云COS
  ↓ 自动处理
图片压缩 + CDN加速
  ↓ 更新
dim_products.image_url
  ↓ 前端访问
CDN加速URL（极速）
```

#### 配置示例

```python
# backend/services/cdn_uploader.py
class CDNUploader:
    def upload_product_image(self, local_path, sku):
        """上传图片到CDN"""
        # 1. 上传到OSS
        oss_url = oss_client.upload(local_path, f"products/{sku}.jpg")
        
        # 2. 更新数据库
        product = db.query(DimProduct).filter_by(platform_sku=sku).first()
        product.image_url = oss_url
        db.commit()
        
        return oss_url
```

---

### 3. 多图管理（ProductImage表）

#### 查询产品所有图片

```python
# backend/routers/products.py
@router.get("/products/{sku}/images")
async def get_product_images(sku: str, db: Session = Depends(get_db)):
    """获取产品所有图片"""
    images = db.query(ProductImage).filter(
        ProductImage.platform_sku == sku
    ).order_by(
        ProductImage.image_order.asc()
    ).all()
    
    return {
        'success': True,
        'images': [
            {
                'id': img.id,
                'url': img.image_url,
                'thumbnail': img.thumbnail_url,
                'type': img.image_type,
                'is_main': img.is_main_image,
                'order': img.image_order,
                'size': f"{img.width}x{img.height}",
                'format': img.format
            }
            for img in images
        ]
    }
```

#### 上传新图片

```python
@router.post("/products/{sku}/images")
async def upload_product_image(
    sku: str,
    file: UploadFile,
    image_type: str = 'detail',
    db: Session = Depends(get_db)
):
    """上传产品图片"""
    # 1. 保存文件
    local_path = save_upload_file(file, sku)
    
    # 2. 处理图片
    processor = get_image_processor()
    result = processor.process_product_image(local_path, sku)
    
    # 3. 保存到数据库
    image = ProductImage(
        platform_sku=sku,
        image_url=result['original_url'],
        thumbnail_url=result['thumbnail_url'],
        image_type=image_type,
        file_size=result['file_size'],
        width=result['width'],
        height=result['height'],
        format=result['format']
    )
    db.add(image)
    db.commit()
    
    return {'success': True, 'image_id': image.id}
```

---

## 🎯 使用场景

### 场景1: miaoshou库存快照图片入库

**文件**: `miaoshou_products_snapshot_20250925_113119.xlsx`

**字段映射**:
```
商品SKU → platform_sku ✅
商品名称 → product_name ✅
商品图片 → image_url ⭐ 关键！
在途库存 → stock_in_transit
可用库存 → available_stock
```

**查看效果**:
```
产品管理 → 筛选platform=miaoshou → 图片显示
```

---

### 场景2: Shopee产品图片抓取

**方式**: 使用平台API获取图片URL

```python
# modules/platforms/shopee/api_client.py
def get_product_detail(item_id):
    """获取Shopee产品详情（包括图片）"""
    response = api.get(f'/product/get_item_detail?item_id={item_id}')
    
    return {
        'sku': response['item']['item_sku'],
        'name': response['item']['name'],
        'image_url': response['item']['images'][0],  # 主图
        'images': response['item']['images']  # 所有图片
    }
```

**入库**:
```python
product = DimProduct(
    platform_sku=data['sku'],
    product_name=data['name'],
    image_url=data['image_url']  # ← 图片URL
)
db.add(product)
```

---

### 场景3: Excel嵌入图片自动提取

**文件**: Excel中插入了实际图片对象

**配置**:
```bash
# 1. 启动Redis
docker run -d -p 6379:6379 redis:alpine

# 2. 启动Celery
celery -A backend.celery_app worker --pool=solo
```

**入库**:
```
正常进行数据入库
→ 系统自动触发图片提取
→ 后台任务处理图片
→ 保存到ProductImage表
```

---

## 🔍 故障排查

### 问题1: 图片不显示

**症状**: 产品列表中图片显示为占位图标

**排查步骤**:

1. **检查数据库是否有image_url**:
```sql
SELECT platform_sku, product_name, image_url 
FROM dim_products 
WHERE platform_code = 'miaoshou' 
LIMIT 10;
```

2. **检查URL是否有效**:
- 复制image_url
- 在浏览器中直接打开
- 确认图片可以访问

3. **检查前端是否正确传递**:
```javascript
// 浏览器Console
console.log(products.value[0].image_url)
```

4. **检查网络请求**:
- F12打开开发者工具
- Network标签
- 查看图片请求状态（200 OK）

---

### 问题2: 图片字段未映射

**症状**: 入库成功但image_url为空

**原因**: 字段映射时未映射"商品图片"字段

**解决**:
1. 重新打开字段映射审核
2. 选择文件
3. 预览数据
4. **确认"商品图片"映射到"image_url"**
5. 重新入库

---

### 问题3: Celery图片提取不工作

**症状**: 入库成功但ProductImage表无数据

**排查**:

1. **检查Celery是否运行**:
```bash
# 查看进程
ps aux | grep celery

# 查看日志
celery -A backend.celery_app worker --loglevel=debug
```

2. **检查Redis连接**:
```bash
redis-cli ping
# 应返回: PONG
```

3. **检查Excel是否有嵌入图片**:
```python
from openpyxl import load_workbook
wb = load_workbook('file.xlsx')
ws = wb.active
print(f"图片数量: {len(ws._images)}")
```

---

## 📊 性能优化

### 1. 图片懒加载

```vue
<el-image 
  :src="product.image_url"
  lazy  <!-- Element Plus自动懒加载 -->
/>
```

**优点**:
- 只加载可视区域的图片
- 滚动时动态加载
- 节省带宽和加载时间

---

### 2. 缩略图优化

```python
# backend/services/image_processor.py
def generate_thumbnail(image_path, size=(200, 200)):
    """生成缩略图"""
    from PIL import Image
    
    img = Image.open(image_path)
    img.thumbnail(size, Image.LANCZOS)
    
    thumbnail_path = image_path.replace('.jpg', '_thumb.jpg')
    img.save(thumbnail_path, quality=85)
    
    return thumbnail_path
```

**使用**:
```vue
<!-- 列表用缩略图，详情用原图 -->
<el-image :src="thumbnail_url" />  <!-- 200x200 -->
```

---

### 3. CDN加速

```python
# config/cdn.py
CDN_CONFIG = {
    'provider': 'aliyun',  # aliyun/tencent/qiniu
    'domain': 'https://cdn.xihong-erp.com',
    'bucket': 'product-images',
    'access_key': 'YOUR_ACCESS_KEY',
    'secret_key': 'YOUR_SECRET_KEY'
}
```

**URL转换**:
```python
# 原始URL
https://img.miaoshou.com/products/123.jpg

# CDN URL
https://cdn.xihong-erp.com/products/123.jpg?x-oss-process=image/resize,w_200
```

---

## 📈 统计和监控

### 图片覆盖率统计

```sql
-- 产品图片覆盖率
SELECT 
    platform_code,
    COUNT(*) as total_products,
    COUNT(image_url) as with_image,
    ROUND(COUNT(image_url)::float / COUNT(*) * 100, 2) as coverage_rate
FROM dim_products
GROUP BY platform_code;
```

**示例输出**:
```
platform | total | with_image | coverage
---------|-------|------------|----------
miaoshou | 1216  | 980        | 80.59%
shopee   | 523   | 523        | 100.00%
tiktok   | 312   | 298        | 95.51%
```

---

### 图片质量报告

```sql
-- 从ProductImage表获取图片质量统计
SELECT 
    platform_code,
    AVG(quality_score) as avg_quality,
    AVG(file_size / 1024) as avg_size_kb,
    AVG(width) as avg_width,
    AVG(height) as avg_height
FROM product_images
GROUP BY platform_code;
```

---

## 🎓 最佳实践

### 1. 图片URL规范

**推荐格式**:
```
https://cdn.domain.com/products/{platform}/{shop}/{sku}.jpg
```

**不推荐**:
```
C:\images\product.jpg  （本地绝对路径）
./images/product.jpg   （相对路径）
data:image/jpeg;base64,/9j/...  （Base64，太长）
```

---

### 2. 图片命名规范

```
{platform_sku}_main.jpg      - 主图
{platform_sku}_detail_1.jpg  - 详情图1
{platform_sku}_detail_2.jpg  - 详情图2
{platform_sku}_spec.jpg      - 规格图
```

---

### 3. 图片存储规范

**目录结构**:
```
data/images/
├── miaoshou/
│   ├── shop001/
│   │   ├── HJJ-XH-SHTMK001.jpg
│   │   ├── HJJ-XH-SHTMK001_thumb.jpg
│   │   └── ...
│   └── shop002/
├── shopee/
└── tiktok/
```

**大小限制**:
- 原图: ≤2MB
- 缩略图: ≤100KB
- 格式: JPEG（推荐），PNG，WebP

---

## 📋 操作检查清单

### miaoshou库存快照图片入库

- [ ] image_url字段已添加到辞典 ✅（已完成）
- [ ] 选择粒度为"📸 快照"
- [ ] 预览数据确认"商品图片"列存在
- [ ] 映射"商品图片" → "image_url"
- [ ] 确认映射并入库
- [ ] 查看产品管理页面
- [ ] 图片正常显示

---

## 🚀 下一步优化建议

### 短期（1-2周）

1. **完善产品管理页面**
   - [ ] 添加图片上传功能
   - [ ] 支持多图展示
   - [ ] 图片编辑和裁剪

2. **图片质量管理**
   - [ ] 检测低质量图片
   - [ ] 批量压缩优化
   - [ ] 图片格式转换

### 中期（1-2月）

1. **图片CDN集成**
   - [ ] 接入阿里云OSS
   - [ ] 自动上传和同步
   - [ ] CDN加速配置

2. **智能图片功能**
   - [ ] AI去背景
   - [ ] 智能裁剪
   - [ ] 水印添加

---

## 🎯 总结

### ✅ 当前能力

1. **数据库支持** - 双层图片架构（dim_products + product_images）
2. **字段辞典** - image_url标准字段已添加
3. **前端显示** - 产品管理页面已支持图片显示
4. **后端服务** - Celery图片提取服务已实现（需激活）

### 🚀 立即可用

**URL字段映射方式（推荐）**:
- ✅ 5分钟配置
- ✅ 零额外服务
- ✅ 立即显示图片

**操作**: 字段映射时将"商品图片" → "image_url"

---

**文档版本**: v1.0  
**最后更新**: 2025-11-04  
**维护人**: AI Assistant

