<template>
  <div class="erp-page-container">
    <PageHeader
      title="培训分配"
      subtitle="查看人员、岗位、培训项目、截止时间和执行状态"
      family="admin"
    >
      <template #actions>
        <el-button type="primary" @click="createAssignmentDialogVisible = true">新建培训分配</el-button>
      </template>
    </PageHeader>

    <el-card shadow="hover">
      <el-table :data="items" empty-text="暂无培训分配">
        <el-table-column prop="employee_name" label="员工姓名" min-width="120" />
        <el-table-column prop="employee_code" label="员工编号" min-width="120" />
        <el-table-column prop="department" label="部门" min-width="120" />
        <el-table-column prop="program_name" label="培训项目" min-width="180" />
        <el-table-column prop="learning_status" label="学习状态" min-width="120" />
        <el-table-column prop="current_status" label="当前状态" min-width="120" />
        <el-table-column prop="due_date" label="截止日期" min-width="120" />
        <el-table-column prop="supervisor_name" label="直属主管" min-width="120" />
      </el-table>
    </el-card>

    <el-dialog v-model="createAssignmentDialogVisible" title="新建培训分配" width="640px">
      <el-form :model="assignmentForm" label-width="120px">
        <el-form-item label="员工姓名">
          <el-input v-model="assignmentForm.employee_name" />
        </el-form-item>
        <el-form-item label="员工编号">
          <el-input v-model="assignmentForm.employee_code" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="assignmentForm.department" />
        </el-form-item>
        <el-form-item label="岗位">
          <el-input v-model="assignmentForm.role_name" />
        </el-form-item>
        <el-form-item label="培训项目">
          <el-input v-model="assignmentForm.program_name" />
        </el-form-item>
        <el-form-item label="学习状态">
          <el-input v-model="assignmentForm.learning_status" />
        </el-form-item>
        <el-form-item label="当前状态">
          <el-input v-model="assignmentForm.current_status" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-input v-model="assignmentForm.due_date" />
        </el-form-item>
        <el-form-item label="直属主管">
          <el-input v-model="assignmentForm.supervisor_name" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="assignmentForm.note" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createAssignmentDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateAssignment">保存</el-button>
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
const createAssignmentDialogVisible = ref(false)
const assignmentForm = ref({
  employee_name: '',
  employee_code: '',
  department: '',
  role_name: '',
  program_name: 'ERP 操作培训第一期',
  learning_status: '待学习',
  current_status: '待学习',
  due_date: '2026-04-22',
  supervisor_name: '',
  note: ''
})

const loadAssignments = async () => {
  const response = await trainingApi.getAssignments()
  items.value = response.items || []
}

const handleCreateAssignment = async () => {
  const created = await trainingApi.createAssignment(assignmentForm.value)
  items.value = [...items.value, created]
  createAssignmentDialogVisible.value = false
  assignmentForm.value = {
    employee_name: '',
    employee_code: '',
    department: '',
    role_name: '',
    program_name: 'ERP 操作培训第一期',
    learning_status: '待学习',
    current_status: '待学习',
    due_date: '2026-04-22',
    supervisor_name: '',
    note: ''
  }
  ElMessage.success('培训分配已创建')
}

onMounted(() => {
  void loadAssignments()
})
</script>
