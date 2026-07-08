import asyncio
import logging
import os
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID")
CARD_NUMBER = os.getenv("CARD_NUMBER", "-")
CARD_OWNER = os.getenv("CARD_OWNER", "-")
AD_PRICE = os.getenv("AD_PRICE", "10000")

DB_PATH = "ads.db"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ---------- Holatlar (foydalanuvchi bosqichlari) ----------
class AdForm(StatesGroup):
    name = State()
    description = State()
    price = State()
    photo = State()
    receipt = State()


# ---------- Ma'lumotlar bazasi ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                name TEXT,
                description TEXT,
                price TEXT,
                photo_file_id TEXT,
                receipt_file_id TEXT,
                status TEXT DEFAULT 'kutilmoqda',
                created_at TEXT
            )
            """
        )
        await db.commit()


async def save_ad(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO ads (user_id, username, name, description, price, photo_file_id, receipt_file_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'kutilmoqda', ?)
            """,
            (
                data["user_id"],
                data["username"],
                data["name"],
                data["description"],
                data["price"],
                data["photo_file_id"],
                data["receipt_file_id"],
                datetime.now().isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_ad(ad_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ads WHERE id = ?", (ad_id,))
        return await cursor.fetchone()


async def update_ad_status(ad_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ads SET status = ? WHERE id = ?", (status, ad_id))
        await db.commit()


# ---------- Klaviaturalar ----------
def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📢 E'lon joylash")], [KeyboardButton(text="ℹ️ Yordam")]],
        resize_keyboard=True,
    )


def admin_decision_kb(ad_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{ad_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{ad_id}"),
            ]
        ]
    )


# ---------- Foydalanuvchi oqimi ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Bu bot orqali siz o'z mahsulotingiz haqida e'lon joylashtira olasiz.\n"
        f"Har bir e'lon narxi: {AD_PRICE} so'm.\n\n"
        "Boshlash uchun pastdagi tugmani bosing.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "ℹ️ Yordam")
async def help_handler(message: Message):
    await message.answer(
        "Qanday ishlaydi:\n"
        "1. \"E'lon joylash\" tugmasini bosasiz\n"
        "2. Mahsulot nomi, tavsifi, narxi va rasmini yuborasiz\n"
        f"3. {AD_PRICE} so'mni ko'rsatilgan kartaga o'tkazib, chek skrinshotini yuborasiz\n"
        "4. Admin tekshirib tasdiqlaydi\n"
        "5. E'loningiz kanalda chop etiladi ✅"
    )


@router.message(F.text == "📢 E'lon joylash")
async def start_ad(message: Message, state: FSMContext):
    await state.set_state(AdForm.name)
    await message.answer("Mahsulot nomini yozing:", reply_markup=ReplyKeyboardRemove())


@router.message(AdForm.name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdForm.description)
    await message.answer("Mahsulot haqida qisqacha tavsif yozing:")


@router.message(AdForm.description)
async def get_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AdForm.price)
    await message.answer("Mahsulot narxini kiriting (masalan: 150 000 so'm):")


@router.message(AdForm.price)
async def get_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await state.set_state(AdForm.photo)
    await message.answer("Endi mahsulotning rasmini yuboring:")


@router.message(AdForm.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(AdForm.receipt)
    await message.answer(
        f"Rahmat! Endi e'loningizni chop etish uchun {AD_PRICE} so'm to'lov qiling:\n\n"
        f"💳 Karta: {CARD_NUMBER}\n"
        f"👤 Egasi: {CARD_OWNER}\n\n"
        "To'lovni amalga oshirgach, chek skrinshotini shu yerga yuboring."
    )


@router.message(AdForm.photo)
async def photo_invalid(message: Message):
    await message.answer("Iltimos, rasm ko'rinishida yuboring 🖼")


@router.message(AdForm.receipt, F.photo)
async def get_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    ad_data = {
        "user_id": message.from_user.id,
        "username": message.from_user.username or message.from_user.full_name,
        "name": data["name"],
        "description": data["description"],
        "price": data["price"],
        "photo_file_id": data["photo_file_id"],
        "receipt_file_id": message.photo[-1].file_id,
    }
    ad_id = await save_ad(ad_data)
    await state.clear()

    await message.answer(
        "✅ E'loningiz va chekingiz qabul qilindi!\n"
        "Admin tekshirgandan so'ng e'loningiz kanalda chop etiladi.",
        reply_markup=main_menu_kb(),
    )

    # Adminga yuborish
    caption = (
        f"🆕 Yangi e'lon #{ad_id}\n\n"
        f"👤 Foydalanuvchi: @{ad_data['username']}\n"
        f"📦 Nomi: {ad_data['name']}\n"
        f"📝 Tavsif: {ad_data['description']}\n"
        f"💰 Narx: {ad_data['price']}\n"
    )
    await bot.send_photo(ADMIN_ID, ad_data["photo_file_id"], caption=caption)
    await bot.send_photo(
        ADMIN_ID,
        ad_data["receipt_file_id"],
        caption="⬆️ To'lov cheki",
        reply_markup=admin_decision_kb(ad_id),
    )


@router.message(AdForm.receipt)
async def receipt_invalid(message: Message):
    await message.answer("Iltimos, to'lov chekining skrinshotini rasm ko'rinishida yuboring 🖼")


# ---------- Admin qarori ----------
@router.callback_query(F.data.startswith("approve:"))
async def approve_ad(callback: CallbackQuery):
    ad_id = int(callback.data.split(":")[1])
    ad = await get_ad(ad_id)
    if not ad:
        await callback.answer("E'lon topilmadi", show_alert=True)
        return

    await update_ad_status(ad_id, "tasdiqlangan")

    caption = (
        f"📦 {ad['name']}\n\n"
        f"{ad['description']}\n\n"
        f"💰 Narx: {ad['price']}\n"
        f"📞 Sotuvchi: @{ad['username']}"
    )
    await bot.send_photo(CHANNEL_ID, ad["photo_file_id"], caption=caption)
    await bot.send_message(ad["user_id"], f"✅ Sizning e'loningiz (#{ad_id}) tasdiqlandi va kanalda chop etildi!")

    await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ TASDIQLANDI")
    await callback.answer("Tasdiqlandi va kanalga joylandi")


@router.callback_query(F.data.startswith("reject:"))
async def reject_ad(callback: CallbackQuery):
    ad_id = int(callback.data.split(":")[1])
    ad = await get_ad(ad_id)
    if not ad:
        await callback.answer("E'lon topilmadi", show_alert=True)
        return

    await update_ad_status(ad_id, "rad etilgan")
    await bot.send_message(
        ad["user_id"],
        f"❌ Sizning e'loningiz (#{ad_id}) rad etildi.\n"
        "Sabab: to'lov tasdiqlanmadi yoki mahsulot qoidalarga mos kelmadi.\n"
        "Savol bo'lsa admin bilan bog'laning.",
    )

    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ RAD ETILDI")
    await callback.answer("Rad etildi")


# ---------- Ishga tushirish ----------
async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
