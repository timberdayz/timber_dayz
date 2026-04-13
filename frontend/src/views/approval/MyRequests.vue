<template>
  <div class="approval-requests erp-page-container erp-page--admin">
    <PageHeader
      title="我的申请"
      subtitle="统一查看我发起的审批申请、当前状态与处理进度。"
      family="admin"
    >
      <template #actions>
        <el-button :icon="Refresh" @click="loadRequests">刷新</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="16" class="erp-mb-lg">
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="summary-label">申请总数</div>
          <div class="summary-value">{{ summary.total }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="summary-label">审批中</div>
          <div class="summary-value warning">{{ summary.inReview }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="summary-label">已完成</div>
          <div class="summary-value success">{{ summary.finished }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover">
      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="approval_id" label="审批单号" min-width="260" show-overflow-tooltip />
        <el-table-column prop="template_code" label="审批类型" min-width="180" />
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ formatStatus(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="submitted_at" label="提交时间" min-width="180" />
        <el-table-column prop="finished_at" label="完成时间" min-width="180" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-space>
              <el-button link type="primary" @click="openDetail(row.approval_id)">查看详情</el-button>
              <el-button
                v-if="canWithdraw(row.status)"
                link
                type="danger"
                @click="withdrawApproval(row.approval_id)"
              >
                撤回申请
              </el-button>
            </el-space>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" title="审批详情" size="50%">
      <div v-loading="detailLoading" class="detail-panel">
        <template v-if="detail.approval_id">
          <div class="detail-line">审批单号：{{ detail.approval_id }}</div>
          <div class="detail-line">审批类型：{{ detail.template_code }}</div>
          <div class="detail-line">状态：{{ formatStatus(detail.status) }}</div>
          <div class="detail-line">业务标识：{{ detail.business_key || '--' }}</div>

          <el-divider content-position="left">审批步骤</el-divider>
          <el-timeline>
            <el-timeline-item
              v-for="step in detail.steps || []"
              :key="`${detail.approval_id}-${step.step_order}`"
              :timestamp="step.acted_at || ''"
            >
              第 {{ step.step_order }} 步 · {{ formatStatus(step.status) }} · 审批人 {{ step.approver_user_id || '--' }}
            </el-timeline-item>
          </el-timeline>

          <el-divider content-position="left">处理时间线</el-divider>
          <el-timeline>
            <el-timeline-item
              v-for="entry in detail.timeline || []"
              :key="`${detail.approval_id}-${entry.created_at}-${entry.action_type}`"
              :timestamp="entry.created_at || ''"
            >
              {{ entry.action_type }} · {{ entry.comment || '无备注' }}
            </el-timeline-item>
          </el-timeline>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import approvalCenterApi from '@/api/approvalCenter.js'
import PageHeader from '@/components/common/PageHeader.vue'

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const items = ref([])
const detail = ref({})

const summary = computed(() => {
  const total = items.value.length
  const inReview = items.value.filter((item) => ['submitted', 'in_review'].includes(item.status)).length
  const finished = items.value.filter((item) => ['approved', 'rejected', 'cancelled'].includes(item.status)).length
  return { total, inReview, finished }
})

const formatStatus = (status) => {
  const mapping = {
    draft: '草稿',
    submitted: '待审批',
    in_review: '审批中',
    approved: '已通过',
    rejected: '已驳回',
    cancelled: '已撤回'
  }
  return mapping[status] || status || '--'
}

const statusTagType = (status) => {
  if (status === 'approved') return 'success'
  if (status === 'rejected' || status === 'cancelled') return 'danger'
  if (status === 'submitted' || status === 'in_review') return 'warning'
  return 'info'
}

const canWithdraw = (status) => ['draft', 'submitted', 'in_review'].includes(status)

const loadRequests = async () => {
  loading.value = true
  try {
    const payload = await approvalCenterApi.listRequests()
    items.value = payload.items || []
  } finally {
    loading.value = false
  }
}

const openDetail = async (approvalId) => {
  detailLoading.value = true
  detailVisible.value = true
  try {
    detail.value = await approvalCenterApi.getApproval(approvalId)
  } finally {
    detailLoading.value = false
  }
}

const withdrawApproval = async (approvalId) => {
  const { value } = await ElMessageBox.prompt('请输入撤回原因', '撤回申请', {
    confirmButtonText: '确认撤回',
    cancelButtonText: '取消'
  }).catch(() => ({ value: null }))
  if (!value) return
  await approvalCenterApi.withdraw(approvalId, value)
  ElMessage.success('审批申请已撤回')
  await loadRequests()
  if (detailVisible.value && detail.value.approval_id === approvalId) {
    await openDetail(approvalId)
  }
}

onMounted(() => {
  void loadRequests()
})
</script>

<style scoped>
.summary-label {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.summary-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-value.warning {
  color: var(--warning-color);
}

.summary-value.success {
  color: var(--success-color);
}

.detail-panel {
  padding-right: 8px;
}

.detail-line {
  margin-bottom: 12px;
  color: var(--text-primary);
}
</style>
