"""模板**决策资产进 Git** 的守护（2026-11-14，批次 3）。

为什么要有这批守护
------------------
「模板定义进 Git」这件事本身很容易腐化:

* 有人把 ``version`` / ``usage_count`` 这类**运行时状态**写进定义
  ⇒ 每次巡检都产生噪音 diff, Git 里全是假变更;
* 有人复制一份定义改个名字 ⇒ 同一个维度两份定义, 谁生效说不清;
* 有人把 ``confidence`` 这种**算法产物**也提交进来
  ⇒ 重算一次就报一次假差异, 守卫会被当成噪音关掉;
* 有人改了 ``templates/`` 下的文件却没改 CI
  ⇒ 约定只写在文档里, 流水线照样全绿(「流水线绿 ≠ 验收」)。

锁住的事
--------
1. 每份定义都通过格式校验(:func:`validate_definition`);
2. 定义里**不许**出现运行时状态字段;
3. 维度键**唯一**, 且文件名与内容里的维度键一致;
4. ``header_bindings`` 里**不许**出现派生的 ``confidence``;
5. 定义文件是 UTF-8 **无 BOM** + **LF** 换行(Windows 上导出若用默认换行,
   提交进 Git 会让每个文件都是 CRLF, diff 全是噪音);
6. 决策字段名都是 ORM 的**真实列**(防拼写错误导致该字段永远为空);
7. 定义里不许混入凭据(仓库是公开的);
8. **CI 里必须真的跑这一步** —— 没人调用的守护不是守护。

这些用例全是**纯离线**的: 只读仓库文件 + import 脚本模块, 不连数据库。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.template_definitions import (  # noqa: E402
    DECISION_FIELDS,
    DERIVED_BINDING_KEYS,
    DIMENSION_FIELDS,
    RUNTIME_ONLY_FIELDS,
    TemplateDefinitionError,
    definition_file_name,
    dimension_key,
    dimension_key_text,
    load_definitions,
    validate_definition,
)

TEMPLATES_DIR = REPO_ROOT / "templates"
DEFINITIONS_DIR = TEMPLATES_DIR / "definitions"
OVERLAYS_DIR = TEMPLATES_DIR / "overlays"
README_PATH = TEMPLATES_DIR / "README.md"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: 形如 ``password: "xxx"`` / ``"token": "xxx"`` 的非空字面量。
CREDENTIAL_PATTERN = re.compile(
    r"""(?i)["']?(password|passwd|pwd|secret|token|access_key)["']?\s*[:=]\s*["']([^"']{6,})["']"""
)


def _definition_files() -> List[Path]:
    if not DEFINITIONS_DIR.is_dir():
        return []
    return sorted(DEFINITIONS_DIR.glob("*.json"))


def _load_raw(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. 格式合法 + 目录非空
# ---------------------------------------------------------------------------
def test_template_definitions_directory_is_not_empty():
    """决策资产目录必须真的有内容 —— 空目录等于「决策资产没进 Git」。"""
    files = _definition_files()
    assert files, (
        f"{DEFINITIONS_DIR.relative_to(REPO_ROOT)} 下没有任何定义文件: "
        "模板决策资产必须以文件形式进 Git"
    )


def test_every_template_definition_passes_validation():
    """每份定义都要通过格式校验。"""
    for path in _definition_files():
        payload = _load_raw(path)
        try:
            validate_definition(payload, source=path.name)
        except TemplateDefinitionError as exc:
            pytest.fail(f"{path.name} 校验失败: {exc}")


def test_definitions_can_be_loaded_by_the_shared_loader():
    """共享加载器(守卫脚本用的那条路径)必须能读全部定义。"""
    definitions = load_definitions(DEFINITIONS_DIR)
    assert len(definitions) == len(_definition_files())


# ---------------------------------------------------------------------------
# 2. 不许混进运行时状态
# ---------------------------------------------------------------------------
def test_definitions_contain_no_runtime_state_fields():
    """版本号 / 命中次数 / 审计字段属于数据库, 不许进 Git。"""
    offenders: List[str] = []
    for path in _definition_files():
        payload = _load_raw(path)
        hit = sorted(set(payload) & set(RUNTIME_ONLY_FIELDS))
        if hit:
            offenders.append(f"{path.name}: {hit}")
    assert not offenders, "定义里出现运行时状态字段(它们每次都在变): " + "; ".join(
        offenders
    )


def test_runtime_only_fields_are_disjoint_from_decision_fields():
    """两类字段不许有交集 —— 否则「不许混进运行时状态」这条守护会自相矛盾。"""
    overlap = sorted(set(DECISION_FIELDS) & set(RUNTIME_ONLY_FIELDS))
    assert not overlap, f"决策字段与运行时字段重叠: {overlap}"


# ---------------------------------------------------------------------------
# 3. 维度键唯一 + 文件名一致
# ---------------------------------------------------------------------------
def test_definition_dimension_keys_are_unique():
    """一个维度只能有一份定义。"""
    seen: Dict[Any, str] = {}
    for path in _definition_files():
        key = dimension_key(_load_raw(path))
        assert (
            key not in seen
        ), f"{path.name} 与 {seen.get(key)} 的维度键相同: {dimension_key_text(key)}"
        seen[key] = path.name


def test_definition_file_name_matches_its_content():
    """文件名必须由内容里的维度键推导 —— 否则「按名字找定义」会找错。"""
    for path in _definition_files():
        payload = _load_raw(path)
        assert path.name == definition_file_name(payload), (
            f"{path.name} 与内容里的维度键不一致"
            f"(期望 {definition_file_name(payload)})"
        )


def test_dimension_fields_cover_all_dimension_identity():
    """维度身份不能漏字段 —— 漏了就会把不同维度当成同一个。"""
    for name in ("platform", "data_domain", "granularity", "sub_domain", "account"):
        assert name in DIMENSION_FIELDS, f"维度键缺少 {name}"


# ---------------------------------------------------------------------------
# 4. 派生值不进 Git
# ---------------------------------------------------------------------------
def test_definitions_exclude_derived_binding_keys():
    """``confidence`` 是算法产物, 进 Git 会让守卫每次都报假差异。"""
    offenders: List[str] = []
    for path in _definition_files():
        payload = _load_raw(path)
        for index, binding in enumerate(payload.get("header_bindings") or []):
            if not isinstance(binding, dict):
                continue
            hit = sorted(set(binding) & set(DERIVED_BINDING_KEYS))
            if hit:
                offenders.append(f"{path.name}[{index}]: {hit}")
    assert not offenders, "定义里出现派生字段: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# 5. 文件形态: UTF-8 无 BOM + LF
# ---------------------------------------------------------------------------
def test_definition_files_are_utf8_without_bom_and_use_lf_newlines():
    """无 BOM + LF ⇒ Git diff 干净, 且任何工具都能按 UTF-8 正确读。"""
    offenders: List[str] = []
    for path in _definition_files():
        data = path.read_bytes()
        if data[:3] == b"\xef\xbb\xbf":
            offenders.append(f"{path.name}: 带 UTF-8 BOM")
        if b"\r\n" in data:
            offenders.append(f"{path.name}: 含 CRLF 换行")
    assert not offenders, "定义文件形态不对: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# 6. 决策字段必须是 ORM 的真实列
# ---------------------------------------------------------------------------
def test_decision_fields_are_real_orm_columns():
    """决策字段名写错 ⇒ 该字段永远为空, 而且**没有任何报错**。"""
    from modules.core.db import FieldMappingTemplate

    columns = set(FieldMappingTemplate.__table__.columns.keys())
    missing = sorted(set(DECISION_FIELDS) - columns)
    assert not missing, f"决策字段在 ORM 里不存在(写错了): {missing}"


def test_export_payload_never_carries_runtime_state():
    """导出脚本会**覆盖**仓库里的定义文件 —— 它绝不能把运行时状态写进去。

    这是最容易发生、后果最隐蔽的一类腐化: 导出一次就把版本号、
    命中次数、审计时间写进 Git, 之后每次巡检都产生噪音 diff。
    """
    from scripts.template_definitions import build_definition_payload

    fake_row = SimpleNamespace(
        id=42,
        platform="tiktok",
        data_domain="orders",
        granularity="monthly",
        sub_domain=None,
        account=None,
        header_row=1,
        sheet_name=None,
        encoding="utf-8",
        template_name="tiktok_orders__monthly_v12",
        version=12,
        status="published",
        usage_count=99,
        success_rate=0.97,
        created_by="user",
        created_at="2026-11-14T00:00:00+00:00",
        updated_by="user",
        updated_at="2026-11-14T00:00:00+00:00",
        format_signature="form_abc_empty_",
        header_columns=["订单号", "订单状态"],
        deduplication_fields=["订单号"],
        core_fields=[{"raw_name": "订单号", "required": True, "in_hash": True}],
        ignored_extra_fields=["商家成长服务费"],
        header_bindings=[{"raw_name": "订单号", "confidence": 0.9}],
        field_parse_rules=[],
        notes="备注",
    )

    payload = build_definition_payload(fake_row)

    for name in RUNTIME_ONLY_FIELDS:
        assert name not in payload, f"导出结果混进了运行时状态字段 {name}"
    assert payload["platform"] == "tiktok"
    assert payload["header_columns"] == ["订单号", "订单状态"]
    assert payload["core_fields"][0]["required"] is True
    assert payload["ignored_extra_fields"] == ["商家成长服务费"]
    # 派生的 confidence 不进 Git
    assert "confidence" not in payload["header_bindings"][0]


def test_export_payload_normalizes_placeholder_dimensions():
    """历史上出现过把 NULL 渲染成 "N/A" 写进模板名 ⇒ 导出必须归一成 null。"""
    from scripts.template_definitions import build_definition_payload

    fake_row = SimpleNamespace(
        id=7,
        platform="shopee",
        data_domain="orders",
        granularity="daily",
        sub_domain="N/A",
        account="",
        header_row=0,
        sheet_name=None,
        encoding="utf-8",
        template_name="shopee_orders_N/A_daily_v3",
        version=3,
        status="published",
        usage_count=0,
        success_rate=0.0,
        created_by="user",
        created_at=None,
        updated_by=None,
        updated_at=None,
        format_signature=None,
        header_columns=["A"],
        deduplication_fields=["A"],
        core_fields=[],
        ignored_extra_fields=[],
        header_bindings=[],
        field_parse_rules=[],
        notes=None,
    )

    payload = build_definition_payload(fake_row)
    assert payload["sub_domain"] is None
    assert payload["account"] is None


# ---------------------------------------------------------------------------
# 7. 不许混进凭据
# ---------------------------------------------------------------------------
def test_definitions_contain_no_credentials():
    """仓库是公开的 —— 定义文件里出现密码等于公开密码。"""
    offenders: List[str] = []
    for path in _definition_files() + sorted(OVERLAYS_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for match in CREDENTIAL_PATTERN.finditer(text):
            offenders.append(f"{path.name}: {match.group(0)[:60]}")
    assert not offenders, "定义文件出现疑似凭据: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# 8. 文档 + CI 必须真的跑这一步
# ---------------------------------------------------------------------------
def test_templates_readme_documents_the_guard_commands():
    """README 必须把三个入口写清楚 —— 否则没人知道怎么用。"""
    assert README_PATH.is_file(), "缺少 templates/README.md"
    text = README_PATH.read_text(encoding="utf-8")
    for needle in (
        "--validate-only",
        "--check",
        "--apply",
        "export_template_definitions.py",
    ):
        assert needle in text, f"templates/README.md 没有提到 {needle}"


def test_ci_workflow_actually_validates_template_definitions():
    """没人调用的守护不是守护 —— CI 里必须真的有这一步。"""
    assert CI_WORKFLOW.is_file(), "缺少 .github/workflows/ci.yml"
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert (
        "apply_template_definitions.py" in text
    ), "CI 里没有校验模板决策资产 —— 定义文件会悄悄腐化"
    assert "--validate-only" in text, "CI 里的校验必须是离线的 --validate-only"
