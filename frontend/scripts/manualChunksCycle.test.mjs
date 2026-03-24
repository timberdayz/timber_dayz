import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const jsDir = join(process.cwd(), 'dist', 'assets', 'js')

test('build output does not create a circular import between vendor-vue-core and vendor-misc', () => {
  const files = readdirSync(jsDir)
  const vueCoreFile = files.find((file) => file.startsWith('vendor-vue-core-') && file.endsWith('.js'))
  const miscFile = files.find((file) => file.startsWith('vendor-misc-') && file.endsWith('.js'))

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
    `Detected circular import between ${vueCoreFile} and ${miscFile}`,
  )
})

test('build output does not split Element Plus into mutually dependent vendor chunks', () => {
  const files = readdirSync(jsDir)
  const elementPlusFiles = files.filter(
    (file) => file.startsWith('vendor-element-plus-') && file.endsWith('.js'),
  )

  assert.equal(
    elementPlusFiles.length <= 1,
    true,
    `Expected at most one Element Plus vendor chunk, got: ${elementPlusFiles.join(', ')}`,
  )
})
