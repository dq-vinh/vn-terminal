// Signal History Audit Log Tab
import { i18n } from '../i18n/index.js';

export class SignalHistoryTab {
  constructor(containerElement) {
    this.container = containerElement;
  }

  init() {
    this.render();
    i18n.onChange(() => this.render());
  }

  render() {
    this.container.innerHTML = `
      <div class="workspace-container" data-testid="signal-history-tab">
        <table class="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Signal</th>
              <th class="number-col">Score</th>
              <th>Data Version</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="font-family: var(--font-mono);">2026-07-30</td>
              <td style="font-weight: 700; color: var(--accent-blue);">FPT</td>
              <td>Minervini Trend Template</td>
              <td><span class="badge badge-warning">WATCH</span></td>
              <td class="number-col">6 / 8</td>
              <td style="font-size: 10px; color: var(--text-muted);">fdata-2026-07-30</td>
            </tr>
            <tr>
              <td style="font-family: var(--font-mono);">2026-07-29</td>
              <td style="font-weight: 700; color: var(--accent-blue);">FPT</td>
              <td>Minervini Trend Template</td>
              <td><span class="badge badge-success">BUY</span></td>
              <td class="number-col">7 / 8</td>
              <td style="font-size: 10px; color: var(--text-muted);">fdata-2026-07-29</td>
            </tr>
            <tr>
              <td style="font-family: var(--font-mono);">2026-07-25</td>
              <td style="font-weight: 700; color: var(--accent-blue);">KDH</td>
              <td>MA Alignment Crossover</td>
              <td><span class="badge badge-success">BUY</span></td>
              <td class="number-col">8 / 8</td>
              <td style="font-size: 10px; color: var(--text-muted);">fdata-2026-07-25</td>
            </tr>
          </tbody>
        </table>
      </div>
    `;
  }
}
