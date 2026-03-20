import textwrap

from backend.routers.component_recorder import _inject_login_success_criteria_block


BASE_CODE = textwrap.dedent(
    '''
    from modules.components.login.base import LoginResult

    async def run(self, page):
        # TODO: 根据实际成功条件校验 (e.g. URL / element)
        return LoginResult(success=True, message="ok")
    '''
).lstrip()


def test_injects_url_contains_and_not_contains_and_element_selector() -> None:
    crit = {
        "url_contains": ["/welcome", "/dashboard"],
        "url_not_contains": "/login",
        "element_visible_selector": "role=navigation",
    }

    out = _inject_login_success_criteria_block(BASE_CODE, crit)

    # 原始 TODO 块应被替换掉
    assert "TODO: 根据实际成功条件校验" not in out

    # URL 包含判断
    assert "if '/welcome' not in current_url" in out
    assert "if '/dashboard' not in current_url" in out

    # URL 不包含判断
    assert "if '/login' in current_url" in out

    # 元素可见性判断（当前规范：唯一性检查 + expect 可见）
    assert "_succ_elem = page.locator('role=navigation')" in out
    assert "await expect(_succ_elem).to_have_count(1)" in out
    assert "await expect(_succ_elem).to_be_visible(timeout=10000)" in out


def test_no_old_block_returns_original_code() -> None:
    code = "async def run(self, page):\n    return 1\n"
    crit = {"url_contains": "/welcome"}
    out = _inject_login_success_criteria_block(code, crit)
    assert out == code
