// Indicators Analytical Panel Tab
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';

export class IndicatorsPanel {
  constructor(containerElement) {
    this.container = containerElement;
  }

  init() {
    this.render();
    store.subscribe(() => this.render());
    i18n.onChange(() => this.render());
  }

  render() {
    const s = store.getState();
    const ind = s.indicators;

    this.container.innerHTML = `
      <div class="panel-section" data-testid="indicators-panel">
        <div class="panel-card">
          <div class="panel-card-title">${i18n.t('indTitle')}</div>
          <div class="ind-toggle-list">
            <div class="ind-item">
              <span class="ind-item-label">
                <span class="ind-dot" style="background: #2f81f7;"></span>
                ${i18n.t('emaLabel')}
              </span>
              <label class="switch">
                <input type="checkbox" id="toggle-ema" ${ind.ema ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>

            <div class="ind-item">
              <span class="ind-item-label">
                <span class="ind-dot" style="background: #d29922;"></span>
                ${i18n.t('smaLabel')}
              </span>
              <label class="switch">
                <input type="checkbox" id="toggle-sma" ${ind.sma ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>

            <div class="ind-item">
              <span class="ind-item-label">
                <span class="ind-dot" style="background: #26a69a;"></span>
                ${i18n.t('volumeMaLabel')}
              </span>
              <label class="switch">
                <input type="checkbox" id="toggle-vol" ${ind.volume ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>

            <div class="ind-item">
              <span class="ind-item-label">
                <span class="ind-dot" style="background: #a371f7;"></span>
                ${i18n.t('srLevelsLabel')}
              </span>
              <label class="switch">
                <input type="checkbox" id="toggle-sr" ${ind.srLevels ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-card-title">Money Flow & Accumulation (Section 14)</div>
          <div style="font-size: 11px; display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">Accumulation/Distribution:</span>
              <span style="font-family: var(--font-mono); font-weight: 600; color: #56d364;">+1,423.77</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">On-Balance Volume (OBV):</span>
              <span style="font-family: var(--font-mono); font-weight: 600;">63,375,267</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">Up/Down Vol Ratio:</span>
              <span style="font-family: var(--font-mono); font-weight: 600;">0.75</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-secondary);">VWAP Status (Aux1):</span>
              <span class="badge badge-warning">Pending VWAP Confirm</span>
            </div>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
  }

  bindEvents() {
    const bindToggle = (id, key) => {
      const el = this.container.querySelector(id);
      if (el) {
        el.addEventListener('change', () => store.toggleIndicator(key));
      }
    };

    bindToggle('#toggle-ema', 'ema');
    bindToggle('#toggle-sma', 'sma');
    bindToggle('#toggle-vol', 'volume');
    bindToggle('#toggle-sr', 'srLevels');
  }
}
