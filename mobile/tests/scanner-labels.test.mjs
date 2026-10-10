/**
 * The scanner drawer's labels for its three cases (stocked / in the catalog but not in my store / unknown barcode).
 * cd mobile && npm test
 *
 * The button of a catalog product that the shop does not stock used to say "إضافة منتج جديد" / "Add Brand-New"
 * (a key meant for another screen, shown because the key existed), and the badge and the quantity label used
 * a key that exists in neither locale file, so they were English in the Arabic UI.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
const en = JSON.parse(read('../locales/en.json'));
const ar = JSON.parse(read('../locales/ar.json'));
const scanner = read('../app/(merchant)/scanner.tsx');

const ARABIC = /[؀-ۿ]/;
const LATIN = /[A-Za-z]{3,}/;

const WORDING = {
  add_to_my_store: ['إضافة إلى متجري', 'Add to my store'],
  not_in_my_store: ['غير موجود في متجري', 'Not in my store'],
  add_as_new_product: ['إضافة كمنتج جديد', 'Add as a new product'],
  unknown_barcode_hint: ['هذا الباركود غير موجود في الكتالوج. أضفه كمنتج جديد.', "This barcode isn't in the catalog. Add it as a new product."],
};

test('the approved wording', () => {
  for (const [key, [arabic, english]] of Object.entries(WORDING)) {
    assert.equal(ar.scanner[key], arabic, `ar scanner.${key}`);
    assert.equal(en.scanner[key], english, `en scanner.${key}`);
  }
});

test('every new scanner label has a real Arabic and a real English text', () => {
  for (const key of ['stock_quantity', 'in_my_store', 'not_in_my_store', 'add_to_my_store', 'add_as_new_product', 'unknown_barcode_hint']) {
    assert.match(ar.scanner[key], ARABIC, `ar scanner.${key} has no Arabic letters`);
    assert.doesNotMatch(ar.scanner[key], LATIN, `ar scanner.${key} contains English words`);
    assert.match(en.scanner[key], LATIN, `en scanner.${key} has no English words`);
    assert.doesNotMatch(en.scanner[key], ARABIC, `en scanner.${key} contains Arabic`);
  }
});

test('each case of the drawer uses its own label key', () => {
  assert.match(scanner, /t\('scanner\.in_my_store'/);            // stocked: badge
  assert.match(scanner, /t\('scanner\.not_in_my_store'/);        // catalog product, not in my store: badge
  assert.match(scanner, /t\('scanner\.stock_quantity'/);         // quantity label
  assert.match(scanner, /t\('scanner\.add_to_my_store'/);        // catalog product, not in my store: button
  assert.match(scanner, /t\('scanner\.unknown_barcode_hint'/);   // unknown barcode: one-line explanation
  assert.match(scanner, /t\('scanner\.add_as_new_product'/);     // unknown barcode: button
});

test('the keys that were used for the wrong thing are gone from the drawer', () => {
  assert.doesNotMatch(scanner, /t\('inventory\.in_stock'/, 'a key that exists in neither locale');
  assert.doesNotMatch(scanner, /t\('addProduct\.add_new'/, '"Add Brand-New" on a catalog product');
  assert.doesNotMatch(scanner, /t\('scanner\.ingest_new_item'/, '"Ingest" is developer jargon');
});
