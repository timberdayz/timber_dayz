#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 ``semantic_field_registry.py`` 的字典生成 products 域的别名 seed。

单一事实源
----------
「列名 → 标准字段」的**唯一事实源**是
:mod:`backend.services.semantic_field_registry` 里的字典:

* :data:`SEMANTIC_FIELD_DEFINITIONS` —— 标准字段 + 全局别名;
* :data:`DOMAIN_SEMANTIC_ALIASES` —— 域限定别名(真实表头);
* :data:`PLATFORM_CALIBER_HISTORY` —— 平台口径沿革。

本脚本只是这套字典的**投影**, 不新增任何别名。合并规则(域限定优先、
口径不许混、一个列名只认一个标准字段)集中在
:func:`backend.services.semantic_alias_registry.build_domain_alias_records`,
所以「DB seed」与「Python 侧派生别名」不会分叉。

用法
----
``python scripts/generate_semantic_alias_seed.py --stdout``
    打印生成的 SQL seed(与 ``sql/semantic/semantic_alias_registry.sql``
    的 INSERT 段同形: 同样的列、同样的 ON CONFLICT 处理)。

``python scripts/generate_semantic_alias_seed.py --check``
    比较生成结果与现有 SQL 资产里的 INSERT 段; 不一致时打印差异并以
    非零退出码结束(供 CI / 守护测试调用)。**本模式不写任何文件。**

``python scripts/generate_semantic_alias_seed.py --normalized-stdout``
    打印归一化形态清单(列名 ``normalized_alias``), 供 PG 侧归一化匹配
    (阶段 C) 使用。

⚠️ 归一化形态**只作为清单产出**, 不直接写成别名行 ——
   归一化会把不同指标压到同一个形态(例: ``商品曝光次数.1`` → ``商品曝光次数``,
   而后者是**总曝光量**的真实表头), 直接 seed 会把两个指标混成一个。

``--output PATH`` / ``--normalized-output PATH``
    写文件(默认不写)。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 导入 backend.* 会触发应用配置初始化, 那里会往 **stdout** 打 INFO 日志。
# 本脚本的 stdout 是**产物**(SQL seed / TSV 清单) ⇒ 导入期间必须把 stdout 静音。
#
# 注意: ``contextlib.redirect_stdout`` 对这里**无效** —— 日志处理器在创建时
# 就把 ``sys.stdout`` 的**对象**绑定了, 之后再换 ``sys.stdout`` 它也不跟着走。
# ⇒ 只能在**文件描述符层**把 fd 1 暂时指向 devnull, 导入完再换回来。
import os  # noqa: E402

_STDOUT_FD = os.dup(1)
_DEVNULL = open(os.devnull, "w")
try:
    os.dup2(_DEVNULL.fileno(), 1)
    from backend.services.semantic_alias_registry import (  # noqa: E402
        build_domain_alias_records,
    )
    from backend.services.semantic_field_registry import (  # noqa: E402
        apply_caliber_history,
        normalize_semantic_alias,
    )
finally:
    os.dup2(_STDOUT_FD, 1)
    os.close(_STDOUT_FD)
    _DEVNULL.close()


#: 生成的 SQL 资产路径(只读; 本脚本默认不写它)。
DEFAULT_SQL_ASSET = ROOT / "sql" / "semantic" / "semantic_alias_registry.sql"

#: seed 行的列 —— 与 ``semantic.semantic_field_aliases`` 表和现有
#: INSERT 段完全一致。
#:
#: ⚠ ``platform_code`` 是**平台维度**的别名隔离: 同一个业务事实, 不同平台
#:   叫不同的列名(买家实付: shopee「买家支付(RMB)」/ tiktok「买家实付金额(RMB)」)。
#:   不带平台维度就会在取数时抢张。
SEED_COLUMNS: Tuple[str, ...] = (
    "data_domain",
    "standard_field",
    "raw_alias",
    "platform_code",
    "normalized_alias",
    "source",
    "confidence",
    "status",
)

#: seed 覆盖的数据域 —— 与 ``semantic.semantic_field_aliases`` 的既有内容对齐。
#:
#: * ``products`` —— 商品报表(口径分「已付款 / 已下单」两套)
#: * ``orders``   —— 订单报表(金额列成对出现: 原币 + ``(RMB)``)
#: * ``analytics`` —— 流量报表(shopee 店铺流量 / tiktok 商品流量)
#:
#: ⚠ 2026-11-08 加入 ``analytics``: 此前该域**从来没有** builtin 别名行,
#:   ``semantic.resolve_alias()`` 只能命中 9 条「模板确认行」
#:   ⇒ 域限定别名清单形同虚设。加入后 ``semantic.fact_analytics_atomic``
#:   的取数才能走别名表。
#:
#: ⚠ 非 products 域的行统一落在**第二段**清理语句(4 元组)里 ⇒
#:   已执行迁移 20261202 / 20261203 的自检(只数第一段 products 的 3 元组
#:   条数)**不受影响**。
SEED_DOMAINS: Tuple[str, ...] = ("products", "orders", "analytics")

#: 与现有 INSERT 段一致的 ON CONFLICT 处理。
ON_CONFLICT_CLAUSE = """ON CONFLICT (
    data_domain,
    standard_field,
    raw_alias,
    COALESCE(platform_code, ''),
    COALESCE(granularity, '')
)
DO UPDATE SET updated_at = NOW(),
              normalized_alias = EXCLUDED.normalized_alias,
              confidence = EXCLUDED.confidence,
              status = EXCLUDED.status;"""

#: 现有 SQL 资产 INSERT 段里一行的形态。
#:
#: ``platform_code`` 允许是 ``NULL``(通用别名)或 ``'shopee'`` 这种字符串。
_SEED_ROW_PATTERN = re.compile(
    r"\(\s*'(?P<data_domain>[^']*)'\s*,\s*'(?P<standard_field>[^']*)'\s*,"
    r"\s*'(?P<raw_alias>[^']*)'\s*,"
    r"\s*(?:'(?P<platform_code>[^']*)'|NULL)\s*,"
    r"\s*'(?P<normalized_alias>[^']*)'\s*,"
    r"\s*'(?P<source>[^']*)'\s*,"
    r"\s*(?P<confidence>[0-9.]+)\s*,\s*'(?P<status>[^']*)'\s*\)"
)

_INSERT_HEAD = "INSERT INTO semantic.semantic_field_aliases"


def normalize_alias(raw_alias: str, platform_code: str | None = None) -> str:
    """把列名/别名归一化成可比较的形态(可再叠加口径沿革折算)。"""
    normalized = normalize_semantic_alias(raw_alias)
    if platform_code:
        normalized = apply_caliber_history(normalized, platform_code)
    return normalized


def _escape(value: object) -> str:
    return str(value).replace("'", "''")


def _render_platform_code(value: object) -> str:
    """把平台码渲染成 SQL 字面量(``NULL`` 或 ``'shopee'``)。"""
    text = str(value or "").strip()
    if not text:
        return "NULL"
    return "'{}'".format(_escape(text))


#: 陈旧 builtin 行清理段的标记(用于定位资产里的这一段)。
PRUNE_MARKER = "-- 陈旧 builtin 行清理"

#: 「其它域(含平台维度)」的清理段标记。
#:
#: ⚠ **为什么清理要拆成两段**:
#: 已执行迁移 20261202 / 20261203 的 fail-closed 自检把
#: 「``PRUNE_MARKER`` 段里 **3 元组**的个数」当作「字典派生的
#: **products 域** builtin 行数」, 与表里 ``data_domain='products'``
#: 的 builtin 行数比对。**已执行迁移不可改** ⇒ 资产必须保持那个形状:
#:
#:   * 第一段(``PRUNE_MARKER``)= **products 域**、**3 元组**
#:     (domain, standard_field, raw_alias) —— products 域没有平台维度行,
#:     3 元组足以唯一定位;
#:   * 其它域(当前是 orders, 带平台维度)另起一段, **4 元组**
#:     (domain, standard_field, raw_alias, platform_code) —— 平台限定行是
#:     **另一条**记录, 少了 platform_code 会误删。
#:
#: 两段都在资产里 ⇒ 迁移整份执行资产 ⇒ 其它域的陈旧 builtin 行照样被清。
PRUNE_OTHER_DOMAINS_MARKER = "-- 陈旧 builtin 行清理(其它域, 含平台维度)"


def _render_prune_segment(
    marker: str,
    rows: Sequence[dict],
    *,
    with_platform: bool,
) -> str:
    """渲染一段「陈旧 builtin 行清理」语句。

    ``with_platform=True`` 时键里带 ``platform_code``(平台限定行是**另一条**
    记录, 少了它会被当成同一条而误删); 否则是 3 元组(products 域没有平台
    维度行, 且已执行迁移的自检按 3 元组计数)。
    """
    if not rows:
        raise ValueError("没有可生成的 seed 行")
    domains = sorted({str(row["data_domain"]) for row in rows})
    if with_platform:
        columns = "current_seed(data_domain, standard_field, raw_alias, platform_code)"
        row_template = "        ('{data_domain}', '{standard_field}', '{raw_alias}', {platform_code})"
        extra_match = (
            "        AND COALESCE(s.platform_code, '') = COALESCE(a.platform_code, '')"
        )
    else:
        columns = "current_seed(data_domain, standard_field, raw_alias)"
        row_template = "        ('{data_domain}', '{standard_field}', '{raw_alias}')"
        extra_match = ""
    values = ",\n".join(
        row_template.format(
            data_domain=_escape(row["data_domain"]),
            standard_field=_escape(row["standard_field"]),
            raw_alias=_escape(row["raw_alias"]),
            platform_code=_render_platform_code(row.get("platform_code")),
        )
        for row in rows
    )
    lines = [
        marker,
        "-- 事实源: backend/services/semantic_field_registry.py",
        "-- 字典是唯一事实源: builtin 行不在当前 seed 里 ⇒ 已被字典删掉/改名",
        "-- ⇒ 留着就是事实源漂移。只删 builtin 行(template_confirmed/manual 是用户确认过的)。",
        "WITH {columns} AS (".format(columns=columns),
        "    VALUES",
        values,
        ")",
        "DELETE FROM semantic.semantic_field_aliases a",
        "WHERE a.source = 'builtin'",
        "  AND a.data_domain IN ({})".format(
            ", ".join("'{}'".format(_escape(d)) for d in domains)
        ),
        "  AND NOT EXISTS (",
        "      SELECT 1 FROM current_seed s",
        "      WHERE s.data_domain = a.data_domain",
        "        AND s.standard_field = a.standard_field",
        "        AND s.raw_alias = a.raw_alias",
    ]
    if extra_match:
        lines.append(extra_match)
    lines.append("  );")
    return "\n".join(lines) + "\n"


def render_prune_sql(rows: Sequence[dict]) -> str:
    """渲染「陈旧 builtin 行清理」语句(两段: products 域 + 其它域)。

    第一段(``PRUNE_MARKER``)只含 **products 域**、**3 元组** ——
    已执行迁移 20261202 / 20261203 的自检按这个形状数「字典派生的
    products 域 builtin 行数」(见 :data:`PRUNE_OTHER_DOMAINS_MARKER` 的说明)。

    第二段含**其它域**(当前是 orders)、**4 元组**(带 platform_code) ——
    平台限定行是另一条记录, 少了 platform_code 会误删。
    """
    if not rows:
        raise ValueError("没有可生成的 seed 行")
    products_rows = [row for row in rows if str(row["data_domain"]) == "products"]
    other_rows = [row for row in rows if str(row["data_domain"]) != "products"]
    if not products_rows:
        raise ValueError("products 域没有可生成的 seed 行")
    segments = [
        _render_prune_segment(PRUNE_MARKER, products_rows, with_platform=False),
    ]
    if other_rows:
        segments.append(
            _render_prune_segment(
                PRUNE_OTHER_DOMAINS_MARKER,
                other_rows,
                with_platform=True,
            )
        )
    return "\n".join(segments)


def extract_prune_sql(sql_text: str) -> str:
    """从 SQL 资产里取出「陈旧 builtin 行清理」段(两段一起)。

    两段在资产里**相邻且都在最后**, 所以从标记取到文本末尾即可。
    ⚠ 注意: 已执行迁移 20261202 / 20261203 只数**第一段**(到第一个 ``;``),
    所以第一段的形状不能变(见 :data:`PRUNE_OTHER_DOMAINS_MARKER`)。
    """
    start = sql_text.find(PRUNE_MARKER)
    if start < 0:
        return ""
    return sql_text[start:].rstrip()


def render_seed_sql(rows: Sequence[dict]) -> str:
    """渲染 SQL seed 段(与现有 INSERT 段同形)。"""
    if not rows:
        raise ValueError("没有可生成的 seed 行")
    lines = [
        "-- 本段由 scripts/generate_semantic_alias_seed.py 生成, 请勿手工编辑。",
        "-- 事实源: backend/services/semantic_field_registry.py",
        "INSERT INTO semantic.semantic_field_aliases",
        "    (data_domain, standard_field, raw_alias, platform_code, normalized_alias, "
        "source, confidence, status)",
        "VALUES",
    ]
    body = [
        "    ('{data_domain}', '{standard_field}', '{raw_alias}', {platform_code}, "
        "'{normalized_alias}', '{source}', {confidence:.3f}, '{status}')".format(
            data_domain=_escape(row["data_domain"]),
            standard_field=_escape(row["standard_field"]),
            raw_alias=_escape(row["raw_alias"]),
            platform_code=_render_platform_code(row.get("platform_code")),
            normalized_alias=_escape(row.get("normalized_alias") or ""),
            source=_escape(row["source"]),
            confidence=float(row["confidence"]),
            status=_escape(row["status"]),
        )
        for row in rows
    ]
    lines.append(",\n".join(body))
    lines.append(ON_CONFLICT_CLAUSE)
    lines.append("")
    lines.append(render_prune_sql(rows).rstrip("\n"))
    return "\n".join(lines) + "\n"


def render_normalized_tsv(rows: Sequence[dict]) -> str:
    """渲染归一化形态清单(TSV, 首行是列名)。"""
    lines = [
        "\t".join(
            (
                "data_domain",
                "standard_field",
                "raw_alias",
                "platform_code",
                "normalized_alias",
                "normalized_alias_history",
            )
        )
    ]
    for row in rows:
        lines.append(
            "\t".join(
                (
                    str(row["data_domain"]),
                    str(row["standard_field"]),
                    str(row["raw_alias"]),
                    str(row.get("platform_code") or ""),
                    str(row["normalized_alias"]),
                    str(row.get("normalized_alias_history") or ""),
                )
            )
        )
    return "\n".join(lines) + "\n"


def build_normalized_seed_rows(rows: Sequence[dict]) -> List[dict]:
    """把归一化形态展开成额外的 seed 行(参考用)。

    ⚠️ 这些行**默认不写进别名表**: 归一化会把不同指标压到同一形态
    (例: ``商品曝光次数.1`` → ``商品曝光次数``, 而后者是**总曝光量**的
    真实表头), 直接 seed 会把「去重曝光量」与「曝光量」混成一个。

    这里只做**归一化形态的登记**, 供阶段 C 的 PG 侧归一化匹配按
    (标准字段, 归一化形态) 二元组使用。
    """
    claimed = {
        (str(row["raw_alias"]), str(row.get("platform_code") or "")) for row in rows
    }
    extra: List[dict] = []
    for row in rows:
        normalized = str(row["normalized_alias"] or "")
        if not normalized or normalized == str(row["raw_alias"]):
            continue
        key = (normalized, str(row.get("platform_code") or ""))
        if key in claimed:
            continue
        claimed.add(key)
        extra.append(
            {
                "data_domain": row["data_domain"],
                "standard_field": row["standard_field"],
                "raw_alias": normalized,
                "platform_code": row.get("platform_code"),
                "source": row["source"],
                "confidence": row["confidence"],
                "status": row["status"],
                "normalized_alias": normalized,
                "normalized_alias_history": row.get("normalized_alias_history", ""),
            }
        )
    return extra


def parse_seed_rows(sql_text: str) -> List[Tuple[str, str, str, str, str, str, str]]:
    """解析 SQL 资产 INSERT 段里的 seed 行。

    只看 ``INSERT INTO semantic.semantic_field_aliases`` 到 ``ON CONFLICT``
    之间, 避免把建表语句里的其它括号当成 seed 行。

    Returns:
        ``(data_domain, standard_field, raw_alias, platform_code, source,
        confidence, status)`` 七元组; ``platform_code`` 为空串表示通用别名。
    """
    start = sql_text.find(_INSERT_HEAD)
    if start < 0:
        return []
    end = sql_text.find("ON CONFLICT", start)
    segment = sql_text[start:end] if end > 0 else sql_text[start:]
    rows: List[Tuple[str, str, str, str, str, str, str]] = []
    for match in _SEED_ROW_PATTERN.finditer(segment):
        rows.append(
            (
                match.group("data_domain"),
                match.group("standard_field"),
                match.group("raw_alias"),
                match.group("platform_code") or "",
                match.group("source"),
                match.group("confidence"),
                match.group("status"),
            )
        )
    return rows


def _row_key(row: object) -> Tuple[str, str, str, str]:
    """取一行的 (data_domain, standard_field, raw_alias, platform_code) 四元组。

    同时支持生成侧的 dict 与解析侧的 tuple。
    """
    if isinstance(row, dict):
        return (
            str(row.get("data_domain") or ""),
            str(row.get("standard_field") or ""),
            str(row.get("raw_alias") or ""),
            str(row.get("platform_code") or ""),
        )
    data_domain, standard_field, raw_alias, platform_code = list(row)[:4]
    return (
        str(data_domain),
        str(standard_field),
        str(raw_alias),
        str(platform_code or ""),
    )


def diff_seed_rows(
    generated: Sequence[dict],
    existing: Sequence[Tuple[str, ...]],
) -> Tuple[List[Tuple[str, str, str, str]], List[Tuple[str, str, str, str]]]:
    """比较生成结果与现有 seed 行。

    Returns:
        ``(missing, extra)`` —— ``missing`` 是生成有、现有没有的行;
        ``extra`` 是现有有、生成没有的行。
    """
    generated_keys = {_row_key(row) for row in generated}
    existing_keys = {_row_key(row) for row in existing}
    missing = sorted(generated_keys - existing_keys)
    extra = sorted(existing_keys - generated_keys)
    return missing, extra


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="由 semantic_field_registry 的字典生成 products 域别名 seed"
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="把生成的 SQL seed 打印到标准输出",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="与现有 SQL 资产的 INSERT 段比较; 不一致时打印差异并返回非零退出码(不写文件)",
    )
    parser.add_argument(
        "--normalized-stdout",
        action="store_true",
        help="打印归一化形态清单(TSV, 列名含 normalized_alias)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="把生成的 SQL seed 写到该文件(默认不写)",
    )
    parser.add_argument(
        "--normalized-output",
        default=None,
        help="把归一化形态清单写到该文件(默认不写)",
    )
    parser.add_argument(
        "--sql-asset",
        default=str(DEFAULT_SQL_ASSET),
        help="--check 用来比较的 SQL 资产路径",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    rows: List[dict] = []
    for domain in SEED_DOMAINS:
        rows.extend(build_domain_alias_records(domain))
    rows.sort(
        key=lambda row: (
            str(row.get("data_domain") or ""),
            str(row.get("standard_field") or ""),
            str(row.get("platform_code") or ""),
            str(row.get("raw_alias") or ""),
        )
    )

    if args.check:
        asset_path = Path(args.sql_asset)
        if not asset_path.is_file():
            print(f"[语义别名 seed] 找不到 SQL 资产: {asset_path}")
            return 2
        asset_text = asset_path.read_text(encoding="utf-8", errors="replace")
        existing = parse_seed_rows(asset_text)
        missing, extra = diff_seed_rows(rows, existing)
        print(f"[语义别名 seed] 事实源: backend/services/semantic_field_registry.py")
        print(f"[语义别名 seed] 生成 {len(rows)} 条, 现有 {len(existing)} 条")
        generated_prune = render_prune_sql(rows)
        asset_prune = extract_prune_sql(asset_text)
        if asset_prune.strip() != generated_prune.strip():
            print("[语义别名 seed] 差异: 陈旧 builtin 行清理段不一致")
            print("[语义别名 seed] 资产里的清理段与当前字典不一致")
            return 1
        if not missing and not extra:
            print("[语义别名 seed] 一致: 无差异")
            return 0
        print(f"[语义别名 seed] 差异: 缺失 {len(missing)} 条, 多余 {len(extra)} 条")
        for key in missing:
            print(
                "  - 缺失: ('{0}', '{1}', '{2}', platform={3})".format(
                    key[0], key[1], key[2], key[3] or "NULL"
                )
            )
        for key in extra:
            print(
                "  - 多余: ('{0}', '{1}', '{2}', platform={3})".format(
                    key[0], key[1], key[2], key[3] or "NULL"
                )
            )
        return 1

    if args.normalized_stdout:
        sys.stdout.write(render_normalized_tsv(rows))

    if args.output:
        Path(args.output).write_text(
            render_seed_sql(rows), encoding="utf-8", newline="\n"
        )
        print(f"[语义别名 seed] 已写入 {args.output}")
    elif args.stdout or not args.normalized_stdout:
        sys.stdout.write(render_seed_sql(rows))

    if args.normalized_output:
        Path(args.normalized_output).write_text(
            render_normalized_tsv(rows), encoding="utf-8", newline="\n"
        )
        print(f"[语义别名 seed] 归一化形态已写入 {args.normalized_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
