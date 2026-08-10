"""Repair operation-contract isolation for databases already at 20260808."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260810_operation_contract_isolation"
down_revision = "current_schema_20260808_operation_performance_workbench"
branch_labels = None
depends_on = None


def _columns(connection, table: str, schema: str) -> set[str]:
    return {item["name"] for item in sa.inspect(connection).get_columns(table, schema=schema)}


def upgrade() -> None:
    connection = op.get_bind()
    if "operation_contract_version" not in _columns(
        connection, "target_breakdown", "a_class"
    ):
        op.add_column(
            "target_breakdown",
            sa.Column("operation_contract_version", sa.Integer(), nullable=True),
            schema="a_class",
        )

    connection.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_enforce_operation_breakdown_contract "
            "ON a_class.target_breakdown"
        )
    )
    connection.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_enforce_operation_target_contract "
            "ON a_class.sales_targets"
        )
    )
    connection.execute(sa.text("DROP INDEX IF EXISTS a_class.uq_operation_target_month_metric"))
    connection.execute(sa.text("DROP INDEX IF EXISTS a_class.uq_operation_shop_override"))

    connection.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_operation_target_month_metric
            ON a_class.sales_targets (period_start, period_end, metric_code)
            WHERE target_type = 'operation'
              AND metric_catalog_version IS NOT NULL
              AND scope_type = 'shop'
              AND metric_code IS NOT NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_operation_shop_override
            ON a_class.target_breakdown
                (target_id, operation_contract_version, breakdown_type, platform_code, shop_id)
            WHERE breakdown_type = 'shop' AND operation_contract_version IS NOT NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION a_class.enforce_operation_target_contract()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.target_type = 'operation' AND NEW.metric_catalog_version IS NOT NULL THEN
                    IF NEW.scope_type IS DISTINCT FROM 'shop' THEN
                        RAISE EXCEPTION 'operation targets require scope_type=shop';
                    END IF;
                    IF NEW.period_start IS NULL OR NEW.period_end IS NULL
                       OR NEW.period_start <> date_trunc('month', NEW.period_start)::date
                       OR NEW.period_end <> (date_trunc('month', NEW.period_start) + interval '1 month - 1 day')::date THEN
                        RAISE EXCEPTION 'operation targets require a complete calendar month';
                    END IF;
                    IF NULLIF(btrim(NEW.metric_code), '') IS NULL
                       OR NEW.metric_direction IS NULL
                       OR NEW.metric_direction NOT IN ('higher_better', 'lower_better', 'manual_score') THEN
                        RAISE EXCEPTION 'operation targets require a metric code and valid direction';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_enforce_operation_target_contract
            BEFORE INSERT OR UPDATE ON a_class.sales_targets
            FOR EACH ROW EXECUTE FUNCTION a_class.enforce_operation_target_contract();
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION a_class.enforce_operation_breakdown_contract()
            RETURNS trigger AS $$
            DECLARE
                parent_target a_class.sales_targets%ROWTYPE;
            BEGIN
                SELECT * INTO parent_target FROM a_class.sales_targets WHERE id = NEW.target_id;
                IF FOUND AND parent_target.target_type = 'operation' THEN
                    IF parent_target.metric_catalog_version IS NULL THEN
                        IF NEW.operation_contract_version IS NOT NULL THEN
                            RAISE EXCEPTION 'historical operation breakdowns require a null contract version';
                        END IF;
                    ELSE
                        IF NEW.operation_contract_version
                           IS DISTINCT FROM parent_target.metric_catalog_version THEN
                            RAISE EXCEPTION 'operation breakdown contract version must match its parent target';
                        END IF;
                        IF NEW.breakdown_type IS DISTINCT FROM 'shop' THEN
                            RAISE EXCEPTION 'operation targets only allow shop breakdowns';
                        END IF;
                        IF NULLIF(btrim(NEW.platform_code), '') IS NULL
                           OR NULLIF(btrim(NEW.shop_id), '') IS NULL THEN
                            RAISE EXCEPTION 'operation shop breakdowns require platform_code and shop_id';
                        END IF;
                        IF NEW.period_start IS DISTINCT FROM parent_target.period_start
                           OR NEW.period_end IS DISTINCT FROM parent_target.period_end THEN
                            RAISE EXCEPTION 'operation shop breakdowns must use the parent calendar month';
                        END IF;
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_enforce_operation_breakdown_contract
            BEFORE INSERT OR UPDATE ON a_class.target_breakdown
            FOR EACH ROW EXECUTE FUNCTION a_class.enforce_operation_breakdown_contract();
            """
        )
    )


def downgrade() -> None:
    pass
