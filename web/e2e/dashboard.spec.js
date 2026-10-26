import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const screenshots = path.resolve('../reports/dashboard')
test.beforeAll(() => fs.mkdirSync(screenshots, { recursive: true }))

test('report renders, filters match API, and exports figures and data', async ({ page, request }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const response = await request.get('/api/v1/dashboard?start=2018&end=2024')
  expect(response.ok()).toBeTruthy()
  const expected = (await response.json()).totals.registros
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Homicidios y contexto territorial', exact: true })).toBeVisible()
  await expect(page.locator('.kpi-value').first()).toContainText(/\d/)
  expect(Number((await page.locator('.kpi-value').first().innerText()).replace(/\D/g, ''))).toBe(expected)
  await expect(page.getByRole('heading', { name: 'Mapa de calor temporal' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Composición por sexo' })).toBeVisible()
  await expect(page.locator('iframe')).toHaveCount(0)
  await page.screenshot({ path: path.join(screenshots, 'resumen_desktop.png'), fullPage: true })
  await page.screenshot({ path: path.join(screenshots, 'resumen_portada.png'), fullPage: false })
  const provinceResponse = page.waitForResponse(r => r.url().includes('/api/v1/dashboard') && r.url().includes('GUAYAS') && r.ok())
  await page.getByLabel('Añadir provincia').selectOption('GUAYAS')
  const data = await (await provinceResponse).json()
  await expect(page.locator('.kpi-value').first()).toHaveText(new Intl.NumberFormat('es-EC').format(data.totals.registros))
  await expect(page).toHaveURL(/provinces=GUAYAS/)
  const downloadFigure = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Descargar figura: Evolución y comparación temporal', exact: true }).click()
  expect((await downloadFigure).suggestedFilename()).toMatch(/\.png$/)
  const downloadCsv = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSV', exact: true }).first().click()
  expect((await downloadCsv).suggestedFilename()).toMatch(/\.csv$/)
  expect(errors).toEqual([])
})

test('partial arms quantity and absent territory are never replaced by zero', async ({ page }) => {
  await page.goto('/armas?start=2025&end=2025')
  await expect(page.getByText('Hay períodos parciales.', { exact: true })).toBeVisible()
  const card = page.locator('.kpi-card').filter({ hasText: 'Cantidad observada de armas' })
  await expect(card.locator('.kpi-value')).toHaveText('Sin dato')
  await page.goto('/homicidios?start=2014&end=2014&provinces=GAL%C3%81PAGOS')
  await expect(page.getByText('No hay registros observados para esta selección.', { exact: false })).toBeVisible()
  await expect(page.locator('.kpi-card')).toHaveCount(0)
})

test('context and frozen evaluation communicate their scope', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/contexto')
  await expect(page.getByRole('heading', { name: 'Contexto socioeconómico', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Homicidios y pobreza: observaciones provincia–año' })).toBeVisible()
  await page.getByRole('link', { name: 'Evaluación predictiva', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Comparación de errores' })).toBeVisible()
  await expect(page.getByText('Experimento, no modelo operativo aprobado.', { exact: true })).toBeVisible()
  await page.getByLabel('Provincia evaluada').selectOption('GALÁPAGOS')
  await expect(page.getByText('Esta provincia no pertenece al conjunto evaluado', { exact: false })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile navigation and layout remain readable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.locator('.kpi-value').first()).toContainText(/\d/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBeTruthy()
  await page.getByLabel('Abrir navegación').click()
  await page.getByRole('link', { name: 'Homicidios', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Homicidios registrados', exact: true })).toBeVisible()
  await expect(page.locator('.kpi-value').first()).toContainText(/\d/)
  await page.screenshot({ path: path.join(screenshots, 'homicidios_mobile.png'), fullPage: true })
})

test('a failed request is an error, not a zero indicator', async ({ page }) => {
  await page.route('**/api/v1/dashboard?*', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Error de prueba de conexión' }) }))
  await page.goto('/')
  await expect(page.getByText('Error de prueba de conexión', { exact: false })).toBeVisible()
  await expect(page.locator('.kpi-card')).toHaveCount(0)
})
