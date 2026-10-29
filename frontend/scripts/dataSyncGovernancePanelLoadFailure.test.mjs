import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// 自定位: 无论从仓库根目录还是 frontend/ 目录跑, 都能找到源文件
const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDir, '..')

const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncTemplates.vue')
const governancePanelPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateGovernancePanel.vue'
)
const apiPath = resolve(projectRoot, 'src/api/index.js')

assert.equal(existsSync(viewPath), true, 'DataSyncTemplates.vue should exist')
assert.equal(existsSync(governancePanelPath), true, 'TemplateGovernancePanel.vue should exist')
assert.equal(existsSync(apiPath), true, 'src/api/index.js should exist')

const viewText = readFileSync(viewPath, 'utf8')
const governancePanelText = readFileSync(governancePanelPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')

// ── 1. 治理看板接口必须给足超时 ─────────────────────────────────────
//
// 这个接口要对 27 个「平台×数据域×粒度」组合各读一遍样本文件表头并逐列比对,
// 实测 18~43 秒。axios 默认 30 秒会让它**每次都超时**, 前端随即回落到初始全 0 ——
// 页面于是显示「覆盖率 0%、已覆盖 0、需要更新 0」, 而后端其实算得出结果。
assert.match(
  apiText,
  /governance:\s*120000/,
  'api timeouts should reserve a dedicated budget for the governance coverage endpoint'
)
assert.match(
  apiText,
  /\/governance\/detailed-coverage[\s\S]{0,800}TIMEOUTS\.governance/,
  'governance detailed-coverage request should use the widened timeout'
)

// ── 2. 加载失败不能静默保留初始全 0 ────────────────────────────────
//
// 「空态」与「真实是 0」必须区分开, 否则接口一超时, 页面就显示
// 「覆盖率 0%、需要更新 0」, 误导成治理已达标。
assert.match(
  viewText,
  /governanceLoadError/,
  'template view should track a governance load error flag'
)
assert.match(
  viewText,
  /:load-error="governanceLoadError"/,
  'template view should pass the load error down to the governance panel'
)
assert.match(
  viewText,
  /catch[\s\S]{0,400}governanceLoadError\.value\s*=/,
  'template view should record the error when the governance request fails'
)
assert.match(
  governancePanelText,
  /el-alert[\s\S]{0,400}v-if="loadError"/,
  'governance panel should render an explicit error instead of zeroed stats'
)
assert.match(
  governancePanelText,
  /v-if="loadError"/,
  'governance panel should hide the misleading stat cards when loading failed'
)
assert.match(
  governancePanelText,
  /v-if="!loadError"/,
  'governance panel should hide the empty tables when loading failed'
)

console.log('dataSyncGovernancePanelLoadFailure.test.mjs passed')
