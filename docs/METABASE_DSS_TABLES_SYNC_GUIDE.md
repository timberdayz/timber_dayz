# Metabase DSS架构表同步指南

## 概述

本文档说明如何将DSS架构重构后的新表同步到Metabase。

## 需要同步的表

### B类数据表（16张表）

**订单数据域**：
- `fact_raw_data_orders_daily`
- `fact_raw_data_orders_weekly`
- `fact_raw_data_orders_monthly`

**产品数据域**：
- `fact_raw_data_products_daily`
- `fact_raw_data_products_weekly`
- `fact_raw_data_products_monthly`

**流量数据域**：
- `fact_raw_data_traffic_daily`
- `fact_raw_data_traffic_weekly`
- `fact_raw_data_traffic_monthly`

**服务数据域**：
- `fact_raw_data_services_daily`
- `fact_raw_data_services_weekly`
- `fact_raw_data_services_monthly`

**库存数据域**：
- `fact_raw_data_inventory_snapshot`

### 统一对齐表（1张表）

- `entity_aliases`

### A类数据表（7张表，中文字段名）

- `sales_targets_a` - 销售目标
- `sales_campaigns_a` - 销售战役
- `operating_costs` - 运营成本
- `employees` - 员工档案
- `employee_targets` - 员工目标
- `attendance_records` - 考勤记录
- `performance_config_a` - 绩效权重配置

### C类数据表（4张表，中文字段名）

- `employee_performance` - 员工绩效
- `employee_commissions` - 员工提成
- `shop_commissions` - 店铺提成
- `performance_scores_c` - 店铺绩效

### 其他表（1张表）

- `staging_raw_data` - 临时数据表

## 同步方法

### 方法1：使用自动化脚本（推荐）

```bash
# 运行同步脚本
python scripts/sync_dss_tables_to_metabase.py
```

**注意**：如果遇到代理问题，脚本会自动禁用代理。

### 方法2：手动同步（如果脚本失败）

#### 步骤1：登录Metabase

1. 访问 http://localhost:3000
2. 使用管理员账号登录（默认：admin@xihong.com / admin）

#### 步骤2：同步数据库Schema

1. 点击左侧菜单 "Admin" → "Databases"
2. 找到 "xihong_erp" 数据库
3. 点击数据库名称进入详情页
4. 点击右上角 "Sync database schema now" 按钮
5. 等待同步完成（通常需要10-30秒）

#### 步骤3：验证表已同步

1. 在数据库详情页，点击 "Tables" 标签
2. 检查以下表是否已出现：
   - B类数据表（16张）
   - `entity_aliases`
   - A类数据表（7张）
   - C类数据表（4张）
   - `staging_raw_data`

#### 步骤4：验证中文字段名

1. 点击任意A类或C类数据表（如 `sales_targets_a`）
2. 查看字段列表，确认中文字段名正常显示：
   - `店铺ID`
   - `年月`
   - `目标销售额`
   - `目标订单数`
   - 等

## 验证清单

- [ ] B类数据表（16张）全部同步
- [ ] `entity_aliases` 表已同步
- [ ] A类数据表（7张）全部同步
- [ ] C类数据表（4张）全部同步
- [ ] `staging_raw_data` 表已同步
- [ ] A类数据表中文字段名正常显示
- [ ] C类数据表中文字段名正常显示

## 常见问题

### Q1: 表未出现在Metabase中

**解决方案**：
1. 确认数据库连接正常（测试连接）
2. 手动触发Schema同步
3. 检查表是否在PostgreSQL中确实存在

### Q2: 中文字段名显示为乱码

**解决方案**：
1. 确认PostgreSQL数据库编码为UTF-8
2. 确认Metabase连接使用UTF-8编码
3. 重新同步Schema

### Q3: 表同步后无法查询

**解决方案**：
1. 检查表权限（Metabase使用的数据库用户是否有SELECT权限）
2. 检查表是否有数据（空表可能无法创建Question）
3. 尝试手动执行SQL查询测试

## 下一步

同步完成后，可以：
1. 配置表关联（entity_aliases）
2. 创建自定义字段
3. 创建Dashboard

详见：`docs/METABASE_DASHBOARD_MANUAL_SETUP.md`

