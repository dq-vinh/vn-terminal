// VN Terminal Pro Frontend Workstation - Main Application Entry (WP4, WP11, WP12)
import { i18n } from './i18n/index.js';
import { store } from './state/store.js';
import { fixtureClient } from './api/fixtureClient.js';
import { ChartManager } from './chart/chartManager.js';
import { TopToolbar } from './components/topToolbar.js';

// Right Panel Components
import { IndicatorsPanel } from './panels/indicatorsPanel.js';
import { StrategiesPanel } from './panels/strategiesPanel.js';
import { ScreenerPanel } from './panels/screenerPanel.js';
import { FundamentalsPanel } from './panels/fundamentalsPanel.js';
import { AiPanel } from './panels/aiPanel.js';
import { DataQualityPanel } from './panels/dataQualityPanel.js';

// Bottom Workspace Components
import { WatchlistTab } from './workspace/watchlistTab.js';
import { CurrentSignalsTab } from './workspace/currentSignalsTab.js';
import { SignalHistoryTab } from './workspace/signalHistoryTab.js';
import { BacktestTradesTab } from './workspace/backtestTradesTab.js';
import { EquityCurveTab } from './workspace/equityCurveTab.js';
import { PortfolioNotesTab } from './workspace/portfolioNotesTab.js';
import { DataRefreshLogTab } from './workspace/dataRefreshLogTab.js';

// Expose global window references for debugging / E2E test state verification
window.store = store;
window.fixtureClient = fixtureClient;

class Application {
  constructor() {
    this.chartManager = null;
    this.topToolbar = null;
    this.currentSymbol = '';
    this.currentTimeframe = '';
    this.currentBarCount = 0;
  }

  async init() {
    console.log('Initializing VN Terminal Pro Workstation Frontend...');

    // 1. Mount Right Panel Tabs
    this.initRightPanel();

    // 2. Mount Bottom Workspace Tabs
    this.initBottomWorkspace();

    // 3. Mount Top Toolbar
    const toolbarContainer = document.querySelector('#toolbar-container');
    if (toolbarContainer) {
      this.topToolbar = new TopToolbar(toolbarContainer);
      this.topToolbar.init();
    }

    // 4. Mount Chart Workspace
    const chartContainer = document.querySelector('#chart-canvas-wrapper');
    if (chartContainer) {
      this.chartManager = new ChartManager(chartContainer);
      this.chartManager.init();
    }

    // 5. Bind Store Subscriptions
    store.subscribe(() => this.onStateChange());
    i18n.onChange(() => this.updateUiTranslations());

    // 6. Bind Chart Controls
    this.bindChartControls();

    // Initial Data & Tab Visibility Sync
    this.onStateChange(true);
  }

  initRightPanel() {
    const panelsMap = {
      indicators: new IndicatorsPanel(document.querySelector('#pane-indicators')),
      strategies: new StrategiesPanel(document.querySelector('#pane-strategies')),
      screener: new ScreenerPanel(document.querySelector('#pane-screener')),
      fundamentals: new FundamentalsPanel(document.querySelector('#pane-fundamentals')),
      aiAnalysis: new AiPanel(document.querySelector('#pane-ai-analysis')),
      dataQuality: new DataQualityPanel(document.querySelector('#pane-data-quality')),
    };

    Object.values(panelsMap).forEach(panel => panel.init());

    // Direct Event Listeners for Right Tab Switching
    const tabHeader = document.querySelector('#right-tab-header');
    if (tabHeader) {
      tabHeader.querySelectorAll('button.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const tab = btn.getAttribute('data-tab');
          if (tab) store.setState({ activeRightTab: tab });
        });
      });
    }
  }

  initBottomWorkspace() {
    const workspaceMap = {
      watchlist: new WatchlistTab(document.querySelector('#pane-watchlist')),
      currentSignals: new CurrentSignalsTab(document.querySelector('#pane-current-signals')),
      signalHistory: new SignalHistoryTab(document.querySelector('#pane-signal-history')),
      backtestTrades: new BacktestTradesTab(document.querySelector('#pane-backtest-trades')),
      equityCurve: new EquityCurveTab(document.querySelector('#pane-equity-curve')),
      portfolioNotes: new PortfolioNotesTab(document.querySelector('#pane-portfolio-notes')),
      dataRefreshLog: new DataRefreshLogTab(document.querySelector('#pane-data-refresh-log')),
    };

    Object.values(workspaceMap).forEach(tab => tab.init());

    // Direct Event Listeners for Bottom Workspace Tab Switching
    const tabHeader = document.querySelector('#bottom-tab-header');
    if (tabHeader) {
      tabHeader.querySelectorAll('button.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const tab = btn.getAttribute('data-tab');
          if (tab) store.setState({ activeWorkspaceTab: tab });
        });
      });
    }
  }

  onStateChange(force = false) {
    const s = store.getState();

    // Synchronously update legend title elements
    const legendTicker = document.querySelector('#legend-ticker');
    const legendPeriod = document.querySelector('#legend-period');
    if (legendTicker) legendTicker.textContent = s.symbol;
    if (legendPeriod) legendPeriod.textContent = s.timeframe;

    // 1. Sync Tab Visibilities SYNCHRONOUSLY
    this.syncTabVisibilities();

    // 2. Sync Chart Data ASYNCHRONOUSLY
    this.syncChartData(force);
  }

  syncTabVisibilities() {
    const s = store.getState();

    // Sync Right Panel Active Tab
    const rightHeader = document.querySelector('#right-tab-header');
    if (rightHeader) {
      rightHeader.querySelectorAll('.tab-btn').forEach(btn => {
        const isActive = (btn.getAttribute('data-tab') === s.activeRightTab);
        btn.classList.toggle('active', isActive);
      });
      const activeRightId = `pane-${this._camelToKebab(s.activeRightTab)}`;
      document.querySelectorAll('#right-panel-content .tab-pane').forEach(pane => {
        const isActive = (pane.id === activeRightId);
        pane.classList.toggle('active', isActive);
        pane.style.display = isActive ? 'block' : 'none';
      });
    }

    // Sync Bottom Workspace Active Tab
    const bottomHeader = document.querySelector('#bottom-tab-header');
    if (bottomHeader) {
      bottomHeader.querySelectorAll('.tab-btn').forEach(btn => {
        const isActive = (btn.getAttribute('data-tab') === s.activeWorkspaceTab);
        btn.classList.toggle('active', isActive);
      });
      const activeBottomId = `pane-${this._camelToKebab(s.activeWorkspaceTab)}`;
      document.querySelectorAll('#bottom-workspace-content .tab-pane').forEach(pane => {
        const isActive = (pane.id === activeBottomId);
        pane.classList.toggle('active', isActive);
        pane.style.display = isActive ? 'block' : 'none';
      });
    }
  }

  async syncChartData(force = false) {
    const s = store.getState();

    if (force || this.currentSymbol !== s.symbol || this.currentTimeframe !== s.timeframe || this.currentBarCount !== s.barCount) {
      this.currentSymbol = s.symbol;
      this.currentTimeframe = s.timeframe;
      this.currentBarCount = s.barCount;

      try {
        const barData = await fixtureClient.getBars(s.symbol, s.timeframe, s.barCount);
        if (barData) {
          this.updateChartLegend(barData);
          if (this.chartManager) {
            try {
              this.chartManager.setBars(barData.items || [], s.indicators);
            } catch (chartErr) {
              console.warn('Lightweight Charts canvas warning:', chartErr);
            }
          }
        }
      } catch (err) {
        console.warn('Failed to load chart bars:', err);
      }
    }
  }

  updateChartLegend(barData) {
    const legendTicker = document.querySelector('#legend-ticker');
    const legendPeriod = document.querySelector('#legend-period');
    const legendValues = document.querySelector('#legend-values');

    if (legendTicker) legendTicker.textContent = barData.symbol;
    if (legendPeriod) legendPeriod.textContent = barData.timeframe;

    const items = barData.items || [];
    if (items.length > 0 && legendValues) {
      const last = items[items.length - 1];
      const prev = items[items.length - 2] || last;
      const chg = last.close - prev.close;
      const chgPct = (chg / prev.close) * 100;

      legendValues.innerHTML = `
        <span>O: <span class="val">${last.open}</span></span>
        <span>H: <span class="val">${last.high}</span></span>
        <span>L: <span class="val">${last.low}</span></span>
        <span>C: <span class="val">${last.close}</span></span>
        <span class="${chg >= 0 ? 'up' : 'down'}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)} (${chgPct.toFixed(2)}%)</span>
        <span>Vol: <span class="val">${(last.volume || 0).toLocaleString()}</span></span>
      `;
    }
  }

  bindChartControls() {
    const exportCsvBtn = document.querySelector('#btn-export-csv');
    if (exportCsvBtn && this.chartManager) {
      exportCsvBtn.addEventListener('click', () => this.chartManager.exportCSV());
    }

    const btn5kBars = document.querySelector('#btn-load-5k-bars');
    if (btn5kBars) {
      btn5kBars.addEventListener('click', () => {
        store.setBarCount(5000);
        alert('5,000 daily bars synthesized and loaded into TradingView Lightweight Charts workspace!');
      });
    }
  }

  updateUiTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.dataset.i18n;
      if (key) el.textContent = i18n.t(key);
    });
  }

  _camelToKebab(str) {
    return str.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
  }
}

function bootstrap() {
  const app = new Application();
  app.init();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}
