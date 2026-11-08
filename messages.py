import logging

from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

import ai_service
import database as db
import excel_parser
import texts as T
from bot import (
    bot,
    format_schedule,
    get_menu,
    new_code,
    new_id,
)
from states import clear_state, get_state, set_state

log = logging.getLogger("rhythm.messages")


SUBJECT_KEYWORDS = {
    "матем": "Математика", "алгебр": "Алгебра", "геометр": "Геометрия",
    "русск": "Русский язык", "литер": "Литература", "истор": "История",
    "физик": "Физика", "хими": "Химия", "биолог": "Биология",
    "англ": "Английский", "информ": "Информатика", "геогр": "География",
    "обществ": "Обществознание",
}


def guess_subject(text: str) -> str:
    low = text.lower()
    for key, name in SUBJECT_KEYWORDS.items():
        if key in low:
            return name
    return "Общее"


def new_code_safe() -> str:
    for _ in range(10):
        code = new_code()
        if not db.get_class_by_code(code):
            return code
    return new_code()


async def handle_join_by_code(message, user: dict, code: str) -> None:
    cls = db.get_class_by_code(code)
    if not cls:
        await message.send(T.JOIN_NOT_FOUND)
        return
    if user["class_id"]:
        await message.send(T.JOIN_ALREADY)
        return
    if user["role"] != "student":
        await message.send(T.JOIN_ONLY_STUDENT)
        return
    existing = db.get_user_request(user["id"], cls["id"])
    if existing and existing["status"] == "wait":
        await message.send(T.JOIN_ALREADY_WAIT)
        return
    db.create_request(new_id(), cls["id"], user["id"])
    await message.send(T.JOIN_SENT.format(name=cls["name"]))
    teacher_id = db.get_teacher_of_class(cls["id"])
    if teacher_id:
        try:
            await bot.send_message(
                chat_id=int(teacher_id),
                text=f"📥 Новая заявка в класс «{cls['name']}» от {user['name']}.\n"
                     f"Откройте /menu → «Заявки в класс».",
            )
        except Exception as e:
            log.warning("Не удалось уведомить учителя %s: %s", teacher_id, e)


async def handle_state(message, user: dict, user_id: str, text: str, state: dict) -> None:
    action = state.get("action")
    if not text and action != "wait_excel_file":
        await message.send(T.EMPTY_INPUT)
        return

    if action == "wait_dir":
        target = db.get_user(text)
        if not target:
            await message.send(T.USER_NOT_FOUND)
            return
        db.update_user(text, "role", "director")
        clear_state(user_id)
        await message.send(T.ADMIN_DIRECTOR_OK.format(name=target["name"]))

    elif action == "wait_school":
        school_id = new_id()
        db.create_school(school_id, text, user_id)
        db.update_user(user_id, "school_id", school_id)
        clear_state(user_id)
        await message.send(T.DIR_SCHOOL_OK.format(name=text))

    elif action == "wait_teacher":
        target = db.get_user(text)
        if not target:
            await message.send(T.USER_NOT_FOUND)
            return
        db.update_user(text, "role", "teacher")
        if user["school_id"]:
            db.update_user(text, "school_id", user["school_id"])
        clear_state(user_id)
        await message.send(T.DIR_TEACHER_OK.format(name=target["name"]))

    elif action == "wait_zavuch":
        target = db.get_user(text)
        if not target:
            await message.send(T.USER_NOT_FOUND)
            return
        db.update_user(text, "role", "zavuch")
        if user["school_id"]:
            db.update_user(text, "school_id", user["school_id"])
        clear_state(user_id)
        await message.send(T.DIR_ZAVUCH_OK.format(name=target["name"]))

    elif action == "wait_teacher_id_for_class":
        class_id = state.get("class_id")
        cls = db.get_class_by_id(class_id)
        if not cls:
            clear_state(user_id)
            await message.send("Класс не найден.")
            return
            
        target = db.get_user(text)
        if not target:
            await message.send(T.USER_NOT_FOUND)
            return
            
        if target["role"] not in ["teacher", "student"]:
            await message.send("Этот пользователь не может быть учителем (возможно, он родитель или администратор).")
            return
            
        if target["role"] == "student":
            db.update_user(text, "role", "teacher")
            
        if target["class_id"] and target["class_id"] != class_id:
            old_cls = db.get_class_by_id(target["class_id"])
            old_name = old_cls["name"] if old_cls else "другому"
            await message.send(T.TEACHER_ALREADY_IN_CLASS.format(name=old_name))
            return
            
        db.update_user(text, "class_id", class_id)
        db.add_member(class_id, text, "teacher")
        clear_state(user_id)
        await message.send(T.TEACHER_ASSIGNED_OK.format(name=target["name"], cls_name=cls["name"]))
        
        b = InlineKeyboardBuilder()
        b.row(CallbackButton(text="🔙 К списку классов", payload="admin_classes"))
        await message.send("Что дальше?", attachments=[b.as_markup()])

    elif action == "wait_fire":
        teacher = db.get_user(text)
        if not teacher or teacher["role"] != "teacher":
            await message.send(T.DIR_TEACHER_NOT_FOUND)
            return
        db.update_user(text, "role", "student")
        db.update_user(text, "class_id", None)
        db.remove_teacher_memberships(text)
        clear_state(user_id)
        await message.send(T.DIR_FIRE_OK.format(name=teacher["name"]))

    elif action == "wait_excel_file":
        attachments = message.message.body.attachments if message.message.body else None
        if not attachments:
            await message.send("Пожалуйста, прикрепите Excel-файл (.xlsx).")
            return
        
        attachment = attachments[0]
        
        file_url = None
        file_name = ""
        
        if hasattr(attachment, "payload") and attachment.payload:
            payload = attachment.payload
            if hasattr(payload, "url") and payload.url:
                file_url = payload.url
            if hasattr(attachment, "filename") and attachment.filename:
                file_name = attachment.filename
            
        if not file_url:
            await message.send("Не удалось получить ссылку на файл. Попробуйте отправить файл еще раз.")
            return
            
        if file_name and not file_name.lower().endswith(".xlsx"):
            await message.send("Это не похоже на Excel-файл. Прикрепите файл с расширением .xlsx")
            return
        
        await message.send("⏳ Скачиваю и обрабатываю файл...")
        try:
            import requests
            response = requests.get(file_url, timeout=15)
            response.raise_for_status()
            file_bytes = response.content
        except Exception as e:
            log.error("Не удалось скачать файл: %s", e)
            await message.send("Ошибка при скачивании файла. Попробуйте ещё раз.")
            clear_state(user_id)
            return

        try:
            parsed_data = excel_parser.parse_excel_schedule(file_bytes)
        except Exception as e:
            log.error("Ошибка парсинга Excel: %s", e)
            await message.send("Не удалось распознать структуру файла. Убедитесь, что это стандартная таблица расписания.")
            clear_state(user_id)
            return

        if not parsed_data:
            await message.send("В файле не найдено расписания. Проверьте формат.")
            clear_state(user_id)
            return

        school_id = user["school_id"]
        if not school_id:
            await message.send("У вас не привязана школа. Обратитесь к директору.")
            clear_state(user_id)
            return

        created_classes = 0
        updated_schedules = 0
        
        for class_name, lessons in parsed_data.items():
            cls = db.get_class_by_name_and_school(class_name, school_id)
            
            if not cls:
                class_id = new_id()
                code = new_code_safe()
                db.create_class(class_id, school_id, class_name, code)
                created_classes += 1
            else:
                class_id = cls["id"]
                db.clear_schedule(class_id)
            
            for lesson in lessons:
                db.add_lesson(class_id, lesson["day"], lesson["time"], lesson["subject"], new_id())
            updated_schedules += 1

        clear_state(user_id)
        await message.send(T.ZAVUCH_EXCEL_OK.format(
            classes=len(parsed_data),
            created=created_classes,
            updated=updated_schedules
        ))

    elif action == "wait_new_class":
        class_id = new_id()
        code = new_code_safe()
        db.create_class(class_id, user["school_id"], text, code)
        db.update_user(user_id, "class_id", class_id)
        db.add_member(class_id, user_id, "teacher")
        clear_state(user_id)
        await message.send(T.TEACH_CLASS_OK.format(name=text, code=code))

    elif action == "wait_sched_day":
        if not text.isdigit() or not (1 <= int(text) <= 6):
            await message.send(T.TEACH_DAY_BAD)
            return
        set_state(user_id, {"action": "wait_sched_time", "day": int(text) - 1})
        await message.send(T.TEACH_ASK_TIME)

    elif action == "wait_sched_time":
        if ":" not in text or len(text) > 5:
            await message.send(T.TEACH_TIME_BAD)
            return
        set_state(user_id, {
            "action": "wait_sched_subject",
            "day": state["day"], "time": text,
        })
        await message.send(T.TEACH_ASK_SUBJECT)

    elif action == "wait_sched_subject":
        if not user["class_id"]:
            clear_state(user_id)
            await message.send("У вас нет класса. Начните заново.")
            return
        db.add_lesson(user["class_id"], state["day"], state["time"], text, new_id())
        clear_state(user_id)
        await message.send(T.TEACH_LESSON_OK)

    elif action == "wait_hw_text":
        if not user["class_id"]:
            clear_state(user_id)
            await message.send("У вас нет класса.")
            return
            
        await message.send("⏳ Анализирую текст домашки с помощью ИИ...")
        parsed = ai_service.parse_homework_with_ai(text)
        
        if parsed:
            subject, title, deadline = parsed
            count = db.add_homework_to_class(user["class_id"], subject, title, deadline)
            clear_state(user_id)
            if count > 0:
                msg = f"✅ Домашка распознана и разослана {count} ученикам.\n\n"
                msg += f"Предмет: {subject}\nЗадание: {title}\n"
                if deadline:
                    msg += f"Дедлайн: {deadline}"
                await message.send(msg)
            else:
                await message.send("В классе нет учеников, задача никому не ушла.")
        else:
            clear_state(user_id)
            await message.send("Не удалось распознать домашку. Попробуйте написать текст понятнее.")

    elif action == "wait_task":
        await message.send("⏳ Разбиваю задачу на шаги с помощью ИИ...")
        steps = ai_service.split_steps_with_ai(text)
        subject = guess_subject(text)
        db.add_task(new_id(), user_id, text, subject, steps)
        clear_state(user_id)
        pretty = "\n".join(f"  • {s}" for s in steps.split("|"))
        await message.send(T.STUD_TASK_OK.format(subject=subject, steps=pretty))

    elif action == "wait_child_link":
        child = db.get_user(text)
        if not child or child["role"] != "student":
            await message.send(T.PARENT_CHILD_NOT_FOUND)
            return
        db.update_user(user_id, "child_id", text)
        clear_state(user_id)
        await message.send(T.PARENT_CHILD_OK.format(name=child["name"]))

    elif action == "wait_parent_task":
        if not user["child_id"]:
            clear_state(user_id)
            await message.send(T.PARENT_NEED_CHILD)
            return
        await message.send("⏳ Разбиваю задачу на шаги...")
        steps = ai_service.split_steps_with_ai(text)
        db.add_task(new_id(), user["child_id"], text, "От родителя", steps)
        clear_state(user_id)
        await message.send(T.PARENT_TASK_OK)

    else:
        clear_state(user_id)
        await message.send(T.UNKNOWN)


def register(dp) -> None:

    @dp.message_created()
    async def on_msg(message):
        text = ""
        if message.message.body and message.message.body.text:
            text = message.message.body.text.strip()
            
        _, user_id = message.get_ids()
        user_id = str(user_id)
        user = db.get_user(user_id)

        if text == "/start":
            is_new = not user
            if is_new:
                name = message.from_user.first_name if message.from_user else "Друг"
                db.create_user(user_id, name)
                user = db.get_user(user_id)

            payload = db.pop_pending_start(user_id)
            if payload:
                if payload.startswith("school"):
                    code = payload[len("school"):].upper()
                    cls = db.get_class_by_code(code)
                    if cls:
                        await message.send(
                            T.JOIN_FROM_LINK.format(name=cls["name"])
                        )
                    else:
                        await message.send(T.JOIN_FROM_LINK_BAD)
                        return
                    await handle_join_by_code(message, user, code)
                    return
                else:
                    await message.send(T.JOIN_FROM_LINK_BAD)

            if is_new:
                b = InlineKeyboardBuilder()
                b.row(CallbackButton(text="🎓 Я ученик", payload="set_student"))
                b.row(CallbackButton(text="👨‍👩‍👧 Я родитель", payload="set_parent"))
                await message.send(T.WELCOME_NEW, attachments=[b.as_markup()])
            else:
                await message.send(T.WELCOME_BACK)
            return

        if not user:
            await message.send(T.NEED_START)
            return

        state = get_state(user_id)
        
        if state and state.get("action") == "wait_excel_file":
            await handle_state(message, user, user_id, text, state)
            return

        if text in ("/help", "помощь", "Помощь"):
            await message.send(T.HELP)
            return

        if text == "/menu":
            clear_state(user_id)
            await message.send(T.MENU, attachments=[get_menu(user)])
            return
            
        if text == "/cancel":
            clear_state(user_id)
            await message.send(T.CANCELLED)
            return

        if text in ("/профиль", "профиль"):
            school = db.get_school_name(user["school_id"]) or "Нет"
            cls = db.get_class_name(user["class_id"]) or "Нет"
            await message.send(T.profile_text(
                user["name"], user["id"], user["role"],
                school, cls, user["points"], user["ovz"],
            ))
            return

        if text in ("расписание", "/расписание"):
            if not user["class_id"]:
                await message.send(
                    "Вы пока не в классе. Получите у учителя ссылку или код "
                    "и напишите: школа КОД"
                )
                return
            await message.send(format_schedule(db.get_schedule(user["class_id"])))
            return

        if text.lower().startswith("школа "):
            code = text.split(" ", 1)[1].strip().upper()
            await handle_join_by_code(message, user, code)
            return

        if state:
            await handle_state(message, user, user_id, text, state)
            return

        await message.send(T.UNKNOWN)