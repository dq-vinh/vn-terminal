// Mock API Client reading contracts/fixtures/ for frontend development without backend
export class FixtureClient {
  constructor() {
    this.simulatedLatency = 20; // ms for fast responsive UI
    this.forceError = false;
    this.forceEmpty = false;
    this.forceStale = false;
  }

  setSimulatedState({ error = false, empty = false, stale = false }) {
    this.forceError = error;
    this.forceEmpty = empty;
    this.forceStale = stale;
  }

  async _fetchFixture(filename) {
    if (this.simulatedLatency > 0) {
      await new Promise(resolve => setTimeout(resolve, this.simulatedLatency));
    }

    if (this.forceError) {
      throw new Error(`Simulated Network Error reading ${filename}`);
    }

    try {
      const res = await fetch(`/contracts/fixtures/${filename}`);
      if (res.ok) {
        const data = await res.json();
        if (this.forceStale && data.provenance) {
          data.provenance.freshness_status = 'stale';
          data.provenance.warnings.push('STALE DATA WARNING: Last session data is outdated.');
        }
        return data;
      }
    } catch (e) {
      // Ignore fetch error and fall through to in-memory fallback
    }

    try {
      const res2 = await fetch(`../contracts/fixtures/${filename}`);
      if (res2.ok) {
        return await res2.json();
      }
    } catch (e) {
      // Ignore
    }

    return this._getInMemFallback(filename);
  }

  async getSecurityMaster() {
    return this._fetchFixture('security_master.json');
  }

  async getBars(symbol = 'FPT', timeframe = '1D', barCount = 520) {
    if (this.forceEmpty) return { symbol, timeframe, total: 0, items: [], bars: [], provenance: { freshness_status: 'current', warnings: [] } };
    
    const fixtureName = (symbol.toUpperCase() === 'KDH') ? 'bars_KDH.json' : 'bars_FPT.json';
    const data = await this._fetchFixture(fixtureName);
    
    let bars = data.bars || data.items || [];

    // Synthesize 5,000 bars if requested to satisfy smooth 5,000 daily bars performance requirement (WP4)
    if (barCount > bars.length && bars.length > 0) {
      bars = this._synthesizeBars(bars, barCount, symbol);
    }

    // Handle Timeframe aggregation (Weekly, Monthly)
    if (timeframe === '1W') {
      bars = this._aggregateTimeframe(bars, 5);
    } else if (timeframe === '1M') {
      bars = this._aggregateTimeframe(bars, 21);
    }

    return {
      symbol: symbol.toUpperCase(),
      timeframe,
      total: bars.length,
      items: bars,
      bars: bars,
      provenance: data.provenance || { freshness_status: 'current', warnings: [] }
    };
  }

  async getFundamentals(symbol = 'FPT') {
    if (this.forceEmpty) return { symbol, observations: [], provenance: { freshness_status: 'current', warnings: [] } };
    const fixtureName = (symbol.toUpperCase() === 'KDH') ? 'fundamentals_KDH.json' : 'fundamentals_FPT.json';
    return this._fetchFixture(fixtureName);
  }

  async getStrategyDefinitions() {
    return this._fetchFixture('strategy_definitions.json');
  }

  async evaluateStrategy(symbol = 'FPT', strategyId = 'minervini_trend_template') {
    if (this.forceEmpty) return null;
    const fixtureName = (symbol.toUpperCase() === 'KDH') ? 'strategy_evaluation_KDH.json' : 'strategy_evaluation_FPT.json';
    const data = await this._fetchFixture(fixtureName);
    if (data && data.results && data.results.length > 0) {
      return { ...data.results[0], provenance: data.provenance };
    }
    return data;
  }

  async getAiFactBundle(symbol = 'FPT') {
    if (this.forceEmpty) return null;
    const fixtureName = (symbol.toUpperCase() === 'KDH') ? 'ai_fact_bundle_KDH.json' : 'ai_fact_bundle_FPT.json';
    return this._fetchFixture(fixtureName);
  }

  async runScreener(filters = {}) {
    return {
      run_id: 'screen-' + Date.now(),
      total_matches: 2,
      results: [
        { symbol: 'FPT', close: 67.0, change_pct: -0.0122, volume: 7571500, signal: 'watch', score: 6, exchange: 'HOSE' },
        { symbol: 'KDH', close: 34.5, change_pct: 0.0147, volume: 2150000, signal: 'buy', score: 7, exchange: 'HOSE' }
      ]
    };
  }

  async runBacktest(config = {}) {
    return {
      run_id: 'backtest-' + Date.now(),
      metrics: {
        cagr: 0.245,
        max_drawdown: -0.128,
        sharpe_ratio: 1.85,
        sortino_ratio: 2.15,
        win_rate: 0.625,
        profit_factor: 1.92,
        total_trades: 48
      },
      trades: [
        { trade_id: 1, symbol: 'FPT', entry_date: '2026-01-15', exit_date: '2026-03-20', entry_price: 52.0, exit_price: 61.5, profit_pct: 0.182, holding_days: 64, direction: 'LONG' },
        { trade_id: 2, symbol: 'KDH', entry_date: '2026-04-02', exit_date: '2026-05-18', entry_price: 28.5, exit_price: 32.0, profit_pct: 0.122, holding_days: 46, direction: 'LONG' },
        { trade_id: 3, symbol: 'FPT', entry_date: '2026-06-01', exit_date: '2026-07-10', entry_price: 60.0, exit_price: 66.8, profit_pct: 0.113, holding_days: 39, direction: 'LONG' }
      ],
      equity_curve: this._generateMockEquityCurve()
    };
  }

  _generateMockEquityCurve() {
    const points = [];
    let equity = 100000;
    let dd = 0;
    let maxEq = equity;
    const startDate = new Date('2025-01-01');
    for (let i = 0; i < 250; i++) {
      const d = new Date(startDate);
      d.setDate(d.getDate() + i);
      const ret = (Math.sin(i / 10) * 0.005) + (Math.random() * 0.012 - 0.004);
      equity *= (1 + ret);
      if (equity > maxEq) maxEq = equity;
      dd = (equity - maxEq) / maxEq;
      points.push({
        time: d.toISOString().split('T')[0],
        equity: Math.round(equity),
        drawdown: parseFloat(dd.toFixed(4))
      });
    }
    return points;
  }

  _synthesizeBars(baseBars, targetCount, symbol) {
    const result = [];
    const firstDate = new Date(baseBars[0].trading_date);
    let basePrice = baseBars[0].open || 50;

    for (let i = targetCount - baseBars.length; i > 0; i--) {
      const d = new Date(firstDate);
      d.setDate(d.getDate() - i);
      if (d.getDay() === 0 || d.getDay() === 6) continue;
      
      const change = (Math.sin(i / 15) * 0.5) + ((Math.random() - 0.48) * 0.8);
      basePrice = Math.max(10, basePrice + change);
      const open = basePrice;
      const high = open + Math.random() * 0.8;
      const low = Math.max(5, open - Math.random() * 0.8);
      const close = low + Math.random() * (high - low);
      const volume = Math.floor(1000000 + Math.random() * 5000000);

      result.push({
        symbol,
        exchange: 'HOSE',
        timeframe: '1D',
        trading_date: d.toISOString().split('T')[0],
        open: parseFloat(open.toFixed(2)),
        high: parseFloat(high.toFixed(2)),
        low: parseFloat(low.toFixed(2)),
        close: parseFloat(close.toFixed(2)),
        volume,
        source: 'synthesized-5k-fixture'
      });
    }
    return result.concat(baseBars);
  }

  _aggregateTimeframe(dailyBars, groupSize) {
    const aggregated = [];
    for (let i = 0; i < dailyBars.length; i += groupSize) {
      const chunk = dailyBars.slice(i, i + groupSize);
      if (chunk.length === 0) continue;
      const open = chunk[0].open;
      const close = chunk[chunk.length - 1].close;
      let high = chunk[0].high;
      let low = chunk[0].low;
      let volume = 0;
      chunk.forEach(b => {
        if (b.high > high) high = b.high;
        if (b.low < low) low = b.low;
        volume += b.volume;
      });
      aggregated.push({
        ...chunk[chunk.length - 1],
        open, high, low, close, volume
      });
    }
    return aggregated;
  }

  _getInMemFallback(filename) {
    if (filename.includes('security_master')) {
      return {
        items: [
          { symbol: 'FPT', company_name: 'FPT Corporation', exchange: 'HOSE', sector: 'Information Technology' },
          { symbol: 'KDH', company_name: 'Khang Dien House', exchange: 'HOSE', sector: 'Real Estate' }
        ],
        provenance: { freshness_status: 'current', warnings: [] }
      };
    }
    if (filename.includes('bars')) {
      const sym = filename.includes('KDH') ? 'KDH' : 'FPT';
      const bars = [];
      let price = sym === 'FPT' ? 60 : 30;
      const startDate = new Date('2025-01-01');
      for (let i = 0; i < 520; i++) {
        const d = new Date(startDate);
        d.setDate(d.getDate() + i);
        if (d.getDay() === 0 || d.getDay() === 6) continue;
        price += (Math.random() - 0.48) * 0.8;
        const open = price;
        const high = open + Math.random() * 0.6;
        const low = open - Math.random() * 0.6;
        const close = low + Math.random() * (high - low);
        bars.push({
          symbol: sym,
          exchange: 'HOSE',
          timeframe: '1D',
          trading_date: d.toISOString().split('T')[0],
          open: parseFloat(open.toFixed(2)),
          high: parseFloat(high.toFixed(2)),
          low: parseFloat(low.toFixed(2)),
          close: parseFloat(close.toFixed(2)),
          volume: Math.floor(1000000 + Math.random() * 4000000)
        });
      }
      return { symbol: sym, timeframe: '1D', total: bars.length, items: bars, bars: bars, provenance: { freshness_status: 'current', warnings: [] } };
    }
    if (filename.includes('fundamentals')) {
      const sym = filename.includes('KDH') ? 'KDH' : 'FPT';
      return {
        symbol: sym,
        observations: [
          { period_end: '2026-06-30', revenue: 21672, net_income: 1927, publication_date: '2026-07-20' },
          { period_end: '2026-03-31', revenue: 19850, net_income: 1750, publication_date: '2026-04-18' },
          { period_end: '2025-12-31', revenue: 22100, net_income: 2010, publication_date: '2026-01-25' },
          { period_end: '2025-09-30', revenue: 18900, net_income: 1620, publication_date: null }
        ],
        provenance: { freshness_status: 'current', warnings: ['One observation has missing publication_date (Degraded mode)'] }
      };
    }
    if (filename.includes('strategy_evaluation')) {
      const sym = filename.includes('KDH') ? 'KDH' : 'FPT';
      return {
        symbol: sym,
        as_of_date: '2026-07-30',
        strategy_id: 'minervini_trend_template',
        strategy_version: '1.0.0',
        signal: sym === 'KDH' ? 'buy' : 'watch',
        score: 6,
        max_score: 8,
        passed_criteria: ['close_above_150d_sma', 'close_above_200d_sma', '150d_sma_above_200d_sma'],
        failed_criteria: ['within_25pct_of_52w_high'],
        levels: { support: [64.0, 61.5], resistance: [68.5, 71.0], invalidation: 60.0 },
        provenance: { freshness_status: 'current', warnings: [] }
      };
    }
    if (filename.includes('ai_fact_bundle')) {
      const sym = filename.includes('KDH') ? 'KDH' : 'FPT';
      return {
        symbol: sym,
        as_of_date: '2026-07-30',
        price_summary: { last_close: sym === 'KDH' ? 34.5 : 67.0, last_volume: 7571500 },
        indicators: { sma_20: 71.19 },
        money_flow: { accumulation_distribution_line: 1423.77, on_balance_volume: 63375267, up_down_volume_ratio: 0.75 },
        financial_summary: { latest_revenue: 21672.89, latest_net_income: 1927.3 },
        levels: { support: [64.0, 61.5], resistance: [68.5, 71.0], invalidation: 60.0 },
        data_quality: { freshness_status: 'current', warnings: [] }
      };
    }
    return { provenance: { freshness_status: 'current', warnings: [] } };
  }
}

export const fixtureClient = new FixtureClient();
