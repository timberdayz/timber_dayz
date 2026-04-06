import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())

const viewPath = resolve(projectRoot, 'frontend/src/views/DataSyncTemplates.vue')
const governancePanelPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateGovernancePanel.vue'
)
const needsUpdateTablePath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue'
)
const modeDialogPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue'
)
const workbenchDrawerPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue'
)
const apiPath = resolve(projectRoot, 'frontend/src/api/index.js')

assert.equal(existsSync(viewPath), true, 'DataSyncTemplates.vue should exist')
assert.equal(existsSync(governancePanelPath), true, 'TemplateGovernancePanel.vue should exist')
assert.equal(existsSync(needsUpdateTablePath), true, 'TemplateNeedsUpdateTable.vue should exist')
assert.equal(existsSync(workbenchDrawerPath), true, 'TemplateUpdateWorkbenchDrawer.vue should exist')
assert.equal(
  existsSync(modeDialogPath),
  true,
  'TemplateManualUpdateModeDialog.vue should exist for manual update mode selection'
)

const viewText = readFileSync(viewPath, 'utf8')
const governancePanelText = readFileSync(governancePanelPath, 'utf8')
const needsUpdateTableText = readFileSync(needsUpdateTablePath, 'utf8')
const modeDialogText = readFileSync(modeDialogPath, 'utf8')
const workbenchDrawerText = readFileSync(workbenchDrawerPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')

assert.match(
  governancePanelText,
  /manual-update|Manual Update/,
  'covered templates should expose a Manual Update action'
)
assert.match(
  viewText,
  /manualUpdateModeDialogVisible|pendingManualUpdateTemplate|manualUpdateMode/,
  'template view should track manual update orchestration state'
)
assert.match(
  viewText,
  /TemplateManualUpdateModeDialog/,
  'template view should render the manual update mode dialog'
)
assert.match(
  viewText,
  /handleManualUpdate|openManualUpdate|chooseManualUpdateMode/,
  'template view should expose a manual update orchestration handler'
)
assert.match(
  viewText,
  /Manual Update/,
  'template list should expose a Manual Update action'
)
assert.match(
  needsUpdateTableText,
  /Manual Update/,
  'needs-update table should align its action label with Manual Update'
)
assert.match(
  modeDialogText,
  /Core Fields Only/,
  'mode dialog should include the Core Fields Only path'
)
assert.match(
  modeDialogText,
  /Reset From Sample File/,
  'mode dialog should include the Reset From Sample File path'
)
assert.match(
  apiText,
  /getTemplateUpdateContext\(templateId,\s*(fileId\s*=\s*null|\{\s*mode,\s*fileId)/,
  'frontend api should expose a mode-aware getTemplateUpdateContext wrapper'
)
assert.match(
  apiText,
  /mode: mode \|\| ['"]with-sample['"]/,
  'frontend api should forward the requested update mode'
)
assert.match(
  workbenchDrawerText,
  /update_mode|header_source/,
  'workbench drawer should recognize core-only vs with-sample context'
)

console.log('dataSyncCoveredTemplateManualUpdateUi.test.mjs passed')
