// Equity Curve & Drawdown Canvas Renderer Tab
import { i18n } from '../i18n/index.js';
import { fixtureClient } from '../api/fixtureClient.js';
import { renderLoadingState, renderErrorState } from '../components/stateAlert.js';

export class EquityCurveTab {
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

    const m = this.backtest.metrics || {};
    const points = this.backtest.equity_curve || [];

    this.container.innerHTML = `
      <div class="workspace-container" data-testid="equity-curve-tab">
        <div class="metrics-summary-grid">
          <div class="metric-box">
            <div class="label">${i18n.t('cagr')}</div>
            <div class="val" style="color: #56d364;">+${((m.cagr || 0) * 100).toFixed(1)}%</div>
          </div>
          <div class="metric-box">
            <div class="label">${i18n.t('maxDrawdown')}</div>
            <div class="val" style="color: #f85149;">${((m.max_drawdown || 0) * 100).toFixed(1)}%</div>
          </div>
          <div class="metric-box">
            <div class="label">${i18n.t('sharpe')}</div>
            <div class="val" style="color: #58a6ff;">${(m.sharpe_ratio || 0).toFixed(2)}</div>
          </div>
          <div class="metric-box">
            <div class="label">${i18n.t('sortino')}</div>
            <div class="val" style="color: #bc8cff;">${(m.sortino_ratio || 0).toFixed(2)}</div>
          </div>
          <div class="metric-box">
            <div class="label">${i18n.t('winRate')}</div>
            <div class="val">${((m.win_rate || 0) * 100).toFixed(1)}%</div>
          </div>
          <div class="metric-box">
            <div class="label">${i18n.t('profitFactor')}</div>
            <div class="val">${(m.profit_factor || 0).toFixed(2)}</div>
          </div>
        </div>

        <div class="canvas-chart-container">
          <canvas id="equity-canvas"></canvas>
        </div>
      </div>
    `;

    setTimeout(() => this.drawCanvas(points), 50);
  }

  drawCanvas(points) {
    const canvas = this.container.querySelector('#equity-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth || 600;
    const height = canvas.height = canvas.parentElement.clientHeight || 180;

    if (points.length < 2) return;

    ctx.clearRect(0, 0, width, height);

    // Find min and max equity
    const equities = points.map(p => p.equity);
    const minEq = Math.min(...equities) * 0.98;
    const maxEq = Math.max(...equities) * 1.02;

    // Draw Equity Line
    ctx.beginPath();
    ctx.strokeStyle = '#2ea043';
    ctx.lineWidth = 2;

    points.forEach((p, idx) => {
      const x = (idx / (points.length - 1)) * (width - 40) + 20;
      const y = height - 30 - ((p.equity - minEq) / (maxEq - minEq)) * (height - 50);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw Equity Area Fill
    ctx.lineTo((width - 40) + 20, height - 30);
    ctx.lineTo(20, height - 30);
    ctx.closePath();
    ctx.fillStyle = 'rgba(46, 160, 67, 0.1)';
    ctx.fill();

    // Draw Grid Lines & Baseline
    ctx.strokeStyle = '#21262d';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(20, height - 30);
    ctx.lineTo(width - 20, height - 30);
    ctx.stroke();
  }
}
