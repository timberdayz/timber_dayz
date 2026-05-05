<template>
  <div class="workflow-config erp-page-container erp-page--admin">
    <PageHeader
      title="流程配置"
      subtitle="第一版先提供审批模板与目标路由的只读视图，便于管理员核对当前审批中心范围。"
      family="admin"
    >
      <template #actions>
        <el-button :icon="Refresh" @click="loadTemplates">刷新</el-button>
      </template>
    </PageHeader>

    <el-alert
      type="info"
      :closable="false"
      class="erp-mb-lg"
      title="当前为轻量审批模板配置视图"
      description="本阶段先收口审批模板、审批模式与目标页面，复杂流程编辑器后续单独迭代。"
    />

    <el-card shadow="hover">
      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="template_name" label="模板名称" min-width="220" />
        <el-table-column prop="template_code" label="模板编码" min-width="220" show-overflow-tooltip />
        <el-table-column prop="business_type" label="业务类型" min-width="180" />
        <el-table-column prop="approval_mode" label="审批模式" width="120" />
        <el-table-column prop="target_route" label="目标页面" min-width="220" show-overflow-tooltip />
        <el-table-column label="启用状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? '已启用' : '未启用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import approvalCenterApi from '@/api/approvalCenter.js'
import PageHeader from '@/components/common/PageHeader.vue'

const loading = ref(false)
const items = ref([])

const loadTemplates = async () => {
  loading.value = true
  try {
    const payload = await approvalCenterApi.listTemplates()
    items.value = payload.items || []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadTemplates()
})
</script>
