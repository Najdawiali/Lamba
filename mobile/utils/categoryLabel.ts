/**
 * The category name of a product in the app's language.
 *
 * Every API response that describes a product carries `category` (the English name) and, since the merchant
 * API sends them too, `category_name_ar` / `category_name_en`. One rule for all screens: the name in the
 * app's language, else the plain `category`, else `fallback`. A blank string counts as missing.
 *
 * (There used to be a hand-written English-to-Arabic map for this. It covered 7 of the 56 categories.)
 */

type Categorised = {
  category?: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
};

const clean = (value: string | null | undefined): string => (typeof value === 'string' ? value.trim() : '');

export function categoryLabel(item: Categorised | null | undefined, isAr: boolean | undefined, fallback = ''): string {
  if (!item) return fallback;
  const localized = clean(isAr ? item.category_name_ar : item.category_name_en);
  return localized || clean(item.category) || fallback;
}
