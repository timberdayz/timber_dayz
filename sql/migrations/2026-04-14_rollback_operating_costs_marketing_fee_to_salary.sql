DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = 'marketing_fee'
    ) THEN
        EXECUTE 'ALTER TABLE a_class.operating_costs RENAME COLUMN marketing_fee TO salary';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '营销费用'
    ) THEN
        EXECUTE 'ALTER TABLE a_class.operating_costs RENAME COLUMN "营销费用" TO "工资"';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = 'salary'
    ) THEN
        EXECUTE $sql$
            COMMENT ON COLUMN a_class.operating_costs.salary
            IS '工资成本（CNY）'
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '工资'
    ) THEN
        EXECUTE $sql$
            COMMENT ON COLUMN a_class.operating_costs."工资"
            IS '工资成本（CNY）'
        $sql$;
    END IF;
END
$$;
