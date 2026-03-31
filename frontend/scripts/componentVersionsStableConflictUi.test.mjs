import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/ComponentVersions.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('ComponentVersions computes multi-stable conflicts using exact component names', () => {
  assert.equal(
    source.includes('const key = row.component_name'),
    true,
    'stable conflict grouping should use the exact runtime component_name'
  )

  assert.equal(
    source.includes('const key = `${platform}/${compType}`'),
    false,
    'stable conflict grouping should not collapse exports into platform/type buckets'
  )
})

test('ComponentVersions surfaces data-domain and sub-domain labels for export components', () => {
  assert.equal(
    source.includes('getComponentSummary(row.component_name)'),
    true,
    'component name column should render a precise component summary'
  )

  assert.equal(
    source.includes('getComponentTypeFromName(row.component_name)'),
    false,
    'component name column should not reduce subtype exports to the generic export label'
  )
})
