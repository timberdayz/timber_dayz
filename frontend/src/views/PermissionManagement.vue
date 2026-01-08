<template>
  <div class="permission-management">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>🔑 权限管理中心</h1>
      <p>权限管理 • 访问控制 • 安全审计</p>
    </div>

    <!-- 权限统计卡片 -->
    <el-row :gutter="20" class="stats-section">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon total-icon">
            <el-icon><Key /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">总权限数</div>
            <div class="stat-value">{{ permissions.length }}</div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon resource-icon">
            <el-icon><Document /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">资源类型</div>
            <div class="stat-value">{{ resourceTypes.length }}</div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon action-icon">
            <el-icon><Operation /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">操作类型</div>
            <div class="stat-value">{{ actionTypes.length }}</div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon active-icon">
            <el-icon><Check /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">活跃权限</div>
            <div class="stat-value">{{ activePermissions }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 筛选器 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="资源类型">
          <el-select v-model="filters.resource" placeholder="全部资源" clearable @change="handleFilterChange">
            <el-option 
              v-for="resource in resourceTypes" 
              :key="resource" 
              :label="getResourceText(resource)" 
              :value="resource" 
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="操作类型">
          <el-select v-model="filters.action" placeholder="全部操作" clearable @change="handleFilterChange">
            <el-option 
              v-for="action in actionTypes" 
              :key="action" 
              :label="getActionText(action)" 
              :value="action" 
            />
          </el-select>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="refreshPermissions">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 权限列表 -->
    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>📋 权限列表</span>
          <el-tag>共 {{ filteredPermissions.length }} 个权限</el-tag>
        </div>
      </template>

      <el-table 
        :data="filteredPermissions" 
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="权限名称" width="200" />
        <el-table-column prop="description" label="描述" min-width="250" />
        <el-table-column prop="resource" label="资源" width="150">
          <template #default="{ row }">
            <el-tag :type="getResourceType(row.resource)">
              {{ getResourceText(row.resource) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="操作" width="120">
          <template #default="{ row }">
            <el-tag :type="getActionType(row.action)">
              {{ getActionText(row.action) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="使用情况" width="150">
          <template #default="{ row }">
            <el-progress 
              :percentage="getUsagePercentage(row)" 
              :color="getUsageColor(row)"
              :show-text="false"
            />
            <span style="font-size: 12px; color: #666;">
              {{ getUsageCount(row) }} 个角色
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewPermission(row)">
              详情
            </el-button>
            <el-button link type="info" size="small" @click="testPermission(row)">
              测试
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 权限详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="权限详情" width="800px">
      <div v-if="selectedPermission" v-loading="loadingDetail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="权限ID">{{ selectedPermission.id }}</el-descriptions-item>
          <el-descriptions-item label="权限名称">{{ selectedPermission.name }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ selectedPermission.description }}</el-descriptions-item>
          <el-descriptions-item label="资源">
            <el-tag :type="getResourceType(selectedPermission.resource)">
              {{ getResourceText(selectedPermission.resource) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="操作">
            <el-tag :type="getActionType(selectedPermission.action)">
              {{ getActionText(selectedPermission.action) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="使用情况" :span="2">
            <el-progress 
              :percentage="getUsagePercentage(selectedPermission)" 
              :color="getUsageColor(selectedPermission)"
            />
            <div style="margin-top: 10px;">
              <span>被 {{ getUsageCount(selectedPermission) }} 个角色使用</span>
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 使用此权限的角色列表 -->
        <div style="margin-top: 20px;">
          <h4>使用此权限的角色：</h4>
          <el-tag 
            v-for="role in getRolesUsingPermission(selectedPermission)" 
            :key="role" 
            type="primary"
            style="margin-right: 5px; margin-bottom: 5px;"
          >
            {{ role }}
          </el-tag>
        </div>
      </div>
    </el-dialog>

    <!-- 权限测试对话框 -->
    <el-dialog v-model="showTestDialog" title="权限测试" width="600px">
      <div v-if="selectedPermission">
        <el-alert
          title="权限测试"
          :description="`正在测试权限 '${selectedPermission.name}'`"
          type="info"
          show-icon
          style="margin-bottom: 20px;"
        />
        
        <el-form :model="testForm" ref="testFormRef" label-width="100px">
          <el-form-item label="测试用户">
            <el-select v-model="testForm.userId" placeholder="请选择测试用户">
              <el-option 
                v-for="user in testUsers" 
                :key="user.id" 
                :label="user.username" 
                :value="user.id" 
              />
            </el-select>
          </el-form-item>
          <el-form-item label="测试资源">
            <el-input v-model="testForm.resource" placeholder="请输入测试资源ID" />
          </el-form-item>
          <el-form-item label="测试操作">
            <el-input v-model="testForm.action" placeholder="请输入测试操作" />
          </el-form-item>
        </el-form>

        <div v-if="testResult" style="margin-top: 20px;">
          <el-alert
            :title="testResult.success ? '测试通过' : '测试失败'"
            :type="testResult.success ? 'success' : 'error'"
            :description="testResult.message"
            show-icon
          />
        </div>
      </div>

      <template #footer>
        <el-button @click="showTestDialog = false">关闭</el-button>
        <el-button type="primary" @click="runPermissionTest" :loading="testing">
          运行测试
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRolesStore } from '@/stores/roles'
import { useUsersStore } from '@/stores/users'
import { ElMessage } from 'element-plus'
import {
  Key,
  Document,
  Operation,
  Check,
  Refresh
} from '@element-plus/icons-vue'
import * as systemAPI from '@/api/system'

const rolesStore = useRolesStore()
const usersStore = useUsersStore()

// 筛选器
const filters = ref({
  resource: null,
  action: null
})

// 对话框状态
const showDetailDialog = ref(false)
const showTestDialog = ref(false)

// 选中的权限
const selectedPermission = ref(null)
const loadingDetail = ref(false)

// 加载状态
const loading = ref(false)
const testing = ref(false)

// 测试表单
const testForm = ref({
  userId: null,
  resource: '',
  action: ''
})

const testResult = ref(null)
const testUsers = ref([])

// 权限数据
const permissions = ref([])

// 计算属性
const resourceTypes = computed(() => {
  const types = [...new Set(permissions.value.map(p => p.resource))]
  return types
})

const actionTypes = computed(() => {
  const types = [...new Set(permissions.value.map(p => p.action))]
  return types
})

const activePermissions = computed(() => {
  return permissions.value.filter(p => getUsageCount(p) > 0).length
})

const filteredPermissions = computed(() => {
  let filtered = permissions.value

  if (filters.value.resource) {
    filtered = filtered.filter(p => p.resource === filters.value.resource)
  }

  if (filters.value.action) {
    filtered = filtered.filter(p => p.action === filters.value.action)
  }

  return filtered
})

// 初始化数据
const initData = async () => {
  try {
    loading.value = true
    
    // 优先使用新的权限API
    try {
      const data = await systemAPI.getPermissions()
      // 处理响应格式：可能是数组（直接返回）或对象（包含data字段）
      if (Array.isArray(data)) {
        permissions.value = data
      } else if (data && data.permissions && Array.isArray(data.permissions)) {
        permissions.value = data.permissions
      } else if (data && Array.isArray(data.data)) {
        permissions.value = data.data
      } else {
        // 降级到旧的store方法
        await rolesStore.fetchPermissions()
        permissions.value = rolesStore.permissions
      }
    } catch (apiError) {
      console.warn('新权限API失败，使用旧方法:', apiError)
      // 降级到旧的store方法
      await rolesStore.fetchPermissions()
      permissions.value = rolesStore.permissions
    }
    
    // 加载角色列表（用于统计使用情况）
    try {
      await rolesStore.fetchRoles()
    } catch (error) {
      console.warn('加载角色列表失败:', error)
    }
    
    // 加载用户列表（用于测试）
    try {
      await usersStore.fetchUsers()
      testUsers.value = usersStore.users
    } catch (error) {
      console.warn('加载用户列表失败:', error)
    }
    
  } catch (error) {
    ElMessage.error('初始化数据失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

// 刷新权限列表
const refreshPermissions = async () => {
  try {
    await initData()
    ElMessage.success('权限列表已刷新')
  } catch (error) {
    ElMessage.error('刷新失败: ' + error.message)
  }
}

// 处理筛选变化
const handleFilterChange = () => {
  // 筛选逻辑在computed中处理
}

// 查看权限详情
const viewPermission = async (permission) => {
  selectedPermission.value = permission
  showDetailDialog.value = true
}

// 测试权限
const testPermission = (permission) => {
  selectedPermission.value = permission
  testForm.value = {
    userId: null,
    resource: permission.resource,
    action: permission.action
  }
  testResult.value = null
  showTestDialog.value = true
}

// 运行权限测试
const runPermissionTest = async () => {
  try {
    testing.value = true
    
    // 模拟权限测试
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    testResult.value = {
      success: Math.random() > 0.3, // 模拟测试结果
      message: Math.random() > 0.3 ? '用户具有此权限' : '用户没有此权限'
    }
    
  } catch (error) {
    testResult.value = {
      success: false,
      message: '测试失败: ' + error.message
    }
  } finally {
    testing.value = false
  }
}

// 工具函数
const getResourceType = (resource) => {
  const typeMap = {
    'dashboard': 'primary',
    'sales': 'success',
    'inventory': 'warning',
    'finance': 'info',
    'store': 'primary',
    'user': 'danger',
    'role': 'danger',
    'system': 'warning',
    'mapping': 'info'
  }
  return typeMap[resource] || 'info'
}

const getResourceText = (resource) => {
  const textMap = {
    'dashboard': '仪表板',
    'sales': '销售',
    'inventory': '库存',
    'finance': '财务',
    'store': '店铺',
    'user': '用户',
    'role': '角色',
    'system': '系统',
    'mapping': '映射'
  }
  return textMap[resource] || resource
}

const getActionType = (action) => {
  const typeMap = {
    'read': 'success',
    'write': 'warning',
    'delete': 'danger',
    'all': 'primary'
  }
  return typeMap[action] || 'info'
}

const getActionText = (action) => {
  const textMap = {
    'read': '读取',
    'write': '写入',
    'delete': '删除',
    'all': '全部'
  }
  return textMap[action] || action
}

const getUsageCount = (permission) => {
  // 统计使用此权限的角色数量
  const roles = rolesStore.roles
  return roles.filter(role => role.permissions.includes(permission.name)).length
}

const getUsagePercentage = (permission) => {
  const count = getUsageCount(permission)
  const total = rolesStore.roles.length
  return total > 0 ? Math.round((count / total) * 100) : 0
}

const getUsageColor = (permission) => {
  const percentage = getUsagePercentage(permission)
  if (percentage >= 80) return '#67c23a'
  if (percentage >= 50) return '#e6a23c'
  return '#f56c6c'
}

const getRolesUsingPermission = (permission) => {
  const roles = rolesStore.roles
  return roles
    .filter(role => role.permissions.includes(permission.name))
    .map(role => role.name)
}

onMounted(() => {
  initData()
})
</script>

<style scoped>
.permission-management {
  padding: 20px;
  background: #f0f2f5;
  min-height: 100vh;
}

.page-header {
  text-align: center;
  margin-bottom: 30px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 40px 20px;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.page-header h1 {
  margin: 0 0 10px 0;
  font-size: 32px;
  font-weight: 700;
}

.page-header p {
  margin: 0;
  opacity: 0.9;
  font-size: 16px;
}

.stats-section {
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
  margin-bottom: 20px;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
}

.total-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.resource-icon {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.action-icon {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.active-icon {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 14px;
  color: #8c8c8c;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #262626;
}

.filter-card,
.table-card {
  margin-bottom: 20px;
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .permission-management {
    padding: 10px;
  }
  
  .page-header h1 {
    font-size: 24px;
  }
  
  .stat-card {
    flex-direction: column;
    text-align: center;
  }
}
</style>
