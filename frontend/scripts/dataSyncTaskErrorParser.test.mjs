import assert from 'node:assert/strict'
import { extractHeaderChangeErrorEntries, hasHeaderChangeHints } from '../src/domains/data_platform/utils/syncTaskErrorParser.js'

const task = {
  errors: [
    {
      message: '文件2733: 文件tiktok_products_monthly_20260609_173033.xlsx的表头字段已变化,新增176个字段: A; 删除38个字段: B,(匹配率: 0.0%),请更新模板后再同步',
    },
    {
      message: '文件2732: 同步失败:raw_storage,failed to parse metric_date from source_column=日期期间: 01-04-2026 - 30-04-2026',
    },
  ],
}

const hints = extractHeaderChangeErrorEntries(task)

assert.equal(hints.length, 1)
assert.equal(hints[0].file_id, 2733)
assert.equal(hints[0].is_header_changed, true)
assert.equal(hasHeaderChangeHints(task), true)

console.log('dataSyncTaskErrorParser.test.mjs passed')
