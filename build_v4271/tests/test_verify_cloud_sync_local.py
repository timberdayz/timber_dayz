from scripts.verify_cloud_sync_local import parse_args, main


def test_parse_args_supports_verify_db_name():
    args = parse_args(["--verify-db", "xihong_erp_cloud_sync_verify", "--table", "fact_shopee_orders_monthly"])
    assert args.verify_db == "xihong_erp_cloud_sync_verify"
    assert args.table == "fact_shopee_orders_monthly"


def test_main_returns_zero_when_all_steps_succeed():
    calls = []

    def fake_runner(*, verify_db, table):
        calls.append((verify_db, table))
        return True

    code = main(
        ["--verify-db", "xihong_erp_cloud_sync_verify", "--table", "fact_shopee_orders_monthly"],
        runner=fake_runner,
    )

    assert code == 0
    assert calls == [("xihong_erp_cloud_sync_verify", "fact_shopee_orders_monthly")]


def test_main_returns_non_zero_when_verification_fails():
    code = main(
        ["--verify-db", "xihong_erp_cloud_sync_verify"],
        runner=lambda **kwargs: False,
    )
    assert code == 2
