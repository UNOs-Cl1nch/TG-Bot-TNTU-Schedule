import os
import asyncio
import datetime
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove

from parser import get_tntu_schedule

load_dotenv()

TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("Помилка: Токен не знайдено!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

subject_abbreviations = {
    "Сучасні пошукові системи та бібліографія": "СПС та Б",
    "Основи комп'ютерних технологій": "Осн. комп. техн.",
    "Основи національного спротиву": "ОНС",
    "Вступ до спеціальності": "Вступ до спец.",
    "Вища математика": "Вища мат.",
    "Англійська мова": "Англ. мова",
    "Фізичне виховання": "Фіз. вих."
}

ukrainian_days = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]
ukrainian_months = {
    1: "січня", 2: "лютого", 3: "березня", 4: "квітня",
    5: "травня", 6: "червня", 7: "липня", 8: "серпня",
    9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня"
}

user_settings = {}
user_sent_messages = {}

# --- МАТЕМАТИЧЕСКАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ НЕДЕЛИ ---
def get_week_number(target_date):
    ref_monday = datetime.date(2026, 9, 21)

    target = target_date.date() if isinstance(target_date, datetime.datetime) else target_date

    target_monday = target - datetime.timedelta(days=target.weekday())

    weeks_diff = (target_monday - ref_monday).days // 7

    return 2 if weeks_diff % 2 == 0 else 1


async def clear_old_messages(chat_id: int):
    if chat_id in user_sent_messages:
        for msg_id in user_sent_messages[chat_id]:
            try:
                await bot.delete_message(chat_id, msg_id)
            except Exception:
                pass
        user_sent_messages[chat_id] = []

# --- ГЕНЕРАТОР НАТИВНОЙ ТАБЛИЦЫ ---
def format_native_html_table(day_name, date_obj, times_data, sub_filter=0, group_name="sb11", week_filter=0, show_buttons=False):
    month_name = ukrainian_months[date_obj.month]
    date_str = f"{date_obj.day} {month_name} {date_obj.year}"

    html = f"📅 <b>{day_name.capitalize()}: {date_str}</b><br><br>\n"
    html += "<table bordered striped compact>\n"
    html += "<tr><th>№ Пари / Час</th><th>Предмет / Тип</th><th>Перерва</th></tr>\n"

    breaks = {
        "1": "10 хв.", "2": "20 хв.", "3": "30 хв.",
        "4": "20 хв.", "5": "10 хв.", "6": "10 хв.", "7": "Додому"
    }

    if not times_data:
        html += "<tr><td>-</td><td><i>НЕМАЄ</i></td><td>-</td></tr>\n"
    else:
        for time_str, lessons in times_data.items():
            parts = time_str.split("-")
            time_range = time_str.split(" ", 1)[1] if len(time_str.split(" ", 1)) > 1 else time_str
            para_num = time_str.split(" ", 1)[0] if len(time_str.split(" ", 1)) > 1 else "?"

            filtered_lessons = [l for l in lessons if (sub_filter == 0 or l["подгруппа"] == 0 or l["подгруппа"] == sub_filter)]
            real_lessons = [l for l in filtered_lessons if not l.get("пусто")]

            break_text = breaks.get(para_num, "")

            if not real_lessons:
                html += f"<tr><td>{para_num} пара<br>[{time_range}]</td><td><i>НЕМАЄ</i></td><td><i>{break_text}</i></td></tr>\n"
            else:
                subjects_html = ""
                for lesson in real_lessons:
                    short_name = subject_abbreviations.get(lesson['название'], lesson['название'])

                    if lesson.get('ссылка'):
                        name_part = f"<tg-button type=\"url\" url=\"{lesson['ссылка']}\">{short_name}</tg-button>"
                    else:
                        name_part = short_name

                    details = lesson.get('детали', '').strip()
                    format_type, audience = "-", "-"
                    if details:
                        detail_parts = details.split(" ", 1)
                        format_type = detail_parts[0]
                        if len(detail_parts) > 1:
                            audience = detail_parts[1]

                    subjects_html += f"{name_part}<br><i>({format_type}) | ({audience})</i><br>"

                if subjects_html.endswith("<br>"):
                    subjects_html = subjects_html[:-4]

                html += f"<tr><td>{para_num} пара<br>[{time_range}]</td><td>{subjects_html}</td><td><i>{break_text}</i></td></tr>\n"

    sub_text = "Всі" if sub_filter == 0 else f"{sub_filter}-а"

    # Вставляем математически вычисленную неделю в футер, если выбран "Поточний"
    calculated_week = get_week_number(date_obj)
    actual_week = calculated_week if week_filter == 0 else week_filter
    week_text = f"Поточний ({actual_week}-й)" if week_filter == 0 else f"{week_filter}-й"

    html += f"<tr><td>Група: {group_name.upper()}</td><td colspan=\"2\">Тиждень: {week_text} | Підгрупа: {sub_text}</td></tr>\n"
    html += "</table>\n"

    if show_buttons:
        html += "<br>"
        # 1. Фильтр подгрупп
        html += "<tg-button-row align=\"center\">\n"
        html += f"  <tg-button type=\"callback_data\" data=\"sub_0\">Всі підгрупи</tg-button>\n"
        html += f"  <tg-button type=\"callback_data\" data=\"sub_1\">1 Підгрупа</tg-button>\n"
        html += f"  <tg-button type=\"callback_data\" data=\"sub_2\">2 Підгрупа</tg-button>\n"
        html += "</tg-button-row>\n"
        # 2. Фильтр недель
        html += "<tg-button-row align=\"center\">\n"
        html += f"  <tg-button type=\"callback_data\" data=\"week_1\">1 Тиждень</tg-button>\n"
        html += f"  <tg-button type=\"callback_data\" data=\"week_0\">Поточний</tg-button>\n"
        html += f"  <tg-button type=\"callback_data\" data=\"week_2\">2 Тиждень</tg-button>\n"
        html += "</tg-button-row>\n"
        # 3. Навигация
        html += "<tg-button-row align=\"center\">\n"
        html += f"  <tg-button type=\"callback_data\" data=\"menu_today\">📅 Сьогодні</tg-button>\n"
        html += f"  <tg-button type=\"callback_data\" data=\"menu_week\">🗓 Весь тиждень</tg-button>\n"
        html += "</tg-button-row>\n"
        # 4. Смена группы
        html += "<tg-button-row align=\"center\">\n"
        html += f"  <tg-button type=\"callback_data\" data=\"menu_group\">🔄 Змінити групу ({group_name.upper()})</tg-button>\n"
        html += "</tg-button-row>"

    return html

# --- ПРЯМОЙ ЗАПРОС К TELEGRAM API ---
async def send_rich_message_raw(chat_id: int, html_content: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendRichMessage"
    payload = {
        "chat_id": chat_id,
        "rich_message": {"html": html_content}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            res = await response.json()
            if res.get("ok"):
                return res["result"]["message_id"]
            else:
                print("Ошибка TG API (Send):", res)
                return None

# --- ЗАМЕНА СООБЩЕНИЯ НА ЛЕТУ ---
async def edit_rich_message_raw(chat_id: int, message_id: int, html_content: str):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "rich_message": {"html": html_content}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            res = await response.json()
            if res.get("ok"):
                return True
            else:
                if "message is not modified" in res.get("description", ""):
                    return True
                return False


# --- ОБРАБОТЧИКИ ТЕКСТОВЫХ КОМАНД ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "today", "week": 0}

    del_msg = await message.answer("🧹 Очищення інтерфейсу...", reply_markup=ReplyKeyboardRemove())
    await del_msg.delete()

    await send_today_logic(message, force_delete=True)

@dp.message(Command("group", "sb"))
async def cmd_change_group_text(message: types.Message):
    chat_id = message.chat.id
    current = user_settings.get(chat_id, {}).get("group", "sb11")
    new_group = "sb12" if current == "sb11" else "sb11"

    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": new_group, "sub": 0, "mode": "today", "week": 0}
    else:
        user_settings[chat_id]["group"] = new_group

    mode = user_settings[chat_id].get("mode", "today")
    if mode == "full":
        await send_full_logic(message, force_delete=False)
    else:
        await send_today_logic(message, force_delete=False)

@dp.message(Command("today", "sogodni"))
async def cmd_today_text(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "today", "week": 0}
    user_settings[chat_id]["mode"] = "today"
    await send_today_logic(message, force_delete=False)

@dp.message(Command("week", "tyzhden"))
async def cmd_week_text(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "full", "week": 0}
    user_settings[chat_id]["mode"] = "full"
    await send_full_logic(message, force_delete=True)


# --- ОБРАБОТЧИКИ НАЖАТИЙ НА ВСТРОЕННЫЕ КНОПКИ ---

@dp.callback_query(F.data == 'menu_today')
async def cq_today(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "today", "week": 0}
    user_settings[chat_id]["mode"] = "today"

    await send_today_logic(callback.message, force_delete=False)
    await callback.answer("Завантажено сьогоднішній день")

@dp.callback_query(F.data == 'menu_week')
async def cq_week(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "full", "week": 0}
    user_settings[chat_id]["mode"] = "full"

    await send_full_logic(callback.message, force_delete=True)
    await callback.answer("Завантажено весь тиждень")

@dp.callback_query(F.data == 'menu_group')
async def cq_group(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    current = user_settings.get(chat_id, {}).get("group", "sb11")
    new_group = "sb12" if current == "sb11" else "sb11"

    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": new_group, "sub": 0, "mode": "today", "week": 0}
    else:
        user_settings[chat_id]["group"] = new_group

    mode = user_settings[chat_id].get("mode", "today")
    if mode == "full":
        await send_full_logic(callback.message, force_delete=False)
    else:
        await send_today_logic(callback.message, force_delete=False)

    await callback.answer(f"Групу змінено на {new_group.upper()}!")

@dp.callback_query(F.data.startswith('sub_'))
async def handle_subgroup_filter(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    selected_sub = int(callback.data.split('_')[1])

    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "today", "week": 0}
    user_settings[chat_id]["sub"] = selected_sub

    mode = user_settings[chat_id].get("mode", "today")
    if mode == "full":
        await send_full_logic(callback.message, force_delete=False)
    else:
        await send_today_logic(callback.message, force_delete=False)

    await callback.answer("Фільтр підгрупи оновлено!")

@dp.callback_query(F.data.startswith('week_'))
async def handle_week_filter(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    selected_week = int(callback.data.split('_')[1])

    if chat_id not in user_settings:
        user_settings[chat_id] = {"group": "sb11", "sub": 0, "mode": "today", "week": 0}
    user_settings[chat_id]["week"] = selected_week

    mode = user_settings[chat_id].get("mode", "today")
    if mode == "full":
        await send_full_logic(callback.message, force_delete=False)
    else:
        await send_today_logic(callback.message, force_delete=False)

    await callback.answer("Фільтр тижня оновлено!")


# --- ЛОГИКА ОТПРАВКИ И ЗАМЕНЫ ---
async def send_today_logic(message: types.Message, force_delete=False):
    chat_id = message.chat.id
    settings = user_settings.get(chat_id, {"group": "sb11", "sub": 0, "week": 0})

    now = datetime.datetime.now()
    target_date = now

    if now.weekday() == 6:
        target_date = now + datetime.timedelta(days=1)

    today_index = target_date.weekday()
    today_name = ukrainian_days[today_index]

    calculated_week = get_week_number(target_date)
    fetch_week = calculated_week if settings["week"] == 0 else settings["week"]

    data = get_tntu_schedule(settings["group"], fetch_week)

    if "error" in data:
        await clear_old_messages(chat_id)
        sent = await message.answer(f"❌ Помилка: {data['error']}", reply_markup=ReplyKeyboardRemove())
        user_sent_messages[chat_id] = [sent.message_id]
        return

    times_data = data.get("понеділок", {}) if today_index == 5 else data.get(today_name, {})

    html_content = format_native_html_table(today_name, target_date, times_data, settings["sub"], settings["group"], settings["week"], show_buttons=True)

    old_msgs = user_sent_messages.get(chat_id, [])
    if force_delete:
        await clear_old_messages(chat_id)
        old_msgs = []

    if old_msgs:
        success = await edit_rich_message_raw(chat_id, old_msgs[0], html_content)
        if success:
            for msg_id in old_msgs[1:]:
                try:
                    await bot.delete_message(chat_id, msg_id)
                except Exception:
                    pass
            user_sent_messages[chat_id] = [old_msgs[0]]
        else:
            await clear_old_messages(chat_id)
            msg_id = await send_rich_message_raw(chat_id, html_content)
            if msg_id: user_sent_messages[chat_id] = [msg_id]
    else:
        msg_id = await send_rich_message_raw(chat_id, html_content)
        if msg_id: user_sent_messages[chat_id] = [msg_id]


async def send_full_logic(message: types.Message, force_delete=False):
    chat_id = message.chat.id
    settings = user_settings.get(chat_id, {"group": "sb11", "sub": 0, "week": 0})

    now = datetime.datetime.now()
    target_date = now

    if now.weekday() == 6:
        target_date = now + datetime.timedelta(days=1)

    calculated_week = get_week_number(target_date)
    fetch_week = calculated_week if settings["week"] == 0 else settings["week"]

    data = get_tntu_schedule(settings["group"], fetch_week)

    if "error" in data:
        await clear_old_messages(chat_id)
        sent = await message.answer(f"❌ Помилка: {data['error']}", reply_markup=ReplyKeyboardRemove())
        user_sent_messages[chat_id] = [sent.message_id]
        return

    old_msgs = user_sent_messages.get(chat_id, [])
    if force_delete:
        await clear_old_messages(chat_id)
        old_msgs = []

    new_ids = []
    for i in range(6):
        day_name = ukrainian_days[i]
        day_date = target_date - datetime.timedelta(days=target_date.weekday()) + datetime.timedelta(days=i)

        times_data = data.get("понеділок", {}) if i == 5 else data.get(day_name, {})

        html_content = format_native_html_table(day_name, day_date, times_data, settings["sub"], settings["group"], settings["week"], show_buttons=(i == 5))

        if i < len(old_msgs):
            success = await edit_rich_message_raw(chat_id, old_msgs[i], html_content)
            if success:
                new_ids.append(old_msgs[i])
            else:
                msg_id = await send_rich_message_raw(chat_id, html_content)
                if msg_id: new_ids.append(msg_id)
        else:
            msg_id = await send_rich_message_raw(chat_id, html_content)
            if msg_id: new_ids.append(msg_id)

    for msg_id in old_msgs[len(new_ids):]:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    user_sent_messages[chat_id] = new_ids


async def main():
    print("Бот запущено. Очікування підключення...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())