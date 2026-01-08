<template>
  <div class="user-approval">
    <div class="page-header">
      <h1>用户审批</h1>
      <p>审批待审核的新用户注册申请</p>
    </div>

    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>待审批用户列表</span>
          <el-button @click="refreshUsers" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="pendingUsers"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="email" label="邮箱" width="200" />
        <el-table-column prop="full_name" label="姓名" width="150" />
        <el-table-column prop="department" label="部门" width="150" />
        <el-table-column prop="created_at" label="注册时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button
              type="success"
              size="small"
              @click="handleApprove(row)"
            >
              批准
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="handleReject(row)"
            >
              拒绝
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper" v-if="total > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>

      <el-empty v-if="!loading && pendingUsers.length === 0" description="暂无待审批用户" />
    </el-card>

    <!-- 批准对话框 -->
    <el-dialog
      v-model="approveDialogVisible"
      title="批准用户"
      width="500px"
    >
      <el-form :model="approveForm" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="approveForm.username" disabled />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="approveForm.email" disabled />
        </el-form-item>
        <el-form-item label="分配角色">
          <el-select
            v-model="approveForm.roleIds"
            multiple
            placeholder="选择角色（可选，默认operator）"
            style="width: 100%"
            :loading="rolesLoading"
          >
            <el-option
              v-for="role in availableRoles"
              :key="role.id"
              :label="role.name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="审批备注">
          <el-input
            v-model="approveForm.notes"
            type="textarea"
            :rows="3"
            placeholder="可选"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="approveDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmApprove" :loading="approving">
          确认批准
        </el-button>
      </template>
    </el-dialog>

    <!-- 拒绝对话框 -->
    <el-dialog
      v-model="rejectDialogVisible"
      title="拒绝用户"
      width="500px"
    >
      <el-form :model="rejectForm" :rules="rejectRules" ref="rejectFormRef" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="rejectForm.username" disabled />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="rejectForm.email" disabled />
        </el-form-item>
        <el-form-item label="拒绝原因" prop="reason">
          <el-input
            v-model="rejectForm.reason"
            type="textarea"
            :rows="4"
            placeholder="请输入拒绝原因（至少5个字符）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmReject" :loading="rejecting">
          确认拒绝
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import usersApi from '@/api/users'
import rolesApi from '@/api/roles'

const loading = ref(false)
const pendingUsers = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

// 批准对话框
const approveDialogVisible = ref(false)
const approving = ref(false)
const approveForm = reactive({
  userId: null,
  username: '',
  email: '',
  roleIds: [],
  notes: ''
})

// 拒绝对话框
const rejectDialogVisible = ref(false)
const rejecting = ref(false)
const rejectFormRef = ref(null)
const rejectForm = reactive({
  userId: null,
  username: '',
  email: '',
  reason: ''
})

const rejectRules = {
  reason: [
    { required: true, message: '请输入拒绝原因', trigger: 'blur' },
    { min: 5, message: '拒绝原因至少5个字符', trigger: 'blur' }
  ]
}

// 角色相关
const rolesLoading = ref(false)
const availableRoles = ref([])

// 加载待审批用户列表
const loadPendingUsers = async () => {
  loading.value = true
  try {
    const result = await usersApi.getPendingUsers(currentPage.value, pageSize.value)
    // 处理响应（可能是数组或包装对象）
    if (Array.isArray(result)) {
      pendingUsers.value = result
      total.value = result.length // 如果没有分页信息，使用数组长度
    } else if (result.data) {
      pendingUsers.value = result.data
      total.value = result.total || result.data.length
    } else {
      pendingUsers.value = []
      total.value = 0
    }
  } catch (error) {
    console.error('加载待审批用户失败:', error)
    ElMessage.error('加载待审批用户失败: ' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 加载角色列表
const loadRoles = async () => {
  rolesLoading.value = true
  try {
    const result = await rolesApi.getRoles()
    if (Array.isArray(result)) {
      availableRoles.value = result
    } else if (result.data) {
      availableRoles.value = result.data
    }
  } catch (error) {
    console.error('加载角色列表失败:', error)
    // 不显示错误消息，因为角色是可选的
  } finally {
    rolesLoading.value = false
  }
}

// 刷新用户列表
const refreshUsers = () => {
  loadPendingUsers()
}

// 处理批准
const handleApprove = (user) => {
  approveForm.userId = user.user_id
  approveForm.username = user.username
  approveForm.email = user.email
  approveForm.roleIds = []
  approveForm.notes = ''
  approveDialogVisible.value = true
}

// 确认批准
const confirmApprove = async () => {
  approving.value = true
  try {
    const result = await usersApi.approveUser(approveForm.userId, {
      role_ids: approveForm.roleIds.length > 0 ? approveForm.roleIds : undefined,
      notes: approveForm.notes || undefined
    })

    // [*] 校验后端返回的审批结果，避免出现“前端提示成功但实际未生效”
    if (result && result.status === 'active') {
      ElMessage.success('用户批准成功')
    } else {
      ElMessage.warning(`用户已提交批准请求，但状态未变为active（当前：${result?.status || 'unknown'}）`)
    }

    approveDialogVisible.value = false
    await loadPendingUsers()
  } catch (error) {
    console.error('批准用户失败:', error)
    ElMessage.error('批准用户失败: ' + (error.message || '未知错误'))
  } finally {
    approving.value = false
  }
}

// 处理拒绝
const handleReject = (user) => {
  rejectForm.userId = user.user_id
  rejectForm.username = user.username
  rejectForm.email = user.email
  rejectForm.reason = ''
  rejectDialogVisible.value = true
}

// 确认拒绝
const confirmReject = async () => {
  if (!rejectFormRef.value) return
  
  await rejectFormRef.value.validate(async (valid) => {
    if (!valid) return

    rejecting.value = true
    try {
      await usersApi.rejectUser(rejectForm.userId, {
        reason: rejectForm.reason
      })
      
      ElMessage.success('用户已拒绝')
      rejectDialogVisible.value = false
      await loadPendingUsers()
    } catch (error) {
      console.error('拒绝用户失败:', error)
      ElMessage.error('拒绝用户失败: ' + (error.message || '未知错误'))
    } finally {
      rejecting.value = false
    }
  })
}

// 分页处理
const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  loadPendingUsers()
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadPendingUsers()
}

// 工具函数
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return new Date(dateTime).toLocaleString('zh-CN')
}

onMounted(() => {
  loadPendingUsers()
  loadRoles()
})
</script>

<style scoped>
.user-approval {
  padding: 20px;
  background: #f0f2f5;
  min-height: 100vh;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 24px;
  color: #333;
  margin-bottom: 8px;
}

.page-header p {
  color: #666;
  font-size: 14px;
}

.table-card {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>

