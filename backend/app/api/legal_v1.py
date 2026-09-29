"""
Public legal pages (Google Play requires a public privacy policy URL):
  GET /privacy — privacy policy (Arabic + English)
  GET /terms   — terms of service (Arabic + English)
Content comes from app/legal_content.py, the same text the mobile app shows.
"""

import re
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.legal_content import PRIVACY_AR, PRIVACY_EN, TERMS_AR, TERMS_EN

router = APIRouter(tags=["Legal"])

_LINK = re.compile(r"(https://[^\s,]+[^\s,.])|([\w.+-]+@[\w-]+\.[\w.]+)")

_CSS = """body{font-family:system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;max-width:720px;margin:40px auto;
padding:0 20px;line-height:1.75;color:#1a1a2e;background:#fff}h1{font-size:1.5rem;margin-bottom:0}
h2{font-size:1.1rem;margin-top:1.6em}.updated{color:#666;font-size:.9rem;margin-top:.2em}
section{margin-bottom:56px}ul{padding-inline-start:1.3em}a{color:#b8860b}
nav{font-size:.9rem;margin-bottom:24px}.en{direction:ltr;text-align:left}
@media (prefers-color-scheme:dark){body{background:#121212;color:#e8e8e8}.updated{color:#aaa}}"""


def _linkify(text: str) -> str:
    def repl(m: re.Match) -> str:
        url, mail = m.group(1), m.group(2)
        return f'<a href="{url}">{url}</a>' if url else f'<a href="mailto:{mail}">{mail}</a>'
    return _LINK.sub(repl, escape(text))


def _section(doc: dict, lang: str) -> str:
    out = [f'<section lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"'
           + (' class="en"' if lang == "en" else "") + ">",
           f"<h1>{escape(doc['title'])}</h1>",
           f'<p class="updated">{escape(doc["updated"])}</p>',
           f"<p>{_linkify(doc['intro'])}</p>"]
    for heading, paras in doc["sections"]:
        out.append(f"<h2>{escape(heading)}</h2>")
        items = []
        for p in paras:
            if p.startswith("- "):
                items.append(f"<li>{_linkify(p[2:])}</li>")
                continue
            if items:
                out.append("<ul>" + "".join(items) + "</ul>")
                items = []
            out.append(f"<p>{_linkify(p)}</p>")
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
    out.append("</section>")
    return "\n".join(out)


def _page(title: str, ar: dict, en: dict) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{_CSS}</style></head><body>
<nav><a href="#en">English</a></nav>
{_section(ar, "ar")}
<div id="en"></div>
{_section(en, "en")}
</body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy():
    return _page("سياسة الخصوصية — Lamba Privacy Policy", PRIVACY_AR, PRIVACY_EN)


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service():
    return _page("شروط الخدمة — Lamba Terms of Service", TERMS_AR, TERMS_EN)
