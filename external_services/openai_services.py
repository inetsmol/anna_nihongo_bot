"""
Модуль для работы с OpenAI API.

Особенности:
- используется единый асинхронный HTTP-клиент (connection pooling)
- используется единый AsyncOpenAI-клиент
- подходит для async Telegram-ботов (aiogram / pyrogram / fastapi)
"""

from __future__ import annotations

import os
import asyncio
from typing import Optional

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

# -----------------------------------------------------------------------------
# Конфигурация
# -----------------------------------------------------------------------------

load_dotenv()

LOCATION: Optional[str] = os.getenv("LOCATION")
PROXY_URL: Optional[str] = os.getenv("PROXY_URL")

# Используем одну модель для текстовых задач
GPT_MODEL = "gpt-5-nano"

# -----------------------------------------------------------------------------
# Клиенты (создаются один раз на весь процесс)
# -----------------------------------------------------------------------------

_http_client = httpx.AsyncClient(
    proxy=PROXY_URL or None,
    timeout=httpx.Timeout(30.0),
)

openai_client = AsyncOpenAI(http_client=_http_client)

# -----------------------------------------------------------------------------
# API функции
# -----------------------------------------------------------------------------

async def openai_text_to_speech(text: str):
    """
    Генерация аудио (TTS) из текста.

    :param text: Текст для озвучивания
    :return: Ответ OpenAI API с аудиоданными
    """
    return await openai_client.audio.speech.create(
        model="tts-1-hd",
        voice="nova",
        speed=0.85,
        response_format="opus",
        input=text,
    )


async def openai_gpt_add_space(text: str) -> str:
    """
    Добавляет пробелы между словами (актуально для японского языка).

    Если LOCATION != 'ja-JP', возвращает текст без изменений.

    :param text: Исходный текст
    :return: Текст с добавленными пробелами
    """
    if LOCATION != "ja-JP":
        return text

    response = await openai_client.responses.create(
        model=GPT_MODEL,
        input=(
            "Add spaces between words in the following text. "
            "Return only the spaced text:\n\n"
            f"{text}"
        ),
    )
    return response.output_text


async def openai_gpt_translate(text: str) -> str:
    """
    Переводит текст на русский язык.

    :param text: Исходный текст
    :return: Перевод
    """
    response = await openai_client.responses.create(
        model=GPT_MODEL,
        input=(
            "Translate the following text into Russian. "
            "Return only the translation:\n\n"
            f"{text}"
        ),
    )
    return response.output_text


async def openai_gpt_get_phrase_from_text(text: str) -> str:
    """
    Извлекает 5 фраз (2–3 слова), содержащих глаголы и прилагательные,
    без имен собственных, и переводит их на русский язык.

    Формат ответа:
    ФРАЗА – перевод

    :param text: Исходный текст
    :return: Строка с фразами и переводами
    """
    response = await openai_client.responses.create(
        model=GPT_MODEL,
        input=(
            "Выбери из текста 5 фраз из 2–3 слов, содержащих "
            "прилагательные и глаголы. "
            "Фразы не должны содержать имена собственные.\n\n"
            f"Текст: {text}\n\n"
            "Составь пары «фраза – перевод на русский». "
            "В ответе пришли только пары.\n"
            "Пример: たくさん降っています - много идет"
        ),
    )
    return response.output_text

# -----------------------------------------------------------------------------
# Завершение работы (важно для корректного shutdown)
# -----------------------------------------------------------------------------

async def close_openai_client() -> None:
    """
    Корректно закрывает HTTP-клиент.
    Вызывать при завершении приложения.
    """
    await _http_client.aclose()

# -----------------------------------------------------------------------------
# Локальный тест
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    LOCATION = 'ja-JP'
    async def _test() -> None:
        result = await openai_gpt_add_space(
            "状況を話して苦情を言い最後にリクエストを言う"
        )
        print(result)

        await close_openai_client()

    asyncio.run(_test())