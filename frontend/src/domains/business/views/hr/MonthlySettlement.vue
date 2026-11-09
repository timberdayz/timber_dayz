<template>
  <div class="monthly-settlement erp-page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">月度结算单</h1>
        <p class="page-subtitle">
          一个页面看清这个月结算的全貌：本页所有金额直接取自后端结算口径，与工资单实发一致，前端不做任何二次计算。
        </p>
      </div>
    </div>

    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-date-picker
          v-model="yearMonth"
          type="month"
          value-format="YYYY-MM"
          placeholder="选择月份"
          style="width: 180px;"
        />
        <el-button type="primary" :loading="loading" @click="loadSettlement">查询</el-button>
        <el-button :loading="loading" @click="loadSettlement">刷新</el-button>
        <span class="filter-hint">结算月份：{{ yearMonth || '未选择' }}</span>
      </div>
    </el-card>

    <el-alert
      v-if="errorMessage"
      type="error"
      show-icon
      :closable="false"
      :title="errorMessage"
      style="margin-bottom: 16px;"
    />

    <el-skeleton v-if="loading && !settlement" :rows="8" animated />

    <template v-else-if="settlement">
      <!-- 是否可结算 -->
      <div
        class="settlement-banner"
        :class="settlementReady ? 'settlement-banner--ready' : 'settlement-banner--blocked'"
      >
        <div class="settlement-banner__head">
          <el-tag :type="settlementReady ? 'success' : 'warning'" size="large" effect="dark">
            {{ settlementReady ? '可结算' : '暂不可结算' }}
          </el-tag>
          <span class="settlement-banner__title">结算月份 {{ settlement.year_month || yearMonth }}</span>
        </div>
        <div class="settlement-banner__text">
          {{
            settlementReady
              ? '本月没有待补项，结算数据已就绪。'
              : '本月还有 ' + (summary.pending_count || 0) + ' 项待补数据，补齐后才能完成整月结算。'
          }}
        </div>
      </div>

      <!-- 汇总 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-card__label">员工总数</div>
          <div class="stat-card__value">{{ summary.employee_count ?? 0 }}</div>
          <div class="stat-card__hint">本月出现在结算口径里的员工</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">正式参与考核</div>
          <div class="stat-card__value">{{ summary.formal_count ?? 0 }}</div>
          <div class="stat-card__hint">考核状态为「正常参与考核」</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">不参与考核</div>
          <div class="stat-card__value">{{ summary.not_participating_count ?? 0 }}</div>
          <div class="stat-card__hint">不参与考核，不阻断整月结算</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">待处理</div>
          <div class="stat-card__value stat-card__value--warn">{{ summary.pending_count ?? 0 }}</div>
          <div class="stat-card__hint">待补绩效数据的人数</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">提成合计</div>
          <div class="stat-card__value">{{ formatMoney(summary.total_commission) }}</div>
          <div class="stat-card__hint">员工表逐人提成合计</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">绩效工资合计</div>
          <div class="stat-card__value">{{ formatMoney(summary.total_performance_salary) }}</div>
          <div class="stat-card__hint">员工表逐人绩效工资合计</div>
        </div>
        <div class="stat-card stat-card--highlight">
          <div class="stat-card__label">实发合计</div>
          <div class="stat-card__value">{{ formatMoney(summary.total_net_salary) }}</div>
          <div class="stat-card__hint">工资单实发总额，与本页各行一致</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">工资单已确认</div>
          <div class="stat-card__value">{{ summary.payroll_confirmed_count ?? 0 }}</div>
          <div class="stat-card__hint">草稿 {{ summary.payroll_draft_count ?? 0 }} 张</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">店铺总数</div>
          <div class="stat-card__value">{{ summary.shop_count ?? 0 }}</div>
          <div class="stat-card__hint">
            亏损 {{ summary.loss_shop_count ?? 0 }} 家 · 不参与考核 {{ summary.not_applicable_shop_count ?? 0 }} 家
          </div>
        </div>
      </div>

      <!-- 待办 / 阻断项 -->
      <el-card v-if="blockingIssueRows.length" shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span>待办 / 阻断项</span>
            <span class="section-header__hint">共 {{ blockingIssueRows.length }} 项，补齐后本月才能完成结算</span>
          </div>
        </template>
        <el-table :data="blockingIssueRows" border stripe>
          <el-table-column prop="employee_code" label="员工编号" width="140" />
          <el-table-column prop="employee_name" label="姓名" width="140" />
          <el-table-column label="状态" width="150">
            <template #default="{ row }">
              <el-tag v-if="row.status_tag" :type="row.status_tag.type" size="small">
                {{ row.status_tag.label }}
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="缺什么" min-width="200" />
          <el-table-column prop="action" label="去哪补" min-width="280" />
        </el-table>
      </el-card>

      <!-- 员工结算明细 -->
      <el-card v-if="hasContent" shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span>员工结算明细</span>
            <span class="section-header__hint">实发金额即工资单实发金额</span>
          </div>
        </template>
        <el-table
          v-loading="loading"
          :data="employeeRows"
          border
          stripe
          empty-text="本月没有员工结算记录"
        >
          <el-table-column label="员工" min-width="150" fixed="left">
            <template #default="{ row }">
              <div class="cell-stack">
                <span class="cell-stack__main">{{ row.employee_name }}</span>
                <span class="cell-stack__sub">{{ row.employee_code }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="绩效分" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip :content="performanceHint(row)" placement="top">
                <span>{{ formatScore(row.performance_score) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="分数档位系数" width="120" align="right">
            <template #default="{ row }">
              <el-tooltip :content="SCORE_COEFFICIENT_TOOLTIP" placement="top">
                <span>{{ formatCoefficient(row.score_coefficient) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="绩效工资系数" width="130" align="right">
            <template #default="{ row }">
              <el-tooltip :content="PERFORMANCE_SALARY_COEFFICIENT_TOOLTIP" placement="top">
                <span>{{ formatCoefficient(row.performance_salary_coefficient) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="考核状态" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.status_tag" :type="row.status_tag.type" size="small">
                {{ row.status_tag.label }}
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="提成" width="130" align="right">
            <template #default="{ row }">
              <el-tooltip :content="commissionHint(row)" placement="top">
                <span>{{ formatMoney(row.commission_amount) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="提成构成" min-width="260">
            <template #default="{ row }">
              <el-tooltip :content="shopBreakHint(row)" placement="top">
                <span class="cell-stack">
                  <span class="cell-stack__main">{{ shopBreakSummary(row) }}</span>
                  <span class="cell-stack__sub">按店各算各的结算系数</span>
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="绩效工资" width="130" align="right">
            <template #default="{ row }">{{ formatMoney(row.performance_salary) }}</template>
          </el-table-column>
          <el-table-column label="实发" width="140" align="right">
            <template #default="{ row }">
              <span class="amount-strong">{{ formatMoney(row.net_salary) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="工资单状态" width="130">
            <template #default="{ row }">
              <el-tooltip :content="payrollHint(row)" placement="top">
                <el-tag :type="row.payroll_tag.type" size="small">{{ row.payroll_tag.label }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="卡住原因" min-width="240">
            <template #default="{ row }">
              <div v-if="row.blocking_reason" class="cell-stack">
                <span class="cell-stack__main">{{ row.blocking_reason }}</span>
                <span class="cell-stack__sub">{{ row.blocking_action }}</span>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 店铺结算明细 -->
      <el-card v-if="hasContent" shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span>店铺结算明细</span>
            <span class="section-header__hint">提成为 0 时给出业务原因，区分「没配」和「配成 0」</span>
          </div>
        </template>
        <el-table
          v-loading="loading"
          :data="shopRows"
          border
          stripe
          empty-text="本月没有店铺结算记录"
        >
          <el-table-column label="店铺" min-width="170" fixed="left">
            <template #default="{ row }">
              <ShopDisplayText :row="row" />
            </template>
          </el-table-column>
          <el-table-column label="绩效分" width="100" align="right">
            <template #default="{ row }">{{ formatScore(row.total_score) }}</template>
          </el-table-column>
          <el-table-column label="排名" width="160" align="center">
            <template #default="{ row }">
              <span class="rank-value">{{ row.rank ?? '—' }}</span>
              <el-tag v-if="row.pool_tag" :type="row.pool_tag.type" size="small" class="inline-tag">
                {{ row.pool_tag.label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="店铺结算系数" width="130" align="right">
            <template #default="{ row }">
              <el-tooltip :content="COEFFICIENT_TOOLTIP" placement="top">
                <span>{{ formatCoefficient(row.shop_coefficient) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="考核状态" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.status_tag" :type="row.status_tag.type" size="small">
                {{ row.status_tag.label }}
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="利润状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.profit_tag" :type="row.profit_tag.type" size="small">
                {{ row.profit_tag.label }}
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="利润基数" width="140" align="right">
            <template #default="{ row }">
              <el-tooltip :content="basisHint(row)" placement="top">
                <span>{{ formatMoney(row.profit_basis_amount) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="可分配率" width="140">
            <template #default="{ row }">
              <el-tooltip :content="row.rate_tag.text" placement="top">
                <el-tag :type="row.rate_tag.type" size="small">{{ row.rate_tag.label }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="预计提成" width="140" align="right">
            <template #default="{ row }">{{ formatMoney(row.expected_commission) }}</template>
          </el-table-column>
          <el-table-column label="提成为 0 的原因" min-width="240">
            <template #default="{ row }">
              <span v-if="row.zero_reason">{{ row.zero_reason }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-empty v-if="!hasContent" description="该月份暂无结算数据" />
    </template>

    <el-empty v-else-if="!errorMessage" description="请选择月份后查询月度结算单" />
  </div>
</template>

<script setup>
/**
 * 月度结算单（只读展示页）。
 *
 * 这一页的定位：**如实呈现**后端 `/hr/monthly-settlement` 聚合出来的结算事实。
 *
 * 硬性约束：
 * - 所有金额、系数、状态一律直接使用后端返回值，**前端不做任何加减乘除**；
 * - 「提成为 0」直接展示后端给出的业务原因，不在页面复刻计算公式；
 * - 「未配置可分配率」和「可分配率配成 0」必须显示成不同状态（业务含义不同）。
 *
 * 文案与状态标签统一来自 `./settlementDisplayRules.js`，避免各页面各写一套。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import ShopDisplayText from '@/components/common/ShopDisplayText.vue'
import {
  describeAllocatableRate,
  employeeCalculationStatusTag,
  formatBasisVersion,
  formatCoefficient,
  formatCommissionZeroReason,
  profitStatusTag,
  shopCalculationStatusTag
} from './settlementDisplayRules'

const loading = ref(false)
const errorMessage = ref('')
const settlement = ref(null)
const yearMonth = ref(currentYearMonth())

const COEFFICIENT_TOOLTIP =
  '该店当月的结算系数 = min(该店排名档位系数, 该店分数档位系数)。这家店的提成按它算。'

const SCORE_COEFFICIENT_TOOLTIP =
  '个人分数档位系数（≥90→1.2，80→1.0，70→0.9，60→0.8，<60→0.5）。' +
  '提成分店计算时，再与该店结算系数取低的那个。'

const PERFORMANCE_SALARY_COEFFICIENT_TOOLTIP =
  '绩效工资 = 绩效包 × 这个系数。这是绩效工资用的月度系数；' +
  '提成不是用它算的，而是每家店各用各的结算系数逐店计算（见「提成构成」列）。'

const PERFORMANCE_SOURCE_LABELS = {
  shop_inherited: '店铺继承',
  controlled_targets_v1: '受控个人运营目标',
  manual_input: '个人录入',
  manual: '个人录入'
}

const EMPLOYEE_STATUS_FALLBACK = {
  missing: { label: '缺记录', type: 'danger' },
  pending_scope: { label: '待确认考核范围', type: 'warning' }
}

const SHOP_STATUS_FALLBACK = {
  pending: { label: '待补数据', type: 'warning' }
}

const PAYROLL_STATUS_TAGS = {
  confirmed: { label: '已确认', type: 'success' },
  draft: { label: '草稿', type: 'warning' },
  missing: { label: '未生成', type: 'info' }
}

const RANKING_POOL_TAGS = {
  official: { label: '正式排名池', type: 'success' },
  observation: { label: '观察池', type: 'warning' },
  excluded: { label: '不参与排名', type: 'info' }
}

function currentYearMonth() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${now.getFullYear()}-${month}`
}

function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `¥${numeric.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatScore(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return numeric.toFixed(1)
}

function employeeStatusTag(status) {
  const key = String(status ?? '').trim()
  return employeeCalculationStatusTag(key) || EMPLOYEE_STATUS_FALLBACK[key] || null
}

function shopStatusTag(status) {
  const key = String(status ?? '').trim()
  return shopCalculationStatusTag(key) || SHOP_STATUS_FALLBACK[key] || null
}

function shopProfitTag(status) {
  const key = String(status ?? '').trim()
  return profitStatusTag(key) || { label: key || '未知', type: 'info' }
}

function payrollStatusTag(status) {
  const key = String(status ?? '').trim()
  return PAYROLL_STATUS_TAGS[key] || { label: key || '未知', type: 'info' }
}

function rankingPoolTag(pool) {
  const key = String(pool ?? '').trim()
  return RANKING_POOL_TAGS[key] || null
}

function performanceHint(row) {
  const source = PERFORMANCE_SOURCE_LABELS[String(row?.performance_source_type ?? '').trim()]
  const parts = ['个人绩效分']
  if (source) parts.push(`来源：${source}`)
  if (row?.shop_count) parts.push(`负责店铺 ${row.shop_count} 家`)
  return parts.join(' · ')
}

function commissionHint(row) {
  const status = String(row?.commission_status ?? '').trim()
  return status ? `提成状态：${status}` : '提成状态：未计算'
}

/** 提成构成摘要：让人一眼看出这笔钱是哪几家店凑出来的。 */
function shopBreakSummary(row) {
  const breaks = Array.isArray(row?.shop_breaks) ? row.shop_breaks : []
  if (!breaks.length) return '—'
  return breaks
    .map((item) => `${shopLabel(item.shop_key)} ×${formatCoefficient(item.settlement_coefficient)} ${formatMoney(item.commission_amount)}`)
    .join('  +  ')
}

/** 提成构成明细：每家店把系数从哪来写清楚。 */
function shopBreakHint(row) {
  const breaks = Array.isArray(row?.shop_breaks) ? row.shop_breaks : []
  if (!breaks.length) return '本月没有产生提成的店铺'
  const lines = breaks.map((item) => {
    const limited = item.limited_by === 'personal_score' ? '（被个人分数档位压低）' : '（按店铺结算系数）'
    return (
      `${shopLabel(item.shop_key)}：` +
      `基数 ${formatMoney(item.profit_basis_amount)} × 可分配率 ${(Number(item.allocatable_profit_rate || 0) * 100).toFixed(0)}%` +
      ` × 提成比 ${(Number(item.commission_ratio || 0) * 100).toFixed(0)}% × 结算系数 ${formatCoefficient(item.settlement_coefficient)}` +
      ` = ${formatMoney(item.commission_amount)} ${limited}`
    )
  })
  return lines.join('\n')
}

function shopLabel(shopKey) {
  const raw = String(shopKey ?? '').trim()
  if (!raw) return '未知店铺'
  const parts = raw.split('|')
  return parts.length > 1 ? parts[1] : raw
}

function payrollHint(row) {
  const parts = []
  parts.push(row?.payroll_id ? `工资单 ID：${row.payroll_id}` : '尚未生成工资单')
  if (row?.payroll_status) parts.push(`状态：${row.payroll_status}`)
  return parts.join(' · ')
}

function basisHint(row) {
  const version = formatBasisVersion(row?.basis_version)
  return row?.is_basis_locked ? `${version}（已锁定）` : version
}

const summary = computed(() => settlement.value?.summary || {})
const employees = computed(() => settlement.value?.employees || [])
const shops = computed(() => settlement.value?.shops || [])
const blockingIssues = computed(() => settlement.value?.blocking_issues || [])

const settlementReady = computed(() => summary.value.is_settlement_ready === true)
const hasContent = computed(
  () => employees.value.length > 0 || shops.value.length > 0 || blockingIssues.value.length > 0
)

const employeeNameByCode = computed(() => {
  const map = {}
  for (const item of employees.value) {
    if (item?.employee_code) map[item.employee_code] = item.employee_name
  }
  return map
})

const employeeRows = computed(() =>
  employees.value.map((row) => ({
    ...row,
    status_tag: employeeStatusTag(row.calculation_status),
    payroll_tag: payrollStatusTag(row.payroll_status),
    blocking_reason: row.blocking_issue?.reason || '',
    blocking_action: row.blocking_issue?.action || ''
  }))
)

const shopRows = computed(() =>
  shops.value.map((row) => ({
    ...row,
    status_tag: shopStatusTag(row.calculation_status),
    profit_tag: shopProfitTag(row.profit_status),
    pool_tag: rankingPoolTag(row.ranking_pool),
    rate_tag: describeAllocatableRate(row.is_allocatable_rate_configured, row.allocatable_profit_rate),
    zero_reason: formatCommissionZeroReason(row.commission_zero_reason)
  }))
)

const blockingIssueRows = computed(() =>
  blockingIssues.value.map((issue) => ({
    ...issue,
    employee_name: employeeNameByCode.value[issue.employee_code] || issue.employee_code,
    status_tag: employeeStatusTag(issue.status)
  }))
)

async function loadSettlement() {
  if (!yearMonth.value) {
    ElMessage.warning('请选择月份')
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await api.getHrMonthlySettlement({ year_month: yearMonth.value })
    settlement.value = response?.summary ? response : (response?.data ?? response)
  } catch (error) {
    settlement.value = null
    errorMessage.value =
      error?.response?.data?.detail || error?.message || '加载月度结算单失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadSettlement()
})
</script>

<style scoped>
.monthly-settlement {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
}

.page-subtitle {
  margin: 8px 0 0;
  color: #909399;
}

.filter-card,
.section-card {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.settlement-banner {
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border-left: 6px solid var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}

.settlement-banner--ready {
  border-left-color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}

.settlement-banner--blocked {
  border-left-color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}

.settlement-banner__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.settlement-banner__title {
  font-size: 16px;
  font-weight: 600;
}

.settlement-banner__text {
  color: var(--el-text-color-regular);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
}

.stat-card--highlight {
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}

.stat-card__label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.stat-card__value {
  font-size: 22px;
  font-weight: 700;
  margin: 6px 0 4px;
}

.stat-card__value--warn {
  color: var(--el-color-warning);
}

.stat-card__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.section-header__hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.cell-stack {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.cell-stack__main {
  font-weight: 500;
}

.cell-stack__sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.amount-strong {
  font-weight: 600;
}

.rank-value {
  margin-right: 6px;
}

.inline-tag {
  margin-left: 4px;
}

.muted {
  color: var(--el-text-color-secondary);
}
</style>
