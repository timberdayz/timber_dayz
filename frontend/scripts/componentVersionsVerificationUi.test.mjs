import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/ComponentVersions.vue')
const source = fs.readFileSync(viewPath, 'utf8')
const recorderViewPath = path.resolve(__dirname, '../src/views/ComponentRecorder.vue')
const recorderSource = fs.readFileSync(recorderViewPath, 'utf8')

test('ComponentVersions uses shared verification dialog instead of inline captcha card', () => {
  assert.equal(
    source.includes('VerificationResumeDialog'),
    true,
    'component version page should reuse the shared verification dialog'
  )

  assert.equal(
    source.includes('verification-required-card'),
    false,
    'legacy inline verification card should be removed'
  )
})

test('V2 surfaces point formal testing to component versions and demote recorder to draft use', () => {
  assert.equal(
    source.includes('V2: 组件版本管理是正式测试、stable 提升和运行入口确认的默认页面。'),
    true,
    'component versions page should advertise itself as the default formal testing surface'
  )

  assert.equal(
    recorderSource.includes('V2: 录制页只负责草稿生成和页面分析，正式测试与 stable 发布请转到组件版本管理。'),
    true,
    'component recorder page should clearly describe its draft-only role in V2'
  )
})
