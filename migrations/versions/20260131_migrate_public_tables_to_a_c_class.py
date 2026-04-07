"""Migrate public.sales_targets, performance_scores, shop_health_scores, shop_alerts to a_class/c_class

Revision ID: 20260131_pub_to_ac
Revises: 20260130_user_id_emp
Create Date: 2026-01-31

add-performance-and-personal-income:
- public.sales_targets -> a_class.sales_targets (新建，迁移数据，删除原表)
- public.performance_scores -> c_class.performance_scores (合并 performance_scores_c 后删除)
- public.shop_health_scores -> c_class.shop_health_scores
- public.shop_alerts -> c_class.shop_alerts
"""

from alembic import op
from sqlalchemy import text


revision = '20260131_pub_to_ac'
down_revision = '20260130_user_id_emp'
branch_labels = None
depends_on = None


def safe_print(msg):
    """Windows GBK compatible print"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


def table_exists(conn, table_name: str, schema: str = 'public') -> bool:
    r = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :t
        )
    """), {"schema": schema, "t": table_name})
    return r.scalar() or False


def constraint_exists(conn, schema: str, table_name: str, constraint_name: str) -> bool:
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = :schema
              AND table_name = :table_name
              AND constraint_name = :constraint_name
        )
    """), {
        "schema": schema,
        "table_name": table_name,
        "constraint_name": constraint_name,
    })
    return result.scalar() or False


def upgrade():
    conn = op.get_bind()

    # Ensure schemas exist (self-contained; no dependency on migration order)
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS c_class"))

    # ========== Part 1: sales_targets (public -> a_class) ==========
    safe_print("[1/4] Migrating sales_targets to a_class...")

    if table_exists(conn, 'sales_targets', 'public'):
        # 1.1 Create a_class.sales_targets (same structure as public)
        if not table_exists(conn, 'sales_targets', 'a_class'):
            conn.execute(text("""
                CREATE TABLE a_class.sales_targets (
                    id SERIAL PRIMARY KEY,
                    target_name VARCHAR(200) NOT NULL DEFAULT '',
                    target_type VARCHAR(32) NOT NULL DEFAULT 'shop',
                    period_start DATE NOT NULL DEFAULT '1970-01-01',
                    period_end DATE NOT NULL DEFAULT '1970-01-01',
                    target_amount NUMERIC NOT NULL DEFAULT 0,
                    target_quantity INTEGER NOT NULL DEFAULT 0,
                    achieved_amount NUMERIC NOT NULL DEFAULT 0,
                    achieved_quantity INTEGER NOT NULL DEFAULT 0,
                    achievement_rate NUMERIC NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL DEFAULT 'active',
                    description TEXT,
                    weekday_ratios JSONB,
                    created_by VARCHAR(64),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT chk_target_dates CHECK (period_end >= period_start),
                    CONSTRAINT chk_target_amount CHECK (target_amount >= 0),
                    CONSTRAINT chk_target_quantity CHECK (target_quantity >= 0)
                )
            """))
            safe_print("  [OK] Created a_class.sales_targets")

        # 1.2 Copy data (preserve id for target_breakdown FK)
        r = conn.execute(text("SELECT COUNT(*) FROM public.sales_targets"))
        cnt = r.scalar() or 0
        if cnt > 0:
            conn.execute(text("""
                INSERT INTO a_class.sales_targets
                (id, target_name, target_type, period_start, period_end, target_amount, target_quantity,
                 achieved_amount, achieved_quantity, achievement_rate, status, description, weekday_ratios,
                 created_by, created_at, updated_at)
                SELECT id, target_name, target_type, period_start, period_end, target_amount, target_quantity,
                       achieved_amount, achieved_quantity, achievement_rate, status, description, weekday_ratios,
                       created_by, created_at, updated_at
                FROM public.sales_targets
            """))
            conn.execute(text("SELECT setval(pg_get_serial_sequence('a_class.sales_targets', 'id'), COALESCE((SELECT MAX(id) FROM a_class.sales_targets), 1))"))
            safe_print(f"  [OK] Migrated {cnt} rows to a_class.sales_targets")

        if table_exists(conn, 'sales_targets', 'a_class') and not constraint_exists(conn, 'a_class', 'sales_targets', 'sales_targets_pkey'):
            conn.execute(text("""
                ALTER TABLE a_class.sales_targets
                ADD CONSTRAINT sales_targets_pkey PRIMARY KEY (id)
            """))
            safe_print("  [OK] Added sales_targets_pkey on a_class.sales_targets(id)")

        # 1.3 Drop target_breakdown FK to public.sales_targets
        if table_exists(conn, 'target_breakdown', 'a_class'):
            fk_result = conn.execute(text("""
                SELECT tc.constraint_name FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = 'a_class' AND tc.table_name = 'target_breakdown'
                  AND tc.constraint_type = 'FOREIGN KEY' AND kcu.column_name = 'target_id'
            """))
            fk_row = fk_result.fetchone()
            if fk_row:
                fk_name = fk_row[0]
                conn.execute(text(f'ALTER TABLE a_class.target_breakdown DROP CONSTRAINT IF EXISTS "{fk_name}"'))
                safe_print(f"  [OK] Dropped FK {fk_name}")

        # 1.4 Add new FK: target_breakdown.target_id -> a_class.sales_targets.id
        if (
            table_exists(conn, 'target_breakdown', 'a_class')
            and table_exists(conn, 'sales_targets', 'a_class')
            and not constraint_exists(conn, 'a_class', 'target_breakdown', 'fk_target_breakdown_sales_targets')
        ):
            conn.execute(text("""
                ALTER TABLE a_class.target_breakdown
                ADD CONSTRAINT fk_target_breakdown_sales_targets
                FOREIGN KEY (target_id) REFERENCES a_class.sales_targets(id) ON DELETE CASCADE
            """))
            safe_print("  [OK] Added FK target_breakdown -> a_class.sales_targets")

        # 1.5 Drop public.sales_targets
        conn.execute(text("DROP TABLE IF EXISTS public.sales_targets CASCADE"))
        safe_print("  [OK] Dropped public.sales_targets")
    else:
        safe_print("  [SKIP] public.sales_targets not found")

    # ========== Part 2: performance_scores (public -> c_class) ==========
    safe_print("[2/4] Migrating performance_scores to c_class...")

    if table_exists(conn, 'performance_scores', 'public'):
        if not table_exists(conn, 'performance_scores', 'c_class'):
            conn.execute(text("""
                CREATE TABLE c_class.performance_scores (
                    id SERIAL PRIMARY KEY,
                    platform_code VARCHAR(32) NOT NULL,
                    shop_id VARCHAR(64) NOT NULL,
                    period VARCHAR(16) NOT NULL,
                    total_score FLOAT NOT NULL DEFAULT 0,
                    sales_score FLOAT NOT NULL DEFAULT 0,
                    profit_score FLOAT NOT NULL DEFAULT 0,
                    key_product_score FLOAT NOT NULL DEFAULT 0,
                    operation_score FLOAT NOT NULL DEFAULT 0,
                    score_details JSONB,
                    rank INTEGER,
                    performance_coefficient FLOAT NOT NULL DEFAULT 1.0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_performance_shop_period UNIQUE (platform_code, shop_id, period),
                    CONSTRAINT fk_performance_shop FOREIGN KEY (platform_code, shop_id)
                        REFERENCES dim_shops(platform_code, shop_id),
                    CONSTRAINT chk_total_score CHECK (total_score >= 0 AND total_score <= 100)
                )
            """))
            safe_print("  [OK] Created c_class.performance_scores")

        conn.execute(text("""
            INSERT INTO c_class.performance_scores
            (platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score,
             operation_score, score_details, rank, performance_coefficient, created_at, updated_at)
            SELECT platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score,
                   operation_score, score_details, rank, performance_coefficient, created_at, updated_at
            FROM public.performance_scores
            ON CONFLICT (platform_code, shop_id, period) DO NOTHING
        """))
        safe_print("  [OK] Migrated public.performance_scores")

        # Merge performance_scores_c if exists (quality_score -> operation_score, platform_code from dim_shops)
        if table_exists(conn, 'performance_scores_c', 'c_class'):
            conn.execute(text("""
                INSERT INTO c_class.performance_scores
                (platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score,
                 operation_score, rank, performance_coefficient, created_at, updated_at)
                SELECT COALESCE((SELECT platform_code FROM dim_shops WHERE shop_id = pc.shop_id LIMIT 1), 'unknown'),
                       pc.shop_id, pc.period, pc.total_score, pc.sales_score, 0, 0, pc.quality_score,
                       NULL, 1.0, COALESCE(pc.calculated_at, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP
                FROM c_class.performance_scores_c pc
                WHERE NOT EXISTS (
                    SELECT 1 FROM c_class.performance_scores ps
                    WHERE ps.shop_id = pc.shop_id AND ps.period = pc.period
                )
                ON CONFLICT (platform_code, shop_id, period) DO NOTHING
            """))
            conn.execute(text("DROP TABLE IF EXISTS c_class.performance_scores_c CASCADE"))
            safe_print("  [OK] Merged performance_scores_c and dropped")

        conn.execute(text("DROP TABLE IF EXISTS public.performance_scores CASCADE"))
        safe_print("  [OK] Dropped public.performance_scores")
    else:
        safe_print("  [SKIP] public.performance_scores not found")

    # ========== Part 3: shop_health_scores (public -> c_class) ==========
    safe_print("[3/4] Migrating shop_health_scores to c_class...")

    if table_exists(conn, 'shop_health_scores', 'public'):
        if not table_exists(conn, 'shop_health_scores', 'c_class'):
            conn.execute(text("""
                CREATE TABLE c_class.shop_health_scores (
                    id SERIAL PRIMARY KEY,
                    platform_code VARCHAR(32) NOT NULL,
                    shop_id VARCHAR(64) NOT NULL,
                    metric_date DATE NOT NULL,
                    granularity VARCHAR(16) NOT NULL DEFAULT 'daily',
                    health_score FLOAT NOT NULL DEFAULT 0,
                    gmv_score FLOAT NOT NULL DEFAULT 0,
                    conversion_score FLOAT NOT NULL DEFAULT 0,
                    inventory_score FLOAT NOT NULL DEFAULT 0,
                    service_score FLOAT NOT NULL DEFAULT 0,
                    gmv FLOAT NOT NULL DEFAULT 0,
                    conversion_rate FLOAT NOT NULL DEFAULT 0,
                    inventory_turnover FLOAT NOT NULL DEFAULT 0,
                    customer_satisfaction FLOAT NOT NULL DEFAULT 0,
                    risk_level VARCHAR(16) NOT NULL DEFAULT 'low',
                    risk_factors JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_shop_health UNIQUE (platform_code, shop_id, metric_date, granularity),
                    CONSTRAINT fk_shop_health FOREIGN KEY (platform_code, shop_id)
                        REFERENCES dim_shops(platform_code, shop_id),
                    CONSTRAINT chk_health_score CHECK (health_score >= 0 AND health_score <= 100),
                    CONSTRAINT chk_risk_level CHECK (risk_level IN ('low', 'medium', 'high'))
                )
            """))
            safe_print("  [OK] Created c_class.shop_health_scores")

        conn.execute(text("""
            INSERT INTO c_class.shop_health_scores
            SELECT * FROM public.shop_health_scores
            ON CONFLICT (platform_code, shop_id, metric_date, granularity) DO NOTHING
        """))
        conn.execute(text("DROP TABLE IF EXISTS public.shop_health_scores CASCADE"))
        safe_print("  [OK] Migrated and dropped public.shop_health_scores")
    else:
        safe_print("  [SKIP] public.shop_health_scores not found")

    # ========== Part 4: shop_alerts (public -> c_class) ==========
    safe_print("[4/4] Migrating shop_alerts to c_class...")

    if table_exists(conn, 'shop_alerts', 'public'):
        if not table_exists(conn, 'shop_alerts', 'c_class'):
            conn.execute(text("""
                CREATE TABLE c_class.shop_alerts (
                    id SERIAL PRIMARY KEY,
                    platform_code VARCHAR(32) NOT NULL,
                    shop_id VARCHAR(64) NOT NULL,
                    alert_type VARCHAR(64) NOT NULL,
                    alert_level VARCHAR(16) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    metric_value FLOAT,
                    threshold FLOAT,
                    metric_unit VARCHAR(32),
                    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
                    resolved_at TIMESTAMP,
                    resolved_by VARCHAR(64),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_shop_alert FOREIGN KEY (platform_code, shop_id)
                        REFERENCES dim_shops(platform_code, shop_id),
                    CONSTRAINT chk_alert_level CHECK (alert_level IN ('critical', 'warning', 'info'))
                )
            """))
            safe_print("  [OK] Created c_class.shop_alerts")

        conn.execute(text("""
            INSERT INTO c_class.shop_alerts
            SELECT * FROM public.shop_alerts
        """))
        conn.execute(text("DROP TABLE IF EXISTS public.shop_alerts CASCADE"))
        safe_print("  [OK] Migrated and dropped public.shop_alerts")
    else:
        safe_print("  [SKIP] public.shop_alerts not found")

    safe_print("Migration 20260131_pub_to_ac completed.")


def downgrade():
    conn = op.get_bind()
    safe_print("Downgrade: moving tables back to public...")

    # Reverse order: shop_alerts, shop_health_scores, performance_scores, sales_targets
    for table in ['shop_alerts', 'shop_health_scores', 'performance_scores', 'sales_targets']:
        if table_exists(conn, table, 'c_class' if table in ('shop_alerts', 'shop_health_scores', 'performance_scores') else 'a_class'):
            schema = 'c_class' if table in ('shop_alerts', 'shop_health_scores', 'performance_scores') else 'a_class'
            try:
                conn.execute(text(f'ALTER TABLE "{schema}"."{table}" SET SCHEMA public'))
                safe_print(f"  [OK] Moved {schema}.{table} back to public")
            except Exception as e:
                safe_print(f"  [WARN] {table}: {e}")

    # Re-create FK for target_breakdown -> public.sales_targets
    if table_exists(conn, 'target_breakdown', 'a_class') and table_exists(conn, 'sales_targets', 'public'):
        try:
            conn.execute(text("""
                ALTER TABLE a_class.target_breakdown
                DROP CONSTRAINT IF EXISTS fk_target_breakdown_sales_targets
            """))
            conn.execute(text("""
                ALTER TABLE a_class.target_breakdown
                ADD CONSTRAINT target_breakdown_target_id_fkey
                FOREIGN KEY (target_id) REFERENCES public.sales_targets(id) ON DELETE CASCADE
            """))
            safe_print("  [OK] Restored target_breakdown FK to public.sales_targets")
        except Exception as e:
            safe_print(f"  [WARN] Restore FK: {e}")

    safe_print("Downgrade completed.")
