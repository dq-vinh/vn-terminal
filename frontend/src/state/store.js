// Central State Manager with localStorage persistence and fallback (WP12)
class AppStore {
  constructor() {
    this.storageKey = 'vn_terminal_pro_state_v1';
    this.listeners = [];
    
    // Default initial state
    this.state = {
      symbol: 'FPT',
      timeframe: '1D',
      barCount: 520, // Can be set to 5000 for smooth performance testing
      exchange: 'ALL',
      selectedModel: 'OpenRouter / Claude 3.5 Sonnet',
      activeRightTab: 'aiAnalysis',
      activeWorkspaceTab: 'watchlist',
      watchlist: ['FPT', 'KDH'],
      portfolioNotes: {
        FPT: 'FPT position target 72.0. Good quarterly growth and accumulation.',
        KDH: 'KDH real estate project sales expected Q3.'
      },
      indicators: {
        sma: true,
        ema: true,
        volume: true,
        srLevels: true
      },
      screenerResults: [],
      backtestResults: null,
      dataQualityStatus: 'valid', // 'valid' | 'warning' | 'error'
      layout: {
        rightPanelWidth: 420,
        bottomWorkspaceHeight: 280
      }
    };

    this._loadFromStorage();
  }

  getState() {
    return this.state;
  }

  setState(partialState) {
    this.state = { ...this.state, ...partialState };
    this._saveToStorage();
    this._notify();
  }

  setSymbol(symbol) {
    if (symbol && symbol !== this.state.symbol) {
      this.setState({ symbol: symbol.toUpperCase() });
    }
  }

  setTimeframe(tf) {
    if (['1D', '1W', '1M'].includes(tf)) {
      this.setState({ timeframe: tf });
    }
  }

  setBarCount(count) {
    this.setState({ barCount: count });
  }

  toggleIndicator(name) {
    const current = this.state.indicators;
    this.setState({
      indicators: { ...current, [name]: !current[name] }
    });
  }

  addToWatchlist(symbol) {
    const sym = symbol.toUpperCase();
    if (!this.state.watchlist.includes(sym)) {
      this.setState({ watchlist: [...this.state.watchlist, sym] });
    }
  }

  removeFromWatchlist(symbol) {
    const sym = symbol.toUpperCase();
    this.setState({
      watchlist: this.state.watchlist.filter(s => s !== sym)
    });
  }

  saveNote(symbol, text) {
    const sym = symbol.toUpperCase();
    this.setState({
      portfolioNotes: { ...this.state.portfolioNotes, [sym]: text }
    });
  }

  subscribe(callback) {
    this.listeners.push(callback);
    return () => {
      this.listeners = this.listeners.filter(cb => cb !== callback);
    };
  }

  _notify() {
    this.listeners.forEach(cb => cb(this.state));
  }

  _saveToStorage() {
    try {
      const dataToSave = {
        symbol: this.state.symbol,
        timeframe: this.state.timeframe,
        barCount: this.state.barCount,
        selectedModel: this.state.selectedModel,
        watchlist: this.state.watchlist,
        portfolioNotes: this.state.portfolioNotes,
        indicators: this.state.indicators,
        layout: this.state.layout
      };
      localStorage.setItem(this.storageKey, JSON.stringify(dataToSave));
    } catch (e) {
      console.warn('Failed to save state to localStorage:', e);
    }
  }

  _loadFromStorage() {
    try {
      const raw = localStorage.getItem(this.storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          this.state = { ...this.state, ...parsed };
        }
      }
    } catch (e) {
      console.warn('Corrupt localStorage settings detected, falling back safely:', e);
    }
  }
}

export const store = new AppStore();
