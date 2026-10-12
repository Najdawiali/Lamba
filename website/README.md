# lambajo.com — public homepage

Static site served by Cloudflare Pages (independent of the API server).

- `index.html`: the Arabic page, the default at `/`. Fully Arabic.
- `en/index.html`: the English page at `/en/` (same design, `lang="en" dir="ltr"`). Fully English.
  Each page has the same sections in the same order (hero, intro, customers and shops, footer). The only text in
  the other language is the language switch, the small tagline under the hero and the other-script line of the
  wordmark (Lamba under لمبة, لمبة under Lamba), which is part of the logo. Both pages have hreflang
  alternates and their own title, description and Open Graph tags. Keep their copy in step.
- `_redirects`: short links `/privacy`, `/terms`, `/account-deletion` to the live pages on api.lambajo.com.
  These are exact paths; nothing here touches `/en` (Cloudflare serves `/en` as a redirect to `/en/`).
- `icon.png`: copy of `mobile/assets/images/lamba-icon.png`.
- `fonts/`: Lalezar (SIL Open Font License, see `fonts/OFL-Lalezar.txt`), self-hosted.

Deploy: Cloudflare dashboard, Workers & Pages, the `lambajo-site` project, upload this folder.
