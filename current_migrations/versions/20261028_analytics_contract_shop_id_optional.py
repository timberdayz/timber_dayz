"""analytics(流量)语义契约: ``shop_id`` 由 required 降级为 optional。

为什么
----
TikTok 流量(analytics)导出的**表头里没有店铺列** —— 店铺归属来自
``catalog_files.shop_id``(采集元数据), 而不是文件表头。

之前把 ``shop_id`` 列为 required, 造成三个连锁问题:

1. 契约的 ``missing_required`` 恒为 ``['shop_id', 'visitor_count', 'page_views']``
2. 即使文件与模板 **100% 精确匹配**, 契约状态仍然是 ``breaking_drift``
   —— 实测 TikTok 月度流量模板 v6 + 完全一致的源文件, 依然报
   「业务概览无法按店铺归属流量 / UV无法计算 / PV无法计算」
3. 治理面板上出现与真实漂移无关的误导性提示, 掩盖真正的新增/删除字段

``visitor_count`` / ``page_views`` 的解析能力由**代码侧**补齐:
``backend/services/semantic_field_contract_service.py`` 新增了
``ANALYTICS_SEMANTIC_ALIASES``, 让语义键可以从中文表头推断出来, 不再
依赖模板里人工填写的 ``header_bindings``(实测该字段覆盖率极低)。

本迁移只处理**结构上根本无法从表头满足**的 ``shop_id``。

幂等: 只影响 ``data_domain='analytics'`` 且 ``semantic_key='shop_id'`` 的行。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261028_analytics_contract_shop_id_optional"
down_revision = "current_schema_20261025_sku_pricing_min_restock_days"
branch_labels = None
depends_on = None


TABLE = "semantic_field_contracts"
SCHEMA = "core"


def _table_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(TABLE, schema=SCHEMA)


def upgrade() -> None:
    if not _table_exists():
        return
    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
        SET importance = 'optional',
            impact_description = '业务概览无法按店铺归属流量',
            updated_at = now()
        WHERE data_domain = 'analytics'
          AND semantic_key = 'shop_id'
          AND importance = 'required'
        """
    )


def downgrade() -> None:
    if not _table_exists():
        return
    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
        SET importance = 'required',
            impact_description = '业务概览无法按店铺归属流量',
            updated_at = now()
        WHERE data_domain = 'analytics'
          AND semantic_key = 'shop_id'
          AND importance = 'optional'
        """
    )
