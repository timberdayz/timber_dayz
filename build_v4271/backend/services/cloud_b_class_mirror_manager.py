from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import inspect, text

from backend.services.cloud_b_class_sync_utils import quote_ident, validate_b_class_table_name


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
    """Manage remote canonical mirror schema and tables."""

    def __init__(self, engine, schema_name: str = "cloud_b_class") -> None:
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
            return

        columns_sql = ",\n".join(self._column_definitions())
        full_table_name = f"{quote_ident(self.schema_name)}.{quote_ident(table_name)}"
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {full_table_name} (\n{columns_sql}\n)"

        with self.engine.begin() as conn:
            conn.execute(text(create_table_sql))
            conn.execute(text(self._build_conflict_index_sql(table_name, data_domain)))

    def _column_definitions(self) -> Sequence[str]:
        return (
            '"platform_code" VARCHAR(32)',
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
