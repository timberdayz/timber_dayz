# v3.0 产品可视化管理开发计划

**版本**: v3.0  
**预计开发时间**: 2-3周  
**目标**: 实现SKU级产品可视化管理，支持图片显示和运营

---

## 功能目标

### 核心功能
1. **SKU级产品管理**: 查看、编辑、删除产品
2. **图片展示**: 缩略图列表 + 大图预览
3. **图片管理**: 上传、删除、排序主图/详情图
4. **图片搜索**: 按SKU、名称搜索产品及图片
5. **批量操作**: 批量上传图片、批量编辑

---

## 技术架构

### 后端服务

#### 1. 图片提取服务
```python
# backend/services/image_extractor.py（新增）

from openpyxl import load_workbook
from PIL import Image
from io import BytesIO

class ImageExtractor:
    """从Excel提取嵌入图片"""
    
    def extract_from_excel(self, file_path: Path) -> Dict[int, List[bytes]]:
        """提取所有嵌入图片，按行号分组"""
        workbook = load_workbook(file_path, data_only=False)
        sheet = workbook.active
        
        images_by_row = {}
        
        for image in sheet._images:
            row_idx = image.anchor._from.row + 1  # Excel行号
            col_idx = image.anchor._from.col
            
            if row_idx not in images_by_row:
                images_by_row[row_idx] = []
            
            images_by_row[row_idx].append({
                'data': image._data(),
                'format': image.format.lower(),
                'column': col_idx
            })
        
        return images_by_row
```

#### 2. 图片处理服务
```python
# backend/services/image_processor.py（新增）

class ImageProcessor:
    """图片处理：压缩、缩略图、水印"""
    
    def process_product_image(self, image_data: bytes, sku: str, index: int):
        """处理单张产品图片"""
        img = Image.open(BytesIO(image_data))
        
        # 压缩原图（保持质量）
        if img.width > 1920 or img.height > 1920:
            img.thumbnail((1920, 1920), Image.LANCZOS)
        
        # 保存原图
        original_io = BytesIO()
        img.save(original_io, 'JPEG', quality=90, optimize=True)
        original_path = self.storage.save(original_io.getvalue(), f"{sku}_{index}_original.jpg")
        
        # 生成缩略图（200x200）
        img_thumb = img.copy()
        img_thumb.thumbnail((200, 200), Image.LANCZOS)
        thumb_io = BytesIO()
        img_thumb.save(thumb_io, 'JPEG', quality=85)
        thumb_path = self.storage.save(thumb_io.getvalue(), f"{sku}_{index}_thumb.jpg")
        
        return {
            'original_url': f"/static/product_images/{original_path}",
            'thumbnail_url': f"/static/product_images/{thumb_path}",
            'file_size': len(image_data),
            'width': img.width,
            'height': img.height
        }
```

#### 3. 产品管理API
```python
# backend/routers/product_management.py（新增）

@router.get("/products")
async def get_products(
    platform: str = None,
    shop_id: str = None,
    keyword: str = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取产品列表（含图片）"""
    
    query = db.query(FactProductInventory)
    
    if platform:
        query = query.filter(FactProductInventory.platform_code == platform)
    if shop_id:
        query = query.filter(FactProductInventory.shop_id == shop_id)
    if keyword:
        query = query.filter(FactProductInventory.product_name.like(f"%{keyword}%"))
    
    total = query.count()
    products = query.offset((page - 1) * page_size).limit(page_size).all()
    
    # 加载每个产品的图片
    results = []
    for product in products:
        images = db.query(ProductImage).filter(
            ProductImage.platform_sku == product.platform_sku
        ).order_by(ProductImage.image_order).all()
        
        results.append({
            'platform_sku': product.platform_sku,
            'product_name': product.product_name,
            'specification': product.specification,
            'unit_price': product.unit_price,
            'stock': product.stock,
            'thumbnail_url': images[0].thumbnail_url if images else None,
            'all_images': [img.image_url for img in images]
        })
    
    return {
        'success': True,
        'data': results,
        'total': total,
        'page': page,
        'page_size': page_size
    }

@router.post("/products/{sku}/images")
async def upload_product_image(
    sku: str,
    file: UploadFile,
    db: Session = Depends(get_db)
):
    """上传产品图片"""
    
    # 读取图片
    image_data = await file.read()
    
    # 处理图片
    processor = ImageProcessor()
    result = processor.process_product_image(image_data, sku, 0)
    
    # 保存到数据库
    product_image = ProductImage(
        platform_sku=sku,
        image_url=result['original_url'],
        thumbnail_url=result['thumbnail_url'],
        file_size=result['file_size'],
        is_main_image=True  # 第一张为主图
    )
    
    db.add(product_image)
    db.commit()
    
    return {'success': True, 'image': result}
```

---

### 前端组件

#### 产品管理页面结构
```
frontend/src/views/ProductManagement.vue
├─ 顶部筛选器
│  ├─ 平台选择
│  ├─ 店铺选择
│  └─ 关键词搜索
│
├─ 产品列表（表格）
│  ├─ 产品图片列（缩略图，懒加载）
│  ├─ SKU/名称/规格/价格/库存
│  └─ 操作按钮（详情/编辑）
│
└─ 产品详情对话框
   ├─ 图片轮播（多图展示）
   ├─ 产品信息展示
   ├─ 图片管理（上传/删除/排序）
   └─ 产品编辑（修改名称/价格等）
```

---

## 开发任务清单

### 后端开发（10天）

**Week 1**:
- [ ] Day 1-2: 图片提取服务（ImageExtractor）
- [ ] Day 3-4: 图片处理服务（ImageProcessor）
- [ ] Day 5: 图片存储服务（LocalStorage/OSSStorage）

**Week 2**:
- [ ] Day 6-7: 产品管理API（CRUD+图片）
- [ ] Day 8: 批量操作API
- [ ] Day 9: 图片上传API
- [ ] Day 10: 单元测试和集成测试

### 前端开发（7天）

**Week 1**:
- [ ] Day 1-2: 产品列表组件（含缩略图）
- [ ] Day 3-4: 产品详情组件（图片轮播）
- [ ] Day 5: 图片上传组件
- [ ] Day 6: 图片管理组件（删除/排序）
- [ ] Day 7: 集成测试和UI优化

### 数据库（2天）
- [ ] Day 1: 创建product_images表迁移
- [ ] Day 2: 添加索引和约束

---

## 实施步骤

### 阶段1：入库时异步处理图片（Week 1-2）

**目标**: 字段映射入库时，自动提取和存储图片

**实现**:
```python
@router.post("/ingest")
async def ingest_file(..., background_tasks: BackgroundTasks):
    # 1. 快速入库文本数据（1-2秒）
    ...
    
    # 2. 添加后台任务：处理图片（异步）
    background_tasks.add_task(
        extract_and_store_images,
        catalog_record.file_path,
        file_id
    )
    
    return {
        'success': True,
        'imported': 100,
        'image_processing': 'background'  # 图片后台处理中
    }
```

**用户体验**:
- 点击"确认映射并入库" → 2秒返回"数据已入库"
- 后台处理图片 → 1-2分钟完成
- 完成后通知（WebSocket或轮询）

---

### 阶段2：产品管理模块（Week 3）

**目标**: 独立的产品管理界面

**功能**:
- 产品列表（带缩略图）
- 产品详情（大图+信息）
- 图片管理（上传/删除/排序）
- 批量编辑

---

## 性能目标

| 操作 | v2.3（当前） | v3.0（目标） | 说明 |
|------|-------------|-------------|------|
| 数据入库 | 1-2秒 | 1-2秒 | 文本数据，不变 |
| 图片处理 | 不支持 | 1-2分钟（异步） | 后台处理，不阻塞 |
| 产品列表加载 | N/A | <1秒 | 只加载缩略图URL |
| 缩略图显示 | N/A | 懒加载 | 滚动到才加载 |
| 大图预览 | N/A | <500ms | 已缓存 |

---

## 数据流向图

```
┌─────────────────────────────────────────────┐
│     Excel文件（产品+图片，11MB）            │
└──────────────┬──────────────────────────────┘
               │
               ↓
    [字段映射系统 v2.3] ← 用户配置映射
               │
               ├─→ [文本数据] → PostgreSQL
               │     • fact_product_inventory
               │     • 1-2秒快速入库 ✓
               │
               └─→ [图片提取] → 后台任务（v3.0）
                     │
                     ├─→ [压缩/缩略图] → 本地存储
                     │     • data/product_images/
                     │
                     └─→ [URL入库] → PostgreSQL
                           • product_images表
                           • 关联platform_sku
                           
                           ↓
               
    [产品管理模块 v3.0] ← SKU级运营
               │
               ├─→ [产品列表] 显示缩略图
               ├─→ [产品详情] 大图轮播
               ├─→ [图片管理] 上传/编辑
               └─→ [运营分析] 图片质量/主图优化
```

---

## 投入产出分析

### 开发投入
- **时间**: 2-3周（1人全职）
- **人力**: 后端10天 + 前端7天 + 测试2天
- **成本**: 约1人月

### 技术投入
- **存储**: 本地免费 / OSS约2-5元/月
- **开发工具**: 开源库（Pillow/openpyxl）
- **基础设施**: 已有（PostgreSQL+Vue.js）

### 业务价值
- **提升用户体验**: 80% → 100%场景覆盖
- **运营效率**: 图片可视化管理
- **竞争力**: 对标Amazon/Shopee级别
- **扩展性**: 为AI图片识别铺路

**ROI**: 约**10-20倍**

---

## 里程碑规划

### Milestone 1: 基础图片提取（Week 1）
- 图片提取服务
- 本地存储
- 数据库schema

### Milestone 2: 产品管理模块（Week 2）
- 产品列表API
- 前端列表组件
- 图片显示

### Milestone 3: 图片管理功能（Week 3）
- 图片上传API
- 图片管理组件
- 批量操作

### Milestone 4: 测试与上线（Week 3）
- 完整测试
- 性能优化
- 文档更新

---

## 成功标准

### 功能验收
- [ ] 字段映射入库后，图片自动提取（后台）
- [ ] 产品列表显示缩略图
- [ ] 点击产品查看大图和详情
- [ ] 支持手动上传/删除图片
- [ ] 图片与SKU正确关联

### 性能验收
- [ ] 产品列表加载 < 1秒
- [ ] 缩略图懒加载正常
- [ ] 1000个产品图片提取 < 2分钟

### 用户验收
- [ ] 产品管理操作流畅
- [ ] 图片显示清晰
- [ ] 运营功能满足需求

---

## 与当前系统集成

### 无缝升级
```python
# 字段映射系统入库接口升级（向后兼容）

@router.post("/ingest")
async def ingest_file(..., extract_images: bool = True):  # 新增参数
    """数据入库（可选图片处理）"""
    
    # 原有逻辑：快速入库文本数据
    ...
    
    # 新增逻辑：异步处理图片（可选）
    if extract_images:
        background_tasks.add_task(
            process_excel_images,
            catalog_record.file_path,
            file_id
        )
    
    return {
        'success': True,
        'imported': len(rows),
        'image_extraction': extract_images  # 是否处理图片
    }
```

**用户选择**:
- 快速模式：不提取图片（1-2秒）
- 完整模式：提取图片（1-2秒入库 + 后台1-2分钟处理图片）

---

## 总结

### v3.0的定位
- **v2.3**: 数据基础设施（字段映射+入库）✅
- **v3.0**: 产品可视化管理（SKU级运营）🔄
- **v4.0**: AI增强（智能识别+云存储）💡

### 发展路径确认
✅ **完全符合现代化ERP的图片处理方式**
- 数据与图片分离 ✓
- 异步处理不阻塞 ✓
- 按需加载优化 ✓
- SKU级精细管理 ✓

---

**您的理解和规划非常准确！我们现在的方向100%符合Amazon/Shopee等顶级平台的架构设计！** ⭐⭐⭐⭐⭐

