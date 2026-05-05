<!--
数据同步 - 同步历史记录页面
v4.6.0新增：独立的数据同步系统
-->

<template>
  <div class="data-sync-history erp-page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>📜 数据同步 - 同步历史</h1>
      <p>查看历史同步记录和统计</p>
    </div>

    <!-- 筛选器 -->
    <el-card class="filter-card" style="margin-bottom: 20px;">
      <el-form :inline="true" :model="filters">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 400px;"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 150px;">
            <el-option label="成功" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadHistory" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 历史记录列表 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>历史记录（共 {{ history.length }} 条）</span>
          <el-button @click="exportReport">
            <el-icon><Download /></el-icon>
            导出报告
          </el-button>
        </div>
      </template>

      <el-table
        :data="history"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="task_id" label="任务ID" width="200" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'completed'" type="success" size="small">
              <el-icon><Check /></el-icon>
              成功
            </el-tag>
            <el-tag v-else-if="row.status === 'failed'" type="danger" size="small">
              <el-icon><Close /></el-icon>
              失败
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="processed_files" label="处理文件数" width="120" />
        <el-table-column prop="valid_rows" label="成功行数" width="120" />
        <el-table-column prop="quarantined_rows" label="隔离行数" width="120" />
        <el-table-column prop="failed_rows" label="失败行数" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column prop="completed_at" label="完成时间" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row.task_id)">
              <el-icon><View /></el-icon>
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

// 状态
const loading = ref(false)
const history = ref([])
const filters = ref({
  dateRange: null,
  status: null
})

// 加载历史记录
const loadHistory = async () => {
  loading.value = true
  try {
    // TODO: 实现历史记录API
    // const data = await api.getDataSyncHistory(filters.value)
    // history.value = data.history || []
    
    // 临时模拟数据
    history.value = []
  } catch (error) {
    ElMessage.error(error.message || '加载历史记录失败')
  } finally {
    loading.value = false
  }
}

// 重置筛选器
const resetFilters = () => {
  filters.value = {
    dateRange: null,
    status: null
  }
  loadHistory()
}

// 查看详情
const viewDetail = (taskId) => {
  ElMessage.info(`查看任务详情: ${taskId}`)
  // TODO: 实现任务详情页面
}

// 导出报告
const exportReport = () => {
  ElMessage.info('导出报告功能开发中')
  // TODO: 实现导出报告功能
}

// 初始化
onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.data-sync-history {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  color: #666;
  font-size: 14px;
}
</style>

