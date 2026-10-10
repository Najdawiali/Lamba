/**
 * Why a catalog photo could not be uploaded, as a locale key the screen shows in the app's language.
 *
 * The scanner saves the stock and price first and uploads the photo second, so a failed photo is not a failed
 * save. It used to say only "could not be uploaded". The reason is chosen from the HTTP status instead of the
 * server's text, so it is in the right language whichever backend version is running (the photo endpoint's
 * messages were English-only until they became bilingual).
 *
 * Statuses: POST /api/v1/merchant/items/{id}/photos in backend/app/api/merchant_v1.py.
 */

export const PHOTO_ERROR_KEYS = [
  'scanner.photo_err_too_large',
  'scanner.photo_err_not_image',
  'scanner.photo_err_limit',
  'scanner.photo_err_network',
  'scanner.photo_err_other',
] as const;

export type PhotoErrorKey = (typeof PHOTO_ERROR_KEYS)[number];

export function photoUploadErrorKey(err: unknown): PhotoErrorKey {
  const response = (err as { response?: { status?: number } } | null | undefined)?.response;
  if (!response) return 'scanner.photo_err_network';   // no answer at all: offline, timeout
  switch (response.status) {
    case 413: return 'scanner.photo_err_too_large';
    case 415:
    case 422: return 'scanner.photo_err_not_image';
    case 409: return 'scanner.photo_err_limit';
    default: return 'scanner.photo_err_other';
  }
}
