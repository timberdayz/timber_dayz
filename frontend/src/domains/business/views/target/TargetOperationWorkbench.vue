<template>
  <div class="operation-workbench erp-page-container erp-page--admin">
    <PageHeader title="运营绩效" subtitle="按月维护运营指标，运营总分将进入店铺绩效。" family="admin" />

    <section class="toolbar">
      <el-date-picker v-model="yearMonth" type="month" value-format="YYYY-MM" format="YYYY-MM" class="month-picker" @change="loadWorkbench" />
      <el-button :icon="CopyDocument" :loading="copying" @click="copyPrevious">复制上月</el-button>
      <el-button :icon="Refresh" :loading="loading" @click="loadWorkbench">刷新</el-button>
      <el-button type="primary" :icon="Check" :disabled="!canSave" :loading="saving" @click="save">保存</el-button>
    </section>

    <section class="score-summary" :class="{ invalid: !scoreBudgetMatches }">
      <span>已分配满分 {{ assignedMaxScore.toFixed(2) }}</span>
      <span>运营满分 {{ operationMaxScore.toFixed(2) }}</span>
      <span v-if="!scoreBudgetMatches">启用指标满分之和必须等于运营满分</span>
    </section>

    <el-table v-loading="loading" :data="metrics" border stripe class="erp-table">
      <el-table-column label="启用" width="76" align="center">
        <template #default="{ row }"><el-switch v-model="row.is_enabled" /></template>
      </el-table-column>
      <el-table-column prop="metric_name" label="运营指标" min-width="150">
        <template #default="{ row }"><span>{{ row.metric_name }}</span><small>{{ row.metric_code }}</small></template>
      </el-table-column>
      <el-table-column prop="metric_direction" label="评分方向" width="118" />
      <el-table-column label="目标值" width="145">
        <template #default="{ row }"><el-input-number v-model="row.target_value" :disabled="!row.is_enabled || row.manual_score_enabled" :min="0" :precision="2" controls-position="right" /></template>
      </el-table-column>
      <el-table-column label="实际值" width="145">
        <template #default="{ row }"><el-input-number v-model="row.achieved_value" :disabled="!row.is_enabled || row.manual_score_enabled" :min="0" :precision="2" controls-position="right" /></template>
      </el-table-column>
      <el-table-column label="人工评分" width="145">
        <template #default="{ row }"><el-input-number v-model="row.manual_score_value" :disabled="!row.is_enabled || !row.manual_score_enabled" :min="0" :max="row.max_score" :precision="2" controls-position="right" /></template>
      </el-table-column>
      <el-table-column label="满分" width="125">
        <template #default="{ row }"><el-input-number v-model="row.max_score" :disabled="!row.is_enabled" :min="0" :precision="2" controls-position="right" /></template>
      </el-table-column>
      <el-table-column label="罚分" width="90" align="center">
        <template #default="{ row }"><el-switch v-model="row.penalty_enabled" :disabled="!row.is_enabled" /></template>
      </el-table-column>
      <el-table-column label="店铺覆盖" width="105" fixed="right">
        <template #default="{ row }"><el-button text type="primary" @click="openOverrides(row)">维护</el-button></template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="overrideDrawerVisible" :title="selectedMetric?.metric_name || '店铺覆盖'" size="720px">
      <el-alert type="info" :closable="false" show-icon title="留空表示继承全店指标；覆盖与父指标使用同一完整自然月。" />
      <el-table :data="selectedOverrides" border class="override-table">
        <el-table-column label="平台" width="130"><template #default="{ row }"><el-input v-model="row.platform_code" /></template></el-table-column>
        <el-table-column label="店铺 ID" min-width="160"><template #default="{ row }"><el-input v-model="row.shop_id" /></template></el-table-column>
        <el-table-column label="目标值" width="125"><template #default="{ row }"><el-input-number v-model="row.target_value" :min="0" controls-position="right" /></template></el-table-column>
        <el-table-column label="实际值" width="125"><template #default="{ row }"><el-input-number v-model="row.achieved_value" :min="0" controls-position="right" /></template></el-table-column>
        <el-table-column label="人工评分" width="125"><template #default="{ row }"><el-input-number v-model="row.manual_score_value" :min="0" :max="selectedMetric?.max_score" controls-position="right" /></template></el-table-column>
        <el-table-column label="操作" width="68"><template #default="{ $index }"><el-button text type="danger" @click="removeOverride($index)">删除</el-button></template></el-table-column>
      </el-table>
      <template #footer><el-button @click="addOverride">新增店铺覆盖</el-button><el-button type="primary" @click="overrideDrawerVisible = false">完成</el-button></template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Check, CopyDocument, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'

const yearMonth = ref(new Date().toISOString().slice(0, 7))
const loading = ref(false)
const saving = ref(false)
const copying = ref(false)
const metrics = ref([])
const overrides = ref([])
const catalogVersion = ref(null)
const performanceConfigId = ref(null)
const expectedPerformanceConfigUpdatedAt = ref(null)
const expectedUpdatedAt = ref(null)
const operationMaxScore = ref(0)
const selectedMetric = ref(null)
const overrideDrawerVisible = ref(false)

const assignedMaxScore = computed(() => metrics.value.filter((row) => row.is_enabled).reduce((sum, row) => sum + Number(row.max_score || 0), 0))
const scoreBudgetMatches = computed(() => Math.abs(assignedMaxScore.value - operationMaxScore.value) < 0.0001)
const canSave = computed(() => catalogVersion.value && scoreBudgetMatches.value)
const selectedOverrides = computed(() => overrides.value.filter((row) => row.metric_code === selectedMetric.value?.metric_code))

function unwrap(response) {
  return response?.data?.data || response?.data || response
}

async function loadWorkbench() {
  loading.value = true
  try {
    const data = unwrap(await api.getOperationPerformanceWorkbench(yearMonth.value))
    metrics.value = data.metrics || []
    overrides.value = data.shop_overrides || []
    catalogVersion.value = data.catalog_version
    performanceConfigId.value = data.performance_config_id
    expectedPerformanceConfigUpdatedAt.value = data.performance_config_updated_at
    expectedUpdatedAt.value = data.updated_at
    operationMaxScore.value = Number(data.operation_max_score || 0)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载运营绩效失败')
  } finally {
    loading.value = false
  }
}

function openOverrides(metric) {
  selectedMetric.value = metric
  overrideDrawerVisible.value = true
}

function addOverride() {
  if (!selectedMetric.value) return
  overrides.value.push({ metric_code: selectedMetric.value.metric_code, platform_code: '', shop_id: '', target_value: null, achieved_value: null, manual_score_value: null })
}

function removeOverride(index) {
  const row = selectedOverrides.value[index]
  overrides.value.splice(overrides.value.indexOf(row), 1)
}

async function save() {
  if (!scoreBudgetMatches.value) return
  const invalidOverride = overrides.value.find((row) => !row.platform_code?.trim() || !row.shop_id?.trim())
  if (invalidOverride) {
    ElMessage.warning('请填写店铺覆盖的平台和店铺 ID')
    return
  }
  saving.value = true
  try {
    const data = unwrap(await api.applyOperationPerformanceWorkbench({
      year_month: yearMonth.value,
      catalog_version: catalogVersion.value,
      performance_config_id: performanceConfigId.value,
      expected_performance_config_updated_at: expectedPerformanceConfigUpdatedAt.value,
      expected_updated_at: expectedUpdatedAt.value,
      metrics: metrics.value.map((row) => ({
        metric_code: row.metric_code, is_enabled: row.is_enabled, target_value: row.target_value,
        achieved_value: row.achieved_value, max_score: row.max_score, penalty_enabled: row.penalty_enabled,
        penalty_threshold: row.penalty_threshold, penalty_per_unit: row.penalty_per_unit,
        penalty_max: row.penalty_max, manual_score_value: row.manual_score_value
      })),
      shop_overrides: overrides.value
    }))
    expectedUpdatedAt.value = data.updated_at
    ElMessage.success('运营绩效已保存')
    await loadWorkbench()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '保存运营绩效失败')
  } finally {
    saving.value = false
  }
}

async function copyPrevious() {
  try {
    await ElMessageBox.confirm('复制上月指标配置会清空实际值和人工评分。', '复制上月', { type: 'warning' })
    copying.value = true
    const data = unwrap(await api.copyPrevMonthOperationPerformanceWorkbench(yearMonth.value))
    if (data.skipped?.length) ElMessage.warning(`已跳过 ${data.skipped.length} 个退役指标`)
    else ElMessage.success('已复制上月配置')
    await loadWorkbench()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error?.response?.data?.detail || error?.message || '复制上月失败')
  } finally {
    copying.value = false
  }
}

onMounted(loadWorkbench)
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.month-picker { width: 150px; }
.score-summary { display: flex; gap: 20px; padding: 10px 12px; margin-bottom: 12px; border-left: 3px solid var(--el-color-success); background: var(--el-fill-color-light); }
.score-summary.invalid { border-color: var(--el-color-danger); color: var(--el-color-danger); }
small { display: block; color: var(--el-text-color-secondary); margin-top: 3px; }
.override-table { margin-top: 14px; }
</style>
