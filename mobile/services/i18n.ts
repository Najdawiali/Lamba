import { I18nManager } from 'react-native';
import * as Localization from 'expo-localization';
import { I18n } from 'i18n-js';
import * as SecureStore from 'expo-secure-store';

import en from '../locales/en.json';
import ar from '../locales/ar.json';

// Initialize i18n
export const i18n = new I18n({
  en,
  ar,
});

i18n.enableFallback = true;
i18n.defaultLocale = 'ar';
i18n.locale = 'ar';

const LANGUAGE_KEY = 'lamba_language';

// Setup i18n on app start
export const setupI18n = async () => {
  try {
    const savedLanguage = await SecureStore.getItemAsync(LANGUAGE_KEY);
    const lang = savedLanguage || 'ar';
    i18n.locale = lang;
    const isRTL = lang.startsWith('ar');
    I18nManager.allowRTL(isRTL);
    I18nManager.forceRTL(isRTL);
  } catch {
    i18n.locale = 'ar';
    I18nManager.allowRTL(true);
    I18nManager.forceRTL(true);
  }
};

// Toggle language (simple in-memory swap for Expo Go compatibility)
export const toggleLanguage = async () => {
  const currentLang = i18n.locale.includes('ar') ? 'ar' : 'en';
  const newLang = currentLang === 'en' ? 'ar' : 'en';

  const isRTL = newLang === 'ar';

  // Persist preference
  try {
    await SecureStore.setItemAsync(LANGUAGE_KEY, newLang);
  } catch {}

  // Update locale
  i18n.locale = newLang;

  // Force RTL layout if Arabic
  I18nManager.allowRTL(isRTL);
  I18nManager.forceRTL(isRTL);

  // Reload app to apply RTL layout changes
  try {
    const Updates = require('expo-updates');
    if (Updates && Updates.reloadAsync) {
      await Updates.reloadAsync();
    }
  } catch (e) {
    // In Expo Go / dev mode, Updates.reloadAsync() will throw or not be available.
    // We catch this so the caller (like profile.tsx) can show an alert asking the user to manually restart.
    console.warn('Could not auto-reload app, manual restart required:', e);
  }
};

// Expose standard translation function.
// Supports an optional fallback string (commonly used as
// `t('search.filters', 'Filters')`). i18n-js's own fallback machinery only
// honours the locale JSON, so without this wrapper the "fallback" would be
// silently passed as interpolation options and missing keys would render as
// the raw key string on screen.
//
// Signature variants:
//   t(key)                                   — translate
//   t(key, optionsObject)                    — translate with interpolation
//   t(key, fallbackString)                   — translate with fallback
//   t(key, fallbackString, optionsObject)    — translate with fallback + interpolation
export function t(key: string, second?: any, third?: any): string {
  let fallback: string | null = null;
  let options: any = undefined;

  if (second !== undefined) {
    if (typeof second === 'string') {
      fallback = second;
      options = third;
    } else {
      // Object form: t(key, options)
      options = second;
    }
  }

  const value = i18n.t(key, options);
  // Detect i18n-js "missing translation" outcomes:
  //   - the key path itself (some configs)
  //   - the placeholder `'[missing "locale.key" translation]'`
  //   - undefined/null/empty
  // In any of those cases, honour the caller-supplied fallback so the UI never
  // shows raw key paths or "[missing ...]" placeholder strings.
  const isMissing =
    value === key ||
    value === undefined ||
    value === null ||
    value === '' ||
    (typeof value === 'string' && value.startsWith('[missing '));
  if (isMissing && fallback) {
    return fallback;
  }
  return value as string;
}

// Reactive RTL check — re-evaluates on every call (not a static const)
export const isRTL = (): boolean => i18n.locale.includes('ar');

