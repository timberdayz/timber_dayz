from scripts.verify_cloud_sync_local import (
    _build_verify_database_url,
    _load_local_database_url,
    main,
    parse_args,
    run_verification,
)


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


def test_run_verification_uses_env_override_for_cloud_database_url(monkeypatch):
    commands = []

    def fake_run_command(command, env=None):
        commands.append((command, env))

    monkeypatch.setenv(
        "CLOUD_SYNC_VERIFY_DATABASE_URL",
        "postgresql://override-user:override-pass@127.0.0.1:15432/custom_verify_db",
    )
    monkeypatch.setattr("scripts.verify_cloud_sync_local._run_command", fake_run_command)

    run_verification(verify_db="xihong_erp_cloud_sync_verify", table="fact_shopee_orders_monthly")

    assert commands[-1][1]["CLOUD_DATABASE_URL"] == (
        "postgresql://override-user:override-pass@127.0.0.1:15432/custom_verify_db"
    )


def test_build_verify_database_url_reuses_local_database_auth(monkeypatch):
    monkeypatch.delenv("CLOUD_SYNC_VERIFY_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp",
    )

    assert _build_verify_database_url("xihong_erp_cloud_sync_verify") == (
        "postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp_cloud_sync_verify"
    )


def test_load_local_database_url_reads_project_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp\n",
        encoding="utf-8",
    )

    assert _load_local_database_url(tmp_path) == (
        "postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp"
    )
