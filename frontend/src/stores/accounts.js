/**
 * 账号管理Store (v4.7.0)
 * 
 * 使用Pinia管理账号状态
 */

import { defineStore } from 'pinia'
import accountsApi from '@/api/accounts'
import { ElMessage } from 'element-plus'

export const useAccountsStore = defineStore('accounts', {
  state: () => ({
    accounts: [],
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
    /**
     * 获取平台列表
     */
    platformList: (state) => {
      const platforms = new Set(state.accounts.map(a => a.platform))
      return Array.from(platforms).sort()
    },

    /**
     * 根据平台分组的账号
     */
    accountsByPlatform: (state) => {
      const groups = {}
      state.accounts.forEach(account => {
        const platform = account.platform
        if (!groups[platform]) {
          groups[platform] = []
        }
        groups[platform].push(account)
      })
      return groups
    },

    /**
     * 活跃账号列表
     */
    activeAccounts: (state) => {
      return state.accounts.filter(a => a.enabled)
    }
  },

  actions: {
    /**
     * 加载账号列表
     * ⭐ v4.19.0修复：添加超时机制和后台刷新支持，避免数据同步期间阻塞
     */
    async loadAccounts(params = {}, showLoading = true) {
      // 防重复加载
      if (this.loading && showLoading) {
        return
      }

      if (showLoading) {
        this.loading = true
      }

      try {
        const mergedParams = { ...this.filters, ...params }
        
        // ⭐ v4.19.0新增：添加超时机制，避免长时间阻塞
        const API_TIMEOUT = 10000 // 10秒超时
        
        this.accounts = await Promise.race([
          accountsApi.listAccounts(mergedParams),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('加载账号列表超时')), API_TIMEOUT)
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

    /**
     * 加载统计数据
     * ⭐ v4.19.0修复：添加超时机制，避免数据同步期间阻塞
     */
    async loadStats(showLoading = false) {
      try {
        // ⭐ v4.19.0新增：添加超时机制
        const API_TIMEOUT = 10000 // 10秒超时
        
        this.stats = await Promise.race([
          accountsApi.getStats(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('加载统计数据超时')), API_TIMEOUT)
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

    /**
     * 创建账号
     */
    async createAccount(data) {
      this.loading = true
      try {
        const newAccount = await accountsApi.createAccount(data)
        this.accounts.unshift(newAccount)
        await this.loadStats()
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

    /**
     * 更新账号
     */
    async updateAccount(accountId, data) {
      this.loading = true
      try {
        const updatedAccount = await accountsApi.updateAccount(accountId, data)
        const index = this.accounts.findIndex(a => a.account_id === accountId)
        if (index !== -1) {
          this.accounts[index] = updatedAccount
        }
        await this.loadStats()
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

    /**
     * 删除账号
     */
    async deleteAccount(accountId) {
      this.loading = true
      try {
        await accountsApi.deleteAccount(accountId)
        this.accounts = this.accounts.filter(a => a.account_id !== accountId)
        await this.loadStats()
        ElMessage.success('账号删除成功')
      } catch (error) {
        console.error('删除账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '删除账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * 批量创建账号
     */
    async batchCreate(batchData) {
      this.loading = true
      try {
        const newAccounts = await accountsApi.batchCreate(batchData)
        this.accounts.unshift(...newAccounts)
        await this.loadStats()
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

    /**
     * 从local_accounts.py导入
     */
    async importFromLocal() {
      this.loading = true
      try {
        const result = await accountsApi.importFromLocal()
        await this.loadAccounts()
        await this.loadStats()
        ElMessage.success(result.message)
        return result
      } catch (error) {
        console.error('导入失败:', error)
        ElMessage.error(error.response?.data?.detail || '导入失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * 更新筛选条件
     */
    setFilters(filters) {
      this.filters = { ...this.filters, ...filters }
    },

    /**
     * 清空筛选条件
     */
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
