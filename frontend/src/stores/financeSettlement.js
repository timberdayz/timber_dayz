import { defineStore } from 'pinia'
import financeApi from '@/api/finance'

export const useFinanceSettlementStore = defineStore('finance-settlement', {
  state: () => ({
    profitBasis: {
      data: null,
      loading: false,
      error: null
    },
    monthlyProfitSettlement: {
      data: {
        summary: null,
        personnel_details: [],
        adjustments: []
      },
      loading: false,
      error: null
    }
  }),

  actions: {
    async fetchProfitBasis(params = {}) {
      this.profitBasis.loading = true
      this.profitBasis.error = null
      try {
        const response = await financeApi.getProfitBasis(params)
        this.profitBasis.data = response.data || response
      } catch (error) {
        this.profitBasis.error = error.message
        throw error
      } finally {
        this.profitBasis.loading = false
      }
    },

    async rebuildProfitBasis(data) {
      this.profitBasis.loading = true
      this.profitBasis.error = null
      try {
        const response = await financeApi.rebuildProfitBasis(data)
        this.profitBasis.data = response.data || response
        return response
      } catch (error) {
        this.profitBasis.error = error.message
        throw error
      } finally {
        this.profitBasis.loading = false
      }
    },

    async fetchMonthlyProfitSettlement(params = {}) {
      this.monthlyProfitSettlement.loading = true
      this.monthlyProfitSettlement.error = null
      try {
        const response = await financeApi.getMonthlyProfitSettlement(params)
        this.monthlyProfitSettlement.data = response.data || response
      } catch (error) {
        this.monthlyProfitSettlement.error = error.message
        throw error
      } finally {
        this.monthlyProfitSettlement.loading = false
      }
    },

    async rebuildMonthlyProfitSettlement(data) {
      this.monthlyProfitSettlement.loading = true
      this.monthlyProfitSettlement.error = null
      try {
        const response = await financeApi.rebuildMonthlyProfitSettlement(data)
        this.monthlyProfitSettlement.data = response.data || response
        return response
      } catch (error) {
        this.monthlyProfitSettlement.error = error.message
        throw error
      } finally {
        this.monthlyProfitSettlement.loading = false
      }
    },

    async updateMonthlyProfitSettlementTargets(id, data) {
      this.monthlyProfitSettlement.loading = true
      this.monthlyProfitSettlement.error = null
      try {
        const response = await financeApi.updateMonthlyProfitSettlementTargets(id, data)
        this.monthlyProfitSettlement.data = response.data || response
        return response
      } catch (error) {
        this.monthlyProfitSettlement.error = error.message
        throw error
      } finally {
        this.monthlyProfitSettlement.loading = false
      }
    },

    async approveMonthlyProfitSettlement(id) {
      const response = await financeApi.approveMonthlyProfitSettlement(id)
      if (this.monthlyProfitSettlement.data?.summary?.id === id) {
        this.monthlyProfitSettlement.data.summary.status = 'approved'
        this.monthlyProfitSettlement.data.summary.approved_by = response.data?.approved_by || response.approved_by
      }
      return response
    },

    async reopenMonthlyProfitSettlement(id) {
      const response = await financeApi.reopenMonthlyProfitSettlement(id)
      if (this.monthlyProfitSettlement.data?.summary?.id === id) {
        this.monthlyProfitSettlement.data.summary.status = 'draft'
        this.monthlyProfitSettlement.data.summary.approved_by = null
      }
      return response
    }
  }
})
