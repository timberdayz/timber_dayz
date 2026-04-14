DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = 'salary'
    ) THEN
        EXECUTE 'ALTER TABLE a_class.operating_costs RENAME COLUMN salary TO marketing_fee';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '工资'
    ) THEN
        EXECUTE 'ALTER TABLE a_class.operating_costs RENAME COLUMN "工资" TO "营销费用"';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = 'marketing_fee'
    ) THEN
        EXECUTE $sql$
            COMMENT ON COLUMN a_class.operating_costs.marketing_fee
            IS '营销费用（CNY）'
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '营销费用'
    ) THEN
        EXECUTE $sql$
            COMMENT ON COLUMN a_class.operating_costs."营销费用"
            IS '营销费用（CNY）'
        $sql$;
    END IF;
END
$$;
