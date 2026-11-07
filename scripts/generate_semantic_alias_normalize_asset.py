"""生成 sql/semantic/semantic_alias_normalize_asset.sql（SQL 资产正本）。

资产内容：
1. ``semantic.normalize_alias(text)``            —— PG 侧归一化(与 Python 侧同规则)
2. ``semantic.resolve_alias_normalized(...)``     —— 按归一形态解析标准字段
3. products 域别名 seed(含 normalized_alias)      —— 由后端字典派生

单一事实源：``backend/services/semantic_field_registry.py`` 的字典。
本脚本**自包含**(直接 import 字典), 不依赖任何临时文件, 可随时重生成复核。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_TARGET = ROOT / "sql" / "semantic" / "semantic_alias_normalize_asset.sql"

sys.path.insert(0, str(ROOT))

from backend.services.semantic_field_registry import (  # noqa: E402
    DOMAIN_SEMANTIC_ALIASES,
    normalize_semantic_alias,
)

HEADER = """-- 语义别名归一化解析能力 —— 2026-11-08
--
-- 背景
-- ----
-- `semantic.fact_products_atomic` 通过 `semantic.resolve_alias()` 从行的 `raw_data`
-- 里按**逐字相等**取标准字段值。真实表头却带各种修饰:
--
--   "销售额（已付款订单） (SGD)"   ← 口径后缀 + 币种后缀
--   "商品曝光次数.1"                ← Excel 多级表头展开后的重名列
--   "买家支付(RMB)" / "利润（rmb）"  ← 币种后缀
--   "*商品sku" / "下单时间\\n"        ← 必填星号 / 换行
--
-- ⇒ 逐字相等时命中率 0/45, shopee 商品域 25810 行的标准字段**全部为空**。
--
-- 本资产提供**归一化**的解析能力:
--   * `semantic.normalize_alias(text)` —— 与 `backend/services/semantic_field_registry.py`
--     的 `normalize_semantic_alias()` **同规则**(迁移里做 fail-closed 逐条比对);
--   * `semantic.resolve_alias_normalized(...)` —— 按归一形态匹配, 并支持
--     **口径沿革**(平台改口径词后仍能命中)。
--
-- ⚠ 归一化**只用于匹配**, 原始列名一律保留在 raw_data 里。
-- ⚠ 归一化**不剥口径后缀**(「已下单」/「已付款」是不同业务事实, 剥了就混了)。

CREATE SCHEMA IF NOT EXISTS semantic;


-- 归一化: 与 Python 侧 `normalize_semantic_alias()` 逐条等价。
--
-- 步骤(顺序固定, 与 Python 侧一致):
--   1. 去首尾空白;
--   2. 全角标点 → 半角;
--   3. 剥末尾币种/币种名称括号后缀;
--   4. 去必填星号;
--   5. 去所有空白(含全角空格);
--   6. 去下划线;
--   7. 去末尾 ".N" 序号后缀;
--   8. 大小写折叠。
CREATE OR REPLACE FUNCTION semantic.normalize_alias(input TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    text_value TEXT;
    inner_value TEXT;
BEGIN
    -- 1 + 2: 去首尾空白 + 全角标点转半角
    text_value := translate(
        regexp_replace(
            regexp_replace(
                btrim(COALESCE(input, '')),
                '^[[:space:]]+', ''
            ),
            '[[:space:]]+$', ''
        ),
        '（）：，。、％＋－／＿',
        '():,,.%+-/_'
    );

    -- 3a: 末尾「三个字母」的币种括号, 例 "(SGD)" / "(rmb)"
    text_value := regexp_replace(text_value, '\\s*\\([A-Za-z]{3}\\)\\s*$', '');

    -- 3b: 末尾「像币种」的其它括号(最多 12 字符, 内部不含括号)
    IF substring(text_value from '\\s*\\([^()]{0,12}\\)\\s*$') IS NOT NULL THEN
        inner_value := substring(text_value from '([^()]{0,12})\\s*$');
        IF inner_value ~ '^[A-Za-z]{3}$'
           OR inner_value ~ '(元|币|美元|人民币|美金|欧元|日元)' THEN
            text_value := regexp_replace(text_value, '\\s*\\([^()]{0,12}\\)\\s*$', '');
        END IF;
    END IF;

    -- 4: 必填星号
    text_value := replace(text_value, '*', '');
    -- 5: 所有空白(含全角空格 U+3000 —— PG 的 [[:space:]] 不保证包含它)
    text_value := replace(text_value, chr(12288), '');
    text_value := regexp_replace(text_value, '[[:space:]]+', '', 'g');
    -- 6: 下划线
    text_value := replace(text_value, '_', '');
    -- 7: 末尾 ".N" 序号后缀(Excel 重名列)
    text_value := regexp_replace(text_value, '\\.[0-9]+$', '');
    -- 8: 大小写折叠
    RETURN lower(btrim(text_value));
END;
$$;


-- 按归一形态解析标准字段。
--
-- 与 `semantic.resolve_alias()` 的区别: **逐字相等 → 归一后相等**。
-- 其它语义完全一致(domain 优先于全局、platform/granularity 可为空即通用、
-- confidence 优先、manual > template_confirmed > builtin)。
--
-- ⚠ 归一后的 key 可能有碰撞(例 "商品曝光次数" 与 "商品曝光次数.1" 归一后同名)
--   ⇒ 取字典序最小的一个, 与 Python 侧 `resolve_alias_from_row()` 的取值顺序一致。
CREATE OR REPLACE FUNCTION semantic.resolve_alias_normalized(
    raw_data JSONB,
    data_domain TEXT,
    standard_field TEXT,
    platform_code TEXT DEFAULT NULL,
    granularity TEXT DEFAULT NULL
) RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    normalized_keys JSONB;
    resolved_value TEXT;
BEGIN
    IF raw_data IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT jsonb_object_agg(src.norm_key, src.norm_value)
    INTO normalized_keys
    FROM (
        SELECT DISTINCT ON (normed.norm_key) normed.norm_key, normed.norm_value
        FROM (
            SELECT semantic.normalize_alias(e.key) AS norm_key, e.value AS norm_value
            FROM jsonb_each_text(raw_data) e
        ) normed
        WHERE normed.norm_key IS NOT NULL AND normed.norm_key <> ''
        ORDER BY normed.norm_key, normed.norm_value
    ) src;

    IF normalized_keys IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT NULLIF(normalized_keys ->> alias.normalized_alias, '')
    INTO resolved_value
    FROM semantic.semantic_field_aliases alias
    WHERE alias.status = 'active'
      AND alias.data_domain IN (resolve_alias_normalized.data_domain, '*')
      AND alias.standard_field = resolve_alias_normalized.standard_field
      AND (
          alias.platform_code IS NULL
          OR alias.platform_code = resolve_alias_normalized.platform_code
      )
      AND (
          alias.granularity IS NULL
          OR alias.granularity = resolve_alias_normalized.granularity
      )
      AND alias.normalized_alias IS NOT NULL
      AND normalized_keys ? alias.normalized_alias
    ORDER BY
      CASE
          WHEN alias.data_domain = resolve_alias_normalized.data_domain THEN 0
          ELSE 1
      END,
      CASE
          WHEN alias.platform_code = resolve_alias_normalized.platform_code THEN 0
          ELSE 1
      END,
      CASE
          WHEN alias.granularity = resolve_alias_normalized.granularity THEN 0
          ELSE 1
      END,
      alias.confidence DESC,
      CASE alias.source
        WHEN 'manual' THEN 0
        WHEN 'template_confirmed' THEN 1
        ELSE 2
      END,
      alias.id
    LIMIT 1;

    RETURN resolved_value;
END;
$$;
"""

SEED_HEADER = """

-- ── products 域别名 seed ──────────────────────────────────────────────
--
-- 只登 products 域: 以 ``data_domain='*'`` 落全局别名会在**所有**数据域优先生效
-- (域内桶覆盖全局桶), 等于把「商品」这类列名在 orders 域也提升成语义身份
-- ⇒ 跨域污染。
--
-- `raw_alias` = 人能读懂的原始写法; `normalized_alias` = 实际用于匹配的形态。
-- 口径沿革时二者不同: 原写法「销售额（已确定订单）」↔ 匹配形态「销售额(已下单)」。
INSERT INTO semantic.semantic_field_aliases
    (data_domain, standard_field, raw_alias, normalized_alias, source, confidence, status)
VALUES
"""

SEED_FOOTER = """
ON CONFLICT (
    data_domain,
    standard_field,
    raw_alias,
    COALESCE(platform_code, ''),
    COALESCE(granularity, '')
)
DO UPDATE SET updated_at = NOW(),
              normalized_alias = EXCLUDED.normalized_alias,
              status = EXCLUDED.status;
"""


def _collect_products_aliases() -> list[tuple[str, str, str, str]]:
    """从字典派生 products 域别名 (domain, standard_field, raw_alias, normalized_alias)。

    只登记**当前口径词**的形态: 旧口径词(「已确定订单」)只出现在**结构化列名**里,
    raw_data 的 key 里没有 ⇒ PG 侧不需要做沿革折算, 也不必为沿革多插一行
    (那会撞 (domain, field, raw_alias) 的唯一约束)。
    """
    rows: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}
    for standard_field, aliases in DOMAIN_SEMANTIC_ALIASES.get("products", {}).items():
        for raw_alias in aliases:
            normalized = normalize_semantic_alias(raw_alias)
            if not normalized:
                continue
            key = ("products", standard_field, normalized)
            if key in rows:
                continue
            rows[key] = ("products", standard_field, raw_alias, normalized)
    return sorted(rows.values(), key=lambda item: (item[1], item[3]))


def main() -> int:
    aliases = _collect_products_aliases()
    if not aliases:
        print("[FAIL] 派生出 0 条 products 域别名, 拒绝生成空资产")
        return 1

    lines = []
    for domain, standard_field, raw_alias, normalized in aliases:
        raw_sql = raw_alias.replace("'", "''")
        norm_sql = normalized.replace("'", "''")
        lines.append(
            f"    ('{domain}', '{standard_field}', '{raw_sql}', '{norm_sql}', "
            f"'builtin', 1.000, 'active')"
        )

    content = HEADER + SEED_HEADER + ",\n".join(lines) + "\n" + SEED_FOOTER
    ASSET_TARGET.parent.mkdir(parents=True, exist_ok=True)
    ASSET_TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"[OK] 已生成资产: {ASSET_TARGET} ({len(content)} bytes, 别名 {len(aliases)} 条)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
