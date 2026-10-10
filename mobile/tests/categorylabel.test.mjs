/**
 * Tests for utils/categoryLabel.ts: which category name a screen shows.   cd mobile && npm test
 *
 * Node strips the TypeScript types and runs the file as it is (Node 22.18 or newer).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { categoryLabel } from '../utils/categoryLabel.ts';

const spices = { category: 'Spices & Sauces', category_name_ar: 'بهارات وصلصات', category_name_en: 'Spices & Sauces' };

test('the name in the app language is shown', () => {
  assert.equal(categoryLabel(spices, true), 'بهارات وصلصات');
  assert.equal(categoryLabel(spices, false), 'Spices & Sauces');
  assert.equal(categoryLabel({ ...spices, category_name_en: 'Spices and sauces' }, false), 'Spices and sauces');
});

test('a missing Arabic name falls back to the plain category, never to nothing', () => {
  const noArabic = { category: 'Spices & Sauces', category_name_ar: null, category_name_en: 'Spices & Sauces' };
  assert.equal(categoryLabel(noArabic, true), 'Spices & Sauces');
  assert.equal(categoryLabel({ category: 'Beverages' }, true), 'Beverages');
  assert.equal(categoryLabel({ category: 'Beverages' }, false), 'Beverages');
});

test('blank names count as missing', () => {
  const blank = { category: 'Dairy', category_name_ar: '   ', category_name_en: '' };
  assert.equal(categoryLabel(blank, true), 'Dairy');
  assert.equal(categoryLabel(blank, false), 'Dairy');
  assert.equal(categoryLabel({ category: '  ', category_name_ar: '', category_name_en: '' }, true, 'عام'), 'عام');
});

test('the fallback is used only when there is no name at all', () => {
  assert.equal(categoryLabel({}, true, 'عام'), 'عام');
  assert.equal(categoryLabel({ category: null }, false, 'General'), 'General');
  assert.equal(categoryLabel(null, true, 'عام'), 'عام');
  assert.equal(categoryLabel(undefined, false, 'General'), 'General');
  assert.equal(categoryLabel({ category: 'Bakery' }, true, 'عام'), 'Bakery');
});

test('no fallback means an empty string, not "undefined"', () => {
  assert.equal(categoryLabel({}, true), '');
  assert.equal(categoryLabel(undefined, undefined), '');
});

test('the Arabic name is not used in the English UI and the English one not in the Arabic UI', () => {
  const onlyArabic = { category: 'Bakery', category_name_ar: 'المخبوزات' };
  assert.equal(categoryLabel(onlyArabic, false), 'Bakery');
  const onlyEnglish = { category: 'Bakery', category_name_en: 'Bakery & Pastry' };
  assert.equal(categoryLabel(onlyEnglish, true), 'Bakery');
});

test('an undefined language is treated as English', () => {
  assert.equal(categoryLabel(spices, undefined), 'Spices & Sauces');
});
