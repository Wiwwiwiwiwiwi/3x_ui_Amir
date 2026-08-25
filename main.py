import os
import asyncio
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ─── تنظیمات ────────────────────────────────────────────────────────
RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"
REPO = "Wiwwiwiwiwiwi/3XUI_AMIR"
SERVICES = ["NL", "US_V", "US_C", "SG", "NL_MT"]

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot")


# ─── ابزار کمکی ─────────────────────────────────────────────────────
def gql(token, query, variables=None):
    """ارسال درخواست GraphQL به Railway"""
    r = requests.post(
        RAILWAY_GQL,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ─── /start ──────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "🤖 *ربات دیپلوی 3X-UI روی Railway*\n\n"
        "توکن API ریل‌وی خود را ارسال کنید:\n"
        "https://railway.app/account/tokens",
        parse_mode="Markdown",
    )
    ctx.user_data["step"] = "token"


# ─── دریافت متن ─────────────────────────────────────────────────────
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("step")
    if step != "token":
        return

    token = update.message.text.strip()
    await update.message.reply_text("⏳ بررسی توکن...")

    # اعتبارسنجی توکن
    try:
        res = gql(token, "{ me { id email } }")
    except Exception as e:
        await update.message.reply_text(f"❌ خطای شبکه: {e}")
        return

    me = (res.get("data") or {}).get("me")
    if not me:
        await update.message.reply_text(
            "❌ توکن نامعتبر است. دوباره امتحان کنید."
        )
        return

    ctx.user_data["token"] = token
    ctx.user_data["step"] = "confirm"

    # نمایش خلاصه و دکمه تایید
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ بله، دیپلوی کن", callback_data="go")],
            [InlineKeyboardButton("❌ لغو", callback_data="no")],
        ]
    )
    names = "\n".join(f"  • `{s}`" for s in SERVICES)
    await update.message.reply_text(
        f"✅ *توکن تایید شد*\n\n"
        f"👤 کاربر: {me.get('email', '—')}\n"
        f"📦 پروژه جدید: `3XUI-AMIR`\n"
        f"🔗 ریپو: `{REPO}`\n"
        f"🏷️ سرویس‌ها:\n{names}\n\n"
        f"شروع دیپلوی؟",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ─── دکمه‌ها ─────────────────────────────────────────────────────────
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "no":
        ctx.user_data.clear()
        await q.edit_message_text("لغو شد. برای شروع مجدد /start")
        return

    if q.data == "go":
        await q.edit_message_text("🚀 شروع فرآیند دیپلوی...")
        await run_deploy(q.message, ctx)


# ─── منطق دیپلوی ────────────────────────────────────────────────────
async def run_deploy(msg, ctx: ContextTypes.DEFAULT_TYPE):
    token = ctx.user_data["token"]

    # ── ۱. ساخت پروژه ──
    await msg.reply_text("📦 *مرحله ۱:* ساخت پروژه...", parse_mode="Markdown")

    res = gql(
        token,
        """
        mutation ($i: ProjectCreateInput!) {
            projectCreate(input: $i) { id }
        }
        """,
        {"i": {"name": "3XUI-AMIR"}},
    )

    if "errors" in res:
        await msg.reply_text(
            f"❌ خطا در ساخت پروژه:\n`{res['errors'][0]['message']}`",
            parse_mode="Markdown",
        )
        return

    pid = res["data"]["projectCreate"]["id"]
    await msg.reply_text(
        f"✅ پروژه ساخته شد\n🆔 `{pid}`", parse_mode="Markdown"
    )

    # ── ۲. ساخت ۵ سرویس ──
    await msg.reply_text(
        "🏷️ *مرحله ۲:* ساخت سرویس‌ها و دیپلوی...", parse_mode="Markdown"
    )

    ok_count = 0
    for i, name in enumerate(SERVICES, 1):
        await msg.reply_text(
            f"⏳ *({i}/{len(SERVICES)})* دیپلوی `{name}` ...",
            parse_mode="Markdown",
        )

        res = gql(
            token,
            """
            mutation ($i: ServiceCreateInput!) {
                serviceCreate(input: $i) { id name }
            }
            """,
            {
                "i": {
                    "name": name,
                    "projectId": pid,
                    "source": {"repo": REPO},
                }
            },
        )

        if "errors" in res:
            err_msg = res["errors"][0]["message"]
            await msg.reply_text(
                f"❌ `{name}` — خطا: {err_msg}", parse_mode="Markdown"
            )
        else:
            sid = res["data"]["serviceCreate"]["id"]
            await msg.reply_text(
                f"✅ `{name}` دیپلوی شد\n🆔 `{sid}`", parse_mode="Markdown"
            )
            ok_count += 1

        # تاخیر کوتاه برای جلوگیری از rate limit
        await asyncio.sleep(2)

    # ── خلاصه نهایی ──
    fail_count = len(SERVICES) - ok_count
    await msg.reply_text(
        f"🏁 *دیپلوی تمام شد!*\n\n"
        f"✅ موفق: {ok_count}\n"
        f"❌ ناموفق: {fail_count}\n\n"
        f"🔗 [مشاهده پروژه در Railway]"
        f"(https://railway.app/project/{pid})\n\n"
        f"⚠️ بعد از دیپلوی، به تنظیمات هر سرویس بروید و "
        f"Domain بسازید تا آدرس پنل 3X-UI را دریافت کنید.",
        parse_mode="Markdown",
    )
    ctx.user_data.clear()


# ─── اجرای اصلی ─────────────────────────────────────────────────────
def main():
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        log.error("متغیر BOT_TOKEN تنظیم نشده!")
        raise SystemExit(1)

    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("ربات شروع به کار کرد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()