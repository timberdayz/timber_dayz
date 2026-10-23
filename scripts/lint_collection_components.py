#!/usr/bin/env python3
"""采集组件 lint CLI（批次 3，阶段一告警模式）。

把《规范》§13 的强约束做成机器 lint，对手写组件（``modules/platforms/**``）生效，
不依赖录制器保存路径。

用法::

    python scripts/lint_collection_components.py
    python scripts/lint_collection_components.py --paths "a.py b.py" --fail-on none
    python scripts/lint_collection_components.py --format json --severity error

退出码：0 = 通过；1 = 命中 error 级问题；2 = 执行异常（配置或依赖问题）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _entry in (str(PROJECT_ROOT), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


def _force_utf8_output() -> None:
    """输出统一用 UTF-8（CI 已设 PYTHONUTF8=1；本地控制台码页不一致时也能正确显示）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover - 极端环境兜底
            pass


# 先固定输出编码，再导入引擎：导入期把 stdout 让给 stderr，
# 模块初始化日志不能污染 JSON 报告
_force_utf8_output()
with contextlib.redirect_stdout(sys.stderr):
    from backend.services.collection_component_lint import (  # noqa: E402
        SEVERITY_ERROR,
        SEVERITY_WARNING,
        StableComponentRecord,
        StableRecordUnavailable,
        analyze_component_file,
        analyze_stable_records,
        load_stable_component_records,
    )

EXIT_OK = 0
EXIT_HAS_ERROR = 1
EXIT_EXEC_ERROR = 2

DEFAULT_SCOPE_DIR = PROJECT_ROOT / "modules" / "platforms"
ARCHIVE_DIR_NAME = "archive"
REPO_LEVEL_RULES = ("missing_stable_component_record", "stable_points_to_archived_file")

RecordLoader = Callable[[], Sequence[StableComponentRecord]]


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="采集组件 lint 门禁（阶段一告警模式）",
    )
    parser.add_argument(
        "--paths",
        action="append",
        default=None,
        help="要检查的文件/目录，可重复传参；支持空格（CI 格式）、逗号、换行分隔",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="只检查相对基线被改动过的组件",
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="--changed-only 的比较基线，默认 origin/main",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "all"],
        default="all",
        help="最低报告级别，默认 all",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式，默认 text",
    )
    parser.add_argument(
        "--fail-on",
        choices=["error", "none"],
        default="error",
        help="命中 error 时是否以非 0 退出码结束，默认 error",
    )
    return parser


def split_path_tokens(raw: str) -> list[str]:
    """把路径参数切成 token（兼容空格 / 逗号 / 换行分隔）。"""
    normalized = str(raw or "").replace(",", " ").replace("\n", " ").replace("\r", " ")
    tokens: list[str] = []
    for token in normalized.split():
        cleaned = token.strip("'\"")
        if cleaned:
            tokens.append(cleaned)
    return tokens


def iter_default_scope() -> list[Path]:
    """默认扫描范围：modules/platforms/**（排除 archive/）。"""
    if not DEFAULT_SCOPE_DIR.exists():
        return []
    files: list[Path] = []
    for path in sorted(DEFAULT_SCOPE_DIR.rglob("*.py")):
        if ARCHIVE_DIR_NAME in path.parts:
            continue
        files.append(path)
    return files


def resolve_candidate_files(raw_paths: Sequence[str] | None) -> list[Path]:
    """把 --paths 参数解析成待检查的文件列表。"""
    if not raw_paths:
        return iter_default_scope()
    files: list[Path] = []
    seen: set[str] = set()
    for raw in raw_paths:
        for token in split_path_tokens(raw):
            candidate = Path(token)
            if not candidate.is_absolute():
                candidate = PROJECT_ROOT / token
            if candidate.is_dir():
                targets = sorted(candidate.rglob("*.py"))
            elif candidate.exists():
                targets = [candidate]
            else:
                print(f"[WARN] 路径不存在，已跳过：{token}", file=sys.stderr)
                continue
            for target in targets:
                key = str(target)
                if key in seen:
                    continue
                seen.add(key)
                files.append(target)
    return files


def collect_changed_files(base: str) -> list[str]:
    """复用 scripts/ci_changed_python_files.py 的改动文件检测能力。"""
    import ci_changed_python_files as changed_module

    return changed_module.changed_python_files(f"{base}..HEAD")


def filter_changed_files(files: Sequence[Path], base: str) -> list[Path]:
    """按基线过滤出被改动过的文件。"""
    changed = {path.replace("\\", "/") for path in collect_changed_files(base)}
    kept: list[Path] = []
    for path in files:
        try:
            relative = path.resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            relative = path
        if str(relative).replace("\\", "/") in changed:
            kept.append(path)
    return kept


def load_stable_records(
    loader: RecordLoader | None = None,
) -> tuple[list[StableComponentRecord] | None, str | None]:
    """读取 stable 记录；DB 不可用时返回 (None, 原因)。"""
    active_loader = loader or load_stable_component_records
    try:
        return list(active_loader()), None
    except StableRecordUnavailable as exc:
        return None, str(exc)
    except Exception as exc:  # pragma: no cover - 防御性兜底
        return None, f"{type(exc).__name__}: {exc}"


def filter_by_severity(
    errors: list[dict], warnings: list[dict], severity: str
) -> tuple[list[dict], list[dict]]:
    """按最低报告级别过滤结果。"""
    if severity == SEVERITY_ERROR:
        return list(errors), []
    return list(errors), list(warnings)


def build_summary(errors: Sequence[dict], warnings: Sequence[dict]) -> dict:
    """按规则汇总命中数。"""
    by_rule: dict[str, int] = {}
    for item in list(errors) + list(warnings):
        rule = str(item.get("rule") or item.get("type") or "unknown")
        by_rule[rule] = by_rule.get(rule, 0) + int(item.get("count", 1) or 1)
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "error_occurrences": sum(int(i.get("count", 1) or 1) for i in errors),
        "warning_occurrences": sum(int(i.get("count", 1) or 1) for i in warnings),
        "by_rule": dict(sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def render_text(
    errors: Sequence[dict],
    warnings: Sequence[dict],
    summary: dict,
    scanned: int,
    skip_reason: str | None,
) -> str:
    """文本格式报告。"""
    lines: list[str] = []
    for item in errors:
        lines.append(_format_issue("ERROR", item))
    for item in warnings:
        lines.append(_format_issue("WARN", item))
    if skip_reason:
        lines.append(
            "[SKIP] 数据库不可用，跳过 "
            + " / ".join(REPO_LEVEL_RULES)
            + f"（原因：{skip_reason}）"
        )
    lines.append("--- 汇总 ---")
    lines.append(f"扫描文件数: {scanned}")
    lines.append(
        f"error: {summary['errors']}（{summary['error_occurrences']} 处）"
        f" / warning: {summary['warnings']}（{summary['warning_occurrences']} 处）"
    )
    for rule, count in summary["by_rule"].items():
        lines.append(f"  {rule}: {count}")
    return "\n".join(lines)


def _format_issue(level: str, item: dict) -> str:
    """单条命中的文本形态。"""
    file_path = item.get("file", "")
    line = item.get("line", 0)
    rule = item.get("rule") or item.get("type", "")
    message = item.get("message", "")
    count = int(item.get("count", 1) or 1)
    suffix = f"（{count} 处）" if count > 1 else ""
    return f"[{level}] {file_path}:{line} {rule}: {message}{suffix}"


def render_json(
    errors: Sequence[dict],
    warnings: Sequence[dict],
    summary: dict,
    scanned: int,
    skip_reason: str | None,
) -> str:
    """JSON 格式报告。"""
    payload = {
        "scanned_files": scanned,
        "summary": summary,
        "errors": list(errors),
        "warnings": list(warnings),
        "skipped": (
            [{"rules": list(REPO_LEVEL_RULES), "reason": skip_reason}]
            if skip_reason
            else []
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run_lint(
    targets: Sequence[Path],
    *,
    loader: RecordLoader | None = None,
) -> tuple[list[dict], list[dict], str | None]:
    """对给定文件执行 lint，返回 (errors, warnings, skip_reason)。"""
    stable_records, skip_reason = load_stable_records(loader)
    errors: list[dict] = []
    warnings: list[dict] = []
    for path in targets:
        result = analyze_component_file(path, stable_records=stable_records)
        errors.extend(result["errors"])
        warnings.extend(result["warnings"])
    if stable_records is not None:
        repo_result = analyze_stable_records(stable_records)
        errors.extend(repo_result["errors"])
        warnings.extend(repo_result["warnings"])
    return errors, warnings, skip_reason


def _run_quiet(
    targets: Sequence[Path],
    *,
    loader: RecordLoader | None = None,
) -> tuple[list[dict], list[dict], str | None]:
    """执行 lint，期间把 stdout 让给 stderr（DB 初始化日志不能污染报告）。"""
    with contextlib.redirect_stdout(sys.stderr):
        return run_lint(targets, loader=loader)


def main(
    argv: Sequence[str] | None = None,
    *,
    loader: RecordLoader | None = None,
) -> int:
    """CLI 入口。"""
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        targets = resolve_candidate_files(args.paths)
        if args.changed_only:
            targets = filter_changed_files(targets, args.base)
    except Exception as exc:
        print(f"[ERROR] 解析检查目标失败：{exc}", file=sys.stderr)
        return EXIT_EXEC_ERROR

    errors, warnings, skip_reason = _run_quiet(targets, loader=loader)
    errors, warnings = filter_by_severity(errors, warnings, args.severity)
    summary = build_summary(errors, warnings)

    if args.format == "json":
        print(render_json(errors, warnings, summary, len(targets), skip_reason))
    else:
        print(render_text(errors, warnings, summary, len(targets), skip_reason))

    if args.fail_on == "error" and errors:
        return EXIT_HAS_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
