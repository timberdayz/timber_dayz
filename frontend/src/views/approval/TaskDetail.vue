<template>
  <div class="employee-task-detail erp-page-container">
    <PageHeader
      title="任务详情"
      subtitle="查看关联对象、处理时间线和当前可执行动作。"
      family="admin"
    />

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="hover" class="detail-card">
          <template #header>关联对象</template>
          <div class="detail-line">任务标题：{{ task.title || '--' }}</div>
          <div class="detail-line">任务类型：{{ task.task_type || '--' }}</div>
          <div class="detail-line">来源模块：{{ task.source_module || '--' }}</div>
          <div class="detail-line">当前状态：{{ task.status || '--' }}</div>
        </el-card>

        <el-card shadow="hover" class="detail-card">
          <template #header>处理时间线</template>
          <el-timeline>
            <el-timeline-item
              v-for="entry in task.timeline || []"
              :key="entry.id"
              :timestamp="entry.created_at || ''"
            >
              {{ entry.message }}
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="hover" class="detail-card">
          <template #header>处理动作</template>
          <el-button type="primary" @click="startTask">开始处理</el-button>
          <el-button plain @click="submitResult">提交结果</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import employeeTasksApi from '@/api/employeeTasks.js'

const route = useRoute()
const task = ref({})

const loadTask = async () => {
  task.value = await employeeTasksApi.getTask(route.params.taskId)
}

const startTask = async () => {
  task.value = await employeeTasksApi.startTask(route.params.taskId)
}

const submitResult = async () => {
  task.value = await employeeTasksApi.submitTask(route.params.taskId, {
    completion_payload: { submitted: true },
    result_comment: 'submitted from task detail',
    requires_confirmation: true
  })
}

onMounted(() => {
  void loadTask()
})
</script>

<style scoped>
.detail-card + .detail-card {
  margin-top: 16px;
}

.detail-line {
  margin-bottom: 8px;
  color: #606266;
}
</style>
