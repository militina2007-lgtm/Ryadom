import asyncio
import logging
import os
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === ТОКЕН из переменной окружения ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен в Environment Variables")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# === Google Sheets подключение ===
SHEET_ID = "1Q1BQaCoBnMZSPWtM-utnrmVoD0qOsHOO7S4ilhL03D8"

def get_sheet():
    creds_file = "/etc/secrets/credentials.json"
    if not os.path.exists(creds_file):
        logging.warning("Файл credentials.json не найден в /etc/secrets/")
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

# Загружаем прогулки из таблицы при старте
walks = []
user_walks = {}
sheet = get_sheet()

def load_walks_from_sheet():
    global walks, user_walks
    if not sheet:
        return
    rows = sheet.get_all_values()
    if len(rows) <= 1:
        walks = []
        user_walks = {}
        return
    walks = []
    user_walks = {}
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        walk = {
            "id": int(row[0]),
            "name": row[1],
            "place": row[2],
            "datetime": row[3],
            "description": row[4],
            "max": row[5],
            "creator": int(row[6]),
            "members": list(map(int, row[7].split(","))) if row[7] else []
        }
        walks.append(walk)
        for uid in walk["members"]:
            if uid not in user_walks:
                user_walks[uid] = []
            if walk["id"] not in user_walks[uid]:
                user_walks[uid].append(walk["id"])

def save_walk_to_sheet(walk):
    if not sheet:
        return
    rows = sheet.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == str(walk["id"]):
            sheet.update(f"A{i}:H{i}", [[walk["id"], walk["name"], walk["place"], walk["datetime"],
                                         walk["description"], walk["max"], walk["creator"],
                                         ",".join(map(str, walk["members"]))]])
            return
    sheet.append_row([walk["id"], walk["name"], walk["place"], walk["datetime"],
                      walk["description"], walk["max"], walk["creator"],
                      ",".join(map(str, walk["members"]))])

def delete_walk_from_sheet(walk_id):
    if not sheet:
        return
    rows = sheet.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == str(walk_id):
            sheet.delete_rows(i)
            return

# Загружаем данные при старте
load_walks_from_sheet()

# --- Функция парсинга даты ---
def parse_datetime(date_string):
    pattern = r'^(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря),\s+(\d{1,2}):(\d{2})$'
    match = re.match(pattern, date_string.strip())
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2)
    hour = int(match.group(3))
    minute = int(match.group(4))
    month_map = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
        "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }
    month = month_map.get(month_name.lower())
    if not month:
        return None
    try:
        current_year = datetime.now().year
        dt = datetime(current_year, month, day, hour, minute)
        return dt
    except ValueError:
        return None

def is_expired(datetime_str):
    dt = parse_datetime(datetime_str)
    if dt is None:
        return False
    return dt < datetime.now()

def clean_expired_walks():
    global walks, user_walks
    expired_ids = []
    for walk in walks:
        if is_expired(walk["datetime"]):
            expired_ids.append(walk["id"])
    if expired_ids:
        for wid in expired_ids:
            delete_walk_from_sheet(wid)
        walks = [walk for walk in walks if walk["id"] not in expired_ids]
        for uid in user_walks:
            user_walks[uid] = [wid for wid in user_walks[uid] if wid not in expired_ids]

# --- Главное меню ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚶‍♀️ Создать прогулку")],
        [KeyboardButton(text="📅 Смотреть прогулки")],
        [KeyboardButton(text="👤 Мои прогулки")]
    ],
    resize_keyboard=True
)

user_walk_index = {}
user_temp = {}

def get_user_mention(user_id):
    return f"[пользователь](tg://user?id={user_id})"

# --- Правила ---
@dp.message(lambda m: m.text == "Правила")
async def show_rules(message: types.Message):
    await message.answer(
        "📌 *Правила сообщества «Рядом»*\n\n"
        "1. Будьте вежливы друг с другом.\n"
        "2. Не опаздывайте без предупреждения.\n"
        "3. Если не можете прийти — предупредите организатора.\n"
        "4. О конфликтах пишите в поддержку: @ryadom_poisk_support_bot\n"
        "5. Соблюдайте личные границы.\n"
        "6. Запрещена реклама, алкоголь, наркотики.\n\n"
        "🌿 Хороших прогулок!",
        parse_mode="Markdown"
    )

# --- Помощь ---
@dp.message(lambda m: m.text == "Помощь")
async def show_help(message: types.Message):
    await message.answer(
        "🆘 *Если у вас возник вопрос*\n\n"
        "Напишите в поддержку:\n"
        "@ryadom_poisk_support_bot\n\n"
        "Мы ответим в ближайшее время.",
        parse_mode="Markdown"
    )

# --- Создание прогулки ---
@dp.message(lambda m: m.text == "🚶‍♀️ Создать прогулку")
async def create_walk_start(message: types.Message):
    user_temp[message.from_user.id] = {"step": "name"}
    await message.answer(
        "🚶 Давайте создадим прогулку!\n\n"
        "Придумайте название (короткое и понятное).\n\n"
        "➤ Напишите название прогулки"
    )

@dp.message(lambda m: m.from_user.id in user_temp)
async def create_walk_collect(message: types.Message):
    user_id = message.from_user.id
    state = user_temp[user_id]
    step = state.get("step")

    if step == "name":
        state["name"] = message.text
        state["step"] = "place"
        await message.answer(
            "📍 Отлично!\n\n"
            "Где встретимся? Напишите конкретное место, чтобы всем было легко найти друг друга.\n\n"
            "Например: «У центрального входа в парк Горького, у фонтана» или «Кофейня \"Кофе и точка\", Пушкина 10»\n\n"
            "➤ Укажите место сбора"
        )
    elif step == "place":
        state["place"] = message.text
        state["step"] = "datetime"
        await message.answer(
            "🕓 Теперь — когда гуляем?\n\n"
            "Напишите дату и время в правильном формате.\n\n"
            "Например:\n"
            "• 20 мая, 15:00\n\n"
            "➤ Укажите дату и время"
        )
    elif step == "datetime":
        if parse_datetime(message.text) is None:
            await message.answer("❌ Неверный формат! Напишите: 15 мая, 18:30")
            return
        state["datetime"] = message.text
        state["step"] = "description"
        await message.answer(
            "📝 Добавьте пару слов о прогулке (необязательно, но приятно).\n\n"
            "Например: «Забредём в три новые кофейни, возьмите с собой хорошее настроение 🐶 Можно с собаками»\n\n"
            "➤ Напишите описание или нажмите «Пропустить»",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="⏩ Пропустить")]],
                resize_keyboard=True
            )
        )
    elif step == "description":
        if message.text != "⏩ Пропустить":
            state["description"] = message.text
        else:
            state["description"] = ""
        state["step"] = "max_members"
        await message.answer(
            "👥 Сколько человек может пойти?\n\n"
            "• 0 — безлимит\n"
            "• Число — например, 5\n\n"
            "➤ Укажите максимум участников",
            reply_markup=main_kb
        )
    elif step == "max_members":
        state["max"] = message.text
        new_walk = {
            "id": len(walks) + 1 if walks else 1,
            "name": state["name"],
            "place": state["place"],
            "datetime": state["datetime"],
            "description": state.get("description", ""),
            "max": state["max"],
            "creator": user_id,
            "members": [user_id]
        }
        walks.append(new_walk)
        save_walk_to_sheet(new_walk)
        if user_id not in user_walks:
            user_walks[user_id] = []
        user_walks[user_id].append(new_walk["id"])
        del user_temp[user_id]
        await message.answer("✅ Прогулка создана!", reply_markup=main_kb)

# --- Команда /start ---
@dp.message(Command("start"))
async def start(message: types.Message):
    clean_expired_walks()
    await message.answer(
        "👋 Привет! Я — «Рядом».\n"
        "Я здесь, чтобы прогулки стали интереснее, а компании находились проще.\n\n"
        "🚶‍♀️ Создать прогулку — если хочешь позвать других\n"
        "📅 Смотреть прогулки — если ищешь, куда пойти\n"
        "👤 Мои прогулки — где ты участвуешь\n"
        "📖 Правила — безопасность и этика в нашем сообществе (рекомендую прочитать перед первой прогулкой)\n\n"
        "Давай знакомиться?",
        reply_markup=main_kb
    )

# --- Смотреть прогулки ---
@dp.message(lambda m: m.text == "📅 Смотреть прогулки")
async def show_walks_start(message: types.Message):
    clean_expired_walks()
    user_id = message.from_user.id
    available_walks = []
    for walk in walks:
        max_members = int(walk["max"]) if walk["max"].isdigit() else 0
        if max_members == 0 or len(walk["members"]) < max_members:
            available_walks.append(walk)
    if not available_walks:
        await message.answer("Пока нет доступных прогулок. Создайте первую!")
        return
    user_walk_index[user_id] = {"walks": available_walks, "index": 0}
    await show_current_walk(message, user_id)

async def show_current_walk(message: types.Message, user_id: int):
    data = user_walk_index.get(user_id)
    if not data:
        return
    walks_list = data["walks"]
    current_idx = data["index"]
    if current_idx >= len(walks_list):
        await message.answer("Прогулки закончились.")
        del user_walk_index[user_id]
        return
    walk = walks_list[current_idx]
    current_members = len(walk["members"])
    max_members = int(walk["max"]) if walk["max"].isdigit() else 0
    members_text = f"{current_members}"
    if max_members > 0:
        members_text += f" / {max_members}"
    text = (
        f"📍 *{walk['name']}*\n"
        f"🗓 Когда: {walk['datetime']}\n"
        f"📍 Где: {walk['place']}\n"
        f"👥 Участников: {members_text}"
    )
    if walk.get("description"):
        text += f"\n📝 *Описание:* {walk['description']}"
    keyboard_buttons = [
        [InlineKeyboardButton(text="✅ Присоединиться", callback_data=f"join_{walk['id']}")],
        [InlineKeyboardButton(text="⏩ Дальше", callback_data="next_walk")]
    ]
    if current_idx + 1 >= len(walks_list):
        keyboard_buttons[2] = [InlineKeyboardButton(text="🏁 Завершить", callback_data="end_walks")]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "next_walk")
async def next_walk(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = user_walk_index.get(user_id)
    if not data:
        await callback.answer("Список устарел.")
        await callback.message.delete()
        return
    await callback.message.delete()
    data["index"] += 1
    await show_current_walk(callback.message, user_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "end_walks")
async def end_walks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_walk_index:
        del user_walk_index[user_id]
    await callback.message.edit_text("🏁 Просмотр прогулок завершён.")
    await callback.answer()

# --- Просмотр участников ---
@dp.callback_query(lambda c: c.data.startswith("members_"))
async def show_members(callback: types.CallbackQuery):
    walk_id = int(callback.data.split("_")[1])
    walk = None
    for w in walks:
        if w["id"] == walk_id:
            walk = w
            break
    if not walk:
        await callback.answer("Прогулка не найдена!")
        return
    creator_username = None
    try:
        creator_chat = await bot.get_chat(walk["creator"])
        creator_username = "@" + creator_chat.username if creator_chat.username else get_user_mention(walk["creator"])
    except:
        creator_username = get_user_mention(walk["creator"])
    members_list = []
    for uid in walk["members"]:
        if uid == walk["creator"]:
            continue
        try:
            chat = await bot.get_chat(uid)
            username = "@" + chat.username if chat.username else get_user_mention(uid)
            members_list.append(username)
        except:
            members_list.append(get_user_mention(uid))
    members_text = "\n".join(members_list) if members_list else "Пока никого"
    text = (
        f"👥 *Участники прогулки*\n\n"
        f"👑 *Создатель:* {creator_username}\n\n"
        f"📋 *Записались:*\n{members_text}"
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# --- Присоединиться ---
@dp.callback_query(lambda c: c.data.startswith("join_"))
async def join_walk(callback: types.CallbackQuery):
    walk_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    walk = None
    for w in walks:
        if w["id"] == walk_id:
            walk = w
            break
    if not walk:
        await callback.answer("Прогулка не найдена!")
        return
    if walk["creator"] == user_id:
        await callback.answer("❌ Вы создатель!")
        return
    if user_id in walk["members"]:
        await callback.answer("❌ Вы уже записаны!")
        return
    max_members = int(walk["max"]) if walk["max"].isdigit() else 0
    if max_members > 0 and len(walk["members"]) >= max_members:
        await callback.answer("❌ Мест больше нет!")
        return
    walk["members"].append(user_id)
    save_walk_to_sheet(walk)
    if user_id not in user_walks:
        user_walks[user_id] = []
    if walk_id not in user_walks[user_id]:
        user_walks[user_id].append(walk_id)
    await callback.answer("✅ Вы записаны!")
    await callback.message.edit_text(callback.message.text + "\n\n✅ Вы идёте!", reply_markup=None)

# --- Мои прогулки ---
@dp.message(lambda m: m.text == "👤 Мои прогулки")
async def my_walks(message: types.Message):
    clean_expired_walks()
    user_id = message.from_user.id
    my_walks_list = [walk for walk in walks if user_id in walk["members"] or walk["creator"] == user_id]
    if not my_walks_list:
        await message.answer("Вы пока не участвуете в прогулках.")
        return
    for walk in my_walks_list:
        current_members = len(walk["members"])
        max_members = int(walk["max"]) if walk["max"].isdigit() else 0
        members_text = f"{current_members}"
        if max_members > 0:
            members_text += f" / {max_members}"
        creator_text = " (вы создатель)" if walk["creator"] == user_id else ""
        full_text = (
            f"📍 *{walk['name']}*{creator_text}\n"
            f"🗓 Когда: {walk['datetime']}\n"
            f"📍 Где: {walk['place']}\n"
            f"👥 Участников: {members_text}"
        )
        if walk.get("description"):
            full_text += f"\n📝 *Описание:* {walk['description']}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Участники", callback_data=f"members_{walk['id']}")]
        ])
        if walk["creator"] == user_id:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_{walk['id']}")])
        await message.answer(full_text, parse_mode="Markdown", reply_markup=keyboard)

# --- Удалить прогулку ---
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_walk(callback: types.CallbackQuery):
    walk_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    walk_to_delete = None
    for walk in walks:
        if walk["id"] == walk_id:
            walk_to_delete = walk
            break
    if not walk_to_delete:
        await callback.answer("Прогулка не найдена!")
        return
    if walk_to_delete["creator"] != user_id:
        await callback.answer("Не ваша прогулка!")
        return
    walks[:] = [walk for walk in walks if walk["id"] != walk_id]
    delete_walk_from_sheet(walk_id)
    for uid in user_walks:
        if walk_id in user_walks[uid]:
            user_walks[uid].remove(walk_id)
    await callback.answer("Прогулка удалена!")
    await callback.message.edit_text(callback.message.text + "\n\n❌ Удалено", reply_markup=None)

# === Фейковый веб-сервер для Render ===
async def health_check(request):
    return web.Response(text="Bot is running")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# --- Универсальный обработчик (ЛОВИТ ВСЕ КНОПКИ) ---
@dp.message()
async def catch_all(message: types.Message):
    text = message.text
    if text in ["📖 Правила", "Правила"]:
        await message.answer(
            "📌 *Правила сообщества «Рядом»*\n\n"
            "1. Будьте вежливы друг с другом.\n"
            "2. Не опаздывайте без предупреждения.\n"
            "3. Если не можете прийти — предупредите организатора.\n"
            "4. О конфликтах пишите в поддержку: @ryadom_poisk_support_bot\n"
            "5. Соблюдайте личные границы.\n"
            "6. Запрещена реклама, алкоголь, наркотики.\n\n"
            "🌿 Хороших прогулок!",
            parse_mode="Markdown"
        )
    elif text in ["🆘 Помощь", "Помощь"]:
        await message.answer(
            "🆘 *Если у вас возник вопрос*\n\n"
            "Напишите в поддержку:\n"
            "@ryadom_poisk_support_bot\n\n"
            "Мы ответим в ближайшее время.",
            parse_mode="Markdown"
        )
    else:
        pass

# --- Запуск ---
async def main():
    asyncio.create_task(start_web_server())
    clean_expired_walks()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
