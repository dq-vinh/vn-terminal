// Top Toolbar Component
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';
import { fixtureClient } from '../api/fixtureClient.js';

export class TopToolbar {
  constructor(containerElement) {
    this.container = containerElement;
    this.symbols = [
      { symbol: 'FPT', company_name: 'FPT Corporation', exchange: 'HOSE' },
      { symbol: 'KDH', company_name: 'Khang Dien House', exchange: 'HOSE' }
    ];
  }

  async init() {
    try {
      const data = await fixtureClient.getSecurityMaster();
      if (data && data.items && data.items.length > 0) {
        this.symbols = data.items;
      }
    } catch (e) {
      console.warn('Failed to load symbols for toolbar search:', e);
    }

    this.render();
    this.bindEvents();

    store.subscribe(() => this.updateState());
    i18n.onChange(() => this.render());
  }

  render() {
    const s = store.getState();

    this.container.innerHTML = `
      <div class="top-toolbar">
        <div class="toolbar-left">
          <div class="app-brand">
            <span>📈 ${i18n.t('appTitle')}</span>
            <span class="tag">PRO v1.1</span>
          </div>

          <!-- Symbol Search Autocomplete -->
          <div class="symbol-search-container">
            <span class="search-icon">🔍</span>
            <input type="text" 
                   class="symbol-search-input" 
                   id="toolbar-symbol-input"
                   value="${s.symbol}" 
                   placeholder="${i18n.t('searchPlaceholder')}"
                   autocomplete="off"
                   data-testid="symbol-search-input" />
            <div class="search-dropdown" id="search-dropdown"></div>
          </div>

          <!-- Timeframe Group -->
          <div class="timeframe-group" data-testid="timeframe-group">
            <button class="tf-btn ${s.timeframe === '1D' ? 'active' : ''}" data-tf="1D">${i18n.t('tfDaily')}</button>
            <button class="tf-btn ${s.timeframe === '1W' ? 'active' : ''}" data-tf="1W">${i18n.t('tfWeekly')}</button>
            <button class="tf-btn ${s.timeframe === '1M' ? 'active' : ''}" data-tf="1M">${i18n.t('tfMonthly')}</button>
          </div>
        </div>

        <div class="toolbar-right">
          <!-- Refresh EOD Button -->
          <button class="btn btn-sm" id="btn-refresh-eod" title="${i18n.t('refreshBtn')}">
            🔄 ${i18n.t('refreshBtn')}
          </button>

          <!-- Save Layout Button -->
          <button class="btn btn-sm" id="btn-save-layout" title="${i18n.t('saveLayout')}" data-testid="btn-save-layout">
            💾 ${i18n.t('saveLayout')}
          </button>

          <!-- Model Picker -->
          <select class="toolbar-select" id="model-select" data-testid="model-select">
            <option value="OpenRouter / Claude 3.5 Sonnet" ${s.selectedModel.includes('Claude') ? 'selected' : ''}>
              🤖 OpenRouter / Claude 3.5
            </option>
            <option value="Ollama / DeepSeek-R1" ${s.selectedModel.includes('DeepSeek') ? 'selected' : ''}>
              🏠 Ollama / DeepSeek-R1 (Local)
            </option>
            <option value="Local Quantitative Engine" ${s.selectedModel.includes('Quantitative') ? 'selected' : ''}>
              ⚡ Local Deterministic Engine
            </option>
          </select>

          <!-- Data Quality Badge Indicator -->
          <div class="dq-indicator ${s.dataQualityStatus}" id="dq-status-indicator" data-testid="dq-status-indicator">
            <span class="status-dot"></span>
            <span>${s.dataQualityStatus === 'valid' ? i18n.t('dqValid') : i18n.t('dqWarning')}</span>
          </div>

          <!-- Language Toggle Switcher -->
          <button class="btn btn-sm" id="lang-toggle-btn" style="font-weight: 700;" data-testid="lang-toggle-btn">
            🌐 ${i18n.t('langToggle')}
          </button>
        </div>
      </div>
    `;

    this.bindEvents();
  }

  bindEvents() {
    const symbolInput = this.container.querySelector('#toolbar-symbol-input');
    const dropdown = this.container.querySelector('#search-dropdown');

    if (symbolInput && dropdown) {
      symbolInput.addEventListener('focus', () => this.showDropdown(symbolInput.value || ''));
      symbolInput.addEventListener('input', (e) => this.showDropdown(e.target.value));

      document.addEventListener('click', (e) => {
        if (dropdown && !this.container.contains(e.target)) {
          dropdown.classList.remove('active');
        }
      });
    }

    // Timeframe buttons using btn.getAttribute('data-tf')
    this.container.querySelectorAll('.tf-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const tf = btn.getAttribute('data-tf');
        if (tf) store.setTimeframe(tf);
      });
    });

    // Model Selector
    const modelSelect = this.container.querySelector('#model-select');
    if (modelSelect) {
      modelSelect.addEventListener('change', (e) => {
        store.setState({ selectedModel: e.target.value });
      });
    }

    // Language Toggle
    const langBtn = this.container.querySelector('#lang-toggle-btn');
    if (langBtn) {
      langBtn.addEventListener('click', () => {
        i18n.toggleLocale();
      });
    }

    // Save Layout
    const saveBtn = this.container.querySelector('#btn-save-layout');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        store._saveToStorage();
        alert(i18n.t('notesAutosaved'));
      });
    }

    // DQ Status button opens Data Quality tab
    const dqBtn = this.container.querySelector('#dq-status-indicator');
    if (dqBtn) {
      dqBtn.addEventListener('click', () => {
        store.setState({ activeRightTab: 'dataQuality' });
      });
    }
  }

  showDropdown(query) {
    const dropdown = this.container.querySelector('#search-dropdown');
    if (!dropdown) return;

    const q = query.trim().toLowerCase();
    const filtered = this.symbols.filter(s => 
      !q ||
      s.symbol.toLowerCase().includes(q) ||
      (s.company_name && s.company_name.toLowerCase().includes(q))
    );

    if (filtered.length === 0) {
      dropdown.classList.remove('active');
      return;
    }

    dropdown.innerHTML = filtered.map(s => `
      <div class="search-item" data-sym="${s.symbol}">
        <span class="sym">${s.symbol}</span>
        <span class="name">${s.company_name || ''}</span>
        <span class="exch">${s.exchange || ''}</span>
      </div>
    `).join('');

    dropdown.classList.add('active');

    dropdown.querySelectorAll('.search-item').forEach(item => {
      item.addEventListener('mousedown', (e) => {
        e.preventDefault(); // Prevent blur from closing dropdown before click
        const sym = item.getAttribute('data-sym');
        if (sym) {
          store.setSymbol(sym);
          dropdown.classList.remove('active');
        }
      });
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const sym = item.getAttribute('data-sym');
        if (sym) {
          store.setSymbol(sym);
          dropdown.classList.remove('active');
        }
      });
    });
  }

  updateState() {
    const s = store.getState();
    const symbolInput = this.container.querySelector('#toolbar-symbol-input');
    if (symbolInput && symbolInput.value !== s.symbol) {
      symbolInput.value = s.symbol;
    }

    this.container.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tf') === s.timeframe);
    });
  }
}
