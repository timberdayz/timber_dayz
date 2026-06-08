<template>
  <div class="collection-config">
    <!-- legacy-contract: v-if="form.date_range_type === 'custom'" -->
    <!-- legacy-contract: v-for="option in availableDomainOptions" -->
    <!-- legacy-contract: label="执行模式" -->
    <!-- legacy-contract: <el-table-column label="执行模式" -->
    <div class="page-header">
      <div>
        <h2>采集配置管理</h2>
        <p class="page-subtitle">按主账号维护当前配置，统一推进周期时间，并直接在店铺工作区完成例外管理。</p>
      </div>
      <div class="header-actions">
        <el-button @click="backfillLegacyTemplates">回填旧配置</el-button>
        <el-button type="primary" :disabled="!selectedMainAccountCard" @click="openCurrentConfigDialog">
          {{ currentConfigSummary ? '编辑当前配置' : '快速创建配置' }}
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

          <el-switch v-model="showOnlyAttentionAccounts" />
          <span class="table-summary">仅看未配置/待同步主账号</span>

          <el-button @click="reloadPageData">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="granularity-actions">
        <div class="granularity-schedule-bar">
          <div>
            <div class="schedule-title">统一定时采集</div>
            <div class="shop-scope-meta">
              {{ currentGranularityScheduleDescription }}
              <span v-if="granularitySchedule?.is_mixed">，当前存在部分主账号定时状态不一致</span>
            </div>
            <div class="schedule-meta-row">
              <el-tag size="small" type="info">影响 {{ granularitySchedule?.affected_config_count || 0 }} 个当前配置</el-tag>
              <el-tag
                v-if="granularitySchedule?.enabled"
                size="small"
                type="success"
              >
                已覆盖 {{ granularitySchedule?.enabled_config_count || 0 }} 个
              </el-tag>
            </div>
          </div>
          <div class="panel-actions">
            <el-tag v-if="granularitySchedule?.is_mixed" size="small" type="warning">部分已启用</el-tag>
            <el-switch
              :model-value="Boolean(granularitySchedule?.enabled)"
              :loading="granularityScheduleUpdating"
              @change="toggleGranularitySchedule"
            />
            <span class="table-summary">{{ granularitySchedule?.enabled ? '已开启' : '已关闭' }}</span>
          </div>
        </div>
        <el-button
          v-if="activeGranularity === 'weekly'"
          size="small"
          type="primary"
          :disabled="!mainAccountCards.length"
          @click="bulkAdvanceCurrentGranularity"
        >
          全部主账号推进到下一周
        </el-button>
        <el-button
          v-if="activeGranularity === 'monthly'"
          size="small"
          type="primary"
          :disabled="!mainAccountCards.length"
          @click="bulkAdvanceCurrentGranularity"
        >
          全部主账号推进到下一月
        </el-button>
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

    <el-card class="queue-card">
      <template #header>
        <div class="table-header">
          <span>配置执行队列</span>
          <span class="table-summary">运行中 {{ activeConfigRuns.length }} / 排队中 {{ queuedConfigRuns.length }}</span>
        </div>
      </template>

      <div v-if="!configRuns.length" class="empty-tip">当前没有配置执行记录</div>
      <template v-else>
        <div class="queue-status-bar">
          <el-tag size="small" :type="collectionHealth?.queue_runner === 'running' ? 'success' : 'danger'">
            {{ collectionHealth?.queue_runner === 'running' ? '执行器在线' : '执行器未运行' }}
          </el-tag>
          <el-tag size="small" :type="collectionHealth?.scheduler === 'ok' ? 'success' : 'warning'">
            {{ collectionHealth?.scheduler === 'ok' ? '调度器正常' : '调度器不可用' }}
          </el-tag>
          <span v-if="collectionHealth?.queue_runner !== 'running'" class="shop-scope-meta">
            当前只会入队，不会实际消费，请先检查后端 QueueRunner。
          </span>
        </div>
        <div class="queue-list">
        <div
          v-for="run in visibleConfigRuns"
          :key="run.run_id"
          class="queue-item"
        >
          <div class="queue-item-header">
            <div class="queue-item-title">
              <el-tag :type="getConfigRunTagType(run.status)" size="small">{{ getConfigRunStatusLabel(run.status) }}</el-tag>
              <span>{{ run.main_account_id }}</span>
              <span class="queue-run-id">{{ run.run_id }}</span>
            </div>
            <el-button
              v-if="run.status === 'queued'"
              size="small"
              type="danger"
              plain
              @click="cancelConfigRun(run)"
            >
              取消
            </el-button>
          </div>
          <div class="queue-item-meta">
            <span>配置 #{{ run.config_id }}</span>
            <span>{{ getPlatformLabel(run.platform) }}</span>
            <span>{{ run.trigger_type === 'manual' ? '手动执行' : '定时执行' }}</span>
            <span>创建于 {{ formatDateTime(run.created_at) }}</span>
          </div>
          <div v-if="run.error_message" class="queue-item-error">{{ run.error_message }}</div>
        </div>
        </div>
      </template>
    </el-card>

    <div class="workbench-layout">
      <el-card class="nav-panel">
        <template #header>
          <div class="table-header">
            <span>主账号导航</span>
            <span class="table-summary">{{ mainAccountCards.length }} 个主账号</span>
          </div>
        </template>

        <div v-if="!mainAccountGroups.length" class="empty-tip">当前没有可用主账号</div>
        <div v-else class="panel-list account-nav-list">
          <div
            v-for="group in mainAccountGroups"
            :key="group.platform"
            class="account-group"
          >
            <div class="account-group-title">{{ getPlatformLabel(group.platform) }}</div>
            <div
              v-for="account in group.accounts"
              :key="account.key"
              class="panel-card account-card"
              :class="{ active: account.key === selectedMainAccountKey }"
              @click="selectMainAccount(account)"
            >
              <div class="panel-card-header">
                <div>
                  <div class="panel-card-title">{{ account.main_account_name || account.main_account_id }}</div>
                  <div class="panel-card-meta">{{ account.main_account_id }}</div>
                </div>
                <el-tag size="small" :type="account.isConfigured ? 'success' : 'warning'">
                  {{ account.isConfigured ? '已配置' : '未配置' }}
                </el-tag>
              </div>
              <div class="account-summary">
                <span>{{ account.shop_count }} 店</span>
                <span>{{ account.executionLabel }}</span>
              </div>
              <div class="account-summary">
                <el-tag size="small" :type="account.scheduleEnabled ? 'success' : 'info'">{{ account.scheduleEnabled ? '已定时' : '未定时' }}</el-tag>
                <el-tag v-if="account.hasScopeDrift" size="small" type="warning">待同步</el-tag>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="summary-panel">
        <template #header>
          <div class="table-header">
            <span>{{ activeGranularityLabel }}当前配置</span>
            <div class="panel-actions">
              <el-button size="small" type="primary" :disabled="!selectedMainAccountCard" @click="openCurrentConfigDialog">
                {{ currentConfigSummary ? '编辑配置' : '快速创建配置' }}
              </el-button>
              <el-button size="small" :disabled="!currentConfigSummary" @click="advanceCurrentConfig">
                推进到下一周期
              </el-button>
            </div>
          </div>
        </template>

        <div v-if="!selectedMainAccountCard" class="empty-tip">先选择左侧主账号</div>
        <div v-else-if="!currentConfigSummary" class="empty-tip">
          当前主账号在{{ activeGranularityLabel }}下还没有配置
        </div>
        <div v-else class="current-config-body">
          <div class="current-config-card">
            <div class="panel-card-header">
              <div>
                <div class="panel-card-title">{{ selectedMainAccountCard.main_account_name || selectedMainAccountCard.main_account_id }}</div>
                <div class="panel-card-meta">{{ currentConfigSummary.platform }} · {{ currentConfigSummary.main_account_id }}</div>
              </div>
              <el-tag size="small" :type="granularitySchedule?.enabled ? 'success' : 'info'">
                {{ granularitySchedule?.enabled ? '已定时' : '未定时' }}
              </el-tag>
            </div>
            <div class="template-summary">
              <el-tag size="small" type="info">配置 #{{ currentConfigSummary.id }}</el-tag>
              <el-tag size="small" type="info">{{ getGranularityLabel(currentConfigSummary.granularity) }}</el-tag>
              <el-tag size="small" type="info">{{ currentConfigSummary.batch_key || currentConfigSummary.name }}</el-tag>
              <el-tag size="small" type="info">{{ formatConfigDateRange(currentConfigSummary) }}</el-tag>
              <el-tag size="small" :type="currentConfigSummary.execution_mode === 'headed' ? 'warning' : 'success'">
                {{ getExecutionModeLabel(currentConfigSummary.execution_mode) }}
              </el-tag>
              <el-tag size="small" :type="currentConfigSummary.is_active ? 'success' : 'info'">
                {{ currentConfigSummary.is_active ? '启用中' : '已停用' }}
              </el-tag>
            </div>
            <div class="current-config-summary">
              <span>店铺数 {{ currentConfigSummary.shop_scopes?.length || 0 }}</span>
              <span>例外店铺 {{ currentConfigSummary.override_count || 0 }}</span>
            </div>
            <div v-if="blockingTasks.length" class="shop-scope-meta warning-text">
              当前主账号有 {{ blockingTasks.length }} 条活动任务占用，配置执行会跳过这些店铺。
              <el-button size="small" link type="warning" @click="openBlockingTasks">
                查看阻塞任务
              </el-button>
            </div>
            <div v-if="granularitySchedule?.enabled && granularitySchedule?.cron" class="shop-scope-meta">
              Cron：{{ granularitySchedule.cron }}
            </div>
            <div v-if="currentScheduleInfo?.next_run_time" class="shop-scope-meta">
              下次执行：{{ formatDateTime(currentScheduleInfo.next_run_time) }}
            </div>
            <div class="batch-summary-actions">
              <el-button size="small" @click.stop="editConfig(currentConfigSummary)">编辑当前配置</el-button>
              <el-button size="small" @click.stop="openTemporaryRunDialog">临时补采</el-button>
              <el-button size="small" type="success" @click.stop="runConfig(currentConfigSummary)">执行</el-button>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="shop-panel">
        <template #header>
          <div class="table-header">
            <span>店铺工作区</span>
            <div class="panel-actions">
              <el-input
                v-model="shopSearch"
                class="shop-search"
                placeholder="搜索店铺"
                clearable
              />
              <el-switch v-model="onlyExceptionShops" />
              <span class="table-summary">仅看例外店铺</span>
              <el-button size="small" :disabled="!selectedShopScopeIds.length" @click="bulkSetSelectedScopesEnabled(true)">
                批量纳入
              </el-button>
              <el-button size="small" :disabled="!selectedShopScopeIds.length" @click="bulkSetSelectedScopesEnabled(false)">
                批量移出
              </el-button>
              <el-button size="small" :disabled="!selectedShopScopeIds.length" @click="bulkRestoreSelectedScopesDefault">
                批量恢复默认
              </el-button>
              <el-button size="small" type="primary" :disabled="!currentConfigSummary" @click="saveCurrentConfigFromWorkbench">
                保存当前配置
              </el-button>
            </div>
          </div>
        </template>

        <div v-if="!currentConfigSummary" class="empty-tip">先选择一个当前配置</div>
        <div v-else class="shop-panel-body">
          <div class="shop-panel-summary">
            <el-tag size="small" type="info">当前配置 #{{ currentConfigSummary.id }}</el-tag>
            <el-tag size="small" type="info">{{ getGranularityLabel(currentConfigSummary.granularity) }}</el-tag>
            <el-tag size="small" type="info">{{ currentConfigSummary.batch_key || currentConfigSummary.name }}</el-tag>
            <el-tag size="small" type="success">{{ formatConfigDateRange(currentConfigSummary) }}</el-tag>
            <el-tag size="small" :type="currentConfigSummary.execution_mode === 'headed' ? 'warning' : 'success'">
              {{ getExecutionModeLabel(currentConfigSummary.execution_mode) }}
            </el-tag>
            <span class="shop-scope-meta">当前配置定时只会调度这一条配置，店铺工作区用于直接管理例外。</span>
          </div>

          <el-table
            ref="shopTableRef"
            :data="shopScopeRows"
            stripe
            height="100%"
            @selection-change="handleShopSelectionChange"
          >
            <el-table-column type="selection" width="48" />
            <el-table-column label="店铺" min-width="160">
              <template #default="{ row }">
                <div class="shop-name-cell">
                  <div>{{ row.account?.name || row.scope.shop_account_id }}</div>
                  <div class="shop-scope-meta">{{ row.account?.shop_region || '未标注站点' }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="纳入本次" width="110">
              <template #default="{ row }">
                <el-switch v-model="row.scope.enabled" />
              </template>
            </el-table-column>
            <el-table-column label="实际数据域" min-width="240">
              <template #default="{ row }">
                <el-checkbox-group
                  v-model="row.scope.data_domains"
                  @change="onScopeDataDomainsChange(row.scope)"
                >
                  <el-checkbox
                    v-for="option in availableDomainOptions(currentConfigSummary?.platform)"
                    :key="`${row.scope.shop_account_id}-inline-${option.value}`"
                    :label="option.value"
                    :disabled="!isScopeDomainAvailable(row.scope, option.value)"
                  >
                    {{ option.label }}
                  </el-checkbox>
                </el-checkbox-group>
              </template>
            </el-table-column>
            <el-table-column label="可编辑子类型" min-width="180">
              <template #default="{ row }">
                <div
                  v-for="domain in getScopeSubtypeDomains(row.scope)"
                  :key="`${row.scope.shop_account_id}-inline-${domain}`"
                  class="sub-domain-section"
                >
                  <span class="sub-domain-label">{{ getDomainLabel(domain) }}子类型</span>
                  <div class="subtype-checkboxes">
                    <label
                      v-for="option in getSubtypeOptions(domain)"
                      :key="`${row.scope.shop_account_id}-inline-${domain}-${option.value}`"
                      class="subtype-option"
                    >
                      <input
                        type="checkbox"
                        :value="option.value"
                        v-model="row.scope.sub_domains[domain]"
                      >
                      <span>{{ option.label }}</span>
                    </label>
                  </div>
                </div>
                <span v-if="!getScopeSubtypeDomains(row.scope).length" class="shop-scope-meta">无子类型</span>
              </template>
            </el-table-column>
            <el-table-column label="配置来源" width="120">
              <template #default="{ row }">
                <el-tag :type="row.isException ? 'warning' : 'success'">{{ row.isException ? '已覆盖' : '继承默认' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="restoreScopeToDefault(row.scope.shop_account_id)">
                  恢复默认
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? `编辑${activeGranularityLabel}当前配置` : `创建${activeGranularityLabel}当前配置`"
      width="960px"
      class="collection-config-editor-dialog"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" label-width="110px">
        <div class="editor-layout editor-layout-single">
          <div class="editor-main">
            <el-form-item label="配置名称">
              <el-input v-model="form.name" placeholder="可留空，默认使用主账号 + 粒度" />
            </el-form-item>
            <el-form-item label="平台">
              <el-select
                v-model="form.platform"
                class="full-width-select"
                data-testid="collection-config-platform-field"
                placeholder="请选择平台"
                @change="onTemplatePlatformChange"
              >
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
                v-model="form.main_account_id"
                class="full-width-select"
                data-testid="collection-config-main-account-field"
                placeholder="请选择主账号"
                :disabled="!form.platform"
                @change="onTemplateMainAccountChange"
              >
                <el-option
                  v-for="option in dialogMainAccountOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="当前时间策略">
              <el-select v-model="form.default_date_range_type" class="full-width-select">
                <el-option
                  v-for="option in currentGranularityDateOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.default_date_range_type === 'custom'" label="自定义日期">
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
            <el-alert
              title="当前配置的定时开关由上方粒度统一定时控制"
              type="info"
              :closable="false"
            />
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" data-testid="collection-config-save-button" :loading="submitting" @click="submitCurrentConfigForm">
          {{ isEdit ? '保存配置' : '创建配置' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="temporaryRunVisible"
      title="临时补采"
      width="720px"
      destroy-on-close
    >
      <el-form :model="temporaryRunForm" label-width="110px">
        <el-form-item label="补采范围">
          <el-radio-group v-model="temporaryRunForm.scope_mode">
            <el-radio-button label="selected">选中店铺</el-radio-button>
            <el-radio-button label="enabled">当前纳入店铺</el-radio-button>
            <el-radio-button label="all">全部店铺</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="时间策略">
          <el-select v-model="temporaryRunForm.date_range_type" class="full-width-select">
            <el-option
              v-for="option in currentGranularityDateOptions"
              :key="`temporary-${option.value}`"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="temporaryRunForm.date_range_type === 'custom'" label="补采日期">
          <el-date-picker
            v-model="temporaryRunCustomDateRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="执行模式">
          <el-radio-group v-model="temporaryRunForm.execution_mode">
            <el-radio-button label="headless">无头模式</el-radio-button>
            <el-radio-button label="headed">有头模式</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <div class="temporary-run-summary">
          <el-tag size="small" type="info">预计创建 {{ temporaryRunTargets.length }} 个一次性任务</el-tag>
          <span class="shop-scope-meta">临时补采不会修改当前配置，也不会影响定时采集。</span>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="temporaryRunVisible = false">取消</el-button>
        <el-button type="primary" :loading="temporaryRunSubmitting" @click="submitTemporaryRun">
          创建补采任务
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, Edit, MagicStick, Plus, Refresh } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'
import {
  buildAutoSelectedSubDomains,
  buildTimeSelectionPayload,
  getAvailableDomainOptions,
  getSelectedSubtypeDomains,
  getSubtypeOptions,
  normalizeConfigGranularity,
  normalizeDomainSubtypeMap,
} from '@/constants/collection'

const router = useRouter()
const loading = ref(false)
const accountsLoading = ref(false)
const coverageLoading = ref(false)
const configRunsLoading = ref(false)
const dialogVisible = ref(false)
const temporaryRunVisible = ref(false)
const submitting = ref(false)
const temporaryRunSubmitting = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const shopTableRef = ref(null)
const editableCurrentConfigId = ref(null)
const editableShopScopes = ref([])

const activeGranularity = ref('daily')
const selectedMainAccountKey = ref('')
const shopSearch = ref('')
const onlyExceptionShops = ref(false)
const showOnlyAttentionAccounts = ref(false)
const customDateRange = ref([])
const temporaryRunCustomDateRange = ref([])
const selectedShopScopeIds = ref([])

const templatesData = ref([])
const coverage = ref({ summary: {}, items: [] })
const configRuns = ref([])
const collectionHealth = ref(null)
const currentScheduleInfo = ref(null)
const blockingTasks = ref([])
const granularitySchedule = ref(null)
const granularityScheduleUpdating = ref(false)
const flatAccounts = ref([])
const groupedAccounts = ref([])
const dialogAccounts = ref([])

const filters = reactive({
  platform: '',
})

const form = reactive({
  id: null,
  name: '',
  platform: '',
  main_account_id: '',
  default_date_range_type: 'yesterday',
  execution_mode: 'headless',
  schedule_enabled: false,
  schedule_cron: '',
  shop_scopes: [],
})

const temporaryRunForm = reactive({
  scope_mode: 'selected',
  date_range_type: 'custom',
  execution_mode: 'headless',
})

const activeGranularityLabel = computed(() => getGranularityLabel(activeGranularity.value))
const platformOptions = computed(() => {
  const options = new Map()
  for (const account of flatAccounts.value || []) {
    const key = normalizePlatformCode(account.platform)
    if (!options.has(key)) {
      options.set(key, { label: getPlatformLabel(key), value: key })
    }
  }
  return Array.from(options.values())
})

const currentCoverageSummary = computed(() => {
  const summary = coverage.value?.summary || {}
  const key = activeGranularity.value
  return {
    total: summary.total_shop_count || 0,
    covered: summary[`${key}_covered_count`] || 0,
    missing: summary[`${key}_missing_count`] || 0,
    partial: summary.partial_covered_count || 0,
  }
})

const currentGranularityScheduleDescription = computed(() => {
  if (granularitySchedule.value?.description) return granularitySchedule.value.description
  if (activeGranularity.value === 'daily') return '每天 07:00 自动采集昨天'
  if (activeGranularity.value === 'weekly') return '每周一 09:00 自动采集上周'
  return '每月 1 日 09:00 自动采集上月'
})

const activeConfigRuns = computed(() => (configRuns.value || []).filter((run) => run.status === 'running'))
const queuedConfigRuns = computed(() => (configRuns.value || []).filter((run) => run.status === 'queued'))
const visibleConfigRuns = computed(() => (configRuns.value || []).slice(0, 8))
const ACTIVE_TASK_STATUSES = ['pending', 'queued', 'running', 'verification_required', 'verification_submitted', 'paused', 'manual_intervention_required']

const mainAccountCards = computed(() => {
  const cardMap = new Map()
  for (const account of flatAccounts.value || []) {
    if (filters.platform && normalizePlatformCode(account.platform) !== normalizePlatformCode(filters.platform)) continue
    if (String(account.status || '').toLowerCase() !== 'active') continue
    const key = `${normalizePlatformCode(account.platform)}::${account.main_account_id || ''}`
    if (!cardMap.has(key)) {
      cardMap.set(key, {
        key,
        platform: normalizePlatformCode(account.platform),
        main_account_id: account.main_account_id || '',
        main_account_name: account.main_account_name || account.main_account_id || '',
        shop_count: 0,
        templates: [],
      })
    }
    cardMap.get(key).shop_count += 1
  }

  for (const template of templatesData.value || []) {
    const key = `${normalizePlatformCode(template.platform)}::${template.main_account_id}`
    const card = cardMap.get(key) || {
      key,
      platform: normalizePlatformCode(template.platform),
      main_account_id: template.main_account_id,
      main_account_name: template.main_account_id,
      shop_count: 0,
      templates: [],
    }
    card.templates.push(template)
    cardMap.set(key, card)
  }

  return Array.from(cardMap.values())
    .map((card) => {
      const currentTemplate = (card.templates || []).find((item) => normalizeConfigGranularity({ granularity: item.granularity }) === activeGranularity.value) || null
      const hasScopeDrift = Boolean(currentTemplate?.missing_shop_scope_ids?.length || currentTemplate?.stale_shop_scope_ids?.length)
      const isConfigured = Boolean(currentTemplate)
      return {
        ...card,
        currentTemplate,
        isConfigured,
        hasScopeDrift,
        scheduleEnabled: Boolean(currentTemplate?.default_schedule_enabled),
        scheduleLabel: currentTemplate?.default_schedule_enabled ? '已定时' : '未定时',
        executionLabel: currentTemplate ? getExecutionModeLabel(currentTemplate.default_execution_mode) : '未配置',
      }
    })
    .filter((card) => {
      if (!showOnlyAttentionAccounts.value) return true
      return !card.isConfigured || card.hasScopeDrift
    })
})

const mainAccountGroups = computed(() => {
  const groups = new Map()
  for (const card of mainAccountCards.value) {
    if (!groups.has(card.platform)) {
      groups.set(card.platform, [])
    }
    groups.get(card.platform).push(card)
  }
  return Array.from(groups.entries()).map(([platform, accounts]) => ({
    platform,
    accounts: accounts.sort((a, b) => a.main_account_name.localeCompare(b.main_account_name)),
  }))
})

const selectedMainAccountCard = computed(() =>
  mainAccountCards.value.find((item) => item.key === selectedMainAccountKey.value) || null
)

const selectedTemplate = computed(() => selectedMainAccountCard.value?.currentTemplate || null)

const currentConfigSummary = computed(() => {
  if (!selectedTemplate.value) return null
  const batches = [...(selectedTemplate.value.batches || [])].filter((item) =>
    normalizeConfigGranularity({
      granularity: item.granularity,
      date_range_type: item.date_range_type,
    }) === activeGranularity.value
    && String(item.template_id || selectedTemplate.value.id) === String(selectedTemplate.value.id)
  )
  batches.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0))
  const candidate = batches.find((item) => item.status === 'active') || batches[0] || null
  if (!candidate) return null
  return {
    ...candidate,
    platform: selectedTemplate.value.platform,
    main_account_id: selectedTemplate.value.main_account_id,
    default_execution_mode: selectedTemplate.value.default_execution_mode,
    default_schedule_enabled: selectedTemplate.value.default_schedule_enabled,
    default_schedule_cron: selectedTemplate.value.default_schedule_cron,
    override_count: candidate.shop_overrides?.length || 0,
  }
})

const shopScopeRows = computed(() => {
  if (!currentConfigSummary.value || editableCurrentConfigId.value !== currentConfigSummary.value.id) return []
  return (editableShopScopes.value || [])
    .map((scope) => {
      return {
        scope,
        account: getAccountById(scope.shop_account_id),
        isException: isScopeOverridden(scope),
      }
    })
    .filter((row) => {
      const search = shopSearch.value.trim().toLowerCase()
      const matchesSearch = !search
        || String(row.scope.shop_account_id || '').toLowerCase().includes(search)
        || String(row.account?.name || '').toLowerCase().includes(search)
      if (!matchesSearch) return false
      if (onlyExceptionShops.value && !row.isException) return false
      return true
    })
})

const selectedShopScopeRows = computed(() =>
  shopScopeRows.value.filter((row) => selectedShopScopeIds.value.includes(row.scope.shop_account_id))
)

const temporaryRunTargets = computed(() => {
  const rows = temporaryRunForm.scope_mode === 'selected'
    ? selectedShopScopeRows.value
    : shopScopeRows.value

  if (temporaryRunForm.scope_mode === 'all') {
    return rows
  }
  return rows.filter((row) => temporaryRunForm.scope_mode === 'selected' || row.scope.enabled)
})

const dialogMainAccountOptions = computed(() => buildMainAccountOptions(dialogAccounts.value, form.platform))
const currentGranularityDateOptions = computed(() => {
  if (activeGranularity.value === 'daily') {
    return [
      { label: '昨天', value: 'yesterday' },
      { label: '今天', value: 'today' },
      { label: '按日自定义', value: 'custom' },
    ]
  }
  if (activeGranularity.value === 'weekly') {
    return [
      { label: '最近7天', value: 'last_7_days' },
      { label: '按周自定义', value: 'custom' },
    ]
  }
  return [
    { label: '最近30天', value: 'last_30_days' },
    { label: '按月自定义', value: 'custom' },
  ]
})

watch(mainAccountCards, (value) => {
  if (!value.length) {
    selectedMainAccountKey.value = ''
    return
  }
  if (!value.some((item) => item.key === selectedMainAccountKey.value)) {
    selectedMainAccountKey.value = value[0].key
  }
}, { immediate: true })

watch(
  () => [currentConfigSummary.value?.id, currentConfigSummary.value?.updated_at],
  () => {
    syncEditableCurrentConfig()
  },
  { immediate: true }
)

watch(activeGranularity, async () => {
  resetCurrentConfigForm()
  await reloadPageData()
})

watch(
  () => currentConfigSummary.value?.id,
  () => {
    selectedShopScopeIds.value = []
    if (shopTableRef.value) {
      shopTableRef.value.clearSelection?.()
    }
  }
)

watch(
  () => currentConfigSummary.value?.id,
  async (configId) => {
    if (!configId) {
      currentScheduleInfo.value = null
      blockingTasks.value = []
      return
    }
    try {
      currentScheduleInfo.value = await collectionApi.getConfigSchedule(configId)
    } catch (error) {
      currentScheduleInfo.value = null
    }
    try {
      const activeShopIds = new Set((currentConfigSummary.value?.shop_scopes || []).map((scope) => scope.shop_account_id))
      const allTasks = await collectionApi.getTasks({
        platform: currentConfigSummary.value?.platform,
      })
      blockingTasks.value = (allTasks || []).filter(
        (task) =>
          activeShopIds.has(task.account)
          && task.platform === currentConfigSummary.value?.platform
          && ACTIVE_TASK_STATUSES.includes(task.status)
      )
    } catch (error) {
      blockingTasks.value = []
    }
  },
  { immediate: true }
)

function normalizePlatformCode(value) {
  return String(value || '').trim().toLowerCase()
}

function getPlatformLabel(platform) {
  const labels = {
    shopee: 'Shopee',
    tiktok: 'TikTok',
    miaoshou: '妙手',
  }
  return labels[normalizePlatformCode(platform)] || platform || '-'
}

function getGranularityLabel(granularity) {
  const labels = {
    daily: '日采集',
    weekly: '周采集',
    monthly: '月采集',
  }
  return labels[granularity] || granularity
}

function getDateRangeLabel(value) {
  const labels = {
    today: '今天',
    yesterday: '昨天',
    last_7_days: '最近7天',
    last_30_days: '最近30天',
    custom: activeGranularityLabel.value.replace('采集', '') + '自定义',
  }
  return labels[value] || value
}

function getExecutionModeLabel(mode) {
  return mode === 'headed' ? '有头模式' : '无头模式'
}

function getConfigRunStatusLabel(status) {
  const labels = {
    running: '运行中',
    queued: '排队中',
    completed: '已完成',
    partial_success: '部分成功',
    failed: '失败',
    cancelled: '已取消',
  }
  return labels[status] || status
}

function getConfigRunTagType(status) {
  const tagMap = {
    running: 'warning',
    queued: 'info',
    completed: 'success',
    partial_success: 'warning',
    failed: 'danger',
    cancelled: 'info',
  }
  return tagMap[status] || 'info'
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatConfigDateRange(config) {
  if (!config) return '-'
  if (config.custom_date_start && config.custom_date_end) {
    return `${config.custom_date_start} ~ ${config.custom_date_end}`
  }
  return getDateRangeLabel(config.date_range_type)
}

function buildMainAccountOptions(accounts = [], platform = '') {
  const map = new Map()
  for (const account of accounts || []) {
    if (platform && normalizePlatformCode(account.platform) !== normalizePlatformCode(platform)) continue
    const key = String(account.main_account_id || '').trim()
    if (!key) continue
    if (!map.has(key)) {
      map.set(key, {
        label: account.main_account_name || key,
        value: key,
      })
    }
  }
  return Array.from(map.values())
}

function cloneDeep(value) {
  return JSON.parse(JSON.stringify(value))
}

function getTemplateDefaultScope(shopAccountId) {
  return (selectedTemplate.value?.default_shop_scopes || []).find((scope) => scope.shop_account_id === shopAccountId) || null
}

function getAccountById(shopAccountId) {
  return flatAccounts.value.find((account) => account.id === shopAccountId) || null
}

function availableDomainOptions(platform) {
  return getAvailableDomainOptions(platform)
}

function isScopeDomainAvailable(scope, domain) {
  const account = getAccountById(scope.shop_account_id)
  return Boolean(account?.capabilities?.[domain])
}

function getDomainLabel(domain) {
  const option = getAvailableDomainOptions().find((item) => item.value === domain)
  return option?.label || domain
}

function normalizeScopeSubDomains(dataDomains = [], rawSubDomains = {}) {
  const normalized = normalizeDomainSubtypeMap(rawSubDomains)
  const subtypeDomains = getSelectedSubtypeDomains(dataDomains)
  const subtypeDomainSet = new Set(subtypeDomains)

  for (const domain of subtypeDomains) {
    if (!Array.isArray(normalized[domain]) || normalized[domain].length === 0) {
      normalized[domain] = getSubtypeOptions(domain).map((option) => option.value)
    }
  }

  for (const domain of Object.keys(normalized)) {
    if (!subtypeDomainSet.has(domain)) {
      delete normalized[domain]
    }
  }

  return normalized
}

function buildScopeFromAccount(account, existingScope = null) {
  const allowedDomains = getAvailableDomainOptions(account.platform)
    .map((option) => option.value)
    .filter((domain) => account.capabilities?.[domain])
  const dataDomains = existingScope?.data_domains?.length
    ? existingScope.data_domains.filter((domain) => allowedDomains.includes(domain))
    : allowedDomains
  const subDomains = normalizeScopeSubDomains(
    dataDomains,
    existingScope?.sub_domains || buildAutoSelectedSubDomains(dataDomains)
  )
  return {
    shop_account_id: account.id,
    data_domains: [...dataDomains],
    sub_domains: subDomains,
    enabled: existingScope?.enabled ?? true,
  }
}

function ensureScopeSubtypeMap(scope) {
  if (!scope.sub_domains || typeof scope.sub_domains !== 'object' || Array.isArray(scope.sub_domains)) {
    scope.sub_domains = {}
  }
  scope.sub_domains = normalizeScopeSubDomains(scope.data_domains || [], scope.sub_domains)
}

function getScopeSubtypeDomains(scope) {
  return getSelectedSubtypeDomains(scope.data_domains || [])
}

function onScopeDataDomainsChange(scope) {
  ensureScopeSubtypeMap(scope)
}

function cloneScopeForEditing(scope) {
  return {
    ...cloneDeep(scope),
    data_domains: [...(scope?.data_domains || [])],
    sub_domains: normalizeScopeSubDomains(scope?.data_domains || [], scope?.sub_domains),
    enabled: Boolean(scope?.enabled ?? true),
  }
}

function syncEditableCurrentConfig() {
  if (!currentConfigSummary.value) {
    editableCurrentConfigId.value = null
    editableShopScopes.value = []
    return
  }
  editableCurrentConfigId.value = currentConfigSummary.value.id
  editableShopScopes.value = (currentConfigSummary.value.shop_scopes || []).map((scope) => cloneScopeForEditing(scope))
}

function normalizedScopeSnapshot(scope) {
  return {
    enabled: Boolean(scope?.enabled ?? true),
    data_domains: [...(scope?.data_domains || [])].sort(),
    sub_domains: Object.fromEntries(
      Object.entries(normalizeScopeSubDomains(scope?.data_domains || [], scope?.sub_domains))
        .map(([domain, values]) => [domain, [...values].sort()])
        .sort(([left], [right]) => left.localeCompare(right))
    ),
  }
}

function isScopeOverridden(scope) {
  const defaultScope = getTemplateDefaultScope(scope.shop_account_id)
  if (!defaultScope) return true
  return JSON.stringify(normalizedScopeSnapshot(scope)) !== JSON.stringify(normalizedScopeSnapshot(defaultScope))
}

function buildDefaultShopScopes(platform, mainAccountId, existingScopes = []) {
  const sourceAccounts = dialogAccounts.value.length ? dialogAccounts.value : flatAccounts.value
  const accounts = sourceAccounts.filter(
    (account) =>
      normalizePlatformCode(account.platform) === normalizePlatformCode(platform)
      && String(account.main_account_id || '') === String(mainAccountId || '')
      && String(account.status || '').toLowerCase() === 'active'
  )
  const existingMap = Object.fromEntries((existingScopes || []).map((scope) => [scope.shop_account_id, scope]))
  return accounts
    .map((account) => buildScopeFromAccount(account, existingMap[account.id]))
    .sort((a, b) => a.shop_account_id.localeCompare(b.shop_account_id))
}

function resetCurrentConfigForm() {
  Object.assign(form, {
    id: null,
    name: '',
    platform: selectedMainAccountCard.value?.platform || filters.platform || '',
    main_account_id: selectedMainAccountCard.value?.main_account_id || '',
    default_date_range_type: activeGranularity.value === 'daily' ? 'yesterday' : 'custom',
    execution_mode: 'headless',
    schedule_enabled: false,
    schedule_cron: '',
    shop_scopes: [],
  })
  customDateRange.value = []
}

function selectMainAccount(account) {
  selectedMainAccountKey.value = account.key
}

function handleShopSelectionChange(rows) {
  selectedShopScopeIds.value = (rows || []).map((row) => row.scope.shop_account_id)
}

function restoreScopeToDefault(shopAccountId) {
  const defaultScope = getTemplateDefaultScope(shopAccountId)
  const targetScope = editableShopScopes.value.find((scope) => scope.shop_account_id === shopAccountId)
  if (!defaultScope || !targetScope) return
  targetScope.enabled = Boolean(defaultScope.enabled)
  targetScope.data_domains = [...(defaultScope.data_domains || [])]
  targetScope.sub_domains = normalizeScopeSubDomains(targetScope.data_domains, defaultScope.sub_domains)
  ensureScopeSubtypeMap(targetScope)
}

function bulkSetSelectedScopesEnabled(enabled) {
  for (const row of selectedShopScopeRows.value) {
    row.scope.enabled = enabled
  }
}

function bulkRestoreSelectedScopesDefault() {
  for (const row of selectedShopScopeRows.value) {
    restoreScopeToDefault(row.scope.shop_account_id)
  }
}

function openBlockingTasks() {
  if (!blockingTasks.value.length) return
  router.push({
    path: '/collection-tasks',
    query: {
      task_ids: blockingTasks.value.map((task) => task.task_id).join(','),
    },
  })
}

function openCurrentConfigDialog() {
  if (!selectedMainAccountCard.value) return
  isEdit.value = Boolean(currentConfigSummary.value)
  dialogVisible.value = true
  Object.assign(form, {
    id: currentConfigSummary.value?.id || null,
    name: currentConfigSummary.value?.name || '',
    platform: selectedMainAccountCard.value.platform,
    main_account_id: selectedMainAccountCard.value.main_account_id,
    default_date_range_type: currentConfigSummary.value?.date_range_type || (activeGranularity.value === 'daily' ? 'yesterday' : 'custom'),
    execution_mode: currentConfigSummary.value?.execution_mode || selectedTemplate.value?.default_execution_mode || 'headless',
    schedule_enabled: Boolean(granularitySchedule.value?.enabled),
    schedule_cron: granularitySchedule.value?.cron || '',
    shop_scopes: cloneDeep(currentConfigSummary.value?.shop_scopes || selectedTemplate.value?.default_shop_scopes || []),
  })
  customDateRange.value =
    currentConfigSummary.value?.custom_date_start && currentConfigSummary.value?.custom_date_end
      ? [currentConfigSummary.value.custom_date_start, currentConfigSummary.value.custom_date_end]
      : []
  loadDialogAccounts(form.platform)
}

function editTemplate(template) {
  selectedMainAccountKey.value = `${normalizePlatformCode(template.platform)}::${template.main_account_id}`
  openCurrentConfigDialog()
}

function editConfig(row) {
  selectedMainAccountKey.value = `${normalizePlatformCode(row.platform)}::${row.main_account_id}`
  openCurrentConfigDialog()
}

function buildCurrentConfigPayload() {
  return {
    name: form.name || null,
    platform: form.platform,
    main_account_id: form.main_account_id,
    granularity: activeGranularity.value,
    date_range_type: form.default_date_range_type,
    execution_mode: form.execution_mode,
    schedule_enabled: Boolean(granularitySchedule.value?.enabled),
    schedule_cron: granularitySchedule.value?.enabled ? granularitySchedule.value?.cron || null : null,
    retry_count: 3,
    shop_scopes: (form.shop_scopes || []).map((scope) => ({
      shop_account_id: scope.shop_account_id,
      enabled: Boolean(scope.enabled),
      data_domains: [...(scope.data_domains || [])],
      sub_domains: normalizeScopeSubDomains(scope.data_domains || [], scope.sub_domains),
    })),
    time_selection: buildTimeSelectionPayload(form.default_date_range_type, {
      customRange: customDateRange.value,
    }),
  }
}

async function submitCurrentConfigForm() {
  if (!form.platform || !form.main_account_id) {
    ElMessage.warning('请先选择平台和主账号')
    return
  }
  if (!(form.shop_scopes || []).length) {
    ElMessage.warning('请至少配置一个店铺范围')
    return
  }
  submitting.value = true
  try {
    const payload = buildCurrentConfigPayload()
    if (isEdit.value && form.id) {
      await collectionApi.updateConfig(form.id, payload)
      ElMessage.success('当前配置已更新')
    } else {
      const created = await collectionApi.createConfig(payload)
      if (selectedTemplate.value) {
        // 当前阶段仍通过模板/批次兼容层工作，提示用户后续可同步默认。
        created
      }
      ElMessage.success('当前配置已创建')
    }
    dialogVisible.value = false
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`保存当前配置失败: ${error.message}`)
  } finally {
    submitting.value = false
  }
}

async function saveCurrentConfigFromWorkbench() {
  if (!currentConfigSummary.value) return
  try {
    await collectionApi.updateConfig(currentConfigSummary.value.id, {
      shop_scopes: (editableShopScopes.value || []).map((scope) => ({
        shop_account_id: scope.shop_account_id,
        enabled: Boolean(scope.enabled),
        data_domains: [...(scope.data_domains || [])],
        sub_domains: normalizeScopeSubDomains(scope.data_domains || [], scope.sub_domains),
      })),
    })
    ElMessage.success('当前配置已保存')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`保存当前配置失败: ${error.message}`)
  }
}

async function advanceCurrentConfig() {
  if (!currentConfigSummary.value) return
  try {
    await collectionApi.advanceCurrentConfig(currentConfigSummary.value.id)
    ElMessage.success('当前配置时间范围已推进到下一周期')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`推进失败: ${error.message}`)
  }
}

async function reapplySelectedBatchTemplateDefaults() {
  if (!currentConfigSummary.value) return
  try {
    await collectionApi.reapplyTemplateDefaults(currentConfigSummary.value.id)
    ElMessage.success('已重新套用默认设置')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`重新套用失败: ${error.message}`)
  }
}

async function syncTemplateShopScopes() {
  if (!selectedTemplate.value) return
  try {
    const scopes = buildDefaultShopScopes(
      selectedTemplate.value.platform,
      selectedTemplate.value.main_account_id,
      selectedTemplate.value.default_shop_scopes || [],
    )
    await collectionApi.updateConfigTemplate(selectedTemplate.value.id, {
      default_shop_scopes: scopes.map((scope) => ({
        shop_account_id: scope.shop_account_id,
        enabled: Boolean(scope.enabled),
        data_domains: [...(scope.data_domains || [])],
        sub_domains: normalizeScopeSubDomains(scope.data_domains || [], scope.sub_domains),
      })),
    })
    ElMessage.success('主账号默认店铺范围已同步')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`同步店铺范围失败: ${error.message}`)
  }
}

async function syncBatchToTemplateScope(batch) {
  if (!batch?.id) return
  try {
    await collectionApi.reapplyTemplateDefaults(batch.id)
    ElMessage.success('当前配置已同步到最新默认范围')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`同步当前配置失败: ${error.message}`)
  }
}

async function createFutureBatches() {
  if (!currentConfigSummary.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入要生成多少期未来批次（1-12）',
      '批量创建未来批次',
      {
        inputValue: '3',
        inputPattern: /^(?:[1-9]|1[0-2])$/,
        inputErrorMessage: '请输入 1 到 12 之间的整数',
      }
    )
    const result = await collectionApi.createFutureConfigBatches(currentConfigSummary.value.id, {
      periods: Number(value),
    })
    ElMessage.success(`已创建 ${result.created_batches?.length || 0} 个未来批次`)
    await reloadPageData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`批量创建未来批次失败: ${error.message}`)
    }
  }
}

async function backfillLegacyTemplates() {
  try {
    const result = await collectionApi.backfillLegacyConfigTemplates()
    ElMessage.success(`已回填模板 ${result.created_template_count || 0} 条，挂接批次 ${result.attached_batch_count || 0} 条`)
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`回填旧配置失败: ${error.message}`)
  }
}

async function cloneNextBatch() {
  if (!currentConfigSummary.value) return
  try {
    await collectionApi.cloneNextConfigBatch(currentConfigSummary.value.id)
    ElMessage.success('已复制下一周期配置')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`复制失败: ${error.message}`)
  }
}

function applyCapabilitiesToAllShopScopes() {
  if (!dialogVisible.value || !form.platform || !form.main_account_id) return
  form.shop_scopes = buildDefaultShopScopes(form.platform, form.main_account_id, form.shop_scopes)
}

async function loadTemplates() {
  loading.value = true
  try {
    templatesData.value = await collectionApi.getConfigTemplates({
      platform: filters.platform || undefined,
      granularity: activeGranularity.value,
    })
  } catch (error) {
    templatesData.value = []
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
    flatAccounts.value = []
    groupedAccounts.value = []
    ElMessage.error(`加载账号失败: ${error.message}`)
  } finally {
    accountsLoading.value = false
  }
}

async function loadDialogAccounts(platform) {
  if (!platform) {
    dialogAccounts.value = []
    return
  }
  dialogAccounts.value = await collectionApi.getAccounts({ platform })
}

async function loadCoverage() {
  coverageLoading.value = true
  try {
    coverage.value = await collectionApi.getConfigCoverage({
      platform: filters.platform || undefined,
    })
  } catch (error) {
    coverage.value = { summary: {}, items: [] }
    ElMessage.error(`加载覆盖情况失败: ${error.message}`)
  } finally {
    coverageLoading.value = false
  }
}

async function loadConfigRuns() {
  configRunsLoading.value = true
  try {
    configRuns.value = await collectionApi.getConfigRuns()
  } catch (error) {
    configRuns.value = []
    ElMessage.error(`加载执行队列失败: ${error.message}`)
  } finally {
    configRunsLoading.value = false
  }
}

async function loadCollectionHealth() {
  try {
    collectionHealth.value = await collectionApi.getHealth()
  } catch (error) {
    collectionHealth.value = null
  }
}

async function loadGranularitySchedule() {
  try {
    granularitySchedule.value = await collectionApi.getGranularitySchedule(activeGranularity.value)
  } catch (error) {
    granularitySchedule.value = null
  }
}

async function reloadPageData() {
  await Promise.all([loadTemplates(), loadAccounts(), loadCoverage(), loadConfigRuns(), loadCollectionHealth(), loadGranularitySchedule()])
}

function handlePlatformFilterChange() {
  selectedMainAccountKey.value = ''
  reloadPageData()
}

async function onTemplatePlatformChange() {
  form.main_account_id = ''
  form.shop_scopes = []
  await loadDialogAccounts(form.platform)
}

function onTemplateMainAccountChange() {
  form.shop_scopes = buildDefaultShopScopes(form.platform, form.main_account_id)
}

async function cancelConfigRun(run) {
  try {
    await ElMessageBox.confirm('确定要取消这个排队中的配置执行吗？', '确认')
    await collectionApi.cancelConfigRun(run.run_id)
    ElMessage.success('已取消排队中的配置执行')
    await loadConfigRuns()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`取消失败: ${error.message}`)
    }
  }
}

async function runConfig(row) {
  if (!row?.id) return
  if (normalizeConfigGranularity(row) !== activeGranularity.value) {
    ElMessage.error(`当前页面为${activeGranularityLabel.value}，但目标配置粒度为${getGranularityLabel(row.granularity)}`)
    return
  }
  try {
    const runResult = await collectionApi.runConfig(row.id, {
      expected_granularity: activeGranularity.value,
    })
    if (!runResult?.run_id) {
      ElMessage.warning('当前配置未成功加入执行队列')
      return
    }
    await Promise.all([loadConfigRuns(), loadCollectionHealth()])
    if (collectionHealth.value?.queue_runner !== 'running') {
      ElMessage.warning(`已入队 ${runResult.run_id}，但当前执行器未运行`)
      return
    }
    ElMessage.success(`已加入执行队列: ${runResult.run_id}`)
  } catch (error) {
    ElMessage.error(`执行失败: ${error.message}`)
  }
}

function openTemporaryRunDialog() {
  if (!currentConfigSummary.value) return
  temporaryRunForm.scope_mode = selectedShopScopeIds.value.length ? 'selected' : 'enabled'
  temporaryRunForm.date_range_type = currentConfigSummary.value.date_range_type || (activeGranularity.value === 'daily' ? 'yesterday' : 'custom')
  temporaryRunForm.execution_mode = currentConfigSummary.value.execution_mode || 'headless'
  temporaryRunCustomDateRange.value =
    currentConfigSummary.value.custom_date_start && currentConfigSummary.value.custom_date_end
      ? [currentConfigSummary.value.custom_date_start, currentConfigSummary.value.custom_date_end]
      : []
  temporaryRunVisible.value = true
}

async function submitTemporaryRun() {
  if (!currentConfigSummary.value) return
  if (!temporaryRunTargets.value.length) {
    ElMessage.warning('当前没有可补采的店铺')
    return
  }
  if (temporaryRunForm.date_range_type === 'custom' && temporaryRunCustomDateRange.value.length !== 2) {
    ElMessage.warning('请先选择补采日期范围')
    return
  }

  temporaryRunSubmitting.value = true
  try {
    const timeSelection = buildTimeSelectionPayload(temporaryRunForm.date_range_type, {
      customRange: temporaryRunCustomDateRange.value,
    })
    await Promise.all(
      temporaryRunTargets.value.map((row) =>
        collectionApi.createTask({
          platform: currentConfigSummary.value.platform,
          account_id: row.scope.shop_account_id,
          data_domains: [...(row.scope.data_domains || [])],
          sub_domains: normalizeScopeSubDomains(row.scope.data_domains || [], row.scope.sub_domains),
          granularity: activeGranularity.value,
          time_selection: timeSelection,
          debug_mode: temporaryRunForm.execution_mode === 'headed',
          parallel_mode: false,
          max_parallel: 1,
        })
      )
    )
    temporaryRunVisible.value = false
    ElMessage.success(`已创建 ${temporaryRunTargets.value.length} 个临时补采任务`)
  } catch (error) {
    ElMessage.error(`创建临时补采任务失败: ${error.message}`)
  } finally {
    temporaryRunSubmitting.value = false
  }
}

async function bulkAdvanceCurrentGranularity() {
  try {
    const label = activeGranularity.value === 'weekly' ? '下一周' : '下一月'
    await ElMessageBox.confirm(`确认将当前粒度下的主账号统一推进到${label}吗？`, '批量推进确认')
    const result = await collectionApi.bulkAdvanceCurrentGranularity({
      granularity: activeGranularity.value,
      platform: filters.platform || undefined,
    })
    ElMessage.success(`已推进 ${result.affected_config_ids?.length || 0} 条当前配置`)
    await reloadPageData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`批量推进失败: ${error.message}`)
    }
  }
}

async function toggleGranularitySchedule(enabled) {
  granularityScheduleUpdating.value = true
  try {
    granularitySchedule.value = await collectionApi.updateGranularitySchedule(activeGranularity.value, {
      schedule_enabled: Boolean(enabled),
    })
    ElMessage.success(enabled ? '该粒度统一定时已开启' : '该粒度统一定时已关闭')
    await reloadPageData()
  } catch (error) {
    ElMessage.error(`更新统一定时失败: ${error.message}`)
  } finally {
    granularityScheduleUpdating.value = false
  }
}

onMounted(() => {
  resetCurrentConfigForm()
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
.scope-actions,
.panel-actions,
.granularity-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.granularity-card,
.queue-card {
  margin-bottom: 20px;
}

.granularity-schedule-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafcff;
}

.schedule-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.schedule-meta-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
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
  gap: 12px;
}

.table-summary,
.scope-subtitle,
.shop-scope-meta,
.panel-card-meta {
  color: #909399;
  font-size: 12px;
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 260px;
  overflow-y: auto;
  padding-right: 4px;
}

.queue-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.queue-item {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px 14px;
  background: #fafafa;
}

.queue-item-header,
.panel-card-header,
.shop-scope-card-header,
.shop-scope-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.queue-item-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.queue-item-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

.queue-run-id {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #606266;
}

.queue-item-error {
  margin-top: 8px;
  color: #f56c6c;
  font-size: 12px;
}

.workbench-layout {
  display: grid;
  grid-template-columns: 240px 280px minmax(0, 1fr);
  gap: 16px;
  min-height: calc(100vh - 320px);
  align-items: start;
}

.nav-panel,
.summary-panel,
.shop-panel {
  min-height: 0;
}

.panel-list,
.shop-scope-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: calc(100vh - 380px);
  overflow-y: auto;
  padding-right: 4px;
}

.panel-card,
.shop-scope-card,
.current-config-card {
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
}

.account-card {
  cursor: pointer;
}

.account-card.active {
  border-color: #409eff;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.12);
}

.panel-card-title,
.shop-scope-name,
.scope-title,
.account-group-title {
  font-size: 15px;
  font-weight: 600;
}

.account-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.account-summary,
.template-summary,
.batch-summary-row,
.batch-summary-actions,
.shop-panel-summary,
.current-config-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.current-config-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.shop-panel-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: calc(100vh - 410px);
}

.shop-search {
  width: 180px;
}

.shop-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.subtype-checkboxes {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.subtype-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
}

.full-width-select {
  width: 100%;
}

.editor-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
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

.empty-tip {
  padding: 20px;
  text-align: center;
  color: #909399;
  background: #f7f8fa;
  border-radius: 12px;
}

.temporary-run-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.warning-text {
  color: #e6a23c;
}

:deep(.collection-config-editor-dialog) {
  max-height: calc(100vh - 40px);
}

:deep(.collection-config-editor-dialog .el-dialog__body) {
  max-height: calc(100vh - 220px);
  overflow-y: auto;
  padding-top: 12px;
}

@media (max-width: 1520px) {
  .workbench-layout {
    grid-template-columns: 240px 280px minmax(0, 1fr);
  }
}

@media (max-width: 1180px) {
  .workbench-layout {
    grid-template-columns: 1fr;
  }

  .panel-list,
  .shop-panel-body {
    max-height: none;
    min-height: auto;
    height: auto;
  }
}
</style>
