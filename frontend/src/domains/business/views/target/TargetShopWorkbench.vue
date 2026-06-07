<template>
  <div class="target-shop-workbench erp-page-container erp-page--admin">
    <PageHeader
      title="店铺目标管理"
      subtitle="按月份维护公司总销售目标，并快速拆分到平台和店铺。"
      family="admin"
    />

    <section class="toolbar">
      <el-date-picker
        v-model="yearMonth"
        type="month"
        value-format="YYYY-MM"
        format="YYYY-MM"
        placeholder="选择月份"
        class="month-picker"
        @change="loadWorkbench"
      />
      <el-button :icon="CopyDocument" @click="copyPrevMonth" :loading="copying">
        复制上月目标
      </el-button>
      <el-button :icon="Refresh" @click="loadWorkbench" :loading="loading">
        刷新
      </el-button>
      <el-button
        type="primary"
        :icon="Check"
        @click="saveWorkbench"
        :loading="saving"
        :disabled="!canSave"
      >
        保存目标
      </el-button>
    </section>

    <section class="validation-strip" :class="{ 'is-valid': canSave }">
      <span :class="{ invalid: !ratioIsValid }">比例合计 {{ totals.ratioPercent.toFixed(2) }}%</span>
      <span :class="{ invalid: !amountIsValid }">销售额合计 {{ formatAmount(totals.amount) }}</span>
      <span :class="{ invalid: !amountIsValid }">销售额差额 {{ formatAmount(amountDiff) }}</span>
      <span :class="{ invalid: !quantityIsValid }">订单合计 {{ totals.quantity }}</span>
      <span :class="{ invalid: !quantityIsValid }">订单差额 {{ quantityDiff }}</span>
      <span :class="{ invalid: !weekdayRatioIsValid }">周比例 {{ weekdayRatioTotal.toFixed(2) }}%</span>
    </section>

    <section class="summary-panel">
      <el-form :model="summary" label-position="top" class="summary-form">
        <el-form-item label="公司总销售额">
          <el-input-number
            v-model="summary.company_target_amount"
            :min="0"
            :precision="2"
            :step="1000"
            controls-position="right"
            class="number-input"
            @change="splitByRatio"
          />
        </el-form-item>
        <el-form-item label="订单目标">
          <el-input-number
            v-model="summary.company_target_quantity"
            :min="0"
            :step="10"
            controls-position="right"
            class="number-input"
            @change="splitByRatio"
          />
        </el-form-item>
        <el-form-item label="快捷拆分">
          <div class="split-actions">
            <el-button @click="splitEqually">平均拆分</el-button>
            <el-button @click="splitByRatio">按比例重算</el-button>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <el-table
      v-loading="loading"
      :data="shops"
      border
      stripe
      show-summary
      :summary-method="buildTableSummary"
      class="erp-table target-table"
    >
      <el-table-column label="平台" prop="platform_code" width="105" />
      <el-table-column label="店铺" min-width="320">
        <template #default="{ row }">
          <div class="shop-cell">
            <strong>{{ row.standard_name || row.shop_id }}</strong>
            <span>ID: {{ row.shop_id }}</span>
            <span v-if="row.aliases?.length">别名: {{ row.aliases.join(' / ') }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="拆分比例" width="150" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.ratio_percent"
            :min="0"
            :max="100"
            :precision="2"
            :step="1"
            controls-position="right"
            class="cell-number"
            @change="splitByRatio"
          />
          <span class="percent-suffix">%</span>
        </template>
      </el-table-column>
      <el-table-column label="目标销售额" width="170" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.target_amount"
            :min="0"
            :precision="2"
            :step="1000"
            controls-position="right"
            class="cell-number"
          />
        </template>
      </el-table-column>
      <el-table-column label="订单目标" width="135" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.target_quantity"
            :min="0"
            :step="10"
            controls-position="right"
            class="cell-number"
          />
        </template>
      </el-table-column>
      <el-table-column label="日目标" width="130" align="center">
        <template #default="{ row }">
          <el-button text type="primary" @click="openDailyDrawer(row)">
            {{ row.daily_target_count || daysInMonth }} 天
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="dailyDrawerVisible" title="店铺日目标" size="760px">
      <template v-if="currentShop">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="标准名">{{ currentShop.standard_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺ID">{{ currentShop.shop_id }}</el-descriptions-item>
          <el-descriptions-item label="别名">{{ currentShop.aliases?.join(' / ') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="月目标">{{ formatAmount(currentShop.target_amount) }}</el-descriptions-item>
        </el-descriptions>

        <div class="weekday-ratio-panel">
          <div class="panel-title">周一到周日拆分比例</div>
          <div class="weekday-grid">
            <label v-for="day in weekdayOptions" :key="day.key" class="weekday-cell">
              <span>{{ day.label }}</span>
              <el-input-number
                v-model="weekdayRatioPercents[day.key]"
                :min="0"
                :precision="2"
                :step="1"
                controls-position="right"
                class="weekday-input"
              />
              <span>%</span>
            </label>
          </div>
          <div class="weekday-actions">
            <span>周比例合计: {{ weekdayRatioTotal.toFixed(2) }}%</span>
            <el-button size="small" @click="resetWeekdayRatios">平均每天</el-button>
            <el-button size="small" @click="applyWorkdayRatios">工作日更高</el-button>
          </div>
        </div>

        <div class="daily-calendar">
          <div
            v-for="item in dailyPreview"
            :key="item.date"
            class="daily-calendar-cell"
          >
            <div class="daily-calendar-head">
              <strong>{{ item.day }}</strong>
              <span>{{ item.weekday }}</span>
            </div>
            <div>{{ formatCompactAmount(item.amount) }}</div>
            <div>{{ item.quantity }} 单</div>
          </div>
        </div>

        <el-table :data="dailyPreview" border stripe size="small" class="daily-table">
          <el-table-column prop="date" label="日期" width="120" />
          <el-table-column prop="weekday" label="星期" width="90" />
          <el-table-column prop="ratioPercent" label="当日权重" width="110" align="right">
            <template #default="{ row }">{{ row.ratioPercent.toFixed(2) }}%</template>
          </el-table-column>
          <el-table-column prop="amount" label="日销售目标" align="right">
            <template #default="{ row }">{{ formatAmount(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="quantity" label="日订单目标" width="120" align="right" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, CopyDocument, Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'
import {
  WEEKDAY_OPTIONS,
  buildMonthDailyPreview,
  buildWeekdayRatiosPayload as buildWeekdayRatios,
  calculateShopTargetTotals,
  normalizeWeekdayRatiosToPercents,
  splitShopTargetsByPercent,
  splitShopTargetsEqually
} from './shopTargetUtils'

const yearMonth = ref(new Date().toISOString().slice(0, 7))
const loading = ref(false)
const saving = ref(false)
const copying = ref(false)
const shops = ref([])
const dailyDrawerVisible = ref(false)
const currentShop = ref(null)

const summary = reactive({
  target_id: null,
  company_target_amount: 0,
  company_target_quantity: 0
})

const weekdayOptions = WEEKDAY_OPTIONS

const weekdayRatioPercents = reactive({
  1: 14.2857,
  2: 14.2857,
  3: 14.2857,
  4: 14.2857,
  5: 14.2857,
  6: 14.2857,
  7: 14.2857
})

const daysInMonth = computed(() => {
  const [year, month] = yearMonth.value.split('-').map(Number)
  return new Date(year, month, 0).getDate()
})

const totals = computed(() => calculateShopTargetTotals(shops.value))

const amountDiff = computed(() => Number((totals.value.amount - Number(summary.company_target_amount || 0)).toFixed(2)))
const quantityDiff = computed(() => totals.value.quantity - Number(summary.company_target_quantity || 0))
const ratioIsValid = computed(() => Math.abs(totals.value.ratioPercent - 100) < 0.01)
const amountIsValid = computed(() => Math.abs(amountDiff.value) < 0.01)
const quantityIsValid = computed(() => quantityDiff.value === 0)
const weekdayRatioTotal = computed(() => {
  return weekdayOptions.reduce((sum, day) => sum + Number(weekdayRatioPercents[day.key] || 0), 0)
})
const weekdayRatioIsValid = computed(() => Math.abs(weekdayRatioTotal.value - 100) < 0.01)
const canSave = computed(() => ratioIsValid.value && amountIsValid.value && quantityIsValid.value && weekdayRatioIsValid.value)

const dailyPreview = computed(() => {
  if (!currentShop.value) return []
  return buildMonthDailyPreview({
    yearMonth: yearMonth.value,
    amountTotal: Number(currentShop.value.target_amount || 0),
    quantityTotal: Number(currentShop.value.target_quantity || 0),
    weekdayRatioPercents
  })
})

function normalizeResponse(response) {
  return response?.data?.data || response?.data || response || {}
}

async function loadWorkbench() {
  if (!yearMonth.value) return
  loading.value = true
  try {
    const data = normalizeResponse(await api.getShopTargetWorkbench(yearMonth.value))
    summary.target_id = data.target_id || null
    summary.company_target_amount = Number(data.company_target_amount || 0)
    summary.company_target_quantity = Number(data.company_target_quantity || 0)
    setWeekdayRatios(data.weekday_ratios)
    shops.value = Array.isArray(data.shops)
      ? data.shops.map((shop) => ({
        ...shop,
        ratio: Number(shop.ratio || 0),
        ratio_percent: Number(((Number(shop.ratio || 0)) * 100).toFixed(2)),
        target_amount: Number(shop.target_amount || 0),
        target_quantity: Number(shop.target_quantity || 0),
        aliases: Array.isArray(shop.aliases) ? shop.aliases : []
      }))
      : []
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载店铺目标失败')
  } finally {
    loading.value = false
  }
}

function splitEqually() {
  if (!shops.value.length) return
  shops.value = splitShopTargetsEqually(
    shops.value,
    Number(summary.company_target_amount || 0),
    Number(summary.company_target_quantity || 0)
  )
}

function splitByRatio() {
  shops.value = splitShopTargetsByPercent(
    shops.value,
    Number(summary.company_target_amount || 0),
    Number(summary.company_target_quantity || 0)
  )
}

function setWeekdayRatios(ratios = {}) {
  const percents = normalizeWeekdayRatiosToPercents(ratios)
  weekdayOptions.forEach((day) => {
    weekdayRatioPercents[day.key] = percents[day.key]
  })
}

function buildWeekdayRatiosPayload() {
  return buildWeekdayRatios(weekdayRatioPercents)
}

function resetWeekdayRatios() {
  weekdayOptions.forEach((day) => {
    weekdayRatioPercents[day.key] = Number((100 / 7).toFixed(4))
  })
}

function applyWorkdayRatios() {
  const values = { 1: 16, 2: 16, 3: 16, 4: 16, 5: 16, 6: 10, 7: 10 }
  weekdayOptions.forEach((day) => {
    weekdayRatioPercents[day.key] = values[day.key]
  })
}

async function saveWorkbench() {
  if (!canSave.value) {
    ElMessage.error('拆分比例、销售额、订单目标和周比例必须全部对齐后才能保存')
    return
  }
  saving.value = true
  try {
    await api.applyShopTargetWorkbench({
      year_month: yearMonth.value,
      company_target_amount: Number(summary.company_target_amount || 0),
      company_target_quantity: Number(summary.company_target_quantity || 0),
      weekday_ratios: buildWeekdayRatiosPayload(),
      shops: shops.value.map((shop) => ({
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        ratio: Number(shop.ratio_percent || 0) / 100,
        target_amount: Number(shop.target_amount || 0),
        target_quantity: Number(shop.target_quantity || 0)
      }))
    })
    ElMessage.success('店铺目标已保存')
    await loadWorkbench()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '保存店铺目标失败')
  } finally {
    saving.value = false
  }
}

async function copyPrevMonth() {
  copying.value = true
  try {
    await api.copyPrevMonthShopTargetWorkbench(yearMonth.value)
    ElMessage.success('已复制上月目标')
    await loadWorkbench()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '复制上月目标失败')
  } finally {
    copying.value = false
  }
}

function openDailyDrawer(row) {
  currentShop.value = row
  dailyDrawerVisible.value = true
}

function buildTableSummary({ columns }) {
  return columns.map((column, index) => {
    if (index === 0) return '合计'
    if (column.label === '拆分比例') return `${totals.value.ratioPercent.toFixed(2)}%`
    if (column.label === '目标销售额') return formatAmount(totals.value.amount)
    if (column.label === '订单目标') return totals.value.quantity
    if (column.label === '日目标') return canSave.value ? '可保存' : '待对齐'
    return ''
  })
}

function formatAmount(value) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2
  }).format(Number(value || 0))
}

function formatCompactAmount(value) {
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1
  }).format(Number(value || 0))
}

onMounted(loadWorkbench)
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}

.month-picker {
  width: 160px;
}

.summary-panel {
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
}

.validation-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
  padding: 8px 10px;
  border: 1px solid #f3d19e;
  border-radius: 6px;
  background: #fdf6ec;
  color: #b88230;
  font-size: 12px;
}

.validation-strip.is-valid {
  border-color: #b3e19d;
  background: #f0f9eb;
  color: #529b2e;
}

.validation-strip .invalid {
  color: #c45656;
  font-weight: 600;
}

.summary-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  align-items: end;
}

.number-input,
.cell-number {
  width: 100%;
}

.cell-number :deep(.el-input__wrapper) {
  padding-left: 6px;
  padding-right: 28px;
}

.percent-suffix {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.split-actions {
  display: flex;
  gap: 8px;
}

.shop-cell {
  display: grid;
  gap: 2px;
  line-height: 1.25;
}

.shop-cell span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.weekday-ratio-panel {
  margin: 14px 0;
}

.panel-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.weekday-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(88px, 1fr));
  gap: 8px;
}

.weekday-cell {
  display: grid;
  gap: 4px;
  font-size: 12px;
}

.weekday-input {
  width: 100%;
}

.weekday-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.daily-calendar {
  display: grid;
  grid-template-columns: repeat(7, minmax(78px, 1fr));
  gap: 6px;
  margin-top: 12px;
}

.daily-calendar-cell {
  min-height: 76px;
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-extra-light);
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.daily-calendar-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
}

.daily-table {
  margin-top: 12px;
}
</style>
