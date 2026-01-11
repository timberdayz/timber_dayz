# 整合迁移文件创建计划

**日期**: 2026-01-11  
**状态**: ⏳ 计划已制定，待执行

---

## 一、任务总结

### 1.1 已完成的工作

1. ✅ **遗留表清理计划已确认**
   - 文档：`docs/LEGACY_TABLES_CLEANUP_PLAN_FINAL.md`
   - 清理SQL：`sql/cleanup_legacy_tables.sql`
   - 8张public schema的表可以安全清理

2. ✅ **迁移需求已确认**
   - 文档：`docs/MIGRATION_REQUIREMENTS_SUMMARY.md`
   - 需要迁移的表：66张（schema.py中定义但迁移文件中未创建）
   - 不需要迁移的表：36张（动态创建的表26张 + 系统表2张 + 需要清理的遗留表8张）

### 1.2 待完成的工作

**创建整合迁移文件**：包含所有未迁移的表（66张表）

---

## 二、迁移文件创建方案

### 2.1 方案选择

由于66张表数量较多，有以下几种方案：

#### 方案1：使用Alembic autogenerate（推荐）

**优点**:
- ✅ 自动生成迁移文件
- ✅ 基于schema.py中的定义
- ✅ 包含所有索引和约束

**缺点**:
- ⚠️ 需要数据库已经是正确的状态（表已存在）
- ⚠️ 可能生成不完整的迁移（如果表结构不匹配）

**适用场景**: 如果数据库中的表已经存在（通过init_db()创建），可以使用autogenerate

#### 方案2：手动创建迁移文件

**优点**:
- ✅ 完全可控
- ✅ 可以精确控制表的创建顺序
- ✅ 可以使用IF NOT EXISTS模式

**缺点**:
- ❌ 工作量很大（66张表）
- ❌ 容易出错
- ❌ 需要参考schema.py中的定义

**适用场景**: 如果表不存在，或者需要精确控制表的创建

#### 方案3：分步创建迁移文件（推荐）

**优点**:
- ✅ 可以分功能域创建（如核心表、管理表、用户权限表等）
- ✅ 可以逐步验证
- ✅ 迁移文件更清晰

**缺点**:
- ⚠️ 需要多个迁移文件
- ⚠️ 需要正确设置down_revision

**适用场景**: 表数量较多时，分功能域创建更清晰

---

### 2.2 推荐方案

**推荐使用方案3：分步创建迁移文件**

**理由**:
1. 66张表数量较多，分功能域创建更清晰
2. 可以逐步验证，降低风险
3. 迁移文件更易维护

**分组方案**:

1. **核心维度表和事实表**（13张）
   - `dim_platforms`, `dim_shops`, `dim_products`, `dim_product_master`
   - `bridge_product_keys`, `dim_currency_rates`, `dim_exchange_rates`
   - `fact_orders`, `fact_order_items`, `fact_order_amounts`
   - `fact_product_metrics`, `fact_traffic`, `fact_service`, `fact_analytics`

2. **管理表**（20张）
   - `account_aliases`, `accounts`, `catalog_files`, `data_files`, `data_records`
   - `data_quarantine`, `collection_configs`, `collection_tasks`, `collection_task_logs`
   - `collection_sync_points`, `component_versions`, `component_test_history`
   - `platform_accounts`, `field_mappings`, `mapping_sessions`
   - `field_mapping_dictionary`, `field_mapping_templates`, `field_mapping_template_items`
   - `field_mapping_audit`, `field_usage_tracking`

3. **用户权限表**（4张）
   - `dim_users`, `dim_roles`, `user_sessions`, `user_approval_logs`

4. **暂存表**（4张）
   - `staging_orders`, `staging_product_metrics`, `staging_inventory`, `staging_raw_data`

5. **其他表**（25张）
   - `product_images`, `entity_aliases`
   - `sales_campaigns`, `sales_campaign_shops`, `sales_targets`, `target_breakdown`
   - `performance_config`, `performance_scores`, `shop_health_scores`, `shop_alerts`
   - `clearance_rankings`, `notifications`, `user_notification_preferences`
   - `dim_rate_limit_config`, `fact_rate_limit_config_audit`
   - `system_logs`, `security_config`, `backup_records`, `smtp_config`
   - `notification_templates`, `alert_rules`, `system_config`
   - `sync_progress_tasks`

---

## 三、迁移文件创建步骤

### 3.1 第一步：尝试使用Alembic autogenerate

如果数据库中的表已经存在（通过init_db()创建），可以尝试使用autogenerate：

```bash
# 设置环境变量（如果需要）
export PYTHONIOENCODING=utf-8

# 生成迁移文件
python -m alembic revision --autogenerate -m "complete_missing_tables_migration"
```

**注意**: 如果autogenerate失败（如编码问题），可以尝试方案3

### 3.2 第二步：如果autogenerate失败，使用方案3（分步创建）

#### 3.2.1 创建第一个迁移文件（核心维度表和事实表）

**文件**: `migrations/versions/20260111_0001_core_dimension_and_fact_tables.py`

**包含的表**: 13张核心维度表和事实表

**down_revision**: `20260111_merge_all_heads`

**特点**:
- 使用IF NOT EXISTS模式
- 包含所有必要的索引和约束
- 参考schema.py中的定义

#### 3.2.2 创建第二个迁移文件（管理表）

**文件**: `migrations/versions/20260111_0002_management_tables.py`

**包含的表**: 20张管理表

**down_revision**: `20260111_0001_core_dimension_and_fact_tables`

#### 3.2.3 创建第三个迁移文件（用户权限表）

**文件**: `migrations/versions/20260111_0003_user_permission_tables.py`

**包含的表**: 4张用户权限表

**down_revision**: `20260111_0002_management_tables`

#### 3.2.4 创建第四个迁移文件（暂存表）

**文件**: `migrations/versions/20260111_0004_staging_tables.py`

**包含的表**: 4张暂存表

**down_revision**: `20260111_0003_user_permission_tables`

#### 3.2.5 创建第五个迁移文件（其他表）

**文件**: `migrations/versions/20260111_0005_other_tables.py`

**包含的表**: 25张其他表

**down_revision**: `20260111_0004_staging_tables`

---

## 四、迁移文件模板

### 4.1 基本结构

```python
"""Complete missing tables migration

Revision ID: 20260111_0001_core_dimension_and_fact_tables
Revises: 20260111_merge_all_heads
Create Date: 2026-01-11

创建所有缺失的核心维度表和事实表（使用IF NOT EXISTS模式）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, JSON
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '20260111_0001_core_dimension_and_fact_tables'
down_revision = '20260111_merge_all_heads'
branch_labels = None
depends_on = None


def upgrade():
    """创建所有缺失的核心维度表和事实表"""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    print("[INFO] 开始创建核心维度表和事实表（仅创建不存在的表）...")
    created_count = 0
    
    # 1. 创建 dim_platforms 表（如果不存在）
    if 'dim_platforms' not in existing_tables:
        print("[1] 创建 dim_platforms 表...")
        op.create_table(
            'dim_platforms',
            sa.Column('platform_code', sa.String(length=32), primary_key=True),
            sa.Column('name', sa.String(length=64), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.UniqueConstraint('name', name='uq_dim_platforms_name'),
        )
        created_count += 1
        print("[OK] dim_platforms 表创建成功")
    else:
        print("[SKIP] dim_platforms 表已存在")
    
    # ... 更多表的创建 ...
    
    print(f"[OK] 核心维度表和事实表迁移完成: 创建 {created_count} 张新表")


def downgrade():
    """删除所有核心维度表和事实表（谨慎使用）"""
    # 注意：downgrade 只删除在本迁移中创建的表
    # 如果表在迁移前已存在，则不会删除
    
    tables_to_drop = [
        'dim_platforms',
        # ... 更多表 ...
    ]
    
    for table in tables_to_drop:
        try:
            op.drop_table(table)
            print(f"[OK] 删除表: {table}")
        except Exception as e:
            print(f"[SKIP] 表 {table} 不存在或无法删除: {e}")
```

### 4.2 使用IF NOT EXISTS模式

**关键点**:
- 使用 `if 'table_name' not in existing_tables` 检查表是否存在
- 仅创建不存在的表
- 不会覆盖已存在的表

---

## 五、实施建议

### 5.1 第一步：尝试autogenerate

1. 确保数据库中的表已经存在（通过init_db()创建）
2. 设置环境变量（如果需要）
3. 运行autogenerate命令
4. 检查生成的迁移文件
5. 如果生成的迁移文件不完整，手动补充

### 5.2 第二步：如果autogenerate失败，使用方案3

1. 创建第一个迁移文件（核心维度表和事实表）
2. 测试迁移文件（本地环境）
3. 逐步创建其他迁移文件
4. 每个迁移文件都测试验证
5. 所有迁移文件创建完成后，整合测试

### 5.3 第三步：验证和测试

1. 在本地环境执行所有迁移文件
2. 验证所有表都已创建
3. 验证表结构是否正确
4. 验证索引和约束是否正确
5. 在测试环境执行迁移
6. 在生产环境执行迁移（用户确认后）

---

## 六、相关文档

- [迁移需求总结](MIGRATION_REQUIREMENTS_SUMMARY.md) - 迁移需求详细说明
- [遗留表清理计划](LEGACY_TABLES_CLEANUP_PLAN_FINAL.md) - 清理计划
- [表审计总结报告](TABLE_AUDIT_SUMMARY.md) - 完整审计报告
