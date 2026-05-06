import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerSource = fs.readFileSync(path.resolve(__dirname, '../src/router/index.js'), 'utf8')
const menuSource = fs.readFileSync(path.resolve(__dirname, '../src/config/menuGroups.js'), 'utf8')
const rolePermissionsSource = fs.readFileSync(path.resolve(__dirname, '../src/config/rolePermissions.js'), 'utf8')
const overviewPath = path.resolve(__dirname, '../src/domains/platform/views/training/TrainingOverview.vue')
const myTrainingPath = path.resolve(__dirname, '../src/domains/platform/views/training/MyTraining.vue')
const integrationPath = path.resolve(__dirname, '../src/domains/platform/views/training/TrainingIntegration.vue')
const programsPath = path.resolve(__dirname, '../src/domains/platform/views/training/TrainingPrograms.vue')
const assignmentsPath = path.resolve(__dirname, '../src/domains/platform/views/training/TrainingAssignments.vue')
const resultsPath = path.resolve(__dirname, '../src/domains/platform/views/training/TrainingResults.vue')
const trainingApiSource = fs.readFileSync(path.resolve(__dirname, '../src/api/training.js'), 'utf8')

test('formal training routes are registered in router config', () => {
  for (const routePath of [
    '/training/overview',
    '/training/programs',
    '/training/assignments',
    '/training/results',
    '/training/integration',
    '/my-training'
  ]) {
    assert.equal(routerSource.includes(`path: '${routePath}'`), true, `router should contain ${routePath}`)
  }
})

test('formal training pages are listed in menu groups and role permissions', () => {
  assert.equal(menuSource.includes('/training/overview'), true)
  assert.equal(menuSource.includes('/training/integration'), true)
  assert.equal(menuSource.includes('/my-training'), true)
  assert.equal(rolePermissionsSource.includes('training-management'), true)
  assert.equal(rolePermissionsSource.includes('training-integration'), true)
  assert.equal(rolePermissionsSource.includes('my-training'), true)
  assert.equal(menuSource.includes('/training-pilot'), false)
  assert.equal(rolePermissionsSource.includes('training-pilot'), false)
})

test('training overview, integration and my training views exist with expected headings', () => {
  assert.equal(fs.existsSync(overviewPath), true)
  assert.equal(fs.existsSync(myTrainingPath), true)
  assert.equal(fs.existsSync(integrationPath), true)

  const overviewSource = fs.readFileSync(overviewPath, 'utf8')
  const myTrainingSource = fs.readFileSync(myTrainingPath, 'utf8')
  const integrationSource = fs.readFileSync(integrationPath, 'utf8')

  assert.equal(overviewSource.includes('培训总览'), true)
  assert.equal(myTrainingSource.includes('我的培训'), true)
  assert.equal(integrationSource.includes('飞书接入'), true)
})

test('training api and management pages expose create, update, binding and sync entry points', () => {
  const programsSource = fs.readFileSync(programsPath, 'utf8')
  const assignmentsSource = fs.readFileSync(assignmentsPath, 'utf8')
  const resultsSource = fs.readFileSync(resultsPath, 'utf8')
  const detailPath = path.resolve(__dirname, '../src/domains/platform/views/training/TrainingAssignmentDetail.vue')
  const detailSource = fs.readFileSync(detailPath, 'utf8')

  assert.equal(trainingApiSource.includes('createProgram'), true)
  assert.equal(trainingApiSource.includes('createAssignment'), true)
  assert.equal(trainingApiSource.includes('updateResult'), true)
  assert.equal(trainingApiSource.includes('learning_url'), true)
  assert.equal(trainingApiSource.includes('exam_url'), true)
  assert.equal(trainingApiSource.includes('materials_url'), true)
  assert.equal(trainingApiSource.includes('getFeishuConfig'), true)
  assert.equal(trainingApiSource.includes('saveFeishuConfig'), true)
  assert.equal(trainingApiSource.includes('bindFeishu'), true)
  assert.equal(trainingApiSource.includes('syncFeishuResults'), true)

  assert.equal(programsSource.includes('createProgramDialogVisible'), true)
  assert.equal(programsSource.includes('handleCreateProgram'), true)
  assert.equal(programsSource.includes('learning_url'), true)
  assert.equal(programsSource.includes('exam_url'), true)
  assert.equal(programsSource.includes('materials_url'), true)
  assert.equal(assignmentsSource.includes('createAssignmentDialogVisible'), true)
  assert.equal(assignmentsSource.includes('handleCreateAssignment'), true)
  assert.equal(resultsSource.includes('updateResultDialogVisible'), true)
  assert.equal(resultsSource.includes('handleUpdateResult'), true)
  assert.equal(detailSource.includes('去学习'), true)
  assert.equal(detailSource.includes('去考试'), true)
  assert.equal(detailSource.includes('查看资料'), true)
})
