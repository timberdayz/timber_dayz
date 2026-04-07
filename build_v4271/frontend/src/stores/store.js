/**
 * 店铺分析状态管理 (Pinia Store)
 * 管理店铺GMV趋势、转化率、健康度评分、对比分析等数据状态
 */

import { defineStore } from 'pinia'

export const useStoreStore = defineStore('store', {
  state: () => ({
    // 店铺GMV趋势数据
    gmvTrend: {
      data: [],
      loading: false,
      error: null
    },

    // 店铺转化率分析数据
    conversionAnalysis: {
      data: [],
      loading: false,
      error: null
    },

    // 店铺健康度评分数据
    healthScore: {
      data: [],
      loading: false,
      error: null
    },

    // 店铺对比分析数据
    comparison: {
      data: [],
      loading: false,
      error: null
    },

    // 店铺预警提醒数据
    alerts: {
      data: [],
      loading: false,
      error: null
    },

    // 店铺详情
    storeDetail: {
      data: null,
      loading: false,
      error: null
    },

    // 筛选器
    filters: {
      shopId: null,
      platform: null,
      startDate: null,
      endDate: null,
      granularity: 'daily' // daily/weekly/monthly
    }
  }),

  actions: {
    /**
     * 获取店铺GMV趋势（Mock）
     */
    async getGMVTrend(params = {}) {
      this.gmvTrend.loading = true
      this.gmvTrend.error = null

      try {
        const granularity = params.granularity || this.filters.granularity || 'daily'
        const shopId = params.shopId || this.filters.shopId

        // Mock数据 - 模拟GMV趋势（最近30天）
        const mockData = []
        const today = new Date()
        
        for (let i = 29; i >= 0; i--) {
          const date = new Date(today)
          date.setDate(date.getDate() - i)
          
          mockData.push({
            date: date.toISOString().split('T')[0],
            gmv: 5000 + Math.random() * 3000, // 5000-8000随机
            gmv_cny: (5000 + Math.random() * 3000) * 5.2, // 转换为CNY
            order_count: Math.floor(50 + Math.random() * 30),
            avg_order_value: 100 + Math.random() * 50
          })
        }

        this.gmvTrend.data = mockData

        return {
          success: true,
          data: mockData,
          granularity: granularity
        }
      } catch (error) {
        this.gmvTrend.error = error.message
        console.error('获取GMV趋势失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.gmvTrend.loading = false
      }
    },

    /**
     * 获取店铺流量分析（Mock）
     */
    async getTrafficAnalysis(params = {}) {
      this.trafficAnalysis = this.trafficAnalysis || { data: [], loading: false, error: null }
      this.trafficAnalysis.loading = true
      this.trafficAnalysis.error = null

      try {
        const granularity = params.granularity || this.filters.granularity || 'daily'
        const shopId = params.shopId || this.filters.shopId

        // Mock数据 - 模拟流量分析（最近30天）
        const mockData = []
        const today = new Date()
        
        for (let i = 29; i >= 0; i--) {
          const date = new Date(today)
          date.setDate(date.getDate() - i)
          
          const uv = Math.floor(800 + Math.random() * 400) // 800-1200随机
          const pv = Math.floor(uv * (1.5 + Math.random() * 0.5)) // PV是UV的1.5-2倍
          const addToCart = Math.floor(uv * (0.15 + Math.random() * 0.1)) // 15-25%加购率
          const orderCount = Math.floor(uv * (0.05 + Math.random() * 0.02)) // 5-7%转化率
          
          mockData.push({
            date: date.toISOString().split('T')[0],
            page_views: pv,
            unique_visitors: uv,
            add_to_cart: addToCart,
            order_count: orderCount,
            conversion_rate: (orderCount / uv * 100).toFixed(2),
            add_to_cart_rate: (addToCart / uv * 100).toFixed(2),
            bounce_rate: ((uv - addToCart) / uv * 100).toFixed(2),
            avg_page_views_per_visitor: (pv / uv).toFixed(2)
          })
        }

        this.trafficAnalysis.data = mockData

        return {
          success: true,
          data: mockData,
          granularity: granularity
        }
      } catch (error) {
        this.trafficAnalysis.error = error.message
        console.error('获取流量分析失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.trafficAnalysis.loading = false
      }
    },

    /**
     * 获取店铺转化率分析（Mock）
     */
    async getConversionAnalysis(params = {}) {
      this.conversionAnalysis.loading = true
      this.conversionAnalysis.error = null

      try {
        const shopId = params.shopId || this.filters.shopId

        // Mock数据 - 模拟转化率分析
        const mockData = [
          {
            date: '2025-11-01',
            page_views: 1000,
            unique_visitors: 800,
            add_to_cart: 200,
            orders: 50,
            conversion_rate: 5.0,
            add_to_cart_rate: 20.0
          },
          {
            date: '2025-11-02',
            page_views: 1200,
            unique_visitors: 950,
            add_to_cart: 240,
            orders: 60,
            conversion_rate: 5.0,
            add_to_cart_rate: 20.0
          },
          {
            date: '2025-11-03',
            page_views: 1100,
            unique_visitors: 880,
            add_to_cart: 220,
            orders: 55,
            conversion_rate: 5.0,
            add_to_cart_rate: 20.0
          }
          // ... 更多日期数据
        ]

        this.conversionAnalysis.data = mockData

        return {
          success: true,
          data: mockData
        }
      } catch (error) {
        this.conversionAnalysis.error = error.message
        console.error('获取转化率分析失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.conversionAnalysis.loading = false
      }
    },

    /**
     * 获取店铺健康度评分（Mock）
     */
    async getStoreHealthScores(params = {}) {
      this.healthScore.loading = true
      this.healthScore.error = null

      try {
        // Mock数据 - 模拟店铺健康度评分
        const mockData = [
          {
            shop_id: 'shopee_sg_001',
            shop_name: 'Shopee新加坡旗舰店',
            platform: 'Shopee',
            health_score: 85,
            gmv_score: 25,
            conversion_score: 20,
            inventory_score: 20,
            service_score: 20,
            gmv: 42500.00,
            conversion_rate: 5.2,
            inventory_turnover: 12.5,
            customer_satisfaction: 4.5,
            risk_level: 'low',
            risk_factors: []
          },
          {
            shop_id: 'lazada_sg_001',
            shop_name: 'Lazada新加坡店',
            platform: 'Lazada',
            health_score: 90,
            gmv_score: 27,
            conversion_score: 22,
            inventory_score: 21,
            service_score: 20,
            gmv: 36000.00,
            conversion_rate: 5.5,
            inventory_turnover: 13.0,
            customer_satisfaction: 4.6,
            risk_level: 'low',
            risk_factors: []
          },
          {
            shop_id: 'shopee_my_001',
            shop_name: 'Shopee马来旗舰店',
            platform: 'Shopee',
            health_score: 88,
            gmv_score: 26,
            conversion_score: 21,
            inventory_score: 21,
            service_score: 20,
            gmv: 54000.00,
            conversion_rate: 5.3,
            inventory_turnover: 12.8,
            customer_satisfaction: 4.5,
            risk_level: 'low',
            risk_factors: []
          },
          {
            shop_id: 'lazada_my_001',
            shop_name: 'Lazada马来店',
            platform: 'Lazada',
            health_score: 82,
            gmv_score: 24,
            conversion_score: 19,
            inventory_score: 19,
            service_score: 20,
            gmv: 40500.00,
            conversion_rate: 4.8,
            inventory_turnover: 11.5,
            customer_satisfaction: 4.3,
            risk_level: 'medium',
            risk_factors: ['库存周转率偏低']
          },
          {
            shop_id: 'shopee_th_001',
            shop_name: 'Shopee泰国旗舰店',
            platform: 'Shopee',
            health_score: 92,
            gmv_score: 28,
            conversion_score: 23,
            inventory_score: 21,
            service_score: 20,
            gmv: 67500.00,
            conversion_rate: 5.8,
            inventory_turnover: 14.0,
            customer_satisfaction: 4.7,
            risk_level: 'low',
            risk_factors: []
          }
        ]

        // 应用筛选
        let filteredData = [...mockData]
        if (params.shop_id) {
          filteredData = filteredData.filter(item => item.shop_id === params.shop_id)
        }
        if (params.platform_code) {
          filteredData = filteredData.filter(item => item.platform === params.platform_code)
        }

        // 按健康度评分排序
        filteredData.sort((a, b) => b.health_score - a.health_score)

        this.healthScore.data = filteredData

        return {
          success: true,
          data: filteredData
        }
      } catch (error) {
        this.healthScore.error = error.message
        console.error('获取健康度评分失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.healthScore.loading = false
      }
    },

    /**
     * 获取店铺对比分析（Mock）
     */
    async getComparison(params = {}) {
      this.comparison.loading = true
      this.comparison.error = null

      try {
        const shopIds = params.shopIds || []

        // Mock数据 - 模拟店铺对比
        const mockData = [
          {
            shop_id: 'shopee_sg_001',
            shop_name: 'Shopee新加坡旗舰店',
            platform: 'Shopee',
            gmv: 42500.00,
            order_count: 850,
            avg_order_value: 50.00,
            conversion_rate: 5.2,
            page_views: 16346,
            unique_visitors: 13077,
            customer_satisfaction: 4.5,
            inventory_turnover: 12.5,
            health_score: 85
          },
          {
            shop_id: 'lazada_sg_001',
            shop_name: 'Lazada新加坡店',
            platform: 'Lazada',
            gmv: 36000.00,
            order_count: 720,
            avg_order_value: 50.00,
            conversion_rate: 5.5,
            page_views: 13091,
            unique_visitors: 10473,
            customer_satisfaction: 4.6,
            inventory_turnover: 13.0,
            health_score: 90
          }
        ]

        // 如果指定了店铺ID，只返回这些店铺
        let filteredData = shopIds.length > 0 
          ? mockData.filter(item => shopIds.includes(item.shop_id))
          : mockData

        this.comparison.data = filteredData

        return {
          success: true,
          data: filteredData
        }
      } catch (error) {
        this.comparison.error = error.message
        console.error('获取对比分析失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.comparison.loading = false
      }
    },

    /**
     * 获取店铺预警提醒（Mock）
     */
    async getAlerts(params = {}) {
      this.alerts.loading = true
      this.alerts.error = null

      try {
        // Mock数据 - 模拟预警提醒
        const mockData = [
          {
            id: 1,
            shop_id: 'lazada_my_001',
            shop_name: 'Lazada马来店',
            alert_type: 'inventory_turnover',
            alert_level: 'warning',
            title: '库存周转率偏低',
            message: '库存周转率为11.5，低于平均水平12.0',
            metric_value: 11.5,
            threshold: 12.0,
            created_at: '2025-11-13 10:00:00'
          },
          {
            id: 2,
            shop_id: 'shopee_sg_001',
            shop_name: 'Shopee新加坡旗舰店',
            alert_type: 'conversion_rate',
            alert_level: 'info',
            title: '转化率波动',
            message: '最近7天转化率下降2%',
            metric_value: 5.0,
            threshold: 5.2,
            created_at: '2025-11-13 09:30:00'
          }
        ]

        // 应用筛选
        let filteredData = [...mockData]
        if (params.shopId) {
          filteredData = filteredData.filter(item => item.shop_id === params.shopId)
        }
        if (params.alertLevel) {
          filteredData = filteredData.filter(item => item.alert_level === params.alertLevel)
        }

        this.alerts.data = filteredData

        return {
          success: true,
          data: filteredData
        }
      } catch (error) {
        this.alerts.error = error.message
        console.error('获取预警提醒失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.alerts.loading = false
      }
    },

    /**
     * 获取店铺详情（Mock）
     */
    async getStoreDetail(shopId) {
      this.storeDetail.loading = true
      this.storeDetail.error = null

      try {
        // Mock数据 - 模拟店铺详情
        const mockDetail = {
          shop_id: shopId,
          shop_name: 'Shopee新加坡旗舰店',
          platform: 'Shopee',
          region: '新加坡',
          health_score: 85,
          gmv: 42500.00,
          order_count: 850,
          avg_order_value: 50.00,
          conversion_rate: 5.2,
          page_views: 16346,
          unique_visitors: 13077,
          customer_satisfaction: 4.5,
          inventory_turnover: 12.5,
          risk_level: 'low',
          risk_factors: [],
          // 趋势数据
          gmv_trend: [],
          conversion_trend: [],
          // 评分明细
          score_breakdown: {
            gmv_score: 25,
            conversion_score: 20,
            inventory_score: 20,
            service_score: 20
          }
        }

        this.storeDetail.data = mockDetail

        return {
          success: true,
          data: mockDetail
        }
      } catch (error) {
        this.storeDetail.error = error.message
        console.error('获取店铺详情失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.storeDetail.loading = false
      }
    },

    /**
     * 设置筛选器
     */
    setFilters(filters) {
      this.filters = { ...this.filters, ...filters }
    },

    /**
     * 重置状态
     */
    reset() {
      this.gmvTrend.data = []
      this.conversionAnalysis.data = []
      this.healthScore.data = []
      this.comparison.data = []
      this.alerts.data = []
      this.storeDetail.data = null
    }
  }
})

