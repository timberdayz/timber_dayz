<template>
  <div class="personal-workbench erp-page-container erp-page--admin">
    <PageHeader title="个人运营目标管理" subtitle="按月启用个人考核项、确认参与员工，并录入个人实绩；店铺基础分占个人绩效的 80 分。" family="admin" />

    <section class="toolbar">
      <el-date-picker v-model="yearMonth" type="month" value-format="YYYY-MM" format="YYYY-MM" class="month-picker" @change="loadAll" />
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </section>

    <el-alert v-if="isLegacy" type="warning" :closable="false" show-icon title="当前月份使用历史个人绩效输入项" description="历史数据保持只读兼容；请在新的空白月份启用受控个人运营目标。" class="legacy-alert" />
    <template v-else>
      <el-steps :active="activeStep" finish-status="success" class="workbench-steps">
        <el-step title="启用考核项" @click="activeStep = 0" />
        <el-step title="确认参与员工" @click="activeStep = 1" />
        <el-step title="录入个人实绩" @click="activeStep = 2" />
      </el-steps>

      <section v-show="activeStep === 0" class="step-panel">
        <div class="panel-heading"><div><h2>启用个人考核项</h2><p>只选择本月启用项；系统按目录顺序自动均分个人运营 20 分。</p></div><div class="panel-actions"><el-button v-if="scopeConfirmed" @click="startRuleChange">撤销范围后修改规则</el-button><el-button type="primary" :icon="Check" :disabled="!enabledCount || scopeConfirmed" :loading="savingRules" @click="saveRules">{{ scopeConfirmed ? '规则已冻结' : '保存规则' }}</el-button></div></div>
        <section class="score-summary"><span>已启用 {{ enabledCount }} 项</span><span>自动分配 {{ assignedScore }} / 20 分</span><el-tag :type="scopeConfirmed ? 'warning' : 'success'">{{ scopeConfirmed ? '参与范围已确认，规则已冻结' : '规则草稿，可继续修改' }}</el-tag></section>
        <el-table :data="metrics" border stripe class="erp-table">
          <el-table-column label="启用" width="76" align="center"><template #default="{ row }"><el-switch v-model="row.is_enabled" :disabled="scopeConfirmed" /></template></el-table-column>
          <el-table-column prop="metric_name" label="个人指标" min-width="180"><template #default="{ row }"><span>{{ row.metric_name }}</span><small>{{ row.metric_code }}</small></template></el-table-column>
          <el-table-column label="评分方向" width="130"><template #default="{ row }">{{ formatWorkbenchDirection(row.metric_direction) }}</template></el-table-column>
          <el-table-column label="固定目标" width="150"><template #default="{ row }">{{ row.default_target_value ?? '专项任务' }} {{ row.unit || '' }}</template></el-table-column>
          <el-table-column label="自动满分" width="110"><template #default="{ row }"><strong>{{ allocatedScores[row.metric_code] || 0 }}</strong></template></el-table-column>
          <el-table-column label="录入及评分说明" min-width="280"><template #default="{ row }">{{ formatWorkbenchGuidance(row) }}</template></el-table-column>
        </el-table>
      </section>

      <section v-show="activeStep === 1" class="step-panel">
        <div class="panel-heading"><div><h2>确认参与员工</h2><p>仅具备有效店铺归属和正销售目标的员工可参与正式个人绩效；不参与备注可选。</p></div><div class="panel-actions"><el-button v-if="scopeConfirmed" @click="revokeScope">撤销范围</el-button><el-button v-else @click="includeEligible">全部参与</el-button><el-button v-if="!scopeConfirmed" type="primary" :icon="Check" :loading="savingScope" @click="saveScope">确认范围</el-button></div></div>
        <section class="scope-summary"><span>在职员工 {{ scopeEmployees.length }}</span><span>参与 {{ includedCount }}</span><span>阻断 {{ blockedCount }}</span><el-tag :type="scopeConfirmed ? 'success' : 'warning'">{{ scopeConfirmed ? '范围已确认' : '范围待确认' }}</el-tag></section>
        <el-table :data="scopeEmployees" border stripe class="erp-table">
          <el-table-column prop="employee_name" label="姓名" min-width="130" /><el-table-column prop="employee_code" label="工号" min-width="130" /><el-table-column prop="department_name" label="部门" min-width="130" /><el-table-column prop="position_name" label="岗位" min-width="130" />
          <el-table-column label="店铺归属资格" min-width="230"><template #default="{ row }"><el-tag :type="row.eligibility_status === 'eligible' ? 'success' : 'danger'">{{ row.eligibility_status === 'eligible' ? '可参与' : '不可参与' }}</el-tag><div v-if="row.blocking_reasons?.length" class="blocking-reason">{{ row.blocking_reasons.join('；') }}</div></template></el-table-column>
          <el-table-column label="参与" width="110" align="center"><template #default="{ row }"><el-switch v-model="row.is_included" :disabled="scopeConfirmed || row.eligibility_status !== 'eligible'" @change="scopeDirty = true" /></template></el-table-column>
          <el-table-column label="备注（可选）" min-width="220"><template #default="{ row }"><el-input v-model="row.exclusion_note" :disabled="scopeConfirmed || row.is_included" maxlength="512" clearable placeholder="不参与时可填写" @input="scopeDirty = true" /></template></el-table-column>
        </el-table>
      </section>

      <section v-show="activeStep === 2" class="step-panel">
        <div class="panel-heading"><div><h2>录入个人实绩</h2><p>仅参与员工可录入。系统自动计算个人运营分；缺少任一指标时保持待完成。</p></div><el-button type="primary" :icon="Check" :disabled="!scopeReady" :loading="savingEntries" @click="saveEntries">保存个人实绩</el-button></div>
        <el-alert v-if="!scopeReady" title="请先确认本月参与员工范围后再录入个人实绩。" type="warning" :closable="false" show-icon />
        <template v-else><section class="scope-summary"><span>已完成 {{ completion.completed || 0 }}</span><span>待完成 {{ completion.pending || 0 }}</span></section><el-table :data="entryEmployees" border stripe class="erp-table entry-table"><el-table-column prop="employee_name" label="员工" min-width="150"><template #default="{ row }">{{ row.employee_name }}<small>{{ row.employee_code }}</small></template></el-table-column><el-table-column label="完成状态" width="110" align="center"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : 'warning'">{{ row.status === 'completed' ? '已完成' : '待录入' }}</el-tag></template></el-table-column><el-table-column label="指标录入" min-width="620"><template #default="{ row }"><div v-for="metric in row.metrics" :key="metric.metric_code" class="metric-row"><strong>{{ metric.metric_name }}</strong><span class="metric-meta">目标 {{ metric.target_value ?? '-' }} | 满分 {{ metric.max_score }} | {{ formatWorkbenchFormula(metric) }}</span><el-input-number v-if="isNumeric(metric)" v-model="metric.input_payload.actual_value" :min="0" :max="100" :precision="2" controls-position="right" /><template v-else-if="metric.input_kind === 'training_counts'"><el-input-number v-model="metric.input_payload.completed_count" :min="0" :precision="0" controls-position="right" placeholder="已完成" /><el-input-number v-model="metric.input_payload.required_count" :min="0" :precision="0" controls-position="right" placeholder="应完成" /></template><template v-else><el-select v-model="metric.input_payload.result" placeholder="任务结论" clearable><el-option label="完成" value="passed" /><el-option label="部分完成" value="partial" /><el-option label="未完成" value="failed" /></el-select><el-input v-if="['partial', 'failed'].includes(metric.input_payload.result)" v-model="metric.input_payload.note" maxlength="512" show-word-limit placeholder="请填写说明" /></template><el-tag size="small" :type="isPersonalMetricComplete(metric) ? 'success' : 'warning'">{{ isPersonalMetricComplete(metric) ? `自动得分 ${metric.auto_score ?? '-'}` : '待录入' }}</el-tag></div></template></el-table-column></el-table></template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Check, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'
import { allocatePersonalMetricScores, buildPersonalEntryPayload, buildPersonalScopePayload, isPersonalMetricComplete } from './personalPerformanceWorkbench'
import { formatWorkbenchDirection, formatWorkbenchFormula, formatWorkbenchGuidance } from './workbenchDisplay'

const yearMonth = ref(new Date().toISOString().slice(0, 7)); const activeStep = ref(0); const loading = ref(false); const savingRules = ref(false); const savingScope = ref(false); const savingEntries = ref(false)
const metrics = ref([]); const scopeEmployees = ref([]); const entryEmployees = ref([]); const planVersion = ref(null); const scopeConfirmed = ref(false); const scopeDirty = ref(false); const completion = ref({ completed: 0, pending: 0 }); const calculationMode = ref('legacy_inputs'); const legacyReadOnly = ref(false)
const unwrap = (response) => response?.data?.data || response?.data || response
const messageFor = (error, fallback) => error?.response?.data?.detail || error?.message || fallback
const allocatedScores = computed(() => allocatePersonalMetricScores(metrics.value)); const enabledCount = computed(() => metrics.value.filter((metric) => metric.is_enabled).length); const assignedScore = computed(() => Object.values(allocatedScores.value).reduce((total, value) => total + value, 0)); const includedCount = computed(() => scopeEmployees.value.filter((employee) => employee.is_included).length); const blockedCount = computed(() => scopeEmployees.value.filter((employee) => employee.eligibility_status === 'blocked').length); const scopeReady = computed(() => scopeConfirmed.value && !scopeDirty.value); const isLegacy = computed(() => legacyReadOnly.value)
const isNumeric = (metric) => !['training_counts', 'special_task'].includes(metric.input_kind)
async function loadRules() { const data = unwrap(await api.getPersonalPerformanceWorkbench(yearMonth.value)); calculationMode.value = data.calculation_mode; legacyReadOnly.value = Boolean(data.legacy_read_only); planVersion.value = data.plan_version; scopeConfirmed.value = Boolean(data.scope_confirmed); metrics.value = (data.metrics || []).map((metric) => ({ ...metric, is_enabled: metric.max_score > 0 || metric.is_enabled })) }
async function loadScope() { const data = unwrap(await api.getPersonalPerformanceScope(yearMonth.value)); scopeEmployees.value = data.employees || []; scopeConfirmed.value = Boolean(data.scope_confirmed); planVersion.value = data.plan_version ?? planVersion.value; scopeDirty.value = false }
async function loadEntries() { const data = unwrap(await api.getPersonalPerformanceEntries(yearMonth.value)); entryEmployees.value = data.employees || []; completion.value = data.completion || { completed: 0, pending: 0 }; scopeConfirmed.value = Boolean(data.scope_confirmed) }
async function loadAll() { loading.value = true; try { await loadRules(); await Promise.all([loadScope(), loadEntries()]) } catch (error) { ElMessage.error(messageFor(error, '加载个人运营目标失败')) } finally { loading.value = false } }
async function saveRules() { savingRules.value = true; try { const data = unwrap(await api.applyPersonalPerformanceWorkbench({ year_month: yearMonth.value, expected_plan_version: planVersion.value, metrics: metrics.value.map((metric) => ({ metric_code: metric.metric_code, is_enabled: Boolean(metric.is_enabled) })) })); calculationMode.value = data.calculation_mode; planVersion.value = data.plan_version; metrics.value = data.metrics || []; ElMessage.success('个人运营目标规则已保存'); await loadScope() } catch (error) { ElMessage.error(messageFor(error, '保存个人运营目标规则失败')) } finally { savingRules.value = false } }
function includeEligible() { scopeEmployees.value.forEach((employee) => { if (employee.eligibility_status === 'eligible') { employee.is_included = true; employee.exclusion_note = null } }); scopeDirty.value = true }
async function saveScope() { savingScope.value = true; try { const data = unwrap(await api.applyPersonalPerformanceScope(buildPersonalScopePayload(yearMonth.value, planVersion.value, scopeEmployees.value))); scopeEmployees.value = data.employees || []; planVersion.value = data.plan_version; scopeConfirmed.value = Boolean(data.scope_confirmed); scopeDirty.value = false; await loadEntries(); activeStep.value = 2; ElMessage.success('本月参与员工范围已确认') } catch (error) { ElMessage.error(messageFor(error, '确认参与员工范围失败')) } finally { savingScope.value = false } }
async function revokeScope() { try { await ElMessageBox.confirm('撤销后将清空本月个人实绩草稿，需要重新确认参与员工范围。', '撤销范围', { type: 'warning' }); const data = unwrap(await api.revokePersonalPerformanceScope(yearMonth.value, planVersion.value)); scopeEmployees.value = data.employees || []; planVersion.value = data.plan_version; scopeConfirmed.value = false; scopeDirty.value = false; entryEmployees.value = []; activeStep.value = 1; ElMessage.success('参与员工范围已撤销') } catch (error) { if (error !== 'cancel') ElMessage.error(messageFor(error, '撤销参与员工范围失败')) } }
async function startRuleChange() { await revokeScope(); if (!scopeConfirmed.value) activeStep.value = 0 }
async function saveEntries() { savingEntries.value = true; try { const data = unwrap(await api.applyPersonalPerformanceEntries(buildPersonalEntryPayload(yearMonth.value, planVersion.value, entryEmployees.value))); entryEmployees.value = data.employees || []; completion.value = data.completion || completion.value; ElMessage.success('个人实绩已保存') } catch (error) { ElMessage.error(messageFor(error, '保存个人实绩失败')) } finally { savingEntries.value = false } }
onMounted(loadAll)
</script>

<style scoped>
.toolbar,.panel-heading,.panel-actions,.score-summary,.scope-summary{display:flex;align-items:center}.toolbar,.panel-actions{gap:8px;margin-bottom:16px}.month-picker{width:150px}.workbench-steps{margin:0 0 18px;padding:14px 18px;background:var(--el-fill-color-lighter);border:1px solid var(--el-border-color)}.step-panel{margin-top:8px}.panel-heading{justify-content:space-between;gap:16px;margin-bottom:14px}.panel-heading h2{margin:0 0 6px;font-size:18px}.panel-heading p{margin:0;color:var(--el-text-color-secondary)}.score-summary,.scope-summary{gap:18px;margin:12px 0;padding:12px 14px;border-left:3px solid var(--el-color-primary);background:var(--el-fill-color-lighter)}.legacy-alert{margin-bottom:16px}.blocking-reason{margin-top:5px;font-size:12px;color:var(--el-color-danger)}small{display:block;margin-top:4px;color:var(--el-text-color-secondary)}.metric-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--el-border-color-lighter)}.metric-row:last-child{border-bottom:0}.metric-row strong{min-width:110px}.metric-meta{min-width:180px;color:var(--el-text-color-secondary);font-size:12px}.metric-row :deep(.el-input-number){width:132px}.metric-row :deep(.el-select){width:132px}.metric-row :deep(.el-input){width:230px}@media (max-width:760px){.panel-heading{align-items:flex-start;flex-direction:column}.metric-row{align-items:flex-start;flex-direction:column}}
</style>
