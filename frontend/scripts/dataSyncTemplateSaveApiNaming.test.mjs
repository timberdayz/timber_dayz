import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const apiPath = resolve(projectRoot, 'frontend/src/api/index.js')
const apiText = readFileSync(apiPath, 'utf8')

assert.match(
  apiText,
  /async saveTemplate\(\{\s*[\s\S]*templateName[\s\S]*\}\)/,
  'saveTemplate should accept an explicit templateName override'
)

assert.match(
  apiText,
  /resolvedTemplateName|finalTemplateName/,
  'saveTemplate should resolve template names through a dedicated variable'
)

assert.doesNotMatch(
  apiText,
  /template_name:\s*`\$\{platform\}_\$\{finalDomain\}_\$\{subDomain \|\| ''\}_\$\{\s*granularity \|\| 'all'\s*\}_v1`/,
  'saveTemplate should not hardcode a _v1 template_name for every save request'
)

console.log('dataSyncTemplateSaveApiNaming.test.mjs passed')
