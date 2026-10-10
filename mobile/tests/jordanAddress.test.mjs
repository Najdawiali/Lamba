/**
 * Tests for utils/jordanAddress.ts: governorate matching, the device-geocoder prefill, the pin rules,
 * the form checks and the address text customers see. No React Native, no device:   cd mobile && npm test
 *
 * Node strips the TypeScript types and runs the file as it is (Node 22.18 or newer).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  GOVERNORATES, FREE_MOVE_LIMIT_M, GPS_WARN_ACCURACY_M, JORDAN_BOUNDS, JORDAN_CENTER,
  AREA_MAX_LENGTH, STREET_MAX_LENGTH, LANDMARK_MAX_LENGTH, EMPTY_LOCATION,
  governorateName, isInsideJordan, distanceMeters, needsAccuracyWarning, moveStatus,
  normalizeName, matchGovernorate, prefillFromDeviceAddress, planPrefill, applyPlan,
  locationProblems, toLocationPayload, locationFromMarket, formatStoreAddress,
} from '../utils/jordanAddress.ts';

const ARABIC_FIRST = String.fromCharCode(0x0600);
const ARABIC_LAST = String.fromCharCode(0x06ff);
const isArabic = (text) => [...text].every((c) => c === ' ' || (c >= ARABIC_FIRST && c <= ARABIC_LAST));

// ── governorates ──────────────────────────────────────────────────────────

test('there are twelve governorates with unique keys and names, plain ASCII keys', () => {
  assert.equal(GOVERNORATES.length, 12);
  for (const field of ['key', 'ar', 'en']) {
    assert.equal(new Set(GOVERNORATES.map((g) => g[field])).size, 12, field);
  }
  for (const g of GOVERNORATES) {
    assert.match(g.key, /^[a-z]+$/);
    assert.ok(g.key.length <= 20);
    assert.ok(isArabic(g.ar), g.key);
  }
});

test('governorateName follows the language and is empty for an unknown key', () => {
  assert.equal(governorateName('balqa', true), 'البلقاء');
  assert.equal(governorateName('balqa', false), 'Balqa');
  assert.equal(governorateName('maan', false), "Ma'an");
  assert.equal(governorateName('nowhere', true), '');
  assert.equal(governorateName(null, false), '');
  assert.equal(governorateName(undefined, true), '');
});

test('matchGovernorate reads the ways a geocoder writes a governorate', () => {
  const cases = [
    ['Balqa Governorate', 'balqa'],
    ['Al-Balqa', 'balqa'],
    ['محافظة البلقاء', 'balqa'],
    ['البلقاء', 'balqa'],
    ["Ma'an Governorate", 'maan'],
    ['Maan', 'maan'],
    ['معان', 'maan'],
    ['Amman Governorate', 'amman'],
    ['عمان', 'amman'],
    ['Capital Governorate', 'amman'],
    ['Irbid', 'irbid'],
    ['إربد', 'irbid'],
    ['اربد', 'irbid'],
    ["Al-'Aqabah", 'aqaba'],
    ['Aqaba', 'aqaba'],
    ['العقبة', 'aqaba'],
    ['Az Zarqa', 'zarqa'],
    ['الزرقاء', 'zarqa'],
    ['Al Karak', 'karak'],
    ['Kerak Governorate', 'karak'],
    ['At-Tafilah', 'tafilah'],
    ['Madaba', 'madaba'],
    ['مأدبا', 'madaba'],
    ['مادبا', 'madaba'],
    ['Jarash', 'jerash'],
    ['جرش', 'jerash'],
    ['Ajlun', 'ajloun'],
    ['عجلون', 'ajloun'],
    ['Al Mafraq', 'mafraq'],
    ['المفرق', 'mafraq'],
  ];
  for (const [text, key] of cases) assert.equal(matchGovernorate([text]), key, text);
});

test('every governorate matches its own names', () => {
  for (const g of GOVERNORATES) {
    for (const name of [g.key, g.ar, g.en, ...g.aliases]) assert.equal(matchGovernorate([name]), g.key, name);
  }
});

test('matchGovernorate falls back to a main town, and prefers a real governorate name', () => {
  assert.equal(matchGovernorate(['As-Salt']), 'balqa');
  assert.equal(matchGovernorate(['السلط']), 'balqa');
  assert.equal(matchGovernorate(['As-Salt', 'Amman Governorate']), 'amman');
});

test('matchGovernorate is null for things that are not a governorate', () => {
  assert.equal(matchGovernorate(['Texas', 'Jordan', '', null, undefined]), null);
  assert.equal(matchGovernorate([]), null);
});

test('normalizeName folds case, marks, alef and teh forms, punctuation and the article', () => {
  assert.equal(normalizeName("Al-'Aqabah"), 'aqabah');
  assert.equal(normalizeName('  Ma’an  '), 'maan');
  assert.equal(normalizeName('الأردن'), normalizeName('الاردن'));
  assert.equal(normalizeName('مدينة'), normalizeName('مدينه'));
  assert.equal(normalizeName(null), '');
});

// ── the device geocoder prefill ───────────────────────────────────────────

test('the reported case: only city and region come back (As-Salt, Balqa Governorate)', () => {
  const prefill = prefillFromDeviceAddress({ city: 'As-Salt', region: 'Balqa Governorate', street: null, district: null });
  assert.deepEqual(prefill, { governorate: 'balqa', area: 'As-Salt', street: '' });
});

test('a full Amman answer fills all three', () => {
  const prefill = prefillFromDeviceAddress({
    street: 'Wasfi Al Tal St', streetNumber: '12', district: 'Abdoun', city: 'Amman',
    region: 'Amman Governorate', country: 'Jordan', name: '12',
    formattedAddress: 'Wasfi Al Tal St 12, Abdoun, Amman, Jordan',
  });
  assert.deepEqual(prefill, { governorate: 'amman', area: 'Abdoun', street: 'Wasfi Al Tal St' });
});

test('an Arabic answer works the same', () => {
  const prefill = prefillFromDeviceAddress({
    region: 'محافظة البلقاء', city: 'السلط', district: 'المدينة الرياضية', street: 'شارع الجامعة', country: 'الأردن',
  });
  assert.deepEqual(prefill, { governorate: 'balqa', area: 'المدينة الرياضية', street: 'شارع الجامعة' });
});

test('name is used for the street when there is no street, unless it is a place, a number or a plus code', () => {
  const base = { city: 'Irbid', region: 'Irbid Governorate' };
  assert.equal(prefillFromDeviceAddress({ ...base, name: 'University Street' }).street, 'University Street');
  assert.equal(prefillFromDeviceAddress({ ...base, name: 'Irbid' }).street, '');
  assert.equal(prefillFromDeviceAddress({ ...base, name: 'Irbid Governorate' }).street, '');
  assert.equal(prefillFromDeviceAddress({ ...base, name: '42' }).street, '');
  assert.equal(prefillFromDeviceAddress({ ...base, name: '8GCHVC9H+2X' }).street, '');
  assert.equal(prefillFromDeviceAddress({ ...base, name: '8GCHVC9H+2X Irbid' }).street, '');
});

test('a real street wins over name', () => {
  const prefill = prefillFromDeviceAddress({ street: 'Hashmi St', name: 'Some Cafe', city: 'Irbid', region: 'Irbid Governorate' });
  assert.equal(prefill.street, 'Hashmi St');
});

test('the formatted address is used when the separate fields are empty', () => {
  const prefill = prefillFromDeviceAddress({ formattedAddress: 'Al Jubeiha, Amman, Jordan' });
  assert.equal(prefill.governorate, 'amman');
  assert.equal(prefill.area, 'Al Jubeiha');
});

test('plus codes, the country and postal codes in the formatted address are skipped', () => {
  const prefill = prefillFromDeviceAddress({
    formattedAddress: '8GCHVC9H+2X, Tla Al Ali, Amman 11953, Jordan', postalCode: '11953',
  });
  assert.equal(prefill.governorate, 'amman');
  assert.equal(prefill.area, 'Tla Al Ali');
});

test('an area is never just the governorate again', () => {
  assert.equal(prefillFromDeviceAddress({ city: 'Amman', region: 'Amman Governorate' }).area, '');
  assert.equal(prefillFromDeviceAddress({ city: 'Irbid', region: 'Irbid Governorate' }).area, '');
});

test('subregion is used for the area when there is no district, and is not mistaken for the governorate', () => {
  const prefill = prefillFromDeviceAddress({ subregion: 'Salt District', region: 'Balqa Governorate' });
  assert.equal(prefill.governorate, 'balqa');
  assert.equal(prefill.area, 'Salt District');
});

test('nothing usable gives empty strings, and null or undefined are fine', () => {
  const empty = { governorate: '', area: '', street: '' };
  assert.deepEqual(prefillFromDeviceAddress(null), empty);
  assert.deepEqual(prefillFromDeviceAddress(undefined), empty);
  assert.deepEqual(prefillFromDeviceAddress({}), empty);
  assert.deepEqual(prefillFromDeviceAddress({ country: 'Jordan', name: 'Jordan' }), empty);
});

// ── planning a prefill (ask before overwriting) ───────────────────────────

const typed = { governorate: false, area: true, street: true };

test('an empty form takes everything the geocoder found', () => {
  const plan = planPrefill(
    { governorate: '', area: '', street: '' }, { governorate: false, area: false, street: false },
    { governorate: 'balqa', area: 'As-Salt', street: '' },
  );
  assert.deepEqual(plan, { fill: { governorate: 'balqa', area: 'As-Salt' }, conflicts: [] });
});

test('fields still holding an earlier suggestion are refreshed without asking', () => {
  const plan = planPrefill(
    { governorate: 'balqa', area: 'Old Area', street: '' }, { governorate: false, area: false, street: false },
    { governorate: 'amman', area: 'Abdoun', street: 'Wasfi Al Tal St' },
  );
  assert.deepEqual(plan.fill, { governorate: 'amman', area: 'Abdoun', street: 'Wasfi Al Tal St' });
  assert.deepEqual(plan.conflicts, []);
});

test('fields the merchant edited are conflicts when the suggestion differs', () => {
  const plan = planPrefill(
    { governorate: 'balqa', area: 'My Neighbourhood', street: 'My Street' }, typed,
    { governorate: 'balqa', area: 'Abdoun', street: 'Wasfi Al Tal St' },
  );
  assert.deepEqual(plan.fill, {});
  assert.deepEqual(plan.conflicts, ['area', 'street']);
});

test('an edited field that already matches the suggestion is no conflict', () => {
  const plan = planPrefill(
    { governorate: 'balqa', area: 'abdoun', street: '' }, typed,
    { governorate: 'balqa', area: 'Abdoun', street: '' },
  );
  assert.deepEqual(plan, { fill: {}, conflicts: [] });
});

test('an empty suggestion never overwrites anything', () => {
  const plan = planPrefill(
    { governorate: 'balqa', area: 'My Neighbourhood', street: 'My Street' }, typed,
    { governorate: '', area: '', street: '' },
  );
  assert.deepEqual(plan, { fill: {}, conflicts: [] });
});

test('an edited field the merchant left empty is filled, not a conflict', () => {
  const plan = planPrefill(
    { governorate: '', area: '', street: '' }, { governorate: true, area: true, street: true },
    { governorate: 'balqa', area: 'As-Salt', street: '' },
  );
  assert.deepEqual(plan.fill, { governorate: 'balqa', area: 'As-Salt' });
});

test('skipGovernorate leaves the governorate alone (a store whose governorate is fixed)', () => {
  const plan = planPrefill(
    { governorate: 'balqa', area: '', street: '' }, { governorate: false, area: false, street: false },
    { governorate: 'amman', area: 'Abdoun', street: '' }, { skipGovernorate: true },
  );
  assert.deepEqual(plan.fill, { area: 'Abdoun' });
});

test('applyPlan keeps edited fields unless the merchant agrees to replace them', () => {
  const current = { governorate: 'balqa', area: 'My Neighbourhood', street: '' };
  const prefill = { governorate: 'balqa', area: 'Abdoun', street: 'Wasfi Al Tal St' };
  const plan = planPrefill(current, typed, prefill);
  assert.deepEqual(plan.conflicts, ['area']);
  assert.deepEqual(applyPlan(current, plan, prefill, false), { governorate: 'balqa', area: 'My Neighbourhood', street: 'Wasfi Al Tal St' });
  assert.deepEqual(applyPlan(current, plan, prefill, true), { governorate: 'balqa', area: 'Abdoun', street: 'Wasfi Al Tal St' });
});

// ── pins ──────────────────────────────────────────────────────────────────

test('places in Jordan are inside the box, other places and bad numbers are not', () => {
  for (const [lat, lng] of [[31.95, 35.91], [32.04, 35.73], [32.55, 35.85], [29.53, 35.01], [32.35, 38.2]]) {
    assert.ok(isInsideJordan(lat, lng), `${lat},${lng}`);
  }
  for (const [lat, lng] of [[0, 0], [30.04, 31.23], [24.71, 46.67], [48.85, 2.35], [35.91, 31.95], [NaN, 35.9], [31.9, Infinity]]) {
    assert.ok(!isInsideJordan(lat, lng), `${lat},${lng}`);
  }
  assert.ok(isInsideJordan(JORDAN_BOUNDS.minLat, JORDAN_BOUNDS.minLng));
  assert.ok(isInsideJordan(JORDAN_BOUNDS.maxLat, JORDAN_BOUNDS.maxLng));
  assert.ok(!isInsideJordan(JORDAN_BOUNDS.maxLat + 0.001, 35.9));
  assert.ok(isInsideJordan(JORDAN_CENTER.latitude, JORDAN_CENTER.longitude));
});

test('distanceMeters is a great-circle distance', () => {
  assert.equal(distanceMeters(32.04, 35.73, 32.04, 35.73), 0);
  assert.ok(Math.abs(distanceMeters(31, 35, 32, 35) - 111194.9) < 1);
  assert.ok(Math.abs(distanceMeters(31.95, 35.91, 32.04, 35.73) - distanceMeters(32.04, 35.73, 31.95, 35.91)) < 1e-6);
  const amman = distanceMeters(31.95, 35.91, 32.04, 35.73);
  assert.ok(amman > 19000 && amman < 23000, String(amman));
});

test('the limits are the ones the server uses', () => {
  assert.equal(FREE_MOVE_LIMIT_M, 200);
  assert.equal(GPS_WARN_ACCURACY_M, 50);
  assert.deepEqual([AREA_MAX_LENGTH, STREET_MAX_LENGTH, LANDMARK_MAX_LENGTH], [120, 160, 200]);
});

test('moveStatus allows a move up to 200 m and refuses more', () => {
  const saved = { latitude: 32.04, longitude: 35.73 };
  const north = (m) => ({ latitude: saved.latitude + m / 111194.9, longitude: saved.longitude });
  assert.equal(moveStatus(saved, saved).allowed, true);
  assert.equal(moveStatus(saved, north(150)).allowed, true);
  assert.ok(Math.abs(moveStatus(saved, north(150)).meters - 150) < 1);
  assert.equal(moveStatus(saved, north(199)).allowed, true);
  assert.equal(moveStatus(saved, north(201)).allowed, false);
});

test('a GPS fix worse than 50 m gets a warning; a missing one does not', () => {
  assert.equal(needsAccuracyWarning(51), true);
  assert.equal(needsAccuracyWarning(500), true);
  assert.equal(needsAccuracyWarning(50), false);
  assert.equal(needsAccuracyWarning(8), false);
  assert.equal(needsAccuracyWarning(null), false);
  assert.equal(needsAccuracyWarning(undefined), false);
  assert.equal(needsAccuracyWarning(NaN), false);
});

// ── the form value ────────────────────────────────────────────────────────

const complete = { ...EMPTY_LOCATION, latitude: 32.04, longitude: 35.73, governorate: 'balqa', area: ' As-Salt ' };

test('an empty form is missing the pin, the governorate and the area', () => {
  assert.deepEqual(locationProblems(EMPTY_LOCATION), ['pin_missing', 'governorate_missing', 'area_missing']);
  assert.equal(toLocationPayload(EMPTY_LOCATION), null);
});

test('a pin outside Jordan, an unknown governorate and a blank area are reported', () => {
  assert.deepEqual(locationProblems({ ...complete, latitude: 0, longitude: 0 }), ['pin_outside_jordan']);
  assert.deepEqual(locationProblems({ ...complete, governorate: 'texas' }), ['governorate_missing']);
  assert.deepEqual(locationProblems({ ...complete, area: '   ' }), ['area_missing']);
  assert.deepEqual(locationProblems(complete), []);
});

test('the payload is trimmed and empty street and landmark become null', () => {
  assert.deepEqual(toLocationPayload(complete), {
    latitude: 32.04, longitude: 35.73, governorate: 'balqa', area: 'As-Salt', street: null, landmark: null,
  });
  assert.deepEqual(toLocationPayload({ ...complete, street: ' شارع   الجامعة ', landmark: ' مقابل البنك ' }), {
    latitude: 32.04, longitude: 35.73, governorate: 'balqa', area: 'As-Salt', street: 'شارع الجامعة', landmark: 'مقابل البنك',
  });
});

test('locationFromMarket reads a store the server has, with or without structure', () => {
  assert.deepEqual(
    locationFromMarket({ latitude: 32.04, longitude: 35.73, governorate: 'balqa', area: 'As-Salt', street: null, landmark: 'x' }),
    { latitude: 32.04, longitude: 35.73, governorate: 'balqa', area: 'As-Salt', street: '', landmark: 'x' },
  );
  assert.deepEqual(
    locationFromMarket({ latitude: 31.95, longitude: 35.91 }),
    { latitude: 31.95, longitude: 35.91, governorate: '', area: '', street: '', landmark: '' },
  );
});

// ── what customers see ────────────────────────────────────────────────────

test('the address line is street, area, governorate in the app language', () => {
  const parts = { governorate: 'balqa', area: 'المدينة الرياضية', street: 'شارع الجامعة', landmark: 'مقابل البنك' };
  assert.deepEqual(formatStoreAddress(parts, 'ignored', true), {
    line: 'شارع الجامعة، المدينة الرياضية، البلقاء', landmark: 'مقابل البنك',
  });
  assert.deepEqual(formatStoreAddress({ ...parts, area: 'Sport City', street: 'University St' }, 'ignored', false), {
    line: 'University St, Sport City, Balqa', landmark: 'مقابل البنك',
  });
});

test('missing parts are skipped', () => {
  assert.equal(formatStoreAddress({ governorate: 'amman', area: 'عبدون' }, '', true).line, 'عبدون، عمان');
  assert.equal(formatStoreAddress({ governorate: 'amman' }, 'x', false).line, 'Amman');
  assert.equal(formatStoreAddress({ governorate: 'amman', area: ' Abdoun ', street: '  ' }, '', false).line, 'Abdoun, Amman');
  assert.equal(formatStoreAddress({ area: 'Abdoun', landmark: null }, '', false).landmark, '');
});

test('a store without parts shows the plain address text', () => {
  assert.deepEqual(formatStoreAddress(null, 'Old Town, As-Salt, Balqa, Jordan', true), {
    line: 'Old Town, As-Salt, Balqa, Jordan', landmark: '',
  });
  assert.deepEqual(formatStoreAddress(undefined, undefined, false), { line: '', landmark: '' });
  assert.equal(formatStoreAddress({}, ' text ', false).line, 'text');
  assert.equal(formatStoreAddress({ governorate: 'nowhere' }, 'text', false).line, 'text');
});
