# 多Agent开发常见问题（FAQ）

## 📋 文档说明

本文档收集多Agent开发过程中的常见问题和解决方案，帮助你快速解决问题，节省时间。

---

## 🔧 开发工具问题

### Q1: 我应该什么时候使用Cursor，什么时候使用Augment？

**快速回答**:
- **后端任务（数据库、ETL、性能优化）** → Cursor
- **前端任务（页面、UI、用户体验）** → Augment

**详细时间表**:
```
Day 1-4全天: Cursor（后端开发）
Day 5上午: Cursor（完成数据查询服务）
Day 5下午: 切换到Augment（前端修复）
Day 6上午: 继续Augment（前端优化）
Day 6下午: 切换回Cursor（PostgreSQL）
Day 7: 灵活切换
```

**如何决定**:
看今天的主要任务是什么：
- 如果是写models/、services/etl相关 → Cursor
- 如果是写frontend_streamlit/、优化UI → Augment

---

### Q2: 如何切换AI工具？

**Cursor → Augment**:
1. 在Cursor中提交所有代码：`git add . && git commit`
2. 关闭Cursor
3. 打开Augment
4. 在Augment中拉取最新代码（如果需要）

**Augment → Cursor**:
1. 在Augment中提交所有代码
2. 关闭Augment
3. 打开Cursor
4. 继续开发

**注意**: 不需要频繁切换，一般完成一大块工作后再切换（如上午用Cursor，下午切Augment）

---

### Q3: Agent理解错了我的需求怎么办？

**方法1: 重新描述需求**
```
不好的描述：
"帮我写个数据库"

好的描述：
"帮我创建一个订单事实表的ORM模型，包含以下字段：
- order_id（订单号）
- order_date（订单日期）
- total_amount（订单金额）
参考现有的models/product.py的写法"
```

**方法2: 分步骤说明**
```
"我需要实现一个Excel解析器，分3步：
1. 先判断文件格式（.xlsx还是.xls）
2. 使用对应的库读取（openpyxl或xlrd）
3. 返回pandas DataFrame
每一步你都告诉我在做什么"
```

**方法3: 提供示例**
```
"我要实现一个类似这样的功能：
[粘贴示例代码或截图]
帮我在XXX文件中实现"
```

---

## 📁 文件权限问题

### Q4: 如何知道我能不能修改某个文件？

**快速查表法**:
打开 `docs/FILE_ISOLATION_RULES.md`，查看权限矩阵表格

**快速判断法**:
- 文件路径包含`models/`或`migrations/`或`services/etl*` → Agent A可以改
- 文件路径包含`frontend_streamlit/`或`utils/` → Agent B可以改
- 文件路径包含`collection_center/` → 谁都不能改（冻结）

**不确定时**:
默认按照这个原则：
- 数据库、ETL、后端逻辑 → Agent A
- 前端、UI、工具类 → Agent B

---

### Q5: 我不小心改了对方的文件怎么办？

**发现后立即撤销**:
```bash
# 查看改了哪些文件
git status

# 发现改错了，立即撤销
git checkout -- <误修改的文件>

# 如果已经commit了，撤销上一次提交
git reset --soft HEAD~1
```

**预防方法**:
- 提交前检查`git status`
- 看到不属于你的目录，立即撤销

---

### Q6: 我需要修改共享文件怎么办？

**共享文件列表**:
- `services/data_query_service.py`（数据查询服务）
- `config/database.yaml`（数据库配置）
- `docs/API_CONTRACT.md`（接口契约）

**正确流程**:
1. 在`docs/API_CONTRACT.md`中定义接口签名
2. 说明为什么要修改
3. 实现接口（Agent A或B根据职责）
4. Git提交时注明"⚠️ 接口变更"

---

## 🐛 调试问题

### Q7: 代码运行报错了怎么办？

**Step 1: 复制完整错误信息**
```
包括：
- 错误类型（如ValueError, KeyError）
- 错误信息
- 完整的Traceback（堆栈跟踪）
```

**Step 2: 粘贴给Agent**
```
"运行XXX功能时报这个错误：
[粘贴完整错误信息]

这是相关的代码：
[粘贴代码片段]

请帮我修复"
```

**Step 3: 应用修复**
```
Agent会给你修复后的代码，直接替换即可
```

---

### Q8: 如何调试性能问题？

**方法1: 使用cProfile（Python性能分析）**
```python
import cProfile
import pstats

# 创建profiler
profiler = cProfile.Profile()
profiler.enable()

# 你要测试的代码
from services.etl_pipeline import ETLPipeline
pipeline = ETLPipeline()
pipeline.process_file('test.xlsx', 'shopee', 'orders')

# 停止并输出结果
profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')  # 按累计时间排序
stats.print_stats(20)  # 显示最慢的20个函数
```

**看懂结果**:
```
ncalls  tottime  percall  cumtime  percall filename:lineno(function)
1000    2.500    0.003    5.000    0.005   excel_parser.py:45(parse)

解读：
- ncalls: 调用了1000次
- tottime: 总共花了2.5秒
- cumtime: 累计时间5秒（包括子函数）
→ 这个函数是瓶颈！需要优化
```

**方法2: 使用time测量**
```python
import time

start = time.time()
# 你的代码
result = some_function()
print(f"耗时: {time.time() - start:.2f}秒")
```

**方法3: 问Agent**
```
"这段代码运行很慢：
[粘贴代码]
请帮我分析性能瓶颈并优化"
```

---

### Q9: Streamlit页面白屏怎么办？

**最常见原因**: 导入阶段执行了耗时操作

**诊断方法**:
```python
# 检查文件顶部
import streamlit as st
from models.database import get_session

# ❌ 错误：导入时就创建会话
session = get_session()  # 这会导致白屏！

# ✅ 正确：在函数内创建
@st.cache_resource
def init_session():
    from models.database import get_session
    return get_session()

# 使用时调用
session = init_session()
```

**检查清单**:
- [ ] 文件顶部是否有数据库连接？
- [ ] 文件顶部是否有数据查询？
- [ ] 文件顶部是否有文件读取？
- [ ] 文件顶部是否有复杂计算？

**解决方法**:
把所有耗时操作移到函数内部，使用`@st.cache_resource`或`@st.cache_data`

---

### Q10: 如何查看Streamlit的详细错误信息？

**方法1: 浏览器控制台**
```
1. 打开Streamlit页面
2. 按F12打开开发者工具
3. 查看Console标签
4. 复制错误信息给Agent
```

**方法2: 终端错误信息**
```
运行streamlit时，终端会显示详细的Python错误
直接复制Traceback给Agent
```

**方法3: 添加调试信息**
```python
import streamlit as st

try:
    # 可能出错的代码
    df = load_data()
    st.dataframe(df)
except Exception as e:
    st.error(f"错误: {str(e)}")
    import traceback
    st.code(traceback.format_exc())  # 显示完整错误堆栈
```

---

## 🔄 Git与版本控制问题

### Q11: 如何提交代码？

**基础提交流程**:
```bash
# 1. 查看修改了哪些文件
git status

# 2. 添加所有修改（或指定文件）
git add .
# 或
git add models/dimensions.py services/etl_pipeline.py

# 3. 提交（使用规范格式）
git commit -m "[Agent A] Day 1: 完成数据库Schema设计

- 创建维度表模型
- 创建事实表模型
- 实现Alembic迁移
- 影响范围: models/, migrations/
"

# 4. 推送到远程（如果有）
git push
```

**提交频率建议**:
- 小改动：每2-3小时提交一次
- 完成一个功能模块：立即提交
- 每天晚上11:00：必须提交

---

### Q12: 如何撤销错误的修改？

**情况1: 还没commit**
```bash
# 撤销单个文件
git checkout -- <文件路径>

# 撤销所有修改
git checkout -- .
```

**情况2: 已经commit但没push**
```bash
# 撤销上一次commit（保留修改）
git reset --soft HEAD~1

# 撤销上一次commit（丢弃修改）
git reset --hard HEAD~1
```

**情况3: 已经push了**
```bash
# 创建一个新commit撤销之前的修改
git revert <commit-hash>
```

---

### Q13: 如何查看Git历史？

**查看提交历史**:
```bash
# 简洁版
git log --oneline -10

# 详细版
git log -10

# 图形化版本
git log --graph --oneline --all
```

**查看某个文件的修改历史**:
```bash
git log -- models/order.py
```

**查看某次提交的具体改动**:
```bash
git show <commit-hash>
```

---

## 💻 代码问题

### Q14: 如何导入项目中的模块？

**正确的导入方式**:
```python
# ✅ 从项目根目录导入
from models.dimensions import DimPlatform, DimShop
from services.etl_pipeline import ETLPipeline
from modules.core import get_logger

# ❌ 错误：相对导入
from ..models.dimensions import DimPlatform  # 不推荐
```

**如果提示ModuleNotFoundError**:
```python
# 添加项目根目录到Python路径
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 然后再导入
from models.dimensions import DimPlatform
```

---

### Q15: 如何添加类型注解？

**基础类型注解**:
```python
from typing import List, Dict, Optional, Union
from pathlib import Path
import pandas as pd

def process_file(
    file_path: Path,           # Path对象
    platform: str,             # 字符串
    options: Dict[str, Any]    # 字典
) -> pd.DataFrame:             # 返回DataFrame
    """处理文件"""
    pass

def get_orders(
    platforms: List[str],      # 字符串列表
    start_date: Optional[str]  # 可选字符串
) -> Optional[pd.DataFrame]:   # 可能返回None
    """查询订单"""
    pass
```

**复杂类型注解**:
```python
from typing import TypedDict, Union
from dataclasses import dataclass

# 方法1: TypedDict
class OrderFilter(TypedDict):
    platforms: List[str]
    start_date: str
    end_date: str

# 方法2: dataclass
@dataclass
class ProcessResult:
    success: bool
    rows: int
    error: Optional[str] = None

# 方法3: Pydantic
from pydantic import BaseModel

class OrderFilter(BaseModel):
    platforms: List[str]
    start_date: str
    end_date: str
```

---

### Q16: 如何写docstring？

**Google风格docstring**（项目标准）:
```python
def process_file(file_path: Path, platform: str, data_domain: str) -> ProcessResult:
    """
    处理单个文件的完整ETL流程
    
    该函数会执行以下步骤：
    1. 解析Excel文件
    2. 字段映射
    3. 数据验证
    4. 入库到数据库
    
    Args:
        file_path: Excel文件路径
        platform: 平台名称（shopee/tiktok/miaoshou）
        data_domain: 数据域（orders/products/metrics）
    
    Returns:
        ProcessResult: 处理结果，包含成功/失败状态和行数
    
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不支持
        
    Example:
        >>> pipeline = ETLPipeline()
        >>> result = pipeline.process_file(
        ...     Path('temp/outputs/orders.xlsx'),
        ...     'shopee',
        ...     'orders'
        ... )
        >>> print(result.success)
        True
    """
    pass
```

---

## 🔌 接口协调问题

### Q17: 我需要Agent B提供的接口，但他还没实现怎么办？

**解决方案：先写mock实现**
```python
# services/currency_service.py (临时mock版本)
class CurrencyService:
    """汇率服务（临时mock，等Agent B实现）"""
    
    def get_rate(self, from_currency: str, to_currency: str, date: str = None) -> float:
        """临时返回固定汇率"""
        mock_rates = {
            'USD': 7.2,
            'EUR': 7.8,
            'SGD': 5.3,
        }
        return mock_rates.get(from_currency, 1.0)
    
    def convert_to_rmb(self, amount: float, currency: str, date: str = None) -> float:
        """临时实现"""
        if currency in ('CNY', 'RMB'):
            return amount
        return amount * self.get_rate(currency, 'CNY', date)

# 在你的代码中使用mock版本
from services.currency_service import CurrencyService
currency_service = CurrencyService()
rmb_amount = currency_service.convert_to_rmb(100, 'USD')
```

**等Agent B实现后**:
直接替换文件即可，因为接口签名一致

---

### Q18: 接口需要变更怎么办？

**流程**:
1. 在`docs/API_CONTRACT.md`中记录变更
2. 在Git提交信息中注明"⚠️ 接口变更"
3. 如果对方已经在使用该接口，保留旧接口（兼容）

**示例**:
```python
# 旧接口（保留，标记为废弃）
def get_orders(self, platform: str) -> pd.DataFrame:
    """旧接口，已废弃，请使用get_orders_v2"""
    return self.get_orders_v2({'platforms': [platform]})

# 新接口
def get_orders_v2(self, filters: dict) -> pd.DataFrame:
    """新接口，支持更多过滤条件"""
    pass
```

---

## 🚨 紧急问题

### Q19: 一天的任务完成不了怎么办？

**立即行动**（不要拖延）:

**Step 1: 评估剩余时间**
```
当前时间: 下午5点
剩余时间: 6小时（5-11点）
未完成任务: [列出]
```

**Step 2: 优先级排序**
```
P0（必须完成）:
- [任务1]

P1（尽量完成）:
- [任务2]

P2（可以延后）:
- [任务3]
```

**Step 3: 调整计划**
```
集中精力完成P0任务
P1和P2任务记录到 docs/POSTPONED_TASKS.md
明天早上第一件事完成P1任务
```

**Step 4: 记录到进度追踪**
```
在 docs/DAILY_PROGRESS_TRACKER.md 中记录：
- 今日完成情况
- 延后的任务
- 明日计划调整
```

---

### Q20: 遇到技术难题卡住了怎么办？

**超过30分钟还没解决 → 立即换思路**

**方法1: 简化需求**
```
原需求: 实现复杂的AI字段映射算法
简化后: 先用简单的规则匹配，AI算法后面再加
```

**方法2: 换个实现方式**
```
原方案: 使用复杂的ORM查询
替代方案: 直接写SQL，简单明了
```

**方法3: 临时绕过**
```
原需求: 实现完美的错误处理
临时方案: 简单的try-except，先让功能跑起来
```

**方法4: 寻求帮助**
```
1. Google搜索错误信息
2. 查看类似的代码怎么实现的
3. 问AI："有没有更简单的方法实现XXX？"
```

**终极方案: 记录并跳过**
```
在 docs/UNSOLVED_ISSUES.md 中记录：
- 问题描述
- 尝试过的方法
- 卡住的地方
Day 7统一解决
```

---

## 📊 测试问题

### Q21: 如何运行测试？

**运行单个测试文件**:
```bash
# 使用pytest
pytest tests/test_excel_parser.py -v

# 使用python
python -m pytest tests/test_excel_parser.py
```

**运行所有测试**:
```bash
pytest tests/ -v
```

**运行测试并查看覆盖率**:
```bash
pytest tests/ --cov=services --cov=models --cov-report=html

# 查看报告
# 打开 htmlcov/index.html
```

---

### Q22: 测试写不出来怎么办？

**让Agent帮你写**:
```
"帮我为这个函数写单元测试：
[粘贴函数代码]

测试场景：
1. 正常情况
2. 文件不存在
3. 文件格式错误
"
```

**参考现有测试**:
```
查看 tests/ 目录下已有的测试，模仿着写
```

**最简单的测试**:
```python
def test_basic():
    """最基础的测试：能运行不报错"""
    parser = ExcelParser()
    result = parser.parse('test_data/sample.xlsx')
    assert result is not None
    assert len(result) > 0
```

---

## 🎯 效率提升问题

### Q23: 如何提高开发效率？

**技巧1: 复用现有代码**
```
不要从零写，找项目中类似的代码改改
例如：要写models/order.py，就复制models/product.py改
```

**技巧2: 让Agent一次多干点活**
```
不好的做法：
"帮我创建一个类"
"帮我添加一个方法"
"帮我写个测试"
（需要多次对话）

好的做法：
"帮我创建一个Excel解析器类，包含：
1. parse方法（支持.xlsx和.xls）
2. clean方法（清洗数据）
3. 完整的docstring
4. 单元测试
一次性完成"
```

**技巧3: 批量操作**
```bash
# 批量创建文件
告诉Agent：
"帮我创建以下3个文件：
1. models/dimensions.py - 维度表模型
2. models/facts.py - 事实表模型
3. models/management.py - 管理表模型
参考models/product.py的结构"
```

**技巧4: 使用代码片段**
```
在.cursorrules或Agent手册中有很多代码示例
直接复制粘贴，让Agent帮你改成你需要的
```

---

### Q24: 如何避免浪费时间？

**时间杀手1: 追求完美**
```
❌ 不要: 花2小时优化一个不重要的函数
✅ 应该: 先让核心功能跑起来，Day 4再优化
```

**时间杀手2: 重复造轮子**
```
❌ 不要: 自己从零实现Excel解析（pandas已经有了）
✅ 应该: 直接用pd.read_excel，封装一下就行
```

**时间杀手3: 纠结技术选型**
```
❌ 不要: 花1小时研究用Redis还是内存缓存
✅ 应该: 先用简单的dict缓存，Day 4再考虑Redis
```

**时间杀手4: 过度测试**
```
❌ 不要: Day 1就写测试覆盖所有边缘case
✅ 应该: Day 1-3专注功能，Day 4再补测试
```

---

## 🎓 学习问题

### Q25: 我不懂SQLAlchemy怎么办？

**快速学习法**:
```
1. 查看项目现有的models/代码（最快）
2. 让Agent解释给你听
3. 边做边学，不懂就问

不需要系统学习，用到什么学什么
```

**常用操作示例**:
```python
# 查询
from models.facts import FactOrders
orders = session.query(FactOrders).filter(
    FactOrders.platform == 'shopee',
    FactOrders.order_date >= '2024-01-01'
).limit(100).all()

# 插入
new_order = FactOrders(
    platform='shopee',
    order_id='12345',
    total_amount=100.0
)
session.add(new_order)
session.commit()

# 更新
order = session.query(FactOrders).filter_by(order_id='12345').first()
order.total_amount = 200.0
session.commit()
```

---

### Q26: 我不懂Streamlit怎么办？

**快速上手**:
```python
import streamlit as st

# 显示标题
st.title("我的页面")

# 显示文本
st.write("Hello World")

# 显示数据表格
import pandas as pd
df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
st.dataframe(df)

# 添加按钮
if st.button("点击我"):
    st.write("你点击了按钮")

# 添加选择框
option = st.selectbox("选择", ["选项1", "选项2"])
st.write(f"你选择了：{option}")

# 添加输入框
text = st.text_input("输入")
st.write(f"你输入了：{text}")
```

**学习资源**:
- 官方文档: https://docs.streamlit.io/
- 查看项目中现有的pages/代码
- 让Agent写示例代码

---

## 🎯 规划问题

### Q27: 如何规划每天的任务？

**早上9:00的30分钟计划时间**:
```
1. 查看Plan中今日任务
2. 评估任务难度和时间
3. 排定优先级（核心任务优先）
4. 分配到上午/下午/晚上
5. 开始第一个任务
```

**任务分配原则**:
- 上午（9-13）：4小时 → 2-3个任务
- 下午（14-18）：4小时 → 2-3个任务
- 晚上（19-23）：4小时 → 2-3个任务

**示例**:
```
Day 1任务分配:
上午: 
  - 系统诊断（2小时）
  - 数据库评估（1小时）
  - 前端诊断（1小时）

下午:
  - Schema设计（2小时）
  - 创建ORM模型（2小时）

晚上:
  - Alembic配置（1小时）
  - 创建迁移（2小时）
  - 测试迁移（1小时）
```

---

### Q28: 如何判断任务是否完成？

**验收标准**:
每个Day的Plan中都有"验收标准"，对照检查：

```
Day 1验收:
□ 完成系统诊断报告
□ 数据库Schema文档完整
□ ORM模型代码完成
□ Alembic迁移可用

如果全部打勾 → 任务完成 ✅
如果有未完成 → 评估影响，决定是否延后
```

**功能验收**:
```python
# 最简单的验收方法：能运行不报错
python -c "from models.dimensions import DimPlatform; print('✓')"

# ETL验收：能成功处理文件
python -c "from services.etl_pipeline import ETLPipeline; 
           p = ETLPipeline(); 
           r = p.process_file('test.xlsx', 'shopee', 'orders'); 
           print('✓' if r.success else '✗')"
```

---

## 📝 文档问题

### Q29: 需要写多少文档？

**必须写的文档**（Day 6-7）:
- [ ] `API_CONTRACT.md`（接口定义，Agent A+B共同）
- [ ] `DATABASE_SCHEMA_V3.md`（数据库设计，Agent A）
- [ ] `DEPLOYMENT_GUIDE.md`（部署指南，Agent A）
- [ ] `QUICK_START.md`（快速开始，Agent B）

**可延后的文档**:
- 详细的用户手册
- 完整的API参考
- 故障排查详解

**文档编写技巧**:
```
1. 让Agent帮你写：
   "帮我编写部署指南文档，包括：
   1. 环境要求
   2. 安装步骤
   3. 配置说明
   4. 常见问题"

2. 使用模板：
   参考 docs/ 中现有文档的结构

3. 代码注释够用就行：
   写好docstring比单独写文档更重要
```

---

## 🎊 激励与支持

### Q30: 感觉任务太重，完成不了怎么办？

**记住**:
- ✅ 你有84小时有效开发时间
- ✅ 有详细的代码示例和模板
- ✅ 有强大的AI工具辅助
- ✅ 每天都有明确的小目标

**调整心态**:
- 不要追求完美，能用就行
- 核心功能优先，细节后面再说
- 每天完成一点，7天就是一大步
- 相信AI工具，它们很强大

**时间分配**:
- 开发时间：70%（8-9小时）
- 调试时间：20%（2-3小时）
- 休息时间：10%（1小时）

**休息很重要**:
- 每工作1小时，休息5-10分钟
- 中午吃饭+午休1小时
- 晚饭休息30分钟
- 不要连续工作超过2小时

---

## 📞 联系与支持

### 如果真的卡住了
1. 先休息10分钟
2. 回来重新描述问题给Agent
3. 尝试更简单的实现方式
4. 记录问题，先做其他任务
5. Day 7统一解决遗留问题

### 需要调整计划
随时调整计划是正常的！
- 记录到`DAILY_PROGRESS_TRACKER.md`
- 下次开发前先看调整后的计划
- 保证核心功能能完成就行

---

**版本**: v1.0  
**创建日期**: 2025-10-16  
**维护者**: ERP开发团队  
**更新频率**: 持续更新常见问题

