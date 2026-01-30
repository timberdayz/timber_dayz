"""v4.21.0 HR Module Tables - Industry Standard Design

Revision ID: 20260130_hr_module
Revises: migrate_a_c_class_to_schema
Create Date: 2026-01-30 10:00:00

Description:
- Create departments table (tree structure)
- Create positions table (job grade system)
- Rename a_class.employees Chinese columns to English (员工编号->employee_code, etc.) when present
- Update employees table with industry standard fields
- Create work_shifts table
- Update attendance_records table
- Create leave_types table
- Create leave_records table
- Create overtime_records table
- Create salary_structures table
- Create payroll_records table
- Create social_insurance_config table

All tables are created in a_class schema.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '20260130_hr_module'
down_revision = 'migrate_a_c_class_to_schema'
branch_labels = None
depends_on = None


def safe_print(msg):
    """Safe print for Windows GBK encoding"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


def table_exists(conn, table_name, schema='a_class'):
    """Check if table exists in specified schema"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = :schema AND table_name = :table_name
        )
    """), {'schema': schema, 'table_name': table_name})
    return result.scalar()


def column_exists(conn, table_name, column_name, schema='a_class'):
    """Check if column exists in table"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = :schema 
            AND table_name = :table_name 
            AND column_name = :column_name
        )
    """), {'schema': schema, 'table_name': table_name, 'column_name': column_name})
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()
    
    # Ensure a_class schema exists
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
    
    safe_print("=== v4.21.0 HR Module Migration ===")
    
    # 1. Create departments table
    if not table_exists(conn, 'departments'):
        safe_print("Creating departments table...")
        conn.execute(text("""
            CREATE TABLE a_class.departments (
                id BIGSERIAL PRIMARY KEY,
                department_code VARCHAR(64) NOT NULL UNIQUE,
                department_name VARCHAR(128) NOT NULL,
                parent_id BIGINT,
                level INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                manager_id BIGINT,
                description TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_departments_a_code ON a_class.departments(department_code)"))
        conn.execute(text("CREATE INDEX ix_departments_a_parent ON a_class.departments(parent_id)"))
        conn.execute(text("CREATE INDEX ix_departments_a_status ON a_class.departments(status)"))
        safe_print("  - departments table created")
    else:
        safe_print("  - departments table already exists, skipping")
    
    # 2. Create positions table
    if not table_exists(conn, 'positions'):
        safe_print("Creating positions table...")
        conn.execute(text("""
            CREATE TABLE a_class.positions (
                id BIGSERIAL PRIMARY KEY,
                position_code VARCHAR(64) NOT NULL UNIQUE,
                position_name VARCHAR(128) NOT NULL,
                position_level INTEGER NOT NULL DEFAULT 1,
                department_id BIGINT,
                min_salary NUMERIC(15, 2),
                max_salary NUMERIC(15, 2),
                description TEXT,
                requirements TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_positions_a_code ON a_class.positions(position_code)"))
        conn.execute(text("CREATE INDEX ix_positions_a_level ON a_class.positions(position_level)"))
        conn.execute(text("CREATE INDEX ix_positions_a_department ON a_class.positions(department_id)"))
        safe_print("  - positions table created")
    else:
        safe_print("  - positions table already exists, skipping")
    
    # 2.5 Rename Chinese columns in employees to English (align with schema.py / ORM)
    if table_exists(conn, 'employees'):
        safe_print("Renaming a_class.employees Chinese columns to English (if present)...")
        renames = [
            ('员工编号', 'employee_code'),
            ('姓名', 'name'),
            ('部门', 'department_legacy'),
            ('职位', 'position_legacy'),
            ('入职日期', 'hire_date'),
            ('状态', 'status'),
            ('创建时间', 'created_at'),
            ('更新时间', 'updated_at'),
        ]
        for cn_name, en_name in renames:
            if column_exists(conn, 'employees', cn_name) and not column_exists(conn, 'employees', en_name):
                try:
                    conn.execute(text(f'ALTER TABLE a_class.employees RENAME COLUMN "{cn_name}" TO {en_name}'))
                    safe_print(f"  - Renamed {cn_name} -> {en_name}")
                except Exception as e:
                    safe_print(f"  - Rename {cn_name} -> {en_name} skipped: {e}")
    
    # 3. Update employees table with new columns
    safe_print("Updating employees table with industry standard fields...")
    new_employee_columns = [
        ('gender', 'VARCHAR(16)'),
        ('birth_date', 'DATE'),
        ('id_type', 'VARCHAR(32) DEFAULT \'id_card\''),
        ('id_number', 'VARCHAR(64)'),
        ('avatar_url', 'VARCHAR(512)'),
        ('phone', 'VARCHAR(32)'),
        ('email', 'VARCHAR(128)'),
        ('address', 'VARCHAR(512)'),
        ('emergency_contact', 'VARCHAR(128)'),
        ('emergency_phone', 'VARCHAR(32)'),
        ('department_id', 'BIGINT'),
        ('position_id', 'BIGINT'),
        ('manager_id', 'BIGINT'),
        ('probation_end_date', 'DATE'),
        ('regularization_date', 'DATE'),
        ('leave_date', 'DATE'),
        ('contract_type', 'VARCHAR(32)'),
        ('contract_start_date', 'DATE'),
        ('contract_end_date', 'DATE'),
        ('bank_name', 'VARCHAR(128)'),
        ('bank_account', 'VARCHAR(64)'),
        ('status', 'VARCHAR(32) NOT NULL DEFAULT \'active\''),
        ('hire_date', 'DATE'),
    ]
    
    for col_name, col_type in new_employee_columns:
        if not column_exists(conn, 'employees', col_name):
            conn.execute(text(f"ALTER TABLE a_class.employees ADD COLUMN {col_name} {col_type}"))
            safe_print(f"  - Added column: {col_name}")
        else:
            safe_print(f"  - Column {col_name} already exists, skipping")
    
    # Add new indexes for employees (use savepoint so one failure does not abort transaction)
    index_sqls = [
        "CREATE INDEX IF NOT EXISTS ix_employees_a_position ON a_class.employees(position_id)",
        "CREATE INDEX IF NOT EXISTS ix_employees_a_manager ON a_class.employees(manager_id)",
        "CREATE INDEX IF NOT EXISTS ix_employees_a_status ON a_class.employees(status)",
        "CREATE INDEX IF NOT EXISTS ix_employees_a_hire_date ON a_class.employees(hire_date)",
    ]
    for idx_sql in index_sqls:
        try:
            with conn.begin_nested():
                conn.execute(text(idx_sql))
        except Exception as e:
            safe_print(f"  - Index creation warning (skipped): {e}")
    
    # 4. Create work_shifts table
    if not table_exists(conn, 'work_shifts'):
        safe_print("Creating work_shifts table...")
        conn.execute(text("""
            CREATE TABLE a_class.work_shifts (
                id BIGSERIAL PRIMARY KEY,
                shift_code VARCHAR(64) NOT NULL UNIQUE,
                shift_name VARCHAR(128) NOT NULL,
                start_time VARCHAR(8) NOT NULL,
                end_time VARCHAR(8) NOT NULL,
                work_hours FLOAT NOT NULL DEFAULT 8.0,
                break_hours FLOAT NOT NULL DEFAULT 1.0,
                late_tolerance INTEGER NOT NULL DEFAULT 15,
                early_leave_tolerance INTEGER NOT NULL DEFAULT 15,
                is_flexible BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_work_shifts_a_code ON a_class.work_shifts(shift_code)"))
        conn.execute(text("CREATE INDEX ix_work_shifts_a_status ON a_class.work_shifts(status)"))
        safe_print("  - work_shifts table created")
    else:
        safe_print("  - work_shifts table already exists, skipping")
    
    # 5. Update attendance_records table with new columns
    safe_print("Updating attendance_records table...")
    new_attendance_columns = [
        ('clock_in_location', 'VARCHAR(256)'),
        ('clock_out_location', 'VARCHAR(256)'),
        ('clock_in_type', 'VARCHAR(32) DEFAULT \'normal\''),
        ('clock_out_type', 'VARCHAR(32) DEFAULT \'normal\''),
        ('shift_id', 'BIGINT'),
        ('work_hours', 'FLOAT'),
        ('overtime_hours', 'FLOAT DEFAULT 0.0'),
        ('status', 'VARCHAR(32) NOT NULL DEFAULT \'normal\''),
        ('remark', 'VARCHAR(512)'),
    ]
    
    for col_name, col_type in new_attendance_columns:
        if not column_exists(conn, 'attendance_records', col_name):
            conn.execute(text(f"ALTER TABLE a_class.attendance_records ADD COLUMN {col_name} {col_type}"))
            safe_print(f"  - Added column: {col_name}")
        else:
            safe_print(f"  - Column {col_name} already exists, skipping")
    
    try:
        with conn.begin_nested():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_attendance_records_a_status ON a_class.attendance_records(status)"))
    except Exception as e:
        safe_print(f"  - Index creation warning: {e}")
    
    # 6. Create leave_types table
    if not table_exists(conn, 'leave_types'):
        safe_print("Creating leave_types table...")
        conn.execute(text("""
            CREATE TABLE a_class.leave_types (
                id BIGSERIAL PRIMARY KEY,
                leave_code VARCHAR(64) NOT NULL UNIQUE,
                leave_name VARCHAR(128) NOT NULL,
                is_paid BOOLEAN NOT NULL DEFAULT TRUE,
                max_days_per_year FLOAT,
                requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
                description TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_leave_types_a_code ON a_class.leave_types(leave_code)"))
        conn.execute(text("CREATE INDEX ix_leave_types_a_status ON a_class.leave_types(status)"))
        safe_print("  - leave_types table created")
        
        # Insert default leave types
        conn.execute(text("""
            INSERT INTO a_class.leave_types (leave_code, leave_name, is_paid, max_days_per_year, description)
            VALUES 
                ('annual', '年假', TRUE, 10, '带薪年假'),
                ('sick', '病假', TRUE, 12, '带薪病假'),
                ('personal', '事假', FALSE, NULL, '个人事假'),
                ('marriage', '婚假', TRUE, 10, '结婚假'),
                ('maternity', '产假', TRUE, 98, '产假'),
                ('paternity', '陪产假', TRUE, 15, '陪产假'),
                ('bereavement', '丧假', TRUE, 3, '丧亲假')
            ON CONFLICT (leave_code) DO NOTHING
        """))
        safe_print("  - Default leave types inserted")
    else:
        safe_print("  - leave_types table already exists, skipping")
    
    # 7. Create leave_records table
    if not table_exists(conn, 'leave_records'):
        safe_print("Creating leave_records table...")
        conn.execute(text("""
            CREATE TABLE a_class.leave_records (
                id BIGSERIAL PRIMARY KEY,
                employee_code VARCHAR(64) NOT NULL,
                leave_type_id BIGINT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                days FLOAT NOT NULL,
                reason TEXT,
                approver_id BIGINT,
                approval_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                approval_time TIMESTAMP,
                approval_remark VARCHAR(512),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_leave_records_a_employee ON a_class.leave_records(employee_code)"))
        conn.execute(text("CREATE INDEX ix_leave_records_a_date ON a_class.leave_records(start_date, end_date)"))
        conn.execute(text("CREATE INDEX ix_leave_records_a_status ON a_class.leave_records(approval_status)"))
        safe_print("  - leave_records table created")
    else:
        safe_print("  - leave_records table already exists, skipping")
    
    # 8. Create overtime_records table
    if not table_exists(conn, 'overtime_records'):
        safe_print("Creating overtime_records table...")
        conn.execute(text("""
            CREATE TABLE a_class.overtime_records (
                id BIGSERIAL PRIMARY KEY,
                employee_code VARCHAR(64) NOT NULL,
                overtime_date DATE NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                hours FLOAT NOT NULL,
                overtime_type VARCHAR(32) NOT NULL DEFAULT 'workday',
                reason TEXT,
                approver_id BIGINT,
                approval_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                approval_time TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_overtime_records_a_employee ON a_class.overtime_records(employee_code)"))
        conn.execute(text("CREATE INDEX ix_overtime_records_a_date ON a_class.overtime_records(overtime_date)"))
        conn.execute(text("CREATE INDEX ix_overtime_records_a_status ON a_class.overtime_records(approval_status)"))
        safe_print("  - overtime_records table created")
    else:
        safe_print("  - overtime_records table already exists, skipping")
    
    # 9. Create salary_structures table
    if not table_exists(conn, 'salary_structures'):
        safe_print("Creating salary_structures table...")
        conn.execute(text("""
            CREATE TABLE a_class.salary_structures (
                id BIGSERIAL PRIMARY KEY,
                employee_code VARCHAR(64) NOT NULL UNIQUE,
                base_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                position_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                housing_allowance NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                transport_allowance NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                meal_allowance NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                communication_allowance NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                other_allowance NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                performance_ratio FLOAT NOT NULL DEFAULT 0.0,
                commission_ratio FLOAT NOT NULL DEFAULT 0.0,
                social_insurance_base NUMERIC(15, 2),
                housing_fund_base NUMERIC(15, 2),
                effective_date DATE NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_salary_structures_a_employee ON a_class.salary_structures(employee_code)"))
        conn.execute(text("CREATE INDEX ix_salary_structures_a_status ON a_class.salary_structures(status)"))
        safe_print("  - salary_structures table created")
    else:
        safe_print("  - salary_structures table already exists, skipping")
    
    # 10. Create payroll_records table
    if not table_exists(conn, 'payroll_records'):
        safe_print("Creating payroll_records table...")
        conn.execute(text("""
            CREATE TABLE a_class.payroll_records (
                id BIGSERIAL PRIMARY KEY,
                employee_code VARCHAR(64) NOT NULL,
                year_month VARCHAR(7) NOT NULL,
                base_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                position_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                performance_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                overtime_pay NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                commission NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                allowances NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                bonus NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                gross_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                social_insurance_personal NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                housing_fund_personal NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                income_tax NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                other_deductions NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                total_deductions NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                net_salary NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                social_insurance_company NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                housing_fund_company NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                total_cost NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                pay_date DATE,
                remark TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(employee_code, year_month)
            )
        """))
        conn.execute(text("CREATE INDEX ix_payroll_records_a_employee ON a_class.payroll_records(employee_code)"))
        conn.execute(text("CREATE INDEX ix_payroll_records_a_month ON a_class.payroll_records(year_month)"))
        conn.execute(text("CREATE INDEX ix_payroll_records_a_status ON a_class.payroll_records(status)"))
        safe_print("  - payroll_records table created")
    else:
        safe_print("  - payroll_records table already exists, skipping")
    
    # 11. Create social_insurance_config table
    if not table_exists(conn, 'social_insurance_config'):
        safe_print("Creating social_insurance_config table...")
        conn.execute(text("""
            CREATE TABLE a_class.social_insurance_config (
                id BIGSERIAL PRIMARY KEY,
                config_name VARCHAR(128) NOT NULL UNIQUE,
                city VARCHAR(64),
                pension_company_ratio FLOAT NOT NULL DEFAULT 0.16,
                pension_personal_ratio FLOAT NOT NULL DEFAULT 0.08,
                medical_company_ratio FLOAT NOT NULL DEFAULT 0.10,
                medical_personal_ratio FLOAT NOT NULL DEFAULT 0.02,
                unemployment_company_ratio FLOAT NOT NULL DEFAULT 0.008,
                unemployment_personal_ratio FLOAT NOT NULL DEFAULT 0.002,
                injury_company_ratio FLOAT NOT NULL DEFAULT 0.002,
                maternity_company_ratio FLOAT NOT NULL DEFAULT 0.008,
                housing_fund_company_ratio FLOAT NOT NULL DEFAULT 0.12,
                housing_fund_personal_ratio FLOAT NOT NULL DEFAULT 0.12,
                min_base NUMERIC(15, 2),
                max_base NUMERIC(15, 2),
                effective_date DATE NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_social_insurance_config_a_name ON a_class.social_insurance_config(config_name)"))
        conn.execute(text("CREATE INDEX ix_social_insurance_config_a_city ON a_class.social_insurance_config(city)"))
        safe_print("  - social_insurance_config table created")
        
        # Insert default social insurance config
        conn.execute(text("""
            INSERT INTO a_class.social_insurance_config (
                config_name, city, effective_date,
                pension_company_ratio, pension_personal_ratio,
                medical_company_ratio, medical_personal_ratio,
                unemployment_company_ratio, unemployment_personal_ratio,
                injury_company_ratio, maternity_company_ratio,
                housing_fund_company_ratio, housing_fund_personal_ratio
            ) VALUES (
                'default_2026', NULL, '2026-01-01',
                0.16, 0.08,
                0.10, 0.02,
                0.008, 0.002,
                0.002, 0.008,
                0.12, 0.12
            ) ON CONFLICT (config_name) DO NOTHING
        """))
        safe_print("  - Default social insurance config inserted")
    else:
        safe_print("  - social_insurance_config table already exists, skipping")
    
    # 12. Insert default work shifts
    safe_print("Inserting default work shifts...")
    conn.execute(text("""
        INSERT INTO a_class.work_shifts (
            shift_code, shift_name, start_time, end_time, work_hours, break_hours,
            late_tolerance, early_leave_tolerance, is_flexible, status,
            created_at, updated_at
        )
        VALUES 
            ('STD', '标准班', '09:00', '18:00', 8.0, 1.0, 15, 15, FALSE, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('FLEX', '弹性班', '08:00', '20:00', 8.0, 1.0, 15, 15, TRUE, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('EARLY', '早班', '06:00', '14:00', 7.0, 1.0, 15, 15, FALSE, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('LATE', '晚班', '14:00', '22:00', 7.0, 1.0, 15, 15, FALSE, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (shift_code) DO NOTHING
    """))
    safe_print("  - Default work shifts inserted")
    
    # 13. Insert default departments
    safe_print("Inserting default departments...")
    conn.execute(text("""
        INSERT INTO a_class.departments (department_code, department_name, level, sort_order, status, created_at, updated_at)
        VALUES 
            ('MGMT', '管理层', 1, 1, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('SALES', '销售部', 1, 2, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('OPS', '运营部', 1, 3, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('TECH', '技术部', 1, 4, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('FIN', '财务部', 1, 5, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('HR', '人力资源部', 1, 6, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (department_code) DO NOTHING
    """))
    safe_print("  - Default departments inserted")
    
    # 14. Insert default positions
    safe_print("Inserting default positions...")
    conn.execute(text("""
        INSERT INTO a_class.positions (position_code, position_name, position_level, status, created_at, updated_at)
        VALUES 
            ('CEO', '首席执行官', 10, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('GM', '总经理', 9, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('DIR', '总监', 8, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('MGR', '经理', 7, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('SMGR', '高级经理', 6, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('SUPV', '主管', 5, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('SEN', '高级专员', 4, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('SPEC', '专员', 3, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('ASST', '助理', 2, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('INT', '实习生', 1, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (position_code) DO NOTHING
    """))
    safe_print("  - Default positions inserted")
    
    safe_print("=== HR Module Migration Complete ===")


def downgrade() -> None:
    conn = op.get_bind()
    
    safe_print("=== Rolling back HR Module Migration ===")
    
    # Drop new tables (in reverse order of creation)
    tables_to_drop = [
        'social_insurance_config',
        'payroll_records',
        'salary_structures',
        'overtime_records',
        'leave_records',
        'leave_types',
        'work_shifts',
        'positions',
        'departments',
    ]
    
    for table in tables_to_drop:
        if table_exists(conn, table):
            conn.execute(text(f"DROP TABLE IF EXISTS a_class.{table} CASCADE"))
            safe_print(f"  - Dropped table: {table}")
    
    # Note: We don't remove columns from employees and attendance_records
    # as that could cause data loss
    
    safe_print("=== HR Module Rollback Complete ===")
