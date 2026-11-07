"""把 Shopee 流量「月度」模板的日期解析改成「按伴生周期自动判断」。

背景
----
``shopee_analytics__monthly_slash_v3``(模板 id=321)声明::

    {"strict": true, "value_kind": "single_date",
     "date_format": "dd/mm/yyyy", "target_field": "metric_date",
     "source_column": "日期"}

而平台实际导出的「日期」列是**横杠**:``01-10-2026`` / ``01-11-2026``。
⇒ ``parse_date_by_declared_format`` 用 ``strptime(raw, "%d/%m/%Y")`` 解析失败 ⇒
``raw_data_importer`` 抛 ``failed to parse metric_date from source_column=日期`` ⇒
**整份文件入库失败**。

实测(开发库, 2026-11-07):``public.catalog_files`` 里 shopee/analytics 共 107 个文件,
4 个 status='failed', 错误全部是上面那句, 采集时间跨 2026-11-02 ~ 11-07
—— 即**每次采集都失败一次**, 该域月度数据从 2026-08 起就没再进来过。

为什么是「自动判断」而不是直接改成 dd-mm-yyyy
-------------------------------------------
1. 分隔符是**平台行为**, 不是业务事实 —— 平台随时可能再换一次。
   钉死 ``dd-mm-yyyy`` 只是把「猜错就整文件失败」换成「猜错就整文件失败」。
2. 历史模板 320(``shopee_analytics__monthly_dash_v2``, archived, created_by='codex')
   用的是 ``dd-mm-yyyy``; 历史落库数据
   (``b_class.fact_shopee_analytics_monthly`` 2278 行 / 181 个不同 metric_date,
   覆盖 2026-02-01 ~ 2026-07-31) 也证实是**日-月-年**。
   ⇒ 业务含义已经确定, 只有分隔符在漂。
3. 解析器**早就支持** ``auto_by_companion_period``
   (``modules/services/smart_date_parser.py``), 前端下拉框也早有
   「系统根据伴生周期自动判断」这一项 —— 只是没人用它。

为什么候选集限定在「日-月-年」家族
--------------------------------
候选 = ``["dd-mm-yyyy", "dd/mm/yyyy"]`` —— **同一语义、不同分隔符**。

这一点很关键:``strptime`` 的分隔符是**硬约束**, ``"01-10-2026"`` 只有
``dd-mm-yyyy`` 能解析成功, ``dd/mm/yyyy`` 直接 ValueError。
⇒ 候选集限定在单一语义家族 ⇒ **结构上最多一个匹配** ⇒
既不会因为「日 vs 月」歧义报错, 也不依赖文件期间元数据是否准确。

(如果不限定家族, 候选里同时有 ``dd-mm-yyyy`` 与 ``mm-dd-yyyy``,
``"01-10-2026"`` 两者都能解析 ⇒ 只能靠文件期间消歧 ⇒ 期间不准时反而失败。)

为什么**两处**都要改
--------------------
入库时读的是**变体**上的解析规则:

* ``core.field_mapping_templates``(legacy 模板行) —— 投影来源
* ``core.field_mapping_template_variants``(变体) —— **入库实际消费的那一份**

⇒ 只改模板不改变体 ⇒ 当前态仍然失败; 只改变体不改模板 ⇒
下次重投影会把它打回旧值。两个都改, 且都用同一份规则 ⇒ 之后无论走
「保存模板」还是「重投影」, 结果都一致。

为什么不需要回填
----------------
该模板至今**一行数据都没落进去**(``fact_shopee_analytics_monthly`` 的
max(metric_date) 停在 2026-07-31, 与 2026-10/11 的失败文件无关) ⇒
改解析方式不产生任何历史行的指纹变化 ⇒ **无回填风险**。

幂等
----
只在规则形状匹配时改写(``date_format`` 属于日-月-年单值格式且
``value_kind == 'single_date'``); 已经改成 auto 的不会再被匹配 ⇒ 可重复执行。
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261123_shopee_analytics_monthly_date_format"
down_revision = "current_schema_20261122_remove_disabled_shop_collection_scopes"
branch_labels = None
depends_on = None


_SCHEMA = "core"

#: 目标维度 —— 只动 Shopee 流量「月度」这一个模板。
_TARGET_PLATFORM = "shopee"
_TARGET_DATA_DOMAIN = "analytics"
_TARGET_GRANULARITY = "monthly"

#: 会被改写的「日-月-年」单值日期格式。
#:
#: ⚠️ 这里**故意**不包含 ``mm-dd-yyyy`` / ``mm/dd/yyyy``(美式):
#: 美式报表的业务含义是「月-日-年」, 与本模板的日-月-年**不同**,
#: 混进候选集会让同一个值有两种解释 ⇒ 违反「定不了就报警, 绝不静默猜一个」。
_DAY_FIRST_SINGLE_FORMATS = {"dd/mm/yyyy", "dd-mm-yyyy"}

#: 改写后的目标形态。
_NEW_DATE_FORMAT = "auto_by_companion_period"
_NEW_FORMAT_CANDIDATES = ["dd-mm-yyyy", "dd/mm/yyyy"]

#: 回滚时恢复的原始声明。
_ORIGINAL_DATE_FORMAT = "dd/mm/yyyy"


def _rewrite_rules(rules: object, *, target: str) -> list | None:
    """把规则里的日期格式改写成目标形态(双向)。

    - ``target == auto_by_companion_period``:
      把「日-月-年」单值格式改写成 auto + 候选集。
    - ``target == dd/mm/yyyy``(回滚):
      把 auto 形态改回原始声明, 并去掉 ``format_candidates``。

    Returns:
        新的规则列表; 若无需改动则返回 None。
    """
    if not isinstance(rules, list) or not rules:
        return None
    changed = False
    rewritten: list = []
    for rule in rules:
        if not isinstance(rule, dict):
            rewritten.append(rule)
            continue
        new_rule = dict(rule)
        value_kind = str(new_rule.get("value_kind") or "single_date").strip()
        date_format = str(new_rule.get("date_format") or "").strip()

        if target == _NEW_DATE_FORMAT:
            matched = (
                value_kind == "single_date"
                and date_format.lower() in _DAY_FIRST_SINGLE_FORMATS
            )
            if matched:
                changed = True
                new_rule["date_format"] = _NEW_DATE_FORMAT
                new_rule["format_candidates"] = list(_NEW_FORMAT_CANDIDATES)
        else:
            # 回滚: 只认「本迁移写出去的那种 auto 形态」,
            # 不能碰用户自己配的其它 auto 规则。
            matched = (
                value_kind == "single_date"
                and date_format.lower() == _NEW_DATE_FORMAT
                and list(new_rule.get("format_candidates") or [])
                == list(_NEW_FORMAT_CANDIDATES)
            )
            if matched:
                changed = True
                new_rule["date_format"] = target
                new_rule.pop("format_candidates", None)
        rewritten.append(new_rule)
    if not changed:
        return None
    return rewritten


def apply_rewrite(bind, *, target: str) -> dict:
    """把目标维度内的模板行与变体都改写成目标形态。

    对外暴露(而不是只留 ``upgrade``/``downgrade``)是为了让守护测试
    能用 ``session.run_sync(...)`` 跑**生产上真正执行的那份代码**,
    而不是测试里复刻一遍的副本(复刻会漂移)。
    """
    stats = {"templates_updated": 0, "variants_updated": 0}

    # ── 1. legacy 模板行(投影来源) ──────────────────────────────────
    template_sql = sa.text(
        f"""
        SELECT id, field_parse_rules
        FROM {_SCHEMA}.field_mapping_templates
        WHERE platform = :platform
          AND data_domain = :data_domain
          AND granularity = :granularity
          AND status = 'published'
          AND field_parse_rules IS NOT NULL
        """
    )
    template_rows = bind.execute(
        template_sql,
        {
            "platform": _TARGET_PLATFORM,
            "data_domain": _TARGET_DATA_DOMAIN,
            "granularity": _TARGET_GRANULARITY,
        },
    ).fetchall()

    updated_template_rules: dict[int, list] = {}
    for row in template_rows:
        rules = row.field_parse_rules
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except (TypeError, ValueError):
                continue
        rewritten = _rewrite_rules(rules, target=target)
        if rewritten is None:
            continue
        updated_template_rules[int(row.id)] = rewritten

    if updated_template_rules:
        update_sql = sa.text(
            f"""
            UPDATE {_SCHEMA}.field_mapping_templates
            SET field_parse_rules = CAST(:rules AS jsonb),
                updated_at = now()
            WHERE id = :template_id
            """
        )
        for template_id, rules in updated_template_rules.items():
            bind.execute(
                update_sql,
                {
                    "template_id": template_id,
                    "rules": json.dumps(rules, ensure_ascii=False),
                },
            )
            stats["templates_updated"] += 1

    # ── 2. 变体(入库实际消费的那一份) ────────────────────────────────
    #    变体通过 template_version_id → versions.family_id → families
    #    关联到目标维度。family 有 platform/data_domain/granularity 三个列。
    variant_sql = sa.text(
        f"""
        SELECT v.id, v.field_parse_rules
        FROM {_SCHEMA}.field_mapping_template_variants AS v
        JOIN {_SCHEMA}.field_mapping_template_versions AS ver
          ON ver.id = v.template_version_id
        JOIN {_SCHEMA}.field_mapping_template_families AS f
          ON f.id = ver.family_id
        WHERE f.platform = :platform
          AND f.data_domain = :data_domain
          AND f.granularity = :granularity
          AND v.field_parse_rules IS NOT NULL
        """
    )
    variant_rows = bind.execute(
        variant_sql,
        {
            "platform": _TARGET_PLATFORM,
            "data_domain": _TARGET_DATA_DOMAIN,
            "granularity": _TARGET_GRANULARITY,
        },
    ).fetchall()

    update_variant_sql = sa.text(
        f"""
        UPDATE {_SCHEMA}.field_mapping_template_variants
        SET field_parse_rules = CAST(:rules AS jsonb)
        WHERE id = :variant_id
        """
    )
    for row in variant_rows:
        rules = row.field_parse_rules
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except (TypeError, ValueError):
                continue
        rewritten = _rewrite_rules(rules, target=target)
        if rewritten is None:
            continue
        bind.execute(
            update_variant_sql,
            {
                "variant_id": int(row.id),
                "rules": json.dumps(rewritten, ensure_ascii=False),
            },
        )
        stats["variants_updated"] += 1

    return stats


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    return apply_rewrite(bind, target=_NEW_DATE_FORMAT)


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    return apply_rewrite(bind, target=_ORIGINAL_DATE_FORMAT)


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
