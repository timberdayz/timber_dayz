# 日期格式标准化说明文档

## 问题描述

用户担心：不同数据域的原始字段"日期"可能存在多种格式：
- `25/08/2025` (dd/mm/yyyy)
- `2025-08-25` (yyyy-mm-dd)
- `2025\08\25` (yyyy\mm\dd)
- `2025-08-25-16:30` (带时间)

如果这些不同格式的日期都映射到同一个标准字段"日期"，会不会造成入库后的数据混乱？

## 解决方案

**答案：不会造成混乱，系统会自动标准化**

### 核心机制

1. **智能日期解析器** (`modules/services/smart_date_parser.py`)
   - 支持多种日期格式自动识别
   - 自动检测日期格式偏好（dayfirst=True/False）
   - 统一转换为Python `date`对象

2. **数据标准化服务** (`backend/services/data_standardizer.py`)
   - 在数据入库前自动标准化所有日期字段
   - 无论原始格式如何，统一转换为标准格式
   - 入库后数据库中的日期格式完全一致

### 处理流程

```
原始字段（多种格式）
    ↓
字段映射（选择"日期"标准字段）
    ↓
数据标准化（统一转换为date对象）
    ↓
数据验证（确保日期有效）
    ↓
入库（PostgreSQL自动存储为DATE类型）
```

### 支持的日期格式

系统可以自动识别并转换以下格式：

1. **字符串格式**：
   - `25/08/2025` → `2025-08-25` (自动检测dayfirst=True)
   - `2025-08-25` → `2025-08-25` (ISO格式)
   - `2025\08\25` → `2025-08-25` (自动处理反斜杠)
   - `2025-08-25-16:30` → `2025-08-25` (自动丢弃时间部分)

2. **Excel序列值**：
   - `44818` → `2022-09-15` (自动识别Excel日期序列)

3. **datetime对象**：
   - 直接提取date部分

### 自动格式检测

系统会自动检测日期格式偏好：

```python
# 从前10行数据中采样检测
samples = ["25/08/2025", "26/08/2025", "27/08/2025"]
prefer_dayfirst = detect_dayfirst(samples)  # → True (dd/mm/yyyy)

# 使用检测结果解析所有日期
parsed_date = parse_date("25/08/2025", prefer_dayfirst=True)  # → 2025-08-25
```

### 日期 vs 时间字段处理

### DateTime字段（保留时间）

对于需要保留时间信息的字段（如`order_time_utc`），系统会：
- 保留时间部分：`2025-08-25-16:30` → `datetime(2025, 8, 25, 16, 30, 0)`
- 入库后可以精确查询到具体时刻

支持的DateTime字段：
- `order_time_utc` - 订单时间（UTC）
- `payment_time` - 支付时间
- `ship_time` - 发货时间

### Date字段（丢弃时间）

对于只需要日期信息的字段（如`metric_date`），系统会：
- 丢弃时间部分：`2025-08-25-16:30` → `date(2025, 8, 25)`
- 入库后只能按日期查询

支持的Date字段：
- `order_date_local` - 订单日期（本地）
- `metric_date` - 指标日期
- `service_date` - 服务日期

### 自动识别

系统会根据字段名自动判断：
- 包含`time`的字段 → DateTime类型（保留时间）
- 包含`date`的字段 → Date类型（丢弃时间）

### 前端显示

前端可以根据字段类型决定显示格式：
```javascript
// DateTime字段：显示完整时间
if (fieldType === 'datetime') {
  return formatDateTime(value);  // "2025-08-25 16:30:00"
}

// Date字段：只显示日期
if (fieldType === 'date') {
  return formatDate(value);  // "2025-08-25"
}
```

### 错误处理

如果日期无法解析：
- 记录警告日志
- 保留原始值（进入`attributes` JSONB列）
- 不阻塞其他数据的入库

## 使用示例

```python
from backend.services.data_standardizer import standardize_rows

# 原始数据（多种格式）
rows = [
    {"metric_date": "25/08/2025", "amount": 100},
    {"metric_date": "2025-08-25", "amount": 200},
    {"metric_date": "2025-08-25-16:30", "amount": 300},
]

# 标准化后（统一格式）
standardized = standardize_rows(rows, domain="orders")
# 结果：
# [
#     {"metric_date": date(2025, 8, 25), "amount": 100.0},
#     {"metric_date": date(2025, 8, 25), "amount": 200.0},
#     {"metric_date": date(2025, 8, 25), "amount": 300.0},
# ]
```

## 结论

✅ **不会造成数据混乱**
- 系统自动标准化所有日期格式
- 入库后统一为标准的`YYYY-MM-DD`格式
- 查询和分析时不会出现格式不一致的问题

✅ **用户无需担心**
- 无论选择哪种格式的日期字段映射到"日期"
- 系统都会自动处理格式转换
- 入库后的数据格式完全统一

