/**
 * Lamba Design System — Color Palettes
 *
 * Two complete palettes (dark + light) sharing an identical shape so the rest
 * of the app can swap them transparently via ThemeContext.
 *
 * Brand accents (purple #6C63FF, teal-green #00D68F, coral #FF6B9D) stay
 * consistent across both themes. Backgrounds, text, and borders adapt per mode.
 */

export type ColorsType = {
  // ── Core Backgrounds ───────────────────────────────────
  background: string;
  surface: string;
  surfaceElevated: string;
  surfaceGlass: string;

  // ── Accent ─────────────────────────────────────────────
  primary: string;
  primaryLight: string;
  primaryDark: string;
  secondary: string;
  secondaryLight: string;
  accent: string;

  // ── Text ───────────────────────────────────────────────
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textDark: string;
  textOnPrimary: string;

  // ── Status ─────────────────────────────────────────────
  success: string;
  warning: string;
  error: string;
  critical: string;
  inStock: string;
  outOfStock: string;

  // ── Status Backgrounds & Borders ───────────────────────
  successBg: string;
  successBorder: string;
  errorBg: string;
  errorBorder: string;
  warningBg: string;
  warningBorder: string;
  criticalBg: string;
  criticalBorder: string;

  // ── Toggle States ──────────────────────────────────────
  toggleStockActive: string;
  toggleOfferActive: string;
  toggleInactive: string;

  // ── Tab Bar ────────────────────────────────────────────
  tabActive: string;
  tabInactive: string;

  // ── Interactive Pills ──────────────────────────────────
  ratePillBg: string;
  ratePillBorder: string;
  ratePillText: string;
  chatPillBg: string;
  chatPillBorder: string;

  // ── Borders & Dividers ─────────────────────────────────
  border: string;
  divider: string;

  // ── Map ────────────────────────────────────────────────
  mapOverlay: string;

  // ── Review Cards ───────────────────────────────────────
  surfaceReview: string;
  surfaceReviewBorder: string;

  // ── Overlay ────────────────────────────────────────────
  modalOverlay: string;
};

export const darkColors: ColorsType = {
  // ── Core Backgrounds ───────────────────────────────────
  background: '#0A0B14',
  surface: '#12142A',
  surfaceElevated: '#1A1D3A',
  surfaceGlass: 'rgba(18, 20, 42, 0.85)',

  // ── Accent ─────────────────────────────────────────────
  primary: '#6C63FF',
  primaryLight: '#8B83FF',
  primaryDark: '#4A42DB',
  secondary: '#00D68F',
  secondaryLight: '#33E4AB',
  accent: '#FF6B9D',

  // ── Text ───────────────────────────────────────────────
  textPrimary: '#FFFFFF',
  textSecondary: '#B0B3C6',
  textMuted: '#7A7D9C',
  textDark: '#5A5E7A',
  textOnPrimary: '#FFFFFF',

  // ── Status ─────────────────────────────────────────────
  success: '#00D68F',
  warning: '#FFA726',
  error: '#E53935',
  critical: '#FF6B35',
  inStock: '#00D68F',
  outOfStock: '#E53935',

  // ── Status Backgrounds & Borders ───────────────────────
  successBg: 'rgba(0, 214, 143, 0.12)',
  successBorder: 'rgba(0, 214, 143, 0.4)',
  errorBg: 'rgba(229, 57, 53, 0.08)',
  errorBorder: 'rgba(229, 57, 53, 0.2)',
  warningBg: 'rgba(255, 167, 38, 0.1)',
  warningBorder: 'rgba(255, 167, 38, 0.25)',
  criticalBg: 'rgba(255, 107, 53, 0.15)',
  criticalBorder: 'rgba(255, 107, 53, 0.3)',

  // ── Toggle States ──────────────────────────────────────
  toggleStockActive: '#6C63FF',
  toggleOfferActive: '#00D68F',
  toggleInactive: '#2A2D4A',

  // ── Tab Bar ────────────────────────────────────────────
  tabActive: '#00D68F',
  tabInactive: '#5A5E7A',

  // ── Interactive Pills ──────────────────────────────────
  ratePillBg: 'rgba(255, 176, 0, 0.1)',
  ratePillBorder: '#FFB000',
  ratePillText: '#FFB000',
  chatPillBg: 'rgba(108, 99, 255, 0.15)',
  chatPillBorder: 'rgba(108, 99, 255, 0.3)',

  // ── Borders & Dividers ─────────────────────────────────
  border: '#1E2040',
  divider: '#1E2040',

  // ── Map ────────────────────────────────────────────────
  mapOverlay: 'rgba(10, 11, 20, 0.6)',

  // ── Review Cards ───────────────────────────────────────
  surfaceReview: 'rgba(255,255,255,0.015)',
  surfaceReviewBorder: 'rgba(255,255,255,0.04)',

  // ── Overlay ────────────────────────────────────────────
  modalOverlay: 'rgba(10, 11, 20, 0.65)',
};

export const lightColors: ColorsType = {
  // ── Core Backgrounds ───────────────────────────────────
  background: '#F5F6FB',
  surface: '#FFFFFF',
  surfaceElevated: '#EEF0F8',
  surfaceGlass: 'rgba(255, 255, 255, 0.85)',

  // ── Accent ─────────────────────────────────────────────
  primary: '#6C63FF',
  primaryLight: '#8B83FF',
  primaryDark: '#4A42DB',
  secondary: '#00B573',
  secondaryLight: '#33E4AB',
  accent: '#FF6B9D',

  // ── Text ───────────────────────────────────────────────
  textPrimary: '#0E1030',
  textSecondary: '#4A4E6A',
  textMuted: '#7A7E9C',
  textDark: '#A8ACC2',
  textOnPrimary: '#FFFFFF',

  // ── Status ─────────────────────────────────────────────
  success: '#00B573',
  warning: '#E8920A',
  error: '#D32F2F',
  critical: '#E85A1F',
  inStock: '#00B573',
  outOfStock: '#D32F2F',

  // ── Status Backgrounds & Borders ───────────────────────
  successBg: 'rgba(0, 181, 115, 0.12)',
  successBorder: 'rgba(0, 181, 115, 0.35)',
  errorBg: 'rgba(211, 47, 47, 0.08)',
  errorBorder: 'rgba(211, 47, 47, 0.25)',
  warningBg: 'rgba(232, 146, 10, 0.1)',
  warningBorder: 'rgba(232, 146, 10, 0.3)',
  criticalBg: 'rgba(232, 90, 31, 0.12)',
  criticalBorder: 'rgba(232, 90, 31, 0.3)',

  // ── Toggle States ──────────────────────────────────────
  toggleStockActive: '#6C63FF',
  toggleOfferActive: '#00B573',
  toggleInactive: '#D7DAEA',

  // ── Tab Bar ────────────────────────────────────────────
  tabActive: '#00B573',
  tabInactive: '#A8ACC2',

  // ── Interactive Pills ──────────────────────────────────
  ratePillBg: 'rgba(255, 176, 0, 0.12)',
  ratePillBorder: '#E8A000',
  ratePillText: '#B07A00',
  chatPillBg: 'rgba(108, 99, 255, 0.12)',
  chatPillBorder: 'rgba(108, 99, 255, 0.35)',

  // ── Borders & Dividers ─────────────────────────────────
  border: '#E3E5F0',
  divider: '#EDEFF6',

  // ── Map ────────────────────────────────────────────────
  mapOverlay: 'rgba(245, 246, 251, 0.6)',

  // ── Review Cards ───────────────────────────────────────
  surfaceReview: 'rgba(14, 16, 48, 0.02)',
  surfaceReviewBorder: 'rgba(14, 16, 48, 0.05)',

  // ── Overlay ────────────────────────────────────────────
  modalOverlay: 'rgba(14, 16, 48, 0.45)',
};

export type ColorScheme = 'light' | 'dark';

export const getColors = (scheme: ColorScheme): ColorsType =>
  scheme === 'dark' ? darkColors : lightColors;