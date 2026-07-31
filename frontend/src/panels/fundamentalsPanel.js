// Fundamentals Analytical Panel Tab
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';
import { fixtureClient } from '../api/fixtureClient.js';
import { renderLoadingState, renderErrorState } from '../components/stateAlert.js';

export class FundamentalsPanel {
  constructor(containerElement) {
    this.container = containerElement;
    this.fundamentals = null;
    this.loading = false;
    this.lastSymbol = '';
  }

  init() {
    this.lastSymbol = store.getState().symbol;
    this.loadData();
    store.subscribe(() => {
      const s = store.getState();
      if (s.symbol !== this.lastSymbol) {
        this.lastSymbol = s.symbol;
        this.loadData();
      }
    });
    i18n.onChange(() => this.render());
  }

  async loadData() {
    const s = store.getState();
    this.loading = true;
    renderLoadingState(this.container);

    try {
      this.fundamentals = await fixtureClient.getFundamentals(s.symbol);
      this.loading = false;
      this.render();
    } catch (err) {
      this.loading = false;
      renderErrorState(this.container, err.message, () => this.loadData());
    }
  }

  render() {
    if (this.loading || !this.fundamentals) return;

    const data = this.fundamentals;
    const obs = data.observations || [];
    const hasNullPubDate = obs.some(o => o.publication_date === null);

    this.container.innerHTML = `
      <div class="panel-section" data-testid="fundamentals-panel">
        ${hasNullPubDate ? `
          <div class="badge badge-warning" style="padding: 6px 10px; margin-bottom: 8px; line-height: 1.4;">
            ⚠️ ${i18n.t('pubDateWarning')}
          </div>
        ` : ''}

        <div class="panel-card">
          <div class="panel-card-title">
            <span>${i18n.t('fundTitle')} (${data.symbol})</span>
            <div style="display: flex; gap: 4px;">
              <span class="badge badge-info">${i18n.t('viewConsolidated')}</span>
            </div>
          </div>

          <table class="data-table">
            <thead>
              <tr>
                <th>Period</th>
                <th class="number-col">${i18n.t('revenue')}</th>
                <th class="number-col">${i18n.t('netIncome')}</th>
                <th>Pub Date</th>
              </tr>
            </thead>
            <tbody>
              ${obs.slice(0, 8).map(o => `
                <tr>
                  <td style="font-weight: 600; font-family: var(--font-mono);">${o.period_end}</td>
                  <td class="number-col">${(o.revenue || 0).toLocaleString()}</td>
                  <td class="number-col ${o.net_income >= 0 ? 'legend-values up' : 'legend-values down'}">
                    ${(o.net_income || 0).toLocaleString()}
                  </td>
                  <td style="font-size: 10px; color: ${o.publication_date ? 'var(--text-secondary)' : 'var(--accent-amber)'};">
                    ${o.publication_date || 'MISSING ⚠️'}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>

        <div class="panel-card">
          <div class="panel-card-title">Financial Ratios & Growth</div>
          <div style="font-size: 11px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div class="metric-box">
              <div class="label">${i18n.t('grossMargin')}</div>
              <div class="val" style="color: var(--cat-fact-text);">38.5%</div>
            </div>
            <div class="metric-box">
              <div class="label">${i18n.t('netMargin')}</div>
              <div class="val" style="color: var(--cat-calc-text);">18.2%</div>
            </div>
            <div class="metric-box">
              <div class="label">${i18n.t('roe')}</div>
              <div class="val" style="color: var(--accent-purple);">24.8%</div>
            </div>
            <div class="metric-box">
              <div class="label">${i18n.t('roa')}</div>
              <div class="val" style="color: var(--text-primary);">11.4%</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }
}
