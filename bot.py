import asyncio
import json
import logging
import os
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ─────────────────────── CONFIG ───────────────────────

# ✅ TO'G'RI
BOT_TOKEN: str = "8724276114:AAHYzEuD3fhar1QDZWrON35-NXIXss-kf1I"
OWNER_ID: int = 8378615092
DATA_FILE: str = "data.json"

# ─────────────────────── LOGGING ──────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────── DATABASE ─────────────────────

def load_data() -> dict[str, Any]:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "movies": {}, "admins": [], "supports": [], "channels": []}


def save_data(data: dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_role(user_id: int) -> str:
    if user_id == OWNER_ID:
        return "owner"
    data = load_data()
    if user_id in data.get("admins", []):
        return "admin"
    if user_id in data.get("supports", []):
        return "support"
    return "user"


def is_registered(user_id: int) -> bool:
    data = load_data()
    return str(user_id) in data.get("users", {})


# ─────────────────────── STATES ───────────────────────

class AddMovie(StatesGroup):
    waiting_code = State()
    waiting_file = State()


class DeleteMovie(StatesGroup):
    waiting_code = State()


class AddAdmin(StatesGroup):
    waiting_id = State()


class RemoveAdmin(StatesGroup):
    waiting_id = State()


class AddSupport(StatesGroup):
    waiting_id = State()


class RemoveSupport(StatesGroup):
    waiting_id = State()


class AddChannel(StatesGroup):
    waiting_channel = State()


class RemoveChannel(StatesGroup):
    waiting_channel = State()


class Broadcast(StatesGroup):
    waiting_message = State()


# ─────────────────────── KEYBOARDS ────────────────────

def main_kb(user_id: int) -> ReplyKeyboardMarkup:
    role = get_role(user_id)
    buttons = [[KeyboardButton(text="🎬 Kino qidirish")]]
    if role in ("owner", "admin", "support"):
        buttons.append([KeyboardButton(text="⚙️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def admin_kb(user_id: int) -> ReplyKeyboardMarkup:
    role = get_role(user_id)
    buttons = [
        [KeyboardButton(text="➕ Kino qo'shish"), KeyboardButton(text="🗑 Kino o'chirish")],
        [KeyboardButton(text="📢 Reklama"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📡 Majburiy obuna")],
    ]
    if role in ("owner", "admin"):
        buttons.append([
            KeyboardButton(text="👤 Admin qo'shish"),
            KeyboardButton(text="❌ Admin o'chirish"),
        ])
        buttons.append([
            KeyboardButton(text="🤝 Support qo'shish"),
            KeyboardButton(text="➖ Support o'chirish"),
        ])
    buttons.append([KeyboardButton(text="🔙 Orqaga")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def channel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kanal qo'shish"), KeyboardButton(text="🗑 Kanal o'chirish")],
            [KeyboardButton(text="📋 Kanallar ro'yxati")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


def check_sub_kb(channels: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        username = ch if ch.startswith("@") else f"@{ch.lstrip('@')}"
        url = f"https://t.me/{username.lstrip('@')}"
        buttons.append([InlineKeyboardButton(text=f"📢 {username}", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────── SUBSCRIPTION CHECK ───────────────────────

async def check_subscriptions(bot: Bot, user_id: int) -> bool:
    data = load_data()
    channels = data.get("channels", [])
    if not channels:
        return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception as e:
            logger.warning("Kanal tekshirishda xato (%s): %s", ch, e)
    return True


async def send_subscribe_message(message: Message, channels: list[str]) -> None:
    text = (
        "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
        + "\n".join(f"• {ch}" for ch in channels)
    )
    await message.answer(text, reply_markup=check_sub_kb(channels))


# ─────────────────────── ROUTER ───────────────────────
router = Router()


# ──────────── /start ────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    data = load_data()

    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "name": message.from_user.full_name,
            "username": message.from_user.username,
        }
        save_data(data)
        logger.info("Yangi foydalanuvchi: %s (%d)", message.from_user.full_name, user_id)

    channels = data.get("channels", [])
    if channels:
        subscribed = await check_subscriptions(message.bot, user_id)
        if not subscribed:
            await send_subscribe_message(message, channels)
            return

    role = get_role(user_id)
    role_text = {"owner": "👑 Owner", "admin": "🛡 Admin", "support": "🤝 Support"}.get(role, "👤 Foydalanuvchi")
    await message.answer(
        f"Salom, {message.from_user.full_name}! 👋\n"
        f"Roliz: {role_text}\n\n"
        "🎬 Kino kodini yuboring yoki quyidagi tugmalardan foydalaning.",
        reply_markup=main_kb(user_id),
    )


# ──────────── Subscription callback ────────────

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = call.from_user.id

    subscribed = await check_subscriptions(call.bot, user_id)
    if subscribed:
        await call.message.delete()
        role_text = {
            "owner": "👑 Owner", "admin": "🛡 Admin", "support": "🤝 Support"
        }.get(get_role(user_id), "👤 Foydalanuvchi")
        await call.message.answer(
            f"✅ Obuna tasdiqlandi!\n\nSalom, {call.from_user.full_name}!\n"
            f"Roliz: {role_text}\n\n🎬 Kino kodini yuboring.",
            reply_markup=main_kb(user_id),
        )
    else:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)


# ──────────── /admin ────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    role = get_role(user_id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await message.answer("⚙️ Admin panel:", reply_markup=admin_kb(user_id))


@router.message(F.text == "⚙️ Admin panel")
async def panel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    role = get_role(user_id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await message.answer("⚙️ Admin panel:", reply_markup=admin_kb(user_id))


@router.message(F.text == "🔙 Orqaga")
async def back_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 Asosiy menyu:", reply_markup=main_kb(message.from_user.id))


# ──────────── Movie search ────────────

@router.message(F.text == "🎬 Kino qidirish")
async def movie_search_prompt(message: Message, state: FSMContext) -> None:
    await state.clear()
    data = load_data()
    channels = data.get("channels", [])
    if channels:
        subscribed = await check_subscriptions(message.bot, message.from_user.id)
        if not subscribed:
            await send_subscribe_message(message, channels)
            return
    await message.answer("🔢 Kino kodini kiriting:", reply_markup=ReplyKeyboardRemove())


# ──────────── Add Movie ────────────

@router.message(F.text == "➕ Kino qo'shish")
async def add_movie_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await state.set_state(AddMovie.waiting_code)
    await message.answer("🔢 Yangi kino uchun kod kiriting:", reply_markup=ReplyKeyboardRemove())


@router.message(AddMovie.waiting_code)
async def add_movie_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    data = load_data()
    if code in data["movies"]:
        await message.answer(f"⚠️ '{code}' kodi allaqachon mavjud. Boshqa kod kiriting:")
        return
    await state.update_data(code=code)
    await state.set_state(AddMovie.waiting_file)
    await message.answer("🎬 Endi kino faylini yuboring (video yoki document):")


@router.message(AddMovie.waiting_file, F.video | F.document)
async def add_movie_file(message: Message, state: FSMContext) -> None:
    data_state = await state.get_data()
    code = data_state["code"]

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    else:
        file_id = message.document.file_id
        file_type = "document"

    data = load_data()
    data["movies"][code] = {"file_id": file_id, "type": file_type}
    save_data(data)

    await state.clear()
    logger.info("Kino qo'shildi: kod=%s, type=%s", code, file_type)
    await message.answer(
        f"✅ Kino muvaffaqiyatli qo'shildi!\n📌 Kod: <code>{code}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb(message.from_user.id),
    )


@router.message(AddMovie.waiting_file)
async def add_movie_file_wrong(message: Message, state: FSMContext) -> None:
    await message.answer("❌ Iltimos, video yoki fayl yuboring.")


# ──────────── Delete Movie ────────────

@router.message(F.text == "🗑 Kino o'chirish")
async def delete_movie_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await state.set_state(DeleteMovie.waiting_code)
    await message.answer("🔢 O'chirmoqchi bo'lgan kino kodini kiriting:", reply_markup=ReplyKeyboardRemove())


@router.message(DeleteMovie.waiting_code)
async def delete_movie_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    data = load_data()
    if code not in data["movies"]:
        await message.answer(f"❌ '{code}' kodli kino topilmadi. Qaytadan kiriting:")
        return
    del data["movies"][code]
    save_data(data)
    await state.clear()
    logger.info("Kino o'chirildi: kod=%s", code)
    await message.answer(
        f"✅ '{code}' kodli kino o'chirildi.",
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Add Admin ────────────

@router.message(F.text == "👤 Admin qo'shish")
async def add_admin_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await state.set_state(AddAdmin.waiting_id)
    await message.answer("🆔 Admin qilmoqchi bo'lgan foydalanuvchining ID sini kiriting:", reply_markup=ReplyKeyboardRemove())


@router.message(AddAdmin.waiting_id)
async def add_admin_id(message: Message, state: FSMContext) -> None:
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID. Raqam kiriting:")
        return

    if target_id == OWNER_ID:
        await state.clear()
        await message.answer("❌ Owner ni admin qilib bo'lmaydi.", reply_markup=admin_kb(message.from_user.id))
        return

    data = load_data()
    if str(target_id) not in data["users"]:
        await message.answer("❌ Bu foydalanuvchi botda ro'yxatdan o'tmagan (/start bosmagan).")
        return

    if target_id in data["admins"]:
        await state.clear()
        await message.answer("⚠️ Bu foydalanuvchi allaqachon admin.", reply_markup=admin_kb(message.from_user.id))
        return

    if target_id in data["supports"]:
        data["supports"].remove(target_id)

    data["admins"].append(target_id)
    save_data(data)
    await state.clear()
    logger.info("Admin qo'shildi: %d", target_id)
    await message.answer(
        f"✅ {target_id} ID li foydalanuvchi admin qilindi.",
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Remove Admin ────────────

@router.message(F.text == "❌ Admin o'chirish")
async def remove_admin_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    data = load_data()
    if not data["admins"]:
        await message.answer("📋 Adminlar yo'q.", reply_markup=admin_kb(message.from_user.id))
        return
    await state.set_state(RemoveAdmin.waiting_id)
    admins_list = "\n".join(f"• <code>{aid}</code>" for aid in data["admins"])
    await message.answer(
        f"📋 Adminlar:\n{admins_list}\n\n🆔 O'chirmoqchi bo'lgan admin ID sini kiriting:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(RemoveAdmin.waiting_id)
async def remove_admin_id(message: Message, state: FSMContext) -> None:
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID. Raqam kiriting:")
        return

    data = load_data()
    if target_id not in data["admins"]:
        await message.answer("❌ Bu foydalanuvchi admin emas.")
        return

    data["admins"].remove(target_id)
    save_data(data)
    await state.clear()
    logger.info("Admin o'chirildi: %d", target_id)
    await message.answer(
        f"✅ {target_id} ID li admin o'chirildi.",
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Add Support ────────────

@router.message(F.text == "🤝 Support qo'shish")
async def add_support_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await state.set_state(AddSupport.waiting_id)
    await message.answer("🆔 Support qilmoqchi bo'lgan foydalanuvchining ID sini kiriting:", reply_markup=ReplyKeyboardRemove())


@router.message(AddSupport.waiting_id)
async def add_support_id(message: Message, state: FSMContext) -> None:
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID. Raqam kiriting:")
        return

    if target_id == OWNER_ID:
        await state.clear()
        await message.answer("❌ Owner ni support qilib bo'lmaydi.", reply_markup=admin_kb(message.from_user.id))
        return

    data = load_data()
    if str(target_id) not in data["users"]:
        await message.answer("❌ Bu foydalanuvchi botda ro'yxatdan o'tmagan (/start bosmagan).")
        return

    if target_id in data["supports"]:
        await state.clear()
        await message.answer("⚠️ Bu foydalanuvchi allaqachon support.", reply_markup=admin_kb(message.from_user.id))
        return

    if target_id in data["admins"]:
        await state.clear()
        await message.answer("⚠️ Bu foydalanuvchi admin. Avval admin lavozimini oling.", reply_markup=admin_kb(message.from_user.id))
        return

    data["supports"].append(target_id)
    save_data(data)
    await state.clear()
    logger.info("Support qo'shildi: %d", target_id)
    await message.answer(
        f"✅ {target_id} ID li foydalanuvchi support qilindi.",
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Remove Support ────────────

@router.message(F.text == "➖ Support o'chirish")
async def remove_support_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    data = load_data()
    if not data["supports"]:
        await message.answer("📋 Supportlar yo'q.", reply_markup=admin_kb(message.from_user.id))
        return
    await state.set_state(RemoveSupport.waiting_id)
    supports_list = "\n".join(f"• <code>{sid}</code>" for sid in data["supports"])
    await message.answer(
        f"📋 Supportlar:\n{supports_list}\n\n🆔 O'chirmoqchi bo'lgan support ID sini kiriting:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(RemoveSupport.waiting_id)
async def remove_support_id(message: Message, state: FSMContext) -> None:
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID. Raqam kiriting:")
        return

    data = load_data()
    if target_id not in data["supports"]:
        await message.answer("❌ Bu foydalanuvchi support emas.")
        return

    data["supports"].remove(target_id)
    save_data(data)
    await state.clear()
    logger.info("Support o'chirildi: %d", target_id)
    await message.answer(
        f"✅ {target_id} ID li support o'chirildi.",
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Channels ────────────

@router.message(F.text == "📡 Majburiy obuna")
async def channels_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await message.answer("📡 Majburiy obuna boshqaruvi:", reply_markup=channel_kb())


@router.message(F.text == "➕ Kanal qo'shish")
async def add_channel_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await state.set_state(AddChannel.waiting_channel)
    await message.answer(
        "📢 Kanal username yoki ID sini kiriting.\n"
        "Misol: <code>@mening_kanalim</code> yoki <code>-1001234567890</code>\n\n"
        "⚠️ Bot kanalga admin bo'lishi shart!",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(AddChannel.waiting_channel)
async def add_channel_save(message: Message, state: FSMContext) -> None:
    channel = message.text.strip()
    data = load_data()
    try:
        chat = await message.bot.get_chat(channel)
        bot_member = await message.bot.get_chat_member(chat.id, (await message.bot.get_me()).id)
        if bot_member.status not in ("administrator", "creator"):
            await message.answer("❌ Bot bu kanalda admin emas. Avval botni kanalga admin qiling.")
            return
        channel_id = str(chat.id)
    except Exception as e:
        logger.warning("Kanal tekshirishda xato: %s", e)
        await message.answer("❌ Kanal topilmadi yoki bot admin emas. Qaytadan kiriting:")
        return

    if channel_id in data["channels"]:
        await state.clear()
        await message.answer("⚠️ Bu kanal allaqachon qo'shilgan.", reply_markup=channel_kb())
        return

    data["channels"].append(channel_id)
    save_data(data)
    await state.clear()
    logger.info("Kanal qo'shildi: %s", channel_id)
    await message.answer(f"✅ Kanal qo'shildi: {chat.title}", reply_markup=channel_kb())


@router.message(F.text == "🗑 Kanal o'chirish")
async def remove_channel_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    data = load_data()
    if not data["channels"]:
        await message.answer("📋 Kanallar yo'q.", reply_markup=channel_kb())
        return
    await state.set_state(RemoveChannel.waiting_channel)
    channels_list = "\n".join(f"• <code>{ch}</code>" for ch in data["channels"])
    await message.answer(
        f"📋 Mavjud kanallar:\n{channels_list}\n\nO'chirmoqchi bo'lgan kanal ID sini kiriting:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(RemoveChannel.waiting_channel)
async def remove_channel_save(message: Message, state: FSMContext) -> None:
    channel = message.text.strip()
    data = load_data()
    target = None
    if channel in data["channels"]:
        target = channel
    else:
        try:
            chat = await message.bot.get_chat(channel)
            cid = str(chat.id)
            if cid in data["channels"]:
                target = cid
        except Exception:
            pass

    if target is None:
        await message.answer("❌ Bunday kanal topilmadi. Qaytadan kiriting:")
        return

    data["channels"].remove(target)
    save_data(data)
    await state.clear()
    logger.info("Kanal o'chirildi: %s", target)
    await message.answer("✅ Kanal o'chirildi.", reply_markup=channel_kb())


@router.message(F.text == "📋 Kanallar ro'yxati")
async def list_channels(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    data = load_data()
    channels = data.get("channels", [])
    if not channels:
        await message.answer("📋 Majburiy obuna kanallari yo'q.", reply_markup=channel_kb())
        return
    text = "📡 Majburiy obuna kanallari:\n\n" + "\n".join(f"• <code>{ch}</code>" for ch in channels)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=channel_kb())


# ──────────── Broadcast ────────────

@router.message(F.text == "📢 Reklama")
async def broadcast_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await state.set_state(Broadcast.waiting_message)
    await message.answer(
        "📨 Barcha foydalanuvchilarga yuboriladigan xabarni yuboring:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Broadcast.waiting_message)
async def broadcast_send(message: Message, state: FSMContext) -> None:
    await state.clear()
    data = load_data()
    users = list(data["users"].keys())
    sent = 0
    failed = 0

    await message.answer(f"📤 Reklama yuborilmoqda... ({len(users)} ta foydalanuvchi)")

    for uid_str in users:
        uid = int(uid_str)
        try:
            await message.bot.copy_message(
                chat_id=uid,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception as e:
            logger.warning("Reklama yuborishda xato (%d): %s", uid, e)
            failed += 1

    logger.info("Reklama yakunlandi: sent=%d, failed=%d", sent, failed)
    await message.answer(
        f"✅ Reklama yakunlandi!\n\n📬 Yuborildi: {sent}\n❌ Xato: {failed}",
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Statistics ────────────

@router.message(F.text == "📊 Statistika")
async def statistics(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = get_role(message.from_user.id)
    if role not in ("owner", "admin", "support"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    data = load_data()
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{len(data['users'])}</b>\n"
        f"🎬 Kinolar: <b>{len(data['movies'])}</b>\n"
        f"🛡 Adminlar: <b>{len(data['admins'])}</b>\n"
        f"🤝 Supportlar: <b>{len(data['supports'])}</b>\n"
        f"📡 Kanallar: <b>{len(data['channels'])}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb(message.from_user.id),
    )


# ──────────── Movie by code ────────────

@router.message(F.text)
async def handle_movie_code(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is not None:
        return

    user_id = message.from_user.id
    data = load_data()

    channels = data.get("channels", [])
    if channels:
        subscribed = await check_subscriptions(message.bot, user_id)
        if not subscribed:
            await send_subscribe_message(message, channels)
            return

    code = message.text.strip()
    movie = data["movies"].get(code)

    if not movie:
        await message.answer(
            f"❌ <code>{code}</code> kodli kino topilmadi.\nKino kodini to'g'ri kiriting.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        if movie["type"] == "video":
            await message.answer_video(
                video=movie["file_id"],
                caption=f"🎬 Kino kodi: <code>{code}</code>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.answer_document(
                document=movie["file_id"],
                caption=f"🎬 Kino kodi: <code>{code}</code>",
                parse_mode=ParseMode.HTML,
            )
        logger.info("Kino yuborildi: kod=%s, user=%d", code, user_id)
    except TelegramBadRequest as e:
        logger.error("Kino yuborishda xato: %s", e)
        await message.answer("❌ Kinoni yuborishda xato yuz berdi.")


# ─────────────────────── MAIN ─────────────────────────

async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())