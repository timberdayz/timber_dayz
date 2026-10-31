import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/BusinessOverview.vue'),
  'utf8'
)

test('业务概览的积压明细表展示近30天销量（库存采集）', () => {
  assert.match(viewSource, /prop="sold_units_30d"/)
  assert.match(viewSource, /label="近30天销量（库存采集）"/)
  assert.match(viewSource, /row\.sold_units_30d \?\? "-"/)
})

test('近30天销量列说清它是库存数据域口径', () => {
  assert.match(viewSource, /库存数据域（妙手仓库清单）里每个仓库×SKU 自带的近30天销量/)
  assert.match(viewSource, /库存数据域增量更新时才刷新一次/)
  assert.match(viewSource, /不是实时动销速度，也不是订单口径/)
})

test('近30天销量列与积压判据同表，且紧挨可售天数（参考）', () => {
  const daysIndex = viewSource.indexOf('label="距上次进货天数"')
  const sales30Index = viewSource.indexOf('label="近30天销量（库存采集）"')
  const dosIndex = viewSource.indexOf('label="可售天数（参考）"')

  assert.equal(daysIndex > -1, true)
  assert.equal(sales30Index > daysIndex, true)
  assert.equal(dosIndex > sales30Index, true)
})

test('积压明细表的数据源仍是 SKU 级积压模块', () => {
  assert.match(viewSource, /:data="inventoryBacklogProducts"/)
  assert.match(viewSource, /getBusinessOverviewInventoryBacklog/)
})
