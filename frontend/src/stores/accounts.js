import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import accountsApi from '@/api/accounts'

export const useAccountsStore = defineStore('accounts', {
  state: () => ({
    accounts: [],
    unmatchedShopAliases: [],
    stats: {
      total: 0,
      active: 0,
      inactive: 0,
      platforms: 0,
      platform_breakdown: {}
    },
    loading: false,
    filters: {
      platform: null,
      enabled: null,
      shop_type: null,
      search: ''
    }
  }),

  getters: {
    platformList: (state) => {
      const platforms = new Set(state.accounts.map((account) => account.platform))
      return Array.from(platforms).sort()
    },

    accountsByPlatform: (state) => {
      const groups = {}
      state.accounts.forEach((account) => {
        if (!groups[account.platform]) {
          groups[account.platform] = []
        }
        groups[account.platform].push(account)
      })
      return groups
    },

    activeAccounts: (state) => state.accounts.filter((account) => account.enabled)
  },

  actions: {
    async loadAccounts(params = {}, showLoading = true) {
      if (this.loading && showLoading) {
        return
      }

      if (showLoading) {
        this.loading = true
      }

      try {
        const mergedParams = { ...this.filters, ...params }
        const apiTimeout = 10000

        this.accounts = await Promise.race([
          accountsApi.listAccounts(mergedParams),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('加载账号列表超时')), apiTimeout)
          )
        ])
      } catch (error) {
        if (error.message !== '加载账号列表超时') {
          console.error('加载账号列表失败:', error)
          if (showLoading) {
            ElMessage.error('加载账号列表失败')
          }
        } else {
          console.warn('加载账号列表超时，但可能仍在后台加载')
        }
        throw error
      } finally {
        if (showLoading) {
          this.loading = false
        }
      }
    },

    async loadStats() {
      try {
        const apiTimeout = 10000
        this.stats = await Promise.race([
          accountsApi.getStats(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('加载统计数据超时')), apiTimeout)
          )
        ])
      } catch (error) {
        if (error.message !== '加载统计数据超时') {
          console.error('加载统计数据失败:', error)
        } else {
          console.warn('加载统计数据超时，但可能仍在后台加载')
        }
      }
    },

    async loadUnmatchedShopAliases() {
      try {
        const apiTimeout = 10000
        const response = await Promise.race([
          accountsApi.getUnmatchedShopAliases(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('加载未匹配店铺别名超时')), apiTimeout)
          )
        ])
        this.unmatchedShopAliases = response.items || []
      } catch (error) {
        if (error.message !== '加载未匹配店铺别名超时') {
          console.error('加载未匹配店铺别名失败:', error)
        } else {
          console.warn('加载未匹配店铺别名超时，但可能仍在后台加载')
        }
      }
    },

    async createAccount(data) {
      this.loading = true
      try {
        const newAccount = await accountsApi.createAccount(data)
        this.accounts.unshift(newAccount)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success('账号创建成功')
        return newAccount
      } catch (error) {
        console.error('创建账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '创建账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateAccount(accountId, data) {
      this.loading = true
      try {
        const updatedAccount = await accountsApi.updateAccount(accountId, data)
        const index = this.accounts.findIndex((account) => account.account_id === accountId)
        if (index !== -1) {
          this.accounts[index] = updatedAccount
        }
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success('账号更新成功')
        return updatedAccount
      } catch (error) {
        console.error('更新账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '更新账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteAccount(accountId) {
      this.loading = true
      try {
        await accountsApi.deleteAccount(accountId)
        this.accounts = this.accounts.filter((account) => account.account_id !== accountId)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success('账号删除成功')
      } catch (error) {
        console.error('删除账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '删除账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    async batchCreate(batchData) {
      this.loading = true
      try {
        const newAccounts = await accountsApi.batchCreate(batchData)
        this.accounts.unshift(...newAccounts)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success(`成功创建 ${newAccounts.length} 个账号`)
        return newAccounts
      } catch (error) {
        console.error('批量创建失败:', error)
        ElMessage.error(error.response?.data?.detail || '批量创建失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    setFilters(filters) {
      this.filters = { ...this.filters, ...filters }
    },

    clearFilters() {
      this.filters = {
        platform: null,
        enabled: null,
        shop_type: null,
        search: ''
      }
    }
  }
})
