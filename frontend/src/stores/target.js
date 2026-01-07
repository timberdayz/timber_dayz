/**
 * 目标管理状态管理 (Pinia Store)
 * 管理目标配置、目标分解、目标达成等数据状态
 */

import { defineStore } from 'pinia'

export const useTargetStore = defineStore('target', {
  state: () => ({
    // 目标列表数据
    targets: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 目标详情
    targetDetail: {
      data: null,
      loading: false,
      error: null
    },

    // 目标达成情况
    targetAchievement: {
      data: null,
      loading: false,
      error: null
    },

    // 筛选器
    filters: {
      targetType: null, // shop/product/campaign
      period: null,
      status: null // active/completed/cancelled
    }
  }),

  actions: {
    /**
     * 获取目标列表（Mock）
     */
    async getTargets(params = {}) {
      this.targets.loading = true
      this.targets.error = null

      try {
        // Mock数据 - 模拟目标配置列表
        const mockData = [
          {
            id: 1,
            target_name: '2025年1月店铺销售目标',
            target_type: 'shop',
            period_start: '2025-01-01',
            period_end: '2025-01-31',
            target_amount: 500000.00,
            target_quantity: 10000,
            achieved_amount: 425000.00,
            achieved_quantity: 8500,
            achievement_rate: 85.0,
            status: 'active'
          },
          {
            id: 2,
            target_name: '2025年2月店铺销售目标',
            target_type: 'shop',
            period_start: '2025-02-01',
            period_end: '2025-02-28',
            target_amount: 600000.00,
            target_quantity: 12000,
            achieved_amount: 0,
            achieved_quantity: 0,
            achievement_rate: 0,
            status: 'active'
          },
          {
            id: 3,
            target_name: '2025年1月产品销量目标',
            target_type: 'product',
            period_start: '2025-01-01',
            period_end: '2025-01-31',
            target_amount: 300000.00,
            target_quantity: 5000,
            achieved_amount: 270000.00,
            achieved_quantity: 4500,
            achievement_rate: 90.0,
            status: 'active'
          },
          {
            id: 4,
            target_name: '2025春节促销战役目标',
            target_type: 'campaign',
            period_start: '2025-01-20',
            period_end: '2025-02-10',
            target_amount: 500000.00,
            target_quantity: 10000,
            achieved_amount: 425000.00,
            achieved_quantity: 8500,
            achievement_rate: 85.0,
            status: 'active'
          }
        ]

        // 应用筛选
        let filteredData = [...mockData]
        if (params.targetType) {
          filteredData = filteredData.filter(item => item.target_type === params.targetType)
        }
        if (params.status) {
          filteredData = filteredData.filter(item => item.status === params.status)
        }
        if (params.period) {
          filteredData = filteredData.filter(item => 
            item.period_start <= params.period && item.period_end >= params.period
          )
        }

        // 模拟分页
        const page = params.page || this.targets.page
        const pageSize = params.pageSize || this.targets.pageSize
        const start = (page - 1) * pageSize
        const end = start + pageSize

        this.targets.data = filteredData.slice(start, end)
        this.targets.total = filteredData.length
        this.targets.page = page

        return {
          success: true,
          data: this.targets.data,
          total: this.targets.total,
          page: page,
          pageSize: pageSize
        }
      } catch (error) {
        this.targets.error = error.message
        console.error('获取目标列表失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.targets.loading = false
      }
    },

    /**
     * 获取目标详情（Mock）
     */
    async getTargetDetail(id) {
      this.targetDetail.loading = true
      this.targetDetail.error = null

      try {
        // Mock数据 - 模拟目标详情
        const mockDetail = {
          id: id,
          target_name: '2025年1月店铺销售目标',
          target_type: 'shop',
          period_start: '2025-01-01',
          period_end: '2025-01-31',
          target_amount: 500000.00,
          target_quantity: 10000,
          achieved_amount: 425000.00,
          achieved_quantity: 8500,
          achievement_rate: 85.0,
          status: 'active',
          // 目标分解（按店铺）
          breakdown: [
            {
              shop_id: 'shopee_sg_001',
              shop_name: 'Shopee新加坡旗舰店',
              target_amount: 300000.00,
              target_quantity: 6000,
              achieved_amount: 255000.00,
              achieved_quantity: 5100,
              achievement_rate: 85.0
            },
            {
              shop_id: 'lazada_sg_001',
              shop_name: 'Lazada新加坡店',
              target_amount: 200000.00,
              target_quantity: 4000,
              achieved_amount: 170000.00,
              achieved_quantity: 3400,
              achievement_rate: 85.0
            }
          ],
          // 时间分解（按周）
          time_breakdown: [
            {
              week: '2025-W01',
              target_amount: 125000.00,
              target_quantity: 2500,
              achieved_amount: 106250.00,
              achieved_quantity: 2125,
              achievement_rate: 85.0
            },
            {
              week: '2025-W02',
              target_amount: 125000.00,
              target_quantity: 2500,
              achieved_amount: 106250.00,
              achieved_quantity: 2125,
              achievement_rate: 85.0
            },
            {
              week: '2025-W03',
              target_amount: 125000.00,
              target_quantity: 2500,
              achieved_amount: 106250.00,
              achieved_quantity: 2125,
              achievement_rate: 85.0
            },
            {
              week: '2025-W04',
              target_amount: 125000.00,
              target_quantity: 2500,
              achieved_amount: 106250.00,
              achieved_quantity: 2125,
              achievement_rate: 85.0
            }
          ]
        }

        this.targetDetail.data = mockDetail

        return {
          success: true,
          data: mockDetail
        }
      } catch (error) {
        this.targetDetail.error = error.message
        console.error('获取目标详情失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.targetDetail.loading = false
      }
    },

    /**
     * 创建目标（Mock）
     */
    async createTarget(data) {
      try {
        // Mock创建 - 返回成功
        return {
          success: true,
          data: {
            id: Date.now(),
            ...data,
            achieved_amount: 0,
            achieved_quantity: 0,
            achievement_rate: 0,
            status: 'active'
          },
          message: '目标创建成功'
        }
      } catch (error) {
        console.error('创建目标失败:', error)
        return {
          success: false,
          error: error.message
        }
      }
    },

    /**
     * 更新目标（Mock）
     */
    async updateTarget(id, data) {
      try {
        // Mock更新 - 返回成功
        return {
          success: true,
          data: {
            id: id,
            ...data
          },
          message: '目标更新成功'
        }
      } catch (error) {
        console.error('更新目标失败:', error)
        return {
          success: false,
          error: error.message
        }
      }
    },

    /**
     * 删除目标（Mock）
     */
    async deleteTarget(id) {
      try {
        // Mock删除 - 返回成功
        return {
          success: true,
          message: '目标删除成功'
        }
      } catch (error) {
        console.error('删除目标失败:', error)
        return {
          success: false,
          error: error.message
        }
      }
    },

    /**
     * 创建目标分解（Mock）
     */
    async createTargetBreakdown(targetId, breakdown) {
      try {
        // Mock创建分解 - 验证分解总和
        const totalAmount = breakdown.reduce((sum, item) => sum + (item.target_amount || 0), 0)
        const totalQuantity = breakdown.reduce((sum, item) => sum + (item.target_quantity || 0), 0)

        return {
          success: true,
          data: {
            target_id: targetId,
            breakdown: breakdown,
            total_amount: totalAmount,
            total_quantity: totalQuantity
          },
          message: '目标分解创建成功'
        }
      } catch (error) {
        console.error('创建目标分解失败:', error)
        return {
          success: false,
          error: error.message
        }
      }
    },

    /**
     * 获取目标达成情况（Mock）
     */
    async getTargetAchievement(id) {
      this.targetAchievement.loading = true
      this.targetAchievement.error = null

      try {
        // Mock数据 - 模拟目标达成情况
        const mockAchievement = {
          target_id: id,
          target_name: '2025年1月店铺销售目标',
          target_amount: 500000.00,
          target_quantity: 10000,
          achieved_amount: 425000.00,
          achieved_quantity: 8500,
          achievement_rate: 85.0,
          // 实时达成情况（按日）
          daily_achievement: [
            { date: '2025-01-01', amount: 15000.00, quantity: 300 },
            { date: '2025-01-02', amount: 16000.00, quantity: 320 },
            { date: '2025-01-03', amount: 14000.00, quantity: 280 }
            // ... 更多日期数据
          ],
          // 达成率分析
          achievement_analysis: {
            on_track: true, // 是否按计划进行
            projected_completion: '2025-01-31', // 预计完成日期
            remaining_days: 20,
            daily_required: 3750.00 // 每日需要达成的金额
          }
        }

        this.targetAchievement.data = mockAchievement

        return {
          success: true,
          data: mockAchievement
        }
      } catch (error) {
        this.targetAchievement.error = error.message
        console.error('获取目标达成情况失败:', error)
        return {
          success: false,
          error: error.message
        }
      } finally {
        this.targetAchievement.loading = false
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
      this.targets.data = []
      this.targetDetail.data = null
      this.targetAchievement.data = null
    }
  }
})

