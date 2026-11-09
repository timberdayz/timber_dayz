from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import inspect, text

from backend.services.cloud_b_class_sync_utils import quote_ident, validate_b_class_table_name
from modules.core.fact_identity_columns import FACT_SHOP_ID_COLUMN_SEMANTICS
from modules.core.logger import get_logger


logger = get_logger(__name__)


CANONICAL_COLUMNS: tuple[str, ...] = (
    "platform_code",
    "shop_id",
    "data_domain",
    "granularity",
    "sub_domain",
    "metric_date",
    "period_start_date",
    "period_end_date",
    "period_start_time",
    "period_end_time",
    "file_id",
    "template_id",
    "data_hash",
    "ingest_timestamp",
    "currency_code",
    "raw_data",
    "header_columns",
)

NON_SERVICES_CONFLICT_KEY: tuple[str, ...] = (
    "platform_code",
    "shop_id",
    "data_domain",
    "granularity",
    "data_hash",
)

SERVICES_CONFLICT_KEY: tuple[str, ...] = (
    "data_domain",
    "sub_domain",
    "granularity",
    "data_hash",
)


def build_canonical_columns() -> tuple[str, ...]:
    return CANONICAL_COLUMNS


def get_conflict_key_columns(data_domain: str) -> tuple[str, ...]:
    return SERVICES_CONFLICT_KEY if data_domain == "services" else NON_SERVICES_CONFLICT_KEY


class CloudBClassMirrorManager:
    """Ensure the remote canonical raw tables exist and have the required key contract."""

    def __init__(self, engine, schema_name: str = "b_class") -> None:
        self.engine = engine
        self.schema_name = schema_name

    def ensure_cloud_schema_exists(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(self.schema_name)}"))

    def ensure_cloud_mirror_table(self, table_name: str, data_domain: str) -> None:
        validate_b_class_table_name(table_name)
        self.ensure_cloud_schema_exists()

        inspector = inspect(self.engine)
        if inspector.has_table(table_name, schema=self.schema_name):
            self._validate_existing_table_contract(inspector, table_name)
            self._ensure_conflict_index(table_name, data_domain)
            self._ensure_shop_id_column_comment(table_name)
            return

        columns_sql = ",\n".join(self._column_definitions())
        full_table_name = f"{quote_ident(self.schema_name)}.{quote_ident(table_name)}"
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {full_table_name} (\n{columns_sql}\n)"

        with self.engine.begin() as conn:
            conn.execute(text(create_table_sql))
        self._ensure_conflict_index(table_name, data_domain)
        self._ensure_shop_id_column_comment(table_name)

    def _ensure_shop_id_column_comment(self, table_name: str) -> None:
        """给 ``shop_id`` 列挂上语义注释(幂等)。

        ⚠️ 这一列**不是身份列** —— 它装的是采集层写进来的原始标识
        (shopee 上是平台店铺编号 / tiktok 上是导出店名 /
        miaoshou 采集链上是采集方代号 ``xihong``)。

        2026-11-07 上线的同步侧拦截器把它当身份列用, 误杀 3,714 行正常数据。
        权威定义见 ``modules/core/fact_identity_columns.py``。

        ⚠️ 注释**只是文档**, 失败不该阻断同步 —— 挂不上注释只是少了句说明,
        不该让整条同步链挂掉(比如老表上这一列被人工删过)。
        """
        full_table_name = f"{quote_ident(self.schema_name)}.{quote_ident(table_name)}"
        comment_sql = (
            f'COMMENT ON COLUMN {full_table_name}."shop_id" IS :comment'
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(comment_sql),
                    {"comment": FACT_SHOP_ID_COLUMN_SEMANTICS},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[CloudMirror] %s.shop_id 语义注释挂载失败(不影响同步): %s",
                table_name,
                exc,
            )

    def _column_definitions(self) -> Sequence[str]:
        return (
            '"platform_code" VARCHAR(32)',
            # ⚠️ 这一列**不是身份列** —— 见 modules/core/fact_identity_columns.py
            # (SSOT 权威定义)。它装的是采集层写进来的原始标识:
            # shopee 上是平台店铺编号、tiktok 上是导出店名、
            # miaoshou 采集链上是采集方代号 xihong。
            # 身份由 raw_data 内的稳定锚点决定, 规范键由语义层输出。
            '"shop_id" VARCHAR(100)',
            '"data_domain" VARCHAR(100) NOT NULL',
            '"granularity" VARCHAR(50) NOT NULL',
            '"sub_domain" VARCHAR(100)',
            '"metric_date" DATE',
            '"period_start_date" DATE',
            '"period_end_date" DATE',
            '"period_start_time" TIMESTAMP WITH TIME ZONE',
            '"period_end_time" TIMESTAMP WITH TIME ZONE',
            '"file_id" INTEGER',
            '"template_id" INTEGER',
            '"data_hash" VARCHAR(255) NOT NULL',
            '"ingest_timestamp" TIMESTAMP WITH TIME ZONE',
            '"currency_code" VARCHAR(16)',
            '"raw_data" JSONB NOT NULL',
            '"header_columns" JSONB',
        )

    def _build_conflict_index_sql(self, table_name: str, data_domain: str) -> str:
        index_name = f"uq_{table_name}_canonical"
        full_table_name = f"{quote_ident(self.schema_name)}.{quote_ident(table_name)}"
        quoted_index_name = quote_ident(index_name)

        if data_domain == "services":
            return (
                f"CREATE UNIQUE INDEX IF NOT EXISTS {quoted_index_name} "
                f"ON {full_table_name} (data_domain, sub_domain, granularity, data_hash)"
            )

        return (
            f"CREATE UNIQUE INDEX IF NOT EXISTS {quoted_index_name} "
            f"ON {full_table_name} (platform_code, shop_id, data_domain, granularity, data_hash)"
        )

    def _validate_existing_table_contract(self, inspector, table_name: str) -> None:
        actual_columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema=self.schema_name)
        }
        expected_columns = {
            definition.split('"')[1]
            for definition in self._column_definitions()
        }
        missing_columns = sorted(expected_columns - actual_columns)
        if missing_columns:
            raise RuntimeError(
                f"remote table {self.schema_name}.{table_name} missing canonical columns: {', '.join(missing_columns)}"
            )

    def _ensure_conflict_index(self, table_name: str, data_domain: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(self._build_conflict_index_sql(table_name, data_domain)))
