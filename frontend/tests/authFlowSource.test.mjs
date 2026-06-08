import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const authStoreSource = readFileSync(resolve(repoRoot, 'src/stores/auth.js'), 'utf8')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')

function sliceBetween(source, startText, endText) {
  const start = source.indexOf(startText)
  const end = source.indexOf(endText, start)
  assert.notEqual(start, -1, `missing start marker: ${startText}`)
  assert.notEqual(end, -1, `missing end marker: ${endText}`)
  return source.slice(start, end)
}

test('auth store refresh failure records error without clearing local session', () => {
  const refreshBlock = sliceBetween(
    authStoreSource,
    'const refreshAccessToken = async () =>',
    'const fetchCurrentUser = async () =>',
  )

  assert.match(refreshBlock, /lastRefreshError\.value = error/)
  assert.doesNotMatch(refreshBlock, /clearLocalSession\(\)/)
})

test('auth store persists access token expiry without persisting tokens', () => {
  assert.match(authStoreSource, /deriveAccessTokenExpiresAt\(expiresIn\)/)
  assert.match(authStoreSource, /localStorage\.setItem\('accessTokenExpiresAt'/)
  assert.doesNotMatch(authStoreSource, /localStorage\.setItem\('access_token'/)
  assert.doesNotMatch(authStoreSource, /localStorage\.setItem\('refresh_token'/)
})

test('api interceptor refreshes from expiry state and confirms before forced logout', () => {
  assert.match(apiSource, /shouldRefreshAccessToken\(\{\s*accessTokenExpiresAt\s*\}\)/)
  assert.match(apiSource, /const refreshed = await refreshAccessTokenWithBroadcast\(\)/)
  assert.match(apiSource, /const recoveryResult = await recoverAfterRefreshFailure\(refreshError\)/)
  assert.match(apiSource, /confirmCurrentCookieSession/)
})
