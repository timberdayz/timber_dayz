"""提成公式**单源**守护：同一句公式不得在多处独立实现。

背景（ADR-2026-11-21）：提成公式曾被独立实现 5 处，其中 1 处漏乘系数、
1 处少 formal 店铺过滤 ⇒ 同一笔提成在不同页面/工资单上对不上。

现在提成公式的**唯一实现处**是
:mod:`backend.services.commission_caliber`。本守护做源码扫描：
一旦有人在别处重新抄一遍公式（比如 ``max(x, 0) * rate * ratio``），
测试即失败，阻断合并。
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 提成公式的真源模块
CALIBER_MODULE = "backend/services/commission_caliber.py"

#: 允许出现提成公式字面量的文件（真源 + 本守护自身）
ALLOWED_FILES = {
    CALIBER_MODULE,
    "backend/tests/test_commission_single_source.py",
    "backend/tests/test_commission_caliber.py",
}

#: 提成公式的特征字面量。
#: 只匹配「可分配利润 × 提成比」这种**逐店分摊**的乘法链；
#: 不匹配单因子（max(x, 0) 之类），避免误伤。
COMMISSION_FORMULA_PATTERNS = [
    # max(profit_basis, 0) * rate * ratio  （三种变量命名都覆盖）
    re.compile(
        r"max\(\s*\w*(?:profit_basis|basis)\w*\s*,\s*0(?:\.0)?\s*\)"
        r"\s*\*\s*\w*rate\w*\s*\*\s*\w*(?:ratio|commission_ratio)\w*"
    ),
    # allocatable_profit * ratio（可分配利润 × 提成比）
    re.compile(r"\w*allocatable_profit\w*\s*\*\s*\w*(?:ratio|commission_ratio)\w*"),
    # alloc_profit * ratio
    re.compile(r"\balloc_profit\s*\*\s*\w*(?:ratio|commission_ratio)\w*"),
]

#: 允许的例外：注释里出现公式字面量不算实现（本守护只看代码行）。
COMMENT_PREFIX = "#"


def _iter_backend_python_files():
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        yield path


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _strip_strings_and_comments(line: str) -> str:
    """去掉字符串字面量与行注释，避免「文档里写了公式」被误判。"""
    # 粗略但足够：先去掉行注释（不在字符串内的 #），再去掉引号内内容。
    out = []
    in_single = in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(" ")
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(" ")
            i += 1
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(" " if (in_single or in_double) else ch)
        i += 1
    return "".join(out)


def test_commission_formula_only_lives_in_caliber_module():
    """提成公式的字面量只允许出现在真源模块里。"""
    violations = []
    for path in _iter_backend_python_files():
        rel = _relative(path)
        if rel in ALLOWED_FILES:
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = _strip_strings_and_comments(raw)
            if not code.strip():
                continue
            for pattern in COMMISSION_FORMULA_PATTERNS:
                if pattern.search(code):
                    violations.append(f"{rel}:{lineno}: {raw.strip()}")
                    break
    assert not violations, (
        "提成公式在真源模块之外被重新实现（SSOT 违规）：\n"
        + "\n".join(violations)
        + f"\n\n真源模块：{CALIBER_MODULE}"
        + " —— 所有提成计算都必须调用 "
        "backend.services.commission_caliber 的函数，不要就地复刻公式。"
    )


def test_no_settlement_coefficient_in_commission_paths():
    """提成路径不得再出现 ``settlement_coefficient`` 乘法。

    提成已零系数（ADR-2026-11-21）：店铺赛马排名与个人分数档位
    都不参与提成金额。若这里被改回去，说明口径又漂了。
    """
    violations = []
    # 这些文件里「系数」只允许出现在注释 / 展示字段名里，
    # 不得出现在**乘法表达式**中。
    for path in _iter_backend_python_files():
        rel = _relative(path)
        if rel in ALLOWED_FILES:
            continue
        if "settlement_coefficient" not in path.read_text(encoding="utf-8"):
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = _strip_strings_and_comments(raw)
            if "settlement_coefficient" not in code:
                continue
            # 形如 ``* settlement_coefficient`` 或 ``settlement_coefficient *``
            if re.search(r"\*\s*settlement_coefficient\b", code) or re.search(
                r"\bsettlement_coefficient\s*\*", code
            ):
                violations.append(f"{rel}:{lineno}: {raw.strip()}")
    assert (
        not violations
    ), "提成路径重新乘上了 settlement_coefficient（提成应为零系数）：\n" + "\n".join(
        violations
    )


@pytest.mark.parametrize(
    "module_path",
    [
        "backend/services/hr_income_calculation_service.py",
        "backend/services/monthly_settlement_service.py",
        "backend/domains/business/routers/hr_commission.py",
        "backend/services/payroll_generation_service.py",
    ],
)
def test_caliber_consumers_import_the_single_source(module_path):
    """所有消费方都必须**导入**真源模块，而不是各自实现。"""
    path = REPO_ROOT / module_path
    assert path.exists(), f"文件不存在：{module_path}"
    text = path.read_text(encoding="utf-8")
    assert "commission_caliber" in text, (
        f"{module_path} 没有引用 commission_caliber —— "
        "提成/绩效工资口径必须走唯一真源模块。"
    )
