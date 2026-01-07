# 字段辞典内容对照表

**生成时间**: 2025-10-30 17:32:48
**总字段数**: 309

## 📋 使用说明

本对照表用于：
- ✅ 检查自动映射是否正确
- ✅ 查找合适的标准字段进行映射
- ✅ 发现辞典设计问题
- ✅ 验证同义词是否完整

**重要提示**：
- `field_code` 是系统内部使用的标准字段代码（数据库列名）
- `cn_name` 是中文显示名称（数据库列名层，用户选择）
- `en_name` 是英文名称（备用显示）
- `synonyms` 是同义词列表（用于智能匹配）

---

## 📦 订单域 (orders) - 141个字段

| 字段代码 (field_code) | 中文名称 (cn_name) | 英文名称 (en_name) | 同义词 (synonyms) | 数据域 | 是否必填 | 数据类型 |
|:---|:---|:---|:---|:---|:---|:---|
### 维度字段 (4个)

| `account` | 账号 |  | - | orders | ❌ | string |
| `order_id` | 订单号 |  | - | orders | ✅ 必填 | string |
| `platform_code` | 平台 |  | - | orders | ✅ 必填 | string |
| `shop_id` | 店铺 |  | - | orders | ✅ 必填 | string |
### 金额字段 (1个)

| `total_amount` | 订单金额 |  | - | orders | ✅ 必填 | float |
### 时间字段 (1个)

| `order_time_utc` | 下单时间 |  | - | orders | ✅ 必填 | datetime |
### 其他字段 (132个)

| `account_cai_gou` | 采购账号 | account_采购 | - | orders | ❌ | string |
| `actual_shipping_fee` | 实际运费 | 实际运费 | - | orders | ❌ | string |
| `adjustment_cu_xiao` | 促销调整 | 促销调整 | - | orders | ❌ | string |
| `adjustment_qi_ta` | 其他调整 | 其他调整 | - | orders | ❌ | string |
| `advertising_cost` | 广告成本 | 广告成本 | - | orders | ❌ | string |
| `amount_adjustment_zong` | 总调整金额 | amount_总调整 | - | orders | ❌ | string |
| `amount_cai_gou` | 采购金额 | amount_采购 | - | orders | ❌ | string |
| `amount_yi_jie_suan` | 已结算金额 | amount_已结算 | - | orders | ❌ | string |
| `amount_yu_gu_hui_kuan` | 预估回款金额 | amount_预估回款 | - | orders | ❌ | string |
| `ba_xi_kua_jing_shui` | 巴西跨境税 | 巴西跨境税 | - | orders | ❌ | string |
| `bao_cai_fei` | 包材费 | 包材费 | - | orders | ❌ | string |
| `bao_guo_hao` | 包裹号 | 包裹号 | - | orders | ❌ | string |
| `bao_guo_sun_shi_pei_chang` | 包裹损失赔偿 | 包裹损失赔偿 | - | orders | ❌ | string |
| `c34_c78_c03_c84_c16_c53` | 卖家支付运费 | 卖家支付运费 | - | orders | ❌ | string |
| `cai_gou_dan_hao` | 采购单号 | 采购单号 | - | orders | ❌ | string |
| `cang_ku_cao_zuo_fei` | 仓库操作费 | 仓库操作费 | - | orders | ❌ | string |
| `chu_ku_cang_ku` | 出库仓库 | 出库仓库 | - | orders | ❌ | string |
| `commission_da_ren` | 达人佣金 | 达人佣金 | - | orders | ❌ | string |
| `commission_lian_meng` | 联盟佣金 | 联盟佣金 | - | orders | ❌ | string |
| `commission_lian_meng_shang_dian_guang_gao` | 联盟商店广告佣金 | 联盟商店广告佣金 | - | orders | ❌ | string |
| `compensation_ke_hu_fu_wu` | 客户服务补偿 | 客户服务补偿 | - | orders | ❌ | string |
| `compensation_wu_liu` | 物流补偿 | 物流补偿 | - | orders | ❌ | string |
| `cost` | 成本 | 成本 | - | orders | ❌ | string |
| `cost_profit_rate` | 成本利润率 | 成本利润率 | - | orders | ❌ | string |
| `di_san_fang_tuo_guan_shui` | 第三方托管税 | 第三方托管税 | - | orders | ❌ | string |
| `discount_shang_jia_hou_tui_kuan_xiao_ji` | 商家折扣后退款小计 | 商家折扣后退款小计 | - | orders | ❌ | string |
| `discount_shang_jia_qian_tui_kuan_xiao_ji` | 商家折扣前退款小计 | 商家折扣前退款小计 | - | orders | ❌ | string |
| `discounted_price_product` | 产品折后价格 | product_price_折后 | - | orders | ❌ | string |
| `fan_qing_xiao_shui` | 反倾销税 | 反倾销税 | - | orders | ❌ | string |
| `gmv_guang_gao_fei_yong` | GMV广告费用 | gmv广告费用 | - | orders | ❌ | string |
| `gong_tong_chu_zi_fei_yong` | 共同出资费用 | 共同出资费用 | - | orders | ❌ | string |
| `guan_shui` | 关税 | 关税 | - | orders | ❌ | string |
| `jiao_yi_fei` | 交易费 | 交易费 | - | orders | ❌ | string |
| `jiao_yi_shou_xu_fei` | 交易手续费 | 交易手续费 | - | orders | ❌ | string |
| `jin_kou_zeng_zhi_shui` | 进口增值税 | 进口增值税 | - | orders | ❌ | string |
| `kua_jing_shui` | 跨境税 | 跨境税 | - | orders | ❌ | string |
| `ma_lai_xi_ya_shui_fei_sst` | 马来西亚税费SST | 马来西亚税费sst | - | orders | ❌ | string |
| `ma_lai_xi_ya_tui_huo_zeng_zhi_shui_sst` | 马来西亚退货增值税（sst） | 马来西亚退货增值税（sst） | - | orders | ❌ | string |
| `mai_jia_shen_qing_tui_kuan` | 买家申请退款 | 买家申请退款 | - | orders | ❌ | string |
| `mai_jia_voucher` | 卖家voucher | 卖家voucher | - | orders | ❌ | string |
| `mo_xi_ge_lian_bang_suo_de_shui` | 墨西哥联邦所得税 | 墨西哥联邦所得税 | - | orders | ❌ | string |
| `mo_xi_ge_zeng_zhi_shui` | 墨西哥增值税 | 墨西哥增值税 | - | orders | ❌ | string |
| `operation_cost` | 运营成本 | 运营成本 | - | orders | ❌ | string |
| `order_amount_yuan_shi` | 订单原始金额 | order_amount_原始 | - | orders | ❌ | string |
| `order_compensation_tui_kuan` | 退款订单补偿 | order_退款补偿 | - | orders | ❌ | string |
| `order_cost` | 订单成本 | order_成本 | - | orders | ❌ | string |
| `order_info` | 订单信息 | order_信息 | - | orders | ❌ | string |
| `order_status` | 订单状态 | order_status | - | orders | ❌ | string |
| `original_price_shipping_fee_mai_jia` | 买家运费原价 | 买家运费原价 | - | orders | ❌ | string |
| `other_cost` | 其他成本 | 其他成本 | - | orders | ❌ | string |
| `outbound_quantity` | 出库数量 | quantity_出库 | - | orders | ❌ | string |
| `paid_amount` | 实付金额 | amount_实付 | - | orders | ❌ | string |
| `paid_amount_mai_jia` | 买家实付金额 | amount_买家实付 | - | orders | ❌ | string |
| `payment_time` | 付款时间 | time_付款 | - | orders | ❌ | string |
| `platform_code_cai_gou` | 采购平台 | platform_采购 | - | orders | ❌ | string |
| `platform_code_cheng_fa` | 平台惩罚 | platform_惩罚 | - | orders | ❌ | string |
| `platform_code_compensation` | 平台补偿 | platform_补偿 | - | orders | ❌ | string |
| `platform_code_discount_tiktok_shop` | TikTok Shop平台折扣 | platform_tiktok_shop折扣 | - | orders | ❌ | string |
| `platform_code_shou_ru_zhi_chu` | 平台收入/支出 | platform_收入/支出 | - | orders | ❌ | string |
| `platform_commission` | 平台佣金 | platform_佣金 | - | orders | ❌ | string |
| `platform_commission_adjustment` | 平台佣金调整 | platform_佣金调整 | - | orders | ❌ | string |
| `platform_commission_compensation` | 平台佣金补偿 | platform_佣金补偿 | - | orders | ❌ | string |
| `platform_commission_discount` | 平台佣金折扣 | platform_佣金折扣 | - | orders | ❌ | string |
| `platform_commission_tiktok_shop` | TikTok Shop平台佣金 | platform_tiktok_shop佣金 | - | orders | ❌ | string |
| `product_discount_mai_jia` | 卖家产品折扣 | product_卖家折扣 | - | orders | ❌ | string |
| `product_discount_shang_jia` | 商家产品折扣 | product_商家折扣 | - | orders | ❌ | string |
| `product_discount_shopee` | Shopee产品折扣 | product_shopee折扣 | - | orders | ❌ | string |
| `product_id` | 产品ID | product_id | - | orders | ❌ | string |
| `product_ma_lai_xi_ya_di_jia_zhi_shui_lvg` | 马来西亚低价值商品税（lvg） | product_马来西亚低价值税（lvg） | - | orders | ❌ | string |
| `product_original_price` | 产品原价 | product_原价 | - | orders | ❌ | string |
| `product_platform_title` | 平台产品标题 | product_platform_标题 | - | orders | ❌ | string |
| `product_quantity` | 产品数量 | product_quantity | - | orders | ❌ | string |
| `product_sku` | 商品SKU | product_sku | - | orders | ❌ | string |
| `product_tui_huo_tui_kuan_an_bi_li_de_shopee_you_hui_quan_di_xiao` | 退货/退款商品按比例的Shopee优惠券抵消 | product_退货/退款按比例的shopee优惠券抵消 | - | orders | ❌ | string |
| `product_tui_huo_tui_kuan_an_bi_li_yin_hang_fu_kuan_qu_dao_di_xiao` | 退货/退款商品按比例银行付款渠道抵消 | product_退货/退款按比例银行付款渠道抵消 | - | orders | ❌ | string |
| `product_tui_huo_tui_kuan_de_an_bi_li_shopee_zhi_fu_qu_dao_cu_xiao` | 退货/退款的按比例Shopee支付渠道商品促销 | product_退货/退款的按比例shopee支付渠道促销 | - | orders | ❌ | string |
| `product_tui_huo_tui_kuan_de_shopee_bi_di_xiao` | 退货/退款商品的Shopee币抵消 | product_退货/退款的shopee币抵消 | - | orders | ❌ | string |
| `product_type` | 商品类型 | product_type | - | orders | ❌ | string |
| `product_xin_jia_po_zeng_zhi_shui_gst` | 新加坡商品增值税（gst） | product_新加坡增值税（gst） | - | orders | ❌ | string |
| `profit` | 利润 | 利润 | - | orders | ❌ | string |
| `profit_shu_ju` | 利润数据 | 利润数据 | - | orders | ❌ | string |
| `purchase_cost` | 采购成本 | 采购成本 | - | orders | ❌ | string |
| `purchase_time` | 采购时间 | time_采购 | - | orders | ❌ | string |
| `refund_amount` | 退款金额 | amount_退款 | - | orders | ❌ | string |
| `refund_amount_discount_shang_jia` | 商家折扣退款金额 | amount_商家折扣退款 | - | orders | ❌ | string |
| `sales_profit_rate` | 销售利润率 | 销售利润率 | - | orders | ❌ | string |
| `sales_quantity` | 销售数量 | quantity_销售 | - | orders | ❌ | string |
| `service_fee` | 服务费 | 服务费 | - | orders | ❌ | string |
| `service_fee_bonus_jin_bi_fan_xian` | Bonus金币返现服务费 | bonus金币返现服务费 | - | orders | ❌ | string |
| `service_fee_cu_xiao_huo_dong` | 促销活动服务费 | 促销活动服务费 | - | orders | ❌ | string |
| `service_fee_fbt_cang_chu` | FBT仓储服务费 | fbt仓储服务费 | - | orders | ❌ | string |
| `service_fee_live_specials_ji_hua` | LIVE Specials 计划服务费 | live_specials_计划服务费 | - | orders | ❌ | string |
| `service_fee_sfp` | SFP服务费 | sfp服务费 | - | orders | ❌ | string |
| `service_fee_tiktok_shop_mall` | TikTok Shop Mall服务费 | tiktok_shop_mall服务费 | - | orders | ❌ | string |
| `service_fee_voucher_xtra_ji_hua` | Voucher xtra 计划服务费 | voucher_xtra_计划服务费 | - | orders | ❌ | string |
| `service_fee_wu_liu_gong_ying_shang_qing_guan` | 物流供应商清关服务费 | 物流供应商清关服务费 | - | orders | ❌ | string |
| `service_fee_wu_liu_hai_wai_mian_tui` | 物流+:海外免退服务费 | 物流+:海外免退服务费 | - | orders | ❌ | string |
| `service_fee_xian_shi_qiang_gou` | 限时抢购服务费 | 限时抢购服务费 | - | orders | ❌ | string |
| `service_fee_yu_gou_ji_hua` | 预购计划服务费 | 预购计划服务费 | - | orders | ❌ | string |
| `settlement_time` | 结算时间 | time_结算 | - | orders | ❌ | string |
| `shang_jia_ti_yan_kou_kuan` | 商家体验扣款 | 商家体验扣款 | - | orders | ❌ | string |
| `ship_time` | 发货时间 | time_发货 | - | orders | ❌ | string |
| `shipping_adjustment` | 运费调整 | 运费调整 | - | orders | ❌ | string |
| `shipping_compensation` | 运费补偿 | 运费补偿 | - | orders | ❌ | string |
| `shipping_cost` | 运费成本 | 运费成本 | - | orders | ❌ | string |
| `shipping_discount_3pl` | 3pl运费折扣 | 3pl运费折扣 | - | orders | ❌ | string |
| `shipping_discount_mai_jia` | 卖家运费折扣 | 卖家运费折扣 | - | orders | ❌ | string |
| `shipping_discount_platform_code` | 平台运费折扣 | platform_运费折扣 | - | orders | ❌ | string |
| `shipping_discount_shang_jia` | 商家运费折扣 | 商家运费折扣 | - | orders | ❌ | string |
| `shipping_discount_tiktok_shop` | TikTok Shop 运费折扣 | tiktok_shop_运费折扣 | - | orders | ❌ | string |
| `shipping_fee_ke_hu_shi_fu` | 客户实付运费 | 客户实付运费 | - | orders | ❌ | string |
| `shipping_fee_ma_lai_xi_ya_zeng_zhi_shui_sst` | 马来西亚运费增值税（sst） | 马来西亚运费增值税（sst） | - | orders | ❌ | string |
| `shipping_fee_mai_jia_zhi_fu` | 买家支付运费 | 买家支付运费 | - | orders | ❌ | string |
| `shipping_fee_shang_jia` | 商家运费 | 商家运费 | - | orders | ❌ | string |
| `shipping_fee_shi_ji_ni_xiang_wu_liu` | 实际逆向物流运费 | 实际逆向物流运费 | - | orders | ❌ | string |
| `shipping_fee_tui_huo` | 退货运费 | 退货运费 | - | orders | ❌ | string |
| `shipping_fee_xin_jia_po_zeng_zhi_shui_gst` | 新加坡运费增值税（gst） | 新加坡运费增值税（gst） | - | orders | ❌ | string |
| `shipping_fee_yang_pin` | 样品运费 | 样品运费 | - | orders | ❌ | string |
| `shipping_rebate` | 运费回扣 | 运费回扣 | - | orders | ❌ | string |
| `shipping_subsidy_huo_dong` | 活动运费补贴 | 活动运费补贴 | - | orders | ❌ | string |
| `shipping_subsidy_platform_code` | 平台运费补贴 | platform_运费补贴 | - | orders | ❌ | string |
| `shipping_subsidy_xia_pi` | 虾皮运费补贴 | 虾皮运费补贴 | - | orders | ❌ | string |
| `shopee_bi_di_kou` | Shopee币抵扣 | shopee币抵扣 | - | orders | ❌ | string |
| `site` | 站点 | 站点 | - | orders | ❌ | string |
| `specification` | 规格 | 规格 | - | orders | ❌ | string |
| `tui_kuan_guan_li_fei` | 退款管理费 | 退款管理费 | - | orders | ❌ | string |
| `xin_yong_ka_fu_kuan_shou_xu_fei` | 信用卡付款手续费 | 信用卡付款手续费 | - | orders | ❌ | string |
| `yu_kou_shui` | 预扣税 | 预扣税 | - | orders | ❌ | string |
| `yun_shu_bao_xian_fei` | 运输保险费 | 运输保险费 | - | orders | ❌ | string |
| `zeng_zhi_shui_vat` | 增值税(VAT) | 增值税(vat) | - | orders | ❌ | string |
| `zong_fei_yong` | 总费用 | 总费用 | - | orders | ❌ | string |
| `zong_shou_ru` | 总收入 | 总收入 | - | orders | ❌ | string |

---

## 📦 产品域 (products) - 97个字段

| 字段代码 (field_code) | 中文名称 (cn_name) | 英文名称 (en_name) | 同义词 (synonyms) | 数据域 | 是否必填 | 数据类型 |
|:---|:---|:---|:---|:---|:---|:---|
### 金额字段 (1个)

| `price` | 价格 |  | - | products | ❌ | float |
### 其他字段 (94个)

| `c68_c84_1` | *规格 | *规格 | - | products | ❌ | string |
| `cang_ku` | 仓库 | 仓库 | - | products | ❌ | string |
| `cang_wei_1` | 仓位1 | 仓位1 | - | products | ❌ | string |
| `chuang_jian_ren_yuan` | 创建人员 | 创建人员 | - | products | ❌ | string |
| `click_rate_product_ka_pian` | 商品卡片点击率 | product_卡片点击率 | - | products | ❌ | string |
| `click_rate_shang_cheng` | 商城点击率 | 商城点击率 | - | products | ❌ | string |
| `click_rate_shi_pin` | 视频点击率 | 视频点击率 | - | products | ❌ | string |
| `click_rate_zhi_bo` | 直播点击率 | 直播点击率 | - | products | ❌ | string |
| `conversion_rate_jia_ru_gou_wu_che_lv` | 转化率 (加入购物车率) | conversion_rate_(加入购物车率) | - | products | ❌ | string |
| `conversion_rate_order_yi_fu_kuan` | 转化率（已付款订单） | order_conversion_rate_（已付款） | - | products | ❌ | string |
| `conversion_rate_order_yi_xia` | 转化率（已下订单） | order_conversion_rate_（已下） | - | products | ❌ | string |
| `conversion_rate_product_ka_pian` | 商品卡片转化率 | product_conversion_rate_卡片 | - | products | ❌ | string |
| `conversion_rate_shang_cheng` | 商城转化率 | conversion_rate_商城 | - | products | ❌ | string |
| `conversion_rate_shi_pin` | 视频转化率 | conversion_rate_视频 | - | products | ❌ | string |
| `conversion_rate_zhi_bo` | 直播转化率 | conversion_rate_直播 | - | products | ❌ | string |
| `current_item_status` | Current Item Status | current_item_status | - | products | ❌ | string |
| `current_variation_status` | Current Variation Status | current_variation_status | - | products | ❌ | string |
| `dan_jia_yuan` | *单价
（元） | *单价
（元） | - | products | ❌ | string |
| `geng_xin_ren_yuan` | 更新人员 | 更新人员 | - | products | ❌ | string |
| `impressions_product_ka_pian` | 商品卡片曝光次数 | product_卡片曝光次数 | - | products | ❌ | string |
| `impressions_shang_cheng_fa_pin` | 商城发品曝光次数 | 商城发品曝光次数 | - | products | ❌ | string |
| `impressions_shi_pin` | 视频曝光次数 | 视频曝光次数 | - | products | ❌ | string |
| `impressions_zhi_bo` | 直播曝光次数 | 直播曝光次数 | - | products | ❌ | string |
| `jin_30_tian_xiao_liang_shu_ju` | 近30天销量数据 | 近30天销量数据 | - | products | ❌ | string |
| `jin_60_tian_xiao_liang_shu_ju` | 近60天销量数据 | 近60天销量数据 | - | products | ❌ | string |
| `jin_7_tian_xiao_liang_shu_ju` | 近7天销量数据 | 近7天销量数据 | - | products | ❌ | string |
| `jin_90_tian_xiao_liang_shu_ju` | 近90天销量数据 | 近90天销量数据 | - | products | ❌ | string |
| `lai_zi_shi_pin_de_qu_zhong_ye_mian_liu_lan_ci_shu` | 来自视频的去重页面浏览次数 | 来自视频的去重页面浏览次数 | - | products | ❌ | string |
| `lai_zi_shi_pin_de_ye_mian_liu_lan_ci_shu` | 来自视频的页面浏览次数 | 来自视频的页面浏览次数 | - | products | ❌ | string |
| `order_c68` | 订单数 | order_数 | - | products | ❌ | string |
| `order_fu_gou_de_ping_jun_tian_shu_yi_fu_kuan` | 订单复购的平均天数（已付款订单） | order_复购的平均天数（已付款） | - | products | ❌ | string |
| `order_fu_gou_lv_yi_fu_kuan` | 订单复购率（已付款订单） | order_复购率（已付款） | - | products | ❌ | string |
| `order_mai_jia_shu_yi_fu_kuan` | 买家数（已付款订单） | order_买家数（已付款） | - | products | ❌ | string |
| `order_mai_jia_shu_yi_xia` | 买家数（已下订单） | order_买家数（已下） | - | products | ❌ | string |
| `order_piece_count_yi_fu_kuan` | 件数（已付款订单） | order_件数（已付款） | - | products | ❌ | string |
| `order_piece_count_yi_xia` | 件数（已下订单） | order_件数（已下） | - | products | ❌ | string |
| `order_time_utc_chuang_jian` | 创建时间 | time_创建 | - | products | ❌ | string |
| `order_time_utc_geng_xin` | 更新时间 | time_更新 | - | products | ❌ | string |
| `order_xiao_shou_e_yi_fu_kuan_brl` | 销售额（已付款订单） (BRL) | order_销售额（已付款）_(brl) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_fu_kuan_cny` | 销售额（已付款订单） (CNY) | order_销售额（已付款）_(cny) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_fu_kuan_cop` | 销售额（已付款订单） (COP) | order_销售额（已付款）_(cop) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_fu_kuan_sgd` | 销售额（已付款订单） (SGD) | order_销售额（已付款）_(sgd) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_xia_brl` | 销售额（已下订单） (BRL) | order_销售额（已下）_(brl) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_xia_cny` | 销售额（已下订单） (CNY) | order_销售额（已下）_(cny) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_xia_cop` | 销售额（已下订单） (COP) | order_销售额（已下）_(cop) | - | products | ❌ | string |
| `order_xiao_shou_e_yi_xia_sgd` | 销售额（已下订单） (SGD) | order_销售额（已下）_(sgd) | - | products | ❌ | string |
| `piece_count_jia_ru_gou_wu_che` | 件数 (加入购物车） | 件数_(加入购物车） | - | products | ❌ | string |
| `product` | 商品 | product | - | products | ❌ | string |
| `product_bian_hao` | 商品编号 | product_编号 | - | products | ❌ | string |
| `product_bounce_rate` | 商品跳出率 | product_bounce_rate | - | products | ❌ | string |
| `product_c17_c16` | *商品名称 | product_*名称 | - | products | ❌ | string |
| `product_fen_zu` | 商品分组 | product_分组 | - | products | ❌ | string |
| `product_jiao_yi_zong_e` | 商品交易总额 | product_交易总额 | - | products | ❌ | string |
| `product_ka_pian_de_qu_zhong_ye_mian_liu_lan_ci_shu` | 商品卡片的去重页面浏览次数 | product_卡片的去重页面浏览次数 | - | products | ❌ | string |
| `product_ka_pian_de_ye_mian_liu_lan_ci_shu` | 商品卡片的页面浏览次数 | product_卡片的页面浏览次数 | - | products | ❌ | string |
| `product_ka_pian_jiao_yi_zong_e` | 商品卡片商品交易总额 | product_卡片交易总额 | - | products | ❌ | string |
| `product_ka_pian_qu_zhong_ke_hu_shu` | 商品卡片去重客户数 | product_卡片去重客户数 | - | products | ❌ | string |
| `product_quan_qiu_huo_hao` | 全球商品货号 | product_全球货号 | - | products | ❌ | string |
| `product_shang_cheng_jiao_yi_zong_e` | 商城商品交易总额 | product_商城交易总额 | - | products | ❌ | string |
| `product_shang_cheng_qu_zhong_ke_hu_shu` | 商城去重商品客户数 | product_商城去重客户数 | - | products | ❌ | string |
| `product_shi_pin_jiao_yi_zong_e` | 视频商品交易总额 | product_视频交易总额 | - | products | ❌ | string |
| `product_shi_pin_qu_zhong_ke_hu_shu` | 视频去重商品客户数 | product_视频去重客户数 | - | products | ❌ | string |
| `product_sku_1` | *商品SKU | product_sku_* | - | products | ❌ | string |
| `product_tu_pian` | 商品图片 | product_图片 | - | products | ❌ | string |
| `product_visitors_c27` | 商品访客数量 | product_visitors_量 | - | products | ❌ | string |
| `product_ye_mian_fang_wen_liang` | 商品页面访问量 | product_页面访问量 | - | products | ❌ | string |
| `product_zhi_bo_jiao_yi_zong_e` | 直播商品交易总额 | product_直播交易总额 | - | products | ❌ | string |
| `product_zhi_bo_qu_zhong_ke_hu_shu` | 直播去重商品客户数 | product_直播去重客户数 | - | products | ❌ | string |
| `shang_cheng_qu_zhong_ye_mian_liu_lan_ci_shu` | 商城去重页面浏览次数 | 商城去重页面浏览次数 | - | products | ❌ | string |
| `shang_cheng_ye_mian_liu_lan_ci_shu` | 商城页面浏览次数 | 商城页面浏览次数 | - | products | ❌ | string |
| `sou_suo_dian_ji_ren_shu` | 搜索点击人数 | 搜索点击人数 | - | products | ❌ | string |
| `spec_code` | 规格编号 | 规格编号 | - | products | ❌ | string |
| `spec_name` | 规格名称 | 规格名称 | - | products | ❌ | string |
| `spec_sku` | 规格货号 | 规格货号 | - | products | ❌ | string |
| `status` | 状态 | status | - | products | ❌ | string |
| `stock_an_quan` | 安全库存 | stock_安全 | - | products | ❌ | string |
| `stock_huo_dong_yu_liu` | 活动预留库存 | stock_活动预留 | - | products | ❌ | string |
| `stock_ji_hua` | 计划库存 | stock_计划 | - | products | ❌ | string |
| `stock_ke_yong` | 可用库存 | stock_可用 | - | products | ❌ | string |
| `stock_quantity_ke_yong_yu_zhan` | 库存数量
可用库存
预占库存 | stock_quantity_可用
预占 | - | products | ❌ | string |
| `stock_yu_zhan` | 预占库存 | stock_预占 | - | products | ❌ | string |
| `stock_zai_tu` | 在途库存 | stock_在途 | - | products | ❌ | string |
| `stock_zong_liang` | 库存总量 | stock_总量 | - | products | ❌ | string |
| `transaction_count` | 成交件数 | 成交件数 | - | products | ❌ | string |
| `transaction_count_product_ka_pian` | 商品卡片商品成交件数 | product_卡片成交件数 | - | products | ❌ | string |
| `transaction_count_product_shang_cheng` | 商城商品成交件数 | product_商城成交件数 | - | products | ❌ | string |
| `transaction_count_product_shi_pin` | 视频商品成交件数 | product_视频成交件数 | - | products | ❌ | string |
| `transaction_count_product_zhi_bo` | 直播商品成交件数 | product_直播成交件数 | - | products | ❌ | string |
| `visitors_product_jia_ru_gou_wu_che` | 商品访客数 (加入购物车) | product_visitors_(加入购物车) | - | products | ❌ | string |
| `visitors_product_tiao_chu_ye_mian_de` | 跳出商品页面的访客数 | product_visitors_跳出页面的 | - | products | ❌ | string |
| `zan` | 赞 | 赞 | - | products | ❌ | string |
| `zhi_bo_de_qu_zhong_ye_mian_liu_lan_ci_shu` | 直播的去重页面浏览次数 | 直播的去重页面浏览次数 | - | products | ❌ | string |
| `zhi_bo_de_ye_mian_liu_lan_ci_shu` | 直播的页面浏览次数 | 直播的页面浏览次数 | - | products | ❌ | string |
| `zong_jia_yuan` | *总价
（元） | *总价
（元） | - | products | ❌ | string |

---

## 📦 流量域 (traffic) - 23个字段

| 字段代码 (field_code) | 中文名称 (cn_name) | 英文名称 (en_name) | 同义词 (synonyms) | 数据域 | 是否必填 | 数据类型 |
|:---|:---|:---|:---|:---|:---|:---|
### 其他字段 (20个)

| `amount_c64_c54_1` | 退款金额 (₱) | amount_退款_(₱) | - | traffic | ❌ | string |
| `avg_conversion_rate` | 平均转化率 | conversion_rate_平均 | - | traffic | ❌ | string |
| `avg_page_views` | 平均页面访问数 | avg_page_views | - | traffic | ❌ | string |
| `avg_visitors` | 平均访客数 | visitors_平均 | - | traffic | ❌ | string |
| `ke_hu_shu` | 客户数 | 客户数 | - | traffic | ❌ | string |
| `order_sku_c68` | SKU 订单数 | order_sku_数 | - | traffic | ❌ | string |
| `product_c32_c31_c35_c69_1` | 商品交易总额 (₱) | product_交易总额_(₱) | - | traffic | ❌ | string |
| `product_jiao_yi_zong_e_rm` | 商品交易总额 (RM) | product_交易总额_(rm) | - | traffic | ❌ | string |
| `product_jiao_yi_zong_e_s` | 商品交易总额 (S$) | product_交易总额_(s$) | - | traffic | ❌ | string |
| `product_platform_code_subsidy_zong_cheng_jiao_e_han_ming_xi` | 总成交额（含平台商品补贴）明细 | product_platform_总成交额（含补贴）明细 | - | traffic | ❌ | string |
| `refund_amount_rm` | 退款金额 (RM) | amount_退款_(rm) | - | traffic | ❌ | string |
| `refund_amount_s` | 退款金额 (S$) | amount_退款_(s$) | - | traffic | ❌ | string |
| `ri_ping_jun_ke_hu_shu` | 日平均客户数 | 日平均客户数 | - | traffic | ❌ | string |
| `shop_id_ye_mian_fang_wen_liang` | 店铺页面访问量 | shop_页面访问量 | - | traffic | ❌ | string |
| `shu_ju_hui_zong` | 数据汇总 | 数据汇总 | - | traffic | ❌ | string |
| `transaction_count_product` | 商品成交件数 | product_成交件数 | - | traffic | ❌ | string |
| `visitors_xian_you` | 现有访客 | visitors_现有 | - | traffic | ❌ | string |
| `xin_guan_zhu_zhe` | 新关注者 | 新关注者 | - | traffic | ❌ | string |
| `ye_mian_liu_lan_ci_shu` | 页面浏览次数 | 页面浏览次数 | - | traffic | ❌ | string |
| `ye_mian_liu_lan_shu` | 页面浏览数 | 页面浏览数 | - | traffic | ❌ | string |

---

## 📦 服务域 (services) - 40个字段

| 字段代码 (field_code) | 中文名称 (cn_name) | 英文名称 (en_name) | 同义词 (synonyms) | 数据域 | 是否必填 | 数据类型 |
|:---|:---|:---|:---|:---|:---|:---|
### 金额字段 (1个)

| `amount` | 金额 |  | - | services | ✅ 必填 | float |
### 其他字段 (38个)

| `12_xiao_shi_ren_gong_ke_fu_xiang_ying_liao_tian_shu` | 12 小时人工客服响应聊天数 | 12_小时人工客服响应聊天数 | - | services | ❌ | string |
| `12_xiao_shi_ren_gong_ke_fu_xiang_ying_lv` | 12 小时人工客服响应率 | 12_小时人工客服响应率 | - | services | ❌ | string |
| `avg_service_visitors` | 平均服务的访客人数 | visitors_平均服务的人数 | - | services | ❌ | string |
| `bei_fen_pei_hui_hua_shu` | 被分配会话数 | 被分配会话数 | - | services | ❌ | string |
| `cha_ping` | 差评 | 差评 | - | services | ❌ | string |
| `chao_shi_xiang_ying_hui_hua_shu` | 超时响应会话数 | 超时响应会话数 | - | services | ❌ | string |
| `conversion_rate_hui_fu_zhi_xia_dan` | 转化率（回复至下单） | conversion_rate_（回复至下单） | - | services | ❌ | string |
| `conversion_rate_xun_wen_zhi_hui_fu` | 转化率（询问至回复） | conversion_rate_（询问至回复） | - | services | ❌ | string |
| `date` | 日期 | date | - | services | ❌ | string |
| `hao_ping` | 好评 | 好评 | - | services | ❌ | string |
| `hao_ping_bi_li` | 好评比例 | 好评比例 | - | services | ❌ | string |
| `hui_da_wen_ti_lv` | 回答问题率 | 回答问题率 | - | services | ❌ | string |
| `ke_fu_id` | 客服ID | 客服id | - | services | ❌ | string |
| `ke_fu_ni_cheng` | 客服昵称 | 客服昵称 | - | services | ❌ | string |
| `liao_tian_xun_wen` | 聊天询问 | 聊天询问 | - | services | ❌ | string |
| `mai_jia_shu` | 买家数 | 买家数 | - | services | ❌ | string |
| `man_yi_du` | 满意度 | 满意度 | - | services | ❌ | string |
| `order` | 订单 | order | - | services | ❌ | string |
| `order_time_utc_xiang_deng_yu_mai_jia_gong_zuo` | 相等于卖家工作时间 | time_相等于卖家工作 | - | services | ❌ | string |
| `piece_count` | 件数 | 件数 | - | services | ❌ | string |
| `ping_jun_hui_ying_su_du` | 平均回应速度 | 平均回应速度 | - | services | ❌ | string |
| `ping_jun_ping_jia` | 平均评价 | 平均评价 | - | services | ❌ | string |
| `ping_jun_xiang_ying_shi_chang` | 平均响应时长 | 平均响应时长 | - | services | ❌ | string |
| `shou_ci_hui_ying_su_du` | 首次回应速度 | 首次回应速度 | - | services | ❌ | string |
| `visitors_fu_wu_de` | 服务的访客 | visitors_服务的 | - | services | ❌ | string |
| `visitors_tong_shi_fu_wu_de` | 同时服务的访客数 | visitors_同时服务的 | - | services | ❌ | string |
| `visitors_xun_wen` | 访客询问 | visitors_询问 | - | services | ❌ | string |
| `wei_hui_fu_de_liao_tian` | 未回复的聊天 | 未回复的聊天 | - | services | ❌ | string |
| `wei_xiang_ying_hui_hua_shu` | 未响应会话数 | 未响应会话数 | - | services | ❌ | string |
| `xiao_shou_brl` | 销售 (BRL) | 销售_(brl) | - | services | ❌ | string |
| `xiao_shou_cop` | 销售 (COP) | 销售_(cop) | - | services | ❌ | string |
| `xiao_shou_sgd` | 销售 (SGD) | 销售_(sgd) | - | services | ❌ | string |
| `xu_yao_ren_gong_xiang_ying_hui_hua_shu` | 需要人工响应会话数 | 需要人工响应会话数 | - | services | ❌ | string |
| `xun_wen_lv` | 询问率 | 询问率 | - | services | ❌ | string |
| `yi_hui_da_de_wen_ti` | 已回答的问题 | 已回答的问题 | - | services | ❌ | string |
| `yi_hui_fu_de_liao_tian` | 已回复的聊天 | 已回复的聊天 | - | services | ❌ | string |
| `yong_hu_man_yi_du` | 用户满意度% | 用户满意度% | - | services | ❌ | string |
| `zhuan_jiao_gei_mai_jia_de_wen_ti` | 转交给卖家的问题 | 转交给卖家的问题 | - | services | ❌ | string |

---

## 📦 通用域 (general) - 4个字段

| 字段代码 (field_code) | 中文名称 (cn_name) | 英文名称 (en_name) | 同义词 (synonyms) | 数据域 | 是否必填 | 数据类型 |
|:---|:---|:---|:---|:---|:---|:---|
| `start_time` | 开始时间 | Start Time | 开始时间, 起始时间, 开始, start_time, start ... (+1个) | general | ❌ | datetime |
| `end_time` | 结束时间 | End Time | 结束时间, 终止时间, 结束, end_time, end ... (+1个) | general | ❌ | datetime |
| `datetime` | 日期时间 | Date Time | 日期时间, 时间, 时间戳, datetime, timestamp ... (+1个) | general | ❌ | datetime |
| `time_range` | 时间范围 | Time Range | 时间范围, 日期范围, 期间, 时间段, 时间区间 ... (+5个) | general | ❌ | string |

---

## 📦 analytics - 4个字段

| 字段代码 | 中文名称 | 英文名称 | 同义词 | 数据域 | 是否必填 |
|:---|:---|:---|:---|:---|:---|
| `metric_date` | 日期 |  | - | analytics | ✅ 必填 |
| `conversion_rate` | 转化率 |  | - | analytics | ❌ |
| `page_views` | 浏览量 |  | - | analytics | ❌ |
| `unique_visitors` | 访客数 |  | - | analytics | ❌ |

---

## 🔍 常见映射问题检查建议

### 1. 检查字段名称是否准确

**示例问题**：
- ❌ `平台SKU` 被映射到 `平台`（不正确）
- ✅ `平台SKU` 应该映射到 `platform_sku` 或 `产品SKU`

**检查方法**：
1. 查找原始字段中的关键词（如`SKU`、`产品`）
2. 在同义词列中查找匹配项
3. 确认映射到正确的字段代码

### 2. 检查同义词是否完整

**示例问题**：
- 如果`平台SKU`没有被正确映射，检查`platform_sku`字段的同义词是否包含`平台SKU`

**检查方法**：
1. 扫描原始字段中的常见名称
2. 检查标准字段的同义词是否覆盖这些名称
3. 如果不完整，需要更新辞典的同义词

### 3. 检查数据域是否正确

**示例问题**：
- `订单金额`字段应该在`orders`域，而不是`products`域

**检查方法**：
1. 确认字段的业务含义
2. 检查数据域是否正确分类

---

**最后更新**: 2025-10-30 17:32:48
