import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import accountsApi from '@/api/accounts'

function normalizeShopAccount(shopAccount) {
  return {
    ...shopAccount,
    account_id: shopAccount.shop_account_id,
    parent_account: shopAccount.main_account_id,
    account_alias: shopAccount.account_alias || '',
    shop_id: shopAccount.platform_shop_id || '',
    shop_account_id: shopAccount.shop_account_id,
    main_account_id: shopAccount.main_account_id,
    platform_shop_id: shopAccount.platform_shop_id || '',
    platform_shop_id_status: shopAccount.platform_shop_id_status || 'missing',
    capabilities: shopAccount.capabilities || {},
  }
}

function resolveMainAccountId(payload) {
  return String(payload.parent_account || payload.account_id || '').trim()
}

function resolveMainAccountName(payload) {
  return String(payload.main_account_name || '').trim()
}

function normalizeAliasValue(value) {
  return String(value || '').trim()
}

export const useAccountsStore = defineStore('accounts', {
  state: () => ({
    accounts: [],
    mainAccounts: [],
    pendingPlatformShopDiscoveries: [],
    currentDiscoveryResult: null,
    currentDiscoveryError: '',
    discoveryRunning: false,
    unmatchedShopAliases: [],
    stats: {
      total: 0,
      active: 0,
      inactive: 0,
      platforms: 0,
      platform_breakdown: {},
    },
    loading: false,
    filters: {
      platform: null,
      enabled: null,
      shop_type: null,
      search: '',
    },
  }),

  getters: {
    platformList: (state) => {
      const platforms = new Set(state.accounts.map((account) => account.platform))
      return Array.from(platforms).sort()
    },

    activeAccounts: (state) => state.accounts.filter((account) => account.enabled),
  },

  actions: {
    async syncAccountAlias(platform, shopAccountId, aliasValue) {
      const normalizedAlias = normalizeAliasValue(aliasValue)
      if (normalizedAlias) {
        await accountsApi.claimShopAccountAlias({
          platform,
          alias_value: normalizedAlias,
          shop_account_id: shopAccountId,
        })
        return
      }

      await accountsApi.clearShopAccountPrimaryAlias(shopAccountId)
    },

    async loadAccounts(params = {}, showLoading = true) {
      if (this.loading && showLoading) return
      if (showLoading) this.loading = true

      try {
        const mergedParams = { ...this.filters, ...params }
        const defaultEnabled = mergedParams.include_disabled ? mergedParams.enabled : true
        const [shopAccounts, mainAccounts, pendingDiscoveries] = await Promise.all([
          accountsApi.listShopAccounts({
            ...mergedParams,
            enabled: defaultEnabled,
          }),
          accountsApi.listMainAccounts(),
          accountsApi.listPlatformShopDiscoveries(),
        ])
        this.accounts = (shopAccounts || []).map(normalizeShopAccount)
        this.mainAccounts = (mainAccounts || []).filter((item) =>
          mergedParams.include_disabled ? true : item.enabled
        )
        this.pendingPlatformShopDiscoveries = pendingDiscoveries || []
      } catch (error) {
        console.error('加载店铺账号列表失败:', error)
        if (showLoading) {
          ElMessage.error('加载店铺账号列表失败')
        }
        throw error
      } finally {
        if (showLoading) this.loading = false
      }
    },

    async loadStats() {
      try {
        this.stats = await accountsApi.getStats()
      } catch (error) {
        console.error('加载统计数据失败:', error)
      }
    },

    async loadUnmatchedShopAliases() {
      try {
        const response = await accountsApi.getUnmatchedShopAliases()
        this.unmatchedShopAliases = response.items || []
      } catch (error) {
        console.error('加载未匹配店铺别名失败:', error)
      }
    },

    async runCurrentShopDiscovery(mainAccountId, payload = {}) {
      this.discoveryRunning = true
      this.currentDiscoveryError = ''
      try {
        const response = await accountsApi.runCurrentShopDiscovery(mainAccountId, payload)
        this.currentDiscoveryResult = response
        await this.loadAccounts({}, false)
        return response
      } catch (error) {
        this.currentDiscoveryResult = null
        this.currentDiscoveryError = error.response?.data?.detail || error.message || '店铺探测失败'
        throw error
      } finally {
        this.discoveryRunning = false
      }
    },

    async createShopAccountFromDiscovery(discoveryId, payload) {
      this.discoveryRunning = true
      this.currentDiscoveryError = ''
      try {
        const response = await accountsApi.createShopAccountFromDiscovery(discoveryId, payload)
        await this.loadAccounts({}, false)
        await this.loadStats()
        return response
      } catch (error) {
        this.currentDiscoveryError = error.response?.data?.detail || error.message || '基于探测创建店铺账号失败'
        throw error
      } finally {
        this.discoveryRunning = false
      }
    },

    async createAccount(data) {
      this.loading = true
      try {
        const mainAccountId = resolveMainAccountId(data)
        const existingMain = this.mainAccounts.find(
          (item) => item.platform === data.platform && item.main_account_id === mainAccountId
        )
        if (!existingMain) {
          await accountsApi.createMainAccount({
            platform: data.platform,
            main_account_id: mainAccountId,
            main_account_name: resolveMainAccountName(data) || null,
            username: data.username,
            password: data.password,
            login_url: data.login_url,
            enabled: data.enabled,
            notes: data.notes,
          })
        }

        const newAccount = await accountsApi.createShopAccount({
          platform: data.platform,
          shop_account_id: data.account_id,
          main_account_id: mainAccountId,
          store_name: data.store_name,
          platform_shop_id: data.shop_id || null,
          shop_region: data.shop_region,
          shop_type: data.shop_type,
          capabilities: data.capabilities,
          enabled: data.enabled,
          notes: data.notes,
        })

        await this.syncAccountAlias(data.platform, data.account_id, data.account_alias)

        await this.loadAccounts({}, false)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success('店铺账号创建成功')
        return normalizeShopAccount(newAccount)
      } catch (error) {
        console.error('创建店铺账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '创建店铺账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateAccount(accountId, data) {
      this.loading = true
      try {
        const current = this.accounts.find((account) => account.account_id === accountId)
        if (!current) throw new Error(`店铺账号 ${accountId} 不存在`)

        await accountsApi.updateShopAccount(accountId, {
          store_name: data.store_name,
          platform_shop_id: data.shop_id || null,
          platform_shop_id_status: data.shop_id ? 'manual_confirmed' : current.platform_shop_id_status,
          shop_region: data.shop_region,
          shop_type: data.shop_type,
          capabilities: data.capabilities,
          enabled: data.enabled,
          notes: data.notes,
        })

        if (current.parent_account) {
          const mainPayload = {}
          if (data.main_account_name !== undefined) mainPayload.main_account_name = data.main_account_name
          if (data.username) mainPayload.username = data.username
          if (data.password) mainPayload.password = data.password
          if (data.login_url !== undefined) mainPayload.login_url = data.login_url
          if (data.enabled !== undefined) mainPayload.enabled = data.enabled
          if (data.notes !== undefined) mainPayload.notes = data.notes
          if (Object.keys(mainPayload).length > 0) {
            await accountsApi.updateMainAccount(current.parent_account, mainPayload)
          }
        }

        if (data.account_alias !== undefined && normalizeAliasValue(data.account_alias) !== normalizeAliasValue(current.account_alias)) {
          await this.syncAccountAlias(current.platform, accountId, data.account_alias)
        }

        await this.loadAccounts({}, false)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success('店铺账号更新成功')
      } catch (error) {
        console.error('更新店铺账号失败:', error)
        ElMessage.error(error.response?.data?.detail || error.message || '更新店铺账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteAccount(accountId) {
      this.loading = true
      try {
        await accountsApi.deleteShopAccount(accountId)
        this.accounts = this.accounts.filter((account) => account.account_id !== accountId)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success('店铺账号删除成功')
      } catch (error) {
        console.error('删除店铺账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '删除店铺账号失败')
        throw error
      } finally {
        this.loading = false
      }
    },

    async batchCreate(batchData) {
      this.loading = true
      try {
        const existingMain = this.mainAccounts.find(
          (item) => item.platform === batchData.platform && item.main_account_id === batchData.parent_account
        )
        if (!existingMain) {
          await accountsApi.createMainAccount({
            platform: batchData.platform,
            main_account_id: batchData.parent_account,
            main_account_name: batchData.main_account_name || null,
            username: batchData.username,
            password: batchData.password,
            enabled: true,
          })
        }

        const payloads = batchData.shops.map((shop) => ({
          platform: batchData.platform,
          shop_account_id: `${batchData.platform}_${(shop.shop_region || 'unknown').toLowerCase()}_${String(shop.store_name || 'shop').replace(/\s+/g, '_').toLowerCase()}`,
          main_account_id: batchData.parent_account,
          store_name: shop.store_name,
          shop_region: shop.shop_region,
          shop_type: shop.shop_type || 'local',
          enabled: true,
        }))

        const created = await accountsApi.batchCreateShopAccounts(payloads)

        for (const shop of batchData.shops) {
          const generatedShopAccountId = `${batchData.platform}_${(shop.shop_region || 'unknown').toLowerCase()}_${String(shop.store_name || 'shop').replace(/\s+/g, '_').toLowerCase()}`
          await this.syncAccountAlias(batchData.platform, generatedShopAccountId, shop.account_alias)
        }

        await this.loadAccounts({}, false)
        await this.loadStats()
        await this.loadUnmatchedShopAliases()
        ElMessage.success(`成功创建 ${created.length} 个店铺账号`)
        return created.map(normalizeShopAccount)
      } catch (error) {
        console.error('批量创建店铺账号失败:', error)
        ElMessage.error(error.response?.data?.detail || '批量创建店铺账号失败')
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
        search: '',
      }
    },
  },
})
