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
      <el-button type="primary" :icon="Check" @click="saveWorkbench" :loading="saving">
        保存目标
      </el-button>
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
      class="erp-table target-table"
    >
      <el-table-column label="平台" prop="platform_code" width="105" />
      <el-table-column label="店铺" width="360">
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

    <el-drawer v-model="dailyDrawerVisible" title="店铺日目标" size="420px">
      <template v-if="currentShop">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="标准名">{{ currentShop.standard_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺ID">{{ currentShop.shop_id }}</el-descriptions-item>
          <el-descriptions-item label="别名">{{ currentShop.aliases?.join(' / ') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="月目标">{{ formatAmount(currentShop.target_amount) }}</el-descriptions-item>
          <el-descriptions-item label="日均销售额">{{ formatAmount(currentShop.target_amount / daysInMonth) }}</el-descriptions-item>
          <el-descriptions-item label="日均订单">{{ Math.round((currentShop.target_quantity || 0) / daysInMonth) }}</el-descriptions-item>
        </el-descriptions>
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

const daysInMonth = computed(() => {
  const [year, month] = yearMonth.value.split('-').map(Number)
  return new Date(year, month, 0).getDate()
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
  const ratio = 1 / shops.value.length
  shops.value.forEach((shop) => {
    shop.ratio = ratio
    shop.ratio_percent = Number((ratio * 100).toFixed(2))
  })
  splitByRatio()
}

function splitByRatio() {
  const totalRatio = shops.value.reduce((sum, shop) => sum + Number(shop.ratio_percent || 0), 0)
  if (!totalRatio) return
  shops.value.forEach((shop) => {
    const normalizedRatio = Number(shop.ratio_percent || 0) / totalRatio
    shop.ratio = normalizedRatio
    shop.target_amount = Number((summary.company_target_amount * normalizedRatio).toFixed(2))
    shop.target_quantity = Math.round(summary.company_target_quantity * normalizedRatio)
  })
}

async function saveWorkbench() {
  saving.value = true
  try {
    await api.applyShopTargetWorkbench({
      year_month: yearMonth.value,
      company_target_amount: Number(summary.company_target_amount || 0),
      company_target_quantity: Number(summary.company_target_quantity || 0),
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

function formatAmount(value) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2
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
</style>
