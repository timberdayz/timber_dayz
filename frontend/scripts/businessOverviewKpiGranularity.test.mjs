import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(process.cwd(), 'frontend')
const viewSource = readFileSync(resolve(repoRoot, 'src/views/BusinessOverview.vue'), 'utf8')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')

test('BusinessOverview exposes KPI granularity controls and forwards granularity/date', () => {
  assert.equal(viewSource.includes('v-model="kpiGranularity"'), true)
  assert.equal(viewSource.includes('<el-radio-button label="daily">日</el-radio-button>'), true)
  assert.equal(viewSource.includes('<el-radio-button label="weekly">周</el-radio-button>'), true)
  assert.equal(viewSource.includes('<el-radio-button label="monthly">月</el-radio-button>'), true)
  assert.equal(viewSource.includes('api.getBusinessOverviewKPI({'), true)
  assert.equal(viewSource.includes('granularity: kpiGranularity.value'), true)
  assert.equal(viewSource.includes('date: kpiDateStr'), true)
})

test('BusinessOverview operational metrics use month semantics in UI and API', () => {
  assert.equal(viewSource.includes('v-model="operationalDate"'), true)
  assert.equal(viewSource.includes('type="month"'), true)
  assert.equal(viewSource.includes('month: operationalDate.value || undefined'), true)
})

test('BusinessOverview API helper serializes KPI granularity/date', () => {
  assert.equal(apiSource.includes("if (params.granularity) queryParams.append('granularity', params.granularity)"), true)
  assert.equal(apiSource.includes("if (params.date) queryParams.append('date', params.date)"), true)
})

test('BusinessOverview top refresh tolerates partial module failures', () => {
  assert.equal(viewSource.includes('Promise.allSettled(['), true)
  assert.equal(viewSource.includes("ElMessage.warning('部分模块刷新失败，已显示可用数据')"), true)
})

test('BusinessOverview global date sync refreshes KPI for all granularities', () => {
  assert.equal(viewSource.includes("if (useGlobalDate.value.kpi) tasks.push(loadKPIData())"), true)
  assert.equal(viewSource.includes("else if (module === 'kpi') loadKPIData()"), true)
  assert.equal(viewSource.includes('kpiGranularity.value = gr'), true)
  assert.equal(viewSource.includes('useGlobalDate.value = {'), true)
})

test('BusinessOverview removes remaining KPI placeholder garble', () => {
  assert.equal(viewSource.includes("return 'YYYY 第 ww 周'"), true)
  assert.equal(viewSource.includes("return '选择月份'"), true)
  assert.equal(viewSource.includes("return '选择周'"), true)
  assert.equal(viewSource.includes("return '选择日期'"), true)
  assert.equal(viewSource.includes("return '当月'"), true)
  assert.equal(viewSource.includes('return `${month}月`'), true)
})
