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
from external_services.kandinsky import generate_image
from models import Phrase, Category, AudioFile, User
from services.i18n_format import I18NFormat, I18N_FORMAT_KEY
from services.phrase_service import process_new_phrase
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
    text_phrase = text_phrase.strip()
    if len(text_phrase) >= 150:
        await message.answer(i18n_format('sentence-too-long'))
    else:
        # Check for duplicates (case-insensitive)
        phrase = await Phrase.filter(text_phrase__iexact=text_phrase, user_id=message.from_user.id).first()
        if phrase:
            await message.answer(i18n_format("already-added-this-phrase"))
        else:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
            spaced_phrase, translation, voice, voice_id = await process_new_phrase(text_phrase)

            if voice:
                msg = await message.answer_voice(voice=voice, caption=i18n_format("voice-acting"))
                voice_id = msg.voice.file_id

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
