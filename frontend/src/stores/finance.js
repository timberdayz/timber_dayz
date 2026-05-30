import { defineStore } from 'pinia'
import financeApi from '@/api/finance'

export const useFinanceStore = defineStore('finance', {
  state: () => ({
    accountsReceivable: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },
    paymentReceipts: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },
    expenses: {
      data: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null
    },
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
    overdueAlert: {
      data: [],
      total: 0,
      loading: false,
      error: null
    },
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
    cashFlow: {
      data: [],
      loading: false,
      error: null
    },
    filters: {
      platform: null,
      shopId: null,
      status: null,
      startDate: null,
      endDate: null
    }
  }),

  getters: {
    isLoading: (state) => {
      return state.accountsReceivable.loading ||
        state.paymentReceipts.loading ||
        state.profitReport.loading ||
        state.overview.loading
    },

    totalOverdueAmount: (state) => {
      return state.overdueAlert.data.reduce((sum, item) => sum + (item.outstanding_amount_cny || 0), 0)
    },

    totalARAmount: (state) => {
      return state.accountsReceivable.data.reduce((sum, item) => sum + (item.ar_amount_cny || 0), 0)
    }
  },

  actions: {
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

    async recordPayment(data) {
      try {
        const response = await financeApi.recordPayment(data)
        await this.fetchAccountsReceivable()
        return response
      } catch (error) {
        console.error('记录收款失败:', error)
        throw error
      }
    },

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

    setFilters(filters) {
      this.filters = { ...this.filters, ...filters }
    },

    setPage(page, listType = 'accountsReceivable') {
      this[listType].page = page
    },

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
