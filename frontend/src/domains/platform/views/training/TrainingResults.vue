<template>
  <div class="erp-page-container">
    <PageHeader
      title="培训结果"
      subtitle="查看考试成绩、通过状态和补考处理情况"
      family="admin"
    />

    <el-card shadow="hover">
      <el-table :data="items" empty-text="暂无培训结果">
        <el-table-column prop="employee_name" label="员工姓名" min-width="120" />
        <el-table-column prop="employee_code" label="员工编号" min-width="120" />
        <el-table-column prop="program_name" label="培训项目" min-width="180" />
        <el-table-column label="考试成绩" min-width="100">
          <template #default="{ row }">
            {{ row.exam_score ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="current_status" label="当前状态" min-width="120" />
        <el-table-column label="是否通过" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_passed ? 'success' : 'warning'">
              {{ row.is_passed ? '通过' : '未通过' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="最近更新" min-width="160" />
        <el-table-column prop="note" label="备注" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" min-width="120">
          <template #default="{ row }">
            <el-button link type="primary" @click="openUpdateResultDialog(row)">更新结果</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="updateResultDialogVisible" title="更新培训结果" width="560px">
      <el-form :model="resultForm" label-width="120px">
        <el-form-item label="员工编号">
          <el-input v-model="resultForm.employee_code" disabled />
        </el-form-item>
        <el-form-item label="考试成绩">
          <el-input-number v-model="resultForm.exam_score" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="当前状态">
          <el-input v-model="resultForm.current_status" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="resultForm.note" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="updateResultDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleUpdateResult">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import trainingApi from '@/api/training.js'

const items = ref([])
const updateResultDialogVisible = ref(false)
const resultForm = ref({
  assignment_id: '',
  employee_code: '',
  exam_score: 0,
  current_status: '已通过',
  note: ''
})

const loadResults = async () => {
  const response = await trainingApi.getResults()
  items.value = response.items || []
}

const openUpdateResultDialog = (row) => {
  resultForm.value = {
    assignment_id: row.assignment_id,
    employee_code: row.employee_code,
    exam_score: row.exam_score ?? 0,
    current_status: row.current_status,
    note: row.note ?? ''
  }
  updateResultDialogVisible.value = true
}

const handleUpdateResult = async () => {
  const updated = await trainingApi.updateResult(resultForm.value.assignment_id, {
    exam_score: resultForm.value.exam_score,
    current_status: resultForm.value.current_status,
    note: resultForm.value.note
  })
  items.value = items.value.map((item) =>
    item.assignment_id === updated.assignment_id
      ? {
          ...item,
          exam_score: updated.exam_score,
          current_status: updated.current_status,
          is_passed: updated.current_status === '已通过',
          note: updated.note,
          updated_at: updated.updated_at
        }
      : item
  )
  updateResultDialogVisible.value = false
  ElMessage.success('培训结果已更新')
}

onMounted(() => {
  void loadResults()
})
</script>
