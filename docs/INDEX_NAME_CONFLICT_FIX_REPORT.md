# 索引名冲突修复报告

**日期**: 2026-01-12  
**问题**: PostgreSQL索引名冲突导致迁移失败  
**状态**: ✅ **已修复并验证通过**

---

## 一、问题分析

### 1.1 问题根源

PostgreSQL中索引名是**全局唯一的**，不能在不同表之间重复使用。但我们的schema中有多个表对（旧表 + A类新表）使用了相同的索引名。

### 1.2 为什么本地测试"没发现"

1. **本地测试环境差异**：
   - `validate_migrations_local.py` 每次都创建全新的数据库容器
   - 从空白数据库开始执行迁移
   - 第一个表创建索引成功，第二个表创建同名索引时失败

2. **错误误判**：
   - 我们误判为"幂等性问题"（认为索引已存在是因为表已存在）
   - 实际上是**索引名冲突问题**

3. **CI环境差异**：
   - CI环境可能使用持久化的数据库
   - 或者迁移被部分执行后重试
   - 索引名冲突更容易暴露

---

## 二、发现的索引名冲突

### 2.1 冲突列表

使用 `scripts/check_index_name_conflicts.py` 检查，发现以下冲突：

1. ✅ **`ix_performance_config_active`**
   - `performance_config` 表使用
   - `performance_config_a` 表也使用
   - **修复**: 改为 `ix_performance_config_a_active`

2. ✅ **`ix_sales_campaigns_status`**
   - `sales_campaigns` 表使用
   - `sales_campaigns_a` 表也使用
   - **修复**: 改为 `ix_sales_campaigns_a_status`

3. ✅ **`ix_sales_campaigns_type`**
   - `sales_campaigns` 表使用
   - `sales_campaigns_a` 表也使用
   - **修复**: 改为 `ix_sales_campaigns_a_type`

---

## 三、修复详情

### 3.1 修复的文件

1. **`modules/core/db/schema.py`**
   - `PerformanceConfigA` 类：索引名改为 `ix_performance_config_a_active`
   - `SalesCampaignA` 类：索引名改为 `ix_sales_campaigns_a_status` 和 `ix_sales_campaigns_a_type`

2. **`migrations/versions/20260112_v5_0_0_schema_snapshot.py`**
   - `performance_config_a` 表创建：索引名改为 `ix_performance_config_a_active`
   - `sales_campaigns_a` 表创建：索引名改为 `ix_sales_campaigns_a_status` 和 `ix_sales_campaigns_a_type`

### 3.2 修复原则

对于A类数据表（替代旧表的表），索引名应该包含表名后缀，例如：
- `ix_performance_config_active` → `ix_performance_config_a_active`
- `ix_sales_campaigns_status` → `ix_sales_campaigns_a_status`
- `ix_sales_campaigns_type` → `ix_sales_campaigns_a_type`

---

## 四、验证结果

### 4.1 索引名冲突检查

```bash
python scripts/check_index_name_conflicts.py
```

**结果**: ✅ 没有发现重复的索引名

### 4.2 本地CI测试

```bash
python scripts/test_ci_migrations_local.py
```

**结果**: ✅ 5/5项测试通过

### 4.3 Docker迁移测试

```bash
python scripts/validate_migrations_local.py
```

**结果**: ✅ **迁移执行成功**
- 成功创建 107 张表
- 所有关键表都存在（`dim_products`, `bridge_product_keys`, `fact_product_metrics`, `dim_product_master`）
- 没有索引名冲突错误

---

## 五、新增工具

### 5.1 `scripts/check_index_name_conflicts.py`

新增索引名冲突检查脚本，用于：
- 检查迁移脚本中的索引名是否重复
- 在CI/CD流程中集成，防止未来再次出现冲突

**使用方法**:
```bash
python scripts/check_index_name_conflicts.py
```

**输出示例**:
```
[ERROR] 发现 2 个重复的索引名:

  索引名: ix_sales_campaigns_status (出现 2 次)
    - 表: sales_campaigns
    - 表: sales_campaigns_a

  索引名: ix_sales_campaigns_type (出现 2 次)
    - 表: sales_campaigns
    - 表: sales_campaigns_a
```

---

## 六、经验总结

### 6.1 问题识别

1. **不要误判错误类型**：
   - `DuplicateTable` 错误可能是索引名冲突，不一定是表已存在
   - 需要仔细分析错误信息中的对象类型（表 vs 索引）

2. **测试环境差异**：
   - 本地测试使用全新数据库，可能隐藏某些问题
   - CI环境使用持久化数据库，更容易暴露问题

### 6.2 预防措施

1. **索引命名规范**：
   - 对于替代旧表的A类数据表，索引名应该包含表名后缀（如 `_a`）
   - 索引名格式：`ix_{table_name}_{column_name}`

2. **自动化检查**：
   - 使用 `scripts/check_index_name_conflicts.py` 在CI/CD中检查
   - 在生成迁移脚本时自动检查索引名冲突

3. **代码审查**：
   - 审查schema.py中的索引定义，确保索引名唯一
   - 审查迁移脚本生成逻辑

---

## 七、后续建议

1. **CI/CD集成**：
   - 在 `.github/workflows/deploy-production.yml` 中添加索引名冲突检查
   - 在迁移脚本验证步骤中运行 `scripts/check_index_name_conflicts.py`

2. **生成脚本改进**：
   - 在 `scripts/generate_schema_snapshot.py` 中添加索引名冲突检查
   - 自动检测并警告重复的索引名

3. **文档更新**：
   - 更新开发规范，明确索引命名规则
   - 在架构文档中说明索引名唯一性要求

---

**最后更新**: 2026-01-12  
**状态**: ✅ 所有索引名冲突已修复，迁移测试通过
