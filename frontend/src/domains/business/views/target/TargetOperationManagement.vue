<template>
  <div class="target-operation-management erp-page-container erp-page--admin">
    <PageHeader
      title="运营目标管理"
      subtitle="聚焦运营目标配置与查看。当前版本先收口现有 operation 目标，避免与店铺目标、产品目标和战役目标混在一个大表单中。"
      family="admin"
    />

    <el-card shadow="never" class="policy-card">
      <template #header>使用说明</template>
      <div class="policy-grid">
        <div class="policy-item">
          <div class="policy-label">当前作用层</div>
          <div class="policy-text">当前 operation 目标仍进入店铺绩效的运营维度，不直接形成个人绩效分。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">配置方式</div>
          <div class="policy-text">先选择运营指标模板，再填写目标值、实际值和满分；需要时再展开罚分或人工评分。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">后续方向</div>
          <div class="policy-text">店铺运营目标与个人运营目标将在后续模型重构后正式拆分为两套配置入口。</div>
        </div>
      </div>
    </el-card>

    <div class="action-bar">
      <el-date-picker
        v-model="filters.month"
        type="month"
        value-format="YYYY-MM"
        placeholder="选择月份"
        style="width: 160px;"
        @change="loadOperationTargets"
      />
      <el-select
        v-model="filters.metricCode"
        clearable
        placeholder="运营指标"
        style="width: 180px;"
        @change="loadOperationTargets"
      >
        <el-option
          v-for="item in operationMetricOptions"
          :key="item.code"
          :label="item.label"
          :value="item.code"
        />
      </el-select>
      <el-select
        v-model="filters.status"
        clearable
        placeholder="状态"
        style="width: 120px;"
        @change="loadOperationTargets"
      >
        <el-option label="全部状态" value="" />
        <el-option label="进行中" value="active" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建运营目标</el-button>
      <el-button :icon="Refresh" @click="loadOperationTargets">刷新</el-button>
    </div>

    <el-card>
      <el-table :data="targets.data" stripe v-loading="targets.loading" border class="erp-table">
        <el-table-column prop="target_name" label="目标名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="metric_name" label="运营指标" width="160" />
        <el-table-column prop="metric_direction" label="指标方向" width="130" />
        <el-table-column prop="target_value" label="目标值" width="110" align="right">
          <template #default="{ row }">{{ formatNumber(row.target_value) }}</template>
        </el-table-column>
        <el-table-column prop="achieved_value" label="实际值" width="110" align="right">
          <template #default="{ row }">{{ formatNumber(row.achieved_value) }}</template>
        </el-table-column>
        <el-table-column prop="max_score" label="满分" width="90" align="right">
          <template #default="{ row }">{{ formatNumber(row.max_score) }}</template>
        </el-table-column>
        <el-table-column prop="manual_score_enabled" label="人工评分" width="100" align="center">
          <template #default="{ row }">{{ row.manual_score_enabled ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : row.status === 'completed' ? 'info' : 'danger'" size="small">
              {{ row.status === 'active' ? '进行中' : row.status === 'completed' ? '已完成' : '已取消' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑运营目标' : '新建运营目标'"
      width="720px"
      @close="resetForm"
    >
      <TargetOperationEditor
        ref="editorRef"
        :model-value="form"
        :metric-options="operationMetricOptions"
        :rules="formRules"
        @metric-change="handleMetricChange"
      />

      <el-divider>公式预览</el-divider>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="作用层">当前进入店铺绩效的运营维度</el-descriptions-item>
        <el-descriptions-item label="计算方式">{{ formulaPreview.calculation }}</el-descriptions-item>
        <el-descriptions-item label="预计得分">{{ formulaPreview.score }}</el-descriptions-item>
        <el-descriptions-item label="对收入影响">当前仅通过店铺绩效间接影响店铺绩效系数，不直接形成个人绩效工资。</el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'
import TargetOperationEditor from './TargetOperationEditor.vue'
import { buildOperationTargetPreview } from './operationTargetFormula'

const operationMetricOptions = [
  { code: 'customer_satisfaction', label: '客户满意度', direction: 'higher_better' },
  { code: 'complaint_count', label: '客诉', direction: 'lower_better' },
  { code: 'reply_timeliness', label: '回复及时率', direction: 'higher_better' },
  { code: 'training_check', label: '培训检核', direction: 'higher_better' },
  { code: 'exam_score', label: '考试', direction: 'higher_better' },
  { code: 'manual_other', label: '其他', direction: 'manual_score' }
]

const targets = reactive({
  data: [],
  loading: false
})

const filters = reactive({
  month: new Date().toISOString().slice(0, 7),
  metricCode: '',
  status: ''
})

const dialogVisible = ref(false)
const submitting = ref(false)
const editorRef = ref(null)
const form = reactive({
  id: null,
  target_name: '',
  metric_code: '',
  metric_name: '',
  metric_direction: '',
  month: new Date().toISOString().slice(0, 7),
  target_value: 0,
  achieved_value: 0,
  max_score: 20,
  penalty_enabled: false,
  penalty_threshold: 0,
  penalty_per_unit: 0,
  penalty_max: 0,
  manual_score_enabled: false,
  manual_score_value: 0,
  description: ''
})

const formRules = {
  target_name: [{ required: true, message: '请输入目标名称', trigger: 'blur' }],
  metric_code: [{ required: true, message: '请选择运营指标', trigger: 'change' }],
  month: [{ required: true, message: '请选择月份', trigger: 'change' }]
}

const selectedMetric = computed(() => {
  return operationMetricOptions.find((item) => item.code === form.metric_code) || null
})

const formulaPreview = computed(() => buildOperationTargetPreview(form, selectedMetric.value))

function formatNumber(value) {
  if (value == null || value === '') return '—'
  return Number(value).toFixed(2)
}

function handleMetricChange() {
  form.metric_name = selectedMetric.value?.label || ''
  form.metric_direction = selectedMetric.value?.direction || ''
  form.manual_score_enabled = selectedMetric.value?.direction === 'manual_score'
  if (!form.penalty_enabled) {
    form.penalty_threshold = 0
    form.penalty_per_unit = 0
    form.penalty_max = 0
  }
}

function resetForm() {
  form.id = null
  form.target_name = ''
  form.metric_code = ''
  form.metric_name = ''
  form.metric_direction = ''
  form.month = filters.month || new Date().toISOString().slice(0, 7)
  form.target_value = 0
  form.achieved_value = 0
  form.max_score = 20
  form.penalty_enabled = false
  form.penalty_threshold = 0
  form.penalty_per_unit = 0
  form.penalty_max = 0
  form.manual_score_enabled = false
  form.manual_score_value = 0
  form.description = ''
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  form.id = row.id
  form.target_name = row.target_name || ''
  form.metric_code = row.metric_code || ''
  form.metric_name = row.metric_name || ''
  form.metric_direction = row.metric_direction || ''
  form.month = row.period_start ? String(row.period_start).slice(0, 7) : (filters.month || '')
  form.target_value = Number(row.target_value || 0)
  form.achieved_value = Number(row.achieved_value || 0)
  form.max_score = Number(row.max_score || 20)
  form.penalty_enabled = !!row.penalty_enabled
  form.penalty_threshold = Number(row.penalty_threshold || 0)
  form.penalty_per_unit = Number(row.penalty_per_unit || 0)
  form.penalty_max = Number(row.penalty_max || 0)
  form.manual_score_enabled = !!row.manual_score_enabled
  form.manual_score_value = Number(row.manual_score_value || 0)
  form.description = row.description || ''
  dialogVisible.value = true
}

async function loadOperationTargets() {
  targets.loading = true
  try {
    const response = await api.getTargets({
      target_type: 'operation',
      status: filters.status || undefined,
      page: 1,
      page_size: 100
    })
    const items = Array.isArray(response)
      ? response
      : (response?.items || response?.data?.items || response?.data || [])
    const month = filters.month || ''
    targets.data = (Array.isArray(items) ? items : []).filter((row) => {
      const period = String(row.period_start || '').slice(0, 7)
      const metricOk = !filters.metricCode || row.metric_code === filters.metricCode
      const monthOk = !month || period === month
      return metricOk && monthOk
    })
  } catch (error) {
    targets.data = []
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载运营目标失败')
  } finally {
    targets.loading = false
  }
}

async function handleSubmit() {
  const formInstance = editorRef.value?.formRef
  if (!formInstance) return
  handleMetricChange()
  await formInstance.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const periodStart = `${form.month}-01`
      const [y, m] = form.month.split('-')
      const lastDay = new Date(parseInt(y, 10), parseInt(m, 10), 0)
      const periodEnd = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`
      const payload = {
        target_name: form.target_name,
        target_type: 'operation',
        scope_type: 'shop',
        period_start: periodStart,
        period_end: periodEnd,
        target_amount: 0,
        target_quantity: 0,
        target_profit_amount: 0,
        metric_code: form.metric_code,
        metric_name: form.metric_name,
        metric_direction: form.metric_direction,
        target_value: Number(form.target_value || 0),
        achieved_value: Number(form.achieved_value || 0),
        max_score: Number(form.max_score || 0),
        penalty_enabled: !!form.penalty_enabled,
        penalty_threshold: form.penalty_enabled ? Number(form.penalty_threshold || 0) : undefined,
        penalty_per_unit: form.penalty_enabled ? Number(form.penalty_per_unit || 0) : undefined,
        penalty_max: form.penalty_enabled ? Number(form.penalty_max || 0) : undefined,
        manual_score_enabled: !!form.manual_score_enabled,
        manual_score_value: form.manual_score_enabled ? Number(form.manual_score_value || 0) : undefined,
        description: form.description || undefined
      }
      if (form.id) {
        await api.updateTarget(form.id, payload)
      } else {
        await api.createTarget(payload)
      }
      ElMessage.success(form.id ? '运营目标更新成功' : '运营目标创建成功')
      dialogVisible.value = false
      await loadOperationTargets()
    } catch (error) {
      ElMessage.error(error?.response?.data?.detail || error?.message || '保存运营目标失败')
    } finally {
      submitting.value = false
    }
  })
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除运营目标“${row.target_name}”吗？`, '确认删除', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await api.deleteTarget(row.id)
    ElMessage.success('删除成功')
    await loadOperationTargets()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '删除运营目标失败')
    }
  }
}

onMounted(() => {
  loadOperationTargets()
})
</script>

<style scoped>
.target-operation-management {
  min-height: calc(100vh - var(--header-height));
}

.policy-card {
  margin-bottom: 20px;
}

.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.policy-item {
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.policy-label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.policy-text {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
</style>
