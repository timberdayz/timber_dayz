/**
 * 人力资源状态管理 (Pinia Store)
 * 管理绩效管理相关数据状态
 */

import { defineStore } from 'pinia'

export const useHRStore = defineStore('hr', {
  state: () => ({
    // 绩效列表数据
    performanceList: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 绩效详情
    performanceDetail: {
      data: null,
      loading: false,
      error: null
    },

    // 绩效配置
    performanceConfig: {
      data: {
        sales_weight: 30,
        profit_weight: 25,
        key_product_weight: 25,
        operation_weight: 20
      },
      loading: false,
      error: null
    },

    // 筛选器
    filters: {
      shopId: null,
      platform: null,
      period: null // 月度周期，如 '2025-01'
    }
  }),

  actions: {
    /**
     * 获取绩效列表（Mock）
     */
    async getPerformanceList(params = {}) {
      this.performanceList.loading = true
      this.performanceList.error = null

      try {
        // Mock数据 - 模拟绩效公示表格
        const mockData = [
          {
            shop_id: 'shopee_sg_001',
            shop_name: 'Shopee新加坡旗舰店',
            sales_score: 25.5, // 销售额得分（30%）
            profit_score: 22.5, // 毛利得分（25%）
            key_product_score: 23.0, // 重点产品得分（25%）
            operation_score: 18.0, // 运营得分（20%）
            total_score: 89.0, // 总分
            rank: 1,
            performance_coefficient: 1.2
          },
          {
            shop_id: 'lazada_sg_001',
            shop_name: 'Lazada新加坡店',
            sales_score: 27.0,
            profit_score: 23.75,
            key_product_score: 24.0,
            operation_score: 19.0,
            total_score: 93.75,
            rank: 1,
            performance_coefficient: 1.3
          },
          {
            shop_id: 'shopee_my_001',
            shop_name: 'Shopee马来旗舰店',
            sales_score: 26.0,
            profit_score: 23.0,
            key_product_score: 23.5,
            operation_score: 18.5,
            total_score: 91.0,
            rank: 2,
            performance_coefficient: 1.25
          },
          {
            shop_id: 'lazada_my_001',
            shop_name: 'Lazada马来店',
            sales_score: 24.0,
            profit_score: 21.25,
            key_product_score: 22.0,
            operation_score: 17.0,
            total_score: 84.25,
            rank: 3,
            performance_coefficient: 1.1
          },
          {
            shop_id: 'shopee_th_001',
            shop_name: 'Shopee泰国旗舰店',
            sales_score: 28.5,
            profit_score: 24.5,
            key_product_score: 25.0,
            operation_score: 19.5,
            total_score: 97.5,
            rank: 1,
            performance_coefficient: 1.4
          }
        ]

        // 应用筛选
        let filteredData = [...mockData]
        if (params.shopId) {
          filteredData = filteredData.filter(item => item.shop_id === params.shopId)
        }
        if (params.platform) {
          filteredData = filteredData.filter(item => item.shop_name.includes(params.platform))
        }

        // 重新排序
        filteredData.sort((a, b) => b.total_score - a.total_score)
        filteredData.forEach((item, index) => {
          item.rank = index + 1
        })

        // 模拟分页
        const page = params.page || this.performanceList.page
        const pageSize = params.pageSize || this.performanceList.pageSize
        const start = (page - 1) * pageSize
        const end = start + pageSize

        this.performanceList.data = filteredData.slice(start, end)
        this.performanceList.total = filteredData.length
        this.performanceList.page = page

        return {
          success: true,
          data: this.performanceList.data,
          total: this.performanceList.total,
          page: page,
          pageSize: pageSize
        }
      } catch (error) {
        this.performanceList.error = error.message
        console.error('获取绩效列表失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.performanceList.loading = false
      }
    },

    /**
     * 获取店铺详细绩效（Mock）
     */
    async getPerformanceDetail(shopId) {
      this.performanceDetail.loading = true
      this.performanceDetail.error = null

      try {
        // Mock数据 - 模拟绩效详情
        const mockDetail = {
          shop_id: shopId,
          shop_name: 'Shopee新加坡旗舰店',
          period: '2025-01',
          // 销售额得分详情
          sales_score: {
            score: 25.5,
            weight: 30,
            target: 50000.00,
            achieved: 42500.00,
            rate: 85.0,
            calculation: '(42500 / 50000) * 30 = 25.5'
          },
          // 毛利得分详情
          profit_score: {
            score: 22.5,
            weight: 25,
            target: 10000.00,
            achieved: 9000.00,
            rate: 90.0,
            calculation: '(9000 / 10000) * 25 = 22.5'
          },
          // 重点产品得分详情
          key_product_score: {
            score: 23.0,
            weight: 25,
            target: 100,
            achieved: 92,
            rate: 92.0,
            calculation: '(92 / 100) * 25 = 23.0',
            breakdown: {
              backlog_clearance: 12, // 滞销清理
              service_score: 80 // 服务得分
            }
          },
          // 运营得分详情
          operation_score: {
            score: 18.0,
            weight: 20,
            score_raw: 90.0,
            calculation: '90 * 20% = 18.0',
            breakdown: {
              order_fulfillment_rate: 95.0,
              customer_satisfaction: 88.0,
              inventory_turnover: 87.0
            }
          },
          // 总分
          total_score: 89.0,
          rank: 1,
          performance_coefficient: 1.2
        }

        this.performanceDetail.data = mockDetail

        return {
          success: true,
          data: mockDetail
        }
      } catch (error) {
        this.performanceDetail.error = error.message
        console.error('获取绩效详情失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.performanceDetail.loading = false
      }
    },

    /**
     * 更新绩效配置（Mock）
     */
    async updatePerformanceConfig(config) {
      try {
        // Mock更新 - 验证权重总和
        const totalWeight = config.sales_weight + config.profit_weight + 
                           config.key_product_weight + config.operation_weight
        
        if (totalWeight !== 100) {
          return {
            success: false,
            error: '各项权重总和必须等于100%'
          }
        }

        this.performanceConfig.data = { ...this.performanceConfig.data, ...config }

        return {
          success: true,
          data: this.performanceConfig.data,
          message: '绩效配置更新成功'
        }
      } catch (error) {
        console.error('更新绩效配置失败:', error)
        return {
          success: false,
          error: error.message
        }
      }
    },

    /**
     * 获取绩效配置（Mock）
     */
    async getPerformanceConfig() {
      try {
        return {
          success: true,
          data: this.performanceConfig.data
        }
      } catch (error) {
        console.error('获取绩效配置失败:', error)
        return {
          success: false,
          error: error.message
        }
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
      this.performanceList.data = []
      this.performanceDetail.data = null
    }
  }
})

