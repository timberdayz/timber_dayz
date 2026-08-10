from pathlib import Path

from scripts.verify_release_local import (
    _build_verify_database_url_from_env,
    main,
    parse_args,
    run_release_verification,
)


def test_parse_args_supports_skip_build_and_table():
    args = parse_args(["--skip-build", "--table", "fact_tiktok_orders_monthly"])

    assert args.skip_build is True
    assert args.table == "fact_tiktok_orders_monthly"


def test_main_returns_zero_when_runner_succeeds():
    calls = []

    def fake_runner(*, skip_build, table):
        calls.append((skip_build, table))
        return True

    code = main(["--skip-build", "--table", "fact_tiktok_orders_monthly"], runner=fake_runner)

    assert code == 0
    assert calls == [(True, "fact_tiktok_orders_monthly")]


def test_build_verify_database_url_from_env_reads_database_url(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp\n",
        encoding="utf-8",
    )

    assert _build_verify_database_url_from_env(env_file) == (
        "postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/xihong_erp"
    )


def test_release_verification_does_not_check_the_default_local_database(monkeypatch):
    commands = []

    def fake_run(command, *, env=None):
        commands.append(command)

    monkeypatch.setattr("scripts.verify_release_local._run_command", fake_run)

    run_release_verification(skip_build=True, table="fact_shopee_orders_monthly")

    assert all("scripts/verify_schema_consistency.py" not in command for command in commands)


def test_release_verification_validates_compose_without_rendering_secrets(monkeypatch):
    commands = []

    def fake_run(command, *, env=None):
        commands.append(command)

    monkeypatch.setattr("scripts.verify_release_local._run_command", fake_run)

    run_release_verification(skip_build=True, table="fact_shopee_orders_monthly")

    compose_config_command = next(command for command in commands if command[-1] == "--quiet")
    assert compose_config_command[-2] == "config"
