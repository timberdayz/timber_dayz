"""事实表 ``shop_id`` 列的语义定性(SSOT 单一权威定义)。

这一列到底是什么
----------------
``b_class.fact_*`` 事实表有一列叫 ``shop_id``。它的**真实语义**是:

    「**采集层写进来的原始标识**」—— 也就是采集器当时手上有的那个字符串,
    原样落库。它**不承载店铺身份**。

为什么需要这份文件
------------------
这一列的**名字长得像身份列**(就叫 ``shop_id``), 于是任何新代码 —— 包括
AI 助手 —— 都会自然地拿它当身份用。2026-11-07 上线的同步侧拦截器就是这么
干的: 拿事实表的**列** ``shop_id`` 去和行内 ``raw_data['shop_id']`` 比对,
判「不一致」就不写云端。

⚠️ 但这一列在不同链路上装的是**完全不同的东西**:

============  ==========================================  ============
链路          列 ``shop_id`` 实际装的                          实测取值
============  ==========================================  ============
shopee        平台店铺编号                                    ``1407964586``
tiktok        导出店名                                        ``DAWIE Mall``
miaoshou 采集 采集方代号(数据来源, 不是店铺)                  ``xihong``
============  ==========================================  ============

⇒ 拿它当身份列, 等于拿「平台编号」去比「账号 ID」, **同源的两层也永远不相等**。
⇒ 实测(本地 dev 库 65,197 行): 旧判据误杀 **3,781 行正常数据**,
   而这些行在语义层能唯一归属到店铺 —— 数据本来是好的, 是在同步侧被扔掉的。

身份到底由谁决定
----------------
**由行内 ``raw_data`` 里的稳定锚点决定, 由语义层归一。**

* 行内 ``raw_data['shop_account_id']`` —— 最可靠的一路(改名不变、跨平台一致);
* 行内 ``raw_data['platform_shop_id']`` —— 平台编号(会被采集器污染, 次之);
* 行内中文 ``店铺`` 列 / ``store_name`` —— 兜底。

语义层把它们当作**并列候选**,去主数据候选池
(``sql/semantic/shop_identity_resolution_candidates.sql``)里反查,
候选数恰好为 1 ⇒ 归属唯一; 否则落 ``unknown`` 并由看板告警。

⇒ **规范店铺键由语义层输出**, 不是这一列。

这一列的正当职责
----------------
**去重分区**。upsert 冲突键是
``(platform_code, shop_id, data_domain, granularity, data_hash)``,
这一列参与分区, 保证「同一份数据重采时覆盖同一行, 而不是插重复行」。

⚠️ 因此**不要改这一列的取值** —— 改了会动冲突键, 重采会插重复行
(仓库文档 ``docs/superpowers/plans/2026-11-06-shop-identity-alignment-remediation.md``
§9 已把这个风险列为「v7.12.6 踩过」)。

已有的成文说明(本文件把它们**收敛**到一处, 其它地方引用这里)
----------------------------------------------------------------
* ``sql/semantic/orders_atomic.sql`` —— 构造身份候选集时**显式排除**
  ``xihong`` / ``unknown`` / ``none``(采集方代号不是店铺身份);
* ``sql/semantic/inventory_snapshot.sql`` —— 说明这一列「以前叫 shop_id,
  但它是采集层写进来的原始标识 …… 现在保留原值(去重分区口径不变),
  最后再解析成规范键」;
* ``docs/superpowers/plans/2026-11-06-shop-identity-alignment-remediation.md``
  §0.3① —— 说明只有语义层读这一列, 且**只当身份候选**。
"""

from __future__ import annotations


#: 事实表 ``shop_id`` 列的定性(一句话版本)。
FACT_SHOP_ID_COLUMN_SEMANTICS = (
    "采集层写进来的原始标识; 不承载店铺身份 —— "
    "店铺身份由 raw_data 内的稳定锚点决定, 规范键由语义层输出; "
    "本列只参与 upsert 去重分区。"
)

#: 采集方标识 —— 表示「这批数据来自哪个采集器」, **不是**店铺身份。
#:
#: ⚠️ 出现在行内身份键里时必须排除, 否则会把「采集方」当成「店铺」。
#:
#: **唯一执行点** = 候选池构建时剔除
#: (``sql/semantic/shop_identity_resolution_candidates.sql`` + 它的物化副本)
#: —— 链路侧**不再各写一份**字面量排除。
#: **登记载体** = ``core.collection_source_identifiers``
#: (迁移 ``current_schema_20261223_collection_source_identifiers`` 播种,
#:  与本常量逐条一致, 由 ``backend/tests/test_inventory_warehouse_identity_ssot.py``
#:  守护两侧不漂移)。
COLLECTION_SOURCE_IDS: frozenset[str] = frozenset(
    {
        "xihong",
        "miaoshou_real_001",
        "unknown",
        "none",
        "",
    }
)

#: 事实表 ``shop_id`` 列在**各采集链路**上实际承载的语义(诊断用)。
#:
#: ⚠️ 这张表是**事实描述**, 不是规范 —— 它的用途是让看到 ``shop_id`` 列的人
#: 立刻明白「这一列在不同链路上不是同一个东西」。
FACT_SHOP_ID_COLUMN_BY_CHAIN: dict[str, str] = {
    "shopee": "平台店铺编号(如 1407964586)",
    "tiktok": "导出店名(如 DAWIE Mall / FIORO SG)",
    "miaoshou": "采集方代号(如 xihong) —— 数据来源, 不是店铺",
}
