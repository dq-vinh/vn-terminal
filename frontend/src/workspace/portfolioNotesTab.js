// Portfolio Research Notes Bottom Workspace Tab (WP12 Persistence)
import { i18n } from '../i18n/index.js';
import { store } from '../state/store.js';

export class PortfolioNotesTab {
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
    const notesMap = s.portfolioNotes || {};
    const currentNote = notesMap[s.symbol] || '';

    this.container.innerHTML = `
      <div class="workspace-container" data-testid="portfolio-notes-tab">
        <div class="notes-editor-container">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 11px; font-weight: 700; color: var(--accent-blue);">
              📝 Research Notes for ${s.symbol}
            </span>
            <button class="btn btn-sm btn-primary" id="btn-save-notes" data-testid="btn-save-notes">
              💾 ${i18n.t('saveNotesBtn')}
            </button>
          </div>

          <textarea class="notes-textarea" 
                    id="notes-textarea"
                    placeholder="Write analytical notes, target price, risk assessment for ${s.symbol}..."
                    data-testid="notes-textarea">${currentNote}</textarea>
        </div>
      </div>
    `;

    this.bindEvents();
  }

  bindEvents() {
    const textarea = this.container.querySelector('#notes-textarea');
    const saveBtn = this.container.querySelector('#btn-save-notes');

    if (textarea) {
      textarea.addEventListener('input', () => {
        const s = store.getState();
        store.saveNote(s.symbol, textarea.value);
      });
    }

    if (saveBtn && textarea) {
      saveBtn.addEventListener('click', () => {
        const s = store.getState();
        store.saveNote(s.symbol, textarea.value);
        alert(i18n.t('notesAutosaved'));
      });
    }
  }
}
