// Data Refresh Log Bottom Workspace Tab
import { i18n } from '../i18n/index.js';

export class DataRefreshLogTab {
  constructor(containerElement) {
    this.container = containerElement;
  }

  init() {
    this.render();
    i18n.onChange(() => this.render());
  }

  render() {
    this.container.innerHTML = `
      <div class="workspace-container" data-testid="data-refresh-log-tab">
        <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 6px;">
          FData Evening Post-Session Pipeline History (WP16)
        </div>
        
        <div class="log-item">
          <span>[2026-07-30 22:00:15] Daily Close EOD Pipeline Completed.</span>
          <span class="badge badge-success">2,471 Files Processed (3.63M records)</span>
        </div>
        <div class="log-item">
          <span>[2026-07-29 22:00:10] Daily Close EOD Pipeline Completed.</span>
          <span class="badge badge-success">2,471 Files Processed</span>
        </div>
        <div class="log-item">
          <span>[2026-07-28 22:00:12] Daily Close EOD Pipeline Completed.</span>
          <span class="badge badge-success">2,470 Files Processed</span>
        </div>
      </div>
    `;
  }
}
