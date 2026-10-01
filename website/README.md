# lambajo.com — public homepage

Static site served by Cloudflare Pages (independent of the API server).

- `index.html`: the page (Arabic first, English section for reviewers).
- `_redirects`: short links `/privacy`, `/terms`, `/account-deletion` to the live pages on api.lambajo.com.
- `icon.png`: copy of `mobile/assets/images/lamba-icon.png`.
- `fonts/`: Lalezar (SIL Open Font License, see `fonts/OFL-Lalezar.txt`), self-hosted.

Deploy: Cloudflare dashboard, Workers & Pages, the `lambajo-site` project, upload this folder.
