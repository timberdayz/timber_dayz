"""发布 miaoshou inventory 字段映射模板 v3（28 列）。

背景
----
2026-09 妙手 ERP 的库存导出在 V2 canonical 重写后多了 3 个字段：

    次品库存 / 暂存库存 / 备注

现行 published 模板 309 只有 25 列（2026-06-01 发布），治理层因此把
`public.catalog_files` id=2764 判成 `breaking_drift` 挂起，文件永远进不了
b_class，库龄表也就永远是 0 行。

实测（2026-10-21）
------------------
    模板 309（25 列） vs 2026-09-15 采集文件（28 列）
      新增 3 列：次品库存、暂存库存、备注
      删除 0 列
      匹配率 25/28 = 89.3%   ← 与 catalog_files 里的报错完全一致

本迁移做两件事
--------------
1. 基于 309 复制出 v3，header_columns / header_bindings 扩到 28 列
2. 309 置 archived（**不改它的历史内容**）

⚠️ **不要动 `core.collection_configs.template_id`**
------------------------------------------------
那个字段是 **FK → `core.collection_config_templates(id)`**（配置默认值模板：
日期口径 / 执行模式 / 默认 cron），**不是**字段映射模板。
config 30 上的 `template_id = 15` 指向 `miaoshou-miaoshou_real_001-weekly`，
**它是有效的**，不修。

字段映射模板在入库时由 `backend/services/template_matcher.py::find_matching_template`
按 `(platform, data_domain, granularity) + status='published' + version DESC` **自动选取**。
所以只要 v3 是 published 且 version 最高，它就会被选中 —— 不需要任何配置引用。

注意
----
* **不要动** `core.field_mapping_template_items` / `core.field_mapping_template_versions`
  —— 实测 309 的 items 是空表，模板内容全在 `core.field_mapping_templates` 一行里
  （header_columns / header_bindings / deduplication_fields / field_parse_rules）。
* `field_parse_rules` 原样保留：`metric_date = __file_date_from__`。
  这一条决定了库龄锚点，本迁移**不能**改它。
* 这 3 列对库龄计算无影响 —— 库龄只用 `可用库存` / `库存总量` /
  `*单价（元）` / `*总价（元）`，全部已在 25 列里。
"""

from alembic import op
import json
from sqlalchemy import text


revision = "current_schema_20261021_inventory_template_v3"
down_revision = "current_schema_20261021_sku_pricing_creator_commission"
branch_labels = None
depends_on = None


BASE_TEMPLATE_ID = 309
NEW_TEMPLATE_NAME = "miaoshou_inventory__snapshot_v3"
NEW_VERSION = 3

# 新增列及其相对 309 的插入位置。
# 用「after/before + 锚列名」而不是硬编码下标 —— 锚列找不到时直接报错，
# 避免列序错位后静默产出错模板。
NEW_COLUMNS = [
    ("次品库存", "after", "预占库存"),
    ("暂存库存", "after", "次品库存"),
    ("备注", "before", "创建时间"),
]

# header_bindings 单条的字段顺序（与 309 现有 25 条保持一致，便于 diff）
BINDING_KEY_ORDER = (
    "aliases",
    "position",
    "raw_name",
    "required",
    "confidence",
    "sample_type",
    "display_name",
    "semantic_key",
    "semantic_role",
    "hash_participates",
)

BINDING_DEFAULTS = {
    "aliases": [],
    "required": False,
    "confidence": 0.5,
    "sample_type": "string",
    "semantic_key": None,
    "semantic_role": None,
    "hash_participates": False,
}


def _as_list(value):
    """jsonb 列在 text() 查询里可能以 JSON 文本返回，这里统一成 list。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    parsed = json.loads(str(value))
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    return list(parsed)


def _build_columns(base_columns):
    columns = list(base_columns)
    for name, mode, anchor in NEW_COLUMNS:
        if name in columns:
            continue
        if anchor not in columns:
            raise RuntimeError(
                f"inventory template v3 缺少锚列 {anchor!r}，无法确定 {name!r} 的插入位置"
            )
        index = columns.index(anchor) + (1 if mode == "after" else 0)
        columns.insert(index, name)
    return columns


def _build_bindings(base_bindings, new_columns):
    by_name = {str(b.get("raw_name")): b for b in base_bindings if isinstance(b, dict)}
    result = []
    for position, name in enumerate(new_columns):
        source = by_name.get(name)
        merged = dict(BINDING_DEFAULTS)
        if source:
            for key, value in source.items():
                if key not in ("position", "raw_name", "display_name"):
                    merged[key] = value
        merged["position"] = position
        merged["raw_name"] = name
        merged["display_name"] = name
        merged.setdefault("aliases", [])
        result.append({key: merged.get(key) for key in BINDING_KEY_ORDER})
    return result


def _fetch_base_template(bind):
    row = (
        bind.execute(
            text(
                """
                SELECT id, platform, data_domain, granularity, account, sub_domain,
                       header_row, sheet_name, encoding, usage_count, success_rate,
                       header_columns, header_bindings, deduplication_fields,
                       field_parse_rules, created_by, notes
                FROM core.field_mapping_templates
                WHERE id = :template_id
                """
            ),
            {"template_id": BASE_TEMPLATE_ID},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise RuntimeError(
            f"基础模板 core.field_mapping_templates.id={BASE_TEMPLATE_ID} 不存在，"
            "inventory 模板 v3 无法发布"
        )
    return row


def _find_existing_v3(bind):
    """幂等守卫：已存在 published 且 28 列的 inventory 模板时直接复用。"""
    row = (
        bind.execute(
            text(
                """
                SELECT id FROM core.field_mapping_templates
                WHERE data_domain = 'inventory'
                  AND status = 'published'
                  AND field_count = 28
                ORDER BY id DESC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    return row["id"] if row else None


def _insert_v3(bind, base, columns, bindings):
    result = bind.execute(
        text(
            """
            INSERT INTO core.field_mapping_templates (
                platform, data_domain, granularity, account, template_name, version,
                status, field_count, usage_count, success_rate, created_by, created_at,
                updated_by, updated_at, notes, sub_domain, header_row, sheet_name,
                encoding, header_columns, deduplication_fields, field_parse_rules,
                header_bindings
            ) VALUES (
                :platform, :data_domain, :granularity, :account, :template_name, :version,
                'published', :field_count, 0, 0.0, 'migration', now(),
                'migration', now(), :notes, :sub_domain, :header_row, :sheet_name,
                :encoding, CAST(:header_columns AS jsonb),
                CAST(:deduplication_fields AS jsonb),
                CAST(:field_parse_rules AS jsonb),
                CAST(:header_bindings AS jsonb)
            )
            RETURNING id
            """
        ),
        {
            "platform": base["platform"],
            "data_domain": base["data_domain"],
            "granularity": base["granularity"],
            "account": base["account"],
            "template_name": NEW_TEMPLATE_NAME,
            "version": NEW_VERSION,
            "field_count": len(columns),
            "notes": (
                "2026-09 妙手导出新增 次品库存/暂存库存/备注,补齐到 28 列"
            ),
            "sub_domain": base["sub_domain"],
            "header_row": base["header_row"],
            "sheet_name": base["sheet_name"],
            "encoding": base["encoding"],
            "header_columns": json.dumps(columns, ensure_ascii=False),
            "deduplication_fields": json.dumps(
                _as_list(base["deduplication_fields"]), ensure_ascii=False
            ),
            "field_parse_rules": json.dumps(
                _as_list(base["field_parse_rules"]), ensure_ascii=False
            ),
            "header_bindings": json.dumps(bindings, ensure_ascii=False),
        },
    )
    return result.scalar()


def upgrade() -> None:
    bind = op.get_bind()

    existing_id = _find_existing_v3(bind)
    if existing_id is not None:
        # 已发布过：只补齐归档，不重复插入
        bind.execute(
            text(
                "UPDATE core.field_mapping_templates SET status='archived' "
                "WHERE id = :template_id"
            ),
            {"template_id": BASE_TEMPLATE_ID},
        )
        return

    base = _fetch_base_template(bind)
    columns = _build_columns(_as_list(base["header_columns"]))
    bindings = _build_bindings(_as_list(base["header_bindings"]), columns)

    if len(columns) != 28:
        raise RuntimeError(
            f"inventory 模板 v3 列数应为 28，实际 {len(columns)}：{columns}"
        )
    if len(bindings) != len(columns):
        raise RuntimeError(
            f"header_bindings 条数({len(bindings)})与 header_columns 列数({len(columns)})不一致"
        )

    _insert_v3(bind, base, columns, bindings)

    bind.execute(
        text(
            "UPDATE core.field_mapping_templates SET status='archived' "
            "WHERE id = :template_id"
        ),
        {"template_id": BASE_TEMPLATE_ID},
    )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        text(
            "DELETE FROM core.field_mapping_templates "
            "WHERE template_name = :template_name AND data_domain = 'inventory'"
        ),
        {"template_name": NEW_TEMPLATE_NAME},
    )
    bind.execute(
        text(
            "UPDATE core.field_mapping_templates SET status='published' "
            "WHERE id = :template_id"
        ),
        {"template_id": BASE_TEMPLATE_ID},
    )
