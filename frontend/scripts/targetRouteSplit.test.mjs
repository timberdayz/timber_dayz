import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const routerSource = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
const menuSource = readFileSync(new URL('../src/config/menuGroups.js', import.meta.url), 'utf8')
const operationPageSource = readFileSync(new URL('../src/domains/business/views/target/TargetOperationManagement.vue', import.meta.url), 'utf8')
const operationEditorSource = readFileSync(new URL('../src/domains/business/views/target/TargetOperationEditor.vue', import.meta.url), 'utf8')
const personPageSource = readFileSync(new URL('../src/domains/business/views/target/TargetPersonManagement.vue', import.meta.url), 'utf8')

test('router exposes split target management routes', () => {
  assert.equal(routerSource.includes("path: '/target-management/shop'"), true)
  assert.equal(routerSource.includes("path: '/target-management/person'"), true)
  assert.equal(routerSource.includes("path: '/target-management/operation'"), true)
})

test('menu keeps target management entry but points to split shop route', () => {
  assert.equal(menuSource.includes("'/target-management/shop'"), true)
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
})
