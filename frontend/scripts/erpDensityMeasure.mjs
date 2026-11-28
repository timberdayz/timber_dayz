/**
 * 密度改造的**真机**复核：量真实 DOM 的行高 + 截图。
 * 只读：不改仓库文件，截图写到系统临时目录。
 *
 * 鉴权说明：西虹 ERP 的会话本体在 httpOnly cookie 里（backend/dependencies/auth.py
 * 优先读 access_token cookie），前端请求靠 withCredentials 带上；
 * 因此浏览器端必须注入 cookie，只写 localStorage 不建立登录态。
 *
 * 用法（frontend 目录下执行）：
 *   node scripts/erpDensityMeasure.mjs                 # 量 + 截图
 *   DENSITY_DEBUG=1 node scripts/erpDensityMeasure.mjs  # 附带排版诊断明细
 */
/* eslint-env node */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { chromium } from 'playwright'
import { buildAuthStorageEntries } from './frontendSmokeShared.mjs'

const repoRoot = path.resolve(process.cwd(), '..')
const FRONTEND = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:5173'
const OUT_DIR = path.join(os.tmpdir(), 'erp_density_shots')

fs.mkdirSync(OUT_DIR, { recursive: true })

const authRaw = execFileSync('python', ['-u', 'scripts/generate_frontend_smoke_auth.py'], {
  cwd: repoRoot,
  encoding: 'utf8'
})
const authPayload = JSON.parse(authRaw.trim().split(/\r?\n/).filter(Boolean).at(-1))
const storageEntries = buildAuthStorageEntries(authPayload)

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })

// 1) 会话 cookie（真正的登录态）
await context.addCookies([
  {
    name: 'access_token',
    value: authPayload.access_token || '',
    url: FRONTEND,
    httpOnly: true,
    sameSite: 'Lax'
  },
  {
    name: 'refresh_token',
    value: authPayload.refresh_token || '',
    url: FRONTEND,
    httpOnly: true,
    sameSite: 'Lax'
  }
])

// 2) 前端路由守卫需要的持久化会话信息
await context.addInitScript((entries) => {
  for (const [key, value] of Object.entries(entries)) {
    window.localStorage.setItem(key, value)
  }
}, storageEntries)

const page = await context.newPage()
const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('response', (res) => {
  if (res.status() >= 400) consoleErrors.push(`HTTP ${res.status()} ${res.url()}`)
})

const measure = async (route, label) => {
  consoleErrors.length = 0
  await page.goto(`${FRONTEND}/#${route}`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page
    .waitForSelector('.el-table__body-wrapper tbody tr.el-table__row', { timeout: 15000 })
    .catch(() => {})
  await page.waitForTimeout(2000)

  const metrics = await page.evaluate(() => {
    const allRows = [...document.querySelectorAll('.el-table__body-wrapper tbody tr.el-table__row')]
    const visible = allRows.filter((r) => r.getBoundingClientRect().height > 0)
    const heights = visible.map((r) => Math.round(r.getBoundingClientRect().height))
    const header = document.querySelector('.el-table__header-wrapper th.el-table__cell')
    const pageHeader = document.querySelector('.erp-page-header')
    const metricStrip = document.querySelector('.stat-metrics')
    // 行高来源诊断：找出把行撑高的单元格（看 .cell 内容高度，不是 td 拉伸高度）
    const rowBreakdown = []
    const rows = [...document.querySelectorAll('.el-table__body-wrapper tbody tr.el-table__row')]
      .filter((r) => r.getBoundingClientRect().height > 0)
      .slice(0, 3)
    for (const row of rows) {
      const rowH = Math.round(row.getBoundingClientRect().height)
      const cells = [...row.querySelectorAll('td.el-table__cell')]
      const perCell = cells.map((td, idx) => {
        const cell = td.querySelector('.cell')
        const inner = cell
          ? Math.max(0, ...[...cell.children].map((c) => c.getBoundingClientRect().height))
          : 0
        return {
          idx,
          text: (td.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 26),
          innerH: Math.round(inner),
          cellH: cell ? Math.round(cell.getBoundingClientRect().height) : 0,
          cellScrollH: cell ? cell.scrollHeight : 0
        }
      })
      rowBreakdown.push({ rowH, perCell })
    }
    // 第一行的计算样式（行高到底由谁撑起）
    const rowStyleProbe = (() => {
      const tr = document.querySelector('.el-table__body-wrapper tbody tr.el-table__row')
      if (!tr) return null
      const td = tr.querySelector('td.el-table__cell')
      const cell = td?.querySelector('.cell')
      const cs = td ? getComputedStyle(td) : null
      const ccs = cell ? getComputedStyle(cell) : null
      return {
        trStyleAttr: tr.getAttribute('style') || '',
        trClass: tr.className,
        trHeight: Math.round(tr.getBoundingClientRect().height),
        trComputedHeight: getComputedStyle(tr).height,
        tdPadding: cs ? `${cs.paddingTop}/${cs.paddingBottom}` : '',
        tdHeight: td ? Math.round(td.getBoundingClientRect().height) : 0,
        cellHeight: cell ? Math.round(cell.getBoundingClientRect().height) : 0,
        cellScrollHeight: cell ? cell.scrollHeight : 0,
        cellPadding: ccs ? `${ccs.paddingTop}/${ccs.paddingBottom}` : '',
        cellLineHeight: ccs ? ccs.lineHeight : '',
        cellChildren: cell
          ? [...cell.children].map((c) => {
            const r = c.getBoundingClientRect()
            const ccs2 = getComputedStyle(c)
            return {
              tag: c.tagName,
              cls: c.className,
              h: Math.round(r.height),
              mt: ccs2.marginTop,
              mb: ccs2.marginBottom,
              display: ccs2.display
            }
          })
          : []
      }
    })()
    // 样式表扫描：紧凑档规则是否加载、td padding 由谁决定
    const styleProbe = (() => {
      const compactRules = []
      const cellPaddingRules = []
      const walk = (rules, href) => {
        for (const rule of rules) {
          // 注意：CSSStyleRule 也有 cssRules（CSS 嵌套用），恒为真值，
          // 所以必须先判 selectorText，否则普通规则会被当成容器跳过。
          if (!rule.selectorText) {
            if (rule.cssRules) walk(rule.cssRules, href)
            continue
          }
          if (rule.selectorText.includes('erp-compact')) {
            compactRules.push({ href, sel: rule.selectorText, css: rule.style.cssText })
          }
          if (
            rule.selectorText.includes('el-table__cell') &&
            rule.style &&
            rule.style.padding
          ) {
            cellPaddingRules.push({ href, sel: rule.selectorText, css: rule.style.cssText })
          }
        }
      }
      for (const sheet of document.styleSheets) {
        let rules = []
        try {
          rules = sheet.cssRules || []
        } catch {
          continue
        }
        walk(rules, sheet.href || 'inline')
      }
      const td = document.querySelector('.el-table__body-wrapper tbody td.el-table__cell')
      return {
        compactRuleCount: compactRules.length,
        compactRules: compactRules.slice(0, 20),
        cellPaddingRules: cellPaddingRules.slice(0, 20),
        tdHasCompactClass: td
          ? Boolean(td.closest('.erp-compact')) && Boolean(td.closest('.el-table').classList.contains('erp-compact'))
          : null,
        tdClosestCompactClass: td ? td.closest('.erp-compact')?.className || null : null,
        tdTableClass: td ? td.closest('.el-table').className : null,
        computedPadding: td ? getComputedStyle(td).padding : null
      }
    })()
    const tables = [...document.querySelectorAll('.el-table')].map((t) => ({
      compact: t.classList.contains('erp-compact') || Boolean(t.closest('.erp-compact')),
      width: Math.round(t.getBoundingClientRect().width),
      scrollWidth: t.querySelector('.el-scrollbar__wrap')?.scrollWidth || 0,
      columns: [...t.querySelectorAll('.el-table__header-wrapper th.el-table__cell')].map((th) => ({
        label: (th.innerText || '').trim().replace(/\s+/g, ' '),
        width: Math.round(th.getBoundingClientRect().width)
      }))
    }))
    // 成本摘要单元格的内部排版诊断（归属页）
    const costCells = [...document.querySelectorAll('.cost-summary-cell')].slice(0, 3).map((cell) => {
      const box = cell.getBoundingClientRect()
      const text = cell.querySelector('.cost-summary-text')
      const alert = cell.querySelector('.cost-summary-alert')
      const row = cell.closest('tr.el-table__row')
      return {
        rowHeight: row ? Math.round(row.getBoundingClientRect().height) : 0,
        cell: { w: Math.round(box.width), h: Math.round(box.height) },
        text: text
          ? {
            w: Math.round(text.getBoundingClientRect().width),
            scrollW: text.scrollWidth,
            truncated: text.scrollWidth > text.clientWidth + 1
          }
          : null,
        alert: alert ? { w: Math.round(alert.getBoundingClientRect().width), h: Math.round(alert.getBoundingClientRect().height) } : null
      }
    })
    return {
      url: location.hash,
      rowCount: visible.length,
      rowHeightMin: heights.length ? Math.min(...heights) : 0,
      rowHeightMax: heights.length ? Math.max(...heights) : 0,
      rowHeightAvg: heights.length
        ? Math.round(heights.reduce((a, b) => a + b, 0) / heights.length)
        : 0,
      headerHeight: header ? Math.round(header.getBoundingClientRect().height) : 0,
      pageHeaderHeight: pageHeader ? Math.round(pageHeader.getBoundingClientRect().height) : 0,
      metricStripHeight: metricStrip ? Math.round(metricStrip.getBoundingClientRect().height) : 0,
      hasRemarkColumn: [...document.querySelectorAll('th.el-table__cell')].some((th) =>
        (th.innerText || '').includes('备注')
      ),
      tables,
      diagnostics: { rowStyleProbe, styleProbe, rowBreakdown, costCells }
    }
  })

  const shot = path.join(OUT_DIR, `${label}.png`)
  await page.screenshot({ path: shot, fullPage: true })
  // 首行特写（看单行内部排版）
  const firstRow = page.locator('.el-table__body-wrapper tbody tr.el-table__row').first()
  if (await firstRow.count()) {
    await firstRow
      .screenshot({ path: path.join(OUT_DIR, `${label}-row1.png`) })
      .catch(() => {})
  }
  const { diagnostics, ...summary } = metrics
  console.log(`[${label}] ${JSON.stringify(summary)}`)
  if (process.env.DENSITY_DEBUG) {
    console.log(`  诊断: ${JSON.stringify(diagnostics)}`)
  }
  if (consoleErrors.length) {
    console.log(`  控制台/网络异常(${consoleErrors.length}): ${consoleErrors.slice(0, 8).join(' | ')}`)
  }
  console.log(`  截图 -> ${shot}`)
  return metrics
}

// 默认量两个目标页面；也接受命令行传入的其它路由（格式 /path 或 /path:label）
const DEFAULT_ROUTES = [
  ['/expense-management', 'expense'],
  ['/hr-shop-assignment', 'assignment']
]
const routes = process.argv.slice(2).length
  ? process.argv.slice(2).map((arg) => {
    const [route, label] = arg.split(':')
    return [route, label || route.replace(/[^\w-]/g, '') || 'page']
  })
  : DEFAULT_ROUTES

for (const [route, label] of routes) {
  await measure(route, label)
}

await browser.close()
