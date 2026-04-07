# Metabase同步验证指南

## ✅ 从截图看，表已经同步了！

从你提供的Metabase截图可以看到，**很多新表已经显示**：

### 已确认同步的表

**B类数据表（13张）** - ✅ 全部显示：
- Fact Raw Data Inventory Snapshot
- Fact Raw Data Orders Daily
- Fact Raw Data Orders Monthly
- Fact Raw Data Orders Weekly
- Fact Raw Data Products Daily
- Fact Raw Data Products Monthly
- Fact Raw Data Products Weekly
- Fact Raw Data Services Daily
- Fact Raw Data Services Monthly
- Fact Raw Data Services Weekly
- Fact Raw Data Traffic Daily
- Fact Raw Data Traffic Monthly
- Fact Raw Data Traffic Weekly

**其他表** - ✅ 已显示：
- Entity Aliases
- Employee Commissions
- Employee Performance
- Employee Targets
- Employees
- Attendance Records

### 需要查找的表（可能在列表中，需要滚动查看）

**A类数据表**：
- Sales Targets A（可能在"S"开头的区域）
- Sales Campaigns A（可能在"S"开头的区域）
- Operating Costs（可能在"O"开头的区域）
- Performance Config A（可能在"P"开头的区域）

**C类数据表**：
- Shop Commissions（可能在"S"开头的区域）
- Performance Scores C（可能在"P"开头的区域）

**其他表**：
- Staging Raw Data（可能在"S"开头的区域）

## 🔍 如何验证所有表都已同步

### 方法1：使用搜索功能

在Metabase的数据库页面，使用搜索框搜索以下关键词：

1. **搜索 "sales"** - 应该找到：
   - Sales Targets A
   - Sales Campaigns A

2. **搜索 "operating"** - 应该找到：
   - Operating Costs

3. **搜索 "performance"** - 应该找到：
   - Performance Config A
   - Performance Scores C

4. **搜索 "shop"** - 应该找到：
   - Shop Commissions

5. **搜索 "staging"** - 应该找到：
   - Staging Raw Data

### 方法2：按字母顺序查找

表是按字母顺序排列的，可以：

- **查找 "O" 开头的表** → Operating Costs
- **查找 "P" 开头的表** → Performance Config A, Performance Scores C
- **查找 "S" 开头的表** → Sales Targets A, Sales Campaigns A, Shop Commissions, Staging Raw Data

### 方法3：检查表总数

1. 在数据库详情页，查看表的总数
2. 应该看到**至少26张新表**（加上旧表，总数应该更多）

## ⚠️ 如果表确实缺失

### 可能的原因

1. **表过滤设置**
   - Metabase可能配置了表过滤规则
   - 某些表被排除在外

2. **Schema同步不完整**
   - 虽然点击了同步，但可能只同步了部分表

3. **表名大小写问题**
   - PostgreSQL表名是小写，Metabase显示可能不同

### 解决方案

#### 方案1：检查表过滤设置

1. Admin → Databases → XIHONG_ERP → **Edit**
2. 检查以下设置：
   - **Table inclusion patterns**: 应该为空或包含所有表
   - **Table exclusion patterns**: 应该为空或不排除新表
   - **Schema**: 应该包含 `public`

#### 方案2：强制重新同步

1. 在数据库详情页，点击 **"Sync database schema now"**
2. 等待同步完成（可能需要30-60秒）
3. 刷新页面

#### 方案3：使用API强制同步

如果知道Metabase管理员密码：

```bash
# 需要设置正确的密码
export METABASE_PASSWORD="你的密码"
python scripts/sync_dss_tables_to_metabase.py
```

## 📊 完整验证清单

- [ ] 在Metabase中搜索 "sales" - 找到 Sales Targets A 和 Sales Campaigns A
- [ ] 在Metabase中搜索 "operating" - 找到 Operating Costs
- [ ] 在Metabase中搜索 "performance" - 找到 Performance Config A 和 Performance Scores C
- [ ] 在Metabase中搜索 "shop" - 找到 Shop Commissions
- [ ] 在Metabase中搜索 "staging" - 找到 Staging Raw Data
- [ ] 检查数据库详情页的表总数
- [ ] 检查表过滤设置（如果没有找到某些表）

## 💡 提示

从你的截图看，**表已经同步了**！可能只是：
1. 需要滚动页面查看更多表
2. 表名显示格式不同（下划线变成空格，首字母大写）
3. 某些表在列表的其他位置

**建议**：使用搜索功能查找特定的表名，这样更容易找到。

---

**最后更新**: 2025-11-26 17:05

