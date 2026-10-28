"""变体接管判定 (SSOT)

背景
----
模板族(family)的维度是 ``(platform, data_domain, granularity, sub_domain, account)``,
但**导出格式不一定跟着粒度走**。

实测 ``tiktok/products``(2026-10-29, 本地库)::

    family 23 (daily)    active version -> legacy id=362 (176 列, header_row=3)
    family 27 (monthly)  active version -> legacy id=350 ( 38 列, header_row=2)

TikTok 商品导出实际只有一种表结构(176 列), monthly 只是采集时间范围不同。
于是 25 个 monthly 文件在 family 27 里**匹配不到任何变体** ->
``missing_variant`` -> 结构漂移 -> 永不自动入库; 而 family 27 的旧模板会持续
把后续 monthly 文件挡在门外(自我强化的死循环)。

判定口径
--------
* **边界**: 只允许同 ``platform`` + 同 ``data_domain`` 的其他 family 接管
  (不允许跨平台 —— 不同平台的导出格式不可类比)
* **门槛**: 变体 ``required_headers`` 的匹配率 >= ``TAKEOVER_MIN_MATCH_RATE``
  **且** 缺失列 <= ``TAKEOVER_MAX_MISSING_HEADERS``
* **命中后**: 由被接管的变体解释该文件(等价于一份临时契约), 并**显式标注**
  接管来源 —— 不允许静默当成普通 ``ready``

门槛为什么取 95% / 1 列
-----------------------
本例区分度极大: 正确变体匹配率 100%(缺失 0 列), 错误变体匹配率 0%。
门槛可以卡得很死而不误伤。缺失列上限取 1 是为了容许「上游少抓了一列」,
但**不容许**结构性差异 —— 例如 175 列版(少了 ``发品状态``、指标被替换)
相对 176 列版缺失 2 列, 会被拒绝, 因为它是**另一个变体**, 需要单独登记。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

__all__ = [
    "TAKEOVER_MIN_MATCH_RATE",
    "TAKEOVER_MAX_MISSING_HEADERS",
    "TAKEOVER_FLAG",
    "normalize_header_set",
    "evaluate_variant_takeover",
    "build_takeover_report",
    "select_best_takeover",
    "template_explains_columns",
]


#: 接管所需的最小匹配率(变体 required_headers 被文件表头覆盖的比例)
TAKEOVER_MIN_MATCH_RATE: float = 0.95

#: 接管所允许的最大缺失列数
TAKEOVER_MAX_MISSING_HEADERS: int = 1

#: 接管标记 —— 供治理视图/处置模型识别
TAKEOVER_FLAG = "cross_family_variant_takeover"


def normalize_header_set(columns: Optional[Iterable[Any]]) -> Set[str]:
    """列名归一化(去空白 + 小写), 与 family 层 ``_select_variant`` 保持一致。"""
    if not columns:
        return set()
    return {
        str(column).strip().lower()
        for column in columns
        if column is not None and str(column).strip()
    }


def evaluate_variant_takeover(
    variant: Optional[Dict[str, Any]],
    header_columns: Optional[Iterable[Any]],
    *,
    min_match_rate: float = TAKEOVER_MIN_MATCH_RATE,
    max_missing_headers: int = TAKEOVER_MAX_MISSING_HEADERS,
) -> Optional[Dict[str, Any]]:
    """评估某个变体能否接管当前文件。

    返回 ``None`` 表示不满足门槛; 命中时返回接管决定::

        {
            "variant_id": int,
            "variant_key": str,
            "source_legacy_template_id": int | None,
            "header_row": int | None,
            "match_rate": float,
            "matched_headers": list[str],
            "missing_headers": list[str],
        }
    """
    if not variant:
        return None

    required = variant.get("required_headers") or []
    required_set = normalize_header_set(required)
    if not required_set:
        # 没有 required_headers 的变体无法做覆盖率判定 —— 不接管
        return None

    file_set = normalize_header_set(header_columns)
    if not file_set:
        return None

    matched = sorted(required_set & file_set)
    missing = sorted(required_set - file_set)
    match_rate = len(matched) / len(required_set)

    if match_rate < min_match_rate:
        return None
    if len(missing) > max_missing_headers:
        return None

    return {
        "variant_id": variant.get("id"),
        "variant_key": variant.get("variant_key"),
        "source_legacy_template_id": variant.get("source_legacy_template_id"),
        "header_row": variant.get("header_row"),
        "match_rate": round(match_rate, 6),
        "matched_headers": matched,
        "missing_headers": missing,
    }


def build_takeover_report(
    decision: Optional[Dict[str, Any]],
    *,
    source_family: Optional[Dict[str, Any]] = None,
    source_version: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """把接管决定整理成可展示/可落库的字典。

    落库位置: ``catalog_files.file_metadata['template_contract']['takeover']``
    —— 与契约同处, 便于事后追溯「这个文件当年是被哪个 family 接管的」。
    """
    if not decision:
        return None

    family_id = None
    family_granularity = None
    if source_family:
        family_id = source_family.get("id")
        family_granularity = source_family.get("granularity")

    version_id = None
    version_no = None
    if source_version:
        version_id = source_version.get("id")
        version_no = source_version.get("version_no")

    return {
        "flag": TAKEOVER_FLAG,
        "variant_id": decision.get("variant_id"),
        "variant_key": decision.get("variant_key"),
        "source_legacy_template_id": decision.get("source_legacy_template_id"),
        "source_family_id": family_id,
        "source_family_granularity": family_granularity,
        "source_version_id": version_id,
        "source_version_no": version_no,
        "header_row": decision.get("header_row"),
        "match_rate": decision.get("match_rate"),
        "matched_headers": list(decision.get("matched_headers") or []),
        "missing_headers": list(decision.get("missing_headers") or []),
    }


def select_best_takeover(
    candidates: Optional[Iterable[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """在多个接管候选里挑出最优的一个。

    排序口径(与 family 内变体选择保持同一套优先级直觉):

    1. **自家变体优先** —— 接管的前提是「自己家解释不了」;
       自家变体与兄弟 family 的变体都命中时, 必须选自家的,
       否则 monthly 的文件会被 daily 的变体抢走解释权。
    2. 匹配率降序 —— 解释得越完整越可信
    3. ``match_priority`` 升序 —— 数字小的优先
    4. ``variant_id`` 升序 —— 保证结果稳定可复现

    候选元素结构::

        {"variant": {...}, "decision": {...}, "is_own_family": bool, ...}
    """
    best: Optional[Dict[str, Any]] = None
    best_key = None
    for candidate in candidates or []:
        if not candidate:
            continue
        variant = candidate.get("variant") or {}
        decision = candidate.get("decision") or {}
        try:
            match_rate = float(decision.get("match_rate") or 0.0)
        except (TypeError, ValueError):
            match_rate = 0.0
        try:
            priority = int(variant.get("match_priority") or 100)
        except (TypeError, ValueError):
            priority = 100
        try:
            variant_id = int(variant.get("id") or 0)
        except (TypeError, ValueError):
            variant_id = 0
        own_rank = 0 if candidate.get("is_own_family") else 1
        key = (own_rank, -match_rate, priority, variant_id)
        if best_key is None or key < best_key:
            best_key = key
            best = candidate
    return best


def template_explains_columns(
    template: Any,
    header_columns: Optional[Iterable[Any]],
    *,
    min_match_rate: float = TAKEOVER_MIN_MATCH_RATE,
    max_missing_headers: int = TAKEOVER_MAX_MISSING_HEADERS,
) -> bool:
    """模板能否解释给定的表头列。

    复用与接管完全相同的判定口径(覆盖率 >= 门槛 且 缺失列 <= 上限),
    这样「这个模板解释得了这个文件吗」在系统里只有**一把尺子**。

    典型用法: 校验文件自带的模板契约是否仍然成立 ——
    契约指向的模板如果解释不了文件当前的表头, 说明契约已经过时
    (例如文件其实是另一种导出格式, 被跨 family 变体接管了)。
    """
    if template is None:
        return False
    required = getattr(template, "header_columns", None) or []
    if not required:
        return False
    pseudo_variant = {
        "id": getattr(template, "id", None),
        "header_row": getattr(template, "header_row", None),
        "required_headers": list(required),
    }
    return (
        evaluate_variant_takeover(
            pseudo_variant,
            header_columns,
            min_match_rate=min_match_rate,
            max_missing_headers=max_missing_headers,
        )
        is not None
    )
