/**
 * Store addresses in Jordan, without React Native: the governorates, what the phone's own geocoder
 * tells us (turned into an editable prefill), the pin rules, and the address text customers see.
 * Kept free of imports so `node --test` can run it (see mobile/tests/jordanAddress.test.mjs).
 *
 * Erasable TypeScript only (no enums, namespaces or parameter properties): Node strips the types and
 * runs this file as it is.
 *
 * The governorate keys, names, the bounding box and the limits mirror backend/app/jordan_geo.py and
 * backend/app/services/market_location.py; backend/tests/test_jordan_geo.py compares them.
 */

// ── Governorates ───────────────────────────────────────────────────────────

export interface Governorate {
  key: string;
  ar: string;
  en: string;
  /** Other spellings of the governorate's own name (what a geocoder may answer). */
  aliases: string[];
  /** Main towns that tell the governorate when the geocoder gives no region. */
  cities: string[];
}

export const GOVERNORATES: Governorate[] = [
  { key: 'amman', ar: 'عمان', en: 'Amman', aliases: ['Capital', 'العاصمة'], cities: [] },
  { key: 'irbid', ar: 'إربد', en: 'Irbid', aliases: ['اربد'], cities: [] },
  { key: 'zarqa', ar: 'الزرقاء', en: 'Zarqa', aliases: ['Az Zarqa', 'Zarka'], cities: [] },
  { key: 'balqa', ar: 'البلقاء', en: 'Balqa', aliases: ['Al Balqa', 'البلقا'], cities: ['Salt', 'As Salt', 'السلط'] },
  { key: 'madaba', ar: 'مأدبا', en: 'Madaba', aliases: ['Madeba', 'مادبا'], cities: [] },
  { key: 'karak', ar: 'الكرك', en: 'Karak', aliases: ['Kerak', 'Al Karak'], cities: [] },
  { key: 'tafilah', ar: 'الطفيلة', en: 'Tafilah', aliases: ['Tafila', 'Tafileh', 'At Tafilah'], cities: [] },
  { key: 'maan', ar: 'معان', en: "Ma'an", aliases: ['Maan'], cities: [] },
  { key: 'aqaba', ar: 'العقبة', en: 'Aqaba', aliases: ['Aqabah', 'Al Aqabah'], cities: [] },
  { key: 'mafraq', ar: 'المفرق', en: 'Mafraq', aliases: ['Al Mafraq'], cities: [] },
  { key: 'jerash', ar: 'جرش', en: 'Jerash', aliases: ['Jarash'], cities: [] },
  { key: 'ajloun', ar: 'عجلون', en: 'Ajloun', aliases: ['Ajlun', 'Ajlon'], cities: [] },
];

export function governorateName(key: string | null | undefined, isAr: boolean): string {
  const g = GOVERNORATES.find((item) => item.key === key);
  return g ? (isAr ? g.ar : g.en) : '';
}

// ── Pins ───────────────────────────────────────────────────────────────────

/** A rough box around Jordan: catches swapped coordinates and (0, 0), it is not a border. */
export const JORDAN_BOUNDS = { minLat: 29.0, maxLat: 33.5, minLng: 34.8, maxLng: 39.4 };
/** Where maps open when there is no position yet (Amman). */
export const JORDAN_CENTER = { latitude: 31.95, longitude: 35.91 };

/** An existing store's pin may be moved this far in the app; more goes through support. */
export const FREE_MOVE_LIMIT_M = 200;
/** A GPS fix less accurate than this (metres) gets a warning. */
export const GPS_WARN_ACCURACY_M = 50;

export const AREA_MAX_LENGTH = 120;
export const STREET_MAX_LENGTH = 160;
export const LANDMARK_MAX_LENGTH = 200;

export function isInsideJordan(latitude: number, longitude: number): boolean {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return false;
  return (
    latitude >= JORDAN_BOUNDS.minLat && latitude <= JORDAN_BOUNDS.maxLat &&
    longitude >= JORDAN_BOUNDS.minLng && longitude <= JORDAN_BOUNDS.maxLng
  );
}

const EARTH_RADIUS_M = 6371008.8;

/** Great-circle distance in metres (haversine); the server uses the same formula. */
export function distanceMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const rad = Math.PI / 180;
  const dPhi = (lat2 - lat1) * rad;
  const dLambda = (lng2 - lng1) * rad;
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

export function needsAccuracyWarning(accuracyMeters: number | null | undefined): boolean {
  return typeof accuracyMeters === 'number' && Number.isFinite(accuracyMeters) && accuracyMeters > GPS_WARN_ACCURACY_M;
}

export interface Pin {
  latitude: number;
  longitude: number;
}

/** How far `to` is from the store's saved pin, and whether the app may move it there. */
export function moveStatus(saved: Pin, to: Pin): { meters: number; allowed: boolean } {
  const meters = distanceMeters(saved.latitude, saved.longitude, to.latitude, to.longitude);
  return { meters, allowed: meters <= FREE_MOVE_LIMIT_M };
}

// ── Names: matching what a geocoder says against the governorates ──────────

const ARABIC_FIRST = String.fromCharCode(0x0621);
const ARABIC_LAST = String.fromCharCode(0x064a);
const NOT_A_LETTER = new RegExp('[^a-z0-9' + ARABIC_FIRST + '-' + ARABIC_LAST + ']', 'g');
const MARKS = new RegExp('[' + String.fromCharCode(0x064b) + '-' + String.fromCharCode(0x065f) + String.fromCharCode(0x0670) + String.fromCharCode(0x0640) + ']', 'g');
const ALEF_FORMS = new RegExp('[' + String.fromCharCode(0x0623, 0x0625, 0x0622, 0x0671) + ']', 'g');
const ALEF_MAQSURA = new RegExp(String.fromCharCode(0x0649), 'g');
const TEH_MARBUTA = new RegExp(String.fromCharCode(0x0629), 'g');
const ARABIC_ARTICLE = String.fromCharCode(0x0627, 0x0644); // "ال"
// Words a geocoder adds around a name ("Balqa Governorate", "محافظة البلقاء", "Salt District").
const FILLER_WORDS = ['governorate', 'province', 'district', 'محافظة', 'لواء', 'قضاء'].map(simpleFold);

function simpleFold(text: string): string {
  return text
    .toLowerCase()
    .replace(MARKS, '')
    .replace(ALEF_FORMS, String.fromCharCode(0x0627))
    .replace(ALEF_MAQSURA, String.fromCharCode(0x064a))
    .replace(TEH_MARBUTA, String.fromCharCode(0x0647));
}

/** Folds spelling variants together: case, Arabic marks and alef/teh forms, spaces and punctuation, "Al"/"ال". */
export function normalizeName(text: string | null | undefined): string {
  if (!text) return '';
  // Remove filler words while the words are still separate, then drop everything that is not a letter.
  let folded = simpleFold(text).replace(/[-_'’`.]/g, ' ');
  folded = folded
    .split(/\s+/)
    .filter((word) => word && !FILLER_WORDS.includes(word))
    .join('');
  folded = folded.replace(NOT_A_LETTER, '');
  if (folded.startsWith(ARABIC_ARTICLE) && folded.length > 4) folded = folded.slice(2);
  else if (folded.startsWith('al') && folded.length > 4) folded = folded.slice(2);
  return folded;
}

function namesOf(g: Governorate): string[] {
  return [g.key, g.ar, g.en, ...g.aliases].map(normalizeName);
}

/** The governorate key a list of geocoder strings points to (own names first, then main towns), or null. */
export function matchGovernorate(candidates: Array<string | null | undefined>): string | null {
  const wanted = candidates.map(normalizeName).filter(Boolean);
  for (const name of wanted) {
    const hit = GOVERNORATES.find((g) => namesOf(g).includes(name));
    if (hit) return hit.key;
  }
  for (const name of wanted) {
    const hit = GOVERNORATES.find((g) => g.cities.map(normalizeName).includes(name));
    if (hit) return hit.key;
  }
  return null;
}

function isGovernorateName(text: string | null | undefined): boolean {
  const name = normalizeName(text);
  return !!name && GOVERNORATES.some((g) => namesOf(g).includes(name));
}

// ── The phone's geocoder as an editable prefill ────────────────────────────

/** The fields of expo-location's LocationGeocodedAddress that are read. */
export interface DeviceAddress {
  city?: string | null;
  district?: string | null;
  subregion?: string | null;
  region?: string | null;
  street?: string | null;
  streetNumber?: string | null;
  name?: string | null;
  formattedAddress?: string | null;
  postalCode?: string | null;
  country?: string | null;
}

/** '' means the geocoder had nothing usable for that field. */
export interface AddressPrefill {
  governorate: string;
  area: string;
  street: string;
}

export const EMPTY_PREFILL: AddressPrefill = { governorate: '', area: '', street: '' };

const PLUS_CODE = /^[0-9A-Z]{4,8}\+[0-9A-Z]{2,}(\s|$)/i;
const COUNTRY_NAMES = ['jordan', 'الاردن', 'hashemitekingdomofjordan', 'المملكةالاردنيةالهاشمية'].map(normalizeName);

function clean(text: string | null | undefined): string {
  return (text ?? '').replace(/\s+/g, ' ').trim();
}

/** Plus codes, numbers, postal codes and the country are not part of an address line. */
function isNoise(text: string, postalCode?: string | null): boolean {
  if (!text) return true;
  if (PLUS_CODE.test(text)) return true;
  if (/^[\d\s\-/.]+$/.test(text)) return true;
  if (postalCode && clean(postalCode) === text) return true;
  return COUNTRY_NAMES.includes(normalizeName(text));
}

function sameName(a: string, b: string): boolean {
  const na = normalizeName(a);
  return !!na && na === normalizeName(b);
}

/**
 * Turn what the device geocoder returned into governorate / area / street suggestions.
 * Uses every field it gives: region, subregion, city, district, street, name and the formatted
 * address. Anything it cannot place stays ''. The merchant always sees and may change the result.
 */
export function prefillFromDeviceAddress(geo: DeviceAddress | null | undefined): AddressPrefill {
  if (!geo) return { ...EMPTY_PREFILL };
  // "Amman 11953" is a town with its postal code: drop 4 to 6 digit numbers before judging a token.
  const tokens = clean(geo.formattedAddress)
    .split(/[,،]/)
    .map((token) => clean(token.replace(/\b\d{4,6}\b/g, ' ')))
    .filter((token) => !isNoise(token, geo.postalCode));

  const governorate =
    matchGovernorate([geo.region, geo.subregion, geo.city, ...tokens]) ?? '';

  const place = [geo.district, geo.subregion, geo.city].map(clean);
  const unusable = (text: string) => !text || isNoise(text, geo.postalCode);

  let street = clean(geo.street);
  if (unusable(street)) {
    const name = clean(geo.name);
    const isPlaceName = [geo.city, geo.district, geo.subregion, geo.region].some((p) => sameName(name, clean(p)));
    street = unusable(name) || isPlaceName || isGovernorateName(name) ? '' : name;
  }

  const areaCandidates = [...place, ...tokens];
  const area =
    areaCandidates.find(
      (text) => !unusable(text) && !isGovernorateName(text) && !sameName(text, street),
    ) ?? '';

  return { governorate, area, street };
}

export type PrefillField = 'governorate' | 'area' | 'street';

export interface PrefillPlan {
  /** Values to put in right away: the field is empty or the merchant has not touched it. */
  fill: Partial<AddressPrefill>;
  /** Fields the merchant edited that the geocoder disagrees with: ask before replacing them. */
  conflicts: PrefillField[];
}

/**
 * What a new prefill may do to the form. Never writes an empty suggestion, never overwrites a field the
 * merchant edited without asking (`conflicts`), refreshes fields that still hold an earlier suggestion.
 */
export function planPrefill(
  current: AddressPrefill,
  edited: Record<PrefillField, boolean>,
  prefill: AddressPrefill,
  options?: { skipGovernorate?: boolean },
): PrefillPlan {
  const fill: Partial<AddressPrefill> = {};
  const conflicts: PrefillField[] = [];
  const fields: PrefillField[] = options?.skipGovernorate ? ['area', 'street'] : ['governorate', 'area', 'street'];
  for (const field of fields) {
    const suggestion = prefill[field];
    if (!suggestion) continue;
    const now = current[field];
    if (now === suggestion) continue;
    if (!now || !edited[field]) fill[field] = suggestion;
    else if (!sameName(now, suggestion)) conflicts.push(field);
  }
  return { fill, conflicts };
}

/** The values after applying a plan; with `replaceConflicts` the merchant's edited fields are replaced too. */
export function applyPlan(
  current: AddressPrefill,
  plan: PrefillPlan,
  prefill: AddressPrefill,
  replaceConflicts: boolean,
): AddressPrefill {
  const next = { ...current, ...plan.fill } as AddressPrefill;
  if (replaceConflicts) for (const field of plan.conflicts) next[field] = prefill[field];
  return next;
}

// ── The form value, its checks and the request body ────────────────────────

export interface StoreLocationValue {
  latitude: number | null;
  longitude: number | null;
  governorate: string;
  area: string;
  street: string;
  landmark: string;
}

export const EMPTY_LOCATION: StoreLocationValue = {
  latitude: null,
  longitude: null,
  governorate: '',
  area: '',
  street: '',
  landmark: '',
};

export type LocationProblem = 'pin_missing' | 'pin_outside_jordan' | 'governorate_missing' | 'area_missing';

/** What is still wrong with a location form, in the order the form shows it. */
export function locationProblems(value: StoreLocationValue): LocationProblem[] {
  const problems: LocationProblem[] = [];
  if (value.latitude === null || value.longitude === null) problems.push('pin_missing');
  else if (!isInsideJordan(value.latitude, value.longitude)) problems.push('pin_outside_jordan');
  if (!GOVERNORATES.some((g) => g.key === value.governorate)) problems.push('governorate_missing');
  if (!clean(value.area)) problems.push('area_missing');
  return problems;
}

export interface StoreLocationPayload {
  latitude: number;
  longitude: number;
  governorate: string;
  area: string;
  street: string | null;
  landmark: string | null;
}

/** The request body for POST /market and PUT /market/location, or null while the form is incomplete. */
export function toLocationPayload(value: StoreLocationValue): StoreLocationPayload | null {
  if (locationProblems(value).length > 0) return null;
  return {
    latitude: value.latitude as number,
    longitude: value.longitude as number,
    governorate: value.governorate,
    area: clean(value.area),
    street: clean(value.street) || null,
    landmark: clean(value.landmark) || null,
  };
}

/** The form value for a store the server already has. */
export function locationFromMarket(market: {
  latitude: number;
  longitude: number;
  governorate?: string | null;
  area?: string | null;
  street?: string | null;
  landmark?: string | null;
}): StoreLocationValue {
  return {
    latitude: market.latitude,
    longitude: market.longitude,
    governorate: market.governorate ?? '',
    area: market.area ?? '',
    street: market.street ?? '',
    landmark: market.landmark ?? '',
  };
}

// ── What customers see ─────────────────────────────────────────────────────

export interface AddressParts {
  governorate?: string | null;
  area?: string | null;
  street?: string | null;
  landmark?: string | null;
}

/**
 * The address line (street, area, governorate in the app's language) and the landmark, from the
 * structured parts. A store without parts shows the plain `address` text the server kept.
 */
export function formatStoreAddress(
  parts: AddressParts | null | undefined,
  fallback: string | null | undefined,
  isAr: boolean,
): { line: string; landmark: string } {
  const pieces = [clean(parts?.street), clean(parts?.area), governorateName(parts?.governorate, isAr)].filter(Boolean);
  return {
    line: pieces.length > 0 ? pieces.join(isAr ? '، ' : ', ') : clean(fallback),
    landmark: clean(parts?.landmark),
  };
}
