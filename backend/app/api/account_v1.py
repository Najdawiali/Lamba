"""
Account deletion (Google Play requirement for apps with account creation):
  DELETE /api/v1/account   — in-app deletion for the signed-in user (customer or merchant)
  GET    /account-deletion — public web page explaining how to delete an account

Deleting the user row removes everything tied to it through database delete rules:
the merchant's store(s), stock, offers, POS receipts, ratings, chats and messages,
search history, alerts, and reports. Catalog products the user created stay in the
shared catalog without a link to the account (global_items.created_by -> NULL).
"""

import logging
from html import escape

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Account"])


@router.delete("/api/v1/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id
    # Core DELETE (not session.delete) so the database delete rules do the work,
    # instead of the ORM trying to null out child rows first.
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    logger.info("Account %s deleted by its owner", user_id)


@router.get("/account-deletion", response_class=HTMLResponse, include_in_schema=False)
async def account_deletion_page():
    email = escape(settings.support_email) if settings.support_email else ""
    contact_ar = (f'أو راسلنا على <a href="mailto:{email}">{email}</a> من البريد أو الرقم المسجّل في حسابك، '
                  f'وسنحذف الحساب خلال 7 أيام.') if email else ""
    contact_en = (f'Or email <a href="mailto:{email}">{email}</a> from the email or phone number registered '
                  f'to your account, and we will delete it within 7 days.') if email else ""
    html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>حذف الحساب — Lamba</title>
<style>body{{font-family:system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;max-width:680px;margin:40px auto;padding:0 20px;line-height:1.7;color:#1a1a2e}}
h1{{font-size:1.5rem}}section{{margin-bottom:32px}}.en{{direction:ltr;text-align:left}}</style></head>
<body>
<section>
<h1>حذف حساب لمبة (Lamba)</h1>
<p>افتح التطبيق ← <b>حسابي</b> ← <b>حذف الحساب</b>، ثم أكّد. يُحذف الحساب فوراً. {contact_ar}</p>
<p><b>ما الذي يُحذف:</b> حسابك وبياناتك الشخصية، ومتجرك ومخزونه وعروضه (للتجّار)، ومحادثاتك وتقييماتك وسجلّ بحثك وتنبيهاتك وبلاغاتك.</p>
<p><b>ما الذي يبقى:</b> المنتجات التي أضفتها إلى الكتالوج المشترك تبقى متاحة للمتاجر الأخرى دون أي ارتباط بحسابك. تُحذف النسخ الاحتياطية تلقائياً خلال 7 أيام.</p>
</section>
<section class="en" dir="ltr" lang="en">
<h1>Delete your Lamba account</h1>
<p>Open the app → <b>Profile</b> → <b>Delete account</b>, then confirm. Your account is deleted immediately. {contact_en}</p>
<p><b>Deleted:</b> your account and personal data; your store, its stock and offers (merchants); your chats, ratings, search history, alerts and reports.</p>
<p><b>Kept:</b> products you added to the shared catalog stay available to other stores, with no link to your account. Backups are erased automatically within 7 days.</p>
</section>
</body></html>"""
    return HTMLResponse(html)
