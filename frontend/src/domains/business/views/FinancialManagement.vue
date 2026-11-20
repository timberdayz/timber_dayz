<template>
  <div class="financial-management">
    <div class="page-header">
      <h1>财务结算中心</h1>
      <p>先确认公司月结，再按平台切换店铺核对单店利润口径。</p>
    </div>

    <el-alert
      class="page-alert"
      type="info"
      :closable="false"
      show-icon
      title="建议先确认利润基准、店铺提成和工资，再进行月度利润结算审批。"
    />

    <MonthlySettlementPanel
      :monthly-form="monthlyForm"
      :loading="settlementStore.monthlyProfitSettlement.loading"
      :error="settlementStore.monthlyProfitSettlement.error"
      :current-settlement-id="currentSettlementId"
      :monthly-summary="monthlySummary"
      :show-settlement-difference-warning="showSettlementDifferenceWarning"
      :format-currency="formatCurrency"
      :format-percent-value="formatPercentValue"
      :format-ratio-input="formatRatioInput"
      :parse-ratio-input="parseRatioInput"
      @load-monthly="loadMonthlySettlement"
      @rebuild-monthly="rebuildMonthlySettlement"
      @save-monthly-targets="saveMonthlyTargets"
      @approve-monthly="approveMonthlySettlement"
      @reopen-monthly="reopenMonthlySettlement"
    />

    <SettlementWorkspacePanel
      :settlement-store="settlementStore"
      :selected-month="selectedMonth"
      :selected-platform="selectedPlatform"
      :shop-keyword="shopKeyword"
      :active-shop-tab="activeShopTab"
      :platform-options="platformOptions"
      :platform-labels="platformLabels"
      :selected-platform-label="selectedPlatformLabel"
      :filtered-shops="filteredShops"
      :selected-shop="selectedShop"
      :platform-shop-stats="platformShopStats"
      :recommended-actions="recommendedActions"
      :profit-basis-form="profitBasisForm"
      :format-currency="formatCurrency"
      @handle-month-change="handleMonthChange"
      @handle-platform-change="handlePlatformChange"
      @select-shop="selectShop"
      @load-profit-basis="loadProfitBasis"
      @rebuild-profit-basis="rebuildProfitBasis"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { useFinanceSettlementStore } from '@/stores/financeSettlement'
import MonthlySettlementPanel from './finance-settlement/MonthlySettlementPanel.vue'
import SettlementWorkspacePanel from './finance-settlement/SettlementWorkspacePanel.vue'
import { buildShopAccountLookup, decorateShopEntity } from '@/utils/shopDisplay'

const settlementStore = useFinanceSettlementStore()
const currentMonth = new Date().toISOString().slice(0, 7)
const activeShopTab = ref('basis')
const selectedMonth = ref(currentMonth)
const selectedPlatform = ref('shopee')
const shopKeyword = ref('')
const platformLabels = { shopee: 'Shopee', tiktok: 'TikTok', amazon: 'Amazon', miaoshou: '妙手ERP' }
const platformOptions = Object.keys(platformLabels)
const allShops = ref([])
let shopDisplayLookup = new Map()
const selectedShop = ref(null)
const monthlyForm = ref({ period_month: currentMonth, personnel_target_ratio: 0.3, follow_target_ratio: 0.2, company_target_ratio: 0.5, adjustment_amount: 0, adjustment_reason: '' })
const profitBasisForm = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '' })
const monthlySummary = computed(() => settlementStore.monthlyProfitSettlement.data?.summary || null)
const currentSettlementId = computed(() => monthlySummary.value?.id || null)
const showSettlementDifferenceWarning = computed(() => !!monthlySummary.value && (Math.abs(Number(monthlySummary.value.difference_amount || 0)) > 3000 || Math.abs(Number(monthlySummary.value.difference_ratio || 0)) > 0.01))
const selectedPlatformLabel = computed(() => platformLabels[selectedPlatform.value] || selectedPlatform.value)

const filteredShops = computed(() => {
  const keyword = shopKeyword.value.trim().toLowerCase()
  return allShops.value.filter((shop) => {
    if (shop.platform_code !== selectedPlatform.value) return false
    if (!keyword) return true
    return (shop.search_text || `${shop.shop_name || ''} ${shop.shop_id || ''}`.toLowerCase()).includes(keyword)
  })
})

const platformShopStats = computed(() => {
  const total = filteredShops.value.length
  const enabled = filteredShops.value.filter((shop) => shop.enabled !== false).length
  const disabled = total - enabled
  const profitBasisLoaded = !!settlementStore.profitBasis.data
  return { total, enabled, disabled, profitBasisLoaded }
})

const recommendedActions = computed(() => {
  if (!selectedShop.value) return []
  const items = []
  if (!settlementStore.profitBasis.data) {
    items.push({
      key: 'load-profit-basis',
      title: '先查或重算利润口径',
      description: '当前店铺还没有可用的利润口径，请先进入“店铺结算净利润口径”页签完成查询或重算。'
    })
  }
  if (!items.length) {
    items.push({
      key: 'continue-settlement',
      title: '继续核对并完成月结',
      description: '当前店铺已经具备利润口径，可以继续核对利润数据，再回到公司月结完成总账确认。'
    })
  }
  return items
})

const syncMonthlyForm = (payload) => {
  const summary = payload?.summary
  if (!summary) return
  const firstAdjustment = payload?.adjustments?.[0] || null
  monthlyForm.value = {
    period_month: summary.period_month || currentMonth,
    personnel_target_ratio: Number(summary.personnel_target_ratio ?? 0.3),
    follow_target_ratio: Number(summary.follow_target_ratio ?? 0.2),
    company_target_ratio: Number(summary.company_target_ratio ?? 0.5),
    adjustment_amount: Number(summary.adjustment_amount ?? 0),
    adjustment_reason: firstAdjustment?.reason || ''
  }
}

const syncSelectedShopForms = () => {
  if (!selectedShop.value) return
  const shopId = selectedShop.value.shop_id
  profitBasisForm.value = { ...profitBasisForm.value, period_month: selectedMonth.value, platform_code: selectedPlatform.value, shop_id: shopId }
}

const loadShopList = async () => {
  const [targetShopsResult, shopDirectoryResult] = await Promise.allSettled([
    api.getTargetShops(),
    api.getShopDirectory({ enabled: true }),
  ])
  if (targetShopsResult.status !== 'fulfilled') {
    throw targetShopsResult.reason
  }
  const shopDirectory = shopDirectoryResult.status === 'fulfilled' ? shopDirectoryResult.value : []
  shopDisplayLookup = buildShopAccountLookup(Array.isArray(shopDirectory) ? shopDirectory : [])
  const response = targetShopsResult.value
  allShops.value = (response?.data || response || [])
    .filter((shop) => shop.platform_code)
    .map((shop) => decorateShopEntity(shop, shopDisplayLookup))
  if (!selectedShop.value || selectedShop.value.platform_code !== selectedPlatform.value) {
    selectedShop.value = filteredShops.value[0] || null
    syncSelectedShopForms()
  }
}

const selectShop = (shop) => {
  selectedShop.value = shop
  syncSelectedShopForms()
  settlementStore.profitBasis.data = null
  loadProfitBasis()
}

const handlePlatformChange = async () => {
  shopKeyword.value = ''
  selectedShop.value = filteredShops.value[0] || null
  syncSelectedShopForms()
  if (selectedShop.value) {
    loadProfitBasis()
  }
}

const handleMonthChange = async () => {
  monthlyForm.value.period_month = selectedMonth.value
  syncSelectedShopForms()
  await loadMonthlySettlement()
  if (selectedShop.value) {
    await loadProfitBasis()
  }
}

const loadMonthlySettlement = async () => {
  try {
    await settlementStore.fetchMonthlyProfitSettlement({ period_month: monthlyForm.value.period_month })
    syncMonthlyForm(settlementStore.monthlyProfitSettlement.data)
  } catch (_) {}
}

const rebuildMonthlySettlement = async () => {
  try {
    await settlementStore.rebuildMonthlyProfitSettlement({
      period_month: monthlyForm.value.period_month,
      personnel_target_ratio: monthlyForm.value.personnel_target_ratio,
      follow_target_ratio: monthlyForm.value.follow_target_ratio,
      company_target_ratio: monthlyForm.value.company_target_ratio,
      adjustment_amount: monthlyForm.value.adjustment_amount,
      adjustment_reason: monthlyForm.value.adjustment_reason || null
    })
    syncMonthlyForm(settlementStore.monthlyProfitSettlement.data)
    ElMessage.success('月度利润结算已重建')
  } catch (error) {
    ElMessage.error('重建月度利润结算失败: ' + error.message)
  }
}

const saveMonthlyTargets = async () => {
  if (!currentSettlementId.value) return ElMessage.warning('请先查询或重建月结')
  try {
    await settlementStore.updateMonthlyProfitSettlementTargets(currentSettlementId.value, {
      personnel_target_ratio: monthlyForm.value.personnel_target_ratio,
      follow_target_ratio: monthlyForm.value.follow_target_ratio,
      company_target_ratio: monthlyForm.value.company_target_ratio,
      adjustment_amount: monthlyForm.value.adjustment_amount,
      adjustment_reason: monthlyForm.value.adjustment_reason || null
    })
    syncMonthlyForm(settlementStore.monthlyProfitSettlement.data)
    ElMessage.success('月度目标比例已保存')
  } catch (error) {
    ElMessage.error('保存月度目标比例失败: ' + error.message)
  }
}

const approveMonthlySettlement = async () => {
  if (!currentSettlementId.value) return ElMessage.warning('请先查询月结')
  try {
    await settlementStore.approveMonthlyProfitSettlement(currentSettlementId.value)
    ElMessage.success('月度利润结算已审批')
    await loadMonthlySettlement()
  } catch (error) {
    ElMessage.error('审批月度利润结算失败: ' + error.message)
  }
}

const reopenMonthlySettlement = async () => {
  if (!currentSettlementId.value) return ElMessage.warning('请先查询月结')
  try {
    await settlementStore.reopenMonthlyProfitSettlement(currentSettlementId.value)
    ElMessage.success('月度利润结算已回退到草稿')
    await loadMonthlySettlement()
  } catch (error) {
    ElMessage.error('回退月度利润结算失败: ' + error.message)
  }
}

const loadProfitBasis = async () => {
  if (!selectedShop.value) return
  try {
    await settlementStore.fetchProfitBasis({ period_month: profitBasisForm.value.period_month, platform_code: profitBasisForm.value.platform_code, shop_id: profitBasisForm.value.shop_id })
  } catch (_) {}
}

const rebuildProfitBasis = async () => {
  if (!selectedShop.value) return
  try {
    // 利润基数口径由后端统一决定：前端不再指定 basis_version，避免重建历史口径。
    await settlementStore.rebuildProfitBasis({ period_month: profitBasisForm.value.period_month, platform_code: profitBasisForm.value.platform_code, shop_id: profitBasisForm.value.shop_id })
    ElMessage.success('利润分配基准已重算')
  } catch (error) {
    ElMessage.error('重算利润基准失败: ' + error.message)
  }
}

const formatRatioInput = (value) => {
  if (value == null || value === undefined || value === '') return ''
  return `${(Number(value) * 100).toFixed(2)}%`
}

const parseRatioInput = (value) => {
  if (value == null || value === undefined || value === '') return 0
  const numeric = Number(String(value).replace(/[%\s]/g, ''))
  if (Number.isNaN(numeric)) return 0
  return numeric / 100
}

const formatCurrency = (num) => {
  if (num == null || num === undefined) return '-'
  return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num)
}

const formatPercentValue = (num) => (num == null || num === undefined) ? '-' : `${(Number(num) * 100).toFixed(2)}%`

onMounted(async () => {
  await loadShopList()
  monthlyForm.value.period_month = selectedMonth.value
  await loadMonthlySettlement()
  if (selectedShop.value) {
    await loadProfitBasis()
  }
})
</script>

<style scoped>
.financial-management { padding: 20px; background: #f3f5f7; min-height: 100vh; }
.page-header { margin-bottom: 20px; padding: 24px 28px; border-radius: 14px; color: white; background: linear-gradient(135deg, #1f4d78 0%, #2f7a9a 55%, #5aa0a8 100%); }
.page-header h1 { margin: 0 0 8px; font-size: 30px; font-weight: 700; }
.page-header p { margin: 0; opacity: 0.9; }
.page-alert { margin-bottom: 20px; }
.section-alert { margin-bottom: 16px; }
@media (max-width: 768px) {
  .financial-management { padding: 12px; }
  .page-header { padding: 20px; }
  .page-header h1 { font-size: 24px; }
}
</style>
