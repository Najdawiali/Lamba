/**
 * The scanner's drawers (components/PinnedSheet.tsx): their text must be readable in BOTH themes.   cd mobile && npm test
 *
 * The sheet used to be a fixed dark colour while its text came from the theme, so in the light theme the product
 * name was #0E1030 on #0A0A1A (1.06:1). A sheet cannot be rendered here, so this checks what the fix rests on:
 *  - the palette pairs a sheet uses (text on the theme's own surface) stay at WCAG AA (4.5:1) in light and dark;
 *  - PinnedSheet takes its colours from the theme and hardcodes none;
 *  - the scanner builds both drawers with it (not with a hand-made absolute View) and does not bring back the
 *    React Native KeyboardAvoidingView, which does nothing on Android with edge-to-edge.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { darkColors, lightColors } from '../constants/palettes.ts';

const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');

const channel = (value) => {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
function luminance(hex) {
  assert.match(hex, /^#[0-9a-fA-F]{6}$/, `${hex} is not a plain #rrggbb colour`);
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// text token -> the surfaces it is drawn on inside a sheet (the sheet itself, and cards/inputs on it)
const SHEET_PAIRS = [
  ['textPrimary', 'surface'],
  ['textPrimary', 'surfaceElevated'],
  ['textSecondary', 'surface'],
  ['textSecondary', 'surfaceElevated'],
];

for (const [themeName, colors] of [['light', lightColors], ['dark', darkColors]]) {
  test(`${themeName} theme: sheet text is readable on the sheet and on its cards (WCAG AA 4.5:1)`, () => {
    for (const [text, surface] of SHEET_PAIRS) {
      const ratio = contrast(colors[text], colors[surface]);
      assert.ok(ratio >= 4.5, `${themeName}: ${text} ${colors[text]} on ${surface} ${colors[surface]} is only ${ratio.toFixed(2)}:1`);
    }
  });
}

test('the old fixed sheet colour was unreadable in the light theme (why the sheet must follow the theme)', () => {
  const oldSheet = '#0A0A1A'; // rgba(10,10,26,0.95) over black
  assert.ok(contrast(lightColors.textPrimary, oldSheet) < 1.5);
  assert.ok(contrast(darkColors.textPrimary, oldSheet) > 15);
});

test('PinnedSheet takes its surface from the theme and hardcodes no colour', () => {
  const source = read('../components/PinnedSheet.tsx');
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  assert.match(code, /Colors\.surface/);
  assert.match(code, /Colors\.border/);
  assert.doesNotMatch(code, /#[0-9a-fA-F]{3,8}\b|rgba?\(/, 'a literal colour in PinnedSheet');
  assert.match(code, /useSafeAreaInsets/);
  assert.match(code, /KeyboardStickyView/);
});

test('the scanner uses PinnedSheet for both drawers and no hand-made, inset-less, keyboard-less sheet', () => {
  const source = read('../app/(merchant)/scanner.tsx');
  assert.equal((source.match(/<PinnedSheet\b/g) || []).length, 2, 'the inventory drawer and the cart drawer');
  assert.doesNotMatch(source, /drawerContainer/);
  assert.doesNotMatch(source, /KeyboardAvoidingView/);
});
