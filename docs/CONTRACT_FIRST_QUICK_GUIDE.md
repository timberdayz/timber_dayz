# Contract-First 快速开发指南

## 📋 新API开发标准流程（5分钟上手）

### 第1步：在schemas/中定义模型 ⭐

```python
# backend/schemas/your_module.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class YourCreateRequest(BaseModel):
    """创建请求"""
    name: str = Field(..., description="名称")
    description: Optional[str] = Field(None, description="描述")

class YourResponse(BaseModel):
    """响应模型"""
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True  # 支持从ORM对象转换
```

### 第2步：在schemas/__init__.py中导出

```python
# backend/schemas/__init__.py

from backend.schemas.your_module import (
    YourCreateRequest,
    YourResponse,
)

__all__ = [
    # ... 其他导出
    "YourCreateRequest",
    "YourResponse",
]
```

### 第3步：在router中使用

```python
# backend/routers/your_router.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.models.database import get_db
from modules.core.db import YourModel

# ⭐ 从schemas导入（不要在router中定义）
from backend.schemas.your_module import (
    YourCreateRequest,
    YourResponse,
)

router = APIRouter()

# ⭐ 必须添加response_model参数
@router.post("/items", response_model=YourResponse)
async def create_item(
    request: YourCreateRequest,
    db: Session = Depends(get_db)
):
    """创建项目"""
    item = YourModel(**request.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    
    # ⭐ 返回Pydantic模型（不要用success_response）
    return YourResponse.from_orm(item)
```

---

## ✅ 正确示例

### 示例1：简单CRUD

```python
# backend/schemas/product.py
class ProductCreate(BaseModel):
    name: str
    price: float

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    created_at: datetime
    
    class Config:
        from_attributes = True

# backend/routers/product.py
from backend.schemas.product import ProductCreate, ProductResponse

@router.post("/products", response_model=ProductResponse)
async def create_product(request: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**request.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    return ProductResponse.from_orm(product)

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.from_orm(product)
```

### 示例2：列表响应

```python
# backend/schemas/product.py
from typing import List

class ProductListResponse(BaseModel):
    success: bool = True
    products: List[ProductResponse]
    total: int

# backend/routers/product.py
@router.get("/products", response_model=ProductListResponse)
async def list_products(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    products = db.query(Product).offset(skip).limit(limit).all()
    total = db.query(Product).count()
    
    return ProductListResponse(
        success=True,
        products=[ProductResponse.from_orm(p) for p in products],
        total=total
    )
```

### 示例3：使用通用响应

```python
# backend/schemas/common.py
from typing import Generic, TypeVar

T = TypeVar('T')

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None

# backend/routers/product.py
@router.post("/products", response_model=SuccessResponse[ProductResponse])
async def create_product(request: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**request.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    
    return SuccessResponse(
        data=ProductResponse.from_orm(product),
        message="Product created successfully"
    )
```

---

## ❌ 错误示例（禁止）

### 错误1：在router中定义模型

```python
# ❌ 错误：不要在router中定义Pydantic模型
# backend/routers/product.py

from pydantic import BaseModel

class ProductCreate(BaseModel):  # ❌ 应该在schemas/中定义
    name: str
    price: float

@router.post("/products")  # ❌ 缺少response_model
async def create_product(request: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**request.dict())
    db.add(product)
    db.commit()
    return success_response(data={"id": product.id})  # ❌ 不要用通用响应函数
```

### 错误2：缺少response_model

```python
# ❌ 错误：缺少response_model参数
@router.get("/products/{product_id}")  # ❌ 缺少response_model
async def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    return product  # ❌ 类型不明确
```

### 错误3：使用success_response

```python
# ❌ 错误：使用通用响应函数（旧方式）
from backend.utils.api_response import success_response

@router.get("/products")  # ❌ 缺少response_model
async def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return success_response(data=products)  # ❌ 应该返回Pydantic模型
```

---

## 🔧 迁移旧代码（可选）

如果需要修改旧代码，建议同时升级到Contract-First：

### 修改前（旧方式）

```python
# backend/routers/old_module.py
@router.get("/items")
async def get_items(db: Session = Depends(get_db)):
    items = db.query(Item).all()
    return success_response(data=[{
        "id": item.id,
        "name": item.name
    } for item in items])
```

### 修改后（Contract-First）

```python
# 1. 创建schemas
# backend/schemas/old_module.py
class ItemResponse(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class ItemListResponse(BaseModel):
    success: bool = True
    items: List[ItemResponse]

# 2. 更新router
# backend/routers/old_module.py
from backend.schemas.old_module import ItemResponse, ItemListResponse

@router.get("/items", response_model=ItemListResponse)
async def get_items(db: Session = Depends(get_db)):
    items = db.query(Item).all()
    return ItemListResponse(
        items=[ItemResponse.from_orm(item) for item in items]
    )
```

---

## 📊 当前架构状态

### schemas/ 目录结构

```
backend/schemas/
├── __init__.py              # 统一导出
├── common.py                # 通用响应模型
├── account.py               # 账号管理
├── collection.py            # 数据采集
├── account_alignment.py     # 账号对齐
└── data_sync.py             # 数据同步
```

### 已迁移模块（100%覆盖）

- ✅ `account.py` - 账号管理（5个模型）
- ✅ `collection.py` - 数据采集（7个模型）
- ✅ `account_alignment.py` - 账号对齐（15个模型）
- ✅ `data_sync.py` - 数据同步（5个模型）
- ✅ `common.py` - 通用响应（5个模型）

### 未迁移模块（使用旧方式）

这些模块使用通用响应函数，暂不强制迁移：
- management.py
- field_mapping.py
- hr_management.py
- performance_management.py
- 等...

**注意**: 修改这些模块时，建议同步升级到Contract-First。

---

## 🎯 验证清单

开发新API前，请确认：

- [ ] Pydantic模型已定义在`backend/schemas/`
- [ ] 模型已在`backend/schemas/__init__.py`中导出
- [ ] 所有@router装饰器都有`response_model`参数
- [ ] 返回值是Pydantic模型实例（不是dict或success_response）
- [ ] 已运行`python scripts/verify_contract_first.py`验证

---

## 💡 常见问题

### Q1: 为什么要在schemas/中定义模型？

**A**: 
- ✅ 集中管理，避免重复定义
- ✅ 便于前后端共享类型
- ✅ 自动生成API文档
- ✅ 提高代码可维护性

### Q2: 旧代码需要立即迁移吗？

**A**: 
- ❌ 不强制，旧代码可以保持稳定
- ✅ 修改旧代码时，建议同步升级
- ✅ 新代码必须遵循Contract-First

### Q3: response_model必须添加吗？

**A**: 
- ✅ 新API 100%强制
- ⚠️ 旧API暂不强制，但建议添加
- 🎯 长期目标: 90%+覆盖率

### Q4: 如何处理复杂响应？

**A**: 使用嵌套模型或泛型：

```python
# 方式1: 嵌套模型
class UserResponse(BaseModel):
    id: int
    name: str
    profile: ProfileResponse  # 嵌套

# 方式2: 泛型
from typing import Generic, TypeVar

T = TypeVar('T')

class PagedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
```

---

## 📚 参考文档

- **详细规范**: `.cursorrules`
- **完整报告**: `docs/CONTRACT_FIRST_FINAL_REPORT.md`
- **策略分析**: `docs/CONTRACT_FIRST_P3_STRATEGY.md`
- **验证脚本**: `scripts/verify_contract_first.py`

---

**更新日期**: 2025-12-19  
**适用范围**: 所有新API开发（2025-12-19起生效）  
**状态**: ✅ 正式执行

