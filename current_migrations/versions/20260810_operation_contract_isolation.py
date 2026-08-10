"""Repair operation-contract isolation for databases already at 20260808."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260810_operation_contract_isolation"
down_revision = "current_schema_20260808_operation_performance_workbench"
branch_labels = None
depends_on = None


def _columns(connection, table: str, schema: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(connection).get_columns(table, schema=schema)
    }


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

    # Older 20260808 deployments can contain real workbench targets and shop
    # overrides without a persisted contract version. Backfill only rows whose
    # parent unambiguously belongs to the current workbench; invalid or
    # conflicting data must be resolved manually instead of being guessed.
    connection.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM a_class.target_breakdown AS tb
                    JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                    WHERE st.target_type = 'operation'
                      AND st.metric_catalog_version IS NOT NULL
                      AND (
                          tb.breakdown_type IS DISTINCT FROM 'shop'
                          OR NULLIF(btrim(tb.platform_code), '') IS NULL
                          OR NULLIF(btrim(tb.shop_id), '') IS NULL
                          OR tb.period_start IS DISTINCT FROM st.period_start
                          OR tb.period_end IS DISTINCT FROM st.period_end
                          OR (
                              tb.operation_contract_version IS NOT NULL
                              AND tb.operation_contract_version IS DISTINCT FROM st.metric_catalog_version
                          )
                      )
                ) THEN
                    RAISE EXCEPTION
                        'current operation overrides cannot be safely backfilled; manual resolution is required';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM a_class.target_breakdown AS tb
                    JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                    WHERE st.target_type = 'operation'
                      AND st.metric_catalog_version IS NOT NULL
                      AND tb.breakdown_type = 'shop'
                    GROUP BY tb.target_id, tb.platform_code, tb.shop_id
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'duplicate current operation overrides cannot be safely backfilled';
                END IF;

                UPDATE a_class.target_breakdown AS tb
                SET operation_contract_version = st.metric_catalog_version
                FROM a_class.sales_targets AS st
                WHERE st.id = tb.target_id
                  AND st.target_type = 'operation'
                  AND st.metric_catalog_version IS NOT NULL
                  AND tb.operation_contract_version IS NULL;
            END;
            $$;
            """
        )
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
    connection.execute(
        sa.text("DROP INDEX IF EXISTS a_class.uq_operation_target_month_metric")
    )
    connection.execute(
        sa.text("DROP INDEX IF EXISTS a_class.uq_operation_shop_override")
    )

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
                IF TG_OP = 'DELETE' THEN
                    IF OLD.target_type = 'operation' AND OLD.metric_catalog_version IS NULL THEN
                        RAISE EXCEPTION 'historical operation targets are read-only';
                    END IF;
                    RETURN OLD;
                END IF;
                IF (TG_OP = 'UPDATE'
                    AND OLD.target_type = 'operation'
                    AND OLD.metric_catalog_version IS NULL)
                   OR (NEW.target_type = 'operation' AND NEW.metric_catalog_version IS NULL) THEN
                    RAISE EXCEPTION 'historical operation targets are read-only';
                END IF;
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
            BEFORE INSERT OR UPDATE OR DELETE ON a_class.sales_targets
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
                IF TG_OP = 'DELETE' THEN
                    SELECT * INTO parent_target FROM a_class.sales_targets WHERE id = OLD.target_id;
                ELSE
                    SELECT * INTO parent_target FROM a_class.sales_targets WHERE id = NEW.target_id;
                END IF;
                IF FOUND AND parent_target.target_type = 'operation' THEN
                    IF parent_target.metric_catalog_version IS NULL THEN
                        RAISE EXCEPTION 'historical operation breakdowns are read-only';
                    ELSE
                        IF TG_OP = 'DELETE' THEN
                            RETURN OLD;
                        END IF;
                        IF NEW.operation_contract_version IS NULL THEN
                            NEW.operation_contract_version := parent_target.metric_catalog_version;
                        END IF;
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
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_enforce_operation_breakdown_contract
            BEFORE INSERT OR UPDATE OR DELETE ON a_class.target_breakdown
            FOR EACH ROW EXECUTE FUNCTION a_class.enforce_operation_breakdown_contract();
            """
        )
    )


def downgrade() -> None:
    pass
