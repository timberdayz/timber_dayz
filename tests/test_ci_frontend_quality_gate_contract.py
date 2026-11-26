"""前端质量门禁契约：前端测试与「未定义引用」检查必须真的在 CI 里跑。

背景
----
2026-11-20 的重构（``dd04894e``）把「员工管理」拆成独立子组件后，
父容器 ``HumanResources.vue`` 里留下了一行调用已不存在的 ``loadEmployees``：

    await Promise.all([loadDepartments(), loadPositions(), loadEmployeeNames(), loadEmployees()])

运行时抛 ``ReferenceError: loadEmployees is not defined`` ⇒ 被 catch 捕获 ⇒
页面顶部弹「加载数据失败，请刷新重试」⇒ 但**数据其实全部加载成功**
（员工列表由子组件 ``EmployeeTab.vue`` 自己加载）。

这条缺陷能进生产，暴露的是**门禁缺口**而非笔误：

* Vue SFC 的 ESLint 默认关闭 ``no-undef`` ⇒ 构建期不报、``npm run build`` 也不报；
* 前端守护测试是 ``node --test``（纯源码断言，**不挂载组件运行时**）⇒ 测试期也不报；
* ``.github/workflows/ci.yml`` 里前端只有一个 ``frontend-guard`` job，
  它只跑 ``scripts/ci_frontend_test_silence_gate.py``（检测"哑测试"），
  **前端测试本身与前端 lint 从来没有在 CI 里执行过**。

⇒ 约定必须有守护，守护必须进 CI，否则等于没写。

本守护钉住三件事
----------------
1. ``frontend-guard`` job 必须**真的跑前端测试**（``node --test``）；
2. ``frontend-guard`` job 必须**显式打开** ``no-undef`` 并对人力域执行 lint
   （人力域 = 本次修复范围，也是缺陷高发区）；
3. 本文件自己必须出现在 CI 的**根契约清单**里
   （没人调用的守护不是守护 —— 守护本身也要进 CI）。
"""

from __future__ import annotations

from pathlib import Path

CI_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _read_ci() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _frontend_guard_job_block(ci_text: str) -> str:
    """截出 ``frontend-guard`` 这个 job 的正文。"""
    marker = "  frontend-guard:"
    start = ci_text.find(marker)
    assert start != -1, "ci.yml 里找不到 frontend-guard job"
    rest = ci_text[start + len(marker) :]
    # job 之间的分隔：下一行两个空格 + 非空格的 job 名
    lines = rest.splitlines()
    block = [""]
    for line in lines:
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            break
        block.append(line)
    return "\n".join(block)


def test_frontend_guard_job_runs_frontend_tests():
    """前端测试必须真的在 CI 里跑（否则前端守护全是摆设）。"""
    block = _frontend_guard_job_block(_read_ci())
    assert "node --test" in block, (
        "frontend-guard job 必须执行前端测试（node --test）；"
        "历史上该 job 只跑「哑测试检测」，前端测试从未在 CI 里跑过"
    )


def test_frontend_guard_job_enables_no_undef_lint():
    """人力域必须显式打开 no-undef 检查。"""
    block = _frontend_guard_job_block(_read_ci())
    assert "no-undef" in block, (
        "frontend-guard job 必须显式开启 no-undef（Vue SFC 默认关闭它，"
        "『调用了不存在的函数』这类缺陷只会在运行时炸）"
    )
    assert "eslint" in block, "frontend-guard job 必须执行 eslint 检查"
    # 覆盖范围必须包含人力管理页与人力域子目录
    assert (
        "src/domains/business/views/HumanResources.vue" in block
    ), "lint 门禁必须覆盖人力管理页（本次修复的页面）"
    assert (
        "src/domains/business/views/hr" in block
    ), "lint 门禁必须覆盖人力域子目录（EmployeeTab / ShopAssignment 等）"


def test_this_contract_test_is_listed_in_root_contract_suite():
    """本守护自己必须进 CI 根契约清单。"""
    ci_text = _read_ci()
    assert (
        "tests/test_ci_frontend_quality_gate_contract.py" in ci_text
    ), "本契约文件必须出现在 ci.yml 的根契约清单里，否则它只是本地自娱自乐"
