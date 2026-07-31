// Bilingual i18n Translation Manager
import vi from './vi.js';
import en from './en.js';

class I18nManager {
  constructor() {
    this.locale = 'vi'; // Default Vietnamese
    this.dictionaries = { vi, en };
    this.listeners = [];
  }

  setLocale(locale) {
    if (this.dictionaries[locale]) {
      this.locale = locale;
      this.notify();
    }
  }

  getLocale() {
    return this.locale;
  }

  toggleLocale() {
    this.setLocale(this.locale === 'vi' ? 'en' : 'vi');
  }

  t(key, fallback = '') {
    const dict = this.dictionaries[this.locale] || this.dictionaries['vi'];
    return dict[key] || fallback || key;
  }

  onChange(callback) {
    this.listeners.push(callback);
  }

  notify() {
    this.listeners.forEach(cb => cb(this.locale));
  }
}

export const i18n = new I18nManager();
