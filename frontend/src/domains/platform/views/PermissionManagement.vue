<template>
  <div class="permission-management erp-page-container erp-page--admin">
    <PageHeader
      title="权限管理"
      subtitle="查看权限目录、资源维度、角色引用情况，并对指定用户做真实权限校验。"
      family="admin"
    />

    <el-row :gutter="20" class="stats-section">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-label">总权限数</div>
          <div class="stat-value">{{ permissions.length }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-label">资源类型</div>
          <div class="stat-value">{{ resourceTypes.length }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-label">操作类型</div>
          <div class="stat-value">{{ actionTypes.length }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-label">被引用权限</div>
          <div class="stat-value">{{ activePermissions }}</div>
        </div>
      </el-col>
    </el-row>

    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="资源类型">
          <el-select v-model="filters.resource" placeholder="全部资源" clearable>
            <el-option v-for="resource in resourceTypes" :key="resource" :label="resource" :value="resource" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="filters.action" placeholder="全部操作" clearable>
            <el-option v-for="action in actionTypes" :key="action" :label="action" :value="action" />
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

    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>权限列表</span>
          <el-tag>共 {{ filteredPermissions.length }} 个权限</el-tag>
        </div>
      </template>

      <el-table :data="filteredPermissions" v-loading="loading" stripe class="erp-w-full">
        <el-table-column prop="id" label="权限 ID" width="180" />
        <el-table-column prop="name" label="权限名称" width="180" />
        <el-table-column prop="description" label="描述" min-width="220" />
        <el-table-column prop="resource" label="资源" width="140" />
        <el-table-column prop="action" label="操作" width="120" />
        <el-table-column label="引用角色数" width="120">
          <template #default="{ row }">{{ getUsageCount(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewPermission(row)">详情</el-button>
            <el-button link type="info" size="small" @click="testPermission(row)">测试</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showDetailDialog" title="权限详情" width="760px">
      <el-descriptions v-if="selectedPermission" :column="2" border>
        <el-descriptions-item label="权限 ID">{{ selectedPermission.id }}</el-descriptions-item>
        <el-descriptions-item label="权限名称">{{ selectedPermission.name }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ selectedPermission.description }}</el-descriptions-item>
        <el-descriptions-item label="资源">{{ selectedPermission.resource }}</el-descriptions-item>
        <el-descriptions-item label="操作">{{ selectedPermission.action || '-' }}</el-descriptions-item>
        <el-descriptions-item label="引用角色" :span="2">
          <el-tag v-for="roleName in getRolesUsingPermission(selectedPermission)" :key="roleName" class="erp-tag-gap">
            {{ roleName }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-dialog v-model="showTestDialog" title="权限测试" width="560px">
      <el-alert
        v-if="selectedPermission"
        title="真实权限校验"
        :description="`正在校验权限 ${selectedPermission.id}`"
        type="info"
        show-icon
        class="erp-mb-lg"
      />
      <el-form label-width="100px">
        <el-form-item label="测试用户">
          <el-select v-model="testForm.userId" placeholder="请选择测试用户">
            <el-option v-for="user in testUsers" :key="user.id" :label="user.username" :value="user.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="testResult"
        :title="testResult.success ? '校验通过' : '校验未通过'"
        :description="testResult.message"
        :type="testResult.success ? 'success' : 'warning'"
        show-icon
      />
      <template #footer>
        <el-button @click="showTestDialog = false">关闭</el-button>
        <el-button type="primary" :loading="testing" @click="runPermissionTest">开始测试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useRolesStore } from '@/stores/roles'
import { useUsersStore } from '@/stores/users'
import * as systemAPI from '@/api/system'
import PageHeader from '@/components/common/PageHeader.vue'

const rolesStore = useRolesStore()
const usersStore = useUsersStore()
const permissions = ref([])
const loading = ref(false)
const testing = ref(false)
const showDetailDialog = ref(false)
const showTestDialog = ref(false)
const selectedPermission = ref(null)
const testUsers = ref([])
const testResult = ref(null)
const filters = ref({
  resource: null,
  action: null,
})
const testForm = ref({
  userId: null,
})

const resourceTypes = computed(() => [...new Set(permissions.value.map((item) => item.resource))].filter(Boolean))
const actionTypes = computed(() => [...new Set(permissions.value.map((item) => item.action))].filter(Boolean))
const activePermissions = computed(() => permissions.value.filter((item) => getUsageCount(item) > 0).length)

const filteredPermissions = computed(() => {
  return permissions.value.filter((item) => {
    const resourceMatch = !filters.value.resource || item.resource === filters.value.resource
    const actionMatch = !filters.value.action || item.action === filters.value.action
    return resourceMatch && actionMatch
  })
})

const initData = async () => {
  loading.value = true
  try {
    const [permissionPayload] = await Promise.all([
      systemAPI.getPermissions(),
      rolesStore.fetchRoles(),
      usersStore.fetchUsers(),
    ])
    permissions.value = Array.isArray(permissionPayload) ? permissionPayload : (permissionPayload.data || [])
    testUsers.value = usersStore.users
  } finally {
    loading.value = false
  }
}

const refreshPermissions = async () => {
  try {
    await initData()
    ElMessage.success('权限列表已刷新')
  } catch (error) {
    ElMessage.error(`刷新失败: ${error.message}`)
  }
}

const getUsageCount = (permission) => {
  return rolesStore.roles.filter((role) => (role.permissions || []).includes(permission.id)).length
}

const getRolesUsingPermission = (permission) => {
  return rolesStore.roles
    .filter((role) => (role.permissions || []).includes(permission.id))
    .map((role) => role.role_name || role.name)
}

const viewPermission = (permission) => {
  selectedPermission.value = permission
  showDetailDialog.value = true
}

const testPermission = (permission) => {
  selectedPermission.value = permission
  testForm.value = { userId: null }
  testResult.value = null
  showTestDialog.value = true
}

const runPermissionTest = async () => {
  if (!testForm.value.userId || !selectedPermission.value) {
    ElMessage.warning('请选择测试用户')
    return
  }
  try {
    testing.value = true
    const payload = await systemAPI.checkPermissionAssignment({
      user_id: testForm.value.userId,
      permission_id: selectedPermission.value.id,
    })
    const result = payload?.data ?? payload
    testResult.value = {
      success: Boolean(result?.has_permission),
      message: result?.has_permission ? '用户具有此权限' : '用户没有此权限',
    }
  } catch (error) {
    testResult.value = {
      success: false,
      message: `测试失败: ${error.message}`,
    }
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  initData().catch((error) => {
    ElMessage.error(`初始化失败: ${error.message}`)
  })
})
</script>

<style scoped>
.permission-management {
  background: #f0f2f5;
  min-height: calc(100vh - var(--header-height));
}

.stats-section,
.filter-card,
.table-card {
  margin-bottom: 20px;
}

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.stat-label {
  color: #909399;
  font-size: 14px;
}

.stat-value {
  color: #303133;
  font-size: 28px;
  font-weight: 700;
  margin-top: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
</style>
