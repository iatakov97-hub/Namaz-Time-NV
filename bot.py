import asyncio
import csv
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─── Настройки ───────────────────────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
TZ = pytz.timezone("Asia/Yekaterinburg")  # UTC+5, Нижневартовск

PRAYER_NAMES = {
    "fajr":    "🌙 Фаджр",
    "sunrise": "🌅 Восход",
    "dhuhr":   "☀️ Зухр",
    "asr":     "🌤 Аср",
    "maghrib": "🌇 Магриб",
    "isha":    "🌃 Иша",
}

PRAYER_KEYS = ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]

DATA_FILE = Path(__file__).parent / "prayer_times_nizhnevartovsk.csv"
USERS_FILE = Path(__file__).parent / "users.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Постоянная клавиатура с кнопками ────────────────────────────────────────
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🕐 Следующий намаз", "📅 Намазы на сегодня"],
        ["🗓 Расписание на месяц", "🔔 Уведомления"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ─── Загрузка данных ─────────────────────────────────────────────────────────
def load_prayer_times() -> dict:
    times = {}
    with open(DATA_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m, d = int(row["month"]), int(row["day"])
            times.setdefault(m, {})[d] = {k: row[k] for k in PRAYER_KEYS}
    return times

PRAYER_TIMES = load_prayer_times()

# ─── Хранилище пользователей ─────────────────────────────────────────────────
def load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def get_user(users: dict, uid: int) -> dict:
    key = str(uid)
    if key not in users:
        users[key] = {
            "notifications": True,
            "prayers": {k: True for k in PRAYER_KEYS},
            "notify_start": True,
            "notify_15": True,
        }
        save_users(users)
    return users[key]

# ─── Вспомогательные функции ─────────────────────────────────────────────────
def now_local() -> datetime:
    return datetime.now(TZ)

def parse_time(time_str: str, date: datetime) -> datetime:
    h, m = map(int, time_str.split(":"))
    return date.replace(hour=h, minute=m, second=0, microsecond=0)

def get_day_schedule(month: int, day: int) -> dict | None:
    return PRAYER_TIMES.get(month, {}).get(day)

def format_day_schedule(schedule: dict, date: datetime) -> str:
    lines = [f"🕌 *Намазы на {date.strftime('%d.%m')}*\n"]
    for key in PRAYER_KEYS:
        lines.append(f"{PRAYER_NAMES[key]}: *{schedule[key]}*")
    return "\n".join(lines)

def get_next_prayer(schedule: dict, now: datetime):
    for key in PRAYER_KEYS:
        t = parse_time(schedule[key], now)
        if t > now:
            return key, t
    return None

def time_until(target: datetime) -> str:
    delta = target - now_local()
    total = int(delta.total_seconds())
    if total <= 0:
        return "уже наступил"
    h, rem = divmod(total, 3600)
    m = rem // 60
    if h > 0:
        return f"{h} ч {m} мин"
    return f"{m} мин"

# ─── Команды бота ────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    get_user(users, update.effective_user.id)
    text = (
        "🕌 *Бот времён намазов — Нижневартовск*\n\n"
        "Используй кнопки внизу или команды:\n"
        "/today — намазы на сегодня\n"
        "/next — до следующего намаза\n"
        "/month — расписание на месяц\n"
        "/notifications — настройки уведомлений"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_local()
    schedule = get_day_schedule(now.month, now.day)
    if not schedule:
        await update.message.reply_text("Нет данных на сегодня.", reply_markup=MAIN_KEYBOARD)
        return

    text = format_day_schedule(schedule, now)

    nxt = get_next_prayer(schedule, now)
    if nxt:
        key, dt = nxt
        text += f"\n\n⏳ Следующий: {PRAYER_NAMES[key]} через *{time_until(dt)}*"
    else:
        text += "\n\n✅ Все намазы на сегодня совершены"

    if now.weekday() == 4:
        text += f"\n\n🕌 *Сегодня пятница!* Не забудь про Джума-намаз в {schedule['dhuhr']}"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def cmd_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_local()
    schedule = get_day_schedule(now.month, now.day)
    if not schedule:
        await update.message.reply_text("Нет данных.", reply_markup=MAIN_KEYBOARD)
        return

    nxt = get_next_prayer(schedule, now)
    if nxt:
        key, dt = nxt
        text = (
            f"⏳ *Следующий намаз*\n\n"
            f"{PRAYER_NAMES[key]}: *{schedule[key]}*\n"
            f"Осталось: *{time_until(dt)}*"
        )
    else:
        tomorrow = now + timedelta(days=1)
        sched_tmr = get_day_schedule(tomorrow.month, tomorrow.day)
        if sched_tmr:
            first_key = PRAYER_KEYS[0]
            first_t = parse_time(sched_tmr[first_key], tomorrow)
            text = (
                f"✅ Все намазы на сегодня совершены\n\n"
                f"Первый намаз завтра:\n"
                f"{PRAYER_NAMES[first_key]}: *{sched_tmr[first_key]}*\n"
                f"Осталось: *{time_until(first_t)}*"
            )
        else:
            text = "✅ Все намазы на сегодня совершены."

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_local()
    month_data = PRAYER_TIMES.get(now.month, {})
    if not month_data:
        await update.message.reply_text("Нет данных на этот месяц.", reply_markup=MAIN_KEYBOARD)
        return

    month_names = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                   "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]

    lines = [f"🗓 *{month_names[now.month]}* — расписание намазов\n"]
    lines.append("`День  Фаджр  Зухр   Аср    Магриб Иша`")

    for day in sorted(month_data.keys()):
        s = month_data[day]
        marker = "▶️" if day == now.day else "  "
        lines.append(
            f"`{marker}{day:02d}  {s['fajr']}  {s['dhuhr']}  {s['asr']}  {s['maghrib']}  {s['isha']}`"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        mid = len(lines) // 2
        await update.message.reply_text("\n".join(lines[:mid]), parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
        await update.message.reply_text("\n".join(lines[mid:]), parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

# ─── Настройки уведомлений ───────────────────────────────────────────────────
def build_notifications_keyboard(user: dict) -> InlineKeyboardMarkup:
    notif_on = user["notifications"]
    rows = []
    status = "✅ Вкл" if notif_on else "❌ Выкл"
    rows.append([InlineKeyboardButton(f"Уведомления: {status}", callback_data="toggle_all")])

    if notif_on:
        rows.append([InlineKeyboardButton("─── Намазы ───", callback_data="noop")])
        for key in PRAYER_KEYS:
            enabled = user["prayers"].get(key, True)
            icon = "✅" if enabled else "❌"
            rows.append([InlineKeyboardButton(f"{icon} {PRAYER_NAMES[key]}", callback_data=f"toggle_{key}")])

        rows.append([InlineKeyboardButton("─── Тип ───", callback_data="noop")])
        s_on = "✅" if user.get("notify_start", True) else "❌"
        f_on = "✅" if user.get("notify_15", True) else "❌"
        rows.append([InlineKeyboardButton(f"{s_on} При начале намаза", callback_data="toggle_start")])
        rows.append([InlineKeyboardButton(f"{f_on} За 15 мин до конца", callback_data="toggle_15")])

    return InlineKeyboardMarkup(rows)

async def cmd_notifications(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user = get_user(users, update.effective_user.id)
    keyboard = build_notifications_keyboard(user)
    await update.message.reply_text(
        "🔔 *Настройки уведомлений*\nВыбери, о каких намазах напоминать:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    users = load_users()
    user = get_user(users, query.from_user.id)
    data = query.data

    if data == "noop":
        return
    elif data == "toggle_all":
        user["notifications"] = not user["notifications"]
    elif data == "toggle_start":
        user["notify_start"] = not user.get("notify_start", True)
    elif data == "toggle_15":
        user["notify_15"] = not user.get("notify_15", True)
    elif data.startswith("toggle_"):
        key = data.replace("toggle_", "")
        if key in PRAYER_KEYS:
            user["prayers"][key] = not user["prayers"].get(key, True)

    save_users(users)
    keyboard = build_notifications_keyboard(user)
    await query.edit_message_reply_markup(reply_markup=keyboard)

# ─── Обработчик кнопок клавиатуры ────────────────────────────────────────────
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🕐 Следующий намаз":
        await cmd_next(update, ctx)
    elif text == "📅 Намазы на сегодня":
        await cmd_today(update, ctx)
    elif text == "🗓 Расписание на месяц":
        await cmd_month(update, ctx)
    elif text == "🔔 Уведомления":
        await cmd_notifications(update, ctx)

# ─── Планировщик уведомлений ─────────────────────────────────────────────────
async def send_prayer_notifications(app: Application):
    now = now_local()
    schedule = get_day_schedule(now.month, now.day)
    if not schedule:
        return

    users = load_users()

    for key in PRAYER_KEYS:
        prayer_dt = parse_time(schedule[key], now)
        diff_minutes = (prayer_dt - now).total_seconds() / 60

        for uid_str, user in users.items():
            if not user.get("notifications", True):
                continue
            if not user["prayers"].get(key, True):
                continue

            uid = int(uid_str)

            if user.get("notify_start", True) and abs(diff_minutes) < 0.5:
                msg = f"🕌 *Время намаза!*\n\n{PRAYER_NAMES[key]}: *{schedule[key]}*"
                if now.weekday() == 4 and key == "dhuhr":
                    msg += "\n\n🕌 *Не забудь про Джума-намаз!*"
                try:
                    await app.bot.send_message(uid, msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Ошибка отправки {uid}: {e}")

            if user.get("notify_15", True):
                idx = PRAYER_KEYS.index(key)
                if idx < len(PRAYER_KEYS) - 1:
                    next_key = PRAYER_KEYS[idx + 1]
                    next_dt = parse_time(schedule[next_key], now)
                    mins_to_next = (next_dt - now).total_seconds() / 60
                    if 14.5 <= mins_to_next <= 15.5:
                        msg = (
                            f"⏰ *Осталось 15 минут!*\n\n"
                            f"Время {PRAYER_NAMES[key]} заканчивается.\n"
                            f"Следующий — {PRAYER_NAMES[next_key]} в *{schedule[next_key]}*"
                        )
                        try:
                            await app.bot.send_message(uid, msg, parse_mode="Markdown")
                        except Exception as e:
                            logger.error(f"Ошибка отправки {uid}: {e}")

    if now.weekday() == 4 and now.hour == 12 and now.minute == 0:
        dhuhr_time = schedule.get("dhuhr", "")
        for uid_str, user in users.items():
            if not user.get("notifications", True):
                continue
            try:
                await app.bot.send_message(
                    int(uid_str),
                    f"🕌 *Джума Мубарак!*\n\nСегодня пятница.\nЗухр (Джума) в *{dhuhr_time}*",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Ошибка Джума {uid_str}: {e}")

# ─── Запуск ──────────────────────────────────────────────────────────────────
async def post_init(app: Application):
    """Устанавливает меню команд в Telegram."""
    await app.bot.set_my_commands([
        BotCommand("today",         "📅 Намазы на сегодня"),
        BotCommand("next",          "🕐 Следующий намаз"),
        BotCommand("month",         "🗓 Расписание на месяц"),
        BotCommand("notifications", "🔔 Настройки уведомлений"),
        BotCommand("start",         "🏠 Главное меню"),
    ])

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("month", cmd_month))
    app.add_handler(CommandHandler("notifications", cmd_notifications))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(send_prayer_notifications, "cron", second=0, args=[app])
    scheduler.start()

    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
