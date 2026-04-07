import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const jsDir = join(process.cwd(), 'dist', 'assets', 'js')

function pickLatestChunk(files, prefix) {
  const matches = files.filter((file) => file.startsWith(prefix) && file.endsWith('.js'))
  if (matches.length === 0) {
    return undefined
  }
  return matches
    .map((file) => ({ file, mtimeMs: statSync(join(jsDir, file)).mtimeMs }))
    .sort((left, right) => right.mtimeMs - left.mtimeMs)[0].file
}

test('build output does not create a circular import between vendor-vue-core and vendor-misc', () => {
  const files = readdirSync(jsDir)
  const vueCoreFile = pickLatestChunk(files, 'vendor-vue-core-')
  const miscFile = pickLatestChunk(files, 'vendor-misc-')

  if (!vueCoreFile || !miscFile) {
    assert.ok(true)
    return
  }

  const vueCoreText = readFileSync(join(jsDir, vueCoreFile), 'utf8')
  const miscText = readFileSync(join(jsDir, miscFile), 'utf8')

  const vueCoreImportsMisc =
    vueCoreText.includes(`from"./${miscFile}"`) ||
    vueCoreText.includes(`from "./${miscFile}"`)
  const miscImportsVueCore =
    miscText.includes(`from"./${vueCoreFile}"`) ||
    miscText.includes(`from "./${vueCoreFile}"`)

  assert.equal(
    vueCoreImportsMisc && miscImportsVueCore,
    false,
    `Detected circular import between ${vueCoreFile} and ${miscFile}`
  )
})

test('build output does not create circular imports between Element Plus vendor chunks', () => {
  const files = readdirSync(jsDir)
  const prefixes = [
    'vendor-element-plus-core-',
    'vendor-element-plus-icons-',
    'vendor-element-plus-table-',
    'vendor-element-plus-date-',
    'vendor-element-plus-overlay-',
  ]
  const elementPlusFiles = prefixes
    .map((prefix) => pickLatestChunk(files, prefix))
    .filter(Boolean)

  for (let i = 0; i < elementPlusFiles.length; i += 1) {
    for (let j = i + 1; j < elementPlusFiles.length; j += 1) {
      const leftFile = elementPlusFiles[i]
      const rightFile = elementPlusFiles[j]
      const leftText = readFileSync(join(jsDir, leftFile), 'utf8')
      const rightText = readFileSync(join(jsDir, rightFile), 'utf8')

      const leftImportsRight =
        leftText.includes(`from"./${rightFile}"`) ||
        leftText.includes(`from "./${rightFile}"`)
      const rightImportsLeft =
        rightText.includes(`from"./${leftFile}"`) ||
        rightText.includes(`from "./${leftFile}"`)

      assert.equal(
        leftImportsRight && rightImportsLeft,
        false,
        `Detected circular import between ${leftFile} and ${rightFile}`
      )
    }
  }
})
