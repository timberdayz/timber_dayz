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
          <div class="action-list">
            <el-button type="primary" @click="startTask">开始处理</el-button>
            <el-button plain @click="submitResult">提交结果</el-button>
            <el-button v-if="businessRoute" plain @click="goToBusinessPage">前往业务页处理</el-button>
          </div>
        </el-card>

        <el-card shadow="hover" class="detail-card">
          <template #header>协作补充</template>
          <div class="action-list">
            <el-button plain @click="appendComment">补充评论</el-button>
            <el-button plain @click="appendSupplement">补充结构化数据</el-button>
          </div>
        </el-card>

        <el-card shadow="hover" class="detail-card">
          <template #header>发起人操作</template>
          <div class="action-list">
            <el-button plain @click="closeByInitiator">关闭未开始任务</el-button>
            <el-button plain @click="requestCancel">申请取消</el-button>
          </div>
        </el-card>

        <el-card shadow="hover" class="detail-card">
          <template #header>管理员操作</template>
          <div class="action-list">
            <el-button plain @click="reassignTask">重派任务</el-button>
            <el-button plain @click="takeOverTask">接管任务</el-button>
            <el-button type="danger" plain @click="forceCloseTask">强制关闭</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import employeeTasksApi from '@/api/employeeTasks.js'

const route = useRoute()
const router = useRouter()
const task = ref({})

const businessRoute = computed(() => {
  const sourceRecordId = String(task.value?.source_record_id || '')
  if (task.value?.source_module === 'expense-management') {
    const [yearMonth, platformCode, shopId] = sourceRecordId.split(':')
    if (!yearMonth || !shopId) return ''
    return `/expense-management?task_id=${route.params.taskId}&year_month=${encodeURIComponent(yearMonth)}&shop_id=${encodeURIComponent(shopId)}&platform_code=${encodeURIComponent(platformCode || '')}`
  }
  if (task.value?.source_module === 'performance-management') {
    const [yearMonth, employeeCode] = sourceRecordId.split(':')
    if (!yearMonth || !employeeCode) return ''
    return `/hr-performance-display?task_id=${route.params.taskId}&year_month=${encodeURIComponent(yearMonth)}&employee_code=${encodeURIComponent(employeeCode)}`
  }
  if (task.value?.source_module === 'training' && sourceRecordId) {
    return `/training/assignments/${encodeURIComponent(sourceRecordId)}`
  }
  return ''
})

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

const appendComment = async () => {
  task.value = await employeeTasksApi.appendComment(route.params.taskId, 'collaborator comment from task detail')
}

const appendSupplement = async () => {
  task.value = await employeeTasksApi.appendSupplement(route.params.taskId, { supplemented: true })
}

const closeByInitiator = async () => {
  task.value = await employeeTasksApi.closeByInitiator(route.params.taskId, 'initiator close from task detail')
}

const requestCancel = async () => {
  task.value = await employeeTasksApi.requestCancel(route.params.taskId, 'initiator cancel request from task detail')
}

const reassignTask = async () => {
  task.value = await employeeTasksApi.reassignTask(route.params.taskId, 2, 'admin reassignment from task detail')
}

const takeOverTask = async () => {
  task.value = await employeeTasksApi.takeOverTask(route.params.taskId, 'admin takeover from task detail')
}

const forceCloseTask = async () => {
  task.value = await employeeTasksApi.forceCloseTask(route.params.taskId, 'admin force close from task detail')
}

const goToBusinessPage = () => {
  if (!businessRoute.value) return
  router.push(businessRoute.value)
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

.action-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
