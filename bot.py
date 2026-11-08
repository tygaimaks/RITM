import logging
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from maxapi import Bot, Dispatcher
from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, BOT_USERNAME, MAIN_ADMIN_ID

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
log = logging.getLogger("rhythm")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def new_id() -> str:
    return str(uuid.uuid4())[:6]


def new_code() -> str:
    return str(uuid.uuid4())[:6].upper()


def class_link(invite_code: str) -> str:
    return f"https://max.ru/{BOT_USERNAME}?start=school{invite_code}"


def format_schedule(sched) -> str:
    if not sched:
        return (
            "📅 Расписание пока пустое.\n\n"
            "Если вы учитель — добавьте уроки через /menu → «Добавить расписание»."
        )
    text = "📅 Расписание класса:\n\n"
    for row in sched:
        text += f"{DAYS[row['day_of_week']]} | {row['time']} — {row['subject']}\n"
    return text


def get_menu(user: dict):
    b = InlineKeyboardBuilder()
    role = user["role"]

    if user["id"] == MAIN_ADMIN_ID:
        b.row(CallbackButton(text="👑 Назначить директора", payload="admin_dir"))

    if role in ["director", "zavuch"]:
        b.row(CallbackButton(text="📚 Классы и учителя", payload="admin_classes"))
        
    if role == "director":
        b.row(CallbackButton(text="🏫 Создать школу", payload="dir_school"))
        b.row(CallbackButton(text="👨‍🏫 Добавить учителя", payload="dir_teacher"))
        b.row(CallbackButton(text="📑 Назначить завуча", payload="dir_zavuch"))
        b.row(CallbackButton(text="❌ Уволить учителя", payload="dir_fire"))

    if role == "zavuch":
        b.row(CallbackButton(text="👨‍🏫 Добавить учителя", payload="dir_teacher"))
        b.row(CallbackButton(text="📊 Загрузить расписание (Excel)", payload="zavuch_excel"))

    if role == "teacher":
        b.row(CallbackButton(text="📚 Создать класс", payload="teach_class"))
        b.row(CallbackButton(text="🔗 Код и ссылка для учеников", payload="teach_codes"))
        b.row(CallbackButton(text="📅 Добавить урок в расписание", payload="teach_add_sched"))
        b.row(CallbackButton(text="👀 Посмотреть расписание", payload="teach_view_sched"))
        b.row(CallbackButton(text="📥 Заявки в класс", payload="teach_reqs"))
        b.row(CallbackButton(text="👥 Мои ученики", payload="teach_studs"))
        b.row(CallbackButton(text="🗑️ Удалить урок", payload="teach_del_sched"))
        b.row(CallbackButton(text="📝 Задать домашку классу", payload="teach_hw"))

    if role == "student":
        b.row(CallbackButton(text="📝 Мои задачи", payload="stud_tasks"))
        b.row(CallbackButton(text="➕ Добавить задачу", payload="stud_add"))
        b.row(CallbackButton(text="📅 Расписание", payload="stud_sched"))
        b.row(CallbackButton(text="🧩 Спокойный режим", payload="stud_ovz"))

    if role == "parent":
        b.row(CallbackButton(text="👨‍👩‍👧 Привязать ребёнка", payload="parent_link"))
        b.row(CallbackButton(text="📋 Прогресс ребёнка", payload="parent_progress"))
        b.row(CallbackButton(text="➕ Задать задачу ребёнку", payload="parent_add_task"))

    b.row(CallbackButton(text="❓ Помощь", payload="help"))
    b.row(CallbackButton(text="🏠 Главное меню", payload="menu"))
    return b.as_markup()