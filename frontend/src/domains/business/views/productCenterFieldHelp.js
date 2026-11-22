/**
 * 商品中心 · 字段口径说明注册表。
 *
 * 为什么单独放一个模块：
 *   1) 口径说明是**字段级**的（这个数怎么算、为什么这么算、是不是实测值），
 *      写在表格行模板里会**每行重复一遍** ⇒ 表格被撑爆。
 *      现在统一收进表头的小问号，悬浮即看，说明只说一次。
 *   2) ProductCenter.vue 已经 4000+ 行，把说明文案抽出去后文件明显瘦身，
 *      并且文案可以被单独测试（见 frontend/scripts/productCenterFieldHelp.test.mjs）。
 *
 * 结构对齐「业务概览」的 businessOverviewKpiMeta.js：
 *   definition   → 指标含义：这个数是什么
 *   formulaText  → 计算口径：怎么算出来的
 *   businessValue→ 业务作用：看了能干什么
 *   caution      → 口径状态：能不能直接拿去做经营判断
 *
 * 占位符：文案里可以用 {platform} / {warehouse}，由 getFieldHelp(key, params) 填充。
 */

/** 口径状态：决定小问号面板右上角的状态标签 */
export const FIELD_HELP_STATUS = {
  /** 口径稳定，可直接用于经营判断 */
  stable: 'stable',
  /** 口径有已知限制，能看但要小心 */
  observe: 'observe',
  /** 人工维护的值，不是实测值 */
  manual: 'manual'
}

/** 注册表里各字段对应到面板哪一行 */
export const HELP_SECTION_FIELDS = [
  ['definition', '指标含义'],
  ['formulaText', '计算口径'],
  ['businessValue', '业务作用'],
  ['caution', '口径状态']
]

export const productCenterFieldHelp = {
  // --- SPU 管理 --------------------------------------------------------
  'spu.logistics_damage_rate': {
    title: '运输货损率',
    definition:
      '行业基准件损率：这个款在行业主流数据下，发 100 件里坏几件。',
    formulaText:
      '现在按件折进成本（每件按件成本 × (1 + 退货率 + 货损率)），不是按收入比例扣。',
    businessValue:
      '货损是卖一件就真金白银亏一件的成本，折进成本比按收入扣更接近实际漏钱。',
    status: FIELD_HELP_STATUS.manual,
    caution: '人工维护，当前无实测校准。',
    sourceRefs: ['spu-two-rates-batch-9']
  },
  'spu.return_loss_rate': {
    title: '退货损失率',
    definition:
      '行业基准件损率：这个款在行业主流数据下，发 100 件里退几件。',
    formulaText:
      '现在按件折进成本（每件按件成本 × (1 + 退货率 + 货损率)），不是按收入比例扣。',
    businessValue:
      '退货是纯亏：货发出去又退回来，运费还搭进去，折进成本才不会被低估。',
    status: FIELD_HELP_STATUS.manual,
    caution: '人工维护，当前无实测校准。',
    sourceRefs: ['spu-two-rates-batch-9']
  },

  // --- SKU 资料 --------------------------------------------------------
  'sku.spu_binding': {
    title: '所属 SPU（归属关系）',
    definition:
      '这个 SKU 当前挂在哪个款下面。SPU 归属不是货身上的一个字段，是一段有时效的关联。',
    formulaText:
      '换款不改写历史：旧归属被归档，新归属从保存当日起算；候选只给还能挂货的款（已淘汰 / 已删除的款选不到）。',
    businessValue:
      '归属决定这个货按哪个款算成本（运输货损率、退货损失率等），换款等于换成本基准。',
    status: FIELD_HELP_STATUS.stable,
    caution:
      '不支持解绑（清空不会生效）；存量行默认只读，点「换款」才展开编辑。',
    sourceRefs: ['product-center-binding-write-path']
  },
  'sku.min_selling_price': {
    title: '最低售价',
    definition:
      '这一件至少要卖多少钱才不亏（底线），按平台分别算。',
    formulaText:
      '底线按 {platform} 的成本率计算：平台佣金率、平台其他成本率、达人佣金率一起进分母。',
    businessValue:
      '低于底线就是在亏；人工覆盖按平台生效，各平台底线互相独立。',
    status: FIELD_HELP_STATUS.stable,
    caution: '底线按 {platform} 的成本率计算，不同平台成本率不同、底线也不同。',
    sourceRefs: ['sku-cost-floor']
  },
  'sku.creator_commission_rate': {
    title: '达人佣金率',
    definition: '达人带货这一单的佣金比例。',
    formulaText: '留空表示不单独设置，按平台默认计算。',
    businessValue: '达人单的利润比自然流量单薄，佣金率直接进成本底线。',
    status: FIELD_HELP_STATUS.stable,
    caution: '留空 = 用平台默认值（可在「平台成本率」里改）。',
    sourceRefs: ['sku-creator-commission']
  },
  'sku.selling_price_age_days': {
    title: '售价账龄',
    definition: '基准售价距今多少天没有重新确认。',
    formulaText: '账龄 = 今天 − 基准售价确认日期。',
    businessValue: '账龄越久，纪律线用的价格越可能已经失真。',
    status: FIELD_HELP_STATUS.stable,
    caution: '过期或从未确认的行会直接标黄 / 标红，不要按旧价硬投。',
    sourceRefs: ['sku-selling-price-age']
  },

  // --- 平台 SKU 利润测算 ------------------------------------------------
  'operating.free_shipping': {
    title: '包邮',
    definition:
      '这个 SKU 在这个平台包不包邮，是经营选择（粒度 = SKU × 平台，不是仓库属性）。',
    formulaText:
      '开 ⇒ 尾程由我们承担，计入成本底线与利润；关 ⇒ 买家付尾程运费，商家不承担，尾程不进底线、利润按 0 计（不是算不出来）。',
    businessValue:
      '跨境电商不是默认包邮而是选择性包邮，这一个开关直接决定尾程进不进成本底线。',
    status: FIELD_HELP_STATUS.stable,
    caution: '开关一改，尾程口径立刻变，不是渐进生效。',
    sourceRefs: ['sku-free-shipping-batch-6']
  },
  'operating.min_selling_price': {
    title: '最低售价',
    definition: '按平台成本率算出来的最低售价（底线）。',
    formulaText: '按 {platform} 平台成本率计算，不同平台底线不同。',
    businessValue:
      '测算售价低于这个数就会亏，保存利润版本时会被拦下来。',
    status: FIELD_HELP_STATUS.stable,
    caution:
      '库龄档位决定用哪一档让利率；缺库龄天数时按兜底档计算（会标「兜底」）。',
    sourceRefs: ['operating-cost-floor']
  },
  'operating.warehouse_restock': {
    title: '库龄（仓）',
    definition: '当前选中的这个仓自己的库龄 —— 这个货在这个仓压了多久。',
    formulaText:
      '库龄（仓）= 该仓最后一次入库到今天的天数；下面另列其它仓的库龄，老的排前面。',
    businessValue:
      '库里压了多久决定用哪个库龄档位的让利率，同时也是成本底线的依据。',
    status: FIELD_HELP_STATUS.stable,
    caution:
      '页面上显示的库龄与底线依据的库龄是同一个数，两者不会打架。',
    sourceRefs: ['operating-warehouse-restock']
  },
  'operating.ad_contribution_margin_rate': {
    title: '广告前贡献毛利率',
    definition:
      '扣掉采购、头程、仓储、贴单、尾程、平台佣金、达人佣金、货损、退货后的占比。',
    formulaText: '分母是商家实收（= 测算售价），与平台 GMV 同一口径。',
    businessValue:
      '看投广告之前这单还剩多少利润，用来判断还有多少广告空间可以给。',
    status: FIELD_HELP_STATUS.stable,
    caution: '成本不全时这个值偏乐观（缺输入宁可不算不可乐观）。',
    sourceRefs: ['operating-margin-rate']
  },
  'operating.ad_rate': {
    title: '广告分成率',
    definition:
      '广告费用占广告前利润的比例，是「目标 ROI」之外的另一个口径。',
    formulaText:
      '广告费 = 广告前利润 × 分成率；与目标 ROI 口径数值等价（目标 ROI = 保本 ROI ÷ 分成率），切换不改变利润。',
    businessValue:
      '高级逃生口：主输入是「目标 ROI」，手填分成率默认折叠，要显式展开才改得了。',
    status: FIELD_HELP_STATUS.observe,
    caution:
      '两个口径只能留一个：动了哪个以哪个为准，另一个会被可见地清空。',
    sourceRefs: ['operating-ad-rate-escape']
  },
  'operating.actual_recost_completeness': {
    title: '混合成本完整度',
    definition: '这一版利润里有多少比例用了真实成本。',
    formulaText:
      'incomplete = 没算出来 / estimated = 全预估 / mixed = 一半真实 / actual = 全真实。',
    businessValue:
      '告诉运营这个利润数字有多可信：全预估的利润只能当参考，不能直接投。',
    status: FIELD_HELP_STATUS.stable,
    caution: '头程来自真实账单；仓储是规则预估（系统里没有仓储费账单）。',
    sourceRefs: ['operating-actual-recost']
  },

  // --- 平台成本率（抽屉表单）------------------------------------------
  'fee.platform': {
    title: '平台',
    definition: '平台成本率是每个平台一本账。',
    formulaText:
      '这里改哪个平台，就只影响哪个平台的最低售价底线（平台身份由抽屉自己决定，不依赖外部筛选条件）。',
    businessValue:
      '不同平台的佣金与成本结构不同，底线必须分平台算，不能混用。',
    status: FIELD_HELP_STATUS.stable,
    caution: '改错平台会静默写到别的平台行上，保存前请确认平台。',
    sourceRefs: ['platform-fee-drawer']
  },
  'fee.platform_fee_rate': {
    title: '平台佣金率',
    definition: '平台按成交额收取的佣金比例。',
    formulaText:
      '平台佣金率单独进分母，不含在「平台其他成本率」内。',
    businessValue:
      '直接决定底线：佣金率越高，同一件货能卖的最低价越高。',
    status: FIELD_HELP_STATUS.manual,
    caution: '人工维护，请以平台实际费率与合同为准。',
    sourceRefs: ['platform-fee-drawer']
  },
  'fee.default_creator_commission_rate': {
    title: '默认达人佣金率',
    definition: '达人带货的默认佣金比例。',
    formulaText: 'SKU 未单独设置达人佣金率时的兜底值。',
    businessValue:
      '默认值决定绝大多数 SKU 的达人成本；单个 SKU 单独设置只用于特殊款。',
    status: FIELD_HELP_STATUS.manual,
    caution: '人工维护。',
    sourceRefs: ['platform-fee-drawer']
  },
  'fee.other_cost_rate': {
    title: '平台其他成本率',
    definition: '平台侧按收入比例扣的其它款项（不含平台佣金、不含尾程）。',
    formulaText:
      '不含平台佣金、不含尾程（尾程按件进成本）。这里填平台侧按收入比例扣的其它款项（人工维护）。',
    businessValue: '与平台佣金率一起决定底线的分母。',
    status: FIELD_HELP_STATUS.manual,
    caution: '人工维护，不要把平台佣金或尾程重复填进来。',
    sourceRefs: ['platform-fee-drawer']
  },
  'fee.cost_rate_total': {
    title: '底线成本率合计',
    definition:
      '底线成本率合计 = 平台佣金率 + 平台其他成本率 + 默认达人佣金率（平台级，不含 SPU 两率）。',
    formulaText:
      '这三项都按收入比例扣 ⇒ 一起进底线的分母：1 − 平台佣金率 − 平台其他成本率 − 达人佣金率 − 目标利润率。',
    businessValue: '这是底线的分母构成，三项加得越低，底线越高。',
    status: FIELD_HELP_STATUS.stable,
    caution:
      '不含 SPU 的运输货损率与退货损失率（那两个是按件折进成本分子，不是按收入扣）。',
    sourceRefs: ['platform-fee-drawer']
  }
}

const PLACEHOLDER_PATTERN = /\{(\w+)\}/g

/**
 * 取一条字段说明。
 * @param {string} key 注册表里的键
 * @param {Object} params 占位符参数，例如 { platform: "TikTok", warehouse: "美西仓" }
 * @returns {Object|null} 填充好占位符的说明对象；键不存在时返回 null
 */
export function getFieldHelp(key, params = {}) {
  const meta = productCenterFieldHelp[key]
  if (!meta) return null
  const fill = (text) =>
    String(text ?? '').replace(PLACEHOLDER_PATTERN, (match, name) =>
      params[name] != null ? String(params[name]) : match
    )
  return {
    ...meta,
    definition: fill(meta.definition),
    formulaText: fill(meta.formulaText),
    businessValue: fill(meta.businessValue),
    caution: fill(meta.caution)
  }
}

/**
 * 把说明对象转成小问号面板的分区数组 [{ label, text }]。
 * @param {Object} meta getFieldHelp 的返回值
 * @returns {Array<{label: string, text: string}>}
 */
export function toHelpSections(meta) {
  if (!meta) return []
  return HELP_SECTION_FIELDS.map(([field, label]) => ({
    label,
    text: meta[field] || ''
  })).filter((item) => item.text)
}
