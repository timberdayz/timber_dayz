/**
 * 库存管理状态管理 (Pinia Store)
 */

import { defineStore } from 'pinia'
import inventoryApi from '@/api/inventory'

export const useInventoryStore = defineStore('inventory', {
  state: () => ({
    // 库存列表
    inventoryList: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 库存详情
    inventoryDetail: {
      data: null,
      loading: false,
      error: null
    },

    // 库存流水
    transactions: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 低库存预警
    lowStockAlert: {
      data: [],
      total: 0,
      loading: false,
      error: null
    },

    // 库存汇总
    summary: {
      data: {
        totalValue: 0,
        totalItems: 0,
        lowStockCount: 0,
        averageTurnover: 0
      },
      loading: false,
      error: null
    },

    // 筛选器
    filters: {
      platform: null,
      shopId: null,
      keyword: null,
      warehouseCode: null,
      lowStockOnly: false
    }
  }),

  actions: {
    /**
     * 获取库存列表
     */
    async fetchInventoryList(params = {}) {
      this.inventoryList.loading = true
      this.inventoryList.error = null

      try {
        const queryParams = {
          ...this.filters,
          ...params,
          page: this.inventoryList.page,
          pageSize: this.inventoryList.pageSize
        }

        const response = await inventoryApi.getInventoryList(queryParams)
        
        this.inventoryList.data = response.data || response.items || []
        this.inventoryList.total = response.total || 0
      } catch (error) {
        this.inventoryList.error = error.message
        console.error('获取库存列表失败:', error)
      } finally {
        this.inventoryList.loading = false
      }
    },

    /**
     * 获取库存详情
     */
    async fetchInventoryDetail(productId) {
      this.inventoryDetail.loading = true
      this.inventoryDetail.error = null

      try {
        const response = await inventoryApi.getInventoryDetail(productId)
        this.inventoryDetail.data = response.data || response
      } catch (error) {
        this.inventoryDetail.error = error.message
        console.error('获取库存详情失败:', error)
      } finally {
        this.inventoryDetail.loading = false
      }
    },

    /**
     * 获取库存流水
     */
    async fetchTransactions(params = {}) {
      this.transactions.loading = true
      this.transactions.error = null

      try {
        const queryParams = {
          ...params,
          page: this.transactions.page,
          pageSize: this.transactions.pageSize
        }

        const response = await inventoryApi.getInventoryTransactions(queryParams)
        
        this.transactions.data = response.data || response.transactions || []
        this.transactions.total = response.total || 0
      } catch (error) {
        this.transactions.error = error.message
        console.error('获取库存流水失败:', error)
      } finally {
        this.transactions.loading = false
      }
    },

    /**
     * 获取低库存预警
     */
    async fetchLowStockAlert(params = {}) {
      this.lowStockAlert.loading = true
      this.lowStockAlert.error = null

      try {
        const response = await inventoryApi.getLowStockAlert(params)
        
        this.lowStockAlert.data = response.data || response.alerts || []
        this.lowStockAlert.total = response.total || 0
      } catch (error) {
        this.lowStockAlert.error = error.message
        console.error('获取低库存预警失败:', error)
      } finally {
        this.lowStockAlert.loading = false
      }
    },

    /**
     * 获取库存汇总
     */
    async fetchSummary(params = {}) {
      this.summary.loading = true
      this.summary.error = null

      try {
        const response = await inventoryApi.getInventorySummary(params)
        this.summary.data = response.data || response
      } catch (error) {
        this.summary.error = error.message
        console.error('获取库存汇总失败:', error)
      } finally {
        this.summary.loading = false
      }
    },

    /**
     * 调整库存
     */
    async adjustInventory(data) {
      try {
        const response = await inventoryApi.adjustInventory(data)
        
        // 刷新库存列表
        await this.fetchInventoryList()
        
        return response
      } catch (error) {
        console.error('调整库存失败:', error)
        throw error
      }
    },

    /**
     * 设置筛选器
     */
    setFilters(filters) {
      this.filters = { ...this.filters, ...filters }
    },

    /**
     * 设置页码
     */
    setPage(page) {
      this.inventoryList.page = page
    },

    // 注意：getClearanceRanking方法已移除，请使用api.getClearanceRanking()直接调用API
    // 该方法已迁移到frontend/src/api/inventory.js中

    /**
     * 重置状态
     */
    reset() {
      this.inventoryList.data = []
      this.inventoryDetail.data = null
      this.transactions.data = []
      this.lowStockAlert.data = []
      this.summary.data = {}
    }
  }
})


