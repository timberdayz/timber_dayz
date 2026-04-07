# API 接口契约文档

## 📋 文档说明

本文档定义Agent A和Agent B之间的接口契约。**在开发前必须先在此文档中定义清楚接口签名，双方达成一致后再开始实现。**

## 🤝 接口契约原则

### 版本管理
- 每个接口都有版本号（v1.0, v1.1等）
- 破坏性变更必须升级主版本号
- 向后兼容的变更可以升级次版本号

### 变更通知
- 接口变更必须在Git提交中注明"⚠️ 接口变更"
- 重大变更需要通知对方Agent
- 保留旧版本接口至少1个开发周期

### 类型注解
- 所有接口必须有完整的类型注解
- 复杂数据结构使用Pydantic定义
- 返回值必须明确类型

---

## 📊 数据查询服务（DataQueryService）

**提供者**: Agent A  
**调用者**: Agent B  
**版本**: v1.0  
**状态**: ✅ 已实现

### 接口定义

```python
from sqlalchemy.orm import Session
import pandas as pd
from typing import Dict, List, Optional

class DataQueryService:
    """数据查询服务"""
    
    def __init__(self, session: Session):
        """
        初始化数据查询服务
        
        Args:
            session: SQLAlchemy数据库会话
        """
        self.session = session
    
    def get_orders(self, filters: dict) -> pd.DataFrame:
        """
        查询订单数据
        
        Args:
            filters: 查询过滤器
                - platforms: List[str], 可选, 平台列表（如['shopee', 'tiktok']）
                - start_date: str, 必选, 开始日期（格式：YYYY-MM-DD）
                - end_date: str, 必选, 结束日期（格式：YYYY-MM-DD）
                - shops: List[str], 可选, 店铺ID列表
                - order_status: List[str], 可选, 订单状态列表
                - limit: int, 可选, 返回条数限制（默认10000）
        
        Returns:
            pd.DataFrame: 订单数据，包含以下列：
                - id: int, 订单主键
                - platform: str, 平台名称
                - shop_id: str, 店铺ID
                - order_id: str, 订单号
                - order_date: date, 订单日期
                - order_time: datetime, 订单时间
                - total_amount: float, 订单金额
                - currency: str, 货币代码
                - total_amount_rmb: float, 人民币金额
                - order_status: str, 订单状态
                - payment_status: str, 支付状态
                - customer_id: str, 客户ID
                - created_at: datetime, 创建时间
                - updated_at: datetime, 更新时间
        
        Raises:
            TimeoutError: 查询超过5秒
            ValueError: 参数格式错误（如日期格式不正确）
            
        Example:
            >>> filters = {
            ...     'platforms': ['shopee'],
            ...     'start_date': '2024-01-01',
            ...     'end_date': '2024-12-31'
            ... }
            >>> df = service.get_orders(filters)
            >>> print(len(df))
            1234
        """
        pass
    
    def get_products(self, filters: dict) -> pd.DataFrame:
        """
        查询产品数据
        
        Args:
            filters: 查询过滤器
                - platforms: List[str], 可选
                - skus: List[str], 可选, SKU列表
                - category: str, 可选, 产品类别
                - limit: int, 可选, 默认10000
        
        Returns:
            pd.DataFrame: 产品数据，包含以下列：
                - id: int
                - platform: str
                - shop_id: str
                - platform_sku: str
                - product_name: str
                - category: str
                - brand: str
                - created_at: datetime
                - updated_at: datetime
        """
        pass
    
    def get_metrics(self, filters: dict) -> pd.DataFrame:
        """
        查询产品指标数据
        
        Args:
            filters: 查询过滤器
                - platforms: List[str], 可选
                - start_date: str, 必选
                - end_date: str, 必选
                - metric_types: List[str], 可选, 指标类型列表
                - granularity: str, 可选, 粒度（daily/weekly/monthly）
                - limit: int, 可选, 默认10000
        
        Returns:
            pd.DataFrame: 指标数据，包含以下列：
                - id: int
                - platform: str
                - shop_id: str
                - platform_sku: str
                - metric_date: date
                - granularity: str
                - metric_type: str
                - value: float
                - unit: str
        """
        pass
    
    def get_statistics(self, filters: dict) -> dict:
        """
        获取统计数据
        
        Args:
            filters: 查询过滤器（同get_orders）
        
        Returns:
            dict: 统计数据
                - total_orders: int, 总订单数
                - total_gmv: float, 总GMV（人民币）
                - avg_order_value: float, 平均订单金额（人民币）
                - total_products: int, 总产品数（可选）
                - total_customers: int, 总客户数（可选）
        
        Example:
            >>> stats = service.get_statistics(filters)
            >>> print(stats)
            {
                'total_orders': 1234,
                'total_gmv': 567890.12,
                'avg_order_value': 460.39
            }
        """
        pass
```

### 性能要求
- 查询响应时间 < 5秒
- 支持10000条记录以内的查询
- 使用缓存机制（5分钟TTL）

### 错误处理
- 查询失败时返回空DataFrame，不抛出异常
- 错误信息记录到日志
- 超时保护：5秒后自动取消查询

---

## 💱 汇率服务（CurrencyService）

**提供者**: Agent B  
**调用者**: Agent A  
**版本**: v1.0  
**状态**: 📋 待实现

### 接口定义

```python
from typing import Optional, Dict, List
from datetime import date

class CurrencyService:
    """汇率服务"""
    
    def get_rate(self, from_currency: str, to_currency: str, 
                 date: Optional[str] = None) -> float:
        """
        获取汇率
        
        Args:
            from_currency: 源货币代码（ISO 4217，如USD）
            to_currency: 目标货币代码（ISO 4217，如CNY）
            date: 日期（格式：YYYY-MM-DD），None表示使用最新汇率
        
        Returns:
            float: 汇率（保留6位小数）
        
        Raises:
            ValueError: 货币代码不支持
            ConnectionError: API连接失败（会自动使用兜底汇率）
        
        Example:
            >>> rate = service.get_rate('USD', 'CNY', '2024-01-01')
            >>> print(rate)
            7.123456
        """
        pass
    
    def convert_to_rmb(self, amount: float, currency: str, 
                      date: Optional[str] = None) -> float:
        """
        转换为人民币
        
        Args:
            amount: 金额
            currency: 货币代码
            date: 日期（可选）
        
        Returns:
            float: 人民币金额（保留2位小数）
        
        Example:
            >>> rmb = service.convert_to_rmb(100, 'USD', '2024-01-01')
            >>> print(rmb)
            712.35
        """
        pass
    
    def batch_convert(self, data: List[Dict]) -> List[Dict]:
        """
        批量转换（性能优化）
        
        Args:
            data: 待转换数据列表
                每个元素包含：
                - amount: float
                - currency: str
                - date: str (可选)
        
        Returns:
            List[Dict]: 转换后的数据（添加amount_rmb字段）
        
        Example:
            >>> data = [
            ...     {'amount': 100, 'currency': 'USD', 'date': '2024-01-01'},
            ...     {'amount': 200, 'currency': 'EUR', 'date': '2024-01-01'}
            ... ]
            >>> result = service.batch_convert(data)
            >>> print(result)
            [
                {'amount': 100, 'currency': 'USD', 'date': '2024-01-01', 'amount_rmb': 712.35},
                {'amount': 200, 'currency': 'EUR', 'date': '2024-01-01', 'amount_rmb': 1567.89}
            ]
        """
        pass
```

### 性能要求
- API调用超时时间：5秒
- 缓存策略：同一日期的汇率缓存1天
- 批量转换：预加载所有需要的汇率

### 兜底策略
- API失败时使用固定汇率
- 支持的货币：USD, EUR, GBP, SGD, MYR, THB, VND, IDR
- 固定汇率定期更新（每月）

---

## 📁 文件扫描服务（FileScanner）

**提供者**: Agent A  
**调用者**: Agent A（内部使用）  
**版本**: v1.0  
**状态**: 📋 待实现

### 接口定义

```python
from pathlib import Path
from typing import List
from dataclasses import dataclass

@dataclass
class FileMetadata:
    """文件元数据"""
    path: Path
    size: int
    mtime: float
    hash: str
    platform: Optional[str] = None
    data_domain: Optional[str] = None

class FileScanner:
    """文件扫描器"""
    
    def scan_fast(self, directory: Path, 
                  patterns: List[str] = None) -> List[FileMetadata]:
        """
        快速扫描目录（使用缓存）
        
        Args:
            directory: 要扫描的目录
            patterns: 文件模式列表（如['*.xlsx', '*.xls']）
        
        Returns:
            List[FileMetadata]: 文件元数据列表
        
        Performance:
            - 目标：500文件/秒
            - 缓存策略：目录mtime未变化时返回缓存
        """
        pass
```

---

## 🔄 ETL Pipeline接口

**提供者**: Agent A  
**调用者**: Agent A（内部使用）+ 命令行工具  
**版本**: v1.0  
**状态**: 📋 待实现

### 接口定义

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ProcessResult:
    """处理结果"""
    success: bool
    file_path: Path
    rows_processed: int = 0
    rows_failed: int = 0
    error: Optional[str] = None

class ETLPipeline:
    """ETL主流程"""
    
    def process_file(self, file_path: Path, 
                    platform: str, 
                    data_domain: str) -> ProcessResult:
        """
        处理单个文件
        
        Args:
            file_path: 文件路径
            platform: 平台名称（shopee/tiktok/miaoshou）
            data_domain: 数据域（orders/products/metrics）
        
        Returns:
            ProcessResult: 处理结果
        
        Performance:
            - Excel解析：1000行/秒
            - 字段映射：2000行/秒
            - 数据入库：1000行/秒
        """
        pass
    
    def process_directory(self, directory: Path, 
                         platform: str,
                         data_domain: str,
                         parallel: bool = False) -> List[ProcessResult]:
        """
        批量处理目录
        
        Args:
            directory: 目录路径
            platform: 平台名称
            data_domain: 数据域
            parallel: 是否并行处理
        
        Returns:
            List[ProcessResult]: 处理结果列表
        """
        pass
```

---

## 📋 数据模型定义（Pydantic）

### OrderFilters（订单查询过滤器）

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import date

class OrderFilters(BaseModel):
    """订单查询过滤器"""
    
    platforms: Optional[List[str]] = Field(None, description="平台列表")
    start_date: str = Field(..., description="开始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    shops: Optional[List[str]] = Field(None, description="店铺ID列表")
    order_status: Optional[List[str]] = Field(None, description="订单状态")
    limit: int = Field(10000, ge=1, le=50000, description="返回条数限制")
    
    @validator('start_date', 'end_date')
    def validate_date_format(cls, v):
        """验证日期格式"""
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"日期格式错误，应为YYYY-MM-DD: {v}")
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """验证日期范围"""
        start_date = values.get('start_date')
        if start_date and v < start_date:
            raise ValueError("结束日期不能早于开始日期")
        return v

# 使用示例
filters = OrderFilters(
    platforms=['shopee', 'tiktok'],
    start_date='2024-01-01',
    end_date='2024-12-31'
)
```

---

## 🔄 接口变更日志

### v1.0（2025-10-16）
- 初始版本
- 定义DataQueryService基础接口
- 定义CurrencyService基础接口
- 定义FileScanner接口
- 定义ETLPipeline接口

### 未来版本规划

#### v1.1（计划中）
- DataQueryService添加分页支持
- 添加更多统计维度（按店铺、按产品类别）

#### v2.0（长期规划）
- 支持GraphQL查询
- 添加实时数据推送接口
- 支持自定义查询条件

---

## 📞 联系与协调

### 接口问题反馈
- 发现接口不清晰：在此文档中添加注释或提问
- 需要新接口：在此文档中添加"接口需求"章节
- 接口变更：更新此文档并在Git提交中注明

### 接口评审流程
1. 提出接口需求（在此文档中描述）
2. 双方讨论确认接口签名
3. 更新此文档
4. Agent A实现接口
5. Agent B调用测试
6. 确认无问题后标记为"✅ 已实现"

---

**版本**: v1.0  
**创建日期**: 2025-10-16  
**维护者**: Agent A + Agent B  
**状态**: 持续更新中

