import fs from 'node:fs/promises'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

import { buildAuthStorageEntries } from './frontendSmokeShared.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..', '..')

const FRONTEND_BASE_URL = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:5173'
const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://127.0.0.1:8001'
const PYTHON_BIN = process.env.PYTHON_BIN || 'python'
const OUTPUT_ROOT = path.join(repoRoot, 'output', 'playwright', 'template-management-smoke')

function log(message) {
  console.log(`[template-smoke] ${new Date().toISOString()} ${message}`)
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true })
}

async function generateAuthPayload() {
  const scriptPath = path.join(repoRoot, 'scripts', 'generate_frontend_smoke_auth.py')
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, ['-u', scriptPath, '--backend-url', BACKEND_BASE_URL], {
      cwd: repoRoot,
      stdio: ['ignore', 'pipe', 'pipe']
    })

    let stdout = ''
    let stderr = ''

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })

    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })

    child.on('error', reject)
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`auth script exited with code ${code}\nstdout:\n${stdout}\nstderr:\n${stderr}`))
        return
      }

      const lines = stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)

      try {
        resolve(JSON.parse(lines.at(-1)))
      } catch (error) {
        reject(new Error(`failed to parse auth payload\nstdout:\n${stdout}\nstderr:\n${stderr}\n${error}`))
      }
    })
  })
}

async function main() {
  const runDir = path.join(OUTPUT_ROOT, new Date().toISOString().replace(/[:.]/g, '-'))
  await ensureDir(runDir)

  log('generating auth payload')
  const authPayload = await generateAuthPayload()
  const storageEntries = buildAuthStorageEntries(authPayload)

  const browser = await chromium.launch({ headless: process.env.PLAYWRIGHT_HEADLESS !== 'false' })
  const page = await browser.newPage()

  const consoleErrors = []
  const pageErrors = []
  const requestFailures = []

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })
  page.on('pageerror', (error) => {
    pageErrors.push(String(error))
  })
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 500) {
      requestFailures.push({ url: response.url(), status: response.status() })
    }
  })
  page.on('requestfailed', (request) => {
    if (request.url().includes('/api/')) {
      requestFailures.push({
        url: request.url(),
        status: 0,
        error: request.failure()?.errorText || 'request failed'
      })
    }
  })

  try {
    await page.goto(`${FRONTEND_BASE_URL}/#/login`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.evaluate((entries) => {
      window.localStorage.clear()
      for (const [key, value] of Object.entries(entries)) {
        window.localStorage.setItem(key, value)
      }
    }, storageEntries)

    log('opening template management page')
    await page.goto(`${FRONTEND_BASE_URL}/#/data-sync/templates`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000
    })
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1500)

    const selectors = {
      pageRoot: '.data-sync-templates',
      governanceCard: '.governance-card',
      templateTable: '.el-table',
      builderCard: '.template-builder-card'
    }

    const pageState = await page.evaluate((selectorMap) => {
      const results = {}
      for (const [key, selector] of Object.entries(selectorMap)) {
        const element = document.querySelector(selector)
        results[key] = Boolean(element && element.textContent !== null)
      }
      results.bodyText = document.body?.innerText || ''
      results.manualUpdateButtons = Array.from(document.querySelectorAll('button'))
        .filter((button) => /manual update/i.test(button.textContent || ''))
        .length
      results.tabLabels = Array.from(document.querySelectorAll('.el-tabs__item')).map((item) =>
        (item.textContent || '').trim()
      )
      return results
    }, selectors)

    let dialogOpened = false
    if (pageState.manualUpdateButtons > 0) {
      log('opening manual update dialog')
      await page.getByRole('button', { name: /manual update/i }).first().click()
      await page.waitForTimeout(800)
      dialogOpened = await page.locator('.el-dialog').count().then((count) => count > 0)
      if (dialogOpened) {
        await page.getByRole('button', { name: /cancel/i }).click().catch(() => {})
      }
    }

    const screenshotPath = path.join(runDir, 'template-management.png')
    await page.screenshot({ path: screenshotPath, fullPage: true })

    const result = {
      ok:
        pageState.pageRoot &&
        pageState.governanceCard &&
        pageState.templateTable &&
        pageState.builderCard &&
        pageErrors.length === 0 &&
        requestFailures.length === 0,
      dialogOpened,
      pageState,
      consoleErrors,
      pageErrors,
      requestFailures,
      screenshotPath
    }

    await fs.writeFile(
      path.join(runDir, 'result.json'),
      `${JSON.stringify(result, null, 2)}\n`,
      'utf-8'
    )

    if (!result.ok) {
      throw new Error(`template management smoke failed: ${JSON.stringify(result, null, 2)}`)
    }

    log(`smoke passed; screenshot saved to ${screenshotPath}`)
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
