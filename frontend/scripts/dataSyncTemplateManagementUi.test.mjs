import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncTemplates.vue')
const apiPath = resolve(projectRoot, 'src/api/index.js')

const governancePanelPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateGovernancePanel.vue'
)
const needsUpdateTablePath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateNeedsUpdateTable.vue'
)
const workbenchDrawerPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue'
)
const changeSummaryCardPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateChangeSummaryCard.vue'
)
const headerDiffViewerPath = resolve(
  projectRoot,
  'src/components/dataSync/HeaderDiffViewer.vue'
)
const deduplicationReviewPanelPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateDeduplicationReviewPanel.vue'
)
const rawPreviewPanelPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateRawPreviewPanel.vue'
)
const builderWorkspacePath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateBuilderWorkspace.vue'
)
const createWorkbenchDrawerPath = resolve(
  projectRoot,
  'src/components/dataSync/TemplateCreateWorkbenchDrawer.vue'
)
const variantWorkbenchDrawerPath = resolve(
  projectRoot,
  'src/components/dataSync/VariantCreateWorkbenchDrawer.vue'
)

assert.equal(existsSync(viewPath), true, 'DataSyncTemplates.vue should exist')
assert.equal(existsSync(apiPath), true, 'frontend api index should exist')

const viewText = readFileSync(viewPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')
const workbenchDrawerText = existsSync(workbenchDrawerPath)
  ? readFileSync(workbenchDrawerPath, 'utf8')
  : ''
const changeSummaryCardText = existsSync(changeSummaryCardPath)
  ? readFileSync(changeSummaryCardPath, 'utf8')
  : ''
const deduplicationReviewPanelText = existsSync(deduplicationReviewPanelPath)
  ? readFileSync(deduplicationReviewPanelPath, 'utf8')
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
const variantWorkbenchDrawerText = existsSync(variantWorkbenchDrawerPath)
  ? readFileSync(variantWorkbenchDrawerPath, 'utf8')
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
assert.equal(existsSync(variantWorkbenchDrawerPath), true, 'VariantCreateWorkbenchDrawer.vue should exist')

assert.match(viewText, /TemplateGovernancePanel/, 'template page should use a governance panel component')
assert.match(viewText, /TemplateUpdateWorkbenchDrawer/, 'template page should use a dedicated update workbench drawer')
assert.match(viewText, /TemplateCreateWorkbenchDrawer/, 'template page should use a dedicated create workbench drawer')
assert.match(viewText, /VariantCreateWorkbenchDrawer/, 'template page should use a dedicated variant create workbench drawer')
assert.match(viewText, /VariantCreateWorkbenchDrawer/, 'template page should use a dedicated variant create workbench drawer')
assert.match(viewText, /VariantCreateWorkbenchDrawer/, 'template page should use a dedicated variant create workbench drawer')
assert.match(viewText, /workbench|update-context|getTemplateUpdateContext/, 'template page should expose update workbench context wiring')
assert.match(viewText, /showTemplateBuilder|builderVisible/, 'template page should track legacy template builder visibility')
assert.match(viewText, /模板工作区|Template Builder/, 'template page should expose a dedicated builder section label')
assert.match(viewText, /TemplateBuilderWorkspace/, 'template page should use a shared builder workspace component')
assert.match(governancePanelText, /el-tabs|covered|missing|needs_update/, 'governance panel should render governance tabs itself')
assert.match(governancePanelText, /update-template|create-missing/, 'governance panel should emit row actions')
assert.match(needsUpdateTableText, /el-table|sample_file_name|update_reason/, 'needs-update table should render the actual update queue')
assert.match(needsUpdateTableText, /update-template/, 'needs-update table should emit update actions')
assert.match(
  needsUpdateTableText,
  /isActionDisabled|sample_file_id|family_id|等待样本|上下文缺失/,
  'needs-update table should guard variant/update actions when required context is missing'
)
assert.match(createWorkbenchDrawerText, /TemplateBuilderWorkspace/, 'create workbench should embed the shared builder workspace')
assert.match(createWorkbenchDrawerText, /model-value|visible/, 'create workbench should expose drawer visibility state')
assert.match(variantWorkbenchDrawerText, /TemplateBuilderWorkspace/, 'variant create workbench should embed the shared builder workspace')
assert.match(variantWorkbenchDrawerText, /Missing Variant|Create Variant|variant/i, 'variant create workbench should expose variant creation context')
assert.match(workbenchDrawerText, /TemplateChangeSummaryCard/, 'workbench drawer should render a change summary card')
assert.match(workbenchDrawerText, /HeaderDiffViewer/, 'workbench drawer should render a header diff viewer')
assert.match(workbenchDrawerText, /TemplateDeduplicationReviewPanel/, 'workbench drawer should render a deduplication review panel')
assert.match(workbenchDrawerText, /TemplateRawPreviewPanel/, 'workbench drawer should render a raw preview panel')
assert.match(workbenchDrawerText, /match_rate|added_fields|removed_fields|update_reason/, 'workbench drawer should surface core change summary fields')
assert.match(workbenchDrawerText, /existing_deduplication_fields_missing|deduplication_fields/, 'workbench drawer should surface old deduplication field impact')
assert.match(workbenchDrawerText, /existing_deduplication_field_matches/, 'workbench drawer should pass semantic-equivalent deduplication matches')
assert.match(workbenchDrawerText, /recommended_deduplication_fields|current_header_columns/, 'workbench drawer should surface recommended and current-field context')
assert.match(workbenchDrawerText, /preview_data|sample_data/, 'workbench drawer should surface raw preview context')
assert.match(changeSummaryCardText, /已语义匹配/, 'change summary should show semantic-equivalent old fields')
assert.match(changeSummaryCardText, /已语义匹配，但不再参与 Data Hash/, 'change summary should distinguish matched non-hashable fields')
assert.match(deduplicationReviewPanelText, /匹配但不可参与 Data Hash/, 'deduplication review should show matched non-hashable old fields')

assert.match(apiText, /getTemplateUpdateContext/, 'frontend api should expose getTemplateUpdateContext')
assert.match(apiText, /getTemplateVariantCreateContext/, 'frontend api should expose getTemplateVariantCreateContext')
assert.match(apiText, /getTemplateVariantCreateContext/, 'frontend api should expose getTemplateVariantCreateContext')
assert.match(
  apiText,
  /\/field-mapping\/templates\/\$\{templateId\}\/update-context/,
  'frontend api should call the update-context endpoint'
)

console.log('dataSyncTemplateManagementUi.test.mjs passed')
