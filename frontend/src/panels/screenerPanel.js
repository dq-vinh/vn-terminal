// Market-wide Stock Screener Analytical Panel Tab
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';
import { fixtureClient } from '../api/fixtureClient.js';
import { renderLoadingState, renderErrorState, renderEmptyState } from '../components/stateAlert.js';

export class ScreenerPanel {
  constructor(containerElement) {
    this.container = containerElement;
    this.results = [];
    this.loading = false;
  }

  init() {
    this.render();
    i18n.onChange(() => this.render());
  }

  async runScreener() {
    this.loading = true;
    renderLoadingState(this.container);

    try {
      const res = await fixtureClient.runScreener();
      this.results = res.results || [];
      this.loading = false;
      this.render();
    } catch (err) {
      this.loading = false;
      renderErrorState(this.container, err.message, () => this.runScreener());
    }
  }

  render() {
    this.container.innerHTML = `
      <div class="panel-section" data-testid="screener-panel">
        <div class="panel-card">
          <div class="panel-card-title">${i18n.t('screenerTitle')}</div>
          
          <div class="filter-grid">
            <div class="form-group">
              <label>${i18n.t('exchangeFilter')}</label>
              <select class="form-input" id="scr-exch">
                <option value="ALL">ALL (HOSE/HNX/UPCoM)</option>
                <option value="HOSE">HOSE</option>
                <option value="HNX">HNX</option>
              </select>
            </div>
            <div class="form-group">
              <label>${i18n.t('minVolume')}</label>
              <input type="number" class="form-input" id="scr-vol" value="500000" step="100000" />
            </div>
          </div>

          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <button class="btn btn-sm btn-primary" id="btn-run-screener" data-testid="btn-run-screener">
              🔍 ${i18n.t('runScreenerBtn')}
            </button>
            <button class="btn btn-sm" id="btn-export-screener">
              📥 ${i18n.t('exportBtn')}
            </button>
          </div>
        </div>

        <div class="panel-card" style="flex: 1; padding: 0; overflow: hidden; display: flex; flex-direction: column;">
          <div id="screener-table-wrapper" style="flex: 1; overflow-y: auto;">
            ${this.results.length === 0 ? `
              <div class="state-container">
                <div>Press "Run Screener" to scan market strategies</div>
              </div>
            ` : `
              <table class="data-table">
                <thead>
                  <tr>
                    <th>${i18n.t('symbol')}</th>
                    <th class="number-col">${i18n.t('closePrice')}</th>
                    <th class="number-col">${i18n.t('changePct')}</th>
                    <th>${i18n.t('signal')}</th>
                  </tr>
                </thead>
                <tbody>
                  ${this.results.map(r => `
                    <tr class="screener-row" data-sym="${r.symbol}" style="cursor: pointer;">
                      <td style="font-weight: 700; color: var(--accent-blue);">${r.symbol}</td>
                      <td class="number-col">${r.close.toFixed(1)}</td>
                      <td class="number-col ${r.change_pct >= 0 ? 'legend-values up' : 'legend-values down'}">
                        ${(r.change_pct * 100).toFixed(2)}%
                      </td>
                      <td>
                        <span class="badge ${r.signal === 'buy' ? 'badge-success' : 'badge-warning'}">
                          ${r.signal.toUpperCase()} (${r.score})
                        </span>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            `}
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
  }

  bindEvents() {
    const runBtn = this.container.querySelector('#btn-run-screener');
    if (runBtn) {
      runBtn.addEventListener('click', () => this.runScreener());
    }

    this.container.querySelectorAll('.screener-row').forEach(row => {
      row.addEventListener('click', () => {
        const sym = row.dataset.sym;
        if (sym) store.setSymbol(sym);
      });
    });
  }
}
