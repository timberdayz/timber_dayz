<template>
  <div class="role-management erp-page-container erp-page--admin">
    <PageHeader
      title="角色管理"
      subtitle="维护角色、角色编码与权限集合，统一后台 RBAC 配置入口。"
      family="admin"
    />

    <el-card class="action-card">
      <el-row :gutter="20" justify="space-between" align="middle">
        <el-col :span="12">
          <el-button type="primary" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon>
            新增角色
          </el-button>
          <el-button @click="refreshRoles">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-col>
        <el-col :span="12">
          <el-input v-model="searchKeyword" placeholder="搜索角色名称或编码" class="search-input" />
        </el-col>
      </el-row>
    </el-card>

    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>角色列表</span>
          <el-tag>共 {{ filteredRoles.length }} 个角色</el-tag>
        </div>
      </template>

      <el-table :data="filteredRoles" v-loading="rolesStore.isLoading" stripe class="erp-w-full">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="role_name" label="角色名称" width="160" />
        <el-table-column prop="role_code" label="角色编码" width="160" />
        <el-table-column prop="description" label="描述" min-width="220" />
        <el-table-column label="权限" min-width="320">
          <template #default="{ row }">
            <el-tag
              v-for="permissionId in row.permissions"
              :key="permissionId"
              size="small"
              class="erp-tag-gap"
            >
              {{ getPermissionText(permissionId) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="row.is_system ? 'warning' : 'info'">
              {{ row.is_system ? '系统角色' : '自定义角色' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewRole(row)">详情</el-button>
            <el-button link type="primary" size="small" @click="editRole(row)">编辑</el-button>
            <el-button link type="warning" size="small" @click="configurePermissions(row)">配置权限</el-button>
            <el-button
              link
              type="danger"
              size="small"
              :disabled="row.role_code === 'admin' || row.is_system"
              @click="deleteRole(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="创建角色" width="640px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="角色编码" prop="role_code">
          <el-input v-model="createForm.role_code" placeholder="请输入角色编码，例如 hr-admin" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" rows="3" placeholder="请输入角色描述" />
        </el-form-item>
        <el-form-item label="权限" prop="permissions">
          <el-checkbox-group v-model="createForm.permissions">
            <el-row :gutter="16">
              <el-col v-for="permission in availablePermissions" :key="permission.id" :span="12">
                <el-checkbox :label="permission.id">{{ permission.name }}</el-checkbox>
              </el-col>
            </el-row>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑角色" width="640px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-form-item label="角色名称">
          <el-input :model-value="editForm.role_name || editForm.name" disabled />
        </el-form-item>
        <el-form-item label="角色编码">
          <el-input :model-value="editForm.role_code" disabled />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="editForm.description" type="textarea" rows="3" placeholder="请输入角色描述" />
        </el-form-item>
        <el-form-item label="权限" prop="permissions">
          <el-checkbox-group v-model="editForm.permissions">
            <el-row :gutter="16">
              <el-col v-for="permission in availablePermissions" :key="permission.id" :span="12">
                <el-checkbox :label="permission.id">{{ permission.name }}</el-checkbox>
              </el-col>
            </el-row>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDetailDialog" title="角色详情" width="720px">
      <el-descriptions v-if="selectedRole" :column="2" border>
        <el-descriptions-item label="角色名称">{{ selectedRole.role_name || selectedRole.name }}</el-descriptions-item>
        <el-descriptions-item label="角色编码">{{ selectedRole.role_code }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ selectedRole.description || '-' }}</el-descriptions-item>
        <el-descriptions-item label="权限" :span="2">
          <el-tag v-for="permissionId in selectedRole.permissions" :key="permissionId" class="erp-tag-gap">
            {{ getPermissionText(permissionId) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="系统角色">{{ selectedRole.is_system ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(selectedRole.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-dialog v-model="showPermissionDialog" title="配置权限" width="720px">
      <el-alert
        v-if="selectedRole"
        title="权限配置"
        :description="`正在为角色 ${selectedRole.role_name || selectedRole.name} 配置权限`"
        type="info"
        show-icon
        class="erp-mb-lg"
      />
      <el-checkbox-group v-model="permissionForm.permissions">
        <el-row :gutter="16">
          <el-col v-for="permission in availablePermissions" :key="permission.id" :span="12">
            <el-checkbox :label="permission.id">
              <div class="permission-item">
                <div class="permission-title">{{ permission.name }}</div>
                <div class="permission-desc">{{ permission.description }}</div>
              </div>
            </el-checkbox>
          </el-col>
        </el-row>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="showPermissionDialog = false">取消</el-button>
        <el-button type="primary" :loading="configuring" @click="submitPermissions">保存权限</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { useRolesStore } from '@/stores/roles'
import PageHeader from '@/components/common/PageHeader.vue'

const rolesStore = useRolesStore()
const searchKeyword = ref('')
const availablePermissions = ref([])
const selectedRole = ref(null)
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showDetailDialog = ref(false)
const showPermissionDialog = ref(false)
const createFormRef = ref()
const editFormRef = ref()
const creating = ref(false)
const editing = ref(false)
const configuring = ref(false)

const createForm = ref({
  name: '',
  role_code: '',
  description: '',
  permissions: [],
})

const editForm = ref({
  id: null,
  name: '',
  role_name: '',
  role_code: '',
  description: '',
  permissions: [],
})

const permissionForm = ref({
  permissions: [],
})

const createRules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  role_code: [{ required: true, message: '请输入角色编码', trigger: 'blur' }],
  description: [{ required: true, message: '请输入角色描述', trigger: 'blur' }],
  permissions: [{ required: true, message: '请选择权限', trigger: 'change' }],
}

const editRules = {
  description: [{ required: true, message: '请输入角色描述', trigger: 'blur' }],
  permissions: [{ required: true, message: '请选择权限', trigger: 'change' }],
}

const filteredRoles = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return rolesStore.roles
  return rolesStore.roles.filter((role) => {
    const roleName = String(role.role_name || role.name || '').toLowerCase()
    const roleCode = String(role.role_code || '').toLowerCase()
    return roleName.includes(keyword) || roleCode.includes(keyword)
  })
})

const permissionMap = computed(() => {
  const map = new Map()
  for (const item of availablePermissions.value) {
    map.set(item.id, item.name || item.description || item.id)
  }
  return map
})

const initData = async () => {
  await Promise.all([
    rolesStore.fetchRoles(),
    rolesStore.fetchPermissions().then((items) => {
      availablePermissions.value = items
    }),
  ])
}

const refreshRoles = async () => {
  try {
    await rolesStore.fetchRoles()
    ElMessage.success('角色列表已刷新')
  } catch (error) {
    ElMessage.error(`刷新失败: ${error.message}`)
  }
}

const getPermissionText = (permissionId) => permissionMap.value.get(permissionId) || permissionId

const formatDateTime = (value) => (value ? new Date(value).toLocaleString('zh-CN') : '-')

const viewRole = (role) => {
  selectedRole.value = role
  showDetailDialog.value = true
}

const editRole = (role) => {
  editForm.value = {
    id: role.id,
    name: role.name,
    role_name: role.role_name || role.name,
    role_code: role.role_code,
    description: role.description || '',
    permissions: [...(role.permissions || [])],
  }
  showEditDialog.value = true
}

const configurePermissions = (role) => {
  selectedRole.value = role
  permissionForm.value = {
    permissions: [...(role.permissions || [])],
  }
  showPermissionDialog.value = true
}

const submitCreate = async () => {
  try {
    await createFormRef.value.validate()
    creating.value = true
    await rolesStore.createRole(createForm.value)
    showCreateDialog.value = false
    createForm.value = { name: '', role_code: '', description: '', permissions: [] }
    await refreshRoles()
  } catch (error) {
    if (error !== false) ElMessage.error(`创建角色失败: ${error.message}`)
  } finally {
    creating.value = false
  }
}

const submitEdit = async () => {
  try {
    await editFormRef.value.validate()
    editing.value = true
    await rolesStore.updateRole(editForm.value.id, {
      description: editForm.value.description,
      permissions: editForm.value.permissions,
    })
    showEditDialog.value = false
    await refreshRoles()
  } catch (error) {
    if (error !== false) ElMessage.error(`更新角色失败: ${error.message}`)
  } finally {
    editing.value = false
  }
}

const submitPermissions = async () => {
  try {
    configuring.value = true
    await rolesStore.updateRole(selectedRole.value.id, {
      description: selectedRole.value.description,
      permissions: permissionForm.value.permissions,
    })
    showPermissionDialog.value = false
    await refreshRoles()
  } catch (error) {
    ElMessage.error(`配置权限失败: ${error.message}`)
  } finally {
    configuring.value = false
  }
}

const deleteRole = async (role) => {
  try {
    await ElMessageBox.confirm(`确定要删除角色“${role.role_name || role.name}”吗？`, '删除确认', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await rolesStore.deleteRole(role.id)
    await refreshRoles()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(`删除角色失败: ${error.message}`)
  }
}

onMounted(() => {
  initData().catch((error) => {
    ElMessage.error(`初始化失败: ${error.message}`)
  })
})
</script>

<style scoped>
.role-management {
  background: #f0f2f5;
  min-height: calc(100vh - var(--header-height));
}

.action-card,
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

.search-input {
  width: 300px;
}

.permission-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.permission-title {
  font-weight: 600;
}

.permission-desc {
  color: #909399;
  font-size: 12px;
}
</style>
