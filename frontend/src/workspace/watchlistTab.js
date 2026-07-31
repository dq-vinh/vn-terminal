// Watchlist Bottom Workspace Tab (WP12 Persistence)
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';

export class WatchlistTab {
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
    const watchlist = s.watchlist || ['FPT', 'KDH'];

    this.container.innerHTML = `
      <div class="workspace-container" data-testid="watchlist-tab">
        <div class="watchlist-toolbar">
          <div class="watchlist-input-group">
            <input type="text" 
                   class="form-input" 
                   id="wl-add-input" 
                   placeholder="e.g. SSI, VNM..." 
                   style="width: 120px; text-transform: uppercase;"
                   data-testid="wl-add-input" />
            <button class="btn btn-sm btn-primary" id="btn-wl-add" data-testid="btn-wl-add">
              + ${i18n.t('addTicker')}
            </button>
          </div>
          <span style="font-size: 11px; color: var(--text-secondary);">
            ${watchlist.length} securities in watchlist
          </span>
        </div>

        <table class="data-table">
          <thead>
            <tr>
              <th>${i18n.t('symbol')}</th>
              <th class="number-col">${i18n.t('closePrice')}</th>
              <th class="number-col">${i18n.t('changePct')}</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${watchlist.map(sym => `
              <tr class="wl-row ${sym === s.symbol ? 'active' : ''}" data-sym="${sym}" style="cursor: pointer;">
                <td style="font-weight: 700; color: var(--accent-blue);">${sym}</td>
                <td class="number-col">${sym === 'FPT' ? '67.0' : '34.5'}</td>
                <td class="number-col ${sym === 'FPT' ? 'legend-values down' : 'legend-values up'}">
                  ${sym === 'FPT' ? '-1.22%' : '+1.47%'}
                </td>
                <td>
                  <button class="btn btn-sm btn-wl-remove" data-sym="${sym}" style="color: var(--accent-red); padding: 2px 6px;">
                    ${i18n.t('remove')}
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;

    this.bindEvents();
  }

  bindEvents() {
    const addBtn = this.container.querySelector('#btn-wl-add');
    const addInput = this.container.querySelector('#wl-add-input');

    if (addBtn && addInput) {
      addBtn.addEventListener('click', () => {
        const val = addInput.value.trim();
        if (val) {
          store.addToWatchlist(val);
          addInput.value = '';
        }
      });
    }

    this.container.querySelectorAll('.wl-row').forEach(row => {
      row.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-wl-remove')) return;
        const sym = row.dataset.sym;
        if (sym) store.setSymbol(sym);
      });
    });

    this.container.querySelectorAll('.btn-wl-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const sym = btn.dataset.sym;
        if (sym) store.removeFromWatchlist(sym);
      });
    });
  }
}
