# 店铺别名映射表使用指南

## 📋 概述

`config/shop_aliases.yaml` 是妙手(miaoshou)订单账号级对齐的核心配置文件。

### 为什么需要这个文件？

**问题**：
- 妙手ERP导出的订单包含"店铺"列，值如"菲律宾1店"、"3C店"、"5店玩具"
- 这些名称是口语化的，没有统一标准
- 随着人员变动，命名规则可能不一致

**解决**：
- 通过别名表，将这些口语化名称映射到统一的标准账号ID
- 报表按标准账号ID聚合，数据稳定可靠

---

## 🎯 配置格式

### 基本格式
```yaml
shop_aliases:
  'miaoshou:<账号>:<站点>:<原始店铺名>': '<标准账号ID>'
```

### 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| 平台 | 固定为`miaoshou` | miaoshou |
| 账号 | 采购账号名称 | 虾皮巴西_东朗照明主体 |
| 站点 | 国家/地区 | 菲律宾、新加坡、马来 |
| 原始店铺名 | 妙手导出文件中的"店铺"列值 | 菲律宾1店、3C店 |
| 标准账号ID | 你定义的统一ID | shopee_ph_1, shopee_sg_3c |

### 完整示例
```yaml
shop_aliases:
  # 虾皮巴西账号 - 菲律宾站点
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾1店': 'shopee_ph_1'
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾2店': 'shopee_ph_2'
  
  # 虾皮巴西账号 - 新加坡站点
  'miaoshou:虾皮巴西_东朗照明主体:新加坡:3C店': 'shopee_sg_3c'
  'miaoshou:虾皮巴西_东朗照明主体:新加坡:5店玩具': 'shopee_sg_toys'
```

---

## 🔍 工作原理

### 数据流程

#### 1. 订单入库（自动）
```
妙手导出文件：
  订单号 | 店铺 | 站点 | 采购账号 | 金额
  O001 | 菲律宾1店 | 菲律宾 | 虾皮巴西_东朗照明主体 | 100

入库到 fact_orders：
  platform_code = 'miaoshou'
  shop_id = 'none'  # 统一为none
  store_label_raw = '菲律宾1店'  # 保留原始值
  site = '菲律宾'
  account = '虾皮巴西_东朗照明主体'
  aligned_account_id = NULL  # 待对齐
```

#### 2. 别名对齐（执行脚本）
```bash
# 执行回填脚本
python scripts/backfill_account_alignment.py

# 系统查找匹配：
查找 'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾1店'
  ↓
找到映射: 'shopee_ph_1'
  ↓
更新: aligned_account_id = 'shopee_ph_1'
```

#### 3. 报表查询（自动）
```sql
-- 按标准账号ID聚合
SELECT aligned_account_id, SUM(total_amount_rmb) as gmv
FROM fact_orders
WHERE platform_code = 'miaoshou'
GROUP BY aligned_account_id

结果：
shopee_ph_1: 1000元
shopee_ph_2: 2000元
shopee_sg_3c: 3000元
```

### 匹配策略（3级）

系统会按以下顺序尝试匹配：

#### Level 1：精确匹配（最优先）
```
账号 + 站点 + 店铺名 完全匹配
示例：虾皮巴西_东朗照明主体 + 菲律宾 + 菲律宾1店
```

#### Level 2：宽松匹配
```
账号 + 店铺名 匹配（忽略站点）
示例：虾皮巴西_东朗照明主体 + 菲律宾1店
```

#### Level 3：最宽松匹配
```
仅店铺名匹配（忽略账号和站点）
示例：仅匹配 菲律宾1店
```

**建议**：尽量使用精确匹配（Level 1），避免歧义。

---

## 📝 使用步骤

### 方式A：自动生成模板（推荐）

#### 步骤1：提取所有店铺名
```bash
python scripts/miaoshou_shop_alias_builder.py
```

**效果**：
- 自动扫描所有妙手订单文件
- 提取"店铺"列的所有不同值
- 生成/更新 `config/shop_aliases.yaml`
- 每个店铺名后面留空，等待你填入标准ID

**生成的模板示例**：
```yaml
shop_aliases:
  'miaoshou:::菲律宾1店': ''  # 请填入标准账号ID，如 shopee_ph_1
  'miaoshou:::3C店': ''  # 请填入标准账号ID，如 shopee_sg_3c
  'miaoshou:::5店玩具': ''  # 请填入标准账号ID，如 shopee_sg_toys
```

#### 步骤2：填入标准账号ID
编辑文件，将空值改为标准ID：
```yaml
shop_aliases:
  'miaoshou:::菲律宾1店': 'shopee_ph_1'
  'miaoshou:::3C店': 'shopee_sg_3c'
  'miaoshou:::5店玩具': 'shopee_sg_toys'
```

#### 步骤3：执行对齐
```bash
python scripts/backfill_account_alignment.py
```

#### 步骤4：查看结果
```bash
curl http://localhost:8001/api/account-alignment/stats
```

---

### 方式B：手动添加（适合少量店铺）

#### 直接编辑YAML文件
```yaml
shop_aliases:
  # 格式：'miaoshou:<账号>:<站点>:<店铺名>': '<标准ID>'
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾1店': 'shopee_ph_1'
```

#### 或通过API添加
```bash
curl -X POST http://localhost:8001/api/account-alignment/add-alias \
  -H "Content-Type: application/json" \
  -d '{
    "account": "虾皮巴西_东朗照明主体",
    "site": "菲律宾",
    "store_label_raw": "菲律宾1店",
    "target_id": "shopee_ph_1",
    "notes": "菲律宾主力店铺"
  }'
```

---

## 💡 配置示例

### 示例1：完整配置（精确匹配）
```yaml
shop_aliases:
  # 账号1 - 虾皮巴西
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾1店': 'shopee_ph_1'
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾2店': 'shopee_ph_2'
  'miaoshou:虾皮巴西_东朗照明主体:新加坡:3C店': 'shopee_sg_3c'
  
  # 账号2 - 虾皮新加坡
  'miaoshou:虾皮新加坡账号:新加坡:新加坡主店': 'shopee_sg_main'
```

### 示例2：简化配置（全局唯一店铺）
```yaml
shop_aliases:
  # 如果"旗舰店"在所有账号都唯一，可以简化
  'miaoshou:::旗舰店': 'flagship_store'
  
  # 仍推荐完整配置以避免歧义
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:旗舰店': 'shopee_ph_flagship'
```

### 示例3：处理特殊字符
```yaml
shop_aliases:
  # 店铺名包含空格、括号等特殊字符时，用引号包裹
  'miaoshou:账号名:站点:店铺名（旧）': 'standard_id_old'
  'miaoshou:账号名:站点:店铺名 - 新': 'standard_id_new'
```

---

## 🎯 标准账号ID命名建议

### 推荐格式
```
<平台>_<国家代码>_<店铺标识>
```

### 国家代码（ISO 3166-1 alpha-2）
| 国家/地区 | 代码 | 示例 |
|-----------|------|------|
| 菲律宾 | ph | shopee_ph_1 |
| 新加坡 | sg | shopee_sg_3c |
| 马来西亚 | my | shopee_my_1 |
| 泰国 | th | tiktok_th_main |
| 越南 | vn | shopee_vn_1 |
| 印尼 | id | shopee_id_1 |
| 巴西 | br | shopee_br_1 |

### 店铺标识建议
| 原始名称 | 建议标识 | 标准ID示例 |
|----------|----------|------------|
| 菲律宾1店 | 1 | shopee_ph_1 |
| 菲律宾2店 | 2 | shopee_ph_2 |
| 3C店 | 3c | shopee_sg_3c |
| 5店玩具 | toys | shopee_sg_toys |
| 旗舰店 | flagship | shopee_ph_flagship |
| 母婴店 | baby | shopee_sg_baby |

---

## 🔧 维护操作

### 查看当前覆盖率
```bash
curl http://localhost:8001/api/account-alignment/stats
```

**返回示例**：
```json
{
  "success": true,
  "stats": {
    "total_orders": 1000,
    "aligned": 800,
    "unaligned": 200,
    "coverage_rate": 80.0,
    "unique_raw_labels": 15
  }
}
```

### 查看缺失的映射
```bash
curl http://localhost:8001/api/account-alignment/suggestions?min_orders=5
```

**返回示例**：
```json
{
  "success": true,
  "suggestions": [
    {
      "account": "虾皮巴西_东朗照明主体",
      "site": "菲律宾",
      "store_label_raw": "菲律宾4店",
      "order_count": 50,
      "suggested_target_id": "shopee_ph_4"
    }
  ]
}
```

### 批量添加映射
```bash
curl -X POST http://localhost:8001/api/account-alignment/batch-add-aliases \
  -H "Content-Type: application/json" \
  -d '{
    "mappings": [
      {
        "account": "虾皮巴西_东朗照明主体",
        "site": "菲律宾",
        "store_label_raw": "菲律宾4店",
        "target_id": "shopee_ph_4"
      }
    ]
  }'
```

### 重新执行对齐
```bash
# 方式1：命令行
python scripts/backfill_account_alignment.py

# 方式2：API
curl -X POST http://localhost:8001/api/account-alignment/backfill
```

---

## ⚠️ 注意事项

### 1. 唯一性约束
- 同一个`(账号, 站点, 店铺名)`组合只能映射到一个标准ID
- 修改映射时，直接改target_id即可
- 系统会自动使用最新的配置

### 2. 生效时机
- **YAML文件修改后**：需重启后端服务
- **通过API添加**：立即生效（写入数据库）
- **数据对齐**：需手动触发回填脚本

### 3. 映射冲突处理
**场景**：同一个店铺名在不同账号/站点有不同含义

**正确做法**（精确匹配）：
```yaml
shop_aliases:
  # 账号A的"1店"
  'miaoshou:虾皮账号A:菲律宾:菲律宾1店': 'shopee_a_ph_1'
  
  # 账号B的"1店"
  'miaoshou:虾皮账号B:菲律宾:菲律宾1店': 'shopee_b_ph_1'
```

**错误做法**（会产生歧义）：
```yaml
shop_aliases:
  'miaoshou:::菲律宾1店': 'shopee_ph_1'  # ❌ 无法区分是哪个账号的1店
```

### 4. 特殊字符
- **冒号(:)**：用于分隔字段，店铺名中不能有冒号
- **引号('')**：整个key必须用单引号包裹
- **空值('')**：表示待填充，系统会跳过

---

## 📊 质量监控

### 覆盖率指标
```
覆盖率 = (已对齐订单数 / 总订单数) × 100%

建议目标：
- 初期：≥ 50%
- 中期：≥ 80%
- 长期：≥ 95%
```

### 未对齐数据监控
```sql
-- 查询未对齐的订单
SELECT 
    account,
    site,
    store_label_raw,
    COUNT(*) as order_count,
    SUM(total_amount_rmb) as total_gmv
FROM fact_orders
WHERE platform_code = 'miaoshou'
  AND shop_id = 'none'
  AND aligned_account_id IS NULL
GROUP BY account, site, store_label_raw
ORDER BY order_count DESC
```

---

## 🚀 快速上手

### 1分钟快速配置

#### Step 1：自动生成模板
```bash
python scripts/miaoshou_shop_alias_builder.py
```

#### Step 2：编辑 shop_aliases.yaml
打开文件，找到空值行，填入标准ID：
```yaml
# 修改前
'miaoshou:::菲律宾1店': ''

# 修改后
'miaoshou:::菲律宾1店': 'shopee_ph_1'
```

#### Step 3：执行对齐
```bash
python scripts/backfill_account_alignment.py
```

#### Step 4：验证结果
```bash
curl http://localhost:8001/api/account-alignment/stats
```

---

## 🎓 最佳实践

### 1. 命名规范
✅ **推荐**：
- `shopee_ph_1` - 清晰、简洁
- `shopee_sg_3c` - 含义明确
- `tiktok_th_main` - 易于理解

❌ **不推荐**：
- `shop1` - 不知道哪个平台
- `菲律宾店` - 中文在某些系统可能有编码问题
- `xyz123` - 无业务含义

### 2. 分组管理
```yaml
shop_aliases:
  # ==================== 虾皮巴西账号 ====================
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾1店': 'shopee_ph_1'
  'miaoshou:虾皮巴西_东朗照明主体:新加坡:3C店': 'shopee_sg_3c'
  
  # ==================== 虾皮新加坡账号 ====================
  'miaoshou:虾皮新加坡账号:新加坡:主店': 'shopee_sg_main'
```

### 3. 添加注释
```yaml
shop_aliases:
  # 菲律宾主力店铺（月GMV最高）
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾1店': 'shopee_ph_1'
  
  # 新加坡3C品类店（2024年新开）
  'miaoshou:虾皮巴西_东朗照明主体:新加坡:3C店': 'shopee_sg_3c'
```

### 4. 版本控制
- 建议将 `shop_aliases.yaml` 纳入Git版本控制
- 每次修改提交commit，记录变更原因
- 便于回溯和团队协作

---

## 🔄 工作流示例

### 场景：新增一个店铺

#### 发现未对齐数据
```bash
# 查看缺失映射建议
curl http://localhost:8001/api/account-alignment/suggestions?min_orders=1
```

**API返回**：
```json
{
  "store_label_raw": "菲律宾5店",
  "account": "虾皮巴西_东朗照明主体",
  "site": "菲律宾",
  "order_count": 120,
  "suggested_target_id": "shopee_ph_5"
}
```

#### 添加映射
**方式1：编辑YAML**
```yaml
shop_aliases:
  'miaoshou:虾皮巴西_东朗照明主体:菲律宾:菲律宾5店': 'shopee_ph_5'
```

**方式2：调用API**
```bash
curl -X POST http://localhost:8001/api/account-alignment/add-alias \
  -d '{"account":"虾皮巴西_东朗照明主体","site":"菲律宾","store_label_raw":"菲律宾5店","target_id":"shopee_ph_5"}'
```

#### 执行回填
```bash
python scripts/backfill_account_alignment.py
```

#### 验证结果
```bash
# 查看覆盖率（应该提升）
curl http://localhost:8001/api/account-alignment/stats
```

---

## 🐛 常见问题

### Q1: 修改YAML后没有生效？
**A**: 需要重启后端服务或重新加载缓存
```bash
# 重启服务
python run.py

# 或触发回填（会重新加载）
python scripts/backfill_account_alignment.py
```

### Q2: 一个店铺名应该映射到哪个ID？
**A**: 参考API建议
```bash
curl http://localhost:8001/api/account-alignment/suggestions?min_orders=1
```
系统会给出建议的`suggested_target_id`，你可以采纳或自定义。

### Q3: 映射错了怎么改？
**A**: 直接修改YAML中的target_id，重新执行回填即可
```yaml
# 修改前
'miaoshou:::菲律宾1店': 'shopee_ph_1'

# 修改后
'miaoshou:::菲律宾1店': 'shopee_ph_main'  # 改名
```

### Q4: 能否批量导入Excel？
**A**: 可以，准备CSV格式：
```csv
account,site,store_label_raw,target_id,notes
虾皮巴西_东朗照明主体,菲律宾,菲律宾1店,shopee_ph_1,主力店
虾皮巴西_东朗照明主体,新加坡,3C店,shopee_sg_3c,3C品类
```

然后调用批量API或编写导入脚本。

### Q5: 如何验证配置正确性？
**A**: 执行回填后查看日志
```bash
python scripts/backfill_account_alignment.py

# 查看输出：
# [OK] 对齐成功: 800/1000 (80%)
# [WARN] 未对齐: 200/1000 (20%)
# [建议] 缺失映射: 菲律宾7店, 新加坡旗舰店...
```

---

## 📚 相关文件

### 配置文件
- `config/shop_aliases.yaml` - YAML格式别名表（本文件）

### 数据库表
- `account_aliases` - 持久化的别名映射表

### 服务代码
- `modules/services/account_alignment.py` - 对齐服务
- `backend/routers/account_alignment.py` - API端点

### 脚本工具
- `scripts/miaoshou_shop_alias_builder.py` - 自动生成模板
- `scripts/backfill_account_alignment.py` - 执行对齐回填
- `scripts/test_account_alignment_system.py` - 系统测试

---

## 🎉 总结

`shop_aliases.yaml` 是妙手订单账号对齐的核心配置文件：

1. **作用**：将口语化店铺名映射到标准账号ID
2. **格式**：`'miaoshou:<账号>:<站点>:<店铺名>': '<标准ID>'`
3. **使用**：自动生成模板 → 填入标准ID → 执行回填
4. **效果**：实现账号级销售数据统一归并

**你只需要**：
1. 运行`miaoshou_shop_alias_builder.py`生成模板
2. 填入右侧的标准账号ID（参考建议）
3. 执行`backfill_account_alignment.py`
4. 查看统计确认覆盖率

就这么简单！🚀

