import json
import subprocess
import sys

from scripts.pwcli_account_inventory import (
    MainAccountRow,
    build_inspection_accounts,
    display_name,
    work_tag,
)


def test_work_tag_normalizes_spaces_colons_email_and_non_ascii():
    assert work_tag("shopee", "hongxikeji:main") == "shopee-hongxikeji-main-inspect"
    assert work_tag("tiktok", "chenzeweinbnb@163.com") == "tiktok-chenzeweinbnb-163-com-inspect"
    assert work_tag("tiktok", "Tiktok 1店") == "tiktok-tiktok-1-inspect"


def test_display_name_prefers_main_account_name_then_username_then_account_id():
    assert (
        display_name(
            MainAccountRow(
                platform="shopee",
                main_account_id="hongxikeji:main",
                main_account_name="Hongxi",
                username="seller@example.com",
            )
        )
        == "Hongxi"
    )
    assert (
        display_name(
            MainAccountRow(
                platform="tiktok",
                main_account_id="acc-1",
                main_account_name="acc-1",
                username="seller@example.com",
            )
        )
        == "acc-1 (seller@example.com)"
    )


def test_build_inspection_accounts_skips_unknown_platforms_and_outputs_menu_fields():
    rows = [
        MainAccountRow("shopee", "hongxikeji:main", "Hongxi", ""),
        MainAccountRow("unknown", "legacy", "Legacy", ""),
    ]

    accounts, skipped = build_inspection_accounts(rows)

    assert accounts == [
        {
            "platform": "shopee",
            "display_name": "Hongxi",
            "account_id": "hongxikeji:main",
            "work_tag": "shopee-hongxikeji-main-inspect",
        }
    ]
    assert skipped == ["unknown:legacy"]


def test_daily_inspection_cli_outputs_json_from_monkeypatched_loader(monkeypatch):
    import scripts.pwcli_daily_inspection as cli

    monkeypatch.setattr(
        cli,
        "load_accounts",
        lambda: [
            MainAccountRow("miaoshou", "miaoshou_real_001", "xihong", ""),
            MainAccountRow("unknown", "legacy", "Legacy", ""),
        ],
    )

    assert cli.main(["list-accounts", "--format", "json"]) == 0
    payload = json.loads(cli.LAST_STDOUT)
    assert payload == [
        {
            "platform": "miaoshou",
            "display_name": "xihong",
            "account_id": "miaoshou_real_001",
            "work_tag": "miaoshou-miaoshou-real-001-inspect",
        }
    ]
    assert "Skipping unsupported platform account: unknown:legacy" in cli.LAST_STDERR


def test_daily_inspection_cli_script_has_list_accounts_json_entrypoint():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/pwcli_daily_inspection.py",
            "list-accounts",
            "--format",
            "json",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--format" in result.stdout
