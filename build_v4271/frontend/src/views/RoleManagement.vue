<template>
  <div class="role-management erp-page-container erp-page--admin">
    <PageHeader
      title="角色管理"
      subtitle="维护角色、描述和权限集合，统一角色权限配置入口。"
      family="admin"
    />

    <!-- 操作栏 -->
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
          <el-input
            v-model="searchKeyword"
            placeholder="搜索角色名称"
            @input="handleSearch"
            class="search-input"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
      </el-row>
    </el-card>

    <!-- 角色列表 -->
    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>角色列表</span>
          <el-tag>共 {{ rolesStore.roles.length }} 个角色</el-tag>
        </div>
      </template>

      <el-table 
        :data="rolesStore.roles" 
        v-loading="rolesStore.isLoading"
        stripe
        class="erp-w-full"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="角色名称" width="150" />
        <el-table-column prop="description" label="描述" min-width="200" />
        <el-table-column label="权限" min-width="300">
          <template #default="{ row }">
            <el-tag 
              v-for="permission in row.permissions" 
              :key="permission" 
              :type="getPermissionType(permission)"
              size="small"
              class="erp-tag-gap"
            >
              {{ getPermissionText(permission) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewRole(row)">
              详情
            </el-button>
            <el-button link type="primary" size="small" @click="editRole(row)">
              编辑
            </el-button>
            <el-button link type="warning" size="small" @click="configurePermissions(row)">
              配置权限
            </el-button>
            <el-button 
              link 
              type="danger" 
              size="small" 
              @click="deleteRole(row)"
              :disabled="row.name === 'admin'"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建角色对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建角色" width="600px">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="100px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" rows="3" placeholder="请输入角色描述" />
        </el-form-item>
        <el-form-item label="权限" prop="permissions">
          <el-checkbox-group v-model="createForm.permissions">
            <el-row :gutter="20">
              <el-col :span="12" v-for="permission in availablePermissions" :key="permission.id">
                <el-checkbox :label="permission.name">
                  {{ permission.description }}
                </el-checkbox>
              </el-col>
            </el-row>
          </el-checkbox-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCreate" :loading="creating">
          创建角色
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑角色对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑角色" width="600px">
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="100px">
        <el-form-item label="角色名称">
          <el-input v-model="editForm.name" disabled />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="editForm.description" type="textarea" rows="3" placeholder="请输入角色描述" />
        </el-form-item>
        <el-form-item label="权限" prop="permissions">
          <el-checkbox-group v-model="editForm.permissions">
            <el-row :gutter="20">
              <el-col :span="12" v-for="permission in availablePermissions" :key="permission.id">
                <el-checkbox :label="permission.name">
                  {{ permission.description }}
                </el-checkbox>
              </el-col>
            </el-row>
          </el-checkbox-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="submitEdit" :loading="editing">
          保存修改
        </el-button>
      </template>
    </el-dialog>

    <!-- 角色详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="角色详情" width="800px">
      <div v-if="selectedRole" v-loading="loadingDetail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="角色ID">{{ selectedRole.id }}</el-descriptions-item>
          <el-descriptions-item label="角色名称">{{ selectedRole.name }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ selectedRole.description }}</el-descriptions-item>
          <el-descriptions-item label="权限" :span="2">
            <el-tag 
              v-for="permission in selectedRole.permissions" 
              :key="permission" 
              :type="getPermissionType(permission)"
              class="erp-tag-gap"
            >
              {{ getPermissionText(permission) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(selectedRole.created_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>

    <!-- 配置权限对话框 -->
    <el-dialog v-model="showPermissionDialog" title="配置权限" width="800px">
      <div v-if="selectedRole">
        <el-alert
          title="权限配置"
          :description="`正在为角色 '${selectedRole.name}' 配置权限`"
          type="info"
          show-icon
          class="erp-mb-lg"
        />
        
        <el-form :model="permissionForm" ref="permissionFormRef" label-width="100px">
          <el-form-item label="权限配置">
            <el-checkbox-group v-model="permissionForm.permissions">
              <el-row :gutter="20">
                <el-col :span="12" v-for="permission in availablePermissions" :key="permission.id">
                  <el-checkbox :label="permission.name">
                    <div>
                      <div class="permission-item-title">{{ permission.description }}</div>
                      <div class="erp-text-secondary-small">{{ permission.resource }} - {{ permission.action }}</div>
                    </div>
                  </el-checkbox>
                </el-col>
              </el-row>
            </el-checkbox-group>
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="showPermissionDialog = false">取消</el-button>
        <el-button type="primary" @click="submitPermissions" :loading="configuring">
          保存权限
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRolesStore } from '@/stores/roles'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Refresh,
  Search
} from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'

const rolesStore = useRolesStore()

// 搜索
const searchKeyword = ref('')

// 对话框状态
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showDetailDialog = ref(false)
const showPermissionDialog = ref(false)

// 选中的角色
const selectedRole = ref(null)
const loadingDetail = ref(false)

// 可用权限
const availablePermissions = ref([])

// 创建表单
const createForm = ref({
  name: '',
  description: '',
  permissions: []
})

const createRules = {
  name: [
    { required: true, message: '请输入角色名称', trigger: 'blur' },
    { min: 2, max: 20, message: '角色名称长度在2到20个字符', trigger: 'blur' }
  ],
  description: [
    { required: true, message: '请输入角色描述', trigger: 'blur' }
  ],
  permissions: [
    { required: true, message: '请选择权限', trigger: 'change' }
  ]
}

// 编辑表单
const editForm = ref({
  id: null,
  name: '',
  description: '',
  permissions: []
})

const editRules = {
  description: [
    { required: true, message: '请输入角色描述', trigger: 'blur' }
  ],
  permissions: [
    { required: true, message: '请选择权限', trigger: 'change' }
  ]
}

// 权限配置表单
const permissionForm = ref({
  permissions: []
})

// 表单引用
const createFormRef = ref()
const editFormRef = ref()
const permissionFormRef = ref()

// 加载状态
const creating = ref(false)
const editing = ref(false)
const configuring = ref(false)

// 初始化数据
const initData = async () => {
  try {
    // 加载角色列表
    await rolesStore.fetchRoles()
    
    // 加载权限列表
    await rolesStore.fetchPermissions()
    availablePermissions.value = rolesStore.permissions
    
  } catch (error) {
    ElMessage.error('初始化数据失败: ' + error.message)
  }
}

// 刷新角色列表
const refreshRoles = async () => {
  try {
    await rolesStore.fetchRoles()
    ElMessage.success('角色列表已刷新')
  } catch (error) {
    ElMessage.error('刷新失败: ' + error.message)
  }
}

// 处理搜索
const handleSearch = () => {
  // TODO: 实现搜索功能
  console.log('搜索:', searchKeyword.value)
}

// 查看角色详情
const viewRole = async (role) => {
  selectedRole.value = role
  showDetailDialog.value = true
}

// 编辑角色
const editRole = (role) => {
  editForm.value = {
    id: role.id,
    name: role.name,
    description: role.description,
    permissions: [...role.permissions]
  }
  showEditDialog.value = true
}

// 配置权限
const configurePermissions = (role) => {
  selectedRole.value = role
  permissionForm.value = {
    permissions: [...role.permissions]
  }
  showPermissionDialog.value = true
}

// 删除角色
const deleteRole = async (role) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色 "${role.name}" 吗？此操作不可恢复。`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await rolesStore.deleteRole(role.id)
    await refreshRoles()
    
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除角色失败: ' + error.message)
    }
  }
}

// 提交创建
const submitCreate = async () => {
  try {
    await createFormRef.value.validate()
    creating.value = true
    
    await rolesStore.createRole(createForm.value)
    showCreateDialog.value = false
    
    // 重置表单
    createForm.value = {
      name: '',
      description: '',
      permissions: []
    }
    
    await refreshRoles()
    
  } catch (error) {
    if (error !== false) {
      ElMessage.error('创建角色失败: ' + error.message)
    }
  } finally {
    creating.value = false
  }
}

// 提交编辑
const submitEdit = async () => {
  try {
    await editFormRef.value.validate()
    editing.value = true
    
    await rolesStore.updateRole(editForm.value.id, {
      description: editForm.value.description,
      permissions: editForm.value.permissions
    })
    
    showEditDialog.value = false
    await refreshRoles()
    
  } catch (error) {
    if (error !== false) {
      ElMessage.error('更新角色失败: ' + error.message)
    }
  } finally {
    editing.value = false
  }
}

// 提交权限配置
const submitPermissions = async () => {
  try {
    configuring.value = true
    
    await rolesStore.updateRole(selectedRole.value.id, {
      description: selectedRole.value.description,
      permissions: permissionForm.value.permissions
    })
    
    showPermissionDialog.value = false
    await refreshRoles()
    
  } catch (error) {
    ElMessage.error('配置权限失败: ' + error.message)
  } finally {
    configuring.value = false
  }
}

// 工具函数
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return new Date(dateTime).toLocaleString('zh-CN')
}

const getPermissionType = (permission) => {
  const typeMap = {
    'business-overview': 'primary',
    'sales-analysis': 'success',
    'sales-dashboard': 'success',
    'inventory:view': 'warning',
    'inventory:manage': 'danger',
    'inventory-dashboard:view': 'warning',
    'inventory-management': 'warning',
    'financial-management': 'info',
    'store-management': 'primary',
    'user-management': 'danger',
    'role-management': 'danger',
    'system-settings': 'warning',
    'field-mapping': 'info'
  }
  return typeMap[permission] || 'info'
}

const getPermissionText = (permission) => {
  const textMap = {
    'business-overview': '业务概览',
    'sales-analysis': '销售分析',
    'sales-dashboard': '销售看板',
    'inventory:view': '库存查看',
    'inventory:manage': '库存操作',
    'inventory-dashboard:view': '库存看板查看',
    'inventory-management': '库存管理',
    'financial-management': '财务管理',
    'store-management': '店铺管理',
    'user-management': '用户管理',
    'role-management': '角色管理',
    'system-settings': '系统设置',
    'field-mapping': '字段映射'
  }
  return textMap[permission] || permission
}

onMounted(() => {
  initData()
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

.permission-item-title {
  font-weight: 600;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .role-management {
    padding: 10px;
  }

  .search-input {
    width: 100%;
  }
}
</style>
