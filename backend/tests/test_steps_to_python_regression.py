# -*- coding: utf-8 -*-
"""
生成器回归测试（openspec optimize-component-version-management 8.8 +
refactor-generator-runtime-separation）

覆盖：
- 四类反模式不出现于生成结果
- 生成器不注入门卫检测和容器发现框架逻辑
- URL 导航来源优先级保留
- 验证码处理保留
- 登录成功条件模板存在
"""
from __future__ import annotations

import re
from backend.services.steps_to_python import generate_python_code


def _steps_wait_no_reason():
    return [
        {"action": "wait", "timeout": 1000},
    ]


def _steps_wait_with_fixed_reason():
    return [
        {"action": "wait", "timeout": 2000, "comment": "固定等待动画结束"},
    ]


def _steps_login_with_captcha():
    return [
        {"action": "navigate", "url": "https://example.com/login"},
        {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
        {"action": "fill", "selector": "input.captcha-text", "value": "1234", "step_group": "captcha_graphical"},
        {"action": "click", "selector": "button.login"},
    ]


def _steps_optional_click():
    return [
        {"action": "click", "selector": "button.skip", "optional": True},
    ]


class TestAntiPatternsAbsent:
    """生成代码中不应出现关键反模式。"""

    def test_no_bare_except_pass(self):
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=_steps_optional_click(),
        )
        assert "except Exception" in code
        assert "    pass" not in code
        assert "logger.warning" in code or "self.ctx.logger.warning" in code
        assert "i + 1" not in code
        assert "(action=%s)" not in code

    def test_wait_without_fixed_reason_uses_conditional(self):
        code = generate_python_code(
            platform="test",
            component_type="navigation",
            component_name="nav",
            steps=_steps_wait_no_reason(),
        )
        assert "wait_for_load_state" in code
        assert "networkidle" in code
        assert "wait_for_timeout" not in code

    def test_wait_with_fixed_reason_uses_timeout_and_comment(self):
        code = generate_python_code(
            platform="test",
            component_type="navigation",
            component_name="nav",
            steps=_steps_wait_with_fixed_reason(),
        )
        assert "wait_for_timeout" in code
        assert "固定" in code or "等待" in code

    def test_login_captcha_resume_no_first(self):
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=_steps_login_with_captcha(),
        )
        assert "to_have_count(1)" in code
        resume_section = code[code.find("恢复路径") : code.find("恢复路径") + 1200]
        assert ".first" not in resume_section

    def test_captcha_detection_no_count_is_visible(self):
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=_steps_login_with_captcha(),
        )
        assert "count() > 0" not in code
        assert not re.search(r"count\(\)\s*>\s*0.*is_visible", code, re.DOTALL)

    def test_no_dot_first_in_captcha_locator_expr(self):
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=_steps_login_with_captcha(),
        )
        if "page.locator(" in code and "验证码" in code:
            idx = code.find("page.locator(")
            snippet = code[idx : idx + 120]
            assert ".first" not in snippet or "first  #" in snippet

    def test_popup_dialog_uses_expect_unique(self):
        steps = [
            {"action": "click", "selector": "", "step_group": "popup"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "expect(dialog).to_have_count(1)" in code
        assert "dialog = page.locator(" in code
        assert ".first" not in code or "dialog" not in code


class TestGeneratorRuntimeSeparation:
    """refactor-generator-runtime-separation: 生成器不注入框架逻辑。"""

    def test_no_door_guard_login_element_candidates(self):
        """生成的 login 代码不包含 _login_element_candidates 门卫检测。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
            {"action": "fill", "selector": "input[name=password]", "value": "{{account.password}}"},
            {"action": "click", "selector": "button[type=submit]"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "_login_element_candidates" not in code
        assert "_route_markers" not in code
        assert "_ready_before_nav" not in code
        assert "login navigation check failed" not in code

    def test_no_container_discovery_form_candidates(self):
        """生成的 login 代码不包含 _form_candidates 容器发现。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "user"},
            {"action": "click", "selector": "button[type=submit]"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "_form_candidates" not in code
        assert "Login container fallback to page root" not in code
        assert "_form_diag" not in code
        assert "_form = page" in code

    def test_url_navigation_priority_preserved(self):
        """URL 导航来源优先级保留在生成代码中。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "params.get(\"login_url_override\")" in code
        assert "acc.get(\"login_url\")" in code
        assert "config.get(\"default_login_url\")" in code
        assert "_platform_defaults" in code
        assert "await page.goto(_target_url" in code

    def test_simple_navigation_without_guards(self):
        """导航后不再执行门卫重检，仅 domcontentloaded + guard_overlays。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "if _target_url:" in code
        assert "domcontentloaded" in code
        assert "guard_overlays" in code
        # No post-navigation element detection loop
        assert "for _el_name, _el_loc in _login_element_candidates" not in code

    def test_login_success_condition_template(self):
        """生成代码包含登录成功条件模板（TODO 注释）。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
            {"action": "fill", "selector": "input[name=password]", "value": "{{account.password}}"},
            {"action": "click", "selector": "button[type=submit]"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "TODO: edit success condition" in code
        assert "wait_for_url" in code

    def test_captcha_handling_preserved(self):
        """验证码处理逻辑保留在组件中。"""
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=_steps_login_with_captcha(),
        )
        assert "VerificationRequiredError" in code
        assert "captcha" in code.lower()

    def test_framework_code_lines_limited(self):
        """login 组件框架代码（URL 导航 + 容器设置）不超过 50 行。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
            {"action": "fill", "selector": "input[name=password]", "value": "{{account.password}}"},
            {"action": "click", "selector": "button[type=submit]"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        lines = code.split("\n")
        run_start = next(i for i, l in enumerate(lines) if "async def run" in l)
        first_step_comment = None
        for i in range(run_start, len(lines)):
            if "acc.get(" in lines[i] or "_el_" in lines[i]:
                first_step_comment = i
                break
        if first_step_comment:
            framework_lines = first_step_comment - run_start
            assert framework_lines <= 50, f"Framework code is {framework_lines} lines, expected <= 50"

    def test_non_login_component_unaffected(self):
        """export 和 navigation 组件不受门卫/容器移除的影响。"""
        steps = [
            {"action": "click", "selector": "button.export"},
        ]
        code_export = generate_python_code(
            platform="test",
            component_type="export",
            component_name="orders_export",
            steps=steps,
        )
        assert "_login_element_candidates" not in code_export
        assert "_form_candidates" not in code_export

        code_nav = generate_python_code(
            platform="test",
            component_type="navigation",
            component_name="nav",
            steps=steps,
        )
        assert "_login_element_candidates" not in code_nav
        assert "_form_candidates" not in code_nav


class TestGeneratorQualityOptimizations:
    """生成器质量优化：.first 消除、click+fill 合并、容器上下文。"""

    def test_no_dot_first_when_form_is_page(self):
        """_form = page 时生成的 locator 不带 .first。"""
        steps = [
            {"action": "fill", "selector": "input.account-input", "value": "{{account.username}}"},
            {"action": "fill", "selector": "input.password-input", "value": "{{account.password}}"},
            {"action": "click", "selector": "button.login"},
        ]
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "_form = page" in code
        step_section = code[code.find("_form = page"):]
        assert ".first" not in step_section

    def test_click_fill_deduplication(self):
        """click 后紧跟同选择器 fill 时，合并为单个 fill（去除冗余 click）。"""
        steps = [
            {"action": "click", "selector": "input.account-input"},
            {"action": "fill", "selector": "input.account-input", "value": "{{account.username}}"},
            {"action": "click", "selector": "input.password-input"},
            {"action": "fill", "selector": "input.password-input", "value": "{{account.password}}"},
        ]
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        lines = [l.strip() for l in code.split("\n") if l.strip()]
        click_lines = [l for l in lines if ".click(" in l and "_el_" in l]
        fill_lines = [l for l in lines if ".fill(" in l and "_el_" in l]
        assert len(fill_lines) == 2, f"Expected 2 fill, got {len(fill_lines)}"
        assert len(click_lines) == 0, f"Expected 0 click (deduplicated), got {len(click_lines)}"

    def test_click_fill_different_selector_not_merged(self):
        """click 与 fill 选择器不同时不合并。"""
        steps = [
            {"action": "click", "selector": "input.account-input"},
            {"action": "fill", "selector": "input.password-input", "value": "pwd"},
        ]
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        lines = [l.strip() for l in code.split("\n") if l.strip()]
        click_lines = [l for l in lines if ".click(" in l and "_el_" in l]
        fill_lines = [l for l in lines if ".fill(" in l and "_el_" in l]
        assert len(click_lines) == 1
        assert len(fill_lines) == 1

    def test_container_selector_from_metadata(self):
        """metadata 携带 container_selector 时生成具体容器 locator。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
        ]
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=steps,
            metadata={"container_selector": "#J_loginRegisterForm"},
        )
        assert "_form = page.locator(" in code
        assert "#J_loginRegisterForm" in code
        assert "_form = page\n" not in code

    def test_no_container_selector_defaults_to_page(self):
        """metadata 无 container_selector 时默认 _form = page。"""
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
        ]
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=steps,
        )
        assert "_form = page" in code


class TestRealWorldScenarioPatterns:
    """生成代码应包含可应对现实场景的稳健模式。"""

    def test_expect_import_present_when_used(self):
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=_steps_login_with_captcha(),
        )
        assert "from playwright.async_api import expect" in code

    def test_resume_failure_message_includes_context(self):
        code = generate_python_code(
            platform="miaoshou",
            component_type="login",
            component_name="login",
            steps=_steps_login_with_captcha(),
        )
        assert "验证码恢复失败" in code
        assert "getattr(page" in code or "url=" in code
        assert "cap_sel=" in code or "login_sel=" in code

    def test_scope_convergence_dialog_chain_selector(self):
        steps = [
            {"action": "click", "selector": ".ant-modal >> role=button[name=确定]"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="navigation",
            component_name="nav",
            steps=steps,
        )
        assert "作用域收敛：dialog 内定位" in code
        assert "to_have_count(1)" in code
        assert "role=button[name=确定]" not in code

    def test_scope_convergence_iframe_chain_selector(self):
        steps = [
            {"action": "click", "selector": "iframe#iframe-main >> role=button[name=导出]"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="navigation",
            component_name="nav",
            steps=steps,
        )
        assert "frame_locator" in code
        assert "作用域收敛：iframe 内定位" in code

    def test_scope_convergence_row_chain_selector(self):
        steps = [
            {"action": "click", "selector": "table tbody tr[data-row='1'] >> text=导出"},
        ]
        code = generate_python_code(
            platform="test",
            component_type="navigation",
            component_name="nav",
            steps=steps,
        )
        assert "作用域收敛：表格行内定位" in code
        assert "_row_scope_" in code


class TestNewActionSupport:
    """7.1 select/press/download action 生成测试。"""

    def test_select_action_generates_select_option(self):
        steps = [{"action": "select", "selector": "select#country", "value": "China"}]
        code = generate_python_code(
            platform="test", component_type="navigation", component_name="nav", steps=steps,
        )
        assert "select_option" in code
        assert "'China'" in code

    def test_press_action_with_selector(self):
        steps = [{"action": "press", "selector": "input#search", "value": "Enter"}]
        code = generate_python_code(
            platform="test", component_type="navigation", component_name="nav", steps=steps,
        )
        assert ".press(" in code
        assert "'Enter'" in code

    def test_press_action_without_selector(self):
        steps = [{"action": "press", "selector": "", "value": "Escape"}]
        code = generate_python_code(
            platform="test", component_type="navigation", component_name="nav", steps=steps,
        )
        assert "page.keyboard.press(" in code
        assert "'Escape'" in code

    def test_download_action_generates_expect_download(self):
        steps = [{"action": "download", "selector": "a.download-link", "value": ""}]
        code = generate_python_code(
            platform="test", component_type="navigation", component_name="nav", steps=steps,
        )
        assert "expect_download" in code
        assert "save_as" in code
        assert "suggested_filename" in code


class TestExportDownloadTemplate:
    """7.2 export 组件下载模板测试。"""

    def test_export_has_expect_download(self):
        steps = [{"action": "click", "selector": "button.export"}]
        code = generate_python_code(
            platform="test", component_type="export", component_name="orders_export", steps=steps,
        )
        assert "expect_download" in code

    def test_export_has_build_standard_output_root(self):
        steps = [{"action": "click", "selector": "button.export"}]
        code = generate_python_code(
            platform="test", component_type="export", component_name="orders_export", steps=steps,
        )
        assert "build_standard_output_root" in code

    def test_export_has_save_as(self):
        steps = [{"action": "click", "selector": "button.export"}]
        code = generate_python_code(
            platform="test", component_type="export", component_name="orders_export", steps=steps,
        )
        assert "save_as" in code

    def test_export_returns_file_path(self):
        steps = [{"action": "click", "selector": "button.export"}]
        code = generate_python_code(
            platform="test", component_type="export", component_name="orders_export", steps=steps,
        )
        assert "file_path=str(file_path)" in code


class TestBaseClassInheritance:
    """7.3 navigation/date_picker/other 基类继承测试。"""

    def test_navigation_inherits_navigation_component(self):
        steps = [{"action": "click", "selector": "a.nav-link"}]
        code = generate_python_code(
            platform="test", component_type="navigation", component_name="nav", steps=steps,
        )
        assert "NavigationComponent" in code
        assert "NavigationResult" in code
        assert "TargetPage" in code
        assert "target: TargetPage" in code

    def test_date_picker_inherits_date_picker_component(self):
        steps = [{"action": "click", "selector": "input.date-picker"}]
        code = generate_python_code(
            platform="test", component_type="date_picker", component_name="date_picker", steps=steps,
        )
        assert "DatePickerComponent" in code
        assert "DatePickResult" in code
        assert "DateOption" in code
        assert "option: DateOption" in code

    def test_unknown_type_inherits_component_base(self):
        steps = [{"action": "click", "selector": "button.do"}]
        code = generate_python_code(
            platform="test", component_type="custom_action", component_name="my_action", steps=steps,
        )
        assert "ComponentBase" in code
        assert "ResultBase" in code


class TestWaitStepNetworkIdle:
    """7.4 wait 步骤生成 networkidle 测试。"""

    def test_wait_default_networkidle(self):
        steps = [{"action": "wait", "timeout": 3000}]
        code = generate_python_code(
            platform="test", component_type="navigation", component_name="nav", steps=steps,
        )
        assert "networkidle" in code
        assert "domcontentloaded" not in code or "wait_for_load_state" in code


class TestCaptchaPostStepsReorder:
    """7.5 验证码后非验证码步骤保留测试。"""

    def test_post_captcha_steps_reordered_before_raise(self):
        steps = [
            {"action": "fill", "selector": "input[name=username]", "value": "{{account.username}}"},
            {"action": "fill", "selector": "input.captcha-text", "value": "1234", "step_group": "captcha_graphical"},
            {"action": "click", "selector": "input.remember-me"},
        ]
        code = generate_python_code(
            platform="test", component_type="login", component_name="login", steps=steps,
        )
        assert "VerificationRequiredError" in code
        assert "[reorder]" in code
        reorder_idx = code.find("[reorder]")
        raise_idx = code.find("raise VerificationRequiredError")
        assert reorder_idx < raise_idx, "Reordered steps should appear before raise"


class TestCaptchaResumeUrlConfigurable:
    """7.6 验证码恢复块 URL 判断可配置测试。"""

    def test_with_success_criteria(self):
        steps = _steps_login_with_captcha()
        code = generate_python_code(
            platform="test", component_type="login", component_name="login",
            steps=steps, success_criteria={"url_contains": "/dashboard"},
        )
        assert "'/dashboard' in cur" in code
        assert "TODO: configure" not in code

    def test_without_success_criteria(self):
        steps = _steps_login_with_captcha()
        code = generate_python_code(
            platform="test", component_type="login", component_name="login",
            steps=steps, success_criteria=None,
        )
        assert "TODO: configure success URL condition" in code


class TestSelectorFromSelectorsUnique:
    """7.7 _selector_from_selectors unique 降级逻辑测试。"""

    def test_prefers_unique_selector(self):
        from backend.services.steps_to_python import _selector_from_selectors
        selectors = [
            {"type": "role", "value": 'button[name="Login"]', "unique": False},
            {"type": "placeholder", "value": "username", "unique": True},
        ]
        result = _selector_from_selectors(selectors)
        assert result == "placeholder=username"

    def test_fallback_to_first_when_all_non_unique(self):
        from backend.services.steps_to_python import _selector_from_selectors
        selectors = [
            {"type": "role", "value": 'button[name="Login"]', "unique": False},
            {"type": "text", "value": "Login", "unique": False},
        ]
        result = _selector_from_selectors(selectors)
        assert result == 'role=button[name="Login"]'

    def test_unique_true_by_default(self):
        from backend.services.steps_to_python import _selector_from_selectors
        selectors = [
            {"type": "text", "value": "Submit"},
        ]
        result = _selector_from_selectors(selectors)
        assert result == "text=Submit"
