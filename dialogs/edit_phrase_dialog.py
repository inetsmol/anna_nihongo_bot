import base64
import logging

from aiogram.enums import ContentType
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.input import TextInput, MessageInput, ManagedTextInput
from aiogram_dialog.widgets.kbd import Group, Cancel, Button
from aiogram_dialog.widgets.text import Multi
from dotenv import load_dotenv

from bot_init import bot
from dialogs.getters.get_edit_phrase_data import get_data
from external_services.google_cloud_services import google_text_to_speech
from external_services.kandinsky import generate_image
from external_services.openai_services import openai_gpt_add_space
from models import Phrase, AudioFile
from services.i18n_format import I18NFormat, I18N_FORMAT_KEY
from states import EditPhraseSG, ManagementSG

load_dotenv()
logger = logging.getLogger('default')


async def change_text_phrase_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await dialog_manager.switch_to(EditPhraseSG.text_phrase)


async def input_text_phrase(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text_phrase: str):
    dialog_manager.dialog_data["text_phrase"] = text_phrase
    try:
        spaced_phrase = await openai_gpt_add_space(text_phrase)
    except Exception as e:
        logger.error('Ошибка при попытке добавления пробелов: %s', e)
        spaced_phrase = text_phrase
    dialog_manager.dialog_data["spaced_phrase"] = spaced_phrase
    await dialog_manager.switch_to(EditPhraseSG.start)


async def change_translation_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await dialog_manager.switch_to(EditPhraseSG.translation)


async def input_translation(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, translation: str):
    dialog_manager.dialog_data["translation"] = translation
    await dialog_manager.switch_to(EditPhraseSG.start)


async def change_audio_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await dialog_manager.switch_to(EditPhraseSG.audio)


async def input_audio(message: Message, widget: MessageInput, dialog_manager: DialogManager):
    audio_id = message.audio.file_id if message.audio else message.voice.file_id
    dialog_manager.dialog_data["audio_id"] = audio_id
    await dialog_manager.switch_to(EditPhraseSG.start)


async def ai_voice_message(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    text_phrase = dialog_manager.dialog_data["text_phrase"]

    text_to_speech = await google_text_to_speech(text_phrase)
    voice = BufferedInputFile(text_to_speech.audio_content, filename="voice_tts.ogg")
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    msg = await callback.message.answer_voice(voice=voice, caption=i18n_format("new-voice-acting"))

    dialog_manager.dialog_data["audio_id"] = msg.voice.file_id
    dialog_manager.show_mode = ShowMode.SEND
    await dialog_manager.switch_to(EditPhraseSG.start)


async def change_image_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    image_id = dialog_manager.dialog_data["image_id"]
    msg = await callback.message.answer_photo(photo=image_id)
    dialog_manager.dialog_data["msg_photo_id"] = msg.message_id
    dialog_manager.show_mode = ShowMode.SEND
    await dialog_manager.switch_to(EditPhraseSG.image)


async def input_image(message: Message, widget: MessageInput, dialog_manager: DialogManager):
    image_id = message.photo[-1].file_id
    dialog_manager.dialog_data["image_id"] = image_id
    msg_photo_id = dialog_manager.dialog_data["msg_photo_id"]
    await bot.delete_message(chat_id=dialog_manager.event.from_user.id,
                             message_id=msg_photo_id)
    dialog_manager.show_mode = ShowMode.SEND
    await dialog_manager.switch_to(EditPhraseSG.start)


async def ai_image(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    prompt = dialog_manager.dialog_data["prompt"]
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    await callback.message.answer(i18n_format("starting-generate-image"))
    # Функция для генерации изображения автоматически
    try:
        images = await generate_image(prompt=prompt)
        if images and len(images) > 0:
            msg_photo_id = dialog_manager.dialog_data["msg_photo_id"]
            # Удаляем предыдущее изображение
            await bot.delete_message(chat_id=dialog_manager.event.from_user.id,
                                     message_id=msg_photo_id)
            # Декодируем изображение из Base64
            image_data = base64.b64decode(images[0])
            image = BufferedInputFile(image_data, filename="image.png")
            # Отправляем изображение
            msg = await callback.message.answer_photo(photo=image, caption=i18n_format("generated-image"))
            image_id = msg.photo[-1].file_id
            dialog_manager.dialog_data["image_id"] = image_id
            dialog_manager.dialog_data["msg_photo_id"] = msg.message_id

        else:
            await callback.message.answer(i18n_format("failed-generate-image"))
        dialog_manager.show_mode = ShowMode.SEND
        await dialog_manager.switch_to(EditPhraseSG.start)
    except Exception as e:
        await callback.message.answer(text=i18n_format("failed-generate-image"))
        dialog_manager.show_mode = ShowMode.SEND
        logger.error('Ошибка при генерации изображения: %s', e)


async def delite_image_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_manager.dialog_data.pop('image_id')
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    await callback.message.answer(i18n_format("deleted-image"))
    msg_photo_id = dialog_manager.dialog_data['msg_photo_id']
    dialog_manager.dialog_data.pop('msg_photo_id')
    await bot.delete_message(chat_id=dialog_manager.event.from_user.id,
                             message_id=msg_photo_id)
    dialog_manager.show_mode = ShowMode.SEND


async def change_comment_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await dialog_manager.switch_to(EditPhraseSG.comment)


async def input_comment(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, comment: str):
    dialog_manager.dialog_data["comment"] = comment
    await dialog_manager.switch_to(EditPhraseSG.start)


async def save_phrase_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    text_phrase = dialog_manager.dialog_data.get("text_phrase")
    spaced_phrase = dialog_manager.dialog_data.get("spaced_phrase")
    translation = dialog_manager.dialog_data.get("translation")
    audio_id = dialog_manager.dialog_data.get("audio_id")
    image_id = dialog_manager.dialog_data.get("image_id")
    comment = dialog_manager.dialog_data.get("comment")
    # Если редактируем существующую фразу
    if dialog_manager.dialog_data.get("phrase_id"):
        phrase = await Phrase.get(id=dialog_manager.dialog_data["phrase_id"])
    # Если редактируем новую фразу, добавляем фразу
    else:
        phrase = await Phrase.create(text_phrase=dialog_manager.start_data["text_phrase"],
                                     category_id=dialog_manager.start_data["category_id"],
                                     spaced_phrase=dialog_manager.start_data["spaced_phrase"],
                                     user_id=dialog_manager.event.from_user.id)

    if not translation:
        translation = dialog_manager.start_data.get("translation")
    if not audio_id:
        audio_id = dialog_manager.start_data.get("audio_tg_id")
    if not image_id:
        image_id = dialog_manager.start_data.get("image_id")
    if not comment:
        comment = dialog_manager.start_data.get("comment")

    if text_phrase:
        phrase.text_phrase = text_phrase
    if spaced_phrase:
        phrase.spaced_phrase = spaced_phrase
    if translation:
        phrase.translation = translation
    if audio_id:
        phrase.audio_id = audio_id
    if image_id:
        phrase.image_id = image_id
    if comment:
        phrase.comment = comment
    await phrase.save()
    # await dialog_manager.done()
    await dialog_manager.start(state=ManagementSG.select_phrase, data=dialog_manager.dialog_data)


async def back_button_clicked(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await dialog_manager.switch_to(EditPhraseSG.start)


edit_phrase_dialog = Dialog(
    Window(
        Multi(
            I18NFormat("summary-information-to-edit"),
        ),
        Button(
            text=I18NFormat('text-phrase-to-edit'),
            id="text_phrase",
            on_click=change_text_phrase_button_clicked,
        ),
        Button(
            text=I18NFormat('translation-to-edit'),
            id="translation",
            on_click=change_translation_button_clicked,
        ),
        Button(
            text=I18NFormat('audio-to-edit'),
            id="audio_id",
            on_click=change_audio_button_clicked,
        ),
        Button(
            text=I18NFormat('image-to-edit'),
            id="image_id",
            on_click=change_image_button_clicked,
        ),
        Button(
            text=I18NFormat('comment-to-edit'),
            id="comment",
            on_click=change_comment_button_clicked,
        ),
        Group(
            Cancel(I18NFormat("cancel"), id="button_cancel"),
            Button(
                text=I18NFormat("save"),
                id="save_phrase",
                on_click=save_phrase_button_clicked,
            ),
            width=3
        ),
        getter=get_data,
        state=EditPhraseSG.start
    ),
    Window(
        I18NFormat("send-text-phrase-to-edit"),
        TextInput(
            id='input_text_phrase',
            on_success=input_text_phrase,
        ),
        Button(I18NFormat("back"), id="back", on_click=back_button_clicked),
        getter=get_data,
        state=EditPhraseSG.text_phrase
    ),
    Window(
        I18NFormat("send-translation-to-edit"),
        TextInput(
            id='input_translation',
            on_success=input_translation,
        ),
        Button(I18NFormat("back"), id="back", on_click=back_button_clicked),
        getter=get_data,
        state=EditPhraseSG.translation
    ),
    Window(
        I18NFormat("send-audio-to-edit"),
        MessageInput(
            func=input_audio,
            content_types=[ContentType.AUDIO, ContentType.VOICE],
        ),
        Button(I18NFormat("voice-with-ai-button"), id="voice_message", on_click=ai_voice_message),
        Button(I18NFormat("back"), id="back", on_click=back_button_clicked),
        getter=get_data,
        state=EditPhraseSG.audio
    ),
    Window(
        I18NFormat("send-image-to-edit"),
        MessageInput(
            func=input_image,
            content_types=[ContentType.PHOTO],
        ),
        Button(
            I18NFormat("generate-image-button"),
            id="ai_image",
            on_click=ai_image,
            when='is_subscriber',
        ),
        Button(
            I18NFormat("delite-image-button"),
            id="delite_image",
            on_click=delite_image_button_clicked,
            when="msg_photo_id",
        ),
        Button(I18NFormat("back"), id="back", on_click=back_button_clicked),
        getter=get_data,
        state=EditPhraseSG.image
    ),
    Window(
        I18NFormat("send-comment-to-edit"),
        TextInput(
            id='input_comment',
            on_success=input_comment,
        ),
        Button(I18NFormat("back"), id="back", on_click=back_button_clicked),
        getter=get_data,
        state=EditPhraseSG.comment
    ),
)
