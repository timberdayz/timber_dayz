from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_account_management_exposes_main_account_enabled_state():
    # 账号管理页已随前端分层迁移到域目录
    # （commit 5f6748e3 "refactor(frontend): repoint routes to domain-owned views"）。
    text = (
        PROJECT_ROOT / "frontend/src/domains/platform/views/AccountManagement.vue"
    ).read_text(encoding="utf-8")

    assert "selectedMainAccountSnapshot.mainEnabled" in text
    assert "handleToggleMainAccountEnabled" in text
    assert "main-account-status-switch" in text


def test_account_management_view_model_tracks_main_account_enabled_state():
    text = (PROJECT_ROOT / "frontend/src/utils/accountManagementView.js").read_text(encoding="utf-8")

    assert "mainEnabled:" in text
    assert "mainAccountMeta?.enabled" in text


def test_accounts_store_updates_main_account_status_independently():
    text = (PROJECT_ROOT / "frontend/src/stores/accounts.js").read_text(encoding="utf-8")

    assert "async updateMainAccountEnabled(" in text
    assert "accountsApi.updateMainAccount(mainAccountId, { enabled })" in text
