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
        follow_details: [],
        adjustments: []
      },
      loading: false,
      error: null
    },
    followInvestmentSettlement: {
      data: {
        settlement: null,
        details: []
      },
      loading: false,
      error: null
    },
    followInvestments: {
      data: [],
      loading: false,
      error: null
    },
    followInvestmentSettlements: {
      data: [],
      loading: false,
      error: null
    },
    followInvestmentSettlementDetails: {
      data: [],
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
    },

    async calculateFollowInvestmentSettlement(data) {
      this.followInvestmentSettlement.loading = true
      this.followInvestmentSettlement.error = null
      try {
        const response = await financeApi.calculateFollowInvestmentSettlement(data)
        this.followInvestmentSettlement.data = response.data || response
        return response
      } catch (error) {
        this.followInvestmentSettlement.error = error.message
        throw error
      } finally {
        this.followInvestmentSettlement.loading = false
      }
    },

    async fetchFollowInvestments(params = {}) {
      this.followInvestments.loading = true
      this.followInvestments.error = null
      try {
        const response = await financeApi.getFollowInvestments(params)
        this.followInvestments.data = response.data || response || []
      } catch (error) {
        this.followInvestments.error = error.message
        throw error
      } finally {
        this.followInvestments.loading = false
      }
    },

    async createFollowInvestment(data) {
      const response = await financeApi.createFollowInvestment(data)
      await this.fetchFollowInvestments({
        platform_code: data.platform_code,
        shop_id: data.shop_id
      })
      return response
    },

    async updateFollowInvestment(id, data, filters = {}) {
      const response = await financeApi.updateFollowInvestment(id, data)
      await this.fetchFollowInvestments(filters)
      return response
    },

    async archiveFollowInvestment(id, filters = {}) {
      const response = await financeApi.archiveFollowInvestment(id)
      await this.fetchFollowInvestments(filters)
      return response
    },

    async approveFollowInvestmentSettlement(id) {
      const response = await financeApi.approveFollowInvestmentSettlement(id)
      if (this.followInvestmentSettlement.data?.settlement?.id === id) {
        this.followInvestmentSettlement.data.settlement.status = 'approved'
      }
      return response
    },

    async reopenFollowInvestmentSettlement(id) {
      const response = await financeApi.reopenFollowInvestmentSettlement(id)
      if (this.followInvestmentSettlement.data?.settlement?.id === id) {
        this.followInvestmentSettlement.data.settlement.status = 'reopened'
      }
      return response
    },

    async fetchFollowInvestmentSettlements(params = {}) {
      this.followInvestmentSettlements.loading = true
      this.followInvestmentSettlements.error = null
      try {
        const response = await financeApi.getFollowInvestmentSettlements(params)
        this.followInvestmentSettlements.data = response.data || response || []
      } catch (error) {
        this.followInvestmentSettlements.error = error.message
        throw error
      } finally {
        this.followInvestmentSettlements.loading = false
      }
    },

    async fetchFollowInvestmentSettlementDetails(id) {
      this.followInvestmentSettlementDetails.loading = true
      this.followInvestmentSettlementDetails.error = null
      try {
        const response = await financeApi.getFollowInvestmentSettlementDetails(id)
        this.followInvestmentSettlementDetails.data = response.data || response || []
      } catch (error) {
        this.followInvestmentSettlementDetails.error = error.message
        throw error
      } finally {
        this.followInvestmentSettlementDetails.loading = false
      }
    }
  }
})
