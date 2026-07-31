// Strategies Analytical Panel Tab
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';
import { fixtureClient } from '../api/fixtureClient.js';
import { renderLoadingState, renderErrorState } from '../components/stateAlert.js';

export class StrategiesPanel {
  constructor(containerElement) {
    this.container = containerElement;
    this.evaluation = null;
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
      this.evaluation = await fixtureClient.evaluateStrategy(s.symbol);
      this.loading = false;
      this.render();
    } catch (err) {
      this.loading = false;
      renderErrorState(this.container, err.message, () => this.loadData());
    }
  }

  render() {
    if (this.loading || !this.evaluation) return;

    const evalData = this.evaluation;
    const passed = evalData.passed_criteria || [];
    const failed = evalData.failed_criteria || [];
    const levels = evalData.levels || { support: [], resistance: [], invalidation: null };

    this.container.innerHTML = `
      <div class="panel-section" data-testid="strategies-panel">
        <div class="panel-card">
          <div class="panel-card-title">
            <span>${i18n.t('stratTitle')}</span>
            <button class="btn btn-sm btn-primary" id="btn-eval-strat" data-testid="btn-eval-strat">
              ⚡ ${i18n.t('evalBtn')}
            </button>
          </div>
          <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">
            Minervini Trend Template (v1.0.0)
          </div>

          <div class="score-card">
            <div>
              <div style="font-size: 11px; color: var(--text-secondary);">${i18n.t('scoreLabel')}</div>
              <div class="score-main">
                <span class="score-num">${evalData.score}</span>
                <span class="score-max">/ ${evalData.max_score}</span>
              </div>
            </div>
            <span class="badge ${evalData.signal === 'buy' ? 'badge-success' : 'badge-warning'}" style="font-size: 12px; padding: 4px 10px;">
              ${evalData.signal.toUpperCase()}
            </span>
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-card-title">${i18n.t('passedCriteria')} (${passed.length})</div>
          <div class="criteria-list">
            ${passed.map(c => `<div class="criteria-item passed">✓ ${c}</div>`).join('')}
          </div>

          <div class="panel-card-title" style="margin-top: 12px;">${i18n.t('failedCriteria')} (${failed.length})</div>
          <div class="criteria-list">
            ${failed.map(c => `<div class="criteria-item failed">✗ ${c}</div>`).join('')}
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-card-title">${i18n.t('targetLevels')}</div>
          <div style="font-size: 11px; display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">${i18n.t('support')}:</span>
              <span style="font-family: var(--font-mono); color: #56d364;">${(levels.support || []).join(' / ')}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">${i18n.t('resistance')}:</span>
              <span style="font-family: var(--font-mono); color: #58a6ff;">${(levels.resistance || []).join(' / ')}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">${i18n.t('invalidation')}:</span>
              <span style="font-family: var(--font-mono); color: #f85149;">${levels.invalidation || 'N/A'}</span>
            </div>
          </div>
        </div>
      </div>
    `;

    const btn = this.container.querySelector('#btn-eval-strat');
    if (btn) {
      btn.addEventListener('click', () => this.loadData());
    }
  }
}
