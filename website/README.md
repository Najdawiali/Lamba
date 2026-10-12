# lambajo.com — public homepage

Static site served by Cloudflare Pages (independent of the API server).

- `index.html`: the Arabic page, the default at `/`. Fully Arabic.
- `en/index.html`: the English page at `/en/` (same design, `lang="en" dir="ltr"`). Fully English.
  Each page has the same sections in the same order (hero, intro, customers and shops, footer). The only
  other-language text is the language switch; the other-script line of the wordmark (Lamba under لمبة, لمبة
  under Lamba) and the small other-language tagline under the hero are pictures (`img/`), so they cannot be
  selected or copied. Both pages have hreflang alternates and their own title, description and Open Graph
  tags. Keep their copy in step.
- `img/`: transparent PNGs (4x) of those four lines, rendered with headless Chrome. `wordmark-en.png` and
  `wordmark-ar.png`: Lalezar, 64 px, line-height 1.1, colour #FFB300 (the Latin one with 0.04em letter-spacing);
  `tagline-en.png`, `tagline-ar.png` and `tagline-ar-narrow.png` (the same Arabic line on two lines, used up to
  520 px wide): the page's body font stack, 16.8 px, line-height 1.8, colour #FFD98A. The strings are
  "Find what you need in the shops near you." and "دوّر على أي غرض، وشوف وين بتلاقيه بالمحلات القريبة منك."
  The pages give the images their accessible text with `role="img"` and `aria-label`. If a line changes,
  render its picture again and keep the `aria-label` in step.
- `_redirects`: short links `/privacy`, `/terms`, `/account-deletion` to the live pages on api.lambajo.com.
  These are exact paths; nothing here touches `/en` (Cloudflare serves `/en` as a redirect to `/en/`).
- `icon.png`: copy of `mobile/assets/images/lamba-icon.png`.
- `fonts/`: Lalezar (SIL Open Font License, see `fonts/OFL-Lalezar.txt`), self-hosted.

Deploy: Cloudflare dashboard, Workers & Pages, the `lambajo-site` project, upload this folder.
