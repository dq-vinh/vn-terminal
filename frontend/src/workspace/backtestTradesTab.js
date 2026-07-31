// Backtest Trades Log Bottom Workspace Tab
import { i18n } from '../i18n/index.js';
import { fixtureClient } from '../api/fixtureClient.js';
import { renderLoadingState, renderErrorState } from '../components/stateAlert.js';

export class BacktestTradesTab {
  constructor(containerElement) {
    this.container = containerElement;
    this.backtest = null;
    this.loading = false;
  }

  init() {
    this.loadData();
    i18n.onChange(() => this.render());
  }

  async loadData() {
    this.loading = true;
    renderLoadingState(this.container);

    try {
      this.backtest = await fixtureClient.runBacktest();
      this.loading = false;
      this.render();
    } catch (err) {
      this.loading = false;
      renderErrorState(this.container, err.message, () => this.loadData());
    }
  }

  render() {
    if (this.loading || !this.backtest) return;

    const trades = this.backtest.trades || [];

    this.container.innerHTML = `
      <div class="workspace-container" data-testid="backtest-trades-tab">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">
            Executed Trades Log (${trades.length} trades)
          </span>
          <button class="btn btn-sm btn-primary" id="btn-run-backtest" data-testid="btn-run-backtest">
            ▶ Run Backtest
          </button>
        </div>

        <table class="data-table">
          <thead>
            <tr>
              <th>Trade ID</th>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Entry Date</th>
              <th class="number-col">Entry Price</th>
              <th>Exit Date</th>
              <th class="number-col">Exit Price</th>
              <th class="number-col">P&L %</th>
              <th class="number-col">Days Held</th>
            </tr>
          </thead>
          <tbody>
            ${trades.map(t => `
              <tr>
                <td style="font-family: var(--font-mono);">#${t.trade_id}</td>
                <td style="font-weight: 700; color: var(--accent-blue);">${t.symbol}</td>
                <td><span class="badge badge-success">${t.direction}</span></td>
                <td style="font-family: var(--font-mono);">${t.entry_date}</td>
                <td class="number-col">${t.entry_price.toFixed(1)}</td>
                <td style="font-family: var(--font-mono);">${t.exit_date}</td>
                <td class="number-col">${t.exit_price.toFixed(1)}</td>
                <td class="number-col ${t.profit_pct >= 0 ? 'legend-values up' : 'legend-values down'}">
                  +${(t.profit_pct * 100).toFixed(1)}%
                </td>
                <td class="number-col">${t.holding_days}d</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;

    const btn = this.container.querySelector('#btn-run-backtest');
    if (btn) {
      btn.addEventListener('click', () => this.loadData());
    }
  }
}
