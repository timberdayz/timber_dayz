"""《店铺身份唯一台账声明》—— 店铺身份体系的**唯一权威声明**。

为什么要有这一份文件
--------------------
仓库里其实**早就有**一份自称「SSOT 单一权威定义」的文件
(``modules/core/fact_identity_columns.py``) —— 但它的对象只是**事实表的
``shop_id`` 某一列**(那列到底装的是什么、能不能当身份用), **不是整个身份体系**。

于是形成了两份各说一半的成文声明:

* ``fact_identity_columns.py`` 说「身份由行内 ``raw_data`` 里的稳定锚点决定」;
* 语义层的候选池 SQL 说「规范店铺键由语义层输出」。

⇒ 两份各自成立, 合起来**没有一份**说清「谁是台账 / 谁是派生 / 谁只是快照 /
哪个信号最可信」的单一真源声明。2026-11-11 的复核把它记成裂缝之一:
「身份唯一台账从未被成文声明」。

本文件补上这一份声明, 并把「认人优先级」收成**一处**定义:

* 优先级只在这里定义(``IDENTITY_SIGNAL_PRIORITY``);
* Python 侧入库收敛服务**导入**它(不抄第二份);
* 两份 SQL 资产里的 ``resolution_priority`` 数字由守护测试
  (``backend/tests/test_shop_identity_ssot_declaration.py``)断言与本文件一致
  —— 改了 SQL 不改声明, 测试必须红。

仓库先例: ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS``
(「唯一执行点」+ 两侧不漂移守护测试 ``backend/tests/test_inventory_warehouse_identity_ssot.py``)。

四层身份数据
------------
店铺身份在系统里一共以**四种角色**存在。它们**不是**一个东西, 权威性完全不同:

============================  ==================================  ==========  ==================================
层                            对象                                谁能写       出问题怎么办
============================  ==================================  ==========  ==================================
**台账**(ledger)              ``core.shop_accounts``              只有人      对账脚本报警 + 人工修
                              ``core.shop_account_aliases``       (人工确认
                                                                    后落笔)
**派生**(derived)             ``semantic.shop_identity_           机器刷新    指纹比对 + 一致性闸门
                              resolution_candidates``(视图)                  (副本与正本对不上就拦下)
                              ``..._v2_mv``(物化副本)
**快照**(snapshot)            ``b_class.fact_*`` 里已落库的业务    采集写入,  照既定决策**不修**
                              数据行身上的身份戳                  写完不再动  (只保未来, 历史不修)
**映射**(mapping)             ``core.dim_shops``(看板显示名映射)  跟随输出键  跟随输出键
============================  ==================================  ==========  ==================================

逐层说清楚
~~~~~~~~~~

**① 台账 = 唯一真源**
    账号本体(``core.shop_accounts``)与别名(``core.shop_account_aliases``)
    是店铺身份**唯一应当被写入**的地方。**只有人**能写 —— 人工确认后落笔。
    自动流程(巡店探测、同步入库收敛)只允许**读**与**提案**, 不允许改台账
    (2026-11 的错位事故就是自动流程直接改写台账造成的)。

**② 派生 = 从台账算出来, 会漂移**
    候选池视图与它的物化副本是**两份独立复制的 SQL**, 各自从台账算一遍 ⇒
    可能与台账、与彼此都不一致。它们**不是**真源: 出问题时**重刷**即可,
    不要手改副本(改了会被下一次刷新覆盖)。正本与副本的一致性由指纹比对守卫。

**③ 快照 = 当时写下的身份戳, 不是台账**
    ``b_class.fact_*`` 里那些已经落库的业务数据行, 身上的身份键是**采集那一刻**
    写进去的(可能带着当时的错编号)。它们**不承载权威身份**, 只记录历史事实。
    出问题时的既定处置是**不修**(只保未来): 改历史行会动 upsert 冲突键, 造成重复行。

    ⚠️ **一处例外**(2026-11-11 用户决策): **日/周粒度**的历史行**整体废弃重采**。
       详见 :data:`DISPOSABLE_GRANULARITIES`。
       月粒度 / 快照粒度**仍不修**。

**④ 映射 = 看板显示名, 跟随输出键**
    ``core.dim_shops`` 是看板显示名的映射表, 键是**派生**出来的
    (``COALESCE(platform_shop_id, shop_account_id, id)``)。它**不是**真源,
    也不该被单独手工维护 —— 台账改了, 重新同步即可。

认人优先级(唯一定义处)
----------------------
「同一个身份值同时命中多路时先听谁的」—— 只在这里定义一次:

* Python 侧: ``IDENTITY_SIGNAL_PRIORITY``(入库收敛 ``reconcile_identity`` 逐个信号反查);
* SQL 侧: 两份候选池资产里的 ``resolution_priority``(同一套口径的数字)。

⚠️ **不要在本文件之外再写第二份**。要改优先级, 改这里 + 改 SQL 资产,
守护测试会强制两侧一致。

一处已知例外(本轮明确不动)
--------------------------
**归属判定**与**输出键**是两件事:

* **归属判定**(这串身份值属于哪个店) —— **账号章优先**(见上面的优先级);
* **输出键**(报表那一列最终填什么值) —— 当前是
  ``COALESCE(platform_shop_id, shop_account_id, id)``, 即**平台编号优先**,
  与归属判定的方向**相反**。

这不是笔误: 输出键被看板显示名映射表(``core.dim_shops.shop_id``)的**键依赖**
锁死 —— 改了会让显示名整片落空。

* **短期不影响**归属正确性 —— 认不认得出店铺由「归属判定」决定;
* **长期有真风险** —— 平台一旦换编号, 输出键跟着变, 看板关联会断;
* ⇒ **本轮登记为已知风险, 不动**。将来解除的条件:
  **看板显示名映射表先解耦键依赖**(即 ``core.dim_shops`` 改用与输出键无关的
  稳定键, 且所有引用方完成迁移), 才轮到单独一次改造来改输出键口径。

相关文件
--------
* 台账层的另一份声明(只讲事实表那一列): ``modules/core/fact_identity_columns.py``;
* 入库收敛实现: ``backend/services/shop_identity_reconciliation_service.py``;
* 候选池正本 / 副本: ``sql/semantic/shop_identity_resolution_candidates.sql``、
  ``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql``;
* 守护测试: ``backend/tests/test_shop_identity_ssot_declaration.py``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


# ---------------------------------------------------------------------------
# ① 台账层(唯一真源 —— 唯一应当被写入的地方)
# ---------------------------------------------------------------------------

#: 账号本体 —— 店铺账号的唯一登记处(人写)。
SHOP_ACCOUNT_TABLE = "core.shop_accounts"

#: 别名 —— 账号的其它叫法(导出店名 / 中文名 / 旧名 …), FK 指向
#: :data:`SHOP_ACCOUNT_TABLE` 的**整数主键** ``id``(不是字符串账号编码)。
SHOP_ALIAS_TABLE = "core.shop_account_aliases"

# ---------------------------------------------------------------------------
# ② 派生层(从台账算出来 —— 会漂移, 出问题重刷, 不手改)
# ---------------------------------------------------------------------------

#: 候选池正本(实时视图)。
CANDIDATE_POOL_VIEW = "semantic.shop_identity_resolution_candidates"

#: 候选池副本(物化视图) —— 与正本**各自**从台账算一遍 ⇒ 靠指纹比对保持一致。
CANDIDATE_POOL_MATERIALIZED_VIEW = "semantic.shop_identity_resolution_candidates_v2_mv"

# ---------------------------------------------------------------------------
# ③ 快照层(当时写下的身份戳 —— 不是台账, 不修)
# ---------------------------------------------------------------------------

#: 事实表族 —— 已落库的业务数据行, 身份键是采集那一刻写进去的。
FACT_TABLE_PATTERN = "b_class.fact_*"

#: **日/周粒度快照的例外处置**（2026-11-11 用户决策）。
#:
#: 默认处置仍是「不修历史」（见 :data:`IDENTITY_LAYERS` 的快照层）——
#: 逐行订正会动 upsert 冲突键, 造成重复行。
#:
#: 但**日粒度 / 周粒度**的历史行被明确豁免：
#:
#: * **为什么豁免**：这些粒度的历史行里, 店铺身份归属**大面积**错位
#:   （不是个别行错, 是整批错）⇒ 留着它们会持续污染看板与报表口径,
#:   而且**无法分辨**哪些行可信、哪些行已废 —— 越往后拖, 越没人敢用这些数。
#: * **处置方式**：**整体废弃重采**（不是逐行订正）。
#:   - 删掉整批日/周粒度事实行;
#:   - 修完采集侧代码后**重新采集**;
#:   - 语义层物化视图必须**同步重刷**, 否则看板读到的还是旧数据。
#:
#: ⚠️ 「删除」与「订正」是两件事：
#:    删干净了就不会撞 upsert 冲突键 ⇒ 不存在重复行风险。
#:
#: ⚠️ 本例外**只覆盖日/周粒度**；月粒度 / 快照粒度**仍按「不修」处置**
#:    （它们是经营口径的基准, 错了要人工判断, 不批量丢）。
#:
#: 依据: 用户 2026-11-11 决策 —— 「日、周粒度的数据都存在大量问题,
#: 本地和云端的日、周粒度数据都可以先进行清理了, 不要给历史越搞越麻烦」。
DISPOSABLE_GRANULARITIES: tuple[str, ...] = ("daily", "weekly")

#: 被豁免「整体废弃重采」的粒度 —— 与 :data:`DISPOSABLE_GRANULARITIES` 同一口径。
#:
#: 供守护测试断言「声明里的例外 == 代码里的清理范围」。
DISPOSABLE_GRANULARITY_SET: frozenset[str] = frozenset(DISPOSABLE_GRANULARITIES)

# ---------------------------------------------------------------------------
# ④ 映射层(看板显示名 —— 跟随输出键)
# ---------------------------------------------------------------------------

#: 看板显示名映射表 —— 键是**派生**出来的, 不该单独手工维护。
DISPLAY_NAME_MAPPING_TABLE = "core.dim_shops"


# ---------------------------------------------------------------------------
# 分层规则(机器可读 —— 供守护测试断言「分层没有漂移」)
# ---------------------------------------------------------------------------

#: 台账层。
LAYER_LEDGER = "ledger"
#: 派生层。
LAYER_DERIVED = "derived"
#: 快照层。
LAYER_SNAPSHOT = "snapshot"
#: 映射层。
LAYER_MAPPING = "mapping"


@dataclass(frozen=True)
class IdentityLayer:
    """一层身份数据的定性: **谁能写 / 权威性 / 出问题怎么办**。"""

    #: 层名(``ledger`` / ``derived`` / ``snapshot`` / ``mapping``)。
    name: str
    #: 这一层涉及的对象(表 / 视图 / 模式通配)。
    objects: tuple[str, ...]
    #: 谁能写。
    writer: str
    #: 权威性定性。
    authority: str
    #: 出问题怎么办。
    on_problem: str


#: 四层身份数据的定性 —— **唯一**一份。
IDENTITY_LAYERS: tuple[IdentityLayer, ...] = (
    IdentityLayer(
        name=LAYER_LEDGER,
        objects=(SHOP_ACCOUNT_TABLE, SHOP_ALIAS_TABLE),
        writer="只有人(人工确认后落笔); 自动流程只许读与提案",
        authority="唯一真源",
        on_problem="对账脚本报警 + 人工修",
    ),
    IdentityLayer(
        name=LAYER_DERIVED,
        objects=(CANDIDATE_POOL_VIEW, CANDIDATE_POOL_MATERIALIZED_VIEW),
        writer="机器刷新",
        authority="派生(不是真源)",
        on_problem="指纹比对 + 一致性闸门; 重刷副本, 不手改",
    ),
    IdentityLayer(
        name=LAYER_SNAPSHOT,
        objects=(FACT_TABLE_PATTERN,),
        writer="采集写入, 写完不再动",
        authority="不是真源(只是当时的事实)",
        on_problem=(
            "既定决策不修(只保未来); 改它会动 upsert 冲突键。"
            "**例外**: 日/周粒度因身份归属大面积错位 ⇒ 整体废弃重采"
            "(见 DISPOSABLE_GRANULARITIES); 月/快照粒度仍不修"
        ),
    ),
    IdentityLayer(
        name=LAYER_MAPPING,
        objects=(DISPLAY_NAME_MAPPING_TABLE,),
        writer="跟随输出键",
        authority="派生(不是真源)",
        on_problem="跟随输出键; 台账改了重新同步即可",
    ),
)


# ---------------------------------------------------------------------------
# 认人优先级(唯一定义处 —— 代码与 SQL 都从这里导出)
# ---------------------------------------------------------------------------

#: **认人优先级** —— 「同一个身份值同时命中多路时先听谁的」。
#:
#: ⚠️ **唯一定义处**: Python 侧入库收敛(``reconcile_identity``)导入它,
#:    SQL 侧的 ``resolution_priority`` 数字由守护测试断言与本文件一致。
#:    **不要在别处再写第二份**。
#:
#: 每一项为什么排这个位置:
#:
#: 1. ``shop_account_id`` —— **账号章**(我们发的唯一编号)。
#:    改名不变、跨平台一致、采集器写不坏 ⇒ 唯一能当作归属判据的稳定锚点。
#: 2. ``platform_shop_id`` —— 平台编号。**会被采集器污染**
#:    (把 URL 里读到的编号当成主数据)、平台换 ID 就失效 ⇒ 只能次之。
#: 3. ``shop_id`` —— 行内那列(Shopee 是平台编号 / TikTok 是导出店名)。
#:    编号索引查不到时会自动退回别名索引 ⇒ 对应 SQL 侧的 ``alias_match`` 那一路。
#: 4. ``store_name`` —— 店名, 兜底; 命中不到登记店名时同样退回别名索引。
IDENTITY_SIGNAL_PRIORITY: tuple[str, ...] = (
    "shop_account_id",
    "platform_shop_id",
    "shop_id",
    "store_name",
)

#: SQL 侧的同一套口径 —— ``resolution_method`` → ``resolution_priority``。
#:
#: 与两份候选池资产里的数字**逐条一致**(守护测试断言):
#: ``sql/semantic/shop_identity_resolution_candidates.sql`` 与
#: ``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql``。
RESOLUTION_METHOD_PRIORITY: Mapping[str, int] = {
    "shop_account_id": 1,
    "platform_shop_id": 2,
    "alias_match": 3,
    "store_name_match": 4,
}

#: Python 侧信号 → SQL 侧候选方法的对应关系。
#:
#: 两个世界的第四路名字不同(``store_name`` vs ``store_name_match``),
#: 第三路在 Python 侧叫 ``shop_id``(行内那列), 在 SQL 侧叫 ``alias_match``
#: (行内编号查不到就靠别名认人)。**顺序**才是口径, 名字只是各自世界的叫法。
SIGNAL_RESOLUTION_METHOD: Mapping[str, str] = {
    "shop_account_id": "shop_account_id",
    "platform_shop_id": "platform_shop_id",
    "shop_id": "alias_match",
    "store_name": "store_name_match",
}


# ---------------------------------------------------------------------------
# 输出键口径(已知例外 —— 本轮不动)
# ---------------------------------------------------------------------------

#: 语义层输出的**规范店铺键**表达式(当前口径)。
#:
#: ⚠️ **平台编号优先**, 与上面的归属判定(账号章优先)**方向相反**。
#:    这不是笔误 —— 它被看板显示名映射表 ``core.dim_shops.shop_id`` 的键依赖锁死。
#: ⇒ **本轮不动**; 将来解除的条件 = 看板显示名映射表先解耦键依赖。
CANONICAL_SHOP_KEY_EXPRESSION = "COALESCE(platform_shop_id, shop_account_id, id)"

#: 输出键口径的处置说明(供文档与看板引用)。
CANONICAL_SHOP_KEY_POLICY = (
    "输出键当前为平台编号优先, 与归属判定(账号章优先)方向相反; "
    "被 core.dim_shops.shop_id 的键依赖锁死 ⇒ 本轮不动, "
    "将来解除条件 = 看板显示名映射表先解耦键依赖。"
)
