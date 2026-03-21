import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

import { chromium } from 'playwright'

import {
  SMOKE_ROUTES,
  buildAuthStorageEntries,
  summarizeSmokeResults,
} from './frontendSmokeShared.mjs'

const execFileAsync = promisify(execFile)
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..', '..')

const FRONTEND_BASE_URL = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:5173'
const PYTHON_BIN = process.env.PYTHON_BIN || 'python'
const OUTPUT_ROOT = path.join(repoRoot, 'output', 'playwright', 'frontend-smoke')

const MAIN_CONTENT_SELECTORS = [
  '.main-content',
  '.erp-page-container',
  '.page-header',
  'h1',
]

const BLOCKING_TEXT_PATTERNS = [
  'Missing authentication token',
  '未授权',
  'Unauthorized',
  '401',
  '403',
  '500 Internal Server Error',
]

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true })
}

async function generateAuthPayload() {
  const scriptPath = path.join(repoRoot, 'scripts', 'generate_frontend_smoke_auth.py')
  const { stdout } = await execFileAsync(PYTHON_BIN, [scriptPath], {
    cwd: repoRoot,
    encoding: 'utf-8',
  })
  const lines = stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  return JSON.parse(lines.at(-1))
}

function buildRouteUrl(routePath) {
  return `${FRONTEND_BASE_URL}/#${routePath}`
}

function sanitizeFileName(routePath) {
  return routePath.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase()
}

async function writeJson(filePath, payload) {
  await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf-8')
}

async function launchBrowser() {
  const requestedHeadless = process.env.PLAYWRIGHT_HEADLESS !== 'false'

  try {
    return {
      browser: await chromium.launch({ headless: requestedHeadless }),
      headless: requestedHeadless,
      fallbackUsed: false,
    }
  } catch (error) {
    if (requestedHeadless && String(error?.message || '').includes('chrome-headless-shell')) {
      return {
        browser: await chromium.launch({ headless: false }),
        headless: false,
        fallbackUsed: true,
      }
    }
    throw error
  }
}

async function collectRouteResult(page, route, runDir) {
  const consoleErrors = []
  const pageErrors = []
  const requestFailures = []

  const onConsole = (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  }
  const onPageError = (error) => {
    pageErrors.push(String(error))
  }
  const onResponse = (response) => {
    const url = response.url()
    if (url.includes('/api/') && response.status() >= 500) {
      requestFailures.push({ url, status: response.status() })
    }
  }
  const onRequestFailed = (request) => {
    const url = request.url()
    if (url.includes('/api/')) {
      requestFailures.push({
        url,
        status: 0,
        error: request.failure()?.errorText || 'request failed',
      })
    }
  }

  page.on('console', onConsole)
  page.on('pageerror', onPageError)
  page.on('response', onResponse)
  page.on('requestfailed', onRequestFailed)

  let screenshotPath = null

  try {
    await page.goto(buildRouteUrl(route.path), { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1500)

    const title = await page.title()
    const bodyText = await page.locator('body').innerText().catch(() => '')
    const hasMainContent = await page.evaluate((selectors) => {
      return selectors.some((selector) => {
        const element = document.querySelector(selector)
        return Boolean(element && element.textContent && element.textContent.trim().length > 0)
      })
    }, MAIN_CONTENT_SELECTORS)

    const redirectedToLogin = page.url().includes('/login')
    const hasBlockingText = BLOCKING_TEXT_PATTERNS.some((text) => bodyText.includes(text))
    const titleMatches = title.includes(route.expectedTitle)

    const ok =
      !redirectedToLogin &&
      !hasBlockingText &&
      hasMainContent &&
      titleMatches &&
      consoleErrors.length === 0 &&
      pageErrors.length === 0 &&
      requestFailures.length === 0

    if (!ok) {
      screenshotPath = path.join(runDir, `${sanitizeFileName(route.path)}.png`)
      await page.screenshot({ path: screenshotPath, fullPage: true })
    }

    return {
      name: route.name,
      path: route.path,
      expectedTitle: route.expectedTitle,
      actualTitle: title,
      ok,
      redirectedToLogin,
      hasMainContent,
      hasBlockingText,
      consoleErrors,
      pageErrors,
      requestFailures,
      screenshotPath,
    }
  } finally {
    page.off('console', onConsole)
    page.off('pageerror', onPageError)
    page.off('response', onResponse)
    page.off('requestfailed', onRequestFailed)
  }
}

async function main() {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
  const runDir = path.join(OUTPUT_ROOT, timestamp)
  const latestPath = path.join(OUTPUT_ROOT, 'latest.json')
  const runJsonPath = path.join(runDir, 'summary.json')

  await ensureDir(runDir)

  const authPayload = await generateAuthPayload()
  const storageEntries = buildAuthStorageEntries(authPayload)

  const browserLaunch = await launchBrowser()
  const browser = browserLaunch.browser
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
  })

  await context.addInitScript((entries) => {
    Object.entries(entries).forEach(([key, value]) => {
      localStorage.setItem(key, value)
    })
  }, storageEntries)

  const page = await context.newPage()
  const results = []

  try {
    for (const route of SMOKE_ROUTES) {
      const result = await collectRouteResult(page, route, runDir)
      results.push(result)
    }
  } finally {
    await page.close().catch(() => {})
    await context.close().catch(() => {})
    await browser.close().catch(() => {})
  }

  const summary = summarizeSmokeResults(results)
  const payload = {
    frontend_base_url: FRONTEND_BASE_URL,
    generated_at: new Date().toISOString(),
    launch: {
      headless: browserLaunch.headless,
      fallbackUsed: browserLaunch.fallbackUsed,
    },
    results,
    summary,
  }

  await writeJson(runJsonPath, payload)
  await writeJson(latestPath, payload)

  console.log(runJsonPath)

  if (summary.failed > 0) {
    process.exitCode = 1
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
