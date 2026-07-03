/**
 * Lamba Design System — Theme Constants
 *
 * Static design tokens (spacing, typography, border radii, shadows) that do not
 * change with the color scheme. The dynamic color palettes live in
 * `./palettes.ts` and are consumed via `ThemeContext`.
 *
 * For backward compatibility, `Colors` re-exports the dark palette so that
 * any module still importing it compiles — but new code should use
 * `useThemeColors()` from `../context/ThemeContext` for live switching.
 */

import { darkColors, type ColorsType, type ColorScheme } from './palettes';

export { darkColors, lightColors, getColors } from './palettes';
export type { ColorsType, ColorScheme } from './palettes';

/** @deprecated Use `useThemeColors()` from context/ThemeContext for live switching. */
export const Colors: ColorsType = darkColors;

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

export type ShadowKey = 'small' | 'medium' | 'large' | 'glow';

export interface ShadowToken {
  shadowColor: string;
  shadowOffset: { width: number; height: number };
  shadowOpacity: number;
  shadowRadius: number;
  elevation: number;
}

export const Shadows: Record<ShadowKey, ShadowToken> = {
  small: buildShadow(0, 2, 0.14, 4, 3),
  medium: buildShadow(0, 4, 0.18, 8, 6),
  large: buildShadowGlow('#6C63FF', 0, 6, 0.2, 16, 10),
  glow: buildShadowGlow('#6C63FF', 0, 0, 0.4, 20, 8),
};

function buildShadow(
  offsetX: number,
  offsetY: number,
  opacity: number,
  radius: number,
  elevation: number,
): ShadowToken {
  return {
    shadowColor: '#000',
    shadowOffset: { width: offsetX, height: offsetY },
    shadowOpacity: opacity,
    shadowRadius: radius,
    elevation,
  };
}

function buildShadowGlow(
  color: string,
  offsetX: number,
  offsetY: number,
  opacity: number,
  radius: number,
  elevation: number,
): ShadowToken {
  return {
    shadowColor: color,
    shadowOffset: { width: offsetX, height: offsetY },
    shadowOpacity: opacity,
    shadowRadius: radius,
    elevation,
  };
}

/**
 * Resolve shadow tokens for a given scheme. Light mode uses the same purple
 * `glow` for the brand element but reduces base shadow opacities so cards
 * stay readable against light backgrounds.
 */
export function getShadows(scheme: ColorScheme) {
  const baseOpacityMul = scheme === 'dark' ? 1 : 0.5;
  return {
    small: buildShadow(0, 2, 0.14 * baseOpacityMul, 4, 3),
    medium: buildShadow(0, 4, 0.18 * baseOpacityMul, 8, 6),
    large: buildShadowGlow('#6C63FF', 0, 6, 0.2 * baseOpacityMul, 16, 10),
    glow: buildShadowGlow('#6C63FF', 0, 0, 0.4 * baseOpacityMul, 20, 8),
  };
}