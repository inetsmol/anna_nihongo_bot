import asyncio
import logging
from typing import Optional, Tuple

from aiogram.types import BufferedInputFile

from external_services.google_cloud_services import google_text_to_speech
from external_services.openai_services import openai_gpt_add_space, openai_gpt_translate

logger = logging.getLogger(__name__)


async def process_new_phrase(text_phrase: str) -> Tuple[str, str, Optional[BufferedInputFile], Optional[str]]:
    """
    Processes a new phrase by adding spaces, translating, and generating speech concurrently.

    Args:
        text_phrase: The input text phrase.

    Returns:
        A tuple containing:
        - spaced_phrase: The phrase with spaces added (or original if failed).
        - translation: The translation (or original if failed).
        - voice: BufferedInputFile with audio content (or None if failed).
        - voice_id: None (placeholder as it's generated after sending message).
    """

    async def safe_add_space():
        try:
            return await openai_gpt_add_space(text_phrase)
        except Exception as e:
            logger.error(f'Error adding spaces: {e}')
            return text_phrase

    async def safe_translate():
        try:
            return await openai_gpt_translate(text_phrase)
        except Exception as e:
            logger.error(f'Error translating: {e}')
            return text_phrase

    async def safe_tts():
        try:
            tts_result = await google_text_to_speech(text_phrase)
            if tts_result and tts_result.audio_content:
                return BufferedInputFile(tts_result.audio_content, filename="voice_tts.ogg")
            return None
        except Exception as e:
            logger.error(f'Error generating TTS: {e}')
            return None

    # Run tasks concurrently
    results = await asyncio.gather(
        safe_add_space(),
        safe_translate(),
        safe_tts()
    )

    spaced_phrase, translation, voice = results
    return spaced_phrase, translation, voice, None
