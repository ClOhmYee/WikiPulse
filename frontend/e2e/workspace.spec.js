import { test, expect } from '@playwright/test'
import { events, stocks } from '../src/data/mock/fixtures/catalog.js'

const hormuz = events.find(event => event.id === 'iran-hormuz-2025')
const chips = events.find(event => event.id === 'ai-chip-controls')
const nvidia = stocks.find(stock => stock.symbol === 'NVDA')

// Each test uses a new browser context. Save tests explicitly exercise reloads;
// no storage seeds, network stubs or state changes bypass the user interface.
test.beforeEach(async ({ page }) => {
  page.__workspaceErrors = []
  page.on('pageerror', error => page.__workspaceErrors.push(error.message))
})

test.afterEach(async ({ page }) => {
  expect(page.__workspaceErrors, 'No uncaught browser errors during the user journey').toEqual([])
})

async function openWorkspace(page, path = '/pulse') {
  await page.goto(`/#${path}`)
  await expect(page.getByRole('navigation', { name: '주 메뉴' })).toBeVisible()
  await expect(page.getByRole('main')).toHaveCount(1)
}

async function expectNoHorizontalOverflow(page) {
  await expect.poll(() => page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  })).then(size => size.content - size.viewport), {
    message: 'The document should not scroll sideways at this viewport',
  }).toBeLessThanOrEqual(1)
}

test('onboarding CTA opens the workspace and releases onboarding scroll state', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: '탐색 시작하기' })).toBeVisible()
  await page.getByRole('link', { name: '탐색 시작하기' }).click()
  await expect(page).toHaveURL(/#\/pulse$/)
  await expect(page.getByRole('heading', { name: '세상의 변화가 모이는 곳' })).toBeVisible()
  await expect(page.locator('html')).not.toHaveClass(/scene-snap-enabled/)
  await expect(page.getByRole('region', { name: '사건 관계 지도' })).toBeVisible()
})

test('map selection, zoom, pan, reset and snapshot selection update the same view', async ({ page }) => {
  await openWorkspace(page);
  const map = page.getByRole('region', { name: '사건 관계 지도' });
  const preview = page.getByRole('complementary', { name: '선택한 사건' });
  await map.getByRole('button', { name: new RegExp(chips.title) }).locator('.document-cluster__title').click();
  await expect(preview.getByRole('heading', { name: chips.title })).toBeVisible();
  const group = map.locator('svg > g[transform]');
  await page.getByRole('button', { name: '지도 위치 초기화' }).click();
  const initial = await group.getAttribute('transform');
  await page.getByRole('button', { name: '지도 확대', exact: true }).click();
  await expect(group).not.toHaveAttribute('transform', initial);
  for (let i = 0; i < 24; i++) {
    const control = page.getByRole('button', { name: '지도 확대', exact: true });
    if (await control.isEnabled()) await control.click();
  }
  await expect(page.getByRole('button', { name: '지도 확대', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '지도 위치 초기화' }).click();
  await expect(group).toHaveAttribute('transform', initial);
  await map.getByRole('group', { name: '이슈와 문서 관계 그래프' }).scrollIntoViewIfNeeded();
  const box = await map.getByRole('group', { name: '이슈와 문서 관계 그래프' }).boundingBox();
  await page.mouse.move(box.x + 8, box.y + 8);
  await page.mouse.down();
  await page.mouse.move(box.x + 58, box.y + 28, { steps: 4 });
  await page.mouse.up();
  await expect(group).not.toHaveAttribute('transform', initial);
  await page.getByRole('button', { name: '지도 위치 초기화' }).click();
  await expect(group).toHaveAttribute('transform', initial);
  await page.getByRole('button', { name: '이전 시점', exact: true }).click();
  await expect(map).toHaveAttribute('data-snapshot', '2026-09-09T00:00:00.000Z');
  await expect(preview).toHaveAttribute('data-snapshot', '2026-09-09T00:00:00.000Z');
  await expect(preview.getByRole('heading', { name: chips.title })).toBeVisible();
  await preview.getByRole('link', { name: '사건 자세히 보기' }).click();
  await expect(page).toHaveURL(/#\/issues\/ai-chip-controls~2026-09-09$/);
  await expect(page.getByRole('heading', { level: 1, name: chips.title })).toBeVisible();
});

test('event query, category, sorting and empty-state reset return the right events', async ({ page }) => {
  await openWorkspace(page, '/issues')
  await expect(page.locator('.event-row')).toHaveCount(events.length)
  await page.getByRole('textbox', { name: '사건 검색', exact: true }).fill('원자력')
  await expect(page.locator('.event-row')).toHaveCount(events.filter(e => `${e.title} ${e.summary} ${e.keywords.join(' ')}`.includes('원자력')).length)
  await expect(page.locator('.event-row').first()).toContainText('원자력 발전과 우라늄')
  await page.getByRole('button', { name: '검색어 지우기', exact: true }).click()
  await page.getByRole('button', { name: '기술', exact: true }).click()
  await expect(page.locator('.event-row')).toHaveCount(events.filter(e => e.category === 'technology').length)
  await page.getByRole('button', { name: /^전체/ }).click()
  await page.getByRole('combobox', { name: '사건 정렬' }).selectOption('recent')
  await expect(page.locator('.event-row').first()).toContainText([...events].sort((a,b) => b.startAt.localeCompare(a.startAt))[0].title)
  await page.getByRole('combobox', { name: '사건 정렬' }).selectOption('pulse')
  await expect(page.locator('.event-row').first()).toContainText([...events].sort((a,b) => b.pulse-a.pulse)[0].title)
  await page.getByRole('textbox', { name: '사건 검색', exact: true }).fill('no-such-event-zz123')
  await expect(page.getByRole('heading', { name: '일치하는 사건이 없습니다' })).toBeVisible()
  await expect(page.locator('.event-row')).toHaveCount(0)
  await page.getByRole('button', { name: '필터 초기화', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '사건 검색', exact: true })).toHaveValue('')
  await expect(page.locator('.event-row')).toHaveCount(events.length)
})

test('event tabs support keyboard navigation, news filters and evidence drilldown', async ({ page }) => {
  await openWorkspace(page, `/issues/${hormuz.id}`)
  await expect(page.getByRole('heading', { name: hormuz.title, exact: true })).toBeVisible()
  const overview = page.getByRole('tab', { name: '이벤트 개요' })
  await overview.focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: '타임라인' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('heading', { name: '변화가 이어진 순서' })).toBeVisible()
  await page.keyboard.press('End')
  await expect(page.getByRole('tab', { name: '토론', exact: true })).toBeFocused()
  await page.getByRole('tab', { name: /^근거 문서/ }).click()
  await expect(page.locator('.dt-evidence-row')).toHaveCount(hormuz.articleIds.length)
  await page.getByRole('tab', { name: '관련 소식' }).click()
  const news = page.getByRole('region', { name: '관련 소식 목록' })
  await expect(news.locator('.dt-news-item')).toHaveCount(hormuz.news.length)
  await news.getByRole('button', { name: /^분석/ }).click()
  await expect(news.locator('.dt-news-item')).toHaveCount(hormuz.news.filter(item => item.type === 'analysis').length)
  await expect(news.locator('.dt-news-item').first()).toContainText('분석 예시')
  await news.getByRole('searchbox', { name: '관련 소식 검색' }).fill('no-such-news-zz123')
  await expect(news.getByRole('heading', { name: '조건에 맞는 소식이 없어요' })).toBeVisible()
  await news.getByRole('button', { name: '검색 조건 초기화' }).click()
  await expect(news.locator('.dt-news-item')).toHaveCount(hormuz.news.length)
  await page.getByRole('tab', { name: /^근거 문서/ }).click()
  const source = page.locator('.dt-evidence-row').filter({ has: page.getByRole('heading', { name: '호르무즈 해협', exact: true }) })
  await expect(source).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/Strait_of_Hormuz')
  await expect(source).toHaveAttribute('target', '_blank')
})

test('event overview chart range, baseline and selected related document update', async ({ page }) => {
  await openWorkspace(page, `/issues/${hormuz.id}`)
  const chart = page.getByRole('img', { name: /이벤트 편집량 추이 예시/ })
  await expect(chart).toHaveAttribute('aria-label', /24개 시점/)
  await page.locator('[aria-label="편집 차트 기간"]').getByRole('button', { name: '7일', exact: true }).click()
  await expect(chart).toHaveAttribute('aria-label', /7개 시점/)
  const baseline = page.getByRole('checkbox', { name: '평소 편집량' })
  await expect(baseline).toBeChecked()
  await baseline.uncheck()
  await expect(chart.locator('polyline[stroke-dasharray]')).toHaveCount(0)
  await baseline.check()
  await expect(chart.locator('polyline[stroke-dasharray]')).toHaveCount(1)
  await page.locator('.wp-article-network__links').getByRole('button', { name: '이란', exact: true }).click()
  await expect(page.locator('.dt-network-detail').getByRole('heading', { name: '이란', exact: true })).toBeVisible()
  await expect(page.locator('.dt-network-detail').getByRole('link', { name: /위키백과 원문 보기/ })).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/Iran')
})

test('event keyword links arrive in a filtered explorer and survive reload', async ({ page }) => {
  await openWorkspace(page, `/issues/${hormuz.id}`)
  const keyword = hormuz.keywords[0]
  await page.locator('.dt-keywords').getByRole('link', { name: `#${keyword}`, exact: true }).click()
  await expect(page.getByRole('heading', { name: '사건을 탐색하세요' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '사건 검색', exact: true })).toHaveValue(keyword)
  await expect(page.locator('.event-row')).toHaveCount(events.filter(e => e.keywords.includes(keyword)).length)
  await page.reload()
  await expect(page.getByRole('textbox', { name: '사건 검색', exact: true })).toHaveValue(keyword)
  await expect(page.locator('.event-row').first()).toContainText(hormuz.title)
})

test('stock directory filters and event-specific connection types select the right companies', async ({ page }) => {
  await openWorkspace(page, '/stocks')
  await expect(page.locator('.st-stock-row')).toHaveCount(stocks.length)
  await page.getByRole('textbox', { name: '종목 검색', exact: true }).fill('NVDA')
  await expect(page.locator('.st-stock-row')).toHaveCount(1)
  await expect(page.locator('.st-stock-row')).toContainText(nvidia.name)
  await page.getByRole('button', { name: '종목 검색어 지우기' }).click()
  await page.getByRole('combobox', { name: '산업 필터' }).selectOption('기술')
  await expect(page.locator('.st-stock-row')).toHaveCount(stocks.filter(s => s.sector === '기술').length)
  await expect(page.locator('.st-stock-row').filter({ hasText: 'ASML' })).toBeVisible()
  await page.getByRole('button', { name: '필터 초기화', exact: true }).click()
  await page.getByRole('textbox', { name: '종목 검색', exact: true }).fill('no-such-stock-zz123')
  await expect(page.getByRole('heading', { name: '조건에 맞는 종목이 없습니다.' })).toBeVisible()
  await page.getByRole('button', { name: '전체 종목 보기' }).click()
  await expect(page.locator('.st-stock-row')).toHaveCount(stocks.length)
  await openWorkspace(page, `/issues/${chips.id}/stocks`)
  await expect(page.locator('.st-stock-row')).toHaveCount(chips.stockSymbols.length)
  await page.getByRole('combobox', { name: '연결 유형 필터' }).selectOption('supply')
  await expect(page.locator('.st-stock-row')).toHaveCount(0)
  await page.getByRole('combobox', { name: '연결 유형 필터' }).selectOption('direct')
  await expect(page.locator('.st-stock-row')).toHaveCount(0)
  await page.getByRole('combobox', { name: '연결 유형 필터' }).selectOption('industry')
  await expect(page.locator('.st-stock-row')).toHaveCount(chips.stockSymbols.length)
  await page.locator('.st-stock-identity').filter({ hasText: 'NVDA' }).click()
  await expect(page).toHaveURL(/#\/stocks\/NVDA$/)
  await expect(page.getByRole('heading', { name: nvidia.name, exact: true })).toBeVisible()
})

test('stock detail explains the path, offers example chart ranges and links back to its event', async ({ page }) => {
  await openWorkspace(page, '/stocks/NVDA')
  await expect(page.getByRole('list', { name: '사건과 기업의 연결 경로' }).first()).toContainText('엔비디아')
  await expect(page.locator('.st-relationship').first()).toContainText(nvidia.relations[0].explanation)
  await page.getByRole('group', { name: '사건 연결 유형' }).getByRole('button', { name: '산업·기술' }).click()
  await expect(page.locator('.st-timeline-event')).toHaveCount(nvidia.eventIds.length)
  await page.getByRole('group', { name: '예시 가격 차트 기간' }).getByRole('button', { name: '7일', exact: true }).click()
  await expect(page.getByRole('img', { name: /NVDA 예시 가격/ })).toHaveAttribute('aria-label', /7개 시점/)
  await page.locator(`a[href="#/issues/${chips.id}"]`).filter({ hasText: '사건과 근거 살펴보기' }).click()
  await expect(page).toHaveURL(new RegExp(`#\\/issues\\/${chips.id}$`))
  await expect(page.getByRole('heading', { name: chips.title, exact: true })).toBeVisible()
})

test('saved events and stocks persist after reload and are removable from the collection', async ({ page }) => {
  await openWorkspace(page, `/issues/${hormuz.id}`)
  await page.getByRole('button', { name: '이벤트 저장', exact: true }).click()
  await expect(page.getByRole('button', { name: '저장됨', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await openWorkspace(page, '/stocks/NVDA')
  await page.getByRole('button', { name: '엔비디아 관심 종목에 추가', exact: true }).click()
  await page.getByRole('navigation', { name: '주 메뉴' }).getByRole('link', { name: /^보관함/ }).click()
  await expect(page.locator('.event-row')).toHaveCount(1)
  await page.reload()
  await expect(page.locator('.event-row')).toContainText(hormuz.title)
  await page.getByRole('button', { name: /^관심 종목/ }).click()
  await expect(page.locator('.saved-stock-list article')).toHaveCount(1)
  await expect(page.locator('.saved-stock-list')).toContainText('엔비디아')
  await page.getByRole('button', { name: '엔비디아 관심 종목 해제', exact: true }).click()
  await expect(page.getByRole('heading', { name: '궁금한 종목을 저장해 보세요' })).toBeVisible()
  await page.getByRole('button', { name: /^저장한 사건/ }).click()
  await page.getByRole('button', { name: `${hormuz.title} 저장 해제`, exact: true }).click()
  await expect(page.getByRole('heading', { name: '다음에 다시 보고 싶은 사건을 담아보세요' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: /^저장한 사건/ })).toContainText('0')
  await expect(page.getByRole('button', { name: /^관심 종목/ })).toContainText('0')
})

test('global keyboard search supports focus, result selection, Escape and an empty result', async ({ page }) => {
  await openWorkspace(page, '/issues')
  await page.keyboard.press('Control+k')
  const search = page.getByRole('combobox', { name: '전체 검색', exact: true })
  await expect(search).toBeFocused()
  await search.fill('NVDA')
  await expect(page.getByRole('listbox', { name: '전체 검색 결과' })).toBeVisible()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('option', { name: /엔비디아/ })).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/stocks\/NVDA$/)
  await expect(search).toHaveValue('')
  await page.keyboard.press('Control+k')
  await search.fill('no-global-match-zz123')
  await expect(page.getByRole('listbox')).toContainText('결과가 없습니다')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await expect(search).toHaveValue('')
})

test('browser back and forward restore the visited event and stock routes', async ({ page }) => {
  await openWorkspace(page, '/issues')
  await page.locator(`.event-row a[href="#/issues/${hormuz.id}"]`).click()
  await expect(page).toHaveURL(new RegExp(`#\\/issues\\/${hormuz.id}$`))
  await page.getByRole('link', { name: '종목 연결 근거 보기' }).click()
  await expect(page).toHaveURL(new RegExp(`#\\/issues\\/${hormuz.id}\\/stocks$`))
  await page.goBack()
  await expect(page.getByRole('heading', { name: hormuz.title, exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading', { name: '사건을 탐색하세요' })).toBeVisible()
  await page.goForward()
  await expect(page.getByRole('heading', { name: hormuz.title, exact: true })).toBeVisible()
})

test('unknown issue, stock and route IDs show a usable recovery instead of crashing', async ({ page }) => {
  for (const [route, title] of [
    ['/issues/not-a-real-event', '이벤트를 찾을 수 없어요'],
    ['/stocks/NOTREAL', '종목을 찾지 못했습니다.'],
    ['/issues/not-a-real-event/stocks', '연결할 사건을 찾지 못했습니다.'],
    ['/does-not-exist', '페이지를 찾을 수 없습니다'],
  ]) {
    await openWorkspace(page, route)
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
    await expect(page.locator('.wp-empty').getByRole('link')).toBeVisible()
  }
})

test.describe('compact workspace', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

  test('390px navigation, event evidence and stock list remain usable without document overflow', async ({ page }) => {
    await openWorkspace(page)
    await expectNoHorizontalOverflow(page)
    const navigation = page.getByRole('navigation', { name: '주 메뉴' })
    await navigation.getByRole('link', { name: '이슈 탐색', exact: true }).click()
    await expect(page.getByRole('heading', { name: '사건을 탐색하세요' })).toBeVisible()
    await expectNoHorizontalOverflow(page)
    await page.locator('.event-row').getByRole('link', { name: hormuz.title, exact: true }).first().click()
    await expect(page.getByRole('heading', { name: hormuz.title, exact: true })).toBeVisible()
    await expectNoHorizontalOverflow(page)
    await page.getByRole('tab', { name: /^근거 문서/ }).click()
    await expect(page.locator('.dt-evidence-row')).toHaveCount(hormuz.articleIds.length)
    await expectNoHorizontalOverflow(page)
    await navigation.getByRole('link', { name: '종목 탐색', exact: true }).click()
    await expect(page.locator('.st-stock-row')).toHaveCount(stocks.length)
    await expectNoHorizontalOverflow(page)
    await page.getByRole('textbox', { name: '종목 검색', exact: true }).fill('NVDA')
    await page.locator('.st-stock-identity').click()
    await expect(page.getByRole('heading', { name: '엔비디아', exact: true })).toBeVisible()
    await expectNoHorizontalOverflow(page)
    await navigation.getByRole('link', { name: /^보관함/ }).click()
    await expect(page.getByRole('heading', { name: '관심의 흐름을 이어가세요' })).toBeVisible()
    await expectNoHorizontalOverflow(page)
  })
})

test.describe('reduced motion onboarding', () => {
  test.use({ reducedMotion: 'reduce' })

  test('the final scene CTA exits with motion reduction enabled', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/')
    expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true)
    await expect(page.getByRole('link', { name: '탐색 시작하기' })).toBeVisible()
    const lastScene = page.getByRole('button', { name: '04. Match', exact: true })
    if (await lastScene.count()) {
      await lastScene.click()
      await expect(page.locator('.experience')).toHaveAttribute('data-reduced-motion', 'true')
      await expect(page.locator('.experience')).toHaveAttribute('data-scene', '4')
    }
    await page.getByRole('link', { name: 'Pulse Map 시작하기', exact: true }).click()
    await expect(page).toHaveURL(/#\/pulse$/)
    await expect(page.getByRole('heading', { name: '세상의 변화가 모이는 곳' })).toBeVisible()
    await expect(page.locator('html')).not.toHaveClass(/scene-snap-enabled/)
  })
})
