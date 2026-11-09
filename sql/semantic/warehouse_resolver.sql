CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 仓名归一：妙手原始仓名 → 规范仓代码
--
-- 真相点
-- --------
-- 对照表 ``core.dim_warehouse_name_aliases``（源仓名 → 仓码）是**唯一**的登记载体。
-- 本文件把「怎么查这张表」收敛成**一个函数**，让语义层、状态层刷新服务、
-- Metabase 模型共用同一套口径 —— 不再各自写一份查表 / 拼接逻辑。
--
-- 为什么必须显式登记，不能靠字符串规则猜
-- --------------------------------------------
-- 两边的仓名**字符串本身就不一样**：
--     源仓名「新加坡」              ↔ 规范仓名「新加坡仓」
--     源仓名「菲律宾仓库（维修工具）」 ↔ 规范仓名「菲律宾仓（维修工具）」
-- 「去掉仓字后缀」这类规则套上去会得到「马来仓仓」这种垃圾值；
-- 规则一多就必然出现某个仓漏配或错配。
--
-- 猜错的后果是**把货算到别的仓** —— 仓错 ⇒ 库龄错 ⇒ 档位错 ⇒ 底线错 ⇒ 定价错，
-- 而且这种错**在页面上完全看不出来**。
--
-- 查不到就返回 NULL
-- ----------------
-- 归一不出来时**留空**，绝不静默归到一个仓（与
-- ``backend/services/inventory/inventory_state_warehouse_map_service.py``
-- 的降级口径一致）。留空 ⇒ 该行不参与仓级定价，但**仍参与** SKU 级聚合。
--
-- 表不存在时也返回 NULL
-- ----------------------
-- 迁移 ``current_schema_20261205_warehouse_name_aliases`` 未跑的环境
-- （老库 / 半迁移库）不应该让整个语义层视图建不起来 ⇒ 这里显式判 ``to_regclass``。
--
-- 比较口径
-- --------
-- **精确匹配**（不做 TRIM / 大小写折叠）：对照表里登记的字符串就是采集文件里的
-- 原始字符串。Python 侧 ``WarehouseNameResolver.resolve`` 走的也是同一张表的
-- 精确查表 ⇒ 两边逐字一致。改成 TRIM 属于「看起来更宽容、实际多一份规则」，
-- 两侧必须同时改，否则会出现「SQL 能归一、Python 归不出一」的撕裂。
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION semantic.resolve_warehouse_code(p_warehouse_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_code TEXT;
BEGIN
    IF p_warehouse_name IS NULL OR BTRIM(p_warehouse_name) = '' THEN
        RETURN NULL;
    END IF;

    IF to_regclass('core.dim_warehouse_name_aliases') IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT a.warehouse_code
      INTO v_code
      FROM core.dim_warehouse_name_aliases a
     WHERE a.source_warehouse_name = p_warehouse_name
     LIMIT 1;

    RETURN v_code;
END;
$$;
