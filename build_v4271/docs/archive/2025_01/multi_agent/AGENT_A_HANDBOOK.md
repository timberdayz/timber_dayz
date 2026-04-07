# Agent A 开发手册（Cursor - 后端/数据库专家）

## 🎯 你的角色定位

你是**后端和数据库专家**，负责系统的核心数据处理逻辑。你的工作是确保数据能够从Excel文件安全、高效地流入数据库，并为前端提供稳定的数据服务。

## 📋 职责范围

### 核心职责
1. **数据库架构设计**：设计维度表、事实表、索引策略
2. **数据迁移管理**：使用Alembic管理数据库版本
3. **ETL流程开发**：文件扫描→解析→映射→验证→入库
4. **字段映射引擎**：智能映射、规则匹配、历史学习
5. **性能优化**：缓存策略、批处理、索引优化
6. **数据质量保证**：验证规则、异常隔离、错误处理

### 辅助职责
- PostgreSQL支持与配置
- 数据查询服务接口设计（与Agent B协调）
- 核心模块单元测试
- 技术文档编写

## 📁 专属目录

### 你可以修改的目录
```
models/                          # ✅ 数据库ORM模型
├── dimensions.py                # 维度表模型
├── facts.py                     # 事实表模型
├── management.py                # 管理表模型
└── database.py                  # 数据库连接管理

migrations/                      # ✅ Alembic迁移脚本
└── versions/
    └── 001_initial_schema.py

services/                        # ✅ 你负责的服务
├── etl_pipeline.py              # ETL主流程
├── excel_parser.py              # Excel解析器
├── data_validator.py            # 数据验证器
├── data_importer.py             # 数据入库引擎
└── field_mapping/               # 字段映射模块
    ├── __init__.py
    ├── scanner.py               # 文件扫描器
    ├── excel_reader.py          # Excel读取器
    └── mapper.py                # 映射引擎

tests/                           # ✅ 核心模块测试
├── test_excel_parser.py
├── test_field_mapper.py
├── test_data_importer.py
└── test_etl_pipeline.py
```

### 你需要协调的文件
```
services/
└── data_query_service.py        # 📋 需与Agent B协调接口

config/
└── database.yaml                # 📋 数据库配置（需协调）

docs/
└── API_CONTRACT.md              # 📋 接口契约文档（共同维护）
```

### 你不能修改的目录（严格禁止）
```
❌ frontend_streamlit/pages/     # Agent B负责
❌ utils/                        # Agent B负责
❌ services/currency_service.py  # Agent B负责
❌ modules/apps/collection_center/  # 采集模块（冻结）
```

## 🗓️ 7天开发计划

### Day 1: 诊断 + 数据库架构（12小时）
**上午（9:00-13:00）：系统诊断**
- [ ] 运行字段映射审核页面，记录所有问题
- [ ] 使用cProfile分析性能瓶颈
- [ ] 检查models/目录现有表结构
- [ ] 测试前端页面，记录白屏原因
- [ ] 输出：`docs/DIAGNOSTIC_REPORT_DAY1.md`

**下午（14:00-18:00）：数据库Schema设计**
- [ ] 设计完整Schema（维度表+事实表+管理表）
- [ ] 创建`models/dimensions.py`
- [ ] 创建`models/facts.py`
- [ ] 创建`models/management.py`
- [ ] 输出：`docs/DATABASE_SCHEMA_V3.md`

**晚上（19:00-23:00）：Alembic初始化**
- [ ] 安装alembic：`pip install alembic`
- [ ] 初始化：`alembic init migrations`
- [ ] 配置alembic.ini和env.py
- [ ] 创建初始迁移脚本
- [ ] 测试迁移：`alembic upgrade head`

### Day 2: 智能字段映射系统重构（12小时）
**上午（9:00-13:00）：分析与设计**
- [ ] 深度分析现有字段映射系统
- [ ] 设计新架构（scanner/reader/mapper）
- [ ] 输出：`docs/FIELD_MAPPING_REFACTOR_PLAN.md`

**下午（14:00-18:00）：核心逻辑重构**
- [ ] 实现`services/field_mapping/scanner.py`（文件扫描）
- [ ] 实现`services/field_mapping/excel_reader.py`（Excel读取）
- [ ] 实现`services/field_mapping/mapper.py`（字段映射）

**晚上（19:00-23:00）：前端页面重构**
- [ ] 优化`frontend_streamlit/pages/40_字段映射审核.py`
- [ ] 集成新的服务层API
- [ ] 测试性能（目标：<2秒扫描1000文件）

### Day 3: ETL核心流程（12小时）
**上午（9:00-13:00）：Excel解析**
- [ ] 实现`services/excel_parser.py`（统一解析器）
- [ ] 支持.xlsx/.xls/HTML伪装.xls/.csv
- [ ] 集成字段映射引擎

**下午（14:00-18:00）：数据验证与入库**
- [ ] 实现`services/data_validator.py`（数据验证）
- [ ] 实现`services/data_importer.py`（数据入库）
- [ ] 实现幂等性upsert逻辑

**晚上（19:00-23:00）：ETL主流程**
- [ ] 实现`services/etl_pipeline.py`（ETL编排）
- [ ] 创建`scripts/etl_cli.py`（命令行工具）
- [ ] 端到端测试

### Day 4: 性能优化与测试（12小时）
**上午（9:00-13:00）：性能优化**
- [ ] 实现缓存策略（内存或Redis）
- [ ] 优化数据库索引
- [ ] 优化批处理大小

**下午（14:00-18:00）：单元测试**
- [ ] 编写核心模块测试（目标：80%+覆盖率）
- [ ] 测试Excel解析器
- [ ] 测试字段映射
- [ ] 测试数据入库

**晚上（19:00-23:00）：汇率服务与工具**
- [ ] 实现`services/currency_service.py`（汇率服务）
- [ ] 实现`utils/monitoring.py`（性能监控）
- [ ] 实现`utils/file_tools.py`（文件工具）

### Day 5: 数据查询服务（上午，4小时）
**上午（9:00-13:00）：数据查询服务**
- [ ] 实现`services/data_query_service.py`
- [ ] 实现get_orders/get_products/get_metrics
- [ ] 添加缓存和超时保护
- [ ] 与Agent B协调接口签名

**下午开始切换到Agent B使用Augment**

### Day 6: PostgreSQL支持（下午+晚上，8小时）
**下午（14:00-18:00）：PostgreSQL适配**
- [ ] 修改`models/database.py`支持PostgreSQL
- [ ] 测试Alembic在PostgreSQL上的迁移
- [ ] 实现Upsert双数据库适配

**晚上（19:00-23:00）：文档编写**
- [ ] 编写`docs/DEPLOYMENT_GUIDE.md`
- [ ] 编写`docs/API_DOCUMENTATION.md`
- [ ] 编写`docs/TROUBLESHOOTING.md`

### Day 7: 集成测试（上午+下午，8小时）
**上午（9:00-13:00）：端到端测试**
- [ ] 测试完整流程：采集→ETL→展示
- [ ] 性能压力测试
- [ ] 修复发现的bug

**下午（14:00-18:00）：生产环境准备**
- [ ] PostgreSQL数据迁移
- [ ] 生产环境配置
- [ ] 压力测试

**晚上（19:00-23:00）：收尾**
- [ ] 补充测试覆盖
- [ ] 完善文档
- [ ] Git提交

## 🔧 开发指南

### 数据库设计原则

#### 维度表设计
```python
# models/dimensions.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class DimPlatform(Base):
    """平台维度表"""
    __tablename__ = 'dim_platforms'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    region = Column(String(50))
    api_version = Column(String(20))
    created_at = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<DimPlatform(code='{self.code}', name='{self.name}')>"
```

#### 事实表设计
```python
# models/facts.py
class FactOrders(Base):
    """订单事实表"""
    __tablename__ = 'fact_orders'
    
    id = Column(Integer, primary_key=True)
    platform = Column(String(50), nullable=False, index=True)
    shop_id = Column(String(100), nullable=False, index=True)
    order_id = Column(String(200), nullable=False)
    order_date = Column(Date, nullable=False, index=True)
    order_time = Column(DateTime)
    total_amount = Column(Numeric(15, 2))
    currency = Column(String(10))
    total_amount_rmb = Column(Numeric(15, 2))
    order_status = Column(String(50))
    payment_status = Column(String(50))
    customer_id = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('platform', 'shop_id', 'order_id', name='uq_order'),
        Index('idx_orders_date_platform', 'order_date', 'platform'),
        Index('idx_orders_shop_date', 'shop_id', 'order_date'),
    )
```

### Alembic迁移编写

#### 创建迁移脚本
```bash
# 自动生成迁移（基于models变化）
alembic revision --autogenerate -m "add new column"

# 手动创建迁移
alembic revision -m "manual migration"
```

#### 迁移脚本模板
```python
# migrations/versions/001_initial_schema.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    """升级数据库"""
    # 创建维度表
    op.create_table(
        'dim_platforms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('region', sa.String(50)),
        sa.Column('api_version', sa.String(20)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    
    # 创建索引
    op.create_index('idx_platforms_code', 'dim_platforms', ['code'])
    
    # 创建事实表
    op.create_table(
        'fact_orders',
        # ... 字段定义
    )

def downgrade():
    """回滚数据库"""
    op.drop_table('fact_orders')
    op.drop_table('dim_platforms')
```

### ETL流程实现

#### 文件扫描器
```python
# services/field_mapping/scanner.py
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass
import hashlib

@dataclass
class FileMetadata:
    path: Path
    size: int
    mtime: float
    hash: str

class FileScanner:
    def __init__(self):
        self.cache = {}  # {dir_path: (mtime, files)}
    
    def scan_fast(self, directory: Path, 
                  patterns: List[str] = None) -> List[FileMetadata]:
        """
        快速扫描目录（使用缓存）
        
        Args:
            directory: 要扫描的目录
            patterns: 文件模式列表，如['*.xlsx', '*.xls']
        
        Returns:
            FileMetadata列表
        """
        if patterns is None:
            patterns = ['*.xlsx', '*.xls', '*.csv']
        
        # 检查目录mtime，如果没变就返回缓存
        dir_mtime = directory.stat().st_mtime
        if directory in self.cache:
            cached_mtime, cached_files = self.cache[directory]
            if cached_mtime == dir_mtime:
                return cached_files
        
        # 扫描文件
        files = []
        for pattern in patterns:
            for file_path in directory.glob(f"**/{pattern}"):
                if file_path.is_file():
                    files.append(self.get_file_metadata(file_path))
        
        # 更新缓存
        self.cache[directory] = (dir_mtime, files)
        return files
    
    def get_file_metadata(self, file_path: Path) -> FileMetadata:
        """获取文件元数据（不读取内容）"""
        stat = file_path.stat()
        # 计算文件hash
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        
        return FileMetadata(
            path=file_path,
            size=stat.st_size,
            mtime=stat.st_mtime,
            hash=hash_md5.hexdigest()
        )
```

#### Excel解析器
```python
# services/excel_parser.py
import pandas as pd
from pathlib import Path

class ExcelParser:
    def parse(self, file_path: Path, nrows: int = None) -> pd.DataFrame:
        """
        解析Excel文件
        
        Args:
            file_path: 文件路径
            nrows: 读取行数限制（用于预览）
        
        Returns:
            pd.DataFrame
        """
        ext = file_path.suffix.lower()
        
        try:
            if ext == '.xlsx':
                return pd.read_excel(file_path, engine='openpyxl', nrows=nrows)
            
            elif ext == '.xls':
                # 先尝试xlrd
                try:
                    return pd.read_excel(file_path, engine='xlrd', nrows=nrows)
                except Exception:
                    # HTML伪装的xls
                    dfs = pd.read_html(str(file_path))
                    df = dfs[0]
                    if nrows:
                        df = df.head(nrows)
                    return df
            
            elif ext in ['.csv', '.tsv']:
                sep = '\t' if ext == '.tsv' else ','
                return pd.read_csv(file_path, sep=sep, nrows=nrows, encoding='utf-8-sig')
            
            else:
                raise ValueError(f"不支持的文件格式: {ext}")
        
        except Exception as e:
            raise Exception(f"解析文件失败 {file_path}: {str(e)}")
    
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗DataFrame"""
        # 删除全空行
        df = df.dropna(how='all')
        
        # 删除全空列
        df = df.dropna(axis=1, how='all')
        
        # 去除列名首尾空格
        df.columns = df.columns.str.strip()
        
        # 去除字符串列的首尾空格
        string_columns = df.select_dtypes(include=['object']).columns
        df[string_columns] = df[string_columns].apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        
        return df
```

#### 数据入库引擎
```python
# services/data_importer.py
from sqlalchemy.orm import Session
from typing import List, Dict
import pandas as pd

class DataImporter:
    def __init__(self, session: Session):
        self.session = session
    
    def import_orders(self, df: pd.DataFrame, metadata: dict) -> dict:
        """
        导入订单数据
        
        Args:
            df: 订单数据DataFrame
            metadata: 元数据（platform, shop_id等）
        
        Returns:
            {"success_count": int, "failed_count": int}
        """
        success_count = 0
        failed_count = 0
        
        # 批量处理
        batch_size = 1000
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            
            try:
                # 转换为字典列表
                records = batch.to_dict('records')
                
                # Upsert
                self._upsert_batch(FactOrders, records)
                
                success_count += len(records)
                self.session.commit()
            
            except Exception as e:
                self.session.rollback()
                failed_count += len(batch)
                
                # 隔离失败数据
                for idx, row in batch.iterrows():
                    self._quarantine(row.to_dict(), str(e))
        
        return {"success_count": success_count, "failed_count": failed_count}
    
    def _upsert_batch(self, model, records: List[dict]):
        """批量upsert"""
        engine = self.session.bind
        
        if 'postgresql' in str(engine.url):
            # PostgreSQL: INSERT ... ON CONFLICT DO UPDATE
            from sqlalchemy.dialects.postgresql import insert
            stmt = insert(model).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=['platform', 'shop_id', 'order_id'],
                set_={k: stmt.excluded[k] for k in records[0].keys() if k != 'id'}
            )
            self.session.execute(stmt)
        else:
            # SQLite: INSERT OR REPLACE
            for record in records:
                stmt = model.__table__.insert().prefix_with('OR REPLACE').values(**record)
                self.session.execute(stmt)
    
    def _quarantine(self, row: dict, error_msg: str):
        """隔离失败数据"""
        import json
        quarantine = DataQuarantine(
            row_data=json.dumps(row, ensure_ascii=False),
            error_type='ImportError',
            error_msg=error_msg
        )
        self.session.add(quarantine)
        self.session.commit()
```

### ETL主流程编排
```python
# services/etl_pipeline.py
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ProcessResult:
    success: bool
    file_path: Path
    rows_processed: int = 0
    rows_failed: int = 0
    error: str = None

class ETLPipeline:
    def __init__(self):
        self.scanner = FileScanner()
        self.parser = ExcelParser()
        self.mapper = FieldMapper()
        self.validator = DataValidator()
        self.importer = DataImporter(get_session())
    
    def process_file(self, file_path: Path, 
                    platform: str, 
                    data_domain: str) -> ProcessResult:
        """
        处理单个文件
        
        Args:
            file_path: 文件路径
            platform: 平台名称
            data_domain: 数据域（orders/products/metrics）
        
        Returns:
            ProcessResult
        """
        try:
            # 1. 解析Excel
            df = self.parser.parse(file_path)
            df = self.parser.clean_dataframe(df)
            
            # 2. 字段映射
            mapping_result = self.mapper.map_fields(df, platform, data_domain)
            
            # 3. 数据验证
            validation = self.validator.validate(mapping_result.df, data_domain)
            
            # 4. 数据入库
            import_result = self.importer.import_orders(
                validation.clean_df, 
                metadata={"platform": platform}
            )
            
            return ProcessResult(
                success=True,
                file_path=file_path,
                rows_processed=import_result["success_count"],
                rows_failed=import_result["failed_count"]
            )
        
        except Exception as e:
            return ProcessResult(
                success=False,
                file_path=file_path,
                error=str(e)
            )
    
    def process_directory(self, directory: Path, 
                         platform: str,
                         data_domain: str) -> List[ProcessResult]:
        """批量处理目录"""
        files = self.scanner.scan_fast(directory)
        results = []
        
        for file_metadata in files:
            result = self.process_file(
                file_metadata.path, 
                platform, 
                data_domain
            )
            results.append(result)
            
            # 输出进度
            print(f"处理 {result.file_path.name}: "
                  f"{'✓' if result.success else '✗'} "
                  f"成功{result.rows_processed}行")
        
        return results
```

## 🧪 测试指南

### 单元测试示例
```python
# tests/test_excel_parser.py
import pytest
from services.excel_parser import ExcelParser
from pathlib import Path

def test_parse_xlsx():
    """测试解析xlsx文件"""
    parser = ExcelParser()
    df = parser.parse(Path('test_data/sample.xlsx'))
    
    assert len(df) > 0
    assert len(df.columns) > 0

def test_parse_html_xls():
    """测试解析HTML伪装的xls文件"""
    parser = ExcelParser()
    df = parser.parse(Path('test_data/sample_html.xls'))
    
    assert len(df) > 0

def test_clean_dataframe():
    """测试DataFrame清洗"""
    import pandas as pd
    parser = ExcelParser()
    
    df = pd.DataFrame({
        ' 列名 ': ['  值1  ', '值2', None],
        '空列': [None, None, None]
    })
    
    cleaned = parser.clean_dataframe(df)
    
    assert '列名' in cleaned.columns  # 列名去空格
    assert '空列' not in cleaned.columns  # 空列删除
    assert cleaned.iloc[0, 0] == '值1'  # 值去空格
```

## ⚠️ 常见问题

### Q: 如何切换数据库？
```python
# 使用环境变量切换
import os

# SQLite（开发环境）
os.environ['DATABASE_URL'] = 'sqlite:///data/unified_erp_system.db'

# PostgreSQL（生产环境）
os.environ['DATABASE_URL'] = 'postgresql://user:pass@localhost:5432/erp'
```

### Q: 如何调试性能问题？
```python
# 使用cProfile分析
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# 你的代码
pipeline.process_file(file_path)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # 显示前20个最慢的函数
```

### Q: 如何与Agent B协调接口？
1. 先在`docs/API_CONTRACT.md`中定义接口签名
2. 使用类型注解明确参数和返回值
3. 编写接口后通知Agent B
4. 接口变更需要在Git提交中标注"⚠️ 接口变更"

## 📝 每日检查清单

### 开发前
- [ ] 拉取最新代码：`git pull`
- [ ] 查看今日任务：Plan中的Day X任务
- [ ] 检查是否需要与Agent B协调接口

### 开发中
- [ ] 每完成一个模块就测试
- [ ] 遵守文件修改权限
- [ ] 添加类型注解和docstring
- [ ] 每2-3小时提交一次代码

### 开发后
- [ ] 运行相关测试确保通过
- [ ] 更新相关文档
- [ ] Git提交（使用规范格式）
- [ ] 记录明天的任务清单

## 🚀 加油！

你负责的是系统最核心的部分，数据的准确性和性能直接影响整个系统。加油完成这个挑战！💪

---

**创建日期**: 2025-10-16  
**版本**: v1.0  
**维护者**: ERP开发团队

