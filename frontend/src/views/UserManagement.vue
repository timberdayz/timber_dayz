<template>
  <div class="user-management">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>👥 用户管理中心</h1>
      <p>用户管理 • 权限控制 • 安全审计</p>
    </div>

    <!-- 操作栏 -->
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
        </el-col>
        <el-col :span="12">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索用户名或邮箱"
            @input="handleSearch"
            style="width: 300px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
      </el-row>
    </el-card>

    <!-- 用户列表（标签页） -->
    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>📋 用户列表</span>
          <el-tag v-if="activeTab === 'active'">共 {{ usersStore.total }} 个用户</el-tag>
          <el-tag v-else type="info">共 {{ usersStore.deletedTotal }} 个已删除用户</el-tag>
        </div>
      </template>

      <!-- 标签页 -->
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="活跃用户" name="active">
              <el-table 
            :data="usersStore.users" 
            v-loading="usersStore.isLoading"
            stripe
            style="width: 100%"
          >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="email" label="邮箱" width="200" />
        <el-table-column prop="full_name" label="姓名" width="150" />
        <el-table-column label="角色" width="200">
          <template #default="{ row }">
            <el-tag 
              v-for="role in row.roles" 
              :key="role" 
              :type="getRoleType(role)"
              style="margin-right: 5px; margin-bottom: 5px;"
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
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="180">
          <template #default="{ row }">
            {{ row.last_login_at ? formatDateTime(row.last_login_at) : '从未登录' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewUser(row)">
              详情
            </el-button>
            <el-button link type="primary" size="small" @click="editUser(row)">
              编辑
            </el-button>
            <el-button link type="warning" size="small" @click="resetPassword(row)">
              重置密码
            </el-button>
            <el-button 
              link 
              type="danger" 
              size="small" 
              @click="deleteUser(row)"
              :disabled="row.id === currentUserId"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
          </el-table>

          <!-- 分页 -->
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

        <!-- 已删除用户标签页 -->
        <el-tab-pane label="已删除用户" name="deleted">
          <el-table 
            :data="usersStore.deletedUsers" 
            v-loading="usersStore.isLoadingDeleted"
            stripe
            style="width: 100%"
          >
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="username" label="用户名" width="150" />
            <el-table-column prop="email" label="邮箱" width="200" />
            <el-table-column prop="full_name" label="姓名" width="150" />
            <el-table-column label="角色" width="200">
              <template #default="{ row }">
                <el-tag 
                  v-for="role in row.roles" 
                  :key="role" 
                  :type="getRoleType(role)"
                  style="margin-right: 5px; margin-bottom: 5px;"
                >
                  {{ getRoleText(role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag type="info">已删除</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column prop="last_login_at" label="最后登录" width="180">
              <template #default="{ row }">
                {{ row.last_login_at ? formatDateTime(row.last_login_at) : '从未登录' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="viewUser(row)">
                  详情
                </el-button>
                <el-button 
                  link 
                  type="success" 
                  size="small" 
                  @click="restoreUser(row)"
                >
                  恢复
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
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

    <!-- 创建用户对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建用户" width="600px">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="100px">
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
          <el-select v-model="createForm.roles" multiple placeholder="请选择角色">
            <el-option 
              v-for="role in availableRoles" 
              :key="role.name" 
              :label="role.description" 
              :value="role.name" 
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="createForm.is_active" />
          <span style="margin-left: 10px;">{{ createForm.is_active ? '启用' : '禁用' }}</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCreate" :loading="creating">
          创建用户
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑用户" width="600px">
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="100px">
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
          <el-select v-model="editForm.roles" multiple placeholder="请选择角色">
            <el-option 
              v-for="role in availableRoles" 
              :key="role.name" 
              :label="role.description" 
              :value="role.name" 
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.is_active" />
          <span style="margin-left: 10px;">{{ editForm.is_active ? '启用' : '禁用' }}</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="submitEdit" :loading="editing">
          保存修改
        </el-button>
      </template>
    </el-dialog>

    <!-- 用户详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="用户详情" width="800px">
      <div v-if="selectedUser" v-loading="loadingDetail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户ID">{{ selectedUser.id }}</el-descriptions-item>
          <el-descriptions-item label="用户名">{{ selectedUser.username }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ selectedUser.email }}</el-descriptions-item>
          <el-descriptions-item label="姓名">{{ selectedUser.full_name }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag 
              v-for="role in selectedUser.roles" 
              :key="role" 
              :type="getRoleType(role)"
              style="margin-right: 5px;"
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
        </el-descriptions>
      </div>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="showResetDialog" title="重置密码" width="400px">
      <el-form :model="resetForm" :rules="resetRules" ref="resetFormRef" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="resetForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="resetForm.newPassword" type="password" placeholder="请输入新密码" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="resetForm.confirmPassword" type="password" placeholder="请再次输入密码" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showResetDialog = false">取消</el-button>
        <el-button type="primary" @click="submitReset" :loading="resetting">
          重置密码
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useUsersStore } from '@/stores/users'
import { useRolesStore } from '@/stores/roles'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Refresh,
  Search
} from '@element-plus/icons-vue'

const usersStore = useUsersStore()
const rolesStore = useRolesStore()
const authStore = useAuthStore()

// 标签页
const activeTab = ref('active')

// 分页
const currentPage = ref(1)
const deletedPage = ref(1)
const pageSize = ref(20)

// 搜索
const searchKeyword = ref('')

// 对话框状态
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showDetailDialog = ref(false)
const showResetDialog = ref(false)

// 选中的用户
const selectedUser = ref(null)
const loadingDetail = ref(false)

// 当前用户ID（不能删除自己）
const currentUserId = computed(() => authStore.user?.id)

// 可用角色
const availableRoles = ref([])

// 创建表单
const createForm = ref({
  username: '',
  email: '',
  full_name: '',
  password: '',
  roles: [],
  is_active: true
})

const createRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度在3到20个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  full_name: [
    { required: true, message: '请输入姓名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少6个字符', trigger: 'blur' }
  ],
  roles: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
}

// 编辑表单
const editForm = ref({
  id: null,
  username: '',
  email: '',
  full_name: '',
  roles: [],
  is_active: true
})

const editRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  full_name: [
    { required: true, message: '请输入姓名', trigger: 'blur' }
  ],
  roles: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
}

// 重置密码表单
const resetForm = ref({
  userId: null,
  username: '',
  newPassword: '',
  confirmPassword: ''
})

const resetRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少6个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== resetForm.value.newPassword) {
          callback(new Error('两次输入密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

// 表单引用
const createFormRef = ref()
const editFormRef = ref()
const resetFormRef = ref()

// 加载状态
const creating = ref(false)
const editing = ref(false)
const resetting = ref(false)

// 初始化数据
const initData = async () => {
  try {
    // 加载用户列表
    await usersStore.fetchUsers(currentPage.value, pageSize.value)
    
    // 加载角色列表
    await rolesStore.fetchRoles()
    availableRoles.value = rolesStore.roles
    
  } catch (error) {
    ElMessage.error('初始化数据失败: ' + error.message)
  }
}

// 处理标签页切换
const handleTabChange = async (tabName) => {
  if (tabName === 'deleted') {
    // 切换到已删除用户标签页时，加载已删除用户列表
    try {
      await usersStore.fetchDeletedUsers(deletedPage.value, pageSize.value)
    } catch (error) {
      ElMessage.error('加载已删除用户列表失败: ' + error.message)
    }
  } else {
    // 切换到活跃用户标签页时，刷新活跃用户列表
    await refreshUsers()
  }
}

// 刷新用户列表
const refreshUsers = async () => {
  try {
    await usersStore.fetchUsers(currentPage.value, pageSize.value)
    ElMessage.success('用户列表已刷新')
  } catch (error) {
    ElMessage.error('刷新失败: ' + error.message)
  }
}

// 处理搜索
const handleSearch = () => {
  // TODO: 实现搜索功能
  console.log('搜索:', searchKeyword.value)
}

// 处理分页
const handlePageChange = (page) => {
  currentPage.value = page
  usersStore.fetchUsers(page, pageSize.value)
}

const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  usersStore.fetchUsers(1, size)
}

// 已删除用户分页处理
const handleDeletedPageChange = (page) => {
  deletedPage.value = page
  usersStore.fetchDeletedUsers(page, pageSize.value)
}

const handleDeletedSizeChange = (size) => {
  pageSize.value = size
  deletedPage.value = 1
  usersStore.fetchDeletedUsers(1, size)
}

// 查看用户详情
const viewUser = async (user) => {
  selectedUser.value = user
  showDetailDialog.value = true
}

// 编辑用户
const editUser = (user) => {
  editForm.value = {
    id: user.id,
    username: user.username,
    email: user.email,
    full_name: user.full_name,
    roles: [...user.roles],
    is_active: user.is_active
  }
  showEditDialog.value = true
}

// 删除用户
const deleteUser = async (user) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${user.username}" 吗？用户将被软删除，可以在"已删除用户"标签页中恢复。`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await usersStore.deleteUser(user.id)
    await refreshUsers()
    
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除用户失败: ' + error.message)
    }
  }
}

// 恢复用户
const restoreUser = async (user) => {
  try {
    await ElMessageBox.confirm(
      `确定要恢复用户 "${user.username}" 吗？恢复后用户将可以正常登录。`,
      '恢复确认',
      {
        confirmButtonText: '确定恢复',
        cancelButtonText: '取消',
        type: 'success'
      }
    )
    
    await usersStore.restoreUser(user.id)
    // 刷新已删除用户列表
    await usersStore.fetchDeletedUsers(deletedPage.value, pageSize.value)
    
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('恢复用户失败: ' + error.message)
    }
  }
}

// 重置密码
const resetPassword = (user) => {
  resetForm.value = {
    userId: user.id,
    username: user.username,
    newPassword: '',
    confirmPassword: ''
  }
  showResetDialog.value = true
}

// 提交创建
const submitCreate = async () => {
  try {
    await createFormRef.value.validate()
    creating.value = true
    
    await usersStore.createUser(createForm.value)
    showCreateDialog.value = false
    
    // 重置表单
    createForm.value = {
      username: '',
      email: '',
      full_name: '',
      password: '',
      roles: [],
      is_active: true
    }
    
    await refreshUsers()
    
  } catch (error) {
    if (error !== false) { // 验证失败时error为false
      ElMessage.error('创建用户失败: ' + error.message)
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
    
    await usersStore.updateUser(editForm.value.id, {
      email: editForm.value.email,
      full_name: editForm.value.full_name,
      roles: editForm.value.roles,
      is_active: editForm.value.is_active
    })
    
    showEditDialog.value = false
    await refreshUsers()
    
  } catch (error) {
    if (error !== false) {
      ElMessage.error('更新用户失败: ' + error.message)
    }
  } finally {
    editing.value = false
  }
}

// 提交重置密码
const submitReset = async () => {
  try {
    await resetFormRef.value.validate()
    resetting.value = true
    
    await usersStore.resetUserPassword(resetForm.value.userId, resetForm.value.newPassword)
    showResetDialog.value = false
    
    // 重置表单
    resetForm.value = {
      userId: null,
      username: '',
      newPassword: '',
      confirmPassword: ''
    }
    
  } catch (error) {
    if (error !== false) {
      ElMessage.error('重置密码失败: ' + error.message)
    }
  } finally {
    resetting.value = false
  }
}

// 工具函数
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return new Date(dateTime).toLocaleString('zh-CN')
}

const getRoleType = (role) => {
  const typeMap = {
    'admin': 'danger',
    'manager': 'warning',
    'operator': 'primary',
    'finance': 'success',
    'inventory': 'info'
  }
  return typeMap[role] || 'info'
}

const getRoleText = (role) => {
  const textMap = {
    'admin': '管理员',
    'manager': '经理',
    'operator': '操作员',
    'finance': '财务',
    'inventory': '库存'
  }
  return textMap[role] || role
}

onMounted(() => {
  initData()
})
</script>

<style scoped>
.user-management {
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

/* 响应式设计 */
@media (max-width: 768px) {
  .user-management {
    padding: 10px;
  }
  
  .page-header h1 {
    font-size: 24px;
  }
}
</style>
