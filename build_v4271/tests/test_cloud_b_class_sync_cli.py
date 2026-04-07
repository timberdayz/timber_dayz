from scripts.sync_b_class_to_cloud import main, parse_args


class FakeService:
    def __init__(self, result):
        self.result = result

    async def sync_all_tables(self, batch_size: int = 1000):
        return self.result


def test_cli_returns_non_zero_when_any_table_fails():
    code = main(
        ["--batch-size", "100"],
        service_factory=lambda args: FakeService({"failed_tables": 1}),
    )
    assert code != 0


def test_cli_returns_zero_when_all_tables_succeed():
    code = main(
        ["--batch-size", "100"],
        service_factory=lambda args: FakeService({"failed_tables": 0}),
    )
    assert code == 0


def test_cli_calls_single_table_sync_when_table_is_provided():
    class SingleTableService:
        def __init__(self):
            self.called = None

        async def sync_table(self, table_name: str, batch_size: int = 1000):
            self.called = (table_name, batch_size)
            return {"status": "completed"}

    service = SingleTableService()
    code = main(
        ["--table", "fact_shopee_orders_daily", "--batch-size", "50"],
        service_factory=lambda args: service,
    )

    assert code == 0
    assert service.called == ("fact_shopee_orders_daily", 50)


def test_parse_args_supports_dry_run():
    args = parse_args(["--dry-run", "--batch-size", "10"])
    assert args.dry_run is True
    assert args.batch_size == 10
