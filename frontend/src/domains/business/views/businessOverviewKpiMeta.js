export const KPI_HELP_STATUS = {
  stable: 'stable',
  observe: 'observe',
  blocked: 'blocked'
}

export const businessOverviewKpiMeta = [
  {
    key: 'gmv',
    title: 'GMV',
    definition: '统计所选周期内的成交规模，是判断整体销售体量的核心指标。',
    formulaText: '所选周期内的 GMV 汇总，当前统一按实付金额口径汇总。',
    businessValue: '适合先看大盘成交规模，再结合转化率和客单价判断增长来自哪里。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['metrics-dictionary', 'cost-data-sources'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'order_count',
    title: '订单数',
    definition: '统计所选周期内的有效订单笔数，用来判断成交密度。',
    formulaText: '所选周期内的有效订单数汇总。',
    businessValue: '适合和 GMV、客单价一起看，判断增长更多来自单量还是单价。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['metrics-dictionary', 'postgresql-dashboard-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'uv_conversion_rate',
    title: 'UV转化率',
    definition: '衡量访客最终下单的效率，是流量转订单的核心转化指标。',
    formulaText: '订单数 / 访客数 × 100%',
    businessValue: '适合判断流量质量、页面承接和商品吸引力是否足以促成下单。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['metrics-dictionary', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'avg_order_value',
    title: '客单价',
    definition: '衡量每笔订单平均贡献的成交金额，用来观察订单结构。',
    formulaText: 'GMV / 订单数',
    businessValue: '适合判断套餐、加价购和商品价格带是否带来更高单笔产出。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['metrics-dictionary', 'metric-status'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'impressions',
    title: '曝光量',
    definition: '统计商品或店铺在前台被展示的次数，用来判断流量入口规模。',
    formulaText: '所选周期内的曝光次数汇总。',
    businessValue: '适合先看流量入口是否足够，再和访问率一起判断曝光是否转成真实访问。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['postgresql-dashboard-runtime', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'page_views',
    title: '浏览量(PV)',
    definition: '统计页面被浏览的总次数，体现总浏览行为规模。',
    formulaText: '所选周期内的浏览量汇总。',
    businessValue: '适合和访客数、浏览深度一起看，判断用户是否愿意继续浏览更多内容。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['metrics-dictionary', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'visitor_count',
    title: '访客数(UV)',
    definition: '统计进入店铺或页面的访客人数，用来判断真实访问规模。',
    formulaText: '所选周期内的访客数汇总。',
    businessValue: '适合与曝光量、订单数联动看，判断流量入口质量和访问转化情况。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['metrics-dictionary', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'visit_rate',
    title: '访问率',
    definition: '衡量曝光最终转成访问的效率，用来观察流量入口质量。',
    formulaText: '访客数 / 曝光量 × 100%',
    businessValue: '适合判断主图、标题、价格带或投放入口是否能吸引用户点进来。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['postgresql-dashboard-runtime', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'browse_depth',
    title: '浏览深度',
    definition: '衡量单个访客平均浏览了多少次页面，用来观察浏览意愿。',
    formulaText: '浏览量 / 访客数',
    businessValue: '适合判断详情页承接、关联推荐和内容组织是否让用户继续浏览。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['postgresql-dashboard-runtime', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'pv_conversion_rate',
    title: 'PV转化率',
    definition: '衡量页面浏览最终转成下单的效率，是浏览到成交的转化指标。',
    formulaText: '订单数 / 浏览量 × 100%',
    businessValue: '适合判断页面浏览是否有效，能否进一步推进到下单。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['postgresql-dashboard-runtime', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'exposure_order_rate',
    title: '曝光成交率',
    definition: '衡量从曝光到最终成交的整体效率，反映完整漏斗的综合表现。',
    formulaText: '订单数 / 曝光量 × 100%',
    businessValue: '适合从全链路看投放、展示、承接和成交是否协同有效。',
    status: KPI_HELP_STATUS.stable,
    caution: '当前口径稳定，可直接用于经营复盘。',
    sourceRefs: ['postgresql-dashboard-runtime', 'shop-month-kpi-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'attach_rate',
    title: '连带率',
    definition: '衡量每笔订单平均带出多少件商品，用来观察单笔订单的带货件数。',
    formulaText: '商品件数 / 订单数',
    businessValue: '适合判断搭配销售、套餐策略和推荐位是否提升了每单购买件数。',
    status: KPI_HELP_STATUS.observe,
    caution: '当前属于观察口径，跨模块解释时需谨慎使用。',
    sourceRefs: ['metrics-dictionary', 'metric-status', 'postgresql-dashboard-runtime'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  },
  {
    key: 'labor_efficiency',
    title: '人效(当前)',
    definition: '理论上用于衡量每位纳入统计员工带来的成交产出。',
    formulaText: '理论口径：GMV / 在岗且纳入统计的员工数',
    businessValue: '适合从组织产出角度评估人均成交贡献，但前提是员工口径稳定可信。',
    status: KPI_HELP_STATUS.blocked,
    caution: '当前不建议用于经营判断；页面该值尚未形成稳定有效实现。',
    sourceRefs: ['metrics-dictionary', 'metric-status', 'labor-efficiency-design'],
    interactionNote: '桌面端悬停查看，移动端点击信息图标查看。'
  }
]

const metaMap = new Map(businessOverviewKpiMeta.map((item) => [item.key, item]))

export function getKpiHelpMeta(key) {
  return metaMap.get(key) ?? null
}
