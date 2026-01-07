# Agent B 开发手册（Augment - 前端/工具专家）

## 🎯 你的角色定位

你是**前端和工具专家**，负责用户界面和用户体验。你的工作是确保用户能够方便地查看和管理数据，让复杂的数据处理过程变得简单易用。

## 📋 职责范围

### 核心职责
1. **前端页面修复**：解决白屏、加载慢等问题
2. **数据展示优化**：表格、图表、统计卡片的展示
3. **用户交互优化**：筛选器、按钮、表单的交互逻辑
4. **数据查询服务**：为前端提供数据查询接口
5. **工具类开发**：汇率服务、文件工具、监控工具

### 辅助职责
- 前端性能优化（缓存、懒加载）
- 用户体验改进
- 文档编写（用户手册、快速开始指南）

## 📁 专属目录

### 你可以修改的目录
```
frontend_streamlit/                    # ✅ 前端页面
├── pages/
│   ├── 20_数据管理中心.py              # 数据管理中心
│   ├── 40_字段映射审核.py              # 字段映射审核
│   └── unified_dashboard.py          # 统一看板
├── components/                        # UI组件
└── utils/                             # 前端工具函数

services/                              # ✅ 你负责的服务
├── data_query_service.py              # 数据查询服务
└── currency_service.py                # 汇率服务

utils/                                 # ✅ 工具函数
├── file_tools.py                      # 文件工具
└── monitoring.py                      # 监控工具

docs/                                  # ✅ 文档（部分）
├── QUICK_START.md                     # 快速开始指南
├── USER_MANUAL.md                     # 用户手册
└── FRONTEND_PERFORMANCE.md            # 前端性能优化文档
```

### 你需要协调的文件
```
services/
└── data_query_service.py              # 📋 需与Agent A协调接口

config/
└── database.yaml                      # 📋 数据库配置（需协调）

docs/
└── API_CONTRACT.md                    # 📋 接口契约文档（共同维护）
```

### 你不能修改的目录（严格禁止）
```
❌ models/                             # Agent A负责
❌ migrations/                         # Agent A负责
❌ services/etl_pipeline.py            # Agent A负责
❌ services/field_mapping/             # Agent A负责
❌ modules/apps/collection_center/     # 采集模块（冻结）
❌ frontend_streamlit/pages/10_数据采集中心.py  # 采集前端（冻结）
```

## 🗓️ 7天开发计划

### Day 5: 前端数据查询与页面修复（下午+晚上，8小时）
**下午（14:00-18:00）：修复数据管理中心**
- [ ] 修复`frontend_streamlit/pages/20_数据管理中心.py`白屏问题
- [ ] 移除导入阶段的耗时操作
- [ ] 接入`data_query_service`获取数据库数据
- [ ] 添加筛选器（平台、日期范围）
- [ ] 添加统计卡片（总订单数、GMV、平均金额）

**晚上（19:00-23:00）：修复其他页面**
- [ ] 修复`unified_dashboard.py`白屏问题
- [ ] 接入真实数据
- [ ] 添加图表（GMV趋势、平台占比）
- [ ] 优化`40_字段映射审核.py`用户体验

### Day 6: 前端优化与工具开发（上午，4小时）
**上午（9:00-13:00）：前端性能优化**
- [ ] 优化缓存策略（使用`@st.cache_data`）
- [ ] 减少不必要的rerun
- [ ] 使用`st.session_state`管理状态
- [ ] 懒加载数据
- [ ] 添加交互式图表（Plotly）

**下午开始切换到Agent A使用Cursor**

### Day 7: 收尾与文档（部分时间）
**根据需要参与**
- [ ] 修复前端发现的bug
- [ ] 编写用户手册
- [ ] 编写快速开始指南
- [ ] 整理前端代码

## 🔧 开发指南

### Streamlit性能优化

#### 1. 使用缓存避免重复计算
```python
import streamlit as st

# 缓存数据库连接
@st.cache_resource
def get_database_session():
    """缓存数据库连接（全局单例）"""
    from models.database import get_session
    return get_session()

# 缓存数据查询结果
@st.cache_data(ttl=300)  # 5分钟缓存
def load_orders(platform: str, start_date: str, end_date: str):
    """缓存查询结果"""
    session = get_database_session()
    query_service = DataQueryService(session)
    return query_service.get_orders({
        'platforms': [platform],
        'start_date': start_date,
        'end_date': end_date
    })
```

#### 2. 避免导入阶段的副作用
```python
# ❌ 错误示例：导入时执行耗时操作
from models.database import get_session
session = get_session()  # 导致页面加载时连接数据库

# ✅ 正确示例：在函数内执行
@st.cache_resource
def init_session():
    from models.database import get_session
    return get_session()

# 在主程序中调用
session = init_session()
```

#### 3. 使用st.session_state管理状态
```python
# 初始化状态
if 'page' not in st.session_state:
    st.session_state.page = 1

if 'filters' not in st.session_state:
    st.session_state.filters = {
        'platform': 'shopee',
        'start_date': '2024-01-01',
        'end_date': '2024-12-31'
    }

# 使用状态
current_page = st.session_state.page
filters = st.session_state.filters
```

#### 4. 懒加载数据
```python
# 使用占位符和按钮控制加载时机
st.subheader("订单数据")

if st.button("📥 加载数据"):
    with st.spinner("正在加载数据..."):
        df = load_orders(platform, start_date, end_date)
        st.session_state.orders_df = df

# 显示已加载的数据
if 'orders_df' in st.session_state:
    st.dataframe(st.session_state.orders_df, use_container_width=True)
else:
    st.info("点击按钮加载数据")
```

### 数据管理中心页面完整示例

```python
# frontend_streamlit/pages/20_数据管理中心.py
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="数据管理中心", layout="wide")

# 初始化服务（使用缓存）
@st.cache_resource
def get_query_service():
    from services.data_query_service import DataQueryService
    from models.database import get_session
    session = get_session()
    return DataQueryService(session)

query_service = get_query_service()

# 页面标题
st.title("📊 数据管理中心")

# 筛选器
col1, col2, col3, col4 = st.columns(4)

with col1:
    platforms = st.multiselect(
        "平台",
        ["shopee", "tiktok", "miaoshou"],
        default=["shopee"]
    )

with col2:
    start_date = st.date_input(
        "开始日期",
        value=datetime.now() - timedelta(days=30)
    )

with col3:
    end_date = st.date_input(
        "结束日期",
        value=datetime.now()
    )

with col4:
    data_type = st.selectbox(
        "数据类型",
        ["订单", "产品", "指标"]
    )

# 构建查询参数
filters = {
    'platforms': platforms,
    'start_date': str(start_date),
    'end_date': str(end_date)
}

# 统计卡片
st.subheader("📈 核心指标")

try:
    stats = query_service.get_statistics(filters)
    
    col1, col2, col3 = st.columns(3)
    
    col1.metric(
        label="总订单数",
        value=f"{stats['total_orders']:,}",
        delta=None,
        delta_color="normal"
    )
    
    col2.metric(
        label="总GMV",
        value=f"¥{stats['total_gmv']:,.2f}",
        delta=None
    )
    
    col3.metric(
        label="平均订单金额",
        value=f"¥{stats['avg_order_value']:.2f}",
        delta=None
    )

except Exception as e:
    st.error(f"加载统计数据失败：{str(e)}")
    st.info("请检查数据库连接或数据是否存在")

# 数据表格
st.subheader("📋 订单数据")

try:
    with st.spinner("正在加载数据..."):
        df = query_service.get_orders(filters)
    
    if len(df) > 0:
        # 显示数据表格
        st.dataframe(
            df,
            use_container_width=True,
            height=400,
            hide_index=True
        )
        
        # 导出功能
        col1, col2, col3 = st.columns([1, 1, 4])
        
        with col1:
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 导出CSV",
                data=csv,
                file_name=f"orders_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col2:
            st.caption(f"共 {len(df)} 条记录")
    
    else:
        st.info("暂无数据，请调整筛选条件或检查数据采集")

except Exception as e:
    st.error(f"加载数据失败：{str(e)}")
    st.info("可能的原因：1) 数据库中无数据 2) 筛选条件过于严格 3) 数据库连接失败")

# 数据可视化
if 'df' in locals() and len(df) > 0:
    st.subheader("📊 数据可视化")
    
    tab1, tab2, tab3 = st.tabs(["📈 趋势分析", "🥧 平台分布", "📊 详细分析"])
    
    with tab1:
        # 每日GMV趋势
        daily_stats = df.groupby('order_date').agg({
            'total_amount_rmb': 'sum',
            'order_id': 'count'
        }).reset_index()
        daily_stats.columns = ['日期', 'GMV', '订单数']
        
        fig = go.Figure()
        
        # 添加GMV线图
        fig.add_trace(go.Scatter(
            x=daily_stats['日期'],
            y=daily_stats['GMV'],
            name='GMV',
            line=dict(color='#1f77b4', width=2),
            yaxis='y1'
        ))
        
        # 添加订单数柱状图
        fig.add_trace(go.Bar(
            x=daily_stats['日期'],
            y=daily_stats['订单数'],
            name='订单数',
            marker=dict(color='#ff7f0e', opacity=0.6),
            yaxis='y2'
        ))
        
        fig.update_layout(
            title='每日GMV与订单趋势',
            xaxis=dict(title='日期'),
            yaxis=dict(title='GMV (¥)', side='left'),
            yaxis2=dict(title='订单数', side='right', overlaying='y'),
            hovermode='x unified',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        # 平台GMV占比
        platform_stats = df.groupby('platform')['total_amount_rmb'].sum()
        
        fig = px.pie(
            values=platform_stats.values,
            names=platform_stats.index,
            title='各平台GMV占比',
            hole=0.4  # 环形图
        )
        
        fig.update_traces(
            textposition='inside',
            textinfo='percent+label'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        # 详细统计表
        platform_detail = df.groupby('platform').agg({
            'order_id': 'count',
            'total_amount_rmb': ['sum', 'mean', 'median']
        }).round(2)
        
        platform_detail.columns = ['订单数', '总GMV', '平均金额', '中位数金额']
        
        st.dataframe(
            platform_detail,
            use_container_width=True
        )

# 页脚信息
st.divider()
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    st.caption(f"数据来源：数据库")

with col2:
    st.caption(f"最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

with col3:
    if st.button("🔄 刷新数据"):
        st.cache_data.clear()
        st.rerun()
```

### 数据查询服务实现

```python
# services/data_query_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd
import streamlit as st
from typing import Dict, Optional
from models.facts import FactOrders, FactProducts

class DataQueryService:
    """数据查询服务（Agent A提供，Agent B调用）"""
    
    def __init__(self, session: Session):
        self.session = session
    
    @st.cache_data(ttl=300)
    def get_orders(_self, filters: Dict) -> pd.DataFrame:
        """
        查询订单数据
        
        Args:
            filters: 查询过滤器
                - platforms: List[str], 可选
                - start_date: str, 必选, 格式YYYY-MM-DD
                - end_date: str, 必选
                - limit: int, 可选, 默认10000
        
        Returns:
            pd.DataFrame: 订单数据
        """
        query = _self.session.query(FactOrders)
        
        # 应用过滤器
        if filters.get('platforms'):
            query = query.filter(FactOrders.platform.in_(filters['platforms']))
        
        if filters.get('start_date'):
            query = query.filter(FactOrders.order_date >= filters['start_date'])
        
        if filters.get('end_date'):
            query = query.filter(FactOrders.order_date <= filters['end_date'])
        
        # 限制返回条数
        limit = filters.get('limit', 10000)
        query = query.limit(limit)
        
        # 按日期倒序
        query = query.order_by(FactOrders.order_date.desc())
        
        # 转换为DataFrame
        try:
            df = pd.read_sql(query.statement, _self.session.bind)
            return df
        except Exception as e:
            st.error(f"查询订单数据失败：{str(e)}")
            return pd.DataFrame()
    
    @st.cache_data(ttl=60)
    def get_statistics(_self, filters: Dict) -> Dict:
        """
        获取统计数据
        
        Args:
            filters: 查询过滤器
        
        Returns:
            dict: {'total_orders': int, 'total_gmv': float, 'avg_order_value': float}
        """
        query = _self.session.query(
            func.count(FactOrders.id).label('total_orders'),
            func.sum(FactOrders.total_amount_rmb).label('total_gmv'),
            func.avg(FactOrders.total_amount_rmb).label('avg_order_value')
        )
        
        # 应用过滤器
        if filters.get('platforms'):
            query = query.filter(FactOrders.platform.in_(filters['platforms']))
        
        if filters.get('start_date'):
            query = query.filter(FactOrders.order_date >= filters['start_date'])
        
        if filters.get('end_date'):
            query = query.filter(FactOrders.order_date <= filters['end_date'])
        
        try:
            result = query.one()
            return {
                'total_orders': result.total_orders or 0,
                'total_gmv': float(result.total_gmv or 0),
                'avg_order_value': float(result.avg_order_value or 0)
            }
        except Exception as e:
            st.error(f"查询统计数据失败：{str(e)}")
            return {
                'total_orders': 0,
                'total_gmv': 0.0,
                'avg_order_value': 0.0
            }
```

### 汇率服务实现

```python
# services/currency_service.py
import requests
from datetime import datetime
from typing import Dict, Optional

class CurrencyService:
    """汇率服务"""
    
    def __init__(self):
        self.api_base = "https://api.exchangerate.host"
        self.cache = {}  # 简单内存缓存
        self.fallback_rates = {
            'USD': 7.2,
            'EUR': 7.8,
            'GBP': 9.1,
            'SGD': 5.3,
            'MYR': 1.6,
            'THB': 0.2,
            'VND': 0.0003,
            'IDR': 0.0005,
        }
    
    def get_rate(self, from_currency: str, to_currency: str, 
                 date: Optional[str] = None) -> float:
        """
        获取汇率
        
        Args:
            from_currency: 源货币代码（如USD）
            to_currency: 目标货币代码（如CNY）
            date: 日期（YYYY-MM-DD），None表示最新汇率
        
        Returns:
            float: 汇率
        """
        # 同币种返回1.0
        if from_currency == to_currency:
            return 1.0
        
        # 检查缓存
        cache_key = f"{from_currency}_{to_currency}_{date or 'latest'}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # 调用API
            if date:
                url = f"{self.api_base}/{date}"
            else:
                url = f"{self.api_base}/latest"
            
            params = {
                'base': from_currency,
                'symbols': to_currency
            }
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            rate = data['rates'][to_currency]
            
            # 更新缓存
            self.cache[cache_key] = rate
            
            return rate
        
        except Exception as e:
            print(f"获取汇率失败，使用兜底汇率：{str(e)}")
            return self.fallback_rate(from_currency, to_currency)
    
    def fallback_rate(self, from_currency: str, to_currency: str) -> float:
        """兜底汇率"""
        if to_currency in ('CNY', 'RMB'):
            return self.fallback_rates.get(from_currency, 1.0)
        else:
            # 简单处理：通过CNY中转
            rate_to_cny = self.fallback_rates.get(from_currency, 1.0)
            rate_from_cny = 1.0 / self.fallback_rates.get(to_currency, 1.0)
            return rate_to_cny * rate_from_cny
    
    def convert_to_rmb(self, amount: float, currency: str, 
                      date: Optional[str] = None) -> float:
        """
        转换为人民币
        
        Args:
            amount: 金额
            currency: 货币代码
            date: 日期（可选）
        
        Returns:
            float: 人民币金额
        """
        if currency in ('CNY', 'RMB'):
            return amount
        
        rate = self.get_rate(currency, 'CNY', date)
        return amount * rate
```

## ⚠️ 常见问题

### Q: 页面白屏怎么办？
**原因**：导入阶段执行了耗时操作（数据库连接、数据查询等）

**解决方法**：
1. 检查文件顶部的import语句后面是否有执行代码
2. 把耗时操作移到函数内部
3. 使用`@st.cache_resource`缓存全局资源

### Q: 页面加载慢怎么办？
**解决方法**：
1. 使用`@st.cache_data`缓存查询结果
2. 限制每次查询的数据量（limit=10000）
3. 使用懒加载，点击按钮才加载数据
4. 使用分页展示大量数据

### Q: 如何调用Agent A提供的接口？
**步骤**：
1. 先查看`docs/API_CONTRACT.md`确认接口签名
2. 从services导入服务类
3. 初始化服务（使用`@st.cache_resource`）
4. 调用服务方法（使用`@st.cache_data`缓存结果）

### Q: 如何与Agent A协调接口变更？
1. 如果需要新的接口，在`docs/API_CONTRACT.md`中提出
2. 等Agent A实现后再调用
3. 如果Agent A修改了接口，需要同步更新前端调用

## 📝 每日检查清单

### 开发前
- [ ] 拉取最新代码：`git pull`
- [ ] 查看今日任务：Plan中的Day X任务
- [ ] 检查`docs/API_CONTRACT.md`是否有接口更新

### 开发中
- [ ] 每完成一个页面就刷新测试
- [ ] 遵守文件修改权限
- [ ] 优化加载性能
- [ ] 每2-3小时提交一次代码

### 开发后
- [ ] 测试所有修改的页面
- [ ] 检查是否有白屏或报错
- [ ] Git提交（使用规范格式）
- [ ] 记录明天的任务清单

## 🚀 加油！

你负责的是用户直接接触的部分，用户体验的好坏直接影响系统的使用。加油让界面更友好、更高效！💪

---

**创建日期**: 2025-10-16  
**版本**: v1.0  
**维护者**: ERP开发团队

