import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewPath = resolve(projectRoot, 'frontend/src/views/DataSyncTemplates.vue')
const apiPath = resolve(projectRoot, 'frontend/src/api/index.js')

const governancePanelPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateGovernancePanel.vue'
)
const needsUpdateTablePath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue'
)
const workbenchDrawerPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue'
)
const changeSummaryCardPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateChangeSummaryCard.vue'
)
const headerDiffViewerPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/HeaderDiffViewer.vue'
)
const deduplicationReviewPanelPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue'
)
const rawPreviewPanelPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateRawPreviewPanel.vue'
)
const builderWorkspacePath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateBuilderWorkspace.vue'
)
const createWorkbenchDrawerPath = resolve(
  projectRoot,
  'frontend/src/components/dataSync/TemplateCreateWorkbenchDrawer.vue'
)

assert.equal(existsSync(viewPath), true, 'DataSyncTemplates.vue should exist')
assert.equal(existsSync(apiPath), true, 'frontend api index should exist')

const viewText = readFileSync(viewPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')
const workbenchDrawerText = existsSync(workbenchDrawerPath)
  ? readFileSync(workbenchDrawerPath, 'utf8')
  : ''
const governancePanelText = existsSync(governancePanelPath)
  ? readFileSync(governancePanelPath, 'utf8')
  : ''
const needsUpdateTableText = existsSync(needsUpdateTablePath)
  ? readFileSync(needsUpdateTablePath, 'utf8')
  : ''
const createWorkbenchDrawerText = existsSync(createWorkbenchDrawerPath)
  ? readFileSync(createWorkbenchDrawerPath, 'utf8')
  : ''

assert.equal(existsSync(governancePanelPath), true, 'TemplateGovernancePanel.vue should exist')
assert.equal(existsSync(needsUpdateTablePath), true, 'TemplateNeedsUpdateTable.vue should exist')
assert.equal(existsSync(workbenchDrawerPath), true, 'TemplateUpdateWorkbenchDrawer.vue should exist')
assert.equal(existsSync(changeSummaryCardPath), true, 'TemplateChangeSummaryCard.vue should exist')
assert.equal(existsSync(headerDiffViewerPath), true, 'HeaderDiffViewer.vue should exist')
assert.equal(existsSync(deduplicationReviewPanelPath), true, 'TemplateDeduplicationReviewPanel.vue should exist')
assert.equal(existsSync(rawPreviewPanelPath), true, 'TemplateRawPreviewPanel.vue should exist')
assert.equal(existsSync(builderWorkspacePath), true, 'TemplateBuilderWorkspace.vue should exist')
assert.equal(existsSync(createWorkbenchDrawerPath), true, 'TemplateCreateWorkbenchDrawer.vue should exist')

assert.match(viewText, /TemplateGovernancePanel/, 'template page should use a governance panel component')
assert.match(viewText, /TemplateUpdateWorkbenchDrawer/, 'template page should use a dedicated update workbench drawer')
assert.match(viewText, /TemplateCreateWorkbenchDrawer/, 'template page should use a dedicated create workbench drawer')
assert.match(viewText, /workbench|update-context|getTemplateUpdateContext/, 'template page should expose update workbench context wiring')
assert.match(viewText, /showTemplateBuilder|builderVisible/, 'template page should track legacy template builder visibility')
assert.match(viewText, /模板工作区|Template Builder/, 'template page should expose a dedicated builder section label')
assert.match(viewText, /TemplateBuilderWorkspace/, 'template page should use a shared builder workspace component')
assert.match(governancePanelText, /el-tabs|covered|missing|needs_update/, 'governance panel should render governance tabs itself')
assert.match(governancePanelText, /update-template|create-missing/, 'governance panel should emit row actions')
assert.match(needsUpdateTableText, /el-table|sample_file_name|update_reason/, 'needs-update table should render the actual update queue')
assert.match(needsUpdateTableText, /update-template/, 'needs-update table should emit update actions')
assert.match(createWorkbenchDrawerText, /TemplateBuilderWorkspace/, 'create workbench should embed the shared builder workspace')
assert.match(createWorkbenchDrawerText, /model-value|visible/, 'create workbench should expose drawer visibility state')
assert.match(workbenchDrawerText, /TemplateChangeSummaryCard/, 'workbench drawer should render a change summary card')
assert.match(workbenchDrawerText, /HeaderDiffViewer/, 'workbench drawer should render a header diff viewer')
assert.match(workbenchDrawerText, /TemplateDeduplicationReviewPanel/, 'workbench drawer should render a deduplication review panel')
assert.match(workbenchDrawerText, /TemplateRawPreviewPanel/, 'workbench drawer should render a raw preview panel')
assert.match(workbenchDrawerText, /match_rate|added_fields|removed_fields|update_reason/, 'workbench drawer should surface core change summary fields')
assert.match(workbenchDrawerText, /existing_deduplication_fields_missing|deduplication_fields/, 'workbench drawer should surface old deduplication field impact')
assert.match(workbenchDrawerText, /recommended_deduplication_fields|current_header_columns/, 'workbench drawer should surface recommended and current-field context')
assert.match(workbenchDrawerText, /preview_data|sample_data/, 'workbench drawer should surface raw preview context')

assert.match(apiText, /getTemplateUpdateContext/, 'frontend api should expose getTemplateUpdateContext')
assert.match(
  apiText,
  /\/field-mapping\/templates\/\$\{templateId\}\/update-context/,
  'frontend api should call the update-context endpoint'
)

console.log('dataSyncTemplateManagementUi.test.mjs passed')
