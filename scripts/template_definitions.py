#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板**决策资产**的仓库格式(SSOT)。

为什么把模板定义放进 Git
------------------------
模板表 ``core.field_mapping_templates`` 里混着两类东西:

* **决策资产** —— 「这个平台的导出长什么样、我要哪些数据、哪几列参与去重」。
  它是**人工判断的结果**, 改一次要能 review、能 diff、能回滚。
* **运行时状态** —— 版本号、发布时间、命中次数、成功率、审计字段。
  它是系统**跑出来的**, 不该进 Git(进了每次巡检都产生噪音 diff)。

以前两者混在一张表里, 于是「改了模板」这件事只发生在数据库里:
没人能 review 模板改动, 没人能回滚, 换环境还要手工重配一遍。

本模块定义这两者的**分界线**, 以及:

* 定义文件长什么样(:data:`DECISION_FIELDS`);
* 怎么从 ORM 行裁出决策资产(:func:`decision_payload`);
* 怎么比对「仓库定义」与「库内实例」(:func:`diff_decision_payload`);
* 怎么校验一份定义本身合不合法(:func:`validate_definition`)。

口径说明
--------
定义文件**不含**版本号 —— 版本号是运行时状态(库内每次发布都会自增)。
仓库里的定义表达的是**期望状态**「这个维度该长这样」,
库里的实例表达的是**当前状态**「现在库里是这样」。
两者的差异就是需要人工决策的部分。

用法
----
    from scripts.template_definitions import (
        DECISION_FIELDS, DEFINITIONS_DIR, load_definitions,
    )
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


#: 定义文件的 schema 版本(格式演进时递增, 老文件读不出来要明确报错)。
DEFINITION_SCHEMA_VERSION = 1

#: 决策资产目录(进 Git)。
DEFINITIONS_DIR = REPO_ROOT / "templates" / "definitions"

#: 环境 overlay 目录(进 Git; 只放**环境差异**, 不重复基线)。
OVERLAYS_DIR = REPO_ROOT / "templates" / "overlays"

#: 定义文件后缀。
DEFINITION_SUFFIX = ".json"

#: 决策字段 —— 进 Git 的字段(人工决策的结果)。
#:
#: 排序即「写入文件时的字段顺序」, 便于 diff 稳定。
DECISION_FIELDS: Tuple[str, ...] = (
    "platform",
    "data_domain",
    "granularity",
    "sub_domain",
    "account",
    "header_row",
    "sheet_name",
    "encoding",
    "header_columns",
    "deduplication_fields",
    "core_fields",
    "ignored_extra_fields",
    "header_bindings",
    "field_parse_rules",
    "notes",
)

#: 运行时状态字段 —— **只**留在数据库, 不进 Git。
#:
#: 这些字段每次巡检/发布都会变, 进 Git 只会产生噪音 diff,
#: 还会让人误以为「改了版本号就等于改了模板」。
RUNTIME_ONLY_FIELDS: Tuple[str, ...] = (
    "id",
    "version",
    "status",
    "usage_count",
    "success_rate",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
    "template_name",
    "format_signature",
)

#: 维度键 —— 一个模板「属于哪个维度」的完整身份。
#:
#: 实测(2026-11-14): 27 个 published 模板的该组合**互不重复**
#: ⇒ 它可以当定义文件的唯一键。
DIMENSION_FIELDS: Tuple[str, ...] = (
    "platform",
    "data_domain",
    "granularity",
    "sub_domain",
    "account",
)

#: ``header_bindings`` 里**不属于人工决策**的键 —— 算法产物(置信度等)。
#:
#: 它们不进 Git, 比对时也不参与, 否则每次重算都会产生假差异。
DERIVED_BINDING_KEYS: Tuple[str, ...] = ("confidence",)

#: 占位符 —— 历史上有过把 NULL 渲染成字符串的先例
#: (2026-11-13: ``shopee_orders_N/A_daily_v3``), 定义文件里一律用 null。
DIMENSION_PLACEHOLDERS = frozenset({"", "N/A", "NA", "None", "null", "NULL"})


class TemplateDefinitionError(ValueError):
    """定义文件本身不合法(格式错、字段缺、键冲突)。"""


def normalize_dimension(value: Any) -> Optional[str]:
    """把维度值归一成「字符串或 None」。

    与 :func:`backend.services.template_family_service._normalize_dimension`
    同口径: 空串与占位符一律变成 ``None``。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in DIMENSION_PLACEHOLDERS:
        return None
    return text


def field_value(source: Any, name: str) -> Any:
    """从字典**或** ORM 行里取一个字段。

    定义文件是字典, 库内实例是 ORM 行 —— 两者都要能当「一份数据」处理,
    否则每个调用点都要写一遍 isinstance 判断。
    """
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def dimension_key(payload: Any) -> Tuple[str, Optional[str], ...]:
    """取一份定义/一行模板的维度键。"""
    return (
        str(field_value(payload, "platform") or "").strip(),
        str(field_value(payload, "data_domain") or "").strip(),
        normalize_dimension(field_value(payload, "granularity")),
        normalize_dimension(field_value(payload, "sub_domain")),
        normalize_dimension(field_value(payload, "account")),
    )


def dimension_key_text(key: Iterable[Any]) -> str:
    """维度键的可读形式(用于日志与文件名)。"""
    parts = [str(part) if part else "-" for part in key]
    return "/".join(parts)


def definition_file_name(payload: Dict[str, Any]) -> str:
    """按维度键生成定义文件名。

    例: ``tiktok__orders__monthly.json``、
    ``shopee__services__daily__ai_assistant.json``。
    """
    platform, data_domain, granularity, sub_domain, account = dimension_key(payload)
    parts = [platform, data_domain, granularity]
    if sub_domain:
        parts.append(sub_domain)
    if account:
        parts.append(account)
    return "__".join(str(part) for part in parts if part) + DEFINITION_SUFFIX


def _clean_bindings(bindings: Any) -> List[Dict[str, Any]]:
    """裁掉派生键(``confidence``)后的 ``header_bindings``。"""
    if not isinstance(bindings, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for item in bindings:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                key: value
                for key, value in item.items()
                if key not in DERIVED_BINDING_KEYS
            }
        )
    return cleaned


def decision_payload(
    source: Any,
    *,
    include_derived_bindings: bool = False,
) -> Dict[str, Any]:
    """从 ORM 行 / 字典里裁出**决策资产**。

    Args:
        source: ORM 行(``FieldMappingTemplate``)或字典。
        include_derived_bindings: 是否保留 ``confidence`` 等派生键。
            导出定义时用 ``False``(派生值不进 Git);
            比对时两侧都用 ``False`` ⇒ 不会因重算置信度产生假差异。

    Returns:
        只含 :data:`DECISION_FIELDS` 的字典。
    """

    def _get(name: str) -> Any:
        return field_value(source, name)

    payload: Dict[str, Any] = {}
    for name in DECISION_FIELDS:
        if name in ("sub_domain", "account", "granularity"):
            payload[name] = normalize_dimension(_get(name))
        elif name == "header_bindings":
            if include_derived_bindings:
                raw = _get(name)
                payload[name] = list(raw) if isinstance(raw, list) else []
            else:
                payload[name] = _clean_bindings(_get(name))
        elif name in ("header_columns", "deduplication_fields", "core_fields"):
            raw = _get(name)
            payload[name] = (
                list(raw) if isinstance(raw, list) else ([] if raw is None else raw)
            )
        elif name == "ignored_extra_fields":
            raw = _get(name)
            payload[name] = list(raw) if isinstance(raw, list) else []
        else:
            payload[name] = _get(name)
    return payload


def _normalize_for_compare(value: Any) -> Any:
    """把值变成**可稳定比较**的形式。

    * 列表按元素递归归一(列表顺序本身是有意义的, 不排序);
    * 字典按键排序, 便于 JSON 化后直接比字符串;
    * ``None`` 与空串统一成 ``None``(语义上等价)。
    """
    if isinstance(value, dict):
        return {key: _normalize_for_compare(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_compare(item) for item in value]
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def diff_decision_payload(
    expected: Dict[str, Any],
    actual: Dict[str, Any],
) -> List[str]:
    """比对「仓库定义」与「库内实例」的决策资产。

    Returns:
        差异描述列表(空列表 = 完全一致)。
    """
    differences: List[str] = []
    for name in DECISION_FIELDS:
        left = _normalize_for_compare(expected.get(name))
        right = _normalize_for_compare(actual.get(name))
        if left == right:
            continue
        if isinstance(left, list) and isinstance(right, list):
            left_set = [
                json.dumps(item, ensure_ascii=False, sort_keys=True) for item in left
            ]
            right_set = [
                json.dumps(item, ensure_ascii=False, sort_keys=True) for item in right
            ]
            only_left = [item for item in left_set if item not in right_set]
            only_right = [item for item in right_set if item not in left_set]
            if only_left or only_right:
                differences.append(
                    f"{name}: 定义多出 {len(only_left)} 项 / 库内多出 {len(only_right)} 项"
                    + (f" | 定义侧示例: {only_left[0][:120]}" if only_left else "")
                    + (f" | 库内侧示例: {only_right[0][:120]}" if only_right else "")
                )
            continue
        differences.append(
            f"{name}: 定义={json.dumps(left, ensure_ascii=False)[:160]}"
            f" 库内={json.dumps(right, ensure_ascii=False)[:160]}"
        )
    return differences


def validate_definition(payload: Dict[str, Any], *, source: str = "<memory>") -> None:
    """校验一份定义文件是否合法。非法就抛 :class:`TemplateDefinitionError`。"""
    if not isinstance(payload, dict):
        raise TemplateDefinitionError(f"{source}: 顶层必须是对象")

    version = payload.get("$schema_version")
    if version != DEFINITION_SCHEMA_VERSION:
        raise TemplateDefinitionError(
            f"{source}: $schema_version 必须是 {DEFINITION_SCHEMA_VERSION}, 实际={version!r}"
        )

    forbidden = sorted(set(payload) & set(RUNTIME_ONLY_FIELDS))
    if forbidden:
        raise TemplateDefinitionError(
            f"{source}: 不允许出现运行时状态字段 {forbidden}"
            " (它们属于数据库, 不进 Git)"
        )

    unknown = sorted(set(payload) - set(DECISION_FIELDS) - {"$schema_version"})
    if unknown:
        raise TemplateDefinitionError(
            f"{source}: 出现未知字段 {unknown}"
            f" (允许的决策字段: {list(DECISION_FIELDS)})"
        )

    for name in ("platform", "data_domain"):
        if not str(payload.get(name) or "").strip():
            raise TemplateDefinitionError(f"{source}: {name} 不能为空")

    header_row = payload.get("header_row")
    if not isinstance(header_row, int) or not (0 <= header_row <= 100):
        raise TemplateDefinitionError(
            f"{source}: header_row 必须是 0-100 的整数, 实际={header_row!r}"
        )

    header_columns = payload.get("header_columns")
    if not isinstance(header_columns, list) or not header_columns:
        raise TemplateDefinitionError(f"{source}: header_columns 必须是非空列表")
    for column in header_columns:
        if not isinstance(column, str) or not column.strip():
            raise TemplateDefinitionError(
                f"{source}: header_columns 里存在非字符串/空列名: {column!r}"
            )

    core_fields = payload.get("core_fields")
    if core_fields is not None and not isinstance(core_fields, list):
        raise TemplateDefinitionError(f"{source}: core_fields 必须是列表或 null")
    for item in core_fields or []:
        if not isinstance(item, dict):
            raise TemplateDefinitionError(f"{source}: core_fields 元素必须是对象")
        unknown_keys = sorted(
            set(item) - {"semantic_key", "raw_name", "required", "in_hash"}
        )
        if unknown_keys:
            raise TemplateDefinitionError(
                f"{source}: core_fields 元素出现未知键 {unknown_keys}"
            )

    for name in ("deduplication_fields", "ignored_extra_fields"):
        value = payload.get(name)
        if value is not None and not isinstance(value, list):
            raise TemplateDefinitionError(f"{source}: {name} 必须是列表或 null")

    for name in ("header_bindings", "field_parse_rules"):
        value = payload.get(name)
        if value is not None and not isinstance(value, list):
            raise TemplateDefinitionError(f"{source}: {name} 必须是列表或 null")


def load_definition_file(path: Path) -> Dict[str, Any]:
    """读取并校验一个定义文件。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateDefinitionError(f"{path.name}: JSON 解析失败: {exc}") from exc
    validate_definition(payload, source=path.name)
    return payload


def load_definitions(
    directory: Optional[Path] = None,
) -> Dict[Tuple[str, Optional[str], ...], Dict[str, Any]]:
    """加载一个目录下的全部定义文件。

    Returns:
        ``{维度键: 定义内容}``。同键重复会直接报错(定义必须唯一)。
    """
    base = Path(directory) if directory else DEFINITIONS_DIR
    definitions: Dict[Tuple[str, Optional[str], ...], Dict[str, Any]] = {}
    if not base.exists():
        return definitions
    for path in sorted(base.glob(f"*{DEFINITION_SUFFIX}")):
        payload = load_definition_file(path)
        key = dimension_key(payload)
        if key in definitions:
            raise TemplateDefinitionError(
                f"{path.name}: 维度键 {dimension_key_text(key)} 与 "
                f"其它定义重复 —— 一个维度只能有一份定义"
            )
        definitions[key] = payload
    return definitions


def load_overlays(directory: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """加载 overlay 文件(按 overlay 名字索引)。"""
    base = Path(directory) if directory else OVERLAYS_DIR
    overlays: Dict[str, Dict[str, Any]] = {}
    if not base.exists():
        return overlays
    for path in sorted(base.glob(f"*{DEFINITION_SUFFIX}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TemplateDefinitionError(f"{path.name}: JSON 解析失败: {exc}") from exc
        if not isinstance(payload, dict):
            raise TemplateDefinitionError(f"{path.name}: 顶层必须是对象")
        name = str(payload.get("overlay") or path.stem).strip()
        entries = payload.get("definitions")
        if not isinstance(entries, list):
            raise TemplateDefinitionError(f"{path.name}: definitions 必须是列表")
        overlays[name] = payload
    return overlays


def merge_overlay(
    base: Dict[str, Any],
    overlay_entry: Dict[str, Any],
) -> Dict[str, Any]:
    """把 overlay 的一条覆盖合并到基线定义上。

    只允许覆盖 :data:`DECISION_FIELDS`; 维度键本身不允许被改
    (改了就是另一个模板, 不该是「环境差异」)。
    """
    merged = dict(base)
    for name in DECISION_FIELDS:
        if name not in overlay_entry:
            continue
        if name in DIMENSION_FIELDS:
            # 维度键允许改 sub_domain/account 的**空/非空**表示,
            # 但不允许指向另一个维度 —— 那种情况该另起一份定义。
            expected = normalize_dimension(base.get(name))
            actual = normalize_dimension(overlay_entry.get(name))
            if expected != actual:
                raise TemplateDefinitionError(
                    f"overlay 不允许改变维度字段 {name}"
                    f" ({expected!r} -> {actual!r})"
                )
            merged[name] = actual
            continue
        merged[name] = overlay_entry[name]
    return merged


def build_definition_payload(
    row: Any,
    *,
    include_derived_bindings: bool = False,
) -> Dict[str, Any]:
    """生成一份可写进文件的定义内容(字段顺序固定)。"""
    decision = decision_payload(row, include_derived_bindings=include_derived_bindings)
    payload: Dict[str, Any] = {"$schema_version": DEFINITION_SCHEMA_VERSION}
    for name in DECISION_FIELDS:
        payload[name] = decision.get(name)
    return payload


def dump_definition(payload: Dict[str, Any]) -> str:
    """把定义序列化成文件内容(稳定缩进 + 结尾换行 ⇒ diff 友好)。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


__all__ = [
    "DEFINITION_SCHEMA_VERSION",
    "DEFINITIONS_DIR",
    "DECISION_FIELDS",
    "DERIVED_BINDING_KEYS",
    "DIMENSION_FIELDS",
    "OVERLAYS_DIR",
    "RUNTIME_ONLY_FIELDS",
    "TemplateDefinitionError",
    "build_definition_payload",
    "decision_payload",
    "definition_file_name",
    "diff_decision_payload",
    "dimension_key",
    "dimension_key_text",
    "dump_definition",
    "load_definition_file",
    "load_definitions",
    "load_overlays",
    "merge_overlay",
    "normalize_dimension",
    "validate_definition",
]
