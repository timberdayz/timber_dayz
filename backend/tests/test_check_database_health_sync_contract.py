def test_health_check_includes_data_sync_critical_columns():
    from scripts.check_database_health import check_critical_tables

    class _FakeCursor:
        def __init__(self, connection):
            self.connection = connection
            self._rows = []

        def execute(self, sql, params=None):
            compact_sql = " ".join(sql.split())
            if "FROM information_schema.tables" in compact_sql:
                table_name = params[0]
                schema = self.connection.tables.get(table_name)
                self._rows = [(schema,)] if schema else []
                return

            if "FROM information_schema.columns" in compact_sql:
                schema_name, table_name = params
                columns = self.connection.columns.get((schema_name, table_name), [])
                self._rows = [(column,) for column in columns]
                return

            raise AssertionError(f"Unexpected SQL in test: {compact_sql}")

        def fetchall(self):
            return self._rows

        def close(self):
            return None

    class _FakeConnection:
        def __init__(self):
            self.tables = {
                "operating_costs": "a_class",
                "sales_targets": "a_class",
                "sales_targets_a": "a_class",
                "target_breakdown": "a_class",
                "platform_accounts": "core",
                "employees": "a_class",
                "departments": "a_class",
                "data_quarantine": "core",
                "staging_orders": "core",
                "staging_product_metrics": "core",
                "staging_inventory": "core",
            }
            self.columns = {
                ("a_class", "operating_costs"): [
                    "id",
                    "店铺ID",
                    "年月",
                    "租金",
                    "营销费用",
                    "水电费",
                    "AI Token费用",
                    "人力费用",
                    "其他成本",
                    "成本合计",
                    "创建时间",
                    "更新时间",
                ],
                ("a_class", "sales_targets"): ["id", "target_name", "target_type", "period_start", "period_end"],
                ("a_class", "sales_targets_a"): [],
                ("a_class", "target_breakdown"): ["id", "target_id", "breakdown_type"],
                ("core", "platform_accounts"): ["id", "platform", "account_alias"],
                ("a_class", "employees"): ["id", "employee_code", "name"],
                ("a_class", "departments"): ["id", "department_code", "department_name"],
                ("core", "data_quarantine"): ["id", "source_file"],
                ("core", "staging_orders"): ["id"],
                ("core", "staging_product_metrics"): ["id"],
                ("core", "staging_inventory"): ["id"],
            }

        def cursor(self):
            return _FakeCursor(self)

    issues, _recommendations = check_critical_tables(_FakeConnection())

    assert any("core.data_quarantine" in issue and "catalog_file_id" in issue for issue in issues)
    assert any("core.staging_orders" in issue and "file_id" in issue for issue in issues)
    assert any("core.staging_product_metrics" in issue and "file_id" in issue for issue in issues)
    assert any("core.staging_inventory" in issue and "file_id" in issue for issue in issues)
    assert not any("a_class.operating_costs" in issue for issue in issues)
