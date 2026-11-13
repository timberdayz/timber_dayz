#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API契约测试框架

验证内容：
1. API响应格式是否符合标准
2. 错误响应格式是否符合标准
3. 异常处理是否符合规范（AST 精确判定，不是正则猜）
4. 请求ID是否正确传递

[2026-11-13] 扫描范围与判定口径的修复（详见
``docs/superpowers/plans/2026-11-13-api-contract-gate-scope-fix.md``）：

* **扫描范围**原先停在 ``backend/routers/`` —— 那是 76 个旧门牌号（兼容垫片），
  实测里面零路由定义；82 个真正定义路由的文件早已搬到
  ``backend/domains/<业务域>/routers/``。
  于是 ``--changed-files`` 模式（发布门禁用的就是这个）**一个真实路由都匹配不到**，
  报「本次发布没有改动 router 文件，跳过验证」并绿灯放行。
* **判定口径**原先用正则找 ``try:`` + 按缩进猜块尾，报出「518 条缺错误日志」，
  而 AST 重算后真正的静默只有 50 处（9:1 的噪音比）。
  现改为 AST 精确分桶，六桶**互斥**（命中即停），口径钉在守护测试里。

  口径经**人工复核**后重新核准（2026-11-13）：上一轮统计用的临时脚本没有入库，
  「58 处」不可复现（穷举 8 组谓词变体无一命中）；按「except 块里只要有任何
  控制流决策就不算静默」这条最简口径重新核准为 **50 处 / 28 个文件**。
  数字与口径都写在纸上并被守护测试钉住 —— 这正是律 1 的由来。
"""

import sys
import ast
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# 异常处理六桶（互斥分桶，命中即停 —— 顺序不可调换，见方案 §2.6.1）
BUCKET_ORDER = ("A", "D", "B", "C", "E", "F")

BUCKET_LABELS = {
    "A": "A 记了错误日志(logger.error/exception)",
    "D": "D 显式 raise（错误带着 cause 走）",
    "B": "B 只记了其它级别的日志",
    "C": "C 结构化 error_response（正确写法）",
    "E": "E 有意降级（返回了什么/跳过了什么）",
    "F": "F 真静默（不记、不抛、不返回、不跳过）",
}

# HTTP 路由方法名（用于识别 @router.get 这类装饰器）
HTTP_METHOD_NAMES = frozenset(
    {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "websocket",
        "api_route",
    }
)


class APIContractValidator:
    """API契约验证器"""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.stats = {
            "candidate_files": 0,
            "validated_files": 0,
            "defines_router_files": 0,
            "except_blocks": 0,
            "bucket_counts": {bucket: 0 for bucket in BUCKET_ORDER},
        }

    # ------------------------------------------------------------------
    # 扫描范围：发现候选 + 路径归一化
    # ------------------------------------------------------------------

    def discover_router_files(self) -> List[Path]:
        """扫描所有候选路由文件。

        两层都在范围内：

        * ``backend/domains/<业务域>/routers/*.py`` —— 真正定义路由的实现（真源）；
        * ``backend/routers/*.py`` —— 旧门牌号（兼容垫片），实测零路由定义，
          但**保留在范围里**：万一将来有人往垫片里写路由，要能立刻抓住。

        ``__init__.py`` 一律排除（实测 5 个 ``__init__.py`` 均不含路由定义）。
        """
        candidates: List[Path] = []

        domains_root = project_root / "backend" / "domains"
        if domains_root.is_dir():
            for router_dir in sorted(domains_root.glob("*/routers")):
                if not router_dir.is_dir():
                    continue
                for py_file in sorted(router_dir.glob("*.py")):
                    if py_file.name == "__init__.py":
                        continue
                    candidates.append(py_file)

        legacy_root = project_root / "backend" / "routers"
        if legacy_root.is_dir():
            for py_file in sorted(legacy_root.glob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                candidates.append(py_file)

        return candidates

    def normalize_relative_path(self, file_path: Any) -> Optional[str]:
        """把各种写法的路径归一成「相对仓库根的 POSIX 路径」。

        支持：相对路径、``./`` 前缀、Windows 反斜杠、绝对路径。
        """
        raw = str(file_path).replace("\\", "/")

        try:
            path_obj = Path(file_path)
        except (TypeError, ValueError):
            return None

        if path_obj.is_absolute():
            try:
                return path_obj.relative_to(project_root).as_posix()
            except ValueError:
                # 不在仓库内：退而求其次，从 "backend/" 处截取
                index = raw.find("backend/")
                if index == -1:
                    return None
                raw = raw[index:]

        while raw.startswith("./"):
            raw = raw[2:]
        return raw

    def is_router_file(self, file_path: Any) -> bool:
        """判定一个路径是不是「路由文件」（在扫描范围之内）。"""
        relative = self.normalize_relative_path(file_path)
        if not relative or not relative.endswith(".py"):
            return False

        if Path(relative).name == "__init__.py":
            return False

        parts = relative.split("/")
        if len(parts) < 3 or parts[0] != "backend":
            return False

        if parts[1] == "domains":
            # backend/domains/<业务域>/routers/<文件>
            return len(parts) >= 5 and parts[3] == "routers"

        if parts[1] == "routers":
            # backend/routers/<文件>
            return len(parts) == 3

        return False

    # ------------------------------------------------------------------
    # AST 分析：异常块六桶 + 是否真的定义路由
    # ------------------------------------------------------------------

    @staticmethod
    def _read_source(file_path: Path) -> Optional[str]:
        """读文件。

        **必须用 utf-8-sig** —— 仓库里有 74 个路由文件带 UTF-8 BOM，
        而 ``ast.parse`` 对以 U+FEFF 开头的字符串直接抛 SyntaxError，
        用 ``utf-8`` 读会让这些文件被**静默跳过**（本轮统计就因此少算了 12 个文件）。
        """
        try:
            return file_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None

    @staticmethod
    def _direct_nodes(node: ast.AST):
        """遍历块内直属语句，**跳过嵌套函数/类的内部**。

        except 块里定义的内部函数，它的 ``return`` / ``raise`` 不属于
        「本块做了什么」—— 否则一个空 except 块会因为内部函数有 return
        而被误判成「有意降级」。
        """
        nested: Set[ast.AST] = set()
        for sub in ast.walk(node):
            if isinstance(
                sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
            ):
                nested.update(ast.walk(sub))
        for sub in ast.walk(node):
            if sub not in nested:
                yield sub

    @classmethod
    def _logger_levels(cls, node: ast.AST) -> Set[str]:
        """收集块内 ``logger.<level>(...)`` 的 level 集合。"""
        levels: Set[str] = set()
        for sub in cls._direct_nodes(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if not isinstance(func, ast.Attribute):
                continue
            if isinstance(func.value, ast.Name) and func.value.id == "logger":
                levels.add(func.attr)
        return levels

    @classmethod
    def _has_call_to(cls, node: ast.AST, name: str) -> bool:
        """块内是否调用了名为 ``name`` 的函数（含 ``xxx.name(...)`` 形式）。"""
        for sub in cls._direct_nodes(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if isinstance(func, ast.Name) and func.id == name:
                return True
            if isinstance(func, ast.Attribute) and func.attr == name:
                return True
        return False

    @classmethod
    def _has_raise(cls, node: ast.AST) -> bool:
        return any(isinstance(sub, ast.Raise) for sub in cls._direct_nodes(node))

    @classmethod
    def _has_degradation(cls, node: ast.AST) -> bool:
        """块内是否有「有意降级」。

        判定口径（**最简也最可辩护的一条**）：except 块里只要有任何控制流决策
        —— 返回了什么、跳过了什么 —— 就不算「静默」。
        ``return None``、``return None, None, None``、``return None, "Token expired"``
        都是「明确告诉调用方出了什么事」，属于有意降级；
        真正该拦的是**块内什么都没做**（不记、不抛、不返回、不跳过）。
        """
        return any(
            isinstance(sub, (ast.Return, ast.Continue, ast.Pass))
            for sub in cls._direct_nodes(node)
        )

    def _classify_handler(self, handler: ast.ExceptHandler) -> str:
        """把一个 except 块归入六桶之一（互斥，命中即停）。

        顺序固定为 A → D → B → C → E → F：
        先看有没有错误日志，没有就看是不是显式 raise，再看其它级别日志，
        再看结构化错误响应，再看有意降级，全不命中才是真静默。
        """
        levels = self._logger_levels(handler)
        if "error" in levels or "exception" in levels:
            return "A"
        if self._has_raise(handler):
            return "D"
        if levels:
            return "B"
        if self._has_call_to(handler, "error_response"):
            return "C"
        if self._has_degradation(handler):
            return "E"
        return "F"

    @staticmethod
    def _defines_router(tree: ast.AST) -> bool:
        """文件里是否真的定义了路由。

        判定三选一：``APIRouter(...)`` 调用 / ``@router.<method>`` 装饰器 /
        ``include_router(...)`` 调用。
        """
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func

            if isinstance(func, ast.Name) and func.id == "APIRouter":
                return True

            if isinstance(func, ast.Attribute):
                if func.attr == "include_router":
                    return True
                if func.attr in HTTP_METHOD_NAMES:
                    base = func.value
                    if isinstance(base, ast.Name) and base.id.lower().endswith(
                        "router"
                    ):
                        return True
                    if isinstance(base, ast.Attribute) and base.attr.lower().endswith(
                        "router"
                    ):
                        return True
        return False

    def analyze_except_blocks(self, file_path: Any) -> Optional[Dict[str, Any]]:
        """分析单个文件的异常处理块。

        返回 ``None`` 表示**无法解析**（读不到 / 语法错）—— 这不是「没有异常块」，
        两者必须区分，否则会把「没扫到」伪装成「没问题」。
        """
        path = Path(file_path)
        source = self._read_source(path)
        if source is None:
            return None

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return None

        buckets = {bucket: 0 for bucket in BUCKET_ORDER}
        silent: List[Dict[str, Any]] = []
        handlers = [
            node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)
        ]

        for handler in handlers:
            bucket = self._classify_handler(handler)
            buckets[bucket] += 1
            if bucket == "F":
                silent.append(
                    {
                        "file": self.normalize_relative_path(path) or str(path),
                        "line": handler.lineno,
                        "message": "except块真静默：不记日志、不抛错、不走结构化错误响应",
                    }
                )

        return {
            "file": self.normalize_relative_path(path) or str(path),
            "buckets": buckets,
            "except_block_count": len(handlers),
            "silent": silent,
            "defines_router": self._defines_router(tree),
        }

    def analyze_all_router_files(self) -> Dict[str, Any]:
        """全仓扫描：六桶计数 + 真静默明细。"""
        bucket_counts = {bucket: 0 for bucket in BUCKET_ORDER}
        except_block_count = 0
        defines_router_count = 0
        silent: List[Dict[str, Any]] = []
        parse_failures: List[str] = []

        for path in self.discover_router_files():
            analysis = self.analyze_except_blocks(path)
            if analysis is None:
                parse_failures.append(self.normalize_relative_path(path) or str(path))
                continue
            if analysis["defines_router"]:
                defines_router_count += 1
            for bucket in BUCKET_ORDER:
                bucket_counts[bucket] += analysis["buckets"][bucket]
            except_block_count += analysis["except_block_count"]
            silent.extend(analysis["silent"])

        return {
            "bucket_counts": bucket_counts,
            "except_block_count": except_block_count,
            "defines_router_count": defines_router_count,
            "candidate_count": len(self.discover_router_files()),
            "silent": silent,
            "parse_failures": parse_failures,
        }

    # ------------------------------------------------------------------
    # 契约检查
    # ------------------------------------------------------------------

    def validate_response_format(self, file_path: Path) -> List[Dict[str, Any]]:
        """验证API响应格式"""
        issues = []

        try:
            content = self._read_source(file_path)
            if content is None:
                issues.append(
                    {
                        "type": "error",
                        "file": str(file_path),
                        "line": 0,
                        "message": "读取文件失败",
                    }
                )
                return issues

            # 检查是否使用success_response
            if "success_response(" in content:
                # 检查是否正确导入
                if "from backend.utils.api_response import" not in content:
                    issues.append(
                        {
                            "type": "error",
                            "file": str(file_path),
                            "line": 0,
                            "message": "使用success_response但未导入api_response模块",
                        }
                    )

            # 检查是否使用error_response
            if "error_response(" in content:
                # 检查是否正确导入
                if "from backend.utils.api_response import" not in content:
                    issues.append(
                        {
                            "type": "error",
                            "file": str(file_path),
                            "line": 0,
                            "message": "使用error_response但未导入api_response模块",
                        }
                    )

                # 检查是否包含recovery_suggestion
                if "recovery_suggestion" not in content:
                    issues.append(
                        {
                            "type": "warning",
                            "file": str(file_path),
                            "line": 0,
                            "message": "error_response调用缺少recovery_suggestion参数",
                        }
                    )

            # HTTPException 在当前仓库仍是合法模式。
            # 这里不再把它作为阻断发布的错误，只依赖更具体的错误处理规则。

        except Exception as exc:  # pragma: no cover - 防御性兜底
            issues.append(
                {
                    "type": "error",
                    "file": str(file_path),
                    "line": 0,
                    "message": f"读取文件失败: {str(exc)}",
                }
            )

        return issues

    def validate_error_handling(self, file_path: Path) -> List[Dict[str, Any]]:
        """验证错误处理（AST 口径）。

        只有**真静默**（F 桶）算问题；其余四桶是合规或有意为之，不报。
        """
        issues = []

        analysis = self.analyze_except_blocks(file_path)
        if analysis is None:
            issues.append(
                {
                    "type": "error",
                    "file": self.normalize_relative_path(file_path) or str(file_path),
                    "line": 0,
                    "message": "AST解析失败（文件读不到或语法错）—— 门禁没看住这个文件",
                }
            )
            return issues

        for silent in analysis["silent"]:
            issues.append(
                {
                    "type": "warning",
                    "file": silent["file"],
                    "line": silent["line"],
                    "message": silent["message"],
                }
            )

        return issues

    def validate_all(self, target_files: List[Path] = None) -> Dict[str, Any]:
        """验证所有API端点（如果指定了target_files，只验证这些文件）"""
        candidates = self.discover_router_files()

        if target_files is None:
            router_files = candidates
        else:
            # 只验证指定的文件（用与全仓同一套判定，避免两套口径）
            router_files = []
            seen = set()
            for file_path in target_files:
                relative = self.normalize_relative_path(file_path)
                if not relative or not self.is_router_file(relative):
                    continue
                full_path = project_root / relative
                if full_path.exists() and full_path not in seen:
                    seen.add(full_path)
                    router_files.append(full_path)

        bucket_counts = {bucket: 0 for bucket in BUCKET_ORDER}
        except_block_count = 0
        defines_router_count = 0
        silent_details: List[Dict[str, Any]] = []

        all_issues = {
            "errors": [],
            "warnings": [],
            "validated_file_count": len(router_files),
            "candidate_count": len(candidates),
            "defines_router_count": 0,
            "except_block_count": 0,
            "bucket_counts": bucket_counts,
            "silent_details": silent_details,
        }

        for router_file in router_files:
            # 验证响应格式
            response_issues = self.validate_response_format(router_file)
            all_issues["errors"].extend(
                [i for i in response_issues if i["type"] == "error"]
            )
            all_issues["warnings"].extend(
                [i for i in response_issues if i["type"] == "warning"]
            )

            # 验证错误处理（AST 口径：只报真静默）
            error_handling_issues = self.validate_error_handling(router_file)
            all_issues["errors"].extend(
                [i for i in error_handling_issues if i["type"] == "error"]
            )
            all_issues["warnings"].extend(
                [i for i in error_handling_issues if i["type"] == "warning"]
            )

            # 汇总六桶
            analysis = self.analyze_except_blocks(router_file)
            if analysis is not None:
                if analysis["defines_router"]:
                    defines_router_count += 1
                for bucket in BUCKET_ORDER:
                    bucket_counts[bucket] += analysis["buckets"][bucket]
                except_block_count += analysis["except_block_count"]
                silent_details.extend(analysis["silent"])

        all_issues["defines_router_count"] = defines_router_count
        all_issues["except_block_count"] = except_block_count

        self.stats["candidate_files"] = len(candidates)
        self.stats["validated_files"] = len(router_files)
        self.stats["defines_router_files"] = defines_router_count
        self.stats["except_blocks"] = except_block_count
        self.stats["bucket_counts"] = bucket_counts

        return all_issues

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def generate_report(
        self, issues: Dict[str, Any], validated_file_count: int = 0
    ) -> str:
        """生成验证报告（聚合计数，不逐条刷屏）。"""
        report = []
        report.append("=" * 60)
        report.append("API契约验证报告")
        report.append("=" * 60)
        report.append("")

        error_count = len(issues["errors"])
        warning_count = len(issues["warnings"])
        candidate_count = issues.get("candidate_count", 0)
        defines_router_count = issues.get("defines_router_count", 0)

        report.append(f"扫描候选: {candidate_count} 个文件（仓库内可能的路由位置）")
        if validated_file_count > 0:
            report.append(
                f"本次验证: {validated_file_count} 个文件"
                f"（其中定义路由的: {defines_router_count} 个）"
            )
        else:
            report.append(
                "本次验证: 0 个文件"
                "（改动文件中没有 router 文件或指定文件列表为空，跳过验证）"
            )
        report.append(f"异常块总数: {issues.get('except_block_count', 0)}")
        report.append(f"错误数量: {error_count}")
        report.append(f"警告数量: {warning_count}")
        report.append("")

        bucket_counts = issues.get("bucket_counts") or {}
        if bucket_counts:
            report.append("异常处理分桶（六桶互斥，命中即停）:")
            for bucket in BUCKET_ORDER:
                marker = "  ← 需要人看" if bucket == "F" else ""
                report.append(
                    f"  {BUCKET_LABELS[bucket]}: {bucket_counts.get(bucket, 0)}{marker}"
                )
            report.append("")

        silent_details = issues.get("silent_details") or []
        if silent_details:
            per_file: Dict[str, int] = defaultdict(int)
            for item in silent_details:
                per_file[item["file"]] += 1
            report.append(
                f"真静默分布（{len(silent_details)} 处 / {len(per_file)} 个文件）:"
            )
            for file_name, count in sorted(
                per_file.items(), key=lambda kv: (-kv[1], kv[0])
            )[:10]:
                report.append(f"  {count:>3}  {file_name}")
            if len(per_file) > 10:
                report.append(f"  ... 其余 {len(per_file) - 10} 个文件见明细报告")
            report.append("")

        report.append("=" * 60)
        report.append("总结")
        report.append("=" * 60)
        if validated_file_count == 0:
            report.append("[OK] 本次发布没有改动 router 文件，跳过验证")
        elif error_count == 0 and warning_count == 0:
            report.append("[OK] 所有API端点符合契约标准！")
        elif error_count == 0:
            report.append(
                f"[WARN] 发现 0 个错误，{warning_count} 个警告"
                f"（其中真静默 {bucket_counts.get('F', 0)} 处）"
            )
        else:
            report.append(f"[ERROR] 发现 {error_count} 个错误，{warning_count} 个警告")

        return "\n".join(report)

    def write_detail_report(self, issues: Dict[str, Any]) -> Optional[Path]:
        """把完整明细写到 ``temp/validation_api_contracts.txt``。

        CI 的 Validate Data Flow 线会上传 ``temp/validation_*.txt`` 作为 artifact，
        这份明细会**自动被归档**，不需要另加 CI 配置。
        """
        detail_path = project_root / "temp" / "validation_api_contracts.txt"
        try:
            detail_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None

        lines = []
        lines.append("=" * 60)
        lines.append("API契约验证明细报告")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"扫描候选: {issues.get('candidate_count', 0)} 个文件")
        lines.append(
            f"本次验证: {issues.get('validated_file_count', 0)} 个文件"
            f"（其中定义路由的: {issues.get('defines_router_count', 0)} 个）"
        )
        lines.append(f"异常块总数: {issues.get('except_block_count', 0)}")
        lines.append(f"错误数量: {len(issues['errors'])}")
        lines.append(f"警告数量: {len(issues['warnings'])}")
        lines.append("")

        bucket_counts = issues.get("bucket_counts") or {}
        if bucket_counts:
            lines.append("-" * 60)
            lines.append("异常处理分桶（六桶互斥，命中即停）")
            lines.append("-" * 60)
            for bucket in BUCKET_ORDER:
                lines.append(
                    f"  {BUCKET_LABELS[bucket]}: {bucket_counts.get(bucket, 0)}"
                )
            lines.append("")

        if issues["errors"]:
            lines.append("-" * 60)
            lines.append("错误列表")
            lines.append("-" * 60)
            for error in issues["errors"]:
                lines.append(f"[错误] {error['file']}:{error['line']}")
                lines.append(f"  {error['message']}")
                lines.append("")

        silent_details = issues.get("silent_details") or []
        if silent_details:
            lines.append("-" * 60)
            lines.append(f"真静默明细（{len(silent_details)} 处）")
            lines.append("-" * 60)
            for item in silent_details:
                lines.append(f"[真静默] {item['file']}:{item['line']}")
                lines.append(f"  {item['message']}")
                lines.append("")

        if issues["warnings"]:
            lines.append("-" * 60)
            lines.append(f"警告明细（{len(issues['warnings'])} 条）")
            lines.append("-" * 60)
            for warning in issues["warnings"]:
                lines.append(f"[警告] {warning['file']}:{warning['line']}")
                lines.append(f"  {warning['message']}")
                lines.append("")

        try:
            detail_path.write_text("\n".join(lines), encoding="utf-8")
        except OSError:
            return None
        return detail_path


def safe_print(text):
    """安全打印函数，处理Windows终端编码问题"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows GBK编码不支持的特殊字符替换为ASCII字符
        safe_text = text.replace("✓", "[OK]").replace("✗", "[ERROR]")
        print(safe_text)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="验证API契约")
    parser.add_argument(
        "--files",
        nargs="+",
        help="只验证指定的文件列表（相对于项目根目录的路径，如 backend/domains/business/routers/xxx.py）",
    )
    parser.add_argument(
        "--changed-files",
        help="从文件读取改动的文件列表（每行一个文件路径）",
    )
    args = parser.parse_args()

    validator = APIContractValidator()

    target_files = None
    if args.files:
        target_files = [Path(f) for f in args.files]
        safe_print(f"开始验证API契约（仅验证 {len(target_files)} 个指定文件）...")
    elif args.changed_files:
        changed_files_path = Path(args.changed_files)
        if changed_files_path.exists():
            with open(changed_files_path, "r", encoding="utf-8-sig") as handle:
                target_files = [Path(line.strip()) for line in handle if line.strip()]
            safe_print(f"开始验证API契约（仅验证 {len(target_files)} 个改动文件）...")
        else:
            safe_print(
                f"[WARN] 改动文件列表不存在: {args.changed_files}，将验证所有文件"
            )
    else:
        safe_print("开始验证API契约（验证所有文件）...")

    issues = validator.validate_all(target_files)

    validated_file_count = issues.get("validated_file_count", 0)
    report = validator.generate_report(issues, validated_file_count)
    safe_print(report)

    detail_path = validator.write_detail_report(issues)
    if detail_path is not None:
        safe_print(f"[INFO] 完整明细已写入: {detail_path}")

    # 返回退出码：只看 errors（真静默是 warning，不拦发版）
    if issues["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
