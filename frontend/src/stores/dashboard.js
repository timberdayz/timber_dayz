/**
 * 数据看板状态管理 (Pinia Store)
 * 管理销售概览、趋势、利润等数据状态
 */

import { defineStore } from 'pinia'

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    // 总览数据
    overview: {
      data: {
        gmv: 0,
        gmvCny: 0,
        orderCount: 0,
        avgOrderValue: 0,
        totalProfit: 0,
        profitMargin: 0,
        totalOrders: 0,
        totalProducts: 0,
        totalCustomers: 0
      },
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 销售趋势
    salesTrend: {
      data: [],
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 利润分析
    profitAnalysis: {
      data: {
        grossProfit: 0,
        netProfit: 0,
        profitByPlatform: [],
        profitByShop: [],
        profitByProduct: []
      },
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 热销商品
    topProducts: {
      data: [],
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 平台对比
    platformComparison: {
      data: [],
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 订单统计
    orderStatistics: {
      data: {
        byStatus: [],
        byPaymentStatus: [],
        byDate: []
      },
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 转化漏斗
    conversionFunnel: {
      data: {
        visits: 0,
        pageViews: 0,
        cartAdds: 0,
        orders: 0,
        conversionRate: 0
      },
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 实时数据
    realtimeData: {
      data: {
        todayGmv: 0,
        todayOrders: 0,
        onlineVisitors: 0,
        lastOrderTime: null
      },
      loading: false,
      error: null,
      lastUpdate: null
    },

    // 全局筛选器
    filters: {
      startDate: null,
      endDate: null,
      platform: null,
      shopId: null,
      granularity: 'daily'  // daily/weekly/monthly
    },

    // 流量排名数据（v4.11.1新增）
    trafficRanking: {
      data: [],
      loading: false,
      error: null,
      lastUpdate: null
    }
  }),

  actions: {
    /**
     * 获取流量排名（Mock）- v4.11.1新增
     */
    async getTrafficRanking(params = {}) {
      this.trafficRanking.loading = true
      this.trafficRanking.error = null

      try {
        const granularity = params.granularity || 'monthly'
        const dimension = params.dimension || 'shop'

        // Mock数据 - 模拟流量排名（前10名）
        const mockData = []
        const today = new Date()
        
        for (let i = 0; i < 10; i++) {
          const uv = Math.floor(5000 + Math.random() * 5000) // 5000-10000随机
          const pv = Math.floor(uv * (1.5 + Math.random() * 0.5)) // PV是UV的1.5-2倍
          const compareUv = Math.floor(uv * (0.7 + Math.random() * 0.3)) // 对比期UV（70%-100%）
          const comparePv = Math.floor(pv * (0.7 + Math.random() * 0.3)) // 对比期PV
          
          const uvChangeRate = ((uv - compareUv) / compareUv * 100)
          const pvChangeRate = ((pv - comparePv) / comparePv * 100)
          
          mockData.push({
            rank: i + 1,
            name: dimension === 'shop' ? `Shopee${['新加坡', '马来', '泰国', '印尼', '菲律宾', '越南', '台湾', '巴西', '墨西哥', '智利'][i]}旗舰店` : `账号${i + 1}`,
            id: dimension === 'shop' ? `shopee_${['sg', 'my', 'th', 'id', 'ph', 'vn', 'tw', 'br', 'mx', 'cl'][i]}_001` : `account_${i + 1}`,
            platform_code: dimension === 'shop' ? 'shopee' : undefined,
            unique_visitors: uv,
            page_views: pv,
            compare_unique_visitors: compareUv,
            compare_page_views: comparePv,
            uv_change_rate: parseFloat(uvChangeRate.toFixed(2)),
            pv_change_rate: parseFloat(pvChangeRate.toFixed(2))
          })
        }

        this.trafficRanking.data = mockData
        this.trafficRanking.lastUpdate = new Date()

        return {
          success: true,
          data: mockData,
          granularity: granularity,
          dimension: dimension
        }
      } catch (error) {
        this.trafficRanking.error = error.message
        console.error('获取流量排名失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.trafficRanking.loading = false
      }
    }
  },

  getters: {
    /**
     * 是否有任何数据正在加载
     */
    isLoading: (state) => {
      return state.overview.loading ||
             state.salesTrend.loading ||
             state.profitAnalysis.loading ||
             state.topProducts.loading
    },

    /**
     * 获取最近更新时间
     */
    lastUpdateTime: (state) => {
      const times = [
        state.overview.lastUpdate,
        state.salesTrend.lastUpdate,
        state.profitAnalysis.lastUpdate,
        state.topProducts.lastUpdate
      ].filter(t => t !== null)

      if (times.length === 0) return null
      return new Date(Math.max(...times.map(t => new Date(t).getTime())))
    },

    /**
     * 是否有错误
     */
    hasError: (state) => {
      return state.overview.error ||
             state.salesTrend.error ||
             state.profitAnalysis.error ||
             state.topProducts.error
    }
  },

  actions: {
    /**
     * 设置全局筛选器
     */
    setFilters(filters) {
      this.filters = { ...this.filters, ...filters }
    },

    /**
     * 获取总览数据（已迁移到 Metabase Question API）
     * TODO: 迁移到 queryBusinessOverviewKpi
     */
    async fetchOverview(params = {}) {
      this.overview.loading = true
      this.overview.error = null
      // TODO: 使用新的 Metabase Question API
      this.overview.loading = false
    },

    /**
     * 获取销售趋势（已迁移到 Metabase Question API）
     * TODO: 迁移到 queryBusinessOverviewComparison
     */
    async fetchSalesTrend(params = {}) {
      this.salesTrend.loading = true
      this.salesTrend.error = null
      // TODO: 使用新的 Metabase Question API
      this.salesTrend.loading = false
    },

    /**
     * 获取利润分析（已迁移到 Metabase Question API）
     * TODO: 迁移到对应的 Metabase Question
     */
    async fetchProfitAnalysis(params = {}) {
      this.profitAnalysis.loading = true
      this.profitAnalysis.error = null
      // TODO: 使用新的 Metabase Question API
      this.profitAnalysis.loading = false
    },

    /**
     * 获取热销商品（已迁移到 Metabase Question API）
     * TODO: 迁移到对应的 Metabase Question
     */
    async fetchTopProducts(params = {}) {
      this.topProducts.loading = true
      this.topProducts.error = null
      // TODO: 使用新的 Metabase Question API
      this.topProducts.loading = false
    },

    /**
     * 获取平台对比数据（已迁移到 Metabase Question API）
     * TODO: 迁移到 queryBusinessOverviewShopRacing
     */
    async fetchPlatformComparison(params = {}) {
      this.platformComparison.loading = true
      this.platformComparison.error = null
      // TODO: 使用新的 Metabase Question API
      this.platformComparison.loading = false
    },

    /**
     * 获取订单统计（已迁移到 Metabase Question API）
     * TODO: 迁移到对应的 Metabase Question
     */
    async fetchOrderStatistics(params = {}) {
      this.orderStatistics.loading = true
      this.orderStatistics.error = null
      // TODO: 使用新的 Metabase Question API
      this.orderStatistics.loading = false
    },

    /**
     * 获取转化漏斗（已迁移到 Metabase Question API）
     * TODO: 迁移到对应的 Metabase Question
     */
    async fetchConversionFunnel(params = {}) {
      this.conversionFunnel.loading = true
      this.conversionFunnel.error = null
      // TODO: 使用新的 Metabase Question API
      this.conversionFunnel.loading = false
    },

    /**
     * 获取实时数据（已迁移到 Metabase Question API）
     * TODO: 迁移到对应的 Metabase Question
     */
    async fetchRealtimeData(params = {}) {
      this.realtimeData.loading = true
      this.realtimeData.error = null
      // TODO: 使用新的 Metabase Question API
      this.realtimeData.loading = false
    },

    /**
     * 刷新所有数据
     */
    async refreshAll(params = {}) {
      // TODO: 迁移到新的 Metabase Question API
      const promises = [
        this.fetchOverview(params),
        this.fetchSalesTrend(params),
        this.fetchProfitAnalysis(params),
        this.fetchTopProducts(params)
      ]

      await Promise.allSettled(promises)
    },

    /**
     * 重置状态
     */
    reset() {
      this.overview.data = {
        gmv: 0,
        gmvCny: 0,
        orderCount: 0,
        avgOrderValue: 0,
        totalProfit: 0,
        profitMargin: 0
      }
      this.salesTrend.data = []
      this.profitAnalysis.data = {}
      this.topProducts.data = []
      this.platformComparison.data = []
      this.orderStatistics.data = {}
      this.conversionFunnel.data = {}
      this.realtimeData.data = {}
    }
  }
})
