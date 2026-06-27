/**
 * Lamba Design System — Theme Constants
 *
 * Premium dark-first theme with vibrant accents.
 * All colors, spacing, typography, and shadows defined here.
 *
 * Color discipline (from seller-side spec):
 * - Purple (#6C63FF): barcode scanner UI, catalog actions, selected states
 * - Teal-green (#00D68F): CTAs, active nav, prices, success, bottom nav active
 * - Red (#E53935): destructive actions, out-of-stock, closed badges, errors
 * - Orange (#FF6B35): critical stock
 * - Amber (#FFA726): low stock warning
 * - White (#FFFFFF): primary text
 * - #B0B3C6: secondary/body text
 * - #7A7D9C: muted/caption text, section labels
 * - #5A5E7A: disabled/version text, inactive nav icons
 * - #1A1D3A: elevated surfaces, chips, input backgrounds
 * - #12142A: card backgrounds
 * - #0A0B14: page background
 */

export const Colors = {
  // ── Core Backgrounds ───────────────────────────────────
  background: '#0A0B14',       // Page background
  surface: '#12142A',          // Card backgrounds
  surfaceElevated: '#1A1D3A',  // Elevated cards, chips, input backgrounds
  surfaceGlass: 'rgba(18, 20, 42, 0.85)',

  // ── Accent ─────────────────────────────────────────────
  primary: '#6C63FF',          // Vibrant purple — scanner, catalog, selected
  primaryLight: '#8B83FF',
  primaryDark: '#4A42DB',
  secondary: '#00D68F',        // Teal-green — CTAs, active states, success
  secondaryLight: '#33E4AB',
  accent: '#FF6B9D',           // Coral pink (decorative)

  // ── Text ───────────────────────────────────────────────
  textPrimary: '#FFFFFF',      // Primary text — white
  textSecondary: '#B0B3C6',    // Secondary/body text
  textMuted: '#7A7D9C',        // Muted — section labels, captions
  textDark: '#5A5E7A',         // Disabled/version text, inactive nav
  textOnPrimary: '#FFFFFF',    // Text on primary buttons

  // ── Status ─────────────────────────────────────────────
  success: '#00D68F',          // Aligned to teal-green CTA
  warning: '#FFA726',          // Amber — low stock
  error: '#E53935',            // Red — destructive/out-of-stock
  critical: '#FF6B35',         // Orange — critical stock
  inStock: '#00D68F',          // Green dot
  outOfStock: '#E53935',       // Red dot

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
  toggleStockActive: '#6C63FF',    // In-stock toggle ON track
  toggleOfferActive: '#00D68F',    // Offer active toggle ON track
  toggleInactive: '#2A2D4A',       // Toggle OFF track

  // ── Tab Bar ────────────────────────────────────────────
  tabActive: '#00D68F',        // Bottom nav active tint
  tabInactive: '#5A5E7A',     // Bottom nav inactive tint

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
} as const;

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const BorderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,        // Pill badges
  xxl: 24,
  full: 999,
} as const;

export const Typography = {
  // Display — top-level screen titles
  display: { fontSize: 32, fontWeight: '700' as const, lineHeight: 40 },
  h1: { fontSize: 28, fontWeight: '700' as const, letterSpacing: -0.5, lineHeight: 36 },
  h2: { fontSize: 22, fontWeight: '700' as const, letterSpacing: -0.3, lineHeight: 30 },
  // Sub-screen title (centered)
  h3: { fontSize: 20, fontWeight: '600' as const, lineHeight: 28 },
  // Card/item title
  subheading: { fontSize: 17, fontWeight: '600' as const, lineHeight: 24 },
  body: { fontSize: 15, fontWeight: '400' as const, lineHeight: 22 },
  bodySmall: { fontSize: 14, fontWeight: '400' as const, lineHeight: 20 },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  // Section label — UPPERCASE muted
  label: { fontSize: 11, fontWeight: '600' as const, letterSpacing: 0.5, lineHeight: 16 },
  // Badge/tag text
  badge: { fontSize: 11, fontWeight: '600' as const, lineHeight: 14 },
  // Price/key metric
  price: { fontSize: 15, fontWeight: '600' as const, lineHeight: 20 },
  // Button text
  button: { fontSize: 15, fontWeight: '600' as const, letterSpacing: 0.3, lineHeight: 22 },
  // Link/action text
  link: { fontSize: 14, fontWeight: '600' as const, lineHeight: 20 },
  // Muted/version
  muted: { fontSize: 12, fontWeight: '400' as const, lineHeight: 16 },
} as const;

export const Shadows = {
  small: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 3,
  },
  medium: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  large: {
    shadowColor: '#6C63FF',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.2,
    shadowRadius: 16,
    elevation: 10,
  },
  glow: {
    shadowColor: '#6C63FF',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 20,
    elevation: 8,
  },
} as const;
