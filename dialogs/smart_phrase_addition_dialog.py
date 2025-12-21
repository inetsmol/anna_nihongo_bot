import base64
import logging
import os

from aiogram.types import Message, BufferedInputFile, CallbackQuery
from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.input import TextInput, ManagedTextInput
from aiogram_dialog.widgets.kbd import Group, Cancel, Back, Button
from aiogram_dialog.widgets.text import Multi
from dotenv import load_dotenv

from bot_init import bot
from external_services.google_cloud_services import google_text_to_speech
from external_services.kandinsky import generate_image
from external_services.openai_services import openai_gpt_add_space, openai_gpt_translate
from models import Phrase, Category, AudioFile, User
from services.i18n_format import I18NFormat, I18N_FORMAT_KEY
from states import SmartPhraseAdditionSG, EditPhraseSG


logger = logging.getLogger('default')


async def get_data(dialog_manager: DialogManager, **kwargs):
    category_id = dialog_manager.start_data.get("category_id")
    category = await Category.get_or_none(id=category_id)
    dialog_manager.dialog_data['category_id'] = category_id
    dialog_manager.dialog_data['category'] = category.name
    return dialog_manager.dialog_data


async def get_summary_data(dialog_manager: DialogManager, **kwargs):
    return dialog_manager.dialog_data


async def text_phrase_input(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager,
                            text_phrase: str) -> None:
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    if len(text_phrase) >= 150:
        await message.answer(i18n_format('sentence-too-long'))
    else:
        phrase = await Phrase.get_or_none(text_phrase=text_phrase, user_id=message.from_user.id)
        if phrase:
            await bot.send_message(message.chat.id, i18n_format("already-added-this-phrase"))
        else:
            try:
                spaced_phrase = await openai_gpt_add_space(text_phrase)
            except Exception as e:
                logger.error('Ошибка при попытке добавления пробелов: %s', e)
                spaced_phrase = text_phrase
            try:
                translation = await openai_gpt_translate(text_phrase)
            except Exception as e:
                logger.error('Ошибка при попытке перевода: %s', e)
                translation = text_phrase

            try:
                text_to_speech = await google_text_to_speech(text_phrase)
                voice = BufferedInputFile(text_to_speech.audio_content, filename="voice_tts.ogg")
            except Exception as e:
                logger.error('Ошибка при попытке генерации голоса: %s', e)
                voice = None
            if voice:
                i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
                msg = await message.answer_voice(voice=voice, caption=i18n_format("voice-acting"))
                voice_id = msg.voice.file_id
            else:
                voice_id = None

            dialog_manager.dialog_data["category_id"] = dialog_manager.start_data["category_id"]
            dialog_manager.dialog_data["text_phrase"] = text_phrase
            dialog_manager.dialog_data["spaced_phrase"] = spaced_phrase
            dialog_manager.dialog_data["translation"] = translation
            dialog_manager.dialog_data["prompt"] = translation
            dialog_manager.dialog_data["audio_tg_id"] = voice_id
            dialog_manager.dialog_data["comment"] = ''

            await dialog_manager.next()


async def save_phrase_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    category = await Category.get_or_none(id=dialog_manager.start_data["category_id"])
    user_id = dialog_manager.event.from_user.id
    user = await User.get_or_none(id=user_id)
    text_phrase = dialog_manager.dialog_data["text_phrase"]
    voice_id = dialog_manager.dialog_data["audio_tg_id"]
    phrase = Phrase(
        category=category,
        user=user,
        text_phrase=text_phrase,
        audio_id=voice_id,
    )
    if dialog_manager.dialog_data.get("translation"):
        phrase.translation = dialog_manager.dialog_data["translation"]
    if dialog_manager.dialog_data.get("image_id"):
        phrase.image_id = dialog_manager.dialog_data.get("image_id")
    if dialog_manager.dialog_data.get("comment"):
        phrase.comment = dialog_manager.dialog_data.get("comment")
    if dialog_manager.dialog_data.get("spaced_phrase"):
        phrase.spaced_phrase = dialog_manager.dialog_data.get("spaced_phrase")
    try:
        await phrase.save()
    except Exception as e:
        logger.error('Ошибка при сохранении фразы: %s', e)
        await callback.message.answer(text=i18n_format("failed-save-phrase"))
    else:
        await callback.message.answer(text=i18n_format("phrase-saved"))

    new_phrase = [phrase.text_phrase, phrase.id]

    await dialog_manager.done(result={"new_phrase": new_phrase}, show_mode=ShowMode.SEND)


async def edit_phrase_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await dialog_manager.start(state=EditPhraseSG.start, data=dialog_manager.dialog_data)


smart_phrase_addition_dialog = Dialog(
    Window(
        Multi(
            I18NFormat("selected-category"),
            I18NFormat("input-text-phrase"),
        ),
        TextInput(
            id="text_phrase_input",
            on_success=text_phrase_input,
        ),
        Group(
            Cancel(I18NFormat("cancel"), id="button_cancel"),
            width=3
        ),
        getter=get_data,
        state=SmartPhraseAdditionSG.start
    ),
    Window(
        Multi(
            I18NFormat("summary-information"),
        ),
        Button(
            text=I18NFormat('edit-phrase-button'),
            id='edit_phrase',
            on_click=edit_phrase_button_clicked,
        ),
        Group(
            Back(I18NFormat("back"), id="back"),
            Cancel(I18NFormat("cancel"), id="button_cancel"),
            Button(
                text=I18NFormat("save"),
                id="save_phrase",
                on_click=save_phrase_button_clicked,
            ),
            width=3
        ),
        getter=get_summary_data,
        state=SmartPhraseAdditionSG.save
    ),
)
