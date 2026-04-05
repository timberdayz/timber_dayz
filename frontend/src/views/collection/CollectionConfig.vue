<template>
  <div class="collection-config">
    <div class="page-header">
      <div>
        <h2>采集配置管理</h2>
        <p class="page-subtitle">按日、周、月管理店铺账号采集配置，并检查覆盖缺口。</p>
      </div>
      <div class="header-actions">
        <el-button type="success" @click="showQuickSetupDialog">
          <el-icon><MagicStick /></el-icon>
          快速配置
        </el-button>
        <el-button type="primary" @click="showCreateDialog">
          <el-icon><Plus /></el-icon>
          新建配置
        </el-button>
      </div>
    </div>

    <el-card class="granularity-card">
      <div class="granularity-toolbar">
        <el-radio-group v-model="activeGranularity" size="large">
          <el-radio-button label="daily">日采集</el-radio-button>
          <el-radio-button label="weekly">周采集</el-radio-button>
          <el-radio-button label="monthly">月采集</el-radio-button>
        </el-radio-group>

        <div class="filter-bar">
          <el-select v-model="filters.platform" placeholder="平台筛选" clearable @change="reloadPageData">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>

          <el-select v-model="filters.is_active" placeholder="状态筛选" clearable @change="loadConfigs">
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>

          <el-button @click="reloadPageData">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="coverage-grid" v-loading="coverageLoading">
        <div class="coverage-item">
          <div class="coverage-label">店铺总数</div>
          <div class="coverage-value">{{ currentCoverageSummary.total }}</div>
        </div>
        <div class="coverage-item">
          <div class="coverage-label">当前粒度已覆盖</div>
          <div class="coverage-value coverage-ok">{{ currentCoverageSummary.covered }}</div>
        </div>
        <div class="coverage-item">
          <div class="coverage-label">当前粒度未覆盖</div>
          <div class="coverage-value coverage-warn">{{ currentCoverageSummary.missing }}</div>
        </div>
        <div class="coverage-item">
          <div class="coverage-label">全局部分覆盖</div>
          <div class="coverage-value coverage-mid">{{ currentCoverageSummary.partial }}</div>
        </div>
      </div>

      <el-alert
        v-if="missingCoverageItems.length > 0"
        type="warning"
        :closable="false"
        show-icon
        class="coverage-alert"
      >
        <template #title>
          当前{{ activeGranularityLabel }}仍有 {{ missingCoverageItems.length }} 个店铺账号未覆盖
        </template>
        <div class="missing-list">
          <div
            v-for="item in missingCoverageItems.slice(0, 8)"
            :key="`${item.platform}-${item.shop_account_id}`"
            class="missing-list-item"
          >
            <span>{{ item.platform }} / {{ item.main_account_name || item.main_account_id }} / {{ item.shop_account_name }}</span>
            <span class="missing-meta">{{ item.shop_region || '未标注区域' }}</span>
          </div>
        </div>
      </el-alert>
    </el-card>

    <el-card class="table-card">
      <template #header>
        <div class="table-header">
          <span>{{ activeGranularityLabel }}配置列表</span>
          <span class="table-summary">共 {{ filteredConfigs.length }} 条</span>
        </div>
      </template>

      <el-table v-loading="loading" :data="filteredConfigs" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="配置名称" min-width="180" />
        <el-table-column label="平台" width="110">
          <template #default="{ row }">
            <el-tag :type="getPlatformTagType(row.platform)">
              {{ row.platform }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="粒度" width="100">
          <template #default="{ row }">
            <el-tag type="info">{{ getGranularityLabel(row._resolvedGranularity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="店铺账号数" width="100">
          <template #default="{ row }">
            {{ row.account_ids?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="执行模式" width="100">
          <template #default="{ row }">
            <el-tag :type="row.execution_mode === 'headed' ? 'warning' : 'success'">
              {{ getExecutionModeLabel(row.execution_mode) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据域" min-width="220">
          <template #default="{ row }">
            <el-tag
              v-for="domain in row.data_domains"
              :key="domain"
              size="small"
              class="domain-tag"
            >
              {{ getDomainLabel(domain) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="定时" width="90">
          <template #default="{ row }">
            <el-tag :type="row.schedule_enabled ? 'success' : 'info'">
              {{ row.schedule_enabled ? '启用' : '关闭' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" @change="toggleActive(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="editConfig(row)">编辑</el-button>
            <el-button size="small" type="success" @click="runConfig(row)">执行</el-button>
            <el-popconfirm title="确定删除这条配置吗？" @confirm="deleteConfig(row)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? `编辑${activeGranularityLabel}配置` : `新建${activeGranularityLabel}配置`"
      width="920px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="form.name" placeholder="留空自动生成（平台-数据域-v版本号）">
            <template #append v-if="!isEdit">
              <el-button @click="generateConfigName">自动生成</el-button>
            </template>
          </el-input>
          <div class="form-hint" v-if="generatedName">建议名称：{{ generatedName }}</div>
        </el-form-item>

        <el-form-item label="平台" prop="platform">
          <el-select v-model="form.platform" placeholder="请选择平台" @change="onPlatformChange">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>

        <el-form-item label="店铺账号" prop="account_ids">
          <div class="account-selection-panel" v-loading="accountsLoading">
            <div class="account-selection-actions">
              <el-button size="small" @click="applyCapabilitiesFromSelectedAccounts">按店铺能力自动套用</el-button>
              <span class="selection-summary">已选 {{ form.account_ids.length }} 个店铺账号</span>
            </div>

            <div v-if="groupedAccountsForDialog.length === 0" class="empty-tip">
              当前平台暂无可选店铺账号
            </div>

            <div v-else class="grouped-accounts">
              <div
                v-for="group in groupedAccountsForDialog"
                :key="`${group.platform}-${group.main_account_id}`"
                class="main-account-group"
              >
                <div class="group-title">
                  {{ group.main_account_name || group.main_account_id }}
                  <span class="group-subtitle">{{ group.platform }}</span>
                </div>

                <div
                  v-for="region in group.regions"
                  :key="`${group.main_account_id}-${region.shop_region || 'unknown'}`"
                  class="region-group"
                >
                  <div class="region-title">{{ region.shop_region || '未标注区域' }}</div>
                  <el-checkbox-group v-model="form.account_ids" @change="applyCapabilitiesFromSelectedAccounts">
                    <el-checkbox
                      v-for="shop in region.shops"
                      :key="shop.id"
                      :label="shop.id"
                      class="shop-checkbox"
                    >
                      <span>{{ shop.name }}</span>
                      <span class="shop-meta">{{ shop.shop_type || '未分类' }}</span>
                    </el-checkbox>
                  </el-checkbox-group>
                </div>
              </div>
            </div>
          </div>
        </el-form-item>

        <el-form-item label="数据域" prop="data_domains">
          <el-checkbox-group v-model="form.data_domains">
            <el-checkbox
              v-for="option in availableDomainOptions"
              :key="option.value"
              :label="option.value"
            >
              {{ option.label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item
          v-for="domain in selectedSubtypeDomains"
          :key="`subtype-${domain}`"
          :label="`${getDomainLabel(domain)}子类型`"
        >
          <div class="sub-domains-group">
            <el-checkbox-group v-model="form.sub_domains[domain]">
              <el-checkbox
                v-for="option in getSubtypeOptions(domain)"
                :key="option.value"
                :label="option.value"
              >
                {{ option.label }}
              </el-checkbox>
            </el-checkbox-group>
            <el-button size="small" @click="selectAllSubDomains(domain)">全选</el-button>
          </div>
        </el-form-item>

        <el-form-item label="日期范围" prop="date_range_type">
          <el-select v-model="form.date_range_type" placeholder="请选择日期范围">
            <el-option
              v-for="option in currentGranularityDateOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div class="form-hint">当前配置会归入 {{ activeGranularityLabel }} 视图。</div>
        </el-form-item>

        <el-form-item v-if="form.date_range_type === 'custom'" label="自定义日期">
          <el-date-picker
            v-model="customDateRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>

        <el-form-item label="执行模式">
          <el-radio-group v-model="form.execution_mode">
            <el-radio-button label="headless">无头模式</el-radio-button>
            <el-radio-button label="headed">有头模式</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="启用定时">
          <el-switch v-model="form.schedule_enabled" />
        </el-form-item>

        <el-form-item v-if="form.schedule_enabled" label="执行时间">
          <el-select v-model="form.schedule_cron" placeholder="选择执行频率">
            <el-option label="每天 4 次（06:00/12:00/18:00/22:00）" value="0 6,12,18,22 * * *" />
            <el-option label="每天 00:00" value="0 0 * * *" />
            <el-option label="每天 06:00" value="0 6 * * *" />
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

    <el-dialog v-model="quickSetupVisible" title="快速配置" width="540px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="平台">
          <el-select v-model="quickSetup.platform" placeholder="请选择平台">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <div class="form-hint">
            将基于当前{{ activeGranularityLabel }}视图，为所选平台创建一条面向全部店铺账号的默认配置。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="quickSetupVisible = false">取消</el-button>
        <el-button type="primary" :loading="quickSetupSubmitting" @click="executeQuickSetup">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, Plus, Refresh } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'
import {
  buildAutoSelectedSubDomains,
  buildTimeSelectionPayload,
  getAvailableDomainOptions,
  getSubtypeOptions,
  getSelectedSubtypeDomains,
  normalizeConfigGranularity,
  normalizeDomainSubtypeMap,
  resolveAccountIdsForConfigRun
} from '@/constants/collection'

const router = useRouter()

const loading = ref(false)
const accountsLoading = ref(false)
const coverageLoading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const quickSetupVisible = ref(false)
const quickSetupSubmitting = ref(false)
const isEdit = ref(false)

const activeGranularity = ref('daily')
const configs = ref([])
const flatAccounts = ref([])
const groupedAccounts = ref([])
const coverage = ref({ summary: {}, items: [] })
const formRef = ref(null)
const generatedName = ref('')
const customDateRange = ref([])

const filters = reactive({
  platform: '',
  is_active: null
})

const form = reactive({
  id: null,
  name: '',
  platform: '',
  account_ids: [],
  data_domains: [],
  sub_domains: {},
  granularity: 'daily',
  date_range_type: 'yesterday',
  custom_date_start: null,
  custom_date_end: null,
  execution_mode: 'headless',
  schedule_enabled: false,
  schedule_cron: ''
})

const quickSetup = reactive({
  platform: ''
})

const formRules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  data_domains: [{ required: true, message: '请至少选择一个数据域', trigger: 'change' }],
  date_range_type: [{ required: true, message: '请选择日期范围', trigger: 'change' }]
}

const activeGranularityLabel = computed(() => getGranularityLabel(activeGranularity.value))

const availableDomainOptions = computed(() => getAvailableDomainOptions(form.platform))

const selectedSubtypeDomains = computed(() => getSelectedSubtypeDomains(form.data_domains))

const filteredConfigs = computed(() => {
  return (configs.value || []).filter((config) => {
    if ((config._resolvedGranularity || normalizeConfigGranularity(config)) !== activeGranularity.value) return false
    if (filters.platform && config.platform !== filters.platform) return false
    if (filters.is_active !== null && config.is_active !== filters.is_active) return false
    return true
  })
})

const currentCoverageKey = computed(() => `${activeGranularity.value}_covered`)

const coverageItems = computed(() => {
  return (coverage.value.items || []).filter((item) => {
    if (filters.platform && item.platform !== filters.platform) return false
    return true
  })
})

const missingCoverageItems = computed(() =>
  coverageItems.value.filter((item) => !item[currentCoverageKey.value])
)

const currentCoverageSummary = computed(() => {
  const total = coverageItems.value.length
  const missing = missingCoverageItems.value.length
  const covered = total - missing
  const partial = coverageItems.value.filter((item) => item.partial_covered).length
  return { total, covered, missing, partial }
})

const groupedAccountsForDialog = computed(() => {
  const platform = String(form.platform || '').toLowerCase()
  if (!platform) return []
  return groupedAccounts.value.filter((group) => String(group.platform || '').toLowerCase() === platform)
})

const selectedAccountRecords = computed(() => {
  const selectedIds = new Set(form.account_ids || [])
  return flatAccounts.value.filter((account) => selectedIds.has(account.id))
})

const currentGranularityDateOptions = computed(() => {
  if (activeGranularity.value === 'weekly') {
    return [
      { label: '最近7天', value: 'last_7_days' },
      { label: '按周自定义', value: 'custom' }
    ]
  }
  if (activeGranularity.value === 'monthly') {
    return [
      { label: '最近30天', value: 'last_30_days' },
      { label: '按月自定义', value: 'custom' }
    ]
  }
  return [
    { label: '今天', value: 'today' },
    { label: '昨天', value: 'yesterday' },
    { label: '按日自定义', value: 'custom' }
  ]
})

watch(activeGranularity, () => {
  if (!isEdit.value) {
    form.granularity = activeGranularity.value
    form.date_range_type = defaultDateTypeForGranularity(activeGranularity.value)
  }
})

watch(
  () => form.platform,
  (platform) => {
    const allowed = new Set(getAvailableDomainOptions(platform).map((option) => option.value))
    form.data_domains = (form.data_domains || []).filter((domain) => allowed.has(domain))
    for (const domain of Object.keys(form.sub_domains || {})) {
      if (!allowed.has(domain)) {
        delete form.sub_domains[domain]
      }
    }
  }
)

watch(
  () => [...form.data_domains],
  (domains) => {
    const allowedDomains = new Set(getSelectedSubtypeDomains(domains))
    for (const domain of Object.keys(form.sub_domains || {})) {
      if (!allowedDomains.has(domain)) {
        delete form.sub_domains[domain]
      }
    }
  }
)

function getGranularityLabel(value) {
  const labels = {
    daily: '日采集',
    weekly: '周采集',
    monthly: '月采集'
  }
  return labels[value] || value
}

function defaultDateTypeForGranularity(value) {
  if (value === 'weekly') return 'last_7_days'
  if (value === 'monthly') return 'last_30_days'
  return 'yesterday'
}

function getPlatformTagType(platform) {
  const types = { shopee: 'warning', tiktok: 'danger', miaoshou: 'success' }
  return types[String(platform || '').toLowerCase()] || 'info'
}

function getExecutionModeLabel(mode) {
  return mode === 'headed' ? '有头模式' : '无头模式'
}

function getDomainLabel(domain) {
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

function selectAllSubDomains(domain) {
  form.sub_domains[domain] = getSubtypeOptions(domain).map((option) => option.value)
}

async function loadConfigs() {
  loading.value = true
  try {
    const params = {}
    if (filters.platform) params.platform = filters.platform
    if (filters.is_active !== null) params.is_active = filters.is_active
    const response = await collectionApi.getConfigs(params)
    configs.value = (response || []).map((item) => ({
      ...item,
      _resolvedGranularity: normalizeConfigGranularity(item)
    }))
  } catch (error) {
    ElMessage.error(`加载配置失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

async function loadAccounts() {
  accountsLoading.value = true
  try {
    const platformParam = filters.platform ? { platform: filters.platform } : {}
    flatAccounts.value = await collectionApi.getAccounts(platformParam)
    groupedAccounts.value = await collectionApi.getGroupedAccounts(platformParam)
  } catch (error) {
    ElMessage.error(`加载店铺账号失败: ${error.message}`)
  } finally {
    accountsLoading.value = false
  }
}

async function loadCoverage() {
  coverageLoading.value = true
  try {
    const platformParam = filters.platform ? { platform: filters.platform } : {}
    coverage.value = await collectionApi.getConfigCoverage(platformParam)
  } catch (error) {
    ElMessage.error(`加载覆盖率失败: ${error.message}`)
    coverage.value = { summary: {}, items: [] }
  } finally {
    coverageLoading.value = false
  }
}

async function reloadPageData() {
  await Promise.all([loadConfigs(), loadAccounts(), loadCoverage()])
}

function resetForm() {
  Object.assign(form, {
    id: null,
    name: '',
    platform: '',
    account_ids: [],
    data_domains: [],
    sub_domains: {},
    granularity: activeGranularity.value,
    date_range_type: defaultDateTypeForGranularity(activeGranularity.value),
    custom_date_start: null,
    custom_date_end: null,
    execution_mode: 'headless',
    schedule_enabled: false,
    schedule_cron: ''
  })
  generatedName.value = ''
  customDateRange.value = []
}

function showCreateDialog() {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

function showQuickSetupDialog() {
  quickSetup.platform = filters.platform || ''
  quickSetupVisible.value = true
}

function onPlatformChange() {
  form.account_ids = []
  form.data_domains = []
  form.sub_domains = {}
}

function generateConfigName() {
  if (!form.platform || form.data_domains.length === 0) {
    generatedName.value = ''
    return
  }
  const domains = [...form.data_domains].sort().join('-')
  const baseName = `${form.platform}-${activeGranularity.value}-${domains}`
  const existingVersions = configs.value
    .filter((config) => String(config.name || '').startsWith(`${baseName}-v`))
    .map((config) => {
      const match = String(config.name || '').match(/-v(\d+)$/)
      return match ? Number(match[1]) : 0
    })
  const nextVersion = Math.max(0, ...existingVersions) + 1
  generatedName.value = `${baseName}-v${nextVersion}`
  if (!form.name) {
    form.name = generatedName.value
  }
}

function applyCapabilitiesFromSelectedAccounts() {
  const selected = selectedAccountRecords.value
  if (selected.length === 0) {
    return
  }

  const allowedByPlatform = new Set(availableDomainOptions.value.map((option) => option.value))
  const capabilitySets = selected.map((account) =>
    Object.entries(account.capabilities || {})
      .filter(([, enabled]) => enabled)
      .map(([domain]) => domain)
      .filter((domain) => allowedByPlatform.has(domain))
  )

  let domains = capabilitySets[0] || []
  for (const next of capabilitySets.slice(1)) {
    domains = domains.filter((domain) => next.includes(domain))
  }

  form.data_domains = [...domains]
  form.sub_domains = {
    ...normalizeDomainSubtypeMap(form.sub_domains),
    ...buildAutoSelectedSubDomains(domains)
  }

  if (!form.name) {
    generateConfigName()
  }
}

function editConfig(row) {
  isEdit.value = true
  activeGranularity.value = row._resolvedGranularity || normalizeConfigGranularity(row)
  Object.assign(form, {
    id: row.id,
    name: row.name,
    platform: row.platform,
    account_ids: row.account_ids || [],
    data_domains: row.data_domains || [],
    sub_domains: normalizeDomainSubtypeMap(row.sub_domains),
    granularity: row._resolvedGranularity || normalizeConfigGranularity(row),
    date_range_type: row.date_range_type || defaultDateTypeForGranularity(activeGranularity.value),
    custom_date_start: row.custom_date_start,
    custom_date_end: row.custom_date_end,
    execution_mode: row.execution_mode || 'headless',
    schedule_enabled: row.schedule_enabled || false,
    schedule_cron: row.schedule_cron || ''
  })
  customDateRange.value =
    row.custom_date_start && row.custom_date_end ? [row.custom_date_start, row.custom_date_end] : []
  dialogVisible.value = true
}

async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const payload = {
      ...form,
      granularity: activeGranularity.value,
      sub_domains: normalizeDomainSubtypeMap(form.sub_domains)
    }
    if (payload.date_range_type === 'custom' && customDateRange.value.length === 2) {
      payload.custom_date_start = customDateRange.value[0]
      payload.custom_date_end = customDateRange.value[1]
    }
    payload.time_selection = buildTimeSelectionPayload(payload.date_range_type, {
      customRange: customDateRange.value
    })
    delete payload.id

    if (isEdit.value) {
      await collectionApi.updateConfig(form.id, payload)
      ElMessage.success('配置更新成功')
    } else {
      await collectionApi.createConfig(payload)
      ElMessage.success('配置创建成功')
    }

    dialogVisible.value = false
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`操作失败: ${error.message}`)
  } finally {
    submitting.value = false
  }
}

async function deleteConfig(row) {
  try {
    await collectionApi.deleteConfig(row.id)
    ElMessage.success('配置删除成功')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`删除失败: ${error.message}`)
  }
}

async function toggleActive(row) {
  try {
    await collectionApi.updateConfig(row.id, { is_active: row.is_active })
    ElMessage.success(row.is_active ? '配置已启用' : '配置已禁用')
    await loadCoverage()
  } catch (error) {
    row.is_active = !row.is_active
    ElMessage.error(`操作失败: ${error.message}`)
  }
}

async function runConfig(row) {
  try {
    const accountIds = resolveAccountIdsForConfigRun(row, flatAccounts.value)
    if (accountIds.length === 0) {
      ElMessage.warning('该配置没有可用的活跃店铺账号，无法创建采集任务')
      return
    }

    const timeSelection = buildTimeSelectionPayload(row.date_range_type, {
      customRange:
        row.date_range_type === 'custom' && row.custom_date_start && row.custom_date_end
          ? [row.custom_date_start, row.custom_date_end]
          : []
    })

    const createdTaskIds = []
    for (const accountId of accountIds) {
      const task = await collectionApi.createTask({
        platform: row.platform,
        account_id: accountId,
        config_id: row.id,
        data_domains: row.data_domains,
        sub_domains: row.sub_domains || {},
        granularity: row._resolvedGranularity || normalizeConfigGranularity(row),
        time_selection: timeSelection,
        debug_mode: row.execution_mode === 'headed'
      })
      if (task?.task_id) {
        createdTaskIds.push(task.task_id)
      }
    }

    ElMessage.success(`已创建 ${accountIds.length} 个采集任务`)
    await router.push({
      name: 'CollectionTasks',
      query: {
        source: 'config',
        config_id: row.id,
        task_ids: createdTaskIds.join(',')
      }
    })
  } catch (error) {
    ElMessage.error(`执行失败: ${error.message}`)
  }
}

async function executeQuickSetup() {
  if (!quickSetup.platform) {
    ElMessage.warning('请先选择平台')
    return
  }

  quickSetupSubmitting.value = true
  try {
    const domains = getAvailableDomainOptions(quickSetup.platform).map((option) => option.value)
    await collectionApi.createConfig({
      name: '',
      platform: quickSetup.platform,
      account_ids: [],
      data_domains: domains,
      sub_domains: buildAutoSelectedSubDomains(domains),
      granularity: activeGranularity.value,
      date_range_type: defaultDateTypeForGranularity(activeGranularity.value),
      execution_mode: 'headless',
      schedule_enabled: false,
      retry_count: 3
    })
    quickSetupVisible.value = false
    ElMessage.success(`已创建${activeGranularityLabel.value}默认配置`)
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`快速配置失败: ${error.message}`)
  } finally {
    quickSetupSubmitting.value = false
  }
}

onMounted(() => {
  reloadPageData()
})
</script>

<style scoped>
.collection-config {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.page-subtitle {
  margin: 0;
  color: #909399;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.granularity-card,
.table-card {
  margin-bottom: 20px;
}

.granularity-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.coverage-item {
  padding: 16px;
  border-radius: 12px;
  background: #f7f8fa;
}

.coverage-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 6px;
}

.coverage-value {
  font-size: 24px;
  font-weight: 700;
}

.coverage-ok {
  color: #67c23a;
}

.coverage-warn {
  color: #e6a23c;
}

.coverage-mid {
  color: #409eff;
}

.coverage-alert {
  margin-top: 12px;
}

.missing-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.missing-list-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.missing-meta {
  color: #909399;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-summary {
  color: #909399;
  font-size: 13px;
}

.domain-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}

.account-selection-panel {
  width: 100%;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px;
  max-height: 360px;
  overflow: auto;
}

.account-selection-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.selection-summary,
.form-hint,
.group-subtitle,
.shop-meta {
  color: #909399;
  font-size: 12px;
}

.grouped-accounts {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.main-account-group {
  border: 1px solid #f0f2f5;
  border-radius: 10px;
  padding: 12px;
}

.group-title {
  font-weight: 600;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.region-group + .region-group {
  margin-top: 10px;
}

.region-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}

.shop-checkbox {
  display: flex;
  width: 100%;
  margin-right: 0;
  margin-bottom: 8px;
}

.sub-domains-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sub-domains-group :deep(.el-checkbox-group) {
  flex: 1;
}

.empty-tip {
  color: #909399;
}

@media (max-width: 900px) {
  .coverage-grid {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }

  .page-header,
  .granularity-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions,
  .filter-bar {
    flex-wrap: wrap;
  }
}
</style>
