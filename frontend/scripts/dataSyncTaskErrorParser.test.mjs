import assert from 'node:assert/strict'
import {
  extractHeaderChangeErrorEntries,
  hasHeaderChangeHints,
  extractDateParseErrorEntries,
  hasDateParseHints,
  parseDateErrorCode,
} from '../src/domains/data_platform/utils/syncTaskErrorParser.js'

const task = {
  errors: [
    {
      message: '文件2733: 文件tiktok_products_monthly_20260609_173033.xlsx的表头字段已变化,新增176个字段: A; 删除38个字段: B,(匹配率: 0.0%),请更新模板后再同步',
    },
    {
      message: '文件2732: 同步失败:raw_storage,[date_format_mismatch] failed to parse metric_date from source_column=日期期间: 01-04-2026 - 30-04-2026',
    },
  ],
}

const hints = extractHeaderChangeErrorEntries(task)

assert.equal(hints.length, 1)
assert.equal(hints[0].file_id, 2733)
assert.equal(hints[0].is_header_changed, true)
assert.equal(hasHeaderChangeHints(task), true)

// [*] 批次 B · API-7: 结构化错误码分流
assert.equal(parseDateErrorCode(task.errors[1].message), 'date_format_mismatch')
assert.equal(parseDateErrorCode(task.errors[0].message), null)

const dateHints = extractDateParseErrorEntries(task)
assert.equal(dateHints.length, 1)
assert.equal(dateHints[0].file_id, 2732)
assert.equal(dateHints[0].error_code, 'date_format_mismatch')
assert.equal(dateHints[0].error_label, '日期格式与模板声明不一致')
assert.ok(dateHints[0].error_hint.length > 0)
assert.equal(hasDateParseHints(task), true)

// 旧文案(没有错误码)不应被当成日期解析错误
assert.equal(hasDateParseHints({ errors: [{ message: '文件2732: 同步失败:raw_storage,failed to parse metric_date' }] }), false)

console.log('dataSyncTaskErrorParser.test.mjs passed')
