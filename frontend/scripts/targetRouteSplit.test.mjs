import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const routerSource = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
const menuSource = readFileSync(new URL('../src/config/menuGroups.js', import.meta.url), 'utf8')
const operationPageSource = readFileSync(new URL('../src/domains/business/views/target/TargetOperationManagement.vue', import.meta.url), 'utf8')
const operationEditorSource = readFileSync(new URL('../src/domains/business/views/target/TargetOperationEditor.vue', import.meta.url), 'utf8')
const personPageSource = readFileSync(new URL('../src/domains/business/views/target/TargetPersonManagement.vue', import.meta.url), 'utf8')
const shopWorkbenchSource = readFileSync(new URL('../src/domains/business/views/target/TargetShopWorkbench.vue', import.meta.url), 'utf8')

test('router exposes split target management routes', () => {
  assert.equal(routerSource.includes("path: '/target-management/shop'"), true)
  assert.equal(routerSource.includes("path: '/target-management/person'"), true)
  assert.equal(routerSource.includes("path: '/target-management/operation'"), true)
})

test('menu keeps target management entry but points to split shop route', () => {
  assert.equal(menuSource.includes("'/target-management/shop'"), true)
  assert.equal(menuSource.includes("'/target-management/person'"), true)
  assert.equal(menuSource.includes("'/target-management/operation'"), true)
  assert.equal(menuSource.includes("'/hr-performance-management/person'"), true)
  assert.equal(menuSource.includes("'/hr-performance-management/shop'"), true)
})

test('shop target route uses the workbench instead of the legacy entry page', () => {
  assert.equal(routerSource.includes("TargetShopWorkbench.vue"), true)
  assert.equal(routerSource.includes("title: '店铺目标管理'"), true)
  assert.equal(routerSource.includes("title: '个人目标管理'"), true)
  assert.equal(routerSource.includes("title: '运营目标管理'"), true)
})

test('operation target page is separated and uses the dedicated editor/formula helper', () => {
  assert.equal(operationPageSource.includes('TargetOperationEditor'), true)
  assert.equal(operationPageSource.includes('operationTargetFormula'), true)
  assert.equal(operationEditorSource.includes('defineProps'), true)
  assert.equal(operationEditorSource.includes('defineEmits'), true)
})

test('person target page is no longer a placeholder and uses employee target APIs', () => {
  assert.equal(personPageSource.includes('getHrEmployeeTargets'), true)
  assert.equal(personPageSource.includes('createHrEmployeeTarget'), true)
  assert.equal(personPageSource.includes('updateHrEmployeeTarget'), true)
  assert.equal(personPageSource.includes('saveBatchTargets'), true)
})

test('shop target workbench supports month copy, ratio split, aliases, and daily targets', () => {
  assert.equal(shopWorkbenchSource.includes('getShopTargetWorkbench'), true)
  assert.equal(shopWorkbenchSource.includes('applyShopTargetWorkbench'), true)
  assert.equal(shopWorkbenchSource.includes('copyPrevMonthShopTargetWorkbench'), true)
  assert.equal(shopWorkbenchSource.includes('standard_name'), true)
  assert.equal(shopWorkbenchSource.includes('aliases'), true)
  assert.equal(shopWorkbenchSource.includes('daily_target_count'), true)
  assert.equal(shopWorkbenchSource.includes('ratio_percent'), true)
})
