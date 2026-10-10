/**
 * The scanner changes what the shop stocks, but it has no mutation hook that patches the Stock tab's cache, and
 * that tab is never refetched on focus: a product linked in the scanner stayed invisible until pull-to-refresh.
 * cd mobile && npm test
 *
 * The scanner screen cannot run under Node, so this checks the wiring in the source.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
const scanner = read('../app/(merchant)/scanner.tsx');
const hooks = read('../hooks/useMerchant.ts');

/** The source of `const name = async (...) => { ... };` up to the next top-level (two-space) declaration */
function functionBody(source, name) {
  const start = source.indexOf(`  const ${name} = `);
  assert.ok(start >= 0, `${name} not found`);
  const next = source.slice(start + 10).search(/\n  (const|function|useEffect|useFocusEffect|if) /);
  return source.slice(start, next < 0 ? undefined : start + 10 + next);
}

test('useRefreshStock refreshes the stock list and the totals, and the sales history for a sale', () => {
  const body = hooks.slice(hooks.indexOf('export function useRefreshStock'));
  assert.match(body, /merchantKeys\.items/);
  assert.match(body, /merchantKeys\.inventoryValue/);
  assert.match(body, /options\?\.sale[\s\S]*merchantKeys\.checkoutHistory/);
});

test('saving a product in the scanner refreshes the Stock tab, even when a later step failed', () => {
  const save = functionBody(scanner, 'handleSave');
  assert.match(save, /finally\s*\{[\s\S]*refreshStock\(\)/);
});

test('finishing a sale refreshes the stock, the totals and the sales history', () => {
  const checkout = functionBody(scanner, 'handleCheckoutPOS');
  assert.match(checkout, /refreshStock\(\{ sale: true \}\)/);
});

test('a photo that fails to upload is explained in the app language, by status, not by the server text', () => {
  const save = functionBody(scanner, 'handleSave');
  assert.match(save, /photoUploadErrorKey\(photoErr\)/);
  assert.match(save, /scanner\.photo_not_uploaded/);
  assert.doesNotMatch(save, /response\??\.data\??\.detail/);
});

test('the thumbnail reports a failed load and shows an icon instead of an empty box', () => {
  assert.match(scanner, /onError=\{\(e\) =>/);
  assert.match(scanner, /setThumbFailed\(true\)/);
  assert.match(scanner, /thumbFailed \? 'image-outline'/);
});
