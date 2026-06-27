/**
 * Currency Service — Locale-based currency detection & formatting.
 *
 * Detects user's locale on first launch and defaults to the appropriate currency:
 * - JO locale → JOD (Jordanian Dinar)
 * - SA locale → SAR (Saudi Riyal)
 * - Fallback → USD
 *
 * Stores preference in SecureStore. Allows override from Profile → Settings.
 * Format: [amount] [code] — e.g. "45.00 JOD". Always 2 decimal places.
 */

import * as Localization from 'expo-localization';
import * as SecureStore from 'expo-secure-store';

const CURRENCY_KEY = 'lamba_currency';

// Map of country/region codes to currency codes
const LOCALE_CURRENCY_MAP: Record<string, string> = {
  JO: 'JOD',  // Jordan
  SA: 'SAR',  // Saudi Arabia
  AE: 'AED',  // UAE
  KW: 'KWD',  // Kuwait
  BH: 'BHD',  // Bahrain
  QA: 'QAR',  // Qatar
  OM: 'OMR',  // Oman
  EG: 'EGP',  // Egypt
  LB: 'LBP',  // Lebanon
  IQ: 'IQD',  // Iraq
  PS: 'ILS',  // Palestine
  US: 'USD',  // USA
  GB: 'GBP',  // UK
  EU: 'EUR',  // Europe
};

let _currentCurrency: string = 'JOD'; // Default to JOD

/**
 * Detect and set currency on first launch. Call once during app init.
 */
export const setupCurrency = async (): Promise<void> => {
  try {
    // Check for stored preference first
    const saved = await SecureStore.getItemAsync(CURRENCY_KEY);
    if (saved) {
      _currentCurrency = saved;
      return;
    }

    // Detect from device locale
    const locales = Localization.getLocales();
    const regionCode = locales?.[0]?.regionCode?.toUpperCase();

    if (regionCode && LOCALE_CURRENCY_MAP[regionCode]) {
      _currentCurrency = LOCALE_CURRENCY_MAP[regionCode];
    } else {
      _currentCurrency = 'JOD'; // Default fallback
    }

    // Persist the detected currency
    await SecureStore.setItemAsync(CURRENCY_KEY, _currentCurrency);
  } catch (err) {
    console.warn('Currency detection failed, defaulting to JOD:', err);
    _currentCurrency = 'JOD';
  }
};

/**
 * Get the current currency code.
 */
export const getCurrencyCode = (): string => _currentCurrency;

/**
 * Override the currency preference (from Profile → Settings).
 */
export const setCurrency = async (code: string): Promise<void> => {
  _currentCurrency = code.toUpperCase();
  try {
    await SecureStore.setItemAsync(CURRENCY_KEY, _currentCurrency);
  } catch (err) {
    console.warn('Failed to persist currency preference:', err);
  }
};

// Exchange rates relative to JOD (Base currency)
const EXCHANGE_RATES_FROM_JOD: Record<string, number> = {
  JOD: 1.00,
  SAR: 5.29,
  AED: 5.18,
  KWD: 0.43,
  USD: 1.41,
  EUR: 1.31,
  EGP: 67.00,
};

/**
 * Format a price with currency code and perform exchange rate conversion.
 * Base prices are assumed to be in JOD.
 * Returns: "14.00 JOD" or converted equivalent e.g., "19.74 USD"
 */
export const formatPrice = (amount: number | string | null | undefined): string => {
  if (amount === null || amount === undefined || amount === '') return `0.00 ${_currentCurrency}`;
  const num = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (isNaN(num)) return `0.00 ${_currentCurrency}`;
  
  const rate = EXCHANGE_RATES_FROM_JOD[_currentCurrency] || 1;
  const convertedAmount = num * rate;

  return `${convertedAmount.toFixed(2)} ${_currentCurrency}`;
};

/**
 * Get list of supported currencies for settings picker.
 */
export const SUPPORTED_CURRENCIES = [
  { code: 'JOD', label: 'Jordanian Dinar', labelAr: 'دينار أردني' },
  { code: 'SAR', label: 'Saudi Riyal', labelAr: 'ريال سعودي' },
  { code: 'AED', label: 'UAE Dirham', labelAr: 'درهم إماراتي' },
  { code: 'KWD', label: 'Kuwaiti Dinar', labelAr: 'دينار كويتي' },
  { code: 'USD', label: 'US Dollar', labelAr: 'دولار أمريكي' },
  { code: 'EUR', label: 'Euro', labelAr: 'يورو' },
  { code: 'EGP', label: 'Egyptian Pound', labelAr: 'جنيه مصري' },
] as const;
