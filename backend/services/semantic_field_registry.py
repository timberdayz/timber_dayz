from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

from backend.services.currency_extractor import get_currency_extractor


# ── 口径（caliber）维度 ────────────────────────────────────────────────
#
# 平台报表里同一个指标常带**多套统计口径**, 它们不是措辞差异, 是不同的业务事实:
#
#   * ``placed`` —— 已下单(买家提交了订单, 未必付款)
#   * ``paid``   —— 已付款(买家完成了支付)
#
# 2026-11-08 生产实测(shopee 商品月报, 7090 行可比): 两套口径的销售额
# **平均差 5.15%, 最大差 175.89** ⇒ 绝不能归一化成同一个值, 也不能互相冒充。
#
# 平台还会**改词**(报表改版): shopee 的「已确定订单」是「已下订单」的旧叫法
# (实测两者差 4.25%, 属同一口径的措辞迁移), 由 :data:`PLATFORM_CALIBER_HISTORY` 登记。
#
# 「已确认订单」在真实数据里**没有任何数值**(只作为旧报表遗留列存在),
# 无从判断它对应哪个口径 ⇒ 刻意**不折算**, 宁可落 unknown, 也不猜。
CALIBER_PLACED = "placed"
CALIBER_PAID = "paid"


SEMANTIC_FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "order_id": {
        "label": "订单号",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "required": True,
        "aliases": ["订单号", "订单编号", "order id"],
    },
    "line_id": {
        "label": "订单明细行 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["order_line_id", "line id", "order line id", "明细行ID"],
    },
    "product_id": {
        "label": "商品 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["产品id", "商品id", "产品ID", "商品ID", "product id"],
    },
    "platform_sku": {
        "label": "平台 SKU",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["平台sku", "平台 sku", "product_sku", "产品sku", "商品sku"],
    },
    "sku_id": {
        "label": "SKU 编号",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["sku id", "SKU ID", "SKU编号"],
    },
    "service_id": {
        "label": "服务 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["service id", "服务ID", "服务编号"],
    },
    "shop_id": {
        "label": "店铺 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "system_scope": True,
        "aliases": ["店铺", "店铺ID", "shop id"],
    },
    "warehouse_name": {
        "label": "仓库",
        "kind": "dimension",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["warehouse", "仓库", "仓库名称", "warehouse name"],
    },
    "gmv_band": {
        "label": "GMV 区间",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["gmv band", "gmv range", "GMV区间", "GMV 区间"],
    },
    "metric_date": {
        "label": "统计日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["日期", "统计日期", "data_date", "date"],
    },
    "period_start_date": {
        "label": "周期开始日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["开始日期", "周期开始日期", "date_from"],
    },
    "period_end_date": {
        "label": "周期结束日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["结束日期", "周期结束日期", "date_to"],
    },
    "period_start_time": {
        "label": "周期开始时间",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["开始时间", "小时", "时段", "hour", "time", "start time"],
    },
    "period_end_time": {
        "label": "周期结束时间",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["结束时间", "结束小时", "end hour", "end time"],
    },
    "order_date": {
        "label": "下单日期",
        "kind": "time",
        "domain": "orders",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["下单日期", "订单日期", "下单时间"],
    },
    "visitor_count": {
        "label": "访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["访客数", "visitors", "visitor count"],
    },
    # ⚠ 商品级访客数 —— 归属 **products 域**(2026-11-10 从 analytics 域迁出)。
    #   理由: analytics 域的「商品访客数」是 **tiktok 流量报表的访客口径**
    #   (tiktok 当天的访客量), 架构契约已批准它映射到 ``visitor_count``
    #   (见 ``docs/architecture/SEMANTIC_FIELD_RULES.md`` 的 Analytics Rules)
    #   ⇒ 它不能再被登记成 analytics 域的 ``product_visitor_count``,
    #   否则同一个列名会同时指向两个标准字段(SSOT 硬约束)。
    #   本字段现在只服务 products 域的「商品访客数量」(实测 25809 行有值)。
    "product_visitor_count": {
        "label": "商品访客数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        # ⚠ 全局别名**不许**再放中文「商品访客数」—— 那个列名在 analytics 域
        #   归 ``visitor_count``(tiktok 平台限定)。中文裸名留在全局表 = 任何域
        #   的同名列都会被认领 ⇒ 一个列名指向两个标准字段。
        #   products 域的真实表头「商品访客数量」登记在
        #   :data:`PRODUCTS_SEMANTIC_ALIASES` 里(域限定)。
        "aliases": ["product visitors", "product visitor count"],
    },
    "page_views": {
        "label": "浏览量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["浏览量", "pv", "page views", "views"],
    },
    "impressions": {
        "label": "曝光量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["曝光量", "曝光次数", "impression", "impressions"],
    },
    "clicks": {
        "label": "点击量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["点击量", "点击次数", "click", "clicks"],
    },
    "click_rate": {
        "label": "点击率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["点击率", "click rate", "ctr"],
    },
    "conversion_rate": {
        "label": "转化率",
        "kind": "metric",
        "domain": "analytics",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["转化率", "conversion rate", "cvr", "CVR"],
    },
    "order_count": {
        "label": "订单量",
        "kind": "metric",
        "domain": "analytics",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单量", "订单数", "order count", "订单数量", "orders"],
    },
    "sku_order_count": {
        "label": "SKU 订单量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["SKU订单量", "sku orders", "sku order count"],
    },
    "gmv": {
        "label": "GMV",
        "kind": "metric",
        "domain": "common",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["GMV"],
    },
    "total_transaction_amount": {
        "label": "总交易金额",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["总交易金额", "total transaction amount"],
    },
    "bounce_rate": {
        "label": "跳失率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["跳失率", "bounce rate"],
    },
    # ── shopee 专属流量字段(2026-11-09 补登) ───────────────────────
    #
    # 实测(开发库 2026-11-09, `b_class.fact_shopee_analytics_monthly` 2354 行):
    #   * 「新访客」「现有访客」「新关注者」「平均停留时长」「平均页面访问数」
    #     **2354/2354 行全部有值**; 按既有清洗链(去千分位逗号 / 空格 / 破折号)
    #     **2354/2354 全部可解析成数值**(实测存在 `1,004` 这种带千分位的值)。
    #   * 「访客数」== 「新访客」+「现有访客」—— **2354/2354 行精确相等**
    #     ⇒ 三者说的是**同一个「访客」事实的三个切面**(总量 / 新客 / 老客),
    #     但**粒度不同**(访客数是总量, 新老是拆分)⇒ 各自独立成标准字段,
    #     **不合并**(合并会让人以为访客数 == 新访客)。
    #   * 「新关注者」≤「访客数」—— **0 行违反**(关注者是访客的子集)。
    #   * 「平均页面访问数」≈「页面浏览数」÷「访客数」—— 1814 行可用行里
    #     **全部**落在 ±0.02 内 ⇒ 它是**派生均值**, 与 page_views / visitor_count
    #     **不是同一个事实** ⇒ 独立成字段(不登记成 page_views 的别名)。
    #   * 「平均停留时长」是 **HH:MM:SS 字符串**(实测 2354/2354 行, 形如
    #     `00:00:42`, 区间 0~215 秒, 均值 36.5 秒)
    #     ⇒ **不能**套用普通数值清洗(否则 `01:30:00` 会被当成 `13000`)
    #     ⇒ 字段口径是**秒数**, 由视图专门换算(见 `analytics_atomic.sql`)。
    #   * tiktok 侧**没有**这 5 列(实测 tiktok monthly 1374 行的 raw_data
    #     key 里一个都没有)⇒ 标 ``platforms=("shopee",)``,
    #     巡检的平台诊断据此跳过 tiktok(否则报「tiktok 缺这 5 个指标」= 噪音)。
    "new_visitor_count": {
        "label": "新访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("shopee",),
        # ⚠ **只留英文别名**: 中文「新访客」是 shopee 流量报表的**真实表头**,
        #   由 ``ANALYTICS_PLATFORM_ALIASES`` 逐字登记(平台限定)。
        #   放进全局别名表 = 任何域的「新访客」列都会被认领。
        "aliases": ["new visitors", "new visitor count"],
    },
    "returning_visitor_count": {
        "label": "现有访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("shopee",),
        "aliases": ["returning visitors", "returning visitor count"],
    },
    "new_follower_count": {
        "label": "新关注者数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("shopee",),
        "aliases": ["new followers", "new follower count"],
    },
    "avg_session_duration_seconds": {
        "label": "平均停留时长(秒)",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("shopee",),
        "aliases": ["average session duration seconds", "avg session duration"],
    },
    "avg_page_views_per_visitor": {
        "label": "平均页面访问数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("shopee",),
        "aliases": ["average page views per visitor", "avg page views per visitor"],
    },
    "sales_amount": {
        "label": "销售额(已废止)",
        "kind": "metric",
        "domain": "orders",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        # [*] 2026-11-08 废止: 源表已无「销售额/成交金额」这类列
        # ⇒ 该字段永远是 0 且与 `paid_amount` 抢同一个业务含义
        # ⇒ 保留字段但不再取数(见 semantic_field_registry 里的
        # `ORDER_RETIRED_FIELDS`)。
        "retired": True,
        "aliases": ["sales amount", "revenue", "sales", "销售额", "销售金额"],
    },
    "sales_volume": {
        "label": "销量",
        "kind": "metric",
        # [*] 2026-11-08: 订单域的件数列「销售数量」归 ``sales_volume``。
        # 理由: 契约(``DEFAULT_CONTRACTS["orders"]``)、模板确认、历史别名表
        # 三处口径一致 ⇒ 语义键不能为了与视图**物理列名**(``product_quantity``)
        # 对齐就改掉 —— 语义键是口径, 列名只是历史遗留。
        # (products 域的「件数(已付款订单)」仍登记在 ``DOMAIN_SEMANTIC_ALIASES``,
        #  两个域各管各的别名, 不存在跨域污染。)
        "domain": "orders",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        # ⚠ 「销售数量」实测是**行级件数**(同一订单内取值不同)⇒ 只做登记,
        # 不参与「第 2+ 行清空」(见 ``ORDER_LEVEL_QUANTITY_FIELDS``)。
        "order_level_quantity": True,
        # ⚠「销售数量」是**真实表头**(products 域的商品报表里也有这一列)
        # ⇒ 必须留在全局裸名里, 否则 products 域认领不到它。
        # orders 域是**封闭域** ⇒ 不会把全局裸名补进去(裸名在 orders 域
        # 指的是原币列), orders 域靠 ``ORDER_SEMANTIC_ALIASES`` 逐字登记。
        "aliases": ["sales volume", "qty", "units sold", "销量", "销售数量"],
    },
    "paid_amount": {
        "label": "实付金额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["实付金额", "paid amount", "buyer paid amount"],
    },
    "profit": {
        "label": "利润",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["利润", "profit"],
    },
    "purchase_amount": {
        "label": "采购金额",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["采购金额", "purchase amount"],
    },
    "platform_commission": {
        "label": "平台佣金",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["平台佣金", "platform commission", "commission"],
    },
    # ── orders 域的费用/金额字段(2026-11-08) ─────────────
    #
    # 为什么这里新增一批字段定义
    # --------------------
    # 原先 orders 域的取数写在 `sql/semantic/orders_atomic.sql`
    # 的手写 COALESCE 链里, 而字典里只有 `platform_commission`
    # 一个费用字段 ⇒ 字典不能完整描述 orders 域
    # 到底有哪些列, 费用类字段全部落空。
    #
    # 每个字段的 `aliases` 只登记**真实源表列名**。
    #
    # ⚠ 关键口径: 源表里每个金额列都有**两列**:
    #   `买家支付`(原币, 平均 240.11) 与 `买家支付(RMB)`(人民币, 平均 72.03)
    # 实测(2026-11 开发库): 两列**均非零且值相差约 3 倍** ⇒
    # 它们是**两个不同的业务事实**(原币值 vs 折算人民币值)。
    # 本字段的取数口径统一为**人民币口径**⇒ 只登记 `(RMB)` 变体。
    # (原币列不接任何标准字段 ⇒ 避免混币种)。
    "order_original_amount": {
        "label": "订单原始金额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": [
            "订单原始金额",
            "order original amount",
            "original amount",
        ],
    },
    "warehouse_operation_fee": {
        "label": "仓库操作费",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": [
            "仓库操作费",
            "warehouse operation fee",
            "warehouse fee",
        ],
    },
    "shipping_fee": {
        "label": "运费",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["运费", "shipping fee", "logistics fee"],
    },
    "promotion_fee": {
        "label": "推广费",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["推广费", "promotion fee", "campaign fee"],
    },
    "platform_deduction_fee": {
        "label": "平台扣费",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["平台扣费", "platform deduction fee", "deduction fee"],
    },
    "platform_voucher": {
        "label": "平台代金券",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["平台代金券", "platform voucher", "voucher amount"],
    },
    "platform_service_fee": {
        "label": "平台服务费",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["平台服务费", "platform service fee", "service fee"],
    },
    "estimated_settlement_amount": {
        "label": "预估回款金额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": [
            "预估回款金额",
            "estimated settlement amount",
            "estimated settlement",
        ],
    },
    "settled_amount": {
        "label": "已结算金额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["已结算金额", "settled amount"],
    },
    # ── 2026-11-08 补登: 「联盟/达人佣金」 ────────────────────────────
    # 业务事实: **付给达人/联盟的佣金**, 与「平台佣金」是**两笔钱**。
    #   (用户 2026-11-08 确认; 实测也印证两者量级完全不同)
    # 实测(2026-11 开发库):
    #   shopee `Shopee平台佣金(RMB)` 29629 行全有值, 均值 10.24, 合计 303398.64
    #   shopee `联盟佣金(RMB)`       29629 行全有值, 均值  0.76, 合计  22519.01
    #   tiktok `TikTok 平台佣金(RMB)` 4683 行有值,   均值 -5.54, 合计 -25966.22
    #   tiktok `达人佣金(RMB)`        4589 行有值,   均值 -3.85, 合计 -17662.47
    # ⇒ 独立字段, **不能**并进 ``platform_commission``。
    # ⚠ 不并入 ``ORDER_PLATFORM_COST_COMPONENT_FIELDS`` —— 那 6 项是
    #   「平台侧成本」, 联盟佣金是**付给达人**的, 混进去会与利润口径重复计算。
    "affiliate_commission": {
        "label": "联盟/达人佣金",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        # ⚠ **只留英文别名**: 中文「联盟佣金」「达人佣金」是 orders 域的真实表头,
        #   由 ``ORDER_PLATFORM_ALIASES`` 逐字登记(orders 是封闭域, 只登 (RMB) 变体)。
        "aliases": ["affiliate commission", "creator commission"],
    },
    # ── 2026-11-08 补登: 「卖家总收入」 ──────────────────────────────
    # 业务事实: **卖家侧的商品成交总收入**(不含运费等), 与「买家实付金额」**不同**。
    # 实测(2026-11 开发库, tiktok monthly 5254 行):
    #   `总收入(RMB)`      有值 4054 行(77%), 均值 79.47
    #   `买家实付金额(RMB)`          均值 78.66, 但与总收入**行级相等率仅 12.03%**
    #   `产品折后价格(RMB)`          与总收入相等率 69.24%
    #   `产品原价(RMB)`              与总收入相等率  0.06%
    #   按订单商品行数分组后: 单商品订单相等率 69.73% / 双商品订单 72.40%
    #   (多商品订单相等率**反而更高**) ⇒ 它**不是**单品价、也不是折后价之和
    #   ⇒ 是**订单级**的商品成交总额 ⇒ 独立的标准字段。
    "total_income": {
        "label": "卖家总收入",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        # ⚠ **只有 tiktok 有这一列**: shopee 侧的对应概念是「预估回款金额」
        #   /「已结算金额」, 那是**结算口径**(见 :func:`settled_amount`),
        #   不是商品收入口径 ⇒ 不能混为一谈。
        #   标 ``platforms`` ⇒ 巡检的平台诊断据此跳过 shopee
        #   (否则会报「shopee 缺 total_income」= 噪音, 而非真实缺口)。
        "platforms": ("tiktok",),
        # ⚠ **只留英文别名**: 中文「总收入」在源表里**还有裸名(原币)版本**
        #   (实测 tiktok 同时存在「总收入」与「总收入(RMB)」两列) ⇒ 中文裸名
        #   **绝不**进全局别名表, 否则会认到原币列。
        "aliases": ["total income", "seller total income"],
    },
    # ── orders 域的量类与卖家侧字段(2026-11-08) ──────────────────
    # ── orders 域的维度字段(2026-11-08) ───────────────────────────
    # 以前 orders 域的维度列名只散落在视图的手写 COALESCE 链里,
    # 字典里没有对应标准字段 ⇒ 巡检与模板推断都看不见它们。
    "order_status": {
        "label": "订单状态",
        "kind": "dimension",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        # ⚠ **只留英文别名**: 中文「订单状态」是 orders 域的**真实表头**,
        # 由 ``ORDER_SEMANTIC_ALIASES`` 逐字登记(orders 是封闭域)。
        # 放进全局别名表 = 任何域的「订单状态」列都会被认成身份键
        # (实测: products 域的「订单状态」被误认 ⇒ 污染身份推断)。
        # ⚠ **状态类字段不参与语义推断**(:func:`is_inferable_semantic_key`):
        #   状态类列名(「状态」「订单状态」…)一旦被认成语义键, 就会进
        #   身份/去重字段 ⇒ 状态一变就算新行 ⇒ 污染身份推断。
        #   既有守护: backend/tests/test_workbench_template_update_flow.py
        #   ⇒ 但它**仍然**登记在 orders 域别名表里(视图要能取到订单状态)。
        "inferable": False,
        "aliases": ["order status"],
    },
    "product_sku": {
        "label": "商品 SKU",
        "kind": "dimension",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        # ⚠ 同 ``order_status``: 中文「商品SKU」只登记在 orders 域限定表里,
        # 放全局会让别的域的「商品SKU」列被误认成身份键。
        "aliases": ["product sku"],
    },
    "seller_voucher": {
        "label": "卖家代金券",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        # ⚠ 卖家自己发的券 ⇒ **不是平台成本**, 不进 platform_total_cost_itemized。
        "aliases": ["seller voucher", "seller coupon"],
    },
    # ── [*] 2026-11-09: 下面 4 个字段被**复用**到 analytics(流量)域 ──
    #
    # 背景: tiktok 流量报表里有「商家直播 GMV」「商家直播间接 GMV」
    # 「商家视频 GMV」「商家视频间接 GMV」四列 —— 它们的**逐字表头**与
    # 这 4 个既有字段的中文别名**完全一致** ⇒ 复用既有字段, 不另造重复字段
    # (SSOT: 一个业务事实只允许一个标准字段)。
    #
    # ⚠ 实测(开发库 2026-11-09, tiktok monthly 1374 行):
    #   「商家直播 GMV」       **1374 行恒为 0**(0 行非零)
    #   「商家直播间接 GMV」   **1374 行恒为 0**
    #   「商家视频 GMV」       33 行非零
    #   「商家视频间接 GMV」   5 行非零
    #   ⇒ 前两列是「有列、但值恒 0」: 分不清「该渠道真的没成交」与
    #     「平台没回传」⇒ 文档里如实标注, **不**当成「渠道无生意」的结论。
    #
    # ⚠ 标 ``platforms=("tiktok",)``: 这几列**只有 tiktok 有**
    #   (shopee 流量报表 2354 行里一列都没有)⇒ 不标的话巡检会对 shopee
    #   报「缺这几个指标」= 噪音。
    "live_gmv": {
        "label": "商家直播 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["商家直播 GMV", "直播GMV", "live gmv"],
    },
    "live_attributed_gmv": {
        "label": "直播归因 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        # ⚠ 源表**没有**「商家直播归因 GMV」这一列(实测 1374 行的 key 里
        #   没有)⇒ 这个字段的别名是**推测性**的, 命中不了 ⇒ 恒 NULL。
        #   tiktok 真实的「直播归因」列是「达人直播归因 GMV」与
        #   「绑定账号直播归因 GMV」⇒ 那两列**另立字段**(见
        #   ``creator_live_attributed_gmv`` / ``bound_account_live_attributed_gmv``)。
        "aliases": ["商家直播归因 GMV", "直播归因GMV", "live attributed gmv"],
    },
    "live_indirect_gmv": {
        "label": "商家直播间接 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["商家直播间接 GMV", "直播间接GMV", "live indirect gmv"],
    },
    "video_gmv": {
        "label": "商家视频 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["商家视频 GMV", "视频GMV", "video gmv"],
    },
    "video_attributed_gmv": {
        "label": "视频归因 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        # ⚠ 同 ``live_attributed_gmv``: 源表**没有**「商家视频归因 GMV」这一列
        #   ⇒ 推测性别名命中不了 ⇒ 恒 NULL。tiktok 真实的「视频归因」列是
        #   「达人视频归因 GMV」与「绑定账号视频归因 GMV」⇒ 另立字段。
        "aliases": ["商家视频归因 GMV", "视频归因GMV", "video attributed gmv"],
    },
    "video_indirect_gmv": {
        "label": "商家视频间接 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["商家视频间接 GMV", "视频间接GMV", "video indirect gmv"],
    },
    # ── [*] 2026-11-09 新建: tiktok 流量报表里**其余**的 GMV 归因列 ──
    #
    # 为什么这批列**一个一个**独立成字段、且**绝不聚合**:
    # ────────────────────────────────────────────────────────────
    # 实测(开发库 2026-11-09, tiktok monthly 1374 行):
    #   13 个归因列合计 1,072,030.01, 总成交额 1,092,456.33(占 98.13%);
    #   但**逐行**看: 741 个可比行里 **376 行(50.7%)归因和 > 该行总额**,
    #   比值中位 **1.019**、最大 **2.000** ⇒ 同一笔成交被多个维度**重复记账**。
    #
    # ⇒ 业务上: 一笔单可能「在达人直播间看到 → 点商品卡下单 → 分享出去」,
    #   平台会把这单同时记到达人直播、商品卡等多个口径上。
    # ⇒ 所以这批列**只能单列看占比**, **绝不能相加**。
    #   (用户 2026-11-09 决定: 每列一个标准字段, 只单列展示, 绝不聚合。)
    "product_card_gmv": {
        "label": "商品卡 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        # ⚠ **稀疏指标**: 实测只有 198/1374 行有值(147 行非零)
        #   ⇒ 巡检会报「解析率约 14%」, 那是**源表本身稀疏**, 不是缺口。
        "aliases": ["product card gmv"],
    },
    "bound_account_live_attributed_gmv": {
        "label": "绑定账号直播归因 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        # ⚠ 实测 1374 行**恒为 0**(0 行非零)⇒ 有列无值, 不代表结论。
        "aliases": ["bound account live attributed gmv"],
    },
    "bound_account_video_attributed_gmv": {
        "label": "绑定账号视频归因 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["bound account video attributed gmv"],
    },
    "affiliate_video_attributed_gmv": {
        "label": "联盟视频归因 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["affiliate video attributed gmv"],
    },
    "creator_live_gmv": {
        "label": "达人直播 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["creator live gmv"],
    },
    "creator_live_attributed_gmv": {
        "label": "达人直播归因 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["creator live attributed gmv"],
    },
    "creator_live_indirect_gmv": {
        "label": "达人直播间接 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["creator live indirect gmv"],
    },
    "creator_video_gmv": {
        "label": "达人视频 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["creator video gmv"],
    },
    "creator_video_indirect_gmv": {
        "label": "达人视频间接 GMV",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "platforms": ("tiktok",),
        "aliases": ["creator video indirect gmv"],
    },
    "product_name": {
        "label": "商品名称",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": False,
        "identity_strength": "weak",
        "hash_warning": "商品名可能重名或改名，优先使用商品 ID / SKU。",
        "aliases": [
            "item_name",
            "product name",
            "item name",
            "商品",
            "商品名",
            "商品名称",
            "产品名称",
        ],
    },
    "item_status": {
        "label": "商品状态",
        "kind": "attribute",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "product_status",
            "listing_status",
            "item status",
            "product status",
            "发品状态",
            "商品状态",
        ],
    },
    # ── products 域的**口径变体**(2026-11-08 新增) ─────────────────────
    #
    # 平台报表对同一个指标给两套统计口径: 「已下单」与「已付款」。
    # 实测两者销售额平均差 5.15% ⇒ 是不同的业务事实, 必须是两个标准字段,
    # 不能靠别名混成一个。
    #
    # 主口径(``*_paid``)用无后缀的字段名承载(``sales_amount`` 等), 因为
    # 已付款口径与利润/实付字段自洽; 下单口径单独成字段。
    "sales_amount_placed": {
        "label": "销售额（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "销售额（已下单）",
            "销售额（已下订单）",
            "销售额（已确定订单）",
            "下单销售额",
        ],
    },
    "sales_volume_placed": {
        "label": "销量（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "销量（已下单）",
            "件数（已下单）",
            "件数（已下订单）",
            "件数（已确定订单）",
        ],
    },
    "order_count_placed": {
        "label": "订单量（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单量（已下单）", "已下单", "已下订单", "已确定订单"],
    },
    "conversion_rate_placed": {
        "label": "转化率（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["转化率（已下单）", "转化率（已下订单）", "转化率（已确定订单）"],
    },
    "order_conversion_rate_placed": {
        "label": "订单转化率（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "订单转化率（已下单）",
            "订单转化率（已下订单）",
            "订单转化率（已确定订单）",
        ],
    },
    "buyer_count_placed": {
        "label": "买家数（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["买家数（已下单）", "买家数（已下订单）", "买家数（已确定订单）"],
    },
    "aov_placed": {
        "label": "每笔订单销售额（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "每笔订单销售额（已下单）",
            "每笔订单销售额（已下订单）",
            "每笔订单销售额（已确定订单）",
        ],
    },
    # ── products 域此前**根本没有落点**的指标(2026-11-08 新增) ─────────
    #
    # 依据: shopee 商品月报 / tiktok 商品月报的真实表头。实测这些指标与
    # 已有字段**数值不同**(例: 同商品同月「转化率」10.56% vs「订单转化率」-),
    # 混用会造成口径错误 ⇒ 各自独立成字段。
    "order_conversion_rate": {
        "label": "订单转化率",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单转化率", "订单转化率（已付款订单）", "订单转化率（已下订单）"],
    },
    "unique_impressions": {
        "label": "去重商品曝光量",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "不重复的商品曝光量",
            "去重商品曝光次数",
            "去重商品曝光次数（视频）",
        ],
    },
    "unique_clicks": {
        "label": "去重点击量",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["不重复的商品点击量", "去重点击次数", "去重点击次数（视频）"],
    },
    # ── tiktok 点击成交转化率(CTOR)族 ────────────────────────────────
    #
    # 为什么单独成字段, 不并进 ``conversion_rate``:
    #   ``conversion_rate`` 声明的口径是 **已付款订单**(shopee 的「转化率（已付款订单）」);
    #   tiktok 的 CTOR 是**点击成交**口径 —— 分子是订单, 分母是点击(去重与否还分两套)。
    #   实测 tiktok 777 行里「CTOR（SKU 订单）」与「去重点击成交转化率（SKU 订单）」
    #   仅 615 行同值、样例值 8.57% vs 9.09% ⇒ **分母不同, 是两个指标**。
    #   并进 conversion_rate 就是口径混用 ⇒ 各自独立成字段。
    "click_to_order_rate": {
        "label": "点击成交转化率",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["CTOR（SKU 订单）"],
    },
    "unique_click_to_order_rate": {
        "label": "去重点击成交转化率",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["去重点击成交转化率（SKU 订单）"],
    },
    "buyer_count": {
        "label": "买家数",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "买家数（已付款订单）",
            "买家数（已下订单）",
            "买家数（已确定订单）",
        ],
    },
    "aov": {
        "label": "每笔订单销售额",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "每笔订单销售额（已付款订单）",
            "每笔订单销售额（已下订单）",
            "每笔订单销售额",
        ],
    },
    "add_to_cart_count": {
        "label": "加购件数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["加购次数", "加购次数（直播）", "加购次数（视频）"],
    },
    "add_to_cart_user_count": {
        "label": "加购用户数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": [
            "已加购的用户数",
            "已加购的用户数（直播）",
            "已加购的用户数（视频）",
        ],
    },
    "add_to_cart_rate": {
        "label": "加购率",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["加购率", "加购率（直播）", "加购率（视频）", "去重加购率"],
    },
    "refund_amount": {
        "label": "退款金额",
        "kind": "metric",
        # [*] 2026-11-08: products 与 orders **两个域**都有「退款金额」⇒
        # 归属改成 common(域限定别名表各自登记真实列名)。
        # 以前写成 products ⇒ orders 域的「退款金额(RMB)」无处安放。
        "domain": "common",
        "hash_eligible": False,
        "default_hash": False,
        "order_level_amount": True,
        "aliases": ["退款金额", "退款额"],
    },
    "refunded_item_count": {
        "label": "退款商品件数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["已退款的商品件数", "退款商品件数"],
    },
    # ── 渠道维度(tiktok 商品报表按商城/直播/视频/商品卡分块) ──────────
    "channel": {
        "label": "渠道",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["渠道", "channel", "商城页", "直播", "视频", "商品卡"],
    },
}

SEMANTIC_FIELD_ALIASES = {
    key: list(dict.fromkeys([key, *(definition.get("aliases") or [])]))
    for key, definition in SEMANTIC_FIELD_DEFINITIONS.items()
}

#: [*] 批次 E(E-4 / 规格 D1): 指标类字段参与去重的后果提示。
METRIC_HASH_WARNING = (
    "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。"
    "确认「这一行的身份就包含这个指标」再勾选。"
)

# [*] 批次 E(E-4 / 规格 D1): 指标类字段**不再禁止**参与 data_hash。
#
# 以前这里对 ``kind == "metric"`` 硬性拒绝, 理由是「度量不是行身份」。
# 那与业务概念直接冲突: 业务上「日期 + 订单数 + 店铺 = 这一行是什么」
# 是**复合业务键**, 不是实体身份。
#
# 现在统一放开:
#   * ``hash_eligible`` —— 允许(能不能用由用户在模板里勾选决定);
#   * ``default_hash`` —— 仍然是 False(不默认参与, 保持旧行为);
#   * ``hash_warning`` —— 带上后果提示, 让用户知道「指标变了会被当成新行」。
for _metric_key, _metric_meta in SEMANTIC_FIELD_DEFINITIONS.items():
    if _metric_meta.get("kind") == "metric":
        _metric_meta["hash_eligible"] = True
        _metric_meta.setdefault("hash_warning", METRIC_HASH_WARNING)

SEMANTIC_FIELD_META = {
    key: {
        meta_key: meta_value
        for meta_key, meta_value in definition.items()
        if meta_key != "aliases"
    }
    for key, definition in SEMANTIC_FIELD_DEFINITIONS.items()
}


#: 每个标准字段的说明文案(前端下拉框/tooltip 用)。
#:
#: [*] 批次 D: 以前这份文案住在前端 ``headerBindings.js`` 的副本里,
#:     后端这边没有 ⇒ 后端接口返回的字段没有描述, 前端只能自己抄一份。
#:     现在文案回到后端, 与字段定义放在一起, 一起作为唯一口径。
SEMANTIC_FIELD_DESCRIPTIONS: Dict[str, str] = {
    # ── shopee 独有的 5 个流量指标(2026-11-09 补登) ────────────────
    "new_visitor_count": "新访客数：本期第一次到店的访客。实测「访客数」= 新访客 + 现有访客，"
    "两者相加才是总访客数；目前只有 shopee 的流量报表有这一列。",
    "returning_visitor_count": "现有访客数：本期之前来过、本期又到店的访客。与「新访客数」相加等于「访客数」；"
    "目前只有 shopee 的流量报表有这一列。",
    "new_follower_count": "新关注者数：本期新增关注店铺的人数。实测恒小于等于访客数（关注者是访客的子集）；"
    "目前只有 shopee 的流量报表有这一列。",
    "avg_session_duration_seconds": "平均停留时长（秒）：一次访问的平均停留秒数。源表里是「时:分:秒」文本，"
    "系统已换算成秒数存放；目前只有 shopee 的流量报表有这一列。",
    "avg_page_views_per_visitor": "平均页面访问数：一个访客平均浏览的页面数，"
    "实测约等于「页面浏览数」除以「访客数」；目前只有 shopee 的流量报表有这一列。",
    "click_to_order_rate": "tiktok 的点击成交转化率(CTOR), 订单数除以点击数; 与转化率(已付款订单)分母不同, 不可混用。",
    "unique_click_to_order_rate": "tiktok 的去重点击成交转化率, 订单数除以去重点击数; 与全点击口径的 CTOR 数值不同。",
    "affiliate_commission": "付给达人/联盟的佣金，与「平台佣金」是两笔钱，不并入平台成本口径。",
    "total_income": "卖家侧商品成交总收入（不含运费），与「买家实付金额」不是同一个事实；目前只有 tiktok 有这一列。",
    "order_id": "识别同一笔订单的稳定身份字段。",
    "product_id": "平台或系统内识别同一商品的稳定身份字段。",
    "platform_sku": "平台侧商品规格编码，可作为商品身份字段。",
    "sku_id": "订单明细或商品规格粒度的身份字段。",
    "line_id": "订单明细行粒度的稳定身份字段。",
    "service_id": "服务类数据的稳定身份字段。",
    "shop_id": "系统自动加入 Data Hash 的店铺作用域字段。",
    "warehouse_name": "库存快照区分仓库粒度的维度字段。",
    "gmv_band": "按 GMV 区间出报表时可作为行粒度维度。",
    "metric_date": "日/周/月报表定位业务周期的时间字段。",
    "period_start_date": "区间型报表的开始日期。",
    "period_end_date": "区间型报表的结束日期。",
    "order_date": "订单发生日期，通常作为分析维度。",
    "product_name": "弱身份字段。商品名可能重名或改名，优先使用商品 ID / SKU。",
    "item_status": "标准化属性字段，状态变化不应默认改变 Data Hash。",
    # ── products 域的口径变体与新增指标(2026-11-08) ─────────────────
    "sales_amount_placed": "销售额（下单口径）。与「已付款口径」平均差 5.15%，不可混用。",
    "sales_volume_placed": "销量（下单口径）。与「已付款口径」不可混用。",
    "order_count_placed": "订单量（下单口径）。与「已付款口径」不可混用。",
    "conversion_rate_placed": "转化率（下单口径）。与「已付款口径」不可混用。",
    "order_conversion_rate_placed": "订单转化率（下单口径）。与商品转化率是不同指标。",
    "buyer_count_placed": "买家数（下单口径）。与「已付款口径」不可混用。",
    "aov_placed": "每笔订单销售额（下单口径）。与「已付款口径」不可混用。",
    "order_conversion_rate": "订单转化率。与商品转化率是不同指标，不可混用。",
    "unique_impressions": "去重商品曝光量。与商品展示量（曝光次数）是不同指标。",
    "unique_clicks": "去重点击量。与商品点击量（点击次数）是不同指标。",
    "buyer_count": "买家数。已付款口径。",
    "aov": "每笔订单销售额。已付款口径。",
    "add_to_cart_count": "加购件数。",
    "add_to_cart_user_count": "加购用户数。",
    "add_to_cart_rate": "加购率。",
    "refund_amount": "退款金额。",
    "refunded_item_count": "退款商品件数。",
    "channel": "渠道维度。tiktok 商品报表按商城/直播/视频/商品卡分块。",
    "gmv": "指标值，不参与 Data Hash。",
    "sales_amount": "指标值，不参与 Data Hash。",
    "sales_volume": "指标值，不参与 Data Hash。",
    "order_count": "指标值，不参与 Data Hash。",
    "period_start_time": "小时级或更细粒度报表的开始时间，可由用户手动加入 Data Hash。",
    "period_end_time": "小时级或更细粒度报表的结束时间，可由用户手动加入 Data Hash。",
    "visitor_count": (
        "访客数(UV)：店铺当天的访客数。Shopee 实测「新访客 + 现有访客」精确相加，"
        "即去重访客人数。两平台都是「一店一天一行」，口径基本一致，可横向比较。"
        "⚠ 待确认：TikTok 的列名叫「商品访客数」，平台定义为「当天访问过商品的访客」，"
        "它是否等于店铺当天的全部访客，当前数据判定不了。"
        "系统语义指标，不默认参与 Data Hash。"
    ),
    "product_visitor_count": (
        "商品访客数（商品域的「商品访客数量」：按单个商品统计的访客数）。"
        "注意：流量域的「商品访客数」已归 visitor_count，跨域同名不同义。"
        "系统语义指标，不默认参与 Data Hash。"
    ),
    "page_views": "系统语义指标，不参与 Data Hash。",
    "impressions": "系统语义指标，不参与 Data Hash。",
    "clicks": "系统语义指标，不参与 Data Hash。",
    "click_rate": "系统语义指标，不参与 Data Hash。",
    "conversion_rate": "系统语义指标，不参与 Data Hash。",
    "sku_order_count": "系统语义指标，不参与 Data Hash。",
    "total_transaction_amount": "系统语义指标，不参与 Data Hash。",
    "bounce_rate": "系统语义指标，不参与 Data Hash。",
    "paid_amount": "系统语义指标，不参与 Data Hash。",
    "profit": "系统语义指标，不参与 Data Hash。",
    "purchase_amount": "系统语义指标，不参与 Data Hash。",
    "platform_commission": "系统语义指标，不参与 Data Hash。",
    # ── tiktok 的 13 个 GMV 归因列(2026-11-09) ──────────────────────
    #
    # ⚠⚠ 这批列**只能单列看占比, 绝不能相加** ——
    # 实测(开发库 2026-11-09, tiktok monthly 1374 行): 13 列合计 1,072,030.01
    # vs 总成交额 1,092,456.33(占 98.13%); **逐行**看, 741 个可比行里
    # **376 行(50.7%)归因和 > 该行总额**(比值中位 1.019、最大 2.000)
    # ⇒ 同一笔成交被多个维度**重复记账**。
    "product_card_gmv": "商品卡 GMV：用户直接点商品小卡下单带来的成交。源表里只有 198/1374 行有值，是稀疏指标。",
    "live_gmv": "商家直播 GMV：商家自己直播间带来的成交。实测 1374 行恒为 0，分不清「真的没成交」与「平台没回传」。",
    "live_attributed_gmv": "直播归因 GMV：平台判定该笔成交记在商家直播头上的金额。⚠ 源表里没有这一列（推测性别名），目前恒为空。",
    "live_indirect_gmv": "商家直播间接 GMV：先被商家直播种草、之后从别的入口下单的成交。实测 1374 行恒为 0。",
    "video_gmv": "商家视频 GMV：商家自己短视频带来的成交。实测 33 行非零。",
    "video_attributed_gmv": "视频归因 GMV：平台判定该笔成交记在商家视频头上的金额。⚠ 源表里没有这一列（推测性别名），目前恒为空。",
    "video_indirect_gmv": "商家视频间接 GMV：先被商家视频种草、之后从别的入口下单的成交。实测 5 行非零。",
    "bound_account_live_attributed_gmv": "绑定账号直播归因 GMV：商家自有品牌号（绑定账号）的直播带来的成交。实测 1374 行恒为 0。",
    "bound_account_video_attributed_gmv": "绑定账号视频归因 GMV：商家自有品牌号（绑定账号）的视频带来的成交。实测 38 行非零。",
    "affiliate_video_attributed_gmv": "联盟视频归因 GMV：通过达人分销（联盟）带来的成交。实测 531 行非零，是这批里最大的一列（约占总额 41%）。",
    "creator_live_gmv": "达人直播 GMV：第三方达人直播间带来的成交。实测 37 行非零。",
    "creator_live_attributed_gmv": "达人直播归因 GMV：平台判定该笔成交记在达人直播头上的金额。实测 37 行非零。",
    "creator_live_indirect_gmv": "达人直播间接 GMV：先被达人直播种草、之后从别的入口下单的成交。实测 7 行非零。",
    "creator_video_gmv": "达人视频 GMV：第三方达人短视频带来的成交。实测 481 行非零。",
    "creator_video_indirect_gmv": "达人视频间接 GMV：先被达人视频种草、之后从别的入口下单的成交。实测 210 行非零。",
    # ── orders 域(2026-11-08) ───────────────────────────────────────
    "order_original_amount": "订单未减优惠前的金额(人民币口径)。",
    "warehouse_operation_fee": "仓库操作费(人民币口径)。",
    "shipping_fee": "卖家承担的运费(人民币口径)。平台间列名不同。",
    "promotion_fee": "广告/推广成本(人民币口径)。",
    "platform_deduction_fee": "平台扣费(人民币口径)。目前源表无对应列。",
    "platform_voucher": "平台发放的代金券(人民币口径)。",
    "platform_service_fee": "平台服务费(人民币口径)。",
    "seller_voucher": "卖家自己发放的代金券(人民币口径)。不是平台成本。",
    "estimated_settlement_amount": "预估回款金额(人民币口径)。",
    "settled_amount": "已结算金额(人民币口径)。",
    "order_status": "订单状态维度。",
    "product_sku": "卖家侧商品 SKU(与平台 SKU 不同)。",
}


#: hash 的「系统作用域」字段 —— 它们来自采集上下文, 不是文件里的列。
#:
#: 前端以前自己抄了一份这个列表(``headerBindings.js``), 后端在
#: ``field_mapping_templates.py`` 又抄了一份 ⇒ 三份口径。
#: 现在统一到这里。
SYSTEM_HASH_SCOPE_KEYS = frozenset(
    {"platform_code", "shop_id", "data_domain", "granularity", "sub_domain"}
)


# 域限定的「列名 → 语义键」映射。
#
# 为什么不能写进全局别名表
# ----------------------
# 全局别名表对所有数据域一视同仁，但同一个列名在不同域含义不同：
#   - ``ID`` 在 products 域是商品 ID，放到全局表会让别的域的 ``ID`` 也被当成商品身份；
#   - ``客服ID`` 在 services 域是客服（服务人员）ID，在别的域不是。
# 写进全局表 = 跨域污染，别的域的同名列被误提升成语义身份。
#
# 为什么这样做是安全的
# ------------------
# 1. 只在**对应数据域内**生效，别的域完全不受影响；
# 2. 命中结果只标记 ``semantic_review_source=inferred``（系统按列名推断，不是用户确认），
#    家族 hash 一致性比较仍然只认用户确认过的绑定
#    （见 ``field_mapping_templates._binding_lookup_by_source``），
#    所以第 3 批修掉的「假一致」不会被重新制造出来。
#
# 表里的列名全部来自真实源文件的表头（catalog 文件的 header_columns），
# 不做猜测性扩展；拿不准含义的列（状态类、名称类、货号类）一律不映射。
DOMAIN_COLUMN_SEMANTIC_OVERRIDES: Dict[str, Dict[str, str]] = {
    "products": {
        # Shopee 商品维度导出：商品编号 = Item ID
        "商品编号": "product_id",
        # TikTok 商品维度导出：商品 ID / ID
        "商品 id": "product_id",
        "id": "product_id",
        # Shopee 商品维度导出：规格编号 = 规格(SKU) ID
        "规格编号": "sku_id",
    },
    "services": {
        # 客服维度报表：客服ID = 服务人员 ID
        "客服id": "service_id",
        "客服编号": "service_id",
        # 客服维度报表的周期列：值形如 "01-06-2026 - 21-06-2026"。
        # 一个文件只有一个周期行，且**文件名里带的是采集时间、不是周期**，
        # 所以这个单元格是文件里唯一权威的周期来源 ⇒ 必须进 hash，
        # 否则下一期报表会算出同一个 hash，把上一期的行覆盖掉。
        "日期期间": "metric_date",
    },
    "inventory": {
        # 妙手库存导出：带 * 的是必填列
        "*商品sku": "platform_sku",
        "*商品名称": "product_name",
    },
}


# ── 域限定的「业务别名 → 语义键」映射 ──────────────────────────────
#
# [*] 批次 D: 这两张表以前住在 ``semantic_field_contract_service``,
#     但那里的别名**只被契约判定用**, 从没进过「列名 → 语义键」的推断链路 ——
#     于是「页面浏览数」明明有别名(page_views), 推断时却认不出来。
#     现在统一搬到注册表(唯一口径), 推断与契约共用同一份。
ORDER_SEMANTIC_ALIASES: Dict[str, tuple[str, ...]] = {
    # ── 身份与维度 ────────────────────────────────────────────────────
    # 这些列名在两个平台**同名**, 所以按通用别名登记即可(逐字匹配)。
    "order_id": (
        "订单编号",
        "订单号",
        "order_id",
        "order_no",
        "order no",
        "order id",
    ),
    # 「店铺」是源表里的**店铺身份列**(存的是店铺名, 由身份解析层再归一);
    # 模板里用户也确认过「店铺 → shop_id」⇒ 与 orders 域契约的 required 一致。
    "shop_id": (
        "店铺",
        "店铺ID",
        "shop_id",
        "shop id",
        "shop_name",
        "shop name",
    ),
    "order_status": ("订单状态",),
    "order_date": ("下单时间", "order_date", "order time", "order_time"),
    "product_id": ("产品ID", "商品ID"),
    "product_name": ("商品名称",),
    "product_sku": ("商品SKU",),
    "platform_sku": ("平台SKU",),
    "sku_id": ("SKU ID",),
    # ── 量类 ────────────────────────────────────────────────────────
    # 「销售数量」= 订单里的商品件数(两个平台都叫这个名字)。
    # ⚠ 归 ``sales_volume`` 而不是另起一个字段 ——
    #   orders 域的**契约**(``DEFAULT_CONTRACTS["orders"]``)要求的就是
    #   ``sales_volume``, 用户在 weekly 模板里也确认过「销售数量 → sales_volume」
    #   ⇒ 三处口径必须一致, 不能为了与视图列名(``product_quantity``)对齐
    #   就把语义键改掉。
    # 「出库数量」是**另一个事实**(已出库件数) ⇒ 不并进来, 落巡检候选。
    "sales_volume": ("销售数量", "sold_qty", "sales_volume", "quantity"),
    "buyer_count": ("买家数",),
    # ── 金额(只登 (RMB) 变体!) ──────────────────────────────────────
    #
    # ⚠ 重要: 源表金额列**成对出现**:
    #   `买家支付`(原币) 与 `买家支付(RMB)`(人民币)
    # 实测(2026-11 开发库, shopee monthly 29629 行):
    #   买家支付: 原币均值 240.11 / (RMB) 均值 72.03(非零行 27672, 相等仅 391)
    #   利润:     原币均值  27.98 / (RMB) 均值  11.06
    #   仓库操作费: 原币均值 11.56 / (RMB) 均值  4.99
    #   订单原始金额: 原币均值 269.53 / (RMB) 均值 78.72
    #   卖家支付运费: 原币均值 -40.36 / (RMB) 均值 -14.13
    #   广告成本:   原币均值  20.51 / (RMB) 均值   6.71
    # ⇒ 裸名列与 (RMB) 列是**两个不同的业务事实** ⇒ 裸名列(原币)
    #   **不接任何标准字段**, 只登 (RMB) 变体 ⇒ 杜绝混币种。
    #
    # ⚠ 因此 orders 域不能用「剔币种后缀」的归一化匹配:
    #   `normalize_alias("X(RMB)")` == `normalize_alias("X")` == "x"
    #   ⇒ 两列被压成同一个 key ⇒ resolve_alias_normalized 会在两个
    #     **不同业务事实**之间随机取一个
    # ⇒ orders 域取数**必须逐字**匹配(``semantic.resolve_alias``),
    #   且平台间同业务不同列名的场景用 ``platform_code`` 维度区分。
    # ⚠ 英文别名也登记在这里(不是平台维度): 两个平台的**中文/RMB**
    #   列名不同 ⇒ 走 ``ORDER_PLATFORM_ALIASES``; 而**英文**别名
    #   两平台一致 ⇒ 走通用行即可。
    "paid_amount": ("paid_amount", "buyer_paid"),
    "profit": ("利润(RMB)", "profit", "profit_amount", "profit_rmb"),
    "purchase_amount": ("采购成本(RMB)",),
    "refund_amount": ("退款金额(RMB)",),
    "estimated_settlement_amount": (
        "预估回款金额(RMB)",
        "estimated_settlement",
        "estimated_settlement_amount",
    ),
    # ⚠ ``settled_amount`` **走平台维度**(见 ``ORDER_PLATFORM_ALIASES``):
    #   shopee ``已结算金额(RMB)`` / tiktok ``回款金额(RMB)``。
    #   两个平台都有这一列, 只是列名不同 ⇒ 必须在平台表里分平台登记。
    #   (若把其中一个放通用表, 别名生成器会按「有平台别名 ⇒ 通用别名不登记」
    #     把通用那条**挤掉** ⇒ 另一个平台的列就失联了。)
    # ── 费用类 ─────────────────────────────────────────────────────
    "warehouse_operation_fee": ("仓库操作费(RMB)",),
    "promotion_fee": ("广告成本(RMB)",),
    # ── 平台间同业务不同列名的字段一律走 ORDER_PLATFORM_ALIASES ─────
}

#: [*] 2026-11-08 废止的 orders 域标准字段。
#:
#: `sales_amount`(销售额)在源表已**无对应列**(源表金额列是
#: 「买家支付(RMB)」「订单原始金额(RMB)」, 没有「销售额/成交金额」)
#: ⇒ 它恒为 0 且与 `paid_amount` 抢同一个业务含义 ⇒ 废止。
#:
#: 废止的字段**从视图的取数链里拉掉**, 不再输出 0 伪值。
ORDER_RETIRED_FIELDS: frozenset = frozenset({"sales_amount"})


#: [*] orders 域的**平台分别列名**。
#:
#: 源表的两个平台**同业务、不同列名**:
#:
#: * 平台佣金 —— shopee `Shopee平台佣金(RMB)` / tiktok `TikTok 平台佣金(RMB)`
#: * 运费     —— shopee `卖家支付运费(RMB)` / tiktok `商家运费(RMB)`
#:
#: 它们必须分平台登记 ⇒ 否则取数时会抢张(两个别名都非空,
#: 而它们是不同业务事实)。
ORDER_PLATFORM_ALIASES: Dict[str, Dict[str, tuple[str, ...]]] = {
    # ── shopee ─────────────────────────────────────────────────────
    "shopee": {
        # 买家实付(RMB)。shopee 叫「买家支付」, tiktok 叫「买家实付金额」。
        "paid_amount": ("买家支付(RMB)",),
        # 平台自己收的佣金。shopee 叫「Shopee平台佣金」, tiktok 叫「TikTok 平台佣金」。
        "platform_commission": ("Shopee平台佣金(RMB)",),
        # 卖家承担的运费。shopee 叫「卖家支付运费」, tiktok 叫「商家运费」。
        "shipping_fee": ("卖家支付运费(RMB)",),
        # 平台发的券。shopee 的「Shopee voucher」是平台侧券,
        # 「卖家voucher」是卖家侧券 ⇒ 后者不进平台成本(见 seller_voucher)。
        "platform_voucher": ("Shopee voucher(RMB)",),
        # 平台服务费。只有 shopee 有这一列。
        "platform_service_fee": ("服务费(RMB)",),
        # 订单未减优惠前的金额。
        "order_original_amount": ("订单原始金额(RMB)",),
        "seller_voucher": ("卖家voucher(RMB)",),
        # 付给**达人/联盟**的佣金(与平台佣金是两笔钱)。只有 shopee 叫「联盟佣金」。
        "affiliate_commission": ("联盟佣金(RMB)",),
        # 卖家**实际到手**的结算额。
        #   实测(2026-11 开发库): 29629 行中 28063 行有值, 均值 34.50。
        #   ⚠ 与「预估回款金额」行级相等率仅 34.37% ⇒ 预估与实收是**两个事实**,
        #     分属 ``estimated_settlement_amount`` / ``settled_amount``, 不合并。
        "settled_amount": ("已结算金额(RMB)",),
    },
    # ── tiktok ─────────────────────────────────────────────────────
    "tiktok": {
        "paid_amount": ("买家实付金额(RMB)",),
        "platform_commission": ("TikTok 平台佣金(RMB)",),
        "shipping_fee": ("商家运费(RMB)",),
        # ⚠ tiktok 侧**没有**「订单原始金额」这一列, 只有「产品原价」与
        #   「产品折后价格」。二者是**不同的事实**(折后价是打过折的金额)。
        #   「订单原始金额」= 未减优惠前的金额 ⇒ 对应「产品原价」。
        #   这里是有依据的判断, 不是猜测 —— 折后价已被证实是**折后**金额。
        "order_original_amount": ("产品原价(RMB)",),
        # 付给**达人**的佣金(与平台佣金是两笔钱)。tiktok 叫「达人佣金」。
        "affiliate_commission": ("达人佣金(RMB)",),
        # 卖家侧商品成交总收入。**只有 tiktok 有这一列**(见字典 ``platforms`` 标注)。
        "total_income": ("总收入(RMB)",),
        # 卖家**实际到手**的结算额。
        #   实测(2026-11 开发库, tiktok monthly 5254 行):
        #     `回款金额(RMB)` 100% 有值, 均值 54.11;
        #     与「总收入(RMB) + 总费用(RMB)」**行级相等率 59.17%**
        #     ⇒ 回款金额 = 总收入 − 各项费用 = 卖家到手 ⇒ 归 ``settled_amount``。
        #   ⚠ shopee 的「预估回款金额」是**预估**, 与「已结算金额」相等率仅 34.37%
        #     ⇒ 两个是不同事实, 分属两个标准字段(预估 / 实收), 不合并。
        "settled_amount": ("回款金额(RMB)",),
    },
}

#: [*] analytics(流量)域的**平台限定**别名 —— 2026-11-09 补登。
#:
#: 为什么必须分平台
#: ------------------
#: 实测(开发库 2026-11-09):
#: * shopee ``b_class.fact_shopee_analytics_monthly`` 2354 行 —— 这 5 列
#:   **全部有值**;
#: * tiktok ``b_class.fact_tiktok_analytics_monthly`` 1374 行 —— 这 5 列
#:   **一个都没有**(raw_data 的 key 里查不到)。
#:
#: ⇒ 它们是 **shopee 独有**的指标 ⇒ 登记成平台限定别名(``platform_code``),
#:   PG 侧 ``semantic.resolve_alias(..., platform_code)`` 只在 shopee 数据上命中。
#:
#: ⚠ **不登记成通用别名** —— 通用别名会让 tiktok 数据上出现同名列时**串口径**。
#:
#: [*] 2026-11-10: 访客数(``visitor_count``)也**成对**登记在这里 ——
#:
#:   shopee「访客数」     -> ``visitor_count`` (platform='shopee')
#:   tiktok「商品访客数」 -> ``visitor_count`` (platform='tiktok')
#:
#: 实测两边的访客列名**互斥**(shopee 2354 行只有「访客数」, tiktok 1374 行
#: 只有「商品访客数」)⇒ 只能分平台登记。
#:
#: ⚠⚠ **必须成对**: 别名合并规则里, 某个字段一旦登记了平台限定别名, 它的
#:   **通用别名就整体不再登记** ⇒ 只登记一边会把另一边**一起挤掉**
#:   (shopee 的 UV 会静默变 NULL)。这条规则是 ``build_domain_alias_records``
#:   里的 ``platform_fields`` 排他逻辑, 已实测确认。
#:
#: ✅ **两平台口径基本一致, 可以横向比较**(2026-11-10 复核后回正):
#:
#:   实测两边的月报都是**「一店一天一行」**:
#:     * shopee 2354 行 = 2354 个 (店, 日) 组合 —— ``metric_date`` 记**真实那天**;
#:     * tiktok  1374 行 = 45 个 (店, 月) 桶 —— 每桶装着整月 28~31 天,
#:       ``metric_date`` 被归一到**当月 1 号**。
#:
#:   访客列的量级结构也一致:
#:     * shopee「访客数」= 新访客 + 现有访客, **2354/2354 行精确相等**
#:       ⇒ 可证明是**去重访客人数**(不是人次);
#:     * tiktok「商品访客数」≤ 该行「去重商品曝光次数」**0/1374 行违反**
#:       ⇒ 是**访客量**(远小于曝光次数, 不是曝光的另一种写法);
#:       实测 1362/1374 行 ≤ 该行「页面浏览次数」, 剩下 12 行是平台把
#:       「页面浏览次数」**回传成 0**(不是访客数超了)。
#:
#:   ⇒ 两边都是「店铺当天的访客量」, 口径基本一致, **可以横向比较**。
#:
#: ⚠ **唯一还没定的差别**: tiktok 那一列的**列名定义**是「当天访问过商品的访客」,
#:   它是否等于「店铺当天的全部访客」**数据判定不了**(源表里没有第二列访客数
#:   可以对账)⇒ **待确认**。
#:   ⇒ 看板文案写「口径基本一致」, 但**既不能说「不可比」, 也不能说「完全等价」**。
ANALYTICS_PLATFORM_ALIASES: Dict[str, Dict[str, tuple[str, ...]]] = {
    "shopee": {
        # ── 访客数(UV) —— shopee 的真实表头 ─────────────────────────
        # 「访客数」= shopee **当天去重访客人数**
        # (实测 2354/2354 行 == 新访客 + 现有访客, 精确相等)。
        #
        # ⚠⚠ **必须与 tiktok 的「商品访客数」对称登记** ——
        #   :func:`backend.services.semantic_alias_registry.build_domain_alias_records`
        #   的合并规则里有一条**排他**规则: 某个标准字段一旦出现在
        #   ``platform_fields``(即登记了平台限定别名), 它的**通用别名就整体
        #   不再登记** —— 否则同一列名会被两个标准字段认领。
        #   ⇒ 只登记 tiktok 的「商品访客数」会把 shopee 的「访客数」**一起挤掉**
        #   ⇒ shopee 的 UV 全线变 NULL(实测会静默发生, 没有任何报错)。
        #   ⇒ 两个平台**必须**都登记, 各自命中自己的表头。
        "visitor_count": ("访客数",),
        # 新客: 访客数里「第一次来」的那部分(实测 访客数 == 新访客 + 现有访客)。
        "new_visitor_count": ("新访客",),
        # 老客: 访客数里「之前来过」的那部分。
        "returning_visitor_count": ("现有访客",),
        # 新关注者: 本期**新增关注**的人数(实测 ≤ 访客数, 0 行违反)。
        "new_follower_count": ("新关注者",),
        # ⚠ 平均停留时长是 **HH:MM:SS 字符串**(形如 `00:00:42`)——
        #   字段口径是**秒数**, 由视图专门换算(不能套普通数值清洗)。
        "avg_session_duration_seconds": ("平均停留时长",),
        # 平均页面访问数 ≈ 页面浏览数 ÷ 访客数(实测 1814/1814 行 ±0.02 内)。
        "avg_page_views_per_visitor": ("平均页面访问数",),
    },
    # ── tiktok 的 13 个 GMV 归因列(2026-11-09 补登) ────────────────
    #
    # ⚠⚠ **这批列只能单列看, 绝不能相加** ——
    # 实测(开发库 2026-11-09, tiktok monthly 1374 行):
    #   13 列合计 1,072,030.01 vs 总成交额 1,092,456.33(占 98.13%);
    #   **逐行**看: 741 个可比行里 **376 行(50.7%)归因和 > 该行总额**,
    #   比值中位 **1.019**、最大 **2.000**
    #   ⇒ 同一笔成交被多个维度**重复记账**(在直播间看到 → 点商品卡下单 →
    #     分享出去 ⇒ 平台把这单记到达人直播、商品卡等多个口径上)。
    # ⇒ 用户 2026-11-09 决定: **一列一个标准字段, 只单列展示, 绝不聚合**。
    "tiktok": {
        # ── 访客数(UV) —— tiktok 的真实表头 ─────────────────────────
        # 「商品访客数」= tiktok 流量报表里**当天访客量**, 是 tiktok 侧
        # **唯一**的访客口径(实测 1374 行 raw_data key 里只有这一列,
        # 店铺级访客数这一列压根不存在)。
        #
        # ✅ **与 shopee「访客数」口径基本一致, 可横向比较**(2026-11-10 复核):
        #   两边月报都是「一店一天一行」; shopee「访客数」= 新访客 + 现有访客
        #   (2354/2354 行精确相等 ⇒ 去重访客人数);
        #   tiktok「商品访客数」≤ 该行「去重商品曝光次数」(0/1374 行违反)
        #   且 ≤ 该行「页面浏览次数」(1362/1374 行; 剩下 12 行是平台把
        #   「页面浏览次数」回传成 0)⇒ 同样是访客量, 不是人次/曝光。
        #
        # ⚠ **唯一待确认的差别**: 这一列的**列名定义**是「当天访问过商品的访客」,
        #   是否等于「店铺当天的全部访客」**数据判定不了**(源表没有第二列访客数
        #   可对账)⇒ 看板写「口径基本一致」, 不写「完全等价」。
        #
        # ✅ 架构契约早就批准过这件事(2026-05-26):
        #   ``docs/architecture/SEMANTIC_FIELD_RULES.md`` 明写
        #   「TikTok analytics explicitly maps 商品访客数 to canonical
        #   visitor_count」—— 本条登记是把契约**落进实现**, 不是新增口径。
        "visitor_count": ("商品访客数",),
        # 商品卡: 用户直接点商品小卡下单(不经直播/视频)。
        # ⚠ 稀疏指标: 实测只有 198/1374 行有值(147 行非零)。
        "product_card_gmv": ("商品卡 GMV",),
        # 商家自播: 商家自己的直播间 / 商家自己的短视频带来的成交。
        # ⚠ 「商家直播 GMV」「商家直播间接 GMV」实测 **1374 行恒为 0**。
        "live_gmv": ("商家直播 GMV",),
        "live_indirect_gmv": ("商家直播间接 GMV",),
        "video_gmv": ("商家视频 GMV",),
        "video_indirect_gmv": ("商家视频间接 GMV",),
        # 绑定账号: 商家自有品牌号(绑定账号)的内容带来的成交。
        # ⚠ 「绑定账号直播归因 GMV」实测 **1374 行恒为 0**。
        "bound_account_live_attributed_gmv": ("绑定账号直播归因 GMV",),
        "bound_account_video_attributed_gmv": ("绑定账号视频归因 GMV",),
        # 联盟: 通过达人分销(联盟)带来的成交。
        "affiliate_video_attributed_gmv": ("联盟视频归因 GMV",),
        # 达人: 第三方主播的直播间 / 短视频带来的成交。
        # 「达人直播 GMV」= 达人直播间直接成交; 「达人直播归因 GMV」= 平台判定
        # 这笔单该记到达人直播头上; 「间接」= 先被种草、之后从别的入口下单。
        "creator_live_gmv": ("达人直播 GMV",),
        "creator_live_attributed_gmv": ("达人直播归因 GMV",),
        "creator_live_indirect_gmv": ("达人直播间接 GMV",),
        "creator_video_gmv": ("达人视频 GMV",),
        "creator_video_indirect_gmv": ("达人视频间接 GMV",),
    },
}


#: [*] orders 域的**平台分别列名**。
#:
#: 源表的两个平台**同业务、不同列名**:
#:
#: * 买家实付 —— shopee `买家支付(RMB)` / tiktok `买家实付金额(RMB)`
#: * 平台佣金 —— shopee `Shopee平台佣金(RMB)` / tiktok `TikTok 平台佣金(RMB)`
#: * 运费     —— shopee `卖家支付运费(RMB)` / tiktok `商家运费(RMB)`
#:
#: 它们必须**分平台**登记 ⇒ 否则取数时会抢张(两个别名都非空,
#: 而它们是不同业务事实)。
#:
#: ⚠ 平台维度的别名在 PG 侧靠 ``semantic.resolve_alias(..., platform_code)``
#:   的排序命中: 平台精确匹配的行排在通用行前面。
DOMAIN_PLATFORM_SEMANTIC_ALIASES: Dict[str, Dict[str, Dict[str, tuple[str, ...]]]] = {
    "orders": ORDER_PLATFORM_ALIASES,
    "analytics": ANALYTICS_PLATFORM_ALIASES,
}


#: [*] **别名已穷举**的域 —— 不再补全局裸名别名。
#:
#: 为什么 orders 域必须「封闭」:
#: ----------------------
#: 全局别名表是给 products 域补裸名用的(「销售额（已付款订单）」↔「销售额」)。
#: 但 orders 域的每个金额列都有**原币 + (RMB)** 两列, 裸名指的是**原币列**
#: ⇒ 把全局裸名补进 orders 域 = 让取数命中原币列 = 混币种。
#:
#: ⇒ orders 域的列名清单由 :data:`ORDER_SEMANTIC_ALIASES` 与
#:   :data:`ORDER_PLATFORM_ALIASES` **穷举**, 不再从全局表补。
DOMAIN_CLOSED_ALIAS_DOMAINS: frozenset = frozenset({"orders"})


#: [*] 平台成本(platform_total_cost_itemized)的组成项。
#:
#: 口径(与 ``sql/semantic/orders_atomic.sql`` 的出口表达式一一对应):
#: 运费 + 推广费 + 平台佣金 + 平台扣费 + 平台代金券 + 平台服务费。
#:
#: ⚠ 「仓库操作费」**不在**这里 —— 它由下游
#:   (``mart.b_cost_shop_month.total_cost_b``)单独相加, 放进来会重复计。
#:
#: ⚠ 「平台扣费」目前**没有对应源列**(见巡检告警) ⇒ 已知项数恒 ≤ 5。
#:   这不是 bug, 是**如实反映**: 平台成本口径里有一项取不到数。
ORDER_PLATFORM_COST_COMPONENT_FIELDS: tuple[str, ...] = (
    "shipping_fee",
    "promotion_fee",
    "platform_commission",
    "platform_deduction_fee",
    "platform_voucher",
    "platform_service_fee",
)


#: [*] orders 域的标准字段全集 —— 巡检与视图的共用清单。
#:
#: 从字典**派生**(不手写) ⇒ 字典增删字段, 这里自动跟随。
#: 源表实测(2026-11): orders 域取数字段覆盖 12 个。
def _order_standard_fields() -> tuple[str, ...]:
    """orders 域的标准字段全集(从字典派生)。"""
    fields = set(ORDER_SEMANTIC_ALIASES.keys())
    for per_platform in ORDER_PLATFORM_ALIASES.values():
        fields |= set(per_platform.keys())
    for key, meta in SEMANTIC_FIELD_DEFINITIONS.items():
        if str(meta.get("domain") or "") == "orders":
            fields.add(key)
    fields -= set(ORDER_RETIRED_FIELDS)
    return tuple(sorted(fields))


ORDER_STANDARD_FIELDS: tuple[str, ...] = _order_standard_fields()


def semantic_field_applies_to_platform(
    key: str,
    platform_code: str,
    domain: str = "orders",
) -> bool:
    """该标准字段**是否适用于**该平台。

    为什么需要(2026-11-08)
    ----------------------
    有的标准字段**只有部分平台有对应源列** —— 例如 ``total_income``
    (卖家总收入)只有 tiktok 有, shopee 侧的对应概念是「预估回款金额 /
    已结算金额」(**结算口径**, 不是商品收入口径)。

    不做这个区分 ⇒ 巡检的平台诊断会对 shopee 报「缺 total_income」
    ⇒ **噪音**, 运维会以为有真实缺口, 反而掩盖真问题。

    判定依据是字典里的 ``platforms`` 语义属性(SSOT, 与字段定义放在一起):
    * 标了 ``platforms`` ⇒ 只适用于列出的平台;
    * 没标 ⇒ **跨平台通用**, 一律纳入诊断
      (例: ``platform_service_fee`` 语义是跨平台通用的, 只是 tiktok 把费用
      拆成了多列 ⇒ 仍然要报 tiktok 解析不出来, 这是**真实缺口**)。
    """
    meta = SEMANTIC_FIELD_DEFINITIONS.get(str(key or "").strip().lower())
    if meta is None:
        return True
    platforms = meta.get("platforms")
    if not platforms:
        return True
    return str(platform_code or "") in tuple(platforms)


def platform_applicable_fields(
    domain: str = "orders",
    platform_code: str = "",
) -> frozenset:
    """该平台**适用**的标准字段集合(按字典 ``platforms`` 标注过滤)。"""
    if str(domain) == "orders":
        candidates = ORDER_STANDARD_FIELDS
    elif str(domain) == "analytics":
        # 流量域的别名清单里含三个 **common** 字段(gmv / metric_date / shop_id)
        # —— 它们在字典里 domain 是 common, 按「字典 domain == 本域」取会漏掉
        # ⇒ 平台诊断的口径会失真(这三个字段解析不出来时不会被报)。
        # ⇒ 这里以**该域的别名清单**为准, 与巡检实际巡检的字段集合同源。
        #
        # [*] 2026-11-09: 还要并入**平台限定**别名表里的字段 ——
        #   shopee 独有的「新访客 / 现有访客 / 新关注者 / 平均停留时长 /
        #   平均页面访问数」不在域限定表里(它们走平台限定登记),
        #   但**确实**要巡检: shopee 有这几列, 能不能解析出来是真实问题。
        #   平台过滤交给 :func:`semantic_field_applies_to_platform` ——
        #   这 5 个字段在字典里标了 ``platforms=("shopee",)``
        #   ⇒ tiktok 侧自动排除(否则报「tiktok 缺这 5 个指标」= 噪音)。
        candidates = tuple(
            dict.fromkeys(
                list(DOMAIN_SEMANTIC_ALIASES.get("analytics", {}).keys())
                + [
                    field
                    for per_platform in DOMAIN_PLATFORM_SEMANTIC_ALIASES.get(
                        "analytics", {}
                    ).values()
                    for field in per_platform
                ]
            )
        )
    else:
        candidates = tuple(
            key
            for key, meta in SEMANTIC_FIELD_DEFINITIONS.items()
            if str(meta.get("domain") or "") == str(domain)
        )
    return frozenset(
        key
        for key in candidates
        if semantic_field_applies_to_platform(key, platform_code, domain)
    )


# ── 订单级字段的派生(阶段 4 · 入库归一化) ─────────────────────────────
#
# 为什么放在字典里
# ----------------
# ``backend/services/orders_ingestion_normalizer.py`` 以前手写了一份 40+ 条的
# 「订单级金额表头」清单, 与字典各写各的 ⇒
#   * 字典加字段 ⇒ 清单不会跟着变, 漏掉的列会被**重复计入**
#     (多 SKU 订单的订单级金额按行累加 ⇒ 虚增);
#   * 清单里还混着一批**已经写错的表头**(如「预计回款金额(RMB)」, 真实列名是
#     「预估回款金额(RMB)」) ⇒ 真实列一直没被清空。
#
# ⇒ 这里从字典**派生**, normalizer 只 import(单向依赖, 不构成循环 import)。
#
# 派生规则
# --------
# 1. **候选标准字段** = ``SEMANTIC_FIELD_DEFINITIONS`` 里带订单级标记
#    (``order_level_amount`` / ``order_level_quantity``)的字段, 且口径**属于
#    orders 域**(或 common 域且在 orders 别名表登记过)。
#    其它域的字段不纳入 —— 例: ``purchase_amount``(采购成本)的 domain 是
#    products, 实测(2026-11 开发库)它在同一订单内**逐行不同**(vary=655/5372
#    个多行订单)⇒ 是**行级**成本, 清空第 2+ 行会少算。
# 2. **源表列名** = 字段的语义键 + 字段别名 + ``ORDER_SEMANTIC_ALIASES`` /
#    ``ORDER_PLATFORM_ALIASES`` 里登记的真实列名(含各平台列名)。
# 3. **列名变体** = 裸表头 + ``(RMB)`` 变体 + 语义键/英文别名的 snake_case
#    变体 —— 源表金额列**成对出现**「X」(原币) 与「X(RMB)」(人民币)。
#
# ⚠ 粒度实测(2026-11 开发库, 判定方法: 多行订单里该列的取值形态)
#    * ``head_only``(只有首行有值)= 源表**合并单元格** ⇒ **订单级**
#    * ``repeat_same``(每行同值)/ ``vary``(每行不同)= **行级**
#    ⇒ 只有订单级的列才能按订单去重(清空第 2+ 行)。

#: 源表金额列的**币种后缀**(人民币口径)。
ORDER_LEVEL_CURRENCY_SUFFIX = "(RMB)"

#: [*] 订单级金额列的**平台级例外**: ``(平台, 语义键)`` —— 该平台该字段的
#: 源列是**行级**取值, 不能按订单去重(清空第 2+ 行会少算)。
#:
#: 目前只有一处:
#:
#: * ``tiktok`` 的「产品原价(RMB)」—— 字典把它登记为 ``order_original_amount``
#:   的 tiktok 平台别名(见 :data:`ORDER_PLATFORM_ALIASES`), 但**粒度**与
#:   shopee 的「订单原始金额(RMB)」不同: 实测(2026-11 开发库, 1012 个多行
#:   订单)「产品原价(RMB)」repeat_same=899 / vary=113 / **head_only=0** /
#:   blank=0 —— 从不出现「只有首行有值」的合并单元格形态, 且同一订单内不同
#:   SKU 取值不同 ⇒ 它是**行级单价**(该平台「销售数量」恒为 1)⇒ 清空第 2+
#:   行会让订单原始金额**少算约 23%**。
ORDER_LEVEL_AMOUNT_PLATFORM_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("tiktok", "order_original_amount"),
    }
)


def _order_level_field_keys(marker: str) -> tuple[str, ...]:
    """挑出带指定订单级标记、且口径属于 orders 域的标准字段。"""
    orders_registered_keys = set(ORDER_SEMANTIC_ALIASES)
    for per_platform in ORDER_PLATFORM_ALIASES.values():
        orders_registered_keys |= set(per_platform)

    keys: list[str] = []
    for key, meta in SEMANTIC_FIELD_DEFINITIONS.items():
        if not meta.get(marker):
            continue
        if key in ORDER_RETIRED_FIELDS:
            continue
        domain = str(meta.get("domain") or "")
        if domain == "orders" or (domain == "common" and key in orders_registered_keys):
            keys.append(key)
    return tuple(sorted(keys))


def _order_level_header_variants(
    headers: Iterable[str],
    *,
    with_currency_suffix: bool = True,
) -> set[str]:
    """展开订单级字段的源表列名变体(裸表头 + (RMB) 变体 + snake_case)。

    ``with_currency_suffix=False`` 用于**数量**列 —— 数量没有币种维度,
    不该派生「销售数量(RMB)」这种不存在的列名。
    """
    variants: set[str] = set()
    for header in headers:
        name = str(header or "").strip()
        if not name:
            continue
        variants.add(name)

        bare = name
        if with_currency_suffix:
            if bare.endswith(ORDER_LEVEL_CURRENCY_SUFFIX):
                bare = bare[: -len(ORDER_LEVEL_CURRENCY_SUFFIX)].strip()
            variants.add(bare)
            variants.add(f"{bare}{ORDER_LEVEL_CURRENCY_SUFFIX}")

        # snake_case 变体(语义键 / 英文别名 / 历史 hash 字段名)。
        # 中文表头不做 snake 化 —— 否则「TikTok 平台佣金」会退化成「tiktok」。
        if not re.search(r"[\u4e00-\u9fff]", bare):
            snake = re.sub(r"[^0-9a-zA-Z]+", "_", bare).strip("_").lower()
            if snake:
                variants.add(snake)
                if with_currency_suffix:
                    variants.add(f"{snake}_rmb")
    return variants


def _derive_order_level_fields(
    marker: str,
    exceptions: frozenset[tuple[str, str]] = frozenset(),
    *,
    with_currency_suffix: bool = True,
) -> frozenset[str]:
    """从字典派生 orders 域的订单级字段源表列名集合。"""
    headers: set[str] = set()
    for key in _order_level_field_keys(marker):
        meta = SEMANTIC_FIELD_DEFINITIONS[key]
        headers.add(key)
        headers.update(meta.get("aliases") or [])
        headers.update(ORDER_SEMANTIC_ALIASES.get(key, ()))
        for platform, per_platform in ORDER_PLATFORM_ALIASES.items():
            if (platform, key) in exceptions:
                continue
            headers.update(per_platform.get(key, ()))
    return frozenset(
        _order_level_header_variants(headers, with_currency_suffix=with_currency_suffix)
    )


#: [*] orders 域的**订单级金额列名**集合(从字典派生)。
#:
#: 用途: 多 SKU 订单里, 订单级金额只保留在**第 1 行**, 第 2+ 行清空
#: (否则按行 SUM 会把整单金额**重复计入** ⇒ 虚增)。
ORDER_LEVEL_AMOUNT_FIELDS: frozenset[str] = _derive_order_level_fields(
    "order_level_amount",
    ORDER_LEVEL_AMOUNT_PLATFORM_EXCEPTIONS,
)

#: [*] orders 域的**订单级数量列名**集合(从字典派生)。
#:
#: ⚠ **不参与**「第 2+ 行清空」—— 实测(2026-11 开发库):
#:    「销售数量」在同一订单内**取值不同**(例: 订单 2606131JJFE29C 的 8 行是
#:    1/2/1/4/4/2/3/3)且从不出现 head_only 形态 ⇒ 它是**行级件数**
#:    (整单件数 = 各行之和)⇒ 清空第 2+ 行会让**件数少算约 20%**。
#:    这里只做**登记**, 让字典口径与实测口径的差异可见, 不改变入库行为。
ORDER_LEVEL_QUANTITY_FIELDS: frozenset[str] = _derive_order_level_fields(
    "order_level_quantity",
    with_currency_suffix=False,
)


# [*] analytics(流量)域的中文表头别名。
# 用途: 让语义契约能从**平台原始表头**推断出语义键, 而不是只依赖模板里
# 人工填写的 header_bindings。
# 背景: 已发布模板里 header_bindings 的 semantic_key 覆盖率极低
# (tiktok/analytics 71 个绑定只有 12 个有 semantic_key), 导致 required 语义键
# 根本解析不出来 -> 契约状态恒为 breaking_drift(哪怕文件与模板 100% 一致)。
ANALYTICS_SEMANTIC_ALIASES: Dict[str, tuple[str, ...]] = {
    # ── 维度 ──
    "metric_date": ("日期", "统计日期", "交易日期", "日期时间", "date"),
    "shop_id": ("店铺", "店铺id", "店铺名称", "shop_id", "shop id"),
    # ── 访客 ──
    # ⚠⚠ **visitor_count 与 product_visitor_count 都不在**本表(通用别名)里 ——
    #
    # 2026-11-10 实测(开发库全仓扫描 raw_data key):
    #   * shopee 流量月报 2354 行 —— 访客列**只有**「访客数」「新访客」「现有访客」;
    #   * tiktok 流量月报 1374 行 —— 访客列**只有**「商品访客数」;
    #   * 两边的访客列名**互斥** ⇒ 「访客数」与「商品访客数」是**平台专有**列名。
    #
    # ⇒ 两者都改走**平台限定**登记(见 :data:`ANALYTICS_PLATFORM_ALIASES`):
    #   shopee「访客数」     -> visitor_count (platform='shopee')
    #   tiktok「商品访客数」 -> visitor_count (platform='tiktok')
    #
    # ⚠ **通用别名会让两个平台串口径**: 「访客数」若登记成通用别名, tiktok 数据
    #   上将来出现同名列时会被**当成 shopee 的口径**命中 —— 这正是
    #   2026-11-08 edb7921a 修掉的病根(同一个表头被两个标准字段抢认,
    #   口径归属不清), 不能再犯一次。
    #
    # ⚠ 同时, 因为 ``visitor_count`` 进了平台限定别名表, 它的**通用**别名
    #   (「访客量」「访问用户数」「uv」等推测性裸名)会**一起退出**本域 ——
    #   实测两个源表里这些列**一个都不存在**, 留着只是「登记了但命不中」的
    #   假覆盖。**宁可落 unknown, 也不猜。**
    #
    # ⚠ ``product_visitor_count`` 也**退出** analytics 域 ——
    #   analytics 域的「商品访客数」归 ``visitor_count``(见上), 若本域再登记
    #   一条 ``product_visitor_count``, 同一个列名就会指向两个标准字段
    #   (SSOT 硬约束: 一个列名只认一个标准字段)⇒ 迁移的 fail-closed 自检
    #   会直接失败。
    #   本字段现在只服务 **products 域**的「商品访客数量」(实测 25809 行有值)。
    # shopee「页面浏览数」/ tiktok「页面浏览次数」
    "page_views": (
        "页面浏览数",
        "页面浏览次数",
        "页面浏览量",
        "商品浏览量",
        "浏览量",
        "pv",
    ),
    # ── 曝光 / 点击 / 跳出 ──
    # tiktok「商品曝光次数」/「商品点击量」; shopee 侧没有 ⇒ 恒 NULL。
    "impressions": ("商品曝光次数", "曝光量", "曝光次数", "impression", "impressions"),
    "clicks": ("商品点击量", "点击量", "点击次数", "click", "clicks"),
    # shopee「跳出率」(⚠ 全局别名是「跳失率」, 对不上真实表头 ⇒ 这里补登记)
    "bounce_rate": ("跳出率", "跳失率", "bounce rate"),
    # ── 成交 ──
    "conversion_rate": ("转化率", "conversion_rate"),
    "order_count": (
        "订单数",
        "订单量",
        "订单数量",
        "支付订单数",
        "成交订单数",
        "order_count",
    ),
    # ⚠ 真实表头带空格(「SKU 订单数」), 全局别名是「SKU订单量」⇒ 这里补登记
    "sku_order_count": ("SKU 订单数", "SKU订单量", "sku orders", "sku order count"),
    # ⚠ gmv 的字典 domain 是 common ⇒ 全局别名**不会**自动进 analytics 域
    #   ⇒ 这里必须显式登记「GMV」。
    "gmv": ("GMV", "gmv", "成交额", "交易额"),
    # tiktok「总成交额」(全局别名是「总交易金额」⇒ 这里补登记)
    "total_transaction_amount": (
        "总成交额",
        "总交易金额",
        "total transaction amount",
    ),
    # ⚠ ``click_rate`` **两个平台都没有这一列** ⇒ 别名清单里**不登记**它
    #   ⇒ 它恒为 NULL(「不知道」), 而不是 0。
    #
    # ⚠ 下面这些真实列**还没有对应的标准字段**, 本轮不登记
    #   (登记前必须先定义标准字段, 否则就是「有列名、无语义」):
    #   tiktok: 商品成交件数 / 已退款的商品件数 / 客户数 / 平均订单金额 /
    #           去重商品曝光次数 / 去重点击次数 / 退款金额 / 商品卡 GMV /
    #           商家直播 GMV / 商家直播间接 GMV / 商家视频 GMV /
    #           商家视频间接 GMV / 达人直播 GMV / 达人直播归因 GMV /
    #           达人直播间接 GMV / 达人视频 GMV / 达人视频间接 GMV /
    #           绑定账号直播归因 GMV / 绑定账号视频归因 GMV / 联盟视频归因 GMV
    #
    # ⚠ shopee 的「新访客 / 现有访客 / 新关注者 / 平均停留时长 / 平均页面访问数」
    #   已于 2026-11-09 补登 ⇒ 见 :data:`ANALYTICS_PLATFORM_ALIASES`
    #   (它们**只有 shopee 有**, 所以走**平台限定**别名, 不进本表)。
}


#: [*] products 域的业务别名 —— 2026-11-08 按**真实表头**登记。
#:
#: 依据: shopee / tiktok 商品报表的真实表头(``b_class.fact_*_products_*`` 的
#: ``raw_data`` key 与结构化列)。此前 products 域**没有任何**域别名,
#: 而全局别名表里只有「销售额」「曝光次数」这类**裸名**, 与真实表头
#: (「销售额（已付款订单） (SGD)」/「商品曝光次数.1」)完全对不上
#: ⇒ 语义层命中率 0/45。
#:
#: 口径列**成对登记**(:data:`CALIBER_PAID` / :data:`CALIBER_PLACED`),
#: 绝不把两套口径登记到同一个标准字段 —— 实测两者销售额平均差 5.15%。
#:
#: 「已确认订单」在真实数据里没有任何数值, 无从判断它对应哪个口径
#: ⇒ 这里**不登记**它(宁可缺, 也不猜); 只登记「已确定订单」到 placed
#: (有实测支撑: 与「已下订单」差 4.25%, 属同一口径的措辞迁移)。
PRODUCTS_SEMANTIC_ALIASES: Dict[str, tuple[str, ...]] = {
    # ── 身份维度 ──
    "product_id": ("商品编号", "商品 ID", "商品ID", "ID"),
    "product_name": ("商品", "商品名", "商品标题"),
    "item_status": ("Current Item Status", "发品状态"),
    "sku_id": ("规格编号",),
    # ── 已付款口径(主口径) ──
    "order_count": ("已付款订单",),
    # 「GMV」是 tiktok 的头条金额指标(实测与「含税 GMV」数值完全相同);
    # 只登「GMV」不登「含税 GMV」—— 两者同值, 登两个会让 resolve_alias 在
    # 两列都非空时随机挑一个(值虽相同, 但不该依赖这种巧合)。
    "sales_amount": ("销售额（已付款订单）", "销售额（已付款订单） (SGD)", "GMV"),
    "sales_volume": ("件数（已付款订单）", "商品成交件数", "件数"),
    "conversion_rate": ("转化率（已付款订单）",),
    "order_conversion_rate": ("订单转化率（已付款订单）",),
    "buyer_count": ("买家数（已付款订单）",),
    "aov": ("每笔订单销售额（已付款订单）", "每笔订单销售额（已付款订单） (SGD)"),
    # ── 已下单口径 ──
    # 「已确定订单」是「已下订单」的旧叫法 —— 与「已下订单」列**在同一份报表里并存**
    # (实测 MYR/PHP 店铺两个口径列同时存在, 数值差 4.25%)。两列都登记到同一个标准字段时,
    # resolve_alias 只能挑一条 ⇒ 所以旧词别名的**置信度要低于当前措辞**
    # (见 LEGACY_CALIBER_ALIAS_CONFIDENCE), 保证稳定选当前措辞那一列。
    "order_count_placed": ("已下订单", "已确定订单"),
    "sales_amount_placed": (
        "销售额（已下订单）",
        "销售额（已下订单） (SGD)",
        "销售额（已下订单） (MYR)",
        "销售额（已下订单） (PHP)",
        "销售额（已确定订单）",
    ),
    "sales_volume_placed": ("件数（已下订单）", "件数（已确定订单）"),
    "conversion_rate_placed": ("转化率（已下订单）", "转化率（已确定订单）"),
    "order_conversion_rate_placed": (
        "订单转化率（已下订单）",
        "订单转化率（已确定订单）",
    ),
    "buyer_count_placed": ("买家数（已下订单）", "买家数（已确定订单）"),
    "aov_placed": (
        "每笔订单销售额（已下订单）",
        "每笔订单销售额（已下订单） (SGD)",
        "每笔订单销售额（已下订单） (MYR)",
        "每笔订单销售额（已下订单） (PHP)",
        "每笔订单销售额（已确定订单）",
    ),
    # ── 流量指标(无口径) ──
    "impressions": ("商品展示量", "商品曝光次数"),
    "unique_impressions": ("不重复的商品曝光量", "去重商品曝光次数"),
    "clicks": ("商品点击量",),
    "unique_clicks": ("不重复的商品点击量", "去重点击次数"),
    "product_visitor_count": ("商品访客数量",),
    "page_views": ("商品页面访问量",),
    "bounce_rate": ("商品跳出率",),
    # ── 加购族(shopee 写法带空格/半角括号, 必须逐字登记) ──
    "add_to_cart_count": ("件数 (加入购物车）",),
    "add_to_cart_user_count": ("商品访客数 (加入购物车)",),
    "add_to_cart_rate": ("转化率 (加入购物车率)",),
    # ── tiktok 点击成交转化率(CTOR)族 —— 与 conversion_rate 分母不同, 独立成字段 ──
    "click_to_order_rate": ("CTOR（SKU 订单）",),
    "unique_click_to_order_rate": ("去重点击成交转化率（SKU 订单）",),
}


DOMAIN_SEMANTIC_ALIASES: Dict[str, Dict[str, tuple[str, ...]]] = {
    "orders": ORDER_SEMANTIC_ALIASES,
    "analytics": ANALYTICS_SEMANTIC_ALIASES,
    "products": PRODUCTS_SEMANTIC_ALIASES,
}


# ── 语义归一化 ─────────────────────────────────────────────────────
#
# 为什么需要归一化
# ----------------
# 真实表头不是干净的标识符, 而是「业务名 + 修饰」:
#
#   "买家支付(RMB)"  vs  "买家支付"      ← 币种后缀, 同一个指标
#   "利润（rmb）"    vs  "利润(RMB)"      ← 全角/半角括号
#   "商品SKU"       vs  "商品 sku"      ← 空格
#   "下单时间\n"     vs  "下单时间"      ← 换行(妙手导出)
#   "*商品sku"      vs  "商品SKU"        ← 必填星号
#
# 以前匹配是**逐字相等**, 这些全都认不出来 ⇒ 命中率只有 3~6%。
# 归一化之后, 同一个指标的各种写法会收敛到同一个键。
#
# 注意: 归一化**只用于匹配**, 原始列名一律保留在 raw_data 里 ——
# 归一化不是为了改数据, 是为了让「同一个意思」能被认出来。
_CURRENCY_SUFFIX_PATTERN = re.compile(r"[（(]\s*[A-Za-z]{3}\s*[)）]\s*$")
_CURRENCY_NO_PAREN_PATTERN = re.compile(r"[（(][^（()）]{0,12}[)）]\s*$")
_FULLWIDTH_PUNCTUATION = {
    "（": "(",
    "）": ")",
    "：": ":",
    "，": ",",
    "、": ",",
    "。": ".",
    "％": "%",
    "＋": "+",
    "－": "-",
    "／": "/",
    "＿": "_",
}


def normalize_semantic_alias(value: Optional[str]) -> str:
    """把列名/别名归一化成「可比较」的形态。

    归一化步骤(顺序固定):

    1. 去首尾空白;
    2. 全角标点 → 半角;
    3. 去掉末尾的币种/币种名称括号后缀(``(RMB)`` / ``（美元）``);
    4. 去掉所有空白(含换行、全角空格);
    5. 去掉下划线;
    6. 去掉必填星号(``*``);
    7. 去掉末尾的 ``.N`` 序号后缀(Excel 多级表头展开后的重名列);
    8. 大小写折叠。

    Returns:
        归一化后的字符串; 空值返回空字符串。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    for source, target in _FULLWIDTH_PUNCTUATION.items():
        text = text.replace(source, target)
    # 末尾括号内容如果是「币种/币种名称」, 视为同一个指标的币种变体
    match = _CURRENCY_SUFFIX_PATTERN.search(text)
    if not match:
        match = _CURRENCY_NO_PAREN_PATTERN.search(text)
        if match:
            inner = match.group(0).strip("()").strip()
            # 只有「像币种」的才剥: 3 个字母, 或含「元/币/美元/人民币」等
            is_currency_like = bool(re.fullmatch(r"[A-Za-z]{3}", inner)) or bool(
                re.search(r"(元|币|美元|人民币|美金|欧元|日元)", inner)
            )
            if not is_currency_like:
                match = None
    if match:
        text = text[: match.start()].strip()
    text = text.replace("*", "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("_", "")
    # 末尾的 ".N" 序号后缀 —— Excel 多级表头展开后的重名列产物
    # (例: tiktok 商品报表的  /  / ),
    # 与基础列是**同一个指标**, 只是多块表里各出现了一次。
    text = re.sub(r"\.\d+$", "", text)
    return text.strip().lower()


# ── 口径（caliber）维度 ────────────────────────────────────────────────
#
# 平台报表里同一个指标常带**多套统计口径**, 它们不是措辞差异, 是不同的业务事实:
#
#   * ``placed`` —— 已下单(买家提交了订单, 未必付款)
#   * ``paid``   —— 已付款(买家完成了支付)
#
# 2026-11-08 生产实测(shopee 商品月报, 7090 行可比): 两套口径的销售额
# **平均差 5.15%, 最大差 175.89** ⇒ 绝不能归一化成同一个值, 也不能互相冒充。
#
# 平台还会**改词**(报表改版): shopee 的「已确定订单」是「已下订单」的旧叫法
# (实测两者差 4.25%, 属同一口径的措辞迁移), 由 :data:`PLATFORM_CALIBER_HISTORY` 登记。
#
# 「已确认订单」在真实数据里**没有任何数值**(只作为旧报表遗留列存在),
# 无从判断它对应哪个口径 ⇒ 刻意**不折算**, 宁可落 unknown, 也不猜。

#: 平台口径沿革: 平台 → {旧口径词: 当前口径词}
PLATFORM_CALIBER_HISTORY: Dict[str, Dict[str, str]] = {
    "shopee": {
        "已确定订单": "已下单",
    },
}


def apply_caliber_history(normalized: str, platform_code: Optional[str] = None) -> str:
    """把归一化后的列名里的**旧口径词**换成当前口径词。

    沿革表按平台登记 —— 同一个词在不同平台的沿革不一定一样。
    没有登记沿革的平台, 原样返回(不做任何猜测)。
    """
    if not normalized:
        return ""
    history = PLATFORM_CALIBER_HISTORY.get(str(platform_code or "").strip().lower())
    if not history:
        return normalized
    for legacy_word, current_word in history.items():
        if legacy_word in normalized:
            normalized = normalized.replace(legacy_word, current_word)
    return normalized


#: 口径沿革**旧词**别名的置信度 —— 低于当前措辞的 1.000。
#:
#: 为什么需要: shopee 同一份报表里「已下订单」与「已确定订单」两列并存
#: (实测 MYR/PHP 店铺同时存在, 数值差 4.25%)。两列都登记到同一个标准字段时,
#: ``semantic.resolve_alias()`` 只能挑一条 —— 若置信度相同就退化成按 id 挑,
#: 等于把两个数混着报。旧词降级 ⇒ **稳定选当前措辞**。
LEGACY_CALIBER_ALIAS_CONFIDENCE = 0.900


#: 报表**分块列**的判定 —— 列名末尾带 ``.N`` 序号。
#:
#: 为什么分块列**不落标准字段**
#: --------------------------
#: 2026-11-08 实测(tiktok 商品月报 777 行):
#:
#: * 基础列 ``商品曝光次数`` 与 ``商品曝光次数.1/.2/.3/.4`` **同时存在**;
#: * 实测「基础列 = .1+.2+.3+.4」在 701/777 行成立(其余为块缺失的 NULL 行);
#: * 同理 ``GMV`` = ``GMV.1+GMV.2+GMV.3`` 在 684/777 行成立。
#:
#: ⇒ ``.N`` 是**报表分块**(第 N 块), 不是 Excel 重名列 ⇒ 它**不是**基础列那个指标,
#: 更不是"去重版"。把它归到 ``unique_impressions`` 之类是**静默失真**。
#:
#: ⇒ 分块列一律**不落标准字段**: 宁可 unknown, 也不猜。
#: (它们各自的语义需要结合报表结构单独建模, 记为 V2。)
#: 报表分块列的判定正则 —— 列名末尾带 ``.N`` 序号。
BLOCK_COLUMN_ALIAS_PATTERN = re.compile(r"\.\d+$")


def is_block_column_alias(raw_alias: Optional[str]) -> bool:
    """这个列名是报表分块列(末尾带 ``.N``)吗?"""
    text_value = str(raw_alias or "").strip()
    if not text_value:
        return False
    return bool(BLOCK_COLUMN_ALIAS_PATTERN.search(text_value))


def is_legacy_caliber_alias(raw_alias: Optional[str]) -> bool:
    """这个别名用的是**沿革旧口径词**吗?

    沿革词表来自 :data:`PLATFORM_CALIBER_HISTORY` —— 各平台登记自己的旧叫法,
    这里把所有平台的旧词汇总成一个判定集(不带平台维度: 别名行本身不带平台字段,
    降级只影响"同一字段多个别名同时非空时挑谁")。

    「已确认订单」**不在**沿革表里(它没有任何实测数值支撑) ⇒ 不会被降级,
    也就不会被登记成任何标准字段的别名 ⇒ 保持 unknown。
    """
    text_value = str(raw_alias or "")
    if not text_value:
        return False
    for history in PLATFORM_CALIBER_HISTORY.values():
        for legacy_word in history:
            if legacy_word and legacy_word in text_value:
                return True
    return False


def _build_normalized_alias_index() -> Dict[str, str]:
    """全局别名表的归一化索引: 归一化别名 → 语义键。

    冲突(同一个归一化别名指向两个语义键)时**保留先注册的那个**,
    并且不静默 —— 冲突会被 :mod:`backend.services.semantic_alias_registry_service`
    检出并落 ``conflict`` + 报警。
    """
    index: Dict[str, str] = {}
    for semantic_key, aliases in SEMANTIC_FIELD_ALIASES.items():
        for alias in aliases:
            normalized = normalize_semantic_alias(alias)
            if normalized and normalized not in index:
                index[normalized] = semantic_key
    return index


def _caliber_variants(normalized: str) -> set[str]:
    """返回归一化文本在**各平台口径沿革**下的等价形态集合。

    平台报表改版会换口径词(shopee: 「已确定订单」→「已下单」)。同一个指标的
    新词与旧词必须能互相命中, 否则平台一改版, 语义层就整体失配。

    展开方向是**双向**的: 当前词 -> 旧词形态, 旧词 -> 当前词形态。

    只在**域限定别名表**里展开 —— 全局别名表展开会造成跨域污染。
    """
    if not normalized:
        return set()
    variants = {normalized}
    for history in PLATFORM_CALIBER_HISTORY.values():
        for legacy_word, current_word in history.items():
            if current_word in normalized:
                variants.add(normalized.replace(current_word, legacy_word))
            if legacy_word in normalized:
                variants.add(normalized.replace(legacy_word, current_word))
    return variants


def _build_normalized_domain_alias_index() -> Dict[str, Dict[str, str]]:
    """域限定别名的归一化索引。

    别名除了自身形态, 还会登记**口径沿革**下的等价形态
    (见 :func:`_caliber_variants`) —— 平台改口径词时不必再手工补别名。
    """
    result: Dict[str, Dict[str, str]] = {}
    for domain, alias_map in DOMAIN_SEMANTIC_ALIASES.items():
        bucket: Dict[str, str] = {}
        for semantic_key, aliases in alias_map.items():
            for alias in aliases:
                normalized = normalize_semantic_alias(alias)
                if not normalized:
                    continue
                for variant in _caliber_variants(normalized):
                    if variant not in bucket:
                        bucket[variant] = semantic_key
        result[domain] = bucket
    return result


def _build_normalized_column_override_index() -> Dict[str, Dict[str, str]]:
    """域限定列名表的归一化索引。"""
    result: Dict[str, Dict[str, str]] = {}
    for domain, mapping in DOMAIN_COLUMN_SEMANTIC_OVERRIDES.items():
        bucket: Dict[str, str] = {}
        for column, semantic_key in mapping.items():
            normalized = normalize_semantic_alias(column)
            if normalized and normalized not in bucket:
                bucket[normalized] = semantic_key
        result[domain] = bucket
    return result


def is_inferable_semantic_key(value: Optional[str]) -> bool:
    """该语义键**允许**被列名推断认领。

    状态类字段(字典里 ``inferable=False``)不参与推断 —— 状态列名一旦被
    认成语义键, 就会进身份/去重字段 ⇒ 状态一变就算新行 ⇒ 污染身份推断。

    ⚠ 它们**仍然**登记在域别名表里 —— 别名表是**取数**的事实源(视图要能
    取到该列的值), 推断只是「这列是不是语义键」的判断, 两者口径不同。

    ⚠ 这里**不能**调用 :func:`normalize_semantic_key` —— 它定义在本函数
    之后, 而本函数会在模块加载期被调用(构建封闭域逐字索引)。
    """
    key = str(value or "").strip().lower()
    meta = SEMANTIC_FIELD_DEFINITIONS.get(key)
    if meta is None:
        return True
    return meta.get("inferable", True) is not False


def _build_exact_closed_domain_alias_index() -> Dict[str, Dict[str, str]]:
    """封闭域的**逐字**别名索引。

    为什么封闭域要另建一份「逐字」索引
    ----------------------------------
    归一化会把 ``X`` 与 ``X(RMB)`` 压成同一个 key(``normalize_alias("利润(RMB)")
    == normalize_alias("利润") == "利润"``)。orders 域的每个金额列都有
    「原币 + (RMB)」两列 ⇒ 归一化索引会把**原币列**也认领成标准字段
    ⇒ 静默混币种。

    ⇒ 封闭域(:data:`DOMAIN_CLOSED_ALIAS_DOMAINS`)一律**逐字**匹配:
      字典登记的列名一个字符都不差才算命中。
    """
    result: Dict[str, Dict[str, str]] = {}
    for domain in DOMAIN_CLOSED_ALIAS_DOMAINS:
        bucket: Dict[str, str] = {}
        for semantic_key, aliases in DOMAIN_SEMANTIC_ALIASES.get(domain, {}).items():
            if not is_inferable_semantic_key(semantic_key):
                continue
            for alias in aliases:
                text = str(alias or "").strip()
                if text and text not in bucket:
                    bucket[text] = semantic_key
        for per_platform in DOMAIN_PLATFORM_SEMANTIC_ALIASES.get(domain, {}).values():
            for semantic_key, aliases in per_platform.items():
                if not is_inferable_semantic_key(semantic_key):
                    continue
                for alias in aliases:
                    text = str(alias or "").strip()
                    if text and text not in bucket:
                        bucket[text] = semantic_key
        result[domain] = bucket
    return result


_NORMALIZED_ALIAS_INDEX = _build_normalized_alias_index()
_NORMALIZED_DOMAIN_ALIAS_INDEX = _build_normalized_domain_alias_index()
_NORMALIZED_COLUMN_OVERRIDE_INDEX = _build_normalized_column_override_index()
#: 封闭域的**逐字**别名索引(字典侧)
_EXACT_CLOSED_DOMAIN_ALIAS_INDEX = _build_exact_closed_domain_alias_index()


# ── 运行时别名(来自 semantic.semantic_field_aliases) ─────────────────
#
# [*] 批次 D: 表里本来就有 75 条别名(products 域的「销售额」「曝光次数」
# 「点击次数」「转化率」「商品成交件数」…), 但 ORM 侧**没有模型**,
# Python 侧压根看不见这张表 ⇒ 这些别名从来没进过推断链路。
#
# 现在把它们加载进来, 并且按来源分优先级:
#   * 用户确认过(manual / template_confirmed) —— **最高**, 一处生效;
#   * 内置(builtin) —— 次之, 不覆盖代码里的 curated 表。
_RUNTIME_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}
_RUNTIME_CONFIRMED_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}
#: 封闭域的**逐字**运行时别名索引 —— 域 → {原始列名: 标准字段}。
#:
#: 归一化索引对 orders 域是**危险的**(会把原币列与 (RMB) 列压成同一个 key),
#: 所以封闭域另存一份逐字索引, 推断时只用它。
_RUNTIME_EXACT_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}
_RUNTIME_ALIAS_LOADED = False

#: 全局别名用的域占位符
GLOBAL_ALIAS_DOMAIN = "*"


def _runtime_alias_bucket(
    index: Dict[str, Dict[str, str]], domain: str
) -> Dict[str, str]:
    """取「域内 + 全局」的合并视图(域内优先)。"""
    merged: Dict[str, str] = {}
    merged.update(index.get(GLOBAL_ALIAS_DOMAIN, {}))
    merged.update(index.get(domain, {}))
    return merged


async def load_runtime_aliases(db) -> int:
    """把 ``semantic.semantic_field_aliases`` 的有效别名加载进推断索引。

    只加载 ``status='active'`` 的行 —— ``conflict`` 与 ``disabled``
    的行**不进**推断(冲突必须先裁决, 否则等于替用户拍板)。

    Returns:
        加载进来的别名条数。
    """
    global _RUNTIME_ALIAS_INDEX, _RUNTIME_CONFIRMED_ALIAS_INDEX, _RUNTIME_ALIAS_LOADED
    global _RUNTIME_EXACT_ALIAS_INDEX

    builtin_bucket: Dict[str, Dict[str, str]] = {}
    confirmed_bucket: Dict[str, Dict[str, str]] = {}
    exact_bucket: Dict[str, Dict[str, str]] = {}

    try:
        from modules.core.db import SemanticFieldAlias
        from sqlalchemy import select

        result = await db.execute(
            select(SemanticFieldAlias).where(SemanticFieldAlias.status == "active")
        )
        rows = list(result.scalars().all())
    except Exception:  # noqa: BLE001 - 表不存在/连不上时不阻断应用
        _RUNTIME_ALIAS_LOADED = True
        return 0

    for row in rows:
        domain = (
            str(getattr(row, "data_domain", "") or "").strip().lower()
            or GLOBAL_ALIAS_DOMAIN
        )
        semantic_key = str(getattr(row, "standard_field", "") or "").strip()
        raw_alias = str(getattr(row, "raw_alias", "") or "").strip()
        source = str(getattr(row, "source", "") or "").strip()
        if not semantic_key or not raw_alias:
            continue
        if not is_canonical_semantic_key(semantic_key):
            continue
        normalized = normalize_semantic_alias(raw_alias)
        if not normalized:
            continue
        is_confirmed = source in {"manual", "template_confirmed"}
        bucket = confirmed_bucket if is_confirmed else builtin_bucket
        bucket.setdefault(domain, {}).setdefault(normalized, semantic_key)
        if domain in DOMAIN_CLOSED_ALIAS_DOMAINS and is_inferable_semantic_key(
            semantic_key
        ):
            # 封闭域另存**逐字**形态 —— 归一化会混币种。
            exact_bucket.setdefault(domain, {}).setdefault(raw_alias, semantic_key)
        if is_confirmed and domain == GLOBAL_ALIAS_DOMAIN:
            # [*] 人工确认过的**全局**别名也要能被封闭域逐字命中
            # (「一处生效」的产品承诺)。只存确认过的 —— builtin 的全局裸名
            # 在 orders 域指的是原币列, 放进来 = 静默混币种。
            exact_bucket.setdefault(GLOBAL_ALIAS_DOMAIN, {}).setdefault(
                raw_alias, semantic_key
            )

    _RUNTIME_EXACT_ALIAS_INDEX = exact_bucket
    _RUNTIME_ALIAS_INDEX = builtin_bucket
    _RUNTIME_CONFIRMED_ALIAS_INDEX = confirmed_bucket
    _RUNTIME_ALIAS_LOADED = True
    total = sum(len(item) for item in builtin_bucket.values()) + sum(
        len(item) for item in confirmed_bucket.values()
    )
    return total


def runtime_alias_snapshot() -> Dict[str, Dict[str, str]]:
    """当前生效的运行时别名快照(给接口与测试用)。"""
    return {
        "builtin": {
            domain: dict(items) for domain, items in _RUNTIME_ALIAS_INDEX.items()
        },
        "confirmed": {
            domain: dict(items)
            for domain, items in _RUNTIME_CONFIRMED_ALIAS_INDEX.items()
        },
        "loaded": _RUNTIME_ALIAS_LOADED,
    }


def runtime_alias_count() -> int:
    return sum(len(item) for item in _RUNTIME_ALIAS_INDEX.values()) + sum(
        len(item) for item in _RUNTIME_CONFIRMED_ALIAS_INDEX.values()
    )


SEMANTIC_HASH_IDENTITY_KEYS = {
    key for key, meta in SEMANTIC_FIELD_META.items() if meta.get("hash_eligible")
}

# 语义复核状态取值
REVIEW_STATUS_CONFIRMED_SEMANTIC = "confirmed_semantic"
REVIEW_STATUS_CONFIRMED_NON_SEMANTIC = "confirmed_non_semantic"
REVIEW_STATUS_PENDING = "pending"

# 语义复核状态**来源**：区分「用户明确确认」与「系统按表头名推断」。
#
# 为什么需要这个区分：
# 历史绑定里只要推断出了 semantic_key 就会被标成 confirmed_semantic，
# 于是「产品ID」这种中文列名也会被当成 product_id 身份，
# 与真正写成 product_id 的模板判成「口径一致」⇒ 假一致。
# 只有用户明确点过确认的绑定，才允许被提升成语义身份。
REVIEW_SOURCE_USER = "user"
REVIEW_SOURCE_INFERRED = "inferred"


def normalize_semantic_key(value: Optional[str]) -> Optional[str]:
    """把任意写法归一化成**规范语义键**。

    [*] 批次 D: 两级匹配。

    1. **逐字相等**(旧口径): 直接命中别名表 —— 保证老数据行为不变;
    2. **归一化相等**(新口径): 去掉币种后缀/空格/下划线/星号/全角标点后再比 ——
       这是命中率从 3~6% 提到 60%+ 的关键。

    归一化后仍然认不出来 ⇒ 返回小写原文(不猜)。
    """
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in SEMANTIC_FIELD_ALIASES:
        return lowered

    for semantic_key, aliases in SEMANTIC_FIELD_ALIASES.items():
        if lowered == semantic_key:
            return semantic_key
        if any(lowered == str(alias).strip().lower() for alias in aliases):
            return semantic_key

    # [*] 批次 D: 归一化匹配
    normalized = normalize_semantic_alias(text)
    if normalized:
        matched = _NORMALIZED_ALIAS_INDEX.get(normalized)
        if matched:
            return matched

    return lowered


#: 封闭域的「纯 ASCII 别名」归一化索引(懒构建)。
#:
#: 为什么需要它: 封闭域必须**逐字**匹配 —— 否则「利润」会被认成
#: 「利润(RMB)」(原币列)⇒ 静默混币种。但**英文/数字别名**
#: (``order_no`` / ``profit_amount`` / ``buyer_paid``)没有币种歧义,
#: 它们本来就该被识别(否则模板里的英文列名全部失联)。
#:
#: ⇒ 这份索引只收**不含中文**的别名 ⇒ 中文裸名永远进不来;
#: 且只收**该域用到的字段** ⇒ 不跨域污染。
_CLOSED_DOMAIN_ASCII_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}
_CLOSED_DOMAIN_ASCII_ALIAS_INDEX_BUILT = False

#: 中日韩文字符(用于「这个别名是不是中文」的判定)。
_CJK_ALIAS_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _build_closed_domain_ascii_alias_index() -> Dict[str, Dict[str, str]]:
    """按域构建「纯 ASCII 别名」的归一化索引(封闭域专用)。"""
    result: Dict[str, Dict[str, str]] = {}
    for domain in DOMAIN_CLOSED_ALIAS_DOMAINS:
        bucket: Dict[str, str] = {}
        keys = set(DOMAIN_SEMANTIC_ALIASES.get(domain, {}).keys())
        for key, meta in SEMANTIC_FIELD_DEFINITIONS.items():
            if str(meta.get("domain") or "") == domain:
                keys.add(key)
        for key in sorted(keys):
            if not is_inferable_semantic_key(key):
                continue
            meta = SEMANTIC_FIELD_DEFINITIONS.get(key, {})
            names = [key, *(meta.get("aliases") or [])]
            names += list(DOMAIN_SEMANTIC_ALIASES.get(domain, {}).get(key, ()))
            for per_platform in DOMAIN_PLATFORM_SEMANTIC_ALIASES.get(
                domain, {}
            ).values():
                names += list(per_platform.get(key, ()))
            for name in names:
                text = str(name or "").strip()
                if not text or _CJK_ALIAS_PATTERN.search(text):
                    continue
                normalized = normalize_semantic_alias(text)
                if normalized and normalized not in bucket:
                    bucket[normalized] = key
        result[domain] = bucket
    return result


def closed_domain_ascii_alias_index() -> Dict[str, Dict[str, str]]:
    """取封闭域的 ASCII 别名索引(首次调用时构建)。"""
    global _CLOSED_DOMAIN_ASCII_ALIAS_INDEX_BUILT
    if not _CLOSED_DOMAIN_ASCII_ALIAS_INDEX_BUILT:
        _CLOSED_DOMAIN_ASCII_ALIAS_INDEX.update(
            _build_closed_domain_ascii_alias_index()
        )
        _CLOSED_DOMAIN_ASCII_ALIAS_INDEX_BUILT = True
    return _CLOSED_DOMAIN_ASCII_ALIAS_INDEX


def is_canonical_semantic_key(value: Optional[str]) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and text in SEMANTIC_FIELD_ALIASES


def is_hash_identity_semantic_key(value: Optional[str]) -> bool:
    normalized = normalize_semantic_key(value)
    return bool(normalized) and normalized in SEMANTIC_HASH_IDENTITY_KEYS


def resolve_binding_review_status(binding: Optional[Dict[str, Any]]) -> str:
    """返回一条字段绑定的语义复核状态。

    这是读写两侧判定"绑定是否已确认"的唯一来源，避免同一个绑定
    在保存闸门、hash 闸门、读取展示三处得到不同结论。

    规则：
    - 显式带 ``semantic_review_status`` 时以它为准；
    - 历史数据里没有该字段、但已经推断出 ``semantic_key`` 的绑定，
      按迁移期兼容口径视为已确认；
    - 其余情况一律视为待复核。
    """
    if not binding:
        return REVIEW_STATUS_PENDING
    status = str(binding.get("semantic_review_status") or "").strip()
    if status:
        return status
    if normalize_semantic_key(binding.get("semantic_key")):
        return REVIEW_STATUS_CONFIRMED_SEMANTIC
    return REVIEW_STATUS_PENDING


def is_confirmed_semantic_binding(binding: Optional[Dict[str, Any]]) -> bool:
    return resolve_binding_review_status(binding) == REVIEW_STATUS_CONFIRMED_SEMANTIC


def parse_rule_provided_semantic_keys(
    field_parse_rules: Optional[Iterable[Dict[str, Any]]],
) -> set[str]:
    """解析规则能够提供数据来源的语义键集合。

    只要存在一条解析规则产出该语义键，就认为它有数据来源，
    因此不再要求它必须同时具备 confirmed 绑定。
    """
    provided: set[str] = set()
    for rule in field_parse_rules or []:
        if not isinstance(rule, dict):
            continue
        semantic_key = normalize_semantic_key(
            rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
        )
        if semantic_key and is_canonical_semantic_key(semantic_key):
            provided.add(semantic_key)
    return provided


def get_semantic_field_meta(semantic_key: Optional[str]) -> dict[str, Any]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return {}
    meta = SEMANTIC_FIELD_META.get(normalized, {})
    return {"semantic_key": normalized, **meta} if meta else {}


def infer_semantic_key(*values: Optional[str]) -> Optional[str]:
    for value in values:
        normalized = normalize_semantic_key(value)
        if normalized in SEMANTIC_FIELD_ALIASES:
            return normalized
    return None


def infer_semantic_key_for_domain(
    data_domain: Optional[str],
    *values: Optional[str],
) -> Optional[str]:
    """按数据域推断列名对应的语义键。

    [*] 批次 D: 三级查找, 先具体后通用, 每一级都做**归一化**匹配。

    1. **域限定列名表**(:data:`DOMAIN_COLUMN_SEMANTIC_OVERRIDES`)
       —— 同一个列名在不同域含义不同, 所以域内优先;
    2. **域限定别名表**(:data:`DOMAIN_SEMANTIC_ALIASES`)
       —— 域内业务别名(「买家支付」→ ``paid_amount``);
    3. **全局别名表**(:data:`SEMANTIC_FIELD_ALIASES`)。

    这样既能让 ``商品编号`` / ``ID`` / ``客服ID`` 这类真实表头被认出来,
    又不会把「同名列不同含义」污染到别的数据域。
    """
    domain = str(data_domain or "").strip().lower()
    # [*] 2026-11-08: 报表**分块列**(列名末尾带 .N)不落标准字段。
    # 实测(tiktok 商品月报 777 行): 基础列 == .1+.2+.3+.4 在 701 行成立,
    # 同理 GMV == GMV.1+GMV.2+GMV.3 在 684 行成立
    # ⇒ .N 是报表的**第 N 块**, 不是基础指标的另一个写法。
    # 归一化会把它们压到与基础列同名 ⇒ 命中它就是把"一块"当成"总量" ⇒ 静默失真。
    # 宁可落 unknown, 也不猜。
    for value in values:
        if is_block_column_alias(value):
            return None
    override_index = _NORMALIZED_COLUMN_OVERRIDE_INDEX.get(domain, {})
    if override_index:
        for value in values:
            normalized = normalize_semantic_alias(value)
            if not normalized:
                continue
            target = override_index.get(normalized)
            if target and is_canonical_semantic_key(target):
                return target

    # [*] 2026-11-08: 封闭域(orders)走**逐字**匹配。
    #
    # 归一化索引对 orders 域是危险的: ``normalize_alias("利润(RMB)") ==
    # normalize_alias("利润")`` ⇒ 原币列会被一起认领 ⇒ 静默混币种。
    # ⇒ 封闭域只认「一个字符都不差」的列名; 认不出就是认不出(返回 None)。
    if domain in DOMAIN_CLOSED_ALIAS_DOMAINS:
        exact_runtime = _RUNTIME_EXACT_ALIAS_INDEX.get(domain, {})
        exact_dict = _EXACT_CLOSED_DOMAIN_ALIAS_INDEX.get(domain, {})
        # [*] 用户**人工确认过**的全局别名(域 ``*``)也要能在封闭域命中 ——
        # 「一处生效」是产品承诺。但只取**确认过的**那部分: builtin 的全局
        # 裸名(如「利润」)在 orders 域指的是**原币列**, 放进来 = 静默混币种。
        exact_confirmed_global = _RUNTIME_EXACT_ALIAS_INDEX.get(GLOBAL_ALIAS_DOMAIN, {})
        ascii_index = closed_domain_ascii_alias_index().get(domain, {})
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            target = (
                exact_runtime.get(text)
                or exact_dict.get(text)
                or exact_confirmed_global.get(text)
            )
            if target and is_canonical_semantic_key(target):
                return target
            # **纯 ASCII 列名**(order_no / profit_amount / buyer_paid)
            # 没有币种歧义 ⇒ 允许走归一化匹配(该索引里只有不含中文的
            # 别名, 中文裸名进不来 ⇒ 不会认到原币列)。
            if not _CJK_ALIAS_PATTERN.search(text):
                normalized = normalize_semantic_alias(text)
                target = ascii_index.get(normalized) if normalized else None
                if target and is_canonical_semantic_key(target):
                    return target
        return None

    # [*] 批次 D: 用户确认过的全局别名 —— 优先级最高(一处生效)。
    if _RUNTIME_CONFIRMED_ALIAS_INDEX:
        confirmed = _runtime_alias_bucket(_RUNTIME_CONFIRMED_ALIAS_INDEX, domain)
        if confirmed:
            for value in values:
                normalized = normalize_semantic_alias(value)
                if not normalized:
                    continue
                target = confirmed.get(normalized)
                if target and is_canonical_semantic_key(target):
                    return target

    domain_alias_index = _NORMALIZED_DOMAIN_ALIAS_INDEX.get(domain, {})
    if domain_alias_index:
        for value in values:
            normalized = normalize_semantic_alias(value)
            if not normalized:
                continue
            target = domain_alias_index.get(normalized)
            if target and is_canonical_semantic_key(target):
                return target

    # [*] 批次 D: 表里的内置别名(semantic.semantic_field_aliases)。
    if _RUNTIME_ALIAS_INDEX:
        builtin = _runtime_alias_bucket(_RUNTIME_ALIAS_INDEX, domain)
        if builtin:
            for value in values:
                normalized = normalize_semantic_alias(value)
                if not normalized:
                    continue
                target = builtin.get(normalized)
                if target and is_canonical_semantic_key(target):
                    return target

    return infer_semantic_key(*values)


def get_semantic_aliases(semantic_key: Optional[str]) -> list[str]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return []
    aliases = SEMANTIC_FIELD_ALIASES.get(normalized, [normalized])
    return list(dict.fromkeys([normalized, *aliases]))


def get_semantic_requirements(semantic_key: Optional[str]) -> dict[str, Any]:
    """语义键的要求(required / hash 参与资格)。

    [*] 批次 E(E-3 / 规格 D2): **不再返回** ``hash_participates``。

    以前这个字段挂在**绑定**上, 但它只是「模板级 ``deduplication_fields``」
    的派生投影 —— 同一事实两处真相, 而且**声明了但没接线**
    (真正喂 ``calculate_data_hash`` 的是模板级字段表)。

    现在「参与去重」由**版本级核心字段清单**的 ``in_hash`` 表达
    (:mod:`backend.services.core_fields_service`), 绑定级不再重复声明。
    """
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return {"required": False}
    meta = SEMANTIC_FIELD_META.get(normalized, {})
    return {
        "required": bool(meta.get("required", False)),
        "hash_eligible": bool(meta.get("hash_eligible", False)),
        "semantic_kind": str(meta.get("kind", "")),
        "system_scope": bool(meta.get("system_scope", False)),
        "identity_strength": meta.get("identity_strength"),
        "hash_warning": meta.get("hash_warning"),
    }


def _normalize_key_variants(key: str) -> set[str]:
    lowered = key.strip().lower()
    variants = {lowered}
    extractor = get_currency_extractor()
    normalized = extractor.normalize_field_name(key)
    variants.add(normalized.lower())
    variants.add(lowered.replace(" ", ""))
    variants.add(lowered.replace("_", ""))
    variants.add(normalized.lower().replace("_", ""))
    return {variant for variant in variants if len(variant) > 1}


def resolve_semantic_value(
    row: Dict[str, Any],
    semantic_key: str,
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
) -> tuple[Any, Optional[str]]:
    normalized_key = normalize_semantic_key(semantic_key)
    if not normalized_key:
        return None, None

    candidate_names: list[str] = []
    binding_candidates = list(header_bindings or [])
    for binding in binding_candidates:
        binding_semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if binding_semantic_key != normalized_key:
            continue
        raw_name = str(binding.get("raw_name") or "").strip()
        if raw_name:
            candidate_names.append(raw_name)
        source_header = str(binding.get("source_header") or "").strip()
        if source_header:
            candidate_names.append(source_header)
        display_name = str(binding.get("display_name") or "").strip()
        if display_name:
            candidate_names.append(display_name)
        for alias in binding.get("aliases") or []:
            alias_text = str(alias or "").strip()
            if alias_text:
                candidate_names.append(alias_text)

    candidate_names.extend(get_semantic_aliases(normalized_key))
    seen_names: list[str] = []
    seen_set = set()
    for name in candidate_names:
        lowered = str(name).strip().lower()
        if not lowered or lowered in seen_set:
            continue
        seen_set.add(lowered)
        seen_names.append(str(name).strip())

    row_lookup = {
        str(key).strip().lower(): key for key in row.keys() if str(key).strip()
    }
    for candidate in seen_names:
        matched_key = row_lookup.get(candidate.lower())
        if matched_key is not None:
            return row.get(matched_key), matched_key

    for key, value in row.items():
        key_variants = _normalize_key_variants(str(key))
        for candidate in seen_names:
            if any(
                candidate_variant in key_variants
                for candidate_variant in _normalize_key_variants(candidate)
            ):
                return value, key
    return None, None


# ── 标准字段定义的对外投影(批次 D · API-1) ─────────────────────────
#
# 为什么要有这一层
# --------------
# 前端以前在 ``headerBindings.js`` 里**自己抄了一份**标准字段定义。
# 实测两份已经漂了(2026-11-07):
#
#   * 41 个字段里, 前端**普遍缺** ``domain`` / ``required`` / ``system_scope``
#     ⇒ 前端算出来的 ``required`` 永远是 false, 与后端的契约判定对不上;
#   * ``product_name`` 前端叫「商品名」后端叫「商品名称」;
#     ``item_status`` 前端叫「发品状态」后端叫「商品状态」;
#   * 5 个字段的别名列表对不上(``platform_sku`` 大小写、``line_id`` 少一条 …)。
#
# ⇒ 用户在前端看到的选项 ≠ 后端实际认定(FE-1)。
#
# 这一层把「唯一一份定义」投影成前端能直接用的结构, 前端不再抄。

#: 下拉框分组(键 → 中文标题, 顺序即展示顺序)。
SEMANTIC_OPTION_GROUPS: tuple[tuple[str, str], ...] = (
    ("identity", "身份字段"),
    ("time", "时间字段"),
    ("traffic_metric", "流量指标"),
    ("order_metric", "订单指标"),
    ("product_metric", "商品指标"),
    ("attribution_metric", "渠道归因指标"),
    ("attribute", "属性字段"),
)

_ORDER_METRIC_KEYS = frozenset(
    {
        "order_count",
        "sku_order_count",
        "sales_amount",
        "sales_volume",
        "paid_amount",
        "profit",
        "platform_commission",
    }
)
_PRODUCT_METRIC_KEYS = frozenset({"purchase_amount"})
_ATTRIBUTION_METRIC_KEYS = frozenset(
    {
        "live_gmv",
        "live_attributed_gmv",
        "live_indirect_gmv",
        "video_gmv",
        "video_attributed_gmv",
        "video_indirect_gmv",
    }
)


def semantic_option_group_key(
    semantic_key: Optional[str], meta: Optional[Dict[str, Any]] = None
) -> str:
    """判定一个语义键属于哪个下拉分组。

    规则与前端旧实现逐条对应(前端旧实现是这段逻辑的**副本**,
    现在前端直接用后端算好的 ``group``)。
    """
    meta = (
        meta
        if meta is not None
        else SEMANTIC_FIELD_META.get(str(semantic_key or ""), {})
    )
    key = str(semantic_key or "")
    kind = str(meta.get("kind") or "")
    domain = str(meta.get("domain") or "common")
    if kind == "time":
        return "time"
    if kind in ("identity", "dimension"):
        return "identity"
    if key in _ATTRIBUTION_METRIC_KEYS or domain == "attribution":
        return "attribution_metric"
    if key in _ORDER_METRIC_KEYS or domain == "orders":
        return "order_metric"
    if key in _PRODUCT_METRIC_KEYS or domain == "products":
        return "product_metric"
    if kind == "metric":
        return "traffic_metric"
    return "attribute"


def build_semantic_field_definitions_payload() -> Dict[str, Any]:
    """标准字段定义的只读投影(API-1 的返回体)。

    这份载荷就是前端唯一的标准字段来源 ——
    前端不再维护副本, 因此不会再出现「前端看到的 ≠ 后端认定的」。
    """
    fields: list[Dict[str, Any]] = []
    options: list[Dict[str, Any]] = []
    for key, meta in SEMANTIC_FIELD_META.items():
        aliases = get_semantic_aliases(key)
        group = semantic_option_group_key(key, meta)
        description = SEMANTIC_FIELD_DESCRIPTIONS.get(key, "")
        fields.append(
            {
                "semantic_key": key,
                "label": str(meta.get("label") or key),
                "description": description,
                "kind": str(meta.get("kind") or "attribute"),
                "domain": str(meta.get("domain") or "common"),
                "required": bool(meta.get("required", False)),
                "hash_eligible": bool(meta.get("hash_eligible", False)),
                "default_hash": bool(meta.get("default_hash", False)),
                "system_scope": bool(meta.get("system_scope", False)),
                "identity_strength": meta.get("identity_strength"),
                "hash_warning": meta.get("hash_warning"),
                "aliases": aliases,
                "option_group": group,
            }
        )
        options.append(
            {
                "value": key,
                "label": f"{meta.get('label') or key} ({key})",
                "description": description,
                "kind": str(meta.get("kind") or "attribute"),
                "domain": str(meta.get("domain") or "common"),
                "group": group,
                "hash_eligible": bool(meta.get("hash_eligible", False)),
                "default_hash": bool(meta.get("default_hash", False)),
                "system_scope": bool(meta.get("system_scope", False)),
                "identity_strength": meta.get("identity_strength"),
                "hash_warning": meta.get("hash_warning"),
                "aliases": aliases,
            }
        )

    option_groups: list[Dict[str, Any]] = []
    for group_key, group_label in SEMANTIC_OPTION_GROUPS:
        grouped = [option for option in options if option["group"] == group_key]
        if not grouped:
            continue
        option_groups.append({"label": group_label, "options": grouped})

    domain_aliases = [
        {
            "data_domain": domain,
            "semantic_key": semantic_key,
            "aliases": list(aliases),
        }
        for domain, alias_map in DOMAIN_SEMANTIC_ALIASES.items()
        for semantic_key, aliases in alias_map.items()
    ]
    column_overrides = [
        {"data_domain": domain, "raw_name": raw_name, "semantic_key": semantic_key}
        for domain, mapping in DOMAIN_COLUMN_SEMANTIC_OVERRIDES.items()
        for raw_name, semantic_key in mapping.items()
    ]

    return {
        "fields": fields,
        "option_groups": option_groups,
        "domain_aliases": domain_aliases,
        "column_overrides": column_overrides,
        "system_hash_scope_fields": sorted(SYSTEM_HASH_SCOPE_KEYS),
        "hash_identity_keys": sorted(SEMANTIC_HASH_IDENTITY_KEYS),
        "runtime_alias_count": runtime_alias_count(),
        "runtime_alias_loaded": _RUNTIME_ALIAS_LOADED,
        # [*] 运行时别名索引 —— 这两份是**活的**: 用户在模板里沉淀一次,
        #     别名就多一条 ⇒ 前端必须每次从接口拿, 不能用快照。
        "runtime_alias_index": {
            domain: dict(items)
            for domain, items in _RUNTIME_CONFIRMED_ALIAS_INDEX.items()
        },
        "runtime_builtin_alias_index": {
            domain: dict(items) for domain, items in _RUNTIME_ALIAS_INDEX.items()
        },
    }


#: 归一化口径的「样本对」—— 用来锁住前后端两套归一化实现一致。
#:
#: 前端必须自己算一次归一化(它要在浏览器里查别名索引),
#: 所以前端有一份 :func:`normalize_semantic_alias` 的镜像实现。
#: 这份样本对由后端生成, 前端测试逐条断言 ⇒ 两边漂了就红。
NORMALIZATION_SAMPLE_VALUES: tuple[str, ...] = (
    "订单号",
    "订单编号",
    "买家支付(RMB)",
    "买家支付（rmb）",
    "利润（rmb）",
    "利润(RMB)",
    "商品SKU",
    "商品 sku",
    "下单时间\n",
    "*商品sku",
    "*商品名称",
    "商品 id",
    "商品ID",
    "客服ID",
    "日期期间",
    "GMV",
    "gmv",
    "  销售额  ",
    "销售_数量",
    "支付订单数",
    "商品成交件数",
    "曝光次数",
    "点击次数",
    "转化率",
    "date_from",
    "date_to",
    "order id",
    "Order ID",
    "line_id",
    "订单明细行ID",
)


def build_semantic_field_snapshot_payload() -> Dict[str, Any]:
    """前端快照载荷 —— 归一化索引 + 样本对 + 字段定义。

    前端在**浏览器里**用这份快照当兜底(接口没回来时不至于整页空白),
    同时用 ``normalization_samples`` 锁住前后端归一化口径一致。

    这份快照是**生成物**, 不是人手维护的副本 ——
    ``backend/tests/data_pipeline/test_semantic_translation_guardrails.py``
    会重新生成一遍并比对, 漂了就红。
    """
    payload = build_semantic_field_definitions_payload()
    # [*] 运行时别名索引是**活的**(用户在模板里沉淀一次就变一次) ⇒ 不能进快照。
    #     快照只放「代码里定义的」那部分, 运行期数据一律走接口。
    payload.pop("runtime_alias_index", None)
    payload.pop("runtime_builtin_alias_index", None)
    payload["alias_index"] = dict(_NORMALIZED_ALIAS_INDEX)
    payload["domain_alias_index"] = {
        domain: dict(items) for domain, items in _NORMALIZED_DOMAIN_ALIAS_INDEX.items()
    }
    payload["domain_column_index"] = {
        domain: dict(items)
        for domain, items in _NORMALIZED_COLUMN_OVERRIDE_INDEX.items()
    }
    payload["normalization_samples"] = [
        [raw, normalize_semantic_alias(raw)] for raw in NORMALIZATION_SAMPLE_VALUES
    ]
    return payload
