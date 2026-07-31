// Reusable State Alert Component for Explicit Loading, Empty, Error, and Stale Data handling
import { i18n } from '../i18n/index.js';

export function renderLoadingState(containerElement) {
  if (!containerElement) return;
  containerElement.innerHTML = `
    <div class="state-container" data-testid="loading-state">
      <div class="state-icon">⏳</div>
      <div class="state-title">${i18n.t('loading')}</div>
    </div>
  `;
}

export function renderEmptyState(containerElement, message = '') {
  if (!containerElement) return;
  containerElement.innerHTML = `
    <div class="state-container" data-testid="empty-state">
      <div class="state-icon">📂</div>
      <div class="state-title">${i18n.t('emptyData')}</div>
      <div style="font-size: 11px;">${message}</div>
    </div>
  `;
}

export function renderErrorState(containerElement, errorMessage = '', onRetry = null) {
  if (!containerElement) return;
  containerElement.innerHTML = `
    <div class="state-container" data-testid="error-state">
      <div class="state-icon">⚠️</div>
      <div class="state-title" style="color: var(--accent-red);">${i18n.t('errorOccurred')}</div>
      <div style="font-size: 11px; color: var(--text-muted);">${errorMessage}</div>
      <button class="btn btn-sm" id="retry-btn">${i18n.t('retryBtn')}</button>
    </div>
  `;

  if (onRetry) {
    const btn = containerElement.querySelector('#retry-btn');
    if (btn) btn.addEventListener('click', onRetry);
  }
}

export function renderStaleWarningBanner(containerElement, warningMessage = '') {
  if (!containerElement) return;
  const existing = containerElement.querySelector('.stale-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.className = 'stale-banner badge badge-warning';
  banner.style.width = '100%';
  banner.style.borderRadius = '4px';
  banner.style.marginBottom = '8px';
  banner.style.padding = '6px 10px';
  banner.innerHTML = `⚠️ ${warningMessage || i18n.t('staleWarning')}`;
  
  containerElement.prepend(banner);
}
