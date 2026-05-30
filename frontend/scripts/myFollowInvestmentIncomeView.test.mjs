import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/MyFollowInvestmentIncome.vue'),
  'utf8'
)

test('MyFollowInvestmentIncome page uses readable Chinese copy', () => {
  for (const label of ['我的跟投收益', '预计收益', '已批准收益', '已确认收益', '本金快照']) {
    assert.equal(source.includes(label), true, `page should contain ${label}`)
  }
})

test('MyFollowInvestmentIncome page is a read-only view', () => {
  assert.equal(source.includes('试算收益'), false)
  assert.equal(source.includes('审批通过'), false)
  assert.equal(source.includes('回退草稿'), false)
})

test('MyFollowInvestmentIncome page shows key table fields', () => {
  for (const label of ['月份', '投资人', '平台', '店铺ID', '结算基准利润', '分配占比']) {
    assert.equal(source.includes(label), true, `page should contain ${label}`)
  }
})

test('MyFollowInvestmentIncome page explains the four settlement narratives', () => {
  for (const label of ['收益说明', '预计收益', '已批准收益', '已确认收益', '本金快照']) {
    assert.equal(source.includes(label), true, `page should explain ${label}`)
  }
  assert.equal(source.includes('不代表你当前账户里的实时本金余额'), true)
})
