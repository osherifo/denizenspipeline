import { test, expect } from '../fixtures/api'

test.describe('Navigation', () => {
  test('renders the sidebar with app logo', async ({ apiPage: page }) => {
    await page.goto('/')
    await expect(page.getByText('fMRIflow')).toBeVisible()
  })

  test('opens module browser via hash route', async ({ apiPage: page }) => {
    await page.goto('/#modules')
    await expect(page.getByText('Module Browser')).toBeVisible()
    await expect(page.getByText('word_rate')).toBeVisible()
  })

  test('top-level groups expand on click', async ({ apiPage: page }) => {
    await page.goto('/')
    await page.getByText('Pipeline').first().click()
    await expect(page.getByText('Workflows')).toBeVisible()
  })

  test('sidebar links navigate', async ({ apiPage: page }) => {
    await page.goto('/#modules')
    await expect(page.getByText('Module Browser')).toBeVisible()
    await page.locator('a[href="#composer"]').click()
    await expect(page).toHaveURL(/#composer/)
  })
})
