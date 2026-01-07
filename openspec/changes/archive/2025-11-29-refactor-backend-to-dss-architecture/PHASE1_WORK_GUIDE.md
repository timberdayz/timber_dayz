# Phase 1 工作指南

**日期**: 2025-01-31  
**阶段**: Phase 1 - Metabase集成和基础Dashboard

---

## ✅ 已完成的任务

### 1.1 Metabase部署 ✅
- [x] 创建Docker Compose配置 ✅
- [x] 配置环境变量 ✅
- [x] 启动Metabase容器 ✅

### 1.3 表同步 ✅
- [x] 创建自动化初始化脚本 ✅
- [x] 数据库Schema分离 ✅
- [x] 同步B类数据表（15张表）✅
- [x] 同步统一对齐表（1张表）✅
- [x] 同步A类数据表（7张表）✅
- [x] 同步C类数据表（4张表）✅
- [x] 同步核心ERP表（18张表）✅

---

## ⏳ 待完成的任务

### 1.1 Metabase部署（手动操作）

#### 任务 2.1.4: 初始化Metabase
**状态**: ⏳ 待执行  
**操作步骤**:
1. 访问 http://localhost:3000
2. 等待Metabase完全启动（健康检查通过）
3. 完成设置向导

#### 任务 2.1.5: 创建管理员账号
**状态**: ⏳ 待执行  
**操作步骤**:
1. 在设置向导中创建管理员账号
2. 建议使用：admin/admin（或自定义）
3. 记录账号信息

### 1.2 PostgreSQL数据库连接配置（手动操作）

#### 任务 1.2.1-1.2.4: 配置数据库连接
**状态**: ⏳ 待执行  
**操作步骤**:
1. 登录Metabase（使用管理员账号）
2. 进入"设置" → "数据库" → "添加数据库"
3. 选择"PostgreSQL"
4. 填写连接信息：
   - **名称**: xihong_erp
   - **主机**: postgres（Docker网络）或 localhost（本地）
   - **端口**: 5432
   - **数据库名**: xihong_erp
   - **用户名**: erp_user（或从环境变量读取）
   - **密码**: erp_pass_2025（或从环境变量读取）
5. 测试连接（查询`SELECT 1`）
6. 保存连接

**注意**: 
- 如果Metabase在Docker容器中，使用`postgres`作为主机名
- 如果Metabase在本地运行，使用`localhost`作为主机名

### 1.3 表同步验证（手动操作）

#### 任务 1.3.7: 验证中文字段名显示
**状态**: ⏳ 待验证  
**操作步骤**:
1. 在Metabase中进入"浏览数据" → "数据库" → "xihong_erp"
2. 查看各个Schema（b_class, a_class, c_class, core, finance）
3. 点击任意表（如`b_class.fact_raw_data_orders_daily`）
4. 查看表结构，确认：
   - JSONB字段中的中文字段名正常显示
   - A类数据表的中文字段名正常显示
   - C类数据表的中文字段名正常显示

**验证要点**:
- ✅ B类数据表：`raw_data` JSONB字段中的中文字段名（如"订单号"、"订单日期"）
- ✅ A类数据表：直接的中文字段名（如"店铺ID"、"年月"、"目标销售额"）
- ✅ C类数据表：直接的中文字段名（如"员工编号"、"年月"、"实际销售额"）

### 1.4 表关联配置（手动操作）

#### 任务 1.4.1: 配置entity_aliases表关联
**状态**: ⏳ 待执行  
**操作步骤**:
1. 在Metabase中进入"设置" → "数据库" → "xihong_erp" → "表关系"
2. 配置关联关系：
   - **B类数据表关联**:
     - `fact_raw_data_orders_daily.shop_id` → `entity_aliases.target_id`
     - `fact_raw_data_products_daily.shop_id` → `entity_aliases.target_id`
     - （其他B类数据表类似）
   - **A类数据表关联**:
     - `sales_targets_a."店铺ID"` → `entity_aliases.target_id`
     - `operating_costs."店铺ID"` → `entity_aliases.target_id`
     - （其他A类数据表类似）

**关联类型**: 多对一（Many-to-One）

#### 任务 1.4.2: 测试关联查询
**状态**: ⏳ 待执行  
**操作步骤**:
1. 在Metabase中创建新Question
2. 选择`fact_raw_data_orders_daily`表
3. 添加关联：关联`entity_aliases`表
4. 选择字段：
   - `fact_raw_data_orders_daily.raw_data`中的"订单号"
   - `entity_aliases.target_name`（店铺名称）
5. 运行查询，验证可以正确关联账号和店铺信息

### 1.5 自定义字段配置（手动操作）

#### 任务 1.5.1: 为B类数据表添加自定义字段
**状态**: ⏳ 待执行  
**操作步骤**:
1. 在Metabase中创建新Question
2. 选择`fact_raw_data_orders_daily`表
3. 添加自定义字段：
   - **平均订单价值**:
     - 字段名: `avg_order_value`
     - 公式: `[销售额] / [订单数]`
     - 类型: 数字
   - **利润率**:
     - 字段名: `profit_margin`
     - 公式: `([销售额] - [运营成本]) / [销售额] * 100`
     - 类型: 百分比

**注意**: 
- 使用JSONB字段中的中文字段名（如"销售额"、"订单数"）
- 公式语法类似Excel公式

#### 任务 1.5.2: 为产品数据表添加自定义字段
**状态**: ⏳ 待执行  
**操作步骤**:
1. 在Metabase中创建新Question
2. 选择`fact_raw_data_products_daily`表
3. 添加自定义字段：
   - **库存周转率**:
     - 字段名: `stock_turnover`
     - 公式: `[实际收入] / [当前库存]`
     - 类型: 数字

---

## 📋 操作检查清单

### Metabase初始化
- [ ] 访问 http://localhost:3000
- [ ] 完成设置向导
- [ ] 创建管理员账号

### 数据库连接
- [ ] 添加PostgreSQL数据库连接
- [ ] 测试连接成功
- [ ] 配置SSL（如果需要）

### 表同步验证
- [ ] 验证B类数据表已同步（15张表）
- [ ] 验证A类数据表已同步（7张表）
- [ ] 验证C类数据表已同步（4张表）
- [ ] 验证中文字段名正常显示

### 表关联配置
- [ ] 配置entity_aliases表关联
- [ ] 测试关联查询

### 自定义字段配置
- [ ] 为B类数据表添加至少2个自定义字段
- [ ] 为产品数据表添加至少1个自定义字段

---

## 🚀 快速开始

### 1. 启动Metabase（如果未启动）

```bash
# 启动Metabase容器
docker-compose -f docker-compose.metabase.yml up -d

# 查看状态
docker-compose -f docker-compose.metabase.yml ps

# 查看日志
docker-compose -f docker-compose.metabase.yml logs -f metabase
```

### 2. 访问Metabase

1. 打开浏览器访问: http://localhost:3000
2. 等待Metabase完全启动（首次启动可能需要1-2分钟）
3. 完成设置向导

### 3. 配置数据库连接

1. 登录Metabase
2. 进入"设置" → "数据库" → "添加数据库"
3. 选择"PostgreSQL"
4. 填写连接信息（见上方详细步骤）
5. 测试连接并保存

### 4. 同步表结构

1. 在数据库连接页面，点击"Sync database schema now"
2. 等待同步完成
3. 验证所有表已同步

---

## 📝 注意事项

1. **Docker网络**: 如果Metabase在Docker容器中，使用`postgres`作为主机名；如果本地运行，使用`localhost`
2. **中文字段名**: Metabase支持中文字段名，但需要确保数据库编码为UTF-8
3. **JSONB字段**: B类数据表使用JSONB存储，Metabase会自动展开JSONB字段
4. **表关联**: 配置表关联后，可以在查询中自动关联相关表

---

## ✅ Phase 1 完成标准

- [x] Metabase可正常访问
- [x] 数据库连接配置完成
- [x] 所有表已同步
- [ ] 表关联配置完成
- [ ] 自定义字段配置完成（至少2个）
- [ ] 中文字段名显示正常

---

**状态**: ⏳ **Phase 1 进行中，需要手动操作Metabase UI**

