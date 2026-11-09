#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比对两个库之间的**同步模板**差异(只读)。

为什么需要它
------------
模板是**运行时数据**(存在 ``core.field_mapping_templates`` 等 6 张表),
不在 git 里 ⇒ 开发环境改了模板, 生产/采集环境不会自动跟上。

现状的同步入口 ``scripts/sync_templates_to_cloud.ps1`` 只 ``pg_dump`` 了
**一张**表(``field_mapping_templates``), 而:

* 254 个模板里只有 66 个带 ``header_bindings``、119 个带 ``header_columns``;
* **4748 条**「原始列 → 标准字段」映射放在 ``field_mapping_template_items``;

⇒ 列映射的主体根本没进同步范围, 而脚本末尾只校验 ``COUNT(*)`` ——
行数对上了就当同步成功, 漏掉的映射没人知道。

本脚本把「到底差了什么」变成可见的: 按**业务键**逐条比对**内容指纹**
(不是只比行数), 退出码非 0 表示有差异 ⇒ 可以直接当门禁用。

比对键的设计(踩过的坑)
----------------------
1. **不能用自增 id 当跨库键** —— 两个库的 id 分配未必一致。
   一律用业务键(模板名 + 平台/域/粒度, 版本表用 模板名+版本号 …)。
2. **主表有重名** —— 254 行只有 199 个不同 ``template_name``
   (模板族按版本并存) ⇒ 只用 ``template_name`` 会把不同版本折叠成一个,
   必须再拼上平台/域/粒度。
3. **必须排除时间戳** —— ``created_at`` / ``updated_at`` 在任何一次同步后
   必然不同, 留着会让"每一行都不同", 差异信号被淹没。
4. **items 用父模板的业务键** —— 它的 ``template_id`` 指向主表 id, 跨库不可比,
   需先翻译; 且实测有 **740 条孤儿**(指向已删除的模板), 单独计数报告。

用法
----
    # 同库自比(验证脚本本身)
    python scripts/diff_templates.py \
        --source postgresql://erp_user:xxx@localhost:15432/xihong_erp \
        --target postgresql://erp_user:xxx@localhost:15432/xihong_erp

    # 开发库 vs 生产库
    python scripts/diff_templates.py \
        --source postgresql://erp_user:xxx@localhost:15432/xihong_erp \
        --target postgresql://erp_user:xxx@cloud-host:5432/xihong_erp

⚠ 本脚本**只读**: 只发 SELECT, 不写任何库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    from sqlalchemy import create_engine, text
except ImportError:  # pragma: no cover
    print("[ERROR] 需要 sqlalchemy: pip install sqlalchemy psycopg2-binary")
    raise SystemExit(2)


#: 主表参与指纹的列(排除 id 与时间戳)
TEMPLATE_MAIN_COLUMNS = (
    "status",
    "header_row",
    "header_bindings",
    "header_columns",
    "field_parse_rules",
    "deduplication_fields",
)

#: items 表参与指纹的列
TEMPLATE_ITEM_COLUMNS = ("original_column", "standard_field")

#: 各表的业务键定义: (业务键 SQL 表达式列表, 指纹列列表)
#: 键一律用「不含自增 id、不含时间戳」的稳定列。
TABLE_SPECS: Dict[str, Dict[str, Any]] = {
    "field_mapping_templates": {
        "keys": [
            "template_name",
            "platform",
            "data_domain",
            "granularity",
            "sub_domain",
        ],
        "fingerprint": TEMPLATE_MAIN_COLUMNS,
    },
    "field_mapping_template_families": {
        "keys": ["platform", "data_domain", "granularity", "account", "sub_domain"],
        "fingerprint": ["governance_status", "source_mode", "display_name"],
    },
    "field_mapping_template_versions": {
        "keys": ["template_name", "version_no"],
        "fingerprint": [
            "status",
            "deduplication_fields",
            "header_bindings",
            "core_fields",
            "field_parse_rules",
            "legacy_template_ids",
            "notes",
        ],
    },
    "field_mapping_template_variants": {
        "keys": ["template_name", "variant_key", "variant_kind"],
        "fingerprint": [
            "match_priority",
            "header_row",
            "sheet_name_pattern",
            "required_headers",
            "parse_profile",
            "field_parse_rules",
        ],
    },
    "collection_config_templates": {
        "keys": ["name", "platform", "main_account_id", "granularity"],
        "fingerprint": [
            "default_date_range_type",
            "default_execution_mode",
            "default_schedule_enabled",
            "default_schedule_cron",
            "default_retry_count",
            "default_shop_scopes",
            "is_active",
        ],
    },
}

TEMPLATE_TABLES = tuple(TABLE_SPECS.keys()) + ("field_mapping_template_items",)


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:  # pragma: no cover
        print(text.encode("utf-8", "replace").decode("utf-8", "replace"))


def _hash(values: List[Any]) -> str:
    """把一组列值压成稳定指纹。"""
    parts = []
    for v in values:
        if v is None:
            parts.append("-")
        elif isinstance(v, (dict, list)):
            parts.append(json.dumps(v, ensure_ascii=False, sort_keys=True, default=str))
        else:
            parts.append(str(v))
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _detect_schema(engine, table: str) -> Optional[str]:
    """探测表所在的 schema(``core`` / ``public`` / ...)。"""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT n.nspname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = :t AND c.relkind = 'r' "
                "ORDER BY (n.nspname = 'core') DESC, n.nspname LIMIT 1"
            ),
            {"t": table},
        ).fetchone()
    return row[0] if row else None


def _template_key_map(engine, schema: str) -> Dict[str, str]:
    """主表 id -> 业务键(用于把 items 的 template_id 翻译成可跨库比较的键)。"""
    keys = TABLE_SPECS["field_mapping_templates"]["keys"]
    key_expr = ", ".join("coalesce(\"{0}\"::text, '')".format(k) for k in keys)
    qualified = "{0}.field_mapping_templates".format(schema)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id::text, {0} FROM {1}".format(key_expr, qualified))
        ).fetchall()
    return {str(r[0]): "§".join(str(v) for v in r[1:]) for r in rows}


def _fingerprint(engine, schema: str, table: str) -> Dict[str, str]:
    """算一张模板表的指纹: {业务键: 内容指纹}。"""
    qualified = "{0}.{1}".format(schema, table)

    if table == "field_mapping_template_items":
        key_map = _template_key_map(engine, schema)
        cols = ", ".join(
            "coalesce(\"{0}\"::text, '')".format(c) for c in TEMPLATE_ITEM_COLUMNS
        )
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT template_id::text, {0} FROM {1}".format(cols, qualified))
            ).fetchall()
        bucket: Dict[str, List[str]] = {}
        orphans = 0
        for r in rows:
            parent = key_map.get(str(r[0]))
            if parent is None:
                orphans += 1
                continue
            bucket.setdefault(parent, []).append("|".join(str(v) for v in r[1:]))
        result = {key: _hash(sorted(values)) for key, values in bucket.items()}
        # 孤儿条数挂在返回值旁边(用一个特殊键带出去)
        result["__orphans__"] = str(orphans)
        return result

    spec = TABLE_SPECS[table]
    key_expr = ", ".join("coalesce(\"{0}\"::text, '')".format(k) for k in spec["keys"])
    fp_expr = ", ".join(
        "coalesce(\"{0}\"::text, '')".format(c) for c in spec["fingerprint"]
    )
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT {0}, {1} FROM {2}".format(key_expr, fp_expr, qualified))
        ).fetchall()
    # ⚠ 键只取前 n_keys 列, 指纹取其后的**全部**列。
    #   写错成 r[-1:] 会只指纹最后一列, 并把其余指纹列混进键里 ——
    #   那样"内容变了"会表现成"键变了"(仅源有/仅目标有), 信号就废了。
    n_keys = len(spec["keys"])
    return {
        "§".join(str(v) for v in r[:n_keys]): _hash([str(v) for v in r[n_keys:]])
        for r in rows
    }


def _short(key: str) -> str:
    return key.replace("§", " / ")


def diff_templates(source_url: str, target_url: str) -> int:
    source = create_engine(source_url)
    target = create_engine(target_url)

    total_diff = 0

    for table in TEMPLATE_TABLES:
        s_schema = _detect_schema(source, table)
        t_schema = _detect_schema(target, table)

        _safe_print("")
        _safe_print("=== 表 {0} ===".format(table))

        if not s_schema and not t_schema:
            _safe_print("  [SKIP] 两边都不存在")
            continue
        if not s_schema:
            _safe_print("  [差异] 只在目标库存在")
            total_diff += 1
            continue
        if not t_schema:
            _safe_print("  [差异] 只在源库存在")
            total_diff += 1
            continue

        s_fp = _fingerprint(source, s_schema, table)
        t_fp = _fingerprint(target, t_schema, table)

        s_orphans = s_fp.pop("__orphans__", "0")
        t_orphans = t_fp.pop("__orphans__", "0")
        if table == "field_mapping_template_items":
            _safe_print(
                "  孤儿 items(父模板已不存在): 源 {0} / 目标 {1}".format(
                    s_orphans, t_orphans
                )
            )

        only_source = sorted(set(s_fp) - set(t_fp))
        only_target = sorted(set(t_fp) - set(s_fp))
        changed = sorted(k for k in set(s_fp) & set(t_fp) if s_fp[k] != t_fp[k])

        _safe_print("  源 {0} 条 / 目标 {1} 条".format(len(s_fp), len(t_fp)))
        _safe_print("  仅源有: {0}".format(len(only_source)))
        _safe_print("  仅目标有: {0}".format(len(only_target)))
        _safe_print("  内容不同: {0}".format(len(changed)))

        for key in only_source[:15]:
            _safe_print("    [仅源] {0}".format(_short(key)))
        for key in only_target[:15]:
            _safe_print("    [仅目标] {0}".format(_short(key)))
        for key in changed[:15]:
            _safe_print("    [不同] {0}".format(_short(key)))
        if max(len(only_source), len(only_target), len(changed)) > 15:
            _safe_print("    (上面每类最多列 15 条)")

        total_diff += len(only_source) + len(only_target) + len(changed)

    source.dispose()
    target.dispose()

    _safe_print("")
    _safe_print("=" * 66)
    _safe_print("差异合计: {0}".format(total_diff))
    if total_diff:
        _safe_print("结论: 两边**不一致** —— 用 sync_templates_to_cloud.ps1 同步, ")
        _safe_print("      但注意它目前只 dump 主表, 需先补齐另外 5 张表。")
    else:
        _safe_print("结论: 两边**一致**")
    return total_diff


def _mask(url: str) -> str:
    """连接串脱敏(不打印密码)。"""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return "{0}://{1}:***@{2}".format(scheme, user, host)
    return url


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="比对两个库之间的同步模板差异(只读)")
    parser.add_argument("--source", required=True, help="源库连接串(通常是开发库)")
    parser.add_argument(
        "--target", required=True, help="目标库连接串(通常是生产/采集库)"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _safe_print("=" * 66)
    _safe_print("模板差异比对 (只读)")
    _safe_print("  源  : {0}".format(_mask(args.source)))
    _safe_print("  目标: {0}".format(_mask(args.target)))
    _safe_print("=" * 66)

    try:
        total_diff = diff_templates(args.source, args.target)
    except Exception as exc:  # pragma: no cover
        _safe_print("[ERROR] 比对失败: {0}".format(exc))
        return 2

    _safe_print("")
    _safe_print("[提示] 本脚本只读; 要把源库的模板推到目标库, 用")
    _safe_print("       scripts/sync_templates_to_cloud.ps1")
    _safe_print("       (注意: 它目前只 dump 主表, 需先补齐另外 5 张表)")
    return 1 if total_diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
