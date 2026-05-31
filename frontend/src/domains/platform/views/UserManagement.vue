<template>
  <div class="user-management erp-page-container erp-page--admin">
    <PageHeader
      title="用户管理"
      subtitle="管理系统账号、角色分配、密码重置、员工关联与软删除恢复。"
      family="admin"
    >
      <template #actions>
        <el-button type="primary" plain @click="$router.push('/admin/users/pending')">
          用户审批
        </el-button>
      </template>
    </PageHeader>

    <el-card class="action-card">
      <el-row :gutter="20" justify="space-between" align="middle">
        <el-col :span="12">
          <el-button type="primary" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon>
            新增用户
          </el-button>
          <el-button @click="refreshUsers">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button
            type="danger"
            plain
            :disabled="selectedActiveUserIds.length === 0 || selectedActiveUserIds.includes(currentUserId)"
            @click="batchDeleteUsers"
          >
            批量删除 ({{ selectedActiveUserIds.length }})
          </el-button>
        </el-col>
        <el-col :span="12">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索用户名、邮箱或姓名"
            class="search-input"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
      </el-row>
    </el-card>

    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <el-tag v-if="activeTab === 'active'">共 {{ filteredUsers.length }} 个活跃用户</el-tag>
          <el-tag v-else type="info">共 {{ filteredDeletedUsers.length }} 个已删除用户</el-tag>
        </div>
      </template>

      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="活跃用户" name="active">
          <el-table
            :data="filteredUsers"
            v-loading="usersStore.isLoading"
            stripe
            class="erp-w-full"
            @selection-change="handleActiveSelectionChange"
          >
            <el-table-column type="selection" width="48" />
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="username" label="用户名" width="160" />
            <el-table-column prop="email" label="邮箱" width="220" />
            <el-table-column prop="full_name" label="姓名" width="160" />
            <el-table-column label="关联员工" width="180">
              <template #default="{ row }">
                {{ formatEmployee(row) }}
              </template>
            </el-table-column>
            <el-table-column label="角色" width="220">
              <template #default="{ row }">
                <el-tag
                  v-for="role in row.roles"
                  :key="role"
                  :type="getRoleType(role)"
                  class="erp-tag-gap"
                >
                  {{ getRoleText(role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'danger'">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="last_login_at" label="最后登录" width="180">
              <template #default="{ row }">{{ row.last_login_at ? formatDateTime(row.last_login_at) : '从未登录' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="viewUser(row)">详情</el-button>
                <el-button link type="primary" size="small" @click="editUser(row)">编辑</el-button>
                <el-button link type="warning" size="small" @click="resetPassword(row)">重置密码</el-button>
                <el-button
                  link
                  type="danger"
                  size="small"
                  :disabled="row.id === currentUserId"
                  @click="deleteUser(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-container">
            <el-pagination
              v-model:current-page="currentPage"
              :total="usersStore.total"
              :page-size="pageSize"
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="handlePageChange"
              @size-change="handleSizeChange"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="已删除用户" name="deleted">
          <el-table
            :data="filteredDeletedUsers"
            v-loading="usersStore.isLoadingDeleted"
            stripe
            class="erp-w-full"
          >
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="username" label="用户名" width="160" />
            <el-table-column prop="email" label="邮箱" width="220" />
            <el-table-column prop="full_name" label="姓名" width="160" />
            <el-table-column label="角色" width="220">
              <template #default="{ row }">
                <el-tag
                  v-for="role in row.roles"
                  :key="role"
                  :type="getRoleType(role)"
                  class="erp-tag-gap"
                >
                  {{ getRoleText(role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default>
                <el-tag type="info">已删除</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="last_login_at" label="最后登录" width="180">
              <template #default="{ row }">{{ row.last_login_at ? formatDateTime(row.last_login_at) : '从未登录' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="viewUser(row)">详情</el-button>
                <el-button link type="success" size="small" @click="restoreUser(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-container">
            <el-pagination
              v-model:current-page="deletedPage"
              :total="usersStore.deletedTotal"
              :page-size="pageSize"
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="handleDeletedPageChange"
              @size-change="handleDeletedSizeChange"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="创建用户" width="640px">
      <el-alert
        v-if="roleOptionsUnavailable"
        title="角色选项加载失败"
        description="当前无法获取可分配角色，暂时不能创建或编辑用户角色。"
        type="warning"
        show-icon
        class="erp-mb-lg"
      />
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <el-input v-model="createForm.full_name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="角色" prop="roles">
          <el-select v-model="createForm.roles" multiple placeholder="请选择角色" :disabled="roleOptionsUnavailable">
            <el-option
              v-for="role in availableRoles"
              :key="role.role_code || role.name"
              :label="role.role_name || role.name"
              :value="role.role_code || role.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="createForm.is_active" />
          <span class="erp-ml-sm">{{ createForm.is_active ? '启用' : '禁用' }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="roleOptionsUnavailable" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑用户" width="640px">
      <el-alert
        v-if="roleOptionsUnavailable"
        title="角色选项加载失败"
        description="当前无法获取可分配角色，角色字段暂时不可编辑。"
        type="warning"
        show-icon
        class="erp-mb-lg"
      />
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="editForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <el-input v-model="editForm.full_name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="角色" prop="roles">
          <el-select v-model="editForm.roles" multiple placeholder="请选择角色" :disabled="roleOptionsUnavailable">
            <el-option
              v-for="role in availableRoles"
              :key="role.role_code || role.name"
              :label="role.role_name || role.name"
              :value="role.role_code || role.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关联员工">
          <el-select
            v-model="editForm.employee_id"
            placeholder="请选择关联员工，可清空解除关联"
            clearable
            filterable
            class="erp-w-full"
          >
            <el-option
              v-for="emp in employeeOptions"
              :key="emp.id"
              :label="`${emp.name} (${emp.employee_code})`"
              :value="emp.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.is_active" />
          <span class="erp-ml-sm">{{ editForm.is_active ? '启用' : '禁用' }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDetailDialog" title="用户详情" width="800px">
      <div v-if="selectedUser" v-loading="loadingDetail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户 ID">{{ selectedUser.id }}</el-descriptions-item>
          <el-descriptions-item label="用户名">{{ selectedUser.username }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ selectedUser.email }}</el-descriptions-item>
          <el-descriptions-item label="姓名">{{ selectedUser.full_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag
              v-for="role in selectedUser.roles"
              :key="role"
              :type="getRoleType(role)"
              class="erp-tag-gap"
            >
              {{ getRoleText(role) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="selectedUser.is_active ? 'success' : 'danger'">
              {{ selectedUser.is_active ? '启用' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(selectedUser.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="最后登录">
            {{ selectedUser.last_login_at ? formatDateTime(selectedUser.last_login_at) : '从未登录' }}
          </el-descriptions-item>
          <el-descriptions-item label="关联员工">
            {{ formatEmployee(selectedUser) }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>

    <el-dialog v-model="showResetDialog" title="重置密码" width="420px">
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="resetForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="resetForm.newPassword" type="password" placeholder="请输入新密码" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="resetForm.confirmPassword" type="password" placeholder="请再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showResetDialog = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="submitReset">重置密码</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { useUsersStore } from '@/stores/users'
import { useRolesStore } from '@/stores/roles'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'

const usersStore = useUsersStore()
const rolesStore = useRolesStore()
const authStore = useAuthStore()

const activeTab = ref('active')
const currentPage = ref(1)
const deletedPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showDetailDialog = ref(false)
const showResetDialog = ref(false)
const selectedUser = ref(null)
const loadingDetail = ref(false)
const currentUserId = computed(() => authStore.user?.id)
const selectedActiveRows = ref([])
const availableRoles = ref([])
const employeeOptions = ref([])
const creating = ref(false)
const editing = ref(false)
const resetting = ref(false)
const createFormRef = ref()
const editFormRef = ref()
const resetFormRef = ref()

const createForm = ref({
  username: '',
  email: '',
  full_name: '',
  password: '',
  roles: [],
  is_active: true,
})

const editForm = ref({
  id: null,
  username: '',
  email: '',
  full_name: '',
  roles: [],
  is_active: true,
  employee_id: null,
})

const resetForm = ref({
  userId: null,
  username: '',
  newPassword: '',
  confirmPassword: '',
})

const roleOptionsUnavailable = computed(() => availableRoles.value.length === 0)
const selectedActiveUserIds = computed(() => (selectedActiveRows.value || []).map((row) => row.id))

const filteredUsers = computed(() => filterUsers(usersStore.users))
const filteredDeletedUsers = computed(() => filterUsers(usersStore.deletedUsers))

const createRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度需在 3 到 20 个字符之间', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  full_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少 6 个字符', trigger: 'blur' },
  ],
  roles: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const editRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  full_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  roles: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const resetRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少 6 个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== resetForm.value.newPassword) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

const initData = async () => {
  try {
    await usersStore.fetchUsers(currentPage.value, pageSize.value)
  } catch (error) {
    ElMessage.error(`初始化失败: ${error.message}`)
    return
  }

  try {
    availableRoles.value = await rolesStore.fetchAssignableRoles()
  } catch (error) {
    availableRoles.value = []
    ElMessage.warning('角色选项加载失败，创建或编辑用户时将不可选择角色')
  }
}

const filterUsers = (rows = []) => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return rows
  return rows.filter((row) => {
    const fields = [row.username, row.email, row.full_name, row.employee_name, row.employee_code]
    return fields.some((item) => String(item || '').toLowerCase().includes(keyword))
  })
}

const handleActiveSelectionChange = (rows) => {
  selectedActiveRows.value = rows || []
}

const handleTabChange = async (tabName) => {
  if (tabName === 'deleted') {
    try {
      await usersStore.fetchDeletedUsers(deletedPage.value, pageSize.value)
    } catch (error) {
      ElMessage.error(`加载已删除用户失败: ${error.message}`)
    }
  } else {
    await refreshUsers()
  }
}

const refreshUsers = async () => {
  try {
    await usersStore.fetchUsers(currentPage.value, pageSize.value)
    ElMessage.success('用户列表已刷新')
  } catch (error) {
    ElMessage.error(`刷新失败: ${error.message}`)
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  usersStore.fetchUsers(page, pageSize.value)
}

const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  usersStore.fetchUsers(1, size)
}

const handleDeletedPageChange = (page) => {
  deletedPage.value = page
  usersStore.fetchDeletedUsers(page, pageSize.value)
}

const handleDeletedSizeChange = (size) => {
  pageSize.value = size
  deletedPage.value = 1
  usersStore.fetchDeletedUsers(1, size)
}

const viewUser = (user) => {
  selectedUser.value = user
  showDetailDialog.value = true
}

const editUser = async (user) => {
  editForm.value = {
    id: user.id,
    username: user.username,
    email: user.email,
    full_name: user.full_name,
    roles: [...(user.roles || [])],
    is_active: user.is_active,
    employee_id: user.employee_id ?? null,
  }

  try {
    const res = await api.getHrEmployees({ page: 1, page_size: 500 })
    employeeOptions.value = res?.data ?? res ?? []
  } catch {
    employeeOptions.value = []
    ElMessage.warning('员工列表加载失败，员工关联字段暂时不可用')
  }

  showEditDialog.value = true
}

const deleteUser = async (user) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户“${user.username}”吗？用户将被软删除，可在“已删除用户”页恢复。`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    await usersStore.deleteUser(user.id)
    await refreshUsers()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`删除用户失败: ${error.message}`)
    }
  }
}

const batchDeleteUsers = async () => {
  if (!selectedActiveUserIds.value.length) return
  if (selectedActiveUserIds.value.includes(currentUserId.value)) {
    ElMessage.warning('不能删除当前登录用户')
    return
  }

  const promptResult = await ElMessageBox.prompt(
    `将软删除 ${selectedActiveUserIds.value.length} 个用户，可在“已删除用户”页恢复。\n可选填写删除原因：`,
    '批量删除确认',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '可选填写',
      inputValue: '',
    }
  ).catch(() => null)

  if (!promptResult) return

  try {
    const payload = await usersStore.deleteUsersBatch(selectedActiveUserIds.value, (promptResult.value || '').trim())
    const failedItems = (payload?.results || []).filter((item) => !item.ok)
    if (failedItems.length) {
      await ElMessageBox.alert(
        failedItems.map((item) => `user_id=${item.user_id}: ${item.error_message || 'failed'}`).join('\n'),
        '部分失败',
        { type: 'warning' }
      )
    }
    selectedActiveRows.value = []
    await refreshUsers()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`批量删除用户失败: ${error.message}`)
    }
  }
}

const restoreUser = async (user) => {
  try {
    await ElMessageBox.confirm(`确定要恢复用户“${user.username}”吗？`, '恢复确认', {
      confirmButtonText: '确定恢复',
      cancelButtonText: '取消',
      type: 'success',
    })

    await usersStore.restoreUser(user.id)
    await usersStore.fetchDeletedUsers(deletedPage.value, pageSize.value)
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`恢复用户失败: ${error.message}`)
    }
  }
}

const resetPassword = (user) => {
  resetForm.value = {
    userId: user.id,
    username: user.username,
    newPassword: '',
    confirmPassword: '',
  }
  showResetDialog.value = true
}

const submitCreate = async () => {
  try {
    await createFormRef.value.validate()
    creating.value = true
    await usersStore.createUser(createForm.value)
    showCreateDialog.value = false
    createForm.value = {
      username: '',
      email: '',
      full_name: '',
      password: '',
      roles: [],
      is_active: true,
    }
    await refreshUsers()
  } catch (error) {
    if (error !== false) {
      ElMessage.error(`创建用户失败: ${error.message}`)
    }
  } finally {
    creating.value = false
  }
}

const submitEdit = async () => {
  try {
    await editFormRef.value.validate()
    editing.value = true
    await usersStore.updateUser(editForm.value.id, {
      email: editForm.value.email,
      full_name: editForm.value.full_name,
      employee_id: editForm.value.employee_id ?? undefined,
      roles: editForm.value.roles,
      is_active: editForm.value.is_active,
    })
    showEditDialog.value = false
    await refreshUsers()
  } catch (error) {
    if (error !== false) {
      ElMessage.error(`更新用户失败: ${error.message}`)
    }
  } finally {
    editing.value = false
  }
}

const submitReset = async () => {
  try {
    await resetFormRef.value.validate()
    resetting.value = true
    await usersStore.resetUserPassword(resetForm.value.userId, resetForm.value.newPassword)
    showResetDialog.value = false
    resetForm.value = {
      userId: null,
      username: '',
      newPassword: '',
      confirmPassword: '',
    }
  } catch (error) {
    if (error !== false) {
      ElMessage.error(`重置密码失败: ${error.message}`)
    }
  } finally {
    resetting.value = false
  }
}

const formatDateTime = (value) => (value ? new Date(value).toLocaleString('zh-CN') : '-')

const formatEmployee = (row) => {
  return row.employee_code && row.employee_name ? `${row.employee_name} (${row.employee_code})` : '未关联'
}

const getRoleType = (role) => {
  const typeMap = {
    admin: 'danger',
    manager: 'warning',
    operator: 'primary',
    finance: 'success',
    inventory: 'info',
    tourist: 'info',
    investor: 'warning',
  }
  return typeMap[role] || 'info'
}

const getRoleText = (role) => {
  const textMap = {
    admin: '管理员',
    manager: '经理',
    operator: '操作员',
    finance: '财务',
    inventory: '库存',
    tourist: '游客',
    investor: '投资人',
  }
  return textMap[role] || role
}

onMounted(() => {
  initData()
})
</script>

<style scoped>
.user-management {
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

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

.search-input {
  width: 300px;
}

@media (max-width: 768px) {
  .user-management {
    padding: 10px;
  }

  .search-input {
    width: 100%;
  }
}
</style>
