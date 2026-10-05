/**
 * User-facing error text from API failures.
 *
 * Some server messages are bilingual: an Arabic line and an English line separated by a
 * newline. Show only the line in the app's language, instead of both in one alert.
 */

const ARABIC = /[\u0600-\u06FF]/;

export function localizeServerMessage(detail: unknown, isAr: boolean, fallback: string): string {
  if (typeof detail !== 'string' || !detail.trim()) return fallback;
  const lines = detail.split('\n').map(l => l.trim()).filter(Boolean);
  if (lines.length < 2) return detail.trim();
  const arabic = lines.find(l => ARABIC.test(l));
  const english = lines.find(l => !ARABIC.test(l));
  return (isAr ? arabic : english) ?? detail.trim();
}

/** Message for a failed API call: "no connection", the server's message, or a fallback. */
export function messageFromError(
  err: any,
  isAr: boolean,
  text: { network: string; fallback: string },
): string {
  if (!err?.response) return text.network;
  return localizeServerMessage(err.response.data?.detail, isAr, text.fallback);
}
