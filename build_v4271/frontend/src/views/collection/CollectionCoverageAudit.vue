<template>
  <div class="collection-coverage-audit erp-page-container erp-page--admin">
    <PageHeader
      title="采集覆盖率巡检"
      subtitle="查看店铺账号在日、周、月三个粒度下的覆盖状态，并对缺口执行批量补配。"
      family="admin"
    />

    <div class="summary-grid" v-loading="loading">
      <div class="summary-card">
        <div class="summary-label">店铺总数</div>
        <div class="summary-value">{{ filteredSummary.total }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">缺日</div>
        <div class="summary-value danger">{{ filteredSummary.dailyMissing }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">缺周</div>
        <div class="summary-value warning">{{ filteredSummary.weeklyMissing }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">缺月</div>
        <div class="summary-value warning">{{ filteredSummary.monthlyMissing }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">部分覆盖</div>
        <div class="summary-value info">{{ filteredSummary.partial }}</div>
      </div>
    </div>

    <el-card class="filter-card">
      <div class="filter-bar">
        <el-select v-model="filters.platform" clearable placeholder="平台">
          <el-option label="Shopee" value="shopee" />
          <el-option label="TikTok" value="tiktok" />
          <el-option label="妙手ERP" value="miaoshou" />
        </el-select>

        <el-select v-model="filters.mainAccountId" clearable placeholder="主账号">
          <el-option
            v-for="item in mainAccountOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>

        <el-select v-model="filters.region" clearable placeholder="店铺区域">
          <el-option
            v-for="item in regionOptions"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-select v-model="filters.shopType" clearable placeholder="店铺类型">
          <el-option
            v-for="item in shopTypeOptions"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-select v-model="filters.coverageStatus" clearable placeholder="覆盖状态">
          <el-option label="缺日" value="missing_daily" />
          <el-option label="缺周" value="missing_weekly" />
          <el-option label="缺月" value="missing_monthly" />
          <el-option label="部分覆盖" value="partial" />
          <el-option label="全覆盖" value="full" />
        </el-select>

        <el-button @click="loadCoverage">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </el-card>

    <el-card class="table-card">
      <template #header>
        <div class="table-header">
          <div>
            <strong>覆盖率巡检</strong>
            <span class="table-summary">共 {{ filteredItems.length }} 个店铺账号</span>
          </div>
          <div class="batch-actions">
            <el-button :disabled="selectedRows.length === 0" @click="openBatchDialog('daily')">
              批量补日
            </el-button>
            <el-button :disabled="selectedRows.length === 0" @click="openBatchDialog('weekly')">
              批量补周
            </el-button>
            <el-button :disabled="selectedRows.length === 0" @click="openBatchDialog('monthly')">
              批量补月
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="filteredItems"
        stripe
        v-loading="loading"
        row-key="shop_account_id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="platform" label="平台" width="110" />
        <el-table-column prop="main_account_name" label="主账号" min-width="160">
          <template #default="{ row }">
            {{ row.main_account_name || row.main_account_id }}
          </template>
        </el-table-column>
        <el-table-column prop="shop_account_name" label="店铺账号" min-width="180" />
        <el-table-column prop="shop_region" label="区域" width="100">
          <template #default="{ row }">
            {{ row.shop_region || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="shop_type" label="店铺类型" width="100">
          <template #default="{ row }">
            {{ row.shop_type || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="日" width="90">
          <template #default="{ row }">
            <el-tag :type="row.daily_covered ? 'success' : 'danger'">
              {{ row.daily_covered ? '已覆盖' : '缺日' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="周" width="90">
          <template #default="{ row }">
            <el-tag :type="row.weekly_covered ? 'success' : 'warning'">
              {{ row.weekly_covered ? '已覆盖' : '缺周' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="月" width="90">
          <template #default="{ row }">
            <el-tag :type="row.monthly_covered ? 'success' : 'warning'">
              {{ row.monthly_covered ? '已覆盖' : '缺月' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推荐数据域" min-width="220">
          <template #default="{ row }">
            <el-tag
              v-for="domain in row.recommended_domains || []"
              :key="`${row.shop_account_id}-${domain}`"
              size="small"
              class="erp-mr-xs"
            >
              {{ getDomainLabel(domain) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="goToConfig(row)">去配置</el-button>
            <el-button
              size="small"
              :disabled="row.daily_covered"
              @click="openRowDialog('daily', row)"
            >
              补日
            </el-button>
            <el-button
              size="small"
              :disabled="row.weekly_covered"
              @click="openRowDialog('weekly', row)"
            >
              补周
            </el-button>
            <el-button
              size="small"
              :disabled="row.monthly_covered"
              @click="openRowDialog('monthly', row)"
            >
              补月
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialog.visible"
      width="640px"
      :title="`批量补配${getGranularityLabel(dialog.granularity)}`"
    >
      <div class="dialog-summary">
        <p>将为 {{ dialog.rows.length }} 个店铺账号创建配置。</p>
        <p>默认执行模式：无头模式</p>
        <p>默认状态：启用</p>
        <p>默认数据域来源：店铺能力</p>
      </div>

      <div class="dialog-rows">
        <div
          v-for="row in dialog.rows.slice(0, 8)"
          :key="`${dialog.granularity}-${row.shop_account_id}`"
          class="dialog-row"
        >
          <span>{{ row.platform }} / {{ row.main_account_name || row.main_account_id }} / {{ row.shop_account_name }}</span>
          <span>{{ row.shop_region || '-' }}</span>
        </div>
        <div v-if="dialog.rows.length > 8" class="dialog-more">
          其余 {{ dialog.rows.length - 8 }} 个店铺已省略
        </div>
      </div>

      <el-alert
        v-if="lastResult.skipped_shops?.length"
        type="warning"
        :closable="false"
        class="result-alert"
        show-icon
        :title="`本次有 ${lastResult.skipped_shops.length} 个店铺被跳过`"
      />

      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="batchLoading" @click="submitBatchRemediation">
          提交补配
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'

const router = useRouter()

const loading = ref(false)
const batchLoading = ref(false)
const coverage = ref({ summary: {}, items: [] })
const selectedRows = ref([])
const lastResult = ref({ created_configs: [], skipped_shops: [] })

const filters = reactive({
  platform: '',
  mainAccountId: '',
  region: '',
  shopType: '',
  coverageStatus: ''
})

const dialog = reactive({
  visible: false,
  granularity: 'daily',
  rows: []
})

const DOMAIN_LABELS = {
  orders: '订单',
  products: '商品',
  analytics: '流量',
  finance: '财务',
  services: '客服',
  inventory: '库存'
}

const GRANULARITY_LABELS = {
  daily: '日',
  weekly: '周',
  monthly: '月'
}

const items = computed(() => coverage.value.items || [])

const mainAccountOptions = computed(() => {
  const seen = new Map()
  for (const item of items.value) {
    if (!item.main_account_id) continue
    if (!seen.has(item.main_account_id)) {
      seen.set(item.main_account_id, item.main_account_name || item.main_account_id)
    }
  }
  return Array.from(seen.entries()).map(([value, label]) => ({ value, label }))
})

const regionOptions = computed(() =>
  Array.from(new Set(items.value.map((item) => item.shop_region).filter(Boolean))).sort()
)

const shopTypeOptions = computed(() =>
  Array.from(new Set(items.value.map((item) => item.shop_type).filter(Boolean))).sort()
)

const filteredItems = computed(() =>
  items.value.filter((item) => {
    if (filters.platform && item.platform !== filters.platform) return false
    if (filters.mainAccountId && item.main_account_id !== filters.mainAccountId) return false
    if (filters.region && item.shop_region !== filters.region) return false
    if (filters.shopType && item.shop_type !== filters.shopType) return false
    if (filters.coverageStatus === 'missing_daily' && item.daily_covered) return false
    if (filters.coverageStatus === 'missing_weekly' && item.weekly_covered) return false
    if (filters.coverageStatus === 'missing_monthly' && item.monthly_covered) return false
    if (filters.coverageStatus === 'partial' && !item.is_partially_covered && !item.partial_covered) return false
    if (filters.coverageStatus === 'full' && !item.fully_covered) return false
    return true
  })
)

const filteredSummary = computed(() => ({
  total: filteredItems.value.length,
  dailyMissing: filteredItems.value.filter((item) => !item.daily_covered).length,
  weeklyMissing: filteredItems.value.filter((item) => !item.weekly_covered).length,
  monthlyMissing: filteredItems.value.filter((item) => !item.monthly_covered).length,
  partial: filteredItems.value.filter((item) => item.is_partially_covered || item.partial_covered).length
}))

function getDomainLabel(domain) {
  return DOMAIN_LABELS[domain] || domain
}

function getGranularityLabel(granularity) {
  return GRANULARITY_LABELS[granularity] || granularity
}

function handleSelectionChange(rows) {
  selectedRows.value = rows
}

function openRowDialog(granularity, row) {
  lastResult.value = { created_configs: [], skipped_shops: [] }
  dialog.visible = true
  dialog.granularity = granularity
  dialog.rows = [row]
}

function openBatchDialog(granularity) {
  lastResult.value = { created_configs: [], skipped_shops: [] }
  dialog.visible = true
  dialog.granularity = granularity
  dialog.rows = selectedRows.value
}

function goToConfig(row) {
  router.push({
    path: '/collection-config',
    query: {
      platform: row.platform,
      shop_account_id: row.shop_account_id
    }
  })
}

async function loadCoverage() {
  loading.value = true
  try {
    const params = filters.platform ? { platform: filters.platform } : {}
    coverage.value = await collectionApi.getConfigCoverage(params)
  } catch (error) {
    console.error('Failed to load collection coverage audit data:', error)
    ElMessage.error('加载采集覆盖率失败')
    coverage.value = { summary: {}, items: [] }
  } finally {
    loading.value = false
  }
}

async function submitBatchRemediation() {
  if (dialog.rows.length === 0) {
    ElMessage.warning('请先选择至少一个店铺账号')
    return
  }

  batchLoading.value = true
  try {
    const result = await collectionApi.batchRemediateConfigs({
      shop_account_ids: dialog.rows.map((row) => row.shop_account_id),
      granularity: dialog.granularity
    })
    lastResult.value = result || { created_configs: [], skipped_shops: [] }

    const createdCount = result?.created_configs?.length || 0
    const skippedCount = result?.skipped_shops?.length || 0
    if (createdCount > 0 && skippedCount > 0) {
      ElMessage.warning(`已创建 ${createdCount} 条配置，跳过 ${skippedCount} 个已覆盖店铺`)
    } else if (createdCount > 0) {
      ElMessage.success(`已创建 ${createdCount} 条配置`)
    } else {
      ElMessage.warning('没有新增配置，所选店铺可能已覆盖')
    }

    dialog.visible = false
    await loadCoverage()
  } catch (error) {
    console.error('Failed to batch remediate configs:', error)
    ElMessage.error(error?.response?.data?.detail || '批量补配失败')
  } finally {
    batchLoading.value = false
  }
}

onMounted(() => {
  loadCoverage()
})
</script>

<style scoped>
.collection-coverage-audit {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 20px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

.summary-label {
  color: #64748b;
  font-size: 13px;
}

.summary-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.summary-value.danger {
  color: #dc2626;
}

.summary-value.warning {
  color: #d97706;
}

.summary-value.info {
  color: #2563eb;
}

.filter-card,
.table-card {
  border-radius: 12px;
}

.filter-bar,
.table-header,
.batch-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.table-header {
  justify-content: space-between;
}

.table-summary {
  margin-left: 12px;
  color: #64748b;
  font-size: 13px;
}

.dialog-summary p {
  margin: 0 0 8px;
}

.dialog-rows {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dialog-row,
.dialog-more {
  display: flex;
  justify-content: space-between;
  color: #475569;
  font-size: 13px;
}

.result-alert {
  margin-top: 16px;
}
</style>
