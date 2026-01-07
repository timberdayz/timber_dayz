/**
 * 财务管理状态管理 (Pinia Store)
 */

import { defineStore } from 'pinia'
import financeApi from '@/api/finance'

export const useFinanceStore = defineStore('finance', {
  state: () => ({
    // 应收账款
    accountsReceivable: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 收款记录
    paymentReceipts: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 费用列表
    expenses: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },

    // 利润报表
    profitReport: {
      data: {
        totalRevenue: 0,
        totalCost: 0,
        totalExpense: 0,
        grossProfit: 0,
        netProfit: 0,
        profitMargin: 0,
        details: []
      },
      loading: false,
      error: null
    },

    // 逾期预警
    overdueAlert: {
      data: [],
      total: 0,
      loading: false,
      error: null
    },

    // 财务总览
    overview: {
      data: {
        totalAR: 0,
        totalReceived: 0,
        totalOutstanding: 0,
        overdueAmount: 0,
        totalExpense: 0
      },
      loading: false,
      error: null
    },

    // 现金流分析
    cashFlow: {
      data: [],
      loading: false,
      error: null
    },

    // 筛选器
    filters: {
      platform: null,
      shopId: null,
      status: null,
      startDate: null,
      endDate: null
    }
  }),

  getters: {
    /**
     * 是否有任何数据正在加载
     */
    isLoading: (state) => {
      return state.accountsReceivable.loading ||
             state.paymentReceipts.loading ||
             state.profitReport.loading ||
             state.overview.loading
    },

    /**
     * 逾期总金额
     */
    totalOverdueAmount: (state) => {
      return state.overdueAlert.data.reduce((sum, item) => {
        return sum + (item.outstanding_amount_cny || 0)
      }, 0)
    },

    /**
     * 应收账款总额
     */
    totalARAmount: (state) => {
      return state.accountsReceivable.data.reduce((sum, item) => {
        return sum + (item.ar_amount_cny || 0)
      }, 0)
    }
  },

  actions: {
    /**
     * 获取应收账款列表
     */
    async fetchAccountsReceivable(params = {}) {
      this.accountsReceivable.loading = true
      this.accountsReceivable.error = null

      try {
        const queryParams = {
          ...this.filters,
          ...params,
          page: this.accountsReceivable.page,
          pageSize: this.accountsReceivable.pageSize
        }

        const response = await financeApi.getAccountsReceivable(queryParams)
        
        this.accountsReceivable.data = response.data || response.items || []
        this.accountsReceivable.total = response.total || 0
      } catch (error) {
        this.accountsReceivable.error = error.message
        console.error('获取应收账款失败:', error)
      } finally {
        this.accountsReceivable.loading = false
      }
    },

    /**
     * 获取收款记录
     */
    async fetchPaymentReceipts(params = {}) {
      this.paymentReceipts.loading = true
      this.paymentReceipts.error = null

      try {
        const queryParams = {
          ...params,
          page: this.paymentReceipts.page,
          pageSize: this.paymentReceipts.pageSize
        }

        const response = await financeApi.getPaymentReceipts(queryParams)
        
        this.paymentReceipts.data = response.data || response.items || []
        this.paymentReceipts.total = response.total || 0
      } catch (error) {
        this.paymentReceipts.error = error.message
        console.error('获取收款记录失败:', error)
      } finally {
        this.paymentReceipts.loading = false
      }
    },

    /**
     * 记录收款
     */
    async recordPayment(data) {
      try {
        const response = await financeApi.recordPayment(data)
        
        // 刷新应收账款列表
        await this.fetchAccountsReceivable()
        
        return response
      } catch (error) {
        console.error('记录收款失败:', error)
        throw error
      }
    },

    /**
     * 获取费用列表
     */
    async fetchExpenses(params = {}) {
      this.expenses.loading = true
      this.expenses.error = null

      try {
        const queryParams = {
          ...this.filters,
          ...params,
          page: this.expenses.page,
          pageSize: this.expenses.pageSize
        }

        const response = await financeApi.getExpenses(queryParams)
        
        this.expenses.data = response.data || response.items || []
        this.expenses.total = response.total || 0
      } catch (error) {
        this.expenses.error = error.message
        console.error('获取费用列表失败:', error)
      } finally {
        this.expenses.loading = false
      }
    },

    /**
     * 获取利润报表
     */
    async fetchProfitReport(params = {}) {
      this.profitReport.loading = true
      this.profitReport.error = null

      try {
        const queryParams = { ...this.filters, ...params }
        const response = await financeApi.getProfitReport(queryParams)
        
        this.profitReport.data = response.data || response
      } catch (error) {
        this.profitReport.error = error.message
        console.error('获取利润报表失败:', error)
      } finally {
        this.profitReport.loading = false
      }
    },

    /**
     * 获取逾期预警
     */
    async fetchOverdueAlert(params = {}) {
      this.overdueAlert.loading = true
      this.overdueAlert.error = null

      try {
        const response = await financeApi.getOverdueAlert(params)
        
        this.overdueAlert.data = response.data || response.alerts || []
        this.overdueAlert.total = response.total || 0
      } catch (error) {
        this.overdueAlert.error = error.message
        console.error('获取逾期预警失败:', error)
      } finally {
        this.overdueAlert.loading = false
      }
    },

    /**
     * 获取财务总览
     */
    async fetchOverview(params = {}) {
      this.overview.loading = true
      this.overview.error = null

      try {
        const queryParams = { ...this.filters, ...params }
        const response = await financeApi.getFinancialOverview(queryParams)
        
        this.overview.data = response.data || response
      } catch (error) {
        this.overview.error = error.message
        console.error('获取财务总览失败:', error)
      } finally {
        this.overview.loading = false
      }
    },

    /**
     * 获取现金流分析
     */
    async fetchCashFlow(params = {}) {
      this.cashFlow.loading = true
      this.cashFlow.error = null

      try {
        const response = await financeApi.getCashFlowAnalysis(params)
        
        this.cashFlow.data = response.data || response.cashflow || []
      } catch (error) {
        this.cashFlow.error = error.message
        console.error('获取现金流分析失败:', error)
      } finally {
        this.cashFlow.loading = false
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
    setPage(page, listType = 'accountsReceivable') {
      this[listType].page = page
    },

    /**
     * 重置状态
     */
    reset() {
      this.accountsReceivable.data = []
      this.paymentReceipts.data = []
      this.expenses.data = []
      this.profitReport.data = {}
      this.overdueAlert.data = []
      this.overview.data = {}
      this.cashFlow.data = []
    }
  }
})


