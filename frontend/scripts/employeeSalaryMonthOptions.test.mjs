import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/EmployeeSalary.vue'),
  'utf8'
)

test('EmployeeSalary month options include next month and previous 11 months', () => {
  assert.equal(source.includes('for (let i = -1; i < 11; i += 1)'), true)
})
