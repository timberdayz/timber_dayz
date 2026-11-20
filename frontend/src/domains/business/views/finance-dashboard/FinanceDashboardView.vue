<template>
  <div class="finance-dashboard">
    <div class="page-header">
      <h1>月度利润看板</h1>
      <p>只读呈现已发生的月度利润事实：本月赚了多少、分给员工多少、人工调整多少、公司留下多少。</p>
    </div>

    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar">
        <div class="toolbar-field">
          <span class="toolbar-label">月份</span>
          <el-date-picker
            v-model="periodMonth"
            type="month"
            value-format="YYYY-MM"
            format="YYYY-MM"
            style="width: 160px"
            @change="handleMonthChange"
          />
        </div>
        <div class="toolbar-field">
          <span class="toolbar-label">数据截止时间</span>
          <span class="toolbar-value">{{ asOfText }}</span>
        </div>
        <div class="toolbar-field">
          <el-button :loading="store.loading" @click="handleMonthChange">刷新</el-button>
        </div>
      </div>
    </el-card>

    <el-alert
      v-if="shopDirectoryError"
      type="warning"
      :closable="false"
      show-icon
      :title="shopDirectoryError"
      class="section-alert"
    />
    <el-alert
      v-if="store.loading"
      type="info"
      :closable="false"
      show-icon
      title="正在加载月度利润数据，请稍候。"
      class="section-alert"
    />
    <el-alert
      v-if="store.error"
      type="error"
      :closable="false"
      show-icon
      :title="store.error"
      class="section-alert"
    />
    <el-alert
      v-if="!store.loading && !store.error && !store.dashboard"
      type="warning"
      :closable="false"
      show-icon
      title="当前月份暂无月度利润数据，可切换月份或直接新增人工调整项。"
      class="section-alert"
    />

    <ProfitOverviewCards v-if="store.dashboard" :dashboard="store.dashboard" />
    <ShopAllocationTable
      v-if="store.dashboard"
      :breakdown="store.dashboard.shop_breakdown || []"
      :shop-lookup="shopLookup"
    />
    <AdjustmentPanel
      :period-month="activePeriodMonth"
      :adjustments="store.dashboard?.adjustments || []"
      :submitting="store.submitting"
      :error="store.actionError"
      :submit-adjustment="handleSubmitAdjustment"
      :delete-adjustment="handleDeleteAdjustment"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { formatDateTime } from '@/utils/format'
import { buildShopAccountLookup } from '@/utils/shopDisplay'
import { useFinanceDashboardStore } from '@/stores/financeDashboard'
import ProfitOverviewCards from './ProfitOverviewCards.vue'
import ShopAllocationTable from './ShopAllocationTable.vue'
import AdjustmentPanel from './AdjustmentPanel.vue'

const store = useFinanceDashboardStore()

/** 当前月份（本地时区，避免 UTC 跨月导致月份错位）。 */
const currentPeriodMonth = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${now.getFullYear()}-${month}`
}

const periodMonth = ref(currentPeriodMonth())
const shopLookup = ref(new Map())
const shopDirectoryError = ref('')

const asOfText = computed(() => {
  const asOf = store.dashboard?.as_of
  return asOf ? formatDateTime(asOf) : '—'
})

const activePeriodMonth = computed(() => store.periodMonth || periodMonth.value)

/** 店铺显示名走全站统一口径；失败不影响看板金额，只提示降级。 */
const loadShopDirectory = async () => {
  try {
    const response = await api.getShopDirectory({ enabled: true })
    const list = Array.isArray(response) ? response : (Array.isArray(response?.data) ? response.data : [])
    shopLookup.value = buildShopAccountLookup(list)
    shopDirectoryError.value = ''
  } catch (error) {
    shopDirectoryError.value = `店铺名称暂不可用，店铺分布表将显示店铺编号：${error?.message || '加载店铺目录失败'}`
  }
}

const loadDashboard = async () => {
  try {
    await store.fetchDashboard(periodMonth.value)
  } catch (_) {
    // 失败已落在 store.error 上，由 el-alert 呈现（不让失败对页面不可见）
  }
}

const handleMonthChange = async () => {
  await loadDashboard()
}

const handleSubmitAdjustment = async (payload) => {
  try {
    await store.addAdjustment(payload)
    ElMessage.success('人工调整项已新增')
    return true
  } catch (error) {
    ElMessage.error(store.actionError || `新增人工调整项失败：${error?.message || '未知错误'}`)
    return false
  }
}

const handleDeleteAdjustment = async (adjustmentId) => {
  try {
    await store.removeAdjustment(adjustmentId)
    ElMessage.success('人工调整项已删除')
    return true
  } catch (error) {
    ElMessage.error(store.actionError || `删除人工调整项失败：${error?.message || '未知错误'}`)
    return false
  }
}

onMounted(async () => {
  await loadShopDirectory()
  await loadDashboard()
})
</script>

<style scoped>
.finance-dashboard { padding: 20px; background: #f3f5f7; min-height: 100vh; }
.page-header { margin-bottom: 20px; padding: 24px 28px; border-radius: 14px; color: white; background: linear-gradient(135deg, #1f4d78 0%, #2f7a9a 55%, #5aa0a8 100%); }
.page-header h1 { margin: 0 0 8px; font-size: 30px; font-weight: 700; }
.page-header p { margin: 0; opacity: 0.9; }
.toolbar-card { margin-bottom: 20px; }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 24px; }
.toolbar-field { display: flex; align-items: center; gap: 10px; }
.toolbar-label { color: #606266; font-size: 13px; }
.toolbar-value { font-size: 15px; font-weight: 600; color: #303133; }
.section-alert { margin-bottom: 16px; }
@media (max-width: 768px) {
  .finance-dashboard { padding: 12px; }
  .page-header { padding: 20px; }
  .page-header h1 { font-size: 24px; }
}
</style>
