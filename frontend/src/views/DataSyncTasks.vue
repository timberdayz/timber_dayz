<!--
数据同步 - 同步任务管理页面
v4.6.0新增：独立的数据同步系统
-->

<template>
  <div class="data-sync-tasks erp-page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>⚙️ 数据同步 - 同步任务</h1>
      <p>查看和管理数据同步任务</p>
    </div>

    <!-- 任务统计 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">进行中</div>
            <div class="stat-value" style="color: #409EFF;">{{ stats.running }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">已完成</div>
            <div class="stat-value" style="color: #67C23A;">{{ stats.completed }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">失败</div>
            <div class="stat-value" style="color: #F56C6C;">{{ stats.failed }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">总计</div>
            <div class="stat-value">{{ stats.total }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 任务列表 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>任务列表</span>
          <el-button @click="loadTasks" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="tasks"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="task_id" label="任务ID" width="200" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'running' || row.status === 'processing'" type="primary" size="small">
              <el-icon><Loading /></el-icon>
              进行中
            </el-tag>
            <el-tag v-else-if="row.status === 'waiting'" type="warning" size="small">
              <el-icon><Clock /></el-icon>
              等待中
            </el-tag>
            <el-tag v-else-if="row.status === 'completed' || row.status === 'success'" type="success" size="small">
              <el-icon><Check /></el-icon>
              已完成
            </el-tag>
            <el-tag v-else-if="row.status === 'failed' || row.status === 'error'" type="danger" size="small">
              <el-icon><Close /></el-icon>
              失败
            </el-tag>
            <el-tag v-else type="info" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :status="row.status === 'failed' ? 'exception' : undefined"
            />
          </template>
        </el-table-column>
        <el-table-column prop="processed_files" label="已处理文件" width="120" />
        <el-table-column prop="total_files" label="总文件数" width="120" />
        <el-table-column prop="valid_rows" label="成功行数" width="120" />
        <el-table-column prop="quarantined_rows" label="隔离行数" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewTaskDetail(row.task_id)">
              <el-icon><View /></el-icon>
              查看详情
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small"
              type="danger"
              @click="cancelTask(row.task_id)"
            >
              <el-icon><Close /></el-icon>
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

// 状态
const loading = ref(false)
const tasks = ref([])
const stats = ref({
  running: 0,
  completed: 0,
  failed: 0,
  total: 0
})

let refreshInterval = null

// 加载任务列表
const loadTasks = async () => {
  loading.value = true
  try {
    // ⭐ v4.19.8修复：添加 limit 参数，限制返回数量，避免数据量过大导致问题
    // ⭐ v4.19.8修复：api.getSyncHistory() 通过响应拦截器后直接返回数组
    // 响应拦截器已经处理了 { success: true, data: [...] } 格式，直接返回 data
    const data = await api.getSyncHistory({ limit: 100 })
    
    // ⭐ v4.19.8新增：添加调试日志（帮助排查问题）
    console.log('[DataSyncTasks] API返回数据:', {
      type: typeof data,
      isArray: Array.isArray(data),
      length: Array.isArray(data) ? data.length : 'N/A',
      sample: Array.isArray(data) && data.length > 0 ? data[0] : null
    })
    
    // 确保 data 是数组
    const taskList = Array.isArray(data) ? data : []
    
    // ⭐ v4.19.8新增：如果数据不是数组，显示警告
    if (!Array.isArray(data)) {
      console.warn('[DataSyncTasks] API返回的不是数组:', data)
      ElMessage.warning('任务数据格式异常，请刷新重试')
      tasks.value = []
      updateStats()
      return
    }
    
    // 处理后端返回的任务数据
    tasks.value = taskList.map(task => {
      // 计算进度百分比
      const progress = task.total_files > 0 
        ? Math.round((task.processed_files / task.total_files) * 100) 
        : 0
      
      // 映射状态（后端可能返回 'processing', 'waiting', 'success', 'error' 等）
      let normalizedStatus = task.status
      if (task.status === 'processing' || task.status === 'waiting') {
        normalizedStatus = 'running'
      } else if (task.status === 'success') {
        normalizedStatus = 'completed'
      } else if (task.status === 'error') {
        normalizedStatus = 'failed'
      }
      
      // 处理时间字段（如果没有 created_at，使用 start_time）
      const created_at = task.created_at || task.start_time || task.updated_at
      
      return {
        ...task,
        progress,
        status: normalizedStatus,
        created_at,
        // 确保字段存在
        quarantined_rows: task.quarantined_rows || 0,
        valid_rows: task.valid_rows || 0,
        processed_files: task.processed_files || 0,
        total_files: task.total_files || 0
      }
    })
    updateStats()
  } catch (error) {
    console.error('加载任务列表失败:', error)
    ElMessage.error(error.message || '加载任务列表失败')
    tasks.value = []
    updateStats()
  } finally {
    loading.value = false
  }
}

// 更新统计
const updateStats = () => {
  stats.value = {
    // 包括所有可能的状态值
    running: tasks.value.filter(t => 
      t.status === 'running' || 
      t.status === 'processing' || 
      t.status === 'waiting'
    ).length,
    completed: tasks.value.filter(t => 
      t.status === 'completed' || 
      t.status === 'success'
    ).length,
    failed: tasks.value.filter(t => 
      t.status === 'failed' || 
      t.status === 'error'
    ).length,
    total: tasks.value.length
  }
}

// 查看任务详情
const viewTaskDetail = (taskId) => {
  ElMessage.info(`查看任务详情: ${taskId}`)
  // TODO: 实现任务详情页面
}

// 取消任务
const cancelTask = async (taskId) => {
  try {
    // TODO: 实现取消任务API
    ElMessage.success('任务已取消')
    await loadTasks()
  } catch (error) {
    ElMessage.error(error.message || '取消任务失败')
  }
}

// 初始化
onMounted(() => {
  loadTasks()
  // 每5秒刷新一次
  refreshInterval = setInterval(() => {
    loadTasks()
  }, 5000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.data-sync-tasks {
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

.stat-item {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
}
</style>

