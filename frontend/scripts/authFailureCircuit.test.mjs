import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/index.js')
const authApiPath = path.resolve(__dirname, '../src/api/auth.js')
const authSessionPath = path.resolve(__dirname, '../src/utils/authSession.js')
const mainPath = path.resolve(__dirname, '../src/main.js')
const appPath = path.resolve(__dirname, '../src/App.vue')
const apiSource = fs.readFileSync(apiPath, 'utf8')
const authApiSource = fs.readFileSync(authApiPath, 'utf8')
const authSessionSource = fs.readFileSync(authSessionPath, 'utf8')
const mainSource = fs.readFileSync(mainPath, 'utf8')
const appSource = fs.readFileSync(appPath, 'utf8')

test('auth session utilities expose auth failure circuit helpers', () => {
  assert.equal(
    authSessionSource.includes('export function markAuthRecoveryFailed'),
    true,
    'authSession.js should expose markAuthRecoveryFailed()'
  )
  assert.equal(
    authSessionSource.includes('export function hasAuthRecoveryFailed'),
    true,
    'authSession.js should expose hasAuthRecoveryFailed()'
  )
  assert.equal(
    authSessionSource.includes('export function resetAuthRecoveryState'),
    true,
    'authSession.js should expose resetAuthRecoveryState()'
  )
})

test('api layer short-circuits authenticated requests after auth recovery failure', () => {
  assert.equal(
    apiSource.includes('hasAuthRecoveryFailed(localStorage)'),
    true,
    'api request interceptor should check auth recovery failure state before sending authenticated requests'
  )
  assert.equal(
    apiSource.includes("new Error('Authentication session invalidated')"),
    true,
    'api layer should reject with a stable invalidated-session error once auth recovery is known to have failed'
  )
  assert.equal(
    apiSource.includes('markAuthRecoveryFailed(localStorage)'),
    true,
    'api layer should mark auth recovery failure when refresh flow fails'
  )
  assert.equal(
    apiSource.includes('localStorage.getItem(\'access_token\')'),
    false,
    'api layer should not read access tokens from localStorage in Cookie-only auth mode'
  )
})

test('auth api refresh without explicit token does not send an empty JSON body', () => {
  assert.equal(
    authApiSource.includes("return await api._post('/auth/refresh')"),
    true,
    'auth refresh should rely on cookie-only POST when no refresh token argument is provided'
  )
  assert.equal(
    authApiSource.includes("const payload = refreshToken ? { refresh_token: refreshToken } : {}"),
    false,
    'auth refresh should not send an empty object body that triggers backend validation'
  )
})

test('frontend resolves persisted auth state before mount and avoids duplicate user bootstrap in App.vue', () => {
  assert.equal(
    mainSource.includes('await userStore.initUserInfo()'),
    true,
    'main.js should resolve persisted auth state before app.mount()'
  )
  assert.equal(
    appSource.includes('userStore.initUserInfo()'),
    false,
    'App.vue should not trigger a duplicate user bootstrap after mount'
  )
})
