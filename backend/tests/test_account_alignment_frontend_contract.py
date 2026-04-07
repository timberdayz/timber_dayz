from pathlib import Path


def test_account_alignment_view_uses_current_alias_workflow():
    text = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/views/AccountAlignment.vue"
    ).read_text(encoding="utf-8")

    assert "accountsApi.getUnmatchedShopAliases()" in text
    assert "accountsApi.claimShopAccountAlias({" in text
    assert "accountsApi.listShopAccounts()" in text
    assert "accountsApi.listShopAccountAliases()" in text


def test_account_alignment_view_no_longer_depends_on_legacy_account_alignment_endpoints():
    text = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/views/AccountAlignment.vue"
    ).read_text(encoding="utf-8")

    assert "/account-alignment/distinct-raw-stores" not in text
    assert "/account-alignment/add-alias" not in text
    assert "/account-alignment/batch-add-aliases" not in text
