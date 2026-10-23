"""采集组件 lint 引擎（批次 3）。

《规范》§13 强约束的机器判定实现，是**唯一**规则来源：

- :func:`analyze_python_code`：既有 9 条代码级规则（原样搬自录制器，判定与文案一字未改）。
- :func:`analyze_component_file`：文件级分析（代码级规则 + AST 扩展 + 新增规则 + 豁免机制）。
- :func:`analyze_stable_records`：仓库级规则（stable 记录指向归档 / 缺失文件）。

引擎**导入时不连接数据库**：仓库级规则所需的 stable 记录由调用方显式传入，
或通过 :func:`load_stable_component_records` 惰性读取——DB 不可用时抛
:class:`StableRecordUnavailable`，由调用方明确跳过（禁止静默通过）。

配套设计稿：``docs/superpowers/specs/2026-10-23-collection-component-lint-gate-design.md``。
"""

from __future__ import annotations

import ast
import asyncio
import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from backend.services.active_collection_components import is_missing_component_file
from backend.services.collection_component_topology import (
    is_canonical_component_filename,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# 《规范》/ docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md:211,213
MAX_FUNCTION_LINES = 50
MAX_CLASS_LINES = 500

# 豁免理由最短长度（少于该长度视为无效豁免）
MIN_REASON_LENGTH = 4

WAIT_TIMEOUT_REASON_KEYWORDS = ("固定等待", "reason", "验证码", "回传", "动画", "节奏")
SLEEP_REASON_KEYWORDS = ("固定等待", "验证码", "回传", "等待", "reason", "节奏", "动画")
FIRST_NTH_REASON_KEYWORDS = (
    "业务语义",
    "第n",
    "nth",
    "first-nth-justified",
    "有序",
    "第 ",
)

_SWALLOW_REGEX = re.compile(r"except\s+Exception\s*:\s*pass")
_COUNT_IS_VISIBLE_REGEX = re.compile(r"count\(\)\s*>\s*0.*is_visible\(", re.DOTALL)
_FIRST_NTH_REGEX = re.compile(r"\.first\b|\.nth\(")
_INLINE_IGNORE_REGEX = re.compile(r"lint:ignore\[([^\]]*)\](.*)$")
_FILE_IGNORE_REGEX = re.compile(r"lint:ignore-file\[([^\]]*)\](.*)$")
_ANY_IGNORE_REGEX = re.compile(r"#.*lint:ignore(?:-file)?\[")
_REASON_TRIM_CHARS = "-—–:：=,，。、 \t"

# 规则族：同族规则共享豁免（豁免 error 变体时，warning 变体一并放行）
_RULE_FAMILIES: dict[str, set[str]] = {
    "wait_for_timeout_usage": {
        "wait_for_timeout_usage",
        "wait_for_timeout_with_reason",
    },
    "wait_for_timeout_with_reason": {
        "wait_for_timeout_usage",
        "wait_for_timeout_with_reason",
    },
    "fixed_sleep_usage": {"fixed_sleep_usage", "fixed_sleep_with_reason"},
    "fixed_sleep_with_reason": {"fixed_sleep_usage", "fixed_sleep_with_reason"},
    "first_nth_usage": {"first_nth_usage", "first_nth_with_reason"},
    "first_nth_with_reason": {"first_nth_usage", "first_nth_with_reason"},
}

ExemptChecker = Callable[[str, int], bool]
SwallowDetector = Callable[[str], list[tuple[int, str]]]


@dataclass(frozen=True)
class LintIssue:
    """一条 lint 命中。"""

    type: str
    severity: str
    message: str
    line: int = 0
    rule: str = ""
    file: str = ""
    count: int = 1

    def to_dict(self) -> dict:
        """文件级 / 仓库级返回形状（含 line / rule / file / count）。"""
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "rule": self.rule or self.type,
            "file": self.file,
            "count": self.count,
        }

    def to_legacy_dict(self) -> dict:
        """录制器兼容形状：只含 type / message。"""
        return {"type": self.type, "message": self.message}


@dataclass(frozen=True)
class StableComponentRecord:
    """core.component_versions 的一条 stable 记录（仓库级规则用）。"""

    component_name: str
    file_path: str


class StableRecordUnavailable(RuntimeError):
    """DB 不可用（模块导入失败 / 连接失败 / 查询失败）。

    调用方必须**明确跳过**仓库级规则并打印原因，不允许静默当作通过。
    """


@dataclass
class _IgnoreIndex:
    """豁免索引：行内豁免 + 文件级豁免 + 无效豁免清单。"""

    inline: dict[int, set[str]] = field(default_factory=dict)
    file_rules: set[str] = field(default_factory=set)
    invalid: list[LintIssue] = field(default_factory=list)

    def is_exempt(self, rule: str, line: int) -> bool:
        """该行该规则是否被豁免（行内豁免或文件级豁免）。

        行内豁免作用范围：注释所在行 + 其下一行。
        这样 ``# lint:ignore[rule] —— 理由`` 无论写成行尾注释，
        还是写成违规语句的上一行注释（设计稿 §5.1 的示例形态），都能命中。
        """
        if not rule:
            return False
        family = _rule_family(rule)
        if family & self.file_rules:
            return True
        for anchor in (line, line - 1):
            line_rules = self.inline.get(anchor)
            if line_rules and (family & line_rules):
                return True
        return False


def _rule_family(rule: str) -> set[str]:
    """规则族（同族共享豁免）。"""
    return _RULE_FAMILIES.get(rule, {rule})


def _has_reason_comment(
    lines: Sequence[str], index: int, reason_keywords: Sequence[str]
) -> bool:
    """检查当前行及前两行是否存在「理由」注释。

    与录制器原实现语义完全一致（原为内嵌闭包，此处提为模块级函数复用）。
    """
    start = max(0, index - 2)
    for j in range(start, index + 1):
        text = lines[j].strip().lower()
        if not text.startswith("#"):
            continue
        if any(k.lower() in text for k in reason_keywords):
            return True
    return False


def _is_exempt(exempt: ExemptChecker | None, rule: str, line: int) -> bool:
    """判定某行某规则是否被豁免（含同族规则）。"""
    if exempt is None:
        return False
    return any(exempt(member, line) for member in _rule_family(rule))


def _regex_swallow_occurrences(python_code: str) -> list[tuple[int, str]]:
    """既有正则判定（只覆盖 pass 形态），返回 (行号, 形态)。"""
    match = _SWALLOW_REGEX.search(python_code)
    if not match:
        return []
    return [(python_code[: match.start()].count("\n") + 1, "pass")]


def _ast_swallow_occurrences(tree: ast.AST) -> list[tuple[int, str]]:
    """AST 判定：捕获 Exception 的 handler 里出现 pass / 末条 continue / 末条 return。"""
    occurrences: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _catches_exception(node):
            continue
        form = _swallow_form(node)
        if form:
            occurrences.append((node.lineno, form))
    return sorted(occurrences)


def _catches_exception(handler: ast.ExceptHandler) -> bool:
    """handler 是否捕获 Exception（与既有正则口径一致）。"""
    if handler.type is None:
        return False
    if isinstance(handler.type, ast.Name):
        return handler.type.id == "Exception"
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(el, ast.Name) and el.id == "Exception"
            for el in handler.type.elts
        )
    return False


def _swallow_form(handler: ast.ExceptHandler) -> str | None:
    """吞异常形态：pass / continue / return；不是吞异常则返回 None。"""
    body = list(handler.body)
    if not body:
        return None
    if any(isinstance(stmt, ast.Pass) for stmt in body):
        return "pass"
    last = body[-1]
    if isinstance(last, ast.Continue):
        return "continue"
    if isinstance(last, ast.Return):
        return "return"
    return None


def _swallow_message(form: str) -> str:
    """吞异常提示文案（pass 形态与既有文案一字不差）。"""
    if form == "pass":
        return "检测到 except Exception: pass。请改为记录上下文并返回可诊断错误，避免静默继续。"
    return f"检测到 except Exception: {form}。请改为记录上下文并返回可诊断错误，避免静默继续。"


def _wait_for_timeout_hits(
    lines: Sequence[str], exempt: ExemptChecker | None
) -> list[LintIssue]:
    """wait_for_timeout 规则（无理由=error，有理由=warning）。"""
    indices = [i for i, line in enumerate(lines) if "wait_for_timeout(" in line]
    kept = [i for i in indices if not _is_exempt(exempt, "wait_for_timeout_usage", i)]
    unreasoned = [
        i
        for i in kept
        if not _has_reason_comment(lines, i, WAIT_TIMEOUT_REASON_KEYWORDS)
    ]
    if unreasoned:
        return [
            LintIssue(
                type="wait_for_timeout_usage",
                severity=SEVERITY_ERROR,
                message=(
                    f"检测到 {len(unreasoned)} 处无理由 wait_for_timeout。"
                    "请改为条件等待，或补充明确固定等待原因注释。"
                ),
                line=unreasoned[0] + 1,
                count=len(unreasoned),
            )
        ]
    if kept:
        return [
            LintIssue(
                type="wait_for_timeout_with_reason",
                severity=SEVERITY_WARNING,
                message=(
                    f"检测到 {len(kept)} 处有理由的 wait_for_timeout。"
                    "建议评估是否可进一步改为条件等待。"
                ),
                line=kept[0] + 1,
                count=len(kept),
            )
        ]
    return []


def _fixed_sleep_hits(
    lines: Sequence[str], exempt: ExemptChecker | None
) -> list[LintIssue]:
    """固定 sleep 规则（无理由=error，有理由=warning）。"""
    indices = [
        i
        for i, line in enumerate(lines)
        if ("time.sleep(" in line or "asyncio.sleep(" in line)
    ]
    kept = [i for i in indices if not _is_exempt(exempt, "fixed_sleep_usage", i)]
    unreasoned = [
        i for i in kept if not _has_reason_comment(lines, i, SLEEP_REASON_KEYWORDS)
    ]
    if unreasoned:
        return [
            LintIssue(
                type="fixed_sleep_usage",
                severity=SEVERITY_ERROR,
                message=(
                    f"检测到 {len(unreasoned)} 处无理由固定 sleep。"
                    "请优先使用条件等待；若确需固定延时，请注释说明原因。"
                ),
                line=unreasoned[0] + 1,
                count=len(unreasoned),
            )
        ]
    if kept:
        return [
            LintIssue(
                type="fixed_sleep_with_reason",
                severity=SEVERITY_WARNING,
                message=(
                    f"检测到 {len(kept)} 处有理由固定 sleep。"
                    "建议评估是否可替换为条件等待。"
                ),
                line=kept[0] + 1,
                count=len(kept),
            )
        ]
    return []


def _count_is_visible_hits(
    python_code: str, exempt: ExemptChecker | None
) -> list[LintIssue]:
    """count()+is_visible() 单次判断规则。"""
    occurrences = [
        python_code[: match.start()].count("\n") + 1
        for match in _COUNT_IS_VISIBLE_REGEX.finditer(python_code)
    ]
    kept = [
        ln
        for ln in occurrences
        if not _is_exempt(exempt, "count_is_visible_pattern", ln)
    ]
    if not kept:
        return []
    return [
        LintIssue(
            type="count_is_visible_pattern",
            severity=SEVERITY_ERROR,
            message="检测到 count()+is_visible() 单次判断。请改为 expect()/wait_for() 可重试等待。",
            line=kept[0],
            count=len(kept),
        )
    ]


def _swallow_hits(
    python_code: str,
    exempt: ExemptChecker | None,
    detector: SwallowDetector | None,
) -> list[LintIssue]:
    """吞异常规则（默认用既有正则，文件级分析改用 AST 判定）。"""
    detect = detector or _regex_swallow_occurrences
    issues: list[LintIssue] = []
    for line, form in detect(python_code):
        if _is_exempt(exempt, "swallow_exception_pattern", line):
            continue
        issues.append(
            LintIssue(
                type="swallow_exception_pattern",
                severity=SEVERITY_ERROR,
                message=_swallow_message(form),
                line=line,
            )
        )
    return issues


def _first_nth_hits(
    lines: Sequence[str], exempt: ExemptChecker | None
) -> list[LintIssue]:
    """.first / .nth( 规则（无业务语义注释=error，有注释=warning）。"""
    indices = [i for i, line in enumerate(lines) if _FIRST_NTH_REGEX.search(line)]
    kept = [i for i in indices if not _is_exempt(exempt, "first_nth_usage", i)]
    unreasoned = [
        i for i in kept if not _has_reason_comment(lines, i, FIRST_NTH_REASON_KEYWORDS)
    ]
    if unreasoned:
        return [
            LintIssue(
                type="first_nth_usage",
                severity=SEVERITY_ERROR,
                message=(
                    f"检测到 {len(unreasoned)} 处无注释依据的 .first/.nth。"
                    "请先收敛作用域，或补充业务语义注释后再使用。"
                ),
                line=unreasoned[0] + 1,
                count=len(unreasoned),
            )
        ]
    if kept:
        return [
            LintIssue(
                type="first_nth_with_reason",
                severity=SEVERITY_WARNING,
                message=(
                    f"检测到 {len(kept)} 处有注释依据的 .first/.nth，"
                    "请确认该场景确有业务顺序语义。"
                ),
                line=kept[0] + 1,
                count=len(kept),
            )
        ]
    return []


def _evaluate_code_rules(
    python_code: str,
    *,
    exempt: ExemptChecker | None = None,
    swallow_detector: SwallowDetector | None = None,
) -> list[LintIssue]:
    """执行既有 9 条代码级规则。

    exempt(rule, line) -> bool：该行该规则是否被豁免（仅文件级分析传入）。
    swallow_detector：吞异常判定器，默认使用既有正则（保证录制器路径行为零变化）。
    """
    lines = python_code.splitlines()
    issues: list[LintIssue] = []
    issues.extend(_wait_for_timeout_hits(lines, exempt))
    issues.extend(_fixed_sleep_hits(lines, exempt))
    issues.extend(_count_is_visible_hits(python_code, exempt))
    issues.extend(_swallow_hits(python_code, exempt, swallow_detector))
    issues.extend(_first_nth_hits(lines, exempt))
    return issues


def analyze_python_code(python_code: str) -> dict:
    """既有 9 条代码级规则（原样搬自录制器，判定与文案一字未改）。

    返回 ``{"errors": [...], "warnings": [...]}``，每项形如
    ``{"type": ..., "message": ...}``（与录制器完全一致的形状）。
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    if not python_code:
        return {"errors": errors, "warnings": warnings}

    try:
        ast.parse(python_code)
    except SyntaxError as exc:
        logger.error("Python syntax error in lint check: %s", exc)
        errors.append({"type": "syntax_error", "message": str(exc)})
        return {"errors": errors, "warnings": warnings}

    for issue in _evaluate_code_rules(python_code):
        if issue.severity == SEVERITY_ERROR:
            errors.append(issue.to_legacy_dict())
        else:
            warnings.append(issue.to_legacy_dict())

    return {"errors": errors, "warnings": warnings}


def _iter_comments(source: str) -> list[tuple[int, str]]:
    """返回 (行号, 注释文本) 列表；tokenize 失败时退化为正则扫描。"""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return [
            (tok.start[0], tok.string) for tok in tokens if tok.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        return _scan_comments_by_regex(source)


def _scan_comments_by_regex(source: str) -> list[tuple[int, str]]:
    """tokenize 不可用时的兜底：只找含 lint:ignore 的注释行。"""
    found: list[tuple[int, str]] = []
    for idx, line in enumerate(source.splitlines(), start=1):
        match = _ANY_IGNORE_REGEX.search(line)
        if match:
            found.append((idx, line[match.start() :]))
    return found


def _parse_ignore_rules(raw: str) -> list[str]:
    """解析豁免规则名列表（逗号分隔）。"""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalize_reason(text: str) -> str:
    """取出豁免理由文本（去掉开头的装饰符号与空白）。"""
    cleaned = str(text or "").strip()
    while cleaned and cleaned[0] in _REASON_TRIM_CHARS:
        cleaned = cleaned[1:].strip()
    return cleaned


def _invalid_ignore_issue(line: int, detail: str) -> LintIssue:
    """无效豁免提示（error）。"""
    return LintIssue(
        type="invalid_ignore_comment",
        severity=SEVERITY_ERROR,
        message=f"无效豁免注释：{detail}。无效豁免不生效，请补全后重试。",
        line=line,
    )


def _collect_ignores(source: str, tree: ast.Module | None) -> _IgnoreIndex:
    """解析行内 / 文件级豁免，并检出无效豁免。"""
    index = _IgnoreIndex()
    for line_no, comment in _iter_comments(source):
        file_match = _FILE_IGNORE_REGEX.search(comment)
        if file_match:
            _apply_file_ignore(index, line_no, file_match, tree)
            continue
        inline_match = _INLINE_IGNORE_REGEX.search(comment)
        if inline_match:
            _apply_inline_ignore(index, line_no, inline_match)
    return index


def _apply_file_ignore(
    index: _IgnoreIndex,
    line_no: int,
    match: re.Match,
    tree: ast.Module | None,
) -> None:
    """文件级豁免：必须放在文件首行或模块 docstring 之后，且必须带理由。"""
    rules = _parse_ignore_rules(match.group(1))
    if not rules:
        index.invalid.append(_invalid_ignore_issue(line_no, "文件级豁免未指定规则名"))
        return
    if not _is_file_ignore_position(line_no, tree):
        index.invalid.append(
            _invalid_ignore_issue(
                line_no, "文件级豁免必须放在文件首行或模块 docstring 之后"
            )
        )
        return
    if len(_normalize_reason(match.group(2))) < MIN_REASON_LENGTH:
        index.invalid.append(
            _invalid_ignore_issue(line_no, "文件级豁免缺少有效理由（需至少 4 个字符）")
        )
        return
    index.file_rules.update(rules)


def _is_file_ignore_position(line_no: int, tree: ast.Module | None) -> bool:
    """文件级豁免位置是否合法（位于任何真实代码之前）。"""
    if tree is None or not tree.body:
        return line_no == 1
    first_code_line = tree.body[0].lineno
    for stmt in tree.body:
        if _is_module_docstring(stmt):
            continue
        first_code_line = stmt.lineno
        break
    else:
        first_code_line = 10**9
    return line_no < first_code_line


def _is_module_docstring(stmt: ast.stmt) -> bool:
    """判断语句是否为模块 docstring。"""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _apply_inline_ignore(index: _IgnoreIndex, line_no: int, match: re.Match) -> None:
    """行内豁免：必须带理由，否则视为无效豁免（不生效）。"""
    rules = _parse_ignore_rules(match.group(1))
    if not rules:
        index.invalid.append(_invalid_ignore_issue(line_no, "行内豁免未指定规则名"))
        return
    if len(_normalize_reason(match.group(2))) < MIN_REASON_LENGTH:
        index.invalid.append(
            _invalid_ignore_issue(line_no, "行内豁免缺少有效理由（需至少 4 个字符）")
        )
        return
    index.inline.setdefault(line_no, set()).update(rules)


def _apply_ignores(issues: list[LintIssue], index: _IgnoreIndex) -> list[LintIssue]:
    """按豁免索引过滤命中（invalid_ignore_comment 自身不可豁免）。"""
    kept: list[LintIssue] = []
    for issue in issues:
        if issue.type == "invalid_ignore_comment":
            kept.append(issue)
            continue
        if index.is_exempt(issue.type, issue.line):
            continue
        kept.append(issue)
    return kept


def _defines_run_method(node: ast.ClassDef) -> bool:
    """类是否定义了 run 方法。"""
    return any(
        isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "run"
        for stmt in node.body
    )


def _base_name(base: ast.expr) -> str:
    """基类名（只取最后一段）。"""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return ""


def _has_class_attr(node: ast.ClassDef, attr: str) -> bool:
    """类体是否直接赋值了指定类属性。"""
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == attr:
                    return True
        elif isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            if isinstance(target, ast.Name) and target.id == attr:
                return True
    return False


def _inherits_component_base(node: ast.ClassDef) -> bool:
    """是否直接继承 ComponentBase。"""
    return any(_base_name(base) == "ComponentBase" for base in node.bases)


def _is_component_class(node: ast.ClassDef) -> bool:
    """是否为采集组件类（定义 run 方法，且具备组件特征）。"""
    if not _defines_run_method(node):
        return False
    if _inherits_component_base(node):
        return True
    if _has_class_attr(node, "component_type") or _has_class_attr(node, "platform"):
        return True
    return any("component" in _base_name(base).lower() for base in node.bases)


def _component_classes(tree: ast.AST) -> list[ast.ClassDef]:
    """文件内所有采集组件类。"""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and _is_component_class(node)
    ]


def _count_report_step_calls(tree: ast.AST) -> int:
    """统计 report_step() 调用次数。"""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "report_step":
            count += 1
        elif isinstance(func, ast.Name) and func.id == "report_step":
            count += 1
    return count


def _missing_report_step_hits(tree: ast.AST) -> list[LintIssue]:
    """规则 #1：组件类定义了 run() 但整个文件零 report_step() 调用。"""
    classes = _component_classes(tree)
    if not classes:
        return []
    if _count_report_step_calls(tree) > 0:
        return []
    return [
        LintIssue(
            type="missing_report_step",
            severity=SEVERITY_ERROR,
            message=(
                "组件类定义了 run() 但整个文件没有任何 report_step() 调用，"
                "关键步骤进度无法上报。"
            ),
            line=classes[0].lineno,
        )
    ]


def _missing_logger_usage_hits(tree: ast.AST, source: str) -> list[LintIssue]:
    """规则 #2：组件类未使用 self.logger / self._log。"""
    classes = [
        node
        for node in _component_classes(tree)
        if _inherits_component_base(node) or _has_class_attr(node, "component_type")
    ]
    if not classes:
        return []
    if "self.logger" in source or "self._log" in source:
        return []
    return [
        LintIssue(
            type="missing_logger_usage",
            severity=SEVERITY_WARNING,
            message=(
                "组件类未使用 self.logger / self._log，" "失败时无法留下可诊断日志。"
            ),
            line=classes[0].lineno,
        )
    ]


def _oversized_function_hits(tree: ast.AST) -> list[LintIssue]:
    """规则 #3：函数超过 50 行。"""
    issues: list[LintIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        if length > MAX_FUNCTION_LINES:
            issues.append(
                LintIssue(
                    type="oversized_function",
                    severity=SEVERITY_ERROR,
                    message=(
                        f"函数 {node.name} 共 {length} 行，超过 {MAX_FUNCTION_LINES} 行上限，"
                        "请拆分。"
                    ),
                    line=node.lineno,
                )
            )
    return sorted(issues, key=lambda item: item.line)


def _oversized_class_hits(tree: ast.AST) -> list[LintIssue]:
    """规则 #4：类超过 500 行。"""
    issues: list[LintIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        if length > MAX_CLASS_LINES:
            issues.append(
                LintIssue(
                    type="oversized_class",
                    severity=SEVERITY_ERROR,
                    message=(
                        f"类 {node.name} 共 {length} 行，超过 {MAX_CLASS_LINES} 行上限，"
                        "请拆分。"
                    ),
                    line=node.lineno,
                )
            )
    return sorted(issues, key=lambda item: item.line)


def _navigation_signal_kinds(tree: ast.AST, source: str) -> set[str]:
    """导航就绪信号种类（按种类去重）。"""
    kinds: set[str] = set()
    if "wait_for_selector(" in source:
        kinds.add("wait_for_selector")
    if "wait_for_load_state(" in source:
        kinds.add("wait_for_load_state")
    if "wait_for_url(" in source:
        kinds.add("wait_for_url")
    if "expect_" in source:
        kinds.add("expect_")
    if re.search(r"wait_for\([^)]*state\s*=\s*[\"']visible[\"']", source, re.DOTALL):
        kinds.add("wait_for_visible")
    if _has_url_comparison(tree):
        kinds.add("url_change")
    return kinds


def _has_url_comparison(tree: ast.AST) -> bool:
    """是否存在 page.url 出现在比较表达式里的 URL 变化判断。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            for sub in ast.walk(operand):
                if isinstance(sub, ast.Attribute) and sub.attr == "url":
                    return True
    return False


def _single_signal_navigation_hits(
    tree: ast.AST, source: str, path: Path
) -> list[LintIssue]:
    """规则 #7：导航组件只有单一就绪信号。"""
    stem = path.stem.lower()
    if "navigation" not in stem and "nav" not in stem:
        return []
    kinds = _navigation_signal_kinds(tree, source)
    if len(kinds) >= 2:
        return []
    detail = "、".join(sorted(kinds)) if kinds else "无"
    return [
        LintIssue(
            type="single_signal_navigation",
            severity=SEVERITY_WARNING,
            message=(
                f"导航组件只用了 {len(kinds)} 种就绪信号（{detail}），"
                "缺少「URL 变化 + 元素可见」双信号。"
            ),
            line=1,
        )
    ]


def _unbounded_action_calls(tree: ast.AST) -> list[int]:
    """click() / wait_for() 调用中未带 timeout= 参数的行号。"""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in {
            "click",
            "wait_for",
        }:
            continue
        if any(kw.arg == "timeout" for kw in node.keywords):
            continue
        lines.append(node.lineno)
    return sorted(lines)


def _has_timeout_constant(tree: ast.AST) -> bool:
    """文件内是否存在带 timeout 的常量定义。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "timeout" in target.id.lower():
                    return True
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and "timeout" in target.id.lower():
                return True
    return False


def _missing_retry_budget_hits(tree: ast.AST, source: str) -> list[LintIssue]:
    """规则 #8：缺少显式重试预算声明。"""
    unbounded = _unbounded_action_calls(tree)
    if not unbounded:
        return []
    if "RetryStrategy" in source:
        return []
    if _has_timeout_constant(tree):
        return []
    return [
        LintIssue(
            type="missing_retry_budget",
            severity=SEVERITY_WARNING,
            message=(
                "存在未设置 timeout 的 click()/wait_for() 调用，"
                "且文件内既无 RetryStrategy 也无 timeout 常量声明，缺少显式重试预算。"
            ),
            line=unbounded[0],
        )
    ]


def _file_level_hits(tree: ast.AST, source: str, path: Path) -> list[LintIssue]:
    """文件级规则汇总。"""
    issues: list[LintIssue] = []
    issues.extend(_missing_report_step_hits(tree))
    issues.extend(_missing_logger_usage_hits(tree, source))
    issues.extend(_oversized_function_hits(tree))
    issues.extend(_oversized_class_hits(tree))
    issues.extend(_single_signal_navigation_hits(tree, source, path))
    issues.extend(_missing_retry_budget_hits(tree, source))
    return issues


def _platform_from_path(path: Path) -> str:
    """从 modules/platforms/<platform>/... 路径中取平台名。"""
    parts = [part.lower() for part in Path(path).parts]
    for idx, part in enumerate(parts):
        if part == "platforms" and idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _repo_level_hits(
    path: Path, stable_records: Sequence[StableComponentRecord] | None
) -> list[LintIssue]:
    """规则 #5：canonical 组件缺少 stable 记录。"""
    if stable_records is None:
        return []
    if not is_canonical_component_filename(path.name):
        return []
    platform = _platform_from_path(path)
    if not platform:
        return []
    component_name = f"{platform}/{path.stem}"
    known = {record.component_name for record in stable_records}
    if component_name in known:
        return []
    return [
        LintIssue(
            type="missing_stable_component_record",
            severity=SEVERITY_ERROR,
            message=(
                f"canonical 组件 {component_name} 在 core.component_versions 里"
                "没有 is_stable=True 的记录。"
            ),
            line=1,
        )
    ]


def _parse_module(source: str) -> ast.Module | None:
    """解析模块；语法错误返回 None。"""
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _syntax_error_issues(source: str) -> list[LintIssue]:
    """语法错误提示（复用既有代码级规则的文案）。"""
    legacy = analyze_python_code(source)
    return [
        LintIssue(
            type=item["type"],
            severity=SEVERITY_ERROR,
            message=item["message"],
            line=1,
        )
        for item in legacy["errors"]
    ]


def _issues_to_result(issues: Iterable[LintIssue], file_path: str = "") -> dict:
    """把命中列表转成 {"errors": [...], "warnings": [...]}。"""
    errors: list[dict] = []
    warnings: list[dict] = []
    for issue in issues:
        payload = issue.to_dict()
        if not payload["file"]:
            payload["file"] = file_path
        if issue.severity == SEVERITY_ERROR:
            errors.append(payload)
        else:
            warnings.append(payload)
    return {"errors": errors, "warnings": warnings}


def analyze_component_file(
    path: Path,
    *,
    stable_records: Sequence[StableComponentRecord] | None = None,
) -> dict:
    """单文件分析：代码级规则 + AST 扩展 + 新增文件级规则 + 豁免机制。

    返回 ``{"errors": [...], "warnings": [...]}``，每项含 type / severity /
    message / line / rule / file / count。
    """
    file_path = Path(path)
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        issue = LintIssue(
            type="unreadable_file",
            severity=SEVERITY_ERROR,
            message=f"无法读取采集组件文件：{exc}",
            line=1,
        )
        return _issues_to_result([issue], str(file_path))

    tree = _parse_module(source)
    index = _collect_ignores(source, tree)
    issues: list[LintIssue] = list(index.invalid)
    if tree is None:
        issues.extend(_syntax_error_issues(source))
        return _issues_to_result(issues, str(file_path))

    issues.extend(
        _evaluate_code_rules(
            source,
            exempt=index.is_exempt,
            swallow_detector=lambda code: _ast_swallow_occurrences(tree),
        )
    )
    issues.extend(_file_level_hits(tree, source, file_path))
    issues.extend(_repo_level_hits(file_path, stable_records))
    issues = _apply_ignores(issues, index)
    return _issues_to_result(issues, str(file_path))


def analyze_stable_records(
    records: Iterable[StableComponentRecord],
    *,
    project_root: Path | None = None,
) -> dict:
    """规则 #6：stable 记录指向 archive/ 或磁盘上已不存在的文件。

    判定直接复用 ``backend.services.active_collection_components.is_missing_component_file``。
    """
    issues: list[LintIssue] = []
    for record in records:
        if not is_missing_component_file(record.file_path, project_root=project_root):
            continue
        issues.append(
            LintIssue(
                type="stable_points_to_archived_file",
                severity=SEVERITY_ERROR,
                message=(
                    f"stable 记录 {record.component_name} 指向已归档或缺失的文件："
                    f"{record.file_path}"
                ),
                line=1,
                file=record.file_path,
            )
        )
    return _issues_to_result(issues)


async def _fetch_stable_rows(session_factory, model, select_fn) -> list:
    """读取 is_stable=True 的组件版本记录。"""
    async with session_factory() as session:
        result = await session.execute(
            select_fn(model).where(model.is_stable.is_(True))
        )
        return list(result.scalars().all())


def load_stable_component_records() -> list[StableComponentRecord]:
    """惰性读取 core.component_versions 的 stable 记录。

    引擎导入时不连接数据库；调用本函数才会建立连接。
    DB 不可用时抛 :class:`StableRecordUnavailable`，由调用方明确跳过。
    """
    try:
        from sqlalchemy import select

        from backend.models.database import AsyncSessionLocal
        from modules.core.db.schema import ComponentVersion
    except Exception as exc:  # pragma: no cover - 取决于运行环境
        raise StableRecordUnavailable(f"数据库模块导入失败：{exc}") from exc

    try:
        rows = asyncio.run(
            _fetch_stable_rows(AsyncSessionLocal, ComponentVersion, select)
        )
    except Exception as exc:
        raise StableRecordUnavailable(f"数据库查询失败：{exc}") from exc

    return [
        StableComponentRecord(
            component_name=str(getattr(row, "component_name", "") or ""),
            file_path=str(getattr(row, "file_path", "") or ""),
        )
        for row in rows
    ]
