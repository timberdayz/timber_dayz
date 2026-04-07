/**
 * 销售相关状态管理 (Pinia Store)
 * 管理店铺销售表现、PK排名、销售战役等数据状态
 */

import { defineStore } from 'pinia'

export const useSalesStore = defineStore('sales', {
  state: () => ({
    // 店铺销售表现数据
    shopPerformance: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 销售PK排名数据
    pkRanking: {
      data: [],
      granularity: 'weekly', // weekly/monthly
      loading: false,
      error: null
    },

    // 销售战役数据
    campaigns: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 战役详情
    campaignDetail: {
      data: null,
      loading: false,
      error: null
    },

    // 筛选器
    filters: {
      platform: null,
      shopRegion: null,
      shopId: null,
      period: null,
      granularity: 'weekly' // weekly/monthly
    }
  }),

  actions: {
    /**
     * 获取店铺销售表现数据（Mock）
     */
    async getShopPerformance(params = {}) {
      this.shopPerformance.loading = true
      this.shopPerformance.error = null

      try {
        // Mock数据 - 模拟店铺销售表现
        const mockData = [
          {
            shop_region: '新加坡',
            shop_name: 'Shopee新加坡旗舰店',
            sales_quantity_target: 1000,
            sales_quantity_achieved: 850,
            sales_quantity_rate: 85.0, // 达成率
            sales_amount_target: 50000.00,
            sales_amount_achieved: 42500.00,
            sales_amount_rate: 85.0, // 达成率
            profit: 8500.00,
            commission: 850.00
          },
          {
            shop_region: '新加坡',
            shop_name: 'Lazada新加坡店',
            sales_quantity_target: 800,
            sales_quantity_achieved: 720,
            sales_quantity_rate: 90.0,
            sales_amount_target: 40000.00,
            sales_amount_achieved: 36000.00,
            sales_amount_rate: 90.0,
            profit: 7200.00,
            commission: 720.00
          },
          {
            shop_region: '马来西亚',
            shop_name: 'Shopee马来旗舰店',
            sales_quantity_target: 1200,
            sales_quantity_achieved: 1080,
            sales_quantity_rate: 90.0,
            sales_amount_target: 60000.00,
            sales_amount_achieved: 54000.00,
            sales_amount_rate: 90.0,
            profit: 10800.00,
            commission: 1080.00
          },
          {
            shop_region: '马来西亚',
            shop_name: 'Lazada马来店',
            sales_quantity_target: 900,
            sales_quantity_achieved: 810,
            sales_quantity_rate: 90.0,
            sales_amount_target: 45000.00,
            sales_amount_achieved: 40500.00,
            sales_amount_rate: 90.0,
            profit: 8100.00,
            commission: 810.00
          },
          {
            shop_region: '泰国',
            shop_name: 'Shopee泰国旗舰店',
            sales_quantity_target: 1500,
            sales_quantity_achieved: 1350,
            sales_quantity_rate: 90.0,
            sales_amount_target: 75000.00,
            sales_amount_achieved: 67500.00,
            sales_amount_rate: 90.0,
            profit: 13500.00,
            commission: 1350.00
          }
        ]

        // 应用筛选
        let filteredData = [...mockData]
        if (params.platform) {
          filteredData = filteredData.filter(item => item.shop_name.includes(params.platform))
        }
        if (params.shopRegion) {
          filteredData = filteredData.filter(item => item.shop_region === params.shopRegion)
        }

        // 模拟分页
        const page = params.page || this.shopPerformance.page
        const pageSize = params.pageSize || this.shopPerformance.pageSize
        const start = (page - 1) * pageSize
        const end = start + pageSize

        this.shopPerformance.data = filteredData.slice(start, end)
        this.shopPerformance.total = filteredData.length
        this.shopPerformance.page = page

        return {
          success: true,
          data: this.shopPerformance.data,
          total: this.shopPerformance.total,
          page: page,
          pageSize: pageSize
        }
      } catch (error) {
        this.shopPerformance.error = error.message
        console.error('获取店铺销售表现失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.shopPerformance.loading = false
      }
    },

    /**
     * 获取销售PK排名数据（Mock）
     */
    async getPKRanking(params = {}) {
      this.pkRanking.loading = true
      this.pkRanking.error = null

      try {
        const granularity = params.granularity || this.filters.granularity || 'weekly'
        this.pkRanking.granularity = granularity

        // Mock数据 - 模拟PK排名
        const mockData = [
          {
            rank: 1,
            shop_name: 'Shopee新加坡旗舰店',
            shop_region: '新加坡',
            sales_amount: 42500.00,
            achievement_rate: 85.0,
            growth_rate: 15.5,
            sales_quantity: 850
          },
          {
            rank: 2,
            shop_name: 'Lazada新加坡店',
            shop_region: '新加坡',
            sales_amount: 36000.00,
            achievement_rate: 90.0,
            growth_rate: 12.3,
            sales_quantity: 720
          },
          {
            rank: 3,
            shop_name: 'Shopee马来旗舰店',
            shop_region: '马来西亚',
            sales_amount: 54000.00,
            achievement_rate: 90.0,
            growth_rate: 18.7,
            sales_quantity: 1080
          },
          {
            rank: 4,
            shop_name: 'Lazada马来店',
            shop_region: '马来西亚',
            sales_amount: 40500.00,
            achievement_rate: 90.0,
            growth_rate: 10.2,
            sales_quantity: 810
          },
          {
            rank: 5,
            shop_name: 'Shopee泰国旗舰店',
            shop_region: '泰国',
            sales_amount: 67500.00,
            achievement_rate: 90.0,
            growth_rate: 20.1,
            sales_quantity: 1350
          }
        ]

        // 应用筛选（按店铺/地区/平台分组）
        let filteredData = [...mockData]
        if (params.groupBy === 'region') {
          // 按地区分组
          const grouped = {}
          filteredData.forEach(item => {
            if (!grouped[item.shop_region]) {
              grouped[item.shop_region] = {
                rank: item.rank,
                shop_name: item.shop_region,
                shop_region: item.shop_region,
                sales_amount: 0,
                achievement_rate: 0,
                growth_rate: 0,
                sales_quantity: 0
              }
            }
            grouped[item.shop_region].sales_amount += item.sales_amount
            grouped[item.shop_region].sales_quantity += item.sales_quantity
          })
          filteredData = Object.values(grouped).sort((a, b) => b.sales_amount - a.sales_amount)
          filteredData.forEach((item, index) => {
            item.rank = index + 1
          })
        }

        // 只返回前10名
        this.pkRanking.data = filteredData.slice(0, 10)

        return {
          success: true,
          data: this.pkRanking.data,
          granularity: granularity
        }
      } catch (error) {
        this.pkRanking.error = error.message
        console.error('获取PK排名失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.pkRanking.loading = false
      }
    },

    /**
     * 获取销售战役列表（Mock）
     */
    async getCampaigns(params = {}) {
      this.campaigns.loading = true
      this.campaigns.error = null

      try {
        // Mock数据 - 模拟销售战役
        const mockData = [
          {
            id: 1,
            campaign_name: '2025春节促销',
            campaign_type: 'holiday',
            start_date: '2025-01-20',
            end_date: '2025-02-10',
            target_amount: 500000.00,
            actual_amount: 425000.00,
            achievement_rate: 85.0,
            status: 'active',
            participating_shops: ['Shopee新加坡旗舰店', 'Lazada新加坡店'],
            participating_products: []
          },
          {
            id: 2,
            campaign_name: '新品上市推广',
            campaign_type: 'new_product',
            start_date: '2025-02-01',
            end_date: '2025-02-28',
            target_amount: 300000.00,
            actual_amount: 270000.00,
            achievement_rate: 90.0,
            status: 'active',
            participating_shops: ['Shopee马来旗舰店', 'Lazada马来店'],
            participating_products: []
          },
          {
            id: 3,
            campaign_name: '2024双11大促',
            campaign_type: 'special_event',
            start_date: '2024-11-01',
            end_date: '2024-11-11',
            target_amount: 1000000.00,
            actual_amount: 950000.00,
            achievement_rate: 95.0,
            status: 'completed',
            participating_shops: ['Shopee新加坡旗舰店', 'Lazada新加坡店', 'Shopee马来旗舰店'],
            participating_products: []
          }
        ]

        // 应用筛选
        let filteredData = [...mockData]
        if (params.status) {
          filteredData = filteredData.filter(item => item.status === params.status)
        }
        if (params.campaignType) {
          filteredData = filteredData.filter(item => item.campaign_type === params.campaignType)
        }

        // 模拟分页
        const page = params.page || this.campaigns.page
        const pageSize = params.pageSize || this.campaigns.pageSize
        const start = (page - 1) * pageSize
        const end = start + pageSize

        this.campaigns.data = filteredData.slice(start, end)
        this.campaigns.total = filteredData.length
        this.campaigns.page = page

        return {
          success: true,
          data: this.campaigns.data,
          total: this.campaigns.total,
          page: page,
          pageSize: pageSize
        }
      } catch (error) {
        this.campaigns.error = error.message
        console.error('获取销售战役列表失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.campaigns.loading = false
      }
    },

    /**
     * 获取销售战役详情（Mock）
     */
    async getCampaignDetail(id) {
      this.campaignDetail.loading = true
      this.campaignDetail.error = null

      try {
        // Mock数据 - 模拟战役详情
        const mockDetail = {
          id: id,
          campaign_name: '2025春节促销',
          campaign_type: 'holiday',
          start_date: '2025-01-20',
          end_date: '2025-02-10',
          target_amount: 500000.00,
          actual_amount: 425000.00,
          achievement_rate: 85.0,
          status: 'active',
          participating_shops: [
            {
              shop_id: 'shopee_sg_001',
              shop_name: 'Shopee新加坡旗舰店',
              target_amount: 300000.00,
              actual_amount: 255000.00,
              achievement_rate: 85.0
            },
            {
              shop_id: 'lazada_sg_001',
              shop_name: 'Lazada新加坡店',
              target_amount: 200000.00,
              actual_amount: 170000.00,
              achievement_rate: 85.0
            }
          ],
          participating_products: [],
          shop_ranking: [
            {
              rank: 1,
              shop_name: 'Shopee新加坡旗舰店',
              sales_amount: 255000.00,
              achievement_rate: 85.0
            },
            {
              rank: 2,
              shop_name: 'Lazada新加坡店',
              sales_amount: 170000.00,
              achievement_rate: 85.0
            }
          ],
          product_ranking: []
        }

        this.campaignDetail.data = mockDetail

        return {
          success: true,
          data: mockDetail
        }
      } catch (error) {
        this.campaignDetail.error = error.message
        console.error('获取销售战役详情失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.campaignDetail.loading = false
      }
    },

    /**
     * 创建销售战役（Mock）
     */
    async createCampaign(data) {
      try {
        // Mock创建 - 返回成功
        return {
          success: true,
          data: {
            id: Date.now(),
            ...data,
            status: 'active',
            actual_amount: 0,
            achievement_rate: 0
          },
          message: '销售战役创建成功'
        }
      } catch (error) {
        console.error('创建销售战役失败:', error)
        return {
          success: false,
          error: error.message
        }
      }
    },

    /**
     * 更新销售战役（Mock）
     */
    async updateCampaign(id, data) {
      try {
        // Mock更新 - 返回成功
        return {
          success: true,
          data: {
            id: id,
            ...data
          },
          message: '销售战役更新成功'
        }
      } catch (error) {
        console.error('更新销售战役失败:', error)
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
      this.shopPerformance.data = []
      this.pkRanking.data = []
      this.campaigns.data = []
      this.campaignDetail.data = null
    }
  }
})

