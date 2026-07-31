// Current Strategy Signals Bottom Workspace Tab
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';

export class CurrentSignalsTab {
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

    this.container.innerHTML = `
      <div class="workspace-container" data-testid="current-signals-tab">
        <table class="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Signal</th>
              <th class="number-col">Score</th>
              <th>Support</th>
              <th>Resistance</th>
              <th>Invalidation</th>
            </tr>
          </thead>
          <tbody>
            <tr style="${s.symbol === 'FPT' ? 'background: rgba(47, 129, 247, 0.1);' : ''}">
              <td style="font-weight: 700; color: var(--accent-blue);">FPT</td>
              <td>Minervini Trend Template</td>
              <td><span class="badge badge-warning">WATCH</span></td>
              <td class="number-col">6 / 8</td>
              <td>64.0, 61.5</td>
              <td>68.5, 71.0</td>
              <td style="color: var(--accent-red);">60.0</td>
            </tr>
            <tr style="${s.symbol === 'KDH' ? 'background: rgba(47, 129, 247, 0.1);' : ''}">
              <td style="font-weight: 700; color: var(--accent-blue);">KDH</td>
              <td>MA Alignment Crossover</td>
              <td><span class="badge badge-success">BUY</span></td>
              <td class="number-col">7 / 8</td>
              <td>33.0, 31.5</td>
              <td>36.5, 39.0</td>
              <td style="color: var(--accent-red);">30.5</td>
            </tr>
          </tbody>
        </table>
      </div>
    `;
  }
}
