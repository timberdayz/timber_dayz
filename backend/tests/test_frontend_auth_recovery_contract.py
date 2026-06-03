from pathlib import Path


def test_user_store_treats_401_auth_probe_as_expected_recovery():
    text = Path("frontend/src/stores/user.js").read_text(encoding="utf-8")

    assert "if (error.response && error.response.status === 401)" in text
    assert "console.error('获取用户信息失败:', error)" not in text
    assert "console.warn('获取用户信息失败:', error)" in text


def test_simple_account_switcher_skips_duplicate_auth_probe_after_recovery_failure():
    text = Path("frontend/src/components/common/SimpleAccountSwitcher.vue").read_text(
        encoding="utf-8"
    )

    assert "hasAuthRecoveryFailed" in text
    assert "hasPersistedAuthSession" in text
    assert "readPersistedAuthState(localStorage)" in text
    assert "if (hasAuthRecoveryFailed(localStorage))" in text
