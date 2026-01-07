<template>
  <div class="collection-config">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>采集配置管理</h2>
      <div class="header-actions">
        <el-button type="success" @click="showQuickSetupDialog">
          <el-icon><MagicStick /></el-icon>
          快速配置
        </el-button>
        <!-- 旧的录制组件功能已移至"组件录制工具"页面 -->
        <el-button type="primary" @click="showCreateDialog">
          <el-icon><Plus /></el-icon>
          新建配置
        </el-button>
      </div>
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
          <el-input 
            v-model="form.name" 
            placeholder="留空自动生成（格式：平台-数据域-v版本号）"
          >
            <template #append v-if="!isEdit">
              <el-button @click="generateConfigName">自动生成</el-button>
            </template>
          </el-input>
          <div class="form-hint" v-if="generatedName">
            建议名称: {{ generatedName }}
          </div>
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
          <div class="sub-domains-group">
            <el-checkbox-group v-model="form.sub_domains">
              <el-checkbox label="agent">人工客服</el-checkbox>
              <el-checkbox label="ai_assistant">智能客服</el-checkbox>
            </el-checkbox-group>
            <el-button size="small" @click="selectAllSubDomains">全选</el-button>
          </div>
          <div class="form-hint">可多选，执行时将按顺序采集</div>
        </el-form-item>

        <el-form-item label="日期范围" prop="date_range_type">
          <el-select 
            v-model="form.date_range_type" 
            placeholder="请选择日期范围"
          >
            <el-option label="今天" value="today" />
            <el-option label="昨天" value="yesterday" />
            <el-option 
              :label="getPlatformDateLabel('last_7_days')" 
              value="last_7_days" 
            />
            <el-option 
              :label="getPlatformDateLabel('last_30_days')" 
              value="last_30_days" 
            />
            <el-option label="自定义" value="custom" />
          </el-select>
          <div class="form-hint">
            {{ getDateRangeHint() }}
          </div>
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

    <!-- 快速配置对话框（v4.7.0）-->
    <el-dialog 
      v-model="quickSetupVisible" 
      title="快速配置向导"
      width="600px"
      destroy-on-close
    >
      <el-steps :active="quickSetupStep" align-center>
        <el-step title="选择平台" />
        <el-step title="选择策略" />
        <el-step title="确认并创建" />
      </el-steps>
      
      <div class="quick-setup-content">
        <!-- 步骤1: 选择平台 -->
        <div v-if="quickSetupStep === 0" class="setup-step">
          <el-form label-width="100px">
            <el-form-item label="平台">
              <el-radio-group v-model="quickSetup.platform">
                <el-radio label="shopee">Shopee</el-radio>
                <el-radio label="tiktok">TikTok</el-radio>
                <el-radio label="miaoshou">妙手ERP</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>
        
        <!-- 步骤2: 选择策略 -->
        <div v-if="quickSetupStep === 1" class="setup-step">
          <el-form label-width="100px">
            <el-form-item label="配置策略">
              <el-radio-group v-model="quickSetup.strategy">
                <el-radio label="standard">标准配置（日度+周度+月度）</el-radio>
                <el-radio label="custom">自定义选择</el-radio>
              </el-radio-group>
            </el-form-item>
            
            <el-form-item 
              v-if="quickSetup.strategy === 'custom'" 
              label="选择粒度"
            >
              <el-checkbox-group v-model="quickSetup.granularities">
                <el-checkbox label="daily">日度采集（每天4次）</el-checkbox>
                <el-checkbox label="weekly">周度采集（每周一 05:00）</el-checkbox>
                <el-checkbox label="monthly">月度采集（每月1号 05:00）</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </el-form>
        </div>
        
        <!-- 步骤3: 确认 -->
        <div v-if="quickSetupStep === 2" class="setup-step">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="平台">{{ quickSetup.platform }}</el-descriptions-item>
            <el-descriptions-item label="数据域">全部6个</el-descriptions-item>
            <el-descriptions-item label="账号">该平台所有活跃账号</el-descriptions-item>
            <el-descriptions-item label="配置数量">{{ getQuickSetupConfigCount() }}</el-descriptions-item>
            <el-descriptions-item label="预计任务">{{ getQuickSetupTaskCount() }}</el-descriptions-item>
          </el-descriptions>
          
          <el-alert 
            type="info" 
            :closable="false" 
            style="margin-top: 16px"
          >
            <template #title>
              将创建以下配置：
            </template>
            <ul>
              <li v-for="config in getQuickSetupConfigs()" :key="config.name">
                {{ config.name }} - {{ config.description }}
              </li>
            </ul>
          </el-alert>
        </div>
      </div>
      
      <template #footer>
        <el-button v-if="quickSetupStep > 0" @click="quickSetupStep--">上一步</el-button>
        <el-button @click="quickSetupVisible = false">取消</el-button>
        <el-button 
          v-if="quickSetupStep < 2" 
          type="primary" 
          @click="quickSetupStep++"
          :disabled="!canGoNextStep()"
        >
          下一步
        </el-button>
        <el-button 
          v-if="quickSetupStep === 2" 
          type="primary" 
          :loading="quickSetupSubmitting"
          @click="executeQuickSetup"
        >
          创建配置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, MagicStick, CopyDocument } from '@element-plus/icons-vue'
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

// 表单数据（v4.7.0）
const form = reactive({
  id: null,
  name: '',
  platform: '',
  account_ids: [],
  data_domains: [],
  sub_domains: [],  // v4.7.0: 改为数组
  granularity: 'daily',  // 保留用于后端推断
  date_range_type: 'yesterday',
  custom_date_start: null,
  custom_date_end: null,
  schedule_enabled: false,
  schedule_cron: ''
})

const customDateRange = ref([])
const generatedName = ref('')  // v4.7.0: 自动生成的配置名

// v4.7.0: 快速配置状态
const quickSetupVisible = ref(false)
const quickSetupStep = ref(0)
const quickSetupSubmitting = ref(false)
const quickSetup = reactive({
  platform: '',
  strategy: 'standard',  // standard/custom
  granularities: ['daily', 'weekly', 'monthly']
})

// 表单验证规则（v4.7.0: name可选）
const formRules = {
  name: [{ required: false, message: '留空自动生成', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  account_ids: [{ required: false, message: '留空表示所有活跃账号', trigger: 'change' }],
  data_domains: [{ required: true, message: '请选择至少一个数据域', trigger: 'change' }],
  date_range_type: [{ required: true, message: '请选择日期范围', trigger: 'change' }]
}

// 计算属性
const filteredAccounts = computed(() => {
  if (!form.platform) return accounts.value
  return accounts.value.filter(acc => 
    acc.platform?.toLowerCase() === form.platform.toLowerCase()
  )
})

// v4.7.0: 监听平台和数据域变化，自动生成配置名
watch([() => form.platform, () => form.data_domains], () => {
  if (!isEdit.value && form.platform && form.data_domains.length > 0) {
    generateConfigName()
  }
}, { deep: true })

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
    sub_domains: row.sub_domains || [],  // v4.7.0: 数组
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
    sub_domains: [],  // v4.7.0: 数组
    granularity: 'daily',
    date_range_type: 'yesterday',
    custom_date_start: null,
    custom_date_end: null,
    schedule_enabled: false,
    schedule_cron: ''
  })
  customDateRange.value = []
  generatedName.value = ''  // v4.7.0: 清空生成的名称
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

// ========== v4.7.0: 新功能方法 ==========

// 功能1: 配置名自动生成
const generateConfigName = () => {
  if (!form.platform || form.data_domains.length === 0) {
    generatedName.value = ''
    return
  }
  
  const domains = [...form.data_domains].sort().join('-')
  const baseName = `${form.platform}-${domains}`
  
  // 查找现有版本号
  const existingVersions = configs.value
    .filter(c => c.name.startsWith(baseName + '-v'))
    .map(c => {
      const match = c.name.match(/-v(\d+)$/)
      return match ? parseInt(match[1]) : 0
    })
  
  const nextVersion = Math.max(0, ...existingVersions) + 1
  generatedName.value = `${baseName}-v${nextVersion}`
  
  // 如果name字段为空，自动填充
  if (!form.name) {
    form.name = generatedName.value
  }
}

// 功能2: 平台对齐的日期标签
const getPlatformDateLabel = (dateType) => {
  const labels = {
    'last_7_days': {
      'shopee': '最近7天',
      'tiktok': '最近7天',
      'miaoshou': '最近7天'
    },
    'last_30_days': {
      'shopee': '最近30天',
      'tiktok': '最近28天',
      'miaoshou': '最近30天'
    }
  }
  return labels[dateType]?.[form.platform] || labels[dateType]?.['shopee'] || dateType
}

const getDateRangeHint = () => {
  if (!form.platform) return '请先选择平台'
  
  const hints = {
    'shopee': '与Shopee平台日期控件对齐：今天/昨天/7天/30天',
    'tiktok': '与TikTok平台日期控件对齐：今天/昨天/7天/28天',
    'miaoshou': '与妙手ERP日期控件对齐：今天/昨天/7天/30天'
  }
  return hints[form.platform] || ''
}

// 功能3: 服务子域全选
const selectAllSubDomains = () => {
  form.sub_domains = ['agent', 'ai_assistant']
}

// 功能4: 快速配置向导
const showQuickSetupDialog = () => {
  quickSetupStep.value = 0
  quickSetup.platform = ''
  quickSetup.strategy = 'standard'
  quickSetup.granularities = ['daily', 'weekly', 'monthly']
  quickSetupVisible.value = true
}

const canGoNextStep = () => {
  if (quickSetupStep.value === 0) {
    return quickSetup.platform !== ''
  }
  if (quickSetupStep.value === 1) {
    return quickSetup.strategy === 'standard' || quickSetup.granularities.length > 0
  }
  return true
}

const getQuickSetupConfigCount = () => {
  if (quickSetup.strategy === 'standard') {
    return 3  // 日度+周度+月度
  }
  return quickSetup.granularities.length
}

const getQuickSetupTaskCount = () => {
  const accountCount = accounts.value.filter(
    acc => acc.platform === quickSetup.platform
  ).length
  return accountCount * getQuickSetupConfigCount()
}

const getQuickSetupConfigs = () => {
  const configs = []
  const granularities = quickSetup.strategy === 'standard' 
    ? ['daily', 'weekly', 'monthly']
    : quickSetup.granularities
  
  const schedules = {
    'daily': { cron: '0 6,12,18,22 * * *', desc: '每天4次（06:00/12:00/18:00/22:00）' },
    'weekly': { cron: '0 5 * * 1', desc: '每周一 05:00' },
    'monthly': { cron: '0 5 1 * *', desc: '每月1号 05:00' }
  }
  
  granularities.forEach(g => {
    configs.push({
      name: `${quickSetup.platform}-all-${g}`,
      description: `${quickSetup.platform}平台全部数据域${g === 'daily' ? '日' : g === 'weekly' ? '周' : '月'}度采集 - ${schedules[g].desc}`
    })
  })
  
  return configs
}

const executeQuickSetup = async () => {
  quickSetupSubmitting.value = true
  try {
    const granularities = quickSetup.strategy === 'standard' 
      ? ['daily', 'weekly', 'monthly']
      : quickSetup.granularities
    
    const schedules = {
      'daily': { cron: '0 6,12,18,22 * * *', dateType: 'today' },
      'weekly': { cron: '0 5 * * 1', dateType: 'last_7_days' },
      'monthly': { cron: '0 5 1 * *', dateType: 'last_30_days' }
    }
    
    const allDomains = ['orders', 'products', 'services', 'analytics', 'finance', 'inventory']
    
    for (const gran of granularities) {
      const configData = {
        name: null,  // 自动生成
        platform: quickSetup.platform,
        account_ids: [],  // 所有活跃账号
        data_domains: allDomains,
        sub_domains: ['agent', 'ai_assistant'],  // 服务域全选
        granularity: gran,
        date_range_type: schedules[gran].dateType,
        schedule_enabled: true,
        schedule_cron: schedules[gran].cron,
        retry_count: 3
      }
      
      await collectionApi.createConfig(configData)
    }
    
    ElMessage.success(`成功创建 ${granularities.length} 个配置！`)
    quickSetupVisible.value = false
    loadConfigs()
  } catch (error) {
    ElMessage.error('快速配置失败: ' + error.message)
  } finally {
    quickSetupSubmitting.value = false
  }
}

// 功能5: 录制工具入口
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

/* v4.7.0: 新功能样式 */
.header-actions {
  display: flex;
  gap: 8px;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

.sub-domains-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sub-domains-group .el-checkbox-group {
  flex: 1;
}

.quick-setup-content {
  padding: 24px 0;
  min-height: 200px;
}

.setup-step {
  padding: 16px;
}

:deep(.el-steps) {
  margin-bottom: 20px;
}

:deep(.el-descriptions) {
  margin-bottom: 16px;
}
</style>

