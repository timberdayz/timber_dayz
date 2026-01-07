<template>
  <div class="account-management">
    <!-- 页面头部 -->
    <el-page-header title="返回" content="账号管理" @back="$router.back()" />
    <p class="page-description">统一管理多平台账号，确保账号安全</p>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="总账号数" :value="accountsStore.stats.total">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="活跃账号" :value="accountsStore.stats.active">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="异常账号" :value="accountsStore.stats.inactive">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="支持平台" :value="accountsStore.stats.platforms">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作工具栏 -->
    <el-card class="toolbar-card">
      <el-row :gutter="10" style="margin-bottom: 15px">
        <!-- 筛选 -->
        <el-col :span="4">
          <el-select v-model="filters.platform" placeholder="平台筛选" clearable @change="handleFilterChange">
            <el-option v-for="platform in platformOptions" :key="platform" :label="platform" :value="platform" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.enabled" placeholder="状态筛选" clearable @change="handleFilterChange">
            <el-option label="活跃" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.shop_type" placeholder="店铺类型" clearable @change="handleFilterChange">
            <el-option label="本地店" value="local" />
            <el-option label="全球店" value="global" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-input 
            v-model="filters.search" 
            placeholder="搜索店铺名或账号ID" 
            clearable
            @input="handleSearchChange"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
      </el-row>

      <!-- 操作按钮 -->
      <el-row :gutter="10">
        <el-col :span="24">
          <el-button type="primary" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon>
            添加账号
          </el-button>
          <el-button @click="showBatchDialog = true">
            <el-icon><Files /></el-icon>
            批量添加店铺
          </el-button>
          <el-button @click="handleImport" :loading="importLoading">
            <el-icon><Download /></el-icon>
            从配置文件导入
          </el-button>
          <el-button @click="handleRefresh" :loading="accountsStore.loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 账号列表 -->
    <el-card class="table-card">
      <el-table 
        :data="accountsStore.accounts" 
        v-loading="accountsStore.loading"
        style="width: 100%"
        height="500"
      >
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="account_id" label="账号ID" width="180" show-overflow-tooltip />
        <el-table-column prop="account_alias" label="账号别名" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.account_alias">{{ row.account_alias }}</span>
            <span v-else style="color: #999;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="store_name" label="店铺名称" width="200" show-overflow-tooltip />
        
        <!-- ⭐ v4.18.1新增：店铺ID列 -->
        <el-table-column prop="shop_id" label="店铺ID" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.shop_id">{{ row.shop_id }}</span>
            <span v-else style="color: #999;">-</span>
          </template>
        </el-table-column>
        
        <el-table-column label="店铺类型" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.shop_type === 'local'" type="success" size="small">本地店</el-tag>
            <el-tag v-else-if="row.shop_type === 'global'" type="warning" size="small">全球店</el-tag>
            <el-tag v-else type="info" size="small">未设置</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="shop_region" label="区域" width="80" />
        
        <el-table-column label="能力配置" width="180">
          <template #default="{ row }">
            <el-tooltip :content="getCapabilitiesText(row.capabilities)" placement="top">
              <div class="capabilities-tags">
                <el-tag 
                  v-for="(enabled, domain) in row.capabilities" 
                  :key="domain"
                  :type="enabled ? 'success' : 'info'"
                  size="small"
                  class="capability-tag"
                >
                  {{ domainLabels[domain] || domain }}
                </el-tag>
              </div>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-switch 
              v-model="row.enabled" 
              @change="handleToggleEnabled(row)"
              :loading="row._updating"
            />
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog 
      v-model="showCreateDialog" 
      :title="editingAccount ? '编辑账号' : '添加账号'"
      width="800px"
      :close-on-click-modal="false"
    >
      <el-form :model="accountForm" label-width="120px" :rules="formRules" ref="accountFormRef">
        <el-tabs v-model="activeTab">
          <!-- 基本信息 -->
          <el-tab-pane label="基本信息" name="basic">
            <el-form-item label="平台" prop="platform">
              <el-select v-model="accountForm.platform" placeholder="选择平台">
                <el-option label="Shopee" value="shopee" />
                <el-option label="TikTok" value="tiktok" />
                <el-option label="Amazon" value="amazon" />
                <el-option label="妙手ERP" value="miaoshou" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="账号ID" prop="account_id">
              <el-input v-model="accountForm.account_id" placeholder="唯一标识，如：shopee_sg_local_001" />
              <div class="form-tip">账号的唯一标识，创建后不可修改</div>
            </el-form-item>
            
            <el-form-item label="账号别名">
              <el-input v-model="accountForm.account_alias" placeholder="用于关联导出数据中的自定义名称（如：miaoshou ERP的订单数据）" />
              <div class="form-tip">可选，用于匹配导出数据中的账号名称（如：东朗照明主体）</div>
            </el-form-item>
            
            <el-form-item label="店铺名称" prop="store_name">
              <el-input v-model="accountForm.store_name" placeholder="如：HongXi Singapore Local" />
            </el-form-item>
            
            <el-form-item label="主账号">
              <el-input v-model="accountForm.parent_account" placeholder="多店铺共用时填写，如：hongxikeji:main" />
              <div class="form-tip">多个店铺共用同一登录账号时填写</div>
            </el-form-item>
            
            <el-form-item label="店铺类型">
              <el-radio-group v-model="accountForm.shop_type" @change="handleShopTypeChange">
                <el-radio label="local">本地店铺</el-radio>
                <el-radio label="global">全球店铺</el-radio>
              </el-radio-group>
            </el-form-item>
            
            <el-form-item label="店铺区域">
              <el-input v-model="accountForm.shop_region" placeholder="如：SG, MY, GLOBAL" />
              <div class="form-tip">新加坡: SG, 马来西亚: MY, 全球: GLOBAL</div>
            </el-form-item>
            
            <!-- ⭐ v4.18.1新增：店铺ID字段 -->
            <el-form-item label="店铺ID">
              <el-input v-model="accountForm.shop_id" placeholder="用于关联数据同步中的shop_id" />
              <div class="form-tip">可选，用于匹配数据同步中的店铺标识（数据采集模块自动获取的shop_id）</div>
            </el-form-item>
          </el-tab-pane>
          
          <!-- 登录信息 -->
          <el-tab-pane label="登录信息" name="login">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="accountForm.username" placeholder="登录用户名" />
            </el-form-item>
            
            <el-form-item label="密码" prop="password">
              <el-input 
                v-model="accountForm.password" 
                type="password" 
                placeholder="登录密码（加密存储）"
                show-password 
              />
              <div class="form-tip">密码将被加密存储，更新时留空表示不修改</div>
            </el-form-item>
            
            <el-form-item label="登录URL">
              <el-input v-model="accountForm.login_url" placeholder="https://..." />
            </el-form-item>
            
            <el-form-item label="邮箱">
              <el-input v-model="accountForm.email" placeholder="example@email.com" />
            </el-form-item>
            
            <el-form-item label="手机号">
              <el-input v-model="accountForm.phone" placeholder="手机号码" />
            </el-form-item>
            
            <el-form-item label="账号地区">
              <el-input v-model="accountForm.region" placeholder="CN" />
            </el-form-item>
            
            <el-form-item label="主货币">
              <el-input v-model="accountForm.currency" placeholder="CNY" />
            </el-form-item>
          </el-tab-pane>
          
          <!-- 能力配置 -->
          <el-tab-pane label="能力配置" name="capabilities">
            <div class="capabilities-grid">
              <el-checkbox v-model="accountForm.capabilities.orders">
                <div class="capability-item">
                  <el-icon><ShoppingCart /></el-icon>
                  <span>订单数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.products">
                <div class="capability-item">
                  <el-icon><Box /></el-icon>
                  <span>商品数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.services">
                <div class="capability-item">
                  <el-icon><Service /></el-icon>
                  <span>客服数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.analytics">
                <div class="capability-item">
                  <el-icon><TrendCharts /></el-icon>
                  <span>流量数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.finance">
                <div class="capability-item">
                  <el-icon><Money /></el-icon>
                  <span>财务数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.inventory">
                <div class="capability-item">
                  <el-icon><Grid /></el-icon>
                  <span>库存数据</span>
                </div>
              </el-checkbox>
            </div>
            
            <el-alert 
              title="提示" 
              type="info" 
              :closable="false"
              style="margin-top: 20px"
            >
              根据店铺类型自动配置：
              <ul>
                <li>本地店铺：通常支持所有数据域</li>
                <li>全球店铺：通常不支持客服数据</li>
              </ul>
            </el-alert>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      
      <template #footer>
        <el-button @click="handleCancelEdit">取消</el-button>
        <el-button type="primary" @click="handleSaveAccount" :loading="accountsStore.loading">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量添加店铺对话框 -->
    <el-dialog 
      v-model="showBatchDialog" 
      title="批量添加店铺"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="batchForm" label-width="120px">
        <el-form-item label="主账号" required>
          <el-input v-model="batchForm.parent_account" placeholder="如：hongxikeji:main" />
        </el-form-item>
        
        <el-form-item label="平台" required>
          <el-select v-model="batchForm.platform">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="用户名" required>
          <el-input v-model="batchForm.username" placeholder="共用的登录用户名" />
        </el-form-item>
        
        <el-form-item label="密码" required>
          <el-input v-model="batchForm.password" type="password" placeholder="共用的登录密码" show-password />
        </el-form-item>
        
        <el-form-item label="店铺列表">
          <el-table :data="batchForm.shops" style="width: 100%">
            <el-table-column label="店铺名称">
              <template #default="{ row }">
                <el-input v-model="row.store_name" placeholder="店铺名称" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="账号别名" width="150">
              <template #default="{ row }">
                <el-input v-model="row.account_alias" placeholder="可选" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                <el-select v-model="row.shop_type" size="small">
                  <el-option label="本地" value="local" />
                  <el-option label="全球" value="global" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="区域" width="100">
              <template #default="{ row }">
                <el-input v-model="row.shop_region" size="small" placeholder="SG/MY" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ $index }">
                <el-button size="small" type="danger" @click="removeShop($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button @click="addShop" style="margin-top: 10px" size="small">
            <el-icon><Plus /></el-icon>
            添加店铺
          </el-button>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showBatchDialog = false">取消</el-button>
        <el-button type="primary" @click="handleBatchCreate" :loading="accountsStore.loading">批量创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useAccountsStore } from '@/stores/accounts'
import { ElMessageBox, ElMessage } from 'element-plus'
import { 
  Search, Plus, Download, Refresh, Files,
  ShoppingCart, Box, Service, TrendCharts, Money, Grid
} from '@element-plus/icons-vue'

const accountsStore = useAccountsStore()

// 数据域标签映射
const domainLabels = {
  orders: '订单',
  products: '商品',
  services: '客服',
  analytics: '流量',
  finance: '财务',
  inventory: '库存'
}

// 筛选条件
const filters = reactive({
  platform: null,
  enabled: null,
  shop_type: null,
  search: ''
})

// 平台选项
const platformOptions = computed(() => accountsStore.platformList)

// 对话框状态
const showCreateDialog = ref(false)
const showBatchDialog = ref(false)
const activeTab = ref('basic')
const editingAccount = ref(null)
const importLoading = ref(false)

// 表单引用
const accountFormRef = ref(null)

// 账号表单
const accountForm = reactive({
  account_id: '',
  parent_account: '',
  platform: 'shopee',
  account_alias: '',
  store_name: '',
  shop_type: 'local',
  shop_region: '',
  shop_id: '',  // ⭐ v4.18.1新增
  username: '',
  password: '',
  login_url: '',
  email: '',
  phone: '',
  region: 'CN',
  currency: 'CNY',
  capabilities: {
    orders: true,
    products: true,
    services: true,
    analytics: true,
    finance: true,
    inventory: true
  },
  enabled: true,
  proxy_required: false,
  notes: ''
})

// 表单验证规则
// 表单验证规则（动态：编辑时密码可选，创建时必填）
const formRules = computed(() => ({
  account_id: [{ required: true, message: '请输入账号ID', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  store_name: [{ required: true, message: '请输入店铺名称', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: editingAccount.value 
    ? [] // 编辑时：密码可选（留空表示不修改）
    : [{ required: true, message: '请输入密码', trigger: 'blur' }] // 创建时：密码必填
}))

// 批量表单
const batchForm = reactive({
  parent_account: '',
  platform: 'shopee',
  username: '',
  password: '',
  shops: [
    { store_name: '', shop_type: 'local', shop_region: 'SG' }
  ]
})

// ==================== 方法 ====================

/**
 * 初始化
 * ⭐ v4.19.0修复：首次加载显示loading，后续支持后台刷新
 */
onMounted(async () => {
  // 首次加载显示loading
  await accountsStore.loadAccounts({}, true)
  await accountsStore.loadStats(false) // 统计数据后台加载，不显示loading
})

/**
 * 筛选变更
 */
function handleFilterChange() {
  accountsStore.setFilters(filters)
  accountsStore.loadAccounts()
}

/**
 * 搜索变更（防抖）
 */
let searchTimeout = null
function handleSearchChange() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    handleFilterChange()
  }, 500)
}

/**
 * 刷新
 * ⭐ v4.19.0修复：刷新时显示loading
 */
async function handleRefresh() {
  await accountsStore.loadAccounts({}, true)
  await accountsStore.loadStats(false) // 统计数据后台加载，不显示loading
  ElMessage.success('刷新成功')
}

/**
 * 导入
 */
async function handleImport() {
  importLoading.value = true
  try {
    await accountsStore.importFromLocal()
  } finally {
    importLoading.value = false
  }
}

/**
 * 编辑账号
 */
function handleEdit(account) {
  editingAccount.value = account
  Object.assign(accountForm, {
    account_id: account.account_id,
    parent_account: account.parent_account || '',
    platform: account.platform,
    account_alias: account.account_alias || '',
    store_name: account.store_name,
    shop_type: account.shop_type || 'local',
    shop_region: account.shop_region || '',
    shop_id: account.shop_id || '',  // ⭐ v4.18.1新增
    username: account.username,
    password: '', // 不显示密码
    login_url: account.login_url || '',
    email: account.email || '',
    phone: account.phone || '',
    region: account.region || 'CN',
    currency: account.currency || 'CNY',
    capabilities: { ...account.capabilities },
    enabled: account.enabled,
    proxy_required: account.proxy_required,
    notes: account.notes || ''
  })
  showCreateDialog.value = true
}

/**
 * 保存账号
 */
async function handleSaveAccount() {
  try {
    await accountFormRef.value.validate()
    
    const data = { ...accountForm }
    
    if (editingAccount.value) {
      // 更新（如果密码为空，不发送）
      if (!data.password) {
        delete data.password
      }
      await accountsStore.updateAccount(editingAccount.value.account_id, data)
    } else {
      // 创建
      await accountsStore.createAccount(data)
    }
    
    handleCancelEdit()
  } catch (error) {
    console.error('保存失败:', error)
  }
}

/**
 * 取消编辑
 */
function handleCancelEdit() {
  showCreateDialog.value = false
  editingAccount.value = null
  resetForm()
}

/**
 * 重置表单
 */
function resetForm() {
  Object.assign(accountForm, {
    account_id: '',
    parent_account: '',
    platform: 'shopee',
    account_alias: '',
    store_name: '',
    shop_type: 'local',
    shop_region: '',
    shop_id: '',  // ⭐ v4.18.1新增
    username: '',
    password: '',
    login_url: '',
    email: '',
    phone: '',
    region: 'CN',
    currency: 'CNY',
    capabilities: {
      orders: true,
      products: true,
      services: true,
      analytics: true,
      finance: true,
      inventory: true
    },
    enabled: true,
    proxy_required: false,
    notes: ''
  })
  activeTab.value = 'basic'
}

/**
 * 店铺类型变更
 */
function handleShopTypeChange(value) {
  // 全球店不支持客服数据
  if (value === 'global') {
    accountForm.capabilities.services = false
  } else {
    accountForm.capabilities.services = true
  }
}

/**
 * 删除账号
 */
async function handleDelete(account) {
  try {
    await ElMessageBox.confirm(
      `确定要删除账号 "${account.store_name}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await accountsStore.deleteAccount(account.account_id)
  } catch (error) {
    // 用户取消
  }
}

/**
 * 切换启用状态
 */
async function handleToggleEnabled(account) {
  account._updating = true
  try {
    await accountsStore.updateAccount(account.account_id, {
      enabled: account.enabled
    })
  } catch (error) {
    // 回滚
    account.enabled = !account.enabled
  } finally {
    account._updating = false
  }
}

/**
 * 添加店铺
 */
function addShop() {
  batchForm.shops.push({
    store_name: '',
    account_alias: '',
    shop_type: 'local',
    shop_region: ''
  })
}

/**
 * 删除店铺
 */
function removeShop(index) {
  batchForm.shops.splice(index, 1)
}

/**
 * 批量创建
 */
async function handleBatchCreate() {
  if (!batchForm.parent_account || !batchForm.username || !batchForm.password) {
    ElMessage.warning('请填写必填项')
    return
  }
  
  if (batchForm.shops.length === 0) {
    ElMessage.warning('请至少添加一个店铺')
    return
  }
  
  try {
    await accountsStore.batchCreate(batchForm)
    showBatchDialog.value = false
    // 重置表单
    Object.assign(batchForm, {
      parent_account: '',
      platform: 'shopee',
      username: '',
      password: '',
      shops: [{ store_name: '', shop_type: 'local', shop_region: 'SG' }]
    })
  } catch (error) {
    console.error('批量创建失败:', error)
  }
}

/**
 * 获取能力配置文本
 */
function getCapabilitiesText(capabilities) {
  const enabled = Object.entries(capabilities)
    .filter(([, value]) => value)
    .map(([key]) => domainLabels[key] || key)
  return `支持：${enabled.join('、')}`
}
</script>

<style scoped>
.account-management {
  padding: 20px;
}

.page-description {
  color: #909399;
  margin-bottom: 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-unit {
  color: #909399;
  font-size: 14px;
  margin-left: 5px;
}

.toolbar-card,
.table-card {
  margin-bottom: 20px;
}

.capabilities-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.capability-tag {
  margin: 2px 0;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 15px;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.capability-item .el-icon {
  font-size: 18px;
}
</style>
