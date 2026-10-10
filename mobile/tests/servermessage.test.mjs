/**
 * Tests for utils/serverMessage.ts: which text an API failure shows in the app.   cd mobile && npm test
 *
 * Node strips the TypeScript types and runs the file as it is (Node 22.18 or newer).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { localizeServerMessage, messageFromError } from '../utils/serverMessage.ts';

const FALLBACK = 'fallback';
const BILINGUAL = 'هذا الباركود موجود في الكتالوج.\nThis barcode is already in the catalog.';

test('a plain string is shown as it is', () => {
  assert.equal(localizeServerMessage('Not allowed', false, FALLBACK), 'Not allowed');
  assert.equal(localizeServerMessage('  Not allowed  ', true, FALLBACK), 'Not allowed');
});

test('a bilingual string shows only the line in the app language', () => {
  assert.equal(localizeServerMessage(BILINGUAL, true, FALLBACK), 'هذا الباركود موجود في الكتالوج.');
  assert.equal(localizeServerMessage(BILINGUAL, false, FALLBACK), 'This barcode is already in the catalog.');
});

test('409 barcode_exists: the message of the object is shown, never the object', () => {
  const detail = { code: 'barcode_exists', message: BILINGUAL, global_item_id: 'b1d0c0de-0000-4000-8000-000000000001' };
  assert.equal(localizeServerMessage(detail, true, FALLBACK), 'هذا الباركود موجود في الكتالوج.');
  assert.equal(localizeServerMessage(detail, false, FALLBACK), 'This barcode is already in the catalog.');
});

test('an object whose message is a single-language string is shown as it is', () => {
  const detail = { code: 'barcode_exists', message: 'هذا الباركود موجود في الكتالوج.' };
  assert.equal(localizeServerMessage(detail, false, FALLBACK), 'هذا الباركود موجود في الكتالوج.');
});

test('shapes with no usable message get the fallback', () => {
  assert.equal(localizeServerMessage(undefined, true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage(null, true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage('   ', true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage({}, true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage({ code: 'x' }, true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage({ message: 42 }, true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage({ message: '  ' }, true, FALLBACK), FALLBACK);
  // FastAPI 422: a list of {loc, msg, type}
  assert.equal(localizeServerMessage([{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }], true, FALLBACK), FALLBACK);
  assert.equal(localizeServerMessage(7, true, FALLBACK), FALLBACK);
});

test('messageFromError: no response is the network text, a response goes through the same rules', () => {
  const text = { network: 'offline', fallback: FALLBACK };
  assert.equal(messageFromError(new Error('Network Error'), false, text), 'offline');
  assert.equal(messageFromError({ response: { data: { detail: BILINGUAL } } }, false, text), 'This barcode is already in the catalog.');
  assert.equal(messageFromError({ response: { data: { detail: { message: BILINGUAL } } } }, true, text), 'هذا الباركود موجود في الكتالوج.');
  assert.equal(messageFromError({ response: { data: {} } }, true, text), FALLBACK);
});
