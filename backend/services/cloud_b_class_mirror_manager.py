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
            return

        columns_sql = ",\n".join(self._column_definitions())
        full_table_name = f"{quote_ident(self.schema_name)}.{quote_ident(table_name)}"
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {full_table_name} (\n{columns_sql}\n)"

        with self.engine.begin() as conn:
            conn.execute(text(create_table_sql))
        self._ensure_conflict_index(table_name, data_domain)

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
