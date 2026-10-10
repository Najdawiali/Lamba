/**
 * Translation keys: every t('some.key', 'fallback') in the app must exist in BOTH locales/en.json and
 * locales/ar.json.   cd mobile && npm test
 *
 * Why: t() (services/i18n.ts) silently returns the caller's fallback string for a missing key, so a typo or a
 * forgotten key never fails tsc or a test, and the Arabic UI simply shows English (forgot-password, verify,
 * "Stock Quantity" in the scanner...). This test is a RATCHET:
 *   - a key that is missing and NOT in tests/i18n-known-missing.json fails the test: add it to both locale
 *     files (the Arabic written by someone who reads Arabic, not a copy of the English);
 *   - a key listed there that now exists (or is no longer used) also fails: delete it from the list, so the
 *     list can only shrink.
 * Also checked: en.json and ar.json have exactly the same keys.
 *
 * Only calls with a literal key are seen. Keys built at runtime (t(`storeLocation.problem_${x}`), t(opt.labelKey))
 * are not.
 */

import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_DIRS = ['app', 'components', 'hooks', 'services', 'utils', 'context', 'constants'];
const SKIP_DIRS = new Set(['node_modules']);

const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'));
const en = readJson(join(ROOT, 'locales', 'en.json'));
const ar = readJson(join(ROOT, 'locales', 'ar.json'));
const known = readJson(join(ROOT, 'tests', 'i18n-known-missing.json'));

function flatten(obj, prefix = '') {
  return Object.entries(obj).flatMap(([key, value]) =>
    value && typeof value === 'object' ? flatten(value, `${prefix}${key}.`) : [`${prefix}${key}`]);
}

function sourceFiles(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) sourceFiles(path, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.d\.ts$/.test(name)) out.push(path);
  }
  return out;
}

// t('a.b') / t("a.b") / t(`a.b`), not preceded by a letter, digit, _, $ or . (so i18n.t( and format( are not seen)
const T_CALL = /(?<![\w.$])t\(\s*(['"`])([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)\1/g;

/** key -> ['app/x.tsx:12', ...] for every literal key used in the app */
function usedKeys() {
  const used = new Map();
  for (const dir of SOURCE_DIRS) {
    let files = [];
    try { files = sourceFiles(join(ROOT, dir)); } catch { continue; }
    for (const file of files) {
      const text = readFileSync(file, 'utf8');
      for (const match of text.matchAll(T_CALL)) {
        const line = text.slice(0, match.index).split('\n').length;
        const where = `${relative(ROOT, file).replace(/\\/g, '/')}:${line}`;
        if (!used.has(match[2])) used.set(match[2], []);
        used.get(match[2]).push(where);
      }
    }
  }
  return used;
}

const get = (obj, key) => key.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), obj);
const isTranslated = (key) => typeof get(en, key) === 'string' && typeof get(ar, key) === 'string';

const used = usedKeys();
const knownMissing = new Set(known.keys);

test('the scan finds the app\'s translation calls (guards against the test silently checking nothing)', () => {
  assert.ok(used.size > 400, `only ${used.size} keys found`);
  assert.ok(used.has('common.cancel'));
  assert.ok(used.has('tabs.dashboard'));
});

test('en.json and ar.json have exactly the same keys', () => {
  const enKeys = new Set(flatten(en));
  const arKeys = new Set(flatten(ar));
  const onlyEn = [...enKeys].filter((k) => !arKeys.has(k));
  const onlyAr = [...arKeys].filter((k) => !enKeys.has(k));
  assert.deepEqual({ onlyEn, onlyAr }, { onlyEn: [], onlyAr: [] },
    'every key needs an Arabic and an English text: add the missing side');
});

test('no NEW key is used without a translation in both languages', () => {
  const fresh = [...used.keys()].filter((k) => !isTranslated(k) && !knownMissing.has(k)).sort();
  const report = fresh.map((k) => `  ${k}   (${used.get(k).slice(0, 3).join(', ')})`).join('\n');
  assert.equal(fresh.length, 0,
    `\n${fresh.length} key(s) used in the app but missing from locales/en.json and/or ar.json.\n` +
    `Add them to BOTH files with real Arabic and English text (do not add them to tests/i18n-known-missing.json):\n${report}\n`);
});

test('the known-missing list only shrinks: every entry is still used and still missing', () => {
  const stale = known.keys.filter((k) => !used.has(k) || isTranslated(k)).sort();
  assert.equal(stale.length, 0,
    `\nThese keys in tests/i18n-known-missing.json are now translated or no longer used; delete them from the list:\n` +
    stale.map((k) => `  ${k}${used.has(k) ? '' : '   (not used any more)'}`).join('\n') + '\n');
});

test('the known-missing list is sorted and has no duplicates', () => {
  const sorted = [...new Set(known.keys)].sort();
  assert.deepEqual(known.keys, sorted);
});
