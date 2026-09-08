import { formatNumber } from "../src/lib/format.js";
import { test, expect } from '@playwright/test'
import { events, entities, stocks } from '../src/data/mock/fixtures/catalog.js'

const hormuz = events.find(event => event.id === 'iran-hormuz-2025')
const nvidia = stocks.find(stock => stock.symbol === 'NVDA')

test.beforeEach(async ({ page }) => {
  page.__robustnessErrors = []
  page.on('pageerror', error => page.__robustnessErrors.push(error.message))
})

test.afterEach(async ({ page }) => {
  expect(page.__robustnessErrors, 'No uncaught browser exceptions').toEqual([])
})

test('every event, entity and stock deep link renders its own title without backend requests', async ({ page }) => {
  test.setTimeout(90_000)
  const dataRequests = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (/^\/api(?:\/|$)/.test(url.pathname) || ['fetch', 'xhr'].includes(request.resourceType())) {
      dataRequests.push(`${request.method()} ${request.url()}`)
    }
  })
  const routes = [
    ...events.map(event => [`/events/${event.id}`, event.title]),
    ...entities.map(entity => [`/intelligence/${entity.id}`, entity.name]),
    ...stocks.map(stock => [`/stocks/${stock.symbol}`, stock.name]),
  ]
  expect(routes).toHaveLength(28)
  for (const [route, title] of routes) {
    await test.step(route, async () => {
      await page.goto(`/#${route}`)
      await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
      await expect(page.getByRole('main')).toHaveCount(1)
      await expect(page.getByRole('heading', { name: '화면을 불러오지 못했습니다' })).toHaveCount(0)
    })
  }
  // These are actual user links as well as direct document loads.
  await page.goto('/#/events/ai-chip-controls')
  await page.getByRole('link', { name: '종목 연결 근거 보기' }).click()
  await page.locator('.st-stock-identity').filter({ hasText: 'NVDA' }).click()
  await expect(page.getByRole('heading', { level: 1, name: nvidia.name, exact: true })).toBeVisible()
  expect(dataRequests, 'Page content must come entirely from local fixtures').toEqual([])
})

test('malformed storage and duplicate, invalid saved IDs recover to valid unique collections', async ({ page }) => {
  await page.goto('/#/saved')
  await page.evaluate(() => {
    localStorage.setItem('wikipulse.savedEvents', '{not-valid-json')
    localStorage.setItem('wikipulse.savedStocks', JSON.stringify(['NVDA', 'NVDA', 'UNKNOWN', null, 5, {}]))
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: '관심의 흐름을 이어가세요' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^저장한 사건/ })).toContainText('0')
  await page.getByRole('button', { name: /^관심 종목/ }).click()
  await expect(page.locator('.saved-stock-list article')).toHaveCount(1)
  await expect(page.locator('.saved-stock-list')).toContainText(nvidia.name)

  await page.evaluate(eventId => {
    localStorage.setItem('wikipulse.savedEvents', JSON.stringify([eventId, eventId, 'unknown-event', null, {}]))
    localStorage.setItem('wikipulse.savedStocks', JSON.stringify({ NVDA: true }))
  }, hormuz.id)
  await page.reload()
  await expect(page.locator('.event-row')).toHaveCount(1)
  await expect(page.locator('.event-row')).toContainText(hormuz.title)
  await page.getByRole('button', { name: /^관심 종목/ }).click()
  await expect(page.getByRole('heading', { name: '궁금한 종목을 저장해 보세요' })).toBeVisible()
})

test('storage write failures warn clearly while retaining a usable session collection', async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = function () { throw new DOMException('Storage quota unavailable', 'QuotaExceededError') }
  })
  await page.goto(`/#/events/${hormuz.id}`)
  await page.getByRole('button', { name: '이벤트 저장', exact: true }).click()
  await expect(page.getByRole('button', { name: '저장됨', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.workspace-toast')).toContainText('브라우저 저장 공간을 사용할 수 없어 새로고침하면 사라집니다')
  await page.getByRole('navigation', { name: '주 메뉴' }).getByRole('link', { name: /^보관함/ }).click()
  await expect(page.locator('.event-row')).toHaveCount(1)
  await expect(page.locator('.event-row')).toContainText(hormuz.title)
  await page.getByRole('button', { name: `${hormuz.title} 저장 해제`, exact: true }).click()
  await expect(page.locator('.event-row')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '다음에 다시 보고 싶은 사건을 담아보세요' })).toBeVisible()
})

test('hash query preserves encoded Korean, ampersands, question marks and literal plus signs', async ({ page }) => {
  const query = 'AI & 기술? + 공급망'
  await page.goto(`/#/explore?q=${encodeURIComponent(query)}`)
  await expect(page.getByRole('heading', { name: '사건을 탐색하세요' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '사건 검색', exact: true })).toHaveValue(query)
  await expect(page.getByRole('heading', { name: '일치하는 사건이 없습니다' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('textbox', { name: '사건 검색', exact: true })).toHaveValue(query)
  await page.getByRole('button', { name: '필터 초기화', exact: true }).click()
  await expect(page.locator('.event-row')).toHaveCount(events.length)
})

test('820px tablet keeps all four navigation names and working destinations', async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 })
  await page.goto('/#/pulse')
  const navigation = page.getByRole('navigation', { name: '주 메뉴' })
  for (const [name, route, title] of [
    ['사건 탐색', '/explore', '사건을 탐색하세요'],
    ['종목 탐색', '/stocks', '종목에서 사건의 맥락을 찾으세요.'],
    ['보관함', '/saved', '관심의 흐름을 이어가세요'],
    ['Pulse Map', '/pulse', '세상의 변화가 모이는 곳'],
  ]) {
    const link = navigation.getByRole('link', { name, exact: true })
    await expect(link).toBeVisible()
    await expect(link).toHaveAccessibleName(name)
    await link.click()
    await expect(page).toHaveURL(new RegExp(`#${route}$`))
    await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
    await expect(link).toHaveAttribute('aria-current', 'page')
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
  }
})

test('WebGL unavailable fallback retains the full story and a keyboard-operable exit', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      if (/webgl/i.test(type)) return null
      return original.call(this, type, ...args)
    }
  })
  await page.goto('/')
  await expect(page.locator('.fallback-experience')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'WikiPulse', exact: true })).toBeVisible()
  for (const scene of ['Track', 'Cluster', 'Match']) {
    await expect(page.getByRole('heading', { name: new RegExp(`^${scene}\\.?$`) })).toBeVisible()
  }
  await expect(page.locator('canvas')).toHaveCount(0)
  const exit = page.getByRole('link', { name: 'Pulse Map 시작하기', exact: true })
  await exit.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/pulse$/)
  await expect(page.getByRole('heading', { name: '세상의 변화가 모이는 곳' })).toBeVisible()
  await expect(page.getByRole('main')).toHaveCount(1)
  await expect(page.locator('html')).not.toHaveClass(/scene-snap-enabled/)
})

test('seven-day map values are accumulated correctly and fourteen-day stock charts retain exact prices', async ({ page }) => {
  await page.goto('/#/pulse')
  const map = page.getByRole('region', { name: '사건 관계 지도' })
  await page.getByRole('button', { name: '7일', exact: true }).click()
  for (const event of events) {
    const points = event.chart.slice(-7)
    const edits = points.reduce((sum, point) => sum + point.edits, 0)
    const baseline = points.reduce((sum, point) => sum + point.baseline, 0)
    const pulse = Math.round(edits / baseline * 10) / 10
    await expect(map.getByRole('button', { name: `${event.title}, Pulse ${pulse}배`, exact: true })).toBeVisible()
    const row = page.locator('.event-row').filter({ has: page.getByRole('link', { name: event.title, exact: true }) })
    await expect(row.locator('.event-row__signal')).toContainText(`${pulse.toFixed(1)}×`)
    await expect(row.locator('.event-row__edits')).toContainText(formatNumber(edits))
  }
  await page.goto('/#/stocks/NVDA')
  await page.getByRole('group', { name: '예시 가격 차트 기간' }).getByRole('button', { name: '14일', exact: true }).click()
  const chart = page.getByRole('img', { name: /NVDA 예시 가격/ })
  await expect(chart).toHaveAttribute('aria-label', /14개 시점/)
  await expect(chart).toHaveAttribute('aria-label', new RegExp(`${nvidia.chart.at(-1).date} 값 ${nvidia.chart.at(-1).price}`))
  await chart.focus()
  await page.keyboard.press('ArrowLeft')
  await expect(chart).toHaveAttribute('aria-label', new RegExp(`${nvidia.chart.at(-2).date} 값 ${nvidia.chart.at(-2).price}`))
  for (let step = 0; step < 20; step++) await page.keyboard.press('ArrowLeft')
  await expect(chart).toHaveAttribute('aria-label', new RegExp(`${nvidia.chart.at(-14).date} 값 ${nvidia.chart.at(-14).price}`))
  for (let step = 0; step < 20; step++) await page.keyboard.press('ArrowRight')
  await expect(chart).toHaveAttribute('aria-label', new RegExp(`${nvidia.chart.at(-1).date} 값 ${nvidia.chart.at(-1).price}`))
})
