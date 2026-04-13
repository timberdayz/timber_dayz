<template>
  <div class="approval-history erp-page-container erp-page--admin">
    <PageHeader
      title="审批历史"
      subtitle="查看我处理过的审批动作、处理结果与完整审批链路。"
      family="admin"
    >
      <template #actions>
        <el-button :icon="Refresh" @click="loadHistory">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="hover">
      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="approval_id" label="审批单号" min-width="260" show-overflow-tooltip />
        <el-table-column prop="template_code" label="审批类型" min-width="180" />
        <el-table-column prop="action_type" label="我的动作" width="120" />
        <el-table-column label="当前结果" width="140">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ formatStatus(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="comment" label="处理备注" min-width="220" show-overflow-tooltip />
        <el-table-column prop="acted_at" label="处理时间" min-width="180" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.approval_id)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" title="审批详情" size="50%">
      <div v-loading="detailLoading">
        <template v-if="detail.approval_id">
          <div class="detail-line">审批单号：{{ detail.approval_id }}</div>
          <div class="detail-line">审批类型：{{ detail.template_code }}</div>
          <div class="detail-line">当前状态：{{ formatStatus(detail.status) }}</div>

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

          <el-divider content-position="left">动作日志</el-divider>
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
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import approvalCenterApi from '@/api/approvalCenter.js'
import PageHeader from '@/components/common/PageHeader.vue'

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const items = ref([])
const detail = ref({})

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

const loadHistory = async () => {
  loading.value = true
  try {
    const payload = await approvalCenterApi.listHistory()
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

onMounted(() => {
  void loadHistory()
})
</script>

<style scoped>
.detail-line {
  margin-bottom: 12px;
  color: var(--text-primary);
}
</style>
