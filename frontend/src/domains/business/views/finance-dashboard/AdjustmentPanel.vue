<template>
  <el-card class="section-card">
    <template #header>
      <div class="card-header">
        <span>人工调整</span>
        <el-button type="primary" size="small" @click="openDialog">新增调整项</el-button>
      </div>
    </template>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="调整项金额符号含义：正数 = 从公司留存中扣减（减少留存）；负数 = 追加（增加留存）。"
      class="section-alert"
    />

    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      :title="error"
      class="section-alert"
    />

    <el-table v-if="rows.length" :data="rows" stripe class="adjustment-table">
      <el-table-column label="类型" min-width="140">
        <template #default="{ row }">{{ row.type_label }}</template>
      </el-table-column>
      <el-table-column label="金额" min-width="140" align="right">
        <template #default="{ row }">
          <span :class="valueClass(row.amount)">{{ formatAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原因" min-width="220">
        <template #default="{ row }">{{ row.reason || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作人" min-width="120">
        <template #default="{ row }">{{ row.created_by || '—' }}</template>
      </el-table-column>
      <el-table-column label="录入时间" min-width="180">
        <template #default="{ row }">{{ row.created_at_text }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="100" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" :loading="submitting" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else description="当前月份暂无人工调整项" />

    <el-dialog v-model="dialogVisible" title="新增人工调整项" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="调整类型" prop="adjustment_type">
          <el-select v-model="form.adjustment_type" style="width: 100%">
            <el-option
              v-for="option in adjustmentTypeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="调整金额" prop="amount">
          <el-input-number v-model="form.amount" :precision="2" :step="100" style="width: 100%" />
          <div class="form-hint">正数扣减公司留存，负数追加公司留存。</div>
        </el-form-item>
        <el-form-item label="调整原因" prop="reason">
          <el-input
            v-model="form.reason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="请写明调整原因（必填）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '@/utils/format'
import { formatDashboardAmount } from '@/stores/financeDashboard'

const props = defineProps({
  periodMonth: { type: String, default: '' },
  adjustments: { type: Array, default: () => [] },
  submitting: { type: Boolean, default: false },
  error: { type: String, default: '' },
  submitAdjustment: { type: Function, required: true },
  deleteAdjustment: { type: Function, required: true }
})

const adjustmentTypeOptions = [
  { value: 'manual_adjustment', label: '人工调整' },
  { value: 'cross_period_expense', label: '跨期费用' },
  { value: 'one_off_gain_loss', label: '一次性损益' },
  { value: 'correction', label: '错账更正' }
]

const typeLabelMap = adjustmentTypeOptions.reduce((accumulator, option) => {
  accumulator[option.value] = option.label
  return accumulator
}, {})

const rules = {
  adjustment_type: [{ required: true, message: '请选择调整类型', trigger: 'change' }],
  amount: [{ required: true, message: '请填写调整金额', trigger: 'blur' }],
  reason: [{ required: true, message: '请写明调整原因', trigger: 'blur' }]
}

const dialogVisible = ref(false)
const formRef = ref(null)
const form = reactive({
  adjustment_type: 'manual_adjustment',
  amount: 0,
  reason: ''
})

const formatAmount = (value) => formatDashboardAmount(value)

/** 负数显红：绝不截断为 0、绝不显示绝对值。 */
const valueClass = (value) => (Number(value) < 0 ? 'negative' : '')

const rows = computed(() =>
  (props.adjustments || []).map((row) => ({
    ...row,
    type_label: typeLabelMap[row?.adjustment_type] || row?.adjustment_type || '—',
    created_at_text: row?.created_at ? formatDateTime(row.created_at) : '—'
  }))
)

const resetForm = () => {
  form.adjustment_type = 'manual_adjustment'
  form.amount = 0
  form.reason = ''
  formRef.value?.clearValidate()
}

const openDialog = () => {
  resetForm()
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  if (!String(form.reason || '').trim()) {
    ElMessage.warning('调整原因必填')
    return
  }
  const succeeded = await props.submitAdjustment({
    period_month: props.periodMonth,
    adjustment_type: form.adjustment_type,
    amount: Number(form.amount),
    reason: String(form.reason).trim()
  })
  if (succeeded) {
    dialogVisible.value = false
    resetForm()
  }
}

const handleDelete = async (row) => {
  if (!row?.id) return
  try {
    await ElMessageBox.confirm('确认删除这条人工调整项吗？删除后本月公司留存会重新计算。', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch (_) {
    return
  }
  await props.deleteAdjustment(row.id)
}
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 600; }
.section-alert { margin-bottom: 16px; }
.adjustment-table { width: 100%; }
.form-hint { margin-top: 4px; color: #909399; font-size: 12px; line-height: 1.5; }
.negative { color: #f56c6c; }
</style>
