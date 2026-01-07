<template>
  <div class="collection-config">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>采集配置管理</h2>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        新建配置
      </el-button>
    </div>

    <!-- 筛选工具栏 -->
    <div class="filter-bar">
      <el-select 
        v-model="filters.platform" 
        placeholder="平台筛选" 
        clearable
        @change="loadConfigs"
      >
        <el-option label="Shopee" value="shopee" />
        <el-option label="TikTok" value="tiktok" />
        <el-option label="妙手ERP" value="miaoshou" />
      </el-select>
      
      <el-select 
        v-model="filters.is_active" 
        placeholder="状态筛选" 
        clearable
        @change="loadConfigs"
      >
        <el-option label="已启用" :value="true" />
        <el-option label="已禁用" :value="false" />
      </el-select>
      
      <el-button @click="loadConfigs">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 配置列表 -->
    <el-table 
      v-loading="loading" 
      :data="configs" 
      stripe
      style="width: 100%"
    >
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="配置名称" min-width="150" />
      <el-table-column prop="platform" label="平台" width="100">
        <template #default="{ row }">
          <el-tag :type="getPlatformTagType(row.platform)">
            {{ row.platform }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="账号数" width="80">
        <template #default="{ row }">
          {{ row.account_ids?.length || 0 }}
        </template>
      </el-table-column>
      <el-table-column label="数据域" min-width="180">
        <template #default="{ row }">
          <el-tag 
            v-for="domain in row.data_domains" 
            :key="domain"
            size="small"
            style="margin-right: 4px"
          >
            {{ getDomainLabel(domain) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="定时状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.schedule_enabled ? 'success' : 'info'">
            {{ row.schedule_enabled ? '已启用' : '未启用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="80">
        <template #default="{ row }">
          <el-switch 
            v-model="row.is_active" 
            @change="toggleActive(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="editConfig(row)">
            编辑
          </el-button>
          <el-button size="small" type="success" @click="runConfig(row)">
            执行
          </el-button>
          <el-popconfirm
            title="确定要删除此配置吗？"
            @confirm="deleteConfig(row)"
          >
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="isEdit ? '编辑配置' : '新建配置'"
      width="700px"
      destroy-on-close
    >
      <el-form 
        ref="formRef"
        :model="form" 
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入配置名称" />
        </el-form-item>

        <el-form-item label="平台" prop="platform">
          <el-select 
            v-model="form.platform" 
            placeholder="请选择平台"
            @change="onPlatformChange"
          >
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>

        <el-form-item label="选择账号" prop="account_ids">
          <el-select 
            v-model="form.account_ids" 
            multiple
            placeholder="请选择账号"
            :loading="accountsLoading"
          >
            <el-option 
              v-for="account in filteredAccounts" 
              :key="account.id"
              :label="account.name"
              :value="account.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="数据域" prop="data_domains">
          <el-checkbox-group v-model="form.data_domains">
            <el-checkbox label="orders">订单</el-checkbox>
            <el-checkbox label="products">产品</el-checkbox>
            <el-checkbox label="analytics">流量分析</el-checkbox>
            <el-checkbox label="finance">财务</el-checkbox>
            <el-checkbox label="services">服务</el-checkbox>
            <el-checkbox label="inventory">库存</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item 
          v-if="form.data_domains.includes('services')" 
          label="服务子域"
        >
          <el-select v-model="form.sub_domain" placeholder="请选择子域">
            <el-option label="智能客服" value="ai_assistant" />
            <el-option label="人工客服" value="agent" />
          </el-select>
        </el-form-item>

        <el-form-item label="数据粒度">
          <el-radio-group v-model="form.granularity">
            <el-radio label="daily">日报</el-radio>
            <el-radio label="weekly">周报</el-radio>
            <el-radio label="monthly">月报</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="日期范围">
          <el-select v-model="form.date_range_type">
            <el-option label="今天" value="today" />
            <el-option label="昨天" value="yesterday" />
            <el-option label="最近7天" value="last_7_days" />
            <el-option label="最近30天" value="last_30_days" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>

        <el-form-item 
          v-if="form.date_range_type === 'custom'" 
          label="自定义日期"
        >
          <el-date-picker
            v-model="customDateRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>

        <el-divider content-position="left">定时配置</el-divider>

        <el-form-item label="启用定时">
          <el-switch v-model="form.schedule_enabled" />
        </el-form-item>

        <el-form-item v-if="form.schedule_enabled" label="执行时间">
          <el-select v-model="form.schedule_cron" placeholder="选择执行频率">
            <el-option label="每天 00:00" value="0 0 * * *" />
            <el-option label="每天 06:00" value="0 6 * * *" />
            <el-option label="每天 12:00" value="0 12 * * *" />
            <el-option label="每天 18:00" value="0 18 * * *" />
            <el-option label="每周一 00:00" value="0 0 * * 1" />
            <el-option label="每月1号 00:00" value="0 0 1 * *" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'

// 状态
const loading = ref(false)
const accountsLoading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const configs = ref([])
const accounts = ref([])
const formRef = ref(null)

// 筛选条件
const filters = reactive({
  platform: '',
  is_active: null
})

// 表单数据
const form = reactive({
  id: null,
  name: '',
  platform: '',
  account_ids: [],
  data_domains: [],
  sub_domain: '',
  granularity: 'daily',
  date_range_type: 'yesterday',
  custom_date_start: null,
  custom_date_end: null,
  schedule_enabled: false,
  schedule_cron: ''
})

const customDateRange = ref([])

// 表单验证规则
const formRules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  account_ids: [{ required: true, message: '请选择至少一个账号', trigger: 'change' }],
  data_domains: [{ required: true, message: '请选择至少一个数据域', trigger: 'change' }]
}

// 计算属性
const filteredAccounts = computed(() => {
  if (!form.platform) return accounts.value
  return accounts.value.filter(acc => 
    acc.platform?.toLowerCase() === form.platform.toLowerCase()
  )
})

// 方法
const loadConfigs = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.platform) params.platform = filters.platform
    if (filters.is_active !== null) params.is_active = filters.is_active
    
    configs.value = await collectionApi.getConfigs(params)
  } catch (error) {
    ElMessage.error('加载配置失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const loadAccounts = async () => {
  accountsLoading.value = true
  try {
    accounts.value = await collectionApi.getAccounts()
  } catch (error) {
    ElMessage.error('加载账号失败: ' + error.message)
  } finally {
    accountsLoading.value = false
  }
}

const showCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const editConfig = (row) => {
  isEdit.value = true
  Object.assign(form, {
    id: row.id,
    name: row.name,
    platform: row.platform,
    account_ids: row.account_ids || [],
    data_domains: row.data_domains || [],
    sub_domain: row.sub_domain || '',
    granularity: row.granularity || 'daily',
    date_range_type: row.date_range_type || 'yesterday',
    custom_date_start: row.custom_date_start,
    custom_date_end: row.custom_date_end,
    schedule_enabled: row.schedule_enabled || false,
    schedule_cron: row.schedule_cron || ''
  })
  
  if (row.custom_date_start && row.custom_date_end) {
    customDateRange.value = [row.custom_date_start, row.custom_date_end]
  }
  
  dialogVisible.value = true
}

const resetForm = () => {
  Object.assign(form, {
    id: null,
    name: '',
    platform: '',
    account_ids: [],
    data_domains: [],
    sub_domain: '',
    granularity: 'daily',
    date_range_type: 'yesterday',
    custom_date_start: null,
    custom_date_end: null,
    schedule_enabled: false,
    schedule_cron: ''
  })
  customDateRange.value = []
}

const submitForm = async () => {
  if (!formRef.value) return
  
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  
  submitting.value = true
  try {
    const data = { ...form }
    
    // 处理自定义日期
    if (data.date_range_type === 'custom' && customDateRange.value?.length === 2) {
      data.custom_date_start = customDateRange.value[0]
      data.custom_date_end = customDateRange.value[1]
    }
    
    delete data.id
    
    if (isEdit.value) {
      await collectionApi.updateConfig(form.id, data)
      ElMessage.success('配置更新成功')
    } else {
      await collectionApi.createConfig(data)
      ElMessage.success('配置创建成功')
    }
    
    dialogVisible.value = false
    loadConfigs()
  } catch (error) {
    ElMessage.error('操作失败: ' + error.message)
  } finally {
    submitting.value = false
  }
}

const deleteConfig = async (row) => {
  try {
    await collectionApi.deleteConfig(row.id)
    ElMessage.success('配置删除成功')
    loadConfigs()
  } catch (error) {
    ElMessage.error('删除失败: ' + error.message)
  }
}

const toggleActive = async (row) => {
  try {
    await collectionApi.updateConfig(row.id, { is_active: row.is_active })
    ElMessage.success(row.is_active ? '配置已启用' : '配置已禁用')
  } catch (error) {
    row.is_active = !row.is_active // 回滚
    ElMessage.error('操作失败: ' + error.message)
  }
}

const runConfig = async (row) => {
  try {
    // 为每个账号创建任务
    for (const accountId of row.account_ids) {
      await collectionApi.createTask({
        platform: row.platform,
        account_id: accountId,
        data_domains: row.data_domains,
        sub_domain: row.sub_domain,
        granularity: row.granularity,
        date_range: {
          type: row.date_range_type,
          start_date: row.custom_date_start,
          end_date: row.custom_date_end
        }
      })
    }
    ElMessage.success(`已创建 ${row.account_ids.length} 个采集任务`)
  } catch (error) {
    ElMessage.error('执行失败: ' + error.message)
  }
}

const onPlatformChange = () => {
  form.account_ids = [] // 清空已选账号
}

const getPlatformTagType = (platform) => {
  const types = {
    shopee: 'warning',
    tiktok: 'danger',
    miaoshou: 'success'
  }
  return types[platform?.toLowerCase()] || 'info'
}

const getDomainLabel = (domain) => {
  const labels = {
    orders: '订单',
    products: '产品',
    analytics: '流量',
    finance: '财务',
    services: '服务',
    inventory: '库存'
  }
  return labels[domain] || domain
}

// 生命周期
onMounted(() => {
  loadConfigs()
  loadAccounts()
})
</script>

<style scoped>
.collection-config {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.filter-bar .el-select {
  width: 150px;
}

.el-table {
  border-radius: 8px;
}

:deep(.el-dialog__body) {
  padding-top: 10px;
}

:deep(.el-divider__text) {
  font-size: 14px;
  color: #606266;
}
</style>

