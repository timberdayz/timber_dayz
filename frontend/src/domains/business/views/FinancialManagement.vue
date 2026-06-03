<template>
  <div class="financial-management">
    <div class="page-header">
      <h1>财务结算中心</h1>
      <p>先确认公司月结，再按平台切换店铺处理利润口径、跟投试算、跟投记录与结算台账。</p>
    </div>

    <el-alert
      class="page-alert"
      type="info"
      :closable="false"
      show-icon
      title="建议先确认利润基准、店铺提成、工资和跟投审批，再进行月度利润结算审批。"
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
      :shop-filter-mode="shopFilterMode"
      :active-shop-tab="activeShopTab"
      :platform-options="platformOptions"
      :platform-labels="platformLabels"
      :selected-platform-label="selectedPlatformLabel"
      :filtered-shops="filteredShops"
      :selected-shop="selectedShop"
      :platform-shop-stats="platformShopStats"
      :shop-exception-items="shopExceptionItems"
      :recommended-actions="recommendedActions"
      :profit-basis-form="profitBasisForm"
      :follow-investment-form="followInvestmentForm"
      :follow-investment-query="followInvestmentQuery"
      :settlement-query="settlementQuery"
      :format-currency="formatCurrency"
      :format-percent-value="formatPercentValue"
      :format-date-time="formatDateTime"
      :get-shop-status="getShopStatus"
      @handle-month-change="handleMonthChange"
      @handle-platform-change="handlePlatformChange"
      @select-shop="selectShop"
      @load-profit-basis="loadProfitBasis"
      @rebuild-profit-basis="rebuildProfitBasis"
      @run-follow-settlement="runFollowInvestmentSettlement"
      @load-follow-investments="loadFollowInvestments"
      @load-follow-investment-settlements="loadFollowInvestmentSettlements"
      @view-settlement-details="viewSettlementDetails"
      @approve-follow-investment="approveFollowInvestment"
      @reopen-follow-investment="reopenFollowInvestment"
      @open-create-follow-investment="openCreateFollowInvestment"
      @open-edit-follow-investment="openEditFollowInvestment"
      @archive-follow-investment="archiveFollowInvestment"
    />

    <el-dialog v-model="showFollowInvestmentDialog" :title="followInvestmentDialogMode === 'create' ? '新增跟投' : '编辑跟投'" width="600px">
      <el-form :model="followInvestmentRecordForm" label-width="120px">
        <el-form-item label="投资人ID"><el-input-number v-model="followInvestmentRecordForm.investor_user_id" :min="1" /></el-form-item>
        <el-form-item label="平台"><el-input :model-value="selectedPlatformLabel" disabled style="width: 180px" /></el-form-item>
        <el-form-item label="店铺"><el-input :model-value="selectedShop?.shop_name || ''" disabled /></el-form-item>
        <el-form-item label="本金"><el-input-number v-model="followInvestmentRecordForm.contribution_amount" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="投入日期"><el-date-picker v-model="followInvestmentRecordForm.contribution_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="退出日期"><el-date-picker v-model="followInvestmentRecordForm.withdraw_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="状态"><el-select v-model="followInvestmentRecordForm.status" style="width: 180px"><el-option label="生效" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item>
        <el-form-item label="备注"><el-input v-model="followInvestmentRecordForm.remark" type="textarea" rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFollowInvestmentDialog = false">取消</el-button>
        <el-button type="primary" @click="submitFollowInvestmentRecord" :loading="submitting">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showSettlementDetailsDrawer" title="结算明细" size="50%">
      <el-alert v-if="settlementStore.followInvestmentSettlementDetails.error" type="error" :closable="false" :title="settlementStore.followInvestmentSettlementDetails.error" class="section-alert" />
      <el-table :data="settlementStore.followInvestmentSettlementDetails.data" v-loading="settlementStore.followInvestmentSettlementDetails.loading" stripe>
        <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
        <el-table-column prop="investor_name" label="投资人姓名" width="140" />
        <el-table-column prop="contribution_amount_snapshot" label="本金快照" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.contribution_amount_snapshot) }}</template></el-table-column>
        <el-table-column prop="occupied_days" label="占用天数" width="100" align="right" />
        <el-table-column prop="weighted_capital" label="加权资金" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.weighted_capital) }}</template></el-table-column>
        <el-table-column prop="share_ratio" label="分配占比" width="120" align="right"><template #default="{ row }">{{ formatPercentValue(row.share_ratio) }}</template></el-table-column>
        <el-table-column prop="estimated_income" label="预计收益" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.estimated_income) }}</template></el-table-column>
        <el-table-column prop="approved_income" label="已批准收益" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.approved_income) }}</template></el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import financeApi from '@/api/finance'
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
const shopFilterMode = ref('all')
const platformLabels = { shopee: 'Shopee', tiktok: 'TikTok', amazon: 'Amazon', miaoshou: '妙手ERP' }
const platformOptions = Object.keys(platformLabels)
const allShops = ref([])
let shopDisplayLookup = new Map()
const selectedShop = ref(null)
const platformFollowInvestments = ref([])
const platformSettlementRows = ref([])
const monthlyForm = ref({ period_month: currentMonth, personnel_target_ratio: 0.3, follow_target_ratio: 0.2, company_target_ratio: 0.5, adjustment_amount: 0, adjustment_reason: '' })
const profitBasisForm = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '' })
const followInvestmentForm = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '', distribution_ratio: 0.4 })
const followInvestmentQuery = ref({ platform_code: 'shopee', shop_id: '', status: '' })
const settlementQuery = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '', status: '' })
const showFollowInvestmentDialog = ref(false)
const showSettlementDetailsDrawer = ref(false)
const followInvestmentDialogMode = ref('create')
const editingFollowInvestmentId = ref(null)
const submitting = ref(false)
const followInvestmentRecordForm = ref({ investor_user_id: null, platform_code: 'shopee', shop_id: '', contribution_amount: 0, contribution_date: new Date().toISOString().split('T')[0], withdraw_date: '', status: 'active', remark: '' })
const monthlySummary = computed(() => settlementStore.monthlyProfitSettlement.data?.summary || null)
const currentSettlementId = computed(() => monthlySummary.value?.id || null)
const showSettlementDifferenceWarning = computed(() => !!monthlySummary.value && (Math.abs(Number(monthlySummary.value.difference_amount || 0)) > 3000 || Math.abs(Number(monthlySummary.value.difference_ratio || 0)) > 0.01))
const selectedPlatformLabel = computed(() => platformLabels[selectedPlatform.value] || selectedPlatform.value)

const filteredShops = computed(() => {
  const keyword = shopKeyword.value.trim().toLowerCase()
  return allShops.value.filter((shop) => {
    if (shop.platform_code !== selectedPlatform.value) return false
    const status = getShopStatus(shop)
    if (shopFilterMode.value === 'exception' && !status.hasException) return false
    if (shopFilterMode.value === 'pending' && !status.pendingData) return false
    if (!keyword) return true
    return (shop.search_text || `${shop.shop_name || ''} ${shop.shop_id || ''}`.toLowerCase()).includes(keyword)
  })
})

const platformShopStats = computed(() => {
  const total = filteredShops.value.length
  const canSettle = filteredShops.value.filter((shop) => getShopStatus(shop).canSettle).length
  const withFollowInvestment = filteredShops.value.filter((shop) => getShopStatus(shop).hasFollowInvestment).length
  const withSettlement = filteredShops.value.filter((shop) => getShopStatus(shop).hasSettlement).length
  const pendingData = filteredShops.value.filter((shop) => getShopStatus(shop).pendingData).length
  return { total, canSettle, withFollowInvestment, withSettlement, pendingData }
})

const shopExceptionItems = computed(() => {
  if (!selectedShop.value) return []
  const status = getShopStatus(selectedShop.value)
  const items = []
  if (status.pendingData) {
    items.push({ key: 'pending-data', title: '缺少经营沉淀数据', description: '当前店铺既没有跟投记录，也没有当月结算台账，建议先核对利润口径和跟投数据。' })
  }
  if (!settlementStore.profitBasis.data) {
    items.push({ key: 'profit-basis', title: '尚未加载利润口径', description: '请先查询或重算店铺结算净利润口径，再继续后续试算和审批。' })
  }
  if (!status.hasSettlement) {
    items.push({ key: 'settlement-ledger', title: '缺少当月结算台账', description: '当前月份还没有结算台账，建议先完成跟投收益试算或检查月度结算生成流程。' })
  }
  return items
})

const recommendedActions = computed(() => {
  if (!selectedShop.value) return []
  const status = getShopStatus(selectedShop.value)
  const items = []
  if (!settlementStore.profitBasis.data) {
    items.push({
      key: 'load-profit-basis',
      title: '先查或重算利润口径',
      description: '当前店铺还没有可用的利润口径，请先进入“店铺结算净利润口径”页签完成查询或重算。'
    })
  }
  if (!status.hasSettlement) {
    items.push({
      key: 'run-follow-trial',
      title: '先完成跟投收益试算',
      description: '当前店铺还没有当月结算台账，请先在“跟投收益试算”页签生成试算结果和结算台账。'
    })
  }
  if (status.hasSettlement && platformSettlementRows.value.some((row) => row.shop_id === selectedShop.value.shop_id && row.status === 'approved')) {
    items.push({
      key: 'reopen-before-rebuild',
      title: '已审批时只能回退后再重建',
      description: '如果需要重新试算或调整已审批台账，请先在“结算台账”中执行回退审批，再重新处理。'
    })
  }
  if (!items.length) {
    items.push({
      key: 'continue-settlement',
      title: '继续核对并完成月结',
      description: '当前店铺已经具备结算信号，可以继续核对台账、审批结果，再回到公司月结完成总账确认。'
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
  followInvestmentForm.value = { ...followInvestmentForm.value, period_month: selectedMonth.value, platform_code: selectedPlatform.value, shop_id: shopId }
  followInvestmentQuery.value = { ...followInvestmentQuery.value, platform_code: selectedPlatform.value, shop_id: shopId }
  settlementQuery.value = { ...settlementQuery.value, period_month: selectedMonth.value, platform_code: selectedPlatform.value, shop_id: shopId }
  followInvestmentRecordForm.value = { ...followInvestmentRecordForm.value, platform_code: selectedPlatform.value, shop_id: shopId }
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

const loadPlatformShopSignals = async () => {
  const [followResponse, settlementResponse] = await Promise.all([
    financeApi.getFollowInvestments({ platform_code: selectedPlatform.value }),
    financeApi.getFollowInvestmentSettlements({ platform_code: selectedPlatform.value, period_month: selectedMonth.value })
  ])
  platformFollowInvestments.value = followResponse?.data || followResponse || []
  platformSettlementRows.value = settlementResponse?.data || settlementResponse || []
}

const selectShop = (shop) => {
  selectedShop.value = shop
  syncSelectedShopForms()
  settlementStore.followInvestmentSettlement.data = { settlement: null, details: [] }
  settlementStore.profitBasis.data = null
  loadProfitBasis()
  loadFollowInvestments()
  loadFollowInvestmentSettlements()
}

const handlePlatformChange = async () => {
  shopKeyword.value = ''
  shopFilterMode.value = 'all'
  selectedShop.value = filteredShops.value[0] || null
  syncSelectedShopForms()
  await loadPlatformShopSignals()
  if (selectedShop.value) {
    loadProfitBasis()
    loadFollowInvestments()
    loadFollowInvestmentSettlements()
  }
}

const handleMonthChange = async () => {
  monthlyForm.value.period_month = selectedMonth.value
  syncSelectedShopForms()
  await loadMonthlySettlement()
  await loadPlatformShopSignals()
  if (selectedShop.value) {
    await loadProfitBasis()
    await loadFollowInvestments()
    await loadFollowInvestmentSettlements()
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
    await settlementStore.rebuildProfitBasis({ period_month: profitBasisForm.value.period_month, platform_code: profitBasisForm.value.platform_code, shop_id: profitBasisForm.value.shop_id, basis_version: 'A_ONLY_V1' })
    ElMessage.success('利润分配基准已重算')
  } catch (error) {
    ElMessage.error('重算利润基准失败: ' + error.message)
  }
}

const runFollowInvestmentSettlement = async () => {
  if (!selectedShop.value) return
  try {
    await settlementStore.calculateFollowInvestmentSettlement({
      period_month: followInvestmentForm.value.period_month,
      platform_code: followInvestmentForm.value.platform_code,
      shop_id: followInvestmentForm.value.shop_id,
      distribution_ratio: followInvestmentForm.value.distribution_ratio
    })
    await loadPlatformShopSignals()
    ElMessage.success('跟投收益试算完成')
  } catch (error) {
    ElMessage.error('跟投收益试算失败: ' + error.message)
  }
}

const loadFollowInvestments = async () => {
  if (!selectedShop.value) return
  try {
    await settlementStore.fetchFollowInvestments({
      period_month: selectedMonth.value || undefined,
      platform_code: followInvestmentQuery.value.platform_code || undefined,
      shop_id: followInvestmentQuery.value.shop_id || undefined,
      status: followInvestmentQuery.value.status || undefined
    })
  } catch (_) {}
}

const loadFollowInvestmentSettlements = async () => {
  if (!selectedShop.value) return
  try {
    await settlementStore.fetchFollowInvestmentSettlements({
      period_month: settlementQuery.value.period_month || undefined,
      platform_code: settlementQuery.value.platform_code || undefined,
      shop_id: settlementQuery.value.shop_id || undefined,
      status: settlementQuery.value.status || undefined
    })
  } catch (_) {}
}

const viewSettlementDetails = async (row) => {
  await settlementStore.fetchFollowInvestmentSettlementDetails(row.id)
  showSettlementDetailsDrawer.value = true
}

const resetFollowInvestmentRecordForm = () => {
  followInvestmentRecordForm.value = {
    investor_user_id: null,
    platform_code: selectedPlatform.value,
    shop_id: selectedShop.value?.shop_id || '',
    contribution_amount: 0,
    contribution_date: new Date().toISOString().split('T')[0],
    withdraw_date: '',
    status: 'active',
    remark: ''
  }
  editingFollowInvestmentId.value = null
}

const openCreateFollowInvestment = () => {
  followInvestmentDialogMode.value = 'create'
  resetFollowInvestmentRecordForm()
  showFollowInvestmentDialog.value = true
}

const openEditFollowInvestment = (row) => {
  followInvestmentDialogMode.value = 'edit'
  editingFollowInvestmentId.value = row.id
  followInvestmentRecordForm.value = {
    investor_user_id: row.investor_user_id,
    platform_code: row.platform_code,
    shop_id: row.shop_id,
    contribution_amount: row.contribution_amount,
    contribution_date: row.contribution_date,
    withdraw_date: row.withdraw_date || '',
    status: row.status,
    remark: row.remark || ''
  }
  showFollowInvestmentDialog.value = true
}

const submitFollowInvestmentRecord = async () => {
  try {
    submitting.value = true
    const payload = { ...followInvestmentRecordForm.value, withdraw_date: followInvestmentRecordForm.value.withdraw_date || null }
    if (followInvestmentDialogMode.value === 'create') {
      await settlementStore.createFollowInvestment(payload)
    } else {
      await settlementStore.updateFollowInvestment(editingFollowInvestmentId.value, payload, {
        platform_code: followInvestmentQuery.value.platform_code || undefined,
        shop_id: followInvestmentQuery.value.shop_id || undefined,
        status: followInvestmentQuery.value.status || undefined
      })
    }
    await loadPlatformShopSignals()
    ElMessage.success('跟投记录已保存')
    showFollowInvestmentDialog.value = false
    resetFollowInvestmentRecordForm()
    await loadFollowInvestments()
  } catch (error) {
    ElMessage.error('保存跟投记录失败: ' + error.message)
  } finally {
    submitting.value = false
  }
}

const archiveFollowInvestment = async (row) => {
  try {
    await ElMessageBox.confirm(`确认归档跟投记录 #${row.id} 吗？`, '归档跟投记录', { confirmButtonText: '确认归档', cancelButtonText: '取消', type: 'warning' })
    await settlementStore.archiveFollowInvestment(row.id, {
      platform_code: followInvestmentQuery.value.platform_code || undefined,
      shop_id: followInvestmentQuery.value.shop_id || undefined,
      status: followInvestmentQuery.value.status || undefined
    })
    await loadPlatformShopSignals()
    ElMessage.success('跟投记录已归档')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('归档失败: ' + (error.message || error))
  }
}

const approveFollowInvestment = async (row) => {
  try {
    await settlementStore.approveFollowInvestmentSettlement(row.id)
    await loadPlatformShopSignals()
    ElMessage.success('结算已审批')
    await loadFollowInvestmentSettlements()
  } catch (error) {
    ElMessage.error('审批失败: ' + error.message)
  }
}

const reopenFollowInvestment = async (row) => {
  try {
    await settlementStore.reopenFollowInvestmentSettlement(row.id)
    await loadPlatformShopSignals()
    ElMessage.success('结算已回退')
    await loadFollowInvestmentSettlements()
  } catch (error) {
    ElMessage.error('回退失败: ' + error.message)
  }
}

const getShopStatus = (shop) => {
  const hasFollowInvestment = platformFollowInvestments.value.some((item) => item.shop_id === shop.shop_id)
  const hasSettlement = platformSettlementRows.value.some((item) => item.shop_id === shop.shop_id)
  const canSettle = hasFollowInvestment && hasSettlement
  const pendingData = !hasFollowInvestment && !hasSettlement
  const hasException = pendingData || !hasSettlement
  return { hasFollowInvestment, hasSettlement, canSettle, pendingData, hasException }
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
const formatDateTime = (dateTime) => (!dateTime ? '-' : new Date(dateTime).toLocaleString('zh-CN'))

onMounted(async () => {
  await loadShopList()
  await loadPlatformShopSignals()
  monthlyForm.value.period_month = selectedMonth.value
  await loadMonthlySettlement()
  if (selectedShop.value) {
    await loadProfitBasis()
    await loadFollowInvestments()
    await loadFollowInvestmentSettlements()
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
