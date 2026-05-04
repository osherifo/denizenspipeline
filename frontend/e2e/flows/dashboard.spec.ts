import { test, expect } from '../fixtures/api'

test.describe('Experiment Dashboard', () => {
  test('renders config browser sidebar with grouping', async ({ apiPage: page }) => {
    await page.goto('/#dashboard')
    await expect(page.getByPlaceholder('Search configs...')).toBeVisible()
    await expect(page.getByText('reading_en').first()).toBeVisible()
  })

  test('search filters configs', async ({ apiPage: page }) => {
    await page.goto('/#dashboard')
    await expect(page.getByText('reading_en/sub-01')).toBeVisible()
    await page.getByPlaceholder('Search configs...').fill('does-not-exist')
    await expect(page.getByText('reading_en/sub-01')).not.toBeVisible()
  })

  test('rescan button is visible', async ({ apiPage: page }) => {
    await page.goto('/#dashboard')
    await expect(page.getByRole('button', { name: 'Rescan' })).toBeVisible()
  })
})
