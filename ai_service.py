import logging
import uuid

import requests
from config import GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET

log = logging.getLogger("rhythm.ai")

AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


def _get_token() -> str | None:
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
        log.warning("GigaChat credentials not set")
        return None

    payload = "scope=GIGACHAT_API_PERS"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}",
    }
    try:
        response = requests.post(AUTH_URL, headers=headers, data=payload, verify=False, timeout=10)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        log.error(f"GigaChat auth error: {e}")
        return None


def _ask_gigachat(prompt: str, system_prompt: str = "Ты — полезный ассистент.") -> str | None:
    token = _get_token()
    if not token:
        return None

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }
    try:
        response = requests.post(API_URL, headers=headers, json=data, verify=False, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"GigaChat API error: {e}")
        return None


def split_steps_with_ai(text: str) -> str:
    sys_prompt = (
        "Ты — школьный психолог и эксперт по тайм-менеджменту. "
        "Разбей задачу ученика на 3-5 маленьких конкретных шагов. "
        "Ответь ТОЛЬКО списком шагов, разделенных символом '|'. Без лишнего текста. "
        "Пример: Найти материал|Составить план|Написать текст|Проверить ошибки"
    )
    res = _ask_gigachat(text, sys_prompt)
    if not res:
        return "Найти материал|Составить план|Написать основную часть|Проверить"
    
    res = res.replace("\n", "").replace("- ", "").strip()
    if "|" not in res:
        return "Найти материал|Составить план|Написать основную часть|Проверить"
    return res


def parse_homework_with_ai(text: str) -> tuple[str, str, str] | None:
    sys_prompt = (
        "Ты — парсер домашних заданий. Пользователь присылает текст задания из чата. "
        "Извлеки из него: Предмет, Суть задания, Дедлайн (если есть, в формате YYYY-MM-DD, если нет - 'Нет'). "
        "Ответь строго в формате: Предмет|Суть|Дедлайн. Без лишнего текста. "
        "Пример: Математика|Номера 45 и 46|2024-05-20"
    )
    res = _ask_gigachat(text, sys_prompt)
    if not res:
        return None
    
    parts = res.split("|")
    if len(parts) != 3:
        return None
    
    subject = parts[0].strip()
    title = parts[1].strip()
    deadline_raw = parts[2].strip()
    deadline = deadline_raw if deadline_raw != "Нет" and "-" in deadline_raw else None
    
    return subject, title, deadline