<template>
  <div class="operation-workbench erp-page-container erp-page--admin">
    <PageHeader title="运营绩效" subtitle="按月配置评分规则、确认参与店铺，并完成店铺运营数据录入。" family="admin" />

    <section class="toolbar">
      <el-date-picker v-model="yearMonth" type="month" value-format="YYYY-MM" format="YYYY-MM" class="month-picker" @change="loadAll" />
      <el-button :icon="CopyDocument" :loading="copying" @click="copyPrevious">复制上月规则</el-button>
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </section>

    <el-steps :active="activeStep" finish-status="success" class="workbench-steps">
      <el-step title="评分规则" @click="activeStep = 0" />
      <el-step title="店铺范围确认" @click="activeStep = 1" />
      <el-step title="店铺数据录入与保存" @click="activeStep = 2" />
    </el-steps>

    <section v-show="activeStep === 0" class="step-panel">
      <div class="panel-heading">
        <div>
          <h2>评分规则</h2>
          <p>量化指标使用所有参与店铺共用的目标值；人工指标仅配置单项满分。</p>
        </div>
        <el-button type="primary" :icon="Check" :disabled="!canSaveRules" :loading="savingRules" @click="saveRules">保存规则</el-button>
      </div>

      <section class="score-summary" :class="{ invalid: !scoreBudgetMatches }">
        <span>已分配满分 {{ assignedMaxScore.toFixed(2) }}</span>
        <span>运营满分 {{ operationMaxScore.toFixed(2) }}</span>
        <span v-if="!scoreBudgetMatches">启用指标满分之和必须等于运营满分</span>
      </section>

      <el-table v-loading="loading" :data="metrics" border stripe class="erp-table">
        <el-table-column label="启用" width="76" align="center"><template #default="{ row }"><el-switch v-model="row.is_enabled" /></template></el-table-column>
        <el-table-column prop="metric_name" label="运营指标" min-width="180"><template #default="{ row }"><span>{{ row.metric_name }}</span><small>{{ row.metric_code }}</small></template></el-table-column>
        <el-table-column prop="metric_direction" label="评分方向" width="128" />
        <el-table-column label="统一目标值" width="165">
          <template #default="{ row }">
            <span v-if="row.manual_score_enabled" class="muted">人工评分无需目标值</span>
            <el-input-number v-else v-model="row.target_value" :disabled="!row.is_enabled" :min="0" :precision="2" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="满分" width="130"><template #default="{ row }"><el-input-number v-model="row.max_score" :disabled="!row.is_enabled" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
        <el-table-column label="罚分" width="96" align="center"><template #default="{ row }"><el-switch v-model="row.penalty_enabled" :disabled="!row.is_enabled || row.manual_score_enabled" /></template></el-table-column>
      </el-table>
    </section>

    <section v-show="activeStep === 1" class="step-panel">
      <div class="panel-heading">
        <div>
          <h2>店铺范围确认</h2>
          <p>系统载入当月有效经营店铺。标准名与别名用于识别；不参与备注可选。</p>
        </div>
        <div class="panel-actions"><el-button @click="includeAllShops">全部参与</el-button><el-button @click="excludeAllShops">全部不参与</el-button><el-button v-if="scopeConfirmed" @click="revokeScope">撤销范围</el-button><el-button type="primary" :icon="Check" :loading="savingScope" @click="saveScope">确认范围</el-button></div>
      </div>

      <section class="scope-summary">
        <span>启用店铺 {{ scopeShops.length }}</span><span>参与 {{ includedShopCount }}</span><span>不参与 {{ scopeShops.length - includedShopCount }}</span>
        <el-tag :type="scopeReady ? 'success' : 'warning'">{{ scopeReady ? '本月范围已确认' : '范围待确认' }}</el-tag>
      </section>

      <el-table v-loading="loadingScope" :data="scopeShops" border stripe class="erp-table">
        <el-table-column prop="platform_code" label="平台" width="140" />
        <el-table-column prop="shop_id" label="店铺 ID" min-width="180" />
        <el-table-column prop="standard_name" label="标准店铺名" min-width="180"><template #default="{ row }">{{ row.standard_name || row.shop_id }}</template></el-table-column>
        <el-table-column label="店铺别名" min-width="200"><template #default="{ row }"><span>{{ (row.aliases || []).join('、') || '-' }}</span></template></el-table-column>
        <el-table-column label="是否参与" width="125" align="center"><template #default="{ row }"><el-switch v-model="row.is_included" active-text="参与" inactive-text="不参与" @change="scopeDirty = true" /></template></el-table-column>
        <el-table-column label="备注（可选）" min-width="260"><template #default="{ row }"><el-input v-model="row.exclusion_reason" :disabled="row.is_included" placeholder="不参与时可填写备注" maxlength="512" show-word-limit clearable @input="scopeDirty = true" /></template></el-table-column>
      </el-table>
    </section>

    <section v-show="activeStep === 2" class="step-panel">
      <div class="panel-heading">
        <div>
          <h2>店铺数据录入与保存</h2>
          <p>仅展示已参与店铺。量化指标填写实际值；人工指标填写 0 至该指标满分之间的人工评分。</p>
        </div>
        <el-button type="primary" :icon="Check" :disabled="!scopeReady" :loading="savingEntries" @click="saveEntries">保存店铺数据</el-button>
      </div>

      <el-alert v-if="!scopeReady" title="请先确认当前店铺范围后再录入店铺运营数据。" type="warning" :closable="false" show-icon />
      <template v-else>
        <section class="scope-summary">
          <span>已完成 {{ entryCompletion.completed }}</span><span>待完成 {{ entryCompletion.pending }}</span>
          <el-tag :type="entryCompletion.pending ? 'warning' : 'success'">{{ entryCompletion.pending ? '存在待录入店铺' : '全部店铺已完成' }}</el-tag>
        </section>
        <el-table v-loading="loadingEntries" :data="entryShops" border stripe class="erp-table entry-shop-table">
          <el-table-column prop="platform_code" label="平台" width="130" />
          <el-table-column prop="shop_id" label="店铺 ID" min-width="165" />
          <el-table-column prop="shop_name" label="店铺名称" min-width="160"><template #default="{ row }">{{ row.shop_name || '-' }}</template></el-table-column>
          <el-table-column label="完成状态" width="120" align="center"><template #default="{ row }"><el-tag :type="getStoreEntryStatus(row) === 'completed' ? 'success' : 'warning'">{{ getStoreEntryStatus(row) === 'completed' ? '已完成' : '待录入' }}</el-tag></template></el-table-column>
          <el-table-column label="指标录入" min-width="520">
            <template #default="{ row }">
              <div class="metric-entry-list">
                <div v-for="metric in row.metrics" :key="metric.metric_code" class="metric-entry-row">
                  <div class="metric-entry-name"><strong>{{ metric.metric_name }}</strong><small>{{ metric.metric_code }}</small></div>
                  <span v-if="metric.is_manual" class="target-display">人工评分，满分 {{ Number(metric.max_score || 0).toFixed(2) }}</span>
                  <span v-else class="target-display">统一目标 {{ metric.target_value ?? '-' }}</span>
                  <el-input-number v-if="metric.is_manual" v-model="metric.manual_score_value" :min="0" :max="metric.max_score" :precision="2" controls-position="right" placeholder="人工评分" />
                  <el-input-number v-else v-model="metric.achieved_value" :min="0" :precision="2" controls-position="right" placeholder="实际值" />
                  <el-tag size="small" :type="isMetricComplete(metric) ? 'success' : 'warning'">{{ isMetricComplete(metric) ? '已录入' : '待录入' }}</el-tag>
                </div>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Check, CopyDocument, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'
import { buildEntryPayload, buildScopePayload, getStoreEntryStatus } from './operationPerformanceWorkbench'

const yearMonth = ref(new Date().toISOString().slice(0, 7))
const activeStep = ref(0)
const loading = ref(false)
const loadingScope = ref(false)
const loadingEntries = ref(false)
const savingRules = ref(false)
const savingScope = ref(false)
const savingEntries = ref(false)
const copying = ref(false)
const metrics = ref([])
const scopeShops = ref([])
const entryShops = ref([])
const scopeConfirmed = ref(false)
const scopeDirty = ref(false)
const entryCompletion = ref({ completed: 0, pending: 0 })
const catalogVersion = ref(null)
const performanceConfigId = ref(null)
const expectedPerformanceConfigUpdatedAt = ref(null)
const expectedUpdatedAt = ref(null)
const operationMaxScore = ref(0)

const assignedMaxScore = computed(() => metrics.value.filter((row) => row.is_enabled).reduce((sum, row) => sum + Number(row.max_score || 0), 0))
const scoreBudgetMatches = computed(() => Math.abs(assignedMaxScore.value - operationMaxScore.value) < 0.0001)
const canSaveRules = computed(() => catalogVersion.value && scoreBudgetMatches.value)
const includedShopCount = computed(() => scopeShops.value.filter((shop) => shop.is_included).length)
const scopeReady = computed(() => scopeConfirmed.value && !scopeDirty.value)

function unwrap(response) { return response?.data?.data || response?.data || response }
function errorMessage(error, fallback) { return error?.response?.data?.detail || error?.message || fallback }
function isMetricComplete(metric) { return metric.is_manual ? metric.manual_score_value !== null && metric.manual_score_value !== undefined : metric.achieved_value !== null && metric.achieved_value !== undefined }

async function loadRules() {
  const data = unwrap(await api.getOperationPerformanceWorkbench(yearMonth.value))
  metrics.value = data.metrics || []
  catalogVersion.value = data.catalog_version
  performanceConfigId.value = data.performance_config_id
  expectedPerformanceConfigUpdatedAt.value = data.performance_config_updated_at
  expectedUpdatedAt.value = data.updated_at
  operationMaxScore.value = Number(data.operation_max_score || 0)
}

async function loadScope() {
  loadingScope.value = true
  try {
    const data = unwrap(await api.getOperationPerformanceScope(yearMonth.value))
    scopeShops.value = data.shops || []
    scopeConfirmed.value = Boolean(data.is_confirmed)
    scopeDirty.value = false
  } finally { loadingScope.value = false }
}

async function loadEntries() {
  loadingEntries.value = true
  try {
    const data = unwrap(await api.getOperationPerformanceEntries(yearMonth.value))
    entryShops.value = data.shops || []
    scopeConfirmed.value = Boolean(data.scope_confirmed)
    entryCompletion.value = data.completion || { completed: 0, pending: 0 }
  } finally { loadingEntries.value = false }
}

async function loadAll() {
  loading.value = true
  try { await Promise.all([loadRules(), loadScope(), loadEntries()]) } catch (error) { ElMessage.error(errorMessage(error, '加载运营绩效失败')) } finally { loading.value = false }
}

async function saveRules() {
  if (!scoreBudgetMatches.value) return
  savingRules.value = true
  try {
    const data = unwrap(await api.applyOperationPerformanceWorkbench({
      year_month: yearMonth.value,
      catalog_version: catalogVersion.value,
      performance_config_id: performanceConfigId.value,
      expected_performance_config_updated_at: expectedPerformanceConfigUpdatedAt.value,
      expected_updated_at: expectedUpdatedAt.value,
      metrics: metrics.value.map((row) => ({
        metric_code: row.metric_code, is_enabled: row.is_enabled,
        target_value: row.manual_score_enabled ? null : row.target_value,
        max_score: row.max_score, penalty_enabled: row.manual_score_enabled ? false : row.penalty_enabled,
        penalty_threshold: row.penalty_threshold, penalty_per_unit: row.penalty_per_unit, penalty_max: row.penalty_max
      }))
    }))
    expectedUpdatedAt.value = data.updated_at
    ElMessage.success('运营评分规则已保存')
    await loadEntries()
  } catch (error) { ElMessage.error(errorMessage(error, '保存运营评分规则失败')) } finally { savingRules.value = false }
}

function includeAllShops() {
  scopeShops.value.forEach((shop) => { shop.is_included = true; shop.exclusion_reason = null })
  scopeDirty.value = true
}

function excludeAllShops() {
  scopeShops.value.forEach((shop) => { shop.is_included = false })
  scopeDirty.value = true
}

async function saveScope() {
  savingScope.value = true
  try {
    const data = unwrap(await api.applyOperationPerformanceScope(buildScopePayload(yearMonth.value, scopeShops.value)))
    scopeShops.value = data.shops || []
    scopeConfirmed.value = Boolean(data.is_confirmed)
    scopeDirty.value = false
    await loadEntries()
    activeStep.value = 2
    ElMessage.success('本月店铺范围已确认')
  } catch (error) { ElMessage.error(errorMessage(error, '确认店铺范围失败')) } finally { savingScope.value = false }
}

async function revokeScope() {
  try {
    await ElMessageBox.confirm('撤销后将清空本月店铺运营录入草稿，需重新确认店铺范围。', '撤销范围', { type: 'warning' })
    await api.revokeOperationPerformanceScope(yearMonth.value)
    await loadAll()
    activeStep.value = 1
    ElMessage.success('本月店铺范围已撤销')
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error, '撤销范围失败')) }
}

async function saveEntries() {
  if (!scopeReady.value) return
  savingEntries.value = true
  try {
    const data = unwrap(await api.applyOperationPerformanceEntries(buildEntryPayload(yearMonth.value, entryShops.value)))
    entryShops.value = data.shops || []
    entryCompletion.value = data.completion || { completed: 0, pending: 0 }
    ElMessage.success('店铺运营数据已保存')
  } catch (error) { ElMessage.error(errorMessage(error, '保存店铺运营数据失败')) } finally { savingEntries.value = false }
}

async function copyPrevious() {
  try {
    await ElMessageBox.confirm('仅复制上月评分规则和满分配置；本月店铺范围与店铺录入数据不会继承。', '复制上月规则', { type: 'warning' })
    copying.value = true
    const data = unwrap(await api.copyPrevMonthOperationPerformanceWorkbench(yearMonth.value))
    if (data.skipped?.length) ElMessage.warning(`已跳过 ${data.skipped.length} 个退役指标`)
    else ElMessage.success('已复制上月评分规则')
    await loadAll()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error, '复制上月规则失败')) } finally { copying.value = false }
}

onMounted(loadAll)
</script>

<style scoped>
.toolbar, .panel-heading, .panel-actions, .score-summary, .scope-summary { display: flex; align-items: center; }
.toolbar { gap: 8px; margin-bottom: 16px; }
.month-picker { width: 150px; }
.workbench-steps { margin: 0 0 18px; padding: 14px 18px; background: var(--el-fill-color-lighter); border: 1px solid var(--el-border-color-lighter); }
.workbench-steps :deep(.el-step) { cursor: pointer; }
.step-panel { min-height: 420px; }
.panel-heading { justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.panel-heading h2 { margin: 0 0 4px; font-size: 18px; font-weight: 600; }
.panel-heading p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.panel-actions { gap: 8px; flex-shrink: 0; }
.score-summary, .scope-summary { flex-wrap: wrap; gap: 16px; padding: 10px 12px; margin-bottom: 12px; border-left: 3px solid var(--el-color-success); background: var(--el-fill-color-light); }
.score-summary.invalid { border-color: var(--el-color-danger); color: var(--el-color-danger); }
.scope-summary { border-color: var(--el-color-primary); }
.muted, small { color: var(--el-text-color-secondary); }
small { display: block; margin-top: 3px; font-size: 12px; }
.metric-entry-list { display: grid; gap: 8px; }
.metric-entry-row { display: grid; grid-template-columns: minmax(130px, 1fr) minmax(145px, 1fr) 150px 64px; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.metric-entry-row:last-child { border-bottom: 0; }
.metric-entry-name { min-width: 0; }
.metric-entry-name strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.target-display { color: var(--el-text-color-regular); font-size: 13px; }
@media (max-width: 900px) { .panel-heading { align-items: flex-start; flex-direction: column; } .metric-entry-row { grid-template-columns: 1fr 1fr; } }
</style>
