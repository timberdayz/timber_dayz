<template>
  <div class="employee-task-center erp-page-container">
    <PageHeader
      title="我的任务"
      subtitle="统一查看今日待处理事项、我发起的协同任务，以及抄送我的任务。"
      family="admin"
    />

    <el-row :gutter="16" class="summary-row">
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="summary-label">待处理</div>
          <div class="summary-value">{{ summary.pending }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="summary-label">临近到期</div>
          <div class="summary-value">{{ summary.dueSoon }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="summary-label">超期</div>
          <div class="summary-value">{{ summary.overdue }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover">
      <div class="toolbar">
        <el-tabs v-model="activeScope" class="scope-tabs">
          <el-tab-pane label="我的任务" name="owner" />
          <el-tab-pane label="我发起的" name="initiated" />
          <el-tab-pane label="抄送我的" name="cc" />
        </el-tabs>
        <div class="filters">
          <el-select v-model="statusFilter" placeholder="按状态筛选" clearable class="filter-select">
            <el-option label="待处理" value="pending" />
            <el-option label="进行中" value="in_progress" />
            <el-option label="待确认" value="pending_confirmation" />
            <el-option label="已完成" value="completed" />
          </el-select>
          <el-select v-model="priorityFilter" placeholder="按优先级筛选" clearable class="filter-select">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </div>
      </div>

      <el-table :data="filteredTasks" empty-text="暂无任务">
        <el-table-column prop="title" label="任务标题" min-width="220" />
        <el-table-column prop="task_type" label="任务类型" min-width="160" />
        <el-table-column prop="source_module" label="来源模块" min-width="140" />
        <el-table-column prop="status" label="状态" width="160" />
        <el-table-column prop="priority" label="优先级" width="120" />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button type="primary" link @click="openTask(row.task_id, row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import employeeTasksApi from '@/api/employeeTasks.js'

const router = useRouter()
const activeScope = ref('owner')
const statusFilter = ref('')
const priorityFilter = ref('')
const tasks = ref([])

const summary = computed(() => ({
  pending: tasks.value.filter((task) => task.status === 'pending').length,
  dueSoon: tasks.value.filter((task) => task.priority === 'high').length,
  overdue: tasks.value.filter((task) => task.status === 'rejected').length
}))

const filteredTasks = computed(() =>
  tasks.value.filter((task) => {
    if (statusFilter.value && task.status !== statusFilter.value) {
      return false
    }
    if (priorityFilter.value && task.priority !== priorityFilter.value) {
      return false
    }
    return true
  })
)

const loadTasks = async () => {
  const response = await employeeTasksApi.listTasks(activeScope.value)
  tasks.value = response?.items || []
}

const openTask = (taskId, row) => {
  if (row?.source_module === 'training' && row?.source_record_id) {
    router.push(`/training/assignments/${row.source_record_id}`)
    return
  }
  router.push(`/my-tasks/${taskId}`)
}

onMounted(() => {
  void loadTasks()
})
</script>

<style scoped>
.summary-row {
  margin-bottom: 16px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
}

.summary-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 600;
  color: #303133;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

.scope-tabs {
  flex: 1;
}

.filters {
  display: flex;
  gap: 12px;
}

.filter-select {
  width: 160px;
}
</style>
