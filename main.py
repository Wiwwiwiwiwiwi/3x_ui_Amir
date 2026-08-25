import os
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─── تنظیمات ────────────────────────────────────────────────────────
RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"
REPO = "Wiwwiwiwiwiwi/3XUI_AMIR"
SERVICES = ["NL", "US_V", "US_C", "SG", "NL_MT"]

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot")

router = Router()


# ─── وضعیت‌ها ────────────────────────────────────────────────────────
class DeployState(StatesGroup):
    waiting_token = State()
    confirm = State()


# ─── ابزار کمکی GraphQL ─────────────────────────────────────────────
async def gql(token: str, query: str, variables: dict = None) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            RAILWAY_GQL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            return await resp.json()


# ─── /start ──────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🤖 *ربات دیپلوی 3X-UI روی Railway*\n\n"
        "توکن API ریل‌وی خود را ارسال کنید:\n"
        "https://railway.app/account/tokens",
        parse_mode="Markdown",
    )
    await state.set_state(DeployState.waiting_token)


# ─── دریافت توکن ────────────────────────────────────────────────────
@router.message(DeployState.waiting_token)
async def on_token(message: Message, state: FSMContext):
    token = message.text.strip()
    await message.answer("⏳ بررسی توکن...")

    try:
        res = await gql(token, "{ me { id email } }")
    except Exception as e:
        await message.answer(f"❌ خطای شبکه: {e}")
        return

    me = (res.get("data") or {}).get("me")
    if not me:
        await message.answer("❌ توکن نامعتبر است. دوباره امتحان کنید.")
        return

    await state.update_data(token=token)
    await state.set_state(DeployState.confirm)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ بله، دیپلوی کن", callback_data="go")],
            [InlineKeyboardButton(text="❌ لغو", callback_data="no")],
        ]
    )
    names = "\n".join(f"  • `{s}`" for s in SERVICES)
    await message.answer(
        f"✅ *توکن تایید شد*\n\n"
        f"👤 کاربر: {me.get('email', '—')}\n"
        f"📦 پروژه جدید: `3XUI-AMIR`\n"
        f"🔗 ریپو: `{REPO}`\n"
        f"🏷️ سرویس‌ها:\n{names}\n\n"
        f"شروع دیپلوی؟",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ─── دکمه لغو ───────────────────────────────────────────────────────
@router.callback_query(F.data == "no")
async def on_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("لغو شد. برای شروع مجدد /start")
    await call.answer()


# ─── دکمه شروع دیپلوی ──────────────────────────────────────────────
@router.callback_query(F.data == "go")
async def on_go(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("🚀 شروع فرآیند دیپلوی...")
    await run_deploy(call.message, state)


# ─── منطق دیپلوی ────────────────────────────────────────────────────
async def run_deploy(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data["token"]

    # ── ۱. ساخت پروژه ──
    await message.answer("📦 *مرحله ۱:* ساخت پروژه...", parse_mode="Markdown")

    res = await gql(
        token,
        """
        mutation ($i: ProjectCreateInput!) {
            projectCreate(input: $i) { id }
        }
        """,
        {"i": {"name": "3XUI-AMIR"}},
    )

    if "errors" in res:
        await message.answer(
            f"❌ خطا در ساخت پروژه:\n`{res['errors'][0]['message']}`",
            parse_mode="Markdown",
        )
        await state.clear()
        return

    pid = res["data"]["projectCreate"]["id"]
    await message.answer(
        f"✅ پروژه ساخته شد\n🆔 `{pid}`", parse_mode="Markdown"
    )

    # ── ۲. ساخت ۵ سرویس ──
    await message.answer(
        "🏷️ *مرحله ۲:* ساخت سرویس‌ها و دیپلوی...", parse_mode="Markdown"
    )

    ok_count = 0
    for i, name in enumerate(SERVICES, 1):
        await message.answer(
            f"⏳ *({i}/{len(SERVICES)})* دیپلوی `{name}` ...",
            parse_mode="Markdown",
        )

        res = await gql(
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
            await message.answer(
                f"❌ `{name}` — خطا: {err_msg}", parse_mode="Markdown"
            )
        else:
            sid = res["data"]["serviceCreate"]["id"]
            await message.answer(
                f"✅ `{name}` دیپلوی شد\n🆔 `{sid}`", parse_mode="Markdown"
            )
            ok_count += 1

        await asyncio.sleep(2)

    # ── خلاصه نهایی ──
    fail_count = len(SERVICES) - ok_count
    await message.answer(
        f"🏁 *دیپلوی تمام شد!*\n\n"
        f"✅ موفق: {ok_count}\n"
        f"❌ ناموفق: {fail_count}\n\n"
        f"🔗 https://railway.app/project/{pid}\n\n"
        f"⚠️ بعد از دیپلوی، به تنظیمات هر سرویس بروید و "
        f"Domain بسازید تا آدرس پنل 3X-UI فعال شود.",
        parse_mode="Markdown",
    )
    await state.clear()


# ─── اجرای اصلی ─────────────────────────────────────────────────────
async def main():
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        log.error("متغیر BOT_TOKEN تنظیم نشده!")
        raise SystemExit(1)

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log.info("ربات شروع به کار کرد...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())