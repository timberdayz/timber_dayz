<template>
  <div class="collection-config">
    <div class="page-header">
      <div>
        <h2>采集配置管理</h2>
        <p class="page-subtitle">按日、周、月管理单平台多店铺采集配置，并按店铺维度设置数据域。</p>
      </div>
      <div class="header-actions">
        <el-button type="success" @click="showQuickSetupDialog">
          <el-icon><MagicStick /></el-icon>
          快速配置
        </el-button>
        <el-button type="primary" data-testid="collection-config-create-button" @click="showCreateDialog">
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
          <el-select
            v-model="filters.platform"
            class="full-width-select"
            data-testid="collection-config-platform-filter"
            placeholder="平台筛选"
            clearable
            @change="handlePlatformFilterChange"
          >
            <el-option
              v-for="option in platformOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>

          <el-select
            v-model="filters.main_account_id"
            class="full-width-select"
            data-testid="collection-config-main-account-filter"
            placeholder="主账号筛选"
            clearable
            :disabled="!filters.platform"
            @change="reloadPageData"
          >
            <el-option
              v-for="option in filterMainAccountOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>

          <el-select
            v-model="filters.date_range_type"
            class="full-width-select"
            placeholder="日期范围"
            clearable
            @change="loadConfigs"
          >
            <el-option
              v-for="option in listDateRangeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>

          <el-select
            v-model="filters.execution_mode"
            class="full-width-select"
            placeholder="执行模式"
            clearable
            @change="loadConfigs"
          >
            <el-option label="无头模式" value="headless" />
            <el-option label="有头模式" value="headed" />
          </el-select>

          <el-select
            v-model="filters.schedule_enabled"
            class="full-width-select"
            placeholder="启用定时"
            clearable
            @change="loadConfigs"
          >
            <el-option label="启用定时" :value="true" />
            <el-option label="未启用" :value="false" />
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
          <div class="coverage-label">部分覆盖</div>
          <div class="coverage-value coverage-mid">{{ currentCoverageSummary.partial }}</div>
        </div>
      </div>
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
              {{ getPlatformLabel(row.platform) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="主账号" min-width="180">
          <template #default="{ row }">
            {{ row.main_account_name || row.main_account_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="粒度" width="100">
          <template #default="{ row }">
            <el-tag type="info">{{ getGranularityLabel(row._resolvedGranularity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="店铺数" width="100">
          <template #default="{ row }">
            {{ row.shop_scopes?.length || row.account_ids?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="执行模式" width="100">
          <template #default="{ row }">
            <el-tag :type="row.execution_mode === 'headed' ? 'warning' : 'success'">
              {{ getExecutionModeLabel(row.execution_mode) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据域摘要" min-width="220">
          <template #default="{ row }">
            <el-tag
              v-for="domain in row.data_domains || []"
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
      width="1100px"
      class="collection-config-editor-dialog"
      destroy-on-close
      data-testid="collection-config-dialog"
    >
      <el-form ref="formRef" class="editor-form" :model="form" :rules="formRules" label-width="110px">
        <div class="editor-layout">
          <div class="editor-main">
            <el-form-item label="配置名称" prop="name">
              <div data-testid="collection-config-name-input">
                <el-input v-model="form.name" placeholder="留空自动生成（平台-粒度-域集合-v版本号）">
                  <template #append v-if="!isEdit">
                    <el-button @click="generateConfigName">自动生成</el-button>
                  </template>
                </el-input>
              </div>
              <div class="form-hint" v-if="generatedName">建议名称：{{ generatedName }}</div>
            </el-form-item>

            <el-form-item label="平台" prop="platform">
              <el-select
                v-model="form.platform"
                class="full-width-select"
                data-testid="collection-config-platform-field"
                placeholder="请选择平台"
                @change="onPlatformChange"
              >
                <el-option
                  v-for="option in platformOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="主账号" prop="main_account_id">
              <el-select
                v-model="form.main_account_id"
                class="full-width-select"
                data-testid="collection-config-main-account-field"
                placeholder="请选择主账号"
                :disabled="!form.platform"
                @change="onMainAccountChange"
              >
                <el-option
                  v-for="option in dialogMainAccountOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
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
                <el-option label="每月 1 号 00:00" value="0 0 1 * *" />
              </el-select>
            </el-form-item>
          </div>

          <div class="editor-side">
            <div class="shop-scope-header">
              <div>
                <div class="scope-title">店铺维度配置</div>
                <div class="scope-subtitle">当前主账号下所有可用店铺必须参与配置，每个店铺至少选择 1 个数据域。</div>
              </div>
              <div class="scope-actions">
                <el-button size="small" @click="applyCapabilitiesToAllShopScopes">按店铺能力自动套用</el-button>
              </div>
            </div>

            <div v-if="!form.platform || !form.main_account_id" class="empty-tip">先选择平台和主账号，再加载店铺维度配置。</div>
            <div v-else-if="shopScopeRows.length === 0" class="empty-tip">当前主账号下暂无可用店铺账号。</div>

            <div v-else class="shop-scope-list" data-testid="collection-config-shop-scope-list">
              <el-card
                v-for="{ scope, account } in shopScopeRows"
                :key="scope.shop_account_id"
                class="shop-scope-card"
                shadow="never"
                :data-testid="`collection-config-shop-scope-card-${scope.shop_account_id}`"
              >
                <template #header>
                  <div class="shop-scope-card-header">
                    <div>
                      <div class="shop-scope-name">{{ account?.name || scope.shop_account_id }}</div>
                      <div class="shop-scope-meta">
                        {{ account?.main_account_name || account?.main_account_id || '未绑定主账号' }}
                        <span class="dot">·</span>
                        {{ account?.shop_region || '未标注区域' }}
                      </div>
                    </div>
                    <el-tag type="success">已纳入采集</el-tag>
                  </div>
                </template>

                <div class="scope-block">
                  <div class="scope-label">店铺能力</div>
                  <div class="capability-tags">
                    <el-tag
                      v-for="option in availableDomainOptions"
                      :key="`${scope.shop_account_id}-cap-${option.value}`"
                      :type="isScopeDomainAvailable(scope, option.value) ? 'success' : 'info'"
                      size="small"
                    >
                      {{ option.label }}
                    </el-tag>
                  </div>
                </div>

                <div class="scope-block">
                  <div class="scope-label">本店铺实际采集数据域</div>
                  <el-checkbox-group v-model="scope.data_domains">
                    <el-checkbox
                      v-for="option in availableDomainOptions"
                      :key="`${scope.shop_account_id}-${option.value}`"
                      :label="option.value"
                      :disabled="!isScopeDomainAvailable(scope, option.value)"
                    >
                      {{ option.label }}
                    </el-checkbox>
                  </el-checkbox-group>
                </div>

                <div
                  v-for="domain in getSelectedSubtypeDomains(scope.data_domains)"
                  :key="`${scope.shop_account_id}-sub-${domain}`"
                  class="scope-block"
                >
                  <div class="scope-label">{{ getDomainLabel(domain) }}子类型</div>
                  <div class="sub-domain-row">
                    <el-checkbox-group v-model="scope.sub_domains[domain]">
                      <el-checkbox
                        v-for="option in getSubtypeOptions(domain)"
                        :key="`${scope.shop_account_id}-${domain}-${option.value}`"
                        :label="option.value"
                      >
                        {{ option.label }}
                      </el-checkbox>
                    </el-checkbox-group>
                    <el-button size="small" @click="selectAllScopeSubDomains(scope, domain)">全选</el-button>
                  </div>
                </div>
              </el-card>
            </div>
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          data-testid="collection-config-save-button"
          :loading="submitting"
          @click="submitForm"
        >
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="quickSetupVisible" title="快速配置" width="520px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="平台">
          <el-select v-model="quickSetup.platform" class="full-width-select" placeholder="请选择平台" @change="onQuickSetupPlatformChange">
            <el-option
              v-for="option in platformOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="主账号">
          <el-select
            v-model="quickSetup.main_account_id"
            class="full-width-select"
            placeholder="请选择主账号"
            :disabled="!quickSetup.platform"
          >
            <el-option
              v-for="option in quickSetupMainAccountOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <div class="form-hint">
            将基于当前{{ activeGranularityLabel }}视图，为所选平台的全部可用店铺创建一条默认配置，并按店铺能力自动套用数据域。
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
  normalizeDomainSubtypeMap
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
const dialogAccounts = ref([])
const groupedAccounts = ref([])
const coverage = ref({ summary: {}, items: [] })
const formRef = ref(null)
const generatedName = ref('')
const customDateRange = ref([])

const filters = reactive({
  platform: '',
  main_account_id: '',
  date_range_type: '',
  execution_mode: '',
  schedule_enabled: null
})

const form = reactive({
  id: null,
  name: '',
  platform: '',
  main_account_id: '',
  shop_scopes: [],
  granularity: 'daily',
  date_range_type: 'yesterday',
  custom_date_start: null,
  custom_date_end: null,
  execution_mode: 'headless',
  schedule_enabled: false,
  schedule_cron: ''
})

const quickSetup = reactive({
  platform: '',
  main_account_id: ''
})

const formRules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  main_account_id: [{ required: true, message: '请选择主账号', trigger: 'change' }],
  date_range_type: [{ required: true, message: '请选择日期范围', trigger: 'change' }]
}

const activeGranularityLabel = computed(() => getGranularityLabel(activeGranularity.value))
const availableDomainOptions = computed(() => getAvailableDomainOptions(form.platform))
const platformOptions = computed(() => {
  const source = [...flatAccounts.value, ...dialogAccounts.value]
  const values = Array.from(
    new Set(source.map((account) => normalizePlatformCode(account.platform)).filter(Boolean))
  )
  return values
    .sort((left, right) => left.localeCompare(right))
    .map((value) => ({ value, label: getPlatformLabel(value) }))
})
const filterMainAccountOptions = computed(() => buildMainAccountOptions(flatAccounts.value, filters.platform))
const dialogMainAccountOptions = computed(() => buildMainAccountOptions(dialogAccounts.value, form.platform))
const quickSetupMainAccountOptions = computed(() => buildMainAccountOptions(flatAccounts.value, quickSetup.platform))
const listDateRangeOptions = computed(() => [
  { label: '今天', value: 'today' },
  { label: '昨天', value: 'yesterday' },
  { label: '最近 7 天', value: 'last_7_days' },
  { label: '最近 30 天', value: 'last_30_days' },
  { label: '自定义', value: 'custom' }
])

const filteredConfigs = computed(() =>
  (configs.value || []).filter((config) => {
    if ((config._resolvedGranularity || normalizeConfigGranularity(config)) !== activeGranularity.value) return false
    if (filters.platform && normalizePlatformCode(config.platform) !== normalizePlatformCode(filters.platform)) return false
    if (filters.main_account_id && config.main_account_id !== filters.main_account_id) return false
    if (filters.date_range_type && config.date_range_type !== filters.date_range_type) return false
    if (filters.execution_mode && config.execution_mode !== filters.execution_mode) return false
    if (filters.schedule_enabled !== null && config.schedule_enabled !== filters.schedule_enabled) return false
    return true
  })
)

const currentCoverageKey = computed(() => `${activeGranularity.value}_covered`)
const coverageItems = computed(() =>
  (coverage.value.items || []).filter((item) => {
    if (filters.platform && normalizePlatformCode(item.platform) !== normalizePlatformCode(filters.platform)) return false
    if (filters.main_account_id && item.main_account_id !== filters.main_account_id) return false
    return true
  })
)
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

const platformAccounts = computed(() => {
  const scopedAccounts = dialogAccounts.value.length ? dialogAccounts.value : flatAccounts.value
  const platform = String(form.platform || '').toLowerCase()
  const mainAccountId = String(form.main_account_id || '').trim()
  return scopedAccounts.filter(
    (account) =>
      String(account.platform || '').toLowerCase() === platform
      && (!mainAccountId || String(account.main_account_id || '') === mainAccountId)
      && account.status === 'active'
  )
})

const shopScopeRows = computed(() =>
  (form.shop_scopes || []).map((scope) => ({
    scope,
    account: platformAccounts.value.find((item) => item.id === scope.shop_account_id)
  }))
)

const currentGranularityDateOptions = computed(() => {
  if (activeGranularity.value === 'weekly') {
    return [
      { label: '最近 7 天', value: 'last_7_days' },
      { label: '按周自定义', value: 'custom' }
    ]
  }
  if (activeGranularity.value === 'monthly') {
    return [
      { label: '最近 30 天', value: 'last_30_days' },
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

function getGranularityLabel(value) {
  const labels = { daily: '日采集', weekly: '周采集', monthly: '月采集' }
  return labels[value] || value
}

function normalizePlatformCode(platform) {
  return String(platform || '').trim().toLowerCase()
}

function getPlatformLabel(platform) {
  const labels = {
    miaoshou: 'Miaoshou',
    shopee: 'Shopee',
    tiktok: 'TikTok'
  }
  return labels[normalizePlatformCode(platform)] || platform
}

function buildMainAccountOptions(accounts, platform) {
  const normalizedPlatform = normalizePlatformCode(platform)
  const options = new Map()

  for (const account of accounts || []) {
    if (normalizedPlatform && normalizePlatformCode(account.platform) !== normalizedPlatform) continue
    const mainAccountId = String(account.main_account_id || '').trim()
    if (!mainAccountId) continue
    if (options.has(mainAccountId)) continue
    options.set(mainAccountId, {
      value: mainAccountId,
      label: `${account.main_account_name || mainAccountId} / ${mainAccountId}`
    })
  }

  return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label))
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
    analytics: '流量分析',
    finance: '财务',
    services: '服务',
    inventory: '库存'
  }
  return labels[domain] || domain
}

function getAccountById(shopAccountId) {
  return platformAccounts.value.find((account) => account.id === shopAccountId) || null
}

function isScopeDomainAvailable(scope, domain) {
  const account = getAccountById(scope.shop_account_id)
  if (!account) return false
  return Boolean(account.capabilities?.[domain])
}

function buildScopeFromAccount(account, existingScope = null) {
  const allowedDomains = getAvailableDomainOptions(account.platform).map((option) => option.value)
  let dataDomains = []
  if (existingScope?.data_domains?.length) {
    dataDomains = existingScope.data_domains.filter(
      (domain) => allowedDomains.includes(domain) && Boolean(account.capabilities?.[domain])
    )
  } else {
    dataDomains = allowedDomains.filter((domain) => Boolean(account.capabilities?.[domain]))
  }

  const subDomains = normalizeDomainSubtypeMap(
    existingScope?.sub_domains || buildAutoSelectedSubDomains(dataDomains)
  )

  return {
    shop_account_id: account.id,
    data_domains: [...dataDomains],
    sub_domains: subDomains,
    enabled: true
  }
}

function buildDefaultShopScopes(platform, mainAccountId, existingScopes = []) {
  const sourceAccounts = dialogAccounts.value.length ? dialogAccounts.value : flatAccounts.value
  const accounts = sourceAccounts.filter(
    (account) =>
      normalizePlatformCode(account.platform) === normalizePlatformCode(platform)
      && String(account.main_account_id || '') === String(mainAccountId || '')
      && account.status === 'active'
  )
  const existingMap = Object.fromEntries((existingScopes || []).map((scope) => [scope.shop_account_id, scope]))
  return accounts.map((account) => buildScopeFromAccount(account, existingMap[account.id])).sort((a, b) => a.shop_account_id.localeCompare(b.shop_account_id))
}

function normalizeShopScopesForPayload() {
  const validIds = new Set(platformAccounts.value.map((account) => account.id))
  return (form.shop_scopes || [])
    .filter((scope) => validIds.has(scope.shop_account_id))
    .map((scope) => ({
    shop_account_id: scope.shop_account_id,
    data_domains: [...(scope.data_domains || [])],
    sub_domains: normalizeDomainSubtypeMap(scope.sub_domains),
    enabled: true
    }))
}

function validateShopScopes() {
  const validIds = new Set(platformAccounts.value.map((account) => account.id))
  const normalizedScopes = normalizeShopScopesForPayload()

  if (!normalizedScopes.length) {
    ElMessage.warning('当前平台暂无可保存的店铺配置')
    return false
  }
  if (normalizedScopes.length !== validIds.size) {
    ElMessage.warning('存在未覆盖或无效的店铺 scope，请重新选择平台后再保存')
    form.shop_scopes = buildDefaultShopScopes(form.platform, form.main_account_id, normalizedScopes)
    return false
  }

  const invalidScope = normalizedScopes.find((scope) => !(scope.data_domains || []).length)
  if (invalidScope) {
    const account = getAccountById(invalidScope.shop_account_id)
    ElMessage.warning(`${account?.name || invalidScope.shop_account_id} 至少需要选择一个数据域`)
    return false
  }
  return true
}

function selectAllScopeSubDomains(scope, domain) {
  scope.sub_domains[domain] = getSubtypeOptions(domain).map((option) => option.value)
}

function generateConfigName() {
  if (!form.platform || !form.main_account_id || !form.shop_scopes.length) {
    generatedName.value = ''
    return
  }
  const unionDomains = Array.from(
    new Set(form.shop_scopes.flatMap((scope) => scope.data_domains || []))
  ).sort()
  if (!unionDomains.length) {
    generatedName.value = ''
    return
  }
  const baseName = `${form.platform}-${form.main_account_id}-${activeGranularity.value}-${unionDomains.join('-')}`
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

function applyCapabilitiesToAllShopScopes() {
  form.shop_scopes = buildDefaultShopScopes(form.platform, form.main_account_id, form.shop_scopes)
  if (!form.name) {
    generateConfigName()
  }
}

async function loadConfigs() {
  loading.value = true
  try {
    const params = {}
    if (filters.platform) params.platform = filters.platform
    if (filters.main_account_id) params.main_account_id = filters.main_account_id
    if (filters.date_range_type) params.date_range_type = filters.date_range_type
    if (filters.execution_mode) params.execution_mode = filters.execution_mode
    if (filters.schedule_enabled !== null) params.schedule_enabled = filters.schedule_enabled
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
    flatAccounts.value = await collectionApi.getAccounts()
    groupedAccounts.value = await collectionApi.getGroupedAccounts()
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
    if (filters.main_account_id) platformParam.main_account_id = filters.main_account_id
    coverage.value = await collectionApi.getConfigCoverage(platformParam)
  } catch (error) {
    ElMessage.error(`加载覆盖情况失败: ${error.message}`)
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
    main_account_id: '',
    shop_scopes: [],
    granularity: activeGranularity.value,
    date_range_type: defaultDateTypeForGranularity(activeGranularity.value),
    custom_date_start: null,
    custom_date_end: null,
    execution_mode: 'headless',
    schedule_enabled: false,
    schedule_cron: ''
  })
  dialogAccounts.value = []
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
  quickSetup.main_account_id = filters.main_account_id || ''
  quickSetupVisible.value = true
}

function handlePlatformFilterChange() {
  filters.main_account_id = ''
  reloadPageData()
}

async function loadDialogAccounts(platform) {
  if (!platform) {
    dialogAccounts.value = []
    return
  }
  try {
    dialogAccounts.value = await collectionApi.getAccounts({ platform })
  } catch (error) {
    dialogAccounts.value = []
    ElMessage.error(`加载平台店铺失败: ${error.message}`)
  }
}

async function onPlatformChange() {
  if (!form.platform) {
    form.main_account_id = ''
    dialogAccounts.value = []
    form.shop_scopes = []
    return
  }
  form.main_account_id = ''
  form.shop_scopes = []
  await loadDialogAccounts(form.platform)
  generatedName.value = ''
}

function onMainAccountChange() {
  form.shop_scopes = []
  if (!form.platform || !form.main_account_id) return
  form.shop_scopes = buildDefaultShopScopes(form.platform, form.main_account_id)
  if (!isEdit.value) {
    form.name = ''
    generateConfigName()
  }
}

function onQuickSetupPlatformChange() {
  quickSetup.main_account_id = ''
}

async function editConfig(row) {
  isEdit.value = true
  activeGranularity.value = row._resolvedGranularity || normalizeConfigGranularity(row)
  const detail = await collectionApi.getConfig(row.id)
  await loadDialogAccounts(detail.platform)
  Object.assign(form, {
    id: detail.id,
    name: detail.name,
    platform: detail.platform,
    main_account_id: detail.main_account_id,
    shop_scopes: buildDefaultShopScopes(detail.platform, detail.main_account_id, detail.shop_scopes || []),
    granularity: detail._resolvedGranularity || normalizeConfigGranularity(detail),
    date_range_type: detail.date_range_type || defaultDateTypeForGranularity(activeGranularity.value),
    custom_date_start: detail.custom_date_start,
    custom_date_end: detail.custom_date_end,
    execution_mode: detail.execution_mode || 'headless',
    schedule_enabled: detail.schedule_enabled || false,
    schedule_cron: detail.schedule_cron || ''
  })
  customDateRange.value =
    detail.custom_date_start && detail.custom_date_end ? [detail.custom_date_start, detail.custom_date_end] : []
  dialogVisible.value = true
}

async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid || !validateShopScopes()) return

  submitting.value = true
  try {
    const payload = {
      name: form.name,
      platform: form.platform,
      main_account_id: form.main_account_id,
      shop_scopes: normalizeShopScopesForPayload(),
      granularity: activeGranularity.value,
      date_range_type: form.date_range_type,
      execution_mode: form.execution_mode,
      schedule_enabled: form.schedule_enabled,
      schedule_cron: form.schedule_enabled ? form.schedule_cron : null,
      retry_count: 3
    }
    if (payload.date_range_type === 'custom' && customDateRange.value.length === 2) {
      payload.custom_date_start = customDateRange.value[0]
      payload.custom_date_end = customDateRange.value[1]
    }
    payload.time_selection = buildTimeSelectionPayload(payload.date_range_type, {
      customRange: customDateRange.value
    })

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
    const tasks = await collectionApi.runConfig(row.id)
    const taskIds = (tasks || []).map((task) => task.task_id).filter(Boolean)
    if (!taskIds.length) {
      ElMessage.warning('该配置没有创建出可执行的采集任务')
      return
    }
    ElMessage.success(`已创建 ${taskIds.length} 个采集任务`)
    await router.push({
      name: 'CollectionTasks',
      query: {
        source: 'config',
        config_id: row.id,
        task_ids: taskIds.join(',')
      }
    })
  } catch (error) {
    ElMessage.error(`执行失败: ${error.message}`)
  }
}

async function executeQuickSetup() {
  if (!quickSetup.platform || !quickSetup.main_account_id) {
    ElMessage.warning('请先选择平台和主账号')
    return
  }

  quickSetupSubmitting.value = true
  try {
    const shopScopes = buildDefaultShopScopes(quickSetup.platform, quickSetup.main_account_id)
    await collectionApi.createConfig({
      name: '',
      platform: quickSetup.platform,
      main_account_id: quickSetup.main_account_id,
      shop_scopes: shopScopes,
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

.header-actions,
.filter-bar,
.scope-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
}

.coverage-item {
  padding: 16px;
  border-radius: 12px;
  background: #f7f8fa;
}

.coverage-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.coverage-value {
  font-size: 28px;
  font-weight: 600;
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

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-summary,
.form-hint,
.scope-subtitle,
.shop-scope-meta {
  color: #909399;
  font-size: 12px;
}

.domain-tag {
  margin-right: 6px;
  margin-bottom: 6px;
}

.full-width-select {
  width: 100%;
}

.editor-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 20px;
  align-items: stretch;
  min-height: 0;
  height: 100%;
}

.editor-form,
.editor-main,
.editor-side {
  min-width: 0;
}

.editor-form,
.editor-side {
  height: 100%;
}

.editor-side {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.shop-scope-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.scope-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.shop-scope-list {
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: 12px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.shop-scope-card {
  border: 1px solid #ebeef5;
}

.shop-scope-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.shop-scope-name {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.scope-block {
  margin-bottom: 14px;
}

.scope-label {
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
  font-weight: 600;
}

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sub-domain-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.empty-tip {
  padding: 20px;
  text-align: center;
  color: #909399;
  background: #f7f8fa;
  border-radius: 12px;
}

.dot {
  margin: 0 6px;
}

:deep(.collection-config-editor-dialog) {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
  margin-top: 16px;
  margin-bottom: 16px;
}

:deep(.collection-config-editor-dialog .el-dialog__header) {
  flex-shrink: 0;
}

:deep(.collection-config-editor-dialog .el-dialog__body) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

:deep(.collection-config-editor-dialog .el-dialog__footer) {
  flex-shrink: 0;
}

@media (max-width: 960px) {
  .editor-layout {
    grid-template-columns: 1fr;
  }
}
</style>
