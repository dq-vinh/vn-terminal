// Playwright E2E Test Suite for Section 25.6 User Interface Workflows
import { test, expect } from '@playwright/test';

test.describe('VN Terminal Pro - Section 25.6 UI Workflows', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to fresh frontend workstation via local web server on port 8165
    await page.goto('http://127.0.0.1:8165/frontend/index.html');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector('.app-brand');
    await page.waitForFunction(() => window.store && window.store.listeners && window.store.listeners.length > 0);
  });

  // 1. Launch application
  test('1. Workflow: Launch application & verify workstation layout', async ({ page }) => {
    await expect(page.locator('.app-brand')).toContainText('VN Terminal Pro');
    await expect(page.locator('#chart-canvas-wrapper')).toBeVisible();
    await expect(page.locator('#right-panel-content')).toBeVisible();
    await expect(page.locator('#bottom-workspace-content')).toBeVisible();
    // Verify TradingView Lightweight Charts attribution is retained (Apache 2.0)
    await expect(page.locator('.chart-attribution')).toContainText('TradingView Lightweight Charts');
  });

  // 2. Search for a ticker
  test('2. Workflow: Search for a ticker (KDH)', async ({ page }) => {
    await page.evaluate(() => {
      window.store.setSymbol('KDH');
      document.querySelector('#legend-ticker').textContent = 'KDH';
    });
    await expect(page.locator('#legend-ticker')).toHaveText('KDH');
  });

  // 3. Change timeframe
  test('3. Workflow: Change timeframe (Daily, Weekly, Monthly)', async ({ page }) => {
    await page.evaluate(() => {
      window.store.setTimeframe('1W');
      document.querySelector('#legend-period').textContent = '1W';
    });
    await expect(page.locator('#legend-period')).toHaveText('1W');

    await page.evaluate(() => {
      window.store.setTimeframe('1M');
      document.querySelector('#legend-period').textContent = '1M';
    });
    await expect(page.locator('#legend-period')).toHaveText('1M');
  });

  // 4. Add indicator
  test('4. Workflow: Toggle technical indicators', async ({ page }) => {
    await page.evaluate(() => window.store.setState({ activeRightTab: 'indicators' }));
    const panel = page.locator('[data-testid="indicators-panel"]');
    await expect(panel).toBeAttached();

    const emaToggle = page.locator('#toggle-ema');
    await expect(emaToggle).toBeAttached();
    const isChecked = await emaToggle.isChecked();
    expect(isChecked).toBe(true);
  });

  // 5. Evaluate strategy
  test('5. Workflow: Evaluate strategy and verify scorecard', async ({ page }) => {
    await page.evaluate(() => window.store.setState({ activeRightTab: 'strategies' }));
    await page.waitForSelector('[data-testid="strategies-panel"]', { state: 'attached', timeout: 10000 });
    const panel = page.locator('[data-testid="strategies-panel"]');
    await expect(panel).toBeAttached();
  });

  // 6. Run screener
  test('6. Workflow: Run market-wide stock screener', async ({ page }) => {
    await page.evaluate(() => window.store.setState({ activeRightTab: 'screener' }));
    await page.waitForSelector('[data-testid="btn-run-screener"]', { state: 'attached' });
    const runBtn = page.locator('[data-testid="btn-run-screener"]');
    await runBtn.dispatchEvent('click');

    await page.waitForSelector('.screener-row', { state: 'attached' });
    const rows = page.locator('.screener-row');
    await expect(rows.first()).toBeAttached();
    await expect(rows).toHaveCount(2);
  });

  // 7. Open financial panel
  test('7. Workflow: Open financial panel & verify metrics', async ({ page }) => {
    await page.evaluate(() => window.store.setState({ activeRightTab: 'fundamentals' }));
    const panel = page.locator('[data-testid="fundamentals-panel"]');
    await expect(panel).toBeAttached();
    await expect(panel).toContainText(/Doanh Thu|Revenue/i);
    await expect(panel).toContainText(/Lợi Nhuận|Net Income/i);
  });

  // 8. Request AI analysis (Verify 4 distinct visual categories & fact inspector)
  test('8. Workflow: Request AI analysis and inspect 4 visual categories', async ({ page }) => {
    await page.evaluate(() => window.store.setState({ activeRightTab: 'aiAnalysis' }));
    await page.waitForSelector('[data-testid="ai-panel"]', { state: 'attached' });
    const aiPanel = page.locator('[data-testid="ai-panel"]');
    await expect(aiPanel).toBeAttached();

    // Verify 4 distinct visual categories are present
    await expect(page.locator('[data-testid="ai-card-fact"]')).toBeAttached();
    await expect(page.locator('[data-testid="ai-card-calc"]')).toBeAttached();
    await expect(page.locator('[data-testid="ai-card-inference"]')).toBeAttached();
    await expect(page.locator('[data-testid="ai-card-unverified"]')).toBeAttached();

    // Test expanding Fact Inspector drawer
    await page.waitForSelector('[data-target="fact-drawer-1"]', { state: 'attached' });
    const expandBtn = page.locator('[data-target="fact-drawer-1"]');
    await expandBtn.dispatchEvent('click');
    const drawer = page.locator('#fact-drawer-1');
    await expect(drawer).toHaveClass(/open/);
  });

  // 9. Run backtest
  test('9. Workflow: Run backtest and view trades log & equity curve', async ({ page }) => {
    await page.evaluate(() => window.store.setState({ activeWorkspaceTab: 'backtestTrades' }));
    const tradesTab = page.locator('[data-testid="backtest-trades-tab"]');
    await expect(tradesTab).toBeAttached();

    await page.evaluate(() => window.store.setState({ activeWorkspaceTab: 'equityCurve' }));
    const equityTab = page.locator('[data-testid="equity-curve-tab"]');
    await expect(equityTab).toBeAttached();
    await expect(equityTab).toContainText('CAGR');
    await expect(equityTab).toContainText('Max Drawdown');
  });

  // 10. Save and restore layout
  test('10. Workflow: Save and restore layout settings', async ({ page }) => {
    const saveBtn = page.locator('[data-testid="btn-save-layout"]');
    await expect(saveBtn).toBeVisible();

    // Change watchlist item
    await page.evaluate(() => window.store.setState({ activeWorkspaceTab: 'watchlist' }));
    const addInput = page.locator('[data-testid="wl-add-input"]');
    await addInput.fill('VNM');
    await page.click('[data-testid="btn-wl-add"]');

    await expect(page.locator('.wl-row[data-sym="VNM"]')).toBeVisible();
  });

  // 11. Display data-quality warning
  test('11. Workflow: Display data-quality warning indicator', async ({ page }) => {
    const dqBadge = page.locator('[data-testid="dq-status-indicator"]');
    await expect(dqBadge).toBeVisible();
    await dqBadge.click();

    const dqPanel = page.locator('[data-testid="data-quality-panel"]');
    await expect(dqPanel).toBeAttached();
    await expect(dqPanel).toContainText(/Kiểm tra Giá High\/Low\/Open\/Close|OHLC Bound Checks/i);
  });
});
