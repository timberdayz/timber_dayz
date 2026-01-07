<template>
  <div class="account-switcher">
    <el-dropdown @command="handleCommand" trigger="click">
      <div class="account-trigger">
        <el-avatar :size="32" :src="currentUser.avatar">
          <el-icon><User /></el-icon>
        </el-avatar>
        <span class="account-name">{{ currentUser.name }}</span>
        <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
      </div>
      <template #dropdown>
        <el-dropdown-menu>
          <!-- 当前用户信息 -->
          <div class="current-user-info">
            <div class="user-avatar">
              <el-avatar :size="40" :src="currentUser.avatar">
                <el-icon><User /></el-icon>
              </el-avatar>
            </div>
            <div class="user-details">
              <div class="user-name">{{ currentUser.name }}</div>
              <div class="user-role">{{ getRoleName(currentUser.role) }}</div>
            </div>
          </div>
          
          <el-dropdown-item command="personal-settings">
            <el-icon><User /></el-icon>
            <span>个人设置</span>
          </el-dropdown-item>
          
          <el-dropdown-item command="system-settings">
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </el-dropdown-item>
          
          <!-- 账号切换区域 -->
          <el-dropdown-item divided>
            <div class="switch-account-header">
              <el-icon><Switch /></el-icon>
              <span>切换账号</span>
            </div>
          </el-dropdown-item>
          
          <div class="account-list">
            <div 
              v-for="account in availableAccounts" 
              :key="account.id"
              class="account-item"
              :class="{ active: account.id === currentUser.id }"
              @click="switchAccount(account)"
            >
              <el-avatar :size="24" :src="account.avatar">
                <el-icon><User /></el-icon>
              </el-avatar>
              <div class="account-info">
                <div class="account-name">{{ account.name }}</div>
                <div class="account-role">{{ getRoleName(account.role) }}</div>
              </div>
              <el-icon v-if="account.id === currentUser.id" class="check-icon">
                <Check />
              </el-icon>
            </div>
          </div>
          
          <!-- 添加新账号 -->
          <el-dropdown-item command="add-account">
            <el-icon><Plus /></el-icon>
            <span>添加账号</span>
          </el-dropdown-item>
          
          <el-dropdown-item divided command="logout">
            <el-icon><SwitchButton /></el-icon>
            <span>退出登录</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    
    <!-- 添加账号对话框 -->
    <el-dialog
      v-model="showAddAccountDialog"
      title="添加新账号"
      width="500px"
      :before-close="handleCloseDialog"
    >
      <el-form :model="newAccount" :rules="accountRules" ref="accountFormRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="newAccount.username" placeholder="请输入用户名"></el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="newAccount.password" type="password" placeholder="请输入密码"></el-input>
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="newAccount.name" placeholder="请输入姓名"></el-input>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="newAccount.role" placeholder="请选择角色">
            <el-option label="管理员" value="admin"></el-option>
            <el-option label="经理" value="manager"></el-option>
            <el-option label="操作员" value="operator"></el-option>
            <el-option label="财务" value="finance"></el-option>
            <el-option label="库存" value="inventory"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="newAccount.email" placeholder="请输入邮箱"></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showAddAccountDialog = false">取消</el-button>
          <el-button type="primary" @click="confirmAddAccount">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  User, ArrowDown, Setting, Switch, Check, Plus, SwitchButton 
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const accountFormRef = ref(null)

// 响应式数据
const showAddAccountDialog = ref(false)

// 当前用户信息
const currentUser = computed(() => userStore.userInfo || {
  id: 1,
  name: '管理员',
  role: 'admin',
  avatar: '',
  email: 'admin@xihong-erp.com'
})

// 可用账号列表
const availableAccounts = ref([
  {
    id: 1,
    name: '管理员',
    role: 'admin',
    avatar: '',
    email: 'admin@xihong-erp.com',
    username: 'admin'
  },
  {
    id: 2,
    name: '张经理',
    role: 'manager',
    avatar: '',
    email: 'manager@xihong-erp.com',
    username: 'manager'
  },
  {
    id: 3,
    name: '李操作员',
    role: 'operator',
    avatar: '',
    email: 'operator@xihong-erp.com',
    username: 'operator'
  },
  {
    id: 4,
    name: '王财务',
    role: 'finance',
    avatar: '',
    email: 'finance@xihong-erp.com',
    username: 'finance'
  }
])

// 新账号表单
const newAccount = reactive({
  username: '',
  password: '',
  name: '',
  role: '',
  email: ''
})

// 表单验证规则
const accountRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' }
  ],
  role: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ]
}

// 方法
const getRoleName = (role) => {
  const roleMap = {
    'admin': '管理员',
    'manager': '经理',
    'operator': '操作员',
    'finance': '财务',
    'inventory': '库存'
  }
  return roleMap[role] || '未知角色'
}

const handleCommand = (command) => {
  switch (command) {
    case 'personal-settings':
      router.push('/personal-settings')
      break
    case 'system-settings':
      router.push('/system-settings')
      break
    case 'add-account':
      addAccount()
      break
    case 'logout':
      logout()
      break
  }
}

const switchAccount = (account) => {
  ElMessageBox.confirm(
    `确定要切换到账号 "${account.name}" 吗？`,
    '切换账号',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'info'
    }
  ).then(() => {
    // 模拟账号切换
    userStore.userInfo = {
      ...account,
      id: account.id,
      name: account.name,
      role: account.role,
      avatar: account.avatar,
      email: account.email,
      username: account.username
    }
    
    // 根据角色设置权限
    const rolePermissions = {
      'admin': [
        'business-overview', 'sales-analysis', 'inventory-management', 
        'human-resources', 'financial-management', 'store-management',
        'system-settings', 'account-management', 'personal-settings', 'field-mapping'
      ],
      'manager': [
        'business-overview', 'sales-analysis', 'inventory-management', 
        'human-resources', 'financial-management', 'store-management',
        'personal-settings'
      ],
      'operator': [
        'business-overview', 'sales-analysis', 'inventory-management',
        'personal-settings'
      ],
      'finance': [
        'business-overview', 'financial-management', 'personal-settings'
      ],
      'inventory': [
        'business-overview', 'inventory-management', 'personal-settings'
      ]
    }
    
    userStore.permissions = rolePermissions[account.role] || []
    userStore.roles = [account.role]
    
    // 保存到本地存储
    localStorage.setItem('userInfo', JSON.stringify(userStore.userInfo))
    localStorage.setItem('permissions', JSON.stringify(userStore.permissions))
    localStorage.setItem('roles', JSON.stringify(userStore.roles))
    
    ElMessage.success(`已切换到账号: ${account.name}`)
    
    // 刷新页面以更新权限
    setTimeout(() => {
      window.location.reload()
    }, 1000)
  })
}

const addAccount = () => {
  showAddAccountDialog.value = true
}

const confirmAddAccount = () => {
  accountFormRef.value.validate((valid) => {
    if (valid) {
      // 检查用户名是否已存在
      const existingAccount = availableAccounts.value.find(
        account => account.username === newAccount.username
      )
      
      if (existingAccount) {
        ElMessage.error('用户名已存在')
        return
      }
      
      // 添加新账号
      const newId = Math.max(...availableAccounts.value.map(a => a.id)) + 1
      const account = {
        id: newId,
        username: newAccount.username,
        name: newAccount.name,
        role: newAccount.role,
        email: newAccount.email,
        avatar: ''
      }
      
      availableAccounts.value.push(account)
      
      // 重置表单
      Object.keys(newAccount).forEach(key => {
        newAccount[key] = ''
      })
      accountFormRef.value?.resetFields()
      
      showAddAccountDialog.value = false
      ElMessage.success('账号添加成功')
    } else {
      ElMessage.error('请检查输入信息')
    }
  })
}

const handleCloseDialog = () => {
  showAddAccountDialog.value = false
  // 重置表单
  Object.keys(newAccount).forEach(key => {
    newAccount[key] = ''
  })
  accountFormRef.value?.resetFields()
}

const logout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '确认退出', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  })
}

// 组件挂载
onMounted(() => {
  console.log('账号切换组件已加载')
})
</script>

<style scoped>
.account-switcher {
  display: flex;
  align-items: center;
}

.account-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.1);
}

.account-trigger:hover {
  background: rgba(255, 255, 255, 0.2);
}

.account-name {
  color: white;
  font-size: 14px;
  font-weight: 500;
}

.dropdown-icon {
  color: white;
  font-size: 12px;
  transition: transform 0.3s ease;
}

.current-user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 6px;
  margin: 8px;
}

.user-details {
  flex: 1;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 2px;
}

.user-role {
  font-size: 12px;
  color: #909399;
}

.switch-account-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 8px;
}

.account-list {
  max-height: 200px;
  overflow-y: auto;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  cursor: pointer;
  transition: all 0.3s ease;
  border-radius: 4px;
  margin: 2px 8px;
}

.account-item:hover {
  background: #f0f9ff;
}

.account-item.active {
  background: #e1f5fe;
  border: 1px solid #409eff;
}

.account-info {
  flex: 1;
}

.account-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}

.account-role {
  font-size: 12px;
  color: #909399;
}

.check-icon {
  color: #409eff;
  font-size: 16px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .account-trigger {
    padding: 6px 8px;
  }
  
  .account-name {
    display: none;
  }
  
  .current-user-info {
    flex-direction: column;
    text-align: center;
  }
  
  .account-item {
    padding: 12px 16px;
  }
}
</style>