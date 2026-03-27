<template>
  <div class="component-versions">
    <div class="page-header">
      <h2>采集组件库</h2>
      <p class="subtitle">管理采集组件版本，A/B测试，快速回滚。只有稳定版本可用于正式采集和定时调度。</p>
    </div>

    <!-- 筛选栏：筛选为空时后端按全选处理 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline>
        <el-form-item label="平台">
          <el-select
            v-model="filterForm.platform"
            placeholder="全部平台"
            clearable
            class="filter-select"
            @change="loadVersions"
          >
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item label="组件类型">
          <el-select
            v-model="filterForm.type"
            placeholder="全部类型"
            clearable
            class="filter-select"
            @change="loadVersions"
          >
            <el-option label="登录" value="login" />
            <el-option label="导航" value="navigation" />
            <el-option label="导出" value="export" />
            <el-option label="日期选择" value="date_picker" />
            <el-option label="店铺切换" value="shop_switch" />
            <el-option label="筛选" value="filters" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filterForm.status"
            placeholder="全部状态"
            clearable
            class="filter-select"
            @change="loadVersions"
          >
            <el-option label="稳定版本" value="stable" />
            <el-option label="测试中" value="testing" />
            <el-option label="已禁用" value="inactive" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadVersions">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button type="success" @click="batchRegisterPythonComponents" :loading="batchRegistering">
            批量注册 Python 组件
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 版本列表 -->
    <el-card shadow="never" class="versions-card">
      <!-- 4.2: 同平台同类型多稳定版冲突提示 -->
      <el-alert
        v-if="multiStableConflicts.length > 0"
        type="warning"
        :title="`存在 ${multiStableConflicts.length} 组多稳定版冲突`"
        :description="multiStableConflictDescription"
        show-icon
        class="multi-stable-alert"
      />
      <el-table 
        v-loading="loading" 
        :data="versions" 
        stripe
        :default-sort="{ prop: 'success_rate', order: 'descending' }"
      >
        <el-table-column prop="component_name" label="组件名称" width="200" fixed>
          <template #default="{ row }">
            <div class="component-name">
              <el-tag size="small" type="info">{{ getPlatformFromName(row.component_name) }}</el-tag>
              <span>{{ getComponentTypeFromName(row.component_name) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="version" label="版本" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_stable ? 'success' : 'info'" size="small">
              v{{ row.version }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="file_path" label="实际执行文件" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="file-path">{{ row.file_path || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag 
              :type="getLogicalTypeTag(getComponentTypeFromName(row.component_name))" 
              size="small"
              effect="plain"
            >
              {{ getLogicalTypeLabel(getComponentTypeFromName(row.component_name)) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <div class="status-badges">
              <el-tag v-if="row.is_stable" type="success" size="small">稳定</el-tag>
              <el-tag v-if="row.is_testing" type="warning" size="small">测试中</el-tag>
              <el-tag v-if="!row.is_active" type="info" size="small">已禁用</el-tag>
              <el-tooltip v-if="hasMultiStableConflict(row)" content="该组件类型存在多个稳定版冲突。正式运行应先清理冲突，只保留一个稳定版。" placement="top">
                <el-icon class="conflict-warning"><WarningFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="成功率" width="150" sortable prop="success_rate">
          <template #default="{ row }">
            <div class="success-rate">
              <el-progress 
                :percentage="Math.round(row.success_rate * 100)" 
                :color="getProgressColor(row.success_rate)"
                :stroke-width="8"
              />
              <span class="rate-text">{{ (row.success_rate * 100).toFixed(1) }}%</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="使用统计" width="200">
          <template #default="{ row }">
            <div class="usage-stats">
              <div class="stat-item">
                <span class="label">总计:</span>
                <span class="value">{{ row.usage_count }}</span>
              </div>
              <div class="stat-item success">
                <span class="label">成功:</span>
                <span class="value">{{ row.success_count }}</span>
              </div>
              <div class="stat-item failed">
                <span class="label">失败:</span>
                <span class="value">{{ row.failure_count }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="A/B测试" width="150">
          <template #default="{ row }">
            <div v-if="row.is_testing" class="ab-test-info">
              <el-tag type="warning" size="small">
                流量: {{ (row.test_ratio * 100).toFixed(0) }}%
              </el-tag>
              <div class="test-time">
                {{ formatDate(row.test_start_at) }} -
                {{ formatDate(row.test_end_at) }}
              </div>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />

        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button 
                v-if="row.is_active"
                type="primary" 
                size="small"
                @click="showTestDialog(row)"
              >
                测试组件
              </el-button>
              <el-button 
                v-if="!row.is_stable && row.is_active" 
                type="success" 
                size="small"
                @click="promoteToStable(row)"
              >
                提升稳定版
              </el-button>
              <el-button 
                v-if="!row.is_testing && row.is_active" 
                type="warning" 
                size="small"
                @click="showABTestDialog(row)"
              >
                A/B测试
              </el-button>
              <el-button 
                v-if="row.is_testing" 
                type="info" 
                size="small"
                @click="stopABTest(row)"
              >
                停止测试
              </el-button>
              <el-button 
                type="danger" 
                size="small"
                @click="toggleActive(row)"
              >
                {{ row.is_active ? '禁用' : '启用' }}
              </el-button>
              <el-button 
                v-if="!row.is_testing && !row.is_active"
                type="danger" 
                size="small"
                plain
                @click="deleteVersion(row)"
              >
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadVersions"
        @current-change="loadVersions"
        style="margin-top: 20px; justify-content: center;"
      />
    </el-card>

    <!-- 测试组件对话框 -->
    <el-dialog
      v-model="testDialogVisible"
      title="测试组件"
      width="900px"
      :close-on-click-modal="false"
    >
      <!-- 测试配置 -->
      <div class="test-header" style="margin-bottom: 20px; padding: 15px; background: #f5f7fa; border-radius: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
          <div>
            <span style="font-weight: 600; margin-right: 10px;">组件:</span>
            <el-tag>{{ currentTestComponent.component_name }}</el-tag>
            <el-tag type="success" style="margin-left: 8px;">v{{ currentTestComponent.version }}</el-tag>
            <span v-if="currentTestComponent.file_path" style="margin-left: 12px; font-size: 12px; color: #909399;">
              执行文件: {{ currentTestComponent.file_path }}
            </span>
          </div>
        </div>
        
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <span style="font-weight: 600;">测试账号:</span>
          <el-select 
            v-model="testAccountId" 
            size="small" 
            style="width: 300px;"
            :disabled="testing"
            placeholder="请选择测试账号"
          >
            <el-option
              v-for="account in testAccounts"
              :key="account.id"
              :label="getAccountLabel(account)"
              :value="account.account_id"
            />
          </el-select>

          <template v-if="isCurrentTestExport">
            <span style="font-weight: 600;">时间方式:</span>
            <el-select
              v-model="testTimeMode"
              size="small"
              style="width: 140px;"
              :disabled="testing"
            >
              <el-option label="快捷时间" value="preset" />
              <el-option label="自定义时间" value="custom" />
            </el-select>

            <template v-if="testTimeMode === 'preset'">
              <span style="font-weight: 600;">快捷时间:</span>
              <el-select
                v-model="testDatePreset"
                size="small"
                style="width: 160px;"
                :disabled="testing"
              >
                <el-option label="今天" value="today" />
                <el-option label="昨天" value="yesterday" />
                <el-option label="近7天" value="last_7_days" />
                <el-option label="近30天" value="last_30_days" />
              </el-select>

              <span style="font-weight: 600;">粒度:</span>
              <el-tag type="info">{{ testDerivedGranularityLabel }}</el-tag>
            </template>

            <template v-else>
              <span style="font-weight: 600;">粒度:</span>
              <el-select
                v-model="testGranularity"
                size="small"
                style="width: 140px;"
                :disabled="testing"
                placeholder="请选择粒度"
              >
                <el-option label="日报" value="daily" />
                <el-option label="周报" value="weekly" />
                <el-option label="月报" value="monthly" />
              </el-select>

              <span style="font-weight: 600;">日期范围:</span>
              <el-date-picker
                v-model="testDateRange"
                type="daterange"
                size="small"
                style="width: 260px;"
                :disabled="testing"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
              />
            </template>

            <template v-if="currentTestComponent.data_domain">
              <span style="font-weight: 600;">数据域:</span>
              <el-tag type="info">{{ currentTestComponent.data_domain }}</el-tag>
            </template>

            <template v-if="requiresCurrentTestSubDomain">
              <span style="font-weight: 600;">子数据域:</span>
              <el-select
                v-model="testSubDomain"
                size="small"
                style="width: 180px;"
                :disabled="testing"
                placeholder="请选择子数据域"
              >
                <el-option
                  v-for="option in currentTestSubDomainOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </template>

            <template v-else-if="currentTestComponent.sub_domain">
              <span style="font-weight: 600;">子数据域:</span>
              <el-tag>{{ currentTestComponent.sub_domain }}</el-tag>
            </template>
          </template>
          
          <el-button 
            type="primary" 
            size="small"
            :loading="testing"
            :disabled="!canStartCurrentTest"
            @click="startComponentTest"
          >
            {{ testing ? '测试中...' : '开始测试' }}
          </el-button>
        </div>
      </div>

      <!-- 测试提示 -->
      <el-alert 
        v-if="!testResult && !testing"
        type="info" 
        :closable="false" 
        style="margin-bottom: 20px;"
      >
        <template #title>
          <div>
            <p style="margin: 0 0 8px 0;">📌 测试说明：</p>
            <p style="margin: 0; font-size: 13px;">1. 点击"开始测试"将打开浏览器窗口（有头模式）</p>
            <p style="margin: 0; font-size: 13px;">2. 您可以观察每个步骤的执行过程</p>
            <p style="margin: 0; font-size: 13px;">3. 测试完成后会自动更新组件统计信息</p>
          </div>
        </template>
      </el-alert>

      <el-alert 
        v-if="testing"
        type="warning" 
        :closable="false" 
        style="margin-bottom: 20px;"
      >
        <template #title>
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>浏览器窗口已打开，正在执行测试...</span>
          </div>
        </template>
      </el-alert>

      <!-- ⭐ v4.7.3: 实时进度显示 -->
      <div v-if="testing && testStatus.testId" class="real-time-progress">
        <el-card style="margin-bottom: 20px;">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>🔄 测试执行中...</span>
              <el-tag v-if="testStatus.testId">测试ID: {{ testStatus.testId.slice(0, 12) }}</el-tag>
            </div>
          </template>
          
          <el-progress 
            :percentage="testStatus.progress" 
            :status="testStatus.progress === 100 ? 'success' : null"
            style="margin-bottom: 15px;"
          />
          
          <el-alert 
            :title="testStatus.currentStep" 
            type="info" 
            :closable="false"
            style="margin-bottom: 15px;"
          />
          
          <div style="max-height: 300px; overflow-y: auto; background: #f5f7fa; padding: 10px; border-radius: 4px;">
            <div 
              v-for="(log, index) in testStatus.logs" 
              :key="index"
              style="margin-bottom: 8px; font-size: 12px; font-family: monospace;"
              :style="{ color: log.level === 'error' ? '#f56c6c' : log.level === 'warning' ? '#e6a23c' : '#606266' }"
            >
              <span style="color: #909399;">[{{ log.time }}]</span>
              {{ log.message }}
            </div>
          </div>
        </el-card>
      </div>

      <!-- 验证码回传：需要验证码时展示截图与输入框 -->
      <div v-if="verificationRequired" class="verification-required-card" style="margin-bottom: 20px;">
        <el-card>
          <template #header>
            <span>需要验证码</span>
          </template>
          <p v-if="verificationRequired.verificationType !== 'otp' && verificationRequired.verificationType !== 'sms' && verificationRequired.verificationType !== 'email_code'" style="margin-bottom: 12px; color: #606266;">
            请根据下方截图输入图形验证码
          </p>
          <p v-else style="margin-bottom: 12px; color: #606266;">
            请输入收到的短信/邮件验证码
          </p>
          <div v-if="verificationRequired.verificationType !== 'otp' && verificationRequired.verificationType !== 'sms' && verificationRequired.verificationType !== 'email_code'" style="margin-bottom: 16px;">
            <img :src="verificationRequired.screenshotUrl" alt="验证码截图" style="max-width: 100%; max-height: 200px; border: 1px solid #dcdfe6; border-radius: 4px;" @error="($event.target).style.display='none'" />
          </div>
          <el-input
            v-model="verificationInput"
            :placeholder="verificationRequired.verificationType === 'otp' || verificationRequired.verificationType === 'sms' || verificationRequired.verificationType === 'email_code' ? '请输入短信/邮件验证码' : '请输入验证码'"
            style="max-width: 280px; margin-right: 12px;"
            clearable
            @keyup.enter="submitVerification"
          />
          <el-button type="primary" :loading="verificationSubmitting" @click="submitVerification">
            提交
          </el-button>
        </el-card>
      </div>

      <!-- 测试结果（复用测试结果组件样式） -->
      <div v-if="testResult" class="test-results">
        <!-- ⭐ 验证标准失败警告 -->
        <el-alert 
          v-if="testResult.error && testResult.steps_failed === 0"
          type="warning" 
          :closable="false" 
          style="margin-bottom: 20px;"
        >
          <template #title>
            <div>
              <p style="margin: 0 0 8px 0; font-weight: bold;">⚠️ 所有步骤执行成功，但验证标准未通过</p>
              <p style="margin: 0; font-size: 13px;">错误信息：{{ testResult.error }}</p>
              <p v-if="testResult.phase" style="margin: 4px 0 0 0; font-size: 12px;">
                失败阶段：{{ testResult.phase }}{{ testResult.phase_component_name ? ' / ' + testResult.phase_component_name : '' }}{{ testResult.phase_component_version ? ' v' + testResult.phase_component_version : '' }}
              </p>
              <p style="margin: 8px 0 0 0; font-size: 12px; color: #909399;">
                提示：可能是URL不匹配或必需元素未找到。请检查组件的 success_criteria 配置。
              </p>
            </div>
          </template>
        </el-alert>

        <!-- 总体结果 -->
        <div style="display: flex; gap: 20px; margin-bottom: 20px;">
          <el-statistic title="总耗时" :value="testResult.duration_ms" suffix="ms" />
          <el-statistic 
            title="步骤成功率" 
            :value="testResult.success_rate" 
            suffix="%" 
            :value-style="{ color: testResult.success_rate >= 90 ? '#67c23a' : '#f56c6c' }"
          />
          <el-statistic title="成功步骤" :value="testResult.steps_passed" :suffix="`/ ${testResult.steps_total}`" />
        </div>

        <!-- 步骤执行列表 -->
        <el-timeline>
          <el-timeline-item 
            v-for="(step, index) in testResult.step_results" 
            :key="index"
            :type="getStepStatusType(step.status)"
          >
            <div class="step-result">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <el-tag :type="getStepStatusType(step.status)" size="small">
                  步骤 {{ index + 1 }}: {{ step.action }}
                </el-tag>
                <span style="color: #909399; font-size: 12px;">{{ step.duration_ms }}ms</span>
              </div>
              
              <!-- 失败详情 -->
              <div v-if="step.status === 'failed'">
                <el-alert type="error" :closable="false" style="margin-bottom: 10px;">
                  <template #title>{{ step.error }}</template>
                </el-alert>
                
                <!-- 失败截图 -->
                <el-image 
                  v-if="step.screenshot_base64"
                  :src="`data:image/png;base64,${step.screenshot_base64}`"
                  :preview-src-list="[`data:image/png;base64,${step.screenshot_base64}`]"
                  fit="contain"
                  style="max-width: 400px; cursor: pointer; border: 1px solid #dcdfe6;"
                  :preview-teleported="true"
                />
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
      
      <template #footer>
        <div style="display: flex; justify-content: space-between;">
          <el-button @click="testDialogVisible = false">关闭</el-button>
          <el-button 
            v-if="testResult"
            type="primary" 
            @click="startComponentTest"
            :loading="testing"
          >
            🔄 重新测试
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- A/B测试对话框 -->
    <el-dialog
      v-model="abTestDialogVisible"
      title="启动A/B测试"
      width="500px"
    >
      <el-form :model="abTestForm" label-width="100px">
        <el-form-item label="组件">
          <el-input :value="abTestForm.component_name" disabled />
        </el-form-item>
        <el-form-item label="版本">
          <el-input :value="abTestForm.version" disabled />
        </el-form-item>
        <el-form-item label="测试流量">
          <el-slider 
            v-model="abTestForm.test_ratio" 
            :min="5" 
            :max="50" 
            :step="5"
            :marks="{ 5: '5%', 10: '10%', 20: '20%', 30: '30%', 50: '50%' }"
            show-stops
          />
          <div class="slider-tip">建议从10%开始，逐步提升</div>
        </el-form-item>
        <el-form-item label="测试时长">
          <el-input-number v-model="abTestForm.duration_days" :min="1" :max="30" />
          <span style="margin-left: 8px;">天</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="abTestDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="startABTest">
          启动测试
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Loading, WarningFilled } from '@element-plus/icons-vue'
import api from '@/api'
// v4.7.4: 移除 WebSocket，改用 HTTP 轮询

// 数据
const loading = ref(false)
const versions = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const batchRegistering = ref(false)

const filterForm = reactive({
  platform: '',
  type: '',
  status: ''
})

const abTestDialogVisible = ref(false)
const submitting = ref(false)
const abTestForm = reactive({
  id: null,
  component_name: '',
  version: '',
  test_ratio: 10,
  duration_days: 7
})

// 测试组件相关状态
const testDialogVisible = ref(false)
const testing = ref(false)
const testAccountId = ref('')
const testTimeMode = ref('preset')
const testDatePreset = ref('today')
const testGranularity = ref('daily')
const testDateRange = ref([])
const testSubDomain = ref('')
const testAccounts = ref([])
const testResult = ref(null)
const currentTestComponent = ref({
  id: null,
  component_name: '',
  version: '',
  file_path: '',
  logical_type: '',
  data_domain: '',
  sub_domain: ''
})

// ⭐ v4.7.3: 实时进度状态
const testStatus = ref({
  testId: null,
  versionId: null,
  currentStep: '准备测试环境...',
  progress: 0,
  logs: []
})

// 验证码回传：当 status 为 verification_required 时展示
const verificationRequired = ref(null) // { versionId, testId, verificationType, screenshotUrl }
const verificationInput = ref('')
const verificationSubmitting = ref(false)

const SERVICE_SUB_DOMAIN_OPTIONS = [
  { label: '智能客服', value: 'ai_assistant' },
  { label: '人工客服', value: 'agent' }
]

const parseComponentMeta = (name) => {
  const [platform = '', raw = ''] = (name || '').split('/')
  const meta = {
    platform,
    raw,
    logicalType: raw || 'unknown',
    dataDomain: '',
    subDomain: ''
  }

  if (raw === 'login' || raw.endsWith('_login')) {
    meta.logicalType = 'login'
    return meta
  }
  if (raw === 'navigation') {
    meta.logicalType = 'navigation'
    return meta
  }
  if (raw === 'date_picker') {
    meta.logicalType = 'date_picker'
    return meta
  }
  if (raw === 'shop_switch') {
    meta.logicalType = 'shop_switch'
    return meta
  }
  if (raw === 'filters') {
    meta.logicalType = 'filters'
    return meta
  }
  if (raw === 'export') {
    meta.logicalType = 'export'
    return meta
  }
  if (raw.endsWith('_export')) {
    meta.logicalType = 'export'
    const domainParts = raw.slice(0, -7).split('_').filter(Boolean)
    if (domainParts.length > 0) {
      meta.dataDomain = domainParts[0]
      meta.subDomain = domainParts.slice(1).join('_')
    }
    return meta
  }
  return meta
}

const PRESET_GRANULARITY_MAP = {
  today: 'daily',
  yesterday: 'daily',
  last_7_days: 'weekly',
  last_30_days: 'monthly'
}

const GRANULARITY_LABEL_MAP = {
  daily: '日报',
  weekly: '周报',
  monthly: '月报'
}

const isCurrentTestExport = computed(() => currentTestComponent.value.logical_type === 'export')
const requiresCurrentTestSubDomain = computed(() => {
  return isCurrentTestExport.value
    && currentTestComponent.value.data_domain === 'services'
    && !currentTestComponent.value.sub_domain
})
const currentTestSubDomainOptions = computed(() => {
  if (currentTestComponent.value.data_domain === 'services') {
    return SERVICE_SUB_DOMAIN_OPTIONS
  }
  return []
})
const testEffectiveGranularity = computed(() => {
  if (testTimeMode.value === 'preset') {
    return PRESET_GRANULARITY_MAP[testDatePreset.value] || 'daily'
  }
  return testGranularity.value
})

const testDerivedGranularityLabel = computed(() => {
  return GRANULARITY_LABEL_MAP[testEffectiveGranularity.value] || testEffectiveGranularity.value
})

const canStartCurrentTest = computed(() => {
  if (!testAccountId.value) return false
  if (!isCurrentTestExport.value) return true
  if (testTimeMode.value === 'preset') {
    if (!testDatePreset.value) return false
  } else {
    if (!testGranularity.value) return false
    if (!Array.isArray(testDateRange.value) || testDateRange.value.length !== 2) return false
  }
  if (requiresCurrentTestSubDomain.value && !testSubDomain.value) return false
  return true
})

// 4.2: 同平台同类型多稳定版冲突（基于当前列表计算）
const multiStableConflicts = computed(() => {
  const map = new Map()
  for (const row of versions.value) {
    const platform = getPlatformFromName(row.component_name)
    const compType = getComponentTypeFromName(row.component_name)
    const key = `${platform}/${compType}`
    if (row.is_stable) {
      map.set(key, (map.get(key) || 0) + 1)
    }
  }
  return Array.from(map.entries())
    .filter(([, count]) => count > 1)
    .map(([key]) => {
      const [p, t] = key.split('/')
      return { platform: p, componentType: t }
    })
})
const multiStableConflictDescription = computed(() => {
  if (multiStableConflicts.value.length === 0) return ''
  return '以下组件类型存在多个稳定版冲突。正式运行前应只保留一个稳定版：' +
    multiStableConflicts.value.map(({ platform, componentType }) => `${platform}/${componentType}`).join('、')
})
const hasMultiStableConflict = (row) => {
  const platform = getPlatformFromName(row.component_name)
  const compType = getComponentTypeFromName(row.component_name)
  return multiStableConflicts.value.some(
    (c) => c.platform === platform && c.componentType === compType
  )
}

// 方法
// ⭐ v4.19.0修复：添加超时机制和后台刷新支持，避免数据同步期间阻塞
const loadVersions = async (showLoading = true) => {
  // 防重复加载
  if (loading.value && showLoading) {
    return
  }

  if (showLoading) {
    loading.value = true
  }

  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      platform: filterForm.platform || undefined,
      component_type: filterForm.type || undefined,
      status: filterForm.status || undefined
    }
    
    // ⭐ v4.19.0新增：添加超时机制，避免长时间阻塞
    const API_TIMEOUT = 10000 // 10秒超时
    
    const res = await Promise.race([
      api.getComponentVersions(params),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('加载组件版本列表超时')), API_TIMEOUT)
      )
    ])
    
    versions.value = res.data
    total.value = res.total
    
  } catch (error) {
    if (error.message !== '加载组件版本列表超时') {
      console.error('加载组件版本失败:', error)
      if (showLoading) {
        ElMessage.error('加载失败: ' + error.message)
      }
    } else {
      console.warn('加载组件版本列表超时，但可能仍在后台加载')
    }
  } finally {
    if (showLoading) {
      loading.value = false
    }
  }
}

const showABTestDialog = (row) => {
  abTestForm.id = row.id
  abTestForm.component_name = row.component_name
  abTestForm.version = row.version
  abTestForm.test_ratio = 10
  abTestForm.duration_days = 7
  abTestDialogVisible.value = true
}

const startABTest = async () => {
  submitting.value = true
  try {
    await api.startABTest(abTestForm.id, {
      test_ratio: abTestForm.test_ratio / 100,
      duration_days: abTestForm.duration_days
    })
    
    ElMessage.success('A/B测试已启动')
    abTestDialogVisible.value = false
    loadVersions(false) // ⭐ v4.19.0修复：后台刷新，不显示loading
  } catch (error) {
    ElMessage.error('启动失败: ' + error.message)
  } finally {
    submitting.value = false
  }
}

const stopABTest = async (row) => {
  try {
    await ElMessageBox.confirm('确定停止A/B测试吗？', '确认', {
      type: 'warning'
    })
    
    await api.stopABTest(row.id)
    
    ElMessage.success('已停止A/B测试')
    loadVersions(false) // ⭐ v4.19.0修复：后台刷新，不显示loading
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('操作失败: ' + error.message)
    }
  }
}

const promoteToStable = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定将 ${row.component_name} v${row.version} 提升为稳定版本吗？`,
      '确认',
      { type: 'warning' }
    )
    
    await api.promoteToStable(row.id)
    
    ElMessage.success('已提升为稳定版本')
    loadVersions(false) // ⭐ v4.19.0修复：后台刷新，不显示loading
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('操作失败: ' + error.message)
    }
  }
}

const toggleActive = async (row) => {
  const action = row.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定${action}该版本吗？`, '确认', {
      type: 'warning'
    })
    
    await api.updateComponentVersion(row.id, {
      is_active: !row.is_active
    })
    
    ElMessage.success(`已${action}`)
    loadVersions(false) // ⭐ v4.19.0修复：后台刷新，不显示loading
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('操作失败: ' + error.message)
    }
  }
}

const deleteVersion = async (row) => {
  try {
    let message = `确定删除 ${row.component_name} v${row.version} 吗？`
    if (row.is_stable) {
      const others = versions.value.filter(
        (v) => v.component_name === row.component_name && v.id !== row.id
      )
      if (others.length > 0) {
        message += '\n\n此为稳定版，删除后建议将其他版本提升为稳定版。'
      }
    }
    message += '\n\n若为该组件的最后一条版本记录，将同时删除磁盘上的组件文件。'
    await ElMessageBox.confirm(message, '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger'
    })
    
    await api.deleteComponentVersion(row.id)
    // 乐观更新：立即从列表移除，避免删除后仍显示
    versions.value = versions.value.filter((v) => v.id !== row.id)
    total.value = Math.max(0, (total.value || 0) - 1)
    ElMessage.success('版本已删除')
    loadVersions(false) // 后台刷新以同步服务端状态
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + (error.message || error))
    }
  }
}

// 工具函数
const getPlatformFromName = (name) => {
  return parseComponentMeta(name).platform || 'unknown'
}

const getComponentTypeFromName = (name) => {
  return parseComponentMeta(name).logicalType || 'unknown'
}

const getProgressColor = (rate) => {
  if (rate >= 0.95) return '#67c23a'
  if (rate >= 0.85) return '#e6a23c'
  return '#f56c6c'
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('zh-CN')
}

const formatDateTime = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

const getLogicalTypeLabel = (compPart) => {
  if (!compPart) return '未知'
  if (compPart === 'login') return '登录'
  if (compPart === 'navigation') return '导航'
  if (compPart === 'export') return '导出'
  if (compPart === 'date_picker') return '日期'
  if (compPart === 'shop_switch') return '店铺'
  if (compPart === 'filters') return '筛选'
  return compPart
}
const getLogicalTypeTag = (compPart) => {
  if (compPart === 'login') return 'danger'
  if (compPart === 'navigation') return 'primary'
  if (compPart === 'export') return 'success'
  return 'info'
}

// 批量注册 Python 组件
const batchRegisterPythonComponents = async () => {
  try {
    await ElMessageBox.confirm(
      '此操作将扫描 modules/platforms/ 下所有 Python 组件并注册到版本管理系统。已存在的组件将被跳过。是否继续？',
      '批量注册 Python 组件',
      { type: 'info' }
    )
    
    batchRegistering.value = true
    
    const response = await api.batchRegisterPythonComponents()
    
    // 显示注册结果
    const message = `注册完成！\n已注册: ${response.registered_count}\n已跳过: ${response.skipped_count}\n错误: ${response.error_count}`
    
    if (response.error_count > 0) {
      ElMessage.warning(message)
    } else {
      ElMessage.success(message)
    }
    
    // 刷新版本列表
    await loadVersions(false) // ⭐ v4.19.0修复：后台刷新，不显示loading
    
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量注册失败:', error)
      ElMessage.error('批量注册失败: ' + (error.message || error))
    }
  } finally {
    batchRegistering.value = false
  }
}

// 测试组件方法
const showTestDialog = async (row) => {
  const meta = parseComponentMeta(row.component_name)
  currentTestComponent.value = {
    id: row.id,
    component_name: row.component_name,
    version: row.version,
    file_path: row.file_path,
    logical_type: meta.logicalType,
    data_domain: meta.dataDomain,
    sub_domain: meta.subDomain
  }
  
  testDialogVisible.value = true
  testAccountId.value = ''
  testTimeMode.value = 'preset'
  testDatePreset.value = 'today'
  testGranularity.value = 'daily'
  testDateRange.value = []
  testSubDomain.value = meta.subDomain || ''
  testResult.value = null
  testing.value = false
  
  // 加载账号列表
  await loadTestAccounts(row.component_name)
}

// 格式化账号显示标签
const getAccountLabel = (account) => {
  if (!account) return '未知账号'
  
  // 优先显示：店铺名称 (账号ID)
  const storeName = account.store_name || account.name || account.account_id
  const accountId = account.account_id || account.id
  
  // 如果有店铺区域，也显示出来
  if (account.shop_region) {
    return `${storeName} (${accountId}) - ${account.shop_region}`
  }
  
  return `${storeName} (${accountId})`
}

const loadTestAccounts = async (componentName) => {
  try {
    // 从组件名称提取平台
    const platform = componentName.split('/')[0]
    
    console.log('[DEBUG] Loading accounts for platform:', platform, 'from component:', componentName)
    
    // 加载该平台的账号
    const accountsApi = await import('@/api/accounts')
    // BUG FIX: 方法名从getAccounts改为listAccounts
    const response = await accountsApi.default.listAccounts({
      platform: platform,
      enabled: true
    })
    
    console.log('[DEBUG] API response:', response)
    console.log('[DEBUG] API response type:', Array.isArray(response) ? 'array' : typeof response)
    
    // BUG FIX: response已经是数组，不需要.data
    testAccounts.value = response || []
    
    console.log('[DEBUG] Final testAccounts:', testAccounts.value)
    console.log('[DEBUG] testAccounts count:', testAccounts.value.length)
  } catch (error) {
    console.error('加载账号列表失败:', error)
    ElMessage.error('加载账号列表失败: ' + error.message)
    testAccounts.value = []
  }
}

const startComponentTest = async () => {
  if (!testAccountId.value) {
    ElMessage.warning('请选择测试账号')
    return
  }
  if (isCurrentTestExport.value) {
    if (testTimeMode.value === 'preset') {
      if (!testDatePreset.value) {
        ElMessage.warning('请选择快捷时间')
        return
      }
    } else {
      if (!testGranularity.value || !Array.isArray(testDateRange.value) || testDateRange.value.length !== 2) {
        ElMessage.warning('请选择自定义时间范围和粒度')
        return
      }
    }
    if (requiresCurrentTestSubDomain.value && !testSubDomain.value) {
      ElMessage.warning('请选择子数据域')
      return
    }
  }
  
  try {
    testing.value = true
    testResult.value = null
    
    // ⭐ v4.7.3: 重置实时进度状态
    testStatus.value = {
      testId: null,
      versionId: currentTestComponent.value.id,
      currentStep: '正在启动测试...',
      progress: 0,
      logs: []
    }
    verificationRequired.value = null
    verificationInput.value = ''
    
    ElMessage.info({
      message: '正在打开浏览器窗口，请稍候...',
      duration: 3000
    })
    
    const payload = {
      account_id: testAccountId.value
    }
    if (isCurrentTestExport.value) {
      payload.granularity = testEffectiveGranularity.value
      payload.time_mode = testTimeMode.value
      if (testTimeMode.value === 'preset') {
        payload.date_preset = testDatePreset.value
      } else {
        payload.start_date = testDateRange.value[0]
        payload.end_date = testDateRange.value[1]
      }
      if (requiresCurrentTestSubDomain.value && testSubDomain.value) {
        payload.sub_domain = testSubDomain.value
      }
    }

    const response = await api.testComponentVersion(currentTestComponent.value.id, payload)
    
    // ⭐ v4.7.4: 处理后台运行模式（HTTP 轮询）
    if (response.test_id) {
      // 测试在后台运行，通过 HTTP 轮询接收进度
      testStatus.value.testId = response.test_id
      testStatus.value.versionId = currentTestComponent.value.id
      startPollingTestStatus(response.test_id, currentTestComponent.value.id)
      
      // 显示启动成功消息
      if (response.success) {
        ElMessage.success({
          message: response.message || '测试已启动，请查看实时进度',
          duration: 3000
        })
      } else {
        ElMessage.error({
          message: response.message || '测试启动失败',
          duration: 5000
        })
        testing.value = false
      }
    } else if (response.test_result) {
      // ⭐ 兼容旧格式：直接返回测试结果（同步执行）
      testResult.value = response.test_result
      testing.value = false
      
      if (response.success) {
        ElMessage.success({
          message: `测试通过！成功率：${response.test_result.success_rate}%`,
          duration: 3000
        })
      } else {
        // 测试失败时也要显示详细步骤
        // ⭐ 区分步骤失败和验证标准失败
        if (response.test_result.steps_failed > 0) {
          ElMessage.error({
            message: `测试失败：${response.test_result.steps_failed} 个步骤执行失败。请查看下方详情`,
            duration: 5000
          })
        } else if (response.test_result.error) {
          ElMessage.warning({
            message: `测试未通过：步骤执行成功，但验证标准未满足（${response.test_result.error}）`,
            duration: 5000
          })
        } else {
          ElMessage.warning({
            message: '测试失败。请查看下方步骤详情',
            duration: 5000
          })
        }
      }
        
      // 刷新版本列表（更新统计信息）
      loadVersions(false) // ⭐ v4.19.0修复：后台刷新，不显示loading
    } else {
      // ⭐ 既没有 test_id 也没有 test_result（异常情况）
      testing.value = false
      ElMessage.error({
        message: response.message || '测试启动失败：未收到有效响应',
        duration: 5000
      })
    }
  } catch (error) {
    console.error('组件测试失败:', error)
    ElMessage.error('组件测试失败: ' + error.message)
  } finally {
    // 注意：如果使用轮询，testing 状态将由轮询回调控制
    if (!testStatus.value.testId) {
      testing.value = false
    }
  }
}

// ⭐ v4.7.4: HTTP 轮询获取测试进度（替代 WebSocket）
// 4.5: 轮询生命周期治理（完成/失败/关弹窗/卸载时停止；连续异常与整体超时）
let pollingInterval = null
const POLL_INTERVAL_MS = 1000
const POLL_MAX_CONSECUTIVE_ERRORS = 5
const POLL_OVERALL_TIMEOUT_MS = 10 * 60 * 1000 // 10 分钟

const stopPollingTestStatus = () => {
  if (pollingInterval) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }
}

const startPollingTestStatus = (testId, versionId) => {
  stopPollingTestStatus()
  const startedAt = Date.now()
  let consecutiveErrors = 0

  pollingInterval = setInterval(async () => {
    try {
      if (Date.now() - startedAt > POLL_OVERALL_TIMEOUT_MS) {
        stopPollingTestStatus()
        testing.value = false
        ElMessage.warning({ message: '测试状态轮询超时，请关闭弹窗后重试', duration: 5000 })
        return
      }
      const response = await api.getTestStatus(versionId, testId)
      consecutiveErrors = 0

      testStatus.value.progress = response.progress || 0
      testStatus.value.currentStep = response.current_step || '执行中...'

      if (response.step_index > 0) {
        const logMessage = `步骤 ${response.step_index}/${response.step_total}: ${response.current_step}`
        const lastLog = testStatus.value.logs[testStatus.value.logs.length - 1]
        if (!lastLog || lastLog.message !== logMessage) {
          testStatus.value.logs.push({
            time: new Date().toLocaleTimeString('zh-CN'),
            level: 'info',
            message: logMessage
          })
        }
      }

      if (response.status === 'verification_required') {
        verificationRequired.value = {
          versionId,
          testId,
          verificationType: response.verification_type || 'graphical_captcha',
          screenshotUrl: api.getTestVerificationScreenshotUrl(versionId, testId)
        }
      }

      if (response.status === 'completed' || response.status === 'failed') {
        verificationRequired.value = null
        if (response.verification_timeout) {
          ElMessage.warning({ message: '验证码输入超时', duration: 5000 })
        }
        stopPollingTestStatus()
        testing.value = false
        testStatus.value.progress = 100
        testStatus.value.currentStep = response.status === 'completed' ? '测试完成' : '测试失败'

        if (response.test_result) {
          testResult.value = {
            status: response.test_result.status,
            steps_total: response.test_result.steps_total,
            steps_passed: response.test_result.steps_passed,
            steps_failed: response.test_result.steps_failed,
            duration_ms: response.test_result.duration_ms,
            success_rate: response.test_result.success_rate || 0,
            error: response.test_result.error,
            step_results: response.test_result.step_results || [],
            phase: response.phase,
            phase_component_name: response.phase_component_name,
            phase_component_version: response.phase_component_version
          }
        }

        await loadVersions(false)

        const testPassed = response.status === 'completed' &&
                          response.test_result &&
                          response.test_result.status === 'passed' &&
                          !response.test_result.error

        if (testPassed) {
          const successRate = response.test_result.success_rate || 100
          ElMessage.success({
            message: `测试通过！成功率：${successRate}%`,
            duration: 3000
          })
        } else {
          let errorMsg = '测试失败'
          if (response.test_result && response.test_result.error) {
            errorMsg = `测试失败: ${response.test_result.error}`
          } else if (response.error) {
            errorMsg = `测试失败: ${response.error}`
          } else if (response.test_result && response.test_result.steps_failed > 0) {
            errorMsg = `测试失败: ${response.test_result.steps_failed} 个步骤失败`
          }
          if (response.phase) {
            errorMsg += ` [阶段: ${response.phase}${response.phase_component_name ? ' / ' + response.phase_component_name : ''}${response.phase_component_version ? ' v' + response.phase_component_version : ''}]`
          }
          ElMessage.error({
            message: errorMsg,
            duration: 5000
          })
        }
        if (response.stats_update_error) {
          ElMessage.warning({
            message: '测试已执行完成，但版本统计更新失败，请稍后刷新列表',
            duration: 5000
          })
        }
      }
    } catch (error) {
      console.error('轮询测试状态失败:', error)
      consecutiveErrors += 1
      if (consecutiveErrors >= POLL_MAX_CONSECUTIVE_ERRORS) {
        stopPollingTestStatus()
        testing.value = false
        ElMessage.warning({
          message: `连续 ${POLL_MAX_CONSECUTIVE_ERRORS} 次轮询失败，已停止。请检查网络后关闭弹窗重试。`,
          duration: 5000
        })
      }
    }
  }, POLL_INTERVAL_MS)
}

// 验证码回传：用户输入后提交
const submitVerification = async () => {
  const v = verificationRequired.value
  if (!v || !verificationInput.value.trim()) return
  verificationSubmitting.value = true
  try {
    const isOtp = ['otp', 'sms', 'email_code'].includes((v.verificationType || '').toLowerCase())
    await api.resumeTest(v.versionId, v.testId, isOtp
      ? { otp: verificationInput.value.trim() }
      : { captcha_code: verificationInput.value.trim() }
    )
    ElMessage.success('验证码已提交，测试将继续执行')
    verificationRequired.value = null
    verificationInput.value = ''
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message || '提交失败')
  } finally {
    verificationSubmitting.value = false
  }
}

// 4.5: 关弹窗时停止轮询
watch(testDialogVisible, (visible) => {
  if (!visible) stopPollingTestStatus()
})
// 组件卸载时清理轮询
onBeforeUnmount(() => {
  stopPollingTestStatus()
})

const getStepStatusType = (status) => {
  const types = {
    'passed': 'success',
    'failed': 'danger',
    'running': 'warning',
    'pending': 'info'
  }
  return types[status] || 'info'
}

// 生命周期
// ⭐ v4.19.0修复：首次加载显示loading，后续支持后台刷新
onMounted(() => {
  loadVersions(true) // 首次加载显示loading
})
</script>

<style scoped>
.component-versions {
  padding: 20px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #303133;
}

.subtitle {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.filter-card {
  margin-bottom: 20px;
}

.multi-stable-alert {
  margin-bottom: 12px;
}

.conflict-warning {
  margin-left: 4px;
  color: var(--el-color-warning);
  vertical-align: middle;
}

/* 筛选框最小宽度，便于看清已选内容；空选时后端按全选处理 */
.filter-card .filter-select {
  min-width: 160px;
}

.component-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-badges {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.success-rate {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rate-text {
  font-weight: 600;
  min-width: 50px;
}

.usage-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.stat-item .label {
  color: #909399;
}

.stat-item.success .value {
  color: #67c23a;
  font-weight: 600;
}

.stat-item.failed .value {
  color: #f56c6c;
  font-weight: 600;
}

.overview-cards {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-card {
  min-width: 140px;
  text-align: center;
}

.stat-card .stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.stat-card .stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.ab-test-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.test-time {
  font-size: 11px;
  color: #909399;
}

.text-muted {
  color: #c0c4cc;
}

.slider-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>

