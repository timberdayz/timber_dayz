import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewPath = resolve(projectRoot, 'frontend/src/views/DataSyncTemplates.vue')
const apiPath = resolve(projectRoot, 'frontend/src/api/index.js')

const viewText = readFileSync(viewPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')

assert.match(
  apiText,
  /saveMode/,
  'saveTemplate api wrapper should accept an explicit saveMode'
)

assert.match(
  viewText,
  /saveMode:\s*['"]new_version['"]/,
  'template update workbench should persist updates as new versions explicitly'
)

console.log('dataSyncTemplateVersioningUi.test.mjs passed')
