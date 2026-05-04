import { test, expect } from '../fixtures/api'

test.describe('Module Browser', () => {
  test('renders module cards grouped by stage', async ({ apiPage: page }) => {
    await page.goto('/#modules')
    await expect(page.getByText('word_rate')).toBeVisible()
    await expect(page.getByText('phoneme_rate')).toBeVisible()
    await expect(page.getByText('audio_loader')).toBeVisible()
  })

  test('search filters cards', async ({ apiPage: page }) => {
    await page.goto('/#modules')
    await page.getByPlaceholder(/Search modules/).fill('phoneme')
    await expect(page.getByText('phoneme_rate')).toBeVisible()
    await expect(page.getByText('word_rate')).not.toBeVisible()
  })

  test('clicking a card expands it', async ({ apiPage: page }) => {
    await page.goto('/#modules')
    await page.getByText('word_rate').click()
    await expect(page.getByText(/click to expand/)).not.toBeVisible()
  })
})
