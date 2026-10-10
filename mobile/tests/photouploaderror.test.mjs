/**
 * Tests for utils/photoUploadError.ts: why a scanner photo upload failed, as a locale key.   cd mobile && npm test
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { PHOTO_ERROR_KEYS, photoUploadErrorKey } from '../utils/photoUploadError.ts';

const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
const en = JSON.parse(read('../locales/en.json'));
const ar = JSON.parse(read('../locales/ar.json'));
const get = (obj, key) => key.split('.').reduce((o, k) => o?.[k], obj);

const http = (status) => ({ response: { status, data: { detail: 'whatever the server said' } } });

test('the status decides the reason', () => {
  assert.equal(photoUploadErrorKey(http(413)), 'scanner.photo_err_too_large');
  assert.equal(photoUploadErrorKey(http(415)), 'scanner.photo_err_not_image');
  assert.equal(photoUploadErrorKey(http(422)), 'scanner.photo_err_not_image');
  assert.equal(photoUploadErrorKey(http(409)), 'scanner.photo_err_limit');
});

test('no response at all is a connection problem', () => {
  assert.equal(photoUploadErrorKey(new Error('Network Error')), 'scanner.photo_err_network');
  assert.equal(photoUploadErrorKey({ code: 'ECONNABORTED' }), 'scanner.photo_err_network');
  assert.equal(photoUploadErrorKey(null), 'scanner.photo_err_network');
  assert.equal(photoUploadErrorKey(undefined), 'scanner.photo_err_network');
});

test('anything else is the generic reason', () => {
  for (const status of [400, 403, 404, 500, 502, 503]) {
    assert.equal(photoUploadErrorKey(http(status)), 'scanner.photo_err_other', String(status));
  }
});

test('the server\'s own text is never what is shown', () => {
  assert.ok(PHOTO_ERROR_KEYS.includes(photoUploadErrorKey(http(413))));
});

test('every reason key has real Arabic and English text', () => {
  // The keys are returned from code, so the translation-key test (literal t() calls only) cannot see them.
  for (const key of [...PHOTO_ERROR_KEYS, 'scanner.photo_saved_title', 'scanner.photo_not_uploaded', 'scanner.photo_retry_hint']) {
    assert.match(String(get(ar, key)), /[؀-ۿ]/, `ar ${key}`);
    assert.match(String(get(en, key)), /[A-Za-z]{3,}/, `en ${key}`);
  }
});
