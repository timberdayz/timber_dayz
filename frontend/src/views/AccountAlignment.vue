<template>
  <div class="account-alignment">
    <div class="page-header">
      <h1>店铺别名对齐</h1>
      <p>查看 orders 数据域中的未认领店铺别名，并将其认领到现有店铺账号。</p>
    </div>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card>
          <el-statistic title="待认领别名" :value="stats.unmatchedAliases" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="涉及订单数" :value="stats.unmatchedOrders" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="已激活别名" :value="stats.activeAliases" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="可认领店铺账号" :value="stats.availableShopAccounts" />
        </el-card>
      </el-col>
    </el-row>

    <div class="action-buttons">
      <el-button type="primary" size="large" @click="loadData" :loading="loading">
        <el-icon><Refresh /></el-icon>
        刷新数据
      </el-button>
      <el-button
        type="warning"
        size="large"
        :disabled="selectedStores.length === 0"
        @click="openBatchClaimDialog"
      >
        <el-icon><Connection /></el-icon>
        批量认领选中项
      </el-button>
    </div>

    <el-alert
      v-if="!loading && unmatchedStores.length === 0"
      title="当前没有待认领的店铺别名。"
      type="success"
      :closable="false"
      show-icon
      class="summary-alert"
    />

    <el-card class="unaligned-stores">
      <template #header>
        <div class="card-header">
          <span>待认领店铺别名 ({{ unmatchedStores.length }})</span>
          <span class="card-header__meta">数据来源：当前 semantic 订单事实表</span>
        </div>
      </template>

      <el-table
        :data="unmatchedStores"
        @selection-change="handleSelectionChange"
        stripe
        border
        max-height="420"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="site" label="站点" width="110">
          <template #default="{ row }">
            {{ row.site || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="store_label_raw" label="原始店铺别名" min-width="220" show-overflow-tooltip />
        <el-table-column prop="order_count" label="订单数" width="100" sortable />
        <el-table-column prop="paid_amount" label="支付金额" width="140" sortable>
          <template #default="{ row }">
            {{ formatAmount(row.paid_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="建议店铺账号" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="getSuggestedShopAccount(row)">
              {{ formatShopAccountOption(getSuggestedShopAccount(row)) }}
            </span>
            <span v-else class="muted-text">未命中建议，请手动选择</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="openQuickClaimDialog(row)">
              认领
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="configured-aliases">
      <template #header>
        <div class="card-header">
          <span>已激活别名 ({{ configuredAliasesForDisplay.length }})</span>
          <span class="card-header__meta">展示当前已生效的店铺账号别名</span>
        </div>
      </template>

      <el-table
        :data="configuredAliasesForDisplay"
        stripe
        border
        max-height="420"
      >
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="alias_value" label="别名" min-width="220" show-overflow-tooltip />
        <el-table-column label="店铺账号ID" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.shop_account_code }}
          </template>
        </el-table-column>
        <el-table-column label="店铺名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.store_name }}
          </template>
        </el-table-column>
        <el-table-column label="主账号ID" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.main_account_id }}
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="140" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="danger"
              :disabled="!row.shop_account_code || !row.is_primary"
              @click="clearPrimaryAlias(row)"
            >
              清除主别名
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="quickClaimDialogVisible" title="认领店铺别名" width="640px">
      <el-form :model="quickClaimForm" label-width="120px">
        <el-form-item label="平台">
          <el-input v-model="quickClaimForm.platform" disabled />
        </el-form-item>
        <el-form-item label="站点">
          <el-input :value="quickClaimForm.site || '-'" disabled />
        </el-form-item>
        <el-form-item label="原始别名">
          <el-input v-model="quickClaimForm.alias_value" disabled />
        </el-form-item>
        <el-form-item label="订单数">
          <el-input :value="String(quickClaimForm.order_count || 0)" disabled />
        </el-form-item>
        <el-form-item label="支付金额">
          <el-input :value="formatAmount(quickClaimForm.paid_amount)" disabled />
        </el-form-item>
        <el-form-item label="认领到店铺账号" required>
          <el-select
            v-model="quickClaimForm.shop_account_id"
            filterable
            clearable
            placeholder="请选择目标店铺账号"
            class="dialog-select"
          >
            <el-option
              v-for="option in filteredShopAccountOptions(quickClaimForm.platform)"
              :key="option.shop_account_id"
              :label="formatShopAccountOption(option)"
              :value="option.shop_account_id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="quickClaimDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="confirmQuickClaim">
          确认认领
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchClaimDialogVisible" title="批量认领选中别名" width="640px">
      <el-alert
        :title="`将把 ${selectedStores.length} 个别名认领到同一个店铺账号。仅当这些别名确实属于同一店铺时使用。`"
        type="warning"
        :closable="false"
        show-icon
        class="batch-alert"
      />

      <el-form :model="batchClaimForm" label-width="120px">
        <el-form-item label="目标平台">
          <el-input :value="batchClaimPlatformLabel" disabled />
        </el-form-item>
        <el-form-item label="目标店铺账号" required>
          <el-select
            v-model="batchClaimForm.shop_account_id"
            filterable
            clearable
            placeholder="请选择目标店铺账号"
            class="dialog-select"
          >
            <el-option
              v-for="option in filteredShopAccountOptions(batchClaimPlatform)"
              :key="option.shop_account_id"
              :label="formatShopAccountOption(option)"
              :value="option.shop_account_id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="batchClaimDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="confirmBatchClaim">
          确认批量认领
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Connection, Refresh } from '@element-plus/icons-vue'

import accountsApi from '@/api/accounts'

const loading = ref(false)
const saving = ref(false)

const unmatchedStores = ref([])
const configuredAliases = ref([])
const shopAccounts = ref([])
const selectedStores = ref([])

const quickClaimDialogVisible = ref(false)
const batchClaimDialogVisible = ref(false)

const quickClaimForm = ref({
  platform: '',
  site: '',
  alias_value: '',
  order_count: 0,
  paid_amount: 0,
  shop_account_id: '',
})

const batchClaimForm = ref({
  shop_account_id: '',
})

const shopAccountByDbId = computed(() => {
  return new Map(shopAccounts.value.map((item) => [item.id, item]))
})

const configuredAliasesForDisplay = computed(() => {
  return configuredAliases.value
    .filter((item) => item.is_active)
    .map((item) => {
      const shopAccount = shopAccountByDbId.value.get(item.shop_account_id)
      return {
        ...item,
        shop_account_code: shopAccount?.shop_account_id || '',
        store_name: shopAccount?.store_name || '-',
        main_account_id: shopAccount?.main_account_id || '-',
      }
    })
})

const stats = computed(() => {
  const unmatchedOrders = unmatchedStores.value.reduce((sum, item) => {
    return sum + Number(item.order_count || 0)
  }, 0)

  return {
    unmatchedAliases: unmatchedStores.value.length,
    unmatchedOrders,
    activeAliases: configuredAliasesForDisplay.value.length,
    availableShopAccounts: shopAccounts.value.filter((item) => item.enabled).length,
  }
})

const batchClaimPlatform = computed(() => {
  const platforms = Array.from(new Set(selectedStores.value.map((item) => item.platform).filter(Boolean)))
  return platforms.length === 1 ? platforms[0] : ''
})

const batchClaimPlatformLabel = computed(() => batchClaimPlatform.value || '包含多个平台')

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

function normalizeLooseText(value) {
  return normalizeText(value).replace(/[\s_\-()/]+/g, '')
}

function formatAmount(value) {
  return Number(value || 0).toFixed(2)
}

function formatDateTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

function formatShopAccountOption(option) {
  const parts = [
    option.platform,
    option.store_name || option.account_alias || option.shop_account_id,
    option.shop_account_id,
  ].filter(Boolean)
  return parts.join(' / ')
}

function filteredShopAccountOptions(platform) {
  const normalizedPlatform = normalizeText(platform)
  return shopAccounts.value.filter((item) => {
    if (!item.enabled) return false
    if (!normalizedPlatform) return true
    return normalizeText(item.platform) === normalizedPlatform
  })
}

function getSuggestedShopAccount(unmatchedItem) {
  const options = filteredShopAccountOptions(unmatchedItem.platform)
  const aliasKey = normalizeLooseText(unmatchedItem.store_label_raw)

  if (!aliasKey) {
    return null
  }

  const exactMatch = options.find((item) => {
    return [
      item.account_alias,
      item.store_name,
      item.shop_account_id,
    ].some((candidate) => normalizeLooseText(candidate) === aliasKey)
  })
  if (exactMatch) return exactMatch

  const partialMatch = options.find((item) => {
    return [
      item.account_alias,
      item.store_name,
      item.shop_account_id,
    ].some((candidate) => {
      const normalizedCandidate = normalizeLooseText(candidate)
      return normalizedCandidate && (
        normalizedCandidate.includes(aliasKey) || aliasKey.includes(normalizedCandidate)
      )
    })
  })

  return partialMatch || null
}

async function loadData() {
  loading.value = true
  try {
    const [unmatchedResponse, aliasResponse, shopAccountResponse] = await Promise.all([
      accountsApi.getUnmatchedShopAliases(),
      accountsApi.listShopAccountAliases(),
      accountsApi.listShopAccounts(),
    ])

    unmatchedStores.value = unmatchedResponse?.items || []
    configuredAliases.value = aliasResponse || []
    shopAccounts.value = (shopAccountResponse || []).map((item) => ({
      ...item,
      id: Number(item.id),
    }))
    selectedStores.value = []
  } catch (error) {
    console.error('加载店铺别名对齐数据失败:', error)
    ElMessage.error('加载店铺别名对齐数据失败')
  } finally {
    loading.value = false
  }
}

function handleSelectionChange(selection) {
  selectedStores.value = selection
}

function openQuickClaimDialog(store) {
  const suggestedShopAccount = getSuggestedShopAccount(store)
  quickClaimForm.value = {
    platform: store.platform,
    site: store.site || '',
    alias_value: store.store_label_raw,
    order_count: Number(store.order_count || 0),
    paid_amount: Number(store.paid_amount || 0),
    shop_account_id: suggestedShopAccount?.shop_account_id || '',
  }
  quickClaimDialogVisible.value = true
}

async function confirmQuickClaim() {
  if (!quickClaimForm.value.shop_account_id) {
    ElMessage.warning('请选择目标店铺账号')
    return
  }

  saving.value = true
  try {
    await accountsApi.claimShopAccountAlias({
      platform: quickClaimForm.value.platform,
      alias_value: quickClaimForm.value.alias_value,
      shop_account_id: quickClaimForm.value.shop_account_id,
    })
    ElMessage.success('店铺别名认领成功')
    quickClaimDialogVisible.value = false
    await loadData()
  } catch (error) {
    console.error('认领店铺别名失败:', error)
    ElMessage.error(error.response?.data?.detail || '认领店铺别名失败')
  } finally {
    saving.value = false
  }
}

function openBatchClaimDialog() {
  if (selectedStores.value.length === 0) {
    ElMessage.warning('请先选择待认领项')
    return
  }

  const platforms = new Set(selectedStores.value.map((item) => item.platform))
  if (platforms.size > 1) {
    ElMessage.warning('批量认领仅支持同一平台的别名')
    return
  }

  const suggestedShopAccount = getSuggestedShopAccount(selectedStores.value[0])
  batchClaimForm.value = {
    shop_account_id: suggestedShopAccount?.shop_account_id || '',
  }
  batchClaimDialogVisible.value = true
}

async function confirmBatchClaim() {
  if (!batchClaimForm.value.shop_account_id) {
    ElMessage.warning('请选择目标店铺账号')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认将 ${selectedStores.value.length} 个别名认领到 ${batchClaimForm.value.shop_account_id} 吗？`,
      '确认批量认领',
      { type: 'warning' }
    )
  } catch {
    return
  }

  saving.value = true
  try {
    await Promise.all(
      selectedStores.value.map((item) =>
        accountsApi.claimShopAccountAlias({
          platform: item.platform,
          alias_value: item.store_label_raw,
          shop_account_id: batchClaimForm.value.shop_account_id,
        })
      )
    )
    ElMessage.success('批量认领完成')
    batchClaimDialogVisible.value = false
    await loadData()
  } catch (error) {
    console.error('批量认领失败:', error)
    ElMessage.error(error.response?.data?.detail || '批量认领失败')
  } finally {
    saving.value = false
  }
}

async function clearPrimaryAlias(row) {
  if (!row.shop_account_code) {
    ElMessage.warning('未找到对应的店铺账号ID')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认清除 ${row.shop_account_code} 的主别名吗？`,
      '确认清除',
      { type: 'warning' }
    )
  } catch {
    return
  }

  saving.value = true
  try {
    await accountsApi.clearShopAccountPrimaryAlias(row.shop_account_code)
    ElMessage.success('主别名已清除')
    await loadData()
  } catch (error) {
    console.error('清除主别名失败:', error)
    ElMessage.error(error.response?.data?.detail || '清除主别名失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.account-alignment {
  padding: var(--content-padding);
}

.page-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
  background: linear-gradient(135deg, #4f6bdc 0%, #7756b8 100%);
  color: white;
  padding: var(--spacing-2xl);
  border-radius: var(--border-radius-lg);
}

.page-header h1 {
  margin: 0 0 var(--spacing-base) 0;
  font-size: var(--font-size-4xl);
}

.page-header p {
  margin: 0;
}

.stats-row {
  margin-bottom: var(--spacing-xl);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-base);
  margin-bottom: var(--spacing-xl);
  justify-content: center;
}

.summary-alert,
.unaligned-stores,
.configured-aliases {
  margin-bottom: var(--spacing-xl);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.card-header__meta {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.dialog-select {
  width: 100%;
}

.batch-alert {
  margin-bottom: 16px;
}

.muted-text {
  color: var(--el-text-color-secondary);
}
</style>
